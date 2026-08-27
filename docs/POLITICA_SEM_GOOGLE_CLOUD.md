# Política — Google Cloud proibido no Mplacas

**Status: OBRIGATÓRIA.** Vigente desde 2026-08-25, reafirmada pelo dono do produto em 2026-08-26.

Sucede `infra/gcp/ZERO_COST_POLICY.md`, removido junto com o diretório `infra/gcp/`. O documento
mudou de lugar, **não** de força: a proibição continua valendo integralmente.

## Invariante

O Mplacas não pode depender de nenhuma configuração do Google Cloud capaz de gerar cobrança.

O Free Tier do Google Cloud **não** conta como garantia de custo zero: ele exige uma conta de
faturamento ativa e passa a cobrar quando a franquia é excedida. Foi exatamente assim que a cobrança
não prevista de agosto de 2026 aconteceu.

## Consequência

Enquanto esta política existir, estão proibidos:

- implantar serviço no Cloud Run;
- criar ou executar Cloud Run Job;
- provisionar Cloud Scheduler;
- rodar auditoria de custo ou job de migração no Google Cloud;
- provisionar qualquer recurso faturável do Google Cloud;
- reintroduzir dependência, SDK, credencial ou script de deploy do Google Cloud no repositório.

Permanecem permitidos: limpeza, auditoria somente-leitura, e o que for necessário para
desvincular ou manter desativado o faturamento.

## Estado do projeto GCP

**O projeto `mplacas` foi excluído em 2026-08-26.** Verificado por `gcloud projects describe mplacas`:

```
lifecycleState: DELETE_REQUESTED
projectNumber: '104231254500'
```

O que isso significa, com precisão:

- os recursos foram desligados e **nada mais pode gerar cobrança**;
- o faturamento já estava desativado antes da exclusão (`billingEnabled: false`), e as duas contas
  de faturamento da conta Google estão fechadas;
- a exclusão é **reversível por 30 dias**. Depois desse prazo o projeto é apagado em definitivo e o
  `projectId` `mplacas` não volta.

Nenhuma ação pendente do lado do Google Cloud. A única coisa a **não** fazer é restaurar o projeto
dentro da janela de 30 dias — o que reativaria o serviço e os 12 Cloud Run Jobs que existiam nele.

## Arquitetura em vigor

Nada aqui depende do Google Cloud — ver `docs/ADR-076-saida-do-google-cloud.md` e
`docs/RUNBOOK_DEPLOY.md`:

| Peça | Onde |
|---|---|
| Frontend | Cloudflare Pages |
| Banco | Neon (nunca esteve no Google Cloud) |
| API | Render, plano free |
| Jobs e migrações | GitHub Actions |

## Alteração desta política

Mudar ou revogar esta política exige decisão arquitetural explícita do dono do produto, registrada
em ADR novo, aceitando de forma consciente a possibilidade de cobrança pelo Google Cloud.

Remover uma suspensão administrativa, um arquivo de estado ou um guardrail **não** autoriza, por si
só, voltar a implantar no Google Cloud.
