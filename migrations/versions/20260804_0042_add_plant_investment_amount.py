"""Add plant investment amount and recorded date.

Revision ID: 20260804_0042
Revises: 20260803_0041

Adds two nullable columns to ``plants`` for the ROI/payback feature
(ADR-067): ``investment_amount_brl`` (the CAPEX the client reports having
invested in the plant) and ``investment_recorded_on`` (the date the client
registered that value, informative only — the calculation reference date
remains ``commissioned_on``). Both columns are nullable from the start:
there is no historical value to backfill, so the three-migration
nullable/backfill/NOT NULL pattern does not apply here. ``plants`` is
already under RLS (see ``20260802_0040_enable_postgresql_rls.py``,
``ORGANIZATION_TABLES["plants"] = "organization_id"``); PostgreSQL
row-level-security policies are evaluated per row, not per column, so the
new columns automatically inherit the existing isolation without any new
policy.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260804_0042"
down_revision = "20260803_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("plants") as batch:
        batch.add_column(
            sa.Column("investment_amount_brl", sa.Numeric(12, 2), nullable=True)
        )
        batch.add_column(
            sa.Column("investment_recorded_on", sa.Date(), nullable=True)
        )
        batch.create_check_constraint(
            "ck_plants_investment_amount_positive",
            "investment_amount_brl IS NULL OR investment_amount_brl > 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("plants") as batch:
        batch.drop_constraint("ck_plants_investment_amount_positive", type_="check")
        batch.drop_column("investment_recorded_on")
        batch.drop_column("investment_amount_brl")
