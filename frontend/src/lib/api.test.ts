import { afterEach, describe, expect, it, vi } from 'vitest'
import { API_URL } from '../env'
import { DATA_TIMEOUT_MS, RequestTimeoutError, apiFetch, configureApi, downloadMonthlyReportExport, fetchMonthlyReportExport, fetchPlants, withTimeout } from './api'
import { TokenStore } from './auth'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// jsdom não implementa `URL.createObjectURL`/`revokeObjectURL` (ver
// `frontend/src/lib/api.ts::downloadMonthlyReportExport`) — este stub some no
// `afterEach` de cada describe abaixo, para não vazar entre testes de outros
// arquivos que rodem no mesmo worker.
function stubObjectUrl() {
  const createObjectURL = vi.fn(() => 'blob:mock-url')
  const revokeObjectURL = vi.fn()
  Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true, writable: true })
  Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true, writable: true })
  return { createObjectURL, revokeObjectURL }
}

function clearObjectUrlStub() {
  delete (URL as unknown as { createObjectURL?: unknown }).createObjectURL
  delete (URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL
}

describe('fetchPlants', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    TokenStore.clear()
  })

  it('chama GET /plants e devolve os itens já parseados', async () => {
    TokenStore.set('token-abc')
    const payload = {
      count: 2,
      items: [
        { id: '11111111-1111-1111-1111-111111111111', name: 'Matriz — Telhado A', installed_power_kwp: '48.600' },
        { id: '22222222-2222-2222-2222-222222222222', name: 'Filial Norte', installed_power_kwp: null },
      ],
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(payload))

    const plants = await fetchPlants()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_URL}/plants`)
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer token-abc')

    expect(plants).toEqual([
      { id: '11111111-1111-1111-1111-111111111111', name: 'Matriz — Telhado A', installedPowerKwp: '48.600' },
      { id: '22222222-2222-2222-2222-222222222222', name: 'Filial Norte', installedPowerKwp: null },
    ])
  })

  it('lança erro quando a resposta não é 200', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ detail: 'nope' }, 500))

    await expect(fetchPlants()).rejects.toThrow('Erro ao buscar usinas (500).')
  })

  it('lança erro quando o payload vem malformado', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ count: 1, items: [{ id: 'x' }] }))

    await expect(fetchPlants()).rejects.toThrow(/Resposta inválida da API/)
  })
})

describe('fetchMonthlyReportExport', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    TokenStore.clear()
  })

  it('busca o formato pedido com plant_id na query string, sem os parâmetros deprecated', async () => {
    TokenStore.set('token-abc')
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(new Blob(['a,b\n1,2']), { status: 200 }))

    await fetchMonthlyReportExport('plant-1', 'csv')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_URL}/reports/monthly/latest.csv?plant_id=plant-1`)
    expect(url).not.toContain('expected_production_kwh')
    expect(url).not.toContain('stable_tolerance_percent')
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer token-abc')
  })
})

describe('downloadMonthlyReportExport', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    clearObjectUrlStub()
    TokenStore.clear()
  })

  it('baixa o blob, dispara o clique via <a> temporário com o nome do Content-Disposition, e revoga o object URL depois', async () => {
    const { createObjectURL, revokeObjectURL } = stubObjectUrl()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const appendSpy = vi.spyOn(document.body, 'appendChild')
    const blob = new Blob(['pdf-bytes'], { type: 'application/pdf' })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(blob, {
        status: 200,
        headers: { 'Content-Disposition': 'attachment; filename="mplacas-monthly-2026-07-plant-1.pdf"' },
      })
    )

    await downloadMonthlyReportExport('plant-1', 'pdf')

    expect(createObjectURL).toHaveBeenCalledTimes(1)
    const appendedLink = appendSpy.mock.calls[0]?.[0] as HTMLAnchorElement
    expect(appendedLink.tagName).toBe('A')
    expect(appendedLink.download).toBe('mplacas-monthly-2026-07-plant-1.pdf')
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1)
    // Revogado depois do clique — prova de que a memória do object URL não vaza.
    expect(revokeObjectURL).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith(createObjectURL.mock.results[0]?.value)
  })

  it('usa um nome de arquivo determinístico quando a resposta não traz Content-Disposition', async () => {
    stubObjectUrl()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const appendSpy = vi.spyOn(document.body, 'appendChild')
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(new Blob(['x']), { status: 200 }))

    await downloadMonthlyReportExport('plant-1', 'xlsx')

    const appendedLink = appendSpy.mock.calls[0]?.[0] as HTMLAnchorElement
    expect(appendedLink.download).toMatch(/^mplacas-monthly-plant-1-\d{4}-\d{2}-\d{2}\.xlsx$/)
  })

  it('revoga o object URL mesmo que o clique de download lance uma exceção', async () => {
    const { createObjectURL, revokeObjectURL } = stubObjectUrl()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {
      throw new Error('boom')
    })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(new Blob(['x']), { status: 200 }))

    await expect(downloadMonthlyReportExport('plant-1', 'csv')).rejects.toThrow('boom')

    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledTimes(1)
  })

  it('lança erro genérico com o status quando o backend não consegue gerar o relatório', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 500 }))

    await expect(downloadMonthlyReportExport('plant-1', 'csv')).rejects.toThrow(
      'Não foi possível gerar o relatório (500).'
    )
  })

  it('lança mensagem específica quando não há ciclo de faturamento fechado (404)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 404 }))

    await expect(downloadMonthlyReportExport('plant-1', 'csv')).rejects.toThrow(
      'Nenhum ciclo de faturamento fechado disponível para exportar ainda.'
    )
  })

  it('cai no nome determinístico quando o Content-Disposition traz travessia de diretório (../..)', async () => {
    stubObjectUrl()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const appendSpy = vi.spyOn(document.body, 'appendChild')
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob(['x']), {
        status: 200,
        headers: { 'Content-Disposition': 'attachment; filename="../../etc/passwd"' },
      })
    )

    await downloadMonthlyReportExport('plant-1', 'csv')

    const appendedLink = appendSpy.mock.calls[0]?.[0] as HTMLAnchorElement
    expect(appendedLink.download).not.toContain('..')
    expect(appendedLink.download).not.toContain('/')
    expect(appendedLink.download).toMatch(/^mplacas-monthly-plant-1-\d{4}-\d{2}-\d{2}\.csv$/)
  })

  it('cai no nome determinístico quando o Content-Disposition traz caractere de controle', async () => {
    stubObjectUrl()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const appendSpy = vi.spyOn(document.body, 'appendChild')
    const dirtyFilename = `relatorio${String.fromCharCode(7)}.csv`
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob(['x']), {
        status: 200,
        headers: { 'Content-Disposition': `attachment; filename="${dirtyFilename}"` },
      })
    )

    await downloadMonthlyReportExport('plant-1', 'csv')

    const appendedLink = appendSpy.mock.calls[0]?.[0] as HTMLAnchorElement
    expect(appendedLink.download).not.toBe(dirtyFilename)
    expect(appendedLink.download).toMatch(/^mplacas-monthly-plant-1-\d{4}-\d{2}-\d{2}\.csv$/)
  })

  it('cai no nome determinístico quando o Content-Disposition traz um override de direção Unicode (RLO)', async () => {
    stubObjectUrl()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const appendSpy = vi.spyOn(document.body, 'appendChild')
    // U+202E (RIGHT-TO-LEFT OVERRIDE): vetor clássico de spoofing de extensão —
    // "relatorio<RLO>fdp.exe" pode ser renderizado como "relatorio.exe.pdf".
    // A `Headers` real do fetch rejeita esse code point ao construir a
    // resposta (ByteString-only), então a resposta é simulada com um objeto
    // mínimo compatível com a interface que `downloadMonthlyReportExport`
    // realmente usa (`.ok`, `.status`, `.headers.get`, `.blob`).
    const spoofedFilename = `relatorio${String.fromCharCode(0x202e)}fdp.exe`
    const fakeResponse = {
      ok: true,
      status: 200,
      headers: {
        get: (name: string) =>
          name === 'Content-Disposition' ? `attachment; filename="${spoofedFilename}"` : null,
      },
      blob: async () => new Blob(['x']),
    } as unknown as Response
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(fakeResponse)

    await downloadMonthlyReportExport('plant-1', 'csv')

    const appendedLink = appendSpy.mock.calls[0]?.[0] as HTMLAnchorElement
    expect(appendedLink.download).not.toBe(spoofedFilename)
    expect(appendedLink.download).not.toContain(String.fromCharCode(0x202e))
    expect(appendedLink.download).toMatch(/^mplacas-monthly-plant-1-\d{4}-\d{2}-\d{2}\.csv$/)
  })

  it('cai no nome determinístico quando o Content-Disposition traz extensão dupla divergente do formato pedido', async () => {
    stubObjectUrl()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const appendSpy = vi.spyOn(document.body, 'appendChild')
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob(['x']), {
        status: 200,
        headers: { 'Content-Disposition': 'attachment; filename="fatura.csv.exe"' },
      })
    )

    // Formato pedido é csv, mas o nome do header termina em .exe.
    await downloadMonthlyReportExport('plant-1', 'csv')

    const appendedLink = appendSpy.mock.calls[0]?.[0] as HTMLAnchorElement
    expect(appendedLink.download).not.toBe('fatura.csv.exe')
    expect(appendedLink.download).toMatch(/^mplacas-monthly-plant-1-\d{4}-\d{2}-\d{2}\.csv$/)
  })

  it('aceita o nome do Content-Disposition quando a extensão bate com o formato pedido', async () => {
    stubObjectUrl()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const appendSpy = vi.spyOn(document.body, 'appendChild')
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob(['x']), {
        status: 200,
        headers: { 'Content-Disposition': 'attachment; filename="fatura-2026-07.pdf"' },
      })
    )

    await downloadMonthlyReportExport('plant-1', 'pdf')

    const appendedLink = appendSpy.mock.calls[0]?.[0] as HTMLAnchorElement
    expect(appendedLink.download).toBe('fatura-2026-07.pdf')
  })

  it('cai no nome determinístico quando o Content-Disposition traz apenas "."', async () => {
    stubObjectUrl()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const appendSpy = vi.spyOn(document.body, 'appendChild')
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob(['x']), {
        status: 200,
        headers: { 'Content-Disposition': 'attachment; filename="."' },
      })
    )

    await downloadMonthlyReportExport('plant-1', 'csv')

    const appendedLink = appendSpy.mock.calls[0]?.[0] as HTMLAnchorElement
    expect(appendedLink.download).toMatch(/^mplacas-monthly-plant-1-\d{4}-\d{2}-\d{2}\.csv$/)
  })
})

// A-02 da auditoria v6 (S1). O backend rotaciona o refresh token e revoga a
// FAMÍLIA inteira ao detectar reutilização de um token já consumido
// (`src/mplacas/auth/session_service.py::_handle_failed_rotation`). Antes do
// single-flight, cada 401 disparava seu próprio refresh: duas requisições
// concorrentes apresentavam o mesmo refresh token, a segunda caía como
// reutilização, e o usuário era deslogado pelo controle de segurança
// funcionando como projetado.
describe('apiFetch — renovação single-flight (A-02)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    TokenStore.clear()
    configureApi(() => null, () => {}, () => {})
  })

  it('duas requisições com 401 simultâneo usam UMA única renovação', async () => {
    TokenStore.set('token-velho')
    const setRefresh = vi.fn()
    const logout = vi.fn()
    configureApi(() => 'refresh-1', setRefresh, logout)

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/auth/refresh')) {
        return jsonResponse({ access_token: 'token-novo', refresh_token: 'refresh-2' })
      }
      // A primeira tentativa de cada recurso expira; a repetição usa o token
      // renovado e passa.
      const auth = 'token-novo'
      return TokenStore.get() === auth
        ? jsonResponse({ ok: true })
        : new Response('', { status: 401 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const [a, b] = await Promise.all([apiFetch('/recurso-a'), apiFetch('/recurso-b')])

    expect(a.status).toBe(200)
    expect(b.status).toBe(200)
    // O ponto do teste: uma renovação só. Sem single-flight seriam duas, e a
    // segunda apresentaria um refresh token já consumido.
    const refreshCalls = fetchMock.mock.calls.filter(([input]) => String(input).endsWith('/auth/refresh'))
    expect(refreshCalls).toHaveLength(1)
    expect(setRefresh).toHaveBeenCalledTimes(1)
    expect(logout).not.toHaveBeenCalled()
  })

  it('renovação rejeitada desloga e não deixa promessa presa para a próxima chamada', async () => {
    TokenStore.set('token-velho')
    const logout = vi.fn()
    configureApi(() => 'refresh-invalido', () => {}, logout)

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/auth/refresh')) return new Response('', { status: 401 })
      return new Response('', { status: 401 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const first = await apiFetch('/recurso')
    expect(first.status).toBe(401)
    expect(logout).toHaveBeenCalled()

    // Segunda chamada precisa tentar renovar de novo: se a promessa em voo
    // ficasse em cache, toda requisição seguinte herdaria a falha antiga sem
    // nunca mais tentar.
    const antes = fetchMock.mock.calls.filter(([i]) => String(i).endsWith('/auth/refresh')).length
    await apiFetch('/outro-recurso')
    const depois = fetchMock.mock.calls.filter(([i]) => String(i).endsWith('/auth/refresh')).length
    expect(depois).toBe(antes + 1)
  })

  it('resposta 200 malformada não grava token inválido e trata como falha', async () => {
    TokenStore.set('token-velho')
    const setRefresh = vi.fn()
    const logout = vi.fn()
    configureApi(() => 'refresh-1', setRefresh, logout)

    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      // 200, mas sem os campos do contrato — uma asserção de tipo não existe
      // em runtime e gravaria `undefined` no TokenStore.
      if (url.endsWith('/auth/refresh')) return jsonResponse({ token: 'formato-errado' })
      return new Response('', { status: 401 })
    }))

    const response = await apiFetch('/recurso')

    expect(response.status).toBe(401)
    expect(setRefresh).not.toHaveBeenCalled()
    expect(logout).toHaveBeenCalled()
    expect(TokenStore.get()).toBe('token-velho')
  })
})

// A-03 da auditoria v6: nenhuma chamada tinha prazo. `fetch` não expira
// sozinho, entao uma conexao que abre e nunca responde deixava a interface em
// "carregando" para sempre — sem erro e sem saida.
describe('withTimeout / apiFetch — prazo e cancelamento (A-03)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
    TokenStore.clear()
    configureApi(() => null, () => {}, () => {})
  })

  it('aborta e sinaliza prazo esgotado quando o servidor nao responde', async () => {
    vi.useFakeTimers()
    const deadline = withTimeout(1000)

    expect(deadline.signal.aborted).toBe(false)
    expect(deadline.timedOut()).toBe(false)

    vi.advanceTimersByTime(1000)

    expect(deadline.signal.aborted).toBe(true)
    expect(deadline.timedOut()).toBe(true)
    deadline.clear()
  })

  // A distincao que a auditoria pediu: prazo esgotado e cancelamento do usuario
  // exigem tratamento diferente na interface — o primeiro merece mensagem e
  // nova tentativa, o segundo e silencioso porque a tela ja saiu.
  it('cancelamento externo aborta sem marcar como prazo esgotado', () => {
    const external = new AbortController()
    const deadline = withTimeout(60_000, external.signal)

    external.abort()

    expect(deadline.signal.aborted).toBe(true)
    expect(deadline.timedOut()).toBe(false)
    deadline.clear()
  })

  it('sinal externo ja abortado antes da chamada aborta imediatamente', () => {
    const external = new AbortController()
    external.abort()

    const deadline = withTimeout(60_000, external.signal)

    expect(deadline.signal.aborted).toBe(true)
    deadline.clear()
  })

  it('apiFetch converte prazo esgotado em RequestTimeoutError', async () => {
    TokenStore.set('token')
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
      // Simula servidor que nunca responde: so rejeita quando o sinal aborta.
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () =>
          reject(new DOMException('Aborted', 'AbortError'))
        )
      })
    ))

    vi.useFakeTimers()
    const pending = apiFetch('/lento')
    const assertion = expect(pending).rejects.toBeInstanceOf(RequestTimeoutError)
    await vi.advanceTimersByTimeAsync(DATA_TIMEOUT_MS)
    await assertion
  })
})
