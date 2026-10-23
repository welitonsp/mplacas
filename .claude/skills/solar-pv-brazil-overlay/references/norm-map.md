# Mapa Normativo Detalhado — NEC → Brasil

> Apoio técnico, não parecer. O projeto final é assinado por engenheiro responsável com ART.

## 1. Dimensionamento de string (Voc a frio)

- **NEC 690.7** → **ABNT NBR 16690:2019**, seção de dimensionamento elétrico.
- A NBR 16690 exige que a tensão de circuito aberto (Voc) da string, corrigida para a
  **temperatura mínima do local**, não exceda a tensão máxima de entrada do inversor.
- **Fonte da temperatura mínima**: Normais Climatológicas do **INMET** (mínima absoluta ou
  mínima média do mês mais frio, conforme critério do projetista).
- **Coeficiente de temperatura**: usar o valor publicado pelo fabricante do módulo
  (βVoc, em %/°C), não a tabela genérica da NEC.
- Fórmula e exemplo: `string-sizing-br.md`.

## 2. Desligamento rápido (NEC 690.12, "rapid shutdown")

- **Não há equivalente obrigatório universal na NBR 16690.**
- A exigência pode existir em **Instruções Técnicas do Corpo de Bombeiros Militar (CBM)** de
  alguns estados (ex.: IT do CBPMESP; NTCB 49/2024 em MT).
- Também pode ser exigida pelo **padrão de conexão** de distribuidoras específicas.
- **Ação**: verificar a IT do CBM do estado do projeto e o padrão da distribuidora antes de
  especificar MLPE (otimizadores ou microinversores).

## 3. Interconexão (NEC 705.12)

- A **NBR 16690** estabelece os critérios de proteção e conexão.
- A **REN ANEEL nº 1.000/2021** regulamenta o acesso à rede de distribuição para micro e
  minigeração distribuída; a **Lei nº 14.300/2022** é o marco legal da GD.
- **Microgeração**: potência instalada ≤ 75 kW.
- **Minigeração**: potência instalada > 75 kW e ≤ 5 MW (fontes despacháveis) ou ≤ 3 MW
  (fontes não despacháveis, como a solar, conforme regulamentação vigente).
- Cada distribuidora tem seu **padrão de conexão** e seu **formulário de solicitação de
  acesso**. A regra dos 120% da NEC **não se aplica diretamente**; vale a NBR 16690 + o
  padrão local.

## 4. Inversores (UL 1741 → Inmetro)

- **Certificação obrigatória**: Portaria Inmetro nº 140/2022 (substituiu a Portaria
  004/2011 para equipamentos de sistemas fotovoltaicos).
- **Normas de conformidade**: ABNT NBR 16149:2013 (interface com a rede) e
  ABNT NBR 16150:2013 (procedimento de ensaio).
- **Não aceitar** inversor sem registro Inmetro válido.

## 5. Instalação elétrica (NEC 690 → NBR 5410)

- **ABNT NBR 5410** rege as instalações de baixa tensão, incluindo a parte CA do sistema FV.
- **ABNT NBR 16690** complementa com requisitos específicos para o arranjo FV (CC e CA).
- **ABNT NBR 5419** rege o SPDA (proteção contra descargas atmosféricas). Nos EUA isso fica
  na NFPA 780, fora do NEC.

## 6. Estruturas e vento (ASCE 7 → NBR 6123)

- **ABNT NBR 6123** define as forças devidas ao vento.
- A capacidade de arrancamento (pull-out) dos fixadores vem do fabricante, para a espécie de
  madeira ou o tipo de telhado, verificada contra as cargas da NBR 6123.
