from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GCP_DIR = ROOT / "infra" / "gcp"
SCRIPT_NAMES = {
    "audit-costs.sh",
    "bootstrap.sh",
    "deploy-service.sh",
    "destroy-resources.sh",
    "lib.sh",
    "run-migrations.sh",
    "set-secrets.sh",
    "verify-deployment.sh",
}


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_expected_gcp_scripts_exist_and_use_strict_bash() -> None:
    scripts = {path.name for path in GCP_DIR.glob("*.sh")}
    assert scripts == SCRIPT_NAMES

    for script_name in sorted(SCRIPT_NAMES):
        content = read(f"infra/gcp/{script_name}")
        assert content.startswith("#!/usr/bin/env bash\nset -Eeuo pipefail\n")


def test_config_locks_initial_cost_guardrails() -> None:
    config = read("infra/gcp/config.example.env")
    required = {
        "GCP_REGION=us-central1",
        "GCP_MIN_INSTANCES=0",
        "GCP_MAX_INSTANCES=1",
        "GCP_CPU=1",
        "GCP_MEMORY=512Mi",
        "MPLACAS_TIMEZONE=America/Sao_Paulo",
    }
    assert required.issubset(set(config.splitlines()))


def test_gcloudignore_excludes_local_and_sensitive_artifacts() -> None:
    patterns = set(read(".gcloudignore").splitlines())
    required = {
        ".git/",
        ".github/",
        ".venv/",
        ".env",
        ".env.*",
        "infra/gcp/config.env",
        "tests/",
        "docs/",
        "storage/",
        "reports/",
        "*.db",
        "*.sqlite3",
        "*.dump",
        "*.pdf",
    }
    assert required.issubset(patterns)


def test_library_uses_stable_billing_command_and_revision_annotations() -> None:
    library = read("infra/gcp/lib.sh")

    assert "gcloud billing projects describe" in library
    assert "gcloud beta billing" not in library
    assert "--format=json" in library
    assert 'template["metadata"]["annotations"]' in library
    assert 'annotations["autoscaling.knative.dev/minScale"]' in library
    assert 'annotations["autoscaling.knative.dev/maxScale"]' in library
    assert 'template["spec"]["serviceAccountName"]' in library


def test_secret_rotation_captures_created_version_without_racy_sort() -> None:
    script = read("infra/gcp/set-secrets.sh")

    assert 'local secret_name="$1"' in script
    assert 'local keep_version="$2"' in script
    assert "gcloud secrets versions add" in script
    assert "--format='value(name.basename())'" in script
    assert "--sort-by='~createTime'" not in script
    assert "versions destroy" not in script
    assert '[[ "$new_version" =~ ^[0-9]+$ ]]' in script


def test_secret_access_is_scoped_to_each_secret() -> None:
    script = read("infra/gcp/set-secrets.sh")

    assert "gcloud secrets add-iam-policy-binding" in script
    assert "roles/secretmanager.secretAccessor" in script
    assert "roles/owner" not in script.lower()
    assert "roles/editor" not in script.lower()


def test_deploy_uses_cloud_build_source_and_revision_limits() -> None:
    script = read("infra/gcp/deploy-service.sh")

    assert "gcloud run deploy" in script
    assert '--source "$(repo_root)"' in script
    assert '--min-instances "$GCP_MIN_INSTANCES"' in script
    assert '--max-instances "$GCP_MAX_INSTANCES"' in script
    assert '--min "$GCP_MIN_INSTANCES"' not in script
    assert '--max "$GCP_MAX_INSTANCES"' not in script
    assert '--cpu "$GCP_CPU"' in script
    assert '--memory "$GCP_MEMORY"' in script
    assert "validate_cloud_run_limits" in script


def test_cost_audit_is_read_only() -> None:
    script = read("infra/gcp/audit-costs.sh")
    prohibited_mutations = (
        " services enable ",
        " services disable ",
        " run deploy ",
        " run services delete ",
        " run jobs delete ",
        " secrets delete ",
        " secrets create ",
        " instances create ",
        " scheduler jobs create ",
    )

    normalized = f" {script.replace(chr(10), ' ')} "
    for command in prohibited_mutations:
        assert command not in normalized
    assert "cost audit completed in read-only mode" in script


def test_destroy_preserves_high_scope_resources() -> None:
    script = read("infra/gcp/destroy-resources.sh")

    assert "--delete-secrets" in script
    assert "Artifact Registry is never deleted automatically" in script
    assert "projects delete" not in script
    assert "billing projects unlink" not in script
    assert "artifacts repositories delete" not in script


def test_no_prohibited_privilege_or_failure_masking_patterns() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(GCP_DIR.glob("*.sh"))
    ).lower()
    prohibited = (
        "roles/owner",
        "roles/editor",
        "gcloud beta",
        "continue-on-error",
        "--exit-zero",
        "set +e",
        "compute instances create",
        "sql instances create",
        "scheduler jobs create",
        "versions destroy",
    )

    for pattern in prohibited:
        assert pattern not in combined


def test_ci_validates_bash_contract() -> None:
    workflow = read(".github/workflows/ci.yml")

    assert "Bash syntax" in workflow
    assert "bash -n" in workflow
    assert "ShellCheck" in workflow
    assert "shellcheck infra/gcp/*.sh" in workflow
