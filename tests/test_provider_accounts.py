from __future__ import annotations

import base64
import uuid

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from mplacas.core.secret_box import KEY_BYTES, SecretBox
from mplacas.db.base import Base
from mplacas.db.models import Plant
from mplacas.organizations.db_models import DEFAULT_ORGANIZATION_ID, OrganizationRecord
from mplacas.providers import db_models as _provider_models  # noqa: F401
from mplacas.providers.accounts import (
    NEPVIEWER,
    ProviderAccountConflictError,
    ProviderAccountError,
    ProviderAccountNotFoundError,
    ProviderAccountService,
    ProviderLogin,
    mask_login,
)
from mplacas.providers.db_models import ProviderAccountRecord

PLANT_A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
PLANT_B = uuid.UUID("00000000-0000-0000-0000-00000000000b")
KEY_1 = base64.b64encode(b"\x01" * KEY_BYTES).decode()
KEY_2 = base64.b64encode(b"\x02" * KEY_BYTES).decode()
LOGIN = ProviderLogin(login=" Cliente@Example.com ", password="s3nh4-do-inversor")
_ENGINES: list[AsyncEngine] = []


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    while _ENGINES:
        await _ENGINES.pop().dispose()


async def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _ENGINES.append(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            OrganizationRecord(
                id=DEFAULT_ORGANIZATION_ID, name="Default", slug="default", active=True
            )
        )
        await session.flush()
        for plant_id, name in ((PLANT_A, "Casa"), (PLANT_B, "Sítio")):
            session.add(Plant(id=plant_id, organization_id=DEFAULT_ORGANIZATION_ID, name=name))
        await session.commit()
    return factory


def _box(raw: str = f"1:{KEY_1}") -> SecretBox:
    return SecretBox.from_keyring(raw)


async def test_save_stores_only_ciphertext_and_a_masked_hint() -> None:
    factory = await _factory()
    async with factory() as session:
        record = await ProviderAccountService(session, _box()).save(
            plant_id=PLANT_A, provider=NEPVIEWER, credentials=LOGIN
        )
        await session.commit()

    assert record.active
    assert record.login_hint == "Cl***@Example.com"
    assert record.key_version == 1
    assert record.ciphertext is not None
    assert b"s3nh4" not in record.ciphertext
    assert b"Cliente" not in record.ciphertext
    assert "cliente" not in (record.account_fingerprint or "").lower()
    assert "s3nh4" not in repr(record) and "Cliente" not in repr(record)


async def test_open_returns_the_normalized_login_and_the_exact_password() -> None:
    factory = await _factory()
    async with factory() as session:
        service = ProviderAccountService(session, _box())
        record = await service.save(plant_id=PLANT_A, provider=NEPVIEWER, credentials=LOGIN)

        opened = service.open(record)

    assert opened.login == "Cliente@Example.com"
    assert opened.password == "s3nh4-do-inversor"
    assert "s3nh4" not in repr(opened)


async def test_ciphertext_moved_to_another_plant_cannot_be_opened() -> None:
    factory = await _factory()
    async with factory() as session:
        service = ProviderAccountService(session, _box())
        stolen = await service.save(plant_id=PLANT_A, provider=NEPVIEWER, credentials=LOGIN)
        other = await service.save(
            plant_id=PLANT_B,
            provider=NEPVIEWER,
            credentials=ProviderLogin(login="outro@example.com", password="x"),
        )
        other.ciphertext = stolen.ciphertext
        other.key_version = stolen.key_version

        with pytest.raises(ProviderAccountError, match="could not be decrypted"):
            service.open(other)


async def test_same_account_on_another_plant_is_refused_regardless_of_case() -> None:
    factory = await _factory()
    async with factory() as session:
        service = ProviderAccountService(session, _box())
        await service.save(plant_id=PLANT_A, provider=NEPVIEWER, credentials=LOGIN)

        with pytest.raises(ProviderAccountConflictError):
            await service.save(
                plant_id=PLANT_B,
                provider=NEPVIEWER,
                credentials=ProviderLogin(login="cliente@example.com", password="outra"),
            )


async def test_resaving_the_same_plant_replaces_the_secret_in_place() -> None:
    factory = await _factory()
    async with factory() as session:
        service = ProviderAccountService(session, _box())
        first = await service.save(plant_id=PLANT_A, provider=NEPVIEWER, credentials=LOGIN)
        first_id, first_ciphertext = first.id, first.ciphertext
        second = await service.save(
            plant_id=PLANT_A,
            provider=NEPVIEWER,
            credentials=ProviderLogin(login=LOGIN.login, password="senha-nova"),
        )

        assert second.id == first_id
        assert second.ciphertext != first_ciphertext
        assert second.rotated_at is not None
        assert service.open(second).password == "senha-nova"


async def test_deactivate_wipes_the_secret_and_frees_the_account() -> None:
    factory = await _factory()
    async with factory() as session:
        service = ProviderAccountService(session, _box())
        await service.save(plant_id=PLANT_A, provider=NEPVIEWER, credentials=LOGIN)
        record = await service.deactivate(PLANT_A)

        assert not record.active
        assert record.ciphertext is None
        assert record.account_fingerprint is None
        assert record.deactivated_at is not None
        assert await service.list_active() == []
        with pytest.raises(ProviderAccountNotFoundError):
            service.open(record)
        with pytest.raises(ProviderAccountNotFoundError):
            await service.deactivate(PLANT_A)

        moved = await service.save(plant_id=PLANT_B, provider=NEPVIEWER, credentials=LOGIN)
        assert moved.active


async def test_database_refuses_an_active_row_without_ciphertext() -> None:
    factory = await _factory()
    async with factory() as session:
        await ProviderAccountService(session, _box()).save(
            plant_id=PLANT_A, provider=NEPVIEWER, credentials=LOGIN
        )
        await session.commit()
        with pytest.raises(IntegrityError):
            await session.execute(update(ProviderAccountRecord).values(ciphertext=None))
            await session.flush()


@pytest.mark.parametrize(
    ("provider", "credentials"),
    [
        ("SOLIS", LOGIN),
        (NEPVIEWER, ProviderLogin(login="  ", password="x")),
        (NEPVIEWER, ProviderLogin(login="a@b.c", password="")),
        (NEPVIEWER, ProviderLogin(login="a" * 255, password="x")),
    ],
)
async def test_invalid_input_is_refused_without_echoing_it(
    provider: str, credentials: ProviderLogin
) -> None:
    factory = await _factory()
    async with factory() as session:
        with pytest.raises(ProviderAccountError) as raised:
            await ProviderAccountService(session, _box()).save(
                plant_id=PLANT_A, provider=provider, credentials=credentials
            )

    assert "s3nh4" not in str(raised.value)
    assert "Cliente" not in str(raised.value)


async def test_unknown_plant_is_refused() -> None:
    factory = await _factory()
    async with factory() as session:
        with pytest.raises(ProviderAccountNotFoundError):
            await ProviderAccountService(session, _box()).save(
                plant_id=uuid.uuid4(), provider=NEPVIEWER, credentials=LOGIN
            )


async def test_rotation_reencrypts_with_the_new_key_and_recomputes_fingerprints() -> None:
    factory = await _factory()
    async with factory() as session:
        old = ProviderAccountService(session, _box(f"1:{KEY_1}"))
        record = await old.save(plant_id=PLANT_A, provider=NEPVIEWER, credentials=LOGIN)
        old_fingerprint = record.account_fingerprint

        new = ProviderAccountService(session, _box(f"1:{KEY_1},2:{KEY_2}"))
        assert await new.rotate_all() == 1
        assert record.key_version == 2
        assert record.account_fingerprint != old_fingerprint
        assert await new.rotate_all() == 0

        only_new = ProviderAccountService(session, _box(f"2:{KEY_2}"))
        assert only_new.open(record).password == LOGIN.password
        with pytest.raises(ProviderAccountConflictError):
            await only_new.save(plant_id=PLANT_B, provider=NEPVIEWER, credentials=LOGIN)


async def test_failure_bookkeeping_keeps_only_the_error_code() -> None:
    factory = await _factory()
    async with factory() as session:
        service = ProviderAccountService(session, _box())
        record = await service.save(plant_id=PLANT_A, provider=NEPVIEWER, credentials=LOGIN)
        await service.record_failure(record, code="ProviderAuthenticationError" * 10)
        assert record.last_failure_code is not None and len(record.last_failure_code) == 80
        await service.record_success(record)
        assert record.last_failure_code is None
        assert record.last_success_at is not None


@pytest.mark.parametrize(
    ("login", "masked"),
    [
        ("cliente@example.com", "cl***@example.com"),
        ("usuario123", "us***23"),
        ("abc", "a***"),
        ("", "***"),
    ],
)
def test_mask_login(login: str, masked: str) -> None:
    assert mask_login(login) == masked


async def test_same_account_is_refused_between_adding_a_key_and_rotating() -> None:
    """Chave nova acrescentada, rotação ainda não rodou: o conflito continua visível."""
    factory = await _factory()
    async with factory() as session:
        await ProviderAccountService(session, _box(f"1:{KEY_1}")).save(
            plant_id=PLANT_A, provider=NEPVIEWER, credentials=LOGIN
        )
        both_keys = ProviderAccountService(session, _box(f"1:{KEY_1},2:{KEY_2}"))

        with pytest.raises(ProviderAccountConflictError):
            await both_keys.save(plant_id=PLANT_B, provider=NEPVIEWER, credentials=LOGIN)

        assert await both_keys.rotate_all() == 1


async def test_rotation_names_the_plant_that_cannot_be_decrypted() -> None:
    factory = await _factory()
    async with factory() as session:
        record = await ProviderAccountService(session, _box(f"1:{KEY_1}")).save(
            plant_id=PLANT_A, provider=NEPVIEWER, credentials=LOGIN
        )
        assert record.ciphertext is not None
        record.ciphertext = record.ciphertext[:-1] + bytes([record.ciphertext[-1] ^ 1])

        with pytest.raises(ProviderAccountError, match=str(PLANT_A)) as raised:
            await ProviderAccountService(session, _box(f"1:{KEY_1},2:{KEY_2}")).rotate_all()
    assert "s3nh4" not in str(raised.value)


async def test_concurrent_connection_of_the_same_plant_becomes_a_domain_error() -> None:
    factory = await _factory()
    async with factory() as first, factory() as second:
        await ProviderAccountService(first, _box()).save(
            plant_id=PLANT_A, provider=NEPVIEWER, credentials=LOGIN
        )
        await first.commit()
        # A segunda sessão perdeu a corrida: grava como se a usina estivesse livre.
        service = ProviderAccountService(second, _box())

        async def _nobody(*_args, **_kwargs):
            return None

        service.get = _nobody  # type: ignore[method-assign]
        with pytest.raises(ProviderAccountConflictError):
            await service.save(
                plant_id=PLANT_A,
                provider=NEPVIEWER,
                credentials=ProviderLogin(login="outro@example.com", password="x"),
            )
