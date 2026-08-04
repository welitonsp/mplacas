import { Component, type ErrorInfo, type ReactNode } from 'react'

// Sem isso, um erro de render (ex.: `env.ts` lançando por variável de
// ambiente ausente — ver `main.tsx`) deixava a página inteiramente em branco,
// sem nenhuma pista para quem está usando o app (ver P3-05 na auditoria de
// UI/UX). A mensagem é deliberadamente genérica — nunca expõe `error.message`
// ou stack trace na tela, que podem conter detalhes internos (nomes de
// variável de ambiente, URLs de API); esses detalhes só vão para o console,
// útil para quem está depurando localmente.
export class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error('Erro não tratado na interface do Mplacas:', error, info.componentStack)
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
          <div className="w-full max-w-sm text-center">
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <h1 className="text-lg font-semibold text-gray-900">Não foi possível carregar o Mplacas</h1>
              <p className="mt-2 text-sm text-gray-500">
                Algo deu errado ao abrir o painel. Tente recarregar a página; se o problema
                continuar, entre em contato com o suporte.
              </p>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="mt-6 w-full rounded-lg bg-[var(--color-brand-primary)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-brand-primary-dark)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-primary)] focus:ring-offset-2 transition-colors duration-150"
              >
                Recarregar
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
