"""Add evidence-aware daily PV loss assessments.

Revision ID: 20260802_0036
Revises: 20260802_0035
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_0036"
down_revision = "20260802_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_pv_loss_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("evidence_level", sa.String(24), nullable=False),
        sa.Column("taxonomy_model_version", sa.String(80), nullable=False),
        sa.Column("performance_model_version", sa.String(80), nullable=False),
        sa.Column("baseline_model_version", sa.String(80), nullable=True),
        sa.Column("estimated_loss_percent", sa.Numeric(7, 2), nullable=True),
        sa.Column("evidence_codes", sa.JSON(), nullable=False),
        sa.Column("limitation", sa.String(240), nullable=True),
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
            "estimated_loss_percent IS NULL OR estimated_loss_percent >= 0",
            name="ck_pv_loss_estimate_nonnegative",
        ),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plant_id",
            "observation_date",
            "category",
            "taxonomy_model_version",
            name="uq_daily_pv_loss_assessment_identity",
        ),
    )
    op.create_index(
        "ix_daily_pv_loss_assessments_plant_id",
        "daily_pv_loss_assessments",
        ["plant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_daily_pv_loss_assessments_plant_id",
        table_name="daily_pv_loss_assessments",
    )
    op.drop_table("daily_pv_loss_assessments")
