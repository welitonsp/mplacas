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
     - diagnóstico que o motor classificou como `CRITICAL`.
   - Lacuna num ciclo fechado é explicada uma vez (`buildCalmNote`), sem pedir ação.
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

## Consequências

- A aba Início faz quatro leituras (executivo, produção diária, retorno, cadastro).
  Falha das duas últimas não derruba a tela, só omite a parte correspondente.
- O módulo Energia faz uma leitura a mais (executivo). O chunk ficou em 14,56 kB de
  15 kB; a etapa 3 precisa reduzir ou dividir.
- Nenhuma mudança em dados, cálculos, contratos de API, autenticação ou permissões.
- Validação:
  - testes de regra (`home.test.ts`), de página (`OverviewPage.test.tsx`), de navegação
    e de redirecionamento;
  - capturas `e2e/screenshots.spec.ts` (desktop e celular) e guarda de rolagem lateral
    (`overflow.spec.ts`), incluindo a subpágina técnica.
