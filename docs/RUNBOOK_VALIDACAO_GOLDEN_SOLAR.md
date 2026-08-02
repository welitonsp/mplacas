# Runbook — validação de datasets golden solares

## Objetivo

Converter casos reais já autorizados em evidência anônima, obter revisão de especialista solar e ativar
o gate de falso positivo/falso negativo sem expor cliente, usina, conta ou equipamento.

## Estado atual

- Contrato: `MPLACAS_SOLAR_GOLDEN_V1`.
- Candidato: `tests/golden/solar_loss_taxonomy_candidates_v1.json`.
- Revisão: `PENDING`; casos exclusivamente sintéticos.
- SOL-06 não pode ser encerrada com esse arquivo.

## Procedimento para outra IA

1. Obter autorização explícita para usar uma amostra de campo e uma referência controlada para o
   registro da revisão. Não copiar arquivos brutos para o repositório.
2. Remover nomes de cliente/usina/organização, seriais, contas, endereço, latitude/longitude e qualquer
   identificador indireto. Usar IDs opacos novos, sem hash de identificador real.
3. Criar um novo arquivo `tests/golden/solar_loss_taxonomy_anonymized_field_vN.json`; não alterar o
   candidato sintético para fingir proveniência de campo.
4. Para cada caso, preencher todas as oito categorias com `POSITIVE`, `NEGATIVE` ou
   `NOT_ASSESSABLE`. Divergências entre revisores devem ser resolvidas fora do código e registradas na
   referência de evidência.
5. Somente após revisão real, definir `expert_review.status=APPROVED`, papel do revisor, instante com
   timezone e `evidence_ref` não sensível. O revisor não precisa ser identificado nominalmente no Git.
6. Manter ao menos cinco positivos e cinco negativos por categoria. Para `SHADING` e outras categorias
   hoje não avaliáveis, o gate só será possível depois de disponibilizar a telemetria exigida pela
   ADR-061; não relabelar ausência de dados como negativo.
7. Executar:

   ```powershell
   .venv\Scripts\python.exe scripts/evaluate-solar-golden.py `
     tests/golden/solar_loss_taxonomy_anonymized_field_vN.json
   .venv\Scripts\python.exe -m pytest -q tests/test_golden_solar_validation.py
   .venv\Scripts\python.exe -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning
   ```

   O avaliador retorna código 0 somente quando o gate está aprovado e imprime as métricas em JSON.

8. Revisar no relatório por categoria: precisão, recall, cobertura, FPR e FNR. Não reduzir thresholds
   para fazer o dataset passar; corrigir regra, label ou qualidade dos dados com justificativa.
9. Atualizar `docs/CHECKLIST_REMEDIACAO_AUDITORIA.md` com o ID/versionamento do dataset, referência da
   revisão, quantidade de casos e métricas observadas. Só então mudar SOL-06 de parcial para concluída.

## Critérios de bloqueio

Interromper a incorporação se houver identificadores diretos, origem não autorizada, label sem revisão,
revisor sem competência solar, amostra desbalanceada ou tentativa de promover caso sintético como real.
