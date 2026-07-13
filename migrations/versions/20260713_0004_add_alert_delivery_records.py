"""Add durable alert delivery ledger.

Revision ID: 20260713_0004
Revises: 20260712_0003
"""

from alembic import op
import sqlalchemy as sa

revision = "20260713_0004"
down_revision = "20260712_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_delivery_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("destination_ref", sa.String(length=128), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index(
        "ix_alert_delivery_records_fingerprint",
        "alert_delivery_records",
        ["fingerprint"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_alert_delivery_records_fingerprint",
        table_name="alert_delivery_records",
    )
    op.drop_table("alert_delivery_records")
