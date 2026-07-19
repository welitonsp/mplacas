"""Add transactional outbox events.

Revision ID: 20260719_0012
Revises: 20260719_0011
"""

from alembic import op
import sqlalchemy as sa

revision = "20260719_0012"
down_revision = "20260719_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = sa.Enum("PENDING", "PROCESSING", "DELIVERED", "FAILED", name="outboxeventstatus")
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("destination_ref", sa.String(length=128), nullable=False),
        sa.Column("deduplication_key", sa.String(length=255), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deduplication_key"),
    )
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index(
        "ix_outbox_events_destination_created",
        "outbox_events",
        ["destination_ref", "created_at"],
    )
    op.create_index(
        "ix_outbox_events_dispatch",
        "outbox_events",
        ["event_type", "destination_ref", "status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_outbox_events_plant_created",
        "outbox_events",
        ["plant_id", "created_at"],
    )
    op.create_index(
        "ix_outbox_events_status_available",
        "outbox_events",
        ["status", "available_at", "created_at"],
    )


def downgrade() -> None:
    status = sa.Enum("PENDING", "PROCESSING", "DELIVERED", "FAILED", name="outboxeventstatus")
    op.drop_index("ix_outbox_events_status_available", table_name="outbox_events")
    op.drop_index("ix_outbox_events_plant_created", table_name="outbox_events")
    op.drop_index("ix_outbox_events_dispatch", table_name="outbox_events")
    op.drop_index("ix_outbox_events_destination_created", table_name="outbox_events")
    op.drop_index("ix_outbox_events_event_type", table_name="outbox_events")
    op.drop_table("outbox_events")
    status.drop(op.get_bind(), checkfirst=True)
