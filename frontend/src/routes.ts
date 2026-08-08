// Constantes de path dos módulos do painel (ADR-072, Decisão 1). Único lugar
// que conhece os literais das 4 URLs de módulo — `DashboardNav`,
// `DashboardIndexRedirect` e a árvore de rotas em `App.tsx` importam daqui,
// para nunca divergir do path realmente registrado no roteador.

export const DASHBOARD_ROOT_PATH = '/dashboard'

// Segmentos relativos, usados nas rotas filhas aninhadas sob `/dashboard`
// (`<Route path="visao-geral" .../>` em `App.tsx`) — o `react-router` resolve
// esses paths relativos ao path da rota de layout pai.
const OVERVIEW_SEGMENT = 'visao-geral'
const PRODUCTION_SEGMENT = 'producao'
const FINANCIAL_SEGMENT = 'financeiro'
const TECHNICAL_SEGMENT = 'tecnico'

export const DASHBOARD_MODULE_SEGMENTS = {
  overview: OVERVIEW_SEGMENT,
  production: PRODUCTION_SEGMENT,
  financial: FINANCIAL_SEGMENT,
  technical: TECHNICAL_SEGMENT,
} as const

export const DASHBOARD_OVERVIEW_PATH = `${DASHBOARD_ROOT_PATH}/${OVERVIEW_SEGMENT}` as const
export const DASHBOARD_PRODUCTION_PATH = `${DASHBOARD_ROOT_PATH}/${PRODUCTION_SEGMENT}` as const
export const DASHBOARD_FINANCIAL_PATH = `${DASHBOARD_ROOT_PATH}/${FINANCIAL_SEGMENT}` as const
export const DASHBOARD_TECHNICAL_PATH = `${DASHBOARD_ROOT_PATH}/${TECHNICAL_SEGMENT}` as const

// Rota de aterrissagem: para onde `DashboardIndexRedirect` (índice de
// `/dashboard` e catch-all `/dashboard/*`) redireciona por padrão.
export const DASHBOARD_DEFAULT_PATH = DASHBOARD_OVERVIEW_PATH
