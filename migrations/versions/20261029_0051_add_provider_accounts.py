"""Add provider_accounts (credencial do inversor por usina).

Revision ID: 20261029_0051
Revises: 20261028_0050

ADR-091, fase 3: uma conexão por usina com a conta do fabricante do inversor.
Login e senha ficam cifrados (AES-256-GCM, chave fora do banco); conexão
desligada perde o texto cifrado. Primeira tabela de inquilino criada depois da
ativação do RLS (20260802_0040): no PostgreSQL, esta migration liga RLS
forçado com a mesma política de escopo por usina das tabelas ``PLANT_TABLES``.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261029_0051"
down_revision = "20261028_0050"
branch_labels = None
depends_on = None

TABLE = "provider_accounts"
POLICY_NAME = "mplacas_rls_isolation"
POLICY_EXPRESSION = (
    "((EXISTS ("
    "SELECT 1 FROM public.plants AS rls_plant "
    "WHERE rls_plant.id = provider_accounts.plant_id "
    "AND rls_plant.organization_id = public.mplacas_current_organization_id()"
    ")) OR public.mplacas_platform_bypass_allowed())"
)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "plant_id",
            sa.Uuid(),
            sa.ForeignKey("plants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("login_hint", sa.String(120), nullable=False),
        sa.Column("account_fingerprint", sa.String(64), nullable=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("key_version", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_code", sa.String(80), nullable=True),
        sa.UniqueConstraint("plant_id", name="uq_provider_accounts_plant"),
        sa.UniqueConstraint(
            "provider",
            "account_fingerprint",
            name="uq_provider_accounts_provider_fingerprint",
        ),
        sa.CheckConstraint(
            "key_version IS NULL OR key_version >= 1",
            name="ck_provider_accounts_key_version",
        ),
        sa.CheckConstraint(
            "(active AND ciphertext IS NOT NULL AND key_version IS NOT NULL "
            "AND account_fingerprint IS NOT NULL) "
            "OR (NOT active AND ciphertext IS NULL AND key_version IS NULL "
            "AND account_fingerprint IS NULL)",
            name="ck_provider_accounts_secret_only_when_active",
        ),
    )
    # Sem índice extra em plant_id: uq_provider_accounts_plant já indexa.

    if op.get_bind().dialect.name == "postgresql":
        op.execute(f'ALTER TABLE public."{TABLE}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public."{TABLE}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{POLICY_NAME}" ON public."{TABLE}" '
            f"FOR ALL USING ({POLICY_EXPRESSION}) WITH CHECK ({POLICY_EXPRESSION})"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON public."{TABLE}"')
    op.drop_table(TABLE)
