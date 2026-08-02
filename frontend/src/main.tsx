import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { App } from './App'

// Environment variables are validated at import time in env.ts.
// If any required variable is missing or invalid, the import will throw
// and the app will fail fast with a clear error message.
import './env'

// Migração de segurança do dashboard FastAPI removido. Nunca lemos o
// valor: apenas apagamos a credencial de longa duração deixada por versões antigas.
window.localStorage.removeItem('mplacas_creds_v1')

const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('Root element #root not found in DOM')
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
