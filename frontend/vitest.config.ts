import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

// Config separada da build de produção (vite.config.ts) para não arriscar afetar
// o CSS/bundle gerado por `npm run build` — reaproveita os plugins já configurados
// lá (React + Tailwind) e só adiciona as opções do vitest.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      globals: false,
    },
  })
)
