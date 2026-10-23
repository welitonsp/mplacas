---
name: solar-pv-brazil-overlay
description: Use para projetos de energia solar fotovoltaica no Brasil que exijam conformidade com normas ABNT (NBR 16690, NBR 5410, NBR 5419, NBR 6123), regulamentação ANEEL (REN 1000/2021, Lei 14.300/2022) e certificação INMETRO (NBR 16149/16150). Ativa quando o usuário mencionar NBR, ANEEL, INMETRO, concessionária brasileira, INMET ou projeto FV no Brasil.
license: MIT
metadata:
  author: equipe-solar-br
  version: "1.0.0"
  maturity: stable
  spec: 2
allowed-tools: []
---

# Solar PV Brazil Overlay — Conformidade Normativa Brasileira

## Identity

Esta skill **não substitui** a skill `solar-photovoltaic-installer`. Ela é uma **camada de compatibilidade normativa** para o mercado brasileiro. Quando ativada, sua função é garantir que todo raciocínio técnico produzido pela skill base (física, dimensionamento, heurísticas) seja **remapeado** para a regulamentação brasileira aplicável, e que nenhuma exigência americana (NEC) seja citada como se fosse obrigatória no Brasil.

## Regra de Ouro (Non-negotiable)

> **Nenhuma referência à NEC (National Electrical Code) deve ser aceita como fonte normativa para um projeto no Brasil.** Toda menção à NEC deve ser traduzida para a norma ABNT/ANEEL/INMETRO equivalente. Se não houver equivalente direto, o agente deve declarar explicitamente: "Esta exigência não tem equivalente obrigatório no Brasil; verificar IT do Corpo de Bombeiros estadual e padrão da distribuidora local."

## Mapa de Remapeamento Normativo

Sempre que a skill base citar uma norma americana, aplique a tradução da tabela abaixo. O detalhamento completo está em `references/norm-map.md`.

| Referência na skill base (EUA) | Equivalente brasileiro | Observação crítica |
|---|---|---|
| NEC 690.7 (Voc a frio) | **ABNT NBR 16690** (dimensionamento de string) | Usar temperatura mínima do **INMET** por município, não ASHRAE |
| NEC 690.12 (rapid shutdown) | **Sem equivalente obrigatório universal** | Verificar IT do CBM estadual e padrão da distribuidora |
| NEC 705.12(B)(3)(c) (120%) | **NBR 16690** + **padrão da concessionária** | Cada distribuidora tem regra própria de conexão |
| ASCE 7 (wind uplift) | **ABNT NBR 6123** (forças devidas ao vento) | Pull-out capacity segue o fabricante + NBR 6123 |
| UL 1741 (inversor) | **Portaria Inmetro nº 140/2022** (substituiu a 004/2011) + **NBR 16149/16150** | Certificação obrigatória para comercialização no Brasil |
| IEEE 1547 (conexão à rede) | **ANEEL REN 1000/2021** + **Lei 14.300/2022** | Marco legal da GD; procedimento de acesso no PRODIST |
| NEC 690 (instalação geral) | **ABNT NBR 5410** (BT) + **NBR 16690** | |
| NFPA 780 (SPDA — fora do NEC; o NEC só trata aterramento, Art. 250/690.47) | **ABNT NBR 5419** | Proteção contra descargas atmosféricas |

## Fluxo de Trabalho Obrigatório

Sempre que esta skill for ativada, siga esta ordem:

1.  **Identifique a norma citada** pela skill base ou pelo usuário. Se for NEC, aplique o remapeamento acima.
2.  **Carregue a referência específica** em `references/` conforme o tema:
    - Dimensionamento de string → `references/string-sizing-br.md`
    - Mapa normativo completo → `references/norm-map.md`
    - Conexão à rede / ANEEL e checklist de conformidade → ainda não escritos (`interconnection-br.md` e `checklists-br.md` não vieram no pacote); use a seção 3 de `norm-map.md`
3.  **Verifique a fonte da temperatura mínima**: use dados do **INMET** (normais climatológicas) para o município do projeto, não valores genéricos.
4.  **Confirme o enquadramento ANEEL**: microgeração (≤ 75 kW) ou minigeração (75 kW a 5 MW, conforme REN 1000/2021).
5.  **Sinalize lacunas**: se uma exigência americana não tiver equivalente brasileiro, declare a lacuna e indique quem deve ser consultado (CBM estadual, distribuidora, engenheiro responsável).
6.  **Emita o resultado com ressalva profissional**: "Este parecer é apoio técnico. O projeto final deve ser assinado por engenheiro responsável com ART."

## Heurísticas Brasileiras

- **Temperatura mínima de projeto**: no Brasil, a maioria dos municípios tem mínimas entre 5 °C e 15 °C (INMET). Não use valores genéricos ou de clima americano; use o dado municipal.
- **Rapid shutdown**: não presuma que MLPE é obrigatório no Brasil. Verifique a IT do CBM do estado e o padrão da distribuidora. Em muitos casos, não há exigência de desenergização module-level.
- **Interconexão**: a regra dos 120% da NEC não se aplica diretamente. O limite é definido pela **NBR 16690** em conjunto com o **padrão de conexão da distribuidora** (cada uma tem seu formulário e seus critérios).
- **Certificação de inversor**: no Brasil, o inversor **precisa** de certificação Inmetro (Portaria nº 140/2022, que substituiu a 004/2011) e conformidade com **NBR 16149/16150**. Não aceite inversor sem registro no INMETRO.
- **SPDA**: a NBR 5419 é obrigatória para a proteção do arranjo FV contra descargas atmosféricas, em conjunto com a NBR 16690.

## Limitações Explícitas

| Esta skill **é** | Esta skill **não é** |
|---|---|
| Camada de conformidade normativa brasileira | Substituto da skill base (que fornece a física e o julgamento) |
| Baseada em ABNT, ANEEL, INMETRO, INMET | Norma aplicável sem revisão de engenheiro responsável |
| Atualizada para REN 1000/2021 e Lei 14.300/2022 | Consultoria jurídica ou parecer de engenharia |
## Uso no Mplacas

O Mplacas monitora e audita usinas; não projeta instalações. Esta skill entra como apoio
consultivo (ex.: o `solar-domain-specialist` explicar por que um arranjo pode ter limitação
ao interpretar telemetria). A UI nunca afirma conformidade normativa nem substitui a ART do
engenheiro responsável.
