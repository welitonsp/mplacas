# ADR-059 — Performance Ratio e disponibilidade observável

Status: aceito em 2026-08-02.

## Contexto

A IEC 61724-1:2021 define terminologia e métodos para monitoramento de desempenho fotovoltaico. O
Mplacas agora possui energia AC diária por inversor, potência DC STC cadastrada e POA modelada e
versionada, suficientes para calcular yields e Performance Ratio diário. Contudo, ainda não coleta
estados operacionais intervalares, eventos de rede, exclusões contratuais nem categorias de tempo
necessárias para declarar disponibilidade técnica da planta.

## Decisão

O modelo `MPLACAS_IEC61724_DAILY_PR_V1` calcula:

- yield final `Yf = energia AC medida / potência DC STC`, em `kWh/kWp`;
- yield de referência `Yr = POA / 1 kW/m²`, em horas;
- PR AC diário `PR = Yf / Yr`, adimensional;
- PR corrigido por temperatura, separadamente, usando o equivalente POA ajustado à temperatura do
  ADR-058. O PR padrão nunca é silenciosamente substituído pelo corrigido.

A natureza do PR é persistida como `IEC_61724_STYLE_AC_PR_MODELED_POA`: a fórmula segue o contrato
de yields usado pela IEC, mas a POA é modelada a partir de GHI diário, não medida por piranômetro ou
célula de referência. Fonte climática, versões dos modelos solar e de desempenho, fronteira de
energia, unidades, entradas e flags de qualidade acompanham cada resultado.

Enquanto não houver telemetria de estado por intervalo, o sistema calcula apenas
`CAPACITY_WEIGHTED_DAILY_REPORTING_PROXY`: capacidade DC dos inversores com registro diário válido
dividida pela capacidade DC total configurada nos inversores. Ausência de potência por inversor torna
o indicador `NULL`; não há fallback por contagem que misture inversores de tamanhos diferentes. Esse
proxy mede cobertura de reporte, não disponibilidade técnica, energética ou contratual.

Resultados com energia incompleta ou provisória continuam calculáveis para observabilidade, mas são
marcados `INCOMPLETE` ou `PROVISIONAL`. A incerteza numérica permanece `NULL` com natureza
`NOT_QUANTIFIED_SENSOR_CLASSES_UNAVAILABLE`, pois inventar uma porcentagem sem classe/metrologia dos
sensores seria falsa precisão.

## Persistência e operação

`daily_pv_performance_results` é identificado por usina, data, versão solar e versão de desempenho.
O pipeline diário recalcula o resultado idempotentemente depois da coleta/POA e antes da avaliação de
alertas. Ausência de potência DC, POA ou energia gera `skipped` com motivo observável. A série segue a
mesma janela de retenção de clima/POA.

## Limitações e próxima evolução

- O modelo não certifica conformidade de classe de monitoramento IEC 61724-1; faltam inventário e
  incerteza dos sensores, aquisição intervalar e controle de qualidade metrológico.
- Disponibilidade técnica deve ser implementada sobre categorias temporais de estado e exclusões
  acordadas, seguindo a estrutura da IEC TS 63019, sem reinterpretar o proxy diário.
- Múltiplas fontes POA para a mesma data são rejeitadas como ambíguas até existir uma política
  explícita de precedência.
- SOL-04 poderá usar PR com qualidade final como série de baseline, sem permitir contaminação por
  dias incompletos ou indisponíveis.

## Referências

- IEC, `IEC 61724-1:2021 — Photovoltaic system performance — Part 1: Monitoring`:
  `https://webstore.iec.ch/en/publication/65561`.
- Marion et al., *Performance Parameters for Grid-Connected PV Systems*, NREL/CP-520-37358:
  `https://docs.nrel.gov/docs/fy05osti/37358.pdf`.
- Sandia PVPMC, *Performance Ratio*:
  `https://pvpmc.sandia.gov/modeling-guide/5-ac-system-output/pv-performance-metrics/performance-ratio/`.
- IEC, `IEC TS 63019:2019 — Information model for availability`:
  `https://webstore.iec.ch/en/publication/27253`.
