"""Add versioned daily PV performance indicators.

Revision ID: 20260802_0034
Revises: 20260802_0033
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_0034"
down_revision = "20260802_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_pv_performance_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("solar_model_version", sa.String(80), nullable=False),
        sa.Column("performance_model_version", sa.String(80), nullable=False),
        sa.Column("climate_source", sa.String(40), nullable=False),
        sa.Column("performance_ratio_nature", sa.String(80), nullable=False),
        sa.Column("availability_nature", sa.String(80), nullable=False),
        sa.Column("uncertainty_percent", sa.Numeric(6, 3), nullable=True),
        sa.Column("uncertainty_nature", sa.String(80), nullable=False),
        sa.Column("measured_energy_kwh", sa.Numeric(12, 3), nullable=False),
        sa.Column("dc_capacity_kwp", sa.Numeric(10, 3), nullable=False),
        sa.Column("poa_irradiation_kwh_m2", sa.Numeric(10, 3), nullable=False),
        sa.Column("final_yield_kwh_per_kwp", sa.Numeric(12, 3), nullable=False),
        sa.Column("reference_yield_hours", sa.Numeric(10, 3), nullable=False),
        sa.Column("performance_ratio", sa.Numeric(8, 4), nullable=False),
        sa.Column(
            "temperature_corrected_performance_ratio", sa.Numeric(8, 4), nullable=True
        ),
        sa.Column("reporting_availability_ratio", sa.Numeric(8, 4), nullable=True),
        sa.Column("reporting_device_count", sa.Integer(), nullable=False),
        sa.Column("configured_device_count", sa.Integer(), nullable=False),
        sa.Column("reporting_capacity_kwp", sa.Numeric(10, 3), nullable=True),
        sa.Column("configured_device_capacity_kwp", sa.Numeric(10, 3), nullable=True),
        sa.Column("data_quality_status", sa.String(24), nullable=False),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.Column("units_json", sa.JSON(), nullable=False),
        sa.Column("assumptions_json", sa.JSON(), nullable=False),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "measured_energy_kwh >= 0", name="ck_pv_performance_energy_nonnegative"
        ),
        sa.CheckConstraint(
            "dc_capacity_kwp > 0", name="ck_pv_performance_dc_capacity_positive"
        ),
        sa.CheckConstraint(
            "poa_irradiation_kwh_m2 > 0", name="ck_pv_performance_poa_positive"
        ),
        sa.CheckConstraint(
            "performance_ratio >= 0", name="ck_pv_performance_pr_nonnegative"
        ),
        sa.CheckConstraint(
            "reporting_availability_ratio IS NULL OR "
            "(reporting_availability_ratio >= 0 AND reporting_availability_ratio <= 1)",
            name="ck_pv_performance_availability_range",
        ),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plant_id",
            "observation_date",
            "solar_model_version",
            "performance_model_version",
            name="uq_daily_pv_performance_identity",
        ),
    )
    op.create_index(
        "ix_daily_pv_performance_results_plant_id",
        "daily_pv_performance_results",
        ["plant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_daily_pv_performance_results_plant_id",
        table_name="daily_pv_performance_results",
    )
    op.drop_table("daily_pv_performance_results")
