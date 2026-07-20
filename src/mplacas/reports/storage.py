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
