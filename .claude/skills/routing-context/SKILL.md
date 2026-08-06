---
name: routing-context
description: Use ao adicionar ou modificar rotas, contextos globais (AuthContext, PlantContext) ou proteção de rota no frontend Mplacas — documenta o padrão já estabelecido (ProtectedRoute, PlantProvider dentro de ProtectedRoute) para não duplicar ou quebrar o fluxo de autenticação/seleção de usina.
---

# Routing & Context — Mplacas

## Finalidade
Preservar o padrão já estabelecido de roteamento e contexto global, evitando reinvenção a cada nova rota.

## Quando usar
- Ao adicionar uma rota nova.
- Ao adicionar um contexto global novo (ex: um futuro `OrganizationContext`).
- Ao mexer em `ProtectedRoute`, `AppShell`, `AuthContext` ou `PlantContext`.

## Procedimento
1. Toda rota autenticada passa por `ProtectedRoute` (`frontend/src/components/ProtectedRoute.tsx`) — nunca duplique a checagem de autenticação numa página individual.
2. `PlantProvider` fica DENTRO de `ProtectedRoute`, nunca envolvendo `AuthProvider` — `GET /plants` exige autenticação (ADR-069 §8). Qualquer contexto novo que dependa de dado autenticado segue o mesmo padrão.
3. Contexto global só quando o estado precisa ser compartilhado por 3+ componentes não relacionados por hierarquia direta — senão, prop passing ou contexto local já resolve.
4. Redirecionamento por falta de autenticação usa `<Navigate replace>` declarativo, nunca `navigate()` imperativo durante o render (causa efeito colateral inválido).
5. Estado de sessão (ex: usina selecionada) que deve ser limpo no logout precisa ser explicitamente removido em `AuthContext.logout()` — ver `SELECTED_PLANT_STORAGE_KEY` como exemplo já implementado.

## Critérios de saída
- Nenhuma checagem de autenticação duplicada fora de `ProtectedRoute`.
- Nenhum novo contexto global sem justificativa de compartilhamento real entre 3+ consumidores.
- Estado de sessão sensível é limpo no logout.

## Anti-patterns
- Context Provider global demais (ex: um Provider por feature pequena).
- Checar `isAuthenticated` manualmente em vez de usar `ProtectedRoute`.

## Checklist
- [ ] Rota nova protegida via `ProtectedRoute`, não checagem manual
- [ ] Contexto novo justificado por compartilhamento real
- [ ] Estado de sessão sensível limpo no logout
