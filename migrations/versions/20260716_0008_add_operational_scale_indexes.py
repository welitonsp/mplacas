"""Add operational scale indexes.

Revision ID: 20260716_0008
Revises: 20260713_0007
"""

from alembic import op

revision = "20260716_0008"
down_revision = "20260713_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_devices_plant_id", "devices", ["plant_id"], unique=False)
    op.create_index(
        "ix_daily_energy_versions_daily_energy_id",
        "daily_energy_versions",
        ["daily_energy_id"],
        unique=False,
    )
    op.create_index(
        "ix_utility_bills_plant_status_cycle",
        "utility_bills",
        ["plant_id", "status", "cycle_end", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_utility_bills_plant_status_cycle", table_name="utility_bills")
    op.drop_index(
        "ix_daily_energy_versions_daily_energy_id",
        table_name="daily_energy_versions",
    )
    op.drop_index("ix_devices_plant_id", table_name="devices")
