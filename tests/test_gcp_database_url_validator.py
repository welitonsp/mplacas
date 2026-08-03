from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "infra" / "gcp" / "validate_database_url.py"
SPEC = importlib.util.spec_from_file_location("gcp_database_url_validator", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


@pytest.mark.parametrize(
    ("hostname", "expected"),
    [
        ("ep-example-pooler.us-east-1.aws.neon.tech", "runtime"),
        ("ep-example.us-east-1.aws.neon.tech", "migration"),
    ],
)
def test_accepts_canonical_neon_urls(hostname: str, expected: str) -> None:
    VALIDATOR.validate_database_url(
        f"postgresql://role:secret@{hostname}/neondb"
        "?sslmode=require&channel_binding=require",
        expected,
    )


@pytest.mark.parametrize(
    "query",
    [
        "sslmode=require&channel_binding=require&channel_binding=require",
        "sslmode=require&channel_binding=requirepostgresql://role:secret@host/neondb",
        "sslmode=disable&channel_binding=require",
        "sslmode=require&channel_binding=disable",
        "sslmode=require&channel_binding=require&unexpected=value",
    ],
)
def test_rejects_unsafe_or_corrupted_query_strings(query: str) -> None:
    with pytest.raises(ValueError):
        VALIDATOR.validate_database_url(
            "postgresql://role:secret@ep-example-pooler.us-east-1.aws.neon.tech/neondb?"
            + query,
            "runtime",
        )


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://role@ep-example-pooler.us-east-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require",
        "postgresql://role:secret@ep-example.us-east-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require",
        "postgresql://role:secret@ep-example-pooler.us-east-1.aws.neon.tech/a/b"
        "?sslmode=require&channel_binding=require",
        "postgresql://role:secret@ep-example-pooler.us-east-1.aws.neon.tech/neondb "
        "?sslmode=require&channel_binding=require",
    ],
)
def test_rejects_missing_credentials_wrong_kind_path_or_whitespace(url: str) -> None:
    with pytest.raises(ValueError):
        VALIDATOR.validate_database_url(url, "runtime")
