from __future__ import annotations

import ast
from pathlib import Path

from mplacas.alerts import db_models as _alert_models  # noqa: F401
from mplacas.auth import db_models as _auth_models  # noqa: F401
from mplacas.audit import db_models as _audit_models  # noqa: F401
from mplacas.billing import db_models as _billing_models  # noqa: F401
from mplacas.climate import db_models as _climate_models  # noqa: F401
from mplacas.collection import db_models as _collection_models  # noqa: F401
from mplacas.credentials import db_models as _credential_models  # noqa: F401
from mplacas.db import models as _models  # noqa: F401
from mplacas.db.base import Base
from mplacas.db.rls_inventory import (
    PUBLIC_REFERENCE_TABLES,
    RLS_TABLES,
    RlsScope,
    classified_application_tables,
)
from mplacas.events import db_models as _event_models  # noqa: F401
from mplacas.market import db_models as _market_models  # noqa: F401
from mplacas.operations import models as _operation_models  # noqa: F401
from mplacas.orchestration import db_models as _orchestration_models  # noqa: F401
from mplacas.organizations import db_models as _organization_models  # noqa: F401
from mplacas.organizations import invitation_db_models as _invitation_models  # noqa: F401
from mplacas.photovoltaic import db_models as _photovoltaic_models  # noqa: F401
from mplacas.providers import db_models as _provider_models  # noqa: F401
from mplacas.reports import db_models as _report_models  # noqa: F401
from mplacas.tariffs import db_models as _tariff_models  # noqa: F401


def test_every_application_table_has_exactly_one_rls_classification() -> None:
    assert classified_application_tables() == frozenset(Base.metadata.tables)
    assert not (frozenset(RLS_TABLES) & PUBLIC_REFERENCE_TABLES)
    assert len(RLS_TABLES) == 25


def test_public_reference_tables_carry_no_tenant_ownership_column() -> None:
    for table_name in PUBLIC_REFERENCE_TABLES:
        columns = set(Base.metadata.tables[table_name].c.keys())
        assert not columns & {"organization_id", "plant_id", "device_id"}


def test_rls_ownership_columns_exist_and_platform_tables_are_explicit() -> None:
    for table_name, policy in RLS_TABLES.items():
        table = Base.metadata.tables[table_name]
        if policy.scope is RlsScope.PLATFORM:
            assert policy.ownership_column is None
        else:
            assert policy.ownership_column in table.c

    assert {
        table_name
        for table_name, policy in RLS_TABLES.items()
        if policy.scope is RlsScope.PLATFORM
    } == {
        "job_runs",
        "login_rate_limits",
    }


def test_every_application_session_sets_context_before_other_work() -> None:
    source_root = Path(__file__).parents[1] / "src" / "mplacas"
    session_factory_module = source_root / "db" / "session.py"
    violations: list[str] = []

    for source_file in source_root.rglob("*.py"):
        if source_file == session_factory_module:
            continue
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncWith) or not node.items:
                continue
            context_expr = node.items[0].context_expr
            if not (
                isinstance(context_expr, ast.Call)
                and isinstance(context_expr.func, ast.Name)
                and context_expr.func.id == "SessionFactory"
            ):
                continue
            first_statement = node.body[0] if node.body else None
            if not (
                isinstance(first_statement, ast.Expr)
                and isinstance(first_statement.value, ast.Await)
                and isinstance(first_statement.value.value, ast.Call)
                and isinstance(first_statement.value.value.func, ast.Name)
                and first_statement.value.value.func.id
                in {
                    "set_platform_context",
                    "set_principal_context",
                    "set_organization_context",
                    "set_tenant_context",
                }
            ):
                relative_path = source_file.relative_to(source_root.parent.parent)
                violations.append(f"{relative_path}:{node.lineno}")

    assert violations == []
