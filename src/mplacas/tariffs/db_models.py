from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base


class DistributorTariffRecord(Base):
    """Tarifa homologada pela ANEEL para uma classe de consumo, sem tributos.

    Dado público e global (não pertence a nenhuma organização): fica fora do
    RLS por organização, como ``market_index_monthly``. ``full_brl_kwh`` é a
    tarifa cheia (TUSD + TE) que paga quem não tem geração própria;
    ``scee_brl_kwh`` é a tarifa da energia compensada no SCEE (TE reduzida),
    a que aparece na linha "CONSUMO SCEE" da fatura.
    """

    __tablename__ = "distributor_tariffs"
    __table_args__ = (
        UniqueConstraint("distributor", "tariff_class", "valid_from"),
        CheckConstraint("valid_to >= valid_from", name="ck_distributor_tariffs_period"),
        CheckConstraint("full_brl_kwh > 0", name="ck_distributor_tariffs_full_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    distributor: Mapped[str] = mapped_column(String(40))
    tariff_class: Mapped[str] = mapped_column(String(60))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)
    full_brl_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    scee_brl_kwh: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    source: Mapped[str] = mapped_column(String(200))
