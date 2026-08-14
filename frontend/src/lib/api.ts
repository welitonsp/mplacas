import { API_URL } from '../env'
import { TokenStore } from './auth'
import { parsePlantsResponse, type Plant } from './dashboard/plant-contracts'

// Timeout de rede (auditoria v6, achado A-03). Nenhuma chamada tinha limite:
// uma conexão que abre e nunca responde — rede móvel instável, captive portal,
// balanceador que engole a requisição — deixava a interface em "carregando"
// para sempre, sem erro e sem saída. `fetch` não expira sozinho.
//
// Dois valores porque as operações não têm o mesmo perfil: autenticação é
// interativa e o usuário está olhando; leitura de dados pode legitimamente
// demorar mais (relatório, janela de 90 dias). Ambos generosos o bastante para
// não cortar requisição sadia em rede ruim.
export const AUTH_TIMEOUT_MS = 15_000
export const DATA_TIMEOUT_MS = 30_000

// Combina o prazo interno com um `AbortController` externo, quando o chamador
// tiver um (desmontagem de componente, troca de usina). Cancelar por qualquer
// um dos dois motivos aborta a requisição; o `clear` devolvido evita que o
// timer sobreviva à resposta e dispare um abort tardio sobre nada.
export function withTimeout(
  timeoutMs: number,
  externalSignal?: AbortSignal | null
): { signal: AbortSignal; clear: () => void; timedOut: () => boolean } {
  const controller = new AbortController()
  let expired = false

  const timer = setTimeout(() => {
    expired = true
    controller.abort()
  }, timeoutMs)

  const forward = () => controller.abort()
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort()
    else externalSignal.addEventListener('abort', forward, { once: true })
  }

  return {
    signal: controller.signal,
    clear: () => {
      clearTimeout(timer)
      externalSignal?.removeEventListener('abort', forward)
    },
    timedOut: () => expired,
  }
}

// Erro distinto para o caso de prazo esgotado. A interface precisa poder
// diferenciar "servidor demorou demais" de "servidor recusou" e de "usuário
// saiu da tela" — as três situações pedem mensagens e ações diferentes, e
// tratar todas como falha genérica de rede foi o que a auditoria apontou.
export class RequestTimeoutError extends Error {
  constructor(path: string, timeoutMs: number) {
    super(`A requisição para ${path} excedeu ${timeoutMs}ms.`)
    this.name = 'RequestTimeoutError'
  }
}

type RefreshTokenGetter = () => string | null
type RefreshTokenSetter = (token: string) => void
type LogoutFn = () => void

let _getRefreshToken: RefreshTokenGetter = () => null
let _setRefreshToken: RefreshTokenSetter = () => {}
let _logout: LogoutFn = () => {}

export function configureApi(
  getRefreshToken: RefreshTokenGetter,
  setRefreshToken: RefreshTokenSetter,
  logout: LogoutFn,
) {
  _getRefreshToken = getRefreshToken
  _setRefreshToken = setRefreshToken
  _logout = logout
}

// Renovação em voo, compartilhada por todas as requisições concorrentes
// (single-flight). Achado A-02 da auditoria de frontend v6, severidade S1.
//
// O backend ROTACIONA o refresh token a cada renovação e, ao detectar
// reutilização de um token já consumido, revoga a FAMÍLIA inteira de sessões
// (`src/mplacas/auth/session_service.py`, `_handle_failed_rotation`). Isso é
// política de segurança correta — o problema estava aqui.
//
// Antes desta correção cada requisição que recebia 401 disparava seu próprio
// refresh. Com duas chamadas em paralelo expirando juntas — situação normal nos
// módulos do painel, que buscam vários recursos ao mesmo tempo — a sequência
// era: ambas recebem 401, ambas renovam, a primeira consome e rotaciona o
// token, a segunda apresenta o token já consumido, o backend classifica como
// reutilização e derruba a família. O usuário era deslogado pelo controle de
// segurança funcionando exatamente como projetado.
//
// Agora a primeira requisição a precisar de renovação cria a promessa; as
// demais aguardam a MESMA promessa e reexecutam com o token que ela produziu.
// O refresh token é apresentado uma única vez por rotação.
let refreshInFlight: Promise<string | null> | null = null

async function performRefresh(): Promise<string | null> {
  const refreshToken = _getRefreshToken()
  if (!refreshToken) return null

  const deadline = withTimeout(AUTH_TIMEOUT_MS)
  let refreshResponse: Response
  try {
    refreshResponse = await fetch(`${API_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
      signal: deadline.signal,
    })
  } catch {
    // Timeout ou falha de rede na renovação: tratado como renovação falha, o
    // que leva a `_logout()` no chamador. Deixar a promessa pendurada aqui
    // travaria toda requisição que estivesse aguardando esta renovação.
    return null
  } finally {
    deadline.clear()
  }

  if (!refreshResponse.ok) return null

  const payload = (await refreshResponse.json()) as unknown
  // Validação em runtime: uma asserção de tipo não existe depois da
  // compilação, e uma resposta 200 malformada gravaria lixo no `TokenStore`,
  // deixando a sessão num estado pior que o 401 original.
  if (
    typeof payload !== 'object' ||
    payload === null ||
    typeof (payload as { access_token?: unknown }).access_token !== 'string' ||
    typeof (payload as { refresh_token?: unknown }).refresh_token !== 'string'
  ) {
    return null
  }

  const { access_token, refresh_token } = payload as {
    access_token: string
    refresh_token: string
  }
  TokenStore.set(access_token)
  _setRefreshToken(refresh_token)
  return access_token
}

// Devolve o novo token de acesso, ou `null` quando a renovação falhou. Uma
// única renovação roda por vez; chamadas concorrentes compartilham o resultado.
// O `finally` limpa a referência mesmo em caso de exceção — sem isso, uma falha
// de rede deixaria uma promessa rejeitada em cache e toda requisição seguinte
// herdaria esse erro para sempre.
function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight === null) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = TokenStore.get()
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  headers.set('Content-Type', 'application/json')

  // O prazo interno convive com o `signal` que o chamador tenha passado: quem
  // cancela por desmontagem de componente continua funcionando, e quem não
  // passa nada ganha o prazo mesmo assim.
  const deadline = withTimeout(DATA_TIMEOUT_MS, init.signal)
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers, signal: deadline.signal })
  } catch (error) {
    // Distingue prazo esgotado de cancelamento do usuário: a interface trata
    // os dois de forma diferente — o primeiro merece mensagem e nova
    // tentativa, o segundo é silencioso porque a tela já saiu.
    if (deadline.timedOut()) throw new RequestTimeoutError(path, DATA_TIMEOUT_MS)
    throw error
  } finally {
    deadline.clear()
  }

  if (response.status !== 401) return response

  const accessToken = await refreshAccessToken()
  if (accessToken === null) {
    _logout()
    return response
  }

  // Repete a chamada original com o token renovado.
  const retryHeaders = new Headers(init.headers)
  retryHeaders.set('Authorization', `Bearer ${accessToken}`)
  retryHeaders.set('Content-Type', 'application/json')
  const retryDeadline = withTimeout(DATA_TIMEOUT_MS, init.signal)
  try {
    return await fetch(`${API_URL}${path}`, {
      ...init,
      headers: retryHeaders,
      signal: retryDeadline.signal,
    })
  } catch (error) {
    if (retryDeadline.timedOut()) throw new RequestTimeoutError(path, DATA_TIMEOUT_MS)
    throw error
  } finally {
    retryDeadline.clear()
  }
}

// Dashboard executivo do ciclo de faturamento atual (`GET /energy/executive/latest`) —
// headline, status, indicadores e diagnósticos do ciclo em curso (ver `contracts.ts`,
// `parseExecutiveDashboard`).
export async function fetchExecutiveDashboard(plantId: string): Promise<Response> {
  return apiFetch(`/energy/executive/latest?plant_id=${encodeURIComponent(plantId)}`)
}

// Histórico de anomalias de produção diária (`GET /energy/anomalies/latest`).
// `expected_daily_production_kwh` saiu da query string: o backend marca o
// parâmetro `deprecated=True` e o ignora (ver `intelligence/router.py`) — o
// endpoint agora resolve a expectativa sozinho e devolve `200` sempre, com
// campos por dia `null` quando não há expectativa disponível (ver
// `AnomalyDailyPoint.level`/`expected_unavailable_reason`).
export async function fetchAnomalyHistory(plantId: string, days = 90): Promise<Response> {
  return apiFetch(`/energy/anomalies/latest?plant_id=${encodeURIComponent(plantId)}&days=${days}`)
}

// Leitura composta da modelagem fotovoltaica (performance + baseline sazonal +
// perdas) para uma usina, em uma única requisição (ver ADR-065, seção 4,
// `GET /photovoltaic/summary`). Sempre 200 quando a usina está no escopo do
// principal — blocos ausentes vêm como `null` acompanhados de um motivo, nunca
// como erro HTTP, então não há tratamento de status especial além do 401 já
// coberto por `apiFetch`.
export async function fetchPhotovoltaicSummary(plantId: string): Promise<Response> {
  return apiFetch(`/photovoltaic/summary?plant_id=${encodeURIComponent(plantId)}`)
}

// ROI/payback do investimento (ADR-067, `GET /energy/financial-return/latest`).
// Estritamente leitura; mesma convenção de sempre-200-dentro-do-escopo dos demais
// endpoints de `/energy/*` — indisponibilidade vem como campo no payload, não como
// status HTTP de erro (ver `financial-return-contracts.ts`).
export async function fetchFinancialReturn(plantId: string): Promise<Response> {
  return apiFetch(`/energy/financial-return/latest?plant_id=${encodeURIComponent(plantId)}`)
}

// Histórico de produção por ciclo de faturamento (`GET /reports/monthly/history`).
// Só devolve ciclos já fechados com fatura confirmada — nunca um ciclo "em curso" —
// e uma usina sem nenhum ciclo fechado recebe `200` com `cycles: []`, nunca 404.
// Mesma convenção de sempre-200-dentro-do-escopo das demais leituras deste arquivo.
export async function fetchMonthlyProductionHistory(
  plantId: string,
  limit = 12
): Promise<Response> {
  return apiFetch(
    `/reports/monthly/history?plant_id=${encodeURIComponent(plantId)}&limit=${limit}`
  )
}

// Estado operacional por inversor (device) da usina para o dia mais recente
// com qualquer `DailyEnergy` (ADR-074, Decisão 3, `GET /devices/daily-status`).
// Mesma convenção de sempre-200-dentro-do-escopo das demais leituras deste
// arquivo: um inversor sem comunicação nunca some da resposta — ele aparece
// com `reporting_status: "NOT_REPORTED"` — e a indisponibilidade de
// rendimento vem como campo + motivo, nunca como status HTTP de erro (ver
// `device-contracts.ts::parseDeviceDailyStatus`).
export async function fetchDeviceDailyStatus(plantId: string): Promise<Response> {
  return apiFetch(`/devices/daily-status?plant_id=${encodeURIComponent(plantId)}`)
}

// Explicação em linguagem natural do estado executivo do ciclo atual
// (`GET /energy/explanations/latest`, `explanations/router.py:27`, T4 do
// plano de auditoria 2026-08-12) — camada interpretativa OPCIONAL sobre os
// diagnósticos já calculados por `build_executive_dashboard` (mesma fonte de
// `DiagnosticsCard`). Nunca produz um número novo: o texto só nasce quando
// `explanation_api_url` está configurado (`explanations/router.py:36`) e,
// mesmo aí, cai para a mesma resposta determinística sempre que o provedor
// externo falhar (`explanations/service.py::explain_with_fallback`) — os
// dois casos voltam como `200` com `source: 'DETERMINISTIC'`, nunca erro.
// Buscado só sob demanda (ação explícita do usuário) — nunca no carregamento
// da página, ver `AiExplanationPanel`.
export async function fetchLatestExplanation(plantId: string): Promise<Response> {
  return apiFetch(`/energy/explanations/latest?plant_id=${encodeURIComponent(plantId)}`)
}

// Configuração financeira (CAPEX) da usina (ADR-067,
// `GET/PATCH /plants/{plant_id}/financial-configuration`). `GET` usa `ReadPlantPath`,
// `PATCH` usa `AdminPlantPath` — um chamador com credencial READ recebe 403 do
// backend no `PATCH`, que é a fronteira de autorização real (ver
// `plants/router.py::update_plant_financial_configuration`); o frontend hoje não tem
// mecanismo de distinção de papel para esconder a ação antes disso (ver
// `CapexRegistrationForm`).
export async function fetchFinancialConfiguration(plantId: string): Promise<Response> {
  return apiFetch(`/plants/${encodeURIComponent(plantId)}/financial-configuration`)
}

// Lista de usinas da organização do principal autenticado (ADR-069, seção 4,
// `GET /plants`) — base do seletor de usina (Etapa D) e do `PlantContext`
// (Etapa C), nenhum dos dois implementado ainda. Diferente das demais funções
// de fetch deste arquivo, já devolve os itens parseados em vez do `Response`
// cru: não há estado de indisponibilidade específico por campo a preservar
// aqui (como em `parsePhotovoltaicSummary`/`parseFinancialReturn`) — um payload
// malformado ou um status não-200 são sempre erro, nunca um estado de negócio
// a exibir.
export async function fetchPlants(): Promise<Plant[]> {
  const response = await apiFetch('/plants')
  if (!response.ok) {
    throw new Error(`Erro ao buscar usinas (${response.status}).`)
  }
  const parsed = parsePlantsResponse(await response.json())
  return parsed.items
}

export interface FinancialConfigurationUpdatePayload {
  investment_amount_brl?: string
  investment_recorded_on?: string | null
}

export async function updateFinancialConfiguration(
  plantId: string,
  payload: FinancialConfigurationUpdatePayload,
): Promise<Response> {
  return apiFetch(`/plants/${encodeURIComponent(plantId)}/financial-configuration`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

// Formatos servidos pelo caminho síncrono de exportação (T2, plano de
// auditoria 2026-08-12). O pipeline assíncrono (`POST /monthly/exports` +
// polling de `exports/{task_id}`) fica fora de escopo — ver
// `reports/router.py:202` em diante — só se justifica se o relatório demorar
// a ponto de estourar timeout, o que não foi observado.
export type MonthlyReportExportFormat = 'csv' | 'pdf' | 'xlsx'

// Relatório mensal do ciclo mais recente já fechado, num dos três formatos
// (`GET /reports/monthly/latest.csv|.pdf|.xlsx`, `reports/router.py:107,130,
// 153`). `expected_production_kwh`/`stable_tolerance_percent` são parâmetros
// legados marcados `deprecated=True` no backend (ignorados dentro de
// `_build_report`, `reports/router.py:45-50`) — nunca enviados aqui. Devolve
// o `Response` cru, como as demais funções deste arquivo: quem chama decide
// como tratar erro e como converter o corpo em blob para o download.
export async function fetchMonthlyReportExport(
  plantId: string,
  format: MonthlyReportExportFormat,
): Promise<Response> {
  return apiFetch(
    `/reports/monthly/latest.${format}?plant_id=${encodeURIComponent(plantId)}`
  )
}

// Nome de arquivo determinístico usado quando a resposta não traz
// `Content-Disposition` (ou traz um valor que não passa na sanitização
// abaixo). O backend sempre inclui o header (`_download_headers`,
// `reports/router.py:72-83`), mas em requisição cross-origin — como é o
// deploy real, frontend em `pages.dev` e API em `run.app` — o navegador só
// deixa o JS ler headers de resposta que estejam em `expose_headers` do
// `CORSMiddleware` (`main.py`). Este fallback é o caminho que roda sempre
// que essa configuração faltar, mudar, ou o header vier ausente/inválido por
// qualquer outro motivo — o download não pode travar nem sair sem nome.
function fallbackExportFilename(plantId: string, format: MonthlyReportExportFormat): string {
  const today = new Date().toISOString().slice(0, 10)
  return `mplacas-monthly-${plantId}-${today}.${format}`
}

const MAX_DOWNLOAD_FILENAME_LENGTH = 200

// U+202A–U+202E (embedding/override) e U+2066–U+2069 (isolate) são os
// controles de direcionalidade Unicode usados no vetor clássico de spoofing
// de extensão: um nome com RLO (U+202E) pode renderizar
// "relatorio‮fdp.exe" como se fosse "relatorio.exe.pdf". Nenhum nome de
// arquivo legítimo gerado pelo backend precisa desses caracteres.
function hasUnicodeDirectionOverride(name: string): boolean {
  for (let i = 0; i < name.length; i += 1) {
    const code = name.charCodeAt(i)
    if (code >= 0x202a && code <= 0x202e) return true
    if (code >= 0x2066 && code <= 0x2069) return true
  }
  return false
}

// Valida o nome antes de usá-lo em `link.download`. O valor vem de um header
// HTTP — não é confiável por construção, mesmo vindo do próprio backend —
// então é defesa em profundidade contra travessia de diretório e nomes
// malformados: rejeita separador de caminho (`/`, `\`), sequência de subida
// de diretório (`..`), caracteres de controle, controles de direção Unicode
// (ver `hasUnicodeDirectionOverride`), nomes vazios/só-ponto/iniciados por
// ponto, e nomes vazios ou longos demais. Qualquer falha aqui cai no nome
// determinístico.
function isSafeDownloadFilename(name: string): boolean {
  if (!name || name.length > MAX_DOWNLOAD_FILENAME_LENGTH) return false
  if (name === '.' || name.startsWith('.')) return false
  if (name.includes('/') || name.includes('\\') || name.includes('..')) return false
  if (hasUnicodeDirectionOverride(name)) return false
  for (let i = 0; i < name.length; i += 1) {
    const code = name.charCodeAt(i)
    if (code <= 0x1f || code === 0x7f) return false
  }
  return true
}

// Extrai o nome de arquivo de `Content-Disposition: attachment;
// filename="..."` — formato exato devolvido por `_download_headers`
// (`reports/router.py:79`, sempre aspas duplas, nunca `filename*=` RFC 5987).
// Além de `isSafeDownloadFilename`, o nome só é aceito se terminar
// exatamente com a extensão do `format` pedido (comparação
// case-insensitive): sem essa checagem, um header malicioso ou malformado
// como `filename="fatura.csv.exe"` passaria pela sanitização de caracteres
// e ainda assim baixaria com extensão divergente da que o usuário pediu. Um
// valor que falhe em qualquer uma das duas checagens é tratado como
// ausente, para cair no fallback determinístico.
function filenameFromContentDisposition(
  headerValue: string | null,
  format: MonthlyReportExportFormat,
): string | null {
  if (!headerValue) return null
  const match = /filename="([^"]+)"/.exec(headerValue)
  if (!match) return null
  const filename = match[1]
  if (!isSafeDownloadFilename(filename)) return null
  if (!filename.toLowerCase().endsWith(`.${format}`)) return null
  return filename
}

// Dispara o download autenticado de um relatório mensal no navegador. Um
// `<a href>` cru não carregaria o `Authorization`: o token de acesso vive só
// em memória (`lib/auth.ts:1`), não em cookie — por isso o corpo vem via
// `apiFetch` (que já injeta o header) como `blob`, e o download é disparado
// por um `<a>` temporário apontando para um `URL.createObjectURL`. O object
// URL é sempre revogado no `finally` (sucesso ou falha do clique) para não
// vazar memória.
export async function downloadMonthlyReportExport(
  plantId: string,
  format: MonthlyReportExportFormat,
): Promise<void> {
  const response = await fetchMonthlyReportExport(plantId, format)
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('Nenhum ciclo de faturamento fechado disponível para exportar ainda.')
    }
    throw new Error(`Não foi possível gerar o relatório (${response.status}).`)
  }

  const blob = await response.blob()
  const filename =
    filenameFromContentDisposition(response.headers.get('Content-Disposition'), format) ??
    fallbackExportFilename(plantId, format)

  const objectUrl = URL.createObjectURL(blob)
  try {
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}
