import { describe, expect, it } from 'vitest'
import { savingsUnavailableMessage } from './contracts'

describe('savingsUnavailableMessage', () => {
  it('explica cada motivo do backend sem nunca mostrar R$ 0,00', () => {
    expect(savingsUnavailableMessage('TARIFF_NOT_AVAILABLE')).toMatch(/tarifa/)
    expect(savingsUnavailableMessage('NO_CONSUMPTION_DATA')).toMatch(/consumo/)
    expect(savingsUnavailableMessage('NO_PRODUCTION_DATA')).toMatch(/produção do inversor/)
    expect(savingsUnavailableMessage('OUTRO')).not.toMatch(/R\$/)
  })
})
