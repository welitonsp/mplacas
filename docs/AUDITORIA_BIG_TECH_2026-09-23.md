# Auditoria de escalabilidade — Mplacas — 2026-09-23

Escopo: backend, domínio solar/NEPViewer, frontend e operação. Executada pelos agentes
`architect`, `solar-domain-specialist` e `frontend-architect`, consolidada e com os achados P0
conferidos contra o código. Não repete o que já foi fechado em
`AUDITORIA_BIG_TECH_2026-08-01.md` e `AUDITORIA_BIG_TECH_2026-08-26.md`.

Restrições que valem para toda recomendação abaixo: custo zero (`POLITICA_CUSTO_ZERO.md`) e
Google Cloud proibido (`POLITICA_SEM_GOOGLE_CLOUD.md`). "Escalável" aqui significa crescer de 1
para N usinas / fornecedores / organizações sem reescrita, dentro das franquias gratuitas.

## Veredito

A fundação é sólida: motores de cálculo puros (`photovoltaic/*`, `intelligence/*_engine.py` não
importam SQLAlchemy nem FastAPI), API sem estado em memória, RLS no PostgreSQL, testes contra
Postgres real com `alembic check`, lockfiles com hash e SBOM. O que falha é a operação: **o
sistema está parado em produção e nada avisou.** O limite estrutural de crescimento está nos
jobs, que continuam de uma conta e uma organização enquanto schema, auth e RLS já são multi-tenant.

## P0 — produção quebrada ou risco imediato

| # | Achado | Evidência | Estado em 2026-09-23 |
|---|---|---|---|
| 1 | Ciclo diário falhou todos os dias desde 28/08. Até 18/09 por falta de segredos; depois porque o passo `daily-pipeline` exige o token do Telegram e o workflow não o repassava. A coleta NEPViewer funciona desde 18/09; análise, alertas e vigia não. | `src/mplacas/cloud_jobs.py:519`, `.github/workflows/operational-jobs.yml:130`, run 35872372368 | Corrigido na branch `fix/ciclo-diario-token-telegram` (c23511f), com teste de contrato que falha sem a correção |
| 2 | Dashboard fora do ar: `VITE_API_URL` aponta para o Cloud Run excluído. `watchdog.yml` fica verde porque se desativa nesse caso. | variável de repositório; `watchdog.yml:67-72` | Aberto — publicar API no Render e trocar a variável (`RUNBOOK_DEPLOY.md`) |
| 3 | Laço de relogin: 401/403 persistente chama `_post` recursivamente sem limite → rajada de logins na conta NEP e `RecursionError`, que não é `ProviderError` e escapa da fila de retentativa. Sem teste de 401. | `providers/nepviewer/client.py:81-85`, `collection/job.py:63` | Aberto (P) |
| 4 | D-1 consolidado sem checar completude e nunca recoletado; valor `null` conta como dia coberto. Contraria ADR-047:57-58. | `collection/job.py:46-51`, `client.py:203-205` | Aberto (P) |
| 5 | `npm audit --audit-level=high` reprova `sharp` via `wrangler`→`miniflare` (GHSA-rgj7-g3m4-5g8c, dependência só de deploy) antes de qualquer teste de frontend. Todo PR novo nasce vermelho. | `.github/workflows/ci.yml:206` | Aberto (P) — bloqueia o PR do item 1 |
| 6 | GitHub desativa workflows agendados de repo público após 60 dias sem atividade; último commit na `main` em 27/08 → ~26/10. Inclui a coleta. | `git log` | Resolvido por qualquer merge na `main` |

## P1 — confiabilidade

**Operação e backend**
- **Detecção de falha levou 26 dias.** Único alerta é o e-mail do GitHub (`operational-jobs.yml:13-15`).
  Recomendação: passo final `if: failure()` com aviso curto ao Telegram via `curl`; linha de SLI no
  digest ("ciclo de ontem: X/Y usinas OK"). (P)
- **Análise acoplada ao segredo de entrega.** `orchestration/daily_pipeline.py:62,201` recebe
  `TelegramAlertProvider`, mas pelo ADR-040 a análise só grava no outbox. Passar apenas
  `provider_name` e `destination_ref`; exigir token só em `dispatch-outbox`/`daily-digest`;
  opção `--suppress-alerts-before` para backfill. Confirmar na implementação que o pipeline não envia direto. (M)
- **Contrato de env por subcomando.** Generalizar o teste do item 1: mapa `REQUIRED_ENV` em
  `cloud_jobs.py` usado pelo código e pelo teste do YAML. (P)
- **Scanner de segredos com falso positivo desde agosto.** `.gitleaks.toml` usava `[[allowlists]]`,
  que o gitleaks 8.24.3 pinado no CI ignora em silêncio. Corrigido para `[allowlist]` na branch
  `fix/ciclo-diario-token-telegram` (714d28c), validado com o binário 8.24.3 e teste de mutação.

**Domínio solar / NEPViewer**
- **Fuso do portal nunca verificado** (nenhuma menção a UTC+8 no repo; datas parseadas sem fuso em
  `client.py:110-125`). Conferir o fuso da usina no portal e testar defasagem produção × GHI (0 vs ±1 dia); registrar em ADR.
- **Falta de comunicação vira 0 kWh.** `lastUpdate` é lido (`client.py:143`) e descartado
  (`services/collection.py:79-84`); INCOMPLETE nunca é gravado (`collection.py:90-95`). Gravar
  INCOMPLETE/UNAVAILABLE quando `lastUpdate` for anterior ao fim do dia-alvo.
- **Coleta de janela.** Buscar sempre D-7..D-1 (mesma requisição por aparelho, custo zero), manter
  PROVISIONAL até D-3, ligar `expect_complete`.
- **Ciclo de fatura ignora falha parcial.** Dia com 1 de N microinversores faltando entra como completo
  (`intelligence/cycle_service.py:84-88`); `max(0, …)` em `billing/models.py:93` esconde produção < injeção.
- **Retenção destrói a âncora da degradação.** `seasonal_baseline.py:83` ancora na primeira observação
  existente; `retention/timeseries_service.py:94-98` apaga após 1825 dias. Preservar o primeiro ano ou gravar a âncora.
- **HTTP 429 tratado como mudança de schema** (`client.py:89-92`). Tratar como indisponibilidade temporária, respeitando `Retry-After`.

**Frontend**
- **Login falha no cold start.** `AUTH_TIMEOUT_MS = 15_000` (`frontend/src/lib/api.ts:14`) contra 30–60 s
  do Render free; a mensagem culpa a conexão. Pré-aquecer com `GET /health` ao montar Login/Home,
  prazo ~60 s, texto "Iniciando o servidor…" após ~5 s. Não viola invariante (é chamado só por visita humana). (P)
- **"Tentar novamente" desloga.** `window.location.reload()` em `OverviewPage.tsx:385`,
  `ProductionPage.tsx:164`, `FinancialPage.tsx:74`, `TechnicalPage.tsx:124`; sessão é em memória (ADR-073).
  Expor `reload()` no `PlantContext`. (P)
- **PR #151 não é segura como está.** Runtime/patches são baixo risco, mas vitest 4→5 e jsdom 25→30
  vieram juntos e o teste local foi instável. Dividir em (a) runtime e (b) infraestrutura de teste. (M)

## P2 — escalabilidade de 1 para N

**Multi-usina / multi-conta (pré-requisito A do ADR-070, ainda aberto)**
- Coleta com uma conta NEP e usina fixa por nome (`cloud_jobs.py:305-350`, `config.py:39-40`);
  `SolarDevice` sem usina (`providers/base.py:32-37`); unicidade `(provider, serial_number)` global
  (`db/models.py:110`); `"NEPVIEWER"` fixo em `services/collection.py:123,131`.
- Jobs só processam `DEFAULT_ORGANIZATION_ID` (`cloud_jobs.py:239, 536, 740`); organização criada pelo
  onboarding (ADR-054) nunca é processada. ADR-045 segue "Aceito" sem marca de substituído pelo ADR-053.
- `device/list` sem paginação (`client.py:128`, `size: 100`): do 101º microinversor em diante somem sem aviso.
- Orientação só por usina (`db/models.py:84-90`): telhado de duas águas gera POA/PR errados.
- **Requer decisão do dono** por mudar o schema; passar pelo `reviewer`.

**Carga (estimativa, não medida)**
- 5–20 s por usina no pipeline sequencial. 10 usinas: +1–3 min/dia. 100 usinas: 8–33 min, estoura
  `timeout-minutes: 30` (`operational-jobs.yml:50`). Saída gratuita: `strategy.matrix` por hash da usina.
- Compute do Neon para jobs ~4–5 CU-h/mês, cabe na franquia. O teto real é o uso interativo da API.
- Instrumentar duração por usina a partir de `pipeline_executions` antes de otimizar.
- Não particionar séries temporais: granularidade diária, ~365 mil linhas/ano com 100 usinas × 10 inversores.

**Engenharia**
- `cloud_jobs.py` (821 linhas) e `alerts/production_alert.py` (767): pacote `jobs/` com um módulo por
  comando; travar camadas com `import-linter`. Docstring obsoleta cita Cloud Run (`cloud_jobs.py:756`).
- Suíte de contrato parametrizada para `SolarProvider` + registro `provider_name → factory`.
- Cobertura (`pytest-cov`) com gate só nos pacotes de risco.
- Postgres divergente: CI 16 (`ci.yml:144`), restore drill 18 (`restore-drill.yml:23`); alinhar ao Neon.
- SLOs sobre os ledgers do banco: D+1 consolidado até 09:00; ≥95% de ciclos OK em 7 dias; idade do
  evento mais antigo no outbox. Decidir se OTLP fica documentado como desligado ou sai do código.
- `environment: production` restrito à `main` para os segredos dos jobs.
- Frontend: cache por `(recurso, plantId)` com TTL curto no `usePlantResource` e `AbortSignal`;
  teste Python que confere os campos consumidos pelos parsers contra `app.openapi()`;
  `toHaveScreenshot` nas 4 rotas do dashboard; `@axe-core/playwright` no job `captura-visual` (A-09).

**Domínio solar**
- Detecção de microinversor com defeito por comparação com vizinhos no mesmo dia (kWh/kWp, mesma
  orientação). Hoje proibida pela Restrição 2 do ADR-074 — **decisão do dono**. No nível da usina,
  1 microinversor parado em 8 (~12,5%) não é detectado (`loss_taxonomy.py:157-165`).
- Correção térmica usa temperatura média de 24 h (`poa.py:103-109`): viés sistemático para baixo.
- Produção esperada é teto de céu limpo P90 (`expected_production.py:59`); a UI não pode chamá-la de "esperado" sem qualificar.
- Curva intradiária não coletada: verificar se `echarts` com outro `types` a devolve; é o dado que o portal guarda por menos tempo.
- Golden datasets: 4 casos sintéticos `PENDING`. Priorizar POA contra PVGIS, resposta NEP com `null`/`0`, 401 persistente.

## Roteiro

**Agora**
1. Corrigir o gate do `npm audit` (P0-5): bloqueante com `--omit=dev`, depois de testes e build.
2. Publicar e mesclar `fix/ciclo-diario-token-telegram`.
3. Rodar `backfill.yml` com pipeline de 18/09 até a data do merge (esperar lote de alertas; ver cabeçalho do workflow).
4. Corrigir P0-3 e P0-4 na coleta.
5. Publicar a API no Render e trocar `VITE_API_URL` (P0-2).
6. Alerta de falha no Telegram e desacoplamento análise/entrega.

**Próximos 3 meses:** restante do P1; vínculo usina↔conta de provedor; jobs por organização;
paginação de dispositivos; SLOs e instrumentação de duração.

**Se virar produto (só documentar):** ADR com os limiares que forçariam revisar a política de custo
zero (>70 CU-h/mês, p95 do ciclo >15 min, >1 organização ativa) — decisão exclusiva do dono;
cofre de credenciais de saída por organização (pré-requisito B do ADR-070).

## Decisões pendentes do dono

1. Reabrir a Restrição 2 do ADR-074 (comparação entre microinversores vizinhos).
2. Autorizar a mudança de schema para N usinas / N contas de provedor.
