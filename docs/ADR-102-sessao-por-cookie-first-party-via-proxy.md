# ADR-102 — Sessão persistente por cookie first-party via proxy

## Status

Aceito (2026-11-25). Substitui o ADR-073 (sessão só em memória). A implantação é em etapas
(ver "Ordem de implantação"); este documento registra a etapa 1 — backend aceitando os dois
fluxos — e o destino das próximas.

## Contexto

O ADR-073 manteve access e refresh token só na memória da aba: cada `F5`, aba restaurada ou volta
de outro app obriga a logar de novo. O próprio ADR-073 listou os gatilhos para reabrir a decisão, e
dois deles ocorreram:

1. **Atrito real relatado pelo dono do produto** (gatilho 1): no celular, o navegador descarta abas
   em segundo plano com frequência, e cada volta ao Mplacas vira um login.
2. **Mesma origem passa a ser viável** (gatilho 2). O motivo nº 1 da recusa era o deploy
   cross-site: frontend em `mplacas-frontend.pages.dev`, API em `*.onrender.com` (antes
   `*.run.app`). Os dois são sufixos públicos, então são *sites* diferentes, e um cookie
   `SameSite=Strict` nunca viajaria entre eles. A saída aprovada é uma **Cloudflare Pages
   Function em `mplacas-frontend.pages.dev/api/*`** que repassa as chamadas ao Render. Para o
   navegador, a API passa a ser a própria origem do frontend (first-party), sem domínio próprio e
   dentro do plano gratuito do Pages.

Com a API na mesma origem, o refresh token pode morar num cookie `HttpOnly` + `Secure` +
`SameSite=Strict`, que o JavaScript não lê — a alternativa que o ADR-073 chamou de "tecnicamente
séria" e recusou só pelo custo de CSRF do `SameSite=None`, que aqui não é necessário.

## Decisão

### 1. O refresh token vai para um cookie first-party

Todo endpoint que **abre** sessão — `POST /auth/login`, `POST /auth/invitations/accept` (convite e
redefinição de acesso, ADR-095) — e o `POST /auth/refresh` gravam:

```
Set-Cookie: __Secure-mplacas_rt=<refresh token>; HttpOnly; Secure; SameSite=Strict;
            Path=/api/auth; Max-Age=<segundos até a sessão expirar>
```

| Atributo | Motivo |
|---|---|
| `__Secure-` | o navegador recusa o cookie se ele vier sem `Secure` ou por HTTP |
| `HttpOnly` | nenhum script da página lê o token (um XSS não o exfiltra) |
| `Secure` | só trafega em HTTPS |
| `SameSite=Strict` | nunca acompanha pedido iniciado por outro site (CSRF clássico morre aqui) |
| `Path=/api/auth` | o cookie só vai para as rotas de autenticação, não para toda chamada da API. É o caminho **como o navegador vê** (atrás do proxy `/api/*`); configurável em `MPLACAS_AUTH_COOKIE_PATH` |
| `Max-Age` | tempo restante da sessão persistida (`auth_sessions.expires_at`), que já vem limitado pelo teto absoluto (item 5) |

Sem `Domain`: o cookie é *host-only*, preso a `mplacas-frontend.pages.dev`.

`MPLACAS_AUTH_COOKIE_ENABLED` (padrão `true`) liga/desliga a emissão **e** a leitura do cookie;
desligado, só o fluxo antigo (token no corpo) existe.

**Transitório:** o `refresh_token` continua no corpo JSON das respostas, para o frontend atual
seguir funcionando. Ele sai do corpo na etapa 4.

### 2. Refresh lê o cookie primeiro; logout revoga e apaga

- `POST /auth/refresh`: com cookie presente, **ele é a credencial** e o corpo é ignorado (nunca
  "cookie inválido, tenta o corpo"). Sem cookie, vale o corpo, exatamente como antes. Com cookie
  e refresh recusado (401), a resposta também apaga o cookie, para o navegador parar de mandar um
  token morto — **exceto** na tolerância de rotação (item 4), que responde 401 sem `Set-Cookie`.
- `POST /auth/logout`: com cookie, revoga a sessão e responde com o cookie apagado (`Max-Age=0`,
  mesmo `Path`/atributos). Continua `204` para token válido, inválido, expirado ou já revogado.

### 3. Defesa CSRF

**Pedidos autenticados pelo cookie (refresh e logout):** exigem **as duas coisas**:

1. cabeçalho `X-Mplacas-Auth: 1` (valor exato) — um formulário HTML de outro site não consegue
   mandar cabeçalho customizado, e um `fetch` de outro site com ele dispara preflight CORS, que só
   é liberado para as origens configuradas;
2. cabeçalho `Origin` presente e igual a uma origem de `MPLACAS_CORS_ALLOWED_ORIGINS` (a mesma lista
   do CORS; comparação exata após normalizar caixa e barra final). Lista vazia → nada passa.

Falhou qualquer uma → `403 {"detail": "request origin not allowed"}`, **sem rotacionar, revogar ou
apagar o cookie** (senão um site de terceiros conseguiria deslogar a vítima). A mensagem é a mesma
para todas as falhas.

O `SameSite=Strict` já impede o envio do cookie em pedido cross-site; as duas checagens acima são
defesa em profundidade para o que `SameSite` não cobre bem (subdomínios irmãos não existem em
`pages.dev`, mas navegadores antigos, extensões e bugs de navegador existem).

**Login-CSRF (login e aceite de convite):** quem abre sessão **não** recebe cookie de entrada, então
o risco é outro: um site de terceiros logar a vítima *na conta do atacante*. Regra: se o pedido
traz `Origin`, ele precisa estar na lista permitida (senão 403, sem tocar no contador de tentativas
nem criar sessão). `Origin: null` conta como presente e é recusado. **Sem `Origin`, segue como
antes** — decisão deliberada:

- navegadores atuais sempre mandam `Origin` em `POST` cruzado (formulário ou `fetch`), então a
  ausência de `Origin` significa cliente que não é navegador (script, teste, servidor-a-servidor),
  e aí não existe vítima de CSRF;
- exigir `Origin` quebraria testes e integrações servidor-a-servidor sem ganho de segurança;
- `X-Mplacas-Auth` **não** é exigido no login nesta etapa, porque o frontend atual não o envia e o
  fluxo do corpo não pode piorar. Pode passar a ser exigido na etapa 4.

`/auth/invitations/inspect` não abre sessão e fica fora da regra.

O CORS do backend (`main.py`) já tem `allow_credentials=True` e `allow_headers=["*"]`, que libera o
`X-Mplacas-Auth` no preflight só para as origens exatas da lista (teste em
`tests/test_cors_expose_headers.py`). Atrás do proxy as chamadas viram same-origin e o CORS deixa de
ser exercitado no navegador, mas a checagem de `Origin` no backend continua valendo — o proxy
**deve repassar o `Origin` original**.

### 4. Tolerância de rotação (duas abas)

Duas abas pedindo refresh juntas apresentam o mesmo token; uma ganha a rotação. Antes, a perdedora
caía no caminho de replay e **derrubava a família inteira** — inclusive a sessão recém-criada da
vencedora. Agora: token autêntico, inativo, **não revogado** e rotacionado há menos de
`MPLACAS_AUTH_REFRESH_REUSE_GRACE_SECONDS` (padrão 10 s, máximo 60) → `401` **sem** revogar a família
e **sem** emitir sessão nova, e a resposta **não traz `Set-Cookie`**: se chegasse depois da
resposta da aba vencedora, um cookie de remoção apagaria o cookie novo e deslogaria o usuário
(`RotationRejection.WITHIN_GRACE` × `DEFINITIVE` em `rotate_session`). Depois da janela, o comportamento de sempre: replay → família
revogada. O frontend (etapa 3) deve repetir o refresh uma única vez ao receber 401 do próprio
refresh: o pote de cookies já terá o token novo gravado pela outra aba.

Correção junto: a revogação por replay era escrita na transação e **descartada** pelo `raise` antes
do `commit` no router — só funcionava quando o serviço era chamado direto. O refresh agora faz
commit também na falha.

### 5. Teto absoluto da sessão

Uma família não se estende além de `MPLACAS_AUTH_SESSION_MAX_AGE_DAYS` (padrão 30, 1–365) a partir
do `created_at` da **sessão-raiz** (a de `id == family_id`, criada pelo login/aceite —
`AuthSessionService.create_session`). Mecânica:

- ao abrir: `expires_at = agora + min(TTL do refresh, teto)`;
- ao rotacionar: `expires_at = min(agora + TTL, criação da raiz + teto)`;
- refresh com a família já no teto → `401` e a família é encerrada (`revoked_at` preenchido);
- raiz ausente (expurgada pela retenção) → falha fechada, família encerrada. Na prática não
  acontece: a retenção é de 90 dias e o teto, 30.

Sem migration: usa `created_at`, `family_id` e `expires_at`, que já existem.

### 6. IP do cliente confiável (limite de tentativas)

**Problema.** `server.py` usava `forwarded_allow_ips="*"`: o uvicorn aceita `X-Forwarded-For` de
**qualquer** um e pega o primeiro endereço da lista, que o cliente escreve. Trocando o cabeçalho a
cada tentativa, dá para escapar do bloqueio de login e de convite.

**Por que não fechar já com "redes privadas".** A documentação do Render não pôde ser consultada,
então não se sabe quantos proxies (balanceador do Render, borda Cloudflare) ficam entre o cliente e
o contêiner, nem por quais redes eles chegam. Errar para o lado restritivo **não é inofensivo**: se
o IP resolvido virar o do balanceador ou o de um nó de borda, todos os clientes atrás dele passam a
dividir a mesma chave de limite (`usuário + IP`). Aí um atacante que conheça o e-mail de alguém
erra a senha 5 vezes e **bloqueia o login legítimo da vítima por 15 minutos, repetidamente**
(negação de serviço direcionada pelo agrupamento). Por isso esta etapa não muda o comportamento do
deploy e prepara a correção para ser ligada depois de medida.

**O que está no código:**

1. **Transitório — padrão igual ao de antes.** `MPLACAS_FORWARDED_ALLOW_IPS` tem padrão `*` (aceito
   explicitamente pela validação, só sozinho). O risco conhecido continua o mesmo de hoje: o XFF é
   forjável e o bloqueio de tentativas pode ser contornado. Nenhum risco novo é introduzido.
2. **Modo robusto, desligado por padrão — `MPLACAS_TRUSTED_PROXY_HOPS = N`** (1–10, sem padrão).
   Cada proxy confiável acrescenta um endereço à direita do XFF, então o IP do cliente é
   `XFF[-N]`; o que o cliente forjou fica mais à esquerda e é descartado. XFF com menos de N itens
   ou item não-IP → par TCP (falha fechada). Nesse modo o uvicorn **não** reescreve o endereço do
   cliente: `server.build_asgi_app` aplica o `ProxyHeadersMiddleware` (só para o esquema https) e
   em seguida devolve ao escopo o par TCP real (`RestoreTcpPeerMiddleware`); o IP dos limites sai
   só de `resolve_client_ip`.
3. **Cabeçalho do proxy autenticado.** `X-Mplacas-Client-IP` só vale quando o pedido também traz
   `X-Mplacas-Proxy-Secret` igual a `MPLACAS_PROXY_SHARED_SECRET` (mínimo 32 bytes;
   `hmac.compare_digest`). Tem precedência sobre os demais. Sem segredo configurado (padrão), o
   cabeçalho é ignorado. Segredo errado gera só o log `proxy_shared_secret_mismatch`. O segredo
   nunca entra em log, `repr` nem `safe_summary`; segredo em branco é tratado como ausente e gera o
   aviso `proxy_shared_secret_blank_ignored` na subida.
4. **Diagnóstico temporário — `client_ip_diagnostic`** (INFO, só no login, flag
   `MPLACAS_CLIENT_IP_DIAGNOSTIC`, padrão ligado). Registra **apenas**: `peer_is_private` (o par
   TCP é endereço privado?), `forwarded_for_hops` (quantos itens tem o XFF),
   `resolved_matches_peer` (o IP resolvido é o próprio par TCP?) e
   `trusted_proxy_hops_configured`. Nunca endereço, usuário ou cabeçalho (há teste). Para isso o
   `TcpPeerMiddleware` guarda o par TCP real antes de qualquer reescrita.

Os dois limites (`/auth/login` e convites) usam `mplacas.core.client_ip.resolve_client_ip`.

**Procedimento para sair do transitório (dono do produto + agente):**

1. Publicar este PR e fazer alguns logins reais, de redes diferentes (4G e Wi-Fi).
2. Nos logs do Render, ler os eventos `client_ip_diagnostic`. Esperado: `peer_is_private=true` e
   `forwarded_for_hops` constante entre logins sem XFF forjado — esse número é N.
3. Definir `MPLACAS_TRUSTED_PROXY_HOPS=N` no Render. Conferir de novo: `resolved_matches_peer`
   deve ser `false` (o IP veio do XFF, não do balanceador).
4. Teste de fumaça: um login com `X-Forwarded-For: 1.2.3.4` forjado deve somar `+1` em
   `forwarded_for_hops` e continuar bloqueando após 5 erros.
5. Só então: trocar o padrão de `MPLACAS_FORWARDED_ALLOW_IPS` (remover o `*`) e remover o
   `client_ip_diagnostic` num PR próprio. Depois da etapa 2 (proxy), o IP passa a vir do cabeçalho
   autenticado e o XFF só importa para chamadas que não passam pelo proxy.

## Comportamento por plataforma

| Plataforma | Esperado após a etapa 3 |
|---|---|
| Desktop (Chrome, Edge, Firefox, Safari) | cookie first-party persiste entre `F5`, abas e reinícios do navegador até o `Max-Age`; logout apaga |
| Android (Chrome) | igual ao desktop; aba descartada em segundo plano volta logada |
| iPhone (Safari e qualquer navegador no iOS, todos WebKit) | O limite de 7 dias do ITP vale para cookie gravado por JavaScript e para cookie de resposta servida de IP "de terceiro" (CNAME/servidor em outra rede). Aqui o cookie vem de resposta HTTP da própria origem, servida pela Pages Function na mesma borda Cloudflare do site, então o esperado é valer o `Max-Age`. **Conferir em aparelho real na etapa 3** — se o ITP cortar para 7 dias, a consequência é só um login por semana. O site adicionado à tela de início usa um pote de cookies separado do Safari: exige um login lá, uma vez. Navegação privada perde tudo ao fechar, como deve |

Em qualquer plataforma: depois do teto de 30 dias desde o login, pede senha de novo.

## Modelo de ameaça

| Ameaça | Antes (ADR-073) | Agora |
|---|---|---|
| XSS lê o refresh token | não (memória da aba) mas o script pode chamar a API enquanto a aba vive | não (`HttpOnly`); o script ainda pode chamar a API pela aba — XSS segue grave, e a CSP `script-src 'self'` continua sendo a defesa principal |
| XSS exfiltra token para usar fora | access token em memória, sim, por 15 min | access token em memória, sim, por 15 min; refresh não |
| CSRF em refresh/logout | não se aplica (sem cookie) | `SameSite=Strict` + `X-Mplacas-Auth` + `Origin` permitido |
| Login-CSRF | `Origin` não era checado | `Origin` presente precisa estar na lista |
| Roubo de token por máquina compartilhada | nada sobrevive à aba | cookie sobrevive até o `Max-Age`/teto: **logout explícito importa**; navegação privada recomendada em máquina alheia |
| Token roubado usado em paralelo | replay derruba a família | igual, salvo nos 10 s de tolerância (ver Negativas) |
| Burlar bloqueio de login trocando `X-Forwarded-For` | possível | ainda possível no padrão transitório; fechado com `MPLACAS_TRUSTED_PROXY_HOPS` ou pelo cabeçalho autenticado do proxy (item 6) |
| Bloquear o login de uma vítima por agrupamento de IP | não | evitado de propósito: nada fica restritivo antes de medir os saltos (item 6) |
| Proxy comprometido / segredo vazado | — | quem tem o segredo escolhe o IP do limite de tentativas, nada além disso; trocar o segredo no Render e no Pages |

## Ordem de implantação

1. **Este PR (backend):** aceita os dois fluxos. Cookie emitido e lido, defesa CSRF, tolerância,
   teto, IP confiável. O frontend atual (token no corpo, chamando o Render direto) não muda: o
   cookie é emitido numa resposta cross-site sem credenciais e o navegador simplesmente não o
   guarda; nenhum pedido dele leva cookie, então nenhuma regra nova o atinge.
2. **Proxy:** Pages Function em `/api/*` → Render, repassando `Origin`, `Cookie`, `Set-Cookie` e
   `X-Mplacas-Auth`, e acrescentando `X-Mplacas-Client-IP` (do `CF-Connecting-IP`) e
   `X-Mplacas-Proxy-Secret`. Só então configurar `MPLACAS_PROXY_SHARED_SECRET` no Render e no Pages.
3. **Frontend:** `VITE_API_URL` aponta para `/api`; `credentials: 'include'` nas chamadas de auth;
   `X-Mplacas-Auth: 1`; ao carregar, tenta um refresh para restaurar a sessão; repete o refresh
   uma vez em 401 (item 4); para de guardar refresh token em memória; CSP `connect-src 'self'`.
4. **Limpeza:** remover `refresh_token` dos corpos de resposta e o fallback de corpo no
   refresh/logout; avaliar exigir `X-Mplacas-Auth` no login.

Cada etapa é reversível sozinha, e nenhuma exige migration.

## Consequências

### Positivas

- `F5`, aba restaurada e volta ao app não pedem mais login (após a etapa 3).
- O refresh token sai do alcance de JavaScript.
- Duas abas não se derrubam mais.
- Sessão tem fim garantido (teto), independentemente de uso contínuo.
- O bloqueio de tentativas de login fica pronto para deixar de ser burlável por cabeçalho (após o
  procedimento do item 6).
- A revogação por replay passa a ser de fato gravada.

### Negativas

- **Sessão sobrevive ao fechamento da aba.** Em máquina compartilhada, quem não clicar em "Sair"
  deixa a conta aberta até o teto. Aceito: o público é dono de usina no próprio aparelho.
- **Janela de tolerância favorece o ladrão rápido:** se um token roubado for usado antes do dono, a
  tentativa do dono dentro de 10 s recebe 401 sem derrubar a família, e o ladrão segue com a
  sessão até a próxima rotação do dono falhar fora da janela (aí cai tudo). Janela curta e
  limitada a 60 s na config por isso.
- **Mais uma peça no caminho:** a Pages Function vira dependência de toda chamada à API (limite de
  pedidos do plano gratuito do Workers, latência extra pequena).
- **Período transitório com o token também no corpo** (etapas 1–3): durante ele, a proteção
  `HttpOnly` não vale para quem ainda usa o corpo.
- Backend passa a ter regras que dependem de `MPLACAS_CORS_ALLOWED_ORIGINS` estar correto: lista
  errada derruba o login de navegador com 403.

## Validação

- `tests/test_auth_cookie_session.py`: atributos do cookie em login/refresh/convite/redefinição;
  `Max-Age` limitado pelo teto; caminho configurável; liga/desliga; refresh pelo cookie; cookie
  vence o corpo; 403 sem rotação para cada falha da defesa CSRF; falha fechada sem origens; login e
  aceite com `Origin` alheio/`null` → 403 sem tocar no contador; logout pelo cookie revoga e apaga;
  logout sem defesa → 403 e sessão intacta; tolerância → 401 sem revogar; replay após a janela →
  família revogada (cookie e corpo); teto → 401 e família encerrada; sessão rotacionada nunca passa
  do teto; isolamento entre organizações pelo cookie; usuário/organização desativados; IP do proxy
  só com segredo; `X-Forwarded-For` forjado ignorado; bloqueio não burlável; segredo fora dos logs.
- `tests/test_auth_cookie_session.py` (cont.): resposta 401 da tolerância sem `Set-Cookie`; cadeia
  real do `server.py` com o padrão transitório; `TRUSTED_PROXY_HOPS` com 1, 2 e 3 saltos, XFF
  forjado à esquerda, XFF curto e item inválido; diagnóstico sem nenhum endereço, usuário ou senha.
- `tests/test_server_contract.py`: o uvicorn recebe a cadeia de `build_asgi_app`.
- `tests/test_cors_expose_headers.py`: preflight libera `X-Mplacas-Auth` com credenciais só para a
  origem configurada.
- Fluxo antigo: `tests/test_auth_characterization.py`, `tests/test_auth_logout.py` e demais
  passam sem alteração.

## Reversibilidade

Alta. `MPLACAS_AUTH_COOKIE_ENABLED=false` desliga emissão e leitura do cookie sem deploy de código;
o fluxo do corpo continua vivo até a etapa 4. A tolerância vai a zero com
`MPLACAS_AUTH_REFRESH_REUSE_GRACE_SECONDS=0`. Depois da etapa 4, reverter exige devolver o
`refresh_token` ao corpo e o frontend à memória (o caminho do ADR-073).
