# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Obseil API image
# Multi-stage: dependencies are built once into a wheel-backed venv, then only
# the venv and the source are copied into a slim, non-root runtime image.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt


# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 obseil

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=obseil:obseil alembic.ini pyproject.toml ./
COPY --chown=obseil:obseil alembic ./alembic
COPY --chown=obseil:obseil app ./app
COPY --chown=obseil:obseil scripts ./scripts

RUN mkdir -p /app/var/datasets && chown -R obseil:obseil /app/var
USER obseil

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
