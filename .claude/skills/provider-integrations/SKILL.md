---
name: provider-integrations
description: Use ao construir UX de integração com provedor de telemetria solar no Mplacas (hoje NEPViewer, único, via providers/nepviewer/). Define o fluxo de conexão/descoberta e a limitação atual (conta única/global, sem distinção por usina).
---

# Provider Integrations — Mplacas

## Finalidade
Documentar o estado real da integração de provedores, para não desenhar uma UX que assume capacidade que o backend não tem hoje.

## Estado real confirmado
- Único provedor implementado: NEPViewer (`src/mplacas/providers/nepviewer/`), configurado via credenciais **únicas e globais** (`MPLACAS_NEP_ACCOUNT`/`MPLACAS_NEP_PASSWORD`), não por usina.
- `SolarDevice` não carrega identificador de usina física — a coleta hoje não distingue múltiplas usinas na mesma conta (ver `energy-data-lineage` e a exceção documentada no ADR-069 §E9 sobre `run_collection`).
- Não há hoje wizard de onboarding self-service de provedor na UI — a configuração é feita via variável de ambiente/infra, não pela interface.

## Quando usar
- Antes de desenhar qualquer tela de "adicionar integração"/"conectar provedor" — confirme que o backend já suporta múltiplas contas/credenciais por organização antes de prometer isso na UI.

## Procedimento
1. Não construa uma UI de múltiplos provedores/múltiplas contas por usina enquanto o backend for de conta única global — isso seria promessa falsa.
2. Se o pedido for para dar suporte a múltiplos provedores, isso é mudança de arquitetura de backend primeiro (escalar ao architect/backend), não algo que o frontend resolve sozinho.
3. Qualquer tela nova de credencial segue `secret-safe-ui`.

## Anti-patterns
- Tela de "conectar novo provedor" quando o backend só suporta um, globalmente.
- Prometer descoberta automática de usina por conta quando o dado não permite distinguir usinas.

## Checklist
- [ ] Capacidade real do backend confirmada antes de desenhar a UI
- [ ] Nenhuma promessa de multi-conta/multi-provedor não suportada
