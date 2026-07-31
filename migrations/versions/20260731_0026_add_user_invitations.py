"""Add user_invitations table.

Revision ID: 20260731_0026
Revises: 20260731_0025
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa

revision = "20260731_0026"
down_revision = "20260731_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_user_invitations_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["operational_users.id"],
            name="fk_user_invitations_created_by_user_id",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_user_id"],
            ["operational_users.id"],
            name="fk_user_invitations_accepted_user_id",
        ),
    )
    op.create_index(
        "ix_user_invitations_organization_id",
        "user_invitations",
        ["organization_id"],
    )
    op.create_index(
        "ix_user_invitations_token_hash",
        "user_invitations",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_user_invitations_token_hash", table_name="user_invitations")
    op.drop_index("ix_user_invitations_organization_id", table_name="user_invitations")
    op.drop_table("user_invitations")
