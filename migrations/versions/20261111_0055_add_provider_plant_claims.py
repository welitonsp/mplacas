"""Add provider_plant_claims (reserva da usina física do fabricante).

Revision ID: 20261111_0055
Revises: 20261102_0054

Tabela só de criação: nada no código atual lê ou grava nela, então a migration
pode rodar em produção antes do deploy. O UNIQUE (provider_family,
serial_number) vale para todas as linhas, inclusive as que o RLS esconde do
inquilino que insere, e fecha a corrida entre duas conexões simultâneas.
RLS forçado com a mesma política de escopo por usina de ``meter_readings``.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261111_0055"
down_revision = "20261102_0054"
branch_labels = None
depends_on = None

TABLE = "provider_plant_claims"
POLICY_NAME = "mplacas_rls_isolation"
POLICY_EXPRESSION = (
    "((EXISTS ("
    "SELECT 1 FROM public.plants AS rls_plant "
    "WHERE rls_plant.id = provider_plant_claims.plant_id "
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
        sa.Column("provider_family", sa.String(40), nullable=False),
        sa.Column("serial_number", sa.String(120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "provider_family",
            "serial_number",
            name="uq_provider_plant_claims_family_serial",
        ),
    )
    op.create_index("ix_provider_plant_claims_plant_id", TABLE, ["plant_id"])

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
    op.drop_index("ix_provider_plant_claims_plant_id", table_name=TABLE)
    op.drop_table(TABLE)
