# ADR-027 — Relatório mensal auditável e exportação CSV

## Status

Aceito.

## Contexto

O Mplacas já possui cálculo determinístico do ciclo energético, qualidade de dados, diagnósticos,
tendências e painel executivo. O roadmap de produto exige relatórios e exportações, mas a camada de
saída não pode recalcular indicadores nem criar uma segunda implementação das regras energéticas.

Também foi identificada divergência entre a versão declarada no `pyproject.toml` (`0.2.0`) e a
versão exposta pelo pacote e pelo endpoint `/health` (`0.1.0`). Como relatórios auditáveis precisam
registrar a versão do cálculo, essa inconsistência deve ser eliminada.

## Decisão

1. Criar o pacote `mplacas.reports` como camada exclusiva de projeção e exportação.
2. Usar `build_executive_dashboard` como única origem dos indicadores, diagnósticos e tendências.
3. Não recalcular energia, percentuais, score, severidades ou recomendações no módulo de relatórios.
4. Entregar inicialmente o relatório mensal do ciclo confirmado mais recente.
5. Expor dois endpoints protegidos pela chave operacional:
   - `GET /reports/monthly/latest`;
   - `GET /reports/monthly/latest.csv`.
6. Registrar em cada indicador:
   - chave estável;
   - rótulo humano;
   - valor;
   - unidade;
   - natureza da métrica;
   - fonte.
7. Registrar no relatório:
   - versão do esquema;
   - versão do cálculo;
   - `plant_id`;
   - `bill_id`;
   - mês de referência;
   - status executivo;
   - headline;
   - qualidade dos dados;
   - diagnósticos;
   - ações prioritárias;
   - tendência, quando houver dois ciclos confirmados.
8. Gerar CSV com biblioteca padrão do Python, sem dependência adicional.
9. Usar UTF-8 com BOM para compatibilidade com planilhas de desktop.
10. Enviar respostas com `Cache-Control: no-store`; o CSV também usa `nosniff` e
    `Content-Disposition` de anexo.
11. Alinhar `mplacas.__version__` ao valor `0.2.0` do `pyproject.toml` e proteger a igualdade por
    teste automatizado.

## Natureza e origem dos dados

- Produção do ciclo: agregado de `DailyEnergy`, natureza `MEASURED_AGGREGATE`.
- Importação e injeção: fatura confirmada, natureza `MEASURED`.
- Autoconsumo, consumo estimado, percentuais, componente energético e score: motor determinístico,
  natureza `CALCULATED` ou `CALCULATED_SCORE`.
- Contadores de qualidade: motor determinístico, natureza `QUALITY_COUNT`.
- Diagnósticos e ações: regras determinísticas existentes.
- Tendências: comparação determinística de ciclos confirmados.

## Segurança e privacidade

- Os endpoints exigem a autenticação operacional já existente.
- O relatório não contém token, senha, chave operacional, endereço, CPF, unidade consumidora,
  coordenadas ou payload externo bruto.
- Não há cache HTTP autorizado para as respostas.
- O nome do arquivo contém apenas mês de referência e UUID da usina.
- O exportador não acessa configuração sensível.

## Consequências

### Positivas

- primeira exportação de produto sem duplicação de regras;
- rastreabilidade por fonte, natureza, período e versão;
- formato JSON adequado a integrações;
- CSV interoperável e sem nova dependência;
- base reutilizável para PDF, XLSX e relatórios anuais posteriores.

### Negativas

- a primeira entrega cobre apenas o ciclo mensal confirmado mais recente;
- PDF e XLSX permanecem fora desta PR;
- o relatório depende da existência de ao menos uma fatura confirmada para a usina.

## Validação

A entrega deve permanecer coberta por:

- teste de alinhamento da versão do pacote com o `pyproject.toml`;
- teste de projeção do dashboard determinístico;
- teste de metadados de fonte, natureza e unidade;
- teste de CSV com BOM UTF-8;
- teste de autenticação obrigatória;
- teste das respostas JSON e CSV;
- Ruff, Mypy, Pytest e CI integralmente verdes.
