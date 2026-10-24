import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import {
  deviceDailyStatusPayload,
  jsonResponse,
  photovoltaicSummaryPayload,
  singlePlant,
} from '../../test/dashboardFixtures'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL` no carregamento do
// módulo — não há `.env.local` no ambiente de teste (ver `LoginPage.test.tsx`,
// `DashboardPage.test.tsx`).
vi.mock('../../env', () => ({
  API_URL: 'https://api.example.test',
}))

// `TechnicalPage` (e, transitivamente, `PlantProvider`/`AuthProvider` usados
// por `renderModule`) só depende de 4 exports de `../../lib/api`: os dois
// recursos do módulo (`fetchPhotovoltaicSummary`, e — desde ADR-074, Decisão
// 5 — `fetchDeviceDailyStatus`), `fetchPlants` (`PlantContext`) e
// `configureApi` (`AuthContext`, chamado incondicionalmente a cada render).
// Nenhum outro fetcher de `../../lib/api` é importado por este módulo — se
// algum teste abaixo os disparasse, o mock (que não os declara) já provaria
// a fronteira de fetch por módulo (ADR-072, Decisão 3).
interface ApiMockOverrides {
  fetchPhotovoltaicSummary?: (plantId: string) => Promise<Response>
  fetchDeviceDailyStatus?: (plantId: string) => Promise<Response>
  fetchPlants?: () => Promise<unknown[]>
}

function installApiMock(overrides: ApiMockOverrides = {}) {
  vi.doMock('../../lib/api', () => ({
    fetchPhotovoltaicSummary:
      overrides.fetchPhotovoltaicSummary ?? vi.fn(async () => jsonResponse(photovoltaicSummaryPayload)),
    fetchDeviceDailyStatus:
      overrides.fetchDeviceDailyStatus ?? vi.fn(async () => jsonResponse(deviceDailyStatusPayload)),
    fetchPlants: overrides.fetchPlants ?? vi.fn(async () => [singlePlant]),
    configureApi: vi.fn(),
  }))
}

async function renderTechnicalPage() {
  const { TechnicalPage } = await import('./TechnicalPage')
  const { renderModule } = await import('../../test/renderModule')
  return renderModule(<TechnicalPage />)
}

describe('TechnicalPage — módulo Técnico (ADR-072, Etapa 2)', () => {
  it('dispara exatamente 2 requisições de dados — /photovoltaic/summary e /devices/daily-status (ADR-074, Decisão 5)', async () => {
    vi.resetModules()
    const fetchPhotovoltaicSummaryMock = vi.fn(async () => jsonResponse(photovoltaicSummaryPayload))
    const fetchDeviceDailyStatusMock = vi.fn(async () => jsonResponse(deviceDailyStatusPayload))
    installApiMock({
      fetchPhotovoltaicSummary: fetchPhotovoltaicSummaryMock,
      fetchDeviceDailyStatus: fetchDeviceDailyStatusMock,
    })

    await renderTechnicalPage()

    // Mesmo achado/correção de `FinancialPage.test.tsx` (ADR-072 Etapa 7): o
    // `<h1>` "Técnico" (e o restante do conteúdo, incluindo "Bruto") só
    // aparece depois que `plantId` resolve, mas não há garantia de que o
    // efeito assíncrono de `usePlantResource` já tenha disparado a
    // requisição no instante em que `findByText` resolve — sem `waitFor` a
    // asserção de contagem corre contra esse efeito.
    await screen.findByText('Bruto')
    await waitFor(() => {
      expect(fetchPhotovoltaicSummaryMock).toHaveBeenCalledTimes(1)
      expect(fetchDeviceDailyStatusMock).toHaveBeenCalledTimes(1)
    })
    expect(fetchPhotovoltaicSummaryMock).toHaveBeenCalledWith(singlePlant.id)
    expect(fetchDeviceDailyStatusMock).toHaveBeenCalledWith(singlePlant.id)
  })

  it('mostra a lista de inversores entre o resumo técnico e o desempenho técnico (ADR-074, Decisão 5)', async () => {
    vi.resetModules()
    installApiMock()

    await renderTechnicalPage()

    const inverterHeading = await screen.findByRole('heading', { level: 2, name: 'Inversores' })
    const region = screen.getByRole('region', { name: 'Inversores' })
    expect(inverterHeading).toBeInTheDocument()

    await waitFor(() => {
      expect(within(region).getByText('SN-1234567890')).toBeInTheDocument()
      expect(within(region).getByText('SN-0987654321')).toBeInTheDocument()
    })
    // O inversor silencioso nunca vira "0" nem some — aparece nomeado.
    expect(within(region).getByText('Não reportou')).toBeInTheDocument()

    // Ordem no DOM: resumo técnico -> inversores -> desempenho técnico. O painel
    // genérico "Diagnóstico de causa" saiu (ADR-083, etapa 3).
    expect(screen.queryByText('Diagnóstico de causa')).not.toBeInTheDocument()
    expect(screen.queryByText(/Agir hoje/)).not.toBeInTheDocument()
    const diagnosticHeading = screen.getByRole('heading', { level: 2, name: 'Resumo técnico' })
    const performanceHeading = screen.getByRole('heading', { level: 2, name: 'Desempenho técnico' })
    expect(
      diagnosticHeading.compareDocumentPosition(inverterHeading) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
    expect(
      inverterHeading.compareDocumentPosition(performanceHeading) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
  })

  it('erro de /devices/daily-status não derruba PR/perdas/degradação renderizados por /photovoltaic/summary', async () => {
    vi.resetModules()
    installApiMock({
      fetchDeviceDailyStatus: vi.fn(async () => jsonResponse({ error: 'boom' }, 500)),
    })

    await renderTechnicalPage()

    await screen.findByText('Bruto')
    const region = screen.getByRole('region', { name: 'Inversores' })
    expect(within(region).getByRole('alert')).toBeInTheDocument()
    // PR/perdas continuam renderizados normalmente apesar do erro isolado.
    expect(screen.getByText('Performance ratio (PR)')).toBeInTheDocument()
  })

  it('resumo técnico: saúde pela performance corrigida pelo calor, maior perda (calor neutro) e produção esperada, sem repetir números de PR', async () => {
    vi.resetModules()
    installApiMock()

    await renderTechnicalPage()

    const title = await screen.findByRole('heading', { level: 2, name: 'Resumo técnico' })
    const section = title.closest('section') as HTMLElement

    // PR corrigido 85% no fixture (bruto 82%): pela corrigida, "Saudável".
    await waitFor(() => {
      expect(within(section).getByText('Saudável')).toBeInTheDocument()
    })
    expect(within(section).getByText('Pela performance já descontado o calor')).toBeInTheDocument()
    expect(within(section).queryByText(/PR bruto|PR corrigido/)).not.toBeInTheDocument()
    expect(within(section).getByText('Principal perda a verificar')).toBeInTheDocument()
    // Sujeira (possível, 1,5%) vem antes do calor (2,3%): pede ação; calor é física.
    expect(within(section).getByText('Sujeira (soiling)')).toBeInTheDocument()
    expect(within(section).getByText('Possível causa · 1,5%')).toBeInTheDocument()
    expect(within(section).queryByText('Principal suspeita')).not.toBeInTheDocument()
    expect(within(section).getByText('Produção esperada')).toBeInTheDocument()
    expect(within(section).getByText('44 kWh/dia')).toBeInTheDocument()
  })

  it('só calor com evidência: aparece como maior perda, com selo neutro e sem alarme', async () => {
    vi.resetModules()
    installApiMock({
      fetchPhotovoltaicSummary: vi.fn(async () =>
        jsonResponse({
          ...photovoltaicSummaryPayload,
          losses: photovoltaicSummaryPayload.losses.map((loss: { category: string }) =>
            loss.category === 'SOILING' ? { ...loss, evidence_level: 'NOT_DETECTED', estimated_loss_percent: '0.00' } : loss,
          ),
        }),
      ),
    })

    await renderTechnicalPage()

    const section = (await screen.findByRole('heading', { level: 2, name: 'Resumo técnico' })).closest('section') as HTMLElement
    await waitFor(() => {
      expect(within(section).getByText('Calor nas placas')).toBeInTheDocument()
    })
    expect(within(section).getByText('Efeito normal do calor · 2,3%')).toBeInTheDocument()
    const tile = within(section).getByText('Calor nas placas').closest('article') as HTMLElement
    expect(tile.className).not.toMatch(/danger/)
  })

  it('comunicação nunca vira "perda a verificar": o motor diz que é capacidade sem dados, não perda de energia', async () => {
    vi.resetModules()
    installApiMock({
      fetchPhotovoltaicSummary: vi.fn(async () =>
        jsonResponse({
          ...photovoltaicSummaryPayload,
          losses: photovoltaicSummaryPayload.losses.map((loss: { category: string }) =>
            loss.category === 'COMMUNICATION'
              ? { ...loss, evidence_level: 'LIKELY', estimated_loss_percent: '9.00' }
              : loss,
          ),
        }),
      ),
    })

    await renderTechnicalPage()

    const section = (await screen.findByRole('heading', { level: 2, name: 'Resumo técnico' })).closest('section') as HTMLElement
    await waitFor(() => {
      expect(within(section).getByText('Sujeira (soiling)')).toBeInTheDocument()
    })
    expect(within(section).queryByText('Comunicação (dados ausentes)')).not.toBeInTheDocument()
  })

  it('renderiza a seção técnica sem nenhum controle de expandir/colapsar (sempre expandida)', async () => {
    vi.resetModules()
    installApiMock()

    await renderTechnicalPage()

    await screen.findByText('Bruto')
    expect(screen.queryByRole('button', { name: /desempenho técnico/i })).not.toBeInTheDocument()

    const region = screen.getByRole('region', { name: 'Desempenho técnico' })
    expect(region).not.toHaveAttribute('hidden')
  })

  it('mostra o esqueleto de carregamento enquanto /photovoltaic/summary está em voo, depois o conteúdo real (sucesso)', async () => {
    vi.resetModules()
    let resolveFetch: (value: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve
    })
    installApiMock({ fetchPhotovoltaicSummary: vi.fn(async () => pending) })

    await renderTechnicalPage()

    // O heading/região da seção já aparecem assim que `plantId` resolve —
    // o esqueleto interno de `TechnicalPerformanceSection` (summary === null)
    // não inclui o texto dos cards reais ainda.
    await screen.findByRole('heading', { level: 2, name: 'Desempenho técnico' })
    expect(screen.queryByText('Performance ratio (PR)')).not.toBeInTheDocument()

    resolveFetch(jsonResponse(photovoltaicSummaryPayload))

    await screen.findByText('Bruto')
    expect(screen.getByText('Performance ratio (PR)')).toBeInTheDocument()
    expect(screen.getAllByText('82%').length).toBeGreaterThan(0)
  })

  it('em erro de /photovoltaic/summary, mostra as mensagens de indisponibilidade por bloco em vez de travar ou de um banner global', async () => {
    vi.resetModules()
    installApiMock({
      fetchPhotovoltaicSummary: vi.fn(async () => jsonResponse({ error: 'boom' }, 500)),
    })

    await renderTechnicalPage()

    await screen.findByRole('heading', { level: 2, name: 'Desempenho técnico' })
    // A mesma mensagem de indisponibilidade aparece em 3 cards (PR, yield
    // específico, disponibilidade de reporte) — todos derivados do mesmo
    // `performance_unavailable_reason` do fallback.
    expect((await screen.findAllByText(/Desempenho técnico ainda não disponível/)).length).toBeGreaterThan(0)

    // Sem banner de erro global (`role="alert"`) — mesma política de
    // `DashboardPage` para este recurso: o erro vira estado de
    // indisponibilidade por bloco, nunca um alerta na tela.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
