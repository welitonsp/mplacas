# Snapshots Históricos de Auditoria (2026-08-01)

Este diretório contém retratos estáticos de auditoria de segurança e dependências capturados em **2026-08-01**.

## Aviso Importante

Esses snapshots:
- **NÃO representam o estado atual** do projeto
- **NÃO devem ser utilizados** para tirar conclusões sobre segurança ou atualização de dependências
- São preservados **apenas para rastreabilidade histórica** e contexto de auditoria

## Fonte de Verdade Atual

Para verificar o estado real de vulnerabilidades e dependências, execute:

- **Frontend:** `npm audit --omit=dev` na pasta `frontend/`
- **Backend:** `pip-audit` na pasta raiz ou no ambiente Python

## Caso Concreto: react-router

Este snapshot lista `react-router` como vulnerável (CVE GHSA-qwww-vcr4-c8h2). Porém, a versão instalada atualmente é **8.3.0**, que já contém a correção do CVE. O snapshot é obsoleto e não reflete a realidade do repositório atual.

---

Data de captura: 2026-08-01  
Data de arquivo: 2026-08-12
