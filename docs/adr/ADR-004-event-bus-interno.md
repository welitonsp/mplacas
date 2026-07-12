# ADR-004 — Event Bus interno

## Estado

Aceito.

## Contexto

Coleta, qualidade, indicadores, anomalias, relatórios e notificações evoluirão em ritmos diferentes. Acoplamento direto entre esses módulos aumentaria o risco de regressões e dificultaria testes.

## Decisão

Adotar um barramento de eventos assíncrono em processo, com eventos tipados e handlers explícitos. Nesta fase não haverá broker externo.

## Consequências

- módulos podem reagir a eventos sem conhecer o produtor;
- testes permanecem rápidos e determinísticos;
- falhas de um handler devem ser observáveis;
- broker distribuído só será considerado quando volume ou disponibilidade justificarem.
