#!/usr/bin/env python3
"""Cruza fontes TSE/IBGE e publica o snapshot no Cloud Storage ou em CSV."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import logging
import math
import os
import re
import sys
import tempfile
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

if __package__:
    from .storage_io import StorageError, archive_source, archive_sources, public_url, publish_json, target as storage_target
else:
    from storage_io import StorageError, archive_source, archive_sources, public_url, publish_json, target as storage_target

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger("gerar_dados")
FIELDS = [
    "uf", "municipio", "cd_ibge", "zona", "secao", "eleitores",
    "local_1t", "endereco_1t", "lat_1t", "lon_1t", "local_2t", "endereco_2t",
    "bairro_2t", "lat_2t", "lon_2t", "distancia_km", "regiao_longe_da_urna",
    "aptos_1t", "abstencao_1t", "lula_1t", "flavio_1t",
    "outros_1t", "brancos_1t", "nulos_1t",
]
CHANGES = {"AA_ELEICAO", "SG_UF", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO",
           "NM_LOCAL_VOTACAO_INICIAL", "NM_LOCAL_VOTACAO_FINAL", "QT_ELEITORES"}
REGISTRY = {"AA_ELEICAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO",
            "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO",
            "DS_ENDERECO", "NM_BAIRRO", "NR_LATITUDE", "NR_LONGITUDE",
            "NR_LOCAL_VOTACAO_ORIGINAL", "NM_LOCAL_VOTACAO_ORIGINAL",
            "DS_ENDERECO_LOCVT_ORIGINAL"}
RESULT_KEY = {"ANO_ELEICAO", "NR_TURNO", "CD_CARGO", "SG_UF", "CD_MUNICIPIO",
              "NR_ZONA", "NR_SECAO"}
Section = tuple[str, str, int, int]


class DataError(ValueError):
    """Fonte incompleta, ambígua ou incompatível com o contrato."""


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.upper())
    return re.sub(r"[^A-Z0-9]", "", "".join(c for c in value if not unicodedata.combining(c)))


def integer(value: str, label: str) -> int:
    try:
        result = int(value)
    except (ValueError, TypeError) as exc:
        raise DataError(f"{label}: inteiro inválido {value!r}") from exc
    if result < 0:
        raise DataError(f"{label}: valor negativo {value!r}")
    return result


def coordinate(value: str, latitude: bool) -> float | None:
    if value.strip() in {"", "-1", "-3", "#NULO", "#NE"}:
        return None
    try:
        number = float(value.replace(",", "."))
    except ValueError as exc:
        raise DataError(f"Coordenada inválida: {value!r}") from exc
    if not math.isfinite(number) or abs(number) > (90 if latitude else 180):
        raise DataError(f"Coordenada fora dos limites: {value!r}")
    return number


def point(row: dict[str, str]) -> tuple[float, float] | None:
    lat, lon = coordinate(row["NR_LATITUDE"], True), coordinate(row["NR_LONGITUDE"], False)
    return (lat, lon) if lat is not None and lon is not None else None


def haversine(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float | None:
    if a is None or b is None:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return round(6371.0088 * 2 * math.asin(math.sqrt(min(1.0, h))), 3)


def key(row: dict[str, str], municipal_name: bool = False) -> Section:
    municipality = normalize(row["NM_MUNICIPIO"]) if municipal_name else str(integer(row["CD_MUNICIPIO"], "CD_MUNICIPIO"))
    return row["SG_UF"].upper(), municipality, integer(row["NR_ZONA"], "NR_ZONA"), integer(row["NR_SECAO"], "NR_SECAO")


def resolve_source(source: str, base: Path) -> str:
    return source if urllib.parse.urlparse(source).scheme in {"http", "https"} else str((base / source).resolve())


def source_version(path: Path) -> dict[str, Any]:
    """Versão da fonte gravada ao lado do arquivo baixado; fontes locais só informam tamanho e SHA-256."""
    sidecar = path.with_name(path.name + ".meta.json")
    if sidecar.is_file():
        return json.loads(sidecar.read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""):
            digest.update(chunk)
    return {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def download(source: str, cache: Path, refresh: bool = False) -> Path:
    """Cache por URL, download em disco e publicação atômica; sem carregar ZIP em RAM."""
    if urllib.parse.urlparse(source).scheme not in {"http", "https"}:
        path = Path(source)
        if not path.is_file():
            raise DataError(f"Fonte local não encontrada: {path}")
        return path
    cache.mkdir(parents=True, exist_ok=True)
    basename = Path(urllib.parse.urlparse(source).path).name or "source"
    destination = cache / (hashlib.sha256(source.encode()).hexdigest()[:16] + "-" + basename)
    if destination.exists() and not refresh:
        LOGGER.info("Usando cache: %s", destination.name)
        return destination
    LOGGER.info("Baixando %s", source)
    temporary: Path | None = None
    try:
        request = urllib.request.Request(source, headers={"User-Agent": "secoes-dashboard/1.0", "Accept-Encoding": "identity"})
        digest = hashlib.sha256()
        with urllib.request.urlopen(request, timeout=120) as response:
            expected = response.headers.get("Content-Length")
            # O TSE sobrescreve alguns ZIPs na mesma URL; Last-Modified/ETag/SHA-256 identificam a versão usada.
            version = {
                "url": source,
                "last_modified": response.headers.get("Last-Modified"),
                "etag": response.headers.get("ETag"),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
            }
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as handle:
                temporary = Path(handle.name)
                for chunk in iter(lambda: response.read(1024*1024), b""):
                    digest.update(chunk)
                    handle.write(chunk)
        if expected and temporary.stat().st_size != int(expected):
            raise DataError(f"Download incompleto: {source}")
        version.update(sha256=digest.hexdigest(), bytes=temporary.stat().st_size)
        write_json(destination.with_name(destination.name + ".meta.json"), version)
        temporary.replace(destination)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def csv_stream(raw: Any, encoding: str) -> Iterator[csv.DictReader]:
    # UTF-8 BOM e nomes minúsculos aparecem em algumas exportações do TSE.
    with io.TextIOWrapper(raw, encoding=encoding, newline="") as text:
        reader = csv.DictReader(text, delimiter=";")
        if reader.fieldnames is None:
            raise DataError("CSV sem cabeçalho")
        reader.fieldnames = [name.lstrip("\ufeff").strip().upper() for name in reader.fieldnames]
        yield reader


def iter_csv(path: Path, required: set[str], encoding: str = "cp1252", ufs: set[str] | None = None) -> Iterator[dict[str, str]]:
    def records(raw: Any, name: str) -> Iterator[dict[str, str]]:
        with csv_stream(raw, encoding) as reader:
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise DataError(f"{name}: colunas ausentes: {', '.join(sorted(missing))}")
            for line, row in enumerate(reader, 2):
                if None in row or any(value is None for value in row.values()):
                    raise DataError(f"{name}:{line}: número incorreto de campos")
                yield {name: value.strip() for name, value in row.items()}

    if not zipfile.is_zipfile(path):
        with path.open("rb") as raw:
            yield from records(raw, str(path))
        return
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX/")]
        if not names:
            raise DataError(f"ZIP sem CSV: {path}")
        # BRASIL/nacional e UFs no mesmo ZIP não podem ser somados duas vezes.
        national = [n for n in names if re.search(r"_(BRASIL|BR)\.csv$", n, re.I)]
        if national:
            names = national[:1]
        elif ufs:
            names = [n for n in names if not re.search(r"_[A-Z]{2}\.csv$", n, re.I) or Path(n).stem[-2:].upper() in ufs]
        for name in names:
            LOGGER.info("Lendo %s", name)
            with archive.open(name) as raw:
                yield from records(raw, name)


def load_changes(path: Path, encoding: str, year: int) -> dict[Section, dict[str, str]]:
    changes: dict[Section, dict[str, str]] = {}
    for row in iter_csv(path, CHANGES, encoding):
        if integer(row["AA_ELEICAO"], "AA_ELEICAO") != year:
            continue
        k = key(row, True)
        if k in changes:
            raise DataError(f"Seção duplicada na lista de alterações: {k}")
        integer(row["QT_ELEITORES"], "QT_ELEITORES")
        changes[k] = row
    if not changes:
        raise DataError("Nenhuma seção alterada encontrada para o ano configurado")
    return changes


def load_ibge(path: Path, overrides: dict[str, int]) -> dict[tuple[str, str], int]:
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    result: dict[tuple[str, str], int] = {}
    for row in json.loads(raw):
        # Municípios novos podem ainda não ter microrregião.
        uf = ((row.get("microrregiao") or {}).get("mesorregiao") or {}).get("UF")
        if not uf:
            uf = (((row.get("regiao-imediata") or {}).get("regiao-intermediaria") or {}).get("UF"))
        if not uf:
            raise DataError(f"IBGE: município sem UF: {row.get('id')}")
        result[(uf["sigla"], normalize(row["nome"]))] = int(row["id"])
    for label, code in overrides.items():
        uf, municipality = label.split(":", 1)
        if int(code) not in result.values():
            raise DataError(f"Override IBGE com código inexistente: {label}={code}")
        result[(uf.upper(), normalize(municipality))] = int(code)
    return result


def load_registry(path: Path, changes: dict[Section, dict[str, str]], encoding: str, year: int, allow_incomplete: bool = False):
    wanted = {(k[0], k[1], k[2]) for k in changes}
    sections: dict[Section, dict[str, str]] = {}
    locations: dict[tuple[str, str, int, str], list[dict[str, str]]] = defaultdict(list)
    names: dict[Section, set[Section]] = defaultdict(set)
    conflicts: set[Section] = set()
    # Assinaturas (nome, endereço, bairro, ponto) por local, em qualquer turno, para achar um local citado só
    # nas colunas *_ORIGINAL. A chave inclui a zona: NR_LOCAL_VOTACAO se repete entre zonas do mesmo município.
    places: dict[tuple[str, str, int, str], set[tuple[str, str, str, tuple[float, float] | None]]] = defaultdict(set)
    for row in iter_csv(path, REGISTRY, encoding, {k[0] for k in changes}):
        if integer(row["AA_ELEICAO"], "AA_ELEICAO") != year:
            continue
        named = key(row, True)
        if named[:3] not in wanted:
            continue
        k = key(row)
        if row["NR_LOCAL_VOTACAO"].isdigit():
            places[(*k[:3], str(int(row["NR_LOCAL_VOTACAO"])))].add((row["NM_LOCAL_VOTACAO"], row["DS_ENDERECO"], row["NM_BAIRRO"], point(row)))
        names[named].add(k)
        old = sections.get(k)
        rank = integer(row["NR_TURNO"], "NR_TURNO")
        if rank not in {1, 2}:
            continue
        if old is None or rank > integer(old["NR_TURNO"], "NR_TURNO"):
            sections[k] = row
            conflicts.discard(k)
        elif rank == integer(old["NR_TURNO"], "NR_TURNO") and any(old[c] != row[c] for c in REGISTRY - {"NR_TURNO"}):
            if not allow_incomplete:
                raise DataError(f"Cadastro conflitante para seção: {k}")
            conflicts.add(k)
    for k in conflicts:
        # Preservar a identidade para cruzar votos, mas nunca escolher um dos locais conflitantes.
        selected = sections[k]
        sections[k] = {c: selected[c] if c in {"AA_ELEICAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO"} else "" for c in REGISTRY}
        sections[k]["_CADASTRO_CONFLITANTE"] = "1"
    # Uma entrada por local, em vez de todas as seções, mantém índices pequenos.
    seen: set[tuple[Any, ...]] = set()
    for k, row in sections.items():
        if k in conflicts:
            continue
        identity = (*k[:3], row["NR_LOCAL_VOTACAO"], row["NM_LOCAL_VOTACAO"], row["DS_ENDERECO"], row["NR_LATITUDE"], row["NR_LONGITUDE"])
        if identity not in seen:
            seen.add(identity)
            locations[(*k[:3], normalize(row["NM_LOCAL_VOTACAO"]))].append(row)
    return sections, locations, names, dict(places)


def find_location(candidates: list[dict[str, str]], label: str) -> dict[str, str] | None:
    if not candidates:
        return None
    signatures = {(r["NR_LOCAL_VOTACAO"], r["DS_ENDERECO"], point(r)) for r in candidates}
    if len(signatures) > 1:
        raise DataError(f"Local ambíguo no cadastro: {label}; não é seguro escolher pelas coordenadas")
    return candidates[0]


def load_results(votes: Path, details: Path, wanted: set[Section], encoding: str, year: int, lula: str, flavio: str):
    result: dict[Section, dict[str, int]] = {}
    presidential = lambda r: r["ANO_ELEICAO"] == str(year) and r["NR_TURNO"] == "1" and r["CD_CARGO"] == "1"
    for row in iter_csv(details, RESULT_KEY | {"QT_APTOS", "QT_ABSTENCOES", "QT_VOTOS_BRANCOS", "QT_VOTOS_NULOS"}, encoding, {k[0] for k in wanted}):
        if not presidential(row):
            continue
        k = key(row)
        if k not in wanted:
            continue
        values = {field: integer(row[column], column) for field, column in {
            "aptos_1t":"QT_APTOS", "abstencao_1t":"QT_ABSTENCOES",
            "brancos_1t":"QT_VOTOS_BRANCOS", "nulos_1t":"QT_VOTOS_NULOS",
        }.items()}
        if k in result and result[k] != values:
            raise DataError(f"Detalhe de votação conflitante para {k}")
        result[k] = values
    vote_totals: dict[Section, dict[str, int]] = {}
    seen: dict[tuple[Section, str], int] = {}
    for row in iter_csv(votes, RESULT_KEY | {"NR_VOTAVEL", "QT_VOTOS"}, encoding, {k[0] for k in wanted}):
        if not presidential(row):
            continue
        k = key(row)
        if k not in wanted:
            continue
        candidate = str(integer(row["NR_VOTAVEL"], "NR_VOTAVEL"))
        count = integer(row["QT_VOTOS"], "QT_VOTOS")
        identity = (k, candidate)
        if identity in seen:
            if seen[identity] != count:
                raise DataError(f"Votos conflitantes para {identity}")
            continue
        seen[identity] = count
        total = vote_totals.setdefault(k, {field:0 for field in ["lula_1t", "flavio_1t", "outros_1t", "brancos_1t", "nulos_1t"]})
        field = "lula_1t" if candidate == lula else "flavio_1t" if candidate == flavio else "brancos_1t" if candidate == "95" else "nulos_1t" if candidate == "96" else "outros_1t"
        if field == "outros_1t" and not 1 <= int(candidate) <= 99:
            raise DataError(f"Código de votável não reconhecido: {candidate}")
        total[field] += count
    for k, total in vote_totals.items():
        if k not in result:
            continue
        for field in ["brancos_1t", "nulos_1t"]:
            if total[field] != result[k][field]:
                raise DataError(f"{field} diverge entre votação e detalhe para {k}")
        if sum(total.values()) + result[k]["abstencao_1t"] != result[k]["aptos_1t"]:
            raise DataError(f"Votos + abstenções não fecham com aptos para {k}")
        result[k].update(total)
    return {k:v for k,v in result.items() if k in vote_totals}


def load_distances(path: Path, encoding: str) -> dict[tuple[str, str, int, str], float]:
    """Contrato explícito da base externa Longe da urna, não da mudança de local."""
    required = {"UF", "CD_MUNICIPIO", "ZONA", "NR_LOCAL_VOTACAO", "DISTANCIA_MEDIA_KM"}
    result: dict[tuple[str, str, int, str], float] = {}
    for row in iter_csv(path, required, encoding):
        k = (row["UF"].upper(), str(integer(row["CD_MUNICIPIO"], "CD_MUNICIPIO")), integer(row["ZONA"], "ZONA"), str(integer(row["NR_LOCAL_VOTACAO"], "NR_LOCAL_VOTACAO")))
        try:
            distance = float(row["DISTANCIA_MEDIA_KM"].replace(",", "."))
        except ValueError as exc:
            raise DataError(f"Distância média inválida para {k}") from exc
        if not math.isfinite(distance) or distance < 0:
            raise DataError(f"Distância média inválida para {k}")
        if k in result and result[k] != distance:
            raise DataError(f"Distância média conflitante para {k}")
        result[k] = distance
    return result


def resolve_final_from_original(registry: dict[str, str], k: Section, places: dict[tuple[str, str, int, str], set[Any]], named: Section, issues: list[str]):
    """Local final citado só nas colunas *_ORIGINAL: o TSE ainda não atualizou a linha do 2º turno."""
    local_id = registry["NR_LOCAL_VOTACAO_ORIGINAL"]
    if not local_id.isdigit():
        return None
    local_id = str(int(local_id))
    found = {"id": local_id, "address": registry["DS_ENDERECO_LOCVT_ORIGINAL"], "bairro": "", "point": None}
    # Só aceita o local se id e nome coincidirem na mesma zona; coordenadas divergentes ficam vazias.
    wanted_name = normalize(registry["NM_LOCAL_VOTACAO_ORIGINAL"])
    located = {s for s in places.get((*k[:3], local_id), set()) if s[3] is not None and normalize(s[0]) == wanted_name}
    points = {s[3] for s in located}
    if len(points) == 1:
        _, address, bairro, coordinates = sorted(located)[0]
        found.update(address=address or found["address"], bairro=bairro, point=coordinates)
    elif points:
        issues.append(f"{named}: local final só nas colunas originais do cadastro; coordenadas ambíguas, mantidas vazias")
    else:
        issues.append(f"{named}: local final só nas colunas originais do cadastro; sem coordenadas disponíveis")
    return found


def build_rows(changes, sections, locations, names, ibge, results, distances, places=None):
    places = places or {}
    output: list[dict[str, Any]] = []
    issues: list[str] = []
    for named, change in sorted(changes.items()):
        uf, municipality, zone, section = named
        row: dict[str, Any] = dict.fromkeys(FIELDS, "")
        row.update(uf=uf, municipio=change["NM_MUNICIPIO"], zona=zone, secao=section,
                   eleitores=integer(change["QT_ELEITORES"], "QT_ELEITORES"),
                   local_1t=change["NM_LOCAL_VOTACAO_INICIAL"], local_2t=change["NM_LOCAL_VOTACAO_FINAL"])
        code = ibge.get((uf, municipality))
        if code is None:
            raise DataError(f"Município não encontrado no IBGE: {uf}:{change['NM_MUNICIPIO']}; configure ibgeOverrides")
        row["cd_ibge"] = code
        candidates = names.get(named, set())
        if len(candidates) != 1:
            raise DataError(f"Seção sem correspondência única no cadastro TSE: {named}")
        k = next(iter(candidates))
        registry = sections[k]
        if registry.get("_CADASTRO_CONFLITANTE"):
            issues.append(f"{named}: cadastro conflitante; endereço, coordenadas e distância mantidos vazios")
            if k in results:
                row.update(results[k])
            else:
                issues.append(f"{named}: resultado de presidente no 1º turno incompleto/ausente")
            output.append(row)
            continue
        final_candidates = locations.get((*k[:3], normalize(row["local_2t"])), [])
        final = registry if normalize(registry["NM_LOCAL_VOTACAO"]) == normalize(row["local_2t"]) else find_location(final_candidates, str(named)+" final")
        original_id = registry["NR_LOCAL_VOTACAO_ORIGINAL"]
        old_candidates = locations.get((*k[:3], normalize(row["local_1t"])), [])
        if original_id.isdigit() and normalize(registry["NM_LOCAL_VOTACAO_ORIGINAL"]) == normalize(row["local_1t"]):
            old_candidates = [r for r in old_candidates if r["NR_LOCAL_VOTACAO"] == original_id]
            row["endereco_1t"] = registry["DS_ENDERECO_LOCVT_ORIGINAL"]
        old = find_location(old_candidates, str(named)+" inicial")
        if old:
            row["endereco_1t"] = old["DS_ENDERECO"]
        final_id: str | None = None
        final_point: tuple[float, float] | None = None
        if final:
            final_id, final_point = str(integer(final["NR_LOCAL_VOTACAO"], "NR_LOCAL_VOTACAO")), point(final)
            row.update(endereco_2t=final["DS_ENDERECO"], bairro_2t=final["NM_BAIRRO"])
        elif normalize(registry["NM_LOCAL_VOTACAO_ORIGINAL"]) == normalize(row["local_2t"]):
            found = resolve_final_from_original(registry, k, places, named, issues)
            if found:
                final_id, final_point = found["id"], found["point"]
                row.update(endereco_2t=found["address"], bairro_2t=found["bairro"])
        if final_id is None:
            issues.append(f"{named}: local final não encontrado na versão do cadastro")
        a, b = point(old) if old else None, final_point
        for suffix, coordinates in [("1t", a), ("2t", b)]:
            if coordinates:
                row[f"lat_{suffix}"], row[f"lon_{suffix}"] = coordinates
        distance = haversine(a, b)
        if distance is not None:
            row["distancia_km"] = distance
        if final_id is not None:
            local_key = (*k[:3], final_id)
            if local_key in distances:
                row["regiao_longe_da_urna"] = distances[local_key] >= 5
            elif distances:
                issues.append(f"{named}: distância média de moradores até o local final indisponível")
        if k in results:
            row.update(results[k])
        else:
            issues.append(f"{named}: resultado de presidente no 1º turno incompleto/ausente")
        output.append(row)
    return output, issues


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def write_output(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            writer = csv.DictWriter(handle, FIELDS, delimiter=";", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "pipeline-config.json")
    parser.add_argument("--destination", choices=["storage", "csv", "both"], default="storage",
                        help="storage publica no Cloud Storage; both também grava CSV")
    parser.add_argument("--output", type=Path, default=ROOT / "data/secoes_alteradas_2t_2026.csv")
    parser.add_argument("--report", type=Path, default=ROOT / "data/geracao-relatorio.json")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache/tse")
    parser.add_argument("--refresh", action="store_true", help="Baixar novamente URLs, ignorando cache")
    parser.add_argument("--overwrite", action="store_true", help="Permitir substituir saída existente, sem lê-la")
    parser.add_argument("--allow-incomplete", action="store_true", help="Permitir indicadores/resultados ausentes como campos vazios; nunca inventar False/zero")
    parser.add_argument("--inspect", action="store_true", help="Baixar somente alterações e informar cabeçalho/contagens, sem gerar saída")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    loki_handler = None
    try:
        from scripts.loki_logger import setup_loki_logging
        loki_handler = setup_loki_logging()
    except Exception:
        pass
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        configured_allow_incomplete = config.get("allowIncomplete", False)
        if not isinstance(configured_allow_incomplete, bool):
            raise DataError("allowIncomplete deve ser um booleano")
        allow_incomplete = args.allow_incomplete or configured_allow_incomplete
        if args.destination in {"storage", "both"}:
            storage_target(config.get("storage", {}))
            archive_sources(config.get("storage", {}))
        base, encoding, year = args.config.resolve().parent, config.get("encoding", "cp1252"), int(config.get("year", 2026))
        sources = config["sources"]
        source_paths: dict[str, Path] = {}
        def source(name: str) -> Path:
            source_paths[name] = download(resolve_source(sources[name], base), args.cache_dir, args.refresh)
            return source_paths[name]
        changes_path = source("changes")
        changes = load_changes(changes_path, encoding, year)
        if args.inspect:
            print(json.dumps({"secoes":len(changes), "eleitores":sum(integer(r["QT_ELEITORES"], "QT_ELEITORES") for r in changes.values()), "ufs":sorted({k[0] for k in changes}), "colunas":sorted(CHANGES)}, ensure_ascii=False, indent=2))
            return 0
        write_csv = args.destination in {"csv", "both"}
        if write_csv and args.output.exists() and not args.overwrite:
            raise DataError("A saída já existe; use --output para outro caminho ou --overwrite. O arquivo existente não será lido.")
        if args.output.resolve() == args.report.resolve():
            raise DataError("Saída e relatório devem ter caminhos diferentes")
        # Enriquecimento adiado pelo usuário: ausências viram NULL, sem bloquear a carga.
        distances = load_distances(source("longDistance"), config.get("longDistanceEncoding", "utf-8-sig")) if sources.get("longDistance") else {}
        ibge = load_ibge(source("municipalities"), config.get("ibgeOverrides", {}))
        sections, locations, names, places = load_registry(source("registry"), changes, encoding, year, allow_incomplete=allow_incomplete)
        wanted = {next(iter(names[k])) for k in changes if len(names.get(k, set())) == 1}
        candidates = config.get("candidates", {"lula":"13", "flavio":"22"})
        lula, flavio = str(integer(str(candidates["lula"]), "candidates.lula")), str(integer(str(candidates["flavio"]), "candidates.flavio"))
        if lula == flavio or any(not 1 <= int(n) <= 94 for n in [lula, flavio]):
            raise DataError("Números dos candidatos devem ser diferentes e estar entre 1 e 94")
        results = load_results(source("votes"), source("details"), wanted, encoding, year, lula, flavio)
        rows, issues = build_rows(changes, sections, locations, names, ibge, results, distances, places)
        generated_at = datetime.now(timezone.utc)
        source_versions = {name: {"source": sources[name], **source_version(path)} for name, path in source_paths.items()}
        report = {
            "generated_at":generated_at.isoformat(),
            "year":year, "sources":sources, "source_versions":source_versions, "candidates":candidates,
            "secoes":len(rows), "eleitores":sum(r["eleitores"] for r in rows),
            "municipios":len({r["cd_ibge"] for r in rows}),
            "sem_distancia_mudanca":sum(r["distancia_km"] == "" for r in rows),
            "campos_ausentes":{field:sum(r[field] == "" for r in rows) for field in FIELDS},
            "pendencias":issues, "publicado":False,
            "destination":args.destination,
            "allow_incomplete":allow_incomplete,
            "enriquecimentos_adiados":[name for name in ["longDistance"] if not sources.get(name)],
        }
        write_json(args.report, report)
        for issue in issues:
            LOGGER.warning("Pendência: %s", issue)
        if issues and not allow_incomplete:
            raise DataError(f"{len(issues)} pendências; saída preservada. Consulte {args.report}")
        if args.destination in {"storage", "both"}:
            storage_config = config.get("storage", {})
            # Cópia da fonte bruta por versão: o TSE sobrescreve a URL, e sem isso a versão usada se perde.
            _, archive_names = archive_sources(storage_config)
            for name in archive_names:
                if name not in source_paths:
                    continue
                try:
                    source_versions[name]["archived"] = archive_source(source_paths[name], name, source_versions[name], storage_config)
                    LOGGER.info("Fonte %s arquivada em %s", name, source_versions[name]["archived"])
                except StorageError as exc:
                    LOGGER.error("%s", exc)
                    report.setdefault("falhas_arquivamento", []).append(str(exc))
            report["storage_object"] = publish_json(rows, FIELDS, storage_config, generated_at, source_versions)
            bucket, object_name = storage_target(storage_config)
            report["dashboard_data_url"] = public_url(bucket, object_name)
            LOGGER.info("Publicado snapshot JSON em %s", report["storage_object"])
        if write_csv:
            write_output(args.output, rows)
            LOGGER.info("Geradas %d seções em %s", len(rows), args.output)
        report["publicado"] = True
        write_json(args.report, report)
        return 0
    except (DataError, StorageError, OSError, ValueError, KeyError, zipfile.BadZipFile, UnicodeError) as exc:
        LOGGER.error("%s", exc)
        return 1
    finally:
        if loki_handler:
            try:
                loki_handler.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())