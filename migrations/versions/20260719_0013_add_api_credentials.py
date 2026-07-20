"""Add persisted API credentials.

Revision ID: 20260719_0013
Revises: 20260719_0012
"""

from alembic import op
import sqlalchemy as sa

revision = "20260719_0013"
down_revision = "20260719_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("plant_ids", sa.JSON(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_api_credentials_name"),
        sa.UniqueConstraint("key_hash", name="uq_api_credentials_key_hash"),
    )
    op.create_index(
        "ix_api_credentials_key_hash",
        "api_credentials",
        ["key_hash"],
        unique=True,
    )
    op.create_index(
        "ix_api_credentials_active",
        "api_credentials",
        ["active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_api_credentials_active", table_name="api_credentials")
    op.drop_index("ix_api_credentials_key_hash", table_name="api_credentials")
    op.drop_table("api_credentials")
