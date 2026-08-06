// Valida variáveis de ambiente no startup. Falha claramente se ausentes ou inválidas.

function requireEnv(key: string): string {
  const value = import.meta.env[key]
  if (!value || typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Missing required environment variable: ${key}`)
  }
  return value.trim()
}

export const API_URL = (() => {
  const url = requireEnv('VITE_API_URL')
  // Em produção, exigir HTTPS
  if (import.meta.env.PROD && !url.startsWith('https://')) {
    throw new Error('VITE_API_URL must use HTTPS in production')
  }
  return url.replace(/\/$/, '') // sem trailing slash
})()
