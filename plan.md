# Plano — revisão visual integral MPlacas

## Objetivo
Elevar a apresentação de todas as telas da MPlacas com maior clareza, consistência, responsividade e acabamento profissional, preservando comportamento e regras de domínio existentes.

## Estrutura verificada
O frontend React/Vite está em `frontend/src`. `App.tsx` define a página pública `/`, o login `/login` e o dashboard protegido em `/dashboard`, com quatro módulos lazy-loaded: visão geral, produção, financeiro e técnico. As páginas ficam em `frontend/src/pages/`; o shell compartilhado vive em `pages/dashboard/DashboardLayout.tsx`. Componentes, contratos e visuais de dados estão divididos em `components/`, `lib/dashboard/` e tokens/styles centrais. O projeto já tem testes por módulo, SVGs próprios e orçamento de bundle.

## Direção de design

- **Movimento:** observatório solar editorial — precisão de instrumento com a serenidade de uma publicação técnica premium.
- **Princípios:** primeiro o dado e a ação; hierarquia tipográfica inequívoca; consistência entre módulos; qualidade e incerteza dos dados permanecem visíveis.
- **Paleta:** preservar navy profundo, teal/verde-azulado e superfícies claras da marca. Estados não serão comunicados apenas por cor.
- **Layout:** shell estável e navegação previsível; cabeçalhos de módulo consistentes; conteúdo agrupado por tarefa em largura e ritmo legíveis. No móvel, reorganização intencional, sem perda de contexto nem rolagem horizontal desnecessária.
- **Assinatura:** acentos teal discretos; métricas alinhadas em uma grade tipográfica; origem, período, unidade e qualidade próximos aos dados que descrevem.
- **Interação:** foco de teclado evidente, alvos confortáveis e estados de carregamento/vazio/erro/indisponibilidade tratados com uma linguagem comum.
- **Movimento:** transições breves e funcionais; respeitar `prefers-reduced-motion`; evitar animação decorativa que compete com diagnósticos.
- **Tipografia:** preservar stack nativa e leve; normalizar papéis de título, subtítulo, corpo e metadado em uma escala legível e responsiva, sem enfraquecer a performance.
- **Marca e voz:** observatório operacional de energia solar para transformar dados rastreáveis em decisões; personalidade precisa, confiável e acessível. Evitar alegações além da evidência.

## Fases
1. **Concluída:** auditar as seis telas e o shell com código, testes, fixtures de demonstração e capturas Playwright em desktop, mobile e 320 CSS px; não usar credenciais ou dados privados.
2. **Concluída:** corrigir os problemas transversais de maior impacto e baixo risco em tokens/tema, navegação/teclado, conversão, ordem do login e reflow de tabelas acessíveis, preservando contratos, cálculos, dados e conteúdo.
3. **Concluída:** validar a suíte, type-check, build, orçamento de bundle, capturas e overflow em mobile; documentar achados resolvidos e backlog que exige continuidade.

## Limites
Sem mudanças de backend, schema, cálculos energéticos/financeiros, permissões, política de login, integrações, credenciais ou produção. Não fazer deploy. As ações concluídas e os itens ainda abertos constam em `TODO.md` e `docs/REVISAO_VISUAL_E_EVOLUCAO_2026-10-15.md`.
