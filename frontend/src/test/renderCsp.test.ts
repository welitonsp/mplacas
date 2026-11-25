// Guarda do CSP same-origin (ADR-102), sucessora da guarda do achado A-01 da
// auditoria 2026-08-26.
//
// Antes, a origem da API entrava no `connect-src` a partir de `VITE_API_URL`.
// Agora o navegador só fala com a própria origem (proxy `/api/*`) e o CSP é
// fixo. Estes testes cobrem a lógica do script; o teste de contrato em Python
// (`tests/test_frontend_auth_contract.py`) confere o arquivo versionado.
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  EXPECTED_CONNECT_SRC,
  LEGACY_PLACEHOLDER,
  assertNoLegacyApiUrl,
  assertSameOriginCsp,
} from '../../scripts/render-csp.mjs'

const policy = (connectSrc: string) =>
  `  Content-Security-Policy: default-src 'self'; ${connectSrc} img-src 'self' data:; script-src 'self'`

describe('assertSameOriginCsp', () => {
  it("aceita exatamente connect-src 'self'", () => {
    expect(() => assertSameOriginCsp(policy(EXPECTED_CONNECT_SRC))).not.toThrow()
  })

  it('o _headers versionado passa na guarda', () => {
    const headers = readFileSync(path.resolve(process.cwd(), 'public/_headers'), 'utf-8')
    expect(() => assertSameOriginCsp(headers)).not.toThrow()
  })

  it.each([
    ['origem do Render', "connect-src 'self' https://mplacas-api.onrender.com;"],
    ['https genérico', "connect-src 'self' https:;"],
    ['curinga', "connect-src *;"],
    ['marcador antigo', `connect-src 'self' ${LEGACY_PLACEHOLDER};`],
  ])('recusa %s', (_nome, directive) => {
    expect(() => assertSameOriginCsp(policy(directive))).toThrow()
  })

  it('recusa CSP sem connect-src (cairia no default-src sem a guarda saber)', () => {
    expect(() => assertSameOriginCsp("Content-Security-Policy: default-src 'self'")).toThrow()
  })
})

describe('assertNoLegacyApiUrl', () => {
  it('passa quando VITE_API_URL não existe ou está vazia', () => {
    expect(() => assertNoLegacyApiUrl({})).not.toThrow()
    expect(() => assertNoLegacyApiUrl({ VITE_API_URL: '  ' })).not.toThrow()
  })

  it('falha o build quando VITE_API_URL ainda está configurada, apontando a variável certa', () => {
    expect(() => assertNoLegacyApiUrl({ VITE_API_URL: 'https://api.exemplo.com' })).toThrow(/MPLACAS_API_ORIGIN/)
  })
})
