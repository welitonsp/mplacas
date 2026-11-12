// Parser mínimo de `GET /energy/cycles/{bill_id}`: só o que a resposta de
// "fatura confirmada" precisa — a economia estimada daquele ciclo e o motivo
// quando ela não existe. O resto do payload (indicadores, diário) continua
// sendo lido pelo parser do painel executivo.
//
// `estimated_savings_brl` chega como string (`Decimal`) ou `null`; `null` nunca
// vira 0 (ver skill `financial-display-rules`).

export interface CycleSavings {
  billId: string
  // `null` = sem economia calculada para o ciclo; ver `unavailableReason`.
  savingsBrl: number | null
  unavailableReason: string | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function parseCycleSavings(payload: unknown): CycleSavings {
  if (!isRecord(payload) || !isRecord(payload.indicators)) throw new Error('Resposta inválida da API.')
  const { bill_id: billId } = payload
  if (typeof billId !== 'string' || billId === '') throw new Error('Resposta inválida da API: bill_id')
  const { estimated_savings_brl: raw, savings_unavailable_reason: reason } = payload.indicators
  let savingsBrl: number | null = null
  if (typeof raw === 'string' && raw.trim() !== '') {
    const numeric = Number(raw)
    if (!Number.isFinite(numeric)) throw new Error('Resposta inválida da API: estimated_savings_brl')
    savingsBrl = numeric
  } else if (raw !== null && raw !== undefined) {
    throw new Error('Resposta inválida da API: estimated_savings_brl')
  }
  return {
    billId,
    savingsBrl,
    unavailableReason: typeof reason === 'string' && reason.trim() !== '' ? reason : null,
  }
}
