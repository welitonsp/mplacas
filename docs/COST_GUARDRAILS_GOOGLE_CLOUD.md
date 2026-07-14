# Controles de custo Google Cloud

## Princípios

O Mplacas foi preparado para Cloud Run com escala a zero e banco Neon Free. A meta de custo
baixo depende de configuração operacional disciplinada.

## Guardrails obrigatórios

- `min-instances=0` para o serviço web.
- `max-instances=1` na configuração inicial.
- Região única definida.
- Memória inicial de 512 MiB.
- CPU inicial igual a 1.
- Sem Compute Engine.
- Sem Cloud SQL.
- Sem load balancer externo dedicado.
- Sem discos persistentes.
- Sem NAT Gateway dedicado.
- Sem armazenamento de dumps ou PDFs no contêiner.

## Orçamento e alertas

Antes do deploy, crie orçamento mensal baixo e alertas em 50%, 80% e 100%. Revise o painel
de billing após o primeiro deploy, após a primeira execução de Scheduler e semanalmente no
primeiro mês.

## Recursos que podem gerar cobrança

- Artifact Registry por armazenamento de imagens.
- Cloud Run por CPU, memória e requisições acima da franquia.
- Cloud Scheduler por jobs acima da franquia.
- Secret Manager por versões e acessos acima da franquia.
- Egress de rede.
- Logs em volume excessivo.

## Checklist antes do deploy

- Billing habilitado com orçamento.
- `min-instances=0`.
- `max-instances=1`.
- Apenas uma região.
- Imagem sem testes, docs, dumps, PDFs, `.env` e `.git`.
- Nenhum Cloud SQL ou Compute Engine criado.
- Secret Manager com versões necessárias apenas.
- Scheduler diário com retry limitado.
- Logs sem payloads grandes.

## Checklist de encerramento

- Remover serviços Cloud Run.
- Remover Cloud Run Jobs.
- Remover Cloud Scheduler.
- Remover imagens antigas do Artifact Registry.
- Remover secrets que não serão usados.
- Confirmar ausência de Cloud SQL, Compute Engine, load balancer e discos.
- Verificar billing no dia seguinte.

## Revisão periódica

Revisar mensalmente: número de revisões Cloud Run, imagens antigas, volume de logs,
execuções de jobs, segredos obsoletos e alertas de orçamento.
