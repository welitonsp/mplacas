import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import {
  anomalyPayload,
  executivePayload,
  financialReturnUnavailablePayload,
  jsonResponse,
  plantSetupCompletePayload,
  singlePlant,
} from '../../test/dashboardFixtures'

// `AuthContext` importa `env.ts`, que valida `VITE_API_URL` no carregamento do
// módulo — não há `.env.local` no ambiente de teste.
vi.mock('../../env', () => ({
  API_URL: 'https://api.example.test',
}))

// Aba Início (ADR-083): quatro recursos de leitura — executivo, produção
// diária, retorno do investimento e cadastro da usina — mais `fetchPlants`
// (`PlantContext`) e `configureApi` (`AuthContext`). Nenhum outro fetcher é
// declarado: se a aba disparasse outro, o teste quebraria (fronteira de fetch
// por módulo, ADR-072, Decisão 3).
interface ApiMockOverrides {
  executivePayload?: unknown
  setupPayload?: unknown
  financialReturnPayload?: unknown
  fetchExecutiveDashboard?: (plantId: string) => Promise<Response>
  fetchAnomalyHistory?: (plantId: string, days?: number) => Promise<Response>
  fetchFinancialReturn?: (plantId: string) => Promise<Response>
  fetchPlantSetup?: (plantId: string) => Promise<Response>
}

function installApiMock(overrides: ApiMockOverrides = {}) {
  vi.doMock('../../lib/api', () => ({
    fetchExecutiveDashboard:
      overrides.fetchExecutiveDashboard ??
      vi.fn(async () => jsonResponse(overrides.executivePayload ?? executivePayload)),
    fetchAnomalyHistory: overrides.fetchAnomalyHistory ?? vi.fn(async () => jsonResponse(anomalyPayload)),
    fetchFinancialReturn:
      overrides.fetchFinancialReturn ??
      vi.fn(async () => jsonResponse(overrides.financialReturnPayload ?? financialReturnUnavailablePayload)),
    fetchPlantSetup:
      overrides.fetchPlantSetup ?? vi.fn(async () => jsonResponse(overrides.setupPayload ?? plantSetupCompletePayload)),
    fetchPlants: vi.fn(async () => [singlePlant]),
    configureApi: vi.fn(),
  }))
}

async function renderHome(overrides: ApiMockOverrides = {}) {
  vi.resetModules()
  installApiMock(overrides)
  const { OverviewPage } = await import('./OverviewPage')
  const { renderModule } = await import('../../test/renderModule')
  const { DASHBOARD_OVERVIEW_PATH } = await import('../../routes')
  return renderModule(<OverviewPage />, DASHBOARD_OVERVIEW_PATH)
}

// O fixture de produção termina em 30/07/2026. Fixar "hoje" no dia seguinte
// mantém a situação estável (a regra de telemetria parada depende da data).
function freezeToday(iso = '2026-07-31T10:00:00') {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(iso))
}

afterEach(() => {
  vi.useRealTimers()
})

const cycleWithBill = {
  ...executivePayload,
  current_cycle: {
    ...executivePayload.current_cycle,
    reference_month: '2026-09',
    indicators: {
      ...executivePayload.current_cycle.indicators,
      estimated_savings_brl: '612.16',
      total_amount_brl: '70.22',
      bill_without_solar_brl: '682.38',
    },
  },
}

const returnReached = {
  ...financialReturnUnavailablePayload,
  investment_amount_brl: '11200.00',
  accumulated_savings_brl: '15435.79',
  average_monthly_savings_brl: '617.43',
  cycles_counted: 25,
  cycles_expected: 26,
  roi_percent: '137.8',
  payback_projection_months: 25,
  unavailable_reason: null,
  payback_unavailable_reason: null,
}

describe('OverviewPage — aba Início (ADR-083)', () => {
  it('dispara exatamente 4 requisições de dados, uma de cada recurso, com a usina ativa', async () => {
    freezeToday()
    const mocks = {
      fetchExecutiveDashboard: vi.fn(async () => jsonResponse(executivePayload)),
      fetchAnomalyHistory: vi.fn(async () => jsonResponse(anomalyPayload)),
      fetchFinancialReturn: vi.fn(async () => jsonResponse(financialReturnUnavailablePayload)),
      fetchPlantSetup: vi.fn(async () => jsonResponse(plantSetupCompletePayload)),
    }
    await renderHome(mocks)

    await screen.findByRole('heading', { level: 2, name: 'Precisa de você' })
    await waitFor(() => {
      for (const mock of Object.values(mocks)) expect(mock).toHaveBeenCalledTimes(1)
    })
    for (const mock of Object.values(mocks)) expect(mock).toHaveBeenCalledWith(singlePlant.id)
  })

  it('título "Início" e a ordem de leitura: situação → dinheiro → 7 dias → precisa de você', async () => {
    freezeToday()
    await renderHome({ executivePayload: cycleWithBill })

    expect(await screen.findByRole('heading', { level: 1, name: 'Início' })).toBeInTheDocument()
    const status = await screen.findByTestId('home-status')
    const savings = await screen.findByRole('region', { name: 'Você economizou em set/26' })
    const week = await screen.findByRole('region', { name: 'Gerou de 24/07 a 30/07' })
    const todo = screen.getByRole('region', { name: 'Precisa de você' })

    const order = [status, savings, week, todo]
    for (let index = 1; index < order.length; index += 1) {
      expect(order[index - 1].compareDocumentPosition(order[index]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
  })

  it('situação: leitura de ontem → frase única, sem "Atenção", "Diretriz" ou plano de ação', async () => {
    freezeToday()
    await renderHome()

    const status = await screen.findByTestId('home-status')
    expect(status).toHaveAttribute('data-tone', 'neutral')
    expect(within(status).getByRole('heading', { level: 2, name: 'Sua usina está gerando' })).toBeInTheDocument()
    expect(within(status).getByText('Último dia: 40 kWh · dado de 30/07')).toBeInTheDocument()

    for (const removed of ['Indicador chave', 'Diretriz', 'Plano de ação', 'Responsável sugerido', 'Próximo check']) {
      expect(screen.queryByText(removed)).not.toBeInTheDocument()
    }
  })

  it('situação: sem leitura há dias → avisa falta de comunicação', async () => {
    freezeToday('2026-08-05T10:00:00')
    await renderHome()

    const status = await screen.findByTestId('home-status')
    expect(status).toHaveAttribute('data-tone', 'warning')
    expect(within(status).getByText('Sem leitura da usina desde 30/07')).toBeInTheDocument()
  })

  it('dinheiro: economia do ciclo, conta com e sem a usina, retorno e link para a aba Dinheiro', async () => {
    freezeToday()
    await renderHome({ executivePayload: cycleWithBill, financialReturnPayload: returnReached })

    const savings = await screen.findByRole('region', { name: 'Você economizou em set/26' })
    expect(within(savings).getByText('R$ 612,16')).toBeInTheDocument()
    expect(within(savings).getByText('Estimado', { exact: true })).toBeInTheDocument()
    expect(within(savings).getByText('R$ 682,38')).toBeInTheDocument()
    expect(within(savings).getByText('R$ 70,22')).toBeInTheDocument()
    expect(await within(savings).findByText('Investimento já recuperado')).toBeInTheDocument()
    expect(within(savings).getByRole('img', { name: '137,8% do investimento já voltou em economia' })).toBeInTheDocument()
    expect(within(savings).getByText('R$ 15.435,79 economizados de R$ 11.200,00 investidos')).toBeInTheDocument()
    expect(within(savings).getByRole('link', { name: /Ver meu dinheiro/ })).toHaveAttribute('href', '/dashboard/dinheiro')
  })

  it('dinheiro: sem investimento cadastrado, explica em vez de mostrar barra vazia', async () => {
    freezeToday()
    await renderHome()

    const savings = await screen.findByRole('region', { name: /Você economizou em/ })
    expect(await within(savings).findByText(/cadastre o valor investido/)).toBeInTheDocument()
    expect(within(savings).queryByRole('img')).not.toBeInTheDocument()
  })

  it('7 dias de calendário: dias sem leitura aparecem como lacuna e o total diz quantos dias somou', async () => {
    freezeToday()
    await renderHome()

    // O fixture só tem 29/07 e 30/07: o backend omite os dias sem leitura.
    const week = await screen.findByRole('region', { name: 'Gerou de 24/07 a 30/07' })
    expect(within(week).getByText('78')).toBeInTheDocument()
    expect(within(week).getByText('kWh · média 39 por dia')).toBeInTheDocument()
    expect(within(week).getByText('Soma de 2 dias: 5 dias ficaram sem leitura.')).toBeInTheDocument()
    expect(within(week).getAllByTestId('home-week-bar')).toHaveLength(2)
    expect(within(week).getAllByTestId('home-week-gap')).toHaveLength(5)
    expect(
      within(week).getByRole('img', {
        name: 'Produção diária: 24/07: sem dado; 25/07: sem dado; 26/07: sem dado; 27/07: sem dado; 28/07: sem dado; 29/07: 38 kWh; 30/07: 40 kWh',
      }),
    ).toBeInTheDocument()
    expect(within(week).getByRole('link', { name: /Ver minha energia/ })).toHaveAttribute('href', '/dashboard/energia')
  })

  it('precisa de você: nada pendente diz isso, e explica o dia sem leitura sem pedir ação', async () => {
    freezeToday()
    await renderHome({
      executivePayload: {
        ...cycleWithBill,
        current_cycle: {
          ...cycleWithBill.current_cycle,
          quality: { missing_days: 1, provisional_days: 0, incomplete_days: 0, unavailable_days: 0 },
          diagnostics: [
            {
              code: 'MISSING_PRODUCTION_DAYS',
              severity: 'WARNING',
              message: 'O ciclo possui 1 dia(s) sem produção consolidada.',
              recommended_action: 'Executar backfill e validar a comunicação dos microinversores.',
            },
          ],
        },
      },
    })

    const todo = await screen.findByRole('region', { name: 'Precisa de você' })
    expect(await within(todo).findByText('Nada pendente.')).toBeInTheDocument()
    expect(
      within(todo).getByText(
        '1 dia do ciclo set/26 ficou sem leitura do inversor, então a produção e a economia desse ciclo podem estar um pouco abaixo do real. Não é algo que você precise resolver.',
      ),
    ).toBeInTheDocument()
    expect(within(todo).queryByText(/backfill/)).not.toBeInTheDocument()
    // A economia desse ciclo é parcial, e o selo diz isso.
    const savings = screen.getByRole('region', { name: 'Você economizou em set/26' })
    expect(within(savings).getByText('Estimado · ciclo parcial')).toBeInTheDocument()
  })

  it('precisa de você: lacuna CRÍTICA de telemetria (3+ dias) não vira tarefa de "backfill"', async () => {
    freezeToday()
    await renderHome({
      executivePayload: {
        ...executivePayload,
        current_cycle: {
          ...executivePayload.current_cycle,
          quality: { missing_days: 3, provisional_days: 0, incomplete_days: 0, unavailable_days: 0 },
          diagnostics: [
            {
              code: 'MISSING_DAILY_DATA',
              severity: 'CRITICAL',
              message: 'O ciclo possui 3 dia(s) sem produção consolidada.',
              recommended_action: 'Executar backfill e validar a comunicação dos microinversores.',
            },
          ],
        },
      },
    })

    const todo = await screen.findByRole('region', { name: 'Precisa de você' })
    expect(await within(todo).findByText('Nada pendente.')).toBeInTheDocument()
    expect(within(todo).queryByText(/backfill/)).not.toBeInTheDocument()
    expect(within(todo).getByText(/3 dias do ciclo jul\/26 ficaram sem leitura do inversor/)).toBeInTheDocument()
  })

  it('precisa de você: cadastro incompleto, faturas pendentes e diagnóstico crítico viram ações', async () => {
    freezeToday()
    await renderHome({
      setupPayload: { ...plantSetupCompletePayload, completed: 5, pending_bills: 2 },
      executivePayload: {
        ...executivePayload,
        current_cycle: {
          ...executivePayload.current_cycle,
          diagnostics: [
            {
              code: 'INVERTER_OFFLINE',
              severity: 'CRITICAL',
              message: 'Um inversor parou de produzir.',
              recommended_action: 'Verifique o disjuntor do inversor.',
            },
          ],
        },
      },
    })

    const todo = await screen.findByRole('region', { name: 'Precisa de você' })
    expect(await within(todo).findByRole('link', { name: /Completar o cadastro da usina/ })).toHaveAttribute(
      'href',
      '/dashboard/minha-usina',
    )
    expect(within(todo).getByRole('link', { name: /Conferir 2 faturas importadas/ })).toHaveAttribute('href', '/dashboard/dinheiro')
    expect(within(todo).queryByText('Nada pendente.')).not.toBeInTheDocument()

    // Diagnóstico crítico abre a lista completa, recolhida no próprio Início.
    const details = document.querySelector('details') as HTMLDetailsElement
    expect(details.open).toBe(false)
    fireEvent.click(within(todo).getByRole('button', { name: /Um inversor parou de produzir/ }))
    expect(details.open).toBe(true)
    expect(within(details).getByText('Um inversor parou de produzir.')).toBeInTheDocument()
  })

  it('falha ao ler o cadastro: diz que não conseguiu conferir, nunca "Nada pendente."', async () => {
    freezeToday()
    await renderHome({ fetchPlantSetup: vi.fn(async () => jsonResponse({ detail: 'erro' }, 500)) })

    const todo = await screen.findByRole('region', { name: 'Precisa de você' })
    expect(
      await within(todo).findByText(
        'Não foi possível conferir o cadastro e as faturas pendentes agora. Use Atualizar para tentar de novo.',
      ),
    ).toBeInTheDocument()
    expect(within(todo).queryByText('Nada pendente.')).not.toBeInTheDocument()
    expect(screen.getByTestId('home-status')).toBeInTheDocument()
  })

  it('histórico diário 404 (nada em 90 dias): a situação avisa, não some', async () => {
    freezeToday()
    await renderHome({ fetchAnomalyHistory: vi.fn(async () => jsonResponse({ detail: 'not found' }, 404)) })

    const status = await screen.findByTestId('home-status')
    expect(status).toHaveAttribute('data-tone', 'warning')
    expect(within(status).getByText('Nenhuma leitura da usina nos últimos 90 dias')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /^Gerou de/ })).not.toBeInTheDocument()
  })

  it('histórico diário com erro de servidor: diz que não conseguiu ler', async () => {
    freezeToday()
    await renderHome({ fetchAnomalyHistory: vi.fn(async () => jsonResponse({ detail: 'erro' }, 500)) })

    const status = await screen.findByTestId('home-status')
    expect(within(status).getByText('Não foi possível ler a produção da usina agora')).toBeInTheDocument()
  })

  it('diagnósticos e evolução ficam recolhidos no fim, com a lista completa', async () => {
    freezeToday()
    const { container } = await renderHome()

    const details = await waitFor(() => {
      const element = container.querySelector('details')
      expect(element).not.toBeNull()
      return element as HTMLDetailsElement
    })
    expect(details.open).toBe(false)
    expect(within(details).getByText('Diagnósticos e evolução do ciclo jul/26')).toBeInTheDocument()
    expect(details.querySelector('#diagnosticos')).not.toBeNull()
  })

  it('erro do executivo: "Tentar novamente" refaz os 4 recursos', async () => {
    freezeToday()
    const fetchExecutiveDashboard = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: 'erro' }, 500))
      .mockResolvedValue(jsonResponse(executivePayload))
    const fetchAnomalyHistory = vi.fn(async () => jsonResponse(anomalyPayload))
    const fetchFinancialReturn = vi.fn(async () => jsonResponse(financialReturnUnavailablePayload))
    const fetchPlantSetup = vi.fn(async () => jsonResponse(plantSetupCompletePayload))
    await renderHome({ fetchExecutiveDashboard, fetchAnomalyHistory, fetchFinancialReturn, fetchPlantSetup })

    fireEvent.click(await screen.findByRole('button', { name: 'Tentar novamente' }))

    await screen.findByRole('region', { name: /Você economizou em/ })
    expect(fetchExecutiveDashboard).toHaveBeenCalledTimes(2)
    expect(fetchAnomalyHistory).toHaveBeenCalledTimes(2)
    expect(fetchFinancialReturn).toHaveBeenCalledTimes(2)
    expect(fetchPlantSetup).toHaveBeenCalledTimes(2)
  })
})
