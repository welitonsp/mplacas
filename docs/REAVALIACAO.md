# Reavaliação Completa do Projeto Mplacas

## Parecer Executivo
O Mplacas tem uma proposta forte e diferenciada, combinando telemetria técnica (NEPViewer), dados comerciais/regulatórios (Equatorial) e análise inteligente. No estado atual, é uma especificação conceitual que precisa de endurecimento em confiabilidade, segurança e operação contínua.

### Maturidade Geral: 5,6/10
- **Visão de Produto:** 9/10
- **Arquitetura Conceitual:** 7/10
- **Segurança e Privacidade:** 5/10
- **Confiabilidade Operacional:** 4/10

---

## 1. Princípios Arquiteturais
Baseado nos frameworks de Google, Microsoft e AWS:
* Excelência operacional e segurança por projeto.
* Zero Trust e observabilidade.
* **Diretriz:** O Mplacas não deve depender de uma única fonte sem validação independente.

---

## 2. Proposta de Produto
Diferencial: Conciliação entre Produção (Inversor) × Medição (Distribuidora) × Fatura × Clima.
**Ajuste na Promessa:** Não prometer medição exata de autoconsumo sem medidor de fluxo; usar estimativas e indicar a natureza da métrica (MEDIDO, CALCULADO, ESTIMADO, etc.).

---

## 3. Arquitetura-alvo
Estrutura recomendada:
- **Adapter NEPViewer:** Camada de abstração para API não oficial.
- **Camada de Ingestão:** Eventos e filas.
- **Banco Operacional:** PostgreSQL com histórico imutável.
- **Motores:** Técnico, Tarifário e Data Quality.

---

## 4. Integração NEPViewer
- **API:** V2 (`https://api.nepviewer.net/v2`).
- **Riscos:** API não contratual, histórico limitado no servidor, omissão de dados em totais mensais.
- **Requisito:** O Mplacas deve construir seu próprio histórico desde o primeiro dia.

---

## 5. Estratégia de Coleta
- **Período Solar:** A cada 5-10 min (potência, status, alertas).
- **Pôr do Sol:** Consolidação diária.
- **Madrugada:** Reconciliação D+1.
- **Semanal:** Backfill para detectar correções retroativas.

---

## 6. Modelo de Dados
Tabelas principais: `users`, `plants`, `devices`, `telemetry_readings`, `daily_energy`, `utility_bills`, `reconciliations`, `anomalies`.
**Regra Financeira:** Nunca usar float para valores monetários; usar Decimal.

---

## 7. Inteligência da Fatura Equatorial
Pipeline: PDF → Extração Determinística → Parser Específico → Validação Matemática → Confirmação Humana.
*A IA entra apenas para classificação ou casos ambíguos.*

---

## 8. Motor Energético
Fórmulas essenciais:
- Produção solar = autoconsumo + injeção
- Autoconsumo estimado = produção do inversor − injeção medida
- Consumo total estimado = importação da rede + autoconsumo

---

## 9. Motor Tarifário e Regulatório
Deve considerar: Modalidade tarifária, SCEE, transição regulatória, tributos e custo de disponibilidade. Versão do cálculo deve ser registrada para auditoria.

---

## 10. Detecção de Anomalias
Classes: `COMMUNICATION_LOSS`, `ZERO_PRODUCTION`, `LOW_DAILY_YIELD`, `MONTHLY_TOTAL_MISMATCH`, `CREDIT_EXPIRATION_RISK`.

---

## 11. Segurança e LGPD
Dados sensíveis (CPF, faturas, hábitos) exigem: Criptografia, URLs temporárias, mascaramento, logs sanitizados e MFA.

---

## 12. Confiabilidade e SRE
Metas: 99,5% disponibilidade painel, 0 perda permanente de dados. Implementar degradação controlada quando a NEP estiver fora do ar.

---

## 13. Backlog Priorizado (P0)
1. Repositório Mplacas
2. Arquitetura e ADRs
3. Conector NEPViewer
4. Banco Histórico
5. Coleta Diária
6. Segurança de Credenciais
