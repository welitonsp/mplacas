import { useId } from 'react'
import { usePlant } from '../contexts/PlantContext'

// Seletor de usina no `AppHeader` (ADR-069, Etapa D). Regra da seção 7 do
// ADR: só existe dropdown quando há mais de uma usina no escopo do
// principal. Com exatamente uma, mostramos o nome como texto simples — ganho
// puro sobre o estado anterior, que não mostrava nome nenhum. Com zero
// usinas não renderizamos nada aqui: o estado vazio já é tratado inteiro em
// `DashboardPage`.
export function PlantSelector() {
  const { plantId, plants, selectPlant } = usePlant()
  const selectId = useId()

  if (plants.length === 0) return null

  if (plants.length === 1) {
    return (
      <span className="ml-1 hidden min-w-0 items-center gap-2 rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-sm text-gray-700 sm:inline-flex">
        <span className="h-2 w-2 rounded-full bg-[var(--color-success)]" aria-hidden="true" />
        <span className="truncate">{plants[0].name}</span>
      </span>
    )
  }

  return (
    <span className="ml-1 hidden items-center gap-2 rounded-full border border-gray-200 bg-gray-50 px-2 py-1 sm:flex">
      <label htmlFor={selectId} className="sr-only">
        Usina ativa
      </label>
      <span className="h-2 w-2 rounded-full bg-[var(--color-success)]" aria-hidden="true" />
      <select
        id={selectId}
        value={plantId ?? ''}
        onChange={(event) => selectPlant(event.target.value)}
        className="max-w-[16rem] truncate rounded-full border-0 bg-transparent py-0.5 pl-1 pr-6 text-sm font-medium text-gray-700 hover:text-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
      >
        {plants.map((plant) => (
          <option key={plant.id} value={plant.id}>
            {plant.name}
          </option>
        ))}
      </select>
    </span>
  )
}
