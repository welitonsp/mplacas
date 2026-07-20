"""Add report_export_tasks table for async PDF/XLSX export queue.

Revision ID: 20260720_0018
Revises: 20260720_0017
"""

import sqlalchemy as sa
from alembic import op

revision = "20260720_0018"
down_revision = "20260720_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_export_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("reference_month", sa.String(7), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("artifact_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("artifact_content_type", sa.String(100), nullable=True),
        sa.Column("artifact_url", sa.String(2048), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["plant_id"],
            ["plants.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_report_export_tasks_status_created",
        "report_export_tasks",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_report_export_tasks_plant_month",
        "report_export_tasks",
        ["plant_id", "reference_month"],
    )


def downgrade() -> None:
    op.drop_index("ix_report_export_tasks_plant_month", table_name="report_export_tasks")
    op.drop_index("ix_report_export_tasks_status_created", table_name="report_export_tasks")
    op.drop_table("report_export_tasks")
