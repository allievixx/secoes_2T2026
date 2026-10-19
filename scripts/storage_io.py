"""Publicação do snapshot JSON no Cloud Storage com as credenciais do ambiente."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

INTEGER_FIELDS = {
    "cd_ibge", "zona", "secao", "eleitores", "aptos_1t", "abstencao_1t",
    "lula_1t", "flavio_1t", "outros_1t", "brancos_1t", "nulos_1t",
}
FLOAT_FIELDS = {"lat_1t", "lon_1t", "lat_2t", "lon_2t", "distancia_km"}
BOOLEAN_FIELDS = {"regiao_longe_da_urna"}


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
) -> str:
    bucket_name, object_name = target(config)
    if not rows:
        raise StorageError("Publicação JSON vazia recusada para preservar o snapshot existente")
    if extracted_at.tzinfo is None or extracted_at.utcoffset() is None:
        raise StorageError("A data da extração deve incluir fuso horário")

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
        current = {
            "extracted_at": extracted_at.astimezone(timezone.utc).isoformat(),
            "rows": [typed_row(row, fields) for row in rows],
        }
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
