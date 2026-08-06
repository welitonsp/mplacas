import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { fetchPlants } from '../lib/api'
import type { Plant } from '../lib/dashboard/plant-contracts'

// Chave de `localStorage` usada para lembrar a última usina escolhida entre
// sessões (ADR-069, seção 5). Exportada para que `AuthContext.logout()` limpe
// o mesmo valor — a seleção de usina é estado de sessão, não deve sobreviver
// a um logout.
export const SELECTED_PLANT_STORAGE_KEY = 'mplacas_selected_plant_v1'

interface PlantContextValue {
  plantId: string | null
  plants: Plant[]
  loading: boolean
  error: string | null
  selectPlant: (id: string) => void
}

const PlantContext = createContext<PlantContextValue | null>(null)

// Resolve a usina ativa a partir da lista carregada e das duas fontes de
// preferência (query string e `localStorage`), na ordem definida pelo ADR-069
// seção 5: `?plant=` válido no escopo → `localStorage` válido no escopo →
// primeiro item da lista (já ordenada por nome pelo backend). Seleção fora do
// escopo é descartada silenciosamente — nunca vira erro.
function resolvePlantId(plants: Plant[], queryPlantId: string | null): string | null {
  if (plants.length === 0) return null

  if (queryPlantId && plants.some((plant) => plant.id === queryPlantId)) {
    return queryPlantId
  }

  const stored = window.localStorage.getItem(SELECTED_PLANT_STORAGE_KEY)
  if (stored && plants.some((plant) => plant.id === stored)) {
    return stored
  }

  return plants[0].id
}

// Busca a lista de usinas da organização do principal autenticado ao montar
// (ver `fetchPlants`, Etapa B) e resolve qual delas fica ativa. Deve ficar
// **dentro** de `ProtectedRoute` — `GET /plants` exige autenticação (ADR-069,
// seção 8).
export function PlantProvider({ children }: { children: React.ReactNode }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [plants, setPlants] = useState<Plant[]>([])
  const [plantId, setPlantId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const items = await fetchPlants()
        if (cancelled) return
        setPlants(items)
        setPlantId(resolvePlantId(items, searchParams.get('plant')))
      } catch (err) {
        if (cancelled) return
        const message = err instanceof Error ? err.message : 'Erro ao buscar usinas.'
        setError(message)
        setPlants([])
        setPlantId(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()

    return () => {
      cancelled = true
    }
    // Resolvido apenas na montagem: a leitura da query string acontece uma
    // vez, na carga inicial. Trocas subsequentes passam por `selectPlant`, que
    // já atualiza `plantId`/query string/`localStorage` diretamente, sem
    // precisar de uma nova busca de `/plants`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selectPlant = useCallback(
    (id: string) => {
      setPlantId(id)
      window.localStorage.setItem(SELECTED_PLANT_STORAGE_KEY, id)
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set('plant', id)
          return next
        },
        { replace: true }
      )
    },
    [setSearchParams]
  )

  const value = useMemo(
    () => ({ plantId, plants, loading, error, selectPlant }),
    [plantId, plants, loading, error, selectPlant]
  )

  return <PlantContext.Provider value={value}>{children}</PlantContext.Provider>
}

export function usePlant(): PlantContextValue {
  const ctx = useContext(PlantContext)
  if (!ctx) throw new Error('usePlant must be used within PlantProvider')
  return ctx
}
