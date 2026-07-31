"""Add telegram_chat_id to organizations.

Revision ID: 20260731_0025
Revises: 20260726_0024
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa

revision = "20260731_0025"
down_revision = "20260726_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(
            sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True)
        )
        batch.create_index(
            "ix_organizations_telegram_chat_id",
            ["telegram_chat_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_index("ix_organizations_telegram_chat_id")
        batch.drop_column("telegram_chat_id")
