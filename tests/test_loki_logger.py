"""Testes do módulo de envio de logs para o Grafana Cloud Loki."""

from __future__ import annotations

import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import threading
import unittest
from unittest.mock import patch

from scripts.loki_logger import (
    LokiHandler,
    build_loki_url,
    parse_labels,
    setup_loki_logging,
)


class MockLokiServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)
        self.received_requests: list[dict] = []
        self.response_status = 204


class MockLokiHandler(BaseHTTPRequestHandler):
    server: MockLokiServer

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        auth = self.headers.get("Authorization", "")
        self.server.received_requests.append(
            {
                "path": self.path,
                "auth": auth,
                "content_type": self.headers.get("Content-Type"),
                "body": json.loads(body) if body else None,
            }
        )
        self.send_response(self.server.response_status)
        self.end_headers()

    def log_message(self, format, *args):
        # Silencia logs do http.server nos testes
        pass


class LokiLoggerTest(unittest.TestCase):
    def test_build_loki_url(self):
        self.assertEqual(build_loki_url(""), "")
        self.assertEqual(build_loki_url("   "), "")
        self.assertEqual(
            build_loki_url("https://logs.grafana.net"),
            "https://logs.grafana.net/loki/api/v1/push",
        )
        self.assertEqual(
            build_loki_url("https://logs.grafana.net/"),
            "https://logs.grafana.net/loki/api/v1/push",
        )
        self.assertEqual(
            build_loki_url("https://logs.grafana.net/loki/api/v1"),
            "https://logs.grafana.net/loki/api/v1/push",
        )
        self.assertEqual(
            build_loki_url("https://logs.grafana.net/loki/api/v1/push"),
            "https://logs.grafana.net/loki/api/v1/push",
        )

    def test_parse_labels(self):
        # Default
        self.assertEqual(parse_labels(None), {"app": "secoes", "job": "secoes"})
        self.assertEqual(parse_labels(""), {"app": "secoes", "job": "secoes"})

        # Dict
        self.assertEqual(
            parse_labels({"app": "custom", "env": "prod"}),
            {"app": "custom", "job": "secoes", "env": "prod"},
        )

        # JSON string
        self.assertEqual(
            parse_labels('{"env": "producao", "job": "worker"}'),
            {"app": "secoes", "job": "worker", "env": "producao"},
        )

        # Comma-separated string
        self.assertEqual(
            parse_labels("env=staging,region=us-central1"),
            {"app": "secoes", "job": "secoes", "env": "staging", "region": "us-central1"},
        )

    def test_setup_loki_logging_disabled(self):
        # Sem variável LOKI_URL -> no-op
        handler = setup_loki_logging({})
        self.assertIsNone(handler)

    def test_setup_loki_logging_enabled(self):
        env = {
            "LOKI_URL": "http://localhost:3100",
            "LOKI_USER": "12345",
            "LOKI_TOKEN": "glc_secret",
            "LOKI_BATCH_SIZE": "10",
        }
        handler = setup_loki_logging(env)
        try:
            self.assertIsNotNone(handler)
            self.assertIsInstance(handler, LokiHandler)
            self.assertEqual(handler.url, "http://localhost:3100/loki/api/v1/push")
            self.assertEqual(handler.user, "12345")
            self.assertEqual(handler.token, "glc_secret")
            self.assertEqual(handler.batch_size, 10)
        finally:
            if handler:
                handler.close()
                logging.getLogger().removeHandler(handler)

    def test_send_logs_to_mock_server(self):
        server = MockLokiServer(("127.0.0.1", 0), MockLokiHandler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        url = f"http://127.0.0.1:{port}"
        handler = LokiHandler(
            url=url,
            user="user99",
            token="secret_token",
            labels={"env": "test"},
            batch_size=2,
            flush_interval=10.0,  # longo para testar o gatilho de batch_size
        )
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger = logging.getLogger("test_loki_mock")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        try:
            logger.info("Primeira mensagem informativa")
            # Batch size é 2, então 1 log ainda não dispara envio imediato
            self.assertEqual(len(server.received_requests), 0)

            logger.info("Segunda mensagem informativa")
            # Dispara flush pelo batch_size
            handler.flush()

            self.assertEqual(len(server.received_requests), 1)
            req = server.received_requests[0]
            self.assertEqual(req["path"], "/loki/api/v1/push")
            self.assertEqual(req["content_type"], "application/json")

            # Confere Basic Auth
            expected_auth = "Basic " + base64.b64encode(b"user99:secret_token").decode("ascii")
            self.assertEqual(req["auth"], expected_auth)

            # Confere estrutura Loki v1
            body = req["body"]
            self.assertIn("streams", body)
            streams = body["streams"]
            self.assertEqual(len(streams), 1)
            stream_obj = streams[0]
            self.assertEqual(
                stream_obj["stream"],
                {"app": "secoes", "job": "secoes", "env": "test", "level": "INFO"},
            )
            self.assertEqual(len(stream_obj["values"]), 2)
            self.assertEqual(stream_obj["values"][0][1], "INFO: Primeira mensagem informativa")
            self.assertEqual(stream_obj["values"][1][1], "INFO: Segunda mensagem informativa")

        finally:
            handler.close()
            logger.removeHandler(handler)
            server.shutdown()
            server.server_close()

    def test_fail_safe_on_server_error(self):
        # O handler não deve levantar exceção se o servidor falhar
        server = MockLokiServer(("127.0.0.1", 0), MockLokiHandler)
        server.response_status = 500
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        handler = LokiHandler(
            url=f"http://127.0.0.1:{port}",
            timeout=1.0,
        )
        logger = logging.getLogger("test_loki_fail_safe")
        logger.addHandler(handler)

        try:
            # Não deve lançar erro mesmo com HTTP 500
            logger.error("Erro que o Loki vai rejeitar")
            handler.flush()
        finally:
            handler.close()
            logger.removeHandler(handler)
            server.shutdown()
            server.server_close()

    def test_fail_safe_on_unreachable_host(self):
        # Porta onde não há ninguém escutando
        handler = LokiHandler(
            url="http://127.0.0.1:59999",
            timeout=0.5,
        )
        logger = logging.getLogger("test_loki_unreachable")
        logger.addHandler(handler)

        try:
            logger.info("Log para servidor inexistente")
            handler.flush()
        finally:
            handler.close()
            logger.removeHandler(handler)

    def test_gerar_dados_main_integrates_loki(self):
        from unittest.mock import MagicMock, patch
        from scripts import gerar_dados

        mock_handler = MagicMock()
        with patch("scripts.loki_logger.setup_loki_logging", return_value=mock_handler) as mock_setup:
            ret = gerar_dados.main(["--config", "/tmp/nonexistent-config.json"])
            self.assertEqual(ret, 1)
            mock_setup.assert_called_once()
            mock_handler.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
