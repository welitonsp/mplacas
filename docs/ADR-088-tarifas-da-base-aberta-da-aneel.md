# ADR-088 — Tarifas homologadas importadas da base aberta da ANEEL

## Status

**Aceito — 2026-10-24.** Faz parte do plano para o sistema atender o mercado brasileiro.
Decisão do dono do produto: importar automaticamente as tarifas da ANEEL e implementar o
leitor de fatura de cada nova distribuidora quando surgir um cliente dela, porque ainda não
temos faturas de exemplo.

## Contexto

A conta "sem a usina" (ADR-080) usa a tarifa cheia homologada. Até aqui, ela era cadastrada
à mão: a migration 0045 tinha só a Equatorial GO, classe B1 residencial. A ANEEL publica a
base aberta "Tarifas de aplicação das distribuidoras de energia elétrica", atualizada toda
semana, com TUSD e TE de todas as distribuidoras desde 2010.

Uma sonda feita pelo GitHub Actions (o ambiente de desenvolvimento não acessa o site da
ANEEL) mostrou o formato real da base:
- 178 MB, separador ";", vírgula decimal, valores em R$/MWh;
- colunas `DscSubGrupo`, `DscBaseTarifaria`, `DscDetalhe` ("Não se aplica" ou "SCEE"),
  `VlrTUSD` e `VlrTE`;
- a Equatorial aparece como "EQUATORIAL GO".

A base **bate com o cadastro**. Para a B1 residencial convencional, TUSD + TE dá
0,710630 / 0,745930 / 0,891810 R$/kWh, e a linha SCEE dá 0,498120 / 0,613030, os mesmos
valores conferidos nas faturas reais.

## Decisão

1. **`tariffs/aneel_import.py`** transforma o CSV em períodos por distribuidora e classe.
   - **Filtros:** só `Tarifa de Aplicação`, modalidade `Convencional`, sem posto
     tarifário, sem usuário específico e unidade MWh.
   - **Tarifa cheia:** linha comum. **Tarifa da energia compensada:** linha "SCEE".
   - **Classes importadas:**
     - B1 Residencial/Residencial → `B1_RESIDENCIAL_CONVENCIONAL`;
     - B2 Rural genérica → `B2_RURAL_CONVENCIONAL`;
     - B3 (uma tarifa só) → comercial, industrial, poder público e serviço público.
   - **Classes não importadas:** baixa renda e tarifa social (faixas de desconto por
     consumo), tarifa branca (postos horários), irrigação e cooperativa. Para essas
     classes, o motor usa o preço da fatura e avisa (ADR-087).
   - **Vigências:** vigências seguidas com os mesmos valores são unidas. A importação
     começa em vigências que terminam a partir de 2019.
   - **Código da distribuidora:** é a sigla da ANEEL normalizada ("EQUATORIAL GO" →
     `EQUATORIAL_GO`). O leitor de fatura de cada distribuidora nova precisa usar a mesma
     regra.
2. **Falha fechada.** Nestes casos a importação é interrompida e nada é gravado:
   - valor implausível (fora de R$ 0,20–2,50/kWh);
   - valores conflitantes na própria base;
   - vigências sobrepostas;
   - cadastro existente com valor diferente do da ANEEL.

   Se o valor for o mesmo, só a data final da vigência pode ser ajustada.
3. **Comando:** `python -m mplacas.cloud_jobs import-tariffs`, com as opções `--dry-run` e
   `--no-db`.
4. **Workflow `import-tariffs`:**
   - **semanal**, às terças, gravando;
   - **manual**, em dois modos: "simular" compara sem gravar; "gravar" exige a confirmação
     `TARIFAS`;
   - **em pull request que mexe no importador**, baixa a base real e só resume, sem banco
     nem segredo.

## Consequências

- O reajuste da Equatorial de 22/10/2026 (REH 3.613/2026) entra sozinho quando a ANEEL o
  publicar na base. Em 24/10 ele ainda não estava lá. Não é mais preciso esperar a fatura de
  novembro para cadastrar.
- Qualquer distribuidora passa a ter tarifa cheia assim que tiver um leitor de fatura. Os
  leitores serão implementados quando surgir o primeiro cliente de cada uma.
- O cadastro manual da migration 0045 continua valendo. A importação confere esse cadastro e
  só acrescenta.

## Validação

- **Testes (`tests/test_aneel_import.py`):** usam as linhas reais da Equatorial GO e cobrem:
  - os valores e a união de vigências;
  - as linhas ignoradas;
  - o mapeamento de B3 e B2;
  - a falha fechada;
  - a importação sobre o cadastro atual (não muda nada e acrescenta só o período novo);
  - divergência e sobreposição recusadas.
- **Comando de ponta a ponta:** testado com um CSV servido localmente.
- **Pull request:** o workflow baixa a base real e resume a importação.
