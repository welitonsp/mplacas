#!/usr/bin/env node
// Orçamento de bundle no CI (T8, plano de execução da auditoria de frontend
// 2026-08-12). Desde a divisão em módulos por rota (ADR-072) ninguém media o
// custo por chunk — o `ProductionPage` já chegou a 13,93 kB gzip contra um
// teto de 15, e nada avisaria ao estourar. Este script lê os arquivos reais
// de `dist/assets/` (pós-build), calcula o tamanho gzip de cada um com o
// mesmo algoritmo que o navegador recebe pela rede, e falha o processo
// (`exit(1)`) se qualquer chunk orçado ultrapassar o teto.
//
// Rodar depois de `npm run build` (o passo "Build" do job `frontend` em
// `.github/workflows/ci.yml`), nunca antes — sem `dist/assets/` não há nada
// para medir.

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ASSETS_DIR = path.resolve(__dirname, '..', 'dist', 'assets')

// ---------------------------------------------------------------------------
// ORÇAMENTO — decisão deliberada, não a medição do dia.
//
// Cada linha é um teto escolhido com folga sobre o tamanho medido em
// 2026-08-13 (ver coluna "medido"), não um espelho automático dele — se o
// gate virasse "o que existe hoje + 1 byte", ele nunca protegeria nada.
// Reveja os números aqui só quando houver decisão consciente de gastar mais
// orçamento numa rota (ex.: nova dependência de runtime aprovada por ADR),
// nunca para "fazer o CI passar" depois de um chunk estourar por acidente.
//
// `match` identifica o(s) arquivo(s) de `dist/assets/` que compõem a
// categoria (hash de build muda a cada build, por isso regex de prefixo).
// Se `match` não encontrar nenhum arquivo, é tratado como FALHA — um chunk
// esperado que sumiu (renomeado, removido, split diferente) é sinal de que a
// configuração de build mudou por baixo do gate, silenciosamente, e por isso
// precisa de atenção tanto quanto um chunk que cresceu demais (mesma lição
// da T8b: um gate que não pode falhar não protege nada).
const BUDGETS = [
  {
    // Chunk de entrada (`index-<hash>.js`) — React, React DOM, react-router e
    // o bootstrap do app. É o único custo pago por TODA visita, mesmo antes
    // de qualquer rota carregar (ver `App.tsx`, rotas em `lazy()`).
    name: 'vendor (index-*.js)',
    match: /^index-.*\.js$/,
    limitKb: 70,
    // medido em 2026-08-13: 61,61 kB (relatório de `npm run build`) / ~59,5
    // kB (medição própria deste script, ver nota de metodologia abaixo).
    //
    // Teto revisado de 65 para 70 kB em 2026-10-12, por decisão do dono, ao
    // atualizar o React (PR #172). Medição deste script: 59,65 kB com React
    // 19.2.8 → 68,05 kB com 19.3.0, com react-router e lucide-react
    // atualizados separadamente sem efeito (68,04 kB no fim). Os +8,4 kB são
    // inteiramente do próprio react-dom, não de código do projeto; a
    // alternativa era manter o React em 19.2.x. Folga restante: ~1,9 kB.
  },
  {
    name: 'CSS (index-*.css)',
    match: /^index-.*\.css$/,
    limitKb: 13,
    // medido em 2026-08-13: 11,03 kB (build) / ~10,7 kB (este script).
  },
  {
    name: 'módulo OverviewPage',
    match: /^OverviewPage-.*\.js$/,
    limitKb: 15,
  },
  {
    name: 'módulo ProductionPage',
    match: /^ProductionPage-.*\.js$/,
    limitKb: 15,
    // O mais apertado dos quatro módulos — 13,93 kB medido em 2026-08-12
    // contra este teto de 15. Foi justamente a folga estreita deste chunk
    // que motivou a T8: sem gate, o próximo componente adicionado a este
    // módulo poderia estourar sem que ninguém percebesse.
  },
  {
    name: 'módulo FinancialPage',
    match: /^FinancialPage-.*\.js$/,
    limitKb: 15,
  },
  {
    name: 'módulo TechnicalPage',
    match: /^TechnicalPage-.*\.js$/,
    limitKb: 15,
  },
  {
    // "Minha usina" (cadastro feito pelo próprio cliente), entrou em
    // 2026-10-15 como quinto módulo. Medido: 6,32 kB; teto com folga para os
    // formulários que ainda vão chegar (ex.: conta do inversor).
    name: 'módulo PlantSetupPage',
    match: /^PlantSetupPage-.*\.js$/,
    limitKb: 10,
  },
  {
    // "Como calculamos" (ADR-086): só texto da memória de cálculo, baixado
    // sob demanda. Teto com folga para novas regras.
    name: 'módulo MethodologyPage',
    match: /^MethodologyPage-.*\.js$/,
    limitKb: 6,
  },
  {
    // Painel do investidor (ADR-079), carregado sob demanda pelo Financeiro.
    // Entrou em 2026-10-19; teto com folga para cenários e premissas editáveis.
    name: 'InvestorPanelSection',
    match: /^InvestorPanelSection-.*\.js$/,
    limitKb: 8,
  },
  {
    // "Vale a pena ampliar?" (ADR-089), sob demanda pelo Financeiro, com a
    // própria leitura e parser. Entrou em 2026-10-25 com 4,7 kB; mesmo teto
    // do painel do investidor (a etapa 2 traz o retorno da proposta).
    name: 'ExpansionSection',
    match: /^ExpansionSection-.*\.js$/,
    limitKb: 8,
  },
  {
    // Faturas de energia (importação em lote, "Confirmar todas", meses a
    // recalcular), sob demanda pelo Financeiro. Saiu do módulo em 2026-10-23,
    // quando a importação em lote levou o Financeiro a 15,09 kB (teto 15).
    name: 'BillsSection',
    match: /^BillsSection-.*\.js$/,
    limitKb: 8,
  },
  {
    // Comparação com a produção esperada (régua do último dia, desvio,
    // sequência, diagnóstico do período, episódios), sob demanda pela aba
    // Energia (ADR-083, etapa 3). Saiu do módulo em 2026-10-24, quando a
    // comparação placas × distribuidora levou Energia a 15,08 kB (teto 15).
    // Só é baixada quando a usina já tem referência esperada. Medido: 6,45 kB.
    name: 'ExpectedComparisonSection',
    match: /^ExpectedComparisonSection-.*\.js$/,
    limitKb: 8,
  },
  {
    name: 'LoginPage',
    match: /^LoginPage-.*\.js$/,
    limitKb: 5,
  },
  {
    // Entrada de clientes por convite (ADR-093, decisão do dono 31/10/2026):
    // telas novas, cada uma carregada só por quem precisa dela.
    name: 'InvitePage',
    match: /^InvitePage-.*\.js$/,
    limitKb: 4,
    // medido em 2026-10-31: 2,50 kB
  },
  {
    name: 'ClientsPage',
    match: /^ClientsPage-.*\.js$/,
    limitKb: 7,
    // medido em 2026-10-31: 2,80 kB (só o dono da plataforma carrega).
    // Teto de 4 para 7 kB em 2026-11-02 (ADR-095): a página virou o CRM do
    // dono (ficha, histórico, redefinir acesso, desativar). Só o operador da
    // plataforma baixa este chunk; nenhum cliente paga por ele.
  },
  {
    // Formulário marca + usuário/senha do app, usado em Minha usina e na
    // primeira conexão (ADR-091/093).
    name: 'BrandLoginForm',
    match: /^BrandLoginForm-.*\.js$/,
    limitKb: 4,
    // medido em 2026-10-31: 2,73 kB
  },
  {
    name: 'FirstConnectionPanel',
    match: /^FirstConnectionPanel-.*\.js$/,
    limitKb: 6,
    // Teto de 3 para 6 kB em 2026-11-02 (ADR-096): virou o assistente de 3
    // passos (conectar, leitura, revisar e salvar). Carregado só por conta sem
    // usina, uma vez na vida do cliente. Medido: 4,41 kB.
  },
  // -------------------------------------------------------------------------
  // CHUNKS COMPARTILHADOS GRANDES E ESTÁVEIS (2026-11-11). Moravam na coletora
  // e ocupavam 24,4 dos 44,8 kB dela, o que a deixava com 0,16 kB de folga:
  // qualquer hook/componente compartilhado novo quebraria o CI, e a única saída
  // à vista era subir o teto da coletora (esconder crescimento). Nomeá-los tira
  // da coletora o que NÃO é novo, e ela volta a medir só o que é.
  //
  // Regra de margem destas quatro linhas (e da coletora, ver abaixo): medido
  // por este script + 5%, arredondado para cima ao próximo 0,25 kB. É menor que
  // a folga das rotas (~20-60%) de propósito: estes chunks não ganham código de
  // feature, só crescem por mudança consciente (nova rota no `App`, novo
  // endpoint no `api`, novo item de navegação no layout, upgrade do
  // react-router). Se um deles estourar, é para discutir, não para subir o teto.
  // Medido em 2026-11-11 (build limpo da main).
  {
    // Núcleo do react-router. O Rollup nomeia os dois chunks compartilhados com
    // o nome do primeiro módulo de cada um (`components` vem de
    // `react-router/.../lib/components.js`, `lib` de `.../dom/lib.js`) — NÃO
    // são código do projeto, apesar do nome. Nome instável por natureza: um
    // upgrade do react-router pode renomeá-los ou fundi-los. Se isso
    // acontecer, o `match` deixa de achar arquivo e a linha vira AUSENTE (falha
    // de propósito, ver topo): reajuste o regex olhando o `dist/assets/`.
    // O regex exige o hash de exatamente 8 caracteres do Vite, para não casar
    // um `lib-foo-<hash>.js` qualquer. Um chunk do projeto que o Rollup venha
    // a nomear `lib`/`components` cairia aqui e estouraria este teto — o
    // aviso de estouro lista os arquivos, e aí se separa. Não fixei os nomes
    // com `manualChunks`: medido, isso adiciona 1 requisição e +0,3 kB na
    // primeira carga da landing e +2,3 kB gzip no total (ver commit).
    // medido: 10,59 (components) + 3,44 (lib) = 14,02 kB
    name: 'react-router (components-* + lib-*)',
    match: /^(components|lib)-[A-Za-z0-9_-]{8}\.js$/,
    limitKb: 14.75,
  },
  {
    // Casca do dashboard (cabeçalho, navegação, seletor de usina), carregada
    // por toda rota autenticada. medido: 4,40 kB
    name: 'DashboardLayout',
    match: /^DashboardLayout-.*\.js$/,
    limitKb: 4.75,
  },
  {
    // Roteador do app (`App.tsx`) com os providers de Auth/Me e o
    // `ProtectedRoute`; baixado em toda visita logo após o entry. Cresce a
    // cada rota nova. medido: 3,18 kB
    name: 'App (rotas + providers)',
    match: /^App-.*\.js$/,
    limitKb: 3.5,
  },
  {
    // Cliente HTTP, sessão (`auth.ts`) e `env.ts`. Cresce a cada endpoint
    // novo. medido: 2,77 kB
    name: 'api (cliente HTTP + sessão)',
    match: /^api-.*\.js$/,
    limitKb: 3,
  },
  {
    // Texto do veredito "placas × distribuidora" e o leitor do histórico
    // mensal (`lib/dashboard/utility-check-text.ts`). Compartilhado entre a
    // aba Energia e a resposta ao confirmar a fatura (aba Dinheiro), de onde
    // saiu do chunk da ProductionPage (12,73 → 11,22 kB). Só cresce se o
    // veredito ganhar um caso novo. medido: 2,02 kB (+5%, ao 0,25 kB acima)
    name: 'veredito da distribuidora (utility-check-text)',
    match: /^utility-check-text-.*\.js$/,
    limitKb: 2.25,
  },
  {
    // Página pública (`PublicHomePage`), entrou depois deste gate e por isso
    // não tinha categoria. JS e CSS juntos porque é uma superfície só, e
    // porque a landing traz CSS próprio de peso comparável ao script.
    name: 'PublicHomePage (js+css)',
    match: /^PublicHomePage-.*\.(js|css)$/,
    limitKb: 15,
  },
]

// ---------------------------------------------------------------------------
// CATEGORIA COLETORA — o que consertou a falha real deste gate.
//
// As categorias acima nomeiam chunks específicos. Isso deixava um buraco: TODO
// arquivo cujo nome não casasse com nenhuma delas entrava no bundle sem ser
// medido por nada. Quando a landing pública foi adicionada, os 11,8 kB dela
// passaram inteiros por este gate sem disparar nada — e junto havia outros
// ~34 kB (`components-*`, `PlantContext-*`, `PageHeader-*`,
// `DashboardLayout-*`, primitivas de gráfico) igualmente invisíveis.
//
// Um gate que só mede o que alguém lembrou de nomear protege o passado, não o
// futuro. Esta categoria fecha o conjunto: soma tudo que sobrou e impõe teto.
// Chunk novo agora aparece aqui até que alguém decida se merece categoria
// própria — a decisão vira explícita em vez de silenciosa.
const CATCH_ALL = {
  name: 'demais chunks (soma)',
  limitKb: 21.5,
  // Teto de 45 para 21,5 kB em 2026-11-11, junto com as quatro categorias
  // nomeadas acima (react-router, DashboardLayout, App, api), que saíram daqui.
  // Medido: 44,84 kB antes (folga 0,16) → 20,46 kB agora (folga 1,04, regra de
  // margem de 5% descrita acima). Soma de todos os tetos: 277 → 279,5 kB (+2,5, a folga que antes era 0,16 virou ~2,7 distribuída).
  // O que sobra aqui é o que a descrição acima sempre quis medir: contratos,
  // utilitários, ícones e componentes pequenos compartilhados. Crescimento
  // novo agora consome a folga DESTA linha e fica visível.
  //
  // Histórico — medido em 2026-08-14: ~34,3 kB somando tudo que não casa com as regras
  // acima. Teto com folga deliberada, não espelho da medição.
  //
  // Teto revisado de 42 para 45 kB em 2026-10-31 (ADR-093, entrada de
  // clientes): as telas novas têm categoria própria acima, mas importam
  // `RetryableError`, `useModuleTitle`, `Card` e o contrato do onboarding, que
  // o empacotador passou a separar em chunks compartilhados (antes iam
  // embutidos nos módulos). Medido antes: 41,36 kB; depois: 44,62 kB.
}
// ---------------------------------------------------------------------------

// Nota de metodologia: o tamanho gzip mostrado por `npm run build` (relatório
// nativo do Vite) e o tamanho calculado aqui por `zlib.gzipSync` divergem em
// ~2-3% (algoritmo/nível de compressão internos do Vite não são API pública
// estável). Isso é esperado e não é bug: os limites acima já têm folga
// suficiente para absorver essa diferença, e o gate compara a medição DESTE
// script contra o teto DESTE script — nunca contra o número impresso pelo
// Vite. `kB` aqui é sempre base 1024 (mesma convenção do relatório do Vite).

function gzipKb(filePath) {
  const buffer = readFileSync(filePath)
  const compressed = gzipSync(buffer)
  return compressed.length / 1024
}

function formatKb(value) {
  return `${value.toFixed(2)} kB`
}

function main() {
  let files
  try {
    files = readdirSync(ASSETS_DIR).filter((name) => statSync(path.join(ASSETS_DIR, name)).isFile())
  } catch (error) {
    console.error(
      `Orçamento de bundle: não encontrei ${ASSETS_DIR}. Rode "npm run build" antes deste script.`
    )
    console.error(error instanceof Error ? error.message : error)
    process.exit(1)
  }

  const rows = []
  const failures = []

  for (const budget of BUDGETS) {
    const matches = files.filter((name) => budget.match.test(name))

    if (matches.length === 0) {
      failures.push(
        `${budget.name}: NENHUM arquivo em dist/assets/ casou com ${budget.match} ` +
          '— chunk esperado sumiu (renomeado, removido, ou split de build mudou). ' +
          'Gate tratado como falho: um chunk orçado que desaparece silenciosamente ' +
          'não deve passar sem revisão humana.'
      )
      rows.push({ name: budget.name, actual: null, limit: budget.limitKb, files: [], status: 'AUSENTE' })
      continue
    }

    const totalKb = matches.reduce((sum, name) => sum + gzipKb(path.join(ASSETS_DIR, name)), 0)
    const overBudget = totalKb > budget.limitKb

    rows.push({
      name: budget.name,
      actual: totalKb,
      limit: budget.limitKb,
      files: matches,
      status: overBudget ? 'ESTOUROU' : 'ok',
    })

    if (overBudget) {
      failures.push(
        `${budget.name}: ${formatKb(totalKb)} gzip, acima do teto de ${formatKb(budget.limitKb)} ` +
          `(arquivo${matches.length > 1 ? 's' : ''}: ${matches.join(', ')}). ` +
          `Excedente: ${formatKb(totalKb - budget.limitKb)}.`
      )
    }
  }

  // Categoria coletora: tudo que nenhuma regra acima reivindicou. Arquivos de
  // mapa de origem e afins ficam de fora porque não são baixados pelo usuário.
  const claimed = new Set(BUDGETS.flatMap((budget) => files.filter((name) => budget.match.test(name))))
  const leftovers = files
    .filter((name) => !claimed.has(name) && /\.(js|css)$/.test(name))
    .map((name) => ({ name, kb: gzipKb(path.join(ASSETS_DIR, name)) }))
    .sort((a, b) => b.kb - a.kb)
  const leftoverTotal = leftovers.reduce((sum, item) => sum + item.kb, 0)

  rows.push({
    name: CATCH_ALL.name,
    actual: leftoverTotal,
    limit: CATCH_ALL.limitKb,
    files: leftovers.map((item) => item.name),
    status: leftoverTotal > CATCH_ALL.limitKb ? 'ESTOUROU' : 'ok',
  })

  if (leftoverTotal > CATCH_ALL.limitKb) {
    failures.push(
      `${CATCH_ALL.name}: ${formatKb(leftoverTotal)} gzip, acima do teto de ` +
        `${formatKb(CATCH_ALL.limitKb)}. Excedente: ${formatKb(leftoverTotal - CATCH_ALL.limitKb)}. ` +
        'Estes chunks não têm categoria própria — decida se algum merece uma (e teto ' +
        'próprio) ou reduza o conjunto:\n' +
        leftovers.map((item) => `      ${item.name.padEnd(36)} ${formatKb(item.kb)}`).join('\n')
    )
  }

  console.log('Orçamento de bundle (gzip, dist/assets/):\n')
  const nameWidth = Math.max(...rows.map((row) => row.name.length), 'chunk'.length)
  console.log(`${'chunk'.padEnd(nameWidth)}  medido      teto      status`)
  for (const row of rows) {
    const actualLabel = row.actual === null ? '—'.padEnd(10) : formatKb(row.actual).padEnd(10)
    console.log(
      `${row.name.padEnd(nameWidth)}  ${actualLabel}  ${formatKb(row.limit).padEnd(8)}  ${row.status}`
    )
  }
  console.log('')

  // Composição por arquivo. A auditoria externa v6 registrou como pendência
  // (`[ABR]`) justamente não saber QUAIS arquivos o regex de cada categoria
  // casava — chegou a supor que uma categoria pudesse estar somando vários
  // arquivos sem que ninguém percebesse. Imprimir sempre, e não atrás de uma
  // flag, torna a pergunta impossível de reaparecer.
  console.log('Composição (arquivo → categoria):\n')
  for (const row of rows) {
    if (row.files.length === 0) continue
    for (const name of row.files) {
      const kb = formatKb(gzipKb(path.join(ASSETS_DIR, name)))
      console.log(`  ${name.padEnd(36)} ${kb.padStart(10)}   ${row.name}`)
    }
  }
  console.log('')

  if (failures.length > 0) {
    console.error(`Orçamento de bundle FALHOU (${failures.length} de ${rows.length} categorias):\n`)
    for (const failure of failures) {
      console.error(`  - ${failure}`)
    }
    console.error('\nAjuste o código para reduzir o chunk, ou revise deliberadamente o teto em')
    console.error('frontend/scripts/check-bundle-budget.mjs (com justificativa, não para silenciar o gate).')
    process.exit(1)
  }

  console.log('Orçamento de bundle OK — todos os chunks orçados dentro do teto.')
}

main()
