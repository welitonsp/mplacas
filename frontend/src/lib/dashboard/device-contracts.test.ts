import { describe, expect, it } from 'vitest'
import {
  observationDateUnavailableMessage,
  parseDeviceDailyStatus,
  yieldUnavailableMessage,
} from './device-contracts'

function buildDevicePayload(overrides: Record<string, unknown> = {}) {
  return {
    device_id: '11111111-1111-1111-1111-111111111111',
    serial_number: 'SN-A',
    reporting_status: 'REPORTED',
    production_kwh: '9.750',
    last_reported_date: '2026-08-11',
    rendimento: '1.993',
    rendimento_median: '1.993',
    relative_to_own_median: '1.000',
    relative_to_own_median_deviation_percent: '0.0',
    yield_status: 'NORMAL',
    yield_unavailable_reason: null,
    ...overrides,
  }
}

function buildEnvelopePayload(overrides: Record<string, unknown> = {}) {
  return {
    plant_id: 'plant-1',
    observation_date: '2026-08-11',
    observation_date_unavailable_reason: null,
    irradiation_kwh_m2: '4.890',
    irradiation_unavailable_reason: null,
    device_count: 1,
    reporting_device_count: 1,
    device_normal_threshold: '0.85',
    units: {
      production: 'kWh',
      irradiation: 'kWh/m2',
      rendimento: 'kWh/(kWh/m2)',
      relative_to_own_median: 'ratio',
      relative_to_own_median_deviation: 'percent',
    },
    devices: [buildDevicePayload()],
    ...overrides,
  }
}

describe('parseDeviceDailyStatus', () => {
  // Caso obrigatório 1: payload válido.
  it('faz parse de um envelope válido com um inversor reportando normalmente', () => {
    const result = parseDeviceDailyStatus(buildEnvelopePayload())

    expect(result.plant_id).toBe('plant-1')
    expect(result.observation_date).toBe('2026-08-11')
    expect(result.device_count).toBe(1)
    expect(result.reporting_device_count).toBe(1)
    expect(result.device_normal_threshold).toBe('0.85')
    expect(result.units).toEqual({
      production: 'kWh',
      irradiation: 'kWh/m2',
      rendimento: 'kWh/(kWh/m2)',
      relative_to_own_median: 'ratio',
      relative_to_own_median_deviation: 'percent',
    })
    expect(result.devices).toHaveLength(1)
    expect(result.devices[0]).toEqual(buildDevicePayload())
  })

  // Caso obrigatório 2: campo null/indisponível — inversor mudo (Restrição 1
  // do ADR-074) e usina sem nenhum dia de produção.
  it('preserva um inversor silencioso (NOT_REPORTED) em vez de omiti-lo ou zerá-lo', () => {
    const result = parseDeviceDailyStatus(
      buildEnvelopePayload({
        device_count: 2,
        reporting_device_count: 1,
        devices: [
          buildDevicePayload(),
          buildDevicePayload({
            device_id: '22222222-2222-2222-2222-222222222222',
            serial_number: 'SN-SILENT',
            reporting_status: 'NOT_REPORTED',
            production_kwh: null,
            last_reported_date: '2026-07-20',
            rendimento: null,
            rendimento_median: null,
            relative_to_own_median: null,
            relative_to_own_median_deviation_percent: null,
            yield_status: 'UNKNOWN',
            yield_unavailable_reason: 'NOT_REPORTED',
          }),
        ],
      })
    )

    expect(result.devices).toHaveLength(2)
    const silent = result.devices[1]
    expect(silent.reporting_status).toBe('NOT_REPORTED')
    expect(silent.production_kwh).toBeNull()
    // Nunca confundido com produção zero.
    expect(silent.production_kwh).not.toBe('0')
    expect(silent.yield_status).toBe('UNKNOWN')
    expect(silent.yield_unavailable_reason).toBe('NOT_REPORTED')
    expect(silent.last_reported_date).toBe('2026-07-20')
    expect(silent.relative_to_own_median_deviation_percent).toBeNull()
  })

  it('faz parse do dia sem nenhuma produção histórica (observation_date null + motivo)', () => {
    const result = parseDeviceDailyStatus(
      buildEnvelopePayload({
        observation_date: null,
        observation_date_unavailable_reason: 'NO_PRODUCTION_HISTORY',
        irradiation_kwh_m2: null,
        irradiation_unavailable_reason: 'NO_CLIMATE_OBSERVATION',
        reporting_device_count: 0,
        devices: [
          buildDevicePayload({
            production_kwh: null,
            last_reported_date: null,
            rendimento: null,
            rendimento_median: null,
            relative_to_own_median: null,
            relative_to_own_median_deviation_percent: null,
            reporting_status: 'NOT_REPORTED',
            yield_status: 'UNKNOWN',
            yield_unavailable_reason: 'NOT_REPORTED',
          }),
        ],
      })
    )

    expect(result.observation_date).toBeNull()
    expect(result.observation_date_unavailable_reason).toBe('NO_PRODUCTION_HISTORY')
    expect(result.irradiation_kwh_m2).toBeNull()
    expect(result.irradiation_unavailable_reason).toBe('NO_CLIMATE_OBSERVATION')
    // Mesmo sem nenhum dia de produção, o device cadastrado continua listado.
    expect(result.devices).toHaveLength(1)
  })

  it('nunca deriva UNKNOWN como saudável: preserva o motivo quando o device reportou mas o rendimento não pôde ser avaliado', () => {
    const result = parseDeviceDailyStatus(
      buildEnvelopePayload({
        devices: [
          buildDevicePayload({
            rendimento: null,
            rendimento_median: null,
            relative_to_own_median: null,
            relative_to_own_median_deviation_percent: null,
            yield_status: 'UNKNOWN',
            yield_unavailable_reason: 'INSUFFICIENT_DEVICE_HISTORY',
          }),
        ],
      })
    )

    const device = result.devices[0]
    expect(device.reporting_status).toBe('REPORTED')
    expect(device.yield_status).toBe('UNKNOWN')
    expect(device.yield_status).not.toBe('NORMAL')
    expect(device.yield_unavailable_reason).toBe('INSUFFICIENT_DEVICE_HISTORY')
    expect(device.relative_to_own_median_deviation_percent).toBeNull()
  })

  it('lista vazia de devices é um estado válido, não erro', () => {
    const result = parseDeviceDailyStatus(
      buildEnvelopePayload({ device_count: 0, reporting_device_count: 0, devices: [] })
    )
    expect(result.devices).toEqual([])
  })

  // Caso obrigatório 3: payload malformado.
  it('lança erro para payload que não é um objeto', () => {
    expect(() => parseDeviceDailyStatus(null)).toThrow('Resposta inválida da API.')
    expect(() => parseDeviceDailyStatus('boom')).toThrow('Resposta inválida da API.')
  })

  it('lança erro quando plant_id está ausente', () => {
    const payload = buildEnvelopePayload()
    delete (payload as Record<string, unknown>).plant_id
    expect(() => parseDeviceDailyStatus(payload)).toThrow(/plant_id/)
  })

  it('lança erro quando devices não é um array', () => {
    expect(() =>
      parseDeviceDailyStatus(buildEnvelopePayload({ devices: 'not-an-array' }))
    ).toThrow(/devices/)
  })

  it('lança erro quando um item de devices[] não é um objeto', () => {
    expect(() => parseDeviceDailyStatus(buildEnvelopePayload({ devices: [null] }))).toThrow(
      /devices\[\]/
    )
  })

  it('lança erro quando reporting_status vem fora do vocabulário conhecido', () => {
    expect(() =>
      parseDeviceDailyStatus(
        buildEnvelopePayload({ devices: [buildDevicePayload({ reporting_status: 'OFFLINE' })] })
      )
    ).toThrow(/reporting_status/)
  })

  it('lança erro quando yield_status vem fora do vocabulário conhecido', () => {
    expect(() =>
      parseDeviceDailyStatus(
        buildEnvelopePayload({ devices: [buildDevicePayload({ yield_status: 'HEALTHY' })] })
      )
    ).toThrow(/yield_status/)
  })

  it('um yield_unavailable_reason desconhecido vira null em vez de lançar (motivo futuro tolerado)', () => {
    const result = parseDeviceDailyStatus(
      buildEnvelopePayload({
        devices: [
          buildDevicePayload({ yield_status: 'UNKNOWN', yield_unavailable_reason: 'FUTURE_REASON' }),
        ],
      })
    )
    expect(result.devices[0].yield_unavailable_reason).toBeNull()
  })

  it('lança erro quando device_count não é um número', () => {
    expect(() => parseDeviceDailyStatus(buildEnvelopePayload({ device_count: '2' }))).toThrow(
      /device_count/
    )
  })

  it('lança erro quando units está ausente ou malformado', () => {
    expect(() => parseDeviceDailyStatus(buildEnvelopePayload({ units: null }))).toThrow(/units/)
    expect(() =>
      parseDeviceDailyStatus(buildEnvelopePayload({ units: { production: 'kWh' } }))
    ).toThrow(/units|irradiation/)
  })

  it('lança erro quando units.relative_to_own_median_deviation está ausente', () => {
    expect(() =>
      parseDeviceDailyStatus(
        buildEnvelopePayload({
          units: {
            production: 'kWh',
            irradiation: 'kWh/m2',
            rendimento: 'kWh/(kWh/m2)',
            relative_to_own_median: 'ratio',
          },
        })
      )
    ).toThrow(/relative_to_own_median_deviation/)
  })

  // ADR-074 correção de rota (revisão P1 de T1c, 2026-08-12): o desvio
  // percentual pronto vem do backend (`devices/metrics.py::assess_devices`)
  // — este parser só converte string→tipo, nunca recalcula
  // `(razão − 1) × 100` a partir de `relative_to_own_median`.
  it('faz parse de relative_to_own_median_deviation_percent sem recalculá-lo a partir da razão', () => {
    const result = parseDeviceDailyStatus(
      buildEnvelopePayload({
        devices: [
          buildDevicePayload({
            relative_to_own_median: '0.719',
            // Deliberadamente NÃO igual a (0.719 - 1) * 100: prova que o
            // parser devolve o valor do backend tal como veio, em vez de
            // recomputar a partir de `relative_to_own_median`.
            relative_to_own_median_deviation_percent: '-28.1',
          }),
        ],
      })
    )

    expect(result.devices[0].relative_to_own_median_deviation_percent).toBe('-28.1')
    expect(result.units.relative_to_own_median_deviation).toBe('percent')
  })

  it('relative_to_own_median_deviation_percent é null quando ausente do payload', () => {
    const result = parseDeviceDailyStatus(
      buildEnvelopePayload({
        devices: [buildDevicePayload({ relative_to_own_median_deviation_percent: null })],
      })
    )
    expect(result.devices[0].relative_to_own_median_deviation_percent).toBeNull()
  })
})

describe('yieldUnavailableMessage', () => {
  it('devolve uma frase própria por motivo, nunca um texto genérico', () => {
    expect(yieldUnavailableMessage('NOT_REPORTED')).toBe('Não reportou neste dia.')
    expect(yieldUnavailableMessage('NO_IRRADIATION_READING')).toBe(
      'Sem leitura de irradiação neste dia.'
    )
    expect(yieldUnavailableMessage('INSUFFICIENT_DEVICE_HISTORY')).toBe(
      'Histórico insuficiente para comparar (mínimo 5 dias).'
    )
  })
})

describe('observationDateUnavailableMessage', () => {
  it('explica a ausência de qualquer dia de produção', () => {
    expect(observationDateUnavailableMessage('NO_PRODUCTION_HISTORY')).toMatch(
      /produção registrada/
    )
  })
})
