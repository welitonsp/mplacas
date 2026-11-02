# ADR-095 — Clientes como CRM do dono: ficha, redefinir acesso, desativar

## Status

**Aceito — 2026-11-02.** Pedido do dono depois do primeiro cliente real. Estende a ADR-093.

## Contexto

O primeiro cliente aceitou o convite, mas depois não conseguia entrar: 5 tentativas recusadas em
02/11. O sistema não tinha recuperação de acesso. Para quem já aceitou, o botão "Novo convite"
some, e o dono ficava sem ação nenhuma, a não ser refazer o cadastro. O dono pediu para tratar
isso dentro do sistema, "como nos CRMs".

## Decisão

1. **Etapa do cliente**, decidida no backend (`clients/router.py::_stage`), na ordem do funil:
   `CONVIDADO`, `CONVITE_VENCIDO`, `ENTROU`, `USINA_CONECTADA`, `RECEBENDO_DADOS`, `COM_FALHA`,
   `DESATIVADO`. Aparece na lista e na ficha.
2. **Ficha** (`GET /platform/clients/{id}`, só operador): usuários, usina, conexão (marca,
   última leitura, última falha), link pendente e histórico. O histórico traz os eventos de
   auditoria da organização, numa lista fechada de ações, com só os campos seguros dos detalhes
   (`provider`, `reason`, `devices_found`, `auto_filled`). Nunca traz token, senha ou login.
3. **Redefinir acesso** (`POST /platform/clients/{id}/access-reset`): link de uso único com o
   mesmo mecanismo do convite. A tabela `user_invitations` ganha `purpose` (`INVITE` | `RESET`,
   migração `20261102_0053`, padrão `INVITE`). Ao aceitar um `RESET`, a senha do usuário
   existente é trocada, todas as sessões dele são encerradas e uma nova é aberta. Auditoria:
   `platform.client_access_reset` e `invitations.access_reset`. Só para quem já entrou; para quem
   não entrou continua "Novo convite", que agora considera só links `INVITE`.
4. **Desativar / reativar** (`POST .../deactivate`, `.../reactivate`): usa o desligamento de
   organização que já existe (encerra sessões; o login já recusa organização inativa). Cliente
   desativado sai da coleta, da análise diária e do vigia. Nada é apagado.
5. **Tela**: a lista mostra a etapa de cada cliente e um botão "Abrir ficha". A ficha traz as
   ações e o histórico em português, com o motivo das recusas traduzido. A página `/convite`
   muda o texto quando o link é de redefinição ("Crie uma senha nova").

## Consequências

- O dono resolve sozinho "esqueci a senha" e acompanha em que etapa cada cliente está, sem
  precisar do suporte técnico.
- O histórico depende do que é auditado. Tentativas de login com senha errada não são
  auditadas hoje (ficam só no log), então não aparecem na ficha.
- A redefinição encerra as sessões (refresh tokens). O token de acesso que já estiver emitido
  continua válido até expirar (prazo curto do JWT). Isso não importa para quem esqueceu a senha;
  importa para quem redefine porque o acesso vazou, e nesse caso o caminho é desativar o cliente.
- O link de redefinição vale para o primeiro ADMIN ativo da organização (hoje cada cliente tem
  um).
- O próprio cliente ainda não pode pedir "esqueci a senha" na tela de login. Isso exigiria envio
  de e-mail, que o sistema não tem.
