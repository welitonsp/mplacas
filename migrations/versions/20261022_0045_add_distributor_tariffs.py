"""Add distributor_tariffs (tarifas homologadas, referência pública).

Revision ID: 20261022_0045
Revises: 20261019_0044

ADR-080: a conta "sem a usina" usa a tarifa cheia (TUSD + TE) que paga quem
não tem geração própria, não a tarifa SCEE da fatura. Dado público e global,
sem dono: fica fora do RLS por organização, como `market_index_monthly`.

Carga inicial: Equatorial GO, B1 residencial convencional, sem tributos.
Cada valor foi conferido contra o preço impresso nas faturas reais do
período (pró-rata de dias reproduz o preço até a 6ª casa).
"""

from datetime import date
from decimal import Decimal
import uuid

from alembic import op
import sqlalchemy as sa

revision = "20261022_0045"
down_revision = "20261019_0044"
branch_labels = None
depends_on = None

_SEED = (
    # vigência, tarifa cheia, tarifa SCEE, fonte
    (
        date(2023, 10, 22),
        date(2024, 10, 21),
        Decimal("0.710630"),
        None,
        "ANEEL reajuste 2023 Equatorial GO; conferido na fatura set/2024 (energia ativa fornecida)",
    ),
    (
        date(2024, 10, 22),
        date(2025, 10, 21),
        Decimal("0.745930"),
        Decimal("0.498120"),
        "ANEEL REH 3.407/2024; conferido nas faturas dez/2024-set/2025 (consumo não compensado)",
    ),
    (
        date(2025, 10, 22),
        date(2026, 10, 21),
        Decimal("0.891810"),
        Decimal("0.613030"),
        "ANEEL REH 3.544/2025 (base tarifas-distribuidoras); SCEE conferida nas faturas 2026",
    ),
)


def upgrade() -> None:
    table = op.create_table(
        "distributor_tariffs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("distributor", sa.String(length=40), nullable=False),
        sa.Column("tariff_class", sa.String(length=60), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=False),
        sa.Column("full_brl_kwh", sa.Numeric(10, 6), nullable=False),
        sa.Column("scee_brl_kwh", sa.Numeric(10, 6), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("distributor", "tariff_class", "valid_from"),
        sa.CheckConstraint("valid_to >= valid_from", name="ck_distributor_tariffs_period"),
        sa.CheckConstraint("full_brl_kwh > 0", name="ck_distributor_tariffs_full_positive"),
    )
    op.bulk_insert(
        table,
        [
            {
                "id": uuid.uuid5(uuid.NAMESPACE_URL, f"mplacas:tariff:EQUATORIAL_GO:{start}"),
                "distributor": "EQUATORIAL_GO",
                "tariff_class": "B1_RESIDENCIAL_CONVENCIONAL",
                "valid_from": start,
                "valid_to": end,
                "full_brl_kwh": full,
                "scee_brl_kwh": scee,
                "source": source,
            }
            for start, end, full, scee, source in _SEED
        ],
    )


def downgrade() -> None:
    op.drop_table("distributor_tariffs")
