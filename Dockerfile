FROM python:3.14-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MPLACAS_ENVIRONMENT=production
ENV PYTHONPATH=/app/src

WORKDIR /app

RUN addgroup --system mplacas && adduser --system --ingroup mplacas mplacas

COPY requirements.lock pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations

RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock \
    && python -m pip uninstall --yes pip setuptools

USER mplacas

EXPOSE 8080

CMD ["python", "-m", "mplacas.cloud_run"]
