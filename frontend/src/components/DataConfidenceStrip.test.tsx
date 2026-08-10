import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DataConfidenceStrip, buildDataConfidenceSummary } from './DataConfidenceStrip'
import type { CycleQuality } from '../lib/dashboard/contracts'

const consolidatedQuality: CycleQuality = {
  missing_days: 0,
  provisional_days: 0,
  incomplete_days: 0,
  unavailable_days: 0,
}

describe('DataConfidenceStrip', () => {
  it('mostra alta confiança quando o ciclo não tem pendências de leitura', () => {
    render(
      <DataConfidenceStrip
        quality={consolidatedQuality}
        latestDataDate="2026-07-30"
        referenceMonth="2026-07"
      />,
    )

    const strip = screen.getByRole('complementary', { name: 'Confiança dos dados' })
    expect(within(strip).getByText('Alta confiança')).toBeInTheDocument()
    expect(within(strip).getByRole('heading', { level: 2, name: 'Dados prontos para decisão' })).toBeInTheDocument()
    expect(within(strip).getByText('Última leitura diária: 30/07/2026.')).toBeInTheDocument()
    expect(within(strip).getByText('Use os indicadores do ciclo para decisão executiva.')).toBeInTheDocument()
    expect(within(strip).getByText('Rotina semanal')).toBeInTheDocument()
  })

  it('orienta validar telemetria quando existem dias sem leitura ou indisponíveis', () => {
    const summary = buildDataConfidenceSummary(
      { missing_days: 2, provisional_days: 0, incomplete_days: 1, unavailable_days: 1 },
      '2026-07-28',
    )

    expect(summary.tone).toBe('danger')
    expect(summary.label).toBe('Validar telemetria')
    expect(summary.description).toBe('2 dias sem leitura, 1 dia incompleto, 1 dia indisponível no ciclo.')
    expect(summary.nextCheck).toBe('Checar hoje')
  })

  it('mantém decisão com ressalva quando só há dados provisórios ou incompletos', () => {
    const summary = buildDataConfidenceSummary(
      { missing_days: 0, provisional_days: 3, incomplete_days: 2, unavailable_days: 0 },
      '2026-07-30',
    )

    expect(summary.tone).toBe('warning')
    expect(summary.label).toBe('Leitura parcial')
    expect(summary.headline).toBe('Decisão permitida com ressalva operacional')
    expect(summary.description).toBe('3 dias provisórios, 2 dias incompletos no ciclo.')
    expect(summary.decisionGuidance).toBe('Compare com histórico antes de transformar o sinal em ação corretiva.')
  })
})
