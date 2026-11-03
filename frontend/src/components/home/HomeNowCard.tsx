import { formatNumber } from '../../lib/format'

// "Agora" no Início para contas Growatt sem histórico (ADR-099): o que a
// marca informa na lista de usinas — total desde a instalação e potência no
// momento da leitura. Sempre com a fonte e a hora; campo que a marca não
// informou aparece como "não informado", nunca como zero.

export interface PlantNow {
  total_kwh: number | null
  current_power_kw: number | null
  read_at: string
}

function toNumber(value: unknown): number | null {
  if (value == null || value === '') return null
  const number = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(number) ? number : null
}

export function parsePlantNow(payload: unknown): PlantNow {
  const body = (payload ?? {}) as Record<string, unknown>
  if (typeof body.read_at !== 'string') throw new Error('plant now without read_at')
  return {
    total_kwh: toNumber(body.total_kwh),
    current_power_kw: toNumber(body.current_power_kw),
    read_at: body.read_at,
  }
}

function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

export function HomeNowCard({ now }: { now: PlantNow }) {
  const time = formatTime(now.read_at)
  return (
    <section
      aria-labelledby="home-now-heading"
      data-testid="home-now"
      className="flex flex-col gap-3.5 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-6"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="home-now-heading" className="text-sm font-medium text-[var(--color-text-secondary)]">
          Sua usina agora
        </h2>
        <span className="shrink-0 rounded-full bg-[var(--color-gray-100)] px-2 py-0.5 text-xs font-semibold text-[var(--color-chart-reference)]">
          Medido
        </span>
      </div>
      <dl className="grid grid-cols-2 gap-4">
        <div>
          <dt className="text-xs text-[var(--color-text-secondary)]">Gerando agora</dt>
          <dd className="font-display text-2xl font-semibold text-[var(--color-text-primary)]">
            {now.current_power_kw == null ? 'não informado' : `${formatNumber(now.current_power_kw, 2)} kW`}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-[var(--color-text-secondary)]">Total desde a instalação</dt>
          <dd className="font-display text-2xl font-semibold text-[var(--color-text-primary)]">
            {now.total_kwh == null ? 'não informado' : `${formatNumber(now.total_kwh, 0)} kWh`}
          </dd>
        </div>
      </dl>
      <p className="text-xs text-[var(--color-text-secondary)]">
        {`Lido na Growatt${time ? ` às ${time}` : ''}. Atualiza a cada 10 minutos.`}
      </p>
    </section>
  )
}
