# ADR-058 — Modelo diário de POA e correção térmica

Status: aceito em 2026-08-02.

## Contexto

O Open-Meteo fornece ao Mplacas radiação solar diária global horizontal, persistida como
`irradiation_kwh_m2`. Esse valor é GHI e não representa a irradiância no plano inclinado dos módulos.
Usá-lo diretamente como base de Performance Ratio misturaria geometria, temperatura e desempenho do
sistema em uma única razão sem rastreabilidade.

Os dados disponíveis hoje são agregados diários: GHI e temperatura ambiente média. Não existem ainda
DNI, DHI, temperatura de módulo nem séries sub-horárias medidas na usina.

## Decisão

O motor puro `MPLACAS_POA_DAILY_ERBS_ISOTROPIC_V1` aplica:

1. geometria solar diária a partir de data e latitude;
2. decomposição de GHI em componentes direta e difusa pela correlação diária de Erbs;
3. integração numérica da incidência direta no plano, respeitando inclinação e azimute definidos no
   ADR-057;
4. transposição difusa isotrópica e reflexão do solo com albedo fixo de 0,20;
5. estimativa de temperatura de célula por NOCT de 45 °C e irradiância POA média durante o período
   diurno;
6. correção térmica com coeficiente por tecnologia: -0,40%/°C para silício monocristalino e `OTHER`,
   -0,41%/°C para policristalino e -0,30%/°C para filme fino, sempre em relação a 25 °C.

O resultado persiste em `daily_solar_model_results`, identificado por usina, data, fonte climática e
versão do modelo. O registro contém snapshot da latitude, orientação, tecnologia, entradas,
componentes estimadas, POA, temperatura, fator térmico, equivalente POA ajustado à temperatura,
premissas e flags de qualidade. Uma nova versão do
modelo cria uma nova identidade e não altera silenciosamente resultados históricos de outra versão.

A coleta climática calcula a projeção na mesma transação após persistir a observação. Configuração
técnica incompleta ou GHI ausente não gera valores artificiais: a projeção é ignorada com motivo
explícito. Temperatura ausente ainda permite POA, mas deixa temperatura de célula, fator e POA
corrigida como `NULL`, com flag `TEMPERATURE_UNAVAILABLE`.

## Limitações e consequências

- `poa_irradiation_kwh_m2` e `temperature_adjusted_poa_equivalent_kwh_m2` são estimativas modeladas, não
  medições de piranômetro.
- A temperatura média diária não é a temperatura ambiente média apenas durante horas solares; a flag
  `AMBIENT_DAILY_MEAN` torna essa limitação explícita.
- Erbs e céu isotrópico são adequados ao estágio diário atual, mas uma futura ingestão horária com
  DNI/DHI deverá ganhar nova versão, preferencialmente com Perez/Hay-Davies e temperatura medida.
- Este modelo não calcula nem se apresenta como Performance Ratio. SOL-03 adicionará energia medida,
  disponibilidade e contrato alinhado à IEC 61724-1 sem redefinir POA retroativamente.

## Referências técnicas

- Erbs, Klein e Duffie, *Estimation of the diffuse radiation fraction for hourly, daily and
  monthly-average global radiation*, Solar Energy 28(4), 1982,
  DOI `10.1016/0038-092X(82)90302-4`.
- Sandia PV Performance Modeling Collaborative, *Plane of Array Irradiance* e *Isotropic Sky
  Diffuse Model*: `https://pvpmc.sandia.gov/modeling-guide/1-weather-design-inputs/plane-of-array-poa-irradiance/`.
- NREL, *SAM Photovoltaic Model Technical Reference Update*, NREL/TP-6A20-67399, seção do modelo de
  temperatura NOCT: `https://www.nrel.gov/docs/fy18osti/67399.pdf`.
