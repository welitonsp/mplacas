from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mplacas.db.base import Base


class MarketIndexMonthlyRecord(Base):
    """Taxa mensal de um indicador público (ex.: CDI, IPCA), em % ao mês.

    Dado público e global (não pertence a nenhuma organização): fica fora do
    RLS por organização. Uma linha por indicador e mês; a busca no Banco
    Central só acrescenta ou corrige meses, nunca apaga.
    """

    __tablename__ = "market_index_monthly"
    __table_args__ = (UniqueConstraint("index_code", "reference_month"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    index_code: Mapped[str] = mapped_column(String(20))
    reference_month: Mapped[str] = mapped_column(String(7))
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    source: Mapped[str] = mapped_column(String(40))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
