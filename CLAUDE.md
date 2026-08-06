# CLAUDE.md — Mplacas

## Roteamento de agentes (revisado em 2026-08-06)

**Decisão explícita do usuário em 2026-08-06: a regra de custo mínimo abaixo foi suspensa.**
O projeto passou de 4 para 16 subagentes (`.claude/agents/`), a maioria especializada em
frontend/produto/domínio, vários fixados em Opus. Não otimize mais por "menor modelo que
resolve" — use o agente cuja especialidade corresponde à tarefa, mesmo que outro mais barato
desse conta. As seções abaixo (regra de decisão, fluxo típico) descrevem o modelo ANTERIOR,
mantidas como referência histórica para os 4 agentes originais, que continuam existindo e
válidos para o que sempre fizeram — mas não são mais os únicos disponíveis.

## Os 16 agentes

**Originais (seguem a lógica de custo mínimo entre si, ainda vale para tarefas genéricas):**

| Agente | Modelo | Quando usar |
|---|---|---|
| architect | Opus | Planejamento genérico, ADRs, decisões de arquitetura não cobertas por um especialista abaixo |
| worker | Sonnet | Implementação de código, testes, correção de bugs, ciclo de CI — cavalo de trabalho padrão |
| reviewer | Sonnet | Revisão de diff antes de concluir, sobretudo billing/auth/credentials/organizations/migrations |
| quick-task | Haiku | Buscas, resumos, comandos de terminal, formatação, tarefas mecânicas |

**Novos, especializados em frontend/produto/domínio (`.claude/agents/`):**

| Agente | Modelo | Quando usar |
|---|---|---|
| repo-auditor | Haiku | Mapear estado real do repositório sem modificar nada — rotas, componentes, testes, tokens |
| frontend-architect | Opus | Arquitetura de rotas/módulos/estado do frontend |
| product-uiux-lead | Opus | Experiência de produto, arquitetura da informação, hierarquia visual |
| design-system-engineer | Sonnet | Implementar tokens e componentes-base reutilizáveis |
| data-visualization-specialist | Sonnet | Gráficos e apresentação de métricas energéticas/financeiras |
| accessibility-specialist | Sonnet | Auditar/corrigir acessibilidade (WCAG 2.2 AA) |
| frontend-performance-engineer | Sonnet | Bundle, code splitting, renders, Web Vitals |
| solar-domain-specialist | Opus | Validar fidelidade técnica fotovoltaica na UI (consultivo, não implementa) |
| financial-audit-specialist | Opus | Validar confiabilidade financeira na UI (consultivo, não implementa) |
| integration-security-specialist | Opus | UX segura de credenciais/integrações de provedor |
| frontend-test-engineer | Sonnet | Estratégia de testes de frontend focada em risco |
| quality-gate-reviewer | Opus | Revisão independente de fase — mesmo papel do `reviewer`, checklist mais amplo de produto |

Skills correspondentes (35 novas + 5 pré-existentes) em `.claude/skills/`, carregadas pelos
agentes acima conforme a tarefa — ver cada `SKILL.md` para escopo específico.

## Regra de decisão (válida para os 4 agentes originais entre si)

1. É uma decisão de arquitetura genérica, um ADR, ou uma tarefa vaga/grande sem especialista dedicado? Delegue ao `architect`.
2. É implementação de algo já especificado, fora do escopo de um especialista de frontend? Delegue ao `worker`.
3. É busca, leitura, resumo, formatação, ou comando pontual? Delegue ao `quick-task`.
4. O worker terminou uma mudança em billing, auth, credentials, organizations, audit ou migrations? Delegue ao `reviewer` antes de dar a tarefa por concluída.

Nunca deixe `reviewer`/`quality-gate-reviewer` implementar ou corrigir código — eles só apontam, quem corrige é o `worker`/especialista de implementação correspondente.
Os agentes consultivos (`solar-domain-specialist`, `financial-audit-specialist`) nunca implementam — devolvem achado com evidência para o `worker`.

## Fluxo típico de uma feature nova

1. Descreva o objetivo em linguagem natural na conversa principal.
2. Para frontend/produto/visual: delegue ao especialista correspondente (ex: `product-uiux-lead` para diagnóstico de UX, `data-visualization-specialist` para gráfico) — para o resto, `architect` continua sendo o planejador genérico.
3. Você aprova (ou ajusta) o plano.
4. A conversa delega cada etapa ao `worker` ou ao agente de implementação especializado (`design-system-engineer`, `data-visualization-specialist`, `accessibility-specialist`, `integration-security-specialist`), que implementa e roda o CI.
5. Buscas e verificações pontuais no meio do caminho vão para `quick-task`/`repo-auditor`.
6. Se a etapa tocou em código de maior risco (billing, auth, credentials, organizations, audit, migrations), a conversa delega ao `reviewer` antes de fechar a etapa. Para fases maiores de produto, `quality-gate-reviewer` faz a revisão final.
