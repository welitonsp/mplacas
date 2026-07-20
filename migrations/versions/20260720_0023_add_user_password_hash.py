"""Add password_hash to operational_users.

Revision ID: 20260720_0023
Revises: 20260720_0022
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20260720_0023"
down_revision = "20260720_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("operational_users") as batch:
        batch.add_column(sa.Column("password_hash", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("operational_users") as batch:
        batch.drop_column("password_hash")
