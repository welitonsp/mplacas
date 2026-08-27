# Auditoria de sistema — Mplacas, 2026-08-26

## Como usar este documento

Escrito para ser retomado por outra sessão de IA sem perder o fio. Se você é a próxima IA:

1. **Comece pelo § _Estado no momento da auditoria_** e reconfirme o ground truth — branch, commit e
   `git status`. Os números de linha citados aqui envelhecem; reconfirme antes de editar.
2. **Trabalhe na ordem do § _Ordem de execução recomendada_.** Ela não é a ordem de severidade: é a
   ordem que evita retrabalho e desbloqueia a produção mais cedo.
3. **Leia o § _O que NÃO fazer_ antes de "corrigir" qualquer coisa.** Ele lista armadilhas onde a
   correção óbvia é errada, incluindo duas que já foram propostas e rejeitadas com evidência.
4. Ao fechar um achado, marque-o aqui com data e commit. Não apague o achado: o histórico de
   auditoria do projeto é comparável ao longo do tempo.

> **Nota para quem lê a partir da `main`.** Esta auditoria examinou a branch do PR #129
> (commit `556561a`), que ainda não foi mesclada. Alguns caminhos citados —
> `docs/POLITICA_SEM_GOOGLE_CLOUD.md`, `docs/RUNBOOK_DEPLOY.md`, `render.yaml`,
> `.github/workflows/operational-jobs.yml` — **só existem naquela branch** e chegam à `main` com o
> merge do PR. O relatório vem para a `main` antes disso de propósito: os achados valem
> independentemente de quando o PR for mesclado, e o P0 precisa ser conhecido antes do deploy.

Formato de cada achado, conforme `.claude/skills/audit-evidence`:
**Afirmação → Evidência → Impacto → Severidade → Solução proposta → Risco da correção.**
Escala: **P0** bloqueia produção ou é risco de segurança · **P1** quebra funcional ou dado incorreto ·
**P2** problema real com contorno · **P3** qualidade sem quebra · **P4** cosmético.

---

## Estado no momento da auditoria

| Item | Valor |
|---|---|
| Data | 2026-08-26 19:57 UTC |
| Branch | `chore/migracao-render-github-actions` |
| Commit | `556561a` |
| `git status` | limpo |
| Posição | 7 commits à frente de `origin/main`, PR #129 aberto e verde (9 checks) |
| Código | 178 arquivos Python / 24.241 linhas · 130 arquivos de teste / 27.267 linhas · 187 arquivos frontend · 43 migrations · 72 ADRs |
| Gates locais | ruff limpo · mypy limpo (194 arquivos) · 821 testes passando, 6 skipped |

**Contexto:** o projeto acabou de sair do Google Cloud (ADR-076) após cobrança sem orçamento. O
projeto GCP `mplacas` foi excluído (`lifecycleState: DELETE_REQUESTED`, reversível por 30 dias).
A arquitetura nova — Render free para a API, GitHub Actions para os 8 jobs, Neon, Cloudflare Pages —
**ainda não foi para produção**. A API está fora do ar desde que o faturamento do GCP caiu.

Esta auditoria cobre o estado do repositório, não um ambiente em execução: não há produção viva para
observar.

---

## Sumário executivo

**A migração não está pronta para produção, e o motivo não é nenhum dos itens já discutidos.**

O achado A-01 é decisivo: a política de segurança de conteúdo do frontend fixa, em arquivo estático,
a URL da API do Google Cloud que acabou de ser excluída. Seguir o runbook de deploy à risca produz
uma aplicação que carrega e não funciona — todo `fetch` bloqueado pelo navegador, sem erro de
servidor para diagnosticar. O runbook manda trocar `VITE_API_URL`, o que é **insuficiente**.

Isso passou por três revisões (a minha, a do ChatGPT e a revisão de código de alto esforço) sem ser
detectado, porque todas procuraram por "google", "gcloud" e "cloud run" — e a string real é
`run.app`. Registro isso como falha de método, não só como achado.

O A-10 apareceu durante esta própria auditoria, ao criar a branch do relatório a partir da `main`:
**a `main` está com o CI vermelho desde 2026-08-25**, por um teste de contrato de backup que ficou
para trás quando a agenda do drill foi desativada. Mesclar o PR #129 conserta.

Fora disso, a base é sólida: RLS ativo com contexto de tenant explícito, nenhum segredo versionado,
gitleaks e CodeQL no CI, 821 testes, ações fixadas por SHA e dependências com hash. Os demais achados
são de resiliência operacional, não de correção.

| Severidade | Quantidade | Achados |
|---|---|---|
| **P0** | 1 | ~~A-01~~ ✅ corrigido |
| **P1** | 3 | ~~A-02~~ ✅ · A-03, A-10 |
| **P2** | 4 | ~~A-04~~ ✅ · A-05 ⚠️ mitigado · A-06, A-07 |
| **P3** | 2 | A-08, A-09 |

---

## P0 — bloqueia produção

### A-01 · O CSP do frontend bloqueia a API nova

> **✅ CORRIGIDO em 2026-08-27, commit `4311d18`.** A origem do CSP e a origem que o cliente HTTP
> chama passam a sair da **mesma** variável (`VITE_API_URL`): `frontend/public/_headers` guarda o
> marcador `__API_ORIGIN__`, resolvido por `frontend/scripts/render-csp.mjs` no `npm run build`. O
> script encerra o build com saída 1 se a variável estiver ausente, malformada, sem HTTPS fora de
> localhost, ou se o marcador tiver sumido — este último caso pega a regressão de alguém voltar a
> escrever a origem à mão. Travado por 10 testes em `frontend/src/test/renderCsp.test.ts` e pelo
> contrato reescrito em `tests/test_frontend_auth_contract.py`, que agora verifica a invariante em
> vez de uma URL literal. Build real validado ponta a ponta.

**Afirmação.** Após migrar a API para o Render, o navegador bloqueará **todas** as chamadas do
dashboard, porque o `Content-Security-Policy` publicado com o frontend só permite conexão com a URL
da API no Google Cloud, que não existe mais.

**Evidência.**

- `frontend/public/_headers:2` — `connect-src 'self' https://mplacas-api-104231254500.us-central1.run.app`
- `frontend/src/env.ts:11` — `API_URL` vem de `VITE_API_URL`, validada como URL absoluta
- `frontend/src/lib/api.ts:171` — `fetch(\`${API_URL}${path}\`, …)`; todas as chamadas usam essa base
- `gcloud projects describe mplacas` → `lifecycleState: DELETE_REQUESTED` (projeto excluído)
- `tests/test_frontend_auth_contract.py:118-121` — teste-guarda que **exige** a URL morta no CSP

**Impacto.** A aplicação carrega, a tela aparece, e nenhuma requisição completa. Login falha, o
dashboard fica vazio. O erro só aparece no console do navegador como violação de CSP — não há erro
de servidor, log de API nem falha de CI que aponte a causa. É o pior modo de falha possível para
quem estiver seguindo o runbook: tudo parece ter dado certo.

**Severidade: P0.** Bloqueia produção de forma total e silenciosa, no caminho documentado como
correto. `docs/RUNBOOK_DEPLOY.md` § 2.3 instrui apenas a trocar `VITE_API_URL` — seguir o runbook
como escrito **produz o defeito**.

**Solução proposta.** A correção exige três arquivos coordenados; mexer em um só deixa o CI vermelho
ou a app quebrada:

1. `frontend/public/_headers` — o valor precisa deixar de ser fixo. Como `_headers` é estático e não
   lê variável de ambiente, gerar o arquivo no build a partir de `VITE_API_URL`, num script em
   `frontend/scripts/` (já existe `check-bundle-budget.mjs` como precedente), com um placeholder no
   arquivo-fonte. Alternativa mais simples e pior: fixar a URL do Render, o que repete o problema na
   próxima migração.
2. `frontend/.env.production` — ver A-02.
3. `tests/test_frontend_auth_contract.py:120` — trocar a asserção de URL literal por uma que verifique
   a **invariante**: `connect-src` contém exatamente a origem de `VITE_API_URL`, não é curinga, e não
   é `https:` genérico (a linha 118 já protege esse último caso e deve ser mantida).

**Risco da correção.** Médio. Gerar `_headers` no build introduz um passo que, se falhar em silêncio,
publica um CSP vazio ou sem `connect-src` — o que quebra a app do mesmo jeito. Mitigação: o próprio
script deve falhar com saída diferente de zero se `VITE_API_URL` estiver ausente ou malformada, e o
teste do item 3 deve rodar sobre o arquivo **gerado**, não sobre o template. Não relaxar o CSP para
`https:` como atalho: isso permitiria exfiltração para qualquer host e derruba a linha 118.

---

## P1 — quebra funcional

### A-02 · `.env.production` versionado aponta para o projeto GCP excluído

> **✅ CORRIGIDO em 2026-08-27, commit `4311d18`.** `frontend/.env.production` removido. A
> configuração de produção passa a ter uma fonte só — a variável `VITE_API_URL` do GitHub, que
> `deploy-frontend.yml` valida antes de construir. Era a última referência funcional ao Google Cloud
> no repositório.

**Afirmação.** O repositório versiona uma configuração de produção que aponta para uma API que não
existe mais.

**Evidência.**

- `frontend/.env.production:3` — `VITE_API_URL=https://mplacas-api-104231254500.us-central1.run.app`
- Precedência do Vite (documentação oficial): *"environment variables that already exist when Vite is
  executed have the highest priority and will not be overwritten by `.env` files"*
- `.github/workflows/deploy-frontend.yml:39` define `VITE_API_URL` a partir de `vars.VITE_API_URL`

**Impacto.** No deploy pelo workflow o valor do shell vence, então **este arquivo não causa o A-01** —
os dois problemas são independentes e ambos precisam de correção. O dano real é em build local
(`npm run build` sem a variável exportada), que produz um bundle apontando para um projeto excluído,
e no fato de o arquivo parecer a fonte de verdade da configuração de produção.

**Severidade: P1.** Não quebra o deploy automatizado, mas é configuração de produção incorreta e
versionada, e a última referência funcional ao Google Cloud num repositório onde ele está proibido
(`docs/POLITICA_SEM_GOOGLE_CLOUD.md`).

**Solução proposta.** Substituir a URL por um placeholder que falhe alto — `env.ts:24` já rejeita URL
malformada no startup — ou remover o arquivo e deixar `deploy-frontend.yml` como única fonte, já que
ele valida a presença da variável antes de construir (`deploy-frontend.yml:42-49`).

**Risco da correção.** Baixo. Se o arquivo for removido, confirmar que nenhum build local documentado
dependia dele; `frontend/.env.example` continua servindo de referência.

---

### A-03 · Backup sem agendamento, com RPO documentado que não é mais cumprido

**Afirmação.** Nenhum backup lógico é gerado automaticamente. A documentação promete RPO de 24 h por
snapshot diário; hoje só existe o PITR nativo do Neon.

**Evidência.**

- `.github/workflows/restore-drill.yml:6-7` — gatilho é apenas `workflow_dispatch`
- `.github/workflows/restore-drill.yml:82` — `retention-days: 35` (a cadeia de retenção só existe se
  o workflow rodar)
- Comentário no próprio arquivo: *"Workstation production policy (2026-08-25): automatic cloud
  execution is disabled"* — decisão deliberada do usuário, commit `95f6726`
- `docs/CHECKLIST_REMEDIACAO_AUDITORIA.md:367` — RPO de 24 h declarado
- `docs/CHECKLIST_REMEDIACAO_AUDITORIA.md:399` — janela PITR do Neon Free registrada como 6 h

**Impacto.** Menor do que parece à primeira vista, e é importante não superestimar: o PITR do Neon
cobre a janela curta e é **mais** apertado que o RPO de 24 h declarado. O que se perdeu foi a cópia
lógica com 35 dias de retenção, que protegia contra dois cenários que o PITR não cobre — corrupção
lógica descoberta tarde, e perda de acesso à própria conta Neon.

**Hipótese não confirmada, e que precisa ser verificada antes de qualquer decisão:** a janela de 6 h
do Neon Free foi confirmada em 2026-08-03. Termos de free tier deste projeto já mudaram uma vez com
consequência grave. **Reconfirmar no painel do Neon** antes de tratar 6 h como garantia.

**Severidade: P1.** Há divergência entre o que a documentação promete e o que o sistema faz. Não é P0
porque existe proteção residual real (PITR) e porque a desativação foi decisão consciente do dono.

**Solução proposta.** Decidir e registrar, não simplesmente religar: (a) reativar a agenda agora que a
arquitetura saiu do "workstation production" e voltou para nuvem gratuita; ou (b) manter manual e
**corrigir a documentação** para declarar o RPO real. A situação insustentável é a atual, em que o
documento afirma uma garantia que o sistema não entrega.

**Risco da correção.** Baixo para (b). Para (a), o workflow usa `environment: production-restore-drill`
e um serviço Postgres — confirmar que o segredo de restore continua válido antes de agendar, senão a
agenda passa a falhar todo dia e treina o operador a ignorar notificação de falha, que é hoje o único
canal de alerta (ver A-04).

---

### A-10 · O gate de qualidade da `main` está quebrado desde 2026-08-25

**Afirmação.** A `main` tem um teste falhando. O gate de qualidade não protege mais nada, e qualquer
branch criada a partir dela nasce com CI vermelho.

**Evidência.** Descoberto ao criar a branch desta auditoria a partir de `origin/main`: o job
`quality` do PR #130 falhou com `1 failed, 871 passed`.

- `tests/test_backup_restore_runbook_contract.py:67` (na `main`) — `assert 'cron: "0 5 * * *"' in workflow`
- Commit `95f6726` (*"ops: stop scheduled cloud backup drill during workstation production"*, 2026-08-25)
  removeu o `schedule:` de `.github/workflows/restore-drill.yml` e **não atualizou o teste**; o diff
  desse commit toca um arquivo só
- Log do job: `FAILED tests/test_backup_restore_runbook_contract.py::test_restore_drill_is_automated_and_fail_closed`

**Impacto.** Dois efeitos, e o segundo é o pior.

O imediato: a `main` está vermelha há um dia, e toda branch nova herda a falha — foi assim que este
achado apareceu.

O de fundo: o teste se chama `test_restore_drill_is_automated_and_fail_closed`. Ele existia
justamente para garantir que o backup fosse automatizado. Desativar a agenda sem tocar no teste não
"quebrou o CI por descuido" — desmontou em silêncio uma garantia que o projeto havia escrito de
forma explícita. É a mesma lacuna do A-03, vista pelo outro lado: lá a documentação promete o que o
sistema não faz; aqui o teste afirmava o que o sistema deixou de fazer.

**Severidade: P1.** Não bloqueia produção — que já está fora do ar por outro motivo —, mas remove a
rede de proteção de todo trabalho futuro enquanto durar.

**Solução proposta.** Já existe e está no PR #129: o teste foi renomeado para
`test_restore_drill_is_manual_and_fail_closed` e passou a exigir `workflow_dispatch:` com ausência de
`schedule:`. **Mesclar o PR #129 conserta a `main`.** Se a decisão do A-03 for religar a agenda, o
teste volta à forma anterior — mas aí por decisão registrada, não por omissão.

**Risco da correção.** Baixo. O risco real é o oposto: deixar como está treina quem revisa a ignorar
CI vermelho, e o próximo teste que quebrar de verdade passa despercebido.

---

## P2 — problema real com contorno

### A-04 · Nada observa a API de fora

> **✅ RESOLVIDO em 2026-08-27.** `.github/workflows/watchdog.yml` verifica a cada 6 h se
> `GET /health` responde 200 e se o ciclo operacional teve sucesso nas últimas 30 h, alertando no
> Telegram e derrubando o workflow (segundo canal, via notificação do GitHub). O intervalo de 6 h é
> parte do contrato e está travado por teste: cada verificação **acorda** o serviço no Render, e o
> plano free dá 750 h/mês contra as ~730 h que o mês tem — um ping frequente estouraria a franquia.
> `/health` não consulta o banco, então o custo em compute do Neon é zero.

**Afirmação.** Não existe verificação externa de disponibilidade da API. Se o serviço do Render cair,
ninguém é avisado.

**Evidência.** `grep -rln "uptime|healthcheck|cron-job.org|betteruptime|statuspage" .github/ docs/RUNBOOK_DEPLOY.md render.yaml` → nenhum resultado.
`src/mplacas/main.py:168-169` — `/health` devolve `{"status": "ok"}` sem consultar dependência alguma.

**Impacto.** O `/health` sem checagem é o comportamento **correto** para um probe de liveness, e o
Render o usa bem nesse papel (`render.yaml:27`) — isso não é o defeito. O defeito é a ausência de
qualquer observador externo: a queda da API só é percebida quando o usuário abre o dashboard. As
policies de Cloud Monitoring que cumpriam esse papel saíram com o Google Cloud e não foram
substituídas (ADR-076 registra isso como risco aceito).

**Severidade: P2.** Não quebra nada por si; degrada o tempo de detecção. Condição pré-existente,
agravada pela saída do GCP.

**Solução proposta.** Um verificador externo gratuito batendo em `/health`. Cuidado específico deste
projeto: um ping frequente **acorda o serviço do Render e consome as 750 h/mês**, e mantém o Neon
acordado — exatamente o que estourou a cota em 2026-08-21. Intervalo longo (≥ 30 min) ou verificação
apenas em janela útil.

**Risco da correção.** Médio, e contraintuitivo: a correção ingênua reintroduz o incidente de custo.

---

### A-05 · As agendas se desabilitam sozinhas após 60 dias sem atividade

> **⚠️ PARCIALMENTE MITIGADO em 2026-08-27.** O `watchdog.yml` detecta ausência de execução do ciclo
> (falha por ausência, que não gera notificação nenhuma sozinha). Mas ele **é agendado**, então cai
> junto se o GitHub desabilitar as agendas — não se auto-vigia, e isso está declarado no cabeçalho do
> próprio arquivo em vez de escondido.
>
> Mitigação real, verificada na documentação do GitHub: **o GitHub envia e-mail de aviso ao admin
> antes de desabilitar**. Somado ao digest diário parando de chegar no Telegram, são dois sinais.
> Cobertura completa exigiria um verificador fora do GitHub; avaliado e descartado — o Cloudflare
> Workers free limita trigger agendado a **10 ms de CPU**, e nenhuma outra opção gratuita compensava
> a infraestrutura nova neste tamanho de projeto. **Fica como risco aceito e consciente.**

**Afirmação.** O GitHub desabilita workflows agendados em repositório público após 60 dias sem
atividade. Nada no projeto detecta isso.

**Evidência.** Documentação do GitHub: *"in public repositories, scheduled workflows are automatically
disabled when no repository activity has occurred in 60 days"*. Registrado em
`docs/RUNBOOK_DEPLOY.md` e no ADR-076, mas sem mecanismo de detecção.

**Impacto.** O ciclo operacional para em silêncio. Não há execução falhando, logo não há notificação
de falha — o modo de falha é ausência, não erro. O único sinal prático é o digest diário parar de
chegar no Telegram, o que depende de o operador reparar na ausência.

**Severidade: P2.** Só se materializa após 60 dias de inatividade, e o projeto está em
desenvolvimento ativo. Vira P1 se o projeto entrar em modo de manutenção.

**Solução proposta.** O `operational-watchdog` já detecta ledger ausente, mas roda dentro do mesmo
workflow que seria desabilitado — não serve. A detecção precisa vir de fora: o mesmo verificador
externo do A-04 pode checar a data da última execução via API do GitHub.

**Risco da correção.** Baixo.

---

### A-06 · 14 documentos citam `infra/gcp/`, caminho que não existe mais

**Afirmação.** A remoção do Google Cloud deixou referências a caminhos inexistentes espalhadas pela
documentação.

**Evidência.** `grep -rln "infra/gcp" docs/` → 14 arquivos. Também 3 arquivos citam runbooks
removidos (`RUNBOOK_GOOGLE_CLOUD_*`, `RUNBOOK_SLO_ALERTS`, `RUNBOOK_WATCHDOG`).

**Impacto.** Assimétrico, e a distinção importa para não gerar trabalho inútil. A maioria são **ADRs
e auditorias datados** — registros históricos que devem descrever o que era verdade quando foram
escritos e **não devem ser reescritos**. O problema real está nos poucos documentos *operacionais*
ainda ativos, principalmente `docs/CHECKLIST_REMEDIACAO_AUDITORIA.md`, que um operador pode tentar
seguir hoje.

**Severidade: P2.**

**Solução proposta.** Não fazer varredura cega. Classificar cada um: histórico (deixar intacto) ou
operacional ativo (marcar obsoleto no topo, como já foi feito em `runbook-producao.md` e
`RUNBOOK_ROTACAO_CREDENCIAL_OPERACIONAL.md`).

**Risco da correção.** Baixo, com um risco real de excesso: reescrever ADR histórico destrói o
registro de por que decisões foram tomadas. `ADR-025`, `ADR-026`, `ADR-041` e `ADR-042` já receberam
cabeçalho de "substituído" — esse é o padrão, não a edição do corpo.

---

### A-07 · A produção vai rodar num plano que o próprio provedor não recomenda para produção

**Afirmação.** O plano free do Render é destinado a hobby e protótipo, e a arquitetura o usa como
plataforma de produção.

**Evidência.** `render.yaml:24` — `plan: free`. Documentação do Render sobre o plano free: hiberna
após 15 min sem tráfego, cold start de 30–60 s, 750 h/mês por workspace, 512 MB de RAM.

**Impacto.** Cold start de até 1 minuto na primeira visita, sem garantia de disponibilidade
contratual. Para um dashboard de um único usuário, é uma troca consciente e razoável — está registrada
no ADR-076 e no runbook.

**Severidade: P2**, e é **risco aceito**, não defeito. Documentado aqui para que a próxima IA não o
"descubra" como novidade nem tente resolvê-lo com keep-alive (ver § _O que NÃO fazer_).

**Solução proposta.** Nenhuma no momento. Reavaliar apenas se houver orçamento ou se o produto passar
a ter mais de um usuário.

**Risco da correção.** N/A.

---

## P3 — qualidade

### A-08 · O ruff roda com regras `F` desligadas

**Afirmação.** A configuração do linter seleciona apenas as regras `E` (pycodestyle), deixando de fora
`F` (Pyflakes) — que detecta import morto, variável não usada e nome indefinido.

**Evidência.** `pyproject.toml:66` — `select = ["E"]`.

**Impacto.** Dois imports mortos sobreviveram a várias rodadas de CI verde e só foram encontrados por
revisão manual nesta sessão. `F821` (nome indefinido) também está desligado, e essa é uma regra que
pega erro real de execução, não só estilo.

**Severidade: P3.** Não há quebra conhecida; é a rede de proteção que está mais fraca do que aparenta.

**Solução proposta.** `select = ["E", "F"]`, corrigindo o que aparecer. Considerar `I` (ordenação de
imports) num passo separado, para não misturar ruído com sinal.

**Risco da correção.** Baixo, mas provavelmente ruidoso na primeira execução. Fazer em commit próprio,
sem misturar com mudança funcional.

---

### A-09 · Sem verificação automatizada de acessibilidade no CI

**Afirmação.** Existem 85 arquivos de teste de frontend, incluindo teste de contraste, mas nenhuma
verificação de acessibilidade roda como gate no CI.

**Evidência.** `git ls-files "frontend/src/**/*.test.*"` → 85 arquivos. `.github/workflows/ci.yml`,
job `frontend`, executa `npm test`, `npm run type-check` e `npm run check-bundle-budget` — não há
passo dedicado de a11y. O projeto declara WCAG 2.2 AA como linha de base
(`.claude/skills/wcag-aa`).

**Impacto.** Regressão de acessibilidade passa despercebida entre revisões manuais.

**Severidade: P3.**

**Solução proposta.** Fora do escopo desta migração. Registrar como dívida; a skill `wcag-aa` e o
agente `accessibility-specialist` já existem para conduzir isso quando for priorizado.

**Risco da correção.** N/A no momento.

---

## Verificado e correto — não reauditar sem motivo

Registrado para poupar trabalho da próxima sessão. Cada item foi confirmado nesta auditoria:

| Área | Evidência |
|---|---|
| Isolamento multi-tenant | RLS ativo (`migrations/versions/20260802_0040_enable_postgresql_rls.py`), contexto por transação em `src/mplacas/db/tenant_context.py:95-106`, bypass exige `mplacas.platform_bypass` |
| Segredos no código | `grep` por literais de credencial em `src/`, `scripts/`, `migrations/` → nenhum. `.env` real não versionado |
| Varredura de segredos | gitleaks no CI (`security.yml:36`), 9 exceções por fingerprint exato |
| Análise estática de segurança | CodeQL no CI, passando |
| Cadeia de suprimentos | Ações fixadas por SHA de 40 caracteres, dependências com `--require-hashes`, gate de drift de lockfile |
| Dependências do Google | Zero. Nenhum import, SDK, credencial ou pacote — removidos no commit `0088b48` |
| Lint de shell | Restaurado no job `shell-lint`, escopado por `git ls-files '*.sh'` |
| Segredos nos workflows | Escopados por passo; `pip install` não os enxerga (`test_deployment_workflows_contract.py`) |
| Gates locais | ruff, mypy e 821 testes passando no commit `556561a` |

---

## Ordem de execução recomendada

Ordem pensada para desbloquear produção cedo e evitar retrabalho — **não** é ordem de severidade.

| # | Ação | Achado | Por que nesta posição |
|---|---|---|---|
| 1 | ~~Corrigir CSP + `.env.production` + teste-guarda~~ | A-01, A-02 | ✅ **feito em 2026-08-27** (`4311d18`) |
| 2 | ~~Atualizar `RUNBOOK_DEPLOY.md` § 2.3~~ | A-01 | ✅ **feito em 2026-08-27** — § 2.3 reescrito e sintoma adicionado à tabela de diagnóstico |
| 3 | Mesclar o PR #129, que também conserta a `main` | A-10 | Enquanto a `main` estiver vermelha, nenhum gate protege trabalho novo |
| 4 | Decidir e registrar o RPO real | A-03 | Decisão do dono, não técnica. Precisa sair antes do go-live para não prometer o que não entrega |
| 5 | Executar o deploy (segredos → merge → migrate → jobs → Render → frontend) | — | Só depois de 1–4 |
| 6 | ~~Verificador externo de disponibilidade~~ | A-04, A-05 | ✅ **feito em 2026-08-27** — ativa sozinho quando `VITE_API_URL` deixar de apontar para o Google Cloud |
| 7 | Triagem do drift de documentação | A-06 | Não bloqueia nada |
| 8 | `select = ["E", "F"]` no ruff, em commit isolado | A-08 | Ruidoso; não misturar com mudança funcional |
| 9 | Gate de acessibilidade | A-09 | Dívida registrada, priorização separada |

---

## O que NÃO fazer

Armadilhas onde a correção óbvia é errada. Duas já foram propostas por revisão automatizada e
**rejeitadas com evidência** — não reabrir sem trazer prova nova.

1. **Não "corrigir" `timezone:` no cron do `operational-jobs.yml`.** É chave válida, GA desde
   março/2026. Uma revisão com corte de conhecimento anterior a essa data já a apontou como inválida.
   Removê-la faz o ciclo rodar às 03:07 em vez de 06:07.
2. **Não "restaurar" o agendamento do `restore-drill.yml` achando que o PR o removeu.** A `main` já
   era manual-only pelo commit `95f6726` do próprio dono. Conferir o diff antes de agir. Religar é
   uma decisão legítima (A-03), mas é decisão, não conserto de regressão.
3. **Não criar keep-alive contra o cold start do Render.** Consome as 750 h/mês (o mês tem ~730) e
   mantém o Neon acordado — foi exatamente isso que estourou a cota de compute em 2026-08-21.
4. **Não relaxar o CSP para `connect-src https:`** como atalho do A-01. `test_frontend_auth_contract.py:118`
   proíbe explicitamente, e permitiria exfiltração para qualquer host.
5. **Não restaurar o projeto no Google Cloud.** Está excluído e reversível por 30 dias a partir de
   2026-08-26. Restaurar reativa o serviço e os 12 Cloud Run Jobs. Proibido por
   `docs/POLITICA_SEM_GOOGLE_CLOUD.md`; revogar exige ADR novo.
6. **Não reescrever ADRs e auditorias históricas** para remover menções ao Google Cloud. São registro
   datado. O padrão do projeto é cabeçalho de "substituído", não edição do corpo.
7. **Não tratar a janela de 6 h do PITR do Neon como garantia** sem reconfirmar no painel. Foi
   confirmada em 2026-08-03, e termos de free tier deste projeto já mudaram uma vez com consequência
   grave.

---

## Nota de método

O A-01 sobreviveu a três revisões — a minha varredura de remoção do Google Cloud, a revisão do
ChatGPT e uma revisão de código de alto esforço. Todas buscaram por `google`, `gcloud`, `google-cloud`
e `cloud run`. A string real no arquivo é `run.app`, que não casa com nenhum desses padrões.

Lição registrada para a próxima auditoria: ao remover um provedor, buscar também pelos **domínios e
identificadores concretos** dos recursos — `run.app`, `appspot.com`, o número do projeto
(`104231254500`), o ID do projeto — e não apenas pelo nome comercial do provedor. Um `grep` pelo
número do projeto teria encontrado o `_headers`, o `.env.production` e o teste-guarda de uma vez.
