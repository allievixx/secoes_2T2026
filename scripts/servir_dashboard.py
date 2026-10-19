"""Servidor local: dashboard → /api/secoes → BigQuery, usando a CLI autenticada."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
from pathlib import Path
import threading
import time
from typing import Any
from urllib.parse import urlsplit

from .bigquery_io import BigQueryError, read_rows, target
from .gerar_dados import FIELDS, ROOT


class Snapshot:
    """Uma consulta por minuto por processo, em vez de uma por visitante."""

    def __init__(self, config: dict[str, Any], ttl: float = 60):
        self.config, self.ttl = config, ttl
        self.rows: list[dict[str, Any]] | None = None
        self.expires = 0.0
        self.lock = threading.Lock()

    def get(self) -> list[dict[str, Any]]:
        with self.lock:
            if self.rows is None or time.monotonic() >= self.expires:
                rows = read_rows(self.config, FIELDS)
                self.rows = rows
                self.expires = time.monotonic() + self.ttl
            return self.rows


def make_handler(snapshot: Snapshot, root: Path = ROOT):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            try:
                if path == "/healthz":
                    self.respond(200, b'{"ok":true}', "application/json")
                elif path == "/api/secoes":
                    body = json.dumps({"rows":snapshot.get()}, ensure_ascii=False, allow_nan=False).encode()
                    self.respond(200, body, "application/json; charset=utf-8")
                elif path == "/dashboard-config.json":
                    config = json.loads((root/"dashboard-config.json").read_text(encoding="utf-8"))
                    config.update(dataUrl="./api/secoes", dataFormat="json")
                    self.respond(200, json.dumps(config).encode(), "application/json; charset=utf-8")
                elif path in {"/", "/index.html", "/app.js", "/dashboard-data.js", "/styles.css"}:
                    file = root / ("index.html" if path == "/" else path[1:])
                    content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                    self.respond(200, file.read_bytes(), content_type+"; charset=utf-8")
                else:
                    # Não servir CSVs, fontes, caches ou configuração privada do pipeline.
                    self.respond(404, b'{"error":"Recurso inexistente"}', "application/json")
            except (BigQueryError, OSError, ValueError, KeyError):
                logging.exception("Falha ao atender %s", path)
                self.respond(503, b'{"error":"Fonte BigQuery indisponivel. Consulte o log do servidor."}', "application/json")

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT/"pipeline-config.json")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8")).get("bigquery", {})
    target(config)  # Validação local, sem chamada ao Google nem checagem de login.
    logging.basicConfig(level=logging.INFO)
    with ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(Snapshot(config))) as server:
        logging.info("Dashboard BigQuery em http://127.0.0.1:%d (somente acesso local)", args.port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()