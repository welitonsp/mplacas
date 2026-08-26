"""ArtifactStorage Protocol and implementations for async report export."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ArtifactStorage(Protocol):
    """Upload artifact bytes and return a URL pointing to the artifact."""

    async def upload(self, key: str, content: bytes, content_type: str) -> str:
        """Upload ``content`` under ``key`` and return a download URL."""
        ...


class InMemoryArtifactStorage:
    """Ephemeral in-process storage for development and testing.

    Returns a ``memory://{key}`` URL. Content is lost on process restart.
    Do not use in production — bytes are not persisted to any durable store.
    """

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def upload(self, key: str, content: bytes, content_type: str) -> str:
        self._store[key] = content
        return f"memory://{key}"

    def get(self, key: str) -> bytes | None:
        return self._store.get(key)


# Não existe implementação de object storage neste momento, e isso é deliberado
# (ADR-076). O antigo GcsArtifactStorage saiu com o Google Cloud, e uma versão
# em disco local seria pior do que nada na arquitetura atual: os jobs rodam em
# runner efêmero do GitHub Actions e a API roda no Render, máquinas distintas —
# o arquivo escrito pelo job nunca existiria na máquina que serve a resposta, e
# o `file://` resultante não é navegável a partir de uma página https.
#
# Enquanto não houver bucket, os bytes do relatório continuam no banco e o
# download passa por `/reports/monthly/exports/{id}/download`, que é o caminho
# padrão e funciona. Para adotar object storage compatível com S3, implemente
# uma classe aderente ao Protocol acima devolvendo URL https assinada e com
# prazo de validade — nada além dela precisa mudar.
