// Captura visual das telas do painel (comparativo visual 2026-08-27, achado V-5).
//
// O achado: nada no fluxo de trabalho mostra a tela para alguém. Os testes de
// componente verificam comportamento — `role`, `aria`, texto — e nunca
// aparência. Foi por isso que a tipografia do produto ficou em `system-ui` sem
// ninguém notar, com as fontes desenhadas já baixadas no repositório.
//
// Isto NÃO é regressão visual automatizada: não há comparação com baseline nem
// falha por diferença de pixel. É captura, para o PR carregar a imagem e um
// humano poder olhar. Comparação automática vem depois, se valer a pena — o
// primeiro problema a resolver é a cegueira, não a tolerância a diferença.
import { defineConfig, devices } from '@playwright/test'

const PORTA = 4173
const BASE_URL = `http://localhost:${PORTA}`

export default defineConfig({
  testDir: './e2e',
  // Sem retry: uma captura que falha precisa ser investigada, não repetida até
  // passar. Falha aqui significa que a tela não renderizou.
  retries: 0,
  reporter: process.env.CI ? 'line' : 'list',
  outputDir: './e2e/.output',

  use: {
    baseURL: BASE_URL,
    // `reduce` para não capturar quadro no meio de transição: o app respeita
    // `motion-reduce:` (ver as classes em MetricCard e useChartEntrance), então
    // isto torna a captura determinística sem desligar estilo nenhum.
    reducedMotion: 'reduce',
    // Fuso e locale fixos: sem isto a captura muda conforme a máquina, e todo
    // diff de imagem viraria ruído de data formatada.
    timezoneId: 'America/Sao_Paulo',
    locale: 'pt-BR',
  },

  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      // O painel é consultado no celular com frequência; capturar só desktop
      // esconderia justamente onde o layout costuma quebrar.
      name: 'mobile',
      use: { ...devices['Pixel 7'] },
    },
  ],

  webServer: {
    // `preview` serve o `dist/` real — o mesmo artefato que vai para o
    // Cloudflare Pages, incluindo o CSS e as fontes finais. Capturar do
    // servidor de desenvolvimento mostraria uma tela que ninguém recebe.
    command: `npm run build && npx vite preview --port ${PORTA} --strictPort`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: {
      // A API é interceptada pelo Playwright; este valor só precisa passar na
      // validação de `env.ts` (URL absoluta, HTTPS em produção).
      VITE_API_URL: 'https://api.captura.test',
    },
  },
})
