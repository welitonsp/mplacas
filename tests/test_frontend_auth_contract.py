from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Substrings that would flag a localStorage key as credential-shaped. Case
# insensitive, checked against the literal string argument passed to
# setItem/getItem/removeItem — never against arbitrary code.
_CREDENTIAL_LIKE = (
    "token",
    "cred",
    "secret",
    "password",
    "jwt",
    "session",
    "api_key",
    "apikey",
)

# Explicit allowlist of non-sensitive localStorage keys the frontend is
# permitted to read/write, with the reason documented alongside. Anything not
# in this list, or anything credential-shaped, fails the test below. Add an
# entry here (with a reason) rather than loosening the assertion.
_ALLOWED_KEYS = {
    "mplacas_creds_v1": (
        "legacy key from a pre-refactor build; only ever removed on "
        "startup (frontend/src/main.tsx), never written"
    ),
    "mplacas:technical-performance-expanded": (
        "UI preference (whether the technical performance section starts "
        "expanded) — not sensitive, no credential/token value"
    ),
    "mplacas:theme": (
        "UI preference (explicit light/dark theme override; absence of the "
        "key means 'follow the OS preference', ADR-071) — not sensitive, no "
        "credential/token value"
    ),
}

_KEY_CALL = re.compile(
    r"localStorage\.(setItem|getItem|removeItem)\(\s*['\"]([^'\"]+)['\"]"
)


def test_frontend_never_persists_tokens_or_operational_keys() -> None:
    sources = {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in (ROOT / "frontend" / "src").rglob("*")
        if path.is_file()
    }

    calls: set[tuple[str, str]] = set()
    for content in sources.values():
        calls.update(_KEY_CALL.findall(content))

    # setItem is the only call that persists a value — that's the one that
    # can actually leak a credential to disk. getItem/removeItem only ever
    # read or clean up, so a credential-shaped key there (e.g. removing the
    # legacy 'mplacas_creds_v1' on startup) is safe by construction.
    written_credential_like = sorted(
        key
        for method, key in calls
        if method == "setItem" and any(marker in key.lower() for marker in _CREDENTIAL_LIKE)
    )
    assert not written_credential_like, (
        "localStorage.setItem with a credential-shaped key, never persist "
        f"these: {written_credential_like}"
    )

    keys_used = {key for _method, key in calls}
    unlisted = sorted(keys_used - _ALLOWED_KEYS.keys())
    assert not unlisted, (
        "localStorage key(s) not in the allowlist above — add an entry with a "
        f"reason if this is legitimate, non-sensitive UI state: {unlisted}"
    )

    assert all("sessionStorage" not in content for content in sources.values())


def test_logout_revokes_server_session_best_effort() -> None:
    frontend = (ROOT / "frontend" / "src" / "contexts" / "AuthContext.tsx").read_text(
        encoding="utf-8"
    )
    backend = (ROOT / "src" / "mplacas" / "auth" / "router.py").read_text(
        encoding="utf-8"
    )

    assert "TokenStore.clear()" in frontend
    assert "refreshTokenRef.current = null" in frontend
    assert "`${API_URL}/auth/logout`" in frontend
    assert "keepalive: true" in frontend
    assert '@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)' in backend


def test_canonical_contract_and_cloudflare_headers_are_complete() -> None:
    contract = (ROOT / "docs" / "AUTH_FRONTEND_CONTRACT.md").read_text(encoding="utf-8")
    headers = (ROOT / "frontend" / "public" / "_headers").read_text(encoding="utf-8")
    required_headers = {
        "Content-Security-Policy:",
        "Strict-Transport-Security:",
        "X-Content-Type-Options: nosniff",
        "X-Frame-Options: DENY",
        "Referrer-Policy: no-referrer",
        "Permissions-Policy:",
        "Cross-Origin-Opener-Policy: same-origin",
        "Cross-Origin-Resource-Policy: same-origin",
        "X-Permitted-Cross-Domain-Policies: none",
    }

    header_lines = [line.strip() for line in headers.splitlines()]
    assert all(
        any(line.startswith(required) for line in header_lines)
        for required in required_headers
    )
    assert "connect-src 'self' https:;" not in headers
    # A origem da API no CSP e a origem que o cliente HTTP chama vêm da MESMA
    # variável (VITE_API_URL), resolvida no build por
    # `frontend/scripts/render-csp.mjs`. Antes disso a origem ficava escrita à
    # mão aqui e sobreviveu à migração de plataforma apontando para um projeto
    # do Google Cloud excluído — a aplicação carregava e o navegador bloqueava
    # todo `fetch`, sem erro de servidor, log ou CI vermelho para acusar
    # (auditoria 2026-08-26, achado A-01).
    #
    # O contrato aqui é sobre o TEMPLATE versionado, não sobre o arquivo gerado:
    # o marcador precisa estar presente e nenhuma origem concreta pode aparecer.
    assert "connect-src 'self' __API_ORIGIN__;" in headers
    assert not re.search(r"connect-src[^;]*https://[^;]*\.(run\.app|onrender\.com)", headers)
    assert "/assets/*" in headers
    assert "Cache-Control: public, max-age=31536000, immutable" in headers
    for term in ("somente em memória", "POST /auth/logout", "redirecionamento `308`", "Wildcard"):
        assert term in contract
