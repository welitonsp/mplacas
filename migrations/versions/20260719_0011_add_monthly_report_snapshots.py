"""Add immutable monthly report snapshots.

Revision ID: 20260719_0011
Revises: 20260716_0010
"""

from alembic import op
import sqlalchemy as sa

revision = "20260719_0011"
down_revision = "20260716_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_report_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("reference_month", sa.String(length=7), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.Column("calculation_version", sa.String(length=40), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["bill_id"], ["utility_bills.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bill_id", name="uq_monthly_report_snapshots_bill"),
    )
    op.create_index(
        "ix_monthly_report_snapshots_plant_reference",
        "monthly_report_snapshots",
        ["plant_id", "reference_month", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_monthly_report_snapshots_plant_reference",
        table_name="monthly_report_snapshots",
    )
    op.drop_table("monthly_report_snapshots")
