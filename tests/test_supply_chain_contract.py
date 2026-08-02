from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_python_locks_pin_every_requirement_with_hashes() -> None:
    for name in ("requirements.lock", "requirements-dev.lock"):
        content = (ROOT / name).read_text(encoding="utf-8")
        requirements = [
            line for line in content.splitlines() if re.match(r"^[a-zA-Z0-9_.-]+==", line)
        ]
        assert requirements
        assert "--hash=sha256:" in content

    dev_lock = (ROOT / "requirements-dev.lock").read_text(encoding="utf-8")
    assert "editables==0.5" in dev_lock


def test_images_and_actions_are_immutable() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^FROM python:3\.12-slim-bookworm@sha256:[0-9a-f]{64}$", dockerfile, re.M)
    assert "--require-hashes -r requirements.lock" in dockerfile
    assert "python -m pip uninstall --yes pip setuptools" in dockerfile

    workflow_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    )
    action_refs = re.findall(r"uses:\s+[^\s@]+@([^\s#]+)", workflow_text)
    assert action_refs
    assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs)
    postgres_images = re.findall(r"image:\s+postgres:16(@sha256:[0-9a-f]{64})?", workflow_text)
    assert postgres_images and all(postgres_images)


def test_automated_updates_scans_and_provenance_are_versioned() -> None:
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    security = (ROOT / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for ecosystem in ("pip", "npm", "github-actions", "docker"):
        assert f"package-ecosystem: {ecosystem}" in dependabot
    assert "github/codeql-action/init@" in security
    assert "gitleaks/gitleaks-action@" in security
    assert "actions/attest-build-provenance@" in ci
    assert "attestations: write" in ci


def test_container_smoke_uses_valid_configuration_and_preserves_failure_logs() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "MPLACAS_JWT_SECRET=ci-00000000000000000000000000000000" in ci
    assert 'docker logs "$CONTAINER_NAME"' in ci
    assert 'docker rm --force "$CONTAINER_NAME"' in ci


def test_ignore_files_do_not_exclude_python_reports_package() -> None:
    for name in (".dockerignore", ".gcloudignore"):
        entries = (ROOT / name).read_text(encoding="utf-8").splitlines()

        assert "/reports/" in entries
        assert "reports/" not in entries


def test_gitleaks_exceptions_are_exact_fingerprints() -> None:
    entries = [
        line for line in (ROOT / ".gitleaksignore").read_text(encoding="utf-8").splitlines() if line
    ]

    assert len(entries) == 9
    assert all(
        re.fullmatch(
            r"[0-9a-f]{40}:[^:]+:generic-api-key:[0-9]+",
            entry,
        )
        for entry in entries
    )
    assert all("*" not in entry for entry in entries)
