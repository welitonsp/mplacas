---
name: secret-safe-ui
description: Use ao construir qualquer UI que lide com credencial/segredo no Mplacas — nunca salvo em localStorage/sessionStorage, nunca retornado após cadastro, erros sanitizados. O projeto já tem um teste de guarda (test_frontend_auth_contract.py) que bloqueia regressão.
---

# Secret-Safe UI — Mplacas

## Finalidade
Impedir vazamento de credencial/token pela UI, com regra dura e testável.

## Regras inegociáveis
- Nenhum segredo (token, senha, API key) salvo em estado persistente do frontend (`localStorage`/`sessionStorage`) — token de sessão do Mplacas já é **só em memória** por decisão deliberada (`TokenStore`).
- Segredo cadastrado (ex: credencial de provedor) nunca é retornado pela API após o cadastro — a UI só mostra "configurado"/status, nunca o valor.
- Nenhum segredo em URL, query string ou analytics.
- Erro vindo de provedor externo é sanitizado antes de chegar à UI — nunca repassar stack trace/erro bruto de terceiro.
- Substituição/revogação de credencial são as únicas ações permitidas sobre um segredo já salvo — nunca "editar e ver o valor atual".
- Testes usam credencial de demonstração/fixture, nunca credencial real.

## Quando usar
- Qualquer tela/form que lide com login, API key, token, senha.

## Procedimento
1. Antes de adicionar uma chave nova a `localStorage`, rode o teste de guarda existente (`tests/test_frontend_auth_contract.py`) — ele bloqueia automaticamente qualquer chave com nome "credential-shaped" (`token`, `cred`, `secret`, `password`, `jwt`, `session`, `api_key`) e exige allowlist explícita com motivo para qualquer chave nova de UI state legítima.
2. Confirme que nenhum `console.log`/log estruturado imprime valor de segredo, mesmo em erro.
3. Ação crítica sobre credencial (revogar, substituir) exige confirmação explícita do usuário antes de executar.

## Anti-patterns
- Guardar token de sessão em `localStorage` "para persistir o login".
- Mostrar o valor de uma API key já cadastrada num campo de edição.
- Logar o corpo de uma resposta de erro de provedor sem sanitizar.

## Checklist
- [ ] Teste de guarda de `localStorage`/`sessionStorage` rodado e passando
- [ ] Nenhum segredo retornado após cadastro
- [ ] Erro de terceiro sanitizado
- [ ] Ação crítica sobre credencial exige confirmação
