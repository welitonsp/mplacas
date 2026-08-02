# Runbook — alertas operacionais no Google Cloud Monitoring

## Objetivo

Garantir que uma falha dos Cloud Run Jobs obrigatórios ou a interrupção silenciosa do fluxo
Scheduler → Cloud Run → ledger seja detectada fora da própria aplicação.

As políticas são declarativas, versionadas em `infra/gcp/monitoring/` e reconciliadas pelo
`infra/gcp/provision-operations.sh`. Não crie cópias manualmente no console.

## Contrato monitorado

O provisionamento mantém duas políticas habilitadas:

1. `operational_job_failure`: alerta quando qualquer job operacional termina com resultado diferente
   de `succeeded` na métrica nativa `run.googleapis.com/job/completed_execution_count`.
2. `operational_watchdog_absence`: alerta quando não há execução bem-sucedida do watchdog por duas
   horas.

O watchdog roda aos cinco minutos de cada hora e falha de forma segura quando a planta configurada
não existe ou é ambígua, não há histórico do pipeline, a última execução falhou, permanece em
andamento por mais de 30 minutos ou o último sucesso terminou há mais de 26 horas. Ele só lê o banco;
não cria plantas nem altera dados operacionais.

As duas condições são complementares: a primeira detecta uma execução que falhou; a segunda detecta
também Scheduler pausado, quebra de IAM ou job que deixou de ser invocado.

## Pré-requisitos

Crie ao menos um canal no Cloud Monitoring e registre seu nome completo em
`infra/gcp/config.env`:

```bash
GCP_MONITORING_NOTIFICATION_CHANNELS=projects/meu-projeto/notificationChannels/123456
```

Vários canais podem ser informados separados por vírgula, sem espaços. O provisionador rejeita
recursos de outro projeto, valores abreviados e entradas vazias.

## Provisionamento idempotente

```bash
bash infra/gcp/provision-operations.sh
```

Cada política possui uma identidade imutável em `userLabels.mplacas_policy_id`. O script lista as
políticas gerenciadas, interrompe se encontrar identidade duplicada, cria quando ausente e atualiza
quando existente. O arquivo versionado é a fonte de verdade; o nome gerado pelo Google não é salvo
no repositório.

## Verificação pós-deploy

```bash
bash infra/gcp/verify-operations.sh
```

Após a confirmação exata, o verificador exige:

- todos os Cloud Run Jobs obrigatórios;
- todos os Scheduler jobs em estado `ENABLED`;
- as duas políticas habilitadas e ligadas aos canais configurados;
- sucesso do smoke job somente leitura;
- sucesso do watchdog, que também produz a primeira amostra para a condição de ausência.

A condição de ausência só pode abrir incidente depois que a série temporal tiver uma medição. Por
isso a primeira execução bem-sucedida do verificador é requisito de ativação, não apenas uma checagem
opcional.

Registre como evidência de aceite o projeto, região, revisão da imagem, nomes das execuções, horário,
resultado do verificador e IDs das políticas, sem copiar segredos ou connection strings.

## Teste controlado do incidente

Faça em homologação:

1. execute o verificador e confirme que o watchdog está saudável;
2. pause apenas a agenda do watchdog;
3. aguarde a janela de duas horas e confirme abertura e entrega do incidente;
4. reative a agenda, execute o watchdog e confirme o fechamento;
5. anexe timestamps e ID do incidente ao registro da mudança.

Não introduza credencial inválida em produção para testar a política de falha.

## Diagnóstico

Para alerta de falha, identifique `resource.labels.job_name`, abra a execução correspondente e siga
os logs estruturados até a causa. Para ausência, verifique nesta ordem: estado do Scheduler, última
tentativa, permissão `roles/run.invoker`, existência do job, execução do watchdog e estado do ledger
do pipeline.

Ausência de histórico, heartbeat ou métrica nunca deve ser interpretada como saúde.

## Rollback seguro

Prefira desabilitar a política, preservando histórico e auditabilidade:

```bash
gcloud monitoring policies update POLICY_NAME --no-enabled --project "$GCP_PROJECT_ID"
```

Para rollback de configuração, reverta os JSONs para a versão aprovada e execute novamente o
provisionador. Se o watchdog estiver gerando ruído por um defeito conhecido, pause somente sua agenda
e mantenha um incidente aberto até a correção. Excluir políticas é uma ação excepcional e exige
registro explícito porque remove o vínculo operacional e pode prejudicar a investigação.
