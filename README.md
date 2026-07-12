# Mplacas

Plataforma de inteligência, auditoria e gestão energética residencial.

## Objetivo

Consolidar telemetria da NEPViewer, dados climáticos e faturas da Equatorial para produzir histórico próprio, conciliação energética, alertas e relatórios auditáveis.

## Estado atual — Fundação P0

- API FastAPI com endpoints `/health` e `/ready`;
- configuração tipada por variáveis de ambiente;
- contrato substituível `SolarProvider`;
- adaptador inicial para a API NEPViewer v2;
- autenticação com renovação automática após 401/403;
- validação explícita contra mudança de schema;
- tratamento de timeout e indisponibilidade;
- suporte a dispositivos, visão geral e energia diária;
- contorno para consulta de um único dia;
- testes unitários e de contrato;
- CI com Ruff, Mypy e Pytest;
- proteção contra commit de credenciais, PDFs e dados privados.

> A API NEPViewer usada é uma interface web não oficial e pode mudar. O adaptador é isolado para impedir acoplamento do restante do sistema.

## Execução local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
cp .env.example .env
uvicorn mplacas.main:app --reload
```

Acesse:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/ready`
- `http://127.0.0.1:8000/docs`

## Segurança

Nunca registre no GitHub:

- senha da NEPViewer;
- token do Telegram;
- faturas de energia;
- CPF, endereço ou unidade consumidora;
- dumps de respostas com dados pessoais.

Use variáveis de ambiente ou GitHub Secrets. O sistema não expõe credenciais nos endpoints operacionais.

## Próximas fases

1. PostgreSQL e histórico diário versionado;
2. scheduler de coleta e backfill D+1;
3. bot Telegram com lista de usuários autorizados;
4. parser determinístico da fatura Equatorial;
5. motor de conciliação por ciclo de leitura;
6. painel web e relatórios;
7. clima, anomalias e explicações assistidas por IA.
