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

### Exceção ativa: edição manual de hash em `pypdf` (2026-08-09)

`pypdf` 6.14.2 → 6.15.0 em `requirements.lock`/`requirements-dev.lock` (commit `07fd426`) corrigiu
CVE-2026-71852 e CVE-2026-71870 (DoS por exaustão de recurso ao processar PDF malformado — caminho
relevante: `src/mplacas/telegram/pdf.py` extrai texto de PDF enviado pelo usuário via fatura no
Telegram). O range em `pyproject.toml` (`>=6.14.2,<7`) já cobria a versão nova; só os lockfiles
precisavam de bump.

**Razão do desvio**: `scripts/compile-locks.sh` requer Docker, indisponível no ambiente onde a
correção foi feita; `pip-tools==7.6.0` local está quebrado por incompatibilidade com `pip==26.2`
(`ImportError: cannot import name 'stdlib_pkgs'`). Os dois hashes (wheel + sdist) foram obtidos e
conferidos **duas vezes de forma independente** direto da API JSON oficial do PyPI
(`https://pypi.org/pypi/pypdf/6.15.0/json`) — uma vez por quem aplicou a correção, uma segunda vez
por revisão independente (`reviewer`) antes do push, ambas batendo byte a byte. Nenhum outro pin foi
tocado (confirmado via `git show 07fd426`).

**O que esta exceção não cobre**: nem `scripts/check_lock_drift.py` nem
`tests/test_supply_chain_contract.py` recalculam hash contra o PyPI — nenhum dos dois guardrails
automatizados teria detectado um erro nesta edição manual caso ele tivesse ocorrido. A garantia aqui
é só a dupla verificação humana/agente registrada acima, não o CI.

**Owner e prazo**: dono do repositório (Weliton). Regenerar `requirements.lock`/`requirements-dev.lock`
via `scripts/compile-locks.sh` (Docker) assim que disponível, substituindo esta edição manual por uma
gerada pelo processo padrão — o mais tardar no próximo ciclo semanal do Dependabot para `pip`, que já
vai tocar esses arquivos de qualquer forma. Remover esta seção quando a regeneração acontecer.
