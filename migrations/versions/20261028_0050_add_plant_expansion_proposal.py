"""Add expansion proposal fields to plants.

Revision ID: 20261028_0050
Revises: 20261024_0049

ADR-089, etapa 2: valor total da proposta de ampliação (placas, inversor,
instalação, homologação) informado pelo dono, para o card "Vale a pena
ampliar?" calcular o retorno. Colunas nullable, sem backfill; quem informou
fica na trilha de auditoria (`plant.expansion_proposal_updated`).
"""

from alembic import op
import sqlalchemy as sa

revision = "20261028_0050"
down_revision = "20261024_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("plants") as batch:
        batch.add_column(
            sa.Column("expansion_proposal_brl", sa.Numeric(12, 2), nullable=True)
        )
        batch.add_column(
            sa.Column("expansion_proposal_includes_inverter", sa.Boolean(), nullable=True)
        )
        batch.add_column(sa.Column("expansion_proposal_recorded_on", sa.Date(), nullable=True))
        batch.create_check_constraint(
            "ck_plants_expansion_proposal_positive",
            "expansion_proposal_brl IS NULL OR expansion_proposal_brl > 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("plants") as batch:
        batch.drop_constraint("ck_plants_expansion_proposal_positive", type_="check")
        batch.drop_column("expansion_proposal_recorded_on")
        batch.drop_column("expansion_proposal_includes_inverter")
        batch.drop_column("expansion_proposal_brl")
