FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

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
