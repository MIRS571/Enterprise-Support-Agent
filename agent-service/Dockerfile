FROM ghcr.io/astral-sh/uv:0.12.3 AS uv

FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    HF_HOME=/cache/huggingface \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY data ./data

RUN mkdir -p /cache/huggingface \
    && chown -R 10001:10001 /app /cache

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "agent_service.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
