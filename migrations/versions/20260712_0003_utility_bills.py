"""Add utility bills.

Revision ID: 20260712_0003
Revises: 20260712_0002
"""

from alembic import op
import sqlalchemy as sa

revision = "20260712_0003"
down_revision = "20260712_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bill_status = sa.Enum("PENDING_REVIEW", "CONFIRMED", "REJECTED", name="billstatus")
    bill_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "utility_bills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("distributor", sa.String(length=60), nullable=False),
        sa.Column("reference_month", sa.String(length=7), nullable=False),
        sa.Column("cycle_start", sa.Date(), nullable=False),
        sa.Column("cycle_end", sa.Date(), nullable=False),
        sa.Column("billed_days", sa.Integer(), nullable=False),
        sa.Column("imported_kwh", sa.Numeric(12, 3), nullable=False),
        sa.Column("injected_kwh", sa.Numeric(12, 3), nullable=False),
        sa.Column("compensated_kwh", sa.Numeric(12, 3), nullable=False),
        sa.Column("credit_balance_kwh", sa.Numeric(12, 3), nullable=False),
        sa.Column("total_amount_brl", sa.Numeric(12, 2), nullable=False),
        sa.Column("public_lighting_brl", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", bill_status, nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("distributor", "reference_month", "cycle_start", "cycle_end"),
        sa.UniqueConstraint("source_hash"),
    )
    op.create_index("ix_utility_bills_distributor", "utility_bills", ["distributor"])
    op.create_index("ix_utility_bills_reference_month", "utility_bills", ["reference_month"])
    op.create_index("ix_utility_bills_status", "utility_bills", ["status"])


def downgrade() -> None:
    op.drop_index("ix_utility_bills_status", table_name="utility_bills")
    op.drop_index("ix_utility_bills_reference_month", table_name="utility_bills")
    op.drop_index("ix_utility_bills_distributor", table_name="utility_bills")
    op.drop_table("utility_bills")
    sa.Enum(name="billstatus").drop(op.get_bind(), checkfirst=True)
