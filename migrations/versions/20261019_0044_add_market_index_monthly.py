"""Add market_index_monthly (CDI/IPCA mensais do Banco Central).

Revision ID: 20261019_0044
Revises: 20260805_0043

ADR-079 (painel do investidor): taxas mensais públicas de CDI (SGS 4391) e
IPCA (SGS 433), em % ao mês, uma linha por indicador e mês. Dado global, sem
`organization_id`: fica fora do RLS por organização (ADR-056) de propósito —
não há dado de cliente aqui. Tabela nova e vazia: nenhum backfill; o serviço
reabastece sob demanda a partir do BCB.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261019_0044"
down_revision = "20260805_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_index_monthly",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("index_code", sa.String(length=20), nullable=False),
        sa.Column("reference_month", sa.String(length=7), nullable=False),
        sa.Column("rate_percent", sa.Numeric(12, 6), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("index_code", "reference_month"),
    )


def downgrade() -> None:
    op.drop_table("market_index_monthly")
