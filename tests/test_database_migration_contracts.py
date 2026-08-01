from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_utility_bill_initial_unique_constraint_is_named_for_batch_migrations() -> None:
    migration = (
        ROOT / "migrations" / "versions" / "20260712_0003_utility_bills.py"
    ).read_text(encoding="utf-8")

    assert "uq_utility_bills_cycle" in migration


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


def test_monthly_report_snapshot_migration_is_present() -> None:
    migration = (
        ROOT
        / "migrations"
        / "versions"
        / "20260719_0011_add_monthly_report_snapshots.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "20260716_0010"' in migration
    assert '"monthly_report_snapshots"' in migration
    assert '"payload_json"' in migration
    assert '"payload_sha256"' in migration
    assert 'sa.UniqueConstraint("bill_id"' in migration
    assert '"ix_monthly_report_snapshots_plant_reference"' in migration


def test_transactional_outbox_migration_is_present() -> None:
    migration = (
        ROOT
        / "migrations"
        / "versions"
        / "20260719_0012_add_transactional_outbox.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "20260719_0011"' in migration
    assert '"outbox_events"' in migration
    assert '"deduplication_key"' in migration
    assert '"payload_sha256"' in migration
    assert '"attempt_count"' in migration
    assert '"available_at"' in migration
    assert '"ix_outbox_events_status_available"' in migration
    assert '"ix_outbox_events_dispatch"' in migration


def test_api_credentials_migration_is_present() -> None:
    source = (
        ROOT
        / "migrations"
        / "versions"
        / "20260719_0013_add_api_credentials.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260719_0013"' in source
    assert 'down_revision = "20260719_0012"' in source
    assert '"api_credentials"' in source
    assert '"key_hash"' in source
    assert "uq_api_credentials_key_hash" in source
    assert "sa.UniqueConstraint" in source


def test_operational_users_migration_is_present() -> None:
    source = (
        ROOT
        / "migrations"
        / "versions"
        / "20260719_0014_add_operational_users.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260719_0014"' in source
    assert 'down_revision = "20260719_0013"' in source
    assert '"operational_users"' in source
    assert "uq_operational_users_name" in source
    assert "fk_api_credentials_user_id" in source
    assert '"expires_at"' in source
    assert "batch_alter_table" in source


def test_collection_task_queue_migration_is_present() -> None:
    source = (
        ROOT
        / "migrations"
        / "versions"
        / "20260719_0015_add_collection_task_queue.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260719_0015"' in source
    assert 'down_revision = "20260719_0014"' in source
    assert '"collection_tasks"' in source
    assert "uq_collection_tasks_deduplication_key" in source
    assert "fk_collection_tasks_plant_id" in source
    assert "ix_collection_tasks_claimable" in source
    assert "collectiontaskstatus" in source


def test_auth_sessions_rate_limits_and_roles_migration_is_present() -> None:
    source = (
        ROOT
        / "migrations"
        / "versions"
        / "20260726_0024_auth_sessions_rate_limits_roles.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260726_0024"' in source
    assert 'down_revision = "20260720_0023"' in source
    assert '"auth_sessions"' in source
    assert '"refresh_token_hash"' in source
    assert '"login_rate_limits"' in source
    assert '"role"' in source


def test_bill_tariff_fields_migration_is_present() -> None:
    source = (
        ROOT
        / "migrations"
        / "versions"
        / "20260801_0028_add_bill_tariff_fields.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260801_0028"' in source
    assert 'down_revision = "20260731_0027"' in source
    assert "batch_alter_table" in source
    assert '"tariff_with_taxes_brl_kwh"' in source
    assert '"tariff_without_taxes_brl_kwh"' in source
    assert '"wire_b_tariff_brl_kwh"' in source
    assert "sa.Numeric(12, 6)" in source
    assert "nullable=True" in source

    def upgrade_body(text: str) -> str:
        start = text.index("def upgrade()")
        end = text.index("def downgrade()")
        return text[start:end]

    def downgrade_body(text: str) -> str:
        start = text.index("def downgrade()")
        return text[start:]

    assert "drop_column" not in upgrade_body(source)
    assert "add_column" not in downgrade_body(source)


def test_climate_temperature_mean_migration_is_present() -> None:
    source = (
        ROOT
        / "migrations"
        / "versions"
        / "20260801_0029_add_climate_temperature_mean.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260801_0029"' in source
    assert 'down_revision = "20260801_0028"' in source
    assert "batch_alter_table" in source
    assert '"temperature_mean_c"' in source
    assert "sa.Numeric(5, 2)" in source
    assert "nullable=True" in source

    def upgrade_body(text: str) -> str:
        start = text.index("def upgrade()")
        end = text.index("def downgrade()")
        return text[start:end]

    def downgrade_body(text: str) -> str:
        start = text.index("def downgrade()")
        return text[start:]

    assert "drop_column" not in upgrade_body(source)
    assert "add_column" not in downgrade_body(source)
    assert "drop_column" in downgrade_body(source)


def test_organization_id_orm_nullability_matches_production_migrations() -> None:
    from mplacas.credentials.db_models import ApiCredentialRecord, OperationalUserRecord
    from mplacas.db.models import Plant

    assert Plant.__table__.c.organization_id.nullable is False
    assert OperationalUserRecord.__table__.c.organization_id.nullable is False
    assert ApiCredentialRecord.__table__.c.organization_id.nullable is False
