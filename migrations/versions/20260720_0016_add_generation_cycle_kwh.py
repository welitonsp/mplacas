"""Add generation_cycle_kwh to utility_bills.

Revision ID: 20260720_0016
Revises: 20260719_0015
"""

from alembic import op
import sqlalchemy as sa

revision = "20260720_0016"
down_revision = "20260719_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "utility_bills",
        sa.Column("generation_cycle_kwh", sa.Numeric(12, 3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("utility_bills", "generation_cycle_kwh")
