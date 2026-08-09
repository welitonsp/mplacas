import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { applyTheme, resolveInitialTheme } from './lib/theme'

// Resolve e aplica o tema (claro/escuro) antes de qualquer render — ADR-071,
// Decisão 2. Side-effect de módulo, roda uma única vez no bootstrap, fora de
// qualquer árvore React — por isso fora do alcance do `ErrorBoundary` (que só
// captura erros durante o ciclo de render de uma árvore já montada). Um
// `localStorage`/`matchMedia` bloqueado por alguma política incomum de
// navegador não pode deixar a página em branco sem nenhuma mensagem: o
// `try/catch` aqui garante um tema padrão seguro (claro) e loga o erro,
// sem lançar — o boot do app nunca trava por causa da resolução de tema.
try {
  applyTheme(resolveInitialTheme())
} catch (error) {
  // eslint-disable-next-line no-console
  console.error('Falha ao resolver o tema inicial do Mplacas; usando o tema claro padrão:', error)
  applyTheme('light')
}

// Migração de segurança do dashboard FastAPI removido. Nunca lemos o
// valor: apenas apagamos a credencial de longa duração deixada por versões antigas.
window.localStorage.removeItem('mplacas_creds_v1')

const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('Root element #root not found in DOM')
}

const root = createRoot(rootElement)

function ConfigErrorScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm text-center">
        <div className="bg-[var(--color-surface)] rounded-2xl shadow-sm border border-gray-200 p-8">
          <h1 className="text-lg font-semibold text-gray-900">Não foi possível carregar o Mplacas</h1>
          <p className="mt-2 text-sm text-gray-500">
            O painel não pôde ser iniciado. Tente recarregar a página; se o problema continuar,
            entre em contato com o suporte.
          </p>
        </div>
      </div>
    </div>
  )
}

async function bootstrap() {
  try {
    // Import dinâmico (em vez de estático no topo do arquivo): `env.ts`
    // valida as variáveis de ambiente obrigatórias e lança na importação se
    // alguma faltar/for inválida (`App` → `AuthProvider`/`api.ts` → `env.ts`).
    // Uma importação estática avaliaria isso antes de qualquer render, fora
    // do alcance de um `ErrorBoundary` (que só captura erros durante o ciclo
    // de render de uma árvore já montada) — adiar para dentro deste `try` é
    // o que torna esse erro específico capturável, sem página em branco
    // (ver P3-05 na auditoria de UI/UX).
    const [{ App }, { ErrorBoundary }] = await Promise.all([
      import('./App'),
      import('./components/ErrorBoundary'),
    ])

    root.render(
      <StrictMode>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </StrictMode>,
    )
  } catch (error) {
    // eslint-disable-next-line no-console
    console.error('Falha ao inicializar o Mplacas:', error)
    root.render(<ConfigErrorScreen />)
  }
}

void bootstrap()
