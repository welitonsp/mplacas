---
name: adr-writer
description: Use ao registrar uma decisão de arquitetura do projeto Mplacas como ADR — quando o usuário pede para "criar um ADR", "documentar essa decisão", "registrar essa arquitetura", ou quando o architect conclui uma análise que deve virar registro permanente. Garante numeração sequencial correta, localização correta (docs/, não docs/adr/), e a estrutura de seções já usada nos ~50 ADRs existentes do projeto.
---

# Criação de ADR — Mplacas

## Convenção real do projeto (verificada em `docs/`, 2026-07-30)

A maioria dos ADRs (ADR-009 até ADR-052) vive solta em `docs/ADR-NNN-titulo-kebab.md`.
Apenas quatro ADRs antigos (`ADR-004`, `ADR-006`, `ADR-008`, `ADR-051`) estão em
`docs/adr/`. **`docs/adr/` é um local legado — não use para ADRs novos.** Todo ADR
novo vai em `docs/ADR-NNN-titulo-kebab.md`.

## Passos

1. **Determine o próximo número.** Rode:
   ```
   ls docs/ADR-*.md docs/adr/ADR-*.md 2>/dev/null
   ```
   Pegue o maior `NNN` entre os dois locais e some 1. Não confie em memória — sempre
   confira o estado atual do diretório, pois pode haver ADRs criados na mesma sessão.

2. **Nomeie o arquivo:** `docs/ADR-NNN-titulo-curto-em-kebab-case.md`. O slug pode ser
   em inglês (padrão majoritário: `nepviewer-collection-resilience`,
   `executive-dashboard-read-model`) — siga o que já existe, não crie novo padrão de
   idioma.

3. **Estrutura de seções** (nem todo ADR tem todas — inclua as que fizerem sentido para
   a decisão; `Status`, `Contexto` e `Decisão` são obrigatórias, o resto é conforme o
   peso da decisão):

   ```markdown
   # ADR-NNN — Título da decisão

   ## Status

   Aceito.

   ## Contexto

   [Por que essa decisão precisou ser tomada. Cite ADRs relacionados por número,
   ex: "ver ADR-045". Se essa decisão substitui ou refina uma anterior, diga isso
   explicitamente.]

   ## Decisão

   [O que foi decidido, em itens numerados se houver múltiplas partes. Seja concreto:
   nomes de arquivo, classes, campos de schema — não fale em abstrato do que "deveria"
   ser feito, descreva o que FOI decidido.]

   ## Consequências

   ### Positivas

   [...]

   ### Negativas

   [Trade-offs aceitos conscientemente — todo ADR de peso real tem pelo menos um.]

   ## Validação

   [Opcional. Como a decisão foi/será comprovada: testes, migrations com
   upgrade/downgrade, CI verde. Presente na maioria dos ADRs recentes (>= ADR-040).]

   ## Reversibilidade

   [Opcional, mas recomendado quando a decisão descarta uma alternativa que poderia
   voltar no futuro — ver ADR-045 como exemplo: descreve o ponto de extensão exato
   para reverter.]
   ```

4. **Linkar ADRs relacionados inline** onde a decisão se apoia em ou substitui outra:
   `(ver ADR-051)`, `(ADR-043 previa isso como Fase 3)`. Isso é a convenção já usada em
   todo o histórico — não pule essa parte, é o que torna os ADRs navegáveis.

5. **Roteamento de trabalho** (ver CLAUDE.md): a redação do conteúdo do ADR — avaliar
   trade-offs, decidir o que entra em "Negativas", decompor em fases — é trabalho do
   `architect` (Opus). Não delegue a escrita de ADR ao `worker` ou `quick-task`; eles
   podem, no máximo, confirmar fatos pontuais (ex: "esse índice já existe?") para o
   architect usar como insumo.

6. **Depois de escrito**, confirme com o usuário antes de considerar o ADR "Aceito" —
   um ADR registra uma decisão já tomada, não uma proposta. Se a decisão ainda está em
   aberto, use `Status: Proposto` em vez de `Aceito`.

## Erros a evitar

- Criar o arquivo em `docs/adr/` (legado, não o padrão atual).
- Reutilizar um número já usado por não ter checado os dois diretórios.
- Escrever um ADR sem nenhuma consequência negativa — se a decisão realmente não tem
  trade-off, provavelmente não precisa de ADR, é só uma implementação.
