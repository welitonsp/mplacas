import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { fetchMe } from '../lib/api'
import { parseMe, type Me } from '../lib/dashboard/onboarding-contracts'

// Quem está logado (ADR-093): decide o que a tela oferece — "Clientes" só ao
// dono da plataforma; formulários de escrita só a ADMIN. É conveniência de
// interface: o servidor continua sendo quem autoriza (403).
//
// Enquanto carrega ou se falhar, `me` fica `null` e a tela segue no modo mais
// restrito (sem "Clientes"), nunca no mais permissivo.
interface MeContextValue {
  me: Me | null
  loading: boolean
}

const MeContext = createContext<MeContextValue>({ me: null, loading: false })

export function MeProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const response = await fetchMe()
        if (!response.ok) return
        const parsed = parseMe(await response.json())
        if (!cancelled) setMe(parsed)
      } catch {
        // sem "quem sou eu": modo restrito
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const value = useMemo(() => ({ me, loading }), [me, loading])
  return <MeContext.Provider value={value}>{children}</MeContext.Provider>
}

export function useMe(): MeContextValue {
  return useContext(MeContext)
}
