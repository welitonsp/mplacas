"""Scope utility bill source hashes by plant.

Revision ID: 20260801_0031
Revises: 20260801_0030
"""

from alembic import op
import sqlalchemy as sa


revision = "20260801_0031"
down_revision = "20260801_0030"
branch_labels = None
depends_on = None

_NAMING_CONVENTION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _unique_constraint_for(columns: set[str]) -> str:
    constraints = sa.inspect(op.get_bind()).get_unique_constraints("utility_bills")
    for constraint in constraints:
        if set(constraint.get("column_names") or ()) == columns:
            return constraint.get("name") or "uq_utility_bills_source_hash"
    raise RuntimeError(f"utility_bills unique constraint not found for {sorted(columns)}")


def _duplicate_count(grouping: str) -> int:
    result = op.get_bind().execute(
        sa.text(
            f"SELECT COUNT(*) FROM (SELECT 1 FROM utility_bills "
            f"GROUP BY {grouping} HAVING COUNT(*) > 1) AS duplicate_groups"
        )
    )
    return int(result.scalar_one())


def upgrade() -> None:
    if _duplicate_count("plant_id, source_hash"):
        raise RuntimeError("duplicate utility_bills plant_id/source_hash groups must be resolved")
    source_constraint = _unique_constraint_for({"source_hash"})
    with op.batch_alter_table(
        "utility_bills", naming_convention=_NAMING_CONVENTION
    ) as batch:
        batch.drop_constraint(source_constraint, type_="unique")
        batch.create_unique_constraint(
            "uq_utility_bills_plant_source_hash",
            ["plant_id", "source_hash"],
        )


def downgrade() -> None:
    if _duplicate_count("source_hash"):
        raise RuntimeError(
            "cannot restore global source_hash uniqueness while cross-plant duplicates exist"
        )
    with op.batch_alter_table("utility_bills") as batch:
        batch.drop_constraint("uq_utility_bills_plant_source_hash", type_="unique")
        batch.create_unique_constraint(
            "uq_utility_bills_source_hash",
            ["source_hash"],
        )
