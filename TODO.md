# TODO — revisão visual integral MPlacas

## Entregue nesta etapa

- [x] **Auditoria das seis superfícies:** `/`, `/login`, `/dashboard/visao-geral`, `/dashboard/producao`, `/dashboard/financeiro`, `/dashboard/tecnico` e shell compartilhado; revisão por código, testes, fixtures e capturas Playwright em desktop, mobile e 320 CSS px. Sem login real ou dados privados.
- [x] **Tokens de texto e tema:** garantir tokens de texto primário, muted e gray-950 em claro/escuro, com valores espelhados e teste de contraste WCAG.
- [x] **Landing e conversão:** link de salto, menu móvel acessível por teclado, alvos táteis maiores, destinos próprios para cards e menor altura de seções/cards no celular; preservar a proposta, FAQ e CTAs.
- [x] **Login:** priorizar o formulário em mobile mantendo o layout em duas colunas em desktop; remover repetição de marca e placeholder que sugere regra de senha; bordas mais legíveis e título específico da rota.
- [x] **Interação do operador:** converter a ação única do avatar em disclosure simples e restaurar foco ao trigger em Escape.
- [x] **Reflow de gráficos:** impedir que tabelas semânticas ocultas ampliem o viewport; medir overflow somente depois de a rota solicitada estar pronta.
- [x] **Preservação do produto:** manter API, dados, permissões, regras de autenticação, valores, unidades, cálculos e estados de negócio.
- [x] **Validação final:** type-check, suíte unitária, build, orçamento de bundle, capturas de rota e reflow mobile.

## Próxima etapa — ainda em aberto

- [ ] **Estados por módulo:** preservar h1, contexto e ação em loading, erro e vazio; adotar skeletons que acompanhem a composição real de cada rota.
- [ ] **Visualizações acessíveis:** alternativa textual do mini-gráfico diário; indicação de conteúdo lateral em séries; permitir leitura completa de labels de perdas no Técnico sem tooltip.
- [ ] **Recursos e erros:** desacoplar histórico de Produção de referências ainda pendentes; consolidar alerts/retries por recurso; oferecer retry contextual onde estiver ausente.
- [ ] **Hierarquia executiva:** diminuir repetição entre decisão, resumo e evidência em Visão Geral, Produção e Financeiro sem remover informação ou unidades.
- [ ] **Mobile/tablet:** ajustar distribuição da comparação de Produção em breakpoint intermediário e adicionar índice/âncoras às seções do módulo Técnico.
- [ ] **Validação assistiva:** ensaio manual com leitor de tela/teclado; revisar tema claro e escuro em sucesso/loading/erro/vazio com dados de demonstração.

## Limites

- Não alterar backend, schema, contratos, cálculos, políticas de acesso, integração ou publicação.
- Usar somente fixtures de demonstração para a navegação do painel; não acessar dados de cliente nem solicitar credenciais.
- Não declarar como concluídos os itens acima marcados em aberto. O relatório `docs/REVISAO_VISUAL_E_EVOLUCAO_2026-10-15.md` registra evidências e próximos passos.
