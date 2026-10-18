"""
compara o local de votação de cada seção entre o 1º e o 2º turno das eleições 2026,
a partir da base "eleitorado por local de votação" do portal de dados abertos do TSE.

uso:
    python scripts/compara_turnos.py                 # baixa a base do TSE e gera o CSV
    python scripts/compara_turnos.py caminho.csv     # usa um CSV _BRASIL já baixado
"""
import io
import sys
import zipfile
import urllib.request
from pathlib import Path

import pandas as pd

URL = ("https://cdn.tse.jus.br/estatistica/sead/odsele/eleitorado_locais_votacao/"
       "eleitorado_local_votacao_2026.zip")
NOME_BRASIL = "eleitorado_local_votacao_2026_BRASIL.csv"
SAIDA = Path(__file__).resolve().parent.parent / "data" / "tse_mudancas_local_votacao_2turno_2026.csv"

COLS = ["DT_GERACAO", "HH_GERACAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA",
        "NR_SECAO", "DS_TIPO_SECAO_AGREGADA", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "DS_ENDERECO",
        "NM_BAIRRO", "NR_CEP", "NR_LATITUDE", "NR_LONGITUDE", "QT_ELEITOR_SECAO"]
CHAVE = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]


def carrega(origem=None):
    if origem:
        return pd.read_csv(origem, sep=";", encoding="latin1", usecols=COLS, dtype=str)
    print("baixando base do TSE (~170 MB)...")
    with urllib.request.urlopen(URL) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    with z.open(NOME_BRASIL) as f:
        return pd.read_csv(f, sep=";", encoding="latin1", usecols=COLS, dtype=str)


def main():
    df = carrega(sys.argv[1] if len(sys.argv) > 1 else None)
    print("base gerada em:", df.DT_GERACAO.iloc[0], df.HH_GERACAO.iloc[0])

    t1 = df[df.NR_TURNO == "1"].set_index(CHAVE)
    t2 = df[df.NR_TURNO == "2"].set_index(CHAVE)
    j = t1.join(t2, lsuffix="_1T", rsuffix="_2T", how="inner")
    print("seções pareadas:", len(j))

    mudou = (j.NR_LOCAL_VOTACAO_1T != j.NR_LOCAL_VOTACAO_2T) | (j.DS_ENDERECO_1T != j.DS_ENDERECO_2T)
    m = j[mudou].reset_index()
    m.insert(0, "TIPO_MUDANCA",
             (m.NR_LOCAL_VOTACAO_1T != m.NR_LOCAL_VOTACAO_2T)
             .map({True: "novo local", False: "mesmo local - nome/endereco editado"}))
    m["QT_ELEITOR_SECAO_2T"] = pd.to_numeric(m.QT_ELEITOR_SECAO_2T, errors="coerce")

    print(m.TIPO_MUDANCA.value_counts().to_string())
    novo = m[m.TIPO_MUDANCA == "novo local"]
    print("eleitores em seções com novo local:", int(novo.QT_ELEITOR_SECAO_2T.sum()))

    out = ["TIPO_MUDANCA", "SG_UF", "NM_MUNICIPIO_1T", "NR_ZONA", "NR_SECAO", "DS_TIPO_SECAO_AGREGADA_2T",
           "QT_ELEITOR_SECAO_2T",
           "NR_LOCAL_VOTACAO_1T", "NM_LOCAL_VOTACAO_1T", "DS_ENDERECO_1T", "NM_BAIRRO_1T",
           "NR_LOCAL_VOTACAO_2T", "NM_LOCAL_VOTACAO_2T", "DS_ENDERECO_2T", "NM_BAIRRO_2T",
           "NR_CEP_2T", "NR_LATITUDE_2T", "NR_LONGITUDE_2T", "CD_MUNICIPIO"]
    SAIDA.parent.mkdir(exist_ok=True)
    (m[out].sort_values(["SG_UF", "NM_MUNICIPIO_1T", "NR_ZONA", "NR_SECAO"])
           .to_csv(SAIDA, index=False, sep=";", encoding="utf-8-sig"))
    print("salvo em", SAIDA)


if __name__ == "__main__":
    main()
