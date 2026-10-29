import { describe, expect, it } from 'vitest'
import { parseProviderAccount, providerAccountErrorMessage } from './provider-account-contracts'

const BASE = {
  status: 'CONECTADA',
  provider: 'NEPVIEWER',
  login_hint: 'cl***@example.com',
  connected_at: '2026-10-29T18:44:00Z',
  last_success_at: null,
  last_failure_at: null,
  devices_found: 3,
}

describe('parseProviderAccount', () => {
  it('lê o estado sem inventar valores', () => {
    expect(parseProviderAccount(BASE)).toEqual({
      status: 'CONECTADA',
      provider: 'NEPVIEWER',
      loginHint: 'cl***@example.com',
      connectedAt: '2026-10-29T18:44:00Z',
      lastSuccessAt: null,
      lastFailureAt: null,
      devicesFound: 3,
    })
  })

  it.each([
    [null],
    [{ ...BASE, status: 'OK' }],
    [{ ...BASE, devices_found: -1 }],
    [{ ...BASE, devices_found: '3' }],
    [{ ...BASE, login_hint: '' }],
  ])('recusa payload malformado %#', (payload) => {
    expect(() => parseProviderAccount(payload)).toThrow(/Resposta inválida/)
  })
})

describe('providerAccountErrorMessage', () => {
  it('usa mensagem genérica para código desconhecido ou corpo não JSON', async () => {
    expect(await providerAccountErrorMessage(new Response('x', { status: 500 }))).toBe(
      'Não foi possível concluir agora. Tente novamente.',
    )
    expect(
      await providerAccountErrorMessage(
        new Response(JSON.stringify({ detail: [{ input: 'segredo' }] }), { status: 422 }),
      ),
    ).not.toContain('segredo')
  })
})
