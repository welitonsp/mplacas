"""Add temperature_mean_c to daily_climate_observations.

Revision ID: 20260801_0029
Revises: 20260801_0028
Create Date: 2026-08-01

Adds a nullable ``temperature_mean_c`` column carrying the Open-Meteo daily
mean 2m air temperature alongside the already-collected irradiance, cloud
cover and precipitation. This is a prerequisite for a future IEC 61724-1
climate-corrected Performance Ratio (irradiance *and* cell-temperature
normalized) — see ADR-019/020. No calculation is introduced here, only the
column and collection of the raw value. No backfill: legacy rows remain
NULL, honest about data collected before this column existed.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260801_0029"
down_revision = "20260801_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("daily_climate_observations") as batch:
        batch.add_column(
            sa.Column("temperature_mean_c", sa.Numeric(5, 2), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("daily_climate_observations") as batch:
        batch.drop_column("temperature_mean_c")
