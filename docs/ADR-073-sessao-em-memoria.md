# ADR-073 — Sessão em memória, sem persistência a recarregamento

## Status

Aceito (2026-08-12). Registra formalmente uma decisão **já em produção** desde a construção do
`AuthContext`; este ADR documenta o trade-off, não o introduz.

## Contexto

A auditoria de frontend de 2026-08-12 (`docs/PLANO_EXECUCAO_AUDITORIA_FRONTEND_2026-08-12.md`,
tarefa T6) apontou que o comportamento de sessão do Mplacas nunca foi registrado como decisão
explícita. Sem registro, o comportamento parece defeito para quem chega ao código depois — e o
risco real é alguém "corrigir" a ausência de persistência sem entender o que ela protege.

### Comportamento atual, verificado no código

| Fato | Evidência |
|---|---|
| Token de acesso vive apenas em variável de módulo, nunca em storage do navegador | `frontend/src/lib/auth.ts:1-7` (`let accessToken: string \| null = null`) |
| Token de refresh vive apenas em `useRef`, nunca persistido | `frontend/src/contexts/AuthContext.tsx:21` |
| Nenhuma chamada usa cookie de sessão | `frontend/src/lib/api.ts` — nenhum `credentials: 'include'` em `apiFetch` |
| Estado inicial de autenticação é derivado da memória | `AuthContext.tsx:17` — `useState(() => !!TokenStore.get())`, sempre `false` num carregamento novo |
| Há limpeza ativa de credencial legada insegura | `frontend/src/main.tsx:22-24` — remove `mplacas_creds_v1` deixado por versões antigas |
| O fim de sessão é comunicado ao usuário | `ProtectedRoute.tsx:12` propaga `state={{ reason: 'SESSION_ENDED' }}`; `LoginPage.tsx:44` consome |
| A usina selecionada é limpa no logout | `AuthContext.tsx:29` remove `SELECTED_PLANT_STORAGE_KEY` |

**Consequência prática:** um `F5` encerra a sessão. O usuário volta ao login, com explicação.

## Decisão

**Manter o token de sessão exclusivamente em memória.** Não persistir token de acesso nem de
refresh em `localStorage`, `sessionStorage`, IndexedDB ou qualquer storage do navegador.

### O que se ganha

1. **Superfície de XSS drasticamente reduzida no ativo mais sensível.** Token em `localStorage` é
   legível por qualquer script que execute na página. Em memória, um XSS ainda é grave, mas não
   entrega ao atacante um token exfiltrável e reutilizável fora da aba.
2. **Nenhum token sobrevive ao fechamento da aba** — não há resíduo em máquina compartilhada.
3. **Coerência com a política já aplicada no projeto.** O `main.tsx:22-24` existe justamente para
   apagar uma credencial de longa duração de versões antigas; persistir token de novo reintroduziria
   a classe de problema que aquele código foi escrito para eliminar.
4. **A CSP estrita reforça, mas não substitui, esta decisão.** `frontend/public/_headers:2` já
   aplica `script-src 'self'` sem `unsafe-inline`. Defesa em profundidade: mesmo que a CSP falhe ou
   seja relaxada, o token não está exposto em storage.

### O que se perde

1. **Reautenticação a cada recarregamento de página.** É o custo real e recorrente, sentido pelo
   usuário a cada `F5`, restauração de aba ou navegação externa e volta.
2. **Nenhuma sessão "lembrada" entre visitas.**

### Alternativa considerada e recusada: refresh token em cookie `httpOnly`

Um cookie `httpOnly` + `Secure` + `SameSite=Strict` resolveria a persistência sem expor o token a
JavaScript, e é a alternativa tecnicamente séria.

**Recusada nesta janela pelos seguintes motivos concretos, não por preferência:**

1. **Custo de superfície nova:** o deploy é cross-origin de fato — frontend em
   `mplacas-frontend.pages.dev`, API em `mplacas-api-*.run.app` (`frontend/.env.production:3`).
   Cookie cross-site exigiria `SameSite=None`, que **reintroduz risco de CSRF** e demandaria uma
   defesa anti-CSRF própria que hoje não existe. `SameSite=Strict` não funcionaria entre esses dois
   domínios.
2. **O ganho é de conveniência, não de segurança.** A decisão atual é a mais conservadora; trocá-la
   aumenta a complexidade da superfície de autenticação para resolver um incômodo de UX.
3. **O incômodo está mitigado, não invisível.** O usuário recebe explicação ao ser deslogado
   (`SESSION_ENDED`), então o comportamento não é percebido como falha silenciosa.

## Consequências

### Positivas

- Nenhum token do Mplacas é recuperável do navegador após fechar a aba.
- A política é verificável por teste automatizado: já existe guarda de contrato em
  `tests/test_frontend_auth_contract.py` (caminho confirmado) impedindo regressão de credencial
  em storage do navegador.

### Negativas

- Fricção recorrente de reautenticação. **Este é o motivo mais provável para revisitar este ADR.**

## Reversibilidade

Alta, mas **não unilateral**. Reverter significa introduzir cookie `httpOnly` cross-site com
`SameSite=None`, e isso **exige, no mesmo trabalho**, uma defesa anti-CSRF explícita (token
sincronizador ou verificação de origem no backend). Não é uma mudança de uma linha no frontend.

Qualquer proposta de reversão passa obrigatoriamente por revisão do agente `reviewer`
(`CLAUDE.md`: mudanças em `auth` exigem revisor independente).

## Gatilho para reavaliação

Reabra este ADR se **qualquer** destes ocorrer:

1. Usuários reais relatarem a reautenticação como atrito relevante (evidência, não suposição).
2. O frontend e a API passarem a compartilhar origem (mesmo domínio ou subdomínio com
   `SameSite=Lax`/`Strict` viável) — o argumento nº 1 da recusa deixa de valer.
3. O projeto adotar defesa anti-CSRF por outro motivo — o custo incremental do cookie cai.

## Riscos e o que fica fora de escopo

- Este ADR **não** altera comportamento algum. É registro de decisão vigente.
- Não trata de duração de token, política de expiração nem rotação de refresh token — esses
  permanecem definidos no backend (`src/mplacas/auth/`).
