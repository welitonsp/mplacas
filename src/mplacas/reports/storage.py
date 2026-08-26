"""ArtifactStorage Protocol and implementations for async report export."""
from __future__ import annotations

import asyncio
from pathlib import Path
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


class LocalDirectoryArtifactStorage:
    """Filesystem-backed artifact storage returning ``file://`` URLs.

    Substitui o antigo GcsArtifactStorage (ver ADR-076). Não depende de SDK de
    nenhum provedor: escreve sob um diretório base e serve para disco local ou
    volume montado. Para object storage compatível com S3, implemente uma nova
    classe aderente ao Protocol ``ArtifactStorage`` — nada mais precisa mudar.
    """

    def __init__(self, base_directory: str | Path) -> None:
        self._base = Path(base_directory)

    async def upload(self, key: str, content: bytes, content_type: str) -> str:
        target = self._base / key

        def _do_write() -> str:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return target.resolve().as_uri()

        return await asyncio.to_thread(_do_write)


def make_artifact_storage(*, directory: str | None) -> ArtifactStorage:
    """Return a LocalDirectoryArtifactStorage when *directory* is set, in-memory otherwise."""
    if directory:
        return LocalDirectoryArtifactStorage(directory)
    return InMemoryArtifactStorage()
