# ADR-087 — Classe tarifária lida da fatura

## Status

**Aceito — 2026-10-24.** Item 4 do plano: deixar o sistema apto para clientes de qualquer
classe tarifária.

## Contexto

A tarifa cheia da conta "sem a usina" (ADR-080) usava sempre a classe residencial B1
convencional (`tariffs/service.py`). Para um cliente comercial, rural, de tarifa branca ou
baixa renda, a economia sairia errada, e normalmente para mais. A fatura imprime a classe
("Classificação: B B1 RESIDENCIAL - RESIDENCIAL NORMAL CONVENCIONAL"). Logo depois, na mesma
linha, vem o nome do titular.

## Decisão

1. **O leitor grava `tariff_class`** (migration `20261024_0049`, nullable, sem backfill).
   - **Formato:** `"<subgrupo>_<classe>_<modalidade>"`, por exemplo
     `B1_RESIDENCIAL_CONVENCIONAL`.
   - **Padrão fechado:** a regex só aceita subgrupos e classes conhecidos e lê a modalidade
     (convencional, branca, baixa renda/tarifa social) num trecho curto depois da classe.
     O nome do titular nunca é capturado.
   - **Classe não reconhecida em fatura nova:** vira `NAO_IDENTIFICADA`, sem tarifa cheia.
     A conta usa o preço da própria fatura (`BILL_TARIFF`), com aviso.
2. **Fatura antiga** (`NULL`, gravada antes da leitura): mantém o cálculo de sempre, B1
   residencial, marcado como **presumido** (`tariff_class_presumed`). Isso evita que a
   economia do ciclo atual (calculada ao vivo no executivo) mude no deploy. Não é uma
   suposição nova: é o comportamento anterior, agora explícito. Reimportar o PDF grava a
   classe (`billing/completion.py`).
3. **`full_tariff_without_taxes` exige a classe:** com `None`, devolve `None`, nunca um
   palpite.
4. **Transparência:**
   - o snapshot ganha a métrica `tariff_class`, com natureza `ASSUMPTION` quando
     presumida;
   - o executivo expõe `tariff_class` e `tariff_class_presumed`;
   - em "Detalhes da fatura", a aba Dinheiro diz se a classe foi lida, presumida ou não
     identificada;
   - a página "Como calculamos" (ADR-086) foi atualizada.

## Validação

- **Faturas reais:** as 30 faturas são lidas como `B1_RESIDENCIAL_CONVENCIONAL`.
- **Leitor e resolução** (`tests/test_tariff_class.py`): residencial, branca, baixa renda,
  comercial e rural; não identificada; nome do titular não capturado; regra
  presumida × não identificada.
- **Tarifas:** classe sem tarifa cadastrada ou `None` devolve `None`.
- **Migration e frontend:** contrato da migration e teste da tela do Dinheiro.

## Próximo passo (mercado brasileiro)

Ler a classe só resolve metade do problema. A outra metade é ter as tarifas homologadas de
cada distribuidora e classe. A fonte natural é a base aberta da ANEEL, com as tarifas de
aplicação de todas as distribuidoras. Isso, junto com leitores de fatura de outras
distribuidoras, fica para ADRs seguintes.
