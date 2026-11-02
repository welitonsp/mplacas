import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { importProductionHistory } from '../../lib/api'
import { DASHBOARD_SETUP_PATH } from '../../routes'

// Usina conectada mas ainda sem nenhuma leitura (ADR-097): em vez de esperar
// a coleta da madrugada, o Início busca na marca a produção dos últimos 90
// dias — uma vez por usina nesta aba — e oferece o botão para tentar de novo.
// Só para ADMIN (quem lê não dispara escrita). Nenhum segredo passa por aqui:
// o servidor usa a conexão guardada.

type State =
  | { kind: 'running' }
  // `days` = registros recebidos da marca (soma por inversor), só para saber se veio algo
  | { kind: 'done'; days: number }
  // a marca não libera o histórico desta conta (ADR-098)
  | { kind: 'meter' }
  | { kind: 'error'; message: string; noConnection: boolean }
  | null

// Uma tentativa automática por usina enquanto a aba estiver aberta: voltar ao
// Início não bate de novo na marca (o servidor também limita).
const autoTried = new Set<string>()

// Só os códigos que a importação devolve. Mantido aqui (e não importado de
// provider-account-contracts) para o Início não puxar o módulo de conexão
// inteiro para o bundle compartilhado.
const IMPORT_ERRORS: Record<string, string> = {
  provider_verify_rate_limited: 'Você já buscou há pouco. Espere alguns minutos e tente de novo.',
  provider_rate_limited: 'A marca bloqueou novas consultas por um tempo. Espere cerca de uma hora e tente de novo.',
  provider_unavailable: 'A marca não respondeu agora. Tente de novo em alguns minutos.',
  provider_login_failed: 'A marca recusou o usuário ou a senha guardados. Atualize a conexão em Minha usina.',
  provider_token_failed: 'A Growatt recusou o token guardado. Gere um novo no app ShinePhone e atualize a conexão em Minha usina.',
  provider_account_unreadable: 'Não foi possível ler a conexão guardada. Conecte de novo em Minha usina.',
  provider_login_blocked: 'A marca bloqueou o acesso vindo do nosso servidor — não é a sua senha. Tente mais tarde.',
  history_import_error: 'Não foi possível gravar a produção agora. Tente de novo em instantes.',
  provider_inverter_in_another_plant: 'Algum inversor desta conta já está ligado a outra usina. Fale com o suporte.',
}

async function importErrorMessage(response: Response): Promise<string> {
  if (response.status === 403) return 'Só o administrador da conta pode buscar a produção.'
  try {
    const code = ((await response.json()) as { detail?: unknown })?.detail
    if (typeof code === 'string' && code in IMPORT_ERRORS) return IMPORT_ERRORS[code]
  } catch {
    // corpo sem JSON: mensagem genérica abaixo
  }
  return 'Não foi possível buscar a produção agora. Tente novamente.'
}

export function resetHistoryAutoImportForTests() {
  autoTried.clear()
}

export function HomeHistoryImport({ plantId, onImported }: { plantId: string; onImported: () => void }) {
  const [state, setState] = useState<State>(null)
  const onImportedRef = useRef(onImported)
  onImportedRef.current = onImported
  const running = useRef(false)

  const run = async () => {
    if (running.current) return
    running.current = true
    setState({ kind: 'running' })
    try {
      const response = await importProductionHistory(plantId)
      if (!response.ok) {
        const noConnection = response.status === 404
        setState({
          kind: 'error',
          noConnection,
          message: noConnection
            ? 'Esta usina não está conectada a uma marca de inversor.'
            : await importErrorMessage(response),
        })
        return
      }
      const body = (await response.json()) as { days_received?: unknown; history_available?: unknown }
      if (body.history_available === false) {
        setState({ kind: 'meter' })
        return
      }
      const days = typeof body.days_received === 'number' ? body.days_received : 0
      setState({ kind: 'done', days })
      if (days > 0) onImportedRef.current()
    } catch {
      setState({ kind: 'error', noConnection: false, message: 'Não foi possível buscar a produção agora. Tente novamente.' })
    } finally {
      running.current = false
    }
  }

  useEffect(() => {
    if (autoTried.has(plantId)) return
    autoTried.add(plantId)
    void run()
    // `run` lê só refs e `plantId`; reexecutar a cada render dispararia de novo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plantId])

  return (
    <div
      data-testid="home-history-import"
      className="flex flex-wrap items-center gap-3 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-sm"
    >
      <p aria-live="polite" className="min-w-0 flex-1 text-[var(--color-text-secondary)]">
        {state?.kind === 'running'
          ? 'Buscando na marca a produção dos últimos 90 dias…'
          : state?.kind === 'done'
            ? state.days > 0
              ? 'Produção importada. Atualizando o Início…'
              : 'A marca ainda não tem produção registrada para esta usina. A coleta automática segue todos os dias.'
            : state?.kind === 'meter'
              ? 'A Growatt não libera o histórico desta conta. A partir de agora o sistema lê o total da usina toda madrugada e mostra a produção de cada dia — o primeiro dia aparece em até dois dias.'
              : state?.kind === 'error'
              ? state.message
              : 'Busque na marca a produção dos últimos 90 dias, sem esperar a coleta automática.'}
        {state?.kind === 'error' && state.noConnection && (
          <>
            {' '}
            <Link to={DASHBOARD_SETUP_PATH} className="font-semibold text-[var(--color-brand-primary)] underline">
              Conectar em Minha usina
            </Link>
          </>
        )}
      </p>
      {state?.kind !== 'running' && state?.kind !== 'meter' && !(state?.kind === 'error' && state.noConnection) && (
        <button
          type="button"
          onClick={() => void run()}
          className="min-h-[44px] rounded-lg border border-[var(--color-border-strong,var(--color-border))] px-4 font-semibold text-[var(--color-text-primary)] hover:bg-[var(--color-surface-sunken)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
        >
          Buscar produção na marca
        </button>
      )}
    </div>
  )
}
