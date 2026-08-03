import { API_URL } from '../env'
import { TokenStore } from './auth'

type RefreshTokenGetter = () => string | null
type RefreshTokenSetter = (token: string) => void
type LogoutFn = () => void

let _getRefreshToken: RefreshTokenGetter = () => null
let _setRefreshToken: RefreshTokenSetter = () => {}
let _logout: LogoutFn = () => {}

export function configureApi(
  getRefreshToken: RefreshTokenGetter,
  setRefreshToken: RefreshTokenSetter,
  logout: LogoutFn,
) {
  _getRefreshToken = getRefreshToken
  _setRefreshToken = setRefreshToken
  _logout = logout
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = TokenStore.get()
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  headers.set('Content-Type', 'application/json')

  const response = await fetch(`${API_URL}${path}`, { ...init, headers })

  if (response.status !== 401) return response

  // Tenta refresh uma única vez.
  const refreshToken = _getRefreshToken()
  if (!refreshToken) { _logout(); return response }

  const refreshResponse = await fetch(`${API_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })

  if (!refreshResponse.ok) { _logout(); return response }

  const { access_token, refresh_token } = await refreshResponse.json() as {
    access_token: string
    refresh_token: string
  }
  TokenStore.set(access_token)
  _setRefreshToken(refresh_token)

  // Repete a chamada original com o novo token.
  const retryHeaders = new Headers(init.headers)
  retryHeaders.set('Authorization', `Bearer ${access_token}`)
  retryHeaders.set('Content-Type', 'application/json')
  return fetch(`${API_URL}${path}`, { ...init, headers: retryHeaders })
}

// Leitura composta da modelagem fotovoltaica (performance + baseline sazonal +
// perdas) para uma usina, em uma única requisição (ver ADR-065, seção 4,
// `GET /photovoltaic/summary`). Sempre 200 quando a usina está no escopo do
// principal — blocos ausentes vêm como `null` acompanhados de um motivo, nunca
// como erro HTTP, então não há tratamento de status especial além do 401 já
// coberto por `apiFetch`.
export async function fetchPhotovoltaicSummary(plantId: string): Promise<Response> {
  return apiFetch(`/photovoltaic/summary?plant_id=${encodeURIComponent(plantId)}`)
}
