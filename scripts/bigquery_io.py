"""BigQuery via CLI já autenticada; nenhuma credencial é enviada ao frontend."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

INTEGER_FIELDS = {"cd_ibge", "zona", "secao", "eleitores", "aptos_1t", "abstencao_1t",
                  "lula_1t", "flavio_1t", "outros_1t", "brancos_1t", "nulos_1t"}
FLOAT_FIELDS = {"lat_1t", "lon_1t", "lat_2t", "lon_2t", "distancia_km"}
BOOLEAN_FIELDS = {"regiao_longe_da_urna", "entrou_desde_15_10"}


class BigQueryError(RuntimeError):
    """Carga ou consulta não concluída."""


def target(config: dict[str, Any]) -> tuple[str, str, str, str]:
    project = config.get("project", "comite-tecnologia")
    dataset = config.get("dataset", "alteracao_locais_votacao")
    table = config.get("table", "secoes_alteradas_2t_2026")
    location = config.get("location", "US")
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", project):
        raise BigQueryError("Identificador de projeto BigQuery inválido")
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,1023}", value) for value in [dataset, table]):
        raise BigQueryError("Identificador de dataset/tabela BigQuery inválido")
    if not re.fullmatch(r"[A-Za-z0-9-]+", location):
        raise BigQueryError("Localização BigQuery inválida")
    return project, dataset, table, location


def schema(fields: list[str]) -> list[dict[str, str]]:
    return [{"name":name, "type":"INTEGER" if name in INTEGER_FIELDS else "FLOAT" if name in FLOAT_FIELDS else "BOOLEAN" if name in BOOLEAN_FIELDS else "STRING", "mode":"NULLABLE"} for name in fields]


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
                raise BigQueryError(f"Booleano inválido: {name}")
        elif name in INTEGER_FIELDS:
            if isinstance(value, bool) or float(value) != int(value):
                raise BigQueryError(f"Inteiro inválido: {name}")
            result[name] = int(value)
        elif name in FLOAT_FIELDS:
            number = float(value)
            if not math.isfinite(number):
                raise BigQueryError(f"Número não finito: {name}")
            result[name] = number
        else:
            result[name] = str(value)
    return result


def run_bq(config: dict[str, Any], arguments: list[str], timeout: int = 600) -> str:
    project, _, _, location = target(config)
    command = ["bq", f"--project_id={project}", f"--location={location}", "--quiet", *arguments]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise BigQueryError("CLI bq não encontrada no PATH. Use a instalação do Google Cloud CLI já autenticada.") from exc
    except subprocess.TimeoutExpired as exc:
        raise BigQueryError("A operação no BigQuery excedeu o tempo limite; confira o job antes de repetir.") from exc
    if completed.returncode:
        raise BigQueryError((completed.stderr or completed.stdout or "Operação BigQuery falhou").strip())
    return completed.stdout


def publish(rows: list[dict[str, Any]], fields: list[str], config: dict[str, Any]) -> str:
    """Load job substitui atomicamente o snapshot, sem DELETE ou streaming parcial."""
    if not rows:
        raise BigQueryError("Carga vazia recusada para não apagar o snapshot existente")
    project, dataset, table, _ = target(config)
    with tempfile.TemporaryDirectory(prefix="secoes-bq-") as directory:
        source, definition = Path(directory)/"rows.ndjson", Path(directory)/"schema.json"
        with source.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(typed_row(row, fields), ensure_ascii=False, allow_nan=False)+"\n")
        definition.write_text(json.dumps(schema(fields)), encoding="utf-8")
        run_bq(config, ["load", "--replace", "--source_format=NEWLINE_DELIMITED_JSON",
                        "--max_bad_records=0", f"{project}:{dataset}.{table}", str(source), str(definition)])
    return f"{project}.{dataset}.{table}"


def read_rows(config: dict[str, Any], fields: list[str], maximum_rows: int = 100000) -> list[dict[str, Any]]:
    project, dataset, table, _ = target(config)
    # SQL fixo e identificadores validados; o navegador não pode enviar SQL.
    projection = ", ".join(f"`{field}`" for field in fields)
    sql = f"SELECT {projection} FROM `{project}.{dataset}.{table}` ORDER BY uf, cd_ibge, zona, secao LIMIT {maximum_rows + 1}"
    result = json.loads(run_bq(config, ["query", "--use_legacy_sql=false", "--format=json",
                                     f"--max_rows={maximum_rows + 1}", "--maximum_bytes_billed=100000000", sql], timeout=25))
    if not isinstance(result, list):
        raise BigQueryError("Resposta BigQuery inválida")
    if len(result) > maximum_rows:
        raise BigQueryError("Quantidade de linhas excede o limite da API; não será retornado um snapshot truncado")
    return [typed_row(row, fields) for row in result]