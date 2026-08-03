#!/usr/bin/env python3
"""Fail a PR when dependency ranges in pyproject.toml change without a
corresponding lockfile update.

Context (see docs/SUPPLY_CHAIN_POLICY.md and the PR #76 incident): Dependabot
only widens the *upper bound* of a range (e.g. ``argon2-cffi>=23.1,<24`` ->
``>=23.1,<26``). The existing pin (``23.1.0``) still satisfies the new range,
so a plain ``pip-compile pyproject.toml`` run produces zero diff — the lock
silently drifts out of date relative to what PyPI now allows. Comparing the
lockfiles textually against a "did pip-compile change anything" check would
never catch this class of bug.

This script instead enforces a structural invariant: if the dependency
sections of ``pyproject.toml`` changed between a base ref and the current
working tree, the corresponding lockfile(s) MUST also have changed in the
same diff. It does not care whether pip-compile's output actually changed —
only whether the human remembered to regenerate and commit the lock.

Usage:
    python scripts/check_lock_drift.py --base-ref <sha-or-branch>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

RUNTIME_LOCK = "requirements.lock"
DEV_LOCK = "requirements-dev.lock"


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _load_pyproject_at_ref(base_ref: str) -> dict[str, Any]:
    text = _run_git(["show", f"{base_ref}:pyproject.toml"])
    return tomllib.loads(text)


def _load_pyproject_worktree() -> dict[str, Any]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _normalize_dependencies(data: dict[str, Any]) -> tuple[str, ...]:
    project = data.get("project", {})
    return tuple(sorted(project.get("dependencies", [])))


def _normalize_optional_dependencies(data: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    project = data.get("project", {})
    optional = project.get("optional-dependencies", {})
    return {extra: tuple(sorted(reqs)) for extra, reqs in sorted(optional.items())}


def _normalize_requires_python(data: dict[str, Any]) -> str:
    project = data.get("project", {})
    return str(project.get("requires-python", ""))


def _normalize_build_requires(data: dict[str, Any]) -> tuple[str, ...]:
    build_system = data.get("build-system", {})
    return tuple(sorted(build_system.get("requires", [])))


def _changed_files_since(base_ref: str) -> set[str]:
    output = _run_git(["diff", "--name-only", base_ref])
    return {line.strip() for line in output.splitlines() if line.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-ref",
        required=True,
        help="Git ref (SHA or branch) to diff pyproject.toml against.",
    )
    args = parser.parse_args()

    base_data = _load_pyproject_at_ref(args.base_ref)
    head_data = _load_pyproject_worktree()

    dependencies_changed = _normalize_dependencies(base_data) != _normalize_dependencies(
        head_data
    )
    optional_changed = _normalize_optional_dependencies(
        base_data
    ) != _normalize_optional_dependencies(head_data)
    requires_python_changed = _normalize_requires_python(
        base_data
    ) != _normalize_requires_python(head_data)
    build_requires_changed = _normalize_build_requires(base_data) != _normalize_build_requires(
        head_data
    )

    if not (
        dependencies_changed
        or optional_changed
        or requires_python_changed
        or build_requires_changed
    ):
        return 0

    # Any change to requires-python or the build backend affects both locks
    # (they are compiled for the same interpreter and toolchain). A change to
    # project.dependencies affects both locks too, since requirements.lock is
    # a subset of requirements-dev.lock. Only optional-dependencies (dev
    # extras) changing on its own requires just the dev lock.
    if dependencies_changed or requires_python_changed or build_requires_changed:
        required_locks = {RUNTIME_LOCK, DEV_LOCK}
    else:
        required_locks = {DEV_LOCK}

    changed_files = _changed_files_since(args.base_ref)
    missing_locks = sorted(lock for lock in required_locks if lock not in changed_files)

    if not missing_locks:
        return 0

    changed_sections = []
    if dependencies_changed:
        changed_sections.append("project.dependencies")
    if optional_changed:
        changed_sections.append("project.optional-dependencies")
    if requires_python_changed:
        changed_sections.append("project.requires-python")
    if build_requires_changed:
        changed_sections.append("build-system.requires")

    print(
        "Dependency ranges changed in pyproject.toml "
        f"({', '.join(changed_sections)}) but the following lockfile(s) were "
        f"not updated in this diff: {', '.join(missing_locks)}.\n"
        "\n"
        "Regenerate the locks with scripts/compile-locks.sh and commit the "
        "result.\n"
        "\n"
        "Note: widening the upper bound of an existing range (the PR #76 "
        "incident — e.g. 'argon2-cffi>=23.1,<24' becoming '>=23.1,<26') does "
        "NOT change pip-compile's output by default, because the existing "
        "pin still satisfies the new range. Running "
        "'scripts/compile-locks.sh' without flags will silently produce no "
        "diff in that case. To actually pick up the newer release allowed by "
        "the widened range, pass the package explicitly:\n"
        "    scripts/compile-locks.sh --upgrade-package <name>\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
