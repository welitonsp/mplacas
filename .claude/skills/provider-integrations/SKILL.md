---
name: provider-integrations
description: Use ao construir UX de integração com provedor de telemetria solar no Mplacas (hoje NEPViewer, via providers/nepviewer/). Define o fluxo de conexão por usina (ADR-091) e o que ainda não existe (outras marcas, várias contas por usina).
---

# Provider Integrations — Mplacas

## Finalidade
Documentar o estado real da integração de provedores, para não desenhar uma UX que assume capacidade que o backend não tem hoje.

## Estado real confirmado (ADR-091, 29/10/2026)
- Único provedor implementado: NEPViewer (`src/mplacas/providers/nepviewer/`).
- **Uma conexão por usina** (`provider_accounts`, `providers/accounts.py`): login e senha cifrados com AES-256-GCM (`core/secret_box.py`), chave em `MPLACAS_PROVIDER_SECRET_KEYS`, fora do banco. Não existe mais conta global em variável de ambiente.
- Rotas: `GET/PUT/DELETE /plants/{plant_id}/provider-account` (`providers/router.py`). PUT só ADMIN, confere a conta na NEPViewer antes de salvar, até 5 conferências por usina a cada 10 min, recusa inversor de outra usina. A senha nunca volta.
- Tela: bloco "Conexão com o inversor" em Minha usina (`frontend/src/components/ProviderConnectionSection.tsx`).
- Coleta (`cloud_jobs.run_collection`, `collection/drain.py`) percorre só as usinas com conexão ativa; usina sem conexão não é coletada.
- `SolarDevice` não carrega identificador de usina física: uma conta = uma usina. O mesmo número de série em outra usina é recusado (`CollectionPlantError`).

## Quando usar
- Antes de desenhar qualquer tela de integração/credencial de provedor.

## Procedimento
1. Marca nova de inversor = novo valor de `provider` + nova fábrica e verificador (ver `claude/integracoes-inversores.md` no projeto); a tabela, o cofre e a tela já servem.
2. Não prometa várias contas na mesma usina, nem usina com duas marcas: o backend não suporta.
3. Qualquer tela nova de credencial segue `secret-safe-ui`; o corpo do PUT é lido à mão no backend para nenhum erro de validação repetir a senha.

## Anti-patterns
- Ler a credencial fora de `ProviderAccountService` ou logar login/senha/texto cifrado.
- Prometer descoberta automática de usina por conta quando o dado não permite distinguir usinas.

## Checklist
- [ ] Capacidade real do backend confirmada antes de desenhar a UI
- [ ] Senha só entra; nunca volta em resposta, log ou auditoria
