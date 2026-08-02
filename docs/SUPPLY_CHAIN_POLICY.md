# Política de supply chain e builds reproduzíveis

## Contrato

- `requirements.lock` contém somente runtime; `requirements-dev.lock` inclui o extra `dev`.
- Instalações automatizadas usam `--require-hashes`; o projeto é instalado depois com
  `--no-deps --no-build-isolation`.
- Imagens Docker usam tag legível mais digest `sha256` obrigatório.
- GitHub Actions usam SHA completo de 40 caracteres, mantendo a versão humana em comentário.
- Dependabot propõe atualizações semanais para pip, npm, Actions e Docker.
- CodeQL, Gitleaks, auditorias, SBOM, Trivy e proveniência são bloqueantes conforme o workflow.

## Atualização dos locks

Execute com Python 3.12, a mesma versão do CI e da imagem:

```bash
python -m pip install 'pip-tools==7.6.0'
pip-compile pyproject.toml --generate-hashes --strip-extras --allow-unsafe --output-file=requirements.lock
pip-compile pyproject.toml --extra dev --generate-hashes --strip-extras --allow-unsafe --output-file=requirements-dev.lock
python -m pip install --dry-run --ignore-installed --require-hashes -r requirements.lock
python -m pip install --dry-run --ignore-installed --require-hashes -r requirements-dev.lock
```

Mudanças no `pyproject.toml` sem atualização dos dois locks devem falhar na revisão. Não editar
versões ou hashes manualmente.

## Atualização de Actions e imagens

Resolva a tag oficial para o commit e fixe o SHA; para tag anotada use o objeto dereferenciado
`refs/tags/<tag>^{}`. Para imagens, consulte o digest do manifest oficial no registry. Toda mudança
de pin deve vir com execução verde de CI, scan e SBOM. Não aceitar `@main`, `@master`, `@vN` ou
imagem de produção apenas por tag.

## Evidência e exceções

Attestations são emitidas em pushes para `main`. Relatórios de dependências, SBOM e vulnerabilidades
ficam como artifacts. Uma exceção precisa indicar pacote/CVE, razão de não aplicabilidade, owner e
prazo; exclusões globais ou sem vencimento são proibidas.
