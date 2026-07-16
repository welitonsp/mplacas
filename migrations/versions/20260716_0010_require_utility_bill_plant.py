"""Require utility bill plant scope.

Revision ID: 20260716_0010
Revises: 20260716_0009
"""

from alembic import op
import sqlalchemy as sa

revision = "20260716_0010"
down_revision = "20260716_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    legacy_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM utility_bills WHERE plant_id IS NULL")
    ).scalar_one()
    if legacy_count:
        plant_ids = list(bind.execute(sa.text("SELECT id FROM plants LIMIT 2")).scalars())
        if len(plant_ids) != 1:
            raise RuntimeError(
                "utility_bills.plant_id has legacy NULL rows; assign them to a plant "
                "before enforcing NOT NULL"
            )
        bind.execute(
            sa.text("UPDATE utility_bills SET plant_id = :plant_id WHERE plant_id IS NULL"),
            {"plant_id": plant_ids[0]},
        )

    with op.batch_alter_table("utility_bills") as batch_op:
        batch_op.alter_column(
            "plant_id",
            existing_type=sa.Uuid(),
            nullable=False,
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("utility_bills") as batch_op:
        batch_op.alter_column(
            "plant_id",
            existing_type=sa.Uuid(),
            nullable=True,
            existing_nullable=False,
        )
