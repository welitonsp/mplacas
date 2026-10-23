// Constantes de path dos módulos do painel (ADR-072, Decisão 1; reorganização
// em 4 perguntas, ADR-083). Único lugar que conhece os literais das URLs de
// módulo — `DashboardNav`, `DashboardIndexRedirect` e a árvore de rotas em
// `App.tsx` importam daqui, para nunca divergir do path realmente registrado.

export const DASHBOARD_ROOT_PATH = '/dashboard'

// Segmentos relativos, usados nas rotas filhas aninhadas sob `/dashboard`
// (`<Route path="inicio" .../>` em `App.tsx`) — o `react-router` resolve
// esses paths relativos ao path da rota de layout pai.
//
// Quatro abas, cada uma responde uma pergunta do dono da usina (ADR-083):
// Início ("está tudo bem?"), Energia ("quanto gerou e para onde foi?"),
// Dinheiro ("quanto ganhei?") e Minha usina ("meus dados"). Os detalhes
// técnicos (PR, perdas, inversores) moram dentro de Energia.
const HOME_SEGMENT = 'inicio'
const ENERGY_SEGMENT = 'energia'
const TECHNICAL_SEGMENT = 'energia/tecnico'
const MONEY_SEGMENT = 'dinheiro'
// "Minha usina": onde o cliente informa os dados da própria usina.
const SETUP_SEGMENT = 'minha-usina'

export const DASHBOARD_MODULE_SEGMENTS = {
  overview: HOME_SEGMENT,
  production: ENERGY_SEGMENT,
  technical: TECHNICAL_SEGMENT,
  financial: MONEY_SEGMENT,
  setup: SETUP_SEGMENT,
} as const

export const DASHBOARD_OVERVIEW_PATH = `${DASHBOARD_ROOT_PATH}/${HOME_SEGMENT}` as const
export const DASHBOARD_PRODUCTION_PATH = `${DASHBOARD_ROOT_PATH}/${ENERGY_SEGMENT}` as const
export const DASHBOARD_TECHNICAL_PATH = `${DASHBOARD_ROOT_PATH}/${TECHNICAL_SEGMENT}` as const
export const DASHBOARD_FINANCIAL_PATH = `${DASHBOARD_ROOT_PATH}/${MONEY_SEGMENT}` as const
export const DASHBOARD_SETUP_PATH = `${DASHBOARD_ROOT_PATH}/${SETUP_SEGMENT}` as const

// URLs da organização anterior (5 abas). Continuam funcionando — favorito,
// link no e-mail do relatório mensal, aba aberta — e redirecionam para a aba
// nova equivalente, preservando `?plant=` (ver `LegacyModuleRedirect`).
export const LEGACY_MODULE_REDIRECTS: ReadonlyArray<{ segment: string; to: string }> = [
  { segment: 'visao-geral', to: DASHBOARD_OVERVIEW_PATH },
  { segment: 'producao', to: DASHBOARD_PRODUCTION_PATH },
  { segment: 'financeiro', to: DASHBOARD_FINANCIAL_PATH },
  { segment: 'tecnico', to: DASHBOARD_TECHNICAL_PATH },
]

// Rota de aterrissagem: para onde `DashboardIndexRedirect` (índice de
// `/dashboard` e catch-all `/dashboard/*`) redireciona por padrão.
export const DASHBOARD_DEFAULT_PATH = DASHBOARD_OVERVIEW_PATH
