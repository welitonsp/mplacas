"""Scope utility bills by plant.

Revision ID: 20260713_0005
Revises: 20260713_0004
"""

from alembic import op
import sqlalchemy as sa

revision = "20260713_0005"
down_revision = "20260713_0004"
branch_labels = None
depends_on = None

_BILL_NAMING_CONVENTION = {
    "uq": (
        "uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s_"
        "%(column_2_name)s_%(column_3_name)s"
    )
}


def upgrade() -> None:
    with op.batch_alter_table(
        "utility_bills",
        naming_convention=_BILL_NAMING_CONVENTION,
    ) as batch_op:
        batch_op.add_column(sa.Column("plant_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_utility_bills_plant_id_plants",
            "plants",
            ["plant_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index("ix_utility_bills_plant_id", ["plant_id"], unique=False)
        batch_op.drop_constraint(
            "uq_utility_bills_distributor_reference_month_cycle_start_cycle_end",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_utility_bills_plant_cycle",
            ["plant_id", "distributor", "reference_month", "cycle_start", "cycle_end"],
        )


def downgrade() -> None:
    with op.batch_alter_table("utility_bills") as batch_op:
        batch_op.drop_constraint("uq_utility_bills_plant_cycle", type_="unique")
        batch_op.create_unique_constraint(
            "uq_utility_bills_distributor_reference_month_cycle_start_cycle_end",
            ["distributor", "reference_month", "cycle_start", "cycle_end"],
        )
        batch_op.drop_index("ix_utility_bills_plant_id")
        batch_op.drop_constraint("fk_utility_bills_plant_id_plants", type_="foreignkey")
        batch_op.drop_column("plant_id")
