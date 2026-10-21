FROM ghcr.io/astral-sh/uv:0.7.12 AS uv

FROM python:3.11-slim

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --python 3.11
RUN /opt/venv/bin/python -m playwright install --with-deps chromium
RUN apt-get update && apt-get install -y --no-install-recommends xvfb xauth tini \
    && rm -rf /var/lib/apt/lists/*

COPY pipeline-config.json ./
COPY scripts/ ./scripts/

ENV PATH="/opt/venv/bin:${PATH}"
# Xorg does not notify a parent with PID 1 via SIGUSR1. Keep xvfb-run
# under an init process, otherwise it can wait forever before starting Python.
ENTRYPOINT ["/usr/bin/tini", "--", "sh", "scripts/run_job.sh"]
