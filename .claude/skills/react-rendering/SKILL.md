---
name: react-rendering
description: Use ao investigar ou evitar re-renders desnecessários no frontend React do Mplacas — quando memoizar, quando não, e como o projeto já estrutura Context/effects para não disparar renders em cascata.
---

# React Rendering — Mplacas

## Finalidade
Evitar tanto o problema (renders excessivos) quanto o over-fix (memoização prematura que complica o código sem ganho medido).

## Quando usar
- Ao investigar lentidão percebida de UI.
- Ao adicionar um contexto/estado que muitos componentes consomem.

## Procedimento
1. Meça antes de otimizar — use o React DevTools Profiler (se disponível) ou raciocínio explícito sobre quais props/contexto mudam a cada render, antes de adicionar `useMemo`/`useCallback`.
2. `useEffect`/`useCallback` de busca de dado ganham as dependências corretas (ex: `plantId` nas chamadas que dependem da usina selecionada — já é o padrão desde a Etapa C do ADR-069) — dependência faltando é bug de dado desatualizado, não só performance.
3. Context Provider (`AuthContext`, `PlantContext`) deve manter o `value` estável entre renders quando os dados não mudaram (evitar recriar objeto literal inline sem necessidade).
4. Não memoize componentes pequenos e baratos "por via das dúvidas" — `useMemo`/`React.memo` tem custo próprio e só vale a pena quando o cálculo/render evitado é genuinamente caro.

## Anti-patterns
- `useMemo` em toda expressão trivial.
- Objeto/array literal novo a cada render passado como prop para componente memoizado (anula a memoização).
- `useEffect` com array de dependências incompleto (bug de dado, não só performance).

## Checklist
- [ ] Otimização baseada em medição, não suposição
- [ ] Dependências de effect/callback completas e corretas
- [ ] Nenhuma memoização desnecessária adicionando complexidade sem ganho
