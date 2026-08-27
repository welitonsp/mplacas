// Captura das telas reais do painel, com a API interceptada.
//
// Por que interceptar em vez de subir o backend: as telas precisam de dados
// para existir, mas o objetivo aqui é ver o LAYOUT, não validar o servidor. Com
// payload fixo, a mesma tela sai igual em qualquer máquina e qualquer dia — se
// a captura mudar, foi o frontend que mudou.
//
// As fixtures são as mesmas de `src/test/dashboardFixtures.ts`, já usadas pelos
// testes de componente. Manter uma fonte só evita a captura mostrar um estado
// que nenhum teste cobre.
import { expect, test } from '@playwright/test'

import {
  anomalyPayload,
  deviceDailyStatusPayload,
  executivePayload,
  financialReturnUnavailablePayload,
  monthlyHistoryPayload,
  photovoltaicSummaryPayload,
  singlePlant,
} from '../src/test/dashboardFixtures'

// Rótulo do menu, não segmento de URL: a navegação é feita CLICANDO, nunca com
// `page.goto`. A sessão vive só em memória (ADR-073), então recarga completa a
// descarta e o app volta para o login — a primeira versão desta captura fazia
// `goto` e gravou quatro vezes a tela de "Sua sessão foi encerrada", com os
// testes passando. Captura errada com teste verde é pior que teste vermelho.
const MODULOS = [
  { rotulo: 'Visão Geral', nome: 'visao-geral' },
  { rotulo: 'Produção', nome: 'producao' },
  { rotulo: 'Financeiro', nome: 'financeiro' },
  { rotulo: 'Técnico', nome: 'tecnico' },
] as const

/** Responde a cada endpoint que o painel consome, sem tocar em rede real. */
async function interceptarApi(page: import('@playwright/test').Page) {
  const rotas: Array<[string, unknown]> = [
    ['**/auth/login', { access_token: 'captura', refresh_token: 'captura' }],
    // Formato de REDE, não o pós-parse. `singlePlant` das fixtures é o objeto
    // já parseado (camelCase, sem envelope), porque os testes de componente
    // mockam `fetchPlants` no nível de módulo e nunca exercitam o fio. Aqui a
    // resposta passa por `parsePlantsResponse`, que exige envelope `{count,
    // items}` e `installed_power_kwp` em snake_case — servir o formato errado
    // rendia "Resposta inválida da API." nos quatro módulos.
    [
      '**/plants',
      {
        count: 1,
        items: [
          {
            id: singlePlant.id,
            name: singlePlant.name,
            installed_power_kwp: singlePlant.installedPowerKwp,
          },
        ],
      },
    ],
    ['**/energy/executive/latest*', executivePayload],
    ['**/energy/anomalies/latest*', anomalyPayload],
    ['**/photovoltaic/summary*', photovoltaicSummaryPayload],
    ['**/energy/financial-return/latest*', financialReturnUnavailablePayload],
    ['**/devices/daily-status*', deviceDailyStatusPayload],
    ['**/reports/monthly/history*', monthlyHistoryPayload],
  ]

  // O catch-all vem PRIMEIRO de propósito: o Playwright resolve rotas em ordem
  // INVERSA de registro, então a última registrada tem precedência. Registrado
  // por último, este bloco interceptava até `/auth/login` e devolvia 404 — o
  // login falhava e as 4 telas do painel nunca eram alcançadas.
  //
  // Ele existe para que um endpoint novo, não previsto abaixo, apareça como
  // estado de erro na captura em vez de vazar para a rede e morrer em timeout.
  await page.route(
    (url) => url.hostname === 'api.captura.test',
    (rota) => rota.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  )

  for (const [padrao, corpo] of rotas) {
    await page.route(padrao, (rota) =>
      rota.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(corpo),
      })
    )
  }
}

async function autenticar(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByLabel(/usuári|usuario/i).fill('operador')
  await page.getByLabel(/senha/i).fill('senha-de-captura')
  await page.getByRole('button', { name: /entrar/i }).click()
  await page.waitForURL('**/dashboard/**', { timeout: 15_000 })
}

test.describe('captura das telas', () => {
  test.beforeEach(async ({ page }) => {
    // Rolagem instantânea durante a captura. O `reducedMotion: 'reduce'` do
    // config cobre transição CSS, mas não `scroll-behavior`, e no mobile o menu
    // de módulos é um scroller horizontal: com rolagem animada o Playwright
    // encontra o link "sempre em movimento" e a ação de clique expira.
    //
    // É ajuste de determinismo da captura, não mudança de produto — a rolagem
    // suave da landing continua valendo para quem usa o site.
    await page.addInitScript(() => {
      const estilo = document.createElement('style')
      // Rolagem instantânea e zero animação. Duas razões:
      //
      // 1. Determinismo da imagem: sem isto a captura pega um quadro no meio de
      //    transição e a mesma tela sai diferente a cada execução.
      // 2. Estabilidade da ação: o link do menu tem `transition-all
      //    duration-200` com `hover:-translate-y-0.5`. No mobile, o Playwright
      //    encontrava o elemento sempre em movimento e o clique expirava.
      estilo.textContent =
        '*, *::before, *::after {' +
        ' scroll-behavior: auto !important;' +
        ' transition: none !important;' +
        ' animation: none !important;' +
        ' }'
      document.documentElement.appendChild(estilo)
    })
    await interceptarApi(page)
  })

  test('pagina publica', async ({ page }, info) => {
    await page.goto('/')
    // A landing usa Manrope e Space Grotesk; esperar as fontes evita capturar
    // o quadro em que o texto ainda está no fallback (`font-display: swap`).
    await page.evaluate(() => document.fonts.ready)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

    await page.screenshot({
      path: `e2e/capturas/${info.project.name}/publica.png`,
      fullPage: true,
    })
  })

  test('login', async ({ page }, info) => {
    await page.goto('/login')
    await page.evaluate(() => document.fonts.ready)
    await expect(page.getByRole('button', { name: /entrar/i })).toBeVisible()

    await page.screenshot({ path: `e2e/capturas/${info.project.name}/login.png`, fullPage: true })
  })

  test('painel — os 4 modulos', async ({ page }, info) => {
    await autenticar(page)

    for (const modulo of MODULOS) {
      // No mobile o menu de módulos é um scroller horizontal (`lg:overflow-visible`
      // no DashboardNav), e a partir do terceiro item o link nasce fora da
      // viewport. Trazer para a área visível antes de clicar evita depender do
      // auto-scroll no limite do tempo de ação.
      const link = page.getByRole('link', { name: modulo.rotulo })
      await link.scrollIntoViewIfNeeded()
      // `force` pula a checagem de estabilidade do Playwright, e isso é
      // deliberado. No mobile o menu é um scroller horizontal (`overflow-x-auto`
      // no DashboardNav) e o par rolar/reposicionar mantém o link em movimento
      // por tempo suficiente para a ação expirar — sem que haja defeito algum.
      //
      // A checagem de acionabilidade é a ferramenta errada aqui: o objetivo é
      // capturar a tela, não validar interação. O que prova que a navegação de
      // fato aconteceu são as asserções ABAIXO — URL e `aria-current` —, e elas
      // falham de verdade se o clique não surtir efeito.
      await link.click({ force: true })
      await page.evaluate(() => document.fonts.ready)

      // Guarda contra a captura silenciosamente errada: se a sessão cair, o app
      // manda para o login e a imagem sairia da tela errada com o teste verde.
      await expect(page).toHaveURL(new RegExp(`/dashboard/`))
      await expect(page.getByRole('link', { name: modulo.rotulo })).toHaveAttribute(
        'aria-current',
        'page'
      )

      // Esperar o conteúdo, não um tempo fixo: `waitForTimeout` capturaria o
      // esqueleto de carregamento em máquina lenta e a tela pronta em máquina
      // rápida, tornando a captura não comparável entre execuções.
      // Guarda contra captura de tela de erro: sem isto a imagem sairia com o
      // card "Não foi possível carregar os dados" e o teste passaria — foi
      // exatamente o que aconteceu enquanto o mock de `/plants` servia o
      // formato pós-parse em vez do formato de rede.
      await expect(page.getByText(/Não foi possível carregar/)).toHaveCount(0)
      await expect(page.getByRole('main')).toBeVisible()
      await expect(page.getByText(/carregando/i)).toHaveCount(0, { timeout: 15_000 })

      await page.screenshot({
        path: `e2e/capturas/${info.project.name}/painel-${modulo.nome}.png`,
        fullPage: true,
      })
    }
  })
})
