#!/usr/bin/env bash
# Regenera requirements.lock e requirements-dev.lock dentro de um container
# baseado exatamente na mesma imagem (mesmo digest) usada em produção pelo
# Dockerfile, garantindo que os markers de ambiente resolvidos pelo
# pip-compile (ex: sys_platform, python_version) reflitam o runtime real.
#
# Uso:
#   scripts/compile-locks.sh
#   scripts/compile-locks.sh --upgrade-package nome-do-pacote
#   scripts/compile-locks.sh --upgrade-package pkg-a --upgrade-package pkg-b
#
# Requer Docker. Escreve requirements.lock e requirements-dev.lock de volta
# no working tree (o repositório é montado como volume no container).
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Mesma imagem base pinada por digest usada em Dockerfile:1 — não reescrever
# à mão; se o digest do Dockerfile mudar, atualize esta linha para bater.
BASE_IMAGE="python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b"

# Mesma versão de pip-tools pinada em pyproject.toml (extra dev).
PIP_TOOLS_VERSION="7.6.0"

docker run --rm \
  --volume "${REPO_ROOT}:/work" \
  --workdir /work \
  "${BASE_IMAGE}" \
  bash -Eeuo pipefail -c '
    python -m pip install --no-cache-dir "pip-tools=='"${PIP_TOOLS_VERSION}"'"
    pip-compile pyproject.toml --generate-hashes --strip-extras --allow-unsafe \
      --output-file=requirements.lock "$@"
    pip-compile pyproject.toml --extra dev --generate-hashes --strip-extras --allow-unsafe \
      --output-file=requirements-dev.lock "$@"
  ' bash "$@"
