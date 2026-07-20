# ADR-049 - Read-model do dashboard executivo com invalidação por impressão digital

## Status

Aceito.

## Contexto

O dashboard executivo recomputa o caminho executivo inteiro a cada acesso: análise do ciclo
confirmado (varredura das leituras diárias do período), comparação de tendência (que reanalisa
ciclos) e montagem. A auditoria de 2026-07-16 classificou como P2 criar cache/read-models para
dashboards. O endpoint `/energy/executive/latest` e outros consumidores (relatórios, alertas,
explicações) repetem esse custo.

O risco de qualquer cache aqui é servir um dashboard **obsoleto**: os dados de energia do ciclo são
mutáveis (leituras provisórias que consolidam, dados tardios, correções). Um cache ingênuo por
`bill_id` violaria a integridade — o princípio "integridade antes de automação" exige que o cache
jamais devolva um resultado que não reflita os dados atuais.

## Decisão

1. Um `ExecutiveDashboardReadModel` guarda dashboards por uma chave que inclui uma **impressão
   digital** dos dados de energia do ciclo, além de `bill_id`, `plant_id`, produção esperada e
   tolerância.
2. A impressão digital (`energy_fingerprint`) é o SHA-256 de `count`, `sum(energy_kwh)` e
   `max(updated_at)` das leituras diárias na janela do ciclo — obtidos em **uma consulta agregada
   leve**. Qualquer alteração nos dados (consolidação, dado tardio, correção) muda ao menos um
   desses valores e, portanto, a impressão.
3. Um acerto de cache só ocorre quando a impressão coincide, ou seja, quando o dashboard seria
   idêntico. **Nunca há risco de servir resultado obsoleto**; na dúvida, recomputa.
4. O custo por acesso cai de recomputar o caminho executivo inteiro para uma consulta agregada
   seguida de, no acerto, retorno direto do valor em memória.
5. O cache é um LRU limitado (padrão 128 entradas) em memória de processo, adequado ao contexto
   single-plant. Não substitui a fonte de verdade; é puramente derivado e descartável.

## Consequências

### Positivas

- Acessos repetidos ao dashboard sem mudança de dados evitam a recomputação completa.
- A correção por impressão digital garante que nenhuma leitura obsoleta seja servida.
- O ponto único (`ExecutiveDashboardReadModel`) pode ser reutilizado pelos demais consumidores.

### Negativas

- Cada acesso ainda faz a consulta de impressão (leve) mesmo no acerto; é o preço da corretude.
- O cache é por processo: instâncias distintas mantêm caches próprios. Aceitável no volume atual;
  um cache distribuído só se justificaria com muitas réplicas.
- O ganho é nulo quando os dados mudam a cada acesso (ciclo em coleta ativa), situação em que o
  recomputo é inevitável de qualquer modo.

## Validação

- segundo acesso sem mudança é acerto de cache;
- adicionar/consolidar leitura do ciclo invalida o cache (recomputa);
- corrigir uma leitura existente invalida o cache;
- produção esperada distinta gera entradas separadas;
- LRU respeita o limite de entradas e valida o parâmetro.
