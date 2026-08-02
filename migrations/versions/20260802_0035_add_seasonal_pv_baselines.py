"""Add robust seasonal PV baseline snapshots.

Revision ID: 20260802_0035
Revises: 20260802_0034
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_0035"
down_revision = "20260802_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seasonal_pv_baseline_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("baseline_model_version", sa.String(80), nullable=False),
        sa.Column("performance_model_version", sa.String(80), nullable=False),
        sa.Column("metric_nature", sa.String(80), nullable=False),
        sa.Column("clear_sky_index_nature", sa.String(80), nullable=False),
        sa.Column("season_key", sa.String(16), nullable=False),
        sa.Column("reference_start_date", sa.Date(), nullable=False),
        sa.Column("reference_end_date", sa.Date(), nullable=False),
        sa.Column("baseline_sample_count", sa.Integer(), nullable=False),
        sa.Column("baseline_excluded_count", sa.Integer(), nullable=False),
        sa.Column("comparison_start_date", sa.Date(), nullable=False),
        sa.Column("comparison_sample_count", sa.Integer(), nullable=False),
        sa.Column("clear_sky_poa_p90_kwh_m2", sa.Numeric(10, 3), nullable=False),
        sa.Column("target_clear_sky_index", sa.Numeric(8, 4), nullable=True),
        sa.Column(
            "baseline_median_performance_ratio", sa.Numeric(8, 4), nullable=False
        ),
        sa.Column("baseline_mad", sa.Numeric(8, 4), nullable=False),
        sa.Column("baseline_q10", sa.Numeric(8, 4), nullable=False),
        sa.Column("baseline_q90", sa.Numeric(8, 4), nullable=False),
        sa.Column(
            "comparison_median_performance_ratio", sa.Numeric(8, 4), nullable=False
        ),
        sa.Column("degradation_percent", sa.Numeric(7, 2), nullable=False),
        sa.Column("annualized_degradation_percent", sa.Numeric(7, 2), nullable=True),
        sa.Column("degradation_status", sa.String(16), nullable=False),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
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
            "baseline_sample_count > 0", name="ck_seasonal_baseline_samples_positive"
        ),
        sa.CheckConstraint(
            "comparison_sample_count > 0",
            name="ck_seasonal_comparison_samples_positive",
        ),
        sa.CheckConstraint(
            "clear_sky_poa_p90_kwh_m2 > 0",
            name="ck_seasonal_clear_sky_poa_positive",
        ),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plant_id",
            "observation_date",
            "baseline_model_version",
            name="uq_seasonal_pv_baseline_identity",
        ),
    )
    op.create_index(
        "ix_seasonal_pv_baseline_results_plant_id",
        "seasonal_pv_baseline_results",
        ["plant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_seasonal_pv_baseline_results_plant_id",
        table_name="seasonal_pv_baseline_results",
    )
    op.drop_table("seasonal_pv_baseline_results")
