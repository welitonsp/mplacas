# ADR-060 — Baseline sazonal robusta e degradação de longo prazo

Status: Aceito — 2026-08-02

## Contexto

PR diário isolado é ruidoso e não distingue variação meteorológica, qualidade de dados e mudança
persistente de desempenho. Uma média móvel também pode absorver lentamente a própria degradação e
passar a tratá-la como normal (*baseline contamination*).

## Decisão

O modelo `MPLACAS_SEASONAL_PR_BASELINE_V1` adota:

- estação definida por mês civil, sem misturar períodos sazonais distintos;
- janela de referência congelada nos primeiros 366 dias a partir da primeira observação elegível;
- PR corrigido por temperatura quando disponível, com fallback explícito para PR padrão;
- somente dados `FINAL`, disponibilidade reportada mínima de 95% e PR fisicamente admissível;
- envoltória empírica de céu limpo pelo P90 sazonal de POA e índice diário `POA/P90`;
- exclusão de dias com índice abaixo de 0,65 ou acima de 1,25;
- rejeição robusta por mediana, MAD escalada e quantis quando MAD é zero;
- comparação formada exclusivamente por dados posteriores à janela congelada;
- mínimo de 12 amostras de referência e 7 de comparação;
- persistência versionada e idempotente dos limites, contagens, premissas e flags usados.

O resultado compara a mediana robusta do período atual com a referência e classifica a variação em
`STABLE`, `WATCH` (queda a partir de 3%) ou `DEGRADED` (queda a partir de 5%). A taxa anualizada só é
calculada com separação mínima de 180 dias entre os pontos centrais das coortes.

## Proteção contra contaminação

Registros futuros são ignorados. Dados posteriores ao fim do primeiro ano nunca entram novamente na
referência, mesmo quando a queda persiste por meses. Dias provisórios, baixa disponibilidade, baixa
irradiância e outliers também não alteram a baseline. Reprocessamentos podem atualizar o snapshot do
mesmo dia, mas não mudam as regras nem misturam versões do modelo de PR.

## Limitações

O P90 de POA é uma envoltória empírica, não um modelo físico de céu limpo com turbidez atmosférica.
Plantas com menos de um ano ou poucos dias elegíveis retornam `skipped`, sem estimativa inventada.
Intervenções, repotenciação e troca de módulos exigirão no futuro um mecanismo explícito de nova época
de referência; não devem ser absorvidas silenciosamente pelo modelo atual.

## Consequências

A série passa a suportar triagem conservadora de degradação de longo prazo, com rastreabilidade dos
dados aceitos/excluídos. SOL-05 poderá consumir `degradation_status`, mas não deve atribuir causa técnica
sem evidências adicionais.
