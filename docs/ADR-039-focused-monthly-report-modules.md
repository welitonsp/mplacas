# ADR-039 - Módulos focados para relatórios mensais

## Status

Aceito.

## Contexto

O ADR-038 corrigiu o ciclo de vida do relatório com snapshots imutáveis, mas `reports/service.py`
ainda concentrava 606 linhas. O módulo definia contratos, consultava inteligência, projetava o
dashboard, serializava JSON e exportava CSV. Essa mistura aumentava o impacto de qualquer mudança e
obrigava consumidores de apresentação a depender de um serviço multifuncional.

Os exportadores PDF e XLSX já recebem um relatório pronto e não consultam domínio nem banco. A
pendência estrutural era separar o núcleo compartilhado sem quebrar importações existentes.

## Decisão

1. Mover os dataclasses imutáveis e a versão de schema para `reports/contract.py`.
2. Manter a orquestração assíncrona em `reports/projection.py`.
3. Isolar a projeção pura do dashboard em `reports/report_projection.py`.
4. Isolar JSON e CSV em `reports/serialization.py`.
5. Reduzir `reports/service.py` a uma fachada de compatibilidade, sem lógica própria.
6. Fazer router, snapshot e exportadores importarem diretamente os módulos focados.
7. Preservar contratos HTTP, payloads, fórmulas, ordem de campos e API Python anterior.
8. Aplicar o limite de 300 linhas como guardrail aos módulos centrais do relatório. Arquivos de
   renderização específicos podem ser divididos quando acumularem mais de uma responsabilidade;
   tamanho isolado não justifica abstração sem uma fronteira coesa.

## Consequências

### Positivas

- Contrato, I/O de domínio, projeção pura e serialização evoluem independentemente.
- O módulo `service.py` deixa de ser um ponto central de 606 linhas.
- Exportadores continuam funções puras e não conhecem persistência ou serviços de inteligência.
- Importações existentes permanecem válidas durante a migração dos consumidores.
- Testes de fronteira impedem que o runtime volte a depender da fachada.

### Negativas

- O pacote ganha quatro módulos pequenos e uma fachada temporária.
- Alterações no contrato podem exigir coordenação entre projeção, snapshot e serializadores.
- PDF e XLSX continuam módulos extensos, porém com responsabilidade única de renderização.

## Validação

A entrega deve permanecer coberta por:

- equivalência dos 171 testes funcionais existentes;
- ausência de importações da fachada pelos módulos de runtime;
- limite de 300 linhas para contrato, projeção, serialização, snapshot e fachada;
- Ruff e Mypy.
