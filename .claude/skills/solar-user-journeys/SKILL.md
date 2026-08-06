---
name: solar-user-journeys
description: Use ao desenhar ou avaliar um fluxo de usuário no Mplacas — mapeia as jornadas reais (dono de usina checando saúde, revisando fatura pendente, investigando queda de produção) para garantir que a UI resolve a tarefa real, não uma tarefa genérica de dashboard solar.
---

# Solar User Journeys — Mplacas

## Finalidade
Ancorar decisões de UX nas tarefas reais do usuário do Mplacas, não em um dashboard solar genérico.

## Quando usar
- Ao desenhar um fluxo novo (ex: onboarding de integração, revisão de fatura).
- Ao avaliar se uma tela resolve a pergunta que o usuário realmente tem.

## Jornadas principais confirmadas pelo produto
1. **Checagem rápida de saúde** — "minha usina está bem hoje?" (hero, diagnóstico crítico).
2. **Revisão de fatura pendente** — usuário confirma/rejeita uma fatura capturada via Telegram/upload antes da consolidação mensal.
3. **Investigação de queda de produção** — usuário percebe produção baixa e quer entender a causa (perdas, clima, sujeira, sombra).
4. **Acompanhamento financeiro** — economia, retorno do investimento, créditos de energia.
5. **Troca de usina ativa** (multiusina, ADR-069) — usuário com mais de uma usina muda o contexto ativo.
6. **Configuração técnica inicial** — preencher inclinação, azimute, tecnologia do módulo, potência dos inversores (pré-requisito para performance/perdas serem calculados — ver `solar-domain-ui`).

## Procedimento
1. Ao propor uma tela/fluxo novo, identifique a qual jornada ele serve — se não serve nenhuma das reais, questione se é necessário agora.
2. Toda jornada preserva o princípio de dado honesto: nenhum passo do fluxo pode mascarar indisponibilidade ou fabricar valor.
3. Fluxos de escrita (confirmar fatura, trocar usina, configurar técnico) sempre confirmam a ação e mostram o resultado — nunca uma ação silenciosa sem feedback.

## Checklist
- [ ] Fluxo mapeado a uma jornada real do usuário
- [ ] Nenhum passo mascara indisponibilidade de dado
- [ ] Ação de escrita sempre confirma e mostra resultado
