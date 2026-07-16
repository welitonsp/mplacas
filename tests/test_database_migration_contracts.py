from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_utility_bill_initial_unique_constraint_is_named_for_batch_migrations() -> None:
    migration = (
        ROOT / "migrations" / "versions" / "20260712_0003_utility_bills.py"
    ).read_text(encoding="utf-8")

    assert "uq_utility_bills_distributor_reference_month_cycle_start_cycle_end" in migration


def test_utility_bill_plant_scope_migration_reflects_sqlite_constraint_names() -> None:
    migration = (
        ROOT
        / "migrations"
        / "versions"
        / "20260713_0005_scope_utility_bills_by_plant.py"
    ).read_text(encoding="utf-8")

    assert "_BILL_NAMING_CONVENTION" in migration
    assert "naming_convention=_BILL_NAMING_CONVENTION" in migration


def test_operational_scale_indexes_migration_is_present() -> None:
    migration = (
        ROOT
        / "migrations"
        / "versions"
        / "20260716_0008_add_operational_scale_indexes.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "20260713_0007"' in migration
    assert '"ix_devices_plant_id"' in migration
    assert '"ix_daily_energy_versions_daily_energy_id"' in migration
    assert '"ix_utility_bills_plant_status_cycle"' in migration
    assert '["plant_id", "status", "cycle_end", "created_at"]' in migration


def test_audit_events_migration_is_present() -> None:
    migration = (
        ROOT / "migrations" / "versions" / "20260716_0009_add_audit_events.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "20260716_0008"' in migration
    assert '"audit_events"' in migration
    assert '"actor_credential_id"' in migration
    assert '"request_id"' in migration
    assert '"ix_audit_events_actor"' in migration
    assert '"ix_audit_events_resource"' in migration


def test_utility_bill_plant_scope_migration_is_present() -> None:
    migration = (
        ROOT
        / "migrations"
        / "versions"
        / "20260716_0010_require_utility_bill_plant.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "20260716_0009"' in migration
    assert "utility_bills.plant_id has legacy NULL rows" in migration
    assert "UPDATE utility_bills SET plant_id = :plant_id WHERE plant_id IS NULL" in migration
    assert '"plant_id"' in migration
    assert "nullable=False" in migration
