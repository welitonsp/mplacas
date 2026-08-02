"""Enforce non-null authentication timestamps.

Revision ID: 20260802_0037
Revises: 20260802_0036
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_0037"
down_revision = "20260802_0036"
branch_labels = None
depends_on = None


def _assert_no_nulls(table: str, column: str) -> None:
    null_count = (
        op.get_bind()
        .execute(sa.text(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NULL'))
        .scalar_one()
    )
    if null_count:
        raise RuntimeError(
            f"{table}.{column} contains {null_count} null value(s); "
            "correct them before enforcing the non-null constraint"
        )


def upgrade() -> None:
    _assert_no_nulls("auth_sessions", "created_at")
    _assert_no_nulls("login_rate_limits", "first_attempt_at")

    with op.batch_alter_table("auth_sessions") as batch:
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
    with op.batch_alter_table("login_rate_limits") as batch:
        batch.alter_column(
            "first_attempt_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("login_rate_limits") as batch:
        batch.alter_column(
            "first_attempt_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
    with op.batch_alter_table("auth_sessions") as batch:
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
