# ADR-057 — Configuração técnica fotovoltaica da usina

Status: aceito em 2026-08-02.

## Contexto

O modelo anterior registrava somente `installed_power_kwp`. Isso era suficiente para regras simples
de produção específica, mas não para calcular irradiância no plano dos módulos, perdas térmicas,
clipping ou Performance Ratio com premissas auditáveis. Também não existia potência atribuída a cada
inversor.

## Decisão

`plants.installed_power_kwp` permanece como a potência DC nominal total instalada. A preservação do
nome evita uma migração destrutiva e mantém os consumidores atuais. A configuração passa a incluir:

- `ac_capacity_kw`: potência AC nominal total;
- `array_tilt_degrees`: inclinação em graus, de 0° a 90°;
- `array_azimuth_degrees`: azimute em graus, no intervalo `[0, 360)`, medido a partir do norte em
  sentido horário (`0° = norte`, `90° = leste`, `180° = sul`, `270° = oeste`);
- `module_technology`: tecnologia controlada (`MONOCRYSTALLINE_SILICON`,
  `POLYCRYSTALLINE_SILICON`, `THIN_FILM` ou `OTHER`);
- `commissioned_on`: data de comissionamento operacional;
- em cada `device`, `dc_capacity_kwp` representa a potência DC conectada ao inversor e
  `ac_capacity_kw` sua potência AC nominal.

Todos os campos são inicialmente anuláveis para permitir adoção gradual nas usinas existentes.
Quando presentes, capacidades devem ser positivas e os ângulos devem respeitar os intervalos acima;
essas invariantes existem tanto na API quanto em `CHECK constraints` do banco.

A API tenant-safe expõe `GET` e `PATCH /plants/{plant_id}/technical-configuration`. Atualizações da
usina e de seus inversores ocorrem na mesma transação. Um identificador de inversor ausente ou de
outra usina rejeita toda a operação sem persistência parcial. Leituras exigem papel READ e alterações
exigem ADMIN, preservando resposta 404 para recursos fora do tenant. Toda alteração aceita gera um
evento de auditoria `plant.technical_configuration_updated`.

## Consequências

- SOL-02 pode calcular POA e correção térmica sem confundir GHI com irradiância no plano.
- SOL-03 pode usar as potências DC/AC como entradas versionadas do cálculo de PR e clipping.
- Arranjos com múltiplas orientações ainda não são representados; quando necessários, deverão ganhar
  uma entidade de subarranjo, sem sobrecarregar os campos agregados definidos aqui.
- A soma das capacidades dos inversores não é forçada a coincidir com a capacidade total: cadastros
  podem ser graduais e existem topologias onde a atribuição DC exige informação por MPPT/subarranjo.
