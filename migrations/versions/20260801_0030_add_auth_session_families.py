"""Add refresh-token session families for replay revocation.

Revision ID: 20260801_0030
Revises: 20260801_0029
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa

revision = "20260801_0030"
down_revision = "20260801_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("auth_sessions") as batch:
        batch.add_column(sa.Column("family_id", sa.Uuid(), nullable=True))

    op.execute(sa.text("UPDATE auth_sessions SET family_id = id WHERE family_id IS NULL"))

    with op.batch_alter_table("auth_sessions") as batch:
        batch.alter_column("family_id", existing_type=sa.Uuid(), nullable=False)
        batch.create_index("ix_auth_sessions_family_id", ["family_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("auth_sessions") as batch:
        batch.drop_index("ix_auth_sessions_family_id")
        batch.drop_column("family_id")
