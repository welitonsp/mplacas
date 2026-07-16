"""Add audit events.

Revision ID: 20260716_0009
Revises: 20260716_0008
"""

from alembic import op
import sqlalchemy as sa

revision = "20260716_0009"
down_revision = "20260716_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("actor_role", sa.String(length=40), nullable=False),
        sa.Column("actor_credential_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"], unique=False)
    op.create_index(
        "ix_audit_events_action_created_at",
        "audit_events",
        ["action", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_actor",
        "audit_events",
        ["actor_role", "actor_credential_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_created_at",
        "audit_events",
        ["created_at"],
        unique=False,
    )
    op.create_index("ix_audit_events_outcome", "audit_events", ["outcome"], unique=False)
    op.create_index(
        "ix_audit_events_resource",
        "audit_events",
        ["resource_type", "resource_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_resource_type",
        "audit_events",
        ["resource_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_resource_type", table_name="audit_events")
    op.drop_index("ix_audit_events_resource", table_name="audit_events")
    op.drop_index("ix_audit_events_outcome", table_name="audit_events")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_actor", table_name="audit_events")
    op.drop_index("ix_audit_events_action_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_table("audit_events")
