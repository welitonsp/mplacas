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
    limitKb: 65,
    // medido em 2026-08-13: 61,61 kB (relatório de `npm run build`) / ~59,5
    // kB (medição própria deste script, ver nota de metodologia abaixo).
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
    name: 'LoginPage',
    match: /^LoginPage-.*\.js$/,
    limitKb: 5,
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
  limitKb: 42,
  // medido em 2026-08-14: ~34,3 kB somando tudo que não casa com as regras
  // acima. Teto com folga deliberada, não espelho da medição.
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
