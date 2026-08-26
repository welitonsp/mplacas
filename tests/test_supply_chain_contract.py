from __future__ import annotations

import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]


def _load_pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _lock_pins(lock_name: str) -> dict[str, str]:
    """Return {canonical-name: pinned-version} for every pin in a lockfile."""
    content = (ROOT / lock_name).read_text(encoding="utf-8")
    pins: dict[str, str] = {}
    for line in content.splitlines():
        match = re.match(r"^([a-zA-Z0-9_.-]+)==([^\s\\]+)", line)
        if match:
            pins[canonicalize_name(match.group(1))] = match.group(2)
    return pins


def _assert_requirements_satisfied_by_lock(requirements: list[str], lock_name: str) -> None:
    pins = _lock_pins(lock_name)
    for raw in requirements:
        requirement = Requirement(raw)
        name = canonicalize_name(requirement.name)
        assert name in pins, f"{name!r} from pyproject.toml is not pinned in {lock_name}"
        pinned_version = pins[name]
        assert requirement.specifier.contains(pinned_version, prereleases=True), (
            f"{name}=={pinned_version} pinned in {lock_name} does not satisfy "
            f"{requirement.specifier!s} declared in pyproject.toml"
        )


def test_python_locks_pin_every_requirement_with_hashes() -> None:
    for name in ("requirements.lock", "requirements-dev.lock"):
        content = (ROOT / name).read_text(encoding="utf-8")
        requirements = [
            line for line in content.splitlines() if re.match(r"^[a-zA-Z0-9_.-]+==", line)
        ]
        assert requirements
        assert "--hash=sha256:" in content

    dev_lock = (ROOT / "requirements-dev.lock").read_text(encoding="utf-8")
    assert "editables==0.6" in dev_lock


def test_runtime_lock_pins_satisfy_pyproject_ranges() -> None:
    project = _load_pyproject()["project"]
    _assert_requirements_satisfied_by_lock(project["dependencies"], "requirements.lock")


def test_dev_lock_pins_satisfy_pyproject_ranges() -> None:
    project = _load_pyproject()["project"]
    dev_requirements = project["optional-dependencies"]["dev"]
    _assert_requirements_satisfied_by_lock(dev_requirements, "requirements-dev.lock")


def test_runtime_lock_excludes_dev_only_packages() -> None:
    project = _load_pyproject()["project"]
    runtime_names = {canonicalize_name(Requirement(r).name) for r in project["dependencies"]}
    dev_names = {
        canonicalize_name(Requirement(r).name)
        for r in project["optional-dependencies"]["dev"]
    }
    dev_only_names = dev_names - runtime_names
    assert dev_only_names

    runtime_pins = _lock_pins("requirements.lock")
    leaked = dev_only_names & set(runtime_pins)
    assert not leaked, f"dev-only packages leaked into requirements.lock: {leaked}"


def test_lock_headers_are_canonical_pip_compile_output() -> None:
    project = _load_pyproject()

    runtime_lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    dev_lock = (ROOT / "requirements-dev.lock").read_text(encoding="utf-8")

    for lock_text in (runtime_lock, dev_lock):
        assert "by pip-compile with Python 3.12" in lock_text
        assert "--allow-unsafe" in lock_text
        assert "--generate-hashes" in lock_text
        assert "--strip-extras" in lock_text

    assert "--extra=dev" not in runtime_lock
    assert "--extra=dev" in dev_lock

    # Guards against regressing the Python 3.14 header-mismatch bug fixed
    # alongside this contract: both locks must state the same interpreter
    # version used for the pin-compatibility markers.
    assert project["project"]["requires-python"] == ">=3.12"


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


def test_dependency_lock_drift_guard_runs_on_pull_requests() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "dependency-lock-drift:" in ci
    assert "if: github.event_name == 'pull_request'" in ci
    assert "fetch-depth: 0" in ci
    assert "scripts/check_lock_drift.py" in ci
    assert "--base-ref ${{ github.event.pull_request.base.sha }}" in ci


def test_container_smoke_uses_valid_configuration_and_preserves_failure_logs() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "MPLACAS_JWT_SECRET=ci-00000000000000000000000000000000" in ci
    assert 'docker logs "$CONTAINER_NAME"' in ci
    assert 'docker rm --force "$CONTAINER_NAME"' in ci


def test_ignore_files_do_not_exclude_python_reports_package() -> None:
    entries = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

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
