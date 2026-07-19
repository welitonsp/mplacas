from pathlib import Path


def test_intelligence_does_not_import_billing_persistence_models() -> None:
    intelligence = Path("src/mplacas/intelligence")

    violations = [
        str(path)
        for path in intelligence.glob("*.py")
        if "mplacas.billing.db_models" in path.read_text(encoding="utf-8")
    ]

    assert violations == []
