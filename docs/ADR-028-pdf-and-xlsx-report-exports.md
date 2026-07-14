# ADR-028 — Exportações mensais em PDF e XLSX

## Status

Aceito.

## Contexto

A ADR-027 introduziu o relatório mensal auditável em JSON e CSV. O produto ainda precisava de dois
formatos adequados para uso humano, arquivamento e compartilhamento operacional:

- PDF paginado e legível;
- planilha XLSX estruturada e compatível com Excel.

Os novos formatos não podem criar uma segunda implementação dos cálculos energéticos. O contrato
`MonthlyEnergyReport` deve permanecer como fonte única dos valores, diagnósticos, qualidade e
tendências.

## Decisão

1. Gerar PDF com ReportLab em memória.
2. Gerar XLSX com XlsxWriter em memória.
3. Não criar arquivos temporários no servidor.
4. Manter `MonthlyEnergyReport` como única entrada dos exportadores.
5. Proibir fórmulas no XLSX.
6. Desabilitar a interpretação automática de strings como fórmulas e URLs no XlsxWriter.
7. Preservar valores exportados como dados literais do relatório auditado.
8. Registrar no PDF e no XLSX:
   - mês de referência;
   - `plant_id`;
   - `bill_id`;
   - versão do esquema;
   - versão do cálculo;
   - status;
   - declaração de ausência de recálculo.
9. Proteger os endpoints com a mesma chave operacional dos demais relatórios.
10. Entregar os arquivos com `Cache-Control: no-store`, `Pragma: no-cache` e `nosniff`.

## Endpoints

- `GET /reports/monthly/latest.pdf`
- `GET /reports/monthly/latest.xlsx`

Os dois endpoints usam os mesmos parâmetros do relatório JSON e do CSV:

- `plant_id`;
- `expected_production_kwh`, opcional;
- `stable_tolerance_percent`, opcional.

## Estrutura do PDF

O PDF usa A4, margens fixas e tabelas com quebra automática entre páginas. Ele contém:

- título e identificação do período;
- metadados de rastreabilidade;
- síntese executiva;
- indicadores do ciclo;
- qualidade dos dados;
- diagnósticos;
- ações prioritárias;
- tendência entre ciclos, quando disponível;
- rodapé com número da página e versões do esquema e do cálculo;
- nota explícita de que a exportação não recalcula indicadores.

## Estrutura do XLSX

O arquivo contém seis abas:

1. `Resumo`;
2. `Indicadores`;
3. `Qualidade`;
4. `Diagnosticos`;
5. `Tendencias`;
6. `Metadados`.

As abas usam cabeçalhos, larguras definidas, quebra de texto, painéis congelados e configuração de
impressão. Os dados são gravados sem fórmulas.

## Segurança

- nenhum segredo é incluído;
- nenhum token ou credencial é incluído;
- nenhum payload externo bruto é incluído;
- strings não são convertidas automaticamente em fórmulas;
- strings não são convertidas automaticamente em links;
- valores são escapados antes de entrar em elementos de texto do PDF;
- os arquivos são produzidos somente após autenticação operacional.

## Consequências

### Positivas

- relatórios adequados para leitura, impressão e arquivamento;
- planilha estruturada para conferência administrativa;
- rastreabilidade equivalente entre JSON, CSV, PDF e XLSX;
- nenhum cálculo duplicado;
- nenhuma dependência de Google Cloud ou infraestrutura externa.

### Negativas

- aumento do tamanho da imagem do contêiner pelas novas bibliotecas;
- o XLSX não contém fórmulas ou gráficos calculados no cliente;
- o PDF usa fontes internas do ReportLab para manter portabilidade.

## Validação

A implementação deve permanecer coberta por:

- Ruff;
- Mypy;
- Pytest;
- abertura do PDF com `pypdf`;
- extração de texto e conferência de metadados do PDF;
- inspeção do pacote ZIP/XML do XLSX;
- verificação das seis abas;
- verificação de ausência de elementos de fórmula no XLSX;
- testes de autenticação e cabeçalhos de download;
- build e smoke test do contêiner.
