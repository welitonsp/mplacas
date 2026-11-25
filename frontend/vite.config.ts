import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Desenvolvimento local (ADR-102): o app sempre chama `/api`, como em produção.
// Lá quem repassa é a Pages Function (`functions/api/[[path]].ts`); aqui é o
// proxy do `vite dev`, com o alvo em `MPLACAS_DEV_API_ORIGIN` (padrão: a API
// local do `uvicorn` na porta 8000). Sem `/api` no backend: o prefixo é tirado,
// igual à Function.
const devApiOrigin = process.env.MPLACAS_DEV_API_ORIGIN ?? 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
  server: {
    proxy: {
      '/api': {
        target: devApiOrigin,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
