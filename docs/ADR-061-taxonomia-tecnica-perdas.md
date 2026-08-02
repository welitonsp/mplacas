# ADR-061 — Taxonomia técnica de perdas com níveis de evidência

Status: Aceito — 2026-08-02

## Contexto

Quedas de produção podem decorrer de comunicação, indisponibilidade, clipping, sujeira, sombra,
temperatura ou degradação. Os dados atuais combinam energia diária, POA diária modelada, PR,
disponibilidade de reporte, clima diário e baseline sazonal. Eles não incluem potência intervalar,
estados operacionais do inversor, eventos de limpeza ou sensores de sujeira.

Uma classificação que trate indícios diários como causa confirmada produziria falsa precisão e ações
operacionais erradas.

## Decisão

O modelo `MPLACAS_DAILY_LOSS_TAXONOMY_V1` sempre gera uma avaliação independente para:

- `COMMUNICATION`;
- `UNAVAILABILITY`;
- `CLIPPING`;
- `SOILING`;
- `SHADING`;
- `TEMPERATURE`;
- `DEGRADATION`;
- `UNEXPLAINED`.

Cada resultado possui um dos níveis `LIKELY`, `POSSIBLE`, `NOT_DETECTED` ou `NOT_ASSESSABLE`, além de
códigos de evidência, limitação e perda estimada somente quando a grandeza é defensável.

## Regras principais

- falha de reporte por dispositivo é comunicação provável, não indisponibilidade técnica;
- energia zero com reporte completo e POA material é indício provável de indisponibilidade, ainda sem
  confirmação por estado intervalar;
- clipping é apenas possível quando razão DC/AC e índice de céu limpo são altos; confirmação exige
  platô de potência intervalar;
- sujeira é apenas possível quando coexistem período seco prolongado e queda contra baseline;
- sombra fica `NOT_ASSESSABLE` sem perfil intervalar e geometria temporal de incidência;
- temperatura compara PR padrão e PR corrigido, preservando a limitação do modelo NOCT diário;
- degradação consome exclusivamente a baseline sazonal congelada da SOL-04;
- queda material sem causa provável recebe `UNEXPLAINED`, em vez de atribuição arbitrária.

## Persistência e operação

Uma linha versionada por planta, dia, categoria e versão guarda a decisão. O pipeline passa a executar
POA → PR → baseline sazonal → taxonomia de perdas → alertas. Categorias não avaliáveis também são
persistidas para diferenciar ausência de sinal de ausência de dados.

## Consequências e próximos dados necessários

A taxonomia já suporta triagem e relatórios auditáveis, mas não substitui diagnóstico de campo. Para
elevar clipping, sombra e indisponibilidade a alta confiança serão necessários potência e estados em
intervalos de 5–15 minutos. Sensores de sujeira ou registros de limpeza são necessários para confirmar
soiling. SOL-06 deverá validar thresholds e falsos positivos/negativos em datasets revisados por
especialista.
