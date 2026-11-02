# ADR-096 — Assistente de primeiro acesso: conectar → ler a usina → revisar e salvar

## Status

**Aceito — 2026-11-02.** Pedido do dono: o primeiro acesso é o diferencial do produto e precisa
de um fluxo profissional. Substitui a primeira conexão de um passo só (ADR-093 § 7) na tela.
A rota antiga `POST /plants/connect` continua existindo por compatibilidade.

## Decisão

1. **Três passos na tela**:
   1. **Conectar**: marca e usuário/senha ou token do app.
   2. **Lendo sua usina**: progresso por etapa, com "nada é salvo antes da sua revisão".
   3. **Revisar e salvar**: a usina montada, cada campo com o selo "Veio da marca" ou
      "Estimado", tudo editável, e um único botão **Salvar usina**.
2. **`POST /plants/connect/preview`** (ADMIN, organização sem usina): confere a conta, lê o
   cadastro na marca, geocodifica e monta o rascunho com as mesmas regras de `plants.autofill`,
   **sem gravar nada** além da auditoria (`plant.connect_previewed`, que conta no teto por
   organização). Devolve o rascunho, as origens e um **bilhete**.
3. **Bilhete** (`providers/connect_ticket.py`): AES-256-GCM com a chave do cofre (ADR-091),
   AAD `connect_ticket:<organization_id>`. Leva a marca, a credencial, os aparelhos e o rascunho
   com as origens, e vence em 15 minutos. Só o servidor abre. Com ele, o navegador não guarda a
   senha entre os passos e o "Salvar" não consulta a marca de novo (a Growatt bloqueia excesso
   de logins).
4. **`POST /plants/connect/confirm`** (`{ticket, plant}`): abre o bilhete (outra organização,
   vencido ou adulterado = `connect_ticket_invalid`), confere de novo o inversor em outra usina,
   cria a usina com os valores revisados (com a organização travada; a segunda confirmação dá
   409) e guarda a conexão. **Origem**: o campo que o cliente manteve igual ao rascunho guarda
   `BRAND`/`ESTIMATE` em `plants.auto_filled`; o que ele mudou passa a ser dele, sem marca.
5. A tela mostra quando a marca não informou potência ou localização, sem impedir de salvar.

## Consequências

- O cliente vê o sistema "fazendo a mágica" e confirma tudo numa tela só, com transparência
  sobre o que veio da marca e o que foi estimado.
- Se o cliente demorar mais de 15 minutos na revisão, precisa conectar de novo, e a tela explica
  isso.
- A prévia conta no mesmo teto de tentativas por organização (5 a cada 10 minutos).
