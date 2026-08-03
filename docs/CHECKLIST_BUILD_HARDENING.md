# Checklist de remediação — Hardening de build e guardrails operacionais

Última atualização: 2026-08-03 (sessão 3)
Base: `origin/main` em `9a1c17c` (sessão 1); reconciliado em `6062530` (sessão 2); P2 automatizado
nesta sessão.
Origem: revisão de um relatório externo sobre o projeto ("Princípios de Confiabilidade",
"Guardrails GCP", "Regra de Entrega"), auditado item a item contra o código atual. A maioria das
premissas do relatório foi confirmada; os itens abaixo são as lacunas reais que sobraram dessa
auditoria — não vulnerabilidades novas, mas gaps de reprodutibilidade e automação.

Legenda: `[x]` concluído, `[~]` parcial, `[ ]` pendente.

## P1 — Build reprodutível

- [x] **Lockfile de dependências criado e enforced.** Resolvido pelo P2-03 do ciclo BIG TECH
  (`AUDITORIA_BIG_TECH_2026-08-01.md`, ver `docs/SUPPLY_CHAIN_POLICY.md:5`): `requirements.lock`
  (runtime) e `requirements-dev.lock` (+ extra `dev`) gerados via `pip-compile --generate-hashes`.
  `Dockerfile:16` e `.github/workflows/ci.yml:22,152` instalam com
  `pip install --require-hashes -r requirements*.lock`, e `-e .` entra com `--no-deps` — ou seja,
  o range em `pyproject.toml` **não** controla a versão instalada de fato; o lockfile é a única
  fonte de verdade para o build. Este checklist (sessão 1, 2026-07-30) estava desatualizado sobre
  isso; reconciliado nesta sessão.

- [x] **Dependabot do grupo `python-runtime` bumpa `pyproject.toml`, não o lockfile — gap
  detectado e corrigido nesta sessão (2026-08-03).** Ao mesclar o PR #76 (`chore(deps): bump the
  python-runtime group with 5 updates`), o diff tocou só `pyproject.toml`; `requirements.lock` e
  `requirements-dev.lock` continuaram pinados nas versões antigas
  (`reportlab==4.5.1`, `argon2-cffi==23.1.0`, `google-cloud-storage==2.19.0`, `mypy==1.20.2`,
  `editables==0.5`), então as 5 dependências não tinham sido atualizadas de fato em runtime/CI
  apesar do PR aparecer mesclado e verde. Regenerado com
  `pip-compile pyproject.toml --generate-hashes --strip-extras --allow-unsafe
  --upgrade-package <nome> --output-file=requirements.lock` (idem com `--extra dev` +
  `mypy`/`editables` para o dev-lock) — usar `--upgrade-package` por nome é necessário porque o
  pip-compile, por padrão, preserva os pins existentes que ainda satisfazem o range e não teria
  de fato bumpado nada. Resultado: `argon2-cffi==25.1.0`, `google-cloud-storage==3.13.0`,
  `reportlab==5.0.0`, `mypy==2.3.0`, `editables==0.6` (mais a transitiva nova `ast-serialize`
  trazida pelo mypy 2.3.0). Um teste de contrato (`test_supply_chain_contract.py:20`) tinha
  `editables==0.5` hardcoded e precisou ser atualizado junto. Validado com
  `pip install --dry-run --require-hashes` (hashes batem) e suíte completa: ruff limpo, mypy
  limpo (181 arquivos, já sob o próprio mypy 2.3.0), 631 testes passando/5 skipped — sem regressão
  do salto maior de mypy nem do reportlab (usado no exportador de PDF).
  **Risco residual — automatizado nesta sessão (ver ADR-064).** Implementado guard de 3 camadas:
  (1) `scripts/check_lock_drift.py` + job `dependency-lock-drift` em `.github/workflows/ci.yml`,
  bloqueante em todo PR, compara semanticamente as seções de dependência do `pyproject.toml` entre
  base e HEAD e exige que o(s) lockfile(s) correspondente(s) tenham mudado junto — validado por
  simulação real do incidente do PR #76 (reviewer reproduziu o cenário via `git worktree` e
  confirmou exit 1); (2) contrato estático em `tests/test_supply_chain_contract.py` travando pins
  dentro do range e header canônico (Python 3.12); (3) `.github/workflows/lock-freshness.yml`,
  checagem semanal não-bloqueante que abre issue se os locks ficarem atrás do PyPI.
  **Pré-requisito resolvido junto:** os locks estavam sendo gerados sob Python 3.14 (divergindo de
  `Dockerfile`/CI/`SUPPLY_CHAIN_POLICY.md`, que sempre exigiram 3.12); regenerados sob 3.12 via novo
  `scripts/compile-locks.sh`, sem mudança de versão de pacote.
  **Item de acompanhamento em aberto (não bloqueante):** a regeneração desta sessão rodou em
  ambiente Windows nativo (sandbox sem Docker disponível), não dentro do container Linux real —
  resolveu a divergência de *versão* do Python mas não a de *plataforma* (`win32` vs `linux`, ex:
  `colorama` aparece no lock por ser dependência condicional de `click` só em Windows). Assim que
  houver Docker disponível (CI ou máquina do time), rodar `scripts/compile-locks.sh` de fato e
  comparar o diff. Sugestão adicional do reviewer, também não bloqueante: declarar `packaging` como
  dependência dev explícita em `pyproject.toml` (hoje só transitiva de `opentelemetry-instrumentation`)
  já que `tests/test_supply_chain_contract.py` a importa diretamente.

## P2 — Automação de guardrail de custo/infra

- [x] **`audit-costs.sh` era um guardrail real mas manual — automatizado nesta sessão
  (2026-08-03).** O script (`infra/gcp/audit-costs.sh`) já falhava explicitamente
  (`fail_if_output`/`die`) se existisse Cloud SQL, Compute Engine, Load Balancer ou VPC Connector
  com nome `~mplacas` — era enforcement de verdade, não só ausência de script de provisionamento.
  O gap era só estar documentado como comando manual em `docs/runbook-producao.md`, sem rodar em
  CI nem em Cloud Scheduler (controle detectivo, não preventivo — infra paralela criada por engano
  só era pega na próxima execução manual).

  **Achado durante a implementação, corrigido antes de agendar:** o check de Cloud Scheduler
  (`infra/gcp/audit-costs.sh:101-109` na versão anterior) usava o mesmo padrão ingênuo dos outros
  recursos — "qualquer scheduler `~mplacas` é proibido" — mas isso é um falso-positivo estrutural
  aqui: os 8 schedulers `mplacas-*` legítimos já criados por `infra/gcp/provision-operations.sh`
  (`mplacas-collect`, `mplacas-daily-pipeline`, `mplacas-dispatch-outbox`,
  `mplacas-drain-collection`, `mplacas-drain-report-exports`, `mplacas-daily-digest`,
  `mplacas-operational-watchdog`, `mplacas-retention`) sempre teriam feito o guardrail falhar.
  Rodar isso sem correção via Cloud Scheduler teria dado alerta de "recurso proibido" contra a
  própria infraestrutura operacional do projeto em toda execução agendada — nunca havia sido
  notado porque a execução manual sempre foi feita por alguém que já sabia que aqueles schedulers
  eram esperados. Corrigido substituindo a checagem binária por uma allowlist:
  `MPLACAS_EXPECTED_SCHEDULER_JOBS` em `infra/gcp/lib.sh` é agora a fonte única de verdade dos
  nomes de scheduler esperados (consultada por `audit-costs.sh`, `provision-operations.sh` e pelo
  novo `provision-cost-audit.sh`); só um scheduler `~mplacas` fora dessa lista falha o guardrail.

  Implementado:
  - `infra/gcp/lib.sh`: `MPLACAS_EXPECTED_SCHEDULER_JOBS`, `scheduler_job_is_expected()`,
    `MPLACAS_CONFIG_FROM_ENV=1` como modo alternativo de `load_config()` (config direto do
    ambiente do container, sem exigir `config.env` em disco — `validate_config()` continua
    aplicada sem relaxamento), `auditor_service_account_email()`,
    `ensure_auditor_service_account()`.
  - `infra/gcp/audit-costs.sh`: check de Cloud Scheduler trocado para allowlist; check de billing
    (`roles/billing.viewer`, fora do escopo do projeto) tornado opcional via
    `MPLACAS_AUDIT_SKIP_BILLING=1`, usado apenas pelo job automatizado — todo o resto do guardrail
    continua obrigatório.
  - `infra/gcp/Dockerfile.audit`: imagem dedicada (pinada por digest), sem código-fonte da
    aplicação nem segredos, roda como usuário não-root.
  - `infra/gcp/provision-cost-audit.sh`: provisiona a service account `mplacas-auditor` (papéis
    só-leitura — `serviceUsageViewer`, `run.viewer`, `cloudsql.viewer`, `compute.viewer`,
    `cloudscheduler.viewer`, `artifactregistry.reader`, `secretmanager.viewer`; nunca
    `secretAccessor`), o Cloud Run Job `mplacas-cost-audit` e o Cloud Scheduler diário (`0 4 * * *`).
  - `infra/gcp/monitoring/operational-job-failure.json`: `cost-audit` incluído no regex de jobs
    monitorados (bump `v1` → `v2`).
  - Testes de contrato cobrindo o allowlist (job esperado passa, job desconhecido falha) e o modo
    `MPLACAS_CONFIG_FROM_ENV` (completo passa sem `config.env` em disco; incompleto falha com a
    mesma mensagem de sempre) em `tests/test_gcp_input_validation.py`.

  Nenhum comando `gcloud` de deploy real foi executado durante a implementação — apenas scripts,
  testes automatizados e revisão manual do `Dockerfile.audit`. O deploy real
  (`bash infra/gcp/provision-cost-audit.sh`) fica para confirmação explícita do operador.

## Resumo

| Categoria | Concluídos | Parciais | Pendentes |
|---|---:|---:|---:|
| P1 (build reprodutível) | 2 | 0 | 0 |
| P2 (automação de guardrail) | 1 | 0 | 0 |

Nenhum item pendente hoje. Dois itens de acompanhamento não bloqueantes ficam em aberto: (1) rodar
`scripts/compile-locks.sh` de fato em ambiente com Docker para fechar a divergência de plataforma
residual dos lockfiles (ver P1 acima); (2) o deploy real de `infra/gcp/provision-cost-audit.sh` —
deliberadamente não executado durante a implementação, aguardando confirmação explícita do operador
antes de tocar infraestrutura compartilhada.

## PR #70 (Docker Python 3.12 → 3.14) — mantido em aberto deliberadamente

Analisado em 2026-08-03: CI falha por design em dois testes de contrato
(`test_dockerfile_uses_cloud_run_entrypoint_and_non_root_user`,
`test_images_and_actions_are_immutable`) que travam a versão/digest da imagem base — não é a
imagem 3.14 quebrando algo, é o guardrail de supply chain funcionando. Salto de duas versões
maiores (pula 3.13), e nenhum teste de CI de fato constrói/roda a aplicação sob 3.14 — só valida
o texto do `Dockerfile`. Não mesclar sem antes: atualizar o digest fixado, validar compatibilidade
real de todas as dependências (lockfile) com 3.14, e rodar a suíte completa numa imagem construída
de fato sob 3.14.
