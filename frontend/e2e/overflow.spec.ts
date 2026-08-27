// Guarda contra rolagem horizontal no celular (achado V-7).
//
// O painel inteiro rolava de lado no mobile: o documento media 750 px numa
// viewport de 412 px. A causa era o `<aside>` do AppShell sem `min-w-0` — item
// de grid tem `min-width: auto` e não encolhe abaixo da largura intrínseca do
// conteúdo, e o menu de módulos é um scroller de 4 itens com `min-w-[9.25rem]`
// cada. O `<main>` ao lado já tinha a proteção; o `<aside>` ficou sem.
//
// Ninguém percebeu porque nenhum teste olhava a largura da página, e a captura
// visual só passou a existir dias antes. As imagens do mobile saíam com 1922 px
// de largura — quase o dobro do esperado — e isso não chamava atenção sem alguém
// dividir pelo `deviceScaleFactor`.
//
// Rolagem lateral no celular é pior que vertical: some com conteúdo fora da tela
// sem sinal visível. Por isso esta é asserção, não relatório.
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

const MODULOS = ['Visão Geral', 'Produção', 'Financeiro', 'Técnico'] as const

test.describe('layout não rola de lado', () => {
  test.skip(({ isMobile }) => !isMobile, 'específico de viewport estreita')

  test('nenhum módulo estoura a largura da viewport', async ({ page }) => {
    test.setTimeout(120_000)

    await page.route(
      (url) => url.hostname === 'api.captura.test',
      (rota) => rota.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
    )
    const rotas: Array<[string, unknown]> = [
      ['**/auth/login', { access_token: 'x', refresh_token: 'x' }],
      [
        '**/plants',
        { count: 1, items: [{ id: singlePlant.id, name: singlePlant.name, installed_power_kwp: null }] },
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
    await page.getByLabel(/senha/i).fill('guarda')
    await page.getByRole('button', { name: /entrar/i }).click()
    await page.waitForURL('**/dashboard/**')

    for (const rotulo of MODULOS) {
      const link = page.getByRole('link', { name: rotulo })
      await link.scrollIntoViewIfNeeded()
      await link.click({ force: true })
      await expect(page.getByRole('main')).toBeVisible()

      const medida = await page.evaluate(() => ({
        viewport: document.documentElement.clientWidth,
        documento: document.documentElement.scrollWidth,
        // Nomear o culpado poupa a investigação inteira de quem quebrar isto.
        culpados: Array.from(document.querySelectorAll('*'))
          .filter((el) => el.getBoundingClientRect().width > document.documentElement.clientWidth + 1)
          .slice(0, 3)
          .map((el) => `<${el.tagName.toLowerCase()} class="${String(el.className).slice(0, 60)}">`),
      }))

      expect(
        medida.documento,
        `${rotulo}: documento tem ${medida.documento}px numa viewport de ${medida.viewport}px. ` +
          `Elementos estourando: ${medida.culpados.join(' ') || '(nenhum identificado)'}. ` +
          'Item de grid/flex precisa de min-w-0 para encolher — ver AppShell.tsx.'
      ).toBeLessThanOrEqual(medida.viewport)
    }
  })
})
