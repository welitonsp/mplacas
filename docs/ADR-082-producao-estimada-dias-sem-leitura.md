# ADR-082 — Produção estimada para dias sem leitura do inversor

- **Status:** aceito
- **Data:** 2026-10-23
- **Relacionados:** ADR-078 (injeção real), ADR-080 (tarifa cheia), ADR-081 (recálculo como
  revisão)

## Contexto

Quando as placas ficam sem internet, os microinversores continuam gerando, mas a NEPViewer
não registra o dia e nunca vai registrar. Na usina de referência, mesmo depois de buscar
todo o histórico desde ago/2024, sobraram estes buracos:

| Mês | Dias sem leitura |
|---|---|
| set/2025 | 26 |
| mai/2026 | 15 |
| jun/2025 | 9 |
| ago/2025 | 8 |

Sem produção nesses dias, o autoconsumo e a economia saem subestimados. Em set/2025 o
inversor registrou 129 kWh, enquanto o medidor da Equatorial registrou 429 kWh injetados:
o autoconsumo virava zero.

## Decisão

1. **Sol do dia × rendimento da própria usina.** Para cada dia sem leitura:

   produção estimada = irradiação diária (Open-Meteo) × mediana do rendimento
   (kWh ÷ kWh/m²) dos dias medidos no ciclo e 30 dias de cada lado.

   - São necessários pelo menos 5 dias de referência, só de dias inteiramente
     consolidados. Dias provisórios ou incompletos puxariam o rendimento para baixo.
   - Dia sem sol conhecido, ou com sol zero, não é estimado.
   - A própria usina se mede: sujeira, sombra e perdas já estão no rendimento.
2. **Piso pelo medidor, só em ciclo com dia sem leitura.** A produção do ciclo nunca fica
   abaixo do `generation_cycle_kwh` da fatura, porque o que foi injetado foi produzido.
   - Num ciclo completo, produção abaixo do medidor é divergência a mostrar (inversor
     subnotificando, recorte de datas), não algo a esconder. O piso sozinho não conta como "dia
   com produção": sem nenhum dia medido ou estimado, a economia continua indisponível
   (`NO_PRODUCTION_DATA`).
3. **Transparência.**
   - O relatório mensal ganha as métricas de qualidade `estimated_production_days`,
     `estimated_production_kwh` e `meter_floor_kwh`, de natureza `ESTIMATED`.
   - A tela de Produção mostra "N dias sem dado, estimados pelo sol".
   - Nenhum valor estimado aparece como medido.
4. **Recálculo.** O "Meses a recalcular" ganha a causa `PARTIAL_PRODUCTION`: um ciclo com
   dias sem leitura, calculado antes desta decisão.
   - A nova revisão só é gravada quando o recálculo tem economia **e** a estimativa de fato
     aconteceu, ou o buraco foi preenchido.
   - Sem clima carregado, o mês continua na lista, em vez de sair dela com "estimados: 0".
5. **Histórico de sol.** O comando `collect-climate` e o workflow `climate-history`, com
   confirmação `CLIMA`, buscam a irradiação diária do Open-Meteo em blocos de até 366 dias
   por usina. Nenhum dos dois gera alerta.

## Consequências

- Os meses com buracos passam a ter economia mais próxima da real, sempre marcada como
  estimada.
- A estimativa depende do clima histórico. Antes de recalcular, é preciso rodar o
  `climate-history` para o período.
- A janela de referência é de 30 dias: num mês inteiro sem leitura, o rendimento vem dos
  meses vizinhos, o que funciona para variação sazonal suave.
- **Dia parcial não é estimado.** Num dia em que só um dos microinversores reportou, a
  produção medida soma só os que reportaram. É uma subestimação que não aparece em
  `estimated_*`. Fica como limitação conhecida.
- **Desempenho contra o esperado.** O desempenho contra o esperado (ADR-057/060) passa a
  ver a produção com estimativa e piso. Um ciclo ruim com buracos pode parecer melhor do
  que foi. A qualidade do ciclo continua mostrando os dias sem leitura.
- **Descartado: estimar pela média dos outros dias do mês.** Ignora que dia nublado gera
  menos. O sol do próprio dia é o melhor preditor disponível.
