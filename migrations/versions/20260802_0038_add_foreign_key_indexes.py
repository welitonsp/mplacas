"""Add indexes for nullable foreign-key lookups.

Revision ID: 20260802_0038
Revises: 20260802_0037
"""

from alembic import op


revision = "20260802_0038"
down_revision = "20260802_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_auth_sessions_replaced_by_session_id",
        "auth_sessions",
        ["replaced_by_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_invitations_created_by_user_id",
        "user_invitations",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_invitations_accepted_user_id",
        "user_invitations",
        ["accepted_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_invitations_accepted_user_id",
        table_name="user_invitations",
    )
    op.drop_index(
        "ix_user_invitations_created_by_user_id",
        table_name="user_invitations",
    )
    op.drop_index(
        "ix_auth_sessions_replaced_by_session_id",
        table_name="auth_sessions",
    )
