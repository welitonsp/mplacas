# Plano de execução — Auditoria de frontend 2026-08-12

**Base:** `HEAD a8e2fe4` (`main`, working tree limpo na emissão deste plano).
**Origem:** auditoria de frontend de 2026-08-12 e sua revisão crítica (4 correções de autorrevisão).
**Auditorias anteriores relacionadas:** `docs/UI_UX_AUDIT_2026-08-04.md`, `docs/CHECKPOINT_UI_UX_FRONTEND_2026-08-09.md`.

Legenda: `[x]` concluído · `[~]` parcial · `[ ]` pendente.

---

## 0. Protocolo obrigatório anti-alucinação

**Leia esta seção inteira antes de tocar em qualquer arquivo. Ela existe porque a auditoria
que originou este plano continha 4 afirmações falsas, todas do mesmo tipo.**

### 0.1 A lição que gerou este protocolo

A primeira versão da auditoria afirmou que *"não existe entidade abaixo de usina; telemetria por
inversor não existe"*. **Isso era falso.** `Device` é entidade de primeira classe e `DailyEnergy`
é por inversor. O erro veio de concluir o que o backend "não tem" lendo apenas `router.py` e
nomes de módulo, **sem abrir `src/mplacas/db/models.py` nem a lógica de domínio**.

Consequência: uma recomendação estratégica inteira foi invertida (de "dispensável, falta dado"
para "é a recomendação nº 1, o dado já existe").

**Regra derivada:** nunca afirme que algo não existe no backend sem ter buscado nos modelos
**e** na lógica de domínio. Ausência em `router.py` prova apenas que não há rota HTTP — não
prova que não há dado, modelo ou cálculo.

⚠ **Armadilha confirmada: os modelos são divididos por módulo.**
`src/mplacas/db/models.py` contém **apenas 4 das 24 tabelas** do projeto (`plants`, `devices`,
`daily_energy`, `daily_energy_versions`). O resto vive em `src/mplacas/<modulo>/db_models.py`.
Buscar só em `db/models.py` produz exatamente o falso negativo que este protocolo existe para
evitar.

**Busca correta — sempre use estes dois comandos, nunca um caminho único:**
```bash
# inventário completo de tabelas
grep -rhoE '__tablename__ = "[a-z_]+"' src/mplacas/ | sort -u
# onde vive cada modelo
find src/mplacas -name "*models*.py" | sort
```

**As 24 tabelas do projeto (verificado em 2026-08-12):** `alert_delivery_records`,
`api_credentials`, `audit_events`, `auth_sessions`, `collection_tasks`,
`daily_climate_observations`, `daily_energy`, `daily_energy_versions`,
`daily_pv_loss_assessments`, `daily_pv_performance_results`, `daily_solar_model_results`,
`devices`, `job_runs`, `login_rate_limits`, `monthly_report_snapshots`, `operational_users`,
`organizations`, `outbox_events`, `pipeline_executions`, `plants`, `report_export_tasks`,
`seasonal_pv_baseline_results`, `user_invitations`, `utility_bills`.

### 0.2 Pré-voo obrigatório (antes de qualquer edição)

Execute e confirme:

```bash
cd /c/Mplacas
git status --short          # deve estar limpo; se houver alteração do usuário, PRESERVE
git log --oneline -1        # confirme o HEAD; se != a8e2fe4, releia a seção 1 antes de seguir
```

Se o HEAD divergir de `a8e2fe4`, **não presuma que este plano continua válido**: reexecute os
comandos de verificação da seção 1 e corrija este documento antes de implementar.

### 0.3 Regras invioláveis

1. **Toda afirmação precisa de `arquivo:linha`.** Sem evidência, escreva `NÃO VERIFICADO`.
2. **Nunca use `git checkout`, `git reset --hard`, `git clean` ou `rm -rf`** para descartar
   trabalho. Se precisar limpar, use `git stash -u` e avise.
3. **Nenhum cálculo energético ou financeiro novo no frontend.** O frontend apresenta; o backend
   calcula. Ver D11 (seção 4) — já existe uma violação a corrigir, não crie a segunda.
4. **Nunca exiba dado estimado como confirmado**, nem `0`/`—` no lugar de "indisponível".
   Indisponibilidade é estado explícito com motivo.
5. **Nunca instale dependência de runtime nova** sem ADR aprovado. Hoje são exatamente três:
   `react`, `react-dom`, `react-router`.
6. **Uma tarefa por commit/PR.** Não agrupe tarefas distintas deste plano.
7. **Quem implementa não aprova.** Ao terminar tarefa que toque em `auth`, `billing`,
   `credentials`, `organizations`, `audit`, `migrations` ou `reports/export`, delegue ao
   agente `reviewer` (ou `quality-gate-reviewer`) antes de marcar `[x]`.
8. **Não marque `[x]` sem colar, abaixo do item, o output numérico real dos testes.**

### 0.4 Gate de qualidade (obrigatório antes de fechar qualquer tarefa)

Backend (se a tarefa tocou `.py`):
```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe -m pytest -q
```

Frontend (se a tarefa tocou `frontend/`):
```bash
cd frontend
npm run test
npm run build      # <- ESTE é o type-check real
```

> ## ⛔ `npm run type-check` é NO-OP neste repositório — não o use como evidência
>
> **Provado por mutação em 2026-08-12.** Um arquivo com erro de tipo óbvio
> (`const probe: number = "texto"`) **passa** por `npm run type-check` e **falha** em
> `npm run build` (`error TS2322`).
>
> Causa: `frontend/tsconfig.json` é um *solution file* (`"files": []`, só `references`), e
> `tsc --noEmit` **sem `-b`** não percorre os projetos referenciados. Confirme você mesmo:
> ```bash
> npx tsc --noEmit --listFiles | wc -l    # retorna 0
> ```
> A checagem de tipo real acontece em `npm run build`, que roda `tsc -b && vite build`.
>
> **Consequência para quem lê o registro de execução abaixo:** toda menção a "type-check 0 erros"
> nas tarefas desta sessão é verificação vazia. Nenhum erro de tipo escapou, porque `npm run build`
> foi executado junto em todas elas — mas a evidência citada era a errada.
>
> Corrigir o script (`tsc -b --noEmit` ou equivalente) está registrado como **T8b**.

**Baseline verificado em 2026-08-12 (se seu resultado for pior, você quebrou algo):**
- `npm run test` → **73 arquivos, 793 testes, 793 passando** (~181s)
- `npm run type-check` → 0 erros
- `npm run build` → sucesso, chunks na tabela da seção 1.4
- `npm audit --omit=dev` → **0 vulnerabilidades**

---

## 1. Estado verificado do repositório

Tudo nesta seção foi confirmado por execução em 2026-08-12. Cada linha traz o comando para
reconfirmar. **Se um comando divergir do esperado, pare e atualize este documento.**

### 1.1 Stack (não presuma — está verificado)

| Item | Valor | Fonte |
|---|---|---|
| Framework | React 19.2 | `frontend/package.json:15` |
| Roteamento | `react-router` 8.3.0 | `frontend/package.json:17` |
| Build | Vite 8.2 + TypeScript 7.0 | `frontend/package.json:28-29` |
| Estilo | Tailwind CSS 4.1 (sem `tailwind.config`) | `frontend/src/index.css:1` |
| Testes | Vitest 4.1 + Testing Library + jsdom | `frontend/package.json:21-30` |
| **Deps de runtime** | **exatamente 3:** `react`, `react-dom`, `react-router` | `frontend/package.json:14-18` |
| Lib de gráfico | **nenhuma** — SVG à mão em `frontend/src/components/charts/` | — |
| Backend | FastAPI + SQLAlchemy 2.0 + PostgreSQL/SQLite | `pyproject.toml` |

### 1.2 Rotas reais do frontend

Duas de topo (`frontend/src/App.tsx`): `/login` e `/dashboard`.
Quatro filhas sob `/dashboard` (`frontend/src/routes.ts:11-14`): `visao-geral`, `producao`,
`financeiro`, `tecnico`. Qualquer outra rota redireciona.

### 1.3 Endpoints do backend × consumo no frontend

Verificar com:
```bash
grep -rnE "@router\.(get|post|patch|put|delete)" src/mplacas/*/router.py
grep -n "apiFetch(" frontend/src/lib/api.ts
```

| Endpoint | Consumido? | Onde |
|---|---|---|
| `GET /energy/executive/latest` | ✅ | `lib/api.ts:62` |
| `GET /energy/anomalies/latest` | ✅ | `lib/api.ts:72` |
| `GET /photovoltaic/summary` | ✅ | `lib/api.ts:82` |
| `GET /energy/financial-return/latest` | ✅ | `lib/api.ts:90` |
| `GET /reports/monthly/history` | ✅ | `lib/api.ts:98` |
| `GET/PATCH /plants/{id}/financial-configuration` | ✅ | `lib/api.ts:114,140` |
| `GET /plants` | ✅ | `lib/api.ts:126` |
| `GET /reports/monthly/latest` | ❌ | — |
| `GET /reports/monthly/latest.csv` | ❌ | `reports/router.py:107` |
| `GET /reports/monthly/latest.pdf` | ❌ | `reports/router.py:130` |
| `GET /reports/monthly/latest.xlsx` | ❌ | `reports/router.py:153` |
| `POST /reports/monthly/exports` | ❌ | `reports/router.py:202` |
| `GET /reports/monthly/exports/{task_id}` | ❌ | `reports/router.py:228` |
| `GET /reports/monthly/exports/{task_id}/download` | ❌ | `reports/router.py:260` |
| `GET /explanations/latest` | ❌ | `explanations/router.py:27` |
| `POST /alerts/run` | ❌ (job interno) | `alerts/router.py:56` |
| `POST /climate/collect` | ❌ (job interno) | `climate/router.py:49` |

### 1.4 Orçamento de bundle atual (gzip)

`npm run build` em 2026-08-12:

| Chunk | gzip |
|---|---|
| `index-*.js` (vendor) | 61,61 kB |
| CSS | 10,88 kB |
| `OverviewPage` | 11,73 kB |
| `ProductionPage` | 12,07 kB |
| `FinancialPage` | 7,43 kB |
| `TechnicalPage` | 6,51 kB |
| `components` (compartilhado) | 8,59 kB |
| `PlantContext` | 6,89 kB |
| `DashboardLayout` | 4,74 kB |
| `PageHeader` | 4,82 kB |
| `LoginPage` | 2,91 kB |
| `App` | 1,96 kB |

Custo inicial de `/login` ≈ **77,4 kB** · custo adicional ao abrir o dashboard ≈ **37 kB**.

### 1.5 Fatos de domínio que a auditoria errou e foram corrigidos (NÃO reintroduza)

| Fato | Evidência |
|---|---|
| `Device` é entidade real (tabela `devices`, FK `plant_id`, `serial_number`, capacidades) | `src/mplacas/db/models.py:107-138` |
| `DailyEnergy` é **por inversor** (FK `device_id`, unique `(device_id, production_date)`) | `src/mplacas/db/models.py:141-151` |
| Existe avaliação de queda **por inversor** contra a mediana do próprio inversor | `src/mplacas/alerts/production_alert.py:122-178` |
| Irradiância **é** exibida no frontend, como rendimento | `lib/dashboard/contracts.ts:124`, `lib/dashboard/yield.ts`, `ProductionHistorySection.tsx:278` |
| `react-router@8.3.0` é a versão **corrigida** do CVE GHSA-qwww-vcr4-c8h2 (faixa vulnerável `>=7.12.0 <8.3.0`) | `npm audit --omit=dev` → 0 vulns |
| Sessão encerrada **é** comunicada ao usuário | `ProtectedRoute.tsx:12`, `LoginPage.tsx:44` |

⚠ **`npm-audit-current.json` na raiz é um retrato de 2026-08-01 e está desatualizado.**
Ele lista `react-router` como vulnerável — o que **já foi corrigido**. Não tire conclusão
de segurança desse arquivo; rode `npm audit --omit=dev`. (Ver tarefa T9.)

---

## 2. Convenções de código que você DEVE seguir

### 2.1 Endpoint de leitura no backend (padrão canônico)

Fonte do padrão: `src/mplacas/photovoltaic/router.py:1-50`. Router fino: abre sessão, aplica
contexto de tenant, delega para `read_service.py`, serializa em `serialization.py`. **Nenhum
cálculo no router.**

```python
router = APIRouter(prefix="/x", tags=["x"])

@router.get("/latest")
async def latest_x(scoped: ReadPlant) -> dict[str, object]:
    async with SessionFactory() as session:
        await set_principal_context(session, scoped.principal)
        record = await get_latest_x(session, plant_id=scoped.plant_id)
    return serialize_x(record)
```

- Autorização de leitura: `ReadPlant` (de `mplacas.core.tenancy`). Escrita/admin: `AdminPlantPath`.
- **Sempre** `await set_principal_context(session, scoped.principal)` — é o que ativa o
  isolamento multi-tenant (RLS). Esquecer isso é falha de segurança, não de estilo.

### 2.2 Contrato no frontend

Todo payload novo ganha um parser em `frontend/src/lib/dashboard/*-contracts.ts` com teste
cobrindo **três casos obrigatórios**: payload válido, campo `null`/indisponível, payload
malformado. Nunca consuma JSON cru no componente.

Convenção de erro dos endpoints de leitura: **200 sempre dentro do escopo**, com campo `null`
+ motivo. Indisponibilidade é dado, não status HTTP de erro.

### 2.3 Tokens visuais

Use apenas variáveis CSS de `frontend/src/index.css` (`--color-*`). **Nunca** classes cruas de
cor (`bg-red-500`, `text-green-600`) — há teste que bloqueia isso. Para texto de severidade use
os tokens `-text` (`--color-success-text`, `--color-warning-text`, `--color-danger-text`), que
são os que passam em WCAG AA; os sem sufixo são para preenchimento.

### 2.4 Testes

Padrão do projeto: Vitest + Testing Library, `fireEvent` (não `user-event`), teste de
comportamento observável, não de implementação. Referências: qualquer `*.test.tsx` em
`frontend/src/components/`.

### 2.5 Roteamento de agentes (de `CLAUDE.md`)

| Tarefa | Agente |
|---|---|
| Decisão de arquitetura / desenho de endpoint novo | `architect` ou `frontend-architect` |
| Implementação + CI | `worker` |
| Componente visual / token | `design-system-engineer` |
| Gráfico / métrica | `data-visualization-specialist` |
| Revisão final | `reviewer` / `quality-gate-reviewer` |
| Validar fidelidade fotovoltaica (consultivo) | `solar-domain-specialist` |
| Busca/leitura pontual | `quick-task` / `repo-auditor` |

---

## 2.6 Ordem de execução recomendada

Se houver capacidade limitada, execute **nesta ordem** — ela é por valor/esforço, não por
numeração:

| Ordem | Tarefa | Por quê primeiro |
|---|---|---|
| 1º | **T5** (rótulo "Esperado") | Menor esforço do plano, corrige algo enganoso hoje, não toca cálculo |
| 2º | **T2** (exportação) | Endpoints prontos e testados; só falta consumir |
| 3º | **T1** (visão por inversor) | Maior valor do plano; exige ADR + endpoint, mas o cálculo já existe |
| 4º | **T4** (explicações IA) | Endpoint pronto; escopo pequeno |
| 5º | **T7, T6, T8, T9** (P2) | Consolidação técnica e higiene |
| 6º | **T3** (central de alertas) | **Mais cara:** o conteúdo do alerta não é persistido hoje; exige modelo novo + migration |

---

## 3. Tarefas P1

### [ ] T1 — Visão por inversor (recomendação nº 1)

**Problema:** o backend sabe qual inversor caiu e nunca conta ao usuário na interface. A
avaliação por device existe e só sai por Telegram.

**Evidência (confirme antes de começar):**
```bash
grep -n "class Device" src/mplacas/db/models.py                    # esperado: linha 107
grep -n "device_id" src/mplacas/db/models.py | head                # DailyEnergy.device_id
grep -n "DeviceProductionMetrics\|_gather_device_metrics" src/mplacas/alerts/production_alert.py
grep -rn "device" frontend/src/lib/dashboard/                      # esperado: NENHUM device_id
```

**O que já existe (NÃO reimplemente):**
- `DeviceProductionMetrics` — `alerts/production_alert.py:122-138`: produção e rendimento por
  inversor, com `production_kwh: None` significando "não reportou" (≠ produziu zero).
- `DeviceYieldAssessment` — `:158-164`: rendimento relativo à **própria** mediana, flag `dropped`.
- `_gather_device_metrics` — `:825`, `_assess_devices` — `:495`.
- `gather_production_alert_metrics` — `:191`, monta tudo. **Atenção:** exige
  `expected_daily_production_kwh: Decimal` obrigatório e levanta
  `ProductionAlertDataNotFoundError` quando não há `daily_energy` no dia.

**Decisão de arquitetura necessária antes de implementar — delegue ao `architect`:**
a lógica por device hoje é privada e vive no caminho de alerta. Decidir entre (a) extrair para
um `read_service.py` reutilizável e expor endpoint de leitura, ou (b) criar superfície de
leitura própria de devices. **Não decida sozinho durante a implementação.** Registre a escolha
como ADR (próximo número livre: **ADR-074** — o 073 foi consumido pela T6, ver
`docs/ADR-073-sessao-em-memoria.md`. Confirme o número livre com `ls docs/ | grep ADR-` antes de
criar). Siga `docs/ADR-072-modulos-dashboard-rotas.md` como referência de estrutura.

**Escopo da UI (proposto, ajuste com `product-uiux-lead`):** lista de inversores no módulo
**Técnico** (`frontend/src/pages/dashboard/TechnicalPage.tsx`), com por device: identificação,
produção do dia, rendimento vs. própria mediana, e estado de comunicação.

**Guardas obrigatórias:**
- "Não reportou" e "produziu 0 kWh" são fatos **diferentes** e devem ter apresentações
  diferentes. Nunca renderize `0` para ausência de dado.
- Rendimento de um inversor só pode ser comparado com a **mediana histórica dele mesmo** —
  inversores têm baseline crônico distinto (o código diz isso explicitamente em
  `production_alert.py:136-138`). Não construa ranking entre inversores diferentes sem validar
  com `solar-domain-specialist`.
- Nenhum cálculo novo no frontend: o rendimento e o desvio vêm prontos do backend.

**Critério de aceite:**
- [ ] ADR-073 escrito e aprovado.
- [ ] Endpoint de leitura devolve, por inversor: identificação, produção, rendimento, mediana
      própria, e estado de comunicação — com `null` + motivo quando indisponível.
- [ ] Parser em `lib/dashboard/` com os 3 testes obrigatórios (§2.2).
- [ ] UI distingue visualmente "sem dados" de "zero".
- [ ] `set_principal_context` presente no handler (isolamento multi-tenant).
- [ ] Gate §0.4 verde nos dois lados.
- [ ] Revisado por `reviewer` (toca autorização/tenancy).

---

### [ ] T2 — Exportação de relatório (CSV/PDF/XLSX)

**Problema:** 7 das 8 rotas de `reports/router.py` não têm consumo. Existe pipeline assíncrono
completo construído e sem porta de entrada.

**Confirme antes:**
```bash
grep -nE "@router\.(get|post)" src/mplacas/reports/router.py
grep -n "reports/monthly" frontend/src/lib/api.ts    # esperado: só /history
```

**Endpoints disponíveis (assinatura real verificada):**
- Síncronos: `GET /reports/monthly/latest.csv|.pdf|.xlsx` — `reports/router.py:107,130,153`.
  Autorização `ReadPlant`. Os parâmetros `expected_production_kwh` e
  `stable_tolerance_percent` estão marcados `deprecated=True` — **não os envie**.
- Assíncronos: `POST /reports/monthly/exports` (202) → `GET .../exports/{task_id}` (status) →
  `GET .../exports/{task_id}/download`. É um pipeline real e persistido — existe a tabela
  `report_export_tasks` (`src/mplacas/reports/db_models.py`).

**Decisão:** comece pelo **caminho síncrono** (mais simples, entrega valor imediato). O
pipeline assíncrono só se justifica se o relatório demorar a ponto de estourar timeout —
verifique antes de construir polling.

**Ponto de atenção real:** o download precisa do header `Authorization`. Um `<a href>` simples
**não** carrega o token (que vive em memória, `lib/auth.ts`). Implemente via `apiFetch` →
`blob` → `URL.createObjectURL`, e **revogue** o object URL depois (`URL.revokeObjectURL`) para
não vazar memória.

**Critério de aceite:**
- [x] Botão de exportação em `MonthlyProductionSection`, com formato selecionável.
- [x] Download autenticado funcionando (não `<a href>` cru) — via `apiFetch`, `href` é sempre `blob:` local.
- [x] `URL.revokeObjectURL` chamado após o download — em `finally`, com teste que falharia se removido.
- [x] Estado de carregamento e de erro tratados; 404 (sem ciclo fechado) distinto de 500.
- [x] Nenhum parâmetro `deprecated` enviado — testado explicitamente.
- [x] Gate §0.4 verde — 73 arquivos, **807 testes**, type-check 0 erros, +0,95 kB gzip.
- [x] Revisado por `reviewer`.
- [ ] **BLOQUEANTE — T2a abaixo:** corrigir o P1 achado na revisão.

#### [ ] T2a — CORS não expõe `Content-Disposition` (bloqueia o fechamento da T2)

**Achado da revisão, confirmado de forma independente.** O nome de arquivo derivado do header
`Content-Disposition` **nunca funciona em produção**:

- `src/mplacas/main.py:72-77` configura `CORSMiddleware` **sem `expose_headers`**. O default do
  Starlette é `()`, então só os headers CORS-safelisted ficam legíveis por JS. `Content-Disposition`
  não está nessa lista. (`allow_headers=["*"]` não resolve — governa headers de *requisição*.)
- O deploy é cross-origin de fato: frontend em `mplacas-frontend.pages.dev`
  (`frontend/wrangler.toml`), API em `mplacas-api-*.run.app` (`frontend/.env.production:3`).

Consequência: `response.headers.get('Content-Disposition')` sempre devolve `null` em produção; o
fallback determinístico é o único caminho executado, e o usuário perde o `reference_month` no nome
do arquivo. **O teste atual mascara o defeito** porque jsdom não reproduz o filtro de CORS —
é o único ponto do frontend que lê header de resposta customizado.

**Correção exigida (a, preferencial):** adicionar `expose_headers=["Content-Disposition"]` ao
`CORSMiddleware` em `src/mplacas/main.py`. É exposição mínima e bem compreendida — o navegador já
recebe o header; isso apenas permite que o JS o leia. Não é regressão de segurança.

**Junto com (obrigatório):**
- Corrigir o comentário em `frontend/src/lib/api.ts:173-176`, que hoje afirma o oposto do que
  acontece ("não deveria acontecer no caminho feliz").
- Sanitizar o nome vindo do header antes de usar em `link.download` (allowlist de caracteres,
  rejeitando `/`, `\`, `..` e caracteres de controle) — defesa em profundidade, `api.ts:185-189`.
- Teste que cubra header ausente **como caminho normal**, não como exceção.

**Guarda:** `main.py` é arquivo de bootstrap da aplicação. Altere **apenas** o parâmetro
`expose_headers`; não mexa em `allow_origins`, `allow_credentials`, `allow_methods` nem
`allow_headers`. Exige `reviewer` por tocar configuração de segurança.

**Status:** implementada e revisada (2026-08-12). Diff mínimo confirmado (1 inserção). A segunda
revisão validou que `expose_headers` como **lista explícita** (não `"*"`) é a forma correta de
conviver com `allow_credentials=True` — a spec do Fetch faz o navegador ignorar `*` em modo
`credentials: include`. Devolveu 1 P1 e 2 P2, tratados na T2b abaixo.

#### [ ] T2b — Cobertura do fix de CORS e reforço da sanitização

**P1 — o fix não tem teste (bloqueia o fechamento da T2/T2a).**
`src/mplacas/main.py:77` corrige um defeito real de produção e **nenhum dos 838 testes de backend
passa por essa linha**. Confirmado:
- `main.py:70` só registra o middleware sob `if _cors_origins:`;
- `core/config.py:111-114` devolve `[]` quando `cors_allowed_origins` é vazio;
- `tests/conftest.py` não configura origem alguma.

Ou seja, **sob pytest o `CORSMiddleware` nunca é registrado**. Remover a linha 77 hoje não quebra
nada no CI — a mesma classe de ponto cego que produziu o P1 original, reincidindo na própria
correção.

⚠ **Armadilha para quem for escrever esse teste:** `main.py:68-70` avalia `get_settings()` e a
condicional em **tempo de importação de módulo**, no escopo global. Monkeypatchar settings e depois
importar `app` não funciona se `mplacas.main` já estiver importado. É preciso forçar reavaliação
(env var antes do import, `importlib.reload`, limpar cache de `get_settings`, ou montar app isolado)
**e garantir teardown**, sob pena de vazar configuração para os outros 838 testes.

**P2 — sanitização incompleta** (`frontend/src/lib/api.ts:195-215`):
1. Não bloqueia override de direção Unicode (U+202A–U+202E, U+2066–U+2069) — vetor clássico de
   spoofing de extensão (RLO faz `relatorio‮fdp.exe` renderizar como `relatorio.exe.pdf`).
2. A extensão do nome extraído não é cruzada com o `format` já conhecido pela função chamadora,
   permitindo extensão dupla (`fatura.csv.exe`).

Ambos exigem `Content-Disposition` adulterado (backend comprometido ou TLS quebrado) para serem
explorados — mas a função se declara "defesa em profundidade" e hoje não cumpre isso.

**Critério de aceite:**
- [x] Teste que falharia se `expose_headers` fosse removida de `main.py` — `tests/test_cors_expose_headers.py`.
      **Provado por mutação:** a linha foi removida temporariamente, o teste falhou
      (`assert 'Content-Disposition' in ''`), e `main.py` foi restaurado (diff confirmado em
      1 inserção, 0 remoções).
- [x] Isolamento comprovado — **840 passed, 6 skipped** na suíte completa, sem falha colateral.
      O teste usa `importlib.reload` + `get_settings.cache_clear()` dentro de `try/finally`, e um
      segundo caso funciona como sentinela: afirma que sem origem configurada **nenhum** header
      CORS aparece. Se o primeiro vazasse, o segundo quebraria.
- [x] Override de direção Unicode rejeitado (U+202A–U+202E, U+2066–U+2069), com teste.
- [x] Extensão validada contra o formato pedido, com teste (`fatura.csv.exe` cai no fallback).
- [x] Gate §0.4 verde nos dois lados — backend 840/6, frontend **814 testes**, type-check 0 erros.

**Regra final de sanitização** (`isSafeDownloadFilename` + `filenameFromContentDisposition`):
rejeita nome vazio ou >200 chars, `.` ou iniciado por `.`, `/`, `\`, `..`, controles C0/DEL,
controles de direção Unicode, e exige extensão idêntica (case-insensitive) ao formato pedido.
Qualquer falha → fallback determinístico. Fail-closed em todos os caminhos.

**✅ T2 / T2a / T2b CONCLUÍDAS** (2026-08-12) — verificadas independentemente pelo orquestrador.

---

### [ ] T3 — Central de alertas in-app

**Problema:** a única entrega de alerta é Telegram. Quem não usa o bot não vê alerta nenhum.

**Confirme antes:**
```bash
grep -nE "@router\." src/mplacas/alerts/router.py            # esperado: SÓ POST /run, linha 56
cat src/mplacas/alerts/db_models.py                          # esperado: só AlertDeliveryRecord
grep -rn "Alert" frontend/src/components/ | grep -v test | grep -v production-alerts
```

> ## ⛔ ESTA SEÇÃO ESTAVA ERRADA — ver `docs/ADR-075-central-de-alertas-in-app.md`
>
> **O diagnóstico abaixo tem premissa falsa e foi refutado com evidência.** A afirmação de que
> "o conteúdo do alerta não é persistido" veio de olhar apenas `alerts/db_models.py` e concluir a
> partir da ausência ali — **exatamente o erro que a §0.1 deste mesmo documento manda evitar**.
> O conteúdo É persistido: `src/mplacas/alerts/outbox.py:80-90` grava `severity`, `title`,
> `message`, `recommended_action` e `occurred_at` em `outbox_events.payload_json`, com checksum,
> FK de usina e RLS ativa. **Nenhuma migration jamais foi necessária.**
>
> Pior: o valor real **já trafega e é descartado**. `intelligence/router.py:200-208` serializa
> `diagnostics[]` por dia (código, mensagem, ação recomendada), o frontend pede **90 dias**
> (`lib/api.ts:72-74`), e `parseAnomalyDaily` (`contracts.ts:352-362`) **não lê o campo**.
>
> Decisão do ADR-075: **não construir central de alertas.** Em vez disso, uma linha do tempo de
> episódios sobre o dado já trafegado — zero backend, zero migration, zero endpoint.
>
> O texto abaixo fica como registro do erro, não como instrução.

**Estado real (já investigado — não repita a investigação, apenas confirme):**

1. `alerts/router.py` expõe apenas `POST /run` (gatilho de job). Não há endpoint de consulta.
2. **A única tabela de alerta é `alert_delivery_records`** (`src/mplacas/alerts/db_models.py:13-29`),
   e ela **não é um histórico de alertas** — é um registro de *entrega*, com apenas:
   `plant_id`, `fingerprint`, `provider`, `destination_ref`, `sent_at`, mais um
   `UniqueConstraint(plant_id, fingerprint)`. Serve para deduplicar envio no Telegram.

**Conclusão: o conteúdo do alerta não é persistido.** Não há severidade, nem texto, nem causa,
nem qual inversor — nada disso sobrevive ao envio. O `fingerprint` identifica o alerta, mas não
o descreve.

**Portanto esta tarefa NÃO é "expor o que já existe".** Ela exige, nesta ordem:
1. **Decisão de arquitetura (`architect`, obrigatório):** persistir o conteúdo do alerta
   (novo modelo + migration Alembic) versus recalcular sob demanda na leitura.
2. Só depois, endpoint de leitura e UI.

**Consequência de esforço:** esta é a mais cara das tarefas P1 (envolve migration). Se a
capacidade de execução for limitada, **priorize T1, T2 e T5 antes desta** — elas entregam mais
valor por esforço e não tocam no schema.

**Se envolver migration:** siga a convenção de `revision id` do projeto (ver `migrations/` e as
migrations existentes; o projeto diverge do default do Alembic) e exija `reviewer`.

**Escopo mínimo viável:** histórico consultável (o quê, quando, severidade, qual usina/ativo).
Ciclo de vida completo (reconhecer → resolver) fica para uma segunda etapa — não construa
os dois de uma vez.

**Guardas:**
- Severidade **nunca** só por cor: sempre cor + texto + ícone (regra WCAG do projeto).
- Cuidado com alarm fatigue: não liste tudo achatado; agrupe/priorize.

**Critério de aceite:**
- [ ] ADR de decisão (persistir conteúdo × recalcular) escrito e aprovado pelo `architect`.
- [ ] Se houve migration: convenção de `revision id` do projeto respeitada e testada.
- [ ] Endpoint de leitura com `ReadPlant` + `set_principal_context`.
- [ ] Severidade com cor + texto + ícone.
- [ ] Gate §0.4 verde.
- [ ] Revisado por `reviewer` (toca schema/migration).

---

### [x] T4 — Explicações por IA na interface

**Problema:** `GET /explanations/latest` existe (`explanations/router.py:27`) e o frontend
nunca chama.

**Assinatura real:** `latest_explanation(scoped: ReadPlant, expected_production_kwh, stable_tolerance_percent)`.
O provider é opcional — só é instanciado se `settings.explanation_api_url` estiver
configurado (`explanations/router.py:35-36`), com **fallback determinístico** quando não há.

**Correção de rota (verificado em 2026-08-13):** o endpoint real é `GET
/energy/explanations/latest` (`router = APIRouter(prefix="/energy/explanations", ...)`,
`explanations/router.py:21-27`) — o prefixo do plano estava incompleto. `plant_id` é query
param obrigatório resolvido por `ReadPlant` (`core/tenancy.py:110`), mesmo padrão das demais
funções de `lib/api.ts`.

**Guardas inegociáveis:**
- A IA **interpreta** número já calculado. Ela **nunca** produz o número oficial. Se a
  explicação divergir do valor determinístico exibido, o determinístico prevalece.
- Deixe visualmente claro que é camada interpretativa — não misture com o dado auditável.
- Acione **sob demanda** (ação explícita do usuário), não como texto sempre presente.
- Trate o caso "provider não configurado" como estado normal, não como erro.

**Escolha de local — `DiagnosticsCard` (não `TechnicalDiagnosticPanel`):** o endpoint monta a
explicação a partir do mesmo `build_executive_dashboard`/`current_cycle.intelligence.diagnostics`
que alimenta `DiagnosticsCard` (`explanations/executive.py::executive_explanation_request`,
`explanations/router.py:51-61`) — é literalmente a mesma evidência, só reformulada em texto.
`TechnicalDiagnosticPanel` deriva de `PhotovoltaicSummaryResponse` (PR, disponibilidade,
perdas), uma fonte de dado completamente diferente que o endpoint de explicação nunca toca —
colocar o painel ali criaria a impressão de que a IA interpreta dado técnico que não vê.

**Implementação:**
- `frontend/src/lib/dashboard/explanation-contracts.ts` (novo) — parser de
  `LatestExplanation` + `classifyExplanationErrorStatus` (404 = nenhum ciclo confirmado ainda,
  5xx/rede = erro, 401 = `null`) + `explanationSourceLabel`. Os 3 casos do §2.2: payload válido
  (dois testes, AI_ASSISTED e DETERMINISTIC), "campo indisponível" (aqui expresso como status
  HTTP 404, já que todo campo de um 200 é garantido não-vazio pelo backend — ver comentário do
  arquivo), payload malformado.
- `fetchLatestExplanation(plantId)` em `lib/api.ts`, comentada no estilo das vizinhas.
- `frontend/src/components/AiExplanationPanel.tsx` (novo) — painel sob demanda (só busca ao
  clique em "Pedir explicação por IA"), estados idle/loading (`LoadingAnnouncement` reusado)/
  erro (404 tratado como informativo, 5xx/rede com nova tentativa, 401 silencioso)/sucesso.
  Resultado sempre rotulado (`explanationSourceLabel`) + selo "Camada interpretativa — não é
  dado auditável" + caixa com borda tracejada (mesmo vocabulário visual de "estimativa" já
  usado em `Card dashed`/`EnergyFlowDiagram`) + disclaimer do backend sempre visível.
- `DiagnosticsCard.tsx` ganhou prop `plantId` e renderiza `AiExplanationPanel` nos dois ramos
  (com e sem diagnósticos).

**Critério de aceite:**
- [x] Painel sob demanda em `DiagnosticsCard` (justificativa acima).
- [x] Origem do texto rotulada como interpretação assistida (`explanationSourceLabel`).
- [x] Fallback/ausência de provider tratado sem erro na tela — `source: 'DETERMINISTIC'`
      renderiza normalmente, mesmo painel, sem branch de erro.
- [x] Gate §0.4 verde — ver linha da tabela de execução.

---

### [ ] T5 — Corrigir o rótulo "Esperado" do gráfico de produção

**Problema (confirmado):** `expected_production_kwh` é **o mesmo valor escalar replicado em
todos os dias** do período, mas a UI desenha traço por barra e diz `Esperado: X kWh` por dia —
sugerindo uma expectativa diária que não existe.

**Evidência:**
```bash
sed -n '145,175p' src/mplacas/intelligence/anomaly_service.py
```
Confirme que `expected_production_kwh=expected_daily_production_kwh` é atribuído dentro do laço
`for current_day in ...` usando o mesmo valor para todos os dias (`:157-171`).

**Estado do componente (já verificado — leia o arquivo inteiro antes de editar):**
- `frontend/src/components/ProductionHistoryChart.tsx:117-126` — `performancePercent` é
  `soma(real)/soma(esperado)` somando só dias com ambos presentes.
- `:256-261` — legenda "Esperado" (tracejado, `--color-chart-reference`).
- `:262-267` — **já existe** uma linha "Média do período" (sólida, brand). Não duplique.
- `:509-513` — `Esperado: X kWh` no painel de detalhe do dia.

**Correção mínima (baixo risco, não toca cálculo nem classificação):**
1. Rotular como **"Média diária esperada (baseline sazonal)"** em vez de "Esperado".
2. Desenhar **uma linha horizontal única** de referência, não um traço por barra.
3. No painel de detalhe, deixar explícito que é referência do período, não expectativa daquele dia.

**NÃO faça:** não altere `assess_daily_performance` nem a classificação
NORMAL/ATENÇÃO/ANOMALIA/CRÍTICO. Ela **já** desconta irradiância e mediana histórica
corretamente e **não** sofre desse problema. O defeito é de rótulo/desenho, não de cálculo.

**Critério de aceite:**
- [ ] Nenhum texto da UI afirma expectativa por dia.
- [ ] Uma única linha de referência, sem duplicar a "Média do período" já existente.
- [ ] Classificação por dia intocada (teste que a prove inalterada).
- [ ] Gate §0.4 verde.

---

## 4. Tarefas P2

### [ ] T6 — ADR da decisão de sessão em memória

**Fato verificado:** o token de acesso vive só em variável de módulo (`frontend/src/lib/auth.ts:1`)
e o refresh em `useRef` (`AuthContext.tsx:21`). Nenhuma chamada usa `credentials: 'include'`.
Consequência: **a sessão não sobrevive a um reload** (F5 desloga).

Isso **é** comunicado ao usuário: `ProtectedRoute.tsx:12` propaga `state={{ reason: 'SESSION_ENDED' }}`
e `LoginPage.tsx:44` consome.

**Tarefa:** escrever ADR (próximo número livre após o usado em T1) registrando a decisão como
intencional: o que se ganha (nenhum token em storage do navegador, superfície de XSS reduzida),
o que se perde (reautenticação a cada reload), e a alternativa considerada (refresh token em
cookie `httpOnly`) com o motivo da recusa.

**Não altere o comportamento nesta tarefa.** É documentação. Mudar o modelo de sessão é
decisão separada, com `reviewer` obrigatório.

- [x] ADR escrito em `docs/ADR-073-sessao-em-memoria.md` (2026-08-12).
      Registra o ganho (superfície de XSS reduzida no ativo mais sensível), a perda
      (reautenticação a cada reload) e a recusa fundamentada do cookie `httpOnly`: o deploy é
      cross-origin (`pages.dev` → `run.app`), o que forçaria `SameSite=None` e **reintroduziria
      risco de CSRF** sem defesa correspondente no projeto. Inclui gatilhos objetivos de
      reavaliação. Nenhum comportamento foi alterado.

---

### [ ] T7 — Mover cálculo de rendimento para o backend

**Problema:** `frontend/src/lib/dashboard/yield.ts:33-59` calcula rendimento
(produção ÷ irradiância) e desvio percentual **no cliente** — o próprio comentário do arquivo
assume *"Calculado 100% no frontend"* (`yield.ts:14-15`). Além disso
`YIELD_ATYPICAL_THRESHOLD_PERCENT = 20` (`yield.ts:31`) é limiar de severidade calibrado em
dois casos reais desta usina, vivendo no frontend.

Isso contraria a convenção do projeto (cálculo e regra de negócio no backend determinístico) e
torna "P1-01 resolvido" da auditoria de 04/08 um **parcialmente resolvido**.

**Atenção:** o backend **já calcula rendimento por usina e por device**
(`alerts/production_alert.py:220-226`, `_plant_rendimento_median`, `_device_rendimento_medians`).
Verifique se dá para reutilizar em vez de escrever fórmula nova — **não duplique fórmula**.

**Critério de aceite:**
- [ ] `computeYieldStats` e o limiar saem do frontend (ou o frontend passa a só ler o resultado).
- [ ] Nenhuma fórmula duplicada: reuso do que já existe no backend, verificado.
- [ ] `YieldCard` continua funcionando; testes de `ProductionHistorySection` verdes.
- [ ] Validado por `solar-domain-specialist` (consultivo — ele não implementa).
- [ ] Gate §0.4 verde.

---

### [x] T8 — Orçamento de bundle no CI

**Problema:** desde a divisão em 4 módulos (ADR-072) ninguém mede o custo por rota. Referência
histórica das skills do projeto ("~99 kB gzip total") está defasada.

**Tarefa:** gate no CI comparando o output de `npm run build` contra limites por chunk.
Valores de partida (da seção 1.4, com folga): vendor ≤ 65 kB, cada módulo do dashboard ≤ 15 kB,
CSS ≤ 13 kB. Falhar o build ao estourar.

**Implementação:** `frontend/scripts/check-bundle-budget.mjs` (novo) — lê os arquivos reais de
`dist/assets/` (não o texto impresso por `vite build`, cujo formato não é API estável entre
versões), calcula o tamanho gzip de cada chunk orçado com `zlib.gzipSync` e falha
(`process.exit(1)`) se algum ultrapassar o teto. Os 7 limites (vendor, CSS, 4 módulos do
dashboard, `LoginPage`) ficam num único array `BUDGETS` no topo do arquivo, com comentário
explicando que são orçamento deliberado — não a medição do dia (mesma lição da T8b: um gate
que sempre reflete o valor atual nunca protege nada). Um chunk orçado que **desaparece** do
build (renomeado/removido) também é tratado como falha, não como "nada a checar" — mesma razão.
Rodado em `.github/workflows/ci.yml`, job `frontend`, novo passo "Check bundle budget" logo
após "Build" e antes de "Upload build artifact" (`npm run check-bundle-budget`).

**Prova de mutação (2026-08-13):** dois limites foram temporariamente quebrados no script —
`ProductionPage` de 15 kB para 1 kB (força "ESTOUROU") e o regex do `LoginPage` para um prefixo
inexistente (força "AUSENTE") — e o script foi rodado antes de restaurar:

```
chunk                  medido      teto      status
vendor (index-*.js)    59.53 kB    65.00 kB  ok
CSS (index-*.css)      10.74 kB    13.00 kB  ok
módulo OverviewPage    12.61 kB    15.00 kB  ok
módulo ProductionPage  13.56 kB    1.00 kB   ESTOUROU
módulo FinancialPage   7.30 kB     15.00 kB  ok
módulo TechnicalPage   8.26 kB     15.00 kB  ok
LoginPage              —           5.00 kB   AUSENTE

Orçamento de bundle FALHOU (2 de 7 categorias):

  - módulo ProductionPage: 13.56 kB gzip, acima do teto de 1.00 kB (arquivo: ProductionPage-Bh_agD0M.js). Excedente: 12.56 kB.
  - LoginPage: NENHUM arquivo em dist/assets/ casou com /^LoginPageNOPE-.*\.js$/ — chunk esperado sumiu (...)
EXIT CODE: 1
```

Restaurado a partir de backup (`diff` confirmou arquivos idênticos) e reexecutado: `EXIT CODE:
0`, todos os 7 chunks `ok`. Números atuais medidos por este script (nota: ~2-3% abaixo do
número impresso por `npm run build`, algoritmo de gzip do Vite não é API pública estável — ver
comentário de metodologia no script): vendor 59,53 kB/65, CSS 10,74 kB/13, `OverviewPage` 12,61
kB/15, `ProductionPage` 13,56 kB/15 (o mais apertado), `FinancialPage` 7,30 kB/15,
`TechnicalPage` 8,26 kB/15, `LoginPage` 2,90 kB/5.

- [x] Gate implementado e falhando de propósito uma vez (prove que funciona) — ver prova acima.
- [x] Limites documentados junto do script — bloco `BUDGETS` comentado em
      `frontend/scripts/check-bundle-budget.mjs`.

---

### [ ] T10 — Dívida de acessibilidade recorrente (achado da revisão da T2)

**Origem:** revisão independente da T2 identificou dois defeitos que **não são regressão da T2** —
ela apenas repetiu padrões que já falhavam em outros pontos do projeto. Por isso a correção deve
ser única e ampla, não remendo por componente.

**Agente indicado:** `accessibility-specialist`.

**Defeito 1 — mudança de estado de botão não é anunciada a leitor de tela.**
Botões que trocam de rótulo durante carregamento (`Baixar PDF` → `Gerando PDF...`) ficam
`disabled` mas não têm `aria-live`/`aria-busy`. Mudança de nome acessível sem live region não é
garantidamente anunciada.
- Ocorrências: `frontend/src/components/MonthlyProductionSection.tsx` (~:62-75),
  `frontend/src/components/CapexRegistrationForm.tsx` (~:110-122).
- **O projeto já tem o padrão correto** em `frontend/src/components/RefreshBar.tsx:36-45`
  (`<p aria-live="polite">` separado do botão). Replique-o; não invente um novo.

**Defeito 2 — `<select>` abaixo do alvo mínimo de toque (44px).**
- Ocorrências: `frontend/src/components/MonthlyProductionSection.tsx` (~:50-56),
  `frontend/src/components/PlantSelector.tsx` (~:55-67).
- Botões vizinhos já usam `min-h-[44px]` corretamente — a inconsistência é só nos selects.

**Critério de aceite:**
- [x] Padrão único de anúncio aplicado — novo `frontend/src/components/LoadingAnnouncement.tsx`
      (`<span aria-live="polite" class="sr-only">`, vazio em repouso), réplica estrutural de
      `RefreshBar.tsx:36-45`. Aplicado a 3 call sites + `aria-busy` nos botões.
- [x] Todo `<select>` interativo com alvo ≥44px — 2 ocorrências (são as únicas do projeto).
- [x] Testes cobrindo anúncio e alvo de toque.
- [x] Gate §0.4 verde — 74 arquivos, **826 testes**, type-check 0 erros, +0,16 kB gzip.

**A busca ampla encontrou uma 5ª ocorrência não listada:** `frontend/src/pages/LoginPage.tsx`
("Entrar no painel" → "Entrando..."). Confirmado que a mudança lá é **puramente apresentacional**
(import + `aria-busy` + componente de anúncio) — nenhuma lógica de autenticação tocada, por isso
não acionou a regra 0.3.7.

**Nota sobre `PlantSelector.tsx`:** o `<select>` vive num chip compacto dentro de um header de
altura fixa (`h-14`/`h-16`); aplicar `min-h-[44px]` cru transbordaria o header. A solução usa
`py-3 -my-3` — o padding amplia a caixa clicável em 24px verticais e a margem negativa cancela
exatamente esse espaço no fluxo, então a área de toque cresce sem deslocar nada. O `<select>` é
`border-0 bg-transparent`, então a área extra é invisível. Técnica documentada inline no arquivo.

**✅ T10 CONCLUÍDA** (2026-08-12) — verificada independentemente pelo orquestrador.

#### [ ] T10b — Alvo de toque do `RetryableError` (achado residual)

Encontrado durante a T1c, **não corrigido lá** por ser componente compartilhado usado em todo o app
— alargar o diff de uma tarefa de produto para mexer nele seria escopo indevido.

`frontend/src/components/RetryableError.tsx` — o botão de nova tentativa usa `min-h-[40px]`, abaixo
do mínimo de 44px que a própria T10 estabeleceu. A T10 varreu selects e botões com troca de rótulo
em carregamento; este caso escapou porque é um botão de ação simples.

**Critério de aceite:**
- [x] Botão de retry com alvo ≥44px.
- [x] Varredura ampla executada — e revelou que o problema era **maior do que a revisão viu**.
      A T10 corrigiu os `<select>` e deixou **todos os botões** abaixo do mínimo. Seis ocorrências:
      `CapexRegistrationForm.tsx:115` (40px), `EpisodeTimelineSection.tsx:155` (40px, arquivo criado
      horas antes), `ErrorBoundary.tsx:39` (40px), `ProductionHistorySection.tsx:206` (40px),
      `RefreshBar.tsx:51` (**38px** — justamente o componente usado como *referência de padrão
      correto* pela T10), `RetryableError.tsx:28` (40px).
- [ ] Gate §0.4 verde.

**Lição:** a T10 declarou ter "eliminado a classe do problema" tendo corrigido só um dos dois
padrões. A varredura de irmãos que este item exigia é o que transforma correção pontual em
correção de classe — e ela só foi feita porque a revisão da T1c tropeçou num caso residual.

---

### [ ] T7b — Achados do `solar-domain-specialist` sobre a janela de rendimento

Parecer consultivo obtido após a T7. A transposição do cálculo está **aritmeticamente fiel** — a
fórmula, o limiar de 20%, o filtro de "ambos os lados positivos", a propagação de `null` em vez de
zero e o uso de `Decimal` estão corretos e **não devem ser mexidos**. Os achados são de janela de
referência e de rótulo.

**[ ] P0 — o card afirma o que não verificou (bloqueante).**
`ProductionHistorySection.tsx:278-283` passa `daily={filteredDaily}` (recorte visível, 7 dias por
padrão) e `daysAnalyzed={days_analyzed}` (janela cheia, 90). Em `YieldCard.tsx`, o cabeçalho (`:68`)
anuncia "período analisado (90 dias)", a varredura de dias atípicos (`:56-63`) percorre só os 7
visíveis, e o estado vazio (`:78`) conclui **"Rendimento estável"** sobre os 90.
Um O&M lê "90 dias estáveis" e não abre o histórico. Pior: trocar o recorte faz a lista aparecer e
sumir sem o cabeçalho mudar — o card contradiz a si mesmo entre dois cliques.
*Correção:* ou restringir a afirmação ao recorte, ou varrer `daily` completo. Hoje é a pior
combinação das duas.

**[ ] P1 — o rótulo usa a contagem errada.**
`days_analyzed` é `len(daily)` (dias com linha de produção, `anomaly_service.py:297`), mas o
rendimento só usa dias com produção **e** irradiância positivas (`:143`). O próprio teste do worker
prova a divergência: `tests/test_anomaly_service.py:475-477` tem `days_analyzed == 4` com
`period_yield` calculado sobre **2** dias. Expor `period_yield_sample_days` e rotular com ele.

**[ ] P1 — dia de produção zero com sol desaparece** (pré-existente, preservado pela T7).
`anomaly_service.py:143` exclui `actual <= 0`. Excluir da **referência** é correto; excluir do
**valor exibido do dia** não é — `0 ÷ 5 kWh/m²` é razão definida e é o evento de rendimento mais
grave possível (−100%). Hoje a usina pode produzir 0 kWh sob sol pleno e o card dizer "estável".

**[ ] P1 — dois "período" diferentes na mesma viewport.**
`ProductionHistoryChart.tsx:261,527` rotula "Média do período" (média de kWh do recorte visível);
`YieldCard.tsx:68` rotula "período analisado" (90 dias). Nada na tela diz que são janelas
diferentes.

**⚠ P1 — janela de referência sazonalmente enviesada (exige decisão, não é correção óbvia).**
O denominador é irradiância **horizontal** (GHI — `climate/open_meteo.py:46`), e produção/GHI não é
estacionário: transposição POA/GHI, temperatura de célula e sujidade derivam de forma sistemática
**5–15% dentro de uma janela de 90 dias** nesta latitude. Contra limiar de 20%, isso consome metade
da margem de detecção e desloca todos os dias recentes para o mesmo lado. Além disso, o dia julgado
está dentro da própria referência: **degradação crônica arrasta a referência e nunca é flagrada**.
*Recomendação do especialista:* manter `period_yield` como número informativo, mas mover o flag de
"dia atípico" para a **mediana rolante de 30 dias** que o projeto já implementou duas vezes
(`production_alert.py:705-732`, `devices/metrics.py:202-254`) — o que **reduz** duplicação em vez de
aumentar. Não é escopo da T7, que era mover e não redesenhar.

**[ ] P2 — dados servidos e descartados.** `period.start_date`/`end_date` chegam
(`intelligence/router.py:142-145`) e `parseAnomalyDashboard` os joga fora (`contracts.ts:371-380`).
`temperature_mean_c` é coletada e persistida, mas não serializada — é o segundo maior driver do
rendimento e transformaria "−12%" de mistério em "dia quente".

---

### [ ] T11 — `App.test.tsx` é intermitente (flaky)

Descoberto em 2026-08-13 ao validar a compatibilidade retroativa do parser.

**Evidência de intermitência**, não de regressão:

| Execução | Resultado |
|---|---|
| suíte completa, sem a mudança de parser | 926/926 ✓ |
| suíte completa, com a mudança, 1ª | 1 falha — `troca de usina preserva a rota atual` |
| suíte completa, com a mudança, 2ª | mesma falha |
| suíte completa, com a mudança, 3ª | **927/927 ✓** |
| `App.test.tsx` isolado, **sem** a mudança | **3 falhas** |
| `App.test.tsx` isolado, **com** a mudança | 2 falhas |

Dois fatos que separam instabilidade de regressão: o arquivo falha **mais** isolado sem a
mudança do que com ela, e a suíte completa passa integralmente na terceira execução. A mudança de
parser é estritamente **mais permissiva** (aceita payload que antes derrubava), então não pode
introduzir falha de corretude — mas alterou o tempo o bastante para expor a instabilidade.

**Por que importa:** um teste que falha 2 de 3 vezes treina o time a reexecutar até passar, e é
assim que uma regressão real entra despercebida. O arquivo também depende de ordem de execução
(falha isolado, passa na suíte), o que é um segundo defeito.

**Critério de aceite:**
- [ ] Causa da intermitência identificada (provável: `waitFor` sobre navegação assíncrona sem
      âncora determinística).
- [ ] Teste passa 10 execuções consecutivas, isolado **e** na suíte.
- [ ] Nenhum `waitFor` sem asserção de estado observável estável.

---

### [ ] T7c — A guarda estática tem isenção que anula o invariante

`no-client-computed-yield-deviation.test.ts:78-85` **exclui `ProductionHistoryChart.tsx`** da
varredura de substring, com justificativa de que o arquivo já tem `* 100` legítimos (posicionamento
em pixel). O efeito colateral é que a forma proibida sobrevive justamente ali:

- `ProductionHistoryChart.tsx:124-127` — `((activeActual - averageProduction) / averageProduction) * 100`
- `ProductionHistoryChart.tsx:103-112` — `performancePercent`, composição de kWh no cliente

É pré-existente (era T5), não introduzido pela T7 — mas a isenção garante que **nunca será pego**.
Uma guarda com carve-out no único lugar onde a violação existe não é guarda.

*Correção sugerida:* varrer por padrão semântico (ex.: identificadores de grandeza física perto de
aritmética) em vez de substring crua, ou mover o cálculo para o backend e então remover a isenção.

---

### [ ] T8b — Corrigir `npm run type-check`, que é no-op silencioso

**Descoberto durante a T7 e provado por mutação (ver §0.4).** O script não checa arquivo nenhum:
`frontend/tsconfig.json` é solution file e `tsc --noEmit` sem `-b` não percorre as referências.

**Gravidade:** é uma verificação que dá certo sempre, inclusive quando deveria falhar. Todo agente
e todo CI que confiaram nela receberam garantia falsa. Só não houve dano porque `npm run build`
roda `tsc -b` e foi executado junto.

**Critério de aceite:**
- [x] `npm run type-check` passa a checar os arquivos reais — agora `tsc -b --force`.
- [x] **Provado por mutação:** com `export const probe: number = "erro proposital"` o script falha
      com `error TS2322`; sem ele, passa limpo. Antes da correção, **passava nos dois casos**.
- [x] CI verificado: **dois** workflows dependiam do comando quebrado —
      `.github/workflows/ci.yml:208` e `.github/workflows/deploy-frontend.yml:60`. Ambos tinham um
      passo de type-check que não podia falhar. Nenhum código ruim foi publicado porque os dois
      rodam `npm run build` na sequência (`ci.yml:224`, `deploy-frontend.yml:65`), que fazia a
      checagem real — mas o degrau era falso, inclusive no caminho de deploy.

**✅ T8b CONCLUÍDA** (2026-08-13).

---

### [ ] T9 — Remover snapshots de auditoria desatualizados da raiz

**Problema:** `npm-audit-current.json`, `npm-audit-p0.json`, `npm-outdated-current.json`,
`pip-audit-p0.json`, `pytest-*.txt` na raiz são retratos de 2026-08-01. O primeiro **induziu a
um erro factual** na auditoria que originou este plano: lista `react-router` como vulnerável,
quando a versão instalada (`8.3.0`) já é a corrigida.

**Tarefa:** mover para artefato de CI não versionado (ou remover e `.gitignore`). Se algum
precisar ser preservado por rastreabilidade, renomeie com a data no nome e marque no cabeçalho
que é retrato histórico.

- [ ] Raiz limpa; `npm audit --omit=dev` documentado como a fonte de verdade.

---

## 5. Não fazer (decisões já tomadas — não reabra sem dado novo)

| Item | Por quê |
|---|---|
| **Digital Twin espacial / hierarquia de 6 níveis** | Só existem 2 níveis: Usina → Inversor. Não há string, módulo, tracker, transformador nem sensor como entidade, nem georreferenciamento por ativo |
| **Realidade aumentada** | Pressupõe ativo identificável em campo + fluxo de campo; nenhum dos dois existe |
| **WebSocket / SSE / tempo real** | A consolidação é D+1. Não há dado que mude em escala de minutos para transmitir |
| **Trocar as primitivas SVG por lib de gráfico** | O maior gráfico tem ~90 pontos. Adicionaria peso de bundle sem resolver problema real |
| **Redux / Zustand / TanStack Query** | Estado de cliente é simples. Só reconsidere com métrica real de chamadas repetidas entre módulos |
| **PWA com service worker de cache agressivo** | Risco de exibir dado financeiro/energético obsoleto como atual. Manifest de instalabilidade (T-futura) é aceitável; cache de dado não |
| **Virtualização de lista** | Nenhuma lista do produto tem volume que justifique |

---

## 6. Definition of Done (por tarefa)

Só marque `[x]` quando **todos** forem verdadeiros:

- [ ] Pré-voo §0.2 executado.
- [ ] Toda afirmação do relato final tem `arquivo:linha`.
- [ ] Gate §0.4 executado, com **output numérico colado** abaixo do item.
- [ ] Nenhum dado estimado apresentado como confirmado; indisponibilidade explícita com motivo.
- [ ] Nenhum cálculo energético/financeiro novo no frontend.
- [ ] Nenhuma dependência de runtime nova sem ADR.
- [ ] Contraste/teclado/foco preservados (testes de acessibilidade verdes).
- [ ] Se tocou `auth`/`billing`/`credentials`/`organizations`/`audit`/`migrations`/`reports/export`:
      revisado por `reviewer` ou `quality-gate-reviewer`.
- [ ] ADR criado quando a tarefa envolveu decisão de arquitetura.

---

## 7. Registro de execução

Preencha ao fechar cada tarefa. **Não marque `[x]` na seção da tarefa sem preencher aqui.**

| Tarefa | Data | Commit | Arquivos | Testes (resultado numérico) | Revisor |
|---|---|---|---|---|---|
| T1 (ADR) | 2026-08-12 | não commitado | `docs/ADR-074-visao-por-inversor.md` (novo, 511 linhas) | n/a | `architect` (Opus); afirmações-chave reverificadas pelo orquestrador |
| T1a | 2026-08-12 | não commitado | `devices/metrics.py` + `__init__.py` (novos), `alerts/production_alert.py`, `tests/test_production_alert.py` | 840 passed/6 skipped; mypy 189→191 | movimento puro **provado por diff** dos corpos de função |
| T1b | 2026-08-12 | não commitado | `devices/read_service.py`, `serialization.py`, `router.py` (novos), `main.py`, `tests/test_devices_daily_status.py` (novo) | **852** passed/6 skipped; mypy 194 | `reviewer` — **nenhum P0/P1**; 2 P2 de cobertura |
| T1c | 2026-08-12 | não commitado | `device-contracts.ts(.test)`, `DeviceStatusSection.tsx(.test)` (novos), `lib/api.ts`, `TechnicalPage.tsx` | 76 arq./858 testes; `TechnicalPage` 6,51→8,43 kB gzip | `reviewer` — **2 P1** → T1d |
| T1d | 2026-08-12 | não commitado | `devices/metrics.py`, `devices/serialization.py`, `device-contracts.ts`, `DeviceStatusSection.tsx`, ADR-074, +3 arquivos de teste | backend **855**/6; frontend **77 arq./867 testes**; 8,46 kB gzip | verificado pelo orquestrador (mutação + Node) |

**✅ T1 COMPLETA** (2026-08-12) — ADR-074 + movimento puro + endpoint + UI + correção dos 2 P1.
O sistema agora responde, na interface, **qual inversor** está com problema.

> **Correção factual descoberta durante o ADR-075:** ao longo da execução da T1 foi dito, várias
> vezes, que "o backend já avisa qual inversor caiu, mas só por Telegram". **Isso é impreciso.**
> `send_production_alert` (`alerts/production_alert.py:392`) **não tem nenhum chamador de
> produção** — as únicas referências fora da própria definição estão em
> `tests/test_production_alert.py`. Verificado com
> `grep -rn "send_production_alert" src/ tests/`.
>
> Ou seja: a avaliação por inversor existia como código, era testada, e **nunca chegava a
> ninguém por canal nenhum**. Isso não reduz o valor da T1 — aumenta: o endpoint e a tela criados
> aqui são hoje o **único** caminho pelo qual essa análise alcança um ser humano.
| T2 | 2026-08-12 | não commitado | `lib/api.ts`, `lib/api.test.ts`, `MonthlyProductionSection.tsx(.test)`, `ProductionPage.tsx` | 807 passando (+11), type-check 0, +0,95 kB gzip | `reviewer` — **1 P1 (ver T2a), 2 P2, 1 P3** |
| T2a | 2026-08-12 | não commitado | `src/mplacas/main.py` (1 linha), `lib/api.ts`, `lib/api.test.ts` | backend 838/6 sem regressão; frontend 810 | `reviewer` (2ª passada) — 1 P1 + 2 P2 → T2b |
| T2b | 2026-08-12 | não commitado | `tests/test_cors_expose_headers.py` (novo), `lib/api.ts`, `lib/api.test.ts` | backend **840** passed/6 skipped; frontend **814** | verificado pelo orquestrador (mutação + suíte completa) |
| T6 | 2026-08-12 | não commitado | `docs/ADR-073-sessao-em-memoria.md` (novo) | n/a (documentação) | escrito pelo orquestrador |
| T3 | | | | | |
| T4 | 2026-08-13 | não commitado | `lib/dashboard/explanation-contracts.ts(.test)` (novos), `components/AiExplanationPanel.tsx(.test)` (novos), `lib/api.ts`, `DiagnosticsCard.tsx(.test)`, `OverviewPage.tsx` | backend 860/6 sem regressão; frontend **84 arquivos, 926 testes**, type-check 0 | não tocou auth/billing/credentials/organizations/audit/migrations — reviewer não acionado (regra 0.3.7) |
| T5 | 2026-08-12 | não commitado | `ProductionHistoryChart.tsx(.test)`, `ProductionHistorySection.test.tsx`, `ProductionPage.test.tsx` | 796 passando (+3), type-check 0, −0,01 kB gzip | verificado pelo orquestrador |
| T5b | 2026-08-12 | não commitado | `ProductionPage.tsx(.test)` | 808 passando (+1), type-check 0 | verificado pelo orquestrador |
| T6 | | | | | |
| T7 | | | | | |
| T8 | 2026-08-13 | não commitado | `frontend/scripts/check-bundle-budget.mjs` (novo), `frontend/package.json`, `.github/workflows/ci.yml` | build ok, gate `check-bundle-budget` verde (7/7 chunks); provado por mutação (ESTOUROU + AUSENTE), depois restaurado e verde de novo | verificado pelo orquestrador (mutação + restauração por diff) |
| T9 | 2026-08-12 | não commitado | 8 snapshots → `docs/snapshots-historicos/` + README | n/a (sem código) | verificado pelo orquestrador |
| T10 | 2026-08-12 | não commitado | `LoadingAnnouncement.tsx(.test)` (novos), `MonthlyProductionSection.*`, `CapexRegistrationForm.*`, `PlantSelector.*`, `LoginPage.*` | 74 arquivos, **826** testes, type-check 0 | verificado pelo orquestrador |

**Nota:** os arquivos eram **não rastreados** pelo git antes da T9 — por isso o `git status` não
mostra deleção na raiz. Confirmado com `git ls-files`.

### ⚠ Higiene de commit — leia antes de commitar qualquer coisa

1. **`src/mplacas/main.py` acumula DUAS mudanças de tarefas diferentes:**
   - `expose_headers=["Content-Disposition"]` (linha ~78) → pertence à **T2a**;
   - `import` + `app.include_router(devices_router)` (linhas ~20 e ~165) → pertence à **T1b**.

   A regra 0.3.6 (uma tarefa por commit) exige separá-las. Commitar o arquivo inteiro de uma vez
   mistura duas tarefas e destrói a rastreabilidade que este plano existe para garantir. Use
   `git add -p` para separar por hunk.

2. **Nomenclatura:** o ADR-074 (Decisão 6) chama a etapa de backend de "T1a" e a de UI de "T1b".
   Este plano usa uma granularidade maior — **T1a** (movimento de código), **T1b** (endpoint),
   **T1c** (UI). Não é divergência de implementação, só de rótulo. Ao ler o ADR, mapeie:
   ADR-T1a = plano-T1a + plano-T1b; ADR-T1b = plano-T1c.
