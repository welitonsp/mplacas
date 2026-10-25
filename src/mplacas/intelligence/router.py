from __future__ import annotations

import logging
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query

from mplacas.core.config import get_settings
from mplacas.core.tenancy import ReadPlant
from mplacas.db.session import SessionFactory
from mplacas.db.tenant_context import set_principal_context
from mplacas.intelligence.anomaly_service import (
    AnomalyDataNotFoundError,
    analyze_recent_persisted_anomalies,
)
from mplacas.intelligence.cycle_service import EnergyCycleNotFoundError, analyze_persisted_cycle
from mplacas.intelligence.dashboard_readmodel import ExecutiveDashboardReadModel
from mplacas.intelligence.expansion import ExpansionAssessment
from mplacas.intelligence.expansion_service import (
    ExpansionPlantNotFoundError,
    get_expansion_assessment,
)
from mplacas.intelligence.financial_return_service import (
    FinancialReturnPlantNotFoundError,
    FinancialReturnResult,
    get_latest_financial_return,
)
from mplacas.intelligence.history_service import (
    EnergyHistoryNotFoundError,
    compare_latest_confirmed_cycles,
)
from mplacas.intelligence.investor_service import (
    InvestorPanel,
    InvestorPlantNotFoundError,
    get_investor_panel,
)
from mplacas.market.bcb import BcbSgsClient
from mplacas.market.service import bcb_host_allowed
from mplacas.photovoltaic.read_service import resolve_expected_daily_production

router = APIRouter(
    prefix="/energy",
    tags=["energy"],
)

logger = logging.getLogger(__name__)

_executive_dashboard_read_model = ExecutiveDashboardReadModel()
_bcb_egress_warning_logged = False


def _optional(value: object) -> str | None:
    return None if value is None else str(value)


def _serialize(result) -> dict[str, object]:
    intelligence = result.intelligence
    reconciliation = intelligence.reconciliation
    return {
        "bill_id": str(result.bill_id),
        "plant_id": str(result.plant_id),
        "reference_month": result.reference_month,
        "quality": {
            "missing_days": result.quality.missing_days,
            "provisional_days": result.quality.provisional_days,
            "incomplete_days": result.quality.incomplete_days,
            "unavailable_days": result.quality.unavailable_days,
        },
        "indicators": {
            "cycle_production_kwh": str(reconciliation.cycle_production_kwh),
            "imported_kwh": str(reconciliation.imported_kwh),
            "injected_kwh": str(reconciliation.injected_kwh),
            "estimated_self_consumption_kwh": str(reconciliation.estimated_self_consumption_kwh),
            "estimated_total_consumption_kwh": str(reconciliation.estimated_total_consumption_kwh),
            "self_consumption_rate_percent": str(reconciliation.self_consumption_rate_percent),
            "self_sufficiency_rate_percent": str(reconciliation.self_sufficiency_rate_percent),
            "grid_dependency_rate_percent": str(intelligence.grid_dependency_rate_percent),
            "exported_generation_rate_percent": str(intelligence.exported_generation_rate_percent),
            "credit_coverage_rate_percent": str(intelligence.credit_coverage_rate_percent),
            "bill_energy_component_brl": str(intelligence.bill_energy_component_brl),
            "health_score": intelligence.health_score,
            "total_amount_brl": str(intelligence.total_amount_brl),
            "public_lighting_brl": str(intelligence.public_lighting_brl),
            "tariff_with_taxes_brl_kwh": (
                str(intelligence.tariff_with_taxes_brl_kwh)
                if intelligence.tariff_with_taxes_brl_kwh is not None
                else None
            ),
            "tariff_without_taxes_brl_kwh": (
                str(intelligence.tariff_without_taxes_brl_kwh)
                if intelligence.tariff_without_taxes_brl_kwh is not None
                else None
            ),
            "savings_tariff_brl_kwh": (
                str(intelligence.savings_tariff_brl_kwh)
                if intelligence.savings_tariff_brl_kwh is not None
                else None
            ),
            "savings_tariff_source": intelligence.savings_tariff_source,
            "credit_balance_kwh": str(intelligence.credit_balance_kwh),
            "estimated_savings_brl": (
                str(intelligence.estimated_savings_brl)
                if intelligence.estimated_savings_brl is not None
                else None
            ),
            "savings_unavailable_reason": intelligence.savings_unavailable_reason,
            # "Conta com e sem a usina" — todos opcionais (null sem tarifa).
            "compensated_kwh": str(intelligence.compensated_kwh),
            "excess_credit_kwh": _optional(reconciliation.excess_credit_kwh),
            "bill_without_solar_brl": _optional(intelligence.bill_without_solar_brl),
            "credit_balance_value_brl": _optional(intelligence.credit_balance_value_brl),
            "modeled_bill_brl": _optional(intelligence.modeled_bill_brl),
            "bill_model_difference_brl": _optional(intelligence.bill_model_difference_brl),
            # ADR-085: bandeira somada à conta sem a usina e créditos que não
            # vêm das placas (fora da economia), como lidos na fatura.
            "flag_tariff_brl_kwh": _optional(intelligence.flag_tariff_brl_kwh),
            "non_energy_credits_brl": _optional(intelligence.non_energy_credits_brl),
            # ADR-087: classe tarifária e se foi presumida (fatura antiga).
            "tariff_class": intelligence.tariff_class,
            "tariff_class_presumed": intelligence.tariff_class_presumed,
        },
        "diagnostics": [
            {
                "code": item.code,
                "severity": item.severity.value,
                "message": item.message,
                "recommended_action": item.recommended_action,
            }
            for item in intelligence.diagnostics
        ],
    }


def _serialize_metric(metric) -> dict[str, object]:
    return {
        "absolute_delta": str(metric.absolute_delta),
        "percent_delta": str(metric.percent_delta) if metric.percent_delta is not None else None,
        "direction": metric.direction.value,
    }


def _serialize_trend(result) -> dict[str, object]:
    comparison = result.comparison
    return {
        "plant_id": str(result.plant_id),
        "current_reference_month": comparison.current_reference_month,
        "previous_reference_month": comparison.previous_reference_month,
        "metrics": {
            "production": _serialize_metric(comparison.production),
            "total_consumption": _serialize_metric(comparison.total_consumption),
            "imported_energy": _serialize_metric(comparison.imported_energy),
            "self_sufficiency_delta_points": str(comparison.self_sufficiency_delta_points),
            "health_score_delta": comparison.health_score_delta,
        },
        "diagnostics": [
            {
                "code": item.code,
                "severity": item.severity,
                "message": item.message,
                "recommended_action": item.recommended_action,
            }
            for item in result.diagnostics
        ],
    }


def _serialize_executive(result) -> dict[str, object]:
    return {
        "plant_id": str(result.plant_id),
        "status": result.status.value,
        "headline": result.headline,
        "priority_actions": list(result.priority_actions),
        "current_cycle": _serialize(result.current_cycle),
        "trend": _serialize_trend(result.trend) if result.trend is not None else None,
    }


def _serialize_anomalies(result) -> dict[str, object]:
    return {
        "plant_id": str(result.plant_id),
        "period": {
            "start_date": result.start_date.isoformat(),
            "end_date": result.end_date.isoformat(),
        },
        "days_analyzed": result.days_analyzed,
        "current_streak_days": result.current_streak_days,
        "worst_level": result.worst_level.value if result.worst_level is not None else None,
        "expected_unavailable_reason": result.expected_unavailable_reason,
        # Rendimento do período (produção ÷ irradiância) e o limiar de
        # severidade que marca um dia como atípico em relação a ele — movidos
        # de `frontend/src/lib/dashboard/yield.ts` para
        # `intelligence/anomaly_service.py::analyze_recent_persisted_anomalies`
        # (2026-08-13, plano T7). `period_yield_kwh_per_kwh_m2` é `None` sob a
        # mesma condição de qualquer `yield_kwh_per_kwh_m2` por dia: nenhum
        # dia do período teve produção E irradiância positivas ao mesmo
        # tempo. `yield_atypical_threshold_percent` é sempre uma string —
        # limiar fixo, não um dado que possa faltar (mesmo padrão de
        # `devices/serialization.py::device_normal_threshold`).
        "period_yield_kwh_per_kwh_m2": (
            str(result.period_yield_kwh_per_kwh_m2)
            if result.period_yield_kwh_per_kwh_m2 is not None
            else None
        ),
        "yield_atypical_threshold_percent": str(result.yield_atypical_threshold_percent),
        # How many of `daily` actually fed `period_yield_kwh_per_kwh_m2`
        # (plan T7b, P1 "o rótulo usa a contagem errada"). Deliberately NOT
        # `days_analyzed`: that counts every day with a persisted production
        # row, while the yield aggregate only counts days with both
        # production and irradiation positive — the frontend must label the
        # yield card with this field, never with `days_analyzed`.
        "period_yield_sample_days": result.period_yield_sample_days,
        "daily": [
            {
                "date": item.observation_date.isoformat(),
                "actual_production_kwh": str(item.actual_production_kwh),
                "expected_production_kwh": (
                    str(item.expected_production_kwh)
                    if item.expected_production_kwh is not None
                    else None
                ),
                "irradiation_kwh_m2": (
                    str(item.irradiation_kwh_m2) if item.irradiation_kwh_m2 is not None else None
                ),
                "level": item.assessment.level.value if item.assessment is not None else None,
                "deviation_kwh": (
                    str(item.assessment.deviation_kwh)
                    if item.assessment is not None and item.assessment.deviation_kwh is not None
                    else None
                ),
                "deviation_percent": (
                    str(item.assessment.deviation_percent)
                    if item.assessment is not None and item.assessment.deviation_percent is not None
                    else None
                ),
                "yield_kwh_per_kwh_m2": (
                    str(item.yield_kwh_per_kwh_m2)
                    if item.yield_kwh_per_kwh_m2 is not None
                    else None
                ),
                "yield_deviation_from_median_percent": (
                    str(item.yield_deviation_from_median_percent)
                    if item.yield_deviation_from_median_percent is not None
                    else None
                ),
                # Collected (`climate/open_meteo.py`) and persisted
                # (`climate/db_models.py::DailyClimateObservationRecord.
                # temperature_mean_c`) since before this endpoint existed, but
                # never serialized here (plan T7b, P2 "dados servidos e
                # descartados"). `None` when there is no climate observation
                # for the day — indisponibilidade explícita, nunca zero
                # fabricado.
                "temperature_mean_c": (
                    str(item.temperature_mean_c) if item.temperature_mean_c is not None else None
                ),
                "diagnostics": (
                    [
                        {
                            "code": diagnostic.code,
                            "level": diagnostic.level.value,
                            "message": diagnostic.message,
                            "recommended_action": diagnostic.recommended_action,
                        }
                        for diagnostic in item.assessment.diagnostics
                    ]
                    if item.assessment is not None
                    else []
                ),
            }
            for item in result.daily
        ],
    }


@router.get("/cycles/{bill_id}")
async def energy_cycle_summary(
    bill_id: uuid.UUID,
    scoped: ReadPlant,
    expected_production_kwh: Decimal | None = Query(default=None, ge=0),
) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        try:
            result = await analyze_persisted_cycle(
                session,
                bill_id=bill_id,
                plant_id=scoped.plant_id,
                expected_production_kwh=expected_production_kwh,
                plant_scope=scoped.principal.plant_scope,
            )
        except EnergyCycleNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize(result)


@router.get("/trends/latest")
async def latest_energy_trend(
    scoped: ReadPlant,
    stable_tolerance_percent: Decimal = Query(default=Decimal("2.0"), ge=0, le=100),
) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        try:
            result = await compare_latest_confirmed_cycles(
                session,
                plant_id=scoped.plant_id,
                stable_tolerance_percent=stable_tolerance_percent,
                plant_scope=scoped.principal.plant_scope,
            )
        except (EnergyHistoryNotFoundError, EnergyCycleNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_trend(result)


@router.get("/executive/latest")
async def latest_executive_dashboard(
    scoped: ReadPlant,
    expected_production_kwh: Decimal | None = Query(default=None, ge=0),
    stable_tolerance_percent: Decimal = Query(default=Decimal("2.0"), ge=0, le=100),
) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        try:
            result = await _executive_dashboard_read_model.get(
                session,
                plant_id=scoped.plant_id,
                expected_production_kwh=expected_production_kwh,
                stable_tolerance_percent=stable_tolerance_percent,
                plant_scope=scoped.principal.plant_scope,
            )
        except EnergyCycleNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_executive(result)


def _serialize_financial_return(result: FinancialReturnResult) -> dict[str, object]:
    return {
        "plant_id": str(result.plant_id),
        "investment_amount_brl": (
            str(result.investment_amount_brl) if result.investment_amount_brl is not None else None
        ),
        "investment_recorded_on": (
            result.investment_recorded_on.isoformat()
            if result.investment_recorded_on is not None
            else None
        ),
        "commissioned_on": (
            result.commissioned_on.isoformat() if result.commissioned_on is not None else None
        ),
        "accumulated_savings_brl": (
            str(result.accumulated_savings_brl)
            if result.accumulated_savings_brl is not None
            else None
        ),
        "average_monthly_savings_brl": (
            str(result.average_monthly_savings_brl)
            if result.average_monthly_savings_brl is not None
            else None
        ),
        "cycles_counted": result.cycles_counted,
        "cycles_expected": result.cycles_expected,
        "roi_percent": (str(result.roi_percent) if result.roi_percent is not None else None),
        "payback_projection_months": result.payback_projection_months,
        "unavailable_reason": (
            result.unavailable_reason.value if result.unavailable_reason is not None else None
        ),
        "payback_unavailable_reason": (
            result.payback_unavailable_reason.value
            if result.payback_unavailable_reason is not None
            else None
        ),
    }


@router.get("/financial-return/latest")
async def latest_financial_return(scoped: ReadPlant) -> dict[str, object]:
    """ROI/payback projection from immutable snapshots (ADR-067).

    Strictly read-only: it never materializes a snapshot (see ADR-067,
    Decisão item 6). ``ReadPlant`` resolves ``plant_id`` from a query
    parameter and validates it against the caller's organization scope,
    the same dependency already used by ``/energy/executive/latest`` and
    ``/energy/trends/latest``.
    """
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        try:
            result = await get_latest_financial_return(
                session,
                plant_id=scoped.plant_id,
                plant_scope=scoped.principal.plant_scope,
            )
        except FinancialReturnPlantNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_financial_return(result)


def _dec(value: object) -> str | None:
    return None if value is None else str(value)


def _serialize_investor(panel: InvestorPanel) -> dict[str, object]:
    realized = panel.realized
    projection = panel.projection
    premises = panel.premises
    return {
        "plant_id": str(panel.plant_id),
        "unavailable_reason": panel.unavailable_reason.value if panel.unavailable_reason else None,
        "investment_brl": _dec(panel.investment_brl),
        "commissioned_month": panel.commissioned_month,
        "months_since_commissioning": panel.months_since_commissioning,
        "cycles_counted": panel.cycles_counted,
        "calculation_versions": list(panel.calculation_versions),
        "includes_pre_correction_cycles": panel.includes_pre_correction_cycles,
        "low_confidence_baseline": panel.low_confidence_baseline,
        "indices": {
            "cdi_12m_per_year": _dec(panel.cdi_12m_per_year),
            "ipca_12m_per_year": _dec(panel.ipca_12m_per_year),
            "as_of_month": panel.indices_as_of_month,
            "source": "Banco Central do Brasil — SGS 4391 (CDI) e 433 (IPCA)",
        },
        "realized": None
        if realized is None
        else {
            "as_of_month": realized.as_of_month,
            "months_elapsed": realized.months_elapsed,
            "accumulated_savings_brl": str(realized.accumulated_savings_brl),
            "cycles_counted": realized.cycles_counted,
            "cdi_path_net_brl": str(realized.cdi_path_net_brl),
            "solar_path_net_brl": str(realized.solar_path_net_brl),
            "cdi_accumulated_percent": str(realized.cdi_accumulated_percent),
        },
        "projection": None
        if projection is None
        else {
            "baseline_monthly_savings_brl": str(projection.baseline_monthly_savings_brl),
            "irr_per_year": _dec(projection.irr_per_year),
            "irr_real_per_year": _dec(projection.irr_real_per_year),
            "cdi_net_per_year": str(projection.cdi_net_per_year),
            "npv_at_cdi_net_brl": str(projection.npv_at_cdi_net_brl),
            "payback_simple_months": projection.payback_simple_months,
            "payback_discounted_months": projection.payback_discounted_months,
            "lifetime_savings_brl": str(projection.lifetime_savings_brl),
            "wire_b_applied": projection.wire_b_applied,
            "patrimony": [
                {
                    "year": point.year,
                    "cdi_path_brl": str(point.cdi_path_brl),
                    "solar_path_brl": str(point.solar_path_brl),
                }
                for point in projection.patrimony
            ],
        },
        "premises": None
        if premises is None
        else {
            "cdi_per_year": str(premises.cdi_per_year),
            "ipca_per_year": str(premises.ipca_per_year),
            "tariff_growth_per_year": str(premises.tariff_growth_per_year),
            "horizon_years": premises.horizon_years,
            "degradation_per_year": str(premises.degradation_per_year),
            "om_per_year_fraction": str(premises.om_per_year_fraction),
            "inverter_replacement_year": premises.inverter_replacement_year,
            "inverter_replacement_fraction": str(premises.inverter_replacement_fraction),
            "long_term_income_tax": str(premises.long_term_income_tax),
        },
    }


@router.get("/investor/latest")
async def latest_investor_panel(scoped: ReadPlant) -> dict[str, object]:
    """Painel do investidor (ADR-079): realizado × CDI e projeção de vida útil.

    Leitura; a única escrita é o reabastecimento das taxas públicas de
    CDI/IPCA (``market_index_monthly``), por isso o ``commit`` no fim.
    """
    global _bcb_egress_warning_logged
    settings = get_settings()
    allowed = bcb_host_allowed(
        settings.market_indices_base_url, settings.external_http_allowed_host_set
    )
    client = BcbSgsClient(base_url=settings.market_indices_base_url) if allowed else None
    if not allowed and not _bcb_egress_warning_logged:
        # Sem isto, uma allowlist explícita sem api.bcb.gov.br deixaria o
        # painel "indisponível" para sempre sem rastro no log (ADR-079).
        _bcb_egress_warning_logged = True
        logger.warning(
            "market_indices_egress_blocked",
            extra={"base_url": settings.market_indices_base_url},
        )
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        try:
            panel = await get_investor_panel(
                session,
                plant_id=scoped.plant_id,
                today=date.today(),
                bcb_client=client,
                plant_scope=scoped.principal.plant_scope,
            )
        except InvestorPlantNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await session.commit()
    return _serialize_investor(panel)


def _serialize_expansion(
    assessment: ExpansionAssessment, context: tuple[str, ...]
) -> dict[str, object]:
    money = assessment.money
    return {
        "status": assessment.status,
        "reasons": list(assessment.reasons),
        "warnings": list(assessment.warnings) + list(context),
        "first_month": assessment.first_month,
        "last_month": assessment.last_month,
        "cycles_used": assessment.cycles_used,
        "imported_kwh_total": _optional(assessment.imported_kwh_total),
        "exported_kwh_total": _optional(assessment.exported_kwh_total),
        "deficit_kwh_year": _optional(assessment.deficit_kwh_year),
        "deficit_kwh_month": _optional(assessment.deficit_kwh_month),
        "direction": assessment.direction,
        "tolerance_kwh_year": _optional(assessment.tolerance_kwh_year),
        "balance_before_kwh": _optional(assessment.balance_before_kwh),
        "balance_after_kwh": _optional(assessment.balance_after_kwh),
        "installed_kwp": _optional(assessment.installed_kwp),
        "measured_cycles": assessment.measured_cycles,
        "yield_kwh_per_kwp_year": _optional(assessment.yield_kwh_per_kwp_year),
        "extra_kwp": _optional(assessment.extra_kwp),
        "inverter_status": assessment.inverter_status,
        "dc_ac_ratio_after": _optional(assessment.dc_ac_ratio_after),
        "problem_months": list(assessment.problem_months),
        "money": None
        if money is None
        else {
            "unavailable_reason": money.unavailable_reason,
            "request_year": money.request_year,
            "monthly_saving_first_year_brl": _optional(money.monthly_saving_first_year_brl),
            "monthly_saving_scenario_brl": _optional(money.monthly_saving_scenario_brl),
            "values_by_year": [
                {
                    "year": value.year,
                    "wire_b_share": str(value.wire_b_share),
                    "value_brl_kwh": str(value.value_brl_kwh),
                    "scenario": value.scenario,
                }
                for value in money.values_by_year
            ],
        },
    }


@router.get("/expansion/latest")
async def latest_expansion_assessment(scoped: ReadPlant) -> dict[str, object]:
    """Vale a pena ampliar a usina? (ADR-089). Somente leitura."""
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        try:
            assessment, context = await get_expansion_assessment(
                session,
                plant_id=scoped.plant_id,
                today=date.today(),
                plant_scope=scoped.principal.plant_scope,
            )
        except ExpansionPlantNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_expansion(assessment, context)


@router.get("/anomalies/latest")
async def latest_energy_anomalies(
    scoped: ReadPlant,
    expected_daily_production_kwh: Decimal | None = Query(default=None, gt=0, deprecated=True),
    days: int = Query(default=7, ge=1, le=90),
) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        resolution = await resolve_expected_daily_production(session, plant_id=scoped.plant_id)
        try:
            result = await analyze_recent_persisted_anomalies(
                session,
                plant_id=scoped.plant_id,
                expected_daily_production_kwh=(
                    resolution.expected.expected_daily_production_kwh
                    if resolution.expected is not None
                    else None
                ),
                days=days,
                expected_unavailable_reason=resolution.unavailable_reason,
            )
        except AnomalyDataNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_anomalies(result)
