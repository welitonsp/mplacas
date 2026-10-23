"""Add revision to monthly_report_snapshots (reprocessamento de meses sem economia).

Revision ID: 20261023_0046
Revises: 20261022_0045

ADR-081: uma fatura confirmada pode ganhar uma nova revisão do relatório
mensal quando o relatório original não tem a economia (relatório anterior ao
cálculo de economia, ou economia indisponível na época). A revisão antiga
nunca é alterada nem apagada; leitores usam a maior revisão por fatura.

Todas as linhas existentes viram revisão 1 pelo `server_default` — não há
ambiguidade de backfill, então a coluna nasce `NOT NULL` numa migration só.
A unicidade passa de `bill_id` para `(bill_id, revision)`.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261023_0046"
down_revision = "20261022_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("monthly_report_snapshots") as batch:
        batch.add_column(
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
        )
        batch.drop_constraint("uq_monthly_report_snapshots_bill", type_="unique")
        batch.create_unique_constraint(
            "uq_monthly_report_snapshots_bill_revision", ["bill_id", "revision"]
        )


def downgrade() -> None:
    # Relatório mensal é imutável (ADR-038): o downgrade NUNCA apaga revisões.
    # Se já houve reprocessamento, ele falha e pede decisão humana.
    revisions = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM monthly_report_snapshots WHERE revision > 1")
    ).scalar_one()
    if revisions:
        raise RuntimeError(
            f"{revisions} revisão(ões) de relatório mensal existem; o downgrade "
            "apagaria dado financeiro auditado (ADR-038/ADR-081). Decida e "
            "remova manualmente antes de voltar a migration."
        )
    with op.batch_alter_table("monthly_report_snapshots") as batch:
        batch.drop_constraint("uq_monthly_report_snapshots_bill_revision", type_="unique")
        batch.create_unique_constraint("uq_monthly_report_snapshots_bill", ["bill_id"])
        batch.drop_column("revision")
