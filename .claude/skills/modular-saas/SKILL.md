---
name: modular-saas
description: Use ao avaliar se o Mplacas precisa de um módulo de produto novo (ex portfólio, clientes, manutenção) — define o critério para decidir se um módulo entra agora ou fica registrado como futuro, evitando construir capacidade que os dados/backend ainda não sustentam.
---

# Modular SaaS — critério de entrada de módulo

## Finalidade
Evitar construir uma tela/módulo de frontend para uma capacidade que o backend ainda não tem dado real para sustentar (ex: "Portfólio" antes de existir mais de uma organização/usina real de verdade em uso).

## Quando usar
- Antes de iniciar qualquer módulo novo da lista de 20 áreas potenciais do produto (dashboard, portfólio, clientes, financeiro, auditoria, integrações etc).

## Quando não usar
- Para ajuste dentro de um módulo já existente (isso é `frontend-architecture`).

## Procedimento
1. Pergunte: o backend já expõe endpoint real para este módulo? Se não, o módulo de frontend não pode ser construído com dado real — registre como pendência de backend primeiro, não construa com mock.
2. Pergunte: existe hoje mais de uma instância do conceito em produção (ex: mais de uma organização real, mais de uma usina real)? Se a resposta é não, o módulo de gestão daquele conceito (ex: seletor de portfólio) é prematuro — a exceção é quando o próprio ADR já decidiu suportar antes da demanda existir (ex: ADR-069, multiusina).
3. Se aprovado, o módulo entra na navegação só quando tiver função real (nunca um item de menu que leva a "em breve").
4. Todo módulo novo referencia o ADR ou decisão que o autorizou.

## Critérios de saída
- Módulo tem endpoint de backend real por trás, não mock.
- Módulo entra na navegação já funcional, nunca como placeholder.

## Anti-patterns
- Construir tela de "Clientes" sem o backend ter conceito de cliente separado de organização.
- Adicionar item de menu "em breve" — isso é sinal de amadorismo, não de roadmap.

## Checklist
- [ ] Backend tem endpoint real
- [ ] Demanda real existe ou está formalmente decidida em ADR
- [ ] Nenhum item de navegação sem função
