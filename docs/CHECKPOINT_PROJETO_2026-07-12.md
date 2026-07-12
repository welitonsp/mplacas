# Checkpoint do Projeto Mplacas — 12/07/2026

## Finalidade

Este documento registra o ponto exato de encerramento do ciclo de desenvolvimento em 12/07/2026, permitindo retomar o trabalho sem perda de contexto, sem repetição de entregas e sem salto indevido de fase.

## Estado consolidado

- Repositório: `welitonsp/mplacas`
- Branch principal: `main`
- Último merge do ciclo: PR nº 20
- Commit de referência da `main`: `ffaaab5a4d9d3e2a749cfd679c7e6c342ac6044e`
- Situação: base funcional consolidada, CI aprovado nas PRs concluídas e nenhuma PR de desenvolvimento pendente após o encerramento deste ciclo.

## Visão do produto alcançada

O Mplacas evoluiu de uma fundação de coleta e persistência para uma plataforma de inteligência energética residencial com:

1. coleta e persistência de produção solar;
2. ingestão e tratamento de faturas;
3. conciliação energética por ciclo;
4. inteligência determinística sobre geração, consumo e dependência da rede;
5. tendências históricas;
6. API executiva consolidada;
7. dashboard web responsivo;
8. correlação climática e detecção de anomalias;
9. explicações assistidas por IA com grounding obrigatório;
10. alertas confiáveis;
11. runtime real de entrega pelo Telegram;
12. deduplicação persistente em SQL e job determinístico de alertas.

## PRs concluídas neste ciclo

| PR | Entrega principal | Commit de merge |
|---|---|---|
| #10 | Fluxo Telegram PDF de ponta a ponta | `54664e388dfcb7375977d1900e486b6d6ed61131` |
| #11 | Inteligência energética determinística | `47aa3590c83e68549a254d480a187ddecd6b7571` |
| #12 | Tendências históricas | `ce2b16b6820b847ab2f43ac6a6ec289dccc2fefd` |
| #13 | API executiva consolidada | `de4c1ddde4df3e4b1d6e5fe8c31640927c920012` |
| #14 | Dashboard web responsivo | merge concluído |
| #16 | Correlação climática e detecção de anomalias | `212de79e0a4c558bf2bfbdd28ccd6a4623716618` |
| #17 | Explicações assistidas por IA com grounding | `be91550b43d40fdbf6186a1389e2f6244de3c95b` |
| #18 | Fundação de alertas confiáveis | `8646c13b08be5dd0c48fcd8cfc06f085bd7e2346` |
| #19 | Runtime real de alertas pelo Telegram | `e5e1f66ccc0dcc7fe3b5f910d3c3e95027713e4a` |
| #20 | Ledger SQL transacional e job de alertas | `ffaaab5a4d9d3e2a749cfd679c7e6c342ac6044e` |

> A PR nº 15 foi uma duplicata acidental da PR nº 14 e foi encerrada sem merge.

## Arquitetura funcional atual

### Coleta e dados solares

- contrato substituível `SolarProvider`;
- adaptador NEPViewer isolado;
- autenticação e renovação controladas;
- persistência assíncrona com SQLAlchemy;
- suporte a PostgreSQL e SQLite;
- histórico e idempotência de produção diária;
- políticas de coleta intradiária, consolidação D+1 e backfill.

### Faturas e conciliação

- fluxo de ingestão de PDF pelo Telegram;
- parser determinístico;
- revisão humana antes da confirmação;
- conciliação por ciclo de leitura;
- métricas em `Decimal`;
- qualidade de dados explícita.

### Inteligência energética

- produção, consumo, importação, injeção e autoconsumo;
- autossuficiência e dependência da rede;
- cobertura por créditos;
- componente de energia da fatura;
- score de saúde de 0 a 100;
- diagnósticos determinísticos com severidade e ação recomendada;
- comparação entre ciclos e tendências `UP`, `DOWN` e `STABLE`;
- API executiva consolidada.

### Dashboard

- rota web responsiva;
- suporte a desktop, tablet e celular;
- tema claro e escuro automático;
- autenticação operacional sem persistência local da chave;
- cartões executivos, qualidade de dados, tendências e ações prioritárias.

### Clima e anomalias

- observação climática diária tipada;
- persistência vinculada à usina;
- irradiação, nebulosidade e precipitação opcionais;
- comparação entre produção esperada e realizada;
- níveis `NORMAL`, `ATTENTION`, `ANOMALY` e `CRITICAL`;
- análise de janelas de 1 a 90 dias;
- detecção de sequência de dias anormais;
- endpoint protegido de anomalias;
- ausência de atribuição automática de causa quando a evidência é insuficiente.

### Explicações assistidas por IA

- IA usada somente como camada opcional de linguagem;
- nenhuma alteração de cálculo, severidade ou diagnóstico;
- grounding obrigatório em evidências já produzidas;
- fallback determinístico obrigatório;
- limite de próximos passos;
- aviso técnico fixo;
- funcionamento preservado mesmo sem provedor de IA.

### Alertas e Telegram

- severidades `INFO`, `WARNING` e `CRITICAL`;
- estados `SKIPPED`, `SENT` e `FAILED`;
- política de severidade mínima;
- deduplicação por fingerprint;
- envio registrado somente após confirmação do provedor;
- nova tentativa após falha;
- adaptador real para Telegram Bot API via `httpx`;
- mensagens sanitizadas em texto simples;
- token, chat e timeout exclusivamente por configuração externa.

### Ledger SQL e job

- modelo `AlertDeliveryRecord`;
- fingerprint único e indexado;
- registro de provedor, referência sanitizada de destino e horário de confirmação;
- `SqlAlertDeliveryLedger` assíncrono;
- tratamento idempotente de conflito de unicidade;
- job `run_alert_dispatch_job`;
- resumo de avaliados, enviados, ignorados e falhos;
- testes de integração com SQLite em memória.

## Decisões de segurança preservadas

- nenhuma credencial no repositório;
- nenhum token real do Telegram;
- nenhuma senha da NEPViewer;
- nenhuma fatura real;
- nenhum CPF, endereço, unidade consumidora ou payload privado;
- IA generativa não participa dos cálculos nem da classificação técnica;
- mensagens externas recebem apenas projeções sanitizadas;
- diagnósticos permanecem auditáveis e determinísticos.

## Ponto exato para retomada

A próxima fase deve começar como **PR nº 21**, a partir da `main` atual.

### Escopo recomendado da PR nº 21

**Operacionalização completa do pipeline de alertas**:

1. criar migração Alembic formal para `alert_delivery_records`;
2. integrar o ledger SQL ao `SessionFactory` de produção;
3. criar serviço operacional protegido para execução do job;
4. conectar os diagnósticos executivos e de anomalia ao gerador de `AlertCandidate`;
5. adicionar logs estruturados e sanitizados;
6. adicionar métricas de avaliados, enviados, ignorados, falhos e duplicados;
7. definir política de reexecução segura;
8. adicionar testes de integração do fluxo completo;
9. atualizar documentação de variáveis de ambiente;
10. validar Ruff, Mypy, Pytest e CI antes do merge.

## Pendências técnicas conhecidas

1. A migração Alembic específica do ledger de alertas ainda deve ser formalizada.
2. O wiring produtivo do job com `SessionFactory` ainda deve ser concluído.
3. A geração automática de candidatos a alerta a partir dos diagnósticos ainda deve ser conectada.
4. A observabilidade persistente do pipeline de alertas ainda deve ser ampliada.
5. O README principal está desatualizado e ainda descreve o estado antigo de fundação/P1; deve ser revisado em uma PR específica de documentação ou junto à próxima fase operacional.
6. Deve ser revisado o vínculo entre faturas e usinas para garantir isolamento correto em cenários multiusina.

## Critérios para a próxima retomada

Antes de iniciar a PR nº 21:

- confirmar que `main` aponta para o commit `ffaaab5a4d9d3e2a749cfd679c7e6c342ac6044e` ou para um commit posterior legítimo;
- confirmar que não existem PRs abertas inesperadas;
- criar nova branch a partir da `main`;
- manter dados de teste sintéticos;
- não incluir segredos ou dados pessoais;
- não declarar CI aprovado antes da confirmação no GitHub Actions.

## Comando de retomada sugerido

```text
Retomar o Mplacas a partir do checkpoint de 12/07/2026 e iniciar a PR nº 21 com a operacionalização completa do pipeline de alertas.
```

## Encerramento do ciclo

O projeto encerra o dia com as PRs nº 19 e nº 20 mergeadas, a `main` consolidada e o próximo passo técnico explicitamente definido. Este documento é a fonte de referência para a retomada do desenvolvimento.
