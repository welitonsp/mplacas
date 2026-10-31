import { describe, expect, it } from 'vitest'
import {
  buildInvitationLink,
  clientErrorMessage,
  parseClientInvitation,
  parseClients,
  parseFirstConnection,
  parseMe,
  readInvitationToken,
} from './onboarding-contracts'
import { parsePlantSetup } from './plant-setup-contracts'

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('convite (ADR-093)', () => {
  it('lê o token do fragmento, com ou sem "token="', () => {
    expect(readInvitationToken('#token=abc123')).toBe('abc123')
    expect(readInvitationToken('#abc123')).toBe('abc123')
    expect(readInvitationToken('')).toBeNull()
    expect(readInvitationToken('#outra=coisa')).toBeNull()
  })

  it('monta o link com o token no fragmento, nunca na query', () => {
    const link = buildInvitationLink('https://mplacas-frontend.pages.dev/', 'a+b/c')
    expect(link).toBe('https://mplacas-frontend.pages.dev/convite#token=a%2Bb%2Fc')
    expect(new URL(link).search).toBe('')
    expect(readInvitationToken(new URL(link).hash)).toBe('a+b/c')
  })
})

describe('parsers', () => {
  it('parseMe exige papel conhecido', () => {
    expect(
      parseMe({ username: 'a@b.c', role: 'ADMIN', organization_name: 'X', is_platform_operator: true }),
    ).toEqual({ username: 'a@b.c', role: 'ADMIN', organizationName: 'X', isPlatformOperator: true })
    expect(() => parseMe({ role: 'ROOT', is_platform_operator: true })).toThrow()
  })

  it('parseClients e parseClientInvitation', () => {
    const [client] = parseClients({
      items: [
        {
          organization_id: 'o1',
          name: 'Rogério',
          slug: 'rogerio',
          active: true,
          created_at: '2026-10-31T10:00:00Z',
          users: 0,
          plants: 0,
          connections: 0,
          admin_username: 'r@x.com',
          invitation_pending_until: '2026-11-03T10:00:00Z',
        },
      ],
    })
    expect(client.adminUsername).toBe('r@x.com')
    expect(() => parseClients({ items: [{ organization_id: 'o1' }] })).toThrow()
    expect(
      parseClientInvitation({
        organization_id: 'o1',
        invitation: { username: 'r@x.com', expires_at: '2026-11-03T10:00:00Z', token: 't' },
      }).token,
    ).toBe('t')
  })

  it('parseFirstConnection recusa origem desconhecida', () => {
    const ok = parseFirstConnection({
      plant_id: 'p1',
      plant_name: 'Casa',
      connection: { status: 'CONECTADA', devices_found: 1 },
      auto_filled: { dc_capacity_kwp: 'BRAND', array_tilt_degrees: 'ESTIMATE' },
    })
    expect(ok.autoFilled).toEqual({ dc_capacity_kwp: 'BRAND', array_tilt_degrees: 'ESTIMATE' })
    expect(() =>
      parseFirstConnection({
        plant_id: 'p1',
        plant_name: 'Casa',
        connection: {},
        auto_filled: { location: 'CHUTE' },
      }),
    ).toThrow()
  })

  it('traduz erros do cadastro de cliente', async () => {
    expect(await clientErrorMessage(json({ detail: 'client_admin_username_invalid' }, 422))).toBe(
      'Informe um e-mail válido para o cliente.',
    )
    expect(await clientErrorMessage(json({ detail: 'x' }, 403))).toMatch(/dono da plataforma/)
  })

  it('setup: needs_review é opcional e vira booleano', () => {
    const base = {
      plant_id: 'p1',
      name: 'Casa',
      technical: { devices: [], module_technology: null },
      financial: {},
      latitude: null,
      longitude: null,
      confirmed_bills: 0,
      pending_bills: 0,
      completed: 1,
      total: 2,
    }
    const setup = parsePlantSetup({
      ...base,
      items: [
        { key: 'ORIENTATION', done: true, needs_review: true },
        { key: 'LOCATION', done: true },
      ],
    })
    expect(setup.items.map((item) => item.needsReview)).toEqual([true, false])
  })
})
