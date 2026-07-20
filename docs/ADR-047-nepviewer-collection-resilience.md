# ADR-047 - Camada de resiliência para a coleta NEPViewer

## Status

Aceito.

## Contexto

A extração da produção diária das placas via API não oficial da NEPViewer é o núcleo do Mplacas:
sem esse dado, não há reconciliação com a fatura da Equatorial. A API é não oficial e sujeita a
três modos de falha observáveis: indisponibilidade transitória (timeout, 5xx), respostas
incompletas (o envelope vem válido, mas sem os dias esperados) e falhas terminais (credencial
recusada, contrato incompatível).

O `NepViewerClient` já era defensivo: distinguia `ProviderUnavailableError`, `ProviderAuthError` e
`ProviderSchemaError`, re-autenticava em 401/403 e validava o envelope. Faltava, porém, **retry**
para falhas transitórias e **detecção explícita de dados incompletos** — num sistema de
reconciliação, "a API não devolveu o dado" não pode ser confundido com "produção zero".

## Decisão

1. Nova exceção `ProviderIncompleteDataError`: o provedor respondeu, mas não cobriu todos os dias
   solicitados. Distinta de produção legitimamente zero.
2. O `NepViewerClient.get_daily_energy` ganha o parâmetro opt-in `expect_complete`. Quando ativo,
   verifica que todos os dias do intervalo foram cobertos pela série e, se faltar algum, levanta
   `ProviderIncompleteDataError`. O comportamento padrão (`expect_complete=False`) é inalterado,
   preservando backfills históricos em que dias sem dado são legítimos.
3. Novo `ResilientSolarProvider`, um wrapper que preserva o contrato `SolarProvider` e aplica retry
   com backoff exponencial (teto de 30s) para as falhas **transitórias**
   (`ProviderUnavailableError` e `ProviderIncompleteDataError`). Falhas de autenticação e de esquema
   **não** são reexecutadas — são terminais e devem falhar de imediato para não mascarar um problema
   real. Esgotadas as tentativas, propaga o erro original.
4. Novo `build_resilient_nepviewer`: composição única de cliente + resiliência, para que a coleta
   nunca seja ligada à API sem a proteção.
5. A fila de coleta (ADR-046) permanece a terceira camada: se, mesmo após o retry, a API seguir
   indisponível, a tarefa é reagendada com backoff sem derrubar o restante do pipeline.

### Defesa em profundidade

- **Curta (segundos):** retry no wrapper absorve o soluço momentâneo da API.
- **Média (contrato):** detecção de dados incompletos impede que um dia faltante vire zero silencioso.
- **Longa (reagendamento):** a fila retenta o dia mais tarde se a indisponibilidade persistir.

## Consequências

### Positivas

- Timeouts e 5xx passageiros da API deixam de derrubar a coleta na primeira ocorrência.
- Um dia ausente na resposta é sinalizado, não engolido — proteção direta da integridade da
  reconciliação.
- O contrato do provedor é preservado: o domínio continua vendo apenas um `SolarProvider`.

### Negativas

- O retry adiciona latência quando a API está de fato instável (limitada pelo teto de backoff e
  pelo número de tentativas).
- `expect_complete` precisa ser ativado conscientemente pelo chamador nos fluxos onde a completude
  é obrigatória (coleta do dia corrente), permanecendo desligado nos backfills.

## Validação

- retry recupera após indisponibilidade transitória e após dados incompletos;
- retry esgota e repropaga o erro original;
- erros de autenticação e de esquema não são reexecutados;
- backoff é validado e limitado pelo teto;
- o cliente sinaliza dia ausente sob `expect_complete` e mapeia timeout para indisponibilidade;
- o factory compõe cliente + resiliência com recuperação ponta a ponta.
