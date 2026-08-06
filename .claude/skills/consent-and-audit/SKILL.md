---
name: consent-and-audit
description: Use ao construir fluxo que envolve consentimento do usuário (ex vincular integração, autorizar acesso a dado de terceiro) no Mplacas — toda ação de consentimento é explícita, registrada e reversível.
---

# Consent & Audit — Mplacas

## Finalidade
Garantir que ações que envolvem dado sensível ou de terceiro têm consentimento explícito e reversível, não implícito.

## Quando usar
- Ao desenhar qualquer fluxo onde o usuário autoriza o sistema a acessar/usar um dado (ex: vincular conta de provedor, compartilhar dado com terceiro).

## Procedimento
1. Consentimento é uma ação explícita do usuário (clique/confirmação), nunca inferido de uso passivo da tela.
2. Toda ação de consentimento gera evento auditável no backend (ver `audit-traceability`) — o frontend não implementa essa lógica, só aciona o endpoint correto.
3. O usuário deve conseguir revogar/desfazer o consentimento em algum ponto da UI, não é um estado permanente sem saída.

## Anti-patterns
- Consentimento pré-marcado por padrão ("opt-out" em vez de "opt-in") para algo sensível.
- Nenhuma forma de revogar depois de consentir.

## Checklist
- [ ] Consentimento é ação explícita, não padrão pré-marcado
- [ ] Ação gera evento auditável no backend
- [ ] Existe caminho de revogação
