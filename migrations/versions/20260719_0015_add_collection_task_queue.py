"""Add collection task queue.

Revision ID: 20260719_0015
Revises: 20260719_0014
"""

from alembic import op
import sqlalchemy as sa

revision = "20260719_0015"
down_revision = "20260719_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(length=80), nullable=False),
        sa.Column("target_date", sa.String(length=10), nullable=False),
        sa.Column("deduplication_key", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PROCESSING",
                "COMPLETED",
                "FAILED",
                name="collectiontaskstatus",
            ),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(
            ["plant_id"],
            ["plants.id"],
            name="fk_collection_tasks_plant_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "deduplication_key",
            name="uq_collection_tasks_deduplication_key",
        ),
    )
    op.create_index(
        "ix_collection_tasks_task_type",
        "collection_tasks",
        ["task_type"],
        unique=False,
    )
    op.create_index(
        "ix_collection_tasks_claimable",
        "collection_tasks",
        ["task_type", "status", "available_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_collection_tasks_plant_created",
        "collection_tasks",
        ["plant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_collection_tasks_plant_created", table_name="collection_tasks")
    op.drop_index("ix_collection_tasks_claimable", table_name="collection_tasks")
    op.drop_index("ix_collection_tasks_task_type", table_name="collection_tasks")
    op.drop_table("collection_tasks")
    sa.Enum(name="collectiontaskstatus").drop(op.get_bind(), checkfirst=True)
