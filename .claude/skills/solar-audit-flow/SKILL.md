---
name: solar-audit-flow
description: Use ao construir ou avaliar a apresentação do fluxo de auditoria da concessionária no Mplacas — produção → autoconsumo → injeção → reconhecimento → compensação → créditos → resultado financeiro. Cada divergência precisa de período, kWh, %, valor, severidade, fonte e ação recomendada.
---

# Solar Audit Flow — Mplacas

## Finalidade
Padronizar como uma divergência entre o que a usina produziu e o que a concessionária reconheceu é apresentada, de forma auditável.

## O fluxo (ordem fixa)
```
produção → autoconsumo → injeção → reconhecimento (concessionária) → compensação → créditos → resultado financeiro
```

## Quando usar
- Ao construir/revisar qualquer tela que compara dado da usina com dado da fatura/concessionária.

## Toda divergência apresentada precisa expor
- Período de referência.
- Valor em kWh.
- Valor em percentual.
- Valor financeiro correspondente (R$).
- Severidade.
- Fonte do dado (usina vs. concessionária).
- Nível de confiança/evidência.
- Recomendação de ação (quando aplicável).

## Procedimento
1. Nunca apresente um número de divergência sem indicar de qual lado do fluxo ele nasce (ex: "produção divergente" é diferente de "reconhecimento divergente").
2. Todo valor de divergência é rastreável até o endpoint/relatório que o originou — não é permitido um número "solto" sem origem clicável/identificável.
3. Diferencie explicitamente estimado (baseado em modelo) de confirmado (baseado em fatura processada).

## Anti-patterns
- Mostrar "divergência de 12%" sem dizer em qual estágio do fluxo ela ocorre.
- Misturar produção estimada com produção confirmada no mesmo número sem aviso.

## Checklist
- [ ] Estágio do fluxo identificado
- [ ] Todos os campos obrigatórios presentes (período, kWh, %, R$, severidade, fonte, ação)
- [ ] Estimado vs. confirmado diferenciado
