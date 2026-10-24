"""Add generation_share_percent and credits_expiring_30d_kwh to utility_bills.

Revision ID: 20261024_0047
Revises: 20261023_0046

ADR-084: a conferência da distribuidora só afirma prejuízo quando a fatura
confirma que 100% da geração é desta UC ("CADASTRO RATEIO GERAÇÃO") e separa
crédito vencido ("SALDO A EXPIRAR EM 30 DIAS KWH") de crédito sumido.

As duas colunas são informativas e nascem nullable, sem backfill: faturas já
gravadas ficam `NULL` (a conferência trata como "não confirmado") até o PDF
completar os campos vazios (`billing/completion.py`). Nenhum valor presumido.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261024_0047"
down_revision = "20261023_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("utility_bills") as batch:
        batch.add_column(sa.Column("generation_share_percent", sa.Numeric(5, 2), nullable=True))
        batch.add_column(sa.Column("credits_expiring_30d_kwh", sa.Numeric(12, 3), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("utility_bills") as batch:
        batch.drop_column("credits_expiring_30d_kwh")
        batch.drop_column("generation_share_percent")
