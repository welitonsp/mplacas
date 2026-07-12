# ADR-012 — Dashboard web responsivo servido pela FastAPI

## Status

Aceito.

## Contexto

O Mplacas já possui uma API executiva consolidada e protegida. A próxima etapa exige uma interface visual responsiva sem duplicar regras de negócio no navegador nem introduzir uma cadeia de build frontend antes de existir necessidade comprovada.

## Decisão

- o dashboard será servido pela própria aplicação FastAPI;
- a interface usará HTML, CSS e JavaScript nativos;
- todos os cálculos permanecem no backend determinístico;
- o navegador apenas consulta e apresenta `GET /energy/executive/latest`;
- a chave operacional nunca será embutida no HTML, JavaScript ou repositório;
- a chave será mantida apenas em memória durante a aba atual, sem `localStorage` ou persistência equivalente;
- o identificador da usina será informado explicitamente pelo operador;
- o layout será responsivo, acessível por teclado e compatível com preferência de tema escuro;
- estados de carregamento, erro, ausência de histórico e sucesso serão explícitos;
- o contrato visual consumirá somente o endpoint executivo, evitando acoplamento a múltiplos endpoints internos.

## Consequências

A aplicação ganha um painel operacional de baixo custo e baixa complexidade, adequado para uso imediato. Caso a interface cresça para múltiplas páginas, autenticação de usuários, gráficos avançados ou edição complexa, uma SPA dedicada poderá ser avaliada em ADR posterior sem alterar o contrato executivo existente.
