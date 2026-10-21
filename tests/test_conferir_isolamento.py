"""Testes da trava de isolamento (tools/conferir_isolamento.py).

Garante que o deploy de dev falha quando aponta para projeto, job ou credencial de produção.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import conferir_isolamento as C  # noqa: E402


class TestConferirIsolamento(unittest.TestCase):
    def setUp(self):
        self.old_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def test_dev_valido_passa(self):
        os.environ["SECOES_ENV"] = "dev"
        os.environ["SECOES_PROJECT_ID"] = "secoes-dev-123"
        os.environ["SECOES_JOB_NAME"] = "secoes-etl-dev"
        problemas = []
        C.conferir_alvo("dev", C.producao(), problemas)
        self.assertEqual(problemas, [])

    def test_dev_sem_project_id_falha(self):
        os.environ["SECOES_ENV"] = "dev"
        os.environ.pop("SECOES_PROJECT_ID", None)
        problemas = []
        C.conferir_alvo("dev", C.producao(), problemas)
        self.assertTrue(any("falta SECOES_PROJECT_ID" in p for p in problemas))

    def test_dev_apontando_para_projeto_producao_falha(self):
        os.environ["SECOES_ENV"] = "dev"
        os.environ["SECOES_PROJECT_ID"] = "thech-against-bozo"
        problemas = []
        C.conferir_alvo("dev", C.producao(), problemas)
        self.assertTrue(any("é um projeto de PRODUÇÃO" in p for p in problemas))

    def test_dev_apontando_para_job_producao_falha(self):
        os.environ["SECOES_ENV"] = "dev"
        os.environ["SECOES_PROJECT_ID"] = "secoes-dev-123"
        os.environ["SECOES_JOB_NAME"] = "secoes-etl-prod"
        problemas = []
        C.conferir_alvo("dev", C.producao(), problemas)
        self.assertTrue(any("é um job de PRODUÇÃO" in p for p in problemas))

    def test_dev_com_credencial_de_producao_falha(self):
        os.environ["SECOES_ENV"] = "dev"
        os.environ["SECOES_PROJECT_ID"] = "secoes-dev-123"
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            json.dump({"project_id": "thech-against-bozo"}, f)
            cred_path = f.name
        try:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
            problemas = []
            C.conferir_alvo("dev", C.producao(), problemas)
            self.assertTrue(any("conta de serviço ativa pertence ao projeto de PRODUÇÃO" in p for p in problemas))
        finally:
            if os.path.exists(cred_path):
                os.unlink(cred_path)

    def test_ambiente_prod_permite_projeto_prod(self):
        os.environ["SECOES_ENV"] = "prod"
        os.environ["SECOES_PROJECT_ID"] = "thech-against-bozo"
        problemas = []
        C.conferir_alvo("prod", C.producao(), problemas)
        self.assertEqual(problemas, [])


if __name__ == "__main__":
    unittest.main()
