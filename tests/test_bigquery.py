"""Testes locais com subprocess/BigQuery simulados; não acessam o Google."""

from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from scripts import bigquery_io
from scripts.gerar_dados import FIELDS
from scripts.servir_dashboard import Snapshot, make_handler


CONFIG = {"project":"comite-tecnologia", "dataset":"alteracao_locais_votacao", "table":"secoes_alteradas_2t_2026", "location":"US"}


def row():
    return dict.fromkeys(FIELDS, "") | {"uf":"AL", "municipio":"Cidade", "cd_ibge":2701506, "zona":20,
                                      "secao":1, "eleitores":400, "lat_2t":-9.95, "lon_2t":-36.78,
                                      "local_1t":"Antigo", "local_2t":"Novo"}


class BigQueryTest(unittest.TestCase):
    def test_explicit_schema_and_nulls(self):
        definition = {f["name"]:f["type"] for f in bigquery_io.schema(FIELDS)}
        self.assertEqual(len(definition),25)
        self.assertEqual(definition["eleitores"],"INTEGER")
        self.assertEqual(definition["lat_1t"],"FLOAT")
        self.assertEqual(definition["regiao_longe_da_urna"],"BOOLEAN")
        typed = bigquery_io.typed_row(row(), FIELDS)
        self.assertIsNone(typed["regiao_longe_da_urna"])
        self.assertIsNone(typed["entrou_desde_15_10"])
        self.assertIsNone(typed["lat_1t"])
        self.assertEqual(typed["eleitores"],400)

    def test_atomic_load_command_and_serialized_data(self):
        def fake_run(command, **kwargs):
            self.assertEqual(command[:4],["bq","--project_id=comite-tecnologia","--location=US","--quiet"])
            self.assertIn("load",command)
            self.assertIn("--replace",command)
            self.assertIn("--max_bad_records=0",command)
            self.assertIn("comite-tecnologia:alteracao_locais_votacao.secoes_alteradas_2t_2026",command)
            typed = json.loads(Path(command[-2]).read_text())
            self.assertIsNone(typed["regiao_longe_da_urna"])
            self.assertEqual(typed["eleitores"],400)
            self.assertEqual(len(json.loads(Path(command[-1]).read_text())),25)
            return subprocess.CompletedProcess(command,0,"OK","")
        with patch("scripts.bigquery_io.subprocess.run",side_effect=fake_run) as mocked:
            self.assertEqual(bigquery_io.publish([row()],FIELDS,CONFIG),"comite-tecnologia.alteracao_locais_votacao.secoes_alteradas_2t_2026")
            self.assertEqual(mocked.call_count,1)  # Sem checagem de autenticação.

    def test_refuse_empty_load_and_unsafe_identifiers(self):
        with self.assertRaises(bigquery_io.BigQueryError):
            bigquery_io.publish([], FIELDS, CONFIG)
        with self.assertRaises(bigquery_io.BigQueryError):
            bigquery_io.target(CONFIG | {"table":"t`; DROP TABLE x"})

    def test_query_fixed_projection_location_and_billing_limit(self):
        response = json.dumps([row() | {"eleitores":"400", "regiao_longe_da_urna":None}])
        with patch("scripts.bigquery_io.subprocess.run",return_value=subprocess.CompletedProcess([],0,response,"")) as mocked:
            rows = bigquery_io.read_rows(CONFIG, FIELDS)
            command = mocked.call_args.args[0]
            self.assertIn("--location=US",command)
            self.assertIn("--maximum_bytes_billed=100000000",command)
            self.assertIn("`comite-tecnologia.alteracao_locais_votacao.secoes_alteradas_2t_2026`",command[-1])
            self.assertEqual(rows[0]["eleitores"],400)
            self.assertIsNone(rows[0]["regiao_longe_da_urna"])

    def test_query_does_not_silently_truncate(self):
        with patch("scripts.bigquery_io.run_bq",return_value=json.dumps([row(),row()])):
            with self.assertRaisesRegex(bigquery_io.BigQueryError,"truncado"):
                bigquery_io.read_rows(CONFIG,FIELDS,maximum_rows=1)

    def test_failure_and_timeout_propagated(self):
        with patch("scripts.bigquery_io.subprocess.run",return_value=subprocess.CompletedProcess([],1,"","Job falhou")):
            with self.assertRaisesRegex(bigquery_io.BigQueryError,"Job falhou"):
                bigquery_io.run_bq(CONFIG,["query"])
        with patch("scripts.bigquery_io.subprocess.run",side_effect=subprocess.TimeoutExpired("bq",25)):
            with self.assertRaisesRegex(bigquery_io.BigQueryError,"tempo limite"):
                bigquery_io.run_bq(CONFIG,["query"])

    def test_backend_cache(self):
        snapshot = Snapshot(CONFIG)
        with patch("scripts.servir_dashboard.read_rows",return_value=[row()]) as mocked:
            snapshot.get()
            snapshot.get()
            self.assertEqual(mocked.call_count,1)
            snapshot.expires=0
            snapshot.get()
            self.assertEqual(mocked.call_count,2)

    def test_local_api_does_not_serve_csv_or_private_files(self):
        snapshot = Snapshot(CONFIG)
        server = ThreadingHTTPServer(("127.0.0.1",0),make_handler(snapshot))
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch("scripts.servir_dashboard.read_rows",return_value=[row()]):
                with urllib.request.urlopen(base+"/api/secoes") as response:
                    self.assertEqual(json.load(response)["rows"][0]["eleitores"],400)
            with urllib.request.urlopen(base+"/dashboard-config.json") as response:
                config = json.load(response)
                self.assertEqual(config["dataFormat"],"json")
                self.assertEqual(config["dataUrl"],"./api/secoes")
            for path in ["/pipeline-config.json", "/.cache/anything", "/data/secoes_alteradas_2t_2026.csv"]:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(base+path)
                self.assertEqual(error.exception.code,404)
                error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()