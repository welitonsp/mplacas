"""Add pipeline execution ledger.

Revision ID: 20260713_0007
Revises: 20260713_0006
"""

from alembic import op
import sqlalchemy as sa

revision = "20260713_0007"
down_revision = "20260713_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execution_status = sa.Enum(
        "RUNNING", "SUCCEEDED", "FAILED", name="pipelineexecutionstatus"
    )
    execution_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "pipeline_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("status", execution_status, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plant_id", "target_date", name="uq_pipeline_execution_plant_date"
        ),
    )
    op.create_index("ix_pipeline_executions_plant_id", "pipeline_executions", ["plant_id"])
    op.create_index("ix_pipeline_executions_target_date", "pipeline_executions", ["target_date"])
    op.create_index("ix_pipeline_executions_status", "pipeline_executions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_executions_status", table_name="pipeline_executions")
    op.drop_index("ix_pipeline_executions_target_date", table_name="pipeline_executions")
    op.drop_index("ix_pipeline_executions_plant_id", table_name="pipeline_executions")
    op.drop_table("pipeline_executions")
    sa.Enum(name="pipelineexecutionstatus").drop(op.get_bind(), checkfirst=True)
