from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from mplacas.operations.repository import JobRunRepository

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class JobOutcome:
    records_seen: int = 0
    records_changed: int = 0
    metrics: dict[str, object] | None = None


class ObservableJobRunner:
    """Executa jobs com persistência de início, sucesso, falha e duração."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._runs = JobRunRepository(session)

    async def run(
        self,
        job_name: str,
        operation: Callable[[], Awaitable[tuple[T, JobOutcome]]],
    ) -> T:
        run, started = await self._runs.start(job_name)
        await self._session.commit()
        try:
            result, outcome = await operation()
            await self._runs.succeed(
                run,
                started,
                records_seen=outcome.records_seen,
                records_changed=outcome.records_changed,
                metrics=outcome.metrics,
            )
            await self._session.commit()
            return result
        except Exception as exc:
            await self._session.rollback()
            refreshed_run = await self._session.get(type(run), run.id)
            if refreshed_run is not None:
                await self._runs.fail(
                    refreshed_run,
                    started,
                    error_code=type(exc).__name__,
                    error_message=str(exc) or "Falha sem mensagem",
                )
                await self._session.commit()
            raise
