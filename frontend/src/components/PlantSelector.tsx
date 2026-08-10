import { useId } from 'react'
import { usePlant } from '../contexts/PlantContext'
import { formatNumber, toNumber } from '../lib/format'

function formatPowerKwp(value: string | null): string | null {
  const power = toNumber(value)
  return power === null ? null : `${formatNumber(power, 1)} kWp`
}

// Seletor de usina no `AppHeader` (ADR-069, Etapa D). Regra da seção 7 do
// ADR: só existe dropdown quando há mais de uma usina no escopo do
// principal. Com exatamente uma, mostramos o nome como texto simples — ganho
// puro sobre o estado anterior, que não mostrava nome nenhum. Com zero
// usinas não renderizamos nada aqui: o estado vazio já é tratado inteiro em
// `DashboardPage`.
export function PlantSelector() {
  const { plantId, plants, selectPlant } = usePlant()
  const selectId = useId()
  const powerId = useId()

  if (plants.length === 0) return null

  const activePlant = plants.find((plant) => plant.id === plantId) ?? plants[0]
  const activePower = formatPowerKwp(activePlant.installedPowerKwp)

  if (plants.length === 1) {
    return (
      <span className="ml-1 flex min-w-0 max-w-[min(52vw,18rem)] items-center gap-2 rounded-2xl border border-gray-200 bg-gray-50 px-2.5 py-1 text-gray-700 shadow-sm">
        <span className="h-2 w-2 shrink-0 rounded-full bg-[var(--color-success)]" aria-hidden="true" />
        <span className="min-w-0">
          <span className="block text-[12px] font-semibold uppercase leading-4 tracking-[0.12em] text-[var(--color-text-muted)]">
            Usina ativa
          </span>
          <span className="block truncate text-sm font-semibold leading-5 text-gray-900">{activePlant.name}</span>
          {activePower && (
            <span className="block truncate text-xs leading-4 text-[var(--color-text-secondary)]">
              {activePower} instalados
            </span>
          )}
        </span>
      </span>
    )
  }

  return (
    <span className="ml-1 flex min-w-0 max-w-[min(52vw,20rem)] items-center gap-2 rounded-2xl border border-gray-200 bg-gray-50 px-2.5 py-1 text-gray-700 shadow-sm">
      <label htmlFor={selectId} className="sr-only">
        Usina ativa
      </label>
      <span className="h-2 w-2 shrink-0 rounded-full bg-[var(--color-success)]" aria-hidden="true" />
      <span className="min-w-0">
        <span className="block text-[12px] font-semibold uppercase leading-4 tracking-[0.12em] text-[var(--color-text-muted)]">
          Usina ativa
        </span>
        <select
          id={selectId}
          value={plantId ?? ''}
          onChange={(event) => selectPlant(event.target.value)}
          aria-describedby={activePower ? powerId : undefined}
          className="block max-w-full truncate rounded-lg border-0 bg-transparent py-0 pr-7 text-sm font-semibold leading-5 text-gray-900 hover:text-gray-950 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
        >
          {plants.map((plant) => (
            <option key={plant.id} value={plant.id}>
              {plant.name}
            </option>
          ))}
        </select>
        {activePower && (
          <span id={powerId} className="block truncate text-xs leading-4 text-[var(--color-text-secondary)]">
            {activePower} instalados
          </span>
        )}
      </span>
    </span>
  )
}
