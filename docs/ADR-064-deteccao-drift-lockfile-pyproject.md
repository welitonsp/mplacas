# ADR-064 — Detecção de drift entre `pyproject.toml` e os lockfiles

Status: Aceito — 2026-08-03

## Contexto

A política de supply-chain do projeto (`docs/SUPPLY_CHAIN_POLICY.md`) estabelece que
`requirements.lock` e `requirements-dev.lock`, gerados por `pip-compile --generate-hashes`, são a
única fonte de verdade das versões instaladas: o `Dockerfile` e o CI instalam com
`pip install --require-hashes -r requirements*.lock` e o pacote local entra com `--no-deps`. Os
ranges de `pyproject.toml` não controlam o que roda em runtime.

Essa assimetria produziu um incidente real. O Dependabot do grupo `python-runtime` mesclou o PR #76
(`chore(deps): bump the python-runtime group with 5 updates`) tocando apenas `pyproject.toml`.
Como o Dependabot só alarga o limite superior do range (por exemplo `argon2-cffi>=23.1,<24` para
`<26`), o pin antigo (`23.1.0`) continuou satisfazendo o range novo; e `pip-compile` sem
`--upgrade-package` preserva pins existentes por padrão. Resultado: os lockfiles não mudaram, o PR
apareceu mesclado e verde, e as 5 dependências não foram atualizadas de fato em runtime nem no
CI. O desvio só foi percebido em auditoria manual e corrigido no commit `035a5db`
(`fix(deps): regenerar lockfiles apos o bump do Dependabot no python-runtime`). O gap havia sido
registrado em `docs/CHECKLIST_BUILD_HARDENING.md` como risco residual de automação do lockfile.

Durante a correção apareceu um achado colateral da mesma classe: os lockfiles vinham sendo gerados
sob Python 3.14, por causa do interpretador do ambiente de quem rodou `pip-compile` por último,
enquanto o `Dockerfile`, o `.github/workflows/ci.yml` e a própria `SUPPLY_CHAIN_POLICY.md` sempre
exigiram Python 3.12. Como o pip-tools resolve environment markers no momento da geração, isso é
uma divergência estrutural entre o ambiente de resolução e o ambiente de runtime, não um detalhe
cosmético. A correção foi criar `scripts/compile-locks.sh`, que executa `pip-compile` dentro de um
container baseado no mesmo digest de imagem do `Dockerfile`, e regenerar os locks sob 3.12.

A abordagem óbvia, `pip-compile --dry-run` seguido de diff simples contra o lock commitado, foi
avaliada e rejeitada: pelo mesmo motivo do primeiro parágrafo (sem `--upgrade-package` os pins
existentes são preservados), ela comprovadamente não teria detectado o incidente do PR #76.

## Decisão

Adotar três camadas complementares, com papéis deliberadamente distintos.

### 1. Guard bloqueante no PR — `scripts/check_lock_drift.py`

Executado pelo job `dependency-lock-drift` do `.github/workflows/ci.yml`, apenas em
`pull_request`, sem instalar dependência alguma (puro stdlib, `tomllib`). Ele compara
semanticamente o `pyproject.toml` entre o base ref do PR e o HEAD, restrito às seções que afetam
resolução: `project.dependencies`, `project.optional-dependencies`, `project.requires-python` e
`build-system.requires`. Se alguma delas mudou, exige que o lockfile correspondente apareça entre
os arquivos alterados do PR; caso contrário falha, apontando para
`scripts/compile-locks.sh --upgrade-package <nome>`. Mudanças em outras seções do `pyproject.toml`
(`[tool.ruff]`, `version` etc.) são ignoradas de propósito, para não gerar falso-positivo.

### 2. Contrato estático — `tests/test_supply_chain_contract.py`

Testes que travam, na suíte, as invariantes que o incidente violou:

- todo pin dos dois lockfiles satisfaz o range declarado em `pyproject.toml`, comparando por nome
  canônico PEP 503 (`tomllib` mais `packaging`);
- pacotes dev-only não vazam para `requirements.lock`;
- o header de ambos os locks é canônico: Python 3.12, flags `--allow-unsafe --generate-hashes
  --strip-extras`, e `--extra=dev` presente somente no dev-lock.

A terceira asserção é o que impede a regressão silenciosa da classe de bug do Python 3.14.

### 3. Freshness semanal não-bloqueante — `.github/workflows/lock-freshness.yml`

Em `schedule` semanal mais `workflow_dispatch`, roda `scripts/compile-locks.sh --upgrade` contra o
Docker real do runner do GitHub Actions e faz `git diff --exit-code` nos locks. Havendo
divergência, abre ou atualiza uma issue deduplicada por título, anexando o diff como artefato. O
job não falha: é puramente detectivo, na mesma classe do `audit-costs.sh` documentado em
`docs/CHECKLIST_BUILD_HARDENING.md`.

A divisão de papéis é o núcleo da decisão: a camada 1 responde "o lock está coerente com o que
este PR declarou?" (barato, determinístico, bloqueante); a camada 3 responde "o lock está atrás do
que o PyPI já publicou?" (caro, dependente de terceiros, informativo).

## Consequências

### Positivas

- O modo de falha exato do PR #76 passa a ser impossível de mesclar em silêncio: qualquer bump de
  dependência direta, manual ou do Dependabot, é barrado até que os locks acompanhem.
- A detecção não custa instalação de dependências nem resolução de rede no caminho do PR: o guard
  é stdlib puro e roda em segundos.
- O ambiente de resolução dos locks passa a ser reprodutível e igual ao de runtime por construção
  (`scripts/compile-locks.sh` usa o digest do `Dockerfile`), e o desvio de versão do interpretador
  fica travado por teste, não por disciplina.
- Atraso em relação ao PyPI vira sinal visível (issue semanal) em vez de descoberta por auditoria
  manual, como aconteceu desta vez.

### Negativas

- A camada 1 exige que todo bump de dependência direta regenere ambos os locks no mesmo PR, mesmo
  quando a resolução resultante seria idêntica. É fricção deliberada, não um bug: o custo de um
  `compile-locks.sh` extra é menor que o custo de um bump fantasma.
- A camada 3 fica fora do caminho do PR de propósito. Um `--upgrade` bloqueante deixaria todo PR
  do projeto refém do calendário de release de terceiros no PyPI: um lançamento novo quebraria PRs
  sem relação alguma com dependências.
- A divergência de plataforma nos locks atuais permanece aberta. A regeneração desta sessão rodou
  num ambiente Windows nativo (sandbox sem Docker disponível), não dentro do container Linux:
  resolveu a divergência de versão do Python (3.14 para 3.12), mas não a de plataforma (`win32`
  vs `linux`). Este ADR não fecha esse ponto; ele é item de acompanhamento explícito, e não um
  problema novo introduzido aqui. A primeira execução de `scripts/compile-locks.sh` num ambiente
  com Docker deve normalizar os markers.
- O guard depende de `fetch-depth: 0` no checkout do job para enxergar o base ref; mudanças no
  workflow precisam preservar isso.

## Alternativas consideradas

- `pip-compile --dry-run` mais diff no PR. Rejeitada: não detectaria o PR #76, pelo motivo já
  descrito no Contexto.
- Renomear `requirements*.lock` para `requirements*.txt`. Faria o Dependabot reconhecer os
  arquivos nativamente e atualizá-los já com hashes, eliminando a causa-raiz em vez de detectá-la.
  Adiada explicitamente: duplicaria PRs do Dependabot e exigiria tocar `Dockerfile`, `ci.yml`,
  `.dockerignore`/`.gcloudignore`, documentação e testes. Fica como possível ADR futuro separado,
  não decidido agora.

## Validação

- O incidente original está reproduzido conceitualmente no guard: um PR que altere apenas
  `project.dependencies` sem tocar nos locks falha o job `dependency-lock-drift`.
- `tests/test_supply_chain_contract.py` roda na suíte padrão e falha se um pin sair do range, se
  um pacote dev vazar para o lock de runtime, ou se o header deixar de ser Python 3.12 com as
  flags canônicas.
- `.github/workflows/lock-freshness.yml` é acionável sob demanda por `workflow_dispatch`, o que
  permite validar o caminho de abertura de issue sem esperar o agendamento.
- Item de acompanhamento em aberto: rodar `scripts/compile-locks.sh` num ambiente com Docker e
  commitar os locks resolvidos com markers de `linux`.

## ADRs e documentos relacionados

- `docs/SUPPLY_CHAIN_POLICY.md` — política de supply-chain: lockfiles hash-locked,
  `pip-compile --generate-hashes`, instalação com `--require-hashes`.
- `docs/CHECKLIST_BUILD_HARDENING.md` — onde o gap do Dependabot foi originalmente registrado como
  risco residual, e onde o padrão de guardrail detectivo (`audit-costs.sh`) está documentado.
- ADR-029 (endurecimento operacional após auditoria profunda) e ADR-063 (Cloud Monitoring e
  watchdog operacional) — mesma família de decisões: transformar verificação manual, dependente de
  disciplina humana, em gate automatizado, distinguindo controle preventivo de controle detectivo.
