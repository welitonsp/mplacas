from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from mplacas.db.rls_inventory import RLS_TABLES


ROOT = Path(__file__).parents[1]
MIGRATION_PATH = (
    ROOT / "migrations" / "versions" / "20260802_0040_enable_postgresql_rls.py"
)
LEGACY_UUID_MIGRATION_PATH = (
    ROOT / "migrations" / "versions" / "20260803_0041_allow_legacy_tenant_uuids.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mplacas_rls_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Tabelas de inquilino criadas depois da 20260802_0040: cada migration liga o
# próprio RLS com a mesma política (ver teste abaixo).
LATER_RLS_MIGRATIONS = {
    "provider_accounts": ROOT
    / "migrations"
    / "versions"
    / "20261029_0051_add_provider_accounts.py",
}


def test_rls_migration_covers_exactly_the_application_inventory() -> None:
    migration = _load_migration()
    assert set(migration.ALL_TABLES) | set(LATER_RLS_MIGRATIONS) == set(RLS_TABLES)
    assert not set(migration.ALL_TABLES) & set(LATER_RLS_MIGRATIONS)
    assert len(migration.ALL_TABLES) == len(set(migration.ALL_TABLES)) == 24


def test_later_tenant_tables_enable_the_same_fail_closed_policy() -> None:
    migration = _load_migration()
    for table_name, path in LATER_RLS_MIGRATIONS.items():
        spec = importlib.util.spec_from_file_location(f"rls_{table_name}", path)
        assert spec is not None and spec.loader is not None
        later = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(later)

        assert later.POLICY_NAME == migration.POLICY_NAME
        expected = migration._policy_expression("devices").replace("devices.", f"{table_name}.")
        assert later.POLICY_EXPRESSION == expected
        source = path.read_text(encoding="utf-8")
        assert "ENABLE ROW LEVEL SECURITY" in source
        assert "FORCE ROW LEVEL SECURITY" in source
        assert "USING ({POLICY_EXPRESSION}) WITH CHECK ({POLICY_EXPRESSION})" in source


def test_rls_policy_expressions_are_fail_closed_and_role_gated() -> None:
    migration = _load_migration()

    for table_name in migration.ALL_TABLES:
        expression = migration._policy_expression(table_name)
        assert "mplacas_platform_bypass_allowed()" in expression
        if table_name in migration.PLATFORM_TABLES:
            assert "mplacas_current_organization_id()" not in expression
        else:
            assert "mplacas_current_organization_id()" in expression

    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "USING ({expression}) WITH CHECK ({expression})" in source
    assert "to_regrole('{PLATFORM_ROLE}')" in source
    assert "MPLACAS_RLS_ACTIVATION_APPROVED" in source
    assert "ENABLE-RLS-20260802" in source


def test_rls_migration_rejects_missing_activation_approval(monkeypatch) -> None:
    migration = _load_migration()
    monkeypatch.delenv("MPLACAS_RLS_ACTIVATION_APPROVED", raising=False)

    with pytest.raises(RuntimeError, match="RLS activation requires"):
        migration.upgrade()


def test_rls_tenant_helper_accepts_canonical_legacy_uuids() -> None:
    source = LEGACY_UUID_MIGRATION_PATH.read_text(encoding="utf-8")

    assert 'revision = "20260803_0041"' in source
    assert 'down_revision = "20260802_0040"' in source
    assert (
        "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        in source
    )
    assert "[1-5][0-9a-f]{3}" not in source.split("def downgrade", maxsplit=1)[0]
