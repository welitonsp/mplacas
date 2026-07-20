const ACCESS_TOKEN_KEY = 'mplacas_access_token'

export const TokenStore = {
  get: (): string | null => localStorage.getItem(ACCESS_TOKEN_KEY),
  set: (token: string): void => { localStorage.setItem(ACCESS_TOKEN_KEY, token) },
  clear: (): void => { localStorage.removeItem(ACCESS_TOKEN_KEY) },
}
