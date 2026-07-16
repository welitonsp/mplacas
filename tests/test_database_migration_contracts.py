from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
