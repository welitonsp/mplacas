# Política — custo zero no Mplacas

**Status: OBRIGATÓRIA.** Declarada pelo dono em 2026-08-27.

## A restrição

O Mplacas é de **uso pessoal**. O dono **não tem interesse em pagar** por infraestrutura — não é
questão de o preço estar alto, é decisão sobre a natureza do projeto.

Isso é restrição de projeto, não preferência do momento. Toda decisão técnica precisa caber nela, e
uma proposta que só funciona pagando é uma proposta rejeitada, por melhor que seja tecnicamente.

Consequência prática que costuma ser mal interpretada: **indisponibilidade é aceitável, cobrança
não.** Se for preciso escolher entre o sistema ficar fora do ar e gerar fatura, ele fica fora do ar.

## Por que isto está escrito, e travado por teste

Duas interrupções em um mês, ambas pelo mesmo mecanismo — algo passou a rodar com frequência alta o
bastante para nunca deixar o recurso hibernar:

| Data | O que houve |
|---|---|
| 2026-08-21 | Dois jobs em `*/5 * * * *` mantiveram o Neon acordado ~730 h/mês: 182 CU-horas contra franquia de 100. Sistema parado 4 dias, backup quebrado junto |
| 2026-08-26 | Cobrança do Google Cloud sem orçamento previsto, que levou à saída do provedor (ADR-076) |

Nenhuma das duas foi falta de cuidado no momento da decisão. Ambas foram consequência indireta de
mudanças que pareciam inofensivas. Por isso as invariantes abaixo são **verificadas por
`tests/test_zero_cost_contract.py`**, não confiadas à disciplina.

## Invariantes

### 1. Nenhuma agenda roda em intervalo menor que 6 horas

O custo não vem do número de consultas — vem do **tempo acordado**. O Neon hiberna 5 minutos após a
última consulta; o Render, 15 minutos sem tráfego. O que importa é quantas vezes por dia algo os
desperta.

Agenda de 6 em 6 horas custa ~30 h/mês de instância. De 5 em 5 minutos mantém tudo acordado o mês
inteiro. Foi essa a diferença entre funcionar e parar.

### 2. `/health` não consulta o banco

É o endpoint que o vigia bate a cada 6 horas. Enquanto devolve estado estático, o ping acorda apenas
o Render e consome **zero** compute do Neon. Uma consulta ali transformaria o próprio monitoramento
em fonte de consumo.

Verificação de dependência é papel de `/ready`, que ninguém agenda.

### 3. Nada de keep-alive contra a hibernação

O plano free do Render dá 750 h de instância por mês, e o mês tem ~730 h — praticamente sem folga.
Um keep-alive periódico consome tudo **e** mantém o Neon acordado, reproduzindo o incidente por
outro caminho.

O cold start de 30 a 60 segundos é o **preço aceito** do custo zero, não um defeito a corrigir.

### 4. O Render permanece no plano gratuito

### 5. Google Cloud continua proibido

Regra própria, em `docs/POLITICA_SEM_GOOGLE_CLOUD.md`.

## Arquitetura em vigor

| Peça | Onde | Custo |
|---|---|---|
| Frontend | Cloudflare Pages | grátis |
| Banco | Neon, plano Free | grátis |
| API | Render, plano free | grátis |
| Jobs, migrações, backup, vigia | GitHub Actions | grátis e ilimitado (repositório público) |
| Alertas | Telegram | grátis |

Consumo atual do Neon: **~5% da franquia gratuita** — cerca de 4,9 CU-horas de 100. Há margem de
20 vezes. Ver `docs/ESTUDO_CUSTO_NEON_2026-08-27.md` para a memória de cálculo.

## O que fazer se a franquia gratuita apertar

A resposta **não** é migrar para o plano pago. Em ordem:

1. **Investigar antes de aceitar.** As duas vezes que a franquia estourou, a causa foi defeito, não
   crescimento legítimo. Consumo subindo sem uso novo é bug até prova em contrário.
2. **Reduzir despertares.** Consolidar jobs numa janela única, aumentar intervalos, remover
   consultas de caminhos quentes.
3. **Reduzir o que é guardado.** Ajustar as janelas de retenção.
4. **Só então** reabrir a discussão de plataforma — e ainda assim procurando alternativa gratuita,
   não o plano pago do provedor atual.

## Sobre limite de gasto como rede de proteção

Não conte com ele. Verificado em 2026-08-27 na documentação do Neon: o limite de gasto **hoje é
apenas alerta por e-mail**. Nas palavras da própria documentação, *"projects continue to run, and
charges continue to accumulate"*. Suspensão automática está anunciada como "coming soon".

É a mesma classe de mecanismo que existia no Google Cloud e não impediu a cobrança de agosto.

**A única proteção confiável hoje é o teto rígido do plano gratuito**, que suspende o recurso em vez
de faturar. Que o plano gratuito falhe fechado é característica desejada aqui, não limitação.

## Alterar esta política

Exige decisão explícita do dono registrada em ADR novo, aceitando conscientemente a possibilidade de
cobrança. Afrouxar uma invariante para "resolver" um sintoma — cold start, latência, indisponibilidade
— é justamente o caminho que as duas interrupções tomaram.
