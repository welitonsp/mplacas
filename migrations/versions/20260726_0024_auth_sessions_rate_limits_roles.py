"""Add auth sessions, login rate limits and user roles.

Revision ID: 20260726_0024
Revises: 20260720_0023
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa

revision = "20260726_0024"
down_revision = "20260720_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("operational_users") as batch:
        batch.add_column(
            sa.Column(
                "role",
                sa.String(length=16),
                nullable=False,
                server_default="ADMIN",
            )
        )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_session_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["operational_users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_session_id"],
            ["auth_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index(
        "ix_auth_sessions_organization_id",
        "auth_sessions",
        ["organization_id"],
    )
    op.create_index(
        "ix_auth_sessions_refresh_token_hash",
        "auth_sessions",
        ["refresh_token_hash"],
        unique=True,
    )
    op.create_index("ix_auth_sessions_active", "auth_sessions", ["active"])

    op.create_table(
        "login_rate_limits",
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "first_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        "ix_login_rate_limits_locked_until",
        "login_rate_limits",
        ["locked_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_login_rate_limits_locked_until", table_name="login_rate_limits")
    op.drop_table("login_rate_limits")

    op.drop_index("ix_auth_sessions_active", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_refresh_token_hash", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_organization_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")

    with op.batch_alter_table("operational_users") as batch:
        batch.drop_column("role")
