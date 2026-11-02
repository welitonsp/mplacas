"""Add meter_readings (total acumulado lido na marca, uma vez por noite).

Revision ID: 20261102_0054
Revises: 20261102_0053

ADR-098: há contas Growatt cujo token só lê a lista de usinas (o histórico
diário volta 10011 "error_permission_denied"). A lista traz o total gerado
desde a instalação; lido toda madrugada, a diferença entre duas noites
seguidas é a produção do dia anterior. RLS forçado com a mesma política de
escopo por usina de ``provider_accounts``.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261102_0054"
down_revision = "20261102_0053"
branch_labels = None
depends_on = None

TABLE = "meter_readings"
POLICY_NAME = "mplacas_rls_isolation"
POLICY_EXPRESSION = (
    "((EXISTS ("
    "SELECT 1 FROM public.plants AS rls_plant "
    "WHERE rls_plant.id = meter_readings.plant_id "
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
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reading_date", sa.Date(), nullable=False),
        sa.Column("total_kwh", sa.Numeric(14, 3), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("device_id", "reading_date", name="uq_meter_readings_device_date"),
        sa.CheckConstraint("total_kwh >= 0", name="ck_meter_readings_total_non_negative"),
    )
    op.create_index("ix_meter_readings_plant_id", TABLE, ["plant_id"])

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
    op.drop_index("ix_meter_readings_plant_id", table_name=TABLE)
    op.drop_table(TABLE)
