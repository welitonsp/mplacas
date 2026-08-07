import { FormEvent, useId, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../contexts/AuthContext'
import { BrandMark } from '../components/BrandMark'

const BENEFITS = [
  'Produção e consumo consolidados',
  'Diagnósticos com ações recomendadas',
  'Indicadores financeiros auditáveis',
]

export function LoginPage() {
  const { login, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const errorId = useId()

  const sessionEnded =
    (location.state as { reason?: string } | null)?.reason === 'SESSION_ENDED'

  // Redirecionamento declarativo
  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)

    if (!username.trim() || !password) {
      setError('Informe usuário e senha para continuar.')
      return
    }

    setLoading(true)
    try {
      await login(username, password)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('Erro ao autenticar. Tente novamente.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden bg-slate-950 font-sans">
      {/* Background animado / Mesh Gradient moderno (Estilo Stripe/Vercel) */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[60%] rounded-full bg-blue-600/20 mix-blend-screen filter blur-[100px] animate-pulse"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[60%] h-[70%] rounded-full bg-indigo-600/20 mix-blend-screen filter blur-[120px]"></div>
      <div className="absolute top-[20%] right-[10%] w-[30%] h-[40%] rounded-full bg-cyan-400/10 mix-blend-screen filter blur-[100px] animate-pulse delay-1000"></div>

      <div className="relative z-10 w-full max-w-6xl flex flex-col lg:flex-row items-center justify-between gap-12 px-6 py-12">
        
        {/* Painel de Apresentação (Esquerda) */}
        <div className="flex-1 w-full text-center lg:text-left space-y-8">
          <div className="inline-flex items-center justify-center lg:justify-start gap-3">
            <BrandMark className="h-10 w-auto text-blue-400" />
            <span className="text-2xl font-bold text-white tracking-tight">Mplacas</span>
          </div>
          
          <h1 className="text-5xl lg:text-7xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-200 to-slate-400 tracking-tight leading-tight">
            Inteligência <br/> Solar.
          </h1>
          <p className="text-lg lg:text-xl text-slate-400 font-medium max-w-lg mx-auto lg:mx-0 leading-relaxed">
            Tenha controle total sobre a operação da sua usina com dados auditáveis e indicadores financeiros em tempo real.
          </p>

          <ul className="mt-8 space-y-4 max-w-md mx-auto lg:mx-0 text-left">
            {BENEFITS.map((benefit) => (
              <li key={benefit} className="flex items-center gap-3 text-slate-300 font-medium">
                <div className="flex-shrink-0 h-6 w-6 rounded-full bg-blue-500/20 flex items-center justify-center border border-blue-500/30">
                  <svg viewBox="0 0 20 20" className="h-4 w-4 text-blue-400" fill="currentColor">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                </div>
                {benefit}
              </li>
            ))}
          </ul>
        </div>

        {/* Card de Login (Direita - Glassmorphism Premium) */}
        <div className="w-full max-w-md bg-white/5 backdrop-blur-2xl border border-white/10 p-10 rounded-[2.5rem] shadow-[0_8px_32px_0_rgba(0,0,0,0.5)]">
          <div className="mb-8 text-center lg:text-left">
            <h2 className="text-2xl font-bold text-white tracking-tight">Acesso ao Painel</h2>
            <p className="text-slate-400 mt-2 text-sm font-medium">Insira suas credenciais para continuar</p>
          </div>

          {sessionEnded && (
            <div role="status" className="mb-6 rounded-2xl bg-rose-500/10 border border-rose-500/20 px-4 py-3 text-sm text-rose-300 font-medium">
              Sua sessão foi encerrada. Entre novamente.
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-5">
            <div>
              <label htmlFor="username" className="block text-sm font-semibold text-slate-300 mb-2">
                Usuário
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                autoFocus
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={loading}
                className="w-full bg-slate-900/50 border border-slate-700/50 rounded-2xl px-5 py-3.5 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/80 focus:border-blue-500 transition-all duration-300 disabled:opacity-50"
                placeholder="Seu usuário"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-semibold text-slate-300 mb-2">
                Senha
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                  className="w-full bg-slate-900/50 border border-slate-700/50 rounded-2xl px-5 py-3.5 pr-16 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/80 focus:border-blue-500 transition-all duration-300 disabled:opacity-50"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  className="absolute inset-y-0 right-2 flex items-center justify-center px-4 text-xs font-bold text-slate-400 hover:text-white transition-colors focus:outline-none"
                >
                  {showPassword ? 'Ocultar' : 'Mostrar'}
                </button>
              </div>
            </div>

            {error && (
              <div id={errorId} role="alert" className="rounded-2xl bg-rose-500/10 border border-rose-500/20 px-4 py-3 text-sm text-rose-300 font-medium">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-4 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-4 text-sm font-bold text-white shadow-[0_0_20px_rgba(37,99,235,0.4)] hover:shadow-[0_0_30px_rgba(37,99,235,0.6)] hover:from-blue-500 hover:to-indigo-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-900 transition-all duration-300 disabled:opacity-50 disabled:transform-none transform hover:-translate-y-1"
            >
              {loading ? 'Entrando...' : 'Entrar no Painel'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
