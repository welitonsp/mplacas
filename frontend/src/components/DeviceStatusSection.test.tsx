import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { PlantResource } from '../hooks/usePlantResource'
import type { DeviceDailyStatus, DeviceDailyStatusResponse } from '../lib/dashboard/device-contracts'
import { DeviceStatusSection } from './DeviceStatusSection'

function buildDevice(overrides: Partial<DeviceDailyStatus> = {}): DeviceDailyStatus {
  return {
    device_id: '11111111-1111-1111-1111-111111111111',
    serial_number: 'SN-1234567890',
    reporting_status: 'REPORTED',
    production_kwh: '12.500',
    last_reported_date: '2026-08-11',
    rendimento: '2.437',
    rendimento_median: '3.390',
    relative_to_own_median: '0.719',
    relative_to_own_median_deviation_percent: '-28.1',
    yield_status: 'DROPPED',
    yield_unavailable_reason: null,
    ...overrides,
  }
}

function buildStatus(overrides: Partial<DeviceDailyStatusResponse> = {}): DeviceDailyStatusResponse {
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
    devices: [buildDevice()],
    ...overrides,
  }
}

function buildResource(
  overrides: Partial<PlantResource<DeviceDailyStatusResponse>> = {}
): PlantResource<DeviceDailyStatusResponse> {
  return {
    data: buildStatus(),
    status: 'success',
    error: null,
    lastUpdated: new Date('2026-08-11T00:00:00Z'),
    refetch: vi.fn(),
    ...overrides,
  }
}

describe('DeviceStatusSection', () => {
  it('lista o inversor silencioso marcado como "Não reportou" — nunca omitido, nunca 0', () => {
    const resource = buildResource({
      data: buildStatus({
        device_count: 2,
        reporting_device_count: 1,
        devices: [
          buildDevice(),
          buildDevice({
            device_id: '22222222-2222-2222-2222-222222222222',
            serial_number: 'SN-0987654321',
            reporting_status: 'NOT_REPORTED',
            production_kwh: null,
            last_reported_date: '2026-07-28',
            rendimento: null,
            rendimento_median: null,
            relative_to_own_median: null,
            relative_to_own_median_deviation_percent: null,
            yield_status: 'UNKNOWN',
            yield_unavailable_reason: 'NOT_REPORTED',
          }),
        ],
      }),
    })

    render(<DeviceStatusSection resource={resource} />)

    expect(screen.getByText('SN-1234567890')).toBeInTheDocument()
    expect(screen.getByText('SN-0987654321')).toBeInTheDocument()

    const silentCard = screen.getByText('SN-0987654321').closest('div') as HTMLElement
    expect(within(silentCard).getByText('Não reportou')).toBeInTheDocument()
    expect(within(silentCard).getByText(/Última leitura registrada: 28\/07\/2026/)).toBeInTheDocument()
    // Nunca um "0 kWh" fabricado para quem não reportou.
    expect(within(silentCard).queryByText(/kWh/)).not.toBeInTheDocument()
  })

  it('distingue "não reportou" de um inversor que reportou exatamente 0 kWh', () => {
    const resource = buildResource({
      data: buildStatus({
        devices: [
          buildDevice({
            reporting_status: 'REPORTED',
            production_kwh: '0',
            yield_status: 'NORMAL',
            relative_to_own_median: '1',
            relative_to_own_median_deviation_percent: '0',
          }),
        ],
      }),
    })

    render(<DeviceStatusSection resource={resource} />)

    expect(screen.getByText('0 kWh')).toBeInTheDocument()
    expect(screen.queryByText('Não reportou')).not.toBeInTheDocument()
  })

  it('UNKNOWN nunca é apresentado como saudável — mostra o motivo específico, não "Rendimento normal"', () => {
    const resource = buildResource({
      data: buildStatus({
        devices: [
          buildDevice({
            reporting_status: 'REPORTED',
            rendimento: null,
            rendimento_median: null,
            relative_to_own_median: null,
            relative_to_own_median_deviation_percent: null,
            yield_status: 'UNKNOWN',
            yield_unavailable_reason: 'INSUFFICIENT_DEVICE_HISTORY',
          }),
        ],
      }),
    })

    render(<DeviceStatusSection resource={resource} />)

    expect(screen.getByText('Sem avaliação de rendimento')).toBeInTheDocument()
    expect(screen.getByText('Histórico insuficiente para comparar (mínimo 5 dias).')).toBeInTheDocument()
    expect(screen.queryByText('Rendimento normal')).not.toBeInTheDocument()
  })

  // P3 (revisão independente de T1c, 2026-08-12): o parser degrada um
  // `yield_unavailable_reason` desconhecido para `null`
  // (`device-contracts.ts::nullableYieldUnavailableReason`), mas nada até
  // aqui provava que essa degradação chega à tela como frase neutra — nunca
  // como "saudável".
  it('motivo de indisponibilidade desconhecido cai numa frase neutra, nunca em "Rendimento normal"', () => {
    const resource = buildResource({
      data: buildStatus({
        devices: [
          buildDevice({
            reporting_status: 'REPORTED',
            relative_to_own_median: null,
            relative_to_own_median_deviation_percent: null,
            yield_status: 'UNKNOWN',
            yield_unavailable_reason: null,
          }),
        ],
      }),
    })

    render(<DeviceStatusSection resource={resource} />)

    expect(screen.getByText('Sem avaliação de rendimento')).toBeInTheDocument()
    expect(screen.getByText('Motivo não informado pelo backend.')).toBeInTheDocument()
    expect(screen.queryByText('Rendimento normal')).not.toBeInTheDocument()
    expect(screen.queryByText('Queda de rendimento')).not.toBeInTheDocument()
  })

  // P1 nº2 (revisão independente de T1c, 2026-08-12): decidir o sinal a
  // partir do valor BRUTO (antes de arredondar) produzia "−0%" para desvios
  // como -0.4/-0.05 e "+0%" para +0.4 — exatamente a faixa mais comum de um
  // inversor saudável (desvio quase nulo). Cobre a faixa que quebrava, mais o
  // zero exato, provando que nenhum "−0%"/"+0%" sai na tela.
  it.each([
    ['-0.4', 'DROPPED' as const],
    ['-0.05', 'DROPPED' as const],
    ['0.4', 'NORMAL' as const],
    ['0', 'NORMAL' as const],
  ])(
    'desvio bruto %s nunca produz "-0%%" nem "+0%%" — mostra texto honesto de "em linha com a mediana"',
    (deviationPercent, yieldStatus) => {
      const resource = buildResource({
        data: buildStatus({
          devices: [
            buildDevice({
              reporting_status: 'REPORTED',
              relative_to_own_median_deviation_percent: deviationPercent,
              yield_status: yieldStatus,
            }),
          ],
        }),
      })

      render(<DeviceStatusSection resource={resource} />)

      expect(screen.queryByText(/-0%/)).not.toBeInTheDocument()
      expect(screen.queryByText(/\+0%/)).not.toBeInTheDocument()
      expect(screen.getByText('Em linha com a mediana deste inversor.')).toBeInTheDocument()
    }
  )

  it('cada motivo de indisponibilidade de rendimento tem frase própria', () => {
    const resource = buildResource({
      data: buildStatus({
        devices: [
          buildDevice({
            reporting_status: 'REPORTED',
            relative_to_own_median: null,
            relative_to_own_median_deviation_percent: null,
            yield_status: 'UNKNOWN',
            yield_unavailable_reason: 'NO_IRRADIATION_READING',
          }),
        ],
      }),
    })

    render(<DeviceStatusSection resource={resource} />)

    expect(screen.getByText('Sem leitura de irradiação neste dia.')).toBeInTheDocument()
  })

  it('lista vazia de inversores é um estado explícito, não um erro', () => {
    const resource = buildResource({
      data: buildStatus({ device_count: 0, reporting_device_count: 0, devices: [] }),
    })

    render(<DeviceStatusSection resource={resource} />)

    expect(screen.getByText('Nenhum inversor cadastrado nesta usina ainda.')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('mostra o rótulo do dia sem produção quando a usina nunca reportou nada', () => {
    const resource = buildResource({
      data: buildStatus({
        observation_date: null,
        observation_date_unavailable_reason: 'NO_PRODUCTION_HISTORY',
        devices: [buildDevice({ reporting_status: 'NOT_REPORTED', production_kwh: null, last_reported_date: null })],
      }),
    })

    render(<DeviceStatusSection resource={resource} />)

    expect(screen.getByText(/Nenhum dia com produção registrada ainda/)).toBeInTheDocument()
    expect(screen.getByText('Nunca reportou dado nesta usina.')).toBeInTheDocument()
  })

  it('mostra erro com retry quando o recurso falha, sem travar em carregamento', () => {
    const refetch = vi.fn()
    const resource = buildResource({ status: 'error', data: null, error: 'Erro ao buscar status dos inversores.', refetch })

    render(<DeviceStatusSection resource={resource} />)

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Erro ao buscar status dos inversores.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }))
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('mostra esqueleto de carregamento enquanto o recurso ainda não resolveu', () => {
    const resource = buildResource({ status: 'loading', data: null, error: null })

    render(<DeviceStatusSection resource={resource} />)

    expect(screen.getByRole('status', { name: 'Carregando inversores' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
