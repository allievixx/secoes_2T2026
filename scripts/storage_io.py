"""Publicação do snapshot JSON no Cloud Storage com as credenciais do ambiente."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from uuid import uuid4

INTEGER_FIELDS = {
    "cd_ibge", "zona", "secao", "eleitores", "aptos_1t", "abstencao_1t",
    "lula_1t", "flavio_1t", "outros_1t", "brancos_1t", "nulos_1t",
}
FLOAT_FIELDS = {"lat_1t", "lon_1t", "lat_2t", "lon_2t", "distancia_km"}
BOOLEAN_FIELDS = {"regiao_longe_da_urna"}
CONTENT_TYPES = {".zip": "application/zip", ".csv": "text/csv; charset=utf-8", ".json": "application/json; charset=utf-8"}


class StorageError(RuntimeError):
    """Publicação do snapshot no Cloud Storage não concluída."""


def target(config: dict[str, Any]) -> tuple[str, str]:
    bucket_name = config.get("bucket")
    object_name = config.get("object", "secoes_alteradas_2t_2026.json")
    if not isinstance(bucket_name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", bucket_name):
        raise StorageError("Nome de bucket Cloud Storage inválido ou não configurado")
    if not isinstance(object_name, str) or not object_name or any(ord(char) < 32 for char in object_name):
        raise StorageError("Nome de objeto Cloud Storage inválido")
    return bucket_name, object_name


def public_url(bucket_name: str, object_name: str) -> str:
    return f"https://storage.googleapis.com/{bucket_name}/{quote(object_name, safe='/')}"


def archive_sources(config: dict[str, Any]) -> tuple[str, list[str]]:
    """Prefixo e fontes arquivadas em cada execução; por padrão todos os arquivos do TSE."""
    prefix = str(config.get("archivePrefix", "fontes")).strip("/")
    names = config.get("archiveSources", ["changes", "registry", "votes", "details"])
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


def archive_source(path: Path, name: str, version: dict[str, Any], config: dict[str, Any]) -> str:
    """Sempre grava uma nova cópia, mesmo com SHA-256 idêntico; devolve o caminho gs://-relativo."""
    bucket_name, _ = target(config)
    prefix, _ = archive_sources(config)
    sha256 = str(version.get("sha256") or "")
    if len(sha256) != 64:
        raise StorageError(f"Fonte {name} sem SHA-256; cópia não arquivada")
    folder = f"{prefix}/{name}/"
    basename = Path(urlparse(str(version.get("url") or "")).path).name or path.name
    archived_at = datetime.now(timezone.utc)
    copy_id = f"{archived_at.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex}"
    object_name = f"{folder}{copy_id}-{_version_stamp(version)}-{sha256[:12]}-{basename}"

    try:
        from google.auth.exceptions import GoogleAuthError
        from google.api_core.exceptions import GoogleAPIError
        from google.cloud import storage
    except ImportError as exc:
        raise StorageError("Dependência google-cloud-storage não instalada") from exc

    try:
        bucket = storage.Client().bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.metadata = {k: str(v) for k, v in {
            "sha256": sha256, "source_url": version.get("url"), "last_modified": version.get("last_modified"),
            "etag": version.get("etag"), "downloaded_at": version.get("downloaded_at"),
            "archived_at": archived_at.isoformat(),
        }.items() if v}
        blob.cache_control = "public, max-age=31536000, immutable"
        blob.upload_from_filename(str(path), content_type=CONTENT_TYPES.get(Path(basename).suffix.lower(), "application/octet-stream"),
                                  checksum="crc32c", if_generation_match=0)
    except (GoogleAPIError, GoogleAuthError) as exc:
        raise StorageError(f"Falha ao arquivar fonte {name} em gs://{bucket_name}/{object_name}: {exc}") from exc
    return f"{bucket_name}/{object_name}"


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

    try:
        from google.auth.exceptions import GoogleAuthError
        from google.api_core.exceptions import GoogleAPIError, PreconditionFailed
        from google.cloud import storage
    except ImportError as exc:
        raise StorageError("Dependência google-cloud-storage não instalada") from exc

    object_path = f"{bucket_name}/{object_name}"
    bucket = storage.Client().bucket(bucket_name)
    current: dict[str, Any] = {
        "extracted_at": extracted_at.astimezone(timezone.utc).isoformat(),
        "rows": [typed_row(row, fields) for row in rows],
    }
    if source_versions:
        current["sources"] = source_versions
    # Releitura + merge após concorrência: nunca reenviar um histórico obsoleto.
    for attempt in range(5):
        try:
            _append_snapshot(bucket.blob(object_name), current, fields)
            return object_path
        except PreconditionFailed as exc:
            if attempt == 4:
                raise StorageError(f"Conflitos concorrentes ao publicar gs://{object_path}; histórico preservado") from exc
        except (GoogleAPIError, GoogleAuthError) as exc:
            raise StorageError(f"Falha ao publicar gs://{object_path}: {exc}") from exc
    raise StorageError(f"Publicação não concluída: gs://{object_path}")


def _snapshot_time(snapshot: dict[str, Any]) -> datetime:
    try:
        instant = datetime.fromisoformat(snapshot["extracted_at"].replace("Z", "+00:00"))
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise StorageError("Data inválida no histórico publicado; publicação cancelada") from exc
    if instant.utcoffset() is None:
        raise StorageError("Data sem fuso no histórico publicado; publicação cancelada")
    return instant.astimezone(timezone.utc)


def _append_snapshot(blob: Any, current: dict[str, Any], fields: list[str]) -> None:
    """Acrescenta atomicamente sem reprocessar ou substituir extrações anteriores."""
    try:
        snapshots = []
        generation = 0
        if blob.exists():
            blob.reload()
            generation = blob.generation
            previous = json.loads(blob.download_as_text(if_generation_match=generation))
            if isinstance(previous, dict) and isinstance(previous.get("snapshots"), list):
                snapshots = previous["snapshots"]
                for snapshot in snapshots:
                    if (not isinstance(snapshot, dict)
                        or not isinstance(snapshot.get("extracted_at"), str)
                        or not isinstance(snapshot.get("rows"), list)
                        or not snapshot["rows"]):
                        raise StorageError("Histórico publicado inválido; publicação cancelada para preservar os dados")
                    _snapshot_time(snapshot)
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
        for snapshot in snapshots:
            if _snapshot_time(snapshot) == _snapshot_time(current):
                if snapshot["rows"] == current["rows"] and snapshot.get("sources") == current.get("sources"):
                    return  # Retry de uma publicação já concluída: não duplica.
                raise StorageError("Extrações diferentes no mesmo instante; histórico não foi substituído")
        snapshots.append(current)
        snapshots.sort(key=_snapshot_time)
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
    except json.JSONDecodeError as exc:
        raise StorageError("JSON publicado inválido; publicação cancelada para preservar o histórico") from exc
