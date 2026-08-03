from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mplacas.db.rls_inventory import RLS_TABLES
from mplacas.db.tenant_context import set_platform_context, set_tenant_context


async def _set_local_role(session, role_name: str) -> None:
    await session.execute(text(f'SET LOCAL ROLE "{role_name}"'))


@pytest.mark.postgres_integration
@pytest.mark.asyncio
async def test_application_rls_enforces_crud_and_every_ownership_chain() -> None:
    url = os.getenv("MPLACAS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("MPLACAS_TEST_POSTGRES_URL is required")

    suffix = uuid.uuid4().hex
    tenant_role = f"mplacas_rls_tenant_{suffix}"
    platform_role = f"mplacas_rls_platform_{suffix}"
    platform_marker = "mplacas_platform"
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    plant_a, plant_b = uuid.uuid4(), uuid.uuid4()
    device_a, device_b = uuid.uuid4(), uuid.uuid4()
    energy_a, energy_b = uuid.uuid4(), uuid.uuid4()
    version_a, version_b = uuid.uuid4(), uuid.uuid4()
    audit_a, audit_b, audit_platform = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    alert_a, alert_b = uuid.uuid4(), uuid.uuid4()
    job_run_id = uuid.uuid4()
    marker_created = False
    roles_created = False
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            marker_created = not bool(
                (
                    await connection.execute(
                        text("SELECT to_regrole(:role_name) IS NOT NULL"),
                        {"role_name": platform_marker},
                    )
                ).scalar_one()
            )
            if marker_created:
                await connection.execute(text(f'CREATE ROLE "{platform_marker}" NOLOGIN'))
            await connection.execute(text(f'CREATE ROLE "{tenant_role}" NOLOGIN'))
            await connection.execute(text(f'CREATE ROLE "{platform_role}" NOLOGIN'))
            roles_created = True
            await connection.execute(
                text(
                    f'GRANT "{tenant_role}", "{platform_role}" '
                    "TO CURRENT_USER WITH SET TRUE"
                )
            )
            await connection.execute(
                text(f'GRANT "{platform_marker}" TO "{platform_role}"')
            )
            await connection.execute(
                text(
                    f'GRANT USAGE ON SCHEMA public TO "{tenant_role}", "{platform_role}"'
                )
            )
            await connection.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                    f'TO "{tenant_role}", "{platform_role}"'
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, active) VALUES "
                    "(:org_a, 'RLS A', :slug_a, true), "
                    "(:org_b, 'RLS B', :slug_b, true)"
                ),
                {
                    "org_a": org_a,
                    "org_b": org_b,
                    "slug_a": f"rls-a-{suffix}",
                    "slug_b": f"rls-b-{suffix}",
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO plants (id, organization_id, name, timezone) VALUES "
                    "(:plant_a, :org_a, 'Plant A', 'America/Sao_Paulo'), "
                    "(:plant_b, :org_b, 'Plant B', 'America/Sao_Paulo')"
                ),
                {"plant_a": plant_a, "org_a": org_a, "plant_b": plant_b, "org_b": org_b},
            )
            await connection.execute(
                text(
                    "INSERT INTO devices (id, plant_id, provider, serial_number) VALUES "
                    "(:device_a, :plant_a, 'RLS', :serial_a), "
                    "(:device_b, :plant_b, 'RLS', :serial_b)"
                ),
                {
                    "device_a": device_a,
                    "plant_a": plant_a,
                    "serial_a": f"rls-a-{suffix}",
                    "device_b": device_b,
                    "plant_b": plant_b,
                    "serial_b": f"rls-b-{suffix}",
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO daily_energy "
                    "(id, device_id, production_date, energy_kwh, status, source) VALUES "
                    "(:energy_a, :device_a, DATE '2026-07-01', 10, 'CONSOLIDATED', 'RLS'), "
                    "(:energy_b, :device_b, DATE '2026-07-01', 20, 'CONSOLIDATED', 'RLS')"
                ),
                {
                    "energy_a": energy_a,
                    "device_a": device_a,
                    "energy_b": energy_b,
                    "device_b": device_b,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO daily_energy_versions "
                    "(id, daily_energy_id, energy_kwh, status) VALUES "
                    "(:version_a, :energy_a, 10, 'CONSOLIDATED'), "
                    "(:version_b, :energy_b, 20, 'CONSOLIDATED')"
                ),
                {
                    "version_a": version_a,
                    "energy_a": energy_a,
                    "version_b": version_b,
                    "energy_b": energy_b,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO audit_events "
                    "(id, organization_id, action, resource_type, outcome, actor_role, "
                    "actor_credential_id, details) VALUES "
                    "(:audit_a, :org_a, 'rls.test', 'plant', 'SUCCEEDED', 'ADMIN', 'a', '{}'), "
                    "(:audit_b, :org_b, 'rls.test', 'plant', 'SUCCEEDED', 'ADMIN', 'b', '{}'), "
                    "(:audit_platform, NULL, 'rls.test', 'platform', 'SUCCEEDED', "
                    "'ADMIN', 'platform', '{}')"
                ),
                {
                    "audit_a": audit_a,
                    "org_a": org_a,
                    "audit_b": audit_b,
                    "org_b": org_b,
                    "audit_platform": audit_platform,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO alert_delivery_records "
                    "(id, plant_id, fingerprint, provider, destination_ref) VALUES "
                    "(:alert_a, :plant_a, :fingerprint_a, 'telegram', 'a'), "
                    "(:alert_b, :plant_b, :fingerprint_b, 'telegram', 'b')"
                ),
                {
                    "alert_a": alert_a,
                    "plant_a": plant_a,
                    "fingerprint_a": f"rls-a-{suffix}",
                    "alert_b": alert_b,
                    "plant_b": plant_b,
                    "fingerprint_b": f"rls-b-{suffix}",
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO job_runs "
                    "(id, job_name, status, records_seen, records_changed, metrics) VALUES "
                    "(:id, 'rls-test', 'SUCCEEDED', 0, 0, '{}')"
                ),
                {"id": job_run_id},
            )

            policy_count = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM pg_policies "
                        "WHERE schemaname = 'public' AND policyname = 'mplacas_rls_isolation'"
                    )
                )
            ).scalar_one()
            enabled_count = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relname = ANY(:tables) "
                        "AND c.relrowsecurity AND c.relforcerowsecurity"
                    ),
                    {"tables": list(RLS_TABLES)},
                )
            ).scalar_one()
            assert policy_count == enabled_count == len(RLS_TABLES) == 24

        async with factory() as session:
            await _set_local_role(session, tenant_role)
            assert (
                await session.execute(text("SELECT count(*) FROM organizations"))
            ).scalar_one() == 0

        async with factory() as session:
            await _set_local_role(session, tenant_role)
            await set_tenant_context(session, org_a)
            assert (
                await session.execute(text("SELECT array_agg(id ORDER BY id) FROM organizations"))
            ).scalar_one() == [org_a]
            assert (
                await session.execute(text("SELECT array_agg(id ORDER BY id) FROM plants"))
            ).scalar_one() == [plant_a]
            assert (
                await session.execute(text("SELECT array_agg(id ORDER BY id) FROM devices"))
            ).scalar_one() == [device_a]
            assert (
                await session.execute(text("SELECT array_agg(id ORDER BY id) FROM daily_energy"))
            ).scalar_one() == [energy_a]
            assert (
                await session.execute(
                    text("SELECT array_agg(id ORDER BY id) FROM daily_energy_versions")
                )
            ).scalar_one() == [version_a]
            assert (
                await session.execute(text("SELECT array_agg(id ORDER BY id) FROM audit_events"))
            ).scalar_one() == [audit_a]
            assert (
                await session.execute(
                    text("SELECT array_agg(id ORDER BY id) FROM alert_delivery_records")
                )
            ).scalar_one() == [alert_a]
            assert (
                await session.execute(text("SELECT count(*) FROM job_runs"))
            ).scalar_one() == 0

            updated = await session.execute(
                text("UPDATE plants SET name = 'forbidden' WHERE id = :plant_id RETURNING id"),
                {"plant_id": plant_b},
            )
            assert updated.scalar_one_or_none() is None
            deleted = await session.execute(
                text("DELETE FROM plants WHERE id = :plant_id RETURNING id"),
                {"plant_id": plant_b},
            )
            assert deleted.scalar_one_or_none() is None
            await session.commit()

            # set_config(..., true) is transaction-local. The session listener
            # must restore the recorded tenant automatically after commit.
            await _set_local_role(session, tenant_role)
            assert (
                await session.execute(text("SELECT array_agg(id ORDER BY id) FROM organizations"))
            ).scalar_one() == [org_a]

        async with factory() as session:
            await _set_local_role(session, tenant_role)
            await set_tenant_context(session, org_a)
            with pytest.raises(DBAPIError):
                await session.execute(
                    text(
                        "INSERT INTO plants (id, organization_id, name, timezone) "
                        "VALUES (:id, :organization_id, 'forbidden', 'UTC')"
                    ),
                    {"id": uuid.uuid4(), "organization_id": org_b},
                )
            await session.rollback()

        own_plant = uuid.uuid4()
        async with factory() as session:
            await _set_local_role(session, tenant_role)
            await set_tenant_context(session, org_a)
            await session.execute(
                text(
                    "INSERT INTO plants (id, organization_id, name, timezone) "
                    "VALUES (:id, :organization_id, 'own', 'UTC')"
                ),
                {"id": own_plant, "organization_id": org_a},
            )
            assert (
                await session.execute(
                    text("UPDATE plants SET name = 'own-updated' WHERE id = :id RETURNING id"),
                    {"id": own_plant},
                )
            ).scalar_one() == own_plant
            assert (
                await session.execute(
                    text("DELETE FROM plants WHERE id = :id RETURNING id"),
                    {"id": own_plant},
                )
            ).scalar_one() == own_plant
            await session.commit()

        async with factory() as session:
            await _set_local_role(session, platform_role)
            assert (
                await session.execute(text("SELECT count(*) FROM organizations"))
            ).scalar_one() == 0

        async with factory() as session:
            await _set_local_role(session, platform_role)
            await set_platform_context(session)
            assert (
                await session.execute(
                    text(
                        "SELECT count(*) FROM organizations "
                        "WHERE id IN (:org_a, :org_b)"
                    ),
                    {"org_a": org_a, "org_b": org_b},
                )
            ).scalar_one() == 2
            assert (
                await session.execute(
                    text("SELECT count(*) FROM job_runs WHERE id = :id"),
                    {"id": job_run_id},
                )
            ).scalar_one() == 1
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM audit_events WHERE id = ANY(:ids)"),
                {"ids": [audit_a, audit_b, audit_platform]},
            )
            await connection.execute(
                text("DELETE FROM alert_delivery_records WHERE id = ANY(:ids)"),
                {"ids": [alert_a, alert_b]},
            )
            await connection.execute(
                text("DELETE FROM job_runs WHERE id = :id"), {"id": job_run_id}
            )
            await connection.execute(
                text("DELETE FROM organizations WHERE id = ANY(:ids)"),
                {"ids": [org_a, org_b]},
            )
            existing_roles = set(
                (
                    await connection.execute(
                        text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:names)"),
                        {"names": [tenant_role, platform_role, platform_marker]},
                    )
                ).scalars()
            )
            if roles_created and platform_role in existing_roles:
                await connection.execute(text(f'DROP OWNED BY "{platform_role}"'))
                await connection.execute(text(f'DROP ROLE "{platform_role}"'))
            if roles_created and tenant_role in existing_roles:
                await connection.execute(text(f'DROP OWNED BY "{tenant_role}"'))
                await connection.execute(text(f'DROP ROLE "{tenant_role}"'))
            if marker_created and platform_marker in existing_roles:
                await connection.execute(text(f'DROP ROLE IF EXISTS "{platform_marker}"'))
        await engine.dispose()
