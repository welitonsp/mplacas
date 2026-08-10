FROM python:3.14-slim-bookworm@sha256:23c59390fc717bf09f9336908199a0ae75d9c4264bf296123f94ad772fea3b52

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MPLACAS_ENVIRONMENT=production
ENV PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system mplacas && adduser --system --ingroup mplacas mplacas

COPY requirements.lock pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations

RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock \
    && python -m pip uninstall --yes pip setuptools

USER mplacas

EXPOSE 8080

CMD ["python", "-m", "mplacas.cloud_run"]
