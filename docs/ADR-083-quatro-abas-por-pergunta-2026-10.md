# ADR-083 — Quatro abas, uma pergunta cada: Início, Energia, Dinheiro e Minha usina

## Status

**Aceito — 2026-10-23.** Proposta aprovada pelo dono do produto a partir da maquete
"MPlacas — nova organização" (Início, Energia e Dinheiro no celular). Entregue em três
etapas: (1) navegação + aba Início, (2) aba Dinheiro reorganizada, (3) aba Energia
reorganizada (Produção + Técnico). Este registro cobre a etapa 1 e fixa as regras das
outras duas.

## Contexto

Depois do ADR-077 o visual ficou limpo, mas o dono avaliou o produto em 6/10 e relatou
ficar "desorientado". A revisão dos cinco módulos em produção (celular, dados reais)
mostrou que o problema era de organização, não de cor:

| Achado | Onde |
|---|---|
| "1 dia sem leitura" repetido seis vezes (faixa de confiança, banner, chip, decisão, plano, diagnósticos) | Visão Geral |
| Painel de decisão genérico: "Diretriz", "Próximo check", "Responsável sugerido: Operação", plano de 3 passos | Visão Geral, Financeiro |
| "Executar backfill hoje" para uma lacuna que o provedor nunca vai recuperar | Visão Geral |
| "Esperado indisponível" em seis lugares; "3 dias abaixo da média" e "0 dias abaixo" na mesma tela | Produção |
| Perda normal por calor (7%) tratada como "Agir hoje"; textos em inglês do motor vazando | Técnico |
| A tela abre pela importação de PDF; a economia de R$ 612 aparece três vezes | Financeiro |

A base de conhecimento da skill `ui-ux-pro-max` (instalada no PR #211) aponta o mesmo
para produtos de energia: transparência de dado, "clareza acima de estética" e nada de
alarme sem lastro.

## Decisão

1. **Quatro abas, cada uma responde uma pergunta do dono**, em `routes.ts`:
   - `inicio` — "Está tudo bem?";
   - `energia` — "Quanto gerou e para onde foi?" (inclui `energia/tecnico`, os
     detalhes técnicos, sem item próprio no menu; "Energia" fica ativa ali);
   - `dinheiro` — "Quanto ganhei?";
   - `minha-usina` — "Meus dados".
2. **URLs antigas redirecionam** (`visao-geral`, `producao`, `financeiro`, `tecnico`),
   preservando `?plant=` — favoritos e links de relatório continuam funcionando.
3. **Início em quatro blocos**, nesta ordem:
   1. uma frase de situação (`buildHomeStatus`);
   2. a economia do último ciclo com fatura, a conta com e sem a usina e quanto do
      investimento já voltou;
   3. a produção medida dos últimos 7 dias;
   4. "Precisa de você" (`buildHomeTodos`).
   Diagnósticos completos e a evolução do ciclo ficam recolhidos num `<details>` no fim.
4. **Alerta só quando o dono precisa agir.**
   - A frase de situação considera só duas coisas: telemetria parada há 3 dias ou mais
     (o mais comum é falta de internet no equipamento) e o gatilho de produção já
     existente (`productionAlertSignal`).
   - "Precisa de você" lista só:
     - cadastro incompleto;
     - faturas aguardando conferência;
     - diagnóstico que o motor classificou como `CRITICAL`, exceto lacuna de telemetria
       (`MISSING_DAILY_DATA`, cuja ação "executar backfill" é de operação, não do dono).
       A tarefa abre a lista completa de diagnósticos, recolhida no próprio Início.
   - Lacuna num ciclo fechado é explicada uma vez (`buildCalmNote`), sem pedir ação e
     **sem esconder o efeito**: a economia usa a produção do inversor (autoconsumo =
     produção − injetado, `energy_engine.py`), então dia sem leitura deixa produção e
     economia abaixo do real. O selo do cartão vira "Estimado · ciclo parcial".
   - "Nada pendente." só quando o cadastro foi lido; falha ao ler diz que não conseguiu
     conferir (indisponível nunca é zero).
   - Histórico diário com erro ou 404 (nenhuma produção em 90 dias) vira frase de
     situação explícita, nunca some.
   - O cartão de 7 dias usa dias de **calendário** até a última leitura: o backend omite
     da série os dias sem leitura, então dia ausente aparece como lacuna e o total diz
     quantos dias somou.
5. **Fluxo de energia vai para a aba Energia** (`EnergyDestinationSection`), com uma frase
   que só repete os percentuais do motor.
6. **Saem** `HeroCard`, `AttentionSummary`, `QualityBanner`, `DataConfidenceStrip`,
   `OverviewKpiRail` e `ExecutiveDecisionPanel`. Eles existiam só para a Visão Geral e
   repetiam números já mostrados.
7. **Regras para as etapas 2 e 3:**
   - cada número aparece uma vez por tela;
   - indisponibilidade dita uma vez, em português;
   - nada de painel de decisão genérico;
   - texto técnico do motor nunca aparece em inglês para o cliente.

## Etapa 2 — aba Dinheiro (2026-10-24)

Ordem nova: **Retorno do investimento → Sua conta com e sem a usina → Detalhes da fatura
(recolhido) → Usina × CDI → Faturas**.

- **Saem**:
  - a faixa "Resumo financeiro", que repetia economia, ROI, payback e cobertura;
  - o painel genérico "Decisão financeira" (`FinancialDecisionPanel`);
  - os blocos "Custo do ciclo" e "Créditos de energia" (`EstimatedSavingsCard`,
    `MetricStrip`, `CurrencyCard`).
- **"Pago com créditos"** entra na conta do ciclo: o percentual do motor
  (`credit_coverage_rate_percent`, 1 casa) e os kWh compensados de kWh da rede. Abaixo de
  100%, diz que o restante foi cobrado sem crédito. O texto é neutro de propósito: em
  faturas antigas, o restante é o mínimo faturável. Explica uma fatura alta como a de
  out/26: 338 kWh da rede, 256 compensados, 82 sem crédito. Sem energia da rede no ciclo,
  a linha não aparece.
- **Detalhes da fatura**, recolhidos:
  - a decomposição do valor ("Energia e encargos" + iluminação pública);
  - a "Tarifa impressa na fatura", com 3 casas;
  - uma nota que diz o que a conta "sem a usina" usou, segundo o motor
    (`savings_tariff_source`). Não afirma de qual linha veio a tarifa, porque isso depende
    do layout da fatura e o backend não informa.
  Antes, as duas tarifas da fatura apareciam com 6 casas ao lado da tarifa cheia usada
  no "sem a usina", sem explicação, o que parecia erro. A conferência de fatura pendente
  mantém as 6 casas, porque ali o valor precisa bater com o impresso.
- **Economia sem conta "sem a usina"** (sem tarifa no ciclo, ou backend anterior ao
  ADR-080) não some nem vira R$ 0,00: aparece a mensagem do motivo ou só o valor
  estimado, com o saldo de créditos e a cobertura junto.
- **Faturas sempre no fim, num único ponto de montagem.** A primeira versão as movia
  (topo sem ciclo, fim com ciclo), e a troca remontava a seção: perdiam-se o retorno da
  importação, a lista de PDFs recusados e o foco. Para uma usina sem ciclo não há perda,
  porque acima delas só ficam o cabeçalho e o aviso.
- "Conferir faturas" no Início leva a `/dashboard/dinheiro#faturas`, que rola até elas
  uma vez, quando já estão na tela.

## Consequências

- A aba Início faz quatro leituras (executivo, produção diária, retorno, cadastro).
  Falha das duas últimas não derruba a tela, só omite a parte correspondente.
- O módulo Energia faz uma leitura a mais (executivo). O chunk ficou em 14,56 kB de
  15 kB; a etapa 3 precisa reduzir ou dividir.
- Nenhuma mudança em dados, cálculos, contratos de API, autenticação ou permissões.
- Dívida conhecida, para a etapa 3: `productionAlertSignal` (compartilhado com Energia)
  compara as 7 últimas ENTRADAS com as 7 anteriores, não 7 dias de calendário. Com lacunas,
  a janela fica mais longa que 7 dias. Não inverte o sinal, mas precisa ser alinhado ao
  contrato real.
- Aceitos como estão (P4 da revisão): `daysBetween` usa o dia local do navegador (sem
  efeito para usuários no Brasil); `aria-current="page"` em Energia também na subpágina
  técnica.
- Validação:
  - testes de regra (`home.test.ts`), de página (`OverviewPage.test.tsx`), de navegação
    e de redirecionamento;
  - capturas `e2e/screenshots.spec.ts` (desktop e celular) e guarda de rolagem lateral
    (`overflow.spec.ts`), incluindo a subpágina técnica.
