import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { jsonResponse, photovoltaicSummaryPayload, singlePlant } from '../../test/dashboardFixtures'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL` no carregamento do
// módulo — não há `.env.local` no ambiente de teste (ver `LoginPage.test.tsx`,
// `DashboardPage.test.tsx`).
vi.mock('../../env', () => ({
  API_URL: 'https://api.example.test',
}))

// `TechnicalPage` (e, transitivamente, `PlantProvider`/`AuthProvider` usados
// por `renderModule`) só depende de 3 exports de `../../lib/api`: o recurso
// do módulo (`fetchPhotovoltaicSummary`), `fetchPlants` (`PlantContext`) e
// `configureApi` (`AuthContext`, chamado incondicionalmente a cada render).
// Nenhum dos outros 4 fetchers de `../../lib/api` é importado por este
// módulo — se algum teste abaixo os disparasse, o mock (que não os declara)
// já provaria a fronteira de fetch por módulo (ADR-072, Decisão 3).
interface ApiMockOverrides {
  fetchPhotovoltaicSummary?: (plantId: string) => Promise<Response>
  fetchPlants?: () => Promise<unknown[]>
}

function installApiMock(overrides: ApiMockOverrides = {}) {
  vi.doMock('../../lib/api', () => ({
    fetchPhotovoltaicSummary:
      overrides.fetchPhotovoltaicSummary ?? vi.fn(async () => jsonResponse(photovoltaicSummaryPayload)),
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
  it('dispara exatamente 1 requisição de dados — só /photovoltaic/summary', async () => {
    vi.resetModules()
    const fetchPhotovoltaicSummaryMock = vi.fn(async () => jsonResponse(photovoltaicSummaryPayload))
    installApiMock({ fetchPhotovoltaicSummary: fetchPhotovoltaicSummaryMock })

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
    })
    expect(fetchPhotovoltaicSummaryMock).toHaveBeenCalledWith(singlePlant.id)
  })

  it('destaca o resumo técnico com saúde, disponibilidade, suspeita principal e produção esperada', async () => {
    vi.resetModules()
    installApiMock()

    await renderTechnicalPage()

    const title = await screen.findByRole('heading', { level: 2, name: 'Resumo técnico' })
    const section = title.closest('section') as HTMLElement

    await waitFor(() => {
      expect(within(section).getByText('Saúde técnica')).toBeInTheDocument()
      expect(within(section).getByText('Atenção')).toBeInTheDocument()
    })
    expect(within(section).getByText('PR bruto 82%')).toBeInTheDocument()
    expect(within(section).getByText('Disponibilidade dos dados')).toBeInTheDocument()
    expect(within(section).getByText('98%')).toBeInTheDocument()
    expect(within(section).getByText('Principal suspeita')).toBeInTheDocument()
    expect(within(section).getByText('Temperatura')).toBeInTheDocument()
    expect(within(section).getByText('Evidência de causa · 2,3%')).toBeInTheDocument()
    expect(within(section).getByText('Produção esperada')).toBeInTheDocument()
    expect(within(section).getByText('44 kWh/dia')).toBeInTheDocument()
    expect(within(section).getByText('PR corrigido 85%')).toBeInTheDocument()
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
