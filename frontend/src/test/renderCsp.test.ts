// Guarda do achado A-01 da auditoria 2026-08-26.
//
// A origem da API ficava escrita à mão no CSP de `public/_headers` e sobreviveu
// à migração de plataforma apontando para um projeto do Google Cloud excluído.
// O modo de falha era silencioso: a aplicação carregava, o navegador bloqueava
// todo `fetch`, e não havia erro de servidor, log ou CI vermelho.
//
// Estes testes cobrem a lógica; o teste de contrato em Python
// (`tests/test_frontend_auth_contract.py`) garante que o template continua com
// o marcador e sem origem fixa.
import { describe, expect, it } from 'vitest'

import { PLACEHOLDER, apiOrigin, renderHeaders } from '../../scripts/render-csp.mjs'

const TEMPLATE =
  "  Content-Security-Policy: default-src 'self'; connect-src 'self' " +
  `${PLACEHOLDER}; img-src 'self' data:; script-src 'self'`

describe('apiOrigin', () => {
  it('reduz a URL da API à origem, porque connect-src não aceita caminho', () => {
    expect(apiOrigin('https://mplacas-api-abc.onrender.com/v1/base')).toBe(
      'https://mplacas-api-abc.onrender.com'
    )
  })

  it('preserva porta não padrão', () => {
    expect(apiOrigin('https://api.exemplo.com:8443')).toBe('https://api.exemplo.com:8443')
  })

  it('aceita http apenas em localhost', () => {
    expect(apiOrigin('http://localhost:8080')).toBe('http://localhost:8080')
    expect(() => apiOrigin('http://api.exemplo.com')).toThrow(/HTTPS/)
  })

  it.each([
    ['ausente', undefined],
    ['vazia', ''],
    ['só espaços', '   '],
    ['sem esquema', 'api.exemplo.com'],
  ])('recusa VITE_API_URL %s em vez de emitir CSP quebrado', (_nome, valor) => {
    expect(() => apiOrigin(valor as string)).toThrow()
  })
})

describe('renderHeaders', () => {
  it('substitui o marcador pela origem da API', () => {
    const rendered = renderHeaders(TEMPLATE, 'https://mplacas-api-abc.onrender.com')

    expect(rendered).toContain("connect-src 'self' https://mplacas-api-abc.onrender.com;")
    expect(rendered).not.toContain(PLACEHOLDER)
  })

  it('falha quando o marcador sumiu, que é a regressão a prevenir', () => {
    const comOrigemFixa = "connect-src 'self' https://fixo.exemplo.com;"

    expect(() => renderHeaders(comOrigemFixa, 'https://novo.onrender.com')).toThrow(
      /marcador/
    )
  })

  it('não relaxa o restante da política', () => {
    const rendered = renderHeaders(TEMPLATE, 'https://api.exemplo.com')

    expect(rendered).toContain("default-src 'self'")
    expect(rendered).toContain("script-src 'self'")
    expect(rendered).not.toContain("connect-src 'self' https:;")
  })
})
