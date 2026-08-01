"""Add tariff fields to utility_bills.

Revision ID: 20260801_0028
Revises: 20260731_0027
Create Date: 2026-08-01

Adds three nullable tariff columns to ``utility_bills``: the R$/kWh unit
price with taxes, the R$/kWh unit price without taxes, and the Fio B
(distribution wire) R$/kWh rate. These values are printed on the SCEE
Equatorial Goiás bill itself (ADR-050 layout) and vary month to month, so
they are modelled as attributes of the bill, not of the plant (see
ADR-055). No backfill: legacy rows remain NULL, honest about data the
parser did not extract at the time.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260801_0028"
down_revision = "20260731_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("utility_bills") as batch:
        batch.add_column(
            sa.Column("tariff_with_taxes_brl_kwh", sa.Numeric(12, 6), nullable=True)
        )
        batch.add_column(
            sa.Column("tariff_without_taxes_brl_kwh", sa.Numeric(12, 6), nullable=True)
        )
        batch.add_column(
            sa.Column("wire_b_tariff_brl_kwh", sa.Numeric(12, 6), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("utility_bills") as batch:
        batch.drop_column("wire_b_tariff_brl_kwh")
        batch.drop_column("tariff_without_taxes_brl_kwh")
        batch.drop_column("tariff_with_taxes_brl_kwh")
