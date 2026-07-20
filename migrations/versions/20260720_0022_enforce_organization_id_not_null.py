"""Enforce organization_id NOT NULL on plants, operational_users, api_credentials.

Revision ID: 20260720_0022
Revises: 20260720_0021
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20260720_0022"
down_revision = "20260720_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("plants") as batch:
        batch.alter_column("organization_id", existing_type=sa.Uuid(), nullable=False)

    with op.batch_alter_table("operational_users") as batch:
        batch.alter_column("organization_id", existing_type=sa.Uuid(), nullable=False)

    with op.batch_alter_table("api_credentials") as batch:
        batch.alter_column("organization_id", existing_type=sa.Uuid(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("api_credentials") as batch:
        batch.alter_column("organization_id", existing_type=sa.Uuid(), nullable=True)

    with op.batch_alter_table("operational_users") as batch:
        batch.alter_column("organization_id", existing_type=sa.Uuid(), nullable=True)

    with op.batch_alter_table("plants") as batch:
        batch.alter_column("organization_id", existing_type=sa.Uuid(), nullable=True)
