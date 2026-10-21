"""Publicação do snapshot JSON no Cloudflare R2 (ou Cloud Storage) com as credenciais do ambiente."""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

INTEGER_FIELDS = {
    "cd_ibge", "zona", "secao", "eleitores", "aptos_1t", "abstencao_1t",
    "lula_1t", "flavio_1t", "outros_1t", "brancos_1t", "nulos_1t",
}
FLOAT_FIELDS = {"lat_1t", "lon_1t", "lat_2t", "lon_2t", "distancia_km"}
BOOLEAN_FIELDS = {"regiao_longe_da_urna"}
CONTENT_TYPES = {".zip": "application/zip", ".csv": "text/csv; charset=utf-8", ".json": "application/json; charset=utf-8"}


class StorageError(RuntimeError):
    """Publicação do snapshot não concluída."""


def is_r2_configured(config: dict[str, Any] | None = None) -> bool:
    """Verifica se credenciais ou configurações do Cloudflare R2 estão presentes."""
    cfg = config or {}
    if os.environ.get("R2_ACCESS_KEY_ID") or os.environ.get("R2_BUCKET_NAME"):
        return True
    if cfg.get("backend") == "r2" or cfg.get("r2"):
        return True
    return False


def target(config: dict[str, Any]) -> tuple[str, str]:
    if is_r2_configured(config):
        bucket_name = (
            os.environ.get("R2_BUCKET_NAME")
            or (config.get("r2") or {}).get("bucket")
            or config.get("bucket")
        )
    else:
        bucket_name = config.get("bucket")
    object_name = os.environ.get("R2_OBJECT_NAME") or config.get("object", "secoes_alteradas_2t_2026.json")

    if not isinstance(bucket_name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", bucket_name):
        raise StorageError("Nome de bucket inválido ou não configurado")
    if not isinstance(object_name, str) or not object_name or any(ord(char) < 32 for char in object_name):
        raise StorageError("Nome de objeto inválido")
    return bucket_name, object_name


def public_url(bucket_name: str, object_name: str) -> str:
    r2_public = os.environ.get("R2_PUBLIC_URL")
    if r2_public:
        return f"{r2_public.rstrip('/')}/{quote(object_name, safe='/')}"
    if is_r2_configured():
        account_id = os.environ.get("R2_ACCOUNT_ID")
        if account_id:
            return f"https://{bucket_name}.{account_id}.r2.cloudflarestorage.com/{quote(object_name, safe='/')}"
        return f"r2://{bucket_name}/{quote(object_name, safe='/')}"
    return f"https://storage.googleapis.com/{bucket_name}/{quote(object_name, safe='/')}"


def archive_sources(config: dict[str, Any]) -> tuple[str, list[str]]:
    """Prefixo e nomes das fontes cujas cópias são guardadas no bucket; por padrão só a lista de alterações."""
    prefix = str(config.get("archivePrefix", "fontes")).strip("/")
    names = config.get("archiveSources", ["changes"])
    if not prefix or not isinstance(names, list) or any(not isinstance(n, str) or not n for n in names):
        raise StorageError("archivePrefix deve ser um texto e archiveSources uma lista de nomes de fontes")
    return prefix, names


def _version_stamp(version: dict[str, Any]) -> str:
    """Instante da versão da fonte, em UTC compacto: Last-Modified do TSE ou, na falta, o momento do download."""
    for key, parse in (("last_modified", parsedate_to_datetime), ("downloaded_at", datetime.fromisoformat)):
        value = version.get(key)
        if value:
            try:
                return parse(value).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            except (TypeError, ValueError):
                continue
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def get_r2_client(config: dict[str, Any] | None = None):
    """Inicializa o cliente S3 apontando para o endpoint do Cloudflare R2."""
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise StorageError("Dependência boto3 não instalada para Cloudflare R2") from exc

    cfg = config or {}
    account_id = os.environ.get("R2_ACCOUNT_ID") or cfg.get("r2_account_id") or (cfg.get("r2") or {}).get("account_id")
    access_key = os.environ.get("R2_ACCESS_KEY_ID") or cfg.get("r2_access_key_id") or (cfg.get("r2") or {}).get("access_key_id")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY") or cfg.get("r2_secret_access_key") or (cfg.get("r2") or {}).get("secret_access_key")
    endpoint = os.environ.get("R2_ENDPOINT_URL") or cfg.get("r2_endpoint_url") or (cfg.get("r2") or {}).get("endpoint_url")

    if not endpoint and account_id:
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    if not endpoint:
        raise StorageError("Cloudflare R2 requer R2_ACCOUNT_ID ou R2_ENDPOINT_URL")
    if not access_key or not secret_key:
        raise StorageError("Cloudflare R2 requer R2_ACCESS_KEY_ID e R2_SECRET_ACCESS_KEY")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def _archive_source_r2(
    path: Path,
    name: str,
    version: dict[str, Any],
    config: dict[str, Any],
    bucket_name: str,
) -> str:
    try:
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:
        raise StorageError("Dependência botocore não instalada para Cloudflare R2") from exc

    prefix, _ = archive_sources(config)
    sha256 = str(version.get("sha256") or "")
    if len(sha256) != 64:
        raise StorageError(f"Fonte {name} sem SHA-256; cópia não arquivada")
    folder = f"{prefix}/{name}/"
    basename = Path(urlparse(str(version.get("url") or "")).path).name or path.name
    object_name = f"{folder}{_version_stamp(version)}-{sha256[:12]}-{basename}"

    s3 = get_r2_client(config)
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name, Prefix=folder):
            for item in page.get("Contents", []):
                head = s3.head_object(Bucket=bucket_name, Key=item["Key"])
                if (head.get("Metadata") or {}).get("sha256") == sha256:
                    return f"{bucket_name}/{item['Key']}"

        s3.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=path.read_bytes(),
            ContentType=CONTENT_TYPES.get(Path(basename).suffix.lower(), "application/octet-stream"),
            Metadata={
                k: str(v) for k, v in {
                    "sha256": sha256,
                    "source_url": version.get("url"),
                    "last_modified": version.get("last_modified"),
                    "etag": version.get("etag"),
                    "downloaded_at": version.get("downloaded_at"),
                }.items() if v
            },
            CacheControl="public, max-age=31536000, immutable",
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageError(f"Falha ao arquivar fonte {name} em r2://{bucket_name}/{object_name}: {exc}") from exc

    return f"{bucket_name}/{object_name}"


def _archive_source_gcs(
    path: Path,
    name: str,
    version: dict[str, Any],
    config: dict[str, Any],
    bucket_name: str,
) -> str:
    prefix, _ = archive_sources(config)
    sha256 = str(version.get("sha256") or "")
    if len(sha256) != 64:
        raise StorageError(f"Fonte {name} sem SHA-256; cópia não arquivada")
    folder = f"{prefix}/{name}/"
    basename = Path(urlparse(str(version.get("url") or "")).path).name or path.name
    object_name = f"{folder}{_version_stamp(version)}-{sha256[:12]}-{basename}"

    try:
        from google.auth.exceptions import GoogleAuthError
        from google.api_core.exceptions import GoogleAPIError
        from google.cloud import storage
    except ImportError as exc:
        raise StorageError("Dependência google-cloud-storage não instalada") from exc

    try:
        bucket = storage.Client().bucket(bucket_name)
        for blob in bucket.list_blobs(prefix=folder):
            if (blob.metadata or {}).get("sha256") == sha256:
                return f"{bucket_name}/{blob.name}"
        blob = bucket.blob(object_name)
        blob.metadata = {k: str(v) for k, v in {
            "sha256": sha256, "source_url": version.get("url"), "last_modified": version.get("last_modified"),
            "etag": version.get("etag"), "downloaded_at": version.get("downloaded_at"),
        }.items() if v}
        blob.cache_control = "public, max-age=31536000, immutable"
        blob.upload_from_filename(str(path), content_type=CONTENT_TYPES.get(Path(basename).suffix.lower(), "application/octet-stream"),
                                  checksum="crc32c", if_generation_match=0)
    except (GoogleAPIError, GoogleAuthError) as exc:
        raise StorageError(f"Falha ao arquivar fonte {name} em gs://{bucket_name}/{object_name}: {exc}") from exc
    return f"{bucket_name}/{object_name}"


def archive_source(path: Path, name: str, version: dict[str, Any], config: dict[str, Any]) -> str:
    """Guarda uma cópia do arquivo-fonte no bucket, uma por versão (SHA-256)."""
    bucket_name, _ = target(config)
    if is_r2_configured(config):
        return _archive_source_r2(path, name, version, config, bucket_name)
    return _archive_source_gcs(path, name, version, config, bucket_name)


def typed_row(row: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in fields:
        value = row[name]
        if value is None or value == "":
            result[name] = None
        elif name in BOOLEAN_FIELDS:
            if isinstance(value, bool):
                result[name] = value
            elif str(value).lower() in {"true", "false"}:
                result[name] = str(value).lower() == "true"
            else:
                raise StorageError(f"Booleano inválido: {name}")
        elif name in INTEGER_FIELDS:
            if isinstance(value, bool):
                raise StorageError(f"Inteiro inválido: {name}")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise StorageError(f"Inteiro inválido: {name}") from exc
            if not math.isfinite(number) or number != int(number):
                raise StorageError(f"Inteiro inválido: {name}")
            result[name] = int(number)
        elif name in FLOAT_FIELDS:
            if isinstance(value, bool):
                raise StorageError(f"Número inválido: {name}")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise StorageError(f"Número inválido: {name}") from exc
            if not math.isfinite(number):
                raise StorageError(f"Número não finito: {name}")
            result[name] = number
        else:
            result[name] = str(value)
    return result


def _publish_json_r2(
    bucket_name: str,
    object_name: str,
    rows: list[dict[str, Any]],
    fields: list[str],
    config: dict[str, Any],
    extracted_at: datetime,
    source_versions: dict[str, Any] | None,
) -> str:
    try:
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:
        raise StorageError("Dependência botocore não instalada para Cloudflare R2") from exc

    s3 = get_r2_client(config)
    object_path = f"{bucket_name}/{object_name}"
    snapshots = []

    try:
        response = s3.get_object(Bucket=bucket_name, Key=object_name)
        content = response["Body"].read().decode("utf-8")
        previous = json.loads(content)
        if isinstance(previous, dict) and isinstance(previous.get("snapshots"), list):
            snapshots = previous["snapshots"]
            for snapshot in snapshots:
                if (not isinstance(snapshot, dict)
                    or not isinstance(snapshot.get("extracted_at"), str)
                    or not isinstance(snapshot.get("rows"), list)
                    or not snapshot["rows"]):
                    raise StorageError("Histórico publicado inválido; publicação cancelada para preservar os dados")
                try:
                    old_extracted_at = datetime.fromisoformat(snapshot["extracted_at"].replace("Z", "+00:00"))
                except ValueError as exc:
                    raise StorageError("Data inválida no histórico publicado; publicação cancelada") from exc
                if old_extracted_at.utcoffset() is None:
                    raise StorageError("Data sem fuso no histórico publicado; publicação cancelada")
                snapshot["extracted_at"] = old_extracted_at.astimezone(timezone.utc).isoformat()
                snapshot["rows"] = [typed_row(row, fields) for row in snapshot["rows"]]
        elif isinstance(previous, dict) and isinstance(previous.get("rows"), list):
            last_modified = response.get("LastModified")
            old_extracted_at = last_modified if isinstance(last_modified, datetime) else None
            if old_extracted_at is None:
                raise StorageError("O snapshot legado não tem data de atualização; histórico não foi alterado")
            if old_extracted_at.tzinfo is None:
                old_extracted_at = old_extracted_at.replace(tzinfo=timezone.utc)
            snapshots = [{
                "extracted_at": old_extracted_at.isoformat(),
                "rows": [typed_row(row, fields) for row in previous["rows"]],
            }]
        else:
            raise StorageError("Formato JSON publicado inválido; publicação cancelada para preservar os dados")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404"):
            snapshots = []
        else:
            raise StorageError(f"Falha ao consultar r2://{object_path}: {exc}") from exc
    except BotoCoreError as exc:
        raise StorageError(f"Falha de conexão com r2://{object_path}: {exc}") from exc

    current: dict[str, Any] = {
        "extracted_at": extracted_at.astimezone(timezone.utc).isoformat(),
        "rows": [typed_row(row, fields) for row in rows],
    }
    if source_versions:
        current["sources"] = source_versions
    snapshots = [snapshot for snapshot in snapshots if snapshot["extracted_at"] != current["extracted_at"]]
    snapshots.append(current)
    snapshots.sort(key=lambda snapshot: snapshot["extracted_at"])
    payload = json.dumps(
        {"snapshots": snapshots},
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )

    try:
        s3.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=payload.encode("utf-8"),
            ContentType="application/json; charset=utf-8",
            CacheControl="public, max-age=60",
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageError(f"Falha ao publicar r2://{object_path}: {exc}") from exc

    return object_path


def _publish_json_gcs(
    bucket_name: str,
    object_name: str,
    rows: list[dict[str, Any]],
    fields: list[str],
    extracted_at: datetime,
    source_versions: dict[str, Any] | None,
) -> str:
    try:
        from google.auth.exceptions import GoogleAuthError
        from google.api_core.exceptions import GoogleAPIError
        from google.cloud import storage
    except ImportError as exc:
        raise StorageError("Dependência google-cloud-storage não instalada") from exc

    object_path = f"{bucket_name}/{object_name}"
    try:
        blob = storage.Client().bucket(bucket_name).blob(object_name)
        snapshots = []
        generation = 0
        if blob.exists():
            blob.reload()
            generation = blob.generation
            previous = json.loads(blob.download_as_text())
            if isinstance(previous, dict) and isinstance(previous.get("snapshots"), list):
                snapshots = previous["snapshots"]
                for snapshot in snapshots:
                    if (not isinstance(snapshot, dict)
                        or not isinstance(snapshot.get("extracted_at"), str)
                        or not isinstance(snapshot.get("rows"), list)
                        or not snapshot["rows"]):
                        raise StorageError("Histórico publicado inválido; publicação cancelada para preservar os dados")
                    try:
                        old_extracted_at = datetime.fromisoformat(snapshot["extracted_at"].replace("Z", "+00:00"))
                    except ValueError as exc:
                        raise StorageError("Data inválida no histórico publicado; publicação cancelada") from exc
                    if old_extracted_at.utcoffset() is None:
                        raise StorageError("Data sem fuso no histórico publicado; publicação cancelada")
                    snapshot["extracted_at"] = old_extracted_at.astimezone(timezone.utc).isoformat()
                    snapshot["rows"] = [typed_row(row, fields) for row in snapshot["rows"]]
            elif isinstance(previous, dict) and isinstance(previous.get("rows"), list):
                old_extracted_at = blob.updated
                if old_extracted_at is None:
                    raise StorageError("O snapshot legado não tem data de atualização; histórico não foi alterado")
                if old_extracted_at.tzinfo is None:
                    old_extracted_at = old_extracted_at.replace(tzinfo=timezone.utc)
                snapshots = [{
                    "extracted_at": old_extracted_at.isoformat(),
                    "rows": [typed_row(row, fields) for row in previous["rows"]],
                }]
            else:
                raise StorageError("Formato JSON publicado inválido; publicação cancelada para preservar os dados")
        current: dict[str, Any] = {
            "extracted_at": extracted_at.astimezone(timezone.utc).isoformat(),
            "rows": [typed_row(row, fields) for row in rows],
        }
        if source_versions:
            current["sources"] = source_versions
        snapshots = [snapshot for snapshot in snapshots if snapshot["extracted_at"] != current["extracted_at"]]
        snapshots.append(current)
        snapshots.sort(key=lambda snapshot: snapshot["extracted_at"])
        payload = json.dumps(
            {"snapshots": snapshots},
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        blob.cache_control = "public, max-age=60"
        blob.upload_from_string(
            payload,
            content_type="application/json; charset=utf-8",
            checksum="crc32c",
            if_generation_match=generation,
        )
    except (GoogleAPIError, GoogleAuthError) as exc:
        raise StorageError(f"Falha ao publicar gs://{object_path}: {exc}") from exc
    return object_path


def publish_json(
    rows: list[dict[str, Any]],
    fields: list[str],
    config: dict[str, Any],
    extracted_at: datetime,
    source_versions: dict[str, Any] | None = None,
) -> str:
    bucket_name, object_name = target(config)
    if not rows:
        raise StorageError("Publicação JSON vazia recusada para preservar o snapshot existente")
    if extracted_at.tzinfo is None or extracted_at.utcoffset() is None:
        raise StorageError("A data da extração deve incluir fuso horário")

    if is_r2_configured(config):
        return _publish_json_r2(bucket_name, object_name, rows, fields, config, extracted_at, source_versions)
    return _publish_json_gcs(bucket_name, object_name, rows, fields, extracted_at, source_versions)
