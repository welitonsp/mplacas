import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { SavingsGapsPanel } from './SavingsGapsPanel'
import * as api from '../lib/api'

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const gaps = {
  count: 3,
  items: [
    { bill_id: 'b5', reference_month: '2026-05', cause: 'REPORT_PREDATES_SAVINGS', savings_unavailable_reason: null, previous_savings_brl: null },
    { bill_id: 'b8', reference_month: '2026-08', cause: 'SAVINGS_UNAVAILABLE', savings_unavailable_reason: 'NO_PRODUCTION_DATA', previous_savings_brl: null },
    { bill_id: 'b9', reference_month: '2026-09', cause: 'OUTDATED_CALCULATION', savings_unavailable_reason: null, previous_savings_brl: '408.29' },
  ],
}

describe('SavingsGapsPanel', () => {
  afterEach(() => vi.restoreAllMocks())

  it('não aparece quando não há meses a recalcular', async () => {
    const fetchGaps = vi.spyOn(api, 'fetchSavingsGaps').mockResolvedValue(json({ count: 0, items: [] }))
    const { container } = render(<SavingsGapsPanel plantId="p1" onReprocessed={() => {}} />)
    await waitFor(() => expect(fetchGaps).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('explica cada mês e mostra o antes e o depois do recálculo', async () => {
    vi.spyOn(api, 'fetchSavingsGaps')
      .mockResolvedValueOnce(json(gaps))
      .mockResolvedValue(json({ count: 1, items: [gaps.items[1]] }))
    const reprocess = vi.spyOn(api, 'reprocessSavingsGaps').mockResolvedValue(
      json({
        count: 3,
        recalculated: 2,
        items: [
          { bill_id: 'b5', reference_month: '2026-05', previous_cause: 'REPORT_PREDATES_SAVINGS', previous_savings_brl: null, outcome: 'RECALCULATED', estimated_savings_brl: '590.10', savings_unavailable_reason: null, stored_revision: 2 },
          { bill_id: 'b8', reference_month: '2026-08', previous_cause: 'SAVINGS_UNAVAILABLE', previous_savings_brl: null, outcome: 'STILL_UNAVAILABLE', estimated_savings_brl: null, savings_unavailable_reason: 'NO_PRODUCTION_DATA', stored_revision: null },
          { bill_id: 'b9', reference_month: '2026-09', previous_cause: 'OUTDATED_CALCULATION', previous_savings_brl: '408.29', outcome: 'RECALCULATED', estimated_savings_brl: '612.16', savings_unavailable_reason: null, stored_revision: 2 },
        ],
      }),
    )
    const onReprocessed = vi.fn()
    render(<SavingsGapsPanel plantId="p1" onReprocessed={onReprocessed} />)

    expect(await screen.findByText('Meses a recalcular')).toBeInTheDocument()
    expect(screen.getByText(/R\$\s?408,29 calculada pela fórmula antiga/)).toBeInTheDocument()
    expect(screen.getByText(/sem produção do inversor registrada no período/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Recalcular 3 meses' }))

    const status = await screen.findByRole('status')
    expect(reprocess).toHaveBeenCalledWith('p1')
    expect(status).toHaveTextContent(/passou de R\$\s?408,29 para R\$\s?612,16/)
    expect(status).toHaveTextContent(/set\/2026/)
    expect(status).toHaveTextContent(/continua indisponível/)
    expect(onReprocessed).toHaveBeenCalled()
  })

  it('avisa quando o perfil não pode recalcular', async () => {
    vi.spyOn(api, 'fetchSavingsGaps').mockResolvedValue(json(gaps))
    vi.spyOn(api, 'reprocessSavingsGaps').mockResolvedValue(json({ detail: 'forbidden' }, 403))
    render(<SavingsGapsPanel plantId="p1" onReprocessed={() => {}} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Recalcular 3 meses' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Seu perfil não tem permissão para recalcular.')
  })

  it('explica o mês com dias sem leitura que agora pode ser estimado', async () => {
    vi.spyOn(api, 'fetchSavingsGaps').mockResolvedValue(
      json({
        count: 1,
        items: [
          { bill_id: 'b25', reference_month: '2025-09', cause: 'PARTIAL_PRODUCTION', savings_unavailable_reason: null, previous_savings_brl: '120.00' },
        ],
      }),
    )
    render(<SavingsGapsPanel plantId="p1" onReprocessed={() => {}} />)

    expect(await screen.findByText(/R\$\s?120,00 com dias sem leitura do inversor/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Recalcular 1 mês' })).toBeInTheDocument()
  })
})
