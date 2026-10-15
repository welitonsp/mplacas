import { describe, expect, it } from 'vitest'
import { parsePlantSetup } from './plant-setup-contracts'

const ITEMS = [
  'LOCATION',
  'DC_CAPACITY',
  'COMMISSIONED_ON',
  'ORIENTATION',
  'MODULE_TECHNOLOGY',
  'INVESTMENT',
  'CONFIRMED_BILL',
].map((key, index) => ({ key, done: index < 2 }))

const valid = {
  plant_id: 'plant-1',
  name: 'Casa',
  technical: {
    plant_id: 'plant-1',
    dc_capacity_kwp: '4.400',
    ac_capacity_kw: null,
    array_tilt_degrees: null,
    array_azimuth_degrees: '0.00',
    module_technology: 'MONOCRYSTALLINE_SILICON',
    commissioned_on: '2025-09-01',
    devices: [{ device_id: 'd1', serial_number: 'INV', dc_capacity_kwp: null, ac_capacity_kw: null }],
  },
  latitude: '-17.740000',
  longitude: null,
  financial: { plant_id: 'plant-1', investment_amount_brl: '11200.00', investment_recorded_on: null },
  confirmed_bills: 1,
  pending_bills: 0,
  items: ITEMS,
  completed: 2,
  total: 7,
}

describe('plant-setup-contracts', () => {
  it('lê o cadastro mantendo números como string e ausentes como null', () => {
    const setup = parsePlantSetup(valid)
    expect(setup.dcCapacityKwp).toBe('4.400')
    expect(setup.acCapacityKw).toBeNull()
    expect(setup.longitude).toBeNull()
    expect(setup.moduleTechnology).toBe('MONOCRYSTALLINE_SILICON')
    expect(setup.deviceCount).toBe(1)
    expect(setup.items).toHaveLength(7)
    expect(setup.completed).toBe(2)
  })

  it('recusa chave de item, tecnologia ou contagem desconhecidas', () => {
    expect(() => parsePlantSetup({ ...valid, items: [{ key: 'NOVO', done: true }] })).toThrow(/items\[\]\.key/)
    expect(() =>
      parsePlantSetup({ ...valid, technical: { ...valid.technical, module_technology: 'GRAFENO' } }),
    ).toThrow(/module_technology/)
    expect(() => parsePlantSetup({ ...valid, completed: -1 })).toThrow(/completed/)
    expect(() => parsePlantSetup({ ...valid, technical: null })).toThrow(/technical/)
  })
})
