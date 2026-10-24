"""Add tariff_class to utility_bills.

Revision ID: 20261024_0049
Revises: 20261024_0048

ADR-087: a classe tarifária passa a ser lida da fatura
("Classificação: B B1 RESIDENCIAL - ... CONVENCIONAL") em vez de presumida
como residencial B1 para todo cliente. Coluna nullable, sem backfill: classe
nunca é presumida. Faturas já gravadas ganham o campo quando o PDF completa
os campos vazios (`billing/completion.py`).
"""

from alembic import op
import sqlalchemy as sa

revision = "20261024_0049"
down_revision = "20261024_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("utility_bills") as batch:
        batch.add_column(sa.Column("tariff_class", sa.String(length=60), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("utility_bills") as batch:
        batch.drop_column("tariff_class")
