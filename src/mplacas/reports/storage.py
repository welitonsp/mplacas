"""ArtifactStorage Protocol and implementations for async report export."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any, Protocol, runtime_checkable


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


class GcsArtifactStorage:
    """GCS-backed artifact storage that returns v4 signed download URLs.

    The google-cloud-storage package is imported lazily so that the module can
    be imported in environments where the package is not installed (e.g. tests
    that do not exercise GCS paths).
    """

    _client: Any

    def __init__(
        self,
        bucket_name: str,
        url_ttl_seconds: int = 900,
        client: Any = None,
    ) -> None:
        import google.cloud.storage as gcs  # type: ignore[import-untyped]

        self._bucket_name = bucket_name
        self._url_ttl_seconds = url_ttl_seconds
        self._client = client if client is not None else gcs.Client()

    async def upload(self, key: str, content: bytes, content_type: str) -> str:
        bucket = self._client.bucket(self._bucket_name)
        blob = bucket.blob(key)

        def _do_upload() -> str:
            blob.upload_from_string(content, content_type=content_type)
            url: str = blob.generate_signed_url(
                expiration=timedelta(seconds=self._url_ttl_seconds),
                method="GET",
                version="v4",
            )
            return url

        return await asyncio.to_thread(_do_upload)


def make_artifact_storage(
    *, bucket: str | None, url_ttl_seconds: int = 900
) -> ArtifactStorage:
    """Return a GcsArtifactStorage when *bucket* is set, InMemoryArtifactStorage otherwise."""
    if bucket:
        return GcsArtifactStorage(bucket, url_ttl_seconds=url_ttl_seconds)
    return InMemoryArtifactStorage()
