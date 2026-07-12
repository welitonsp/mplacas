# Mplacas

Plataforma de inteligência, auditoria e gestão energética residencial.

## Objetivo

Consolidar telemetria da NEPViewer, dados climáticos e faturas da Equatorial para produzir histórico próprio, conciliação energética, alertas e relatórios auditáveis.

## Estado atual — Fundação e Persistência P1

- API FastAPI com endpoints `/health` e `/ready`;
- configuração tipada por variáveis de ambiente;
- contrato substituível `SolarProvider`;
- adaptador para a API NEPViewer v2;
- autenticação com renovação automática após 401/403;
- validação explícita contra mudança de schema;
- tratamento de timeout e indisponibilidade;
- SQLAlchemy assíncrono com PostgreSQL e SQLite;
- migrações Alembic;
- modelos de usina, dispositivo, produção diária e versões históricas;
- persistência idempotente com `Decimal`;
- coleta transacional NEPViewer → banco;
- política intradiária, consolidação D+1 e backfill semanal;
- testes unitários, de contrato e persistência;
- CI com Ruff, Mypy e Pytest;
- proteção contra commit de credenciais, PDFs e dados privados.

> A API NEPViewer usada é uma interface web não oficial e pode mudar. O adaptador é isolado para impedir acoplamento do restante do sistema.

## Ciclo de vida dos dados

1. Durante o dia, a produção é coletada como `PROVISIONAL`.
2. No dia seguinte, o valor é reconsultado e marcado como `CONSOLIDATED`.
3. Semanalmente, os sete últimos dias encerrados são reconsultados.
4. Mudanças retroativas preservam a versão anterior.
5. Falhas durante a coleta provocam rollback integral.

## Execução local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
cp .env.example .env
alembic upgrade head
uvicorn mplacas.main:app --reload
```

Acesse:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/ready`
- `http://127.0.0.1:8000/docs`

## Banco

O padrão de desenvolvimento é SQLite. Para PostgreSQL, configure:

```text
MPLACAS_DATABASE_URL=postgresql+asyncpg://usuario:senha@host:5432/mplacas
```

## Segurança

Nunca registre no GitHub:

- senha da NEPViewer;
- token do Telegram;
- faturas de energia;
- CPF, endereço ou unidade consumidora;
- dumps de respostas com dados pessoais.

Use variáveis de ambiente ou secrets do ambiente de hospedagem. O sistema não expõe credenciais nos endpoints operacionais.

## Próximas fases

1. scheduler de execução e observabilidade persistente;
2. bot Telegram com lista de usuários autorizados;
3. parser determinístico da fatura Equatorial;
4. motor de conciliação por ciclo de leitura;
5. painel web e relatórios;
6. clima, anomalias e explicações assistidas por IA.
