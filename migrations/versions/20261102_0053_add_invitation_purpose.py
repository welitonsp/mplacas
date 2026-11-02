"""Add user_invitations.purpose (convite ou redefinição de acesso).

Revision ID: 20261102_0053
Revises: 20261031_0052

ADR-095: o mesmo link de uso único serve para entrar pela primeira vez
(``INVITE``, cria o usuário) e para redefinir o acesso de quem já entrou
(``RESET``, troca a senha). As linhas existentes ficam como ``INVITE`` pelo
valor padrão do servidor; nenhuma linha muda de significado.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261102_0053"
down_revision = "20261031_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_invitations",
        sa.Column("purpose", sa.String(length=16), nullable=False, server_default="INVITE"),
    )


def downgrade() -> None:
    op.drop_column("user_invitations", "purpose")
