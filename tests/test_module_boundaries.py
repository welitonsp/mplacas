from pathlib import Path


def test_intelligence_does_not_import_billing_persistence_models() -> None:
    intelligence = Path("src/mplacas/intelligence")

    violations = [
        str(path)
        for path in intelligence.glob("*.py")
        if "mplacas.billing.db_models" in path.read_text(encoding="utf-8")
    ]

    assert violations == []


def test_report_runtime_modules_do_not_depend_on_compatibility_facade() -> None:
    reports = Path("src/mplacas/reports")

    violations = [
        str(path)
        for path in reports.glob("*.py")
        if path.name != "service.py"
        and "mplacas.reports.service" in path.read_text(encoding="utf-8")
    ]

    assert violations == []


def test_report_core_modules_remain_focused() -> None:
    reports = Path("src/mplacas/reports")
    focused_modules = (
        "contract.py",
        "projection.py",
        "report_projection.py",
        "serialization.py",
        "service.py",
        "snapshot.py",
    )

    oversized = {
        name: len((reports / name).read_text(encoding="utf-8").splitlines())
        for name in focused_modules
        if len((reports / name).read_text(encoding="utf-8").splitlines()) > 300
    }

    assert oversized == {}
