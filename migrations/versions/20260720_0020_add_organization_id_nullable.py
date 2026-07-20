"""Add organization_id (nullable) to plants, operational_users, api_credentials.

Revision ID: 20260720_0020
Revises: 20260720_0019
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20260720_0020"
down_revision = "20260720_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("plants") as batch:
        batch.add_column(sa.Column("organization_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_plants_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_index("ix_plants_organization_id", ["organization_id"])

    with op.batch_alter_table("operational_users") as batch:
        batch.add_column(sa.Column("organization_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_operational_users_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_operational_users_organization_id", ["organization_id"])

    with op.batch_alter_table("api_credentials") as batch:
        batch.add_column(sa.Column("organization_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_api_credentials_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_index("ix_api_credentials_organization_id", ["organization_id"])


def downgrade() -> None:
    with op.batch_alter_table("api_credentials") as batch:
        batch.drop_index("ix_api_credentials_organization_id")
        batch.drop_constraint("fk_api_credentials_organization_id", type_="foreignkey")
        batch.drop_column("organization_id")

    with op.batch_alter_table("operational_users") as batch:
        batch.drop_index("ix_operational_users_organization_id")
        batch.drop_constraint("fk_operational_users_organization_id", type_="foreignkey")
        batch.drop_column("organization_id")

    with op.batch_alter_table("plants") as batch:
        batch.drop_index("ix_plants_organization_id")
        batch.drop_constraint("fk_plants_organization_id", type_="foreignkey")
        batch.drop_column("organization_id")
