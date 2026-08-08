import { describe, expect, it, vi, afterEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { usePlantResource, type ResourceFailure } from './usePlantResource'

// Nenhum `PlantProvider` em nenhum teste deste arquivo — `usePlantResource`
// recebe `plantId` como parâmetro explícito exatamente para permitir isso
// (ver comentário no hook).

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// Promise controlável de fora — usada nos testes de corrida (g)/(h) e no
// teste de desmontagem (j), onde a ordem de resolução importa.
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('usePlantResource', () => {
  // (a) sucesso
  it('sucesso: status success, data e lastUpdated preenchidos', async () => {
    const fetcher = vi.fn(async (plantId: string) => jsonResponse({ value: 42, plantId }))
    const parse = (payload: unknown) => (payload as { value: number }).value

    const { result } = renderHook(() =>
      usePlantResource({ plantId: 'p1', fetcher, parse, errorMessage: 'Erro genérico.' })
    )

    expect(result.current.status).toBe('loading')

    await waitFor(() => expect(result.current.status).toBe('success'))
    expect(result.current.data).toBe(42)
    expect(result.current.lastUpdated).toBeInstanceOf(Date)
    expect(result.current.error).toBeNull()
    expect(fetcher).toHaveBeenCalledWith('p1')
  })

  // (b) plantId null
  it('plantId null: status idle, nenhuma chamada ao fetcher', async () => {
    const fetcher = vi.fn(async () => jsonResponse({}))
    const parse = (payload: unknown) => payload

    const { result } = renderHook(() =>
      usePlantResource({ plantId: null, fetcher, parse, errorMessage: 'Erro genérico.' })
    )

    // Sincronamente já idle — não depende de nenhum efeito rodar.
    expect(result.current.status).toBe('idle')
    expect(result.current.data).toBeNull()

    // Dá uma volta de microtasks para garantir que nada dispara depois.
    await act(async () => {
      await Promise.resolve()
    })
    expect(fetcher).not.toHaveBeenCalled()
    expect(result.current.status).toBe('idle')
  })

  // (c) HTTP 401 com classifyError retornando null
  it('401 com classifyError retornando null permanece loading, data intacto, sem console.error', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const fetcher = vi.fn(async () => jsonResponse({}, 401))
    const classifyError = vi.fn((_failure: ResourceFailure) => null)
    const parse = (payload: unknown) => payload

    const { result } = renderHook(() =>
      usePlantResource({ plantId: 'p1', fetcher, parse, classifyError })
    )

    await waitFor(() => expect(classifyError).toHaveBeenCalled())
    // Mais uma volta de microtasks depois do classifyError já ter sido
    // chamado, para garantir que nenhum setState tardio ainda estava a
    // caminho.
    await act(async () => {
      await Promise.resolve()
    })

    expect(result.current.status).toBe('loading')
    expect(result.current.data).toBeNull()
    expect(result.current.error).toBeNull()
    expect(consoleErrorSpy).not.toHaveBeenCalled()
  })

  // (d) HTTP 404 com classifyError retornando um valor
  it('404 com classifyError retornando NOT_FOUND vira status error com esse valor', async () => {
    const fetcher = vi.fn(async () => jsonResponse({}, 404))
    const classifyError = vi.fn((failure: ResourceFailure) =>
      failure.kind === 'http' && failure.status === 404 ? 'NOT_FOUND' : null
    )
    const parse = (payload: unknown) => payload

    const { result } = renderHook(() =>
      usePlantResource({ plantId: 'p1', fetcher, parse, classifyError })
    )

    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toBe('NOT_FOUND')
    expect(classifyError).toHaveBeenCalledWith({ kind: 'http', status: 404 })
  })

  // (e) falha de rede
  it('falha de rede (fetcher rejeita) é classificada como {kind: network}', async () => {
    const networkError = new Error('fetch failed')
    const fetcher = vi.fn(async () => {
      throw networkError
    })
    const classifyError = vi.fn((failure: ResourceFailure) =>
      failure.kind === 'network' ? 'NETWORK_ERROR' : 'OTHER'
    )
    const parse = (payload: unknown) => payload

    const { result } = renderHook(() =>
      usePlantResource({ plantId: 'p1', fetcher, parse, classifyError })
    )

    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(classifyError).toHaveBeenCalledWith({ kind: 'network', cause: networkError })
    expect(result.current.error).toBe('NETWORK_ERROR')
  })

  // (f) parse lança
  it('parse lançando gera status error com a errorMessage FIXA, nunca a mensagem original', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const fetcher = vi.fn(async () => jsonResponse({ bad: true }))
    const parse = vi.fn(() => {
      throw new Error('mensagem interna que não deve vazar para a UI')
    })

    const { result } = renderHook(() =>
      usePlantResource({ plantId: 'p1', fetcher, parse, errorMessage: 'Erro fixo de teste.' })
    )

    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toBe('Erro fixo de teste.')
    expect(result.current.error).not.toContain('mensagem interna')
    // A falha completa (com a causa original) foi para o console, nunca para a UI.
    expect(consoleErrorSpy).toHaveBeenCalled()
  })

  // (g) corrida: A resolve devagar, B resolve rápido — data final é o de B,
  // mesmo quando A chega tarde depois.
  it('corrida A→B: resposta tardia de A não sobrescreve o dado de B já carregado', async () => {
    const pendingByPlant: Record<string, ReturnType<typeof deferred<Response>>> = {
      A: deferred<Response>(),
      B: deferred<Response>(),
    }
    const fetcher = vi.fn((plantId: string) => pendingByPlant[plantId].promise)
    const parse = (payload: unknown) => payload as { value: string }

    const { result, rerender } = renderHook(
      ({ plantId }) => usePlantResource({ plantId, fetcher, parse, errorMessage: 'Erro genérico.' }),
      { initialProps: { plantId: 'A' } }
    )

    await waitFor(() => expect(fetcher).toHaveBeenCalledWith('A'))

    rerender({ plantId: 'B' })
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith('B'))

    // B (rápida) resolve primeiro.
    await act(async () => {
      pendingByPlant.B.resolve(jsonResponse({ value: 'B' }))
    })
    await waitFor(() => expect(result.current.data).toEqual({ value: 'B' }))
    expect(result.current.status).toBe('success')

    // A (lenta) resolve depois — não pode sobrescrever o dado de B.
    await act(async () => {
      pendingByPlant.A.resolve(jsonResponse({ value: 'A' }))
      // Dá tempo real para qualquer continuação (incorreta) da promise de A
      // processar e tentar escrever estado, se a proteção de corrida não
      // existisse.
      await new Promise((r) => setTimeout(r, 50))
    })

    expect(result.current.data).toEqual({ value: 'B' })
    expect(result.current.status).toBe('success')
  })

  // (h) durante a troca A→B, antes de B responder, o hook nunca expõe o
  // dado de A — checado em renders intermediários, não só no final.
  it('durante a troca de usina, nunca expõe o dado da usina anterior antes da nova responder', async () => {
    const pendingByPlant: Record<string, ReturnType<typeof deferred<Response>>> = {
      A: deferred<Response>(),
      B: deferred<Response>(),
    }
    const fetcher = vi.fn((plantId: string) => pendingByPlant[plantId].promise)
    const parse = (payload: unknown) => payload as { value: string }

    const { result, rerender } = renderHook(
      ({ plantId }) => usePlantResource({ plantId, fetcher, parse, errorMessage: 'Erro genérico.' }),
      { initialProps: { plantId: 'A' } }
    )

    await act(async () => {
      pendingByPlant.A.resolve(jsonResponse({ value: 'A' }))
    })
    await waitFor(() => expect(result.current.data).toEqual({ value: 'A' }))

    // Troca para B — checagem IMEDIATA (mesmo passe síncrono), antes de B
    // sequer ter respondido: o dado de A não pode continuar visível.
    rerender({ plantId: 'B' })
    expect(result.current.data).toBeNull()
    expect(result.current.status).toBe('loading')

    // Ainda esperando B, uma volta de microtasks depois — continua sem o
    // dado de A.
    await act(async () => {
      await Promise.resolve()
    })
    expect(result.current.data).toBeNull()
    expect(result.current.status).toBe('loading')

    // B finalmente responde.
    await act(async () => {
      pendingByPlant.B.resolve(jsonResponse({ value: 'B' }))
    })
    await waitFor(() => expect(result.current.data).toEqual({ value: 'B' }))
  })

  // (i) refetch da mesma usina preserva data anterior
  it('refetch da mesma usina preserva data anterior enquanto status volta a loading', async () => {
    let call = 0
    const fetcher = vi.fn(async () => {
      call += 1
      return jsonResponse({ value: call })
    })
    const parse = (payload: unknown) => (payload as { value: number }).value

    const { result } = renderHook(() =>
      usePlantResource({ plantId: 'p1', fetcher, parse, errorMessage: 'Erro genérico.' })
    )

    await waitFor(() => expect(result.current.status).toBe('success'))
    expect(result.current.data).toBe(1)

    act(() => {
      result.current.refetch()
    })

    // Logo depois do refetch, ainda no mesmo passe síncrono: volta a
    // 'loading' mas o dado anterior não é zerado.
    expect(result.current.status).toBe('loading')
    expect(result.current.data).toBe(1)

    await waitFor(() => expect(result.current.data).toBe(2))
    expect(result.current.status).toBe('success')
  })

  // (j) desmontar em voo
  it('desmontar enquanto uma requisição está em voo não causa act() warning nem escreve estado após desmontagem', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const pending = deferred<Response>()
    const fetcher = vi.fn(() => pending.promise)
    const parse = (payload: unknown) => payload

    const { unmount } = renderHook(() =>
      usePlantResource({ plantId: 'p1', fetcher, parse, errorMessage: 'Erro genérico.' })
    )

    unmount()

    await act(async () => {
      pending.resolve(jsonResponse({ ok: true }))
      await pending.promise
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(consoleErrorSpy).not.toHaveBeenCalled()
  })
})
