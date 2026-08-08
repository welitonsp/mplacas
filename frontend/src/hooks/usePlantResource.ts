import { useCallback, useEffect, useRef, useState } from 'react'

// Hook genérico de leitura de um recurso dependente da usina ativa
// (`/energy/*`, `/photovoltaic/summary`, `/reports/monthly/history`, etc.).
// `DashboardPage` hoje repete manualmente o mesmo padrão (estado + `useEffect`
// + `useCallback`) uma vez por endpoint — este hook extrai esse padrão com
// duas proteções que o código atual não tem: nenhuma "fresca" de usina
// anterior vaza para a usina nova (nem por um frame) e uma resposta atrasada
// de uma requisição já superada nunca sobrescreve um estado mais novo.

export type ResourceStatus = 'idle' | 'loading' | 'success' | 'error'

export type ResourceFailure =
  | { kind: 'http'; status: number }
  | { kind: 'network'; cause: unknown }
  | { kind: 'contract'; cause: unknown } // o `parse` (ou o `.json()` da resposta) lançou

export interface PlantResource<T, E = string> {
  data: T | null
  status: ResourceStatus
  error: E | null
  lastUpdated: Date | null
  refetch: () => void
}

type PlantResourceOptions<T, E> = {
  plantId: string | null
  fetcher: (plantId: string) => Promise<Response>
  parse: (payload: unknown) => T
} & (
  | { errorMessage: string; classifyError?: never }
  | { classifyError: (failure: ResourceFailure) => E | null; errorMessage?: never }
)

// Guarda de tipo explícita para distinguir os dois ramos da união acima —
// mais confiável do que depender de estreitamento automático do TypeScript
// sobre uma propriedade opcional dentro de um tipo genérico (`T`/`E`), que
// nem sempre estreita de forma previsível.
function hasClassifyError<T, E>(
  options: PlantResourceOptions<T, E>
): options is PlantResourceOptions<T, E> & { classifyError: (failure: ResourceFailure) => E | null } {
  return typeof (options as { classifyError?: unknown }).classifyError === 'function'
}

// O estado interno guarda a que `plantId` ele pertence — é o que permite ao
// hook nunca expor dado da usina anterior sob a usina nova (ver a derivação
// no final do hook). `status`/`error`/`lastUpdated` aqui são o resultado bruto
// da última requisição concluída para `plantId`; a leitura pública (retorno
// do hook) sempre compara este campo com o `plantId` atual do parâmetro antes
// de expor qualquer coisa.
interface InternalState<T, E> {
  plantId: string | null
  data: T | null
  status: ResourceStatus
  error: E | null
  lastUpdated: Date | null
}

function createInitialState<T, E>(): InternalState<T, E> {
  return { plantId: null, data: null, status: 'idle', error: null, lastUpdated: null }
}

export function usePlantResource<T, E = string>(
  options: PlantResourceOptions<T, E>
): PlantResource<T, E> {
  const { plantId } = options

  // Padrão "latest ref": `fetcher`/`parse`/`classifyError`/`errorMessage` NÃO
  // entram nas deps do `useEffect` abaixo. Em quase todo call site esse
  // objeto de opções é literal inline, então muda de identidade a cada
  // render — colocá-lo (ou qualquer um de seus campos de função) nas deps
  // dispararia o efeito a cada render e criaria um loop de novas requisições.
  // O efeito só reage a `plantId`/`nonce`; para tudo o mais, ele lê sempre o
  // valor mais recente através deste ref, atualizado a cada render (fora do
  // efeito, portanto sem esperar o próximo agendamento).
  const optionsRef = useRef(options)
  optionsRef.current = options

  const [state, setState] = useState<InternalState<T, E>>(createInitialState)
  // Incrementado por `refetch()` só para forçar o efeito abaixo a rodar de
  // novo com a mesma usina — o valor em si não é lido em nenhum outro lugar.
  const [nonce, setNonce] = useState(0)

  // Guarda de época: cada execução do efeito recebe um id monotonicamente
  // crescente. Depois de cada `await`, `isStale()` confirma que nenhuma
  // execução mais nova (troca de `plantId`/`nonce`, ou desmontagem) começou
  // enquanto esperávamos — se começou, esta resposta é descartada sem tocar
  // no estado. Cobre tanto "usina trocou no meio do caminho" quanto "duas
  // requisições da mesma usina em voo ao mesmo tempo" (refetch disparado
  // antes da anterior terminar).
  const requestRef = useRef(0)

  useEffect(() => {
    const requestId = ++requestRef.current
    const isStale = () => requestId !== requestRef.current

    if (plantId == null) {
      // Nenhuma chamada de rede quando não há usina — a leitura pública já
      // força `status: 'idle'`/`data: null` neste caso (ver derivação no
      // final do hook), então não há nada para gravar aqui além de encerrar
      // qualquer requisição anterior ainda em voo.
      return () => {
        requestRef.current += 1
      }
    }

    const currentPlantId = plantId

    // Dispara o "loading" de forma síncrona, antes de qualquer `await`: numa
    // troca de usina, zera `data`/`lastUpdated` imediatamente (a usina
    // anterior nunca aparece sob a nova, nem por um frame); num refetch da
    // MESMA usina, preserva `data`/`lastUpdated` anteriores enquanto a nova
    // requisição está em voo (item 5 do plano) — só `status` muda para
    // 'loading' e o erro anterior é limpo.
    setState((prev) => ({
      plantId: currentPlantId,
      data: prev.plantId === currentPlantId ? prev.data : null,
      status: 'loading',
      error: null,
      lastUpdated: prev.plantId === currentPlantId ? prev.lastUpdated : null,
    }))

    function writeFailure(failure: ResourceFailure): void {
      if (isStale()) return
      const opts = optionsRef.current
      if (hasClassifyError(opts)) {
        const classified = opts.classifyError(failure)
        // `null` = falha silenciosa (ex.: 401 — `apiFetch` já tentou refresh
        // e o usuário está sendo deslogado). Não escreve estado nenhum: o
        // hook permanece em `status: 'loading'`.
        if (classified === null) return
        setState({ plantId: currentPlantId, data: null, status: 'error', error: classified, lastUpdated: null })
        return
      }
      // `errorMessage` fixo: a falha completa (com `cause`/`status`) vai para
      // o console — nunca para a tela, mesma política de `ErrorBoundary.tsx`.
      // eslint-disable-next-line no-console
      console.error('usePlantResource: falha ao buscar recurso da usina', currentPlantId, failure)
      setState({
        plantId: currentPlantId,
        data: null,
        status: 'error',
        error: opts.errorMessage as E,
        lastUpdated: null,
      })
    }

    void (async () => {
      let response: Response
      try {
        response = await optionsRef.current.fetcher(currentPlantId)
      } catch (err) {
        if (isStale()) return
        writeFailure({ kind: 'network', cause: err })
        return
      }
      if (isStale()) return

      if (!response.ok) {
        writeFailure({ kind: 'http', status: response.status })
        return
      }

      let payload: unknown
      try {
        payload = await response.json()
      } catch (err) {
        if (isStale()) return
        writeFailure({ kind: 'contract', cause: err })
        return
      }
      if (isStale()) return

      let data: T
      try {
        data = optionsRef.current.parse(payload)
      } catch (err) {
        if (isStale()) return
        writeFailure({ kind: 'contract', cause: err })
        return
      }
      if (isStale()) return

      setState({ plantId: currentPlantId, data, status: 'success', error: null, lastUpdated: new Date() })
    })()

    return () => {
      requestRef.current += 1
    }
  }, [plantId, nonce])

  const refetch = useCallback(() => {
    setNonce((n) => n + 1)
  }, [])

  // Deriva o retorno público comparando o `plantId` a que o estado interno
  // pertence com o `plantId` atual do parâmetro — nunca o estado bruto
  // diretamente. Isso garante que dado da usina anterior nunca é exposto sob
  // a usina nova: mesmo antes do efeito acima rodar (primeiro render após a
  // troca), `current` já é `false` e a leitura pública já reflete
  // `status: 'loading'`/`data: null`.
  const current = state.plantId === plantId
  return {
    data: current ? state.data : null,
    status: plantId == null ? 'idle' : current ? state.status : 'loading',
    error: current ? state.error : null,
    lastUpdated: current ? state.lastUpdated : null,
    refetch,
  }
}
