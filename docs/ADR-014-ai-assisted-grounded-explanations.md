# ADR-014 — Explicações assistidas por IA com grounding obrigatório

## Status

Aceito para a fase P9.

## Contexto

O Mplacas já calcula indicadores, tendências e anomalias por regras determinísticas. A próxima camada deve melhorar a compreensão do usuário sem transferir à IA generativa a responsabilidade por cálculos, classificação, diagnóstico causal ou decisão operacional.

## Decisão

1. A IA recebe somente estado consolidado, manchete e evidências estruturadas já produzidas pelo sistema.
2. A IA não recebe credenciais, faturas brutas, payloads privados ou identificadores desnecessários.
3. A IA não pode recalcular indicadores, alterar severidade, criar causas, remover alertas ou contradizer os diagnósticos determinísticos.
4. Toda resposta mantém aviso fixo de que a explicação não confirma causa técnica nem substitui inspeção profissional.
5. A indisponibilidade, timeout, exceção ou resposta inválida do provedor produz fallback determinístico imediato.
6. O provedor é substituível por contrato e não contamina os motores de domínio.
7. A saída é validada antes de ser entregue e limitada a cinco próximos passos.
8. A origem da explicação é explícita: `DETERMINISTIC` ou `AI_ASSISTED`.

## Consequências

### Positivas

- preserva auditabilidade;
- reduz risco de alucinação causal;
- mantém o produto funcional sem provedor de IA;
- permite troca de fornecedor;
- facilita testes sem rede.

### Limitações

- a explicação pode ser menos detalhada quando o fallback é usado;
- a qualidade da redação depende das evidências já calculadas;
- integração com provedor real e observabilidade ficam para o bloco seguinte desta PR.
