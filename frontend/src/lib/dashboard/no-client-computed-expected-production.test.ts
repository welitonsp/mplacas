import { describe, expect, it } from 'vitest'

// Critério de aceite mecânico #1 do ADR-068 (seção 7): nenhuma chamada do
// frontend envia produção esperada calculada no cliente como parâmetro de
// requisição — o valor só é lido de respostas do backend
// (`GET /photovoltaic/summary`, ADR-068 seção 3), nunca enviado de volta como
// referência de cálculo. Busca textual em toda `frontend/src` porque a
// propriedade a proteger é sintática e permanente.
//
// Lê o texto-fonte de todos os arquivos via `import.meta.glob` do Vite (com
// `query: '?raw'`) em vez de `node:fs`, para não depender de `@types/node`
// só para este teste — o projeto não usa Node em nenhum outro ponto do
// bundle de testes.
const sourceFiles = import.meta.glob('/src/**/*.{ts,tsx}', {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>

const FORBIDDEN_SUBSTRING = 'expected_daily_production_kwh='

// Exceção única, documentada e temporária (ADR-068, seções 5 e 6).
// `pages/DashboardPage.tsx` ainda envia `expected_daily_production_kwh` na
// query string de `GET /energy/anomalies/latest` porque, até a Etapa D do
// ADR-068, o backend (`intelligence/router.py:310`) ainda declara esse
// parâmetro como obrigatório — removê-lo do cliente antes disso quebraria a
// rota com 422. O valor enviado já não é mais calculado no browser (Etapa C:
// vem pronto de `summary.expectedProduction.kwh`, lido de
// `GET /photovoltaic/summary`) — só o nome do parâmetro de query continua
// aparecendo na URL. A Etapa D depreciará o parâmetro no servidor e a Etapa E
// removerá esta linha do cliente; nesse ponto esta exceção deve ser apagada
// junto, não apenas ignorada.
const ALLOWED_FILES = new Set(['/src/pages/DashboardPage.tsx'])

describe('nenhuma chamada nova envia produção esperada calculada ao servidor (ADR-068, seção 7)', () => {
  it('não introduz `expected_daily_production_kwh=` em URL fora da exceção documentada da Etapa D/E', () => {
    const offenders = Object.entries(sourceFiles)
      .filter(([path]) => !path.endsWith('.test.ts') && !path.endsWith('.test.tsx'))
      .filter(([, content]) => content.includes(FORBIDDEN_SUBSTRING))
      .map(([path]) => path)
      .filter((path) => !ALLOWED_FILES.has(path))

    expect(offenders).toEqual([])
  })
})
