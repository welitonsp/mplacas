"""Add plants.auto_filled (cadastro preenchido pela conexão).

Revision ID: 20261031_0052
Revises: 20261029_0051

ADR-093 § 7: ao conectar a conta do fabricante, o sistema preenche os campos
vazios da usina com o que a marca informa (ou com estimativas marcadas como
tal). A coluna guarda quais campos foram preenchidos assim e a origem, para a
tela distinguir "veio da marca"/"estimado" de "informado pelo dono". Coluna
nova e nula: nenhuma linha existente muda; o RLS de ``plants`` já cobre.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0052"
down_revision = "20261029_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plants", sa.Column("auto_filled", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("plants", "auto_filled")
