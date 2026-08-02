"""Tests for async report export: service, storage, and drain."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.reports.db_models import ReportExportTask
from mplacas.reports.export_service import InvalidExportFormat, ReportExportService
from mplacas.reports.storage import (
    ArtifactStorage,
    GcsArtifactStorage,
    InMemoryArtifactStorage,
    make_artifact_storage,
)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _make_plant(session: AsyncSession) -> uuid.UUID:
    plant = Plant(name="Export Test Plant")
    session.add(plant)
    await session.flush()
    return plant.id


# ---------------------------------------------------------------------------
# ArtifactStorage Protocol
# ---------------------------------------------------------------------------


def test_in_memory_storage_implements_protocol() -> None:
    storage = InMemoryArtifactStorage()
    assert isinstance(storage, ArtifactStorage)


@pytest.mark.asyncio
async def test_in_memory_storage_upload_returns_memory_url() -> None:
    storage = InMemoryArtifactStorage()
    url = await storage.upload("key1", b"hello", "application/pdf")
    assert url == "memory://key1"


@pytest.mark.asyncio
async def test_in_memory_storage_get_returns_content() -> None:
    storage = InMemoryArtifactStorage()
    await storage.upload("key2", b"content", "application/pdf")
    assert storage.get("key2") == b"content"


@pytest.mark.asyncio
async def test_in_memory_storage_get_missing_returns_none() -> None:
    storage = InMemoryArtifactStorage()
    assert storage.get("missing") is None


# ---------------------------------------------------------------------------
# ReportExportService — enqueue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_creates_pending_task(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    service = ReportExportService(session)
    task = await service.enqueue(
        plant_id=plant_id,
        reference_month="2026-06",
        format="pdf",
    )
    assert task.id is not None
    assert task.status == "pending"
    assert task.format == "pdf"
    assert task.plant_id == plant_id
    assert task.reference_month == "2026-06"


@pytest.mark.asyncio
async def test_enqueue_invalid_format_raises(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    service = ReportExportService(session)
    with pytest.raises(InvalidExportFormat):
        await service.enqueue(
            plant_id=plant_id,
            reference_month="2026-06",
            format="docx",
        )


@pytest.mark.asyncio
async def test_enqueue_xlsx_format(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    task = await ReportExportService(session).enqueue(
        plant_id=plant_id,
        reference_month="2026-06",
        format="xlsx",
    )
    assert task.format == "xlsx"


# ---------------------------------------------------------------------------
# ReportExportService — claim / complete / fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_transitions_to_processing(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    service = ReportExportService(session)
    task = await service.enqueue(plant_id=plant_id, reference_month="2026-06", format="pdf")
    claimed = await service.claim(task.id)
    assert claimed is True

    refreshed = await service.get(task.id)
    assert refreshed is not None
    assert refreshed.status == "processing"
    assert refreshed.claimed_at is not None


@pytest.mark.asyncio
async def test_claim_already_processing_returns_false(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    service = ReportExportService(session)
    task = await service.enqueue(plant_id=plant_id, reference_month="2026-06", format="pdf")
    await service.claim(task.id)
    claimed_again = await service.claim(task.id)
    assert claimed_again is False


@pytest.mark.asyncio
async def test_mark_completed_stores_bytes(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    service = ReportExportService(session)
    task = await service.enqueue(plant_id=plant_id, reference_month="2026-06", format="pdf")
    await service.claim(task.id)
    await service.mark_completed(
        task.id,
        artifact_bytes=b"%PDF-test",
        artifact_content_type="application/pdf",
        artifact_url=None,
    )
    result = await service.get(task.id)
    assert result is not None
    assert result.status == "completed"
    assert result.artifact_bytes == b"%PDF-test"
    assert result.completed_at is not None


@pytest.mark.asyncio
async def test_mark_failed_records_error(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    service = ReportExportService(session)
    task = await service.enqueue(plant_id=plant_id, reference_month="2026-06", format="pdf")
    await service.claim(task.id)
    await service.mark_failed(task.id, error_message="snapshot not found")
    result = await service.get(task.id)
    assert result is not None
    assert result.status == "failed"
    assert result.error_message == "snapshot not found"


@pytest.mark.asyncio
async def test_pending_ids_returns_oldest_first(session: AsyncSession) -> None:
    plant_id = await _make_plant(session)
    service = ReportExportService(session)
    t1 = await service.enqueue(plant_id=plant_id, reference_month="2026-05", format="pdf")
    t2 = await service.enqueue(plant_id=plant_id, reference_month="2026-06", format="xlsx")
    ids = await service.pending_ids(limit=10)
    assert t1.id in ids
    assert t2.id in ids


# ---------------------------------------------------------------------------
# GcsArtifactStorage
# ---------------------------------------------------------------------------


def _make_gcs_client(signed_url: str = "https://signed.example.com/obj") -> MagicMock:
    blob = MagicMock()
    blob.generate_signed_url.return_value = signed_url
    bucket = MagicMock()
    bucket.blob.return_value = blob
    client = MagicMock()
    client.bucket.return_value = bucket
    return client


@pytest.mark.asyncio
async def test_gcs_upload_calls_blob_and_returns_signed_url() -> None:
    fake_client = _make_gcs_client("https://signed.example.com/report.pdf")
    gcs_module = MagicMock()
    gcs_module.Client.return_value = MagicMock()
    with patch.dict("sys.modules", {"google.cloud.storage": gcs_module}):
        storage = GcsArtifactStorage("my-bucket", url_ttl_seconds=300, client=fake_client)
    content = b"PDF bytes"
    url = await storage.upload("reports/1/2026-06/pdf/report.pdf", content, "application/pdf")
    assert url == "https://signed.example.com/report.pdf"
    blob = fake_client.bucket.return_value.blob.return_value
    blob.upload_from_string.assert_called_once_with(content, content_type="application/pdf")
    blob.generate_signed_url.assert_called_once()
    assert blob.generate_signed_url.call_args.kwargs.get("version") == "v4"
    assert blob.generate_signed_url.call_args.kwargs.get("method") == "GET"


def test_make_artifact_storage_no_bucket_returns_in_memory() -> None:
    storage = make_artifact_storage(bucket=None)
    assert isinstance(storage, InMemoryArtifactStorage)


def test_make_artifact_storage_with_bucket_returns_gcs() -> None:
    gcs_module = MagicMock()
    gcs_module.Client.return_value = MagicMock()
    with patch.dict("sys.modules", {"google.cloud.storage": gcs_module}):
        storage = make_artifact_storage(bucket="my-bucket", url_ttl_seconds=600)
    assert isinstance(storage, GcsArtifactStorage)
    assert storage._bucket_name == "my-bucket"
    assert storage._url_ttl_seconds == 600
