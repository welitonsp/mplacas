// Medição de altura por seção, no mobile.
//
// Não é teste de regressão: é instrumento de diagnóstico, rodado sob demanda
// para decidir ONDE cortar. A lição do R-1 (docs/ANALISE_DENSIDADE_TELAS) foi
// que estimar densidade a olho erra a ordem de grandeza — 200 px previstos como
// "alto impacto" contra 12.576 px de página.
//
// Rodar com:  npx playwright test e2e/medir-secoes.spec.ts --project=mobile
import { test } from '@playwright/test'

import {
  anomalyPayload,
  deviceDailyStatusPayload,
  executivePayload,
  financialReturnUnavailablePayload,
  monthlyHistoryPayload,
  photovoltaicSummaryPayload,
  singlePlant,
} from '../src/test/dashboardFixtures'

const MODULOS = ['Visão Geral', 'Produção', 'Financeiro', 'Técnico'] as const

test('medir seções por módulo', async ({ page }) => {
  test.setTimeout(120_000)

  await page.route(
    (url) => url.hostname === 'api.captura.test',
    (rota) => rota.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  )
  const rotas: Array<[string, unknown]> = [
    ['**/auth/login', { access_token: 'x', refresh_token: 'x' }],
    [
      '**/plants',
      {
        count: 1,
        items: [
          { id: singlePlant.id, name: singlePlant.name, installed_power_kwp: null },
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
  for (const [padrao, corpo] of rotas) {
    await page.route(padrao, (r) =>
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(corpo) })
    )
  }

  await page.goto('/login')
  await page.getByLabel(/usuári|usuario/i).fill('operador')
  await page.getByLabel(/senha/i).fill('captura')
  await page.getByRole('button', { name: /entrar/i }).click()
  await page.waitForURL('**/dashboard/**')

  for (const rotulo of MODULOS) {
    const link = page.getByRole('link', { name: rotulo })
    await link.scrollIntoViewIfNeeded()
    await link.click({ force: true })
    await page.waitForTimeout(600)

    // Filhos diretos do <main>: é o nível em que uma seção pode ser colapsada
    // ou movida sem reescrever a página.
    const secoes = await page.evaluate(() => {
      const main = document.querySelector('main')
      if (!main) return []
      const total = main.scrollHeight
      return Array.from(main.children).flatMap((filho) => {
        const alvos = filho.children.length > 1 ? Array.from(filho.children) : [filho]
        return alvos.map((el) => {
          const titulo =
            el.querySelector('h1, h2, h3')?.textContent?.trim() ??
            el.textContent?.trim().slice(0, 44) ??
            '(sem título)'
          const altura = (el as HTMLElement).getBoundingClientRect().height
          return { titulo, altura: Math.round(altura), pct: +(altura / total * 100).toFixed(1) }
        })
      })
    })

    console.log(`\n### ${rotulo}`)
    for (const s of secoes.filter((s) => s.altura > 80).sort((a, b) => b.altura - a.altura)) {
      console.log(`  ${String(s.altura).padStart(6)} px  ${String(s.pct).padStart(5)}%  ${s.titulo}`)
    }
  }
})
