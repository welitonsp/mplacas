// Cloudflare Pages Function: toda requisição a `/api/*` (e só ela, ver
// `public/_routes.json`) é repassada à API no Render. A lógica e os testes
// moram em `edge/apiProxy.ts`: tudo dentro de `functions/` vira rota.
//
// Configuração (Cloudflare Pages → Settings → Variables and Secrets, produção):
//   MPLACAS_API_ORIGIN           origem https exata da API no Render
//   MPLACAS_PROXY_SHARED_SECRET  segredo (≥ 32 bytes), igual ao do Render
// Faltando qualquer um, a Function responde 503 (falha fechada).
import { proxyApiRequest, type ProxyEnv } from '../../edge/apiProxy'

interface PagesContext {
  request: Request
  env: ProxyEnv
}

export const onRequest = (context: PagesContext): Promise<Response> =>
  proxyApiRequest(context.request, context.env)
