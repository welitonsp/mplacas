import React, { createContext, useCallback, useContext, useRef, useState } from 'react'
import { configureApi, apiFetch } from '../lib/api'
import { TokenStore } from '../lib/auth'
import { API_URL } from '../env'

interface AuthContextValue {
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!TokenStore.get())
  const refreshTokenRef = useRef<string | null>(null)

  const logout = useCallback(() => {
    TokenStore.clear()
    refreshTokenRef.current = null
    setIsAuthenticated(false)
  }, [])

  const getRefreshToken = useCallback(() => refreshTokenRef.current, [])

  // Configura o api.ts com as funções do contexto
  configureApi(getRefreshToken, logout)

  const login = useCallback(async (username: string, password: string) => {
    const response = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })

    if (!response.ok) {
      const status = response.status
      if (status === 401) throw new Error('Credenciais inválidas.')
      if (status === 503) throw new Error('Serviço de autenticação não configurado.')
      throw new Error('Erro ao autenticar. Tente novamente.')
    }

    const { access_token, refresh_token } = await response.json() as {
      access_token: string
      refresh_token: string
    }

    TokenStore.set(access_token)
    refreshTokenRef.current = refresh_token
    setIsAuthenticated(true)
  }, [])

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

// Re-export apiFetch so pages can import from a single auth module if desired
export { apiFetch }
