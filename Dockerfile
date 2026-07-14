FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MPLACAS_ENVIRONMENT=production

WORKDIR /app

RUN addgroup --system mplacas && adduser --system --ingroup mplacas mplacas

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

USER mplacas

EXPOSE 8080

CMD ["python", "-m", "mplacas.cloud_run"]
