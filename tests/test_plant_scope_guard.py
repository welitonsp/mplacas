"""Guard test for PR-2 of the multi-tenancy plan (see
``docs/CHECKLIST_SAAS_MULTITENANCY.md``, section P0).

Every route under a "data" prefix must resolve its ``plant_id`` through
``core.tenancy.ReadPlant`` / ``AdminPlant`` (i.e. declare a parameter annotated
with ``ScopedPlant``) instead of a manually-checked ``plant_id`` query param —
unless the route is explicitly allowlisted below with a reason.

This test starts with a large allowlist. Each subsequent PR in the plan
(billing, alerts, climate, orchestration) removes the corresponding entries as
those routers are migrated to the same structural pattern already applied here
to reports/intelligence/explanations.
"""

from __future__ import annotations

from typing import Annotated, Iterator, get_args, get_origin, get_type_hints

import fastapi.routing as fastapi_routing
from fastapi.routing import APIRoute

from mplacas.core.tenancy import ScopedPlant
from mplacas.main import app


def _iter_effective_routes() -> Iterator[object]:
    """Yield every route FastAPI will actually dispatch to, with its final
    (prefixed) path and merged dependencies.

    FastAPI (>=0.139) defers flattening ``include_router`` calls: ``app.routes``
    only contains top-level ``_IncludedRouter`` wrappers, not the underlying
    ``APIRoute`` objects with their fully-resolved paths. We must walk
    ``_IncludedRouter.effective_route_contexts()`` to get the real, final
    (method, path, endpoint) tuples used at request time.
    """
    for route in app.routes:
        if isinstance(route, fastapi_routing._IncludedRouter):
            yield from route.effective_route_contexts()
        elif isinstance(route, APIRoute):
            yield route

# Path prefixes that serve tenant-scoped operational/business data. Anything
# under these prefixes must either resolve plant_id via ReadPlant/AdminPlant,
# or be explicitly allowlisted below with a reason.
_DATA_PREFIXES = (
    "/billing",
    "/climate",
    "/reports",
    "/energy",  # covers both intelligence's "/energy/..." and
    # explanations' "/energy/explanations/..." routes
    "/alerts",
    "/pipeline",
    "/operations",
    "/telegram",
)

# (method, path) -> justification for not using ReadPlant/AdminPlant/ScopedPlant.
_ALLOWLIST: dict[tuple[str, str], str] = {
    # reports: plant_id is not a query parameter on these two routes — the
    # export task is looked up by task_id first, then
    # `principal.require_plant_access(task.plant_id)` validates against the
    # plant recorded on the persisted task. ReadPlant/AdminPlant only apply
    # when plant_id itself is the query parameter being resolved.
    ("GET", "/reports/monthly/exports/{task_id}"): (
        "plant_id is derived from the persisted export task (looked up by "
        "task_id), not from a query parameter — validated via "
        "principal.require_plant_access(task.plant_id) after lookup"
    ),
    ("GET", "/reports/monthly/exports/{task_id}/download"): (
        "plant_id is derived from the persisted export task (looked up by "
        "task_id), not from a query parameter — validated via "
        "principal.require_plant_access(task.plant_id) after lookup"
    ),
    # operations: org-wide operational visibility, deliberately not
    # plant-scoped (require_unrestricted_access, not require_plant_access).
    ("GET", "/operations/jobs"): (
        "uses principal.require_unrestricted_access() — org-wide operational "
        "job history, not scoped to a single plant"
    ),
    ("GET", "/operations/status"): (
        "uses principal.require_unrestricted_access() — org-wide operational "
        "status, not scoped to a single plant"
    ),
    # operations/credentials, operations/users: organization-scoped
    # management endpoints, not plant-scoped at all.
    ("POST", "/operations/credentials"): (
        "organization-scoped credential management "
        "(principal.require_unrestricted_access()), not plant-scoped"
    ),
    ("GET", "/operations/credentials"): (
        "organization-scoped credential management "
        "(principal.require_unrestricted_access()), not plant-scoped"
    ),
    ("POST", "/operations/credentials/{credential_id}/revoke"): (
        "organization-scoped credential management "
        "(principal.require_unrestricted_access()), not plant-scoped"
    ),
    ("POST", "/operations/users"): (
        "organization-scoped user management "
        "(principal.require_unrestricted_access()), not plant-scoped"
    ),
    ("GET", "/operations/users"): (
        "organization-scoped user management "
        "(principal.require_unrestricted_access()), not plant-scoped"
    ),
    ("POST", "/operations/users/{user_id}/deactivate"): (
        "organization-scoped user management "
        "(principal.require_unrestricted_access()), not plant-scoped"
    ),
    # billing: plant_id is carried in the JSON request body (BillTextIntake),
    # not a query parameter, so ReadPlant/AdminPlant (which resolve a query
    # param) do not apply directly. The handler instead depends on
    # core.tenancy.AdminPrincipal and calls
    # core.tenancy.resolve_admin_plant_scope(principal, payload.plant_id)
    # explicitly — the same organization-scoped resolve+validate logic,
    # applied to a body field instead of a query param.
    ("POST", "/billing/intake-text"): (
        "plant_id is a JSON body field (BillTextIntake.plant_id), not a query "
        "param — resolved via core.tenancy.resolve_admin_plant_scope(principal, "
        "payload.plant_id) using an injected AdminPrincipal"
    ),
    # alerts, climate, orchestration/pipeline: later PRs in the plan.
    ("POST", "/alerts/run"): "PR-4/5 pending — alerts not yet migrated",
    ("POST", "/climate/collect"): "PR-4/5 pending — climate not yet migrated",
    ("POST", "/pipeline/run"): "PR-4/5 pending — orchestration not yet migrated",
    ("GET", "/pipeline/status/latest"): (
        "PR-4/5 pending — orchestration not yet migrated"
    ),
    # telegram: webhook has no OperationsPrincipal at all (authenticated via a
    # shared webhook secret header, not an operational credential/bearer
    # token) and infers the single configured plant globally — out of scope
    # for the ReadPlant/AdminPlant pattern, addressed separately per the
    # architect's plan.
    ("POST", "/telegram/webhook"): (
        "webhook has no OperationsPrincipal — authenticated via Telegram's "
        "shared secret header, plant inferred globally; addressed by a "
        "dedicated PR in the multi-tenancy plan, not this structural change"
    ),
}


def _declares_scoped_plant(endpoint: object) -> bool:
    hints = get_type_hints(endpoint, include_extras=True)
    for hint in hints.values():
        if get_origin(hint) is Annotated:
            args = get_args(hint)
            if args and args[0] is ScopedPlant:
                return True
    return False


def test_data_routes_resolve_plant_scope_or_are_allowlisted() -> None:
    violations: list[tuple[str, str]] = []
    seen_prefixed_routes = 0

    for route in _iter_effective_routes():
        path = route.path
        if not path.startswith(_DATA_PREFIXES):
            continue
        seen_prefixed_routes += 1
        for method in route.methods:
            key = (method, path)
            if key in _ALLOWLIST:
                continue
            if not _declares_scoped_plant(route.endpoint):
                violations.append(key)

    # Sanity check: fail loudly if the prefixes above stop matching any route
    # at all (e.g. a prefix typo), rather than silently passing vacuously.
    assert seen_prefixed_routes > 0, "no routes matched the configured data prefixes"

    assert not violations, (
        "the following data routes do not declare ReadPlant/AdminPlant/ScopedPlant "
        "and are not in the allowlist above (add an allowlist entry with a reason, "
        "or migrate the route to core.tenancy.ReadPlant/AdminPlant): "
        f"{sorted(violations)}"
    )


def test_allowlist_entries_still_correspond_to_real_routes() -> None:
    """Prevent the allowlist from silently rotting as routes are renamed/removed."""
    known_routes = {
        (method, route.path) for route in _iter_effective_routes() for method in route.methods
    }
    stale = set(_ALLOWLIST) - known_routes
    assert not stale, f"allowlist entries reference routes that no longer exist: {stale}"
