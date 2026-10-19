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

COPY pipeline-config.json ./
COPY scripts/ ./scripts/

ENV PATH="/opt/venv/bin:${PATH}"
CMD ["python", "-m", "scripts.gerar_dados"]
