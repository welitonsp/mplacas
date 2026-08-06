---
name: financial-display-rules
description: Use ao exibir qualquer valor financeiro relevante no Mplacas (economia, investimento, custo, payback, ROI, LCOE) — obriga moeda, período, nominal/real, estimado/confirmado, premissas, arredondamento, data-base e memória de cálculo quando aplicável.
---

# Financial Display Rules — Mplacas

## Finalidade
Garantir que todo número financeiro na UI é auditável — nunca "só um número bonito".

## Quando usar
- Sempre que um valor em R$/percentual financeiro for exibido.

## Obrigatório, quando aplicável
- Moeda (R$).
- Período de referência.
- Nominal ou real (valores corrigidos por inflação, se aplicável).
- Estimado ou confirmado — nomenclatura já usada pelo backend (`unavailable_reason`, `savings_unavailable_reason` etc.).
- Fonte/premissas do cálculo (ex: tarifa usada, taxa de desconto).
- Arredondamento consistente com o que o backend já aplica — não arredondar diferente no frontend.
- Data-base do cálculo.
- Cenário, quando há mais de um (ex: projeção otimista/conservadora, se existir).

## Procedimento
1. Confirme que o campo já vem pronto do backend (`FinancialReturnSection`, `financial_return_service.py`) — nunca calcule payback/ROI/economia no frontend.
2. Se o valor tem `*_unavailable_reason`, mostre o motivo tipado, nunca R$ 0,00.
3. Todo valor financeiro relevante para decisão do usuário (ex: economia estimada) tem o período e a premissa visíveis perto do número, não só num tooltip escondido.

## Anti-patterns
- Calcular ROI/payback no frontend a partir de peças soltas.
- Omitir se um valor é estimado ou confirmado.
- `R$ 0,00` para representar "indisponível".

## Checklist
- [ ] Todo valor tem moeda + período visíveis
- [ ] Estimado/confirmado explícito
- [ ] Nenhum cálculo financeiro feito no frontend
- [ ] `*_unavailable_reason` tratado, nunca zero
