# ADR-070 — Módulo de integrações e credenciais multi-fornecedor: registrado no roadmap, não implementado agora

## Status

**Aceito — 2026-08-07.** A decisão aceita é a de **não implementar agora** e registrar a ordem de
pré-requisitos e o gatilho objetivo de reabertura. Este ADR não é uma proposta pendente de
aprovação: a decisão foi tomada pelo usuário na sessão de 2026-08-07, depois do fact-check dos dois
documentos externos contra o código real.

Uma pergunta de modelo de negócio permanece **explicitamente em aberto** e é bloqueante para
qualquer desenho técnico de "Cliente" — ver § *Decisão em aberto (requer o usuário)*. O ADR está
aceito **com** essa pergunta em aberto, porque a decisão registrada aqui é justamente "não desenhar
enquanto ela não for respondida".

## Contexto

O usuário recebeu dois documentos externos — *"Análise Frontend e Concorrência CADASTRO DE
FORNECEDORES PLACAS.pdf"* e *"Análise Frontend e Concorrência.pdf"* — propondo um **Módulo de
Integrações e Credenciais de Fornecedores**. Em resumo, os documentos propõem:

1. Um **hub multi-fornecedor de telemetria**: o Mplacas passaria a ler dados de vários fabricantes
   de inversor/monitoramento, não só de um.
2. Uma **tela de UI de Integrações**, onde se cadastra credencial de fornecedor **por cliente**.
3. Um **catálogo de provedores** apresentado na interface, com o cliente escolhendo de qual
   fornecedor quer conectar sua usina.

A ideia é legítima e é para onde um produto de monitoramento maduro tende. O que este ADR registra
não é uma rejeição do destino, e sim uma decisão de **sequenciamento**: hoje o repositório está a
três frentes de distância de conseguir sustentar essa promessa, e uma delas nem sequer é técnica.

Os documentos foram fact-checados contra o repositório na mesma sessão (metodologia de
`.claude/skills/repository-ground-truth/`: nenhuma afirmação sem caminho de arquivo e símbolo). A
tabela abaixo é o resultado desse fact-check, reconferido no código ao redigir este ADR.

### Tabela de evidência — proposta vs. estado real do código

| # | Proposta dos PDFs | Estado real, verificado | Evidência (arquivo:linha, símbolo) |
|---|---|---|---|
| 1 | Hub com N fornecedores de telemetria | **Um único fornecedor implementado: NEPViewer.** Não existe segundo adaptador, nem esqueleto de segundo adaptador | `src/mplacas/providers/` contém apenas `base.py`, `resilient.py` e `nepviewer/{client,factory}.py` |
| 2 | Abstração de provedor pronta para receber N fornecedores | Existe uma ABC, mas com **três métodos** e desenhada olhando um fornecedor só. `SolarDevice` **não carrega identificador de usina física** | `src/mplacas/providers/base.py:55-70` — `SolarProvider.list_devices/get_overview/get_daily_energy`; `SolarDevice` em `base.py:32-37` (`serial_number`, `model_name`, `city`, `last_update`) |
| 3 | Credencial **por cliente**, por fornecedor | Credencial **única e global por instalação**, injetada por variável de ambiente / Secret Manager. Não há credencial por organização, por usina nem por cliente | `src/mplacas/core/config.py:39-40` (`nep_account`, `nep_password: SecretStr`), consumidas em `src/mplacas/collection/job.py:33-38` e `src/mplacas/collection/drain.py:28-31`; `.env.example:19-20`; `infra/gcp/set-secrets.sh:150-156` |
| 4 | Cofre de credenciais de fornecedor | **Existe um cofre, mas é a primitiva oposta.** `api_credentials` guarda credencial de **entrada** (a API key com que terceiros chamam o Mplacas) como **hash SHA-256 irreversível** | `src/mplacas/credentials/db_models.py:46-84` — `ApiCredentialRecord.key_hash: Mapped[str] = mapped_column(String(64), ...)`; router com prefixo `/operations/credentials` (`credentials/router.py:22`) |
| 5 | Tela de Integrações na UI | **Não existe.** O frontend tem exatamente duas rotas e duas páginas | `frontend/src/App.tsx:14-28` (`/login`, `/dashboard`, catch-all); `frontend/src/pages/` contém apenas `LoginPage.tsx` e `DashboardPage.tsx` |
| 6 | Entidade "Cliente" e entidade "Fornecedor" no banco | **Nenhuma das duas existe.** Não há classe `Customer`/`Client`/`Cliente`/`Installer`/`Integrator` em todo `src/mplacas/`. `provider` é uma **string livre** de 40 caracteres, sem tabela de catálogo, sem enum, sem `CheckConstraint` | `src/mplacas/db/models.py:126` — `provider: Mapped[str] = mapped_column(String(40), default="NEPVIEWER")`; hierarquia de tenancy real é `Organization → Plant → Device` (`organizations/db_models.py:14`, `db/models.py:38,107`) |
| 7 | Vínculo device ↔ usina que suporte N provedores por usina | O vínculo existe (`Device.plant_id`), mas a **unicidade de dispositivo é global à instalação**, não por organização, e a resolução de device **ignora a usina** | `src/mplacas/db/models.py:110` — `UniqueConstraint("provider", "serial_number")`, **sem** `organization_id`/`plant_id`; `Device` não possui coluna `organization_id`; `src/mplacas/services/collection.py:121-127` — `select(Device).where(Device.provider == "NEPVIEWER", Device.serial_number == serial_number)`, **sem filtro de usina** |
| 8 | Descoberta automática das usinas de uma conta de fornecedor | **Impossível hoje.** Todos os dispositivos da conta caem numa **única** usina resolvida por configuração estática de plataforma | `src/mplacas/services/collection.py:110-116` — `_get_or_create_plant` usa `settings.cloud_job_plant_name` sob `DEFAULT_ORGANIZATION_ID`; formalizado como exceção deliberada no ADR-069 § E9 (`run_collection` fica fora do fan-out) |
| 9 | UX de cadastro de segredo já normatizada | **Já normatizada, mas nunca exercitada** — não há nenhuma tela de segredo além do login | `.claude/skills/secret-safe-ui/SKILL.md` (segredo nunca retornado após cadastro; só substituir/revogar; erro de terceiro sanitizado); `.claude/skills/provider-integrations/SKILL.md` já registra a limitação de conta única/global |

**Leitura da tabela:** os itens 1, 3, 5 e 6 são *gap real* — o que os PDFs propõem simplesmente não
existe. Os itens 2, 4 e 9 são *falso conforto*: existe algo com o nome certo (uma abstração de
provedor, um cofre de credenciais, uma skill de UX de segredo), mas nenhum dos três resolve o
problema que o PDF assume resolvido. Os itens 7 e 8 são o achado mais importante deste ADR, e são a
razão da ordem escolhida na próxima seção.

### Achado que define a ordem: a identidade de dispositivo é global e "primeiro que gravar leva"

Este é o achado que muda o desenho, e vale a pena isolá-lo:

```
UniqueConstraint("provider", "serial_number")          # src/mplacas/db/models.py:110
```

```python
result = await self._session.execute(                   # src/mplacas/services/collection.py:121-127
    select(Device).where(
        Device.provider == "NEPVIEWER",
        Device.serial_number == serial_number,
    )
)
```

A constraint não é escopada por organização nem por usina, e a consulta de resolução não filtra por
usina. Consequências, hoje, **antes** de qualquer multi-fornecedor:

- Dois clientes distintos (duas organizações) cujos inversores tenham o mesmo número de série do
  mesmo fornecedor **colidem**: o segundo não cria um `Device` próprio, ele **reusa o `Device` da
  outra organização**, e a energia diária do segundo passa a ser gravada sob a usina do primeiro.
  `daily_energy` é chaveada por `UniqueConstraint("device_id", "production_date")`
  (`db/models.py:143-146`) — não há segunda linha possível para o mesmo dia.
- A tabela `devices` está sob RLS por **usina** (`RlsTable(RlsScope.PLANT, "plant_id")` em
  `src/mplacas/db/rls_inventory.py`), o que protege a *leitura* entre tenants — mas a colisão acima
  acontece no caminho de *escrita* da coleta, que roda sob contexto de plataforma.

Multi-fornecedor **multiplica** essa superfície em vez de introduzi-la: o caso mais provável de um
hub real é o mesmo inversor físico sendo exposto por dois portais diferentes (troca de fornecedor,
período de sobreposição), e com o modelo atual isso vira ou dupla contagem em dois `Device`
distintos da mesma usina, ou dois provedores disputando a mesma linha de `daily_energy`.

Este bug **não é criado nem resolvido por este ADR**. Ele existe hoje, é latente (só é alcançado com
duas organizações reais e serial repetido) e está registrado aqui como o primeiro item da fila —
explicitamente **não bloqueado** pelo gatilho de reabertura: pode e provavelmente deve ser corrigido
antes dele, como tarefa própria. Por tocar em migration, exige `reviewer` (ver `CLAUDE.md`) e
confirmação do usuário quanto à mudança de schema.

## Decisão

### 1. O módulo de integrações e credenciais multi-fornecedor **não é implementado agora**

Nenhum código, nenhuma migration, nenhum endpoint, nenhuma tela. A decisão vale até que o gatilho da
§ 4 dispare.

A razão não é "não é útil" — é que generalizar sobre uma amostra de tamanho um é adivinhação. A ABC
`SolarProvider` de hoje foi escrita olhando o NEPViewer, e o formato dela já carrega hipóteses do
NEPViewer que ninguém testou contra outro fornecedor (ver Consequências negativas). O momento certo
de descobrir quais dessas hipóteses são falsas é quando o segundo fornecedor real estiver em mãos,
não antes.

### 2. Ordem de pré-requisitos: três frentes, em série, nesta ordem

Quando o gatilho disparar, esta é a ordem. Elas são **em série** porque cada uma consome uma decisão
da anterior.

**Pré-requisito A — identidade de dispositivo e vínculo device ↔ usina física.**
Antes de suportar múltiplos provedores por usina, é preciso que "qual dispositivo é este e a qual
usina ele pertence" tenha resposta única e correta. Escopo mínimo:

- Escopar `UniqueConstraint("provider", "serial_number")` por organização (ou pela conta de provedor
  que o originou), e fazer `_get_or_create_device` filtrar pela usina/organização de destino
  (`services/collection.py:118-139`).
- Decidir o que acontece quando o **mesmo dispositivo físico** é visto por **dois provedores** — se
  são dois `Device` (e então `daily_energy` precisa de política de precedência/deduplicação) ou um
  `Device` com origem de dado variável (e então `DailyEnergy.source`, `db/models.py:157`, vira parte
  da chave de reconciliação, não um rótulo).
- Resolver a descoberta de usina: enquanto `SolarDevice` (`providers/base.py:32-37`) não trouxer
  nenhum campo de usina física, a coleta não sabe separar duas usinas na mesma conta — é a razão
  documentada da exceção do ADR-069 § E9.

*Sem A, multi-fornecedor herda um bug de unicidade global e o transforma em corrupção de dado de
produção.* Este é o pré-requisito de **correção**, e é o único que faz sentido tocar antes do
gatilho.

**Pré-requisito B — cofre de credenciais de saída, por tenant.**
Antes de qualquer tela que **colete um segredo**, é preciso existir onde guardá-lo. O cofre atual
não serve, e a razão é estrutural, não de esforço:

| | Credencial de **entrada** (existe hoje) | Credencial de **saída** (o que falta) |
|---|---|---|
| Quem autentica quem | Terceiro → Mplacas | Mplacas → fornecedor |
| Armazenamento | Hash SHA-256, **irreversível** (`credentials/db_models.py:66`) | Precisa ser **recuperável** em texto claro no momento da chamada |
| Exibição | Uma vez, na criação, nunca mais | Nunca, nem na criação |
| Rotação | Revoga e emite outra | Substitui, e a substituição precisa ser testada contra o fornecedor antes de valer |

Portanto B é um ADR próprio, cuja decisão central é **onde o segredo mora**: Secret Manager com um
segredo por tenant (isola de verdade, custa uma chamada de API e uma cota do GCP por tenant) versus
coluna cifrada com envelope encryption via KMS (barato e transacional, mas coloca ciphertext no
mesmo Postgres que já está sob RLS — e RLS não é confidencialidade contra quem tem a conexão). Não
decidir isso agora é deliberado.

Restrições que **já estão formalizadas no projeto** e que B tem de honrar, sem renegociação:

- `.claude/skills/secret-safe-ui/SKILL.md`: segredo nunca retornado pela API após o cadastro — a UI
  mostra apenas "configurado"/status; substituir e revogar são as **únicas** ações sobre um segredo
  já salvo; erro de terceiro sanitizado antes de chegar à UI; nada em `localStorage`/`sessionStorage`
  (há teste de guarda, `tests/test_frontend_auth_contract.py`); ação crítica exige confirmação
  explícita.
- `.claude/skills/provider-integrations/SKILL.md`: não desenhar UI de multi-provedor enquanto o
  backend for de conta única global — "isso seria promessa falsa"; multi-provedor é mudança de
  arquitetura de backend primeiro.
- A tabela nova entra em `RLS_TABLES` (`src/mplacas/db/rls_inventory.py`) com escopo
  `ORGANIZATION`, como `api_credentials` já está — não é opcional, é o inventário que o CI cobra.
- Toda ação sobre credencial de fornecedor gera audit event (ADR-032, ADR-033, ADR-034).

**Pré-requisito C — o modelo de negócio (bloqueante, e não é decisão técnica).**
Ver § *Decisão em aberto* abaixo. C precisa vir **antes** do desenho de B, porque a resposta muda a
chave da tabela de credenciais.

### 3. O que **não** fazer enquanto isso

Estas proibições são a parte operacional deste ADR. Um agente ou pessoa que receber uma tarefa que
caia em qualquer uma delas deve recusar e apontar para cá.

1. **Nada de tela de Integrações com dado fake ou mockado.** Nem "preview", nem "em breve", nem tela
   funcional apontando para um backend inexistente. Uma tela de integrações que lista fornecedores
   que o sistema não sabe coletar é promessa falsa ao cliente — exatamente o anti-pattern nomeado em
   `provider-integrations/SKILL.md`.
2. **Nada de catálogo de fornecedores hardcoded.** Nem constante `PROVIDERS = [...]`, nem enum de
   fornecedor no backend, nem lista de logotipos no frontend. `Device.provider` continua sendo uma
   string livre com um único valor real em uso (`"NEPVIEWER"`, `db/models.py:126`). Um catálogo é
   uma afirmação pública de capacidade; só se cria catálogo quando há mais de um item verdadeiro.
3. **Nada de campo/tabela "Cliente" no banco** enquanto § *Decisão em aberto* não for respondida.
   Adivinhar essa entidade é a mudança mais cara de reverter de todas as listadas aqui, porque ela
   vira FK em tudo que for criado depois.
4. **Nada de generalizar `SolarProvider` "para ficar pronto".** Acrescentar métodos, capabilities,
   `provider_id` ou registry na ABC sem um segundo adaptador real é abstração especulativa: sem o
   segundo caso concreto, não há como saber se a generalização acerta. A ABC fica com os três
   métodos que tem (`providers/base.py:55-70`).
5. **Nada de campo novo de credencial em `Settings`** para "o próximo fornecedor". Credencial global
   por variável de ambiente é justamente o modelo que B substitui; acrescentar mais um par
   `X_ACCOUNT`/`X_PASSWORD` (`core/config.py:39-40`) aumenta a dívida em vez de pagá-la.

**Permitido e desejável enquanto isso:** corrigir o achado de unicidade global de `Device`
(pré-requisito A, § *Achado que define a ordem*), que é correção de bug latente e vale por si só,
independentemente de multi-fornecedor.

### 4. Gatilho de reabertura (objetivo e verificável)

Distinguem-se **reabrir o desenho** de **começar a implementar**.

**Gatilho de reabertura do ADR (redesenho) — qualquer uma das duas condições:**

- **G1 (demanda):** um cliente **pagante** solicita, por escrito, telemetria de um fornecedor
  diferente de NEPViewer. *Verificação:* o pedido registrado por escrito **e** a organização
  correspondente existindo em `organizations` com pelo menos uma usina em `plants`.
- **G2 (viabilidade):** existem **credenciais de teste funcionais** de um segundo fornecedor em
  mãos, comprovadas por **uma chamada real bem-sucedida de listagem de dispositivos** contra a API
  desse fornecedor, com a resposta registrada (schema anonimizado, sem credencial).

**Gatilho de implementação — as três condições, simultaneamente:**

- G1 **e** G2, **e**
- **G3:** a pergunta de modelo de negócio da § *Decisão em aberto* respondida pelo usuário.

**O que explicitamente NÃO é gatilho:** mais um documento de consultoria externa; um concorrente
anunciar a funcionalidade; a percepção de que "vai ser preciso um dia"; um fornecedor com API
pública documentada mas sem cliente pedindo. Nenhum desses produz o segundo caso concreto que a
generalização precisa para não ser adivinhação.

**Ordem de execução quando os três dispararem:** A → C → B → adaptador do segundo fornecedor → UI.
A UI é o **último** passo, nunca o primeiro, exatamente porque é o passo que faz promessa ao
cliente.

## Decisão em aberto (requer o usuário — não decidida neste ADR)

> **Quem é o "Cliente" no Mplacas: o Mplacas atende o dono da usina diretamente, ou revende através
> de integradores/instaladores que administram carteiras de usinas de terceiros?**

Esta pergunta **não é técnica** e não deve ser respondida por nenhum agente. Ela é registrada aqui
porque é bloqueante: a resposta determina **a que a credencial de fornecedor se prende**, e portanto
a chave primária e a chave estrangeira da tabela central do módulo inteiro.

Os três desenhos são mutuamente incompatíveis, e o custo de trocar depois é migração de dado
sensível:

| Se o modelo for… | A credencial pertence a… | Consequências |
|---|---|---|
| **Dono de usina direto** | `organization_id` — a organização já é o cliente | Menor mudança de modelo. `Organization` já existe (`organizations/db_models.py:14`), já está sob RLS, já é a raiz de tenancy (ADR-052/053). Não nasce entidade "Cliente"; ela **já se chama** `Organization`. Uma conta de fornecedor por organização, N usinas dentro dela. |
| **Revenda via integrador/instalador** | Um nível **acima** da organização, ou uma organização "integradora" com filhas | Nasce hierarquia de tenancy nova. Toda a autorização de hoje é plana — `PlantScope` (`core/authorization.py`), `plant_scope_for_organization_in_session` (`core/tenancy.py:25-41`), o RLS por `organization_id` e o vínculo 1:1:1 do Telegram (`telegram_chat_id` é `unique` em `organizations`, `organizations/db_models.py:29-31`). É o cenário **caro**, e é o cenário em que a expressão "cadastro de fornecedores **por cliente**" dos PDFs faz mais sentido literal. |
| **Credencial por usina** | `plant_id` | Mais granular, e o único que suporta "o cliente tem duas usinas em portais diferentes". Custa uma credencial por usina para administrar, e multiplica a superfície de segredo. |

**Sinalização explícita:** enquanto esta pergunta não for respondida, qualquer desenho de "Cliente"
é adivinhação, e por isso o item 3 da § *O que não fazer* proíbe criar campo ou tabela para ela.
Nenhum agente deve responder isto por inferência a partir do código — o código de hoje é compatível
com os três cenários, porque ele nunca precisou escolher.

## Consequências

### Positivas

- **Não se paga o custo de generalizar sobre amostra de tamanho um.** A ABC atual foi escrita
  olhando um fornecedor; o segundo adaptador real é o único instrumento capaz de revelar quais
  hipóteses dela são específicas do NEPViewer.
- **Não se cria superfície de segredo de terceiro sem cofre.** Uma tela que coleta credencial de
  fornecedor sem um cofre de saída desenhado seria a pior classe de dívida possível: reversível em
  código, irreversível em exposição.
- **A ordem "identidade de dispositivo primeiro" impede que multi-fornecedor herde o bug latente de
  unicidade global** (`UniqueConstraint("provider","serial_number")`), transformando um bug
  alcançável só por coincidência de número de série em corrupção sistemática de dado de produção.
- **Nenhuma promessa falsa na interface.** O produto continua declarando exatamente a capacidade que
  tem, que é o princípio já formalizado em `provider-integrations/SKILL.md`.
- **O achado de unicidade global de `Device` sai da sombra.** Ele estava latente e sem registro;
  agora tem dono, ordem na fila e justificativa.

### Negativas

- **Se um segundo fornecedor aparecer com urgência comercial, o caminho crítico é longo e em
  série:** A (migration + reconciliação de dado) → C (decisão de negócio, cuja latência não é
  técnica) → B (ADR de cofre + implementação) → adaptador → UI. Semanas, não dias. Este ADR aceita
  esse risco conscientemente e o mitiga **apenas** registrando a ordem — não adianta trabalho
  especulativo, por decisão.
- **A ABC `SolarProvider` continua com acoplamento implícito ao formato NEPViewer, e ele permanece
  invisível.** Exemplo concreto: `get_daily_energy(serial_number, start, end)`
  (`providers/base.py:63-70`) assume que o fornecedor expõe **série diária por dispositivo**; um
  fornecedor que só exponha agregado por usina, ou só curva de potência instantânea, não cabe nessa
  interface sem reescrevê-la. Esse custo fica empurrado para o futuro e só será medido quando o
  segundo adaptador for escrito.
- **Os PDFs ficam sem resposta implementada.** Se vierem de um interlocutor comercial, é preciso
  comunicar que a decisão é de **sequenciamento**, não de rejeição — e este ADR é o documento a
  enviar, porque nomeia o que falta e o que dispara a retomada.
- **Uma janela de "por que ainda não fizemos isso?" reaparece a cada ciclo de planejamento.** O
  gatilho da § 4 é a resposta pronta, e é justamente por isso que ele precisa ser verificável em vez
  de "quando fizer sentido".
- **`MPLACAS_NEP_ACCOUNT`/`MPLACAS_NEP_PASSWORD` continuam sendo configuração de plataforma**
  (`core/config.py:39-40`), o que significa que onboarding de um cliente novo com conta NEPViewer
  própria continua sendo trabalho manual de infraestrutura (`infra/gcp/set-secrets.sh:150-156`), não
  self-service. Custo operacional aceito enquanto o número de clientes for pequeno; é o primeiro
  indicador que vai pressionar o gatilho G1.

## Validação

Este ADR não introduz código, então a validação é de **conformidade**, não de teste:

- Nenhum arquivo novo em `src/mplacas/providers/` além de `base.py`, `resilient.py` e `nepviewer/`.
- Nenhuma rota nova em `frontend/src/App.tsx` além de `/login` e `/dashboard`.
- Nenhuma tabela nova em `src/mplacas/db/rls_inventory.py` relacionada a credencial de fornecedor.
- Nenhum campo novo de credencial de provedor em `src/mplacas/core/config.py`.

O ponto de aplicação real é o **checklist já existente** de `provider-integrations/SKILL.md`
("Capacidade real do backend confirmada antes de desenhar a UI"; "Nenhuma promessa de
multi-conta/multi-provedor não suportada"). Tarefa delegável de custo trivial, decorrente deste ADR:
acrescentar a `.claude/skills/provider-integrations/SKILL.md` uma referência a este ADR-070 e ao seu
gatilho, para que o agente que carregar a skill encontre a decisão sem precisar procurar em `docs/`.

## Reversibilidade

**Máxima.** Este ADR não consome nada: não há migration para desfazer, não há contrato público
alterado, não há dado a migrar. Reabrir custa exatamente o esforço de reler esta página. O único
custo real de ter esperado é o tempo de calendário entre o gatilho disparar e o módulo existir — e
esse custo está quantificado, e aceito, na primeira consequência negativa.

## ADRs relacionados

- **ADR-047** — resiliência da coleta NEPViewer: a camada `ResilientSolarProvider`
  (`providers/resilient.py`) que qualquer segundo adaptador terá de reusar, não reimplementar.
- **ADR-043** — credenciais operacionais persistidas: o cofre de credencial de **entrada**, que a
  § 2/B distingue explicitamente do cofre de saída que falta.
- **ADR-052 / ADR-053** — evolução multi-tenant e isolamento por organização: a hierarquia de
  tenancy que a § *Decisão em aberto* pode ou não precisar estender.
- **ADR-045** — Mplacas permanece single-tenant: superado por ADR-052/053, citado aqui apenas porque
  a pergunta "quem é o cliente" é a mesma família de decisão.
- **ADR-069 § E9** — a exceção formalizada de `run_collection` no fan-out noturno é a manifestação
  operacional, já em produção, do gap dos itens 2, 7 e 8 da tabela de evidência.
- **ADR-032 / ADR-033 / ADR-034** — trilha de auditoria de ação sensível, que o pré-requisito B terá
  de honrar sem inventar mecanismo novo.
