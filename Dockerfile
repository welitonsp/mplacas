FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MPLACAS_ENVIRONMENT=production
ENV PYTHONPATH=/app/src

WORKDIR /app

# O digest fixa a imagem base, mas o Debian publica correções de segurança
# antes de a imagem upstream ser reconstruída; o upgrade as aplica no build.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
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

CMD ["python", "-m", "mplacas.server"]
