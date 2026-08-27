import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

// Config separada da build de produção (vite.config.ts) para não arriscar afetar
// o CSS/bundle gerado por `npm run build` — reaproveita os plugins já configurados
// lá (React + Tailwind) e só adiciona as opções do vitest.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      // O padrão de inclusão do Vitest (`**/*.spec.ts`) casa com
      // `e2e/screenshots.spec.ts`, que é spec do Playwright e importa
      // `@playwright/test` — módulo que o Vitest não resolve. Sem esta
      // exclusão o job `frontend` do CI falha com o arquivo inteiro em erro,
      // mesmo com os 973 testes de componente passando.
      exclude: ['**/node_modules/**', '**/dist/**', 'e2e/**'],
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      globals: false,
      // `DashboardPage` agora depende de uma requisição adicional (`GET
      // /plants` via `PlantContext`, ADR-069 Etapa C) antes do primeiro
      // render — sob carga da suíte inteira em paralelo, o primeiro teste que
      // monta a página estourava o timeout padrão de 5s. 15s dá folga sem
      // mascarar travamentos reais.
      testTimeout: 15000,
    },
  })
)
