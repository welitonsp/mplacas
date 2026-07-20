"""Add index on daily_energy(production_date, device_id) for range scans.

Revision ID: 20260720_0017
Revises: 20260720_0016
"""

from alembic import op

revision = "20260720_0017"
down_revision = "20260720_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_daily_energy_date_device",
        "daily_energy",
        ["production_date", "device_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_daily_energy_date_device", table_name="daily_energy")
