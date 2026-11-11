// Leitura de números digitados em formulários pt-BR. As duas funções devolvem
// o texto que o backend espera ("4.4", "15000.00"); `null` para vazio e
// `undefined` para inválido.

// Medidas (kWp, graus, coordenadas): aceita vírgula decimal ("4,4") e o ponto
// como decimal ("4.4"). O ponto só vira milhar quando há vírgula ("1.234,5").
// NÃO use para dinheiro: "15.000" aqui vale 15, não quinze mil.
export function normalizeMeasurement(raw: string): string | null | undefined {
  const trimmed = raw.trim().replace(/\s/g, '')
  if (trimmed === '') return null
  const normalized = trimmed.includes(',') ? trimmed.replace(/\./g, '').replace(',', '.') : trimmed
  if (!/^-?\d+(\.\d+)?$/.test(normalized)) return undefined
  return normalized
}

// Dinheiro em reais, padrão pt-BR: "." é milhar e "," é decimal. Aceita o
// prefixo "R$". Regras para os casos ambíguos:
// - com vírgula: a parte inteira é "1500" ou agrupada de 3 em 3 ("1.500");
//   qualquer outro uso do ponto ("1.5,00") é inválido, não adivinhamos;
// - sem vírgula, ponto seguido de exatamente 3 dígitos, em grupos
//   ("15.000", "1.500.000", "1.234"): milhar. Quem digita "15.000" quer
//   quinze mil, e ler como 15,00 erraria o retorno do cliente. O primeiro
//   grupo não pode começar com 0: "0.500" é 0,50, não 500;
// - sem vírgula, ponto em qualquer outro formato ("1500.50", "12.5"): ponto
//   decimal, como vem de planilhas e calculadoras;
// - negativo e lixo são inválidos. Zero é número válido; quem chama decide
//   se aceita.
export function normalizeMoneyBrl(raw: string): string | null | undefined {
  const text = raw.trim().replace(/^R\$\s*/i, '').replace(/\s/g, '')
  if (text === '') return null
  if (text.includes(',')) {
    if (!/^(\d+|[1-9]\d{0,2}(\.\d{3})+),\d+$/.test(text)) return undefined
    return text.replace(/\./g, '').replace(',', '.')
  }
  if (/^[1-9]\d{0,2}(\.\d{3})+$/.test(text)) return text.replace(/\./g, '')
  if (/^\d+(\.\d+)?$/.test(text)) return text
  return undefined
}
