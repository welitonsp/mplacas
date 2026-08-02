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


def test_images_and_actions_are_immutable() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^FROM python:3\.12-slim-bookworm@sha256:[0-9a-f]{64}$", dockerfile, re.M)
    assert "--require-hashes -r requirements.lock" in dockerfile

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
    security = (ROOT / ".github" / "workflows" / "security.yml").read_text(
        encoding="utf-8"
    )
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for ecosystem in ("pip", "npm", "github-actions", "docker"):
        assert f"package-ecosystem: {ecosystem}" in dependabot
    assert "github/codeql-action/init@" in security
    assert "gitleaks/gitleaks-action@" in security
    assert "actions/attest-build-provenance@" in ci
    assert "attestations: write" in ci
