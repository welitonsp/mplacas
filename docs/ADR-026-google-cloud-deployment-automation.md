# ADR-026 — Automação segura da implantação no Google Cloud

## Status

Aceito.

## Contexto

A ADR-025 definiu Google Cloud Run como plataforma de execução do Mplacas. A etapa seguinte
precisa tornar a implantação reproduzível sem exigir Docker ou Google Cloud CLI na estação
Windows. O operador utilizará o Google Cloud Shell, que já fornece um ambiente Linux gerenciado
com `gcloud` autenticado após o login.

A automação deve reduzir erro manual, manter custos iniciais limitados e impedir que comandos de
implantação criem, por conveniência, recursos de maior custo ou privilégios amplos.

## Decisão

1. Manter scripts Bash versionados em `infra/gcp/` como interface operacional oficial.
2. Executar os scripts exclusivamente no Google Cloud Shell ou em ambiente Linux equivalente,
   nunca exigindo Docker ou Google Cloud CLI na estação Windows.
3. Usar `gcloud run deploy --source` para delegar o build ao Google Cloud.
4. Fixar a implantação inicial em:
   - região `us-central1`;
   - `min-instances=0`;
   - `max-instances=1`;
   - 1 CPU;
   - 512 MiB de memória;
   - concorrência 20;
   - timeout de 60 segundos.
5. Usar uma service account de runtime dedicada, sem chaves locais e sem papéis `Owner` ou
   `Editor`.
6. Conceder `roles/secretmanager.secretAccessor` individualmente em cada segredo necessário.
7. Criar novas versões de segredos pelo stdin, capturar diretamente o número retornado pelo
   comando de criação e desabilitar versões anteriores somente após confirmar a nova versão.
8. Nunca destruir automaticamente versões do Secret Manager.
9. Executar migrações como Cloud Run Job explícito, separado do startup HTTP.
10. Validar `/health`, `/ready`, `/dashboard` e os limites reais da revisão após o deploy.
11. Disponibilizar auditoria de custos somente leitura.
12. Exigir confirmação textual forte para deploy, migração e remoção.
13. Preservar segredos por padrão na remoção; excluí-los somente com opção explícita.
14. Nunca excluir automaticamente projeto, billing ou Artifact Registry.

## Recursos deliberadamente fora do escopo

A automação não cria:

- Compute Engine;
- Cloud SQL;
- load balancer dedicado;
- VPC Connector;
- Cloud Scheduler;
- chaves de service account;
- papéis IAM `Owner` ou `Editor`.

A recorrência do pipeline diário será tratada em decisão posterior, após validação operacional e
de custos do serviço e do job de migração.

## Segurança

- `infra/gcp/config.env` é ignorado pelo Git e não deve conter valores secretos.
- Segredos são lidos sem eco no terminal interativo ou pelo stdin.
- Valores secretos não são impressos pelos scripts.
- O deploy referencia versões do Secret Manager, sem inserir segredos na linha de comando como
  texto aberto.
- A identidade de runtime recebe apenas acesso aos segredos nomeados do Mplacas.
- O serviço continua protegido pela autenticação da própria aplicação nos endpoints operacionais.

## Controles de custo

Os limites são validados antes do uso e novamente no recurso implantado. A verificação lê o JSON
do serviço e confere as anotações `minScale` e `maxScale` da revisão, a service account e os
limites de CPU e memória do contêiner.

A auditoria falha quando identifica recursos Mplacas proibidos nas categorias verificadas ou mais
de uma versão habilitada de um segredo gerenciado pela automação.

## Consequências

### Positivas

- implantação reproduzível e auditável;
- nenhuma dependência de Docker ou `gcloud` no Windows;
- menor risco de custo acidental;
- menor risco de privilégio excessivo;
- migrações separadas do processo web;
- rotação de segredos determinística e resistente a execução concorrente.

### Negativas

- o primeiro deploy exige configuração manual do projeto, billing e orçamento;
- `min-instances=0` pode causar cold start;
- o build por `--source` depende do Cloud Build e do Artifact Registry;
- a implantação ainda exige execução humana consciente no Google Cloud Shell.

## Validação

A implementação deve permanecer coberta por:

- Ruff;
- Mypy;
- Pytest;
- `bash -n` em todos os scripts;
- ShellCheck;
- testes de contrato que bloqueiam regressões de segurança, custo e IAM.

Nenhum recurso real do Google Cloud é criado pela inclusão destes arquivos no repositório ou pela
execução do CI.
