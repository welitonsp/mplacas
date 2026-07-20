from __future__ import annotations

from dataclasses import dataclass

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram, MeterProvider as MeterProviderAPI
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from mplacas import __version__
from mplacas.core.config import Settings

_METER_NAME = "mplacas"

OUTCOME_SUCCESS = "success"
OUTCOME_FAILURE = "failure"

_runtime: MetricsRuntime | None = None
_instrument_provider: MeterProviderAPI | None = None
_duration_histogram: Histogram | None = None
_runs_counter: Counter | None = None


@dataclass(slots=True)
class MetricsRuntime:
    provider: MeterProvider | None = None

    def shutdown(self) -> None:
        if self.provider is not None:
            self.provider.force_flush(timeout_millis=5000)
            self.provider.shutdown()


def configure_metrics(
    *,
    settings: Settings,
    service_name: str,
    reader: MetricReader | None = None,
) -> MetricsRuntime:
    """Configura o MeterProvider global quando as métricas estão habilitadas.

    Quando ``cloud_metrics_enabled`` é falso e nenhum ``reader`` de teste é
    fornecido, o provider global permanece no-op e as gravações são descartadas
    sem custo relevante.
    """
    global _runtime
    if not settings.cloud_metrics_enabled and reader is None:
        return MetricsRuntime()
    if _runtime is not None:
        return _runtime

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": __version__,
            "deployment.environment.name": settings.env,
        }
    )
    if reader is None:
        from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter

        reader = PeriodicExportingMetricReader(
            CloudMonitoringMetricsExporter(project_id=settings.gcp_project_id),
            export_interval_millis=settings.metrics_export_interval_seconds * 1000,
        )
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    if settings.cloud_metrics_enabled:
        metrics.set_meter_provider(provider)
    _runtime = MetricsRuntime(provider=provider)
    return _runtime


def record_operation(*, operation: str, outcome: str, duration_ms: float) -> None:
    """Registra a duração e a contagem de uma operação observada.

    Os atributos ficam restritos a ``operation`` e ``outcome`` para manter a
    cardinalidade das séries temporais limitada e previsível.
    """
    histogram, counter = _instruments()
    attributes = {"operation": operation, "outcome": outcome}
    histogram.record(max(0.0, float(duration_ms)), attributes=attributes)
    counter.add(1, attributes=attributes)


def _instruments() -> tuple[Histogram, Counter]:
    global _instrument_provider, _duration_histogram, _runs_counter
    provider: MeterProviderAPI
    if _runtime is not None and _runtime.provider is not None:
        provider = _runtime.provider
    else:
        provider = metrics.get_meter_provider()
    if (
        provider is not _instrument_provider
        or _duration_histogram is None
        or _runs_counter is None
    ):
        meter = provider.get_meter(_METER_NAME, __version__)
        _duration_histogram = meter.create_histogram(
            "mplacas.operation.duration",
            unit="ms",
            description="Duração de operações observadas do Mplacas",
        )
        _runs_counter = meter.create_counter(
            "mplacas.operation.runs",
            unit="1",
            description="Execuções de operações observadas do Mplacas por resultado",
        )
        _instrument_provider = provider
    return _duration_histogram, _runs_counter


def reset_metrics_state_for_tests() -> None:
    """Descarta o runtime e o cache de instrumentos. Uso exclusivo em testes."""
    global _runtime, _instrument_provider, _duration_histogram, _runs_counter
    if _runtime is not None and _runtime.provider is not None:
        _runtime.provider.shutdown()
    _runtime = None
    _instrument_provider = None
    _duration_histogram = None
    _runs_counter = None
