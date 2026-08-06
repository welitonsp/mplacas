---
name: data-quality-ui
description: Use ao exibir qualquer dado energético/financeiro no Mplacas — obriga a expor unidade, período, qualidade (medido/estimado/corrigido/confirmado) e tratar indisponibilidade como estado explícito, nunca como zero ou ausência silenciosa. Regra central do projeto, já aplicada em EstimatedSavingsCard e equivalentes.
---

# Data Quality UI — Mplacas

## Finalidade
Garantir que todo dado apresentado ao usuário é honesto sobre sua origem, período e confiabilidade — é a regra mais importante do projeto, violada = bug grave, não detalhe.

## Quando usar
- Sempre que um valor numérico/percentual/monetário for exibido na UI.

## Obrigatório, quando aplicável
- **Valor**: sempre com unidade visível (`kWh`, `R$`, `%`) — nunca número nu sem contexto.
- **Período**: a que ciclo/data o valor se refere.
- **Origem/método**: de onde veio (medido do provedor, modelado, calculado).
- **Qualidade**: medido, estimado, corrigido, confirmado — usar a nomenclatura que o backend já define no campo (`data_quality_status`, `*_nature`), não inventar rótulo novo.
- **Indisponibilidade**: quando o backend expõe um `*_unavailable_reason`, a UI mostra esse motivo tipado — nunca substitui por `0`, `R$ 0,00`, `0%` ou string vazia sem explicação.

## Procedimento
1. Antes de renderizar um valor, verifique se o contrato do backend (`frontend/src/lib/dashboard/*-contracts.ts`) já carrega um campo de indisponibilidade correspondente — se sim, trate os dois casos (disponível/indisponível) explicitamente no componente.
2. Nunca faça `value ?? 0` ou `value || '-'` genérico para esconder `null`/indisponibilidade — isso mascara a causa real. Trate cada `*_unavailable_reason` com a mensagem específica que já existe (`baselineUnavailableMessage` e equivalentes).
3. Distinga visualmente (não só textualmente) dado provisório/parcial de dado confirmado — badge ou selo, não cor isolada.
4. Se um componente novo precisar de composição de grandezas físicas ou financeiras (multiplicação, soma) que o backend não forneceu pronto, isso é uma violação do ADR-012 — pare e escale, não implemente.

## Anti-patterns
- `R$ ${value ?? 0}` — fabrica um valor monetário falso.
- Esconder o card inteiro quando o dado está indisponível, sem explicar por quê (a menos que a ADR relevante explicitamente decida isso).
- Misturar dado estimado e confirmado na mesma cor/estilo sem diferenciação.

## Checklist
- [ ] Unidade sempre visível
- [ ] Indisponibilidade tratada com o motivo tipado do backend, nunca como zero
- [ ] Nenhuma composição de grandeza feita no frontend
- [ ] Provisório/confirmado visualmente diferenciados
