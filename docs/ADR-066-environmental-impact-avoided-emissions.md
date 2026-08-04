# ADR-066 — Impacto ambiental: CO2 evitado e árvores equivalentes

## Status

Aceito — 2026-08-04.

Decisões A (chip de ícone categórico) e C (fator honesto SIN/MCTI, médio não marginal) já
confirmadas pelo usuário antes deste ADR ser escrito. Os três pontos abaixo continuam como
tarefa da Etapa A do worker (ler a fonte oficial e fixar o valor exato/ano/URL), não como
decisão pendente de produto.

## Contexto

Um gap analysis contra concorrentes do setor solar mostrou que praticamente todos os
portais de monitoramento expõem "CO2 evitado" e "árvores equivalentes". O Mplacas não
expõe nada disso hoje. É um indicador de baixo custo de cálculo e alto valor percebido
pelo dono da usina — mas é também o indicador mais frequentemente publicado errado no
setor brasileiro.

Restrições já estabelecidas que condicionam o desenho:

- **ADR-012** é explícito: "Regras e cálculos energéticos continuam exclusivamente no
  backend determinístico." O cálculo NÃO pode ser feito no frontend, mesmo sendo
  aritmeticamente trivial. O frontend recebe o número pronto e apenas formata.
- **ADR-006** (determinístico antes da IA) reforça o mesmo: indicador auditável, função
  pura, sem IA no caminho.
- **ADR-038** (snapshots mensais imutáveis) proíbe que uma mudança futura do fator de
  emissão altere retroativamente um relatório já emitido. Qualquer fator usado precisa
  ser versionado, no mesmo padrão de `PERFORMANCE_MODEL_VERSION`
  (`src/mplacas/photovoltaic/performance.py`), `MODEL_VERSION` de `poa.py`,
  `BASELINE_MODEL_VERSION` e `LOSS_TAXONOMY_MODEL_VERSION` — todos com o formato
  `MPLACAS_<DOMINIO>_V<N>`.
- O princípio de nunca fabricar um zero já está codificado em
  `src/mplacas/intelligence/energy_engine.py` para `estimated_savings_brl`, que é `None`
  com um `savings_unavailable_reason` explícito em vez de R$ 0,00. O indicador
  ambiental segue o mesmo princípio, sem exceção.

### O ponto técnico central: qual fator de emissão

A maioria dos concorrentes usa um fator na ordem de **0,45 kgCO2/kWh**, herdado de
matrizes elétricas de base térmica (padrão internacional / EPA). Aplicado à matriz
brasileira — hidro-dominante, com participação relevante de eólica e solar — esse fator
**superestima o CO2 evitado em cerca de uma ordem de grandeza**. É um número de
marketing, não um número de engenharia.

O MCTI publica, através do SIRENE, a série oficial de fatores de emissão de CO2 da
geração de energia elétrica do Sistema Interligado Nacional (SIN), com resolução mensal
e média anual, expressa em tCO2/MWh — numericamente idêntica a kgCO2/kWh. A série anual
recente fica na faixa de **0,04 a 0,07 kgCO2/kWh**, com excursão para cerca de 0,13 em
anos de crise hídrica severa (2021), quando o despacho termelétrico sobe.

## Decisão

### 1. Módulo novo `src/mplacas/intelligence/environmental.py`

Módulo de função pura, sem I/O, sem sessão de banco, no mesmo padrão de
`energy_engine.py`. Contrato:

```python
ENVIRONMENTAL_MODEL_VERSION = "MPLACAS_BR_SIN_ENVIRONMENTAL_V1"

# Fonte: MCTI/SIRENE — Fatores de emissão de CO2 da geração de energia
# elétrica no SIN. Média anual de <ANO>, em tCO2/MWh (= kgCO2/kWh).
GRID_EMISSION_FACTOR_KG_CO2_PER_KWH: Final = Decimal("<a confirmar>")

# Aproximação. Fonte: <a confirmar>. Absorção média de CO2 por árvore por ano.
TREE_ABSORPTION_KG_CO2_PER_YEAR: Final = Decimal("22")

ENVIRONMENTAL_UNAVAILABLE_NO_PRODUCTION_DATA = "NO_PRODUCTION_DATA"


@dataclass(frozen=True, slots=True)
class EnvironmentalImpact:
    co2_avoided_kg: Decimal | None
    equivalent_trees: int | None
    emission_factor_version: str
    unavailable_reason: str | None


def assess_environmental_impact(
    *, production_kwh: Decimal | None
) -> EnvironmentalImpact: ...
```

Regras da função:

- `production_kwh` igual a `None` ou menor ou igual a zero: `co2_avoided_kg=None`,
  `equivalent_trees=None`, `unavailable_reason=ENVIRONMENTAL_UNAVAILABLE_NO_PRODUCTION_DATA`.
  NUNCA zero fabricado — mesmo princípio já aplicado a `estimated_savings_brl`.
- `production_kwh` negativo: `ValueError`. É dado corrompido, não ausência de dado —
  mesmo tratamento que `analyze_energy_cycle` dá a contadores negativos.
- `co2_avoided_kg` quantizado em 1 casa decimal com `ROUND_HALF_UP`, igual ao `_q1` já
  usado no motor.
- `equivalent_trees` é truncado para baixo, não arredondado: "equivale a 3 árvores" é
  mais defensável que "equivale a 4" quando o valor real é 3,6. Quando o resultado
  trunca para zero mas há CO2 evitado, o campo vale `0` legitimamente e o frontend
  exibe "menos de 1 árvore" — este é o único zero legítimo do módulo, porque aqui zero
  é resultado de cálculo, não ausência de dado.
- Nenhuma constante é parâmetro de função. O fator é fixo no módulo, versionado, e
  qualquer alteração exige subir para `_V2`.

### 2. Base de cálculo: geração total do ciclo

`co2_avoided_kg = cycle_production_kwh * GRID_EMISSION_FACTOR_KG_CO2_PER_KWH`.

A base é `reconciliation.cycle_production_kwh` — a geração TOTAL do ciclo, não apenas o
autoconsumo. Justificativa: a energia injetada na rede também desloca geração do SIN; do
ponto de vista do sistema elétrico, cada kWh gerado pela usina é um kWh que o SIN não
precisou gerar. Usar apenas o autoconsumo subestimaria o impacto e não teria respaldo
físico.

### 3. Onde entra no contrato de API

Não existe uma classe `ExecutiveIndicators` no projeto. O bloco `indicators` do contrato
executivo é montado à mão em `_serialize()` (`src/mplacas/intelligence/router.py`, linhas
44-76) a partir de `EnergyCycleIntelligence`
(`src/mplacas/intelligence/energy_engine.py`). A integração é, portanto:

1. `EnergyCycleIntelligence` ganha três campos novos, com default, no fim do dataclass:
   `co2_avoided_kg: Decimal | None = None`, `equivalent_trees: int | None = None`,
   `environmental_unavailable_reason: str | None = None`.
2. `analyze_energy_cycle()` chama `assess_environmental_impact()` e preenche os campos.
3. `_serialize()` acrescenta ao dicionário `indicators`: `co2_avoided_kg`,
   `equivalent_trees`, `environmental_unavailable_reason` e `emission_factor_version` —
   este último sempre presente, mesmo quando o cálculo está indisponível, porque o
   cliente precisa saber com qual versão o backend respondeu.
4. `Decimal` serializa como `str` e `int` como `int`, seguindo exatamente a convenção já
   usada no mesmo dicionário.

Os três campos aparecem em `GET /energy/cycles/{bill_id}` e, por composição, em
`GET /energy/executive/latest`, sem mudança adicional nesses endpoints.

### 4. Deliberadamente fora do snapshot mensal nesta frente

`estimated_savings_brl` hoje NÃO está em `src/mplacas/reports/report_projection.py`, e o
CO2 também NÃO entra agora. Motivo: acrescentar métrica ao `MonthlyEnergyReport` altera o
`payload_json` e o `calculation_version` do snapshot (ADR-038), o que é um acoplamento
direto com a frente de ROI (ver ADR-067) e transformaria esta frente de baixo risco em
uma mudança no contrato de relatório imutável. A inclusão do CO2 no relatório mensal em
PDF fica registrada como extensão futura, condicionada à mesma decisão de versionamento
tratada no ADR-067.

### 5. Cache do dashboard executivo

`ExecutiveDashboardReadModel` (`src/mplacas/intelligence/dashboard_readmodel.py`) mantém
um cache LRU EM PROCESSO, chaveado por uma impressão digital dos DADOS de energia
(`energy_fingerprint`), que não inclui a versão do código. Uma entrada em cache criada
antes do deploy não teria os campos novos.

Isso não exige mudança agora: o cache é in-process e não persistente, portanto morre no
restart que acompanha todo deploy no Cloud Run (ADR-025). Fica registrado aqui porque é
uma armadilha real para quem, no futuro, migrar esse cache para Redis — nesse cenário a
chave passa a precisar incluir a versão do modelo.

### 6. Frontend

Card novo, seguindo a skill `frontend-design` e o esqueleto de card de métrica já em uso:

- Card branco padrão, `border-gray-200`, valor em `text-gray-900`. NENHUMA cor
  categórica no número, na borda ou no fundo do card.
- A cor categórica aparece EXCLUSIVAMENTE em um chip de ícone — token novo em
  `frontend/src/index.css`: `--color-accent-environment` (teal, deliberadamente distinto
  de `--color-success`) e `--color-accent-environment-light` para o fundo do chip. Usar
  `success` aqui seria semanticamente errado: verde no projeto significa "dentro do
  esperado", e CO2 evitado não é um estado de saúde da usina.
- Rótulo textual sempre presente ao lado do ícone. A cor nunca é o único portador de
  significado — o projeto exporta relatório em PDF preto e branco.
- Unidade sempre visível: `kg CO2`.
- Nota de rodapé obrigatória no card, citando fator, fonte e ano, e rotulando árvores
  equivalentes como aproximação. Sem essa nota o card não vai para produção — é o que
  separa este indicador do número de marketing dos concorrentes.
- Estado indisponível reusa o padrão de `frontend/src/components/EstimatedSavingsCard.tsx`:
  mensagem explícita, nunca `0 kg`.

### 7. Roteamento de agentes

Esta frente NÃO toca billing, auth, credentials, organizations, audit ou migrations. Não
há mudança de schema — é um cálculo puro mais campos novos de serialização. Pela regra do
`CLAUDE.md`, NÃO exige reviewer; o CI do worker basta. Confirmo essa leitura, com uma
ressalva: se durante a implementação o worker concluir que precisa mexer em
`report_projection.py` ou em qualquer snapshot, a tarefa muda de categoria e passa a
exigir reviewer — nesse caso ele deve parar e escalar, não seguir.

## Consequências

### Positivas

- Paridade com concorrentes em um indicador esperado pelo mercado, sem sair do princípio
  de cálculo determinístico e auditável no backend (ADR-006, ADR-012).
- Diferencial defensável: o número do Mplacas é tecnicamente correto para a matriz
  brasileira, com fonte citada na própria interface. Um cliente que compare os dois
  portais vai ver o Mplacas mostrar um número cerca de 10x menor — e a nota de rodapé é o
  que transforma isso de "o Mplacas mostra menos" em "o Mplacas mostra certo".
- Fator versionado desde o dia zero: uma revisão futura do fator não reescreve o passado.
- Custo de implementação baixo, sem migration, sem mudança de schema, sem risco de
  isolamento entre tenants.

### Negativas

- **Fator médio, não marginal — trade-off consciente e discutível.** O MCTI publica duas
  famílias de fator: o fator médio da matriz (para inventário corporativo de consumo) e o
  fator de margem de operação (para projetos de MDL), sendo este último substancialmente
  maior, porque a geração efetivamente deslocada na margem é térmica, não hídrica.
  Rigorosamente, "CO2 evitado por uma usina nova" é uma pergunta marginal, e o fator
  marginal chegaria perto do 0,45 que este ADR rejeita. A escolha do fator médio é a mais
  conservadora e a mais fácil de defender junto ao cliente — "é o número oficial do MCTI
  para a matriz brasileira" — mas não é a única tecnicamente defensável. Fica registrada
  como escolha explícita, não como verdade única.
- **Um escalar anual esconde variação real relevante.** A série do MCTI varia por mês e,
  entre anos, por um fator de até cerca de 3 em anos de crise hídrica. Um único `Decimal`
  fixo trata 2021 como se fosse 2023. A alternativa — tabela mensal por ano de referência
  — é mais correta e significativamente mais cara (carregamento de dados, cobertura de
  meses sem publicação, atualização anual recorrente). Aceita-se o escalar em V1; a
  tabela mensal é o `_V2` natural.
- **"Árvores equivalentes" é uma aproximação de rigor limitado.** A absorção real varia
  por espécie, idade, bioma e regime de chuvas em quase uma ordem de grandeza. O número
  existe por valor comunicacional, não científico. Mitigação: rótulo explícito de
  aproximação e fonte citada na interface — o ADR aceita conscientemente publicar um
  número impreciso desde que ele não se apresente como preciso.
- O indicador não aparece no relatório mensal em PDF nesta frente, criando inconsistência
  temporária entre o que a tela mostra e o que o relatório exportado contém. Aceito para
  manter esta frente desacoplada do ADR-067.

## Validação

- Testes unitários de `assess_environmental_impact`: produção positiva (valor e
  arredondamento), `None`, zero, negativa (`ValueError`), truncamento de árvores para
  baixo, e um teste que fixa o valor da constante e falha se ela mudar sem bump de versão
  — o teste é o mecanismo que força a disciplina de versionamento.
- Teste de contrato do serializer, no padrão de
  `tests/test_energy_intelligence_router_contract.py`: os quatro campos presentes na
  resposta, com `null` (não `0`) no caminho de indisponibilidade.
- Testes de frontend no padrão já existente (`EstimatedSavingsCard`, `MetricCard`),
  cobrindo o estado indisponível e a presença da nota de rodapé.
- `npm run build` em `frontend/` com verificação de que as classes Tailwind novas do chip
  realmente aparecem no CSS gerado em `dist/assets/*.css` — a skill `frontend-design`
  registra um bug real já ocorrido nesse ponto (commit `b186f67`).

## Reversibilidade

Alta. Remover o indicador é remover um card no frontend e quatro chaves do dicionário
`indicators` — não há dado persistido, não há migration, não há snapshot afetado. Trocar
o fator (por exemplo, migrar para o fator de margem de operação, ou para tabela mensal) é
criar `MPLACAS_BR_SIN_ENVIRONMENTAL_V2` sem tocar em `V1`; como nada foi persistido com
`V1`, não há nem histórico a preservar nessa transição.

## Pontos que exigem confirmação antes de virar Aceito

1. **Valor exato e ano de referência do fator MCTI/SIRENE.** O portal do MCTI está atrás
   de WAF e não foi possível ler a planilha oficial nesta sessão. A faixa 0,04-0,07
   kgCO2/kWh está confirmada como ordem de grandeza correta, e a média anual de 2023 fica
   próxima de 0,0385 tCO2/MWh — mas o número gravado na constante DEVE ser lido da
   planilha oficial, não desta memória. A primeira etapa do worker inclui abrir a fonte,
   fixar valor, ano e URL no docstring do módulo, e reportar o número escolhido antes de
   seguir.
2. **Fator médio versus fator de margem de operação** (ver "Negativas"). A decisão
   registrada é o fator médio. Se a escolha for o marginal, o ADR muda de conclusão, não
   apenas de número.
3. **Fonte do fator de absorção por árvore.** O valor de 22 kg por árvore por ano é o mais
   citado, mas sua rastreabilidade a uma fonte primária é fraca. Se a preferência for uma
   fonte brasileira (Embrapa, ou IPCC para floresta tropical em regeneração), o valor muda
   e a nota de rodapé muda junto.

## Plano de implementação

Três etapas sequenciais. Sem reviewer obrigatório (ver Decisão, item 7).

**Etapa A — módulo de cálculo (não depende de nada).**
Criar `src/mplacas/intelligence/environmental.py` com as constantes versionadas, o
dataclass `EnvironmentalImpact` e a função pura. Confirmar o valor do fator na fonte
oficial do MCTI/SIRENE e citá-la no docstring. Testes unitários em
`tests/test_environmental_impact.py` cobrindo os casos da seção Validação. Nenhuma
alteração fora do módulo novo e do arquivo de teste.

**Etapa B — integração no contrato (depende de A).**
Acrescentar os três campos a `EnergyCycleIntelligence`, preenchê-los em
`analyze_energy_cycle`, e estender o dicionário `indicators` em `_serialize()` com os
quatro campos. Estender `tests/test_energy_intelligence_router_contract.py` e
`tests/test_energy_intelligence.py`. Verificar que os testes de snapshot de relatório
continuam passando sem alteração — se algum falhar, é sinal de acoplamento não previsto,
e o worker deve parar e escalar.

**Etapa C — frontend (depende de B).**
Tokens `--color-accent-environment` e `--color-accent-environment-light` em
`frontend/src/index.css`; parser dos campos novos em `frontend/src/lib/dashboard/contracts.ts`
(padrão de `metricValue`/`optionalString` já existente); componente
`EnvironmentalImpactCard.tsx` com chip de ícone colorido, valor neutro e nota de rodapé;
inclusão no `DashboardPage.tsx`. Testes de componente e `npm run build` com verificação
das classes no CSS gerado.
