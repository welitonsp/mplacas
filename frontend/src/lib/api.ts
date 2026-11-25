import { API_URL } from '../env'
import { TokenStore } from './auth'
import {
  AUTH_TIMEOUT_MS,
  DATA_TIMEOUT_MS,
  RequestTimeoutError,
  authFetch,
  refreshSession,
  withTimeout,
} from './session'
import { parsePlantsResponse, type Plant } from './dashboard/plant-contracts'

// Prazos, `withTimeout` e `RequestTimeoutError` moram em `session.ts` (o
// transporte da sessão precisa deles sem depender deste módulo); reexportados
// aqui para quem já os importava daqui.
export { AUTH_TIMEOUT_MS, DATA_TIMEOUT_MS, RequestTimeoutError, withTimeout }

// Acorda a API sem bloquear nada: a tela de login chama isto ao abrir, para o
// servidor já estar de pé quando o usuário terminar de digitar a senha. Falha
// é ignorada de propósito — é só um aquecimento; o login trata os erros reais.
export function warmUpApi(): void {
  fetch(`${API_URL}/health`, { method: 'GET', cache: 'no-store', credentials: 'same-origin' }).catch(() => undefined)
}

type SessionExpiredFn = () => void

let _onSessionExpired: SessionExpiredFn = () => {}

// O `AuthContext` registra aqui o que fazer quando a renovação é recusada (a
// sessão acabou sem o usuário pedir). Desde a ADR-102 não há refresh token a
// entregar: ele vive no cookie HttpOnly que este código não lê.
export function configureApi(onSessionExpired: SessionExpiredFn) {
  _onSessionExpired = onSessionExpired
}

// Renovação indisponível (rede, prazo, servidor acordando): a sessão pode estar
// viva, então NÃO desloga — a tela mostra erro e deixa tentar de novo.
export class SessionRefreshUnavailableError extends Error {
  constructor() {
    super('Não foi possível renovar a sessão agora. Tente de novo em instantes.')
    this.name = 'SessionRefreshUnavailableError'
  }
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = TokenStore.get()
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  // JSON é o padrão; quem envia outro corpo (o PDF da fatura, por exemplo)
  // declara o próprio `Content-Type` e ele é respeitado.
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  // O prazo interno convive com o `signal` que o chamador tenha passado: quem
  // cancela por desmontagem de componente continua funcionando, e quem não
  // passa nada ganha o prazo mesmo assim.
  const deadline = withTimeout(DATA_TIMEOUT_MS, init.signal)
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers,
      credentials: 'same-origin',
      signal: deadline.signal,
    })
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

  // Renovação pelo cookie (single-flight na aba, serializada entre abas).
  const outcome = await refreshSession()
  if (outcome.kind === 'unreachable') throw new SessionRefreshUnavailableError()
  if (outcome.kind === 'unauthenticated') {
    _onSessionExpired()
    return response
  }
  // A sessão mudou durante a renovação (logout, login de outra pessoa): a
  // resposta original fica como está e a chamada NÃO é repetida com token de
  // outra sessão.
  if (outcome.kind === 'superseded') return response
  const { accessToken } = outcome

  // Repete a chamada original com o token renovado.
  const retryHeaders = new Headers(init.headers)
  retryHeaders.set('Authorization', `Bearer ${accessToken}`)
  if (!retryHeaders.has('Content-Type')) retryHeaders.set('Content-Type', 'application/json')
  const retryDeadline = withTimeout(DATA_TIMEOUT_MS, init.signal)
  try {
    return await fetch(`${API_URL}${path}`, {
      ...init,
      headers: retryHeaders,
      credentials: 'same-origin',
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

// Análise de UM ciclo pela fatura (`GET /energy/cycles/{bill_id}`): a economia
// estimada daquele ciclo e, quando não há, o motivo. Usada para responder, logo
// depois de confirmar a fatura, quanto o ciclo economizou.
export async function fetchEnergyCycle(plantId: string, billId: string): Promise<Response> {
  return apiFetch(
    `/energy/cycles/${encodeURIComponent(billId)}?plant_id=${encodeURIComponent(plantId)}`
  )
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

// Painel do investidor (ADR-079, `GET /energy/investor/latest`): realizado ×
// CDI líquido e projeção de vida útil (TIR, VPL, paybacks). Sempre 200 dentro
// do escopo; o que falta vem em `unavailable_reason`, nunca como erro HTTP.
export async function fetchInvestorPanel(plantId: string): Promise<Response> {
  return apiFetch(`/energy/investor/latest?plant_id=${encodeURIComponent(plantId)}`)
}

// Vale a pena ampliar a usina? (ADR-089, `GET /energy/expansion/latest`).
// Sempre 200 dentro do escopo; o que falta vem em `status`/`reasons`.
export async function fetchExpansionAssessment(plantId: string): Promise<Response> {
  return apiFetch(`/energy/expansion/latest?plant_id=${encodeURIComponent(plantId)}`)
}

// Proposta de ampliação (ADR-089, etapa 2): valor total; `null` apaga. ADMIN.
export async function updateExpansionProposal(
  plantId: string,
  payload: { amount_brl: string | null; includes_inverter: boolean },
): Promise<Response> {
  return apiFetch(`/plants/${encodeURIComponent(plantId)}/expansion-proposal`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

// Cadastro da usina ("Minha usina"). `GET /plants/{id}/setup` reúne em uma
// leitura o que o dono já informou e o checklist do que falta (a regra de
// "feito" de cada item é do backend). As escritas usam as rotas que já
// existiam: configuração técnica, localização e investimento — todas ADMIN
// (`AdminPlantPath`); uma credencial READ recebe 403, tratado na tela.
export async function fetchPlantSetup(plantId: string): Promise<Response> {
  return apiFetch(`/plants/${encodeURIComponent(plantId)}/setup`)
}

// Conexão com o fabricante do inversor (ADR-091). A senha só vai no corpo do
// PUT; nunca é guardada no navegador nem volta do servidor.
export async function fetchProviderAccount(plantId: string): Promise<Response> {
  return apiFetch(`/plants/${encodeURIComponent(plantId)}/provider-account`)
}

export async function saveProviderAccount(
  plantId: string,
  payload: { provider: 'NEPVIEWER'; login: string; password: string },
): Promise<Response> {
  return apiFetch(`/plants/${encodeURIComponent(plantId)}/provider-account`, {
    method: 'PUT',
    body: JSON.stringify({ provider: payload.provider, login: payload.login, password: payload.password }),
  })
}

// Relê o cadastro da usina na marca com a conexão guardada (ADR-094).
export async function refreshPlantProfile(plantId: string): Promise<Response> {
  return apiFetch(`/plants/${encodeURIComponent(plantId)}/provider-account/refresh-profile`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

// Importa a produção dos últimos 90 dias da marca (ADR-097), sem esperar a
// coleta da madrugada. Usa a conexão guardada; nenhum segredo trafega aqui.
export async function importProductionHistory(plantId: string): Promise<Response> {
  return apiFetch(`/plants/${encodeURIComponent(plantId)}/provider-account/import-history`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

// Total gerado e potência agora, lidos na marca (ADR-099). Só Growatt por
// token; outras marcas respondem 404 e a tela não mostra o cartão.
export async function fetchPlantNow(plantId: string): Promise<Response> {
  return apiFetch(`/plants/${encodeURIComponent(plantId)}/provider-account/now`)
}

export async function deleteProviderAccount(plantId: string): Promise<Response> {
  return apiFetch(`/plants/${encodeURIComponent(plantId)}/provider-account`, { method: 'DELETE' })
}

// Primeira conexão (ADR-093 § 7): a usina nasce da conta da marca. Mesmo
// corpo do PUT da conexão; a senha só vai no corpo e nunca volta.
export async function connectFirstPlant(payload: {
  provider: 'NEPVIEWER'
  login: string
  password: string
}): Promise<Response> {
  return apiFetch('/plants/connect', {
    method: 'POST',
    body: JSON.stringify({ provider: payload.provider, login: payload.login, password: payload.password }),
  })
}

// Assistente de primeiro acesso (ADR-096): a prévia lê a usina na marca sem
// salvar e devolve um bilhete cifrado; a confirmação salva com esse bilhete.
export async function previewFirstPlant(payload: {
  provider: 'NEPVIEWER'
  login: string
  password: string
}): Promise<Response> {
  return apiFetch('/plants/connect/preview', {
    method: 'POST',
    body: JSON.stringify({ provider: payload.provider, login: payload.login, password: payload.password }),
  })
}

export async function confirmFirstPlant(ticket: string, plant: Record<string, string | null>): Promise<Response> {
  return apiFetch('/plants/connect/confirm', { method: 'POST', body: JSON.stringify({ ticket, plant }) })
}

// Quem está logado (ADR-093): papel, organização e se é o dono da plataforma.
export async function fetchMe(): Promise<Response> {
  return apiFetch('/auth/me')
}

// Clientes do dono da plataforma (ADR-093). O token do convite volta só na
// criação/reenvio e nunca é guardado no navegador.
export async function fetchClients(): Promise<Response> {
  return apiFetch('/platform/clients')
}

export async function createClient(payload: { name: string; admin_username: string }): Promise<Response> {
  return apiFetch('/platform/clients', { method: 'POST', body: JSON.stringify(payload) })
}

export async function fetchClient(organizationId: string): Promise<Response> {
  return apiFetch(`/platform/clients/${encodeURIComponent(organizationId)}`)
}

export async function resetClientAccess(organizationId: string): Promise<Response> {
  return apiFetch(`/platform/clients/${encodeURIComponent(organizationId)}/access-reset`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export async function setClientActive(organizationId: string, active: boolean): Promise<Response> {
  return apiFetch(
    `/platform/clients/${encodeURIComponent(organizationId)}/${active ? 'reactivate' : 'deactivate'}`,
    { method: 'POST', body: JSON.stringify({}) },
  )
}

export async function reinviteClient(organizationId: string): Promise<Response> {
  return apiFetch(`/platform/clients/${encodeURIComponent(organizationId)}/invitation`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

// Convite (tela /convite, sem login). O token vai no corpo — nunca na URL
// enviada ao servidor — com o mesmo prazo e os mesmos cabeçalhos do login: o
// aceite abre sessão e grava o cookie (ADR-102).
async function publicPost(path: string, body: unknown): Promise<Response> {
  return authFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function inspectInvitation(token: string): Promise<Response> {
  return publicPost('/auth/invitations/inspect', { token })
}

export async function acceptInvitation(token: string, password: string): Promise<Response> {
  return publicPost('/auth/invitations/accept', { token, password })
}

export interface TechnicalConfigurationUpdatePayload {
  dc_capacity_kwp?: string | null
  ac_capacity_kw?: string | null
  array_tilt_degrees?: string | null
  array_azimuth_degrees?: string | null
  module_technology?: string | null
  commissioned_on?: string | null
}

export async function updateTechnicalConfiguration(
  plantId: string,
  payload: TechnicalConfigurationUpdatePayload,
): Promise<Response> {
  return apiFetch(`/plants/${encodeURIComponent(plantId)}/technical-configuration`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function updatePlantLocation(
  plantId: string,
  payload: { latitude: string; longitude: string },
): Promise<Response> {
  return apiFetch(`/plants/${encodeURIComponent(plantId)}/location`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

// Faturas de energia (`/billing/*`). Importar, confirmar e rejeitar exigem
// perfil ADMIN no backend (`AdminPlant`/`AdminPrincipal`) — uma credencial READ
// recebe 403, tratado na tela (mesma limitação conhecida do
// `CapexRegistrationForm`: o frontend ainda não distingue papel).
//
// O PDF vai cru no corpo (`application/pdf`), sem multipart: o backend o lê
// com limite de tamanho, extrai o texto em processo isolado e descarta o
// arquivo — só o texto lido vira a fatura pendente de conferência.
export async function uploadBillPdf(plantId: string, file: Blob): Promise<Response> {
  return apiFetch(`/billing/intake-pdf?plant_id=${encodeURIComponent(plantId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/pdf' },
    body: file,
  })
}

// Até 50: cobre uma importação em lote inteira (o backend aceita até 100).
export const PENDING_BILLS_LIMIT = 50

export async function fetchPendingBills(plantId: string): Promise<Response> {
  return apiFetch(`/billing/pending?plant_id=${encodeURIComponent(plantId)}&limit=${PENDING_BILLS_LIMIT}`)
}

export async function confirmBill(billId: string): Promise<Response> {
  return apiFetch(`/billing/${encodeURIComponent(billId)}/confirm`, { method: 'POST' })
}

export async function rejectBill(billId: string): Promise<Response> {
  return apiFetch(`/billing/${encodeURIComponent(billId)}/reject`, { method: 'POST' })
}

// Meses com fatura confirmada sem economia ou com cálculo antigo (ADR-081).
export async function fetchSavingsGaps(plantId: string): Promise<Response> {
  return apiFetch(`/reports/monthly/savings-gaps?plant_id=${encodeURIComponent(plantId)}`)
}

export async function reprocessSavingsGaps(plantId: string): Promise<Response> {
  return apiFetch(`/reports/monthly/savings-gaps/reprocess?plant_id=${encodeURIComponent(plantId)}`, {
    method: 'POST',
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
