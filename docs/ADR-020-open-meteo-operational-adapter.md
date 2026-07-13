# ADR-020 — Adaptador operacional Open-Meteo

## Contexto

O Mplacas já possui contrato de provedor climático, persistência idempotente e motor determinístico de anomalias. Faltava um adaptador HTTP concreto e uma execução operacional protegida.

## Decisão

Utilizar a Historical Weather API do Open-Meteo como primeiro adaptador concreto, mantendo o domínio dependente apenas do protocolo `ClimateProvider`.

O adaptador solicita agregações diárias de radiação solar, nebulosidade e precipitação. A radiação diária recebida em MJ/m² é convertida para kWh/m² por divisão por 3,6 antes da persistência.

A execução será exposta em `POST /climate/collect`, protegida pela credencial operacional já existente. O endpoint não aceita coordenadas diretamente: elas são recuperadas do cadastro da usina para reduzir associação incorreta e exposição desnecessária.

## Controles

- timeout configurável;
- URL-base configurável externamente;
- limite máximo de backfill;
- validação de unidade e alinhamento dos arrays diários;
- erros externos convertidos em resposta 502 sanitizada;
- nenhuma chave, coordenada real ou payload privado no repositório;
- persistência continua idempotente pela chave usina, data e fonte.

## Consequências

O motor de anomalias passa a poder receber contexto climático real sem acoplamento permanente ao fornecedor. Novos provedores poderão implementar o mesmo contrato sem alteração dos serviços de domínio.
