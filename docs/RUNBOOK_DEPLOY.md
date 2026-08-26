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
  - **direta** — sem `-pooler`. É só a das migrações; DDL não passa pelo pooler.

## Parte 1 — jobs operacionais no GitHub Actions

Faça esta parte primeiro: ela repõe a coleta de dados e independe da API estar no ar.

### 1.1 Cadastrar os secrets

Em **Settings → Secrets and variables → Actions → Secrets**, aba *Repository secrets*:

| Secret | Valor |
|---|---|
| `MPLACAS_DATABASE_URL` | URL **pooled** do Neon |
| `MPLACAS_MIGRATION_DATABASE_URL` | URL **direta** do Neon |
| `MPLACAS_OPERATIONS_API_KEY` | chave operacional |
| `MPLACAS_JWT_SECRET` | segredo JWT (mínimo 32 bytes) |
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

O primeiro passo é `smoke`: valida configuração e conectividade **sem escrever nada**. Se ele falhar,
pare e corrija os secrets — não adianta seguir.

Depois disso o ciclo roda sozinho todo dia às **09:07 UTC (06:07 em Brasília)**.

## Parte 2 — API no Render

### 2.1 Criar pelo Blueprint

New → **Blueprint** → aponte para `welitonsp/mplacas` → o Render lê o `render.yaml` da raiz.

O Blueprint já fixa: plano free, Docker, health check em `/health`, CORS travado na URL exata do
Cloudflare Pages, e as 7 variáveis sensíveis como `sync: false`.

### 2.2 Preencher os segredos no dashboard

O Render vai pedir os 7 valores marcados `sync: false`. Use a URL **pooled** do Neon em
`MPLACAS_DATABASE_URL` — a direta é exclusiva das migrações.

Nunca coloque esses valores em arquivo do repositório: **ele é público**.

### 2.3 Apontar o frontend para a nova URL

O Render publica em `https://mplacas-api-<sufixo>.onrender.com`. Atualize `VITE_API_URL` no projeto
do Cloudflare Pages e refaça o deploy do frontend.

Se mudar o domínio do frontend, atualize também `MPLACAS_CORS_ALLOWED_ORIGINS` no `render.yaml` —
curinga (`*`) é proibido por design.

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

## Diagnóstico rápido

| Sintoma | Causa provável |
|---|---|
| Dashboard não carrega, API responde depois de ~1 min | Cold start normal do plano free |
| Erro de CORS no navegador | `MPLACAS_CORS_ALLOWED_ORIGINS` diferente da URL real do Pages |
| Digest parou sem falha visível no Actions | Agendas desabilitadas por 60 dias de inatividade |
| `smoke` falha com erro de conexão | URL do Neon errada, ou trocada a pooled pela direta |
| Migração falha com erro de DDL | Usou a URL pooled; DDL exige a direta |
