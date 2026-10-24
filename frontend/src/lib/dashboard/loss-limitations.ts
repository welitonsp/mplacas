// Limitações da taxonomia de perdas (ADR-083, etapa 3). O motor
// (`src/mplacas/photovoltaic/loss_taxonomy.py`) devolve a limitação de cada
// categoria em inglês técnico, no campo `limitation`. Texto de motor nunca
// aparece em inglês para o cliente: as frases conhecidas são traduzidas aqui;
// uma frase nova, ainda sem tradução, simplesmente não aparece (o teste
// `loss-limitations.test.ts` lista as frases do motor para pegar a lacuna).
const LIMITATION_PT: Readonly<Record<string, string>> = {
  'daily aggregates cannot distinguish recurring geometric shading':
    'Com dados só diários não dá para separar sombra recorrente de outras perdas.',
  'estimated percentage is missing reporting capacity, not confirmed energy loss':
    'O percentual é capacidade que deixou de reportar dados, não perda de energia confirmada.',
  'interval operating states are unavailable': 'Não há registro do estado de operação ao longo do dia.',
  'daily energy cannot separate outage from other loss mechanisms':
    'Com a energia do dia não dá para separar uma parada de outras perdas.',
  'technical availability requires interval operating-state telemetry':
    'Medir a disponibilidade exige registro do estado de operação ao longo do dia.',
  'daily energy and capacity ratio indicate risk, not confirmed clipping':
    'A energia do dia e a relação entre placas e inversor indicam risco, não limitação confirmada.',
  'confirmation requires interval AC power plateau detection':
    'Confirmar exigiria ver a potência do inversor travada no limite ao longo do dia.',
  'rain history is a proxy; cleaning events and soiling sensors are unavailable':
    'A chuva é só uma aproximação: não há registro de limpeza nem sensor de sujeira.',
  'thermal effect is modeled from daily ambient temperature and simplified NOCT':
    'O efeito do calor é estimado pela temperatura média do dia, com um modelo simplificado.',
  'persistent loss signal is not a component-level root-cause diagnosis':
    'Uma perda que se repete não aponta, sozinha, qual componente é a causa.',
}

export function limitationInPortuguese(limitation: string | null): string | null {
  if (limitation == null) return null
  return LIMITATION_PT[limitation.trim()] ?? null
}

export const KNOWN_ENGINE_LIMITATIONS: readonly string[] = Object.keys(LIMITATION_PT)
