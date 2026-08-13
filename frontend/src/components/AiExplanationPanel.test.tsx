import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { AiExplanationPanel } from './AiExplanationPanel'
import * as api from '../lib/api'

const PLANT_ID = '11111111-1111-1111-1111-111111111111'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function explanationPayload(overrides: Record<string, unknown> = {}) {
  return {
    plant_id: PLANT_ID,
    status: 'ATTENTION',
    source: 'DETERMINISTIC',
    summary: 'Produção abaixo do esperado.',
    what_it_means: 'O ciclo está em atenção pela energia importada acima do previsto.',
    next_steps: ['Revisar consumo importado'],
    disclaimer:
      'Explicação informativa baseada apenas nos diagnósticos calculados pelo Mplacas; não confirma causa técnica nem substitui inspeção profissional.',
    evidence_codes: ['IMPORTED_ENERGY_HIGH'],
    ...overrides,
  }
}

describe('AiExplanationPanel', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('não busca nada ao montar — só ao clique explícito do usuário', () => {
    const fetchSpy = vi.spyOn(api, 'fetchLatestExplanation')
    render(<AiExplanationPanel plantId={PLANT_ID} />)

    expect(fetchSpy).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /pedir explicação por ia/i })).toBeInTheDocument()
  })

  it('busca ao clicar, mostra carregamento acessível e depois o resultado rotulado como interpretação assistida por IA', async () => {
    let resolveFetch: (response: Response) => void = () => {}
    vi.spyOn(api, 'fetchLatestExplanation').mockImplementation(
      () => new Promise((resolve) => { resolveFetch = resolve })
    )
    const { container } = render(<AiExplanationPanel plantId={PLANT_ID} />)

    const button = screen.getByRole('button', { name: /pedir explicação por ia/i })
    expect(button).toHaveAttribute('aria-busy', 'false')
    fireEvent.click(button)

    expect(await screen.findByRole('button', { name: /gerando explicação/i })).toHaveAttribute(
      'aria-busy',
      'true'
    )
    const liveRegion = container.querySelector('[aria-live="polite"]') as HTMLElement
    expect(liveRegion).toHaveTextContent('Gerando explicação por IA, aguarde.')

    resolveFetch(jsonResponse(200, explanationPayload({ source: 'AI_ASSISTED' })))

    const region = await screen.findByRole('region', { name: /explicação interpretativa por ia/i })
    expect(region).toHaveTextContent('Interpretação assistida por IA')
    expect(region).toHaveTextContent('Camada interpretativa — não é dado auditável')
    expect(region).toHaveTextContent('Produção abaixo do esperado.')
    expect(region).toHaveTextContent('Revisar consumo importado')
    expect(region).toHaveTextContent('não confirma causa técnica nem substitui inspeção profissional')

    await waitFor(() => expect(liveRegion).toHaveTextContent(''))
    expect(screen.getByRole('button', { name: /pedir nova explicação/i })).not.toBeDisabled()
  })

  it('rotula o resumo determinístico de forma distinta quando não houver origem de IA disponível (provedor não configurado é estado normal)', async () => {
    vi.spyOn(api, 'fetchLatestExplanation').mockResolvedValue(
      jsonResponse(200, explanationPayload({ source: 'DETERMINISTIC' }))
    )
    render(<AiExplanationPanel plantId={PLANT_ID} />)

    fireEvent.click(screen.getByRole('button', { name: /pedir explicação por ia/i }))

    const region = await screen.findByRole('region', { name: /explicação interpretativa por ia/i })
    expect(region).toHaveTextContent('Resumo determinístico do sistema')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('trata 404 (nenhum ciclo confirmado ainda) como estado informativo, não como erro alarmante', async () => {
    vi.spyOn(api, 'fetchLatestExplanation').mockResolvedValue(jsonResponse(404, { detail: 'not found' }))
    render(<AiExplanationPanel plantId={PLANT_ID} />)

    fireEvent.click(screen.getByRole('button', { name: /pedir explicação por ia/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Ainda não há ciclo de faturamento confirmado para explicar'
    )
    expect(screen.getByRole('button', { name: /pedir explicação por ia/i })).not.toBeDisabled()
  })

  it('mostra erro genérico e permite nova tentativa em falha de servidor', async () => {
    vi.spyOn(api, 'fetchLatestExplanation').mockResolvedValue(jsonResponse(500, { detail: 'boom' }))
    render(<AiExplanationPanel plantId={PLANT_ID} />)

    fireEvent.click(screen.getByRole('button', { name: /pedir explicação por ia/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível gerar a explicação agora.')
    expect(screen.getByRole('button', { name: /pedir explicação por ia/i })).not.toBeDisabled()
  })

  it('mostra erro genérico quando a rede falha (rejeição da promessa), sem travar a página', async () => {
    vi.spyOn(api, 'fetchLatestExplanation').mockRejectedValue(new TypeError('network down'))
    render(<AiExplanationPanel plantId={PLANT_ID} />)

    fireEvent.click(screen.getByRole('button', { name: /pedir explicação por ia/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível gerar a explicação agora.')
  })

  it('trata 401 como logout silencioso — sem erro exibido, volta ao repouso', async () => {
    vi.spyOn(api, 'fetchLatestExplanation').mockResolvedValue(jsonResponse(401, { detail: 'unauthorized' }))
    render(<AiExplanationPanel plantId={PLANT_ID} />)

    fireEvent.click(screen.getByRole('button', { name: /pedir explicação por ia/i }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /pedir explicação por ia/i })).not.toBeDisabled()
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /explicação interpretativa por ia/i })).not.toBeInTheDocument()
  })

  it('limpa o erro anterior ao tentar novamente e mostra o resultado da nova tentativa', async () => {
    const fetchSpy = vi
      .spyOn(api, 'fetchLatestExplanation')
      .mockResolvedValueOnce(jsonResponse(500, { detail: 'boom' }))
      .mockResolvedValueOnce(jsonResponse(200, explanationPayload()))
    render(<AiExplanationPanel plantId={PLANT_ID} />)

    fireEvent.click(screen.getByRole('button', { name: /pedir explicação por ia/i }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /pedir explicação por ia/i }))
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(await screen.findByRole('region', { name: /explicação interpretativa por ia/i })).toBeInTheDocument()
  })

  it('o botão de pedir explicação tem alvo de toque mínimo de 44px', () => {
    render(<AiExplanationPanel plantId={PLANT_ID} />)
    expect(screen.getByRole('button', { name: /pedir explicação por ia/i }).className).toMatch(/min-h-\[44px\]/)
  })
})
