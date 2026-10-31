# ADR-092 — Growatt com usuário e senha do app (API clássica)

## Status

**Aceito — 2026-10-31.** Pedido do dono: o cliente escolhe a marca (NEPViewer ou Growatt) e digita o
mesmo usuário e senha do app do celular, sem token nem passo técnico. Estende a ADR-091.

## Contexto

A Growatt tem duas APIs (levantamento em `claude/integracoes-inversores.md`):

- **OpenAPI V1 oficial**, com token que o dono gera no app ShinePhone. Estável, mas exige que o
  cliente encontre e copie o token — passo que o dono não quer impor.
- **API clássica** do próprio app ShinePhone (`newTwoLoginAPI.do`, `PlantListAPI.do`,
  `PlantDetailAPI.do`), com usuário e senha. Não documentada, já mudou de endereço e passou a
  exigir `User-Agent`, e bloqueia logins repetidos (resposta `507`). É a usada pela biblioteca
  `growattServer` (MIT, base do Home Assistant) e, no espírito, o mesmo tipo de integração que a
  NEPViewer já usa no MPlacas.

## Decisão

1. **Growatt entra pela API clássica, com usuário e senha**, guardados na mesma conexão por usina
   da ADR-091 (`provider = "GROWATT"`). Nada muda na tabela, no cofre nem na auditoria.
2. Cliente próprio em `providers/growatt/client.py` (sem dependência nova), no padrão do da
   NEPViewer: `httpx` com sessão (cookies) e `User-Agent` fixo; senha enviada no formato do app
   (MD5 com a troca de `0` por `c` nas posições pares). O MD5 é só o formato de transporte imposto
   pela Growatt; em repouso a senha continua cifrada pelo cofre da ADR-091.
3. **Nível usina, não inversor.** Cada usina Growatt da conta vira um "aparelho" do MPlacas
   (`GW-PLANT-<id>`), e a produção diária vem de `PlantDetailAPI.do?type=2` (mês, um valor por
   dia). Funciona para qualquer modelo de inversor Growatt, sem depender do tipo (MIN, SPH, MAX…).
4. **Login uma vez por coleta** (uma por dia por usina). Bloqueio `507`
   (`ProviderRateLimitedError`) e senha recusada (`ProviderAuthError`) **não** são repetidos pela
   camada de retry nem voltam na drenagem logo em seguida: o dia entra na fila com **1 h** de
   espera mínima (também nos reagendamentos), e a falha sobe para a conexão aparecer como "falha"
   em Minha usina. Redirecionamento do próprio login é tratado como indisponibilidade, nunca como
   senha errada (aceito: a camada de retry o repete até 3 vezes na mesma coleta).
5. A conferência antes de salvar (ADR-091, fase 5) entra na Growatt e lista as usinas; o teto de 5
   conferências por usina a cada 10 min continua.
6. `SolarCollectionService` passa a gravar o fabricante da conexão no aparelho (`devices.provider`)
   e na origem do dado (`daily_energy.source`: `GROWATT_CLASSIC`), em vez de `NEPVIEWER` fixo.
7. Tela: o bloco "Conexão com o inversor" ganha a escolha da marca e os campos "Usuário do app" e
   "Senha do app".

## Consequências

### Positivas

- Cliente Growatt conecta como já conecta na NEPViewer: marca, usuário e senha.
- Sem dependência nova; a interface `SolarProvider` não muda.

### Negativas

- API não documentada: a Growatt pode mudá-la sem aviso. Falha aparece como "a última leitura
  falhou" em Minha usina e o dia fica na fila.
- O formato exato do mês em `PlantDetailAPI.do?type=2` não está documentado: o leitor aceita as
  formas conhecidas (`"1"`…`"31"` e `"AAAA-MM-DD"`) e é conferido no primeiro cliente real.
- Produção por usina, não por inversor: o detalhe por inversor fica para depois.
- Um `"0"` devolvido para o dia é gravado como zero. A coleta lê o dia anterior (fechado), mas
  isso é conferido no primeiro cliente real junto com o formato do mês.

## Validação

- Testes com respostas simuladas: login, senha recusada, bloqueio `507` sem retry, lista de
  usinas, mês com dias faltando (incompleto ≠ zero), virada de mês, valor não numérico.
- Coleta e fila com uma usina NEPViewer e outra Growatt, cada uma com o seu fabricante gravado.

## Reversibilidade

Trocar para a OpenAPI V1 mexe só em `providers/growatt/`: a conexão passaria a guardar o token em
vez da senha. Se a API clássica oferecer o token da conta depois do login, a troca pode ser
automática, sem o cliente fazer nada.
