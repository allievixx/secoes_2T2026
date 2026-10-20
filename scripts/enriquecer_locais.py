#!/usr/bin/env python3
"""
scripts/enriquecer_locais.py

Enriquecimento e resolução automática de coordenadas e distâncias entre
o local de votação do 1º turno e o local de votação do 2º turno.

Não altera scripts/gerar_dados.py nem a infraestrutura existente.
Resolve:
1. Coordenadas de locais com variações de nomenclatura (E.E., E.M., Prof., Anexo).
2. Coordenadas presentes no 1º turno ou no 2º turno do cadastro eleitorado_local_votacao_2026.
3. Cálculo automático de distancia_km via Haversine.
"""

from __future__ import annotations

import csv
import glob
import io
import json
import math
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Any


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    # Remove acentuação e converte para maiúsculas
    nfd = unicodedata.normalize("NFD", text.upper())
    clean = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    # Expande abreviações comuns de escolas
    clean = re.sub(r"\bE\s*\.?\s*E\s*\.?", "ESCOLA ESTADUAL ", clean)
    clean = re.sub(r"\bE\s*\.?\s*M\s*\.?", "ESCOLA MUNICIPAL ", clean)
    clean = re.sub(r"\bC\s*\.?\s*E\s*\.?", "COLEGIO ESTADUAL ", clean)
    clean = re.sub(r"\bESC\s*\.?", "ESCOLA ", clean)
    clean = re.sub(r"\bCOL\s*\.?", "COLEGIO ", clean)
    clean = re.sub(r"\bPROF\s*\.?\s*A?\b", "", clean)  # remove prefixo prof/professora para evitar descompasso
    clean = re.sub(r"\bLOCAL\s*\d+\b", "", clean)
    clean = re.sub(r"\bPREDIO\s*ANEXO\b", "", clean)
    clean = re.sub(r"[^A-Z0-9\s]", " ", clean)
    return " ".join(clean.split())


def haversine(p1: tuple[float, float] | None, p2: tuple[float, float] | None) -> float | None:
    if not p1 or not p2:
        return None
    lat1, lon1 = p1
    lat2, lon2 = p2
    if (lat1 == -1 and lon1 == -1) or (lat2 == -1 and lon2 == -1):
        return None
    if lat1 == 0 and lon1 == 0:
        return None
    if lat2 == 0 and lon2 == 0:
        return None
    
    R = 6371.0  # Raio da Terra em km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


def parse_float_coord(val: str | None) -> float | None:
    if not val:
        return None
    val_clean = val.strip().replace(",", ".")
    try:
        f = float(val_clean)
        if f in {-1.0, 0.0} or abs(f) > 180:
            return None
        return f
    except ValueError:
        return None


def build_tse_indices(zip_path: Path, needed_ufs: set[str]):
    """
    Constrói índices de coordenadas cobrindo tanto o 1º quanto o 2º turno do cadastro.
    """
    coords_by_sec_turno: dict[tuple[str, int, int, int], tuple[float, float]] = {}
    coords_by_sec_any: dict[tuple[str, int, int], tuple[float, float]] = {}
    coords_by_name: dict[tuple[str, int, str], tuple[float, float]] = {}
    addresses_by_name: dict[tuple[str, int, str], tuple[str, str]] = {}

    with zipfile.ZipFile(zip_path) as z:
        for uf in needed_ufs:
            fname = f"eleitorado_local_votacao_2026_{uf}.csv"
            if fname not in z.namelist():
                continue
            with z.open(fname) as zf:
                reader = csv.DictReader(io.TextIOWrapper(zf, encoding="latin1"), delimiter=";")
                for r in reader:
                    lat = parse_float_coord(r.get("NR_LATITUDE"))
                    lon = parse_float_coord(r.get("NR_LONGITUDE"))
                    pt = (lat, lon) if (lat is not None and lon is not None) else None

                    try:
                        zona = int(r["NR_ZONA"])
                        secao = int(r["NR_SECAO"])
                        turno = int(r["NR_TURNO"])
                    except (ValueError, KeyError):
                        continue

                    uf_code = r["SG_UF"]
                    loc_name_norm = normalize_text(r.get("NM_LOCAL_VOTACAO"))
                    end = r.get("DS_ENDERECO", "")
                    bairro = r.get("NM_BAIRRO", "")

                    if pt:
                        coords_by_sec_turno[(uf_code, zona, secao, turno)] = pt
                        if (uf_code, zona, secao) not in coords_by_sec_any:
                            coords_by_sec_any[(uf_code, zona, secao)] = pt
                        
                        if loc_name_norm and (uf_code, zona, loc_name_norm) not in coords_by_name:
                            coords_by_name[(uf_code, zona, loc_name_norm)] = pt
                            addresses_by_name[(uf_code, zona, loc_name_norm)] = (end, bairro)

    return coords_by_sec_turno, coords_by_sec_any, coords_by_name, addresses_by_name


def find_best_point_for_name(
    uf: str, zona: int, name: str,
    coords_by_name: dict[tuple[str, int, str], tuple[float, float]]
) -> tuple[float, float] | None:
    norm_target = normalize_text(name)
    if not norm_target:
        return None

    # Match exato normalizado
    if (uf, zona, norm_target) in coords_by_name:
        return coords_by_name[(uf, zona, norm_target)]

    # Match por contenção de tokens dentro da mesma zona
    target_tokens = set(norm_target.split())
    best_match = None
    best_score = 0.0

    for (u, z, n), pt in coords_by_name.items():
        if u != uf or z != zona:
            continue
        cand_tokens = set(n.split())
        if not cand_tokens or not target_tokens:
            continue
        intersection = target_tokens & cand_tokens
        score = len(intersection) / max(len(target_tokens), len(cand_tokens))
        if score > 0.6 and score > best_score:
            best_score = score
            best_match = pt

    return best_match


def enrich_rows(rows: list[dict[str, Any]], zip_path: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    needed_ufs = {r["uf"] for r in rows if "uf" in r}
    coords_by_sec_turno, coords_by_sec_any, coords_by_name, addresses_by_name = build_tse_indices(zip_path, needed_ufs)

    initial_missing = sum(1 for r in rows if r.get("distancia_km") in {None, "", 0})
    resolved_count = 0

    for r in rows:
        uf = r["uf"]
        zona = int(r["zona"])
        secao = int(r["secao"])

        # Ponto 1T:
        p1 = None
        # 1. Seção no 1º turno
        if (uf, zona, secao, 1) in coords_by_sec_turno:
            p1 = coords_by_sec_turno[(uf, zona, secao, 1)]
        # 2. Por nome do local 1T
        if not p1 and r.get("local_1t"):
            p1 = find_best_point_for_name(uf, zona, r["local_1t"], coords_by_name)
        # 3. Se já existia lat_1t/lon_1t
        if not p1 and r.get("lat_1t") is not None and r.get("lon_1t") is not None:
            p1 = (float(r["lat_1t"]), float(r["lon_1t"]))

        # Ponto 2T:
        p2 = None
        # 1. Seção no 2º turno
        if (uf, zona, secao, 2) in coords_by_sec_turno:
            p2 = coords_by_sec_turno[(uf, zona, secao, 2)]
        # 2. Por nome do local 2T
        if not p2 and r.get("local_2t"):
            p2 = find_best_point_for_name(uf, zona, r["local_2t"], coords_by_name)
        # 3. Se já existia lat_2t/lon_2t
        if not p2 and r.get("lat_2t") is not None and r.get("lon_2t") is not None:
            p2 = (float(r["lat_2t"]), float(r["lon_2t"]))

        if p1:
            r["lat_1t"] = p1[0]
            r["lon_1t"] = p1[1]
        if p2:
            r["lat_2t"] = p2[0]
            r["lon_2t"] = p2[1]

        dist = haversine(p1, p2)
        if dist is not None:
            r["distancia_km"] = dist
            resolved_count += 1
        elif r.get("distancia_km") in {None, ""}:
            # Se ambos os locais têm o mesmo nome/endereço, distância é 0
            if normalize_text(r.get("local_1t")) == normalize_text(r.get("local_2t")):
                r["distancia_km"] = 0.0
                resolved_count += 1

    final_missing = sum(1 for r in rows if r.get("distancia_km") in {None, ""})
    stats = {
        "total": len(rows),
        "initial_missing": initial_missing,
        "resolved_total": resolved_count,
        "final_missing": final_missing,
    }
    return rows, stats


def main():
    root = Path(__file__).resolve().parent.parent
    data_json = root / "data" / "secoes_novas.json"
    data_csv = root / "data" / "secoes_novas.csv"

    # Encontra o zip do cadastro
    zips = list((root / ".cache" / "tse").glob("*eleitorado_local_votacao_2026*.zip"))
    if not zips:
        print("Erro: Arquivo eleitorado_local_votacao_2026.zip não encontrado no cache local.")
        return

    registry_zip = zips[0]
    print(f"Utilizando cadastro: {registry_zip.name}")

    if not data_json.exists():
        print(f"Erro: {data_json} não encontrado.")
        return

    with open(data_json, encoding="utf-8") as f:
        payload = json.load(f)

    snapshots = payload.get("snapshots", [])
    if not snapshots:
        print("Nenhum snapshot no JSON.")
        return

    latest_snap = snapshots[-1]
    print(f"Processando snapshot mais recente: {latest_snap.get('extracted_at')} com {len(latest_snap['rows'])} seções...")

    enriched_rows, stats = enrich_rows(latest_snap["rows"], registry_zip)
    latest_snap["rows"] = enriched_rows

    print("\nEstatísticas de Resolução de Distâncias:")
    print(f"  Total de seções analisadas: {stats['total']}")
    print(f"  Seções que tinham distância: {stats['total'] - stats['initial_missing']}")
    print(f"  Seções agora com distância calculada: {stats['resolved_total']}")
    print(f"  Faltando resolução: {stats['final_missing']}")

    # Salva JSON atualizado
    with open(data_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] {data_json} atualizado com sucesso!")

    # Se existir secoes_novas.csv, atualiza também
    if data_csv.exists() and enriched_rows:
        fieldnames = list(enriched_rows[0].keys())
        with open(data_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(enriched_rows)
        print(f"[OK] {data_csv} atualizado com sucesso!")


if __name__ == "__main__":
    main()
