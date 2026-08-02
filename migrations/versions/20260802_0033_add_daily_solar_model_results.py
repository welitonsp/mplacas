"""Add versioned daily POA and thermal model results.

Revision ID: 20260802_0033
Revises: 20260802_0032
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_0033"
down_revision = "20260802_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_solar_model_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("climate_source", sa.String(40), nullable=False),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("latitude_degrees", sa.Numeric(9, 6), nullable=False),
        sa.Column("array_tilt_degrees", sa.Numeric(5, 2), nullable=False),
        sa.Column("array_azimuth_degrees", sa.Numeric(5, 2), nullable=False),
        sa.Column("module_technology", sa.String(40), nullable=False),
        sa.Column("ghi_kwh_m2", sa.Numeric(10, 3), nullable=False),
        sa.Column("poa_irradiation_kwh_m2", sa.Numeric(10, 3), nullable=False),
        sa.Column("beam_horizontal_kwh_m2", sa.Numeric(10, 3), nullable=False),
        sa.Column("diffuse_horizontal_kwh_m2", sa.Numeric(10, 3), nullable=False),
        sa.Column("extraterrestrial_horizontal_kwh_m2", sa.Numeric(10, 3), nullable=False),
        sa.Column("ambient_temperature_c", sa.Numeric(5, 2), nullable=True),
        sa.Column("cell_temperature_c", sa.Numeric(5, 2), nullable=True),
        sa.Column("temperature_coefficient_per_c", sa.Numeric(7, 6), nullable=False),
        sa.Column("temperature_factor", sa.Numeric(7, 4), nullable=True),
        sa.Column(
            "temperature_adjusted_poa_equivalent_kwh_m2",
            sa.Numeric(10, 3),
            nullable=True,
        ),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.Column("assumptions_json", sa.JSON(), nullable=False),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("ghi_kwh_m2 >= 0", name="ck_solar_result_ghi_nonnegative"),
        sa.CheckConstraint(
            "poa_irradiation_kwh_m2 >= 0", name="ck_solar_result_poa_nonnegative"
        ),
        sa.CheckConstraint(
            "array_tilt_degrees >= 0 AND array_tilt_degrees <= 90",
            name="ck_solar_result_tilt_range",
        ),
        sa.CheckConstraint(
            "array_azimuth_degrees >= 0 AND array_azimuth_degrees < 360",
            name="ck_solar_result_azimuth_range",
        ),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plant_id",
            "observation_date",
            "climate_source",
            "model_version",
            name="uq_daily_solar_model_result_identity",
        ),
    )
    op.create_index(
        "ix_daily_solar_model_results_plant_id",
        "daily_solar_model_results",
        ["plant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_daily_solar_model_results_plant_id",
        table_name="daily_solar_model_results",
    )
    op.drop_table("daily_solar_model_results")
