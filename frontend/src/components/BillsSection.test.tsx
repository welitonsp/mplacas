import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { BillsSection } from './BillsSection'
import * as api from '../lib/api'

const pendingBill = {
  id: 'bill-1',
  plant_id: 'plant-1',
  distributor: 'EQUATORIAL_GO',
  reference_month: '2026-09',
  cycle_start: '2026-08-17',
  cycle_end: '2026-09-14',
  billed_days: 29,
  imported_kwh: '221.00',
  injected_kwh: '221.00',
  compensated_kwh: '221.00',
  credit_balance_kwh: '17.98',
  total_amount_brl: '70.22',
  public_lighting_brl: '30.21',
  generation_cycle_kwh: '235.00',
  tariff_with_taxes_brl_kwh: '0.787589',
  tariff_without_taxes_brl_kwh: '0.613030',
  wire_b_tariff_brl_kwh: '0.175126',
  status: 'PENDING_REVIEW',
  created_at: null,
  reviewed_at: null,
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function pdfFile(size = 1024): File {
  const file = new File(['%PDF-1.7'], 'fatura.pdf', { type: 'application/pdf' })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

function chooseFile(container: HTMLElement, file: File) {
  chooseFiles(container, [file])
}

function chooseFiles(container: HTMLElement, files: File[]) {
  const input = container.querySelector('#bill-pdf-input') as HTMLInputElement
  fireEvent.change(input, { target: { files } })
}

describe('BillsSection — importar e conferir faturas', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    // Painel "Meses a recalcular" (ADR-081) fica vazio nestes cenários.
    vi.spyOn(api, 'fetchSavingsGaps').mockResolvedValue(json({ count: 0, items: [] }))
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('mostra a fatura pendente com os valores lidos, e a injeção vem do medidor (não da linha SCEE)', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json({ count: 1, items: [pendingBill] }))

    render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)

    const review = await screen.findByRole('article', { name: 'Fatura de set/2026' })
    const field = (label: string) => within(review).getByText(label).nextElementSibling?.textContent
    expect(field('Total da fatura')).toMatch(/70,22/)
    expect(field('Energia puxada da rede')).toBe('221 kWh')
    expect(field('Energia injetada na rede')).toBe('235 kWh')
    expect(field('Energia compensada')).toBe('221 kWh')
    expect(field('Saldo de créditos')).toBe('17,98 kWh')
    expect(field('Tarifa com impostos')).toBe('R$ 0,787589/kWh')
    // 6 casas fixas, como na fatura impressa (não "0,61303").
    expect(field('Tarifa sem impostos')).toBe('R$ 0,613030/kWh')
    expect(field('Ciclo')).toBe('17/08/2026 a 14/09/2026 · 29 dias')
    expect(within(review).getByText('Aguardando sua conferência')).toBeInTheDocument()
  })

  it('campo opcional ausente aparece como "não informado", nunca como zero', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(
      json({ count: 1, items: [{ ...pendingBill, wire_b_tariff_brl_kwh: null }] }),
    )

    render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)

    const review = await screen.findByRole('article', { name: 'Fatura de set/2026' })
    expect(within(review).getByText('Tarifa do Fio B').nextElementSibling?.textContent).toBe(
      'Não informada na fatura',
    )
  })

  it('sem o registro do medidor, não afirma o que saiu para a rede: mostra a linha da fatura com o nome dela', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(
      json({ count: 1, items: [{ ...pendingBill, generation_cycle_kwh: null }] }),
    )

    render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)

    const review = await screen.findByRole('article', { name: 'Fatura de set/2026' })
    expect(within(review).queryByText('Energia injetada na rede')).not.toBeInTheDocument()
    expect(within(review).getByText('Injeção SCEE (como na fatura)').nextElementSibling?.textContent).toBe(
      '221 kWh',
    )
  })

  it('reenvio de fatura ainda pendente (HTTP 200) avisa que ela já estava lá', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json({ count: 1, items: [pendingBill] }))
    vi.spyOn(api, 'uploadBillPdf').mockResolvedValue(json({ status: 'already_imported', bill: pendingBill }, 200))

    const { container } = render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    await screen.findByRole('article', { name: 'Fatura de set/2026' })
    chooseFile(container, pdfFile())

    expect(await screen.findByRole('status')).toHaveTextContent('já tinha sido importada e aguarda sua conferência')
  })

  it('sem pendentes, diz isso em vez de mostrar uma lista vazia', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json({ count: 0, items: [] }))

    render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)

    expect(await screen.findByText('Nenhuma fatura aguardando conferência.')).toBeInTheDocument()
  })

  it('importa o PDF escolhido, avisa que foi lido e recarrega as pendentes', async () => {
    const fetchSpy = vi
      .spyOn(api, 'fetchPendingBills')
      .mockResolvedValueOnce(json({ count: 0, items: [] }))
      .mockResolvedValueOnce(json({ count: 1, items: [pendingBill] }))
    const uploadSpy = vi
      .spyOn(api, 'uploadBillPdf')
      .mockResolvedValue(json({ status: 'pending_review', bill: pendingBill }, 202))

    const { container } = render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    await screen.findByText('Nenhuma fatura aguardando conferência.')

    const file = pdfFile()
    chooseFile(container, file)

    await waitFor(() => expect(uploadSpy).toHaveBeenCalledWith('plant-1', file))
    expect(
      await screen.findByText('Fatura de set/2026 lida. Confira os valores abaixo e confirme.'),
    ).toBeInTheDocument()
    await screen.findByRole('article', { name: 'Fatura de set/2026' })
    expect(fetchSpy).toHaveBeenCalledTimes(2)
  })

  it('recusa arquivo acima de 10 MB sem enviar nada', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json({ count: 0, items: [] }))
    const uploadSpy = vi.spyOn(api, 'uploadBillPdf')

    const { container } = render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    chooseFile(container, pdfFile(10_000_001))

    expect(await screen.findByRole('alert')).toHaveTextContent('passa de 10 MB')
    expect(uploadSpy).not.toHaveBeenCalled()
  })

  it('mostra a mensagem fixa do servidor quando a fatura não pode ser lida (422)', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json({ count: 0, items: [] }))
    vi.spyOn(api, 'uploadBillPdf').mockResolvedValue(
      json({ detail: 'O PDF foi lido, mas não parece uma fatura da Equatorial Goiás com os campos esperados.' }, 422),
    )

    const { container } = render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    chooseFile(container, pdfFile())

    expect(await screen.findByRole('alert')).toHaveTextContent('não parece uma fatura da Equatorial')
  })

  it('PDF de mês já confirmado completa a tarifa que faltava e relê os meses a recalcular', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json({ count: 0, items: [] }))
    const gapsSpy = vi.spyOn(api, 'fetchSavingsGaps').mockResolvedValue(json({ count: 0, items: [] }))
    vi.spyOn(api, 'uploadBillPdf').mockResolvedValue(
      json({
        status: 'completed_missing_fields',
        filled_fields: ['tariff_with_taxes_brl_kwh'],
        bill: { ...pendingBill, status: 'CONFIRMED' },
      }),
    )
    const onConfirmed = vi.fn()

    const { container } = render(<BillsSection plantId="plant-1" onConfirmed={onConfirmed} />)
    await waitFor(() => expect(gapsSpy).toHaveBeenCalledTimes(1))
    chooseFile(container, pdfFile())

    expect(await screen.findByRole('status')).toHaveTextContent('completamos os dados que faltavam')
    expect(onConfirmed).toHaveBeenCalled()
    await waitFor(() => expect(gapsSpy).toHaveBeenCalledTimes(2))
  })

  it('mês já confirmado com valores diferentes mostra a mensagem do servidor (409)', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json({ count: 0, items: [] }))
    vi.spyOn(api, 'uploadBillPdf').mockResolvedValue(
      json(
        {
          detail:
            'Já existe uma fatura confirmada deste mês com valores diferentes dos lidos neste PDF. Nada foi alterado.',
        },
        409,
      ),
    )

    const { container } = render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    chooseFile(container, pdfFile())

    expect(await screen.findByRole('alert')).toHaveTextContent('Nada foi alterado')
  })

  it('fatura já confirmada enviada de novo vira aviso, não pendência', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json({ count: 0, items: [] }))
    vi.spyOn(api, 'uploadBillPdf').mockResolvedValue(
      json({ status: 'pending_review', bill: { ...pendingBill, status: 'CONFIRMED' } }, 202),
    )

    const { container } = render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    chooseFile(container, pdfFile())

    expect(await screen.findByRole('status')).toHaveTextContent('já tinha sido importada e confirmada')
  })

  it('confirmar chama a API, avisa e pede para a página recarregar os números', async () => {
    vi.spyOn(api, 'fetchPendingBills')
      .mockResolvedValueOnce(json({ count: 1, items: [pendingBill] }))
      .mockResolvedValueOnce(json({ count: 0, items: [] }))
    const confirmSpy = vi
      .spyOn(api, 'confirmBill')
      .mockResolvedValue(json({ status: 'confirmed', bill: { ...pendingBill, status: 'CONFIRMED' } }))
    const onConfirmed = vi.fn()

    render(<BillsSection plantId="plant-1" onConfirmed={onConfirmed} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar fatura' }))

    await waitFor(() => expect(confirmSpy).toHaveBeenCalledWith('bill-1'))
    await waitFor(() => expect(onConfirmed).toHaveBeenCalledTimes(1))
    expect(await screen.findByText(/Fatura de set\/2026 confirmada/)).toBeInTheDocument()
  })

  it('rejeitar pede uma segunda confirmação e pode ser cancelado', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json({ count: 1, items: [pendingBill] }))
    const rejectSpy = vi
      .spyOn(api, 'rejectBill')
      .mockResolvedValue(json({ status: 'rejected', bill: { ...pendingBill, status: 'REJECTED' } }))

    render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Rejeitar' }))
    expect(screen.getByText(/Rejeitar esta fatura\?/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(rejectSpy).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Rejeitar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sim, rejeitar' }))
    await waitFor(() => expect(rejectSpy).toHaveBeenCalledWith('bill-1'))
  })

  it('perfil sem permissão recebe mensagem clara ao confirmar', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json({ count: 1, items: [pendingBill] }))
    vi.spyOn(api, 'confirmBill').mockResolvedValue(json({ detail: 'forbidden' }, 403))

    render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar fatura' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('não tem permissão')
  })

  it('importa várias faturas de uma vez, uma de cada vez, e resume o resultado', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json({ count: 0, items: [] }))
    const upload = vi
      .spyOn(api, 'uploadBillPdf')
      .mockResolvedValueOnce(json({ status: 'pending_review', bill: { ...pendingBill, id: 'b1', reference_month: '2024-09' } }, 202))
      .mockResolvedValueOnce(
        json({ detail: 'O PDF foi lido, mas não parece uma fatura da Equatorial Goiás com os campos esperados.' }, 422),
      )
      .mockResolvedValueOnce(json({ status: 'pending_review', bill: { ...pendingBill, id: 'b3', reference_month: '2024-11' } }, 202))

    const { container } = render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    const input = container.querySelector('#bill-pdf-input') as HTMLInputElement
    expect(input.multiple).toBe(true)
    chooseFiles(container, [pdfFile(), pdfFile(), pdfFile()])

    const summary = await screen.findByText(/3 arquivos lidos: 2 para conferir, 1 com problema/)
    expect(summary).toBeInTheDocument()
    expect(upload).toHaveBeenCalledTimes(3)
    expect(screen.getByText(/Fatura de set\/2024 lida/)).toBeInTheDocument()
    expect(screen.getByText(/não parece uma fatura da Equatorial/)).toBeInTheDocument()
  })

  it('recusa mais de 18 arquivos de uma vez sem enviar nada', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json({ count: 0, items: [] }))
    const upload = vi.spyOn(api, 'uploadBillPdf')

    const { container } = render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    chooseFiles(container, Array.from({ length: 19 }, () => pdfFile()))

    expect(await screen.findByRole('alert')).toHaveTextContent('até 18 faturas')
    expect(upload).not.toHaveBeenCalled()
  })

  it('confirmar todas pede uma segunda confirmação e confirma cada fatura', async () => {
    const two = {
      count: 2,
      items: [
        { ...pendingBill, id: 'b1', reference_month: '2024-09' },
        { ...pendingBill, id: 'b2', reference_month: '2024-10' },
      ],
    }
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValueOnce(json(two)).mockResolvedValue(json({ count: 0, items: [] }))
    const confirm = vi.spyOn(api, 'confirmBill').mockResolvedValue(json({ status: 'confirmed', bill: pendingBill }))
    const onConfirmed = vi.fn()

    render(<BillsSection plantId="plant-1" onConfirmed={onConfirmed} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar todas' }))
    expect(confirm).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Sim, confirmar 2 faturas' }))

    expect(await screen.findByText('2 faturas confirmadas. Economia e retorno do investimento atualizados.')).toBeInTheDocument()
    expect(confirm).toHaveBeenCalledWith('b1')
    expect(confirm).toHaveBeenCalledWith('b2')
    expect(onConfirmed).toHaveBeenCalled()
  })

  const twoPending = {
    count: 2,
    items: [
      { ...pendingBill, id: 'b1', reference_month: '2024-09' },
      { ...pendingBill, id: 'b2', reference_month: '2024-10' },
    ],
  }

  it('confirmar todas para no primeiro 403 e diz que o perfil não tem permissão', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json(twoPending))
    const confirm = vi.spyOn(api, 'confirmBill').mockResolvedValue(json({ detail: 'forbidden' }, 403))

    render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar todas' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sim, confirmar 2 faturas' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Seu perfil não tem permissão para confirmar faturas.')
    expect(confirm).toHaveBeenCalledTimes(1)
  })

  it('confirmar todas separa as já revisadas das que falharam', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json(twoPending))
    vi.spyOn(api, 'confirmBill')
      .mockResolvedValueOnce(json({ detail: 'already' }, 409))
      .mockResolvedValueOnce(json({ detail: 'boom' }, 500))

    render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar todas' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sim, confirmar 2 faturas' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('0 faturas confirmadas.')
    expect(alert).toHaveTextContent('Já tinham sido revisadas: set/2024.')
    expect(alert).toHaveTextContent('Não foi possível confirmar: out/2024.')
  })

  it('cancelar a segunda confirmação não confirma nada e devolve o foco', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json(twoPending))
    const confirm = vi.spyOn(api, 'confirmBill')

    render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar todas' }))
    expect(screen.getByRole('button', { name: 'Sim, confirmar 2 faturas' })).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar todas' })).toHaveFocus())
    expect(confirm).not.toHaveBeenCalled()
  })

  it('durante o confirmar todas, importar e os botões de cada fatura ficam travados', async () => {
    vi.spyOn(api, 'fetchPendingBills').mockResolvedValue(json(twoPending))
    let release: (value: Response) => void = () => {}
    vi.spyOn(api, 'confirmBill').mockImplementation(
      () => new Promise<Response>((resolve) => { release = resolve }),
    )

    render(<BillsSection plantId="plant-1" onConfirmed={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar todas' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sim, confirmar 2 faturas' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Importar faturas (PDF)' })).toBeDisabled())
    for (const button of screen.getAllByRole('button', { name: 'Confirmar fatura' })) expect(button).toBeDisabled()
    release(json({ status: 'confirmed', bill: pendingBill }))
  })
})
