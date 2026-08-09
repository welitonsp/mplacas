import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { TechnicalDiagnosticPanel, buildTechnicalDiagnosis } from './TechnicalDiagnosticPanel'
import { photovoltaicSummaryPayload } from '../test/dashboardFixtures'
import type { PhotovoltaicSummaryResponse } from '../lib/dashboard/photovoltaic-contracts'
import { parsePhotovoltaicSummary } from '../lib/dashboard/photovoltaic-contracts'

function parseSummary(payload: unknown): PhotovoltaicSummaryResponse {
  return parsePhotovoltaicSummary(payload)
}

describe('TechnicalDiagnosticPanel', () => {
  it('transforma a principal perda provável em causa, impacto e próxima ação', () => {
    const summary = parseSummary(photovoltaicSummaryPayload)

    render(<TechnicalDiagnosticPanel summary={summary} />)

    expect(screen.getByRole('heading', { level: 2, name: 'Diagnóstico: causa provável localizada' })).toBeInTheDocument()
    expect(screen.getByText('Confiança alta')).toBeInTheDocument()
    expect(screen.getByText(/Temperatura é a hipótese técnica dominante/)).toBeInTheDocument()
    expect(screen.getByText(/Impacto estimado de 2,3%/)).toBeInTheDocument()
    expect(screen.getByText(/Transformar esta causa em ordem de verificação/)).toBeInTheDocument()

    const signals = screen.getByText('PR bruto').closest('div')?.parentElement as HTMLElement
    expect(within(signals).getByText('82%')).toBeInTheDocument()
    expect(within(signals).getByText('98%')).toBeInTheDocument()
  })

  it('prioriza telemetria crítica antes de qualquer causa física', () => {
    const summary = parseSummary({
      ...photovoltaicSummaryPayload,
      performance: {
        ...photovoltaicSummaryPayload.performance,
        reporting_availability_ratio: '0.7400',
      },
    })

    const diagnosis = buildTechnicalDiagnosis(summary)

    expect(diagnosis.tone).toBe('danger')
    expect(diagnosis.title).toBe('Diagnóstico: telemetria crítica')
    expect(diagnosis.action).toMatch(/gateway/)
  })

  it('mostra operação saudável quando PR e disponibilidade estão bons e não há perda provável', () => {
    const summary = parseSummary({
      ...photovoltaicSummaryPayload,
      performance: {
        ...photovoltaicSummaryPayload.performance,
        performance_ratio: '0.9100',
        temperature_corrected_performance_ratio: '0.9300',
        reporting_availability_ratio: '0.9900',
      },
      losses: photovoltaicSummaryPayload.losses.map((loss) => ({
        ...loss,
        evidence_level: loss.category === 'DEGRADATION' ? 'NOT_ASSESSABLE' : 'NOT_DETECTED',
        estimated_loss_percent: loss.category === 'DEGRADATION' ? null : '0.00',
      })),
    })

    render(<TechnicalDiagnosticPanel summary={summary} />)

    expect(screen.getByRole('heading', { level: 2, name: 'Diagnóstico: operação saudável' })).toBeInTheDocument()
    expect(screen.getByText(/Não há causa técnica relevante detectada/)).toBeInTheDocument()
    expect(screen.getByText(/Manter acompanhamento/)).toBeInTheDocument()
  })
})
