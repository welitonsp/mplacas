import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { ExecutiveDecisionPanel, buildExecutiveDecision } from './ExecutiveDecisionPanel'
import { anomalyPayload, executivePayload } from '../test/dashboardFixtures'
import type { Diagnostic, ExecutiveDashboardResponse } from '../lib/dashboard/contracts'
import {
  combineDiagnostics,
  latestNonNullProductionDate,
  parseAnomalyDashboard,
  parseExecutiveDashboard,
} from '../lib/dashboard/contracts'

function dashboard(payload: unknown = executivePayload): ExecutiveDashboardResponse {
  return parseExecutiveDashboard(payload)
}

function latestProduction() {
  const anomalies = parseAnomalyDashboard(anomalyPayload)
  const latestDate = latestNonNullProductionDate(anomalies.daily)
  return {
    latestDataDate: latestDate,
    latestProduction: latestDate
      ? anomalies.daily.find((point) => point.date === latestDate)?.actual_production_kwh ?? null
      : null,
  }
}

describe('ExecutiveDecisionPanel', () => {
  it('promove o diagnóstico crítico mais grave para prioridade executiva', () => {
    const critical: Diagnostic = {
      code: 'LOW_SELF_SUFFICIENCY',
      severity: 'CRITICAL',
      message: 'Autossuficiência abaixo do esperado.',
      recommended_action: 'Revisar consumo importado.',
    }
    const parsed = dashboard({
      ...executivePayload,
      current_cycle: {
        ...executivePayload.current_cycle,
        diagnostics: [critical],
      },
    })

    render(
      <ExecutiveDecisionPanel
        dashboard={parsed}
        diagnostics={combineDiagnostics(parsed)}
        {...latestProduction()}
      />,
    )

    expect(screen.getByRole('heading', { level: 2, name: 'Autossuficiência abaixo do esperado.' })).toBeInTheDocument()
    expect(screen.getByText('Prioridade crítica')).toBeInTheDocument()
    expect(screen.getByText('Resolver primeiro')).toBeInTheDocument()
    expect(screen.getByText(/Risco relevante para geração/)).toBeInTheDocument()
    expect(screen.getAllByText('Revisar consumo importado.')).toHaveLength(2)
    expect(screen.getByText('Agir nas próximas 24h')).toBeInTheDocument()
    expect(screen.getByText('Operação + técnico')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Plano executivo de ação' })).toBeInTheDocument()
    expect(screen.getByText('Atacar causa prioritária')).toBeInTheDocument()
  })

  it('mostra operação sob controle quando o ciclo está saudável e sem diagnósticos', () => {
    const parsed = dashboard({
      ...executivePayload,
      status: 'HEALTHY',
      headline: 'Ciclo saudável; geração e economia dentro do esperado.',
      current_cycle: {
        ...executivePayload.current_cycle,
        indicators: {
          ...executivePayload.current_cycle.indicators,
          health_score: 92,
        },
        diagnostics: [],
      },
    })

    const decision = buildExecutiveDecision({
      dashboard: parsed,
      diagnostics: [],
      ...latestProduction(),
    })

    expect(decision.tone).toBe('success')
    expect(decision.title).toBe('Operação sob controle')
    expect(decision.action).toMatch(/Manter monitoramento/)
    expect(decision.cadence).toBe('Manter rotina semanal')
    expect(decision.owner).toBe('Gestão operacional')
    expect(decision.playbook.map((item) => item.title)).toEqual([
      'Usar como referência',
      'Preservar qualidade',
      'Registrar aprendizado',
    ])
  })

  it('expõe os sinais usados na decisão: saúde, produção, último dia e economia', () => {
    const parsed = dashboard()

    render(
      <ExecutiveDecisionPanel
        dashboard={parsed}
        diagnostics={[]}
        {...latestProduction()}
      />,
    )

    const signals = screen.getByRole('group', { name: 'Sinais usados na decisão' })
    expect(within(signals).getByText('Saúde')).toBeInTheDocument()
    expect(within(signals).getByText('70/100')).toBeInTheDocument()
    expect(within(signals).getByText('Produção do ciclo')).toBeInTheDocument()
    expect(within(signals).getByText('500 kWh')).toBeInTheDocument()
    expect(within(signals).getByText('Último dia (30/07/2026)')).toBeInTheDocument()
    expect(within(signals).getByText('40 kWh')).toBeInTheDocument()
    expect(within(signals).getByText('Economia estimada')).toBeInTheDocument()
    expect(within(signals).getByText(/R\$\s*120,40/)).toBeInTheDocument()
  })
})
