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
      <span className="truncate text-sm text-gray-500 border-l border-gray-200 pl-3 ml-1">
        {plants[0].name}
      </span>
    )
  }

  return (
    <span className="flex items-center gap-2 border-l border-gray-200 pl-3 ml-1">
      <label htmlFor={selectId} className="sr-only">
        Usina ativa
      </label>
      <select
        id={selectId}
        value={plantId ?? ''}
        onChange={(event) => selectPlant(event.target.value)}
        className="max-w-[16rem] truncate rounded border border-gray-200 bg-white py-1 pl-2 pr-6 text-sm text-gray-700 hover:text-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)]"
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
