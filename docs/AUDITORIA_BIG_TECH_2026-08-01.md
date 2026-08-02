# Auditoria técnica BIG TECH — Mplacas

Data: 2026-08-01
Escopo: arquitetura, segurança, confiabilidade, dados, domínio fotovoltaico, observabilidade,
testes, supply chain e prontidão operacional.

Base observada: `HEAD b73e97e` mais alterações locais ainda não commitadas.
Checklist de execução: `docs/CHECKLIST_REMEDIACAO_AUDITORIA.md`, ciclo 2026-08-01.

## 1. Parecer executivo

O Mplacas possui uma fundação técnica acima da média para um produto em evolução: monólito modular
FastAPI, regras determinísticas, uso consistente de `Decimal`, isolamento por usina/organização,
outbox transacional, snapshots auditáveis, telemetria OpenTelemetry, imagem não-root e uma suíte de
testes ampla.

O estado auditado, porém, ainda não deve ser classificado como pronto para operação SaaS no padrão
de uma BIG TECH. A avaliação global é **6,8/10**. Existem bloqueadores de segurança e release (P0),
seguidos por lacunas de concorrência, validação PostgreSQL e automação operacional (P1).

Recomendação de release: **não promover uma nova versão para produção enquanto os P0 deste relatório
não estiverem concluídos e validados**.

## 2. Estado observado e validações executadas

O worktree já estava modificado antes da auditoria. Essas alterações pertencem ao trabalho em curso
e não devem ser descartadas por quem executar a remediação. No início da próxima sessão, executar
`git status --short` e revisar o diff antes de editar qualquer arquivo.

Dimensão aproximada do repositório auditado:

- 157 arquivos em `src`;
- 93 arquivos de testes;
- 29 migrations Alembic;
- backend Python 3.12+, FastAPI e SQLAlchemy assíncrono;
- frontend React 19, TypeScript e Vite;
- PostgreSQL em produção e SQLite usado nos testes/desenvolvimento.

Validações realizadas:

| Verificação | Resultado |
|---|---|
| `python -m ruff check .` | aprovado |
| `.venv/Scripts/python.exe -m mypy` | aprovado em 168 arquivos |
| `npm run type-check` | aprovado |
| `npm run build` | aprovado |
| `.venv/Scripts/python.exe -m pip check` | aprovado |
| `.venv/Scripts/python.exe -m pytest -q` | **513 passaram, 3 falharam, 62 warnings** |
| `npm audit` | 4 vulnerabilidades classificadas como high |
| `pip-audit` sobre o ambiente | 36 vulnerabilidades conhecidas em 2 pacotes |
| `alembic upgrade head` em SQLite vazio | falhou em `CREATE TYPE datastatus` |

As três falhas de Pytest estão em contratos de empacotamento/deploy:

- `test_dockerignore_excludes_local_state_and_sensitive_artifacts`;
- `test_gcloudignore_excludes_local_and_sensitive_artifacts`;
- `test_library_uses_stable_billing_command_and_revision_annotations`.

Os warnings relevantes incluem chaves JWT de teste abaixo de 32 bytes e threads `aiosqlite`
tentando acessar um event loop já encerrado.

## 3. Pontos fortes confirmados

- Domínios separados em módulos de billing, inteligência, clima, alertas, relatórios,
  orquestração, credenciais e organizações.
- Indicadores críticos são determinísticos; IA generativa não calcula energia, dinheiro ou
  severidade.
- Energia e valores monetários usam `Decimal`.
- Faturas exigem confirmação humana e snapshots mensais são imutáveis e verificáveis por checksum.
- Autorização por `PlantScope` e testes cross-tenant cobrem os routers de dados.
- Outbox transacional, deduplicação e locks persistentes reduzem perda e duplicação de alertas.
- Configuração de produção bloqueia SQLite, valida URLs externas e falha fechada sem chave
  operacional.
- Logs estruturados, request/trace IDs, métricas e tracing já possuem fundação consistente.
- Dockerfile usa usuário não-root e copia explicitamente apenas arquivos necessários.

## 4. Achados P0 — bloqueiam release

### P0-01 — `pypdf` vulnerável processa entrada externa

Evidências:

- `pyproject.toml` restringe `pypdf>=5.7,<6`;
- o ambiente auditado usa `pypdf 5.9.0`;
- `telegram/pdf.py` instancia `PdfReader(BytesIO(content), strict=True)` e chama
  `page.extract_text()`;
- `telegram/router.py` executa essa extração sincronamente dentro da rota assíncrona do webhook;
- a implantação limita o Cloud Run a uma instância, ampliando o impacto de bloqueio do processo.

O scan encontrou múltiplas vulnerabilidades de negação de serviço no `pypdf`, incluindo loop
infinito durante extração de texto, corrigido em 6.14.2, e consumo excessivo de memória. O uso de
`strict=True` reduz apenas parte dos casos e não elimina as vulnerabilidades ligadas à extração de
content streams.

Referências:

- https://github.com/advisories/GHSA-g867-7843-wf8q
- https://github.com/advisories/GHSA-5qjq-93h5-hrgp
- https://github.com/advisories/GHSA-7hfw-26vp-jp8m

Remediação:

1. Atualizar para `pypdf>=6.14.2,<7` e executar todos os testes de PDF/parser.
2. Mover parsing para processo ou worker isolado, com timeout real de CPU e limite de memória.
3. Manter limites de bytes, páginas e texto extraído como defesa adicional.
4. Até o deploy corrigido, desabilitar intake de PDF se a funcionalidade estiver exposta.

### P0-02 — dashboard legado persiste chave operacional em `localStorage`

Evidências:

- `src/mplacas/web/static/dashboard.js` grava `{plantId, apiKey}` em `localStorage`;
- `tests/test_web_dashboard.py` exige explicitamente essa persistência;
- `docs/ADR-012-responsive-web-dashboard.md` determina o oposto: chave somente em memória;
- a auditoria de 2026-07-16 também registra incorretamente que não havia persistência local;
- a interface aceita uma “chave operacional” genérica, inclusive uma chave administrativa global.

Impacto: um XSS, extensão maliciosa ou comprometimento da origem pode exfiltrar uma credencial de
longa duração. A existência simultânea do dashboard legado e da SPA React cria dois modelos de
autenticação e aumenta o risco de regressão.

Remediação:

1. Remover ou redirecionar `/dashboard` e manter apenas a SPA autenticada por JWT.
2. Publicar limpeza transitória de `mplacas_creds_v1` do `localStorage`.
3. Rotacionar as chaves que possam ter sido utilizadas no dashboard.
4. Adicionar CSP, HSTS, `frame-ancestors`, `X-Content-Type-Options` e `Referrer-Policy` na borda.
5. Atualizar ADR, README e testes para refletirem uma única decisão.

### P0-03 — baseline de release não está verde

Uma release não deve ser promovida com testes de contrato falhando. Há drift entre `.dockerignore`,
`.gcloudignore`, `infra/gcp/lib.sh` e as expectativas dos testes. Em particular, o contexto enviado
ao Cloud Build deve excluir explicitamente `backups/`, `reports/`, bancos e artefatos locais.

Remediação: decidir se cada falha representa implementação incorreta ou teste obsoleto, corrigir a
fonte apropriada e exigir Pytest/Ruff/Mypy/frontend totalmente verdes antes de merge.

### P0-04 — scans de dependência não bloqueiam o CI

O projeto possui bons testes funcionais, mas não executa `pip-audit`, `npm audit`, scan da imagem ou
geração de SBOM no CI. Essa ausência permitiu que o intake de PDF continuasse preso a uma major
vulnerável.

O `npm audit` reportou quatro highs. O risco efetivo é menor que a classificação bruta: o advisory
do React Router afeta APIs RSC instáveis, aparentemente não usadas, enquanto `sharp/miniflare` entra
via tooling do Wrangler. Mesmo assim, as versões devem ser corrigidas e o scan precisa bloquear
novas vulnerabilidades aplicáveis.

Referências:

- https://github.com/advisories/GHSA-qwww-vcr4-c8h2
- https://github.com/advisories/GHSA-f88m-g3jw-g9cj

## 5. Achados P1 — segurança e confiabilidade

### P1-01 — rotação de refresh token não é atômica

`AuthSessionService.rotate()` carrega a sessão por chave primária, verifica `active`, altera o
registro e cria a sessão sucessora sem lock de linha nem compare-and-swap. Duas requisições
concorrentes podem observar `active=True` e criar duas sessões válidas a partir do mesmo token.

Remediação: usar `UPDATE ... WHERE id=:jti AND active=true RETURNING`, ou lock equivalente, e revogar
toda a família se houver detecção de replay. O critério de aceite deve incluir teste concorrente em
PostgreSQL real; o teste sequencial existente não cobre a corrida.

### P1-02 — access token não revalida estado privilegiado

O bearer access token é aceito após validar assinatura/claims e derivar o escopo por organização,
sem reler usuário, organização ou role. A decisão anterior aceitou a janela residual de 15 minutos
após desativação. No padrão desta auditoria, essa decisão deve ser reavaliada especificamente para
ações ADMIN e resposta a incidentes, sem necessariamente adicionar consulta a toda leitura comum.

Também faltam validação mínima de 32 bytes para o segredo, `aud`, versionamento/rotação de chave e
allowlist rígida do algoritmo JWT.

### P1-03 — ausência de jobs pode aparecer como SLO saudável

`operations/slo.py` define a taxa como 100% quando não existe execução concluída. Se o Scheduler
nunca for criado ou parar de disparar, o sistema pode reportar `healthy`.

Remediação: SLO deve considerar heartbeat/freshness e quantidade mínima esperada de execuções por
janela, além de falhas e jobs presos.

### P1-04 — CI não valida PostgreSQL e migrations reais

A suíte usa majoritariamente SQLite com `Base.metadata.create_all`. O PostgreSQL do job de container
é usado apenas por `/health` e `/ready`, sem executar migrations ou testes de concorrência. O caminho
documentado de SQLite também é inconsistente: a migration inicial executa `CREATE TYPE`, inválido
nesse banco.

Remediação:

- subir PostgreSQL em CI;
- executar `alembic upgrade head` a partir de banco vazio;
- executar `alembic check`;
- testar claims concorrentes de outbox, filas e refresh tokens;
- corrigir documentação/estratégia de migrations SQLite ou declarar formalmente que migrations são
  exclusivas de PostgreSQL.

### P1-05 — operação crítica permanece manual

Há runbooks para Scheduler, políticas de SLO e backup/restore, porém eles não fazem parte do deploy
versionado. É possível implantar uma API saudável sem coleta periódica, drain de filas, alertas,
retenção ou restore drill efetivos.

Remediação: provisionar de forma idempotente jobs, Scheduler, IAM, alert policies e verificação de
backup. O deploy deve falhar se componentes obrigatórios estiverem ausentes.

### P1-06 — crescimento não controlado de tabelas de autenticação

`auth_sessions`, `login_rate_limits` e `user_invitations` não participam da retenção operacional.
Cada rotação cria uma nova linha de sessão. Adicionar políticas seguras que preservem evidência pelo
período definido, mas removam sessões expiradas/revogadas e contadores obsoletos.

## 6. Achados P2 — arquitetura, tenancy e supply chain

- O isolamento cross-tenant na aplicação é forte, mas não existe PostgreSQL RLS como segunda
  barreira. Elaborar ADR e introduzir contexto de tenant transacional antes de escala SaaS maior.
- `utility_bills.source_hash` é único globalmente. A idempotência deveria ser escopada por
  `plant_id`/organização para evitar colisão e negação cruzada entre tenants.
- Dependências Python usam intervalos amplos e não existe lock reproduzível da imagem. A imagem base
  e GitHub Actions usam tags, não digests/SHAs.
- Não há CodeQL/SAST, scan de segredo, scan de container, SBOM ou política automatizada de
  atualização.
- `alerts/production_alert.py`, ainda não versionado na baseline auditada, aproxima-se de 900 linhas
  e mistura consulta, decisão, rendering e despacho. Separar responsabilidades depois de estabilizar
  o comportamento.
- Existem dois frontends e documentação contraditória. Consolidar uma única superfície suportada.

## 7. Evolução recomendada do domínio fotovoltaico

Os motores atuais são auditáveis e seguros, porém ainda usam produção esperada configurada
manualmente e heurísticas globais. A irradiação do Open-Meteo é GHI horizontal, não irradiância no
plano dos módulos. A temperatura média já é coletada, mas ainda não participa do modelo técnico.

Roadmap de domínio:

1. Modelar potência DC/AC, potência por inversor, inclinação, azimute, tecnologia do módulo e data de
   comissionamento.
2. Calcular irradiância POA, temperatura de célula e perdas térmicas.
3. Implementar Performance Ratio versionado e explicitamente alinhado à IEC 61724-1.
4. Adotar baseline sazonal, clear-sky index e métodos robustos como MAD/quantis.
5. Separar perda de comunicação, indisponibilidade, clipping, sujeira, sombra e degradação.
6. Impedir que uma mediana móvel curta absorva degradação gradual como novo “normal”.
7. Persistir versão do modelo, premissas, incerteza e qualidade das entradas em cada diagnóstico.
8. Criar datasets golden com casos reais anonimizados e validação por especialista solar.

## 8. SLOs recomendados

- completude da consolidação D+1 por usina e horário limite;
- idade do último dado válido por usina/dispositivo;
- zero perda permanente após indisponibilidade de provedor;
- idade da tarefa mais antiga em cada fila/outbox;
- latência entre anomalia elegível e alerta entregue;
- taxa de falso positivo e falso negativo revisada em amostra humana;
- restauração de backup ensaiada e registrada;
- erro de cálculo contra datasets golden versionados.

## 9. Ordem de execução

1. P0-01: atualizar e isolar PDF.
2. P0-02: remover dashboard legado e rotacionar chaves afetadas.
3. P0-03/P0-04: restaurar release verde e adicionar scans.
4. P1-01/P1-02: endurecer autenticação.
5. P1-03/P1-04/P1-05: tornar jobs, PostgreSQL e operação verificáveis.
6. P1-06 e P2: retenção, RLS e supply chain.
7. Evolução do motor fotovoltaico após estabilização operacional.

O estado e os critérios de aceite de cada item estão no checklist central. Não marcar um item como
concluído apenas por implementar código: testes, documentação, migração, rollback e evidência de
validação fazem parte da definição de pronto.
