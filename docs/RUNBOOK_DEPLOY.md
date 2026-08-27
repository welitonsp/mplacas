# Runbook — colocar o Mplacas no ar (Render + GitHub Actions)

Substitui `RUNBOOK_GOOGLE_CLOUD_DEPLOYMENT.md` e `RUNBOOK_GOOGLE_CLOUD_RUN.md`, removidos com a
saída do Google Cloud. Contexto e justificativa da escolha: `docs/ADR-076-saida-do-google-cloud.md`.

Custo total desta arquitetura: **zero**. Nenhum passo abaixo pede cartão de crédito.

## Pré-requisitos

- Conta no Render (login com GitHub serve).
- O projeto Neon existente. **Não** crie banco novo — o Neon nunca esteve no Google Cloud e os dados
  seguem lá.
- As duas URLs do Neon, no painel do projeto:
  - **pooled** — hostname contém `-pooler`. É a do runtime e a dos jobs diários.
  - **direta** — sem `-pooler`. É a recomendada pelo Neon para migrações de schema, evitando as
    limitações do PgBouncer em modo transação.

Não reative o Google Cloud para recuperar configuração. Se algum valor existia apenas no Secret
Manager antigo, rotacione-o na origem: senha/role no Neon, token no BotFather e senha na NEPViewer.
As chaves internas (`MPLACAS_OPERATIONS_API_KEY`, `MPLACAS_JWT_SECRET` e
`MPLACAS_TELEGRAM_WEBHOOK_SECRET`) podem ser novas; gere valores aleatórios fortes e mantenha-os
somente nos cofres do GitHub/Render.

## Parte 0 — publicar a mudança

O agendamento do GitHub só funciona quando o workflow existe na branch padrão (`main`). Antes das
partes abaixo, aprove e faça merge do PR desta migração. Não tente executar os arquivos apenas de
uma branch local.

## Parte 1 — jobs operacionais no GitHub Actions

Faça esta parte primeiro: ela repõe a coleta de dados e independe da API estar no ar.

### 1.1 Cadastrar os secrets

Em **Settings → Secrets and variables → Actions → Secrets**, aba *Repository secrets*:

| Secret | Valor |
|---|---|
| `MPLACAS_DATABASE_URL` | URL **pooled** do Neon |
| `MPLACAS_MIGRATION_DATABASE_URL` | URL **direta** do Neon |
| `MPLACAS_OPERATIONS_API_KEY` | chave operacional |
| `MPLACAS_TELEGRAM_BOT_TOKEN` | token do bot |
| `MPLACAS_NEP_ACCOUNT` | conta NEPViewer |
| `MPLACAS_NEP_PASSWORD` | senha NEPViewer |

### 1.2 Cadastrar as variables

Mesma tela, aba *Variables* — estes **não** são segredos, são identificadores e capacidades:

| Variable | Valor |
|---|---|
| `MPLACAS_TELEGRAM_ALERT_CHAT_ID` | ID do chat de alerta |
| `MPLACAS_CLOUD_JOB_PLANT_NAME` | nome exato da usina |
| `MPLACAS_CLOUD_JOB_EXPECTED_DAILY_PRODUCTION_KWH` | produção diária esperada |
| `MPLACAS_CLOUD_JOB_EXPECTED_CYCLE_PRODUCTION_KWH` | opcional |

### 1.3 Aplicar migrações pendentes

Actions → **migrate** → *Run workflow* → digite `MIGRAR` no campo de confirmação.

O workflow recusa qualquer outro valor. Ele usa a URL direta.

### 1.4 Validar o ciclo operacional

Actions → **operational-jobs** → *Run workflow* (deixe a data alvo vazia = ontem).

O primeiro passo é `smoke`: valida todos os secrets/variables do ciclo e a conectividade com o
banco **sem escrever nada**. Se ele falhar, pare e corrija a configuração — não adianta seguir.

Depois disso o ciclo roda sozinho todo dia às **06:07 no fuso `America/Sao_Paulo`**.

## Parte 2 — API no Render

### 2.1 Criar pelo Blueprint

New → **Blueprint** → aponte para `welitonsp/mplacas` → o Render lê o `render.yaml` da raiz.

O Blueprint já fixa: plano free, Docker, health check em `/health`, CORS travado na URL exata do
Cloudflare Pages, deploy somente após o CI passar, e as 8 variáveis sensíveis como `sync: false`.

### 2.2 Preencher os segredos no dashboard

O Render vai pedir os 8 valores marcados `sync: false`. Use a URL **pooled** do Neon em
`MPLACAS_DATABASE_URL` — a direta é exclusiva das migrações.

Nunca coloque esses valores em arquivo do repositório: **ele é público**.

### 2.3 Apontar o frontend para a nova URL

O Render publica em `https://mplacas-api-<sufixo>.onrender.com`.

1. No GitHub, em **Settings → Secrets and variables → Actions → Variables**, edite `VITE_API_URL`
   com a URL do Render, **sem barra no final e sem caminho** — só o endereço base.
2. Rode o workflow **Deploy Frontend** (Actions → Deploy Frontend → Run workflow, branch `main`).

São **duas** coisas que precisam apontar para a mesma origem: o cliente HTTP e o
`Content-Security-Policy` que o navegador aplica. Desde a auditoria de 2026-08-26 (achado A-01) as
duas saem da mesma variável: `frontend/scripts/render-csp.mjs` resolve o marcador `__API_ORIGIN__`
em `dist/_headers` durante o `npm run build`. **Não escreva a origem à mão no `_headers`** — o
script falha de propósito se o marcador sumir, e o teste de contrato também.

Antes desse conserto, o `_headers` trazia a origem fixa da API no Google Cloud. Trocar apenas
`VITE_API_URL` deixava o CSP apontando para o endereço antigo, e o navegador bloqueava **todas** as
chamadas do dashboard: a tela carregava, o login falhava, e não havia erro de servidor, log de API
nem CI vermelho para explicar. Se algum dia você vir esse sintoma, abra o console do navegador e
procure por violação de CSP antes de investigar o backend.

Se mudar o domínio do frontend, atualize também `MPLACAS_CORS_ALLOWED_ORIGINS` no `render.yaml` —
curinga (`*`) é proibido por design.

### 2.4 Registrar o webhook do Telegram na API nova

O endereço do webhook muda junto com a API. No PowerShell, leia os dois segredos sem colocá-los no
histórico do terminal e registre `https://<URL-DO-RENDER>/telegram/webhook`:

> `ConvertFrom-SecureString -AsPlainText` **não existe** no Windows PowerShell 5.1, que é a versão
> desta estação. O trecho abaixo usa o marshalling clássico, que funciona em 5.1 e também em 7+.

```powershell
function ConvertTo-PlainText([Security.SecureString]$Secure) {
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
  try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

$botTokenSecure = Read-Host "MPLACAS_TELEGRAM_BOT_TOKEN" -AsSecureString
$webhookSecretSecure = Read-Host "MPLACAS_TELEGRAM_WEBHOOK_SECRET" -AsSecureString
$botToken = ConvertTo-PlainText $botTokenSecure
$webhookSecret = ConvertTo-PlainText $webhookSecretSecure

$telegramApi = "https://api.telegram.org/bot$botToken/setWebhook"
$body = @{
  url = "https://<URL-DO-RENDER>/telegram/webhook"
  secret_token = $webhookSecret
}
$result = Invoke-RestMethod -Method Post -Uri $telegramApi -Body $body
if (-not $result.ok) { throw "Telegram recusou o webhook" }

Remove-Variable botToken, webhookSecret, botTokenSecure, webhookSecretSecure
```

Substitua `<URL-DO-RENDER>` pelo hostname real, sem `https://` duplicado. O comando não imprime os
segredos; a resposta esperada contém `ok: true`.

## Recuperar dias em que o ciclo não rodou

Se o ciclo diário ficar parado — cota do Neon esgotada, agenda desabilitada, provedor fora do ar —
a telemetria daqueles dias **não se perde**. O NEPViewer serve histórico por intervalo, então dá
para recuperar depois.

Actions → **backfill** → *Run workflow*:

| Campo | O que informar |
|---|---|
| `data_inicial` | primeiro dia parado (YYYY-MM-DD) |
| `data_final` | último dia parado — precisa ser **anterior a hoje**, porque o dia corrente ainda está incompleto |
| `incluir_pipeline` | `true` recupera coleta **e** análise; `false` traz só os dados brutos |
| `confirmacao` | digite `BACKFILL` |

O workflow valida o intervalo antes de instalar qualquer coisa, recusa data inexistente ou invertida,
e tem teto de 60 dias — um ano digitado errado viraria centenas de execuções contra o provedor.

Ele compartilha o grupo de concorrência com o ciclo diário, então os dois nunca escrevem ao mesmo
tempo no mesmo banco: um espera o outro.

### Espere um lote de alertas depois

Com `incluir_pipeline: true`, o `daily-pipeline` enfileira **um evento de alerta por dia
recuperado**. Isso não dá para desligar: desde a ADR-068/069 a expectativa vem de cada usina e a
função exige Telegram configurado.

O backfill **não entrega** esses eventos de propósito — não roda `dispatch-outbox` nem
`daily-digest`. Mas eles ficam na fila, e o **próximo ciclo diário vai entregá-los de uma vez**.

Isso é esperado, não defeito. Cada mensagem é datada. Se preferir só os dados sem análise nem
alerta, rode com `incluir_pipeline: false`.

## Comportamento esperado que **não** é defeito

- **Primeira visita ao dashboard demora de 30 a 60 s.** O plano free hiberna após 15 min sem
  tráfego. É o preço do custo zero, e ajuda o Neon a dormir.
- **Não instale keep-alive para "resolver" isso.** As 750 h/mês mal cobrem um mês (~730 h) e manter
  o Neon acordado 24 h foi exatamente o que estourou a cota de compute em 2026-08-21.

## Manutenção periódica

| Quando | O quê |
|---|---|
| Diário, passivo | O digest chega no Telegram. **Não chegou = investigue**, é o principal sinal de saúde |
| A cada falha | O GitHub notifica falha do `operational-jobs`. Abra o run e leia o passo que quebrou |
| A cada 60 dias | Qualquer atividade no repositório mantém as agendas vivas. Sem atividade, o GitHub **desabilita workflows agendados** de repositório público e o digest para |
| Mensal | Conferir consumo de compute no painel do Neon |

> **Risco temporário:** o restore drill foi mantido apenas manual pela política presente na
> `main`. Até os secrets de backup serem reconfigurados e uma agenda gratuita ser aprovada, a meta
> de RPO de 24 horas não está garantida. Isso não autoriza reativar o Google Cloud.

## Diagnóstico rápido

| Sintoma | Causa provável |
|---|---|
| Dashboard não carrega, API responde depois de ~1 min | Cold start normal do plano free |
| Erro de CORS no navegador | `MPLACAS_CORS_ALLOWED_ORIGINS` diferente da URL real do Pages |
| Tela carrega mas nenhuma chamada completa, console acusa violação de CSP | `connect-src` aponta para outra origem — rodou o build sem `VITE_API_URL` correta (ver § 2.3) |
| Digest parou sem falha visível no Actions | Agendas desabilitadas por 60 dias de inatividade |
| `smoke` falha com erro de conexão | URL do Neon errada, ou trocada a pooled pela direta |
| Migração falha por limitação de sessão/DDL | Usou a URL pooled; use a direta recomendada pelo Neon |
