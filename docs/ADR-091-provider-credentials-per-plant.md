# ADR-091 — Credencial do inversor por usina, cifrada no banco

## Status

**Aceito e implementado — 2026-10-29.** Pré-requisito para o 2º cliente. Decisões tomadas pelo
projetista por delegação do dono. Fases 1–7 entregues em #252–#258; a conta da usina do dono foi
importada e a coleta pela conexão nova foi conferida em produção (29/10, 2 inversores) antes de
remover o caminho antigo.

## Contexto

A coleta de produção usa **uma** conta NEPViewer global, em `MPLACAS_NEP_ACCOUNT` /
`MPLACAS_NEP_PASSWORD` (segredos do GitHub Actions, ADR-047), e grava tudo na usina
`MPLACAS_CLOUD_JOB_PLANT_NAME`, dentro da organização default
(`SolarCollectionService._get_or_create_plant`). O próprio `cloud_jobs.run_collection` documenta
por que a coleta não é feita para cada usina: a conta lista os inversores sem dizer de qual usina
são, e repetir a coleta por usina gravaria os mesmos dados em todas.

Com um segundo cliente, mesmo da mesma marca, isso quebra de três formas:

1. não há onde guardar a senha dele sem criar um segredo de CI à mão por cliente;
2. a coleta só conhece uma usina;
3. `devices` é único por `(provider, serial_number)` e `_get_or_create_device` devolve o
   inversor existente **sem conferir a usina**: um número de série repetido entre contas
   gravaria produção de um cliente na usina de outro.

Diferente da credencial de API (ADR-043), aqui o segredo **precisa ser recuperado** em texto
claro para entrar na API do fabricante. Hash não serve; é preciso cifra reversível.

## Decisão

1. **Uma conexão por usina.** Nova tabela `provider_accounts`, com `plant_id` único (FK
   `plants`, `ON DELETE CASCADE`) e RLS no escopo `PLANT` (`rls_inventory`). Uma conta do
   fabricante mede uma usina; usina com duas marcas fica fora do escopo até aparecer o caso.
   Colunas: `provider` (`NEPVIEWER`), `login_hint` (login mascarado, ex. `we***@gmail.com`),
   `account_fingerprint` (HMAC-SHA256 do login normalizado), `ciphertext`, `key_version`,
   `active`, `created_at`, `rotated_at`, `last_success_at`, `last_failure_at`,
   `last_failure_code` (nome da classe do erro, nunca a mensagem do fabricante).
2. **Cifra AES-256-GCM** (biblioteca `cryptography`, da PyCA — dependência nova, com hash no
   `requirements.lock`). O texto cifrado leva login e senha juntos; o nonce de 96 bits é
   aleatório por gravação. O dado associado (AAD) amarra o texto cifrado a
   `plant_id`, `provider` e `key_version`: copiar a linha para outra usina faz a decifragem
   falhar.
3. **A chave fica fora do banco**, em `MPLACAS_PROVIDER_SECRET_KEYS`, no formato
   `1:<base64 de 32 bytes>,2:<...>`. A versão de maior número cifra; as demais só decifram,
   o que permite trocar a chave e recifrar com um comando (`rotate-provider-secrets`). A mesma
   variável vai para os segredos do GitHub Actions (coleta) e para o Render (API, que cifra ao
   salvar). Sem a chave, a API recusa salvar (503) e a coleta falha com erro claro — nunca grava
   em texto claro.
4. **Mesma conta em duas usinas é recusada.** `account_fingerprint` é único por `provider`. O
   HMAC usa uma subchave derivada da chave atual (HKDF), então o login não aparece nem como
   hash simples. Ao trocar a chave, o comando de rotação recalcula as impressões.
5. **Coleta por usina.** `run_collection` percorre as usinas com conexão ativa; para cada uma,
   decifra, monta o provedor resiliente (ADR-047), coleta e fecha o cliente. Uma usina que falha
   não interrompe as outras (mesma regra do `run_daily_pipeline`, ADR-069). A fila de nova
   tentativa já guarda `plant_id`; o `drain` passa a montar o provedor da usina da tarefa.
   `SolarCollectionService` recebe a usina pelo id e não cria mais usina por nome.
6. **Inversor não troca de usina.** Se o número de série já existe em outra usina,
   `_get_or_create_device` recusa (`ProviderDeviceConflictError`), a coleta daquela usina para,
   e o erro aparece no registro da execução. Mover inversor entre usinas é operação manual.
7. **Cadastro só por ADMIN da organização**, em `PUT /plants/{plant_id}/provider-account`
   (login e senha só na entrada), `GET` (só `provider`, `login_hint`, estado e datas) e
   `DELETE` (desativa e apaga o texto cifrado). Antes de salvar, o servidor entra na conta e
   lista os inversores: senha errada não é guardada. Gravação e remoção vão para a auditoria
   (`provider_account.saved` / `provider_account.removed`) sem login nem senha. Erros devolvidos
   são genéricos (`provider_login_failed`, `provider_unavailable`).
8. **Tela em "Minha usina"**: bloco "Conexão com o inversor" com o estado (conectado, última
   leitura, falha), e formulário de (re)conexão. A senha nunca volta do servidor, o campo nunca
   vem preenchido e nada vai para `localStorage`/`sessionStorage` (skill `secret-safe-ui`).
9. **Transição sem parar a coleta** (histórico: usada em 29/10/2026 e removida na fase 7). O comando `import-provider-account --plant-name <nome>`
   copia `MPLACAS_NEP_ACCOUNT`/`MPLACAS_NEP_PASSWORD` para a usina indicada, uma vez, por
   `workflow_dispatch`. Enquanto nenhuma usina tiver conexão, a coleta segue pelo caminho antigo
   com aviso no log. Depois da importação confirmada, um PR final remove as variáveis `NEP_*`,
   `MPLACAS_CLOUD_JOB_PLANT_NAME` da coleta e o caminho antigo.

## Fases (um PR cada)

| # | Escopo | Revisão |
|---|---|---|
| 1 | Este ADR | dono |
| 2 | `cryptography` + `core/secret_box.py` (chaveiro, cifra com AAD, impressão do login) + configuração + testes | reviewer |
| 3 | Modelo, migration, RLS, serviço `ProviderAccountService`, comandos de importação e rotação | reviewer |
| 4 | Coleta por usina (job, drain, cloud_jobs, workflows), proteção do inversor, caminho antigo como reserva | reviewer |
| 5 | Rotas de ADMIN, verificação antes de salvar, auditoria | reviewer |
| 6 | Bloco "Conexão com o inversor" em Minha usina | quality-gate-reviewer |
| 7 | Remover o caminho antigo, depois da importação | reviewer |

Fase 7 (feita): `MPLACAS_NEP_ACCOUNT`/`MPLACAS_NEP_PASSWORD`, o comando `import-provider-account`
e a coleta por nome de usina saíram; o workflow `provider-accounts` só rotaciona a chave. Usina sem
conexão não é coletada. `MPLACAS_CLOUD_JOB_PLANT_NAME` continua para os outros jobs.

Passo do dono entre as fases 2 e 4: gerar a chave e gravá-la como `MPLACAS_PROVIDER_SECRET_KEYS`
no GitHub e no Render; rodar a importação depois da fase 4.

## Consequências

### Positivas

- Cliente novo se conecta sem mexer em segredo de CI nem em código.
- Isolamento entre clientes coberto por RLS, pelo AAD da cifra e pela proteção do inversor.
- A interface `SolarProvider` (ADR-047) não muda: outra marca vira só outro valor de `provider`
  e outra fábrica (ver `claude/integracoes-inversores.md`).

### Negativas

- Dependência nova (`cryptography`, com binário compilado) e uma chave a mais para guardar. Se a
  chave se perder, todas as conexões precisam ser refeitas pelos clientes; o backup do banco não
  basta sozinho.
- Quem tem a chave e o banco lê as senhas. Um cofre externo (KMS) reduziria isso, mas o projeto
  saiu do Google Cloud e não tem um hoje; a chave em variável é o mesmo nível de proteção que a
  senha global tem agora, só que por cliente.
- A verificação antes de salvar faz uma entrada na conta do fabricante a cada gravação.
- Usina com mais de uma marca de inversor não é atendida até aparecer o caso.

## Validação

- Testes do cofre: ida e volta, AAD de outra usina falha, chave antiga decifra e a nova cifra,
  chave ausente falha fechado, nenhum segredo em `repr`/log.
- Migration com `upgrade`/`downgrade`/`upgrade` e inventário de RLS atualizado.
- Coleta: duas usinas com contas diferentes gravam cada uma só os seus inversores; inversor
  repetido entre usinas é recusado; usina com falha não para as outras.
- Contrato de frontend: nenhuma resposta contém senha; teste de guarda existente
  (`test_frontend_auth_contract.py`) segue verde.

## Reversibilidade

Até a fase 7, o caminho antigo continua funcionando: basta desativar as conexões
(`active = false`) para a coleta voltar às variáveis `NEP_*`. Trocar a cifra local por um KMS
mexe só em `core/secret_box.py` e no comando de rotação; a tabela já guarda `key_version`.
