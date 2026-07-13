# ADR-019 — Pipeline de coleta climática idempotente

## Status

Aceito para implementação incremental.

## Contexto

O motor de anomalias já utiliza irradiação, nebulosidade e precipitação quando esses dados estão disponíveis. Faltava uma forma operacional, auditável e independente de fornecedor para coletar observações climáticas e persistir revisões sem duplicar registros.

## Decisão

1. Cada usina poderá armazenar latitude e longitude opcionais.
2. A coleta somente será executada quando as duas coordenadas estiverem configuradas e dentro das faixas geográficas válidas.
3. O serviço dependerá do contrato `ClimateProvider`, sem acoplamento do domínio a uma API meteorológica específica.
4. A persistência usará a chave lógica `plant_id + observation_date + source`.
5. Reexecuções com os mesmos valores serão classificadas como `unchanged`.
6. Novos valores para a mesma chave atualizarão o registro existente, preservando a idempotência estrutural.
7. O serviço validará o intervalo solicitado e recusará observações retornadas fora dele.
8. Credenciais, coordenadas reais do usuário e payloads externos não serão incluídos no repositório ou nos testes.

## Consequências

- o motor de anomalias passa a ter um pipeline de alimentação climática reutilizável;
- provedores meteorológicos poderão ser substituídos sem alterar o serviço de persistência;
- backfills podem ser repetidos com segurança;
- a próxima etapa deve adicionar um adaptador HTTP concreto, endpoint protegido e agendamento operacional;
- coordenadas são dados operacionais e devem ser tratadas como configuração protegida em produção.
