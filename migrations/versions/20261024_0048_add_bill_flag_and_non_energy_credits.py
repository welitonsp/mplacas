"""Add flag_tariff_brl_kwh and non_energy_credits_brl to utility_bills.

Revision ID: 20261024_0048
Revises: 20261024_0047

ADR-085: a conta "sem a usina" passa a incluir a bandeira tarifária do ciclo
(preço com tributos impresso na fatura) e a economia deixa de contar créditos
que não vêm das placas (compensação por interrupção e Bônus de Itaipu).

Colunas informativas, nullable, sem backfill: faturas já gravadas ficam
`NULL` até o PDF completar os campos vazios (`billing/completion.py`).
"""

from alembic import op
import sqlalchemy as sa

revision = "20261024_0048"
down_revision = "20261024_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("utility_bills") as batch:
        batch.add_column(sa.Column("flag_tariff_brl_kwh", sa.Numeric(12, 6), nullable=True))
        batch.add_column(sa.Column("non_energy_credits_brl", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("utility_bills") as batch:
        batch.drop_column("non_energy_credits_brl")
        batch.drop_column("flag_tariff_brl_kwh")
