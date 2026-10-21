"""Envio de logs do pipeline para o Grafana Cloud Loki.

Funciona de forma não-intrusiva e fail-safe:
- Se as variáveis de ambiente (LOKI_URL, etc.) não estiverem definidas, vira um no-op.
- Não adiciona dependências externas (usa apenas a biblioteca padrão do Python).
- Qualquer falha de rede ou timeout com o Loki nunca interrompe a rotina de dados.
- Realiza batching assíncrono para não impactar a velocidade da execução.
"""

from __future__ import annotations

import atexit
import base64
from collections import defaultdict
import json
import logging
import os
import sys
import threading
import time
from typing import Mapping
import urllib.error
import urllib.request


LOGGER = logging.getLogger("loki_logger")


def build_loki_url(base_url: str) -> str:
    """Normaliza a URL do endpoint de push do Loki."""
    url = (base_url or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/loki/api/v1/push"):
        return url
    if url.endswith("/loki/api/v1"):
        return f"{url}/push"
    return f"{url}/loki/api/v1/push"


def parse_labels(raw: str | Mapping[str, str] | None) -> dict[str, str]:
    """Interpreta labels customizados passados por JSON ou chave=valor."""
    labels = {"app": "secoes", "job": "secoes"}
    if not raw:
        return labels

    if isinstance(raw, Mapping):
        labels.update({str(k): str(v) for k, v in raw.items()})
        return labels

    raw_str = raw.strip()
    if raw_str.startswith("{"):
        try:
            parsed = json.loads(raw_str)
            if isinstance(parsed, dict):
                labels.update({str(k): str(v) for k, v in parsed.items()})
                return labels
        except Exception:
            pass

    for part in raw_str.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()
            if k:
                labels[k] = v

    return labels


class LokiHandler(logging.Handler):
    """Handler de logging do Python que envia registros em lote para o Loki."""

    def __init__(
        self,
        url: str,
        user: str = "",
        token: str = "",
        labels: Mapping[str, str] | None = None,
        batch_size: int = 50,
        flush_interval: float = 2.0,
        timeout: float = 5.0,
    ) -> None:
        super().__init__()
        self.url = build_loki_url(url)
        self.user = (user or "").strip()
        self.token = (token or "").strip()
        self.labels = parse_labels(labels)
        self.batch_size = max(1, batch_size)
        self.flush_interval = max(0.1, flush_interval)
        self.timeout = max(1.0, timeout)

        self._buffer: list[tuple[int, str, str]] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._closed = False

        self._worker_thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name="LokiLoggerWorker",
        )
        self._worker_thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        """Enfileira o log para envio em lote. Nunca levanta exceção."""
        if self._closed:
            return
        try:
            msg = self.format(record)
            ts_ns = getattr(record, "created_ns", None)
            if ts_ns is None:
                ts_ns = int(record.created * 1e9)

            should_wake = False
            with self._lock:
                self._buffer.append((ts_ns, record.levelname, msg))
                if len(self._buffer) >= self.batch_size or record.levelno >= logging.ERROR:
                    should_wake = True

            if should_wake:
                self._wake_event.set()
        except Exception as exc:
            try:
                sys.stderr.write(f"LokiHandler: erro ao registrar mensagem ({exc})\n")
            except Exception:
                pass

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            self._wake_event.wait(timeout=self.flush_interval)
            self._wake_event.clear()
            self.flush()

    def flush(self) -> None:
        """Esvazia o buffer e envia todos os registros pendentes."""
        with self._lock:
            if not self._buffer:
                return
            batch = self._buffer[:]
            self._buffer.clear()

        self._send_batch(batch)

    def _send_batch(self, batch: list[tuple[int, str, str]]) -> None:
        if not batch or not self.url:
            return

        streams_map: dict[tuple[tuple[str, str], ...], list[list[str]]] = defaultdict(list)
        for ts_ns, levelname, msg in batch:
            stream_labels = dict(self.labels)
            stream_labels["level"] = levelname
            key = tuple(sorted(stream_labels.items()))
            streams_map[key].append([str(ts_ns), msg])

        payload = {
            "streams": [
                {
                    "stream": dict(key),
                    "values": values,
                }
                for key, values in streams_map.items()
            ]
        }

        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(self.url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            if self.user and self.token:
                creds = f"{self.user}:{self.token}".encode("utf-8")
                req.add_header("Authorization", f"Basic {base64.b64encode(creds).decode('ascii')}")

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read()
        except Exception as exc:
            try:
                sys.stderr.write(f"LokiHandler: aviso ao enviar logs para o Loki ({exc})\n")
            except Exception:
                pass

    def close(self) -> None:
        """Encerra o worker e envia os logs restantes."""
        if self._closed:
            return
        self._closed = True
        self._stop_event.set()
        self._wake_event.set()
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3.0)
        self.flush()
        super().close()


def setup_loki_logging(env: Mapping[str, str] | None = None) -> LokiHandler | None:
    """Configura o LokiHandler no root logger se LOKI_URL estiver definida.

    Retorna a instância do LokiHandler criada, ou None se estiver desativado.
    """
    environment = os.environ if env is None else env
    url = environment.get("LOKI_URL", "").strip()
    if not url:
        return None

    user = environment.get("LOKI_USER", "").strip()
    token = environment.get("LOKI_TOKEN", "").strip()
    labels = parse_labels(environment.get("LOKI_LABELS"))

    batch_size = 50
    try:
        if "LOKI_BATCH_SIZE" in environment:
            batch_size = int(environment["LOKI_BATCH_SIZE"])
    except (ValueError, TypeError):
        pass

    flush_interval = 2.0
    try:
        if "LOKI_FLUSH_INTERVAL" in environment:
            flush_interval = float(environment["LOKI_FLUSH_INTERVAL"])
    except (ValueError, TypeError):
        pass

    handler = LokiHandler(
        url=url,
        user=user,
        token=token,
        labels=labels,
        batch_size=batch_size,
        flush_interval=flush_interval,
    )
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    logging.getLogger().addHandler(handler)
    atexit.register(handler.close)
    return handler
