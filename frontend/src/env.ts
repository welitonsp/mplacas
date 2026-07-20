// Valida variáveis de ambiente no startup. Falha claramente se ausentes ou inválidas.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

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

export const PLANT_ID = (() => {
  const id = requireEnv('VITE_PLANT_ID')
  if (!UUID_RE.test(id)) {
    throw new Error(`VITE_PLANT_ID is not a valid UUID: ${id}`)
  }
  return id
})()
