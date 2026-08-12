"""Regression test for the CORS ``expose_headers`` configuration.

``src/mplacas/main.py`` registers ``CORSMiddleware`` with
``expose_headers=["Content-Disposition"]`` (see ``main.py`` around the
``CORSMiddleware`` block). Without it, the frontend can never read the
``Content-Disposition`` header on a cross-origin response — the browser
silently drops it, and ``filenameFromContentDisposition`` in
``frontend/src/lib/api.ts`` always falls back to a generic filename. None of
the other 838 backend tests exercise this because ``tests/conftest.py``
never configures an allowed CORS origin, so ``CORSMiddleware`` is never even
registered under pytest (see ``main.py``:
``_cors_origins = _settings_for_startup.cors_allowed_origin_list`` /
``if _cors_origins: app.add_middleware(CORSMiddleware, ...)``, evaluated at
*module import time*, and ``core/config.py``'s
``cors_allowed_origin_list`` returning ``[]`` when unset).

Because that registration happens at import time in module-global scope
(not inside a factory function), monkeypatching settings after
``mplacas.main`` has already been imported has no effect — the middleware
either was or wasn't added, and that decision is frozen. The only way to
observe the "CORS configured" branch is to force the module to be
re-evaluated with the environment variable already set, via
``importlib.reload``. To avoid leaking a CORS-enabled app (and a
CORS-enabled ``get_settings()`` cache) into the other 838 tests, this test
explicitly unwinds both in a ``finally`` block: it clears the env var,
clears the ``get_settings`` cache, and reloads ``mplacas.main`` a second
time so the module ends the test in exactly the state it started in (no
allowed origins, no ``CORSMiddleware``).
"""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

import mplacas.main as main_module
from mplacas.core.config import get_settings

_ALLOWED_ORIGIN = "https://mplacas-frontend.pages.dev"


def test_cors_exposes_content_disposition_header_for_allowed_origin(monkeypatch) -> None:
    monkeypatch.setenv("MPLACAS_CORS_ALLOWED_ORIGINS", _ALLOWED_ORIGIN)
    get_settings.cache_clear()
    importlib.reload(main_module)
    try:
        client = TestClient(main_module.app)

        response = client.get("/health", headers={"Origin": _ALLOWED_ORIGIN})

        assert response.status_code == 200
        exposed_headers = response.headers.get("access-control-expose-headers", "")
        assert "Content-Disposition" in exposed_headers
    finally:
        # Restore the module to its pristine (no-CORS-configured) state so the
        # remaining 838 tests keep running against the same app they always did.
        monkeypatch.delenv("MPLACAS_CORS_ALLOWED_ORIGINS", raising=False)
        get_settings.cache_clear()
        importlib.reload(main_module)


def test_cors_middleware_is_not_registered_without_configured_origins() -> None:
    # Sanity check for the isolation claim above: under the default pytest
    # environment (no MPLACAS_CORS_ALLOWED_ORIGINS), CORSMiddleware never
    # runs, so no Origin header produces no CORS response headers at all.
    response = TestClient(main_module.app).get(
        "/health", headers={"Origin": _ALLOWED_ORIGIN}
    )

    assert response.status_code == 200
    assert "access-control-expose-headers" not in response.headers
    assert "access-control-allow-origin" not in response.headers
