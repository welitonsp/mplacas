// Painel do investidor com projeção completa (ADR-079) — números da usina de
// referência: R$ 11.200, ligada em set/2025, 1 fatura confirmada (R$ 264).
export const investorAvailablePayload = {
  plant_id: 'plant-1',
  unavailable_reason: null,
  investment_brl: '11200.00',
  commissioned_month: '2025-09',
  months_since_commissioning: 13,
  cycles_counted: 1,
  calculation_versions: ['0.3.0'],
  includes_pre_correction_cycles: false,
  low_confidence_baseline: true,
  indices: {
    cdi_12m_per_year: '0.1403',
    ipca_12m_per_year: '0.0458',
    as_of_month: '2026-09',
    source: 'Banco Central do Brasil — SGS 4391 (CDI) e 433 (IPCA)',
  },
  realized: {
    as_of_month: '2026-09',
    months_elapsed: 12,
    accumulated_savings_brl: '264.00',
    cycles_counted: 1,
    cdi_path_net_brl: '12496.24',
    solar_path_net_brl: '264.00',
    cdi_accumulated_percent: '14.03',
  },
  projection: {
    baseline_monthly_savings_brl: '264.00',
    irr_per_year: '0.3290',
    irr_real_per_year: '0.2711',
    cdi_net_per_year: '0.1332',
    npv_at_cdi_net_brl: '16204.01',
    payback_simple_months: 44,
    payback_discounted_months: 57,
    lifetime_savings_brl: '140925.60',
    wire_b_applied: true,
    patrimony: Array.from({ length: 26 }, (_, year) => year).map((year) => ({
      year,
      cdi_path_brl: String(11200 * 1.1332 ** year),
      // Economia de ~R$ 3.168/ano aplicada no CDI líquido: cruza perto do
      // payback descontado de 57 meses, como no cálculo real.
      solar_path_brl: String((3168 * (1.1332 ** year - 1)) / 0.1332),
    })),
  },
  premises: {
    cdi_per_year: '0.1403',
    ipca_per_year: '0.0458',
    tariff_growth_per_year: '0.0458',
    horizon_years: 25,
    degradation_per_year: '0.005',
    om_per_year_fraction: '0.005',
    inverter_replacement_year: 12,
    inverter_replacement_fraction: '0.15',
    long_term_income_tax: '0.15',
  },
}
