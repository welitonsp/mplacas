from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_never_persists_tokens_or_operational_keys() -> None:
    sources = {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in (ROOT / "frontend" / "src").rglob("*")
        if path.is_file()
    }
    local_storage = [
        (name, line)
        for name, content in sources.items()
        for line in content.splitlines()
        if "localStorage" in line
    ]

    assert local_storage == [
        ("frontend/src/main.tsx", "window.localStorage.removeItem('mplacas_creds_v1')")
    ]
    assert all("sessionStorage" not in content for content in sources.values())
    assert all("localStorage.setItem" not in content for content in sources.values())


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
    assert (
        "connect-src 'self' https://mplacas-api-104231254500.us-central1.run.app;"
        in headers
    )
    assert "/assets/*" in headers
    assert "Cache-Control: public, max-age=31536000, immutable" in headers
    for term in ("somente em memória", "POST /auth/logout", "redirecionamento `308`", "Wildcard"):
        assert term in contract
