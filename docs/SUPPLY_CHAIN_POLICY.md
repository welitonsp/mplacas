# Política de supply chain e builds reproduzíveis

## Contrato

- `requirements.lock` contém somente runtime; `requirements-dev.lock` inclui o extra `dev`.
- Instalações automatizadas usam `--require-hashes`; o projeto é instalado depois com
  `--no-deps --no-build-isolation`.
- Imagens Docker usam tag legível mais digest `sha256` obrigatório.
- GitHub Actions usam SHA completo de 40 caracteres, mantendo a versão humana em comentário.
- Dependabot propõe atualizações semanais para pip, npm, Actions e Docker.
- CodeQL, Gitleaks, auditorias, SBOM, Trivy e proveniência são bloqueantes conforme o workflow.

Exceções do Gitleaks devem usar apenas fingerprints completos em `.gitleaksignore`, vinculando
commit, arquivo, regra e linha. Não são permitidas exclusões amplas por diretório. As exceções atuais
correspondem exclusivamente aos valores sintéticos de JWT usados pelos testes e ao campo vazio do
arquivo de exemplo, todos revisados no PR da auditoria BIG TECH.

## Atualização dos locks

Execute `scripts/compile-locks.sh`, que roda o `pip-compile` dentro de um container baseado
exatamente na mesma imagem pinada por digest usada em `Dockerfile:1` (Python 3.12), com
`pip-tools==7.6.0` (mesma versão pinada no extra `dev` de `pyproject.toml`). Rodar dentro do
mesmo container do build evita divergência entre o ambiente de resolução e o runtime real —
tanto de versão do Python quanto de plataforma (`sys_platform`, markers condicionais):

```bash
scripts/compile-locks.sh
python -m pip install --dry-run --ignore-installed --require-hashes -r requirements.lock
python -m pip install --dry-run --ignore-installed --require-hashes -r requirements-dev.lock
```

Para atualizar (bump) um pacote específico, repasse `--upgrade-package <nome>` — sem isso o
`pip-compile` preserva os pins existentes que ainda satisfazem o range do `pyproject.toml`:

```bash
scripts/compile-locks.sh --upgrade-package <nome>
```

Requer Docker disponível localmente ou em CI. Mudanças no `pyproject.toml` sem atualização dos
dois locks devem falhar na revisão. Não editar versões ou hashes manualmente.

## Atualização de Actions e imagens

Resolva a tag oficial para o commit e fixe o SHA; para tag anotada use o objeto dereferenciado
`refs/tags/<tag>^{}`. Para imagens, consulte o digest do manifest oficial no registry. Toda mudança
de pin deve vir com execução verde de CI, scan e SBOM. Não aceitar `@main`, `@master`, `@vN` ou
imagem de produção apenas por tag.

## Evidência e exceções

Attestations são emitidas em pushes para `main`. Relatórios de dependências, SBOM e vulnerabilidades
ficam como artifacts. Uma exceção precisa indicar pacote/CVE, razão de não aplicabilidade, owner e
prazo; exclusões globais ou sem vencimento são proibidas.
