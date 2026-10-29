from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_utility_bill_initial_unique_constraint_is_named_for_batch_migrations() -> None:
    migration = (ROOT / "migrations" / "versions" / "20260712_0003_utility_bills.py").read_text(
        encoding="utf-8"
    )

    assert "uq_utility_bills_cycle" in migration


def test_utility_bill_plant_scope_migration_reflects_sqlite_constraint_names() -> None:
    migration = (
        ROOT / "migrations" / "versions" / "20260713_0005_scope_utility_bills_by_plant.py"
    ).read_text(encoding="utf-8")

    assert "_BILL_NAMING_CONVENTION" in migration
    assert "naming_convention=_BILL_NAMING_CONVENTION" in migration


def test_operational_scale_indexes_migration_is_present() -> None:
    migration = (
        ROOT / "migrations" / "versions" / "20260716_0008_add_operational_scale_indexes.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "20260713_0007"' in migration
    assert '"ix_devices_plant_id"' in migration
    assert '"ix_daily_energy_versions_daily_energy_id"' in migration
    assert '"ix_utility_bills_plant_status_cycle"' in migration
    assert '["plant_id", "status", "cycle_end", "created_at"]' in migration


def test_audit_events_migration_is_present() -> None:
    migration = (ROOT / "migrations" / "versions" / "20260716_0009_add_audit_events.py").read_text(
        encoding="utf-8"
    )

    assert 'down_revision = "20260716_0008"' in migration
    assert '"audit_events"' in migration
    assert '"actor_credential_id"' in migration
    assert '"request_id"' in migration
    assert '"ix_audit_events_actor"' in migration
    assert '"ix_audit_events_resource"' in migration


def test_utility_bill_plant_scope_migration_is_present() -> None:
    migration = (
        ROOT / "migrations" / "versions" / "20260716_0010_require_utility_bill_plant.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "20260716_0009"' in migration
    assert "utility_bills.plant_id has legacy NULL rows" in migration
    assert "UPDATE utility_bills SET plant_id = :plant_id WHERE plant_id IS NULL" in migration
    assert '"plant_id"' in migration
    assert "nullable=False" in migration


def test_monthly_report_snapshot_migration_is_present() -> None:
    migration = (
        ROOT / "migrations" / "versions" / "20260719_0011_add_monthly_report_snapshots.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "20260716_0010"' in migration
    assert '"monthly_report_snapshots"' in migration
    assert '"payload_json"' in migration
    assert '"payload_sha256"' in migration
    assert 'sa.UniqueConstraint("bill_id"' in migration
    assert '"ix_monthly_report_snapshots_plant_reference"' in migration


def test_transactional_outbox_migration_is_present() -> None:
    migration = (
        ROOT / "migrations" / "versions" / "20260719_0012_add_transactional_outbox.py"
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
    source = (ROOT / "migrations" / "versions" / "20260719_0013_add_api_credentials.py").read_text(
        encoding="utf-8"
    )

    assert 'revision = "20260719_0013"' in source
    assert 'down_revision = "20260719_0012"' in source
    assert '"api_credentials"' in source
    assert '"key_hash"' in source
    assert "uq_api_credentials_key_hash" in source
    assert "sa.UniqueConstraint" in source


def test_operational_users_migration_is_present() -> None:
    source = (
        ROOT / "migrations" / "versions" / "20260719_0014_add_operational_users.py"
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
        ROOT / "migrations" / "versions" / "20260719_0015_add_collection_task_queue.py"
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
        ROOT / "migrations" / "versions" / "20260726_0024_auth_sessions_rate_limits_roles.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260726_0024"' in source
    assert 'down_revision = "20260720_0023"' in source
    assert '"auth_sessions"' in source
    assert '"refresh_token_hash"' in source
    assert '"login_rate_limits"' in source
    assert '"role"' in source


def test_auth_session_family_migration_is_present() -> None:
    source = (
        ROOT / "migrations" / "versions" / "20260801_0030_add_auth_session_families.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260801_0030"' in source
    assert 'down_revision = "20260801_0029"' in source
    assert '"family_id"' in source
    assert "UPDATE auth_sessions SET family_id = id" in source
    assert 'batch.create_index("ix_auth_sessions_family_id"' in source


def test_nullable_foreign_keys_have_indexes_in_migration_and_orm() -> None:
    from mplacas.auth.db_models import AuthSessionRecord
    from mplacas.organizations.invitation_db_models import UserInvitationRecord

    source = (
        ROOT / "migrations" / "versions" / "20260802_0038_add_foreign_key_indexes.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260802_0038"' in source
    assert 'down_revision = "20260802_0037"' in source
    for index_name in (
        "ix_auth_sessions_replaced_by_session_id",
        "ix_user_invitations_created_by_user_id",
        "ix_user_invitations_accepted_user_id",
    ):
        assert index_name in source

    assert AuthSessionRecord.__table__.c.replaced_by_session_id.index is True
    assert UserInvitationRecord.__table__.c.created_by_user_id.index is True
    assert UserInvitationRecord.__table__.c.accepted_user_id.index is True


def test_bill_tariff_fields_migration_is_present() -> None:
    source = (
        ROOT / "migrations" / "versions" / "20260801_0028_add_bill_tariff_fields.py"
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
        ROOT / "migrations" / "versions" / "20260801_0029_add_climate_temperature_mean.py"
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


def test_bill_source_hash_is_scoped_by_plant_with_safe_rollback() -> None:
    import sqlalchemy as sa

    from mplacas.billing.db_models import UtilityBillRecord

    migration = (
        ROOT / "migrations" / "versions" / "20260801_0031_scope_bill_source_hash_by_plant.py"
    ).read_text(encoding="utf-8")
    table_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in UtilityBillRecord.__table__.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }

    assert table_constraints["uq_utility_bills_plant_source_hash"] == (
        "plant_id",
        "source_hash",
    )
    assert '_duplicate_count("plant_id, source_hash")' in migration
    assert '_duplicate_count("source_hash")' in migration
    assert "cannot restore global source_hash uniqueness" in migration


def test_plant_technical_configuration_migration_matches_orm() -> None:
    import sqlalchemy as sa

    from mplacas.db.models import Device, Plant

    source = (
        ROOT / "migrations" / "versions" / "20260802_0032_add_plant_technical_configuration.py"
    ).read_text(encoding="utf-8")
    plant_columns = Plant.__table__.c
    device_columns = Device.__table__.c
    plant_checks = {
        constraint.name
        for constraint in Plant.__table__.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    device_checks = {
        constraint.name
        for constraint in Device.__table__.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }

    assert 'revision = "20260802_0032"' in source
    assert 'down_revision = "20260801_0031"' in source
    assert plant_columns.ac_capacity_kw.type.scale == 3
    assert plant_columns.array_tilt_degrees.type.scale == 2
    assert plant_columns.array_azimuth_degrees.type.scale == 2
    assert plant_columns.commissioned_on.type.python_type is __import__("datetime").date
    assert device_columns.dc_capacity_kwp.type.scale == 3
    assert device_columns.ac_capacity_kw.type.scale == 3
    assert "ck_plants_array_tilt_range" in plant_checks
    assert "ck_plants_array_azimuth_range" in plant_checks
    assert "ck_plants_module_technology" in plant_checks
    assert "ck_devices_dc_capacity_positive" in device_checks
    assert "ck_devices_ac_capacity_positive" in device_checks
    assert 'batch.drop_column("commissioned_on")' in source


def test_daily_solar_model_result_migration_is_versioned_and_reversible() -> None:
    import sqlalchemy as sa

    from mplacas.photovoltaic.db_models import DailySolarModelResultRecord

    source = (
        ROOT / "migrations" / "versions" / "20260802_0033_add_daily_solar_model_results.py"
    ).read_text(encoding="utf-8")
    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in DailySolarModelResultRecord.__table__.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }

    assert 'revision = "20260802_0033"' in source
    assert 'down_revision = "20260802_0032"' in source
    assert unique_constraints["uq_daily_solar_model_result_identity"] == (
        "plant_id",
        "observation_date",
        "climate_source",
        "model_version",
    )
    assert 'sa.Column("model_version", sa.String(80), nullable=False)' in source
    assert 'sa.Column("quality_flags", sa.JSON(), nullable=False)' in source
    assert 'sa.Column("assumptions_json", sa.JSON(), nullable=False)' in source
    assert "ck_solar_result_poa_nonnegative" in source
    assert 'op.drop_table("daily_solar_model_results")' in source


def test_daily_pv_performance_migration_preserves_metric_semantics() -> None:
    import sqlalchemy as sa

    from mplacas.photovoltaic.db_models import DailyPvPerformanceRecord

    source = (
        ROOT / "migrations" / "versions" / "20260802_0034_add_daily_pv_performance.py"
    ).read_text(encoding="utf-8")
    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in DailyPvPerformanceRecord.__table__.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }

    assert 'revision = "20260802_0034"' in source
    assert 'down_revision = "20260802_0033"' in source
    assert unique_constraints["uq_daily_pv_performance_identity"] == (
        "plant_id",
        "observation_date",
        "solar_model_version",
        "performance_model_version",
    )
    assert 'sa.Column("performance_ratio_nature", sa.String(80), nullable=False)' in source
    assert 'sa.Column("availability_nature", sa.String(80), nullable=False)' in source
    assert 'sa.Column("uncertainty_percent", sa.Numeric(6, 3), nullable=True)' in source
    assert 'sa.Column("uncertainty_nature", sa.String(80), nullable=False)' in source
    assert 'sa.Column("units_json", sa.JSON(), nullable=False)' in source
    assert "ck_pv_performance_availability_range" in source
    assert 'op.drop_table("daily_pv_performance_results")' in source


def test_seasonal_baseline_migration_is_versioned_and_contamination_auditable() -> None:
    import sqlalchemy as sa

    from mplacas.photovoltaic.db_models import SeasonalPvBaselineRecord

    source = (
        ROOT / "migrations" / "versions" / "20260802_0035_add_seasonal_pv_baselines.py"
    ).read_text(encoding="utf-8")
    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in SeasonalPvBaselineRecord.__table__.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }

    assert 'revision = "20260802_0035"' in source
    assert 'down_revision = "20260802_0034"' in source
    assert unique_constraints["uq_seasonal_pv_baseline_identity"] == (
        "plant_id",
        "observation_date",
        "baseline_model_version",
    )
    assert 'sa.Column("clear_sky_index_nature", sa.String(80), nullable=False)' in source
    assert 'sa.Column("baseline_mad", sa.Numeric(8, 4), nullable=False)' in source
    assert 'sa.Column("baseline_q10", sa.Numeric(8, 4), nullable=False)' in source
    assert 'sa.Column("baseline_q90", sa.Numeric(8, 4), nullable=False)' in source
    assert 'sa.Column("assumptions_json", sa.JSON(), nullable=False)' in source
    assert 'op.drop_table("seasonal_pv_baseline_results")' in source


def test_loss_taxonomy_migration_preserves_category_level_evidence() -> None:
    import sqlalchemy as sa

    from mplacas.photovoltaic.db_models import DailyPvLossAssessmentRecord

    source = (
        ROOT / "migrations" / "versions" / "20260802_0036_add_daily_pv_loss_assessments.py"
    ).read_text(encoding="utf-8")
    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in DailyPvLossAssessmentRecord.__table__.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }

    assert 'revision = "20260802_0036"' in source
    assert 'down_revision = "20260802_0035"' in source
    assert unique_constraints["uq_daily_pv_loss_assessment_identity"] == (
        "plant_id",
        "observation_date",
        "category",
        "taxonomy_model_version",
    )
    assert 'sa.Column("evidence_level", sa.String(24), nullable=False)' in source
    assert 'sa.Column("evidence_codes", sa.JSON(), nullable=False)' in source
    assert 'sa.Column("limitation", sa.String(240), nullable=True)' in source
    assert "ck_pv_loss_estimate_nonnegative" in source
    assert 'op.drop_table("daily_pv_loss_assessments")' in source


def test_organization_default_plant_migration_matches_orm() -> None:

    from mplacas.organizations.db_models import OrganizationRecord

    source = (
        ROOT
        / "migrations"
        / "versions"
        / "20260805_0043_add_organization_default_plant.py"
    ).read_text(encoding="utf-8")
    organization_columns = OrganizationRecord.__table__.c
    foreign_keys = {
        fk.constraint.name: (fk.parent.name, fk.target_fullname)
        for fk in OrganizationRecord.__table__.foreign_keys
    }

    assert 'revision = "20260805_0043"' in source
    assert 'down_revision = "20260804_0042"' in source
    assert "batch_alter_table" in source
    assert '"default_plant_id"' in source
    assert organization_columns.default_plant_id.nullable is True
    assert organization_columns.default_plant_id.type.python_type is __import__("uuid").UUID
    assert foreign_keys["fk_organizations_default_plant_id"] == (
        "default_plant_id",
        "plants.id",
    )
    assert not organization_columns.default_plant_id.index

    def upgrade_body(text: str) -> str:
        start = text.index("def upgrade()")
        end = text.index("def downgrade()")
        return text[start:end]

    def downgrade_body(text: str) -> str:
        start = text.index("def downgrade()")
        return text[start:]

    assert "drop_column" not in upgrade_body(source)
    assert "ondelete=\"SET NULL\"" in upgrade_body(source)
    assert "UPDATE organizations SET default_plant_id" in upgrade_body(source)
    assert "add_column" not in downgrade_body(source)
    assert "drop_column" in downgrade_body(source)
    assert 'drop_constraint("fk_organizations_default_plant_id"' in downgrade_body(source)


def test_postgres_ci_covers_migrations_locks_outbox_queue_and_readiness() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    integration = (ROOT / "tests" / "test_postgres_operational_contracts.py").read_text(
        encoding="utf-8"
    )

    assert "Migrate empty PostgreSQL database" in workflow
    assert "alembic upgrade head" in workflow
    assert "alembic check" in workflow
    assert "pytest -q -m postgres_integration" in workflow
    assert "postgres-integration-report.txt" in workflow
    assert "CollectionQueueRepository(first).claim" in integration
    assert "OutboxRepository(first).claim" in integration
    assert "asyncio.wait_for" in integration
    assert "main_module.ready" in integration
    assert "SELECT version_num FROM alembic_version" in integration


def test_auth_timestamp_migration_rejects_nulls_before_enforcement() -> None:
    source = (
        ROOT / "migrations" / "versions" / "20260802_0037_enforce_auth_timestamp_not_null.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260802_0037"' in source
    assert 'down_revision = "20260802_0036"' in source
    assert '_assert_no_nulls("auth_sessions", "created_at")' in source
    assert '_assert_no_nulls("login_rate_limits", "first_attempt_at")' in source
    assert source.count("nullable=False") == 2
    assert source.count("nullable=True") == 2


def test_plant_investment_amount_migration_matches_orm() -> None:
    import sqlalchemy as sa

    from mplacas.db.models import Plant

    source = (
        ROOT / "migrations" / "versions" / "20260804_0042_add_plant_investment_amount.py"
    ).read_text(encoding="utf-8")
    plant_columns = Plant.__table__.c
    plant_checks = {
        constraint.name
        for constraint in Plant.__table__.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }

    assert 'revision = "20260804_0042"' in source
    assert 'down_revision = "20260803_0041"' in source
    assert "batch_alter_table" in source
    assert '"investment_amount_brl"' in source
    assert '"investment_recorded_on"' in source
    assert "sa.Numeric(12, 2)" in source
    assert "nullable=True" in source
    assert plant_columns.investment_amount_brl.type.precision == 12
    assert plant_columns.investment_amount_brl.type.scale == 2
    assert plant_columns.investment_amount_brl.nullable is True
    assert plant_columns.investment_recorded_on.type.python_type is __import__("datetime").date
    assert plant_columns.investment_recorded_on.nullable is True
    assert "ck_plants_investment_amount_positive" in plant_checks

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
    assert 'batch.drop_constraint("ck_plants_investment_amount_positive"' in downgrade_body(
        source
    )


def test_market_index_monthly_migration_matches_orm() -> None:
    from mplacas.market.db_models import MarketIndexMonthlyRecord

    source = (
        ROOT / "migrations" / "versions" / "20261019_0044_add_market_index_monthly.py"
    ).read_text(encoding="utf-8")
    columns = MarketIndexMonthlyRecord.__table__.c

    assert 'revision = "20261019_0044"' in source
    assert 'down_revision = "20260805_0043"' in source
    assert 'op.drop_table("market_index_monthly")' in source
    assert 'sa.UniqueConstraint("index_code", "reference_month")' in source
    assert "sa.Numeric(12, 6)" in source
    # Dado público e global: sem coluna de dono (fica fora do RLS, ADR-079).
    assert not {"organization_id", "plant_id"} & set(columns.keys())
    assert columns.rate_percent.type.precision == 12
    assert columns.rate_percent.type.scale == 6
    assert columns.reference_month.type.length == 7


def test_distributor_tariffs_migration_matches_orm() -> None:
    from mplacas.tariffs.db_models import DistributorTariffRecord

    source = (
        ROOT / "migrations" / "versions" / "20261022_0045_add_distributor_tariffs.py"
    ).read_text(encoding="utf-8")
    columns = DistributorTariffRecord.__table__.c

    assert 'revision = "20261022_0045"' in source
    assert 'down_revision = "20261019_0044"' in source
    assert 'op.drop_table("distributor_tariffs")' in source
    assert 'sa.UniqueConstraint("distributor", "tariff_class", "valid_from")' in source
    # Dado público e global: sem coluna de dono (fica fora do RLS, ADR-080).
    assert not {"organization_id", "plant_id"} & set(columns.keys())
    assert columns.full_brl_kwh.type.precision == 10
    assert columns.full_brl_kwh.type.scale == 6
    assert columns.scee_brl_kwh.nullable is True


def test_report_snapshot_revision_migration_matches_orm() -> None:
    from mplacas.reports.db_models import MonthlyReportSnapshotRecord

    source = (
        ROOT / "migrations" / "versions" / "20261023_0046_add_report_snapshot_revision.py"
    ).read_text(encoding="utf-8")
    table = MonthlyReportSnapshotRecord.__table__
    unique_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert 'revision = "20261023_0046"' in source
    assert 'down_revision = "20261022_0045"' in source
    # Linhas existentes viram revisão 1 sem backfill ambíguo (ADR-081).
    assert 'server_default="1"' in source
    assert 'drop_constraint("uq_monthly_report_snapshots_bill"' in source
    assert "uq_monthly_report_snapshots_bill_revision" in source
    # O downgrade nunca apaga revisões: falha se houver alguma > 1.
    assert "DELETE FROM" not in source
    assert "WHERE revision > 1" in source
    assert "raise RuntimeError" in source
    assert table.c.revision.nullable is False
    assert ("bill_id", "revision") in unique_sets
    assert ("bill_id",) not in unique_sets


def test_bill_share_and_expiring_migration_matches_orm() -> None:
    from mplacas.billing.db_models import UtilityBillRecord

    source = (
        ROOT
        / "migrations"
        / "versions"
        / "20261024_0047_add_bill_scee_share_and_expiring.py"
    ).read_text(encoding="utf-8")
    columns = UtilityBillRecord.__table__.columns

    assert 'revision = "20261024_0047"' in source
    assert 'down_revision = "20261023_0046"' in source
    # Aditiva e nullable, sem backfill presumido (ADR-084).
    assert "nullable=True" in source
    assert "UPDATE" not in source.upper().replace("UPDATED", "")
    assert columns.generation_share_percent.nullable is True
    assert columns.generation_share_percent.type.precision == 5
    assert columns.generation_share_percent.type.scale == 2
    assert columns.credits_expiring_30d_kwh.nullable is True
    assert columns.credits_expiring_30d_kwh.type.precision == 12
    assert columns.credits_expiring_30d_kwh.type.scale == 3
    assert 'drop_column("credits_expiring_30d_kwh")' in source
    assert 'drop_column("generation_share_percent")' in source


def test_bill_flag_and_credits_migration_matches_orm() -> None:
    from mplacas.billing.db_models import UtilityBillRecord

    source = (
        ROOT
        / "migrations"
        / "versions"
        / "20261024_0048_add_bill_flag_and_non_energy_credits.py"
    ).read_text(encoding="utf-8")
    columns = UtilityBillRecord.__table__.columns

    assert 'revision = "20261024_0048"' in source
    assert 'down_revision = "20261024_0047"' in source
    assert columns.flag_tariff_brl_kwh.nullable is True
    assert columns.flag_tariff_brl_kwh.type.scale == 6
    assert columns.non_energy_credits_brl.nullable is True
    assert columns.non_energy_credits_brl.type.scale == 2
    assert 'drop_column("flag_tariff_brl_kwh")' in source
    assert 'drop_column("non_energy_credits_brl")' in source


def test_bill_tariff_class_migration_matches_orm() -> None:
    from mplacas.billing.db_models import UtilityBillRecord

    source = (
        ROOT / "migrations" / "versions" / "20261024_0049_add_bill_tariff_class.py"
    ).read_text(encoding="utf-8")
    column = UtilityBillRecord.__table__.columns.tariff_class

    assert 'revision = "20261024_0049"' in source
    assert 'down_revision = "20261024_0048"' in source
    assert column.nullable is True
    assert column.type.length == 60
    # O banco nunca grava classe presumida: sem backfill.
    assert "UPDATE" not in source.upper().replace("UPDATED", "")
    assert 'drop_column("tariff_class")' in source


def test_plant_expansion_proposal_migration_matches_orm() -> None:
    from mplacas.db.models import Plant

    source = (
        ROOT / "migrations" / "versions" / "20261028_0050_add_plant_expansion_proposal.py"
    ).read_text(encoding="utf-8")
    columns = Plant.__table__.columns

    assert 'revision = "20261028_0050"' in source
    assert 'down_revision = "20261024_0049"' in source
    assert columns.expansion_proposal_brl.nullable is True
    assert columns.expansion_proposal_brl.type.scale == 2
    assert columns.expansion_proposal_includes_inverter.nullable is True
    assert columns.expansion_proposal_recorded_on.nullable is True
    assert "ck_plants_expansion_proposal_positive" in source
    assert "UPDATE " not in source.upper()  # sem backfill
    assert 'drop_column("expansion_proposal_brl")' in source


def test_provider_accounts_migration_matches_orm() -> None:
    from mplacas.providers.db_models import ProviderAccountRecord

    source = (
        ROOT / "migrations" / "versions" / "20261029_0051_add_provider_accounts.py"
    ).read_text(encoding="utf-8")
    table = ProviderAccountRecord.__table__
    constraint_names = {constraint.name for constraint in table.constraints}

    assert 'revision = "20261029_0051"' in source
    assert 'down_revision = "20261028_0050"' in source
    for name in (
        "uq_provider_accounts_plant",
        "uq_provider_accounts_provider_fingerprint",
        "ck_provider_accounts_key_version",
        "ck_provider_accounts_secret_only_when_active",
    ):
        assert name in constraint_names
        assert name in source
    assert table.c.ciphertext.nullable is True
    assert table.c.login_hint.nullable is False
    # Nenhuma coluna guarda login ou senha em claro.
    assert not {"login", "password", "secret"} & set(table.c.keys())
    assert 'ondelete="CASCADE"' in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "drop_table(TABLE)" in source
