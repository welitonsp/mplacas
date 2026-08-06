---
name: audit-traceability
description: Use ao avaliar se uma ação de escrita no Mplacas (confirmar fatura, cadastrar investimento, trocar usina padrão) está corretamente auditada — todo evento sensível já grava AuditEventRepository no backend; o frontend nunca duplica essa lógica.
---

# Audit Traceability — Mplacas

## Finalidade
Garantir que toda ação relevante do usuário é rastreável, sem duplicar a responsabilidade de auditoria no frontend.

## Quando usar
- Ao avaliar se uma ação de escrita nova precisa de auditoria.

## Procedimento
1. Toda ação de escrita sensível (confirmar/rejeitar fatura, mudar configuração, trocar usina padrão, cadastrar investimento) já é auditada pelo backend via `AuditEventRepository` — confirme isso no endpoint correspondente antes de assumir que falta.
2. O frontend nunca implementa lógica de auditoria própria (log local, etc.) — isso pertenceria ao backend.
3. Se uma ação de escrita nova não tiver endpoint com auditoria, isso é um achado para escalar ao backend/architect, não algo para o frontend compensar.

## Anti-patterns
- Implementar um "log de ações" no frontend em vez de confiar no audit event do backend.
- Assumir que falta auditoria sem checar o backend primeiro.

## Checklist
- [ ] Ação de escrita confirmada como já auditada no backend
- [ ] Nenhuma lógica de auditoria duplicada no frontend
