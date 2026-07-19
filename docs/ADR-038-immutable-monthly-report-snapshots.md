# ADR-038 - Snapshots imutáveis de relatório mensal

## Status

Aceito.

## Contexto

Os quatro formatos de relatório mensal eram montados sob demanda a partir do ciclo confirmado mais
recente. Embora os exportadores não recalculassem indicadores, cada requisição repetia consultas e
a projeção executiva. Uma evolução de código podia, portanto, alterar silenciosamente um relatório
histórico sem que a fatura confirmada tivesse mudado. Também não havia uma identidade persistente
para demonstrar qual conteúdo foi entregue.

A fronteira de leitura definida no ADR-036 permite montar um ciclo histórico exato. O escopo por
usina do ADR-037 precisa continuar aplicado tanto na consulta quanto na persistência do relatório.

## Decisão

1. Persistir um único snapshot mensal por fatura confirmada na tabela
   `monthly_report_snapshots`.
2. Armazenar o documento JSON completo em forma canônica, com chaves ordenadas, separadores
   estáveis, versões de esquema e cálculo, e checksum SHA-256.
3. Materializar o snapshot na mesma transação que confirma a fatura. Se a projeção falhar, a
   confirmação também não é consolidada.
4. Materializar de forma idempotente, na primeira leitura, o relatório de faturas confirmadas antes
   desta decisão.
5. Montar snapshots históricos a partir da fatura identificada e de sua predecessora, sem depender
   do ciclo mais recente da usina.
6. Fazer JSON, CSV, PDF e XLSX apenas serializarem o mesmo modelo reconstruído do snapshot.
7. Verificar checksum e metadados persistidos em toda leitura. Divergência é erro de integridade e
   nunca provoca recomputação silenciosa.
8. Aplicar `PlantScope` no repositório de snapshots e na fronteira de faturas confirmadas.
9. Expor o checksum no cabeçalho HTTP `ETag` e o UUID do artefato em
   `X-Mplacas-Report-Snapshot`.
10. Manter temporariamente os parâmetros `expected_production_kwh` e
    `stable_tolerance_percent` no contrato HTTP, marcados como descontinuados e ignorados. A
    projeção persistida usa as premissas canônicas do motor.
11. Impedir a exclusão da fatura ou da usina referenciada com chaves estrangeiras `RESTRICT`.

## Consequências

### Positivas

- O conteúdo entregue para uma fatura permanece estável quando o código evolui.
- Os quatro formatos têm uma única fonte de verdade e identidade auditável.
- Requisições deixam de repetir consultas e cálculos depois da primeira materialização.
- O checksum detecta corrupção ou alteração direta do payload armazenado.
- A restrição única por fatura e a transação aninhada tornam reexecuções e concorrência
  idempotentes.

### Negativas

- A confirmação de fatura passa a depender da montagem válida do relatório.
- O banco armazena uma cópia JSON dos dados projetados e exige a migration `20260719_0011`.
- Mudanças legítimas de cálculo não reescrevem snapshots existentes; exigem um novo contrato
  explícito de revisão, se essa necessidade surgir.
- A divisão mecânica dos módulos grandes de apresentação permanece uma entrega separada; esta ADR
  altera primeiro o ciclo de vida e a fonte dos dados.

## Validação

A entrega deve permanecer coberta por:

- migration com chaves estrangeiras, unicidade por fatura e índice por usina e referência;
- criação atômica durante a confirmação e materialização tardia para dados legados;
- materialização histórica usando a predecessora correta;
- idempotência e estabilidade depois de alterações nos dados-fonte;
- detecção de checksum adulterado;
- propagação de escopo por usina;
- cabeçalhos de identidade em todos os formatos;
- Ruff, Mypy e Pytest.
