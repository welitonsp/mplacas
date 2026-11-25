from __future__ import annotations

import json
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
    session = (ROOT / "frontend" / "src" / "lib" / "session.ts").read_text(encoding="utf-8")
    backend = (ROOT / "src" / "mplacas" / "auth" / "router.py").read_text(
        encoding="utf-8"
    )

    assert "TokenStore.clear()" in frontend
    assert "void revokeSession()" in frontend
    # Expiração limpa só o local; o revoke no servidor é só do logout voluntário.
    expire = frontend.split("const expireSession")[1].split("}, [")[0]
    assert "revokeSession" not in expire
    # Corrida de identidade (revisão do 8f125df): época da sessão e abertura de
    # sessão atrás do lock do refresh.
    assert "markSessionChanged()" in frontend
    assert "await openSession(" in frontend
    assert "epoch !== sessionEpoch" in session
    assert "LOGOUT_LOCK_WAIT_MS = 3_000" in session
    # ADR-102: logout pelo cookie — sem corpo, mesma origem, com o cabeçalho
    # CSRF, e `keepalive` para terminar mesmo com a aba fechando.
    assert "`${API_URL}/auth/logout`" in session
    assert "keepalive: true" in session
    assert '@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)' in backend


def _frontend_app_sources() -> dict[str, str]:
    """Código de aplicação do frontend, sem testes (que podem citar o proibido)."""
    sources: dict[str, str] = {}
    for path in (ROOT / "frontend" / "src").rglob("*"):
        if not path.is_file() or path.suffix not in {".ts", ".tsx", ".js", ".mjs"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if ".test." in path.name or "/src/test/" in rel:
            continue
        sources[rel] = path.read_text(encoding="utf-8")
    return sources


def test_frontend_never_touches_cookies_or_refresh_tokens() -> None:
    """ADR-102: o refresh token mora num cookie HttpOnly que o JS não lê.

    Nenhum código de aplicação pode mexer em `document.cookie` nem mencionar
    `refresh_token` (ler do corpo, guardar ou enviar). Os testes ficam de fora
    porque simulam respostas do backend que ainda trazem o campo.
    """
    sources = _frontend_app_sources()
    assert sources, "nenhum arquivo de frontend encontrado"
    touching_cookie = sorted(p for p, c in sources.items() if "document.cookie" in c)
    assert not touching_cookie, f"document.cookie no frontend: {touching_cookie}"
    mentioning_refresh = sorted(
        p for p, c in sources.items() if re.search(r"refresh_?token", c, re.IGNORECASE)
    )
    assert not mentioning_refresh, f"refresh token tratado no frontend: {mentioning_refresh}"


def test_auth_client_uses_same_origin_credentials_and_csrf_header() -> None:
    session = (ROOT / "frontend" / "src" / "lib" / "session.ts").read_text(encoding="utf-8")
    api = (ROOT / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
    env = (ROOT / "frontend" / "src" / "env.ts").read_text(encoding="utf-8")

    assert "credentials: 'same-origin'" in session
    assert "headers.set('X-Mplacas-Auth', '1')" in session
    # Com a página em `Referrer-Policy: no-referrer`, a especificação manda
    # `Origin: null` em POST — que o backend recusa. Por pedido, mantém o Origin.
    assert "referrerPolicy: 'same-origin'" in session
    # Serialização entre abas (rotação do refresh token).
    assert "navigator.locks" in session
    assert "'mplacas-refresh'" in session
    # Todas as chamadas de dados também ficam na própria origem.
    assert api.count("credentials: 'same-origin'") >= 3
    assert "export const API_URL = '/api'" in env
    assert "VITE_API_URL" not in env.split("export const API_URL")[1]
    assert "include'" not in session and "include'" not in api


def test_cloudflare_proxy_routes_only_api() -> None:
    routes = json.loads(
        (ROOT / "frontend" / "public" / "_routes.json").read_text(encoding="utf-8")
    )
    assert routes == {"version": 1, "include": ["/api/*"], "exclude": []}
    assert (ROOT / "frontend" / "functions" / "api" / "[[path]].ts").is_file()
    # Só o ponto de entrada mora em `functions/`: todo arquivo lá vira rota.
    function_files = sorted(
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "frontend" / "functions").rglob("*")
        if p.is_file()
    )
    assert function_files == ["frontend/functions/api/[[path]].ts"]

    proxy = (ROOT / "frontend" / "edge" / "apiProxy.ts").read_text(encoding="utf-8")
    # Falha fechada e nada de log.
    assert "genericError(503" in proxy
    assert "console." not in proxy
    for header in ("'x-mplacas-client-ip'", "'x-mplacas-proxy-secret'", "'x-forwarded-for'"):
        assert header not in proxy.split("FORWARDED_REQUEST_HEADERS")[1].split("]")[0]
    assert "getSetCookie()" in proxy


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
    # geolocation=(self): o botão "Usar a localização deste aparelho" da tela de
    # cadastro da usina precisa da API; `()` a bloquearia até para o próprio site.
    assert (
        "Permissions-Policy: camera=(), microphone=(), geolocation=(self), payment=()"
        in header_lines
    )
    # ADR-102: a API é a própria origem (proxy `/api/*` da Pages Function).
    # `connect-src` é exatamente `'self'`: nenhum host externo, nenhum
    # `https:` genérico, nenhum marcador do antigo `render-csp.mjs`.
    connect_src = re.findall(r"connect-src[^;]*;", headers)
    assert connect_src == ["connect-src 'self';"]
    assert "__API_ORIGIN__" not in headers
    assert "/assets/*" in headers
    assert "Cache-Control: public, max-age=31536000, immutable" in headers
    for term in (
        "somente em memória",
        "POST /auth/logout",
        "redirecionamento `308`",
        "Wildcard",
        "connect-src 'self'",
        "MPLACAS_PROXY_SHARED_SECRET",
        "_routes.json",
    ):
        assert term in contract
