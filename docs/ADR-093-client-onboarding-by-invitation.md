# ADR-093 — Cliente novo entra por convite do dono

## Status

**Aceito — 2026-10-31.** Decisão do dono: qualquer usuário Growatt (ou NEPViewer) pode virar
cliente, mas **só por convite**; o dono controla quem entra. Depende das ADR-054 (organizações e
convites), ADR-091 (conexão por usina) e ADR-092 (Growatt).

## Contexto

Levantamento de 31/10/2026: o caminho de um cliente novo tinha quatro buracos.

1. Organização só era criada com a chave de operação (`POST /organizations`), sem tela.
2. O convite era gerado (`/auth/invitations/inspect` e `/accept` já existiam), mas não havia
   tela para o cliente abrir o link e criar a senha.
3. Não havia como criar a usina: sem usina, Minha usina só dizia "Nenhuma usina cadastrada".
4. A análise diária e o vigia rodavam só para as usinas da organização default (ADR-069 § E9).

## Decisão

1. **Operador da plataforma** = a chave de operação **ou** um ADMIN da organização default (a do
   dono). Nova dependência `PlatformOperator` em `core/tenancy.py`; nenhuma rota de inquilino muda.
2. **`/platform/clients`** (só operador):
   - `GET`: lista as organizações-clientes (sem a default) com usinas, conexão e convite pendente.
   - `POST {name, admin_username}`: cria a organização (slug derivado do nome) e o convite de
     ADMIN; devolve o **token do convite uma única vez**, para o dono montar o link.
   - `POST /{organization_id}/invitation`: novo convite para o ADMIN quando o anterior venceu;
     revoga só os convites de ADMIN pendentes (os que o cliente fez para a equipe dele ficam).
   Respostas com token levam `Cache-Control: no-store`.
   Tudo auditado (`platform.client_created`, `platform.client_invited`), sem o token.
3. **`GET /auth/me`**: usuário, papel, nome da organização e se é operador — para a tela mostrar
   "Clientes" só ao dono e esconder escrita de quem não é ADMIN.
4. **A usina nasce da conexão, não de um formulário** (decisão do dono, 31/10): o cliente não
   sabe os dados técnicos da própria usina. Detalhes na seção 7.
5. **Análise diária e vigia** passam a rodar para as usinas da organização default **mais** as
   usinas de outras organizações com conexão ativa (sem conexão não há produção a analisar).
   Alerta por Telegram: só as usinas do dono usam o chat de plataforma; para usina de cliente a
   análise roda sem expectativa diária, o que pula o passo de alerta — dado de cliente não vai
   para o chat do dono. O vigia não acusa usina de cliente que ainda espera a primeira análise;
   falha real (análise que falhou, travou ou atrasou) de qualquer usina, inclusive de cliente,
   continua derrubando o job — o dono é o operador e precisa saber, e a mensagem do agendador
   traz nome e id da usina. Alerta para o próprio cliente (pelo `telegram_chat_id` da organização)
   fica para depois.
6. Tela (PR seguinte): página **/convite** (token no fragmento `#`, nunca na URL enviada ao
   servidor), primeira conexão (escolher a marca, usuário e senha do app) e página **Clientes**
   do dono, com o link para copiar e mandar ao cliente.

7. **Primeira conexão e preenchimento automático** (PR B):
   - `POST /plants/connect` (ADMIN da organização; só se a organização ainda não tem usina):
     confere a conta na marca, cria a usina, marca como padrão e guarda a conexão. Teto de 5
     conferências por organização a cada 10 min, como o da usina. Recusa e sucesso auditados
     sem login nem senha. Rechecagem com a organização travada: dois cliques não criam duas
     usinas.
   - Na mesma sessão de login (a Growatt bloqueia excesso de logins) o sistema lê o cadastro da
     usina na marca. Growatt: `newPlantAPI.do?op=getPlant` da maior usina da conta (nome,
     potência em W, latitude/longitude, cidade). NEPViewer: só a cidade dos inversores; as
     coordenadas vêm da geocodificação da cidade no Open-Meteo, feita **antes** de abrir a
     transação. Falha ao ler o cadastro nunca derruba a conexão.
   - Só campo **vazio** é preenchido, também ao reconectar uma usina existente; o que o dono
     informou nunca muda. Potência nunca é estimada. **Data de ligação nunca é preenchida**:
     a `createDateText` da Growatt é a data do cadastro na nuvem, e a data real decide o
     regime da Lei 14.300 e o retorno do investimento.
   - Para destravar a produção esperada, onde há localização: inclinação ≈ latitude (entre
     10° e 30°), painéis voltados para o equador (azimute 0° no hemisfério sul) e módulo
     monocristalino.
   - Cada campo preenchido assim fica em `plants.auto_filled` (`BRAND` = veio da marca,
     `ESTIMATE` = estimado), campo a campo (inclinação e azimute separados), exposto em "Dados
     da usina". Item do checklist preenchido por estimativa conta como feito, mas vem com
     `needs_review` para a tela pedir conferência. Quando o dono edita o campo, a marca some.
   - Limites conhecidos: o teto de conferências não é atômico (dois cliques simultâneos podem
     gerar dois logins na marca; a usina continua única); o escopo de usina não se aplica à
     rota porque a organização ainda não tem usina.

## Consequências

### Positivas

- Cliente novo vai do convite à produção sem comando técnico: cria a senha, escolhe a marca e
  conecta; a usina aparece sozinha.
- O dono continua decidindo quem entra.

### Negativas

- Todo ADMIN da organização default vira operador, mesmo com acesso restrito a uma usina:
  convidar alguém como ADMIN na própria organização do dono dá a ele poder de ver e criar
  clientes.
- O link de convite é um segredo de uso único (validade de 3 dias, `MPLACAS_AUTH_INVITATION_TTL_SECONDS`):
  quem o receber antes do cliente cria a senha. O dono deve mandá-lo só ao cliente.
- Estimativas (inclinação, orientação, módulo, coordenadas pela cidade) podem errar a produção
  esperada em alguns por cento até o dono conferir. Por isso ficam marcadas e a tela pede
  conferência.
- O cadastro da Growatt veio de biblioteca de referência, não de documentação oficial; campo
  ausente vira vazio, nunca erro. Confirmar com o primeiro cliente real.
- Por ora o cliente não recebe alerta automático; vê tudo no painel. O dono também não recebe
  alerta das usinas dos clientes (de propósito).

## Validação

- Testes: operador vs. ADMIN de cliente (403), criação com slug repetido, novo convite revoga o
  anterior, token fora da auditoria, `/auth/me`, fan-out da análise e do vigia com usina
  conectada de outra organização (sem rodar duas vezes e sem alerta), e só conexão ativa conta.
- PR B: leitura tolerante (potência da Growatt sempre em W, coordenada 0 ou fora da faixa),
  Growatt sem envelope e maior usina, falha no cadastro sem derrubar a conexão, NEPViewer pela
  cidade, não sobrescrever, sem data de ligação, estimativas campo a campo, `needs_review`,
  edição do dono removendo a marca, primeira conexão (cria e preenche, 409 se já há usina, senha errada não
  cria nada, teto por organização, só ADMIN, inversor de outra usina) e migração ida e volta.
