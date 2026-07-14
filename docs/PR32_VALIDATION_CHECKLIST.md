# PR nº 32 — Checklist de validação

## Escopo

Automação segura e reproduzível da implantação do Mplacas no Google Cloud Run pelo Google Cloud
Shell, sem Docker ou Google Cloud CLI na estação Windows.

## Gates automáticos

- [ ] Ruff aprovado.
- [ ] Mypy aprovado.
- [ ] Pytest aprovado.
- [ ] Oito scripts aprovados por `bash -n`.
- [ ] Oito scripts aprovados por ShellCheck.
- [ ] Build do contêiner aprovado.
- [ ] Smoke test `/health` aprovado.
- [ ] Smoke test `/ready` aprovado com PostgreSQL real.
- [ ] Testes de contrato GCP aprovados.

## Segurança

- [x] Nenhum segredo real inserido.
- [x] `infra/gcp/config.env` ignorado pelo Git e pelo contexto do Cloud Build.
- [x] Nenhuma chave de service account criada.
- [x] Nenhum papel `Owner` ou `Editor` usado.
- [x] IAM de acesso a segredo aplicado individualmente.
- [x] Versão nova do segredo capturada diretamente no comando de criação.
- [x] Nenhuma seleção da versão por ordenação de `createTime`.
- [x] Nenhuma destruição automática de versões do Secret Manager.
- [x] Segredos preservados por padrão no script de remoção.

## Custos

- [x] Região fixa em `us-central1`.
- [x] Mínimo de 0 instâncias por revisão.
- [x] Máximo de 1 instância por revisão.
- [x] CPU fixa em 1.
- [x] Memória fixa em 512 MiB.
- [x] Auditoria de custos somente leitura.
- [x] Nenhuma criação de Compute Engine.
- [x] Nenhuma criação de Cloud SQL.
- [x] Nenhuma criação de load balancer dedicado.
- [x] Nenhuma criação de VPC Connector.
- [x] Nenhuma criação de Cloud Scheduler.

## Operação

- [x] Bootstrap com confirmação exata do projeto.
- [x] Deploy com confirmação forte.
- [x] Build remoto por `gcloud run deploy --source`.
- [x] Migração fora do startup HTTP.
- [x] Migração executada por Cloud Run Job explícito.
- [x] Verificação de `/health`, `/ready` e `/dashboard`.
- [x] Validação do JSON real da revisão do Cloud Run.
- [x] Remoção limitada aos recursos nomeados do Mplacas.
- [x] Projeto, billing e Artifact Registry preservados.

## Evidências antes do merge

- [ ] Todos os jobs do GitHub Actions verdes.
- [ ] Revisão do diff concluída.
- [ ] Nenhum comentário de revisão pendente.
- [ ] PR pronta para revisão.
- [ ] Merge por squash.

## Limites desta PR

Esta PR não executa comandos `gcloud`, não cria recursos reais, não configura billing, não cria
orçamento, não implanta o serviço e não insere segredos. A execução real permanece uma etapa humana
posterior e controlada pelo runbook.
