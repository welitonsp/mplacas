import { describe, expect, it } from 'vitest'
import {
  brandLabel,
  isGrowatt,
  parseProviderAccount,
  PROVIDER_BRANDS,
  providerAccountErrorMessage,
} from './provider-account-contracts'

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

describe('mensagens por marca', () => {
  it('usa o nome da marca escolhida', async () => {
    const response = () => new Response(JSON.stringify({ detail: 'provider_login_failed' }), { status: 422 })
    expect(await providerAccountErrorMessage(response(), 'GROWATT')).toBe(
      'A Growatt recusou o usuário ou a senha. Confira e tente de novo.',
    )
    expect(await providerAccountErrorMessage(response(), 'NEPVIEWER')).toContain('A NEPViewer recusou')
    expect(brandLabel('OUTRA')).toBe('fabricante')
    expect(brandLabel(null)).toBe('fabricante')
    expect(brandLabel('toString')).toBe('fabricante')
  })
})

describe('Growatt fora das telas de conexão', () => {
  it('só a NEPViewer pode ser escolhida', () => {
    expect(PROVIDER_BRANDS.map((brand) => brand.value)).toEqual(['NEPVIEWER'])
  })

  it.each(['GROWATT', 'GROWATT_TOKEN'])('conexão %s existente continua sendo lida e nomeada', (provider) => {
    expect(parseProviderAccount({ ...BASE, provider }).provider).toBe(provider)
    expect(brandLabel(provider)).toBe('Growatt')
    expect(isGrowatt(provider)).toBe(true)
  })

  it.each([
    ['provider_unsupported', 'Essa marca não é mais suportada. Hoje a MPlacas conecta apenas inversores NEPViewer.'],
    ['provider_discontinued', 'A integração com essa marca foi desativada. Seu histórico continua disponível.'],
  ])('código %s vira texto em português', async (code, text) => {
    const response = new Response(JSON.stringify({ detail: code }), { status: 422 })
    expect(await providerAccountErrorMessage(response, 'GROWATT_TOKEN')).toBe(text)
  })

  it('códigos só da Growatt deixam de ter texto próprio e código herdado do protótipo não quebra', async () => {
    for (const code of ['provider_token_failed', 'provider_token_invalid', 'provider_login_blocked', 'constructor']) {
      const response = new Response(JSON.stringify({ detail: code }), { status: 422 })
      expect(await providerAccountErrorMessage(response)).toBe('Não foi possível concluir agora. Tente novamente.')
    }
  })
})
