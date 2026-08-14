// Valida variáveis de ambiente no startup. Falha claramente se ausentes ou inválidas.

function requireEnv(key: string): string {
  const value = import.meta.env[key]
  if (!value || typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Missing required environment variable: ${key}`)
  }
  return value.trim()
}

export const API_URL = (() => {
  const raw = requireEnv('VITE_API_URL')

  // Validação por `new URL()` em vez de `startsWith('https://')` (auditoria v6,
  // achado A-14). Prefixo não é forma: `https://` sozinho, `https:// `, ou
  // `https://?x=1` passam pelo teste de prefixo e não são endereço utilizável.
  // O erro apareceria só na primeira requisição, longe da causa — enquanto uma
  // variável de ambiente malformada deve falhar no startup, com mensagem que
  // aponta o que está errado.
  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    throw new Error(`VITE_API_URL is not a valid URL: ${raw}`)
  }

  if (parsed.hostname === '') {
    throw new Error(`VITE_API_URL has no hostname: ${raw}`)
  }

  // Em produção, exigir HTTPS. Fora dela, `http://localhost` é legítimo.
  if (import.meta.env.PROD && parsed.protocol !== 'https:') {
    throw new Error(`VITE_API_URL must use HTTPS in production (got ${parsed.protocol})`)
  }

  return raw.replace(/\/$/, '') // sem trailing slash
})()
