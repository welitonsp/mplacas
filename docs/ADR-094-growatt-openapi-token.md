# ADR-094 — Growatt pela OpenAPI oficial (token do app ShinePhone)

## Status

**Aceito — 2026-10-31.** Complementa a ADR-092 (Growatt por usuário e senha) e a ADR-093
(entrada de clientes).

## Contexto

No primeiro cliente real (31/10/2026), o login por usuário e senha da Growatt
(`newTwoLoginAPI.do`, a API do app) respondeu **HTTP 403** nas duas tentativas, a partir do
servidor no Render. É a Growatt recusando o pedido inteiro, antes de olhar a senha, e não
"senha errada". Mesmo assim, o sistema mostrava "A Growatt recusou o usuário ou a senha".
Outros projetos relatam o mesmo bloqueio: a API do app filtra quem a usa e pode mudar sem aviso.

A Growatt tem uma interface documentada para terceiros, a OpenAPI V1. Ela funciona com um token
no cabeçalho `token`, sem login. O cliente gera o token no app ShinePhone (Me → nome de usuário →
API Token → Reopen).

## Decisão

1. Nova marca de conexão **`GROWATT_TOKEN`** (`providers/growatt/openapi.py`), recomendada na
   tela. O token vai no lugar da senha: cifrado como ela (ADR-091) e nunca devolvido nem gravado
   em log ou auditoria.
2. Endpoints: `plant/list` (usinas → aparelhos `GW-PLANT-<id>`, como no cliente clássico),
   `plant/energy` por dia (no máximo 7 dias por consulta, partido em janelas), `plant/data` e
   `plant/details` (cadastro para o preenchimento automático da ADR-093 § 7; `peak_power` em
   kW). Códigos: `10011` = token recusado; `10012` ou HTTP 429 = esperar.
3. O "login" de uma conexão por token é um identificador aleatório (`token-<16 hex>`), gerado
   no servidor a cada conexão. O token não passa por hash nenhum. A mesma usina Growatt em duas
   usinas do MPlacas é barrada pelos aparelhos `GW-PLANT-<id>`, que conferem senha e token juntos.
   O token é recusado (422) se tiver espaço interno, quebra de linha ou caractere fora do ASCII
   visível.
4. No cliente clássico, 401/403 **no login** vira `ProviderBlockedError` →
   `provider_login_blocked` (503), com mensagem que diz que não é a senha e aponta o token.
   Recusa por senha errada continua como `provider_login_failed`. O bloqueio herda de
   `ProviderAuthError`: a coleta não repete na hora e espera 1 h. No token, só a recusa do token
   vira `provider_token_failed`; resposta fora do formato vira `provider_unavailable`, para o
   cliente não gerar um token novo à toa. A lista de usinas é paginada e nunca truncada.
5. Origem gravada na produção: `GROWATT_OPENAPI_V1`.

## Consequências

- Cliente Growatt conecta sem depender da API do app.
- O usuário e senha da Growatt continuam disponíveis para quem consegue usar, mas deixam de ser
  o caminho padrão.
- A mesma usina conectada antes por senha e depois por token gera aparelhos com marcas diferentes
  (`GROWATT` × `GROWATT_TOKEN`); trocar de modo numa usina com histórico fica para quando
  acontecer.
- O formato das respostas segue a documentação da Growatt e a biblioteca de referência
  (`growattServer`, OpenApiV1). É preciso confirmar com o primeiro token real.
