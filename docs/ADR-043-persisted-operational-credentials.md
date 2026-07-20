# ADR-043 - Credenciais operacionais persistidas com papéis e escopo por usina

## Status

Aceito.

## Contexto

A autenticação operacional dependia de duas chaves fixas em variáveis de ambiente
(`MPLACAS_OPERATIONS_API_KEY` e `MPLACAS_OPERATIONS_READ_API_KEY`), com escopo de usina definido
por configuração. A auditoria técnica profunda de 16/07/2026 classificou como P1 a evolução para
usuários/tenants/claims. Esta é a Fase 1 dessa evolução: mover as credenciais para o banco, com
papéis, escopo por usina, revogação individual e auditoria, sem quebrar a compatibilidade.

## Decisão

1. Nova tabela `api_credentials`: nome único, papel (`ADMIN`/`READ`), hash SHA-256 do segredo,
   escopo opcional de usinas, estado ativo e carimbo de revogação.
2. O segredo em texto claro é gerado pelo servidor (`secrets.token_urlsafe`), exibido uma única vez
   na resposta de criação e nunca persistido, registrado em log ou recuperável.
3. A autenticação tenta primeiro as chaves de ambiente (inalteradas) e, apenas em caso de 401 com
   credencial apresentada, resolve o segredo contra o banco por hash. Falha fechada permanece: sem
   chave administrativa de ambiente configurada, o serviço responde 503.
4. As chaves de ambiente permanecem como credenciais raiz de bootstrap: são necessárias para criar
   a primeira credencial persistida e continuam funcionando indefinidamente.
5. Endpoints administrativos em `/operations/credentials` (criar, listar, revogar), restritos ao
   papel `ADMIN` sem restrição de usina. Criação e revogação geram eventos `credentials.create` e
   `credentials.revoke` na trilha de auditoria, sem segredos nos detalhes.
6. Regras de domínio: credencial `ADMIN` não pode ser restrita por usina; escopo restrito exige ao
   menos uma usina; nomes são únicos.
7. O `credential_id` de principals persistidos usa o formato `credential:<uuid>`, distinguível do
   formato `operations:<papel>:<fingerprint>` das chaves de ambiente na trilha de auditoria.

## Consequências

### Positivas

- Credenciais individuais por consumidor, com revogação imediata sem redeploy.
- Escopo por usina definido por credencial, não mais por configuração global.
- Trilha de auditoria identifica qual credencial executou cada ação sensível.
- Caminho aberto para as próximas fases (usuários, tenants e claims) sem nova quebra.

### Negativas

- Autenticação com credencial persistida adiciona uma consulta ao banco por requisição
  não atendida pelas chaves de ambiente.
- A rotação do segredo exige revogar e criar nova credencial (sem rotação in-place nesta fase).

## Fases seguintes planejadas

- Fase 2: usuários nomeados com credenciais associadas e expiração.
- Fase 3: tenants e claims, com escopo de usina derivado do tenant.

## Validação

- hash como único armazenamento do segredo; resolução apenas por hash de credencial ativa;
- revogação bloqueia autenticação imediatamente;
- regras de domínio (nome único, escopo não vazio, admin sem restrição) cobertas por testes;
- endpoints exigem papel `ADMIN` irrestrito; segredo aparece apenas na criação;
- fallback de autenticação comprovado ponta a ponta em endpoint real;
- contrato de migração presente e encadeado à revisão anterior.
