# ADR-044 - Usuários operacionais nomeados com expiração de credenciais

## Status

Aceito.

## Contexto

O ADR-043 introduziu credenciais persistidas com papéis e escopo por usina (Fase 1 da evolução
RBAC). As credenciais, porém, não tinham dono identificável nem prazo de validade: revogar o acesso
de uma pessoa exigia conhecer e revogar cada credencial individualmente, e credenciais esquecidas
permaneciam válidas para sempre. Esta é a Fase 2 planejada naquele ADR.

## Decisão

1. Nova tabela `operational_users`: nome único, estado ativo e carimbo de desativação
   (migration `20260719_0014`).
2. `api_credentials` ganha `user_id` opcional (chave estrangeira) e `expires_at` opcional.
   Credenciais sem usuário continuam válidas, preservando compatibilidade com a Fase 1.
3. A resolução de credenciais rejeita, além de revogadas: credenciais expiradas
   (`expires_at` no passado, comparação em UTC) e credenciais cujo usuário está desativado.
4. Desativar um usuário bloqueia imediatamente todas as suas credenciais, em uma única ação,
   sem alterar os registros das credenciais (a desativação é do usuário; reativação futura
   voltaria a honrar as credenciais não revogadas e não expiradas).
5. A criação de credencial valida que a expiração esteja no futuro e que o usuário associado
   exista e esteja ativo.
6. Endpoints administrativos em `/operations/users` (criar, listar, desativar), restritos ao
   papel `ADMIN` irrestrito, com eventos `users.create` e `users.deactivate` na trilha de
   auditoria.

## Consequências

### Positivas

- Desligamento de uma pessoa vira uma única operação auditável, sem caça a credenciais.
- Credenciais com prazo eliminam acessos esquecidos de longa duração.
- A trilha de auditoria pode correlacionar ações a um dono nomeado via `user_id` da credencial.

### Negativas

- A resolução de credenciais persistidas carrega o usuário associado (join), um custo pequeno
  e limitado ao caminho de fallback.
- Não há rotação in-place nem reativação de usuário por endpoint nesta fase.

## Fase seguinte planejada

- Fase 3: tenants e claims, com escopo de usina derivado do tenant do usuário.

## Validação

- credencial expirada deixa de autenticar; expiração no passado é rejeitada na criação;
- desativar usuário bloqueia todas as suas credenciais e preserva credenciais órfãs;
- regras de domínio de usuário (nome único e obrigatório, usuário inexistente ou inativo);
- ciclo de vida completo por endpoints com auditoria e exigência de `ADMIN`;
- contrato da migração `20260719_0014` presente e encadeado.
