# ADR-090 — Home pública na identidade da ADR-077 e primário do tema escuro mantido

## Status

**Aceito — 2026-10-29.** Decisão tomada pelo projetista por delegação explícita do dono do produto
("faça as melhores decisões nas questões em aberto"), ao fim do refinamento visual da auditoria de
28/10/2026 (PRs #239–#249). Refina a ADR-077, que deixou a landing fora do escopo.

## Contexto

A ADR-077 definiu a identidade do produto (verde `#009C77` = energia, marinho `#00406E` = estrutura
e ação primária, cinza frio, Space Grotesk/Manrope, sentence case, sem decoração) e aplicou-a ao
painel e ao login. A landing pública (`PublicHomePage`, `public-home.css`) ficou de fora, com
identidade própria:

| | Landing (antes) | Painel (ADR-077) |
|---|---|---|
| Acento | verde-água `#4BB9A9` + âmbar `#E6AE58` decorativo | verde `#009C77` / `#2BC79B` (escuro), laranja só para atenção |
| Fundo claro | creme `#F3F4EE` | cinza frio `#F3F5F8` |
| Fundo escuro | marinho esverdeado `#102126` | tinta `#0E1B2A` / `#0A1017` |
| Ação primária | botão verde-água | marinho (`#7AAEDB` com texto `#06182A` no escuro) |
| Rótulos | CAIXA ALTA com espaçamento largo | sentence case |
| Decoração | textura pontilhada no hero, brilho radial | nenhuma |

O MPlacas será vendido a outros donos de usina. O caminho do cliente é landing → "Entrar" →
painel, e a troca completa de paleta e de voz tipográfica no meio desse caminho faz parecer dois
produtos. A auditoria de 28/10/2026 registrou a questão como decisão do dono; o PR 10 (#248) corrigiu
só a acessibilidade da landing, sem mexer na identidade.

Ficaram também duas questões menores da mesma auditoria: as repetições no texto do diagnóstico de
Energia (resolvidas no PR #250, sem ADR, por aplicarem a decisão 15 da ADR-077) e o botão primário
do tema escuro, que pode parecer desabilitado.

## Decisão

1. **A landing adota a identidade da ADR-077: cores, tipo de rótulo e ausência de decoração.**
   Implementado como um bloco no fim de `frontend/src/pages/public-home.css`, escopado em
   `.site-shell`, que redefine as variáveis da landing para os valores do painel (`--navy` `#0E1B2A`,
   `--navy-2` `#13212F`, `--teal` `#2BC79B`, `--teal-dark` `#00775B`, `--paper` `#F3F5F8`,
   `--paper-2` `#EEF2F6`, `--muted` `#556576`, `--amber` → verde) e sobrescreve as cores que estavam
   escritas direto nas regras.
2. **Ação primária no marinho**, como no painel (ADR-077, decisão 1): os botões da landing, que ficam
   sobre fundo escuro, usam o marinho clareado do tema escuro (`#7AAEDB`, texto `#06182A`, 7,6:1).
   O verde fica para o que é energia (os destaques dos títulos).
3. **Rótulos em sentence case** (ADR-077, decisão 5): `text-transform: none` e espaçamento normal
   nos 21 seletores que usavam CAIXA ALTA, e o texto dos rótulos que vinha em minúsculas passa a
   começar com maiúscula em `PublicHomePage.tsx` ("Role para explorar", "01 — Orientar"…).
4. **Sem decoração** (ADR-077, decisão 6): saem a textura pontilhada do hero e o brilho radial da
   seção de confiabilidade. O véu escuro sobre as fotos **fica**: é funcional (legibilidade do texto
   sobre a imagem), recolorido para a tinta do painel.
5. **Fica como está:** composição, fotos, todo o texto da landing e o **símbolo da marca**
   (`BrandMark`, favicon), que ainda usa verde-água e âmbar. Trocar o logo é decisão de marca, não de
   refinamento de interface.
6. **Botão primário do tema escuro do painel mantido** (`#7AAEDB` com texto `#06182A`). É o padrão de
   ação primária em tema escuro (superfície clara com texto escuro), passa no contraste (7,6:1) e
   tem o mesmo papel do marinho do tema claro. Trocar para uma cor mais saturada com texto branco
   não passa 4,5:1 nos tons de marinho disponíveis, e trocar para o verde quebraria o papel fixo das
   cores (verde = energia). A percepção de "desabilitado" vem da semelhança com o estado
   `disabled:opacity-60`, não da cor em si.

## Consequências

### Positivas

- Landing, login e painel falam a mesma língua visual: o cliente reconhece o produto depois de
  "Entrar".
- Laranja/âmbar volta a significar só atenção em todo o produto, inclusive na landing.
- Nenhuma dependência nova; o CSS da landing continua carregado só nela.

### Negativas

- A landing perde parte do caráter editorial próprio: o creme quente e o verde-água davam um tom de
  revista que o cinza frio não tem.
- O símbolo da marca continua em verde-água e âmbar, agora destoando do resto da landing. Fica
  registrado como pendência de marca.
- O bloco no fim do CSS sobrescreve regras anteriores em vez de reescrevê-las: o arquivo fica mais
  longo e quem editar uma regra antiga precisa conferir o bloco do fim. Escolhido para manter o
  diff pequeno e reversível.
- A percepção de "desabilitado" do primário escuro não foi eliminada, só justificada.

## Validação

- e2e (`frontend/e2e/screenshots.spec.ts`, teste da página pública, todas as viewports da matriz):
  nenhum elemento da landing com `text-transform: uppercase`; botão principal do hero com fundo
  `rgb(122, 174, 219)`. As guardas do PR #248 continuam: piso de 12 px fora da prévia ilustrativa e
  item de menu só do celular escondido no desktop.
- Contraste calculado por fórmula para as combinações novas: verde `#2BC79B` sobre `#0E1B2A` 8,1:1;
  `#00775B` sobre `#F3F5F8` 5,1:1; `#556576` sobre `#EEF2F6` 5,3:1; botão 7,6:1.
- Capturas desktop e celular revisadas antes do PR.

## Reversibilidade

Toda a decisão 1–4 vive em um bloco marcado no fim de `public-home.css` ("Identidade ADR-077 na
landing (ADR-090)") e em 14 strings de rótulo em `PublicHomePage.tsx`. Remover o bloco e voltar as
strings restaura a identidade anterior, mantendo as correções de acessibilidade do #248, que ficam
num bloco separado acima dele.
