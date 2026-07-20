# Runbook Google Cloud Deployment — Arquivado

Este documento foi substituído pelo runbook único e atualizado de produção:

```text
docs/runbook-producao.md
```

Não utilize os comandos de versões anteriores deste arquivo. O fluxo atual exige:

- secrets separadas para conexão Neon pooled e direta;
- subcomandos obrigatórios em `infra/gcp/set-secrets.sh`;
- projeto Cloudflare Pages no modo Direct Upload;
- CORS configurado antes do primeiro deploy do backend;
- migrações executadas com o endpoint direto;
- smoke tests sem senha em argumentos ou histórico.

Consulte somente `docs/runbook-producao.md` para implantação, rotação de secrets, migrações, frontend e verificações pós-deploy.
