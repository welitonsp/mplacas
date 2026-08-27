# Estudo de custo — pagar o Neon valeria a pena?

**Data:** 2026-08-27 · **Pergunta do dono:** *"o que seria por mês se eu pagasse o Neon?"*

Preços conferidos na fonte em 2026-08-27, não de memória — confiar em memória de preço de free tier
foi exatamente o que originou a cobrança do Google Cloud.

## Resposta curta

**Cerca de R$ 3,00 por mês.** E a recomendação é **não pagar** — não por ser caro, mas porque
pagar **inverte o seu perfil de risco** justamente na dimensão que te machucou.

## Preços vigentes (fonte: neon.com/pricing e docs/introduction/plans)

Mudança relevante: **desde dezembro/2025 não existe mínimo mensal.** O Launch virou pagamento por
uso puro — um projeto que consome US$ 3 é cobrado US$ 3.

| | Free | Launch | Scale |
|---|---|---|---|
| Mensalidade | US$ 0 | por uso, sem mínimo | por uso, sem mínimo |
| Compute | 100 CU-horas incluídas | US$ 0,106/CU-hora | US$ 0,222/CU-hora |
| Armazenamento | 0,5 GB | US$ 0,35/GB-mês | US$ 0,35/GB-mês |
| Janela de PITR | **6 horas** | **até 7 dias** | até 30 dias |
| Ao estourar | **compute suspenso** até o ciclo virar | cobra | cobra |

1 CU = 1 vCPU + 4 GB RAM. Câmbio usado: US$ 1 = R$ 5,15 (26/08/2026).

## Seu uso real

O Neon hiberna 5 minutos após a última consulta. O custo é o tempo **acordado**, não o número de
consultas — por isso o que importa é quantas vezes por dia algo desperta o banco.

| Evento | Desperta o banco? | Tempo/dia |
|---|---|---|
| Ciclo operacional 06:07 (9 passos) | sim | ~13 min |
| Backup diário 07:00 (dump de 60 KB) | sim | ~6 min |
| Visitas ao dashboard | sim | ~20 min |
| Vigia a cada 6 h | **não** — `/health` faz zero consulta | 0 min |
| **Total** | | **~39 min/dia** |

- **~20 horas acordado por mês**
- A 0,25 CU (o tamanho mínimo, o mesmo que o free usa): **~4,9 CU-horas/mês**
- Isso é **5% da franquia gratuita de 100 CU-horas**

O tamanho do banco é minúsculo: o dump criptografado de 2026-08-21 tem **60 KB**. Mesmo com índices
e histórico, o armazenamento fica bem abaixo dos 0,5 GB do plano gratuito.

## Se você pagasse mesmo assim

| Item | USD/mês | BRL/mês |
|---|---|---|
| Compute (4,9 CU-horas) | 0,52 | 2,70 |
| Armazenamento (~0,2 GB) | 0,07 | 0,36 |
| **Total** | **0,59** | **~3,06** |

Some ainda IOF e spread do cartão sobre uma cobrança internacional — sobre R$ 3, é ruído, mas é
cobrança em dólar num cartão brasileiro, o que traz variação cambial mensal.

## Por que a recomendação é continuar no gratuito

### 1. Você usa 5% da franquia

O incidente de 2026-08-21 **não foi o plano gratuito ser pequeno demais.** Foi um defeito: dois jobs
a cada 5 minutos mantinham o banco acordado ~730 h/mês, o que dá 182 CU-horas contra uma franquia de
100. Com os jobs consolidados num ciclo diário, o consumo caiu para ~5 CU-horas. Sobra **20 vezes**
o que você usa.

Pagar hoje resolveria um problema que não existe mais.

### 2. O plano gratuito falha fechado — e isso é uma proteção, não um defeito

Este é o ponto central, e é contraintuitivo:

| Situação | No gratuito | No Launch |
|---|---|---|
| Uso normal | R$ 0 | ~R$ 3/mês |
| Bug igual ao de 21/08 (banco 24/7 a 0,25 CU) | **para de funcionar, R$ 0** | **R$ 99/mês** |
| Autoscale sobe para 1 CU sob carga | não acontece | **R$ 399/mês** |
| Autoscale 4 CU sustentado | não acontece | **R$ 1.594/mês** |

O plano gratuito transformou um defeito de software num **sistema parado**. O plano pago
transformaria o mesmo defeito numa **fatura**. Para quem declarou não ter orçamento, o teto rígido
vale mais do que a disponibilidade contínua.

### 3. O limite de gasto do Neon hoje é alerta, não trava

Verificado em `neon.com/docs/introduction/spending-limit`, e é o achado mais importante deste estudo:

> *"Currently, email alerts are the only available action. Automatic project suspension is coming
> soon: when the threshold is reached, projects' computes will pause..."*
>
> *"Projects continue to run, and charges continue to accumulate, until you raise the threshold or
> the billing cycle resets."*

Ou seja: dá para configurar limite de US$ 1 e receber e-mail em 80% e 100% — mas **nada para de
cobrar**. É exatamente a mesma classe de mecanismo que existia no Google Cloud e não impediu a
cobrança que motivou toda esta migração.

**Quando a suspensão automática for lançada, esta conclusão merece ser reavaliada.**

### 4. O único ganho técnico real já está coberto de outro jeito

Pagar levaria a janela de PITR de 6 horas para 7 dias — e essa era a fragilidade residual apontada no
achado A-03 da auditoria. Mas ela já foi endereçada por outro caminho: o snapshot lógico diário foi
religado em 2026-08-27, com **35 dias de retenção** e cópia **fora do provedor** (artifact do GitHub).

O backup lógico cobre inclusive o que o PITR não cobre em plano nenhum: perda de acesso à própria
conta Neon.

## Quando reabrir esta decisão

Pagar passa a fazer sentido se **qualquer um** destes acontecer:

1. **Consumo passar de ~70 CU-horas/mês** (70% da franquia) de forma sustentada e legítima — hoje
   está em ~5.
2. **Banco passar de 0,4 GB** (80% do limite de 0,5 GB).
3. **A aplicação ganhar usuários reais**, em que hibernar e ficar indisponível deixa de ser
   aceitável.
4. **O Neon lançar a suspensão automática no limite de gasto** — isso remove a objeção principal, e
   com teto real US$ 1/mês compraria margem de tranquilidade por um valor irrisório.

Enquanto nenhum deles for verdade, pagar compra risco de fatura sem comprar capacidade necessária.

## Como monitorar sem pagar nada

- **Mensal:** conferir o consumo de CU-horas no painel do Neon. É o número que decide o item 1 acima.
- **Automático:** o `operational-watchdog` do ciclo diário já falha quando o pipeline não roda, e a
  cota esgotada é uma das causas — foi assim que o incidente de 21/08 apareceu nos logs
  (`pg_dump: ... exceeded the compute time quota`).

## Fontes

- `neon.com/pricing` — preços por CU-hora e por GB-mês, planos
- `neon.com/docs/introduction/plans` — franquias do Free, janelas de PITR
- `neon.com/docs/introduction/spending-limit` — comportamento do limite de gasto
- Câmbio USD/BRL de 2026-08-26
- Uso do projeto derivado de `.github/workflows/operational-jobs.yml`,
  `.github/workflows/restore-drill.yml`, `src/mplacas/main.py` e do artifact de backup de 2026-08-21
