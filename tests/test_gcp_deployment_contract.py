from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GCP_DIR = ROOT / "infra" / "gcp"
SCRIPT_NAMES = {
    "audit-costs.sh",
    "bootstrap.sh",
    "deploy-service.sh",
    "destroy-resources.sh",
    "lib.sh",
    "provision-operations.sh",
    "rotate-operations-key.sh",
    "run-migrations.sh",
    "set-secrets.sh",
    "verify-operations.sh",
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
        "/reports/",
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
    # Cloud Run omite minScale quando o valor efetivo é zero. O validador deve
    # tratar a ausência como default, sem enfraquecer maxScale.
    assert 'annotations.get("autoscaling.knative.dev/minScale", "0")' in library
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


def test_database_secret_setup_uses_canonical_url_validator() -> None:
    library = read("infra/gcp/lib.sh")
    validator = read("infra/gcp/validate_database_url.py")

    assert 'validate_database_url.py" "$file" "$expected"' in library
    assert 'ALLOWED_QUERY_KEYS = frozenset({' in validator
    assert 'params.get("sslmode") != "require"' in validator
    assert 'params.get("channel_binding") != "require"' in validator
    assert 'len(keys) != len(set(keys))' in validator
    assert '"://" in item' in validator


def test_operations_key_rotation_is_fail_closed_and_auditable() -> None:
    script = read("infra/gcp/rotate-operations-key.sh")

    required = {
        "confirm_exact",
        "secrets.token_urlsafe(48)",
        "gcloud secrets versions add",
        "--data-file=-",
        "MPLACAS_OPERATIONS_API_KEY=${SECRET_OPERATIONS_KEY}:latest",
        '[[ "$new_key_status" == "200" ]]',
        '[[ "$previous_key_status" == "401" ]]',
        "-smoke",
        "-operational-watchdog",
        "--wait",
    }
    assert all(term in script for term in required)
    assert "gcloud secrets versions disable" in script
    assert "gcloud secrets versions destroy" not in script
    logged_lines = "\n".join(
        line for line in script.splitlines() if line.startswith("log ")
    )
    assert "${previous_key}" not in logged_lines
    assert "${new_key}" not in logged_lines


def test_secret_access_is_scoped_to_each_secret() -> None:
    script = read("infra/gcp/set-secrets.sh")

    assert "gcloud secrets add-iam-policy-binding" in script
    assert "roles/secretmanager.secretAccessor" in script
    assert "roles/owner" not in script.lower()
    assert "roles/editor" not in script.lower()


def test_runtime_trace_access_is_least_privilege_and_trace_api_is_enabled() -> None:
    library = read("infra/gcp/lib.sh")
    bootstrap = read("infra/gcp/bootstrap.sh")
    deploy = read("infra/gcp/deploy-service.sh")

    assert '"cloudtrace.googleapis.com"' in library
    assert 'roles/cloudtrace.agent' in library
    assert "ensure_runtime_trace_access" in bootstrap
    assert "MPLACAS_GCP_PROJECT_ID=${GCP_PROJECT_ID}" in deploy
    assert "MPLACAS_CLOUD_TRACE_ENABLED=true" in deploy


def test_runtime_metrics_access_is_least_privilege_and_monitoring_api_is_enabled() -> None:
    library = read("infra/gcp/lib.sh")
    bootstrap = read("infra/gcp/bootstrap.sh")
    deploy = read("infra/gcp/deploy-service.sh")

    assert '"monitoring.googleapis.com"' in library
    assert "roles/monitoring.metricWriter" in library
    assert "ensure_runtime_metrics_access" in bootstrap
    assert "MPLACAS_CLOUD_METRICS_ENABLED=true" in deploy


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


def test_dashboard_is_configured_and_verified_as_exact_redirect() -> None:
    config = read("infra/gcp/config.example.env")
    deploy = read("infra/gcp/deploy-service.sh")
    verify = read("infra/gcp/verify-deployment.sh")

    assert "MPLACAS_DASHBOARD_URL=https://" in config
    assert "MPLACAS_DASHBOARD_URL=${MPLACAS_DASHBOARD_URL}" in deploy
    assert '[[ "$http_status" == "308" ]]' in verify
    assert "dashboard redirect location does not match MPLACAS_DASHBOARD_URL" in verify
    assert 'fetch_and_validate "${SERVICE_URL}/dashboard" "200"' not in verify


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
        "versions destroy",
    )

    for pattern in prohibited:
        assert pattern not in combined

    scheduler_mutators = [
        path.name
        for path in sorted(GCP_DIR.glob("*.sh"))
        if "scheduler jobs create" in path.read_text(encoding="utf-8").lower()
    ]
    assert scheduler_mutators == ["provision-operations.sh"]


def test_ci_validates_bash_contract() -> None:
    workflow = read(".github/workflows/ci.yml")

    assert "Bash syntax" in workflow
    assert "bash -n" in workflow
    assert "ShellCheck" in workflow
    assert "shellcheck infra/gcp/*.sh" in workflow


def test_operational_jobs_and_schedulers_are_provisioned_idempotently() -> None:
    provision = read("infra/gcp/provision-operations.sh")
    verify = read("infra/gcp/verify-operations.sh")
    required_commands = {
        "collect",
        "daily-pipeline",
        "dispatch-outbox",
        "drain-collection",
        "drain-report-exports",
        "daily-digest",
        "operational-watchdog",
        "retention",
    }

    assert required_commands.issubset(set(_quoted_array(provision, "OPERATIONAL_COMMANDS")))
    assert "gcloud run jobs deploy" in provision
    assert "gcloud scheduler jobs update http" in provision
    assert "gcloud scheduler jobs create http" in provision
    assert "roles/run.invoker" in provision
    assert "scheduler_service_account_email" in provision
    assert "gcloud run jobs execute" in verify
    assert "SMOKE_JOB_NAME" in verify
    assert "WATCHDOG_JOB_NAME" in verify
    assert '[[ "$scheduler_state" == "ENABLED" ]]' in verify
    assert "operational job must have exactly one canonical enabled Scheduler trigger" in verify
    assert 'schedule.get("state") == "ENABLED"' in verify
    assert "enabled_triggers != [expected_name]" in verify
    assert "--wait" in verify


def test_monitoring_policies_are_versioned_and_upserted_with_stable_cli() -> None:
    library = read("infra/gcp/lib.sh")
    provision = read("infra/gcp/provision-operations.sh")
    policy_dir = GCP_DIR / "monitoring"
    policies = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in policy_dir.glob("*.json")
    }

    assert set(policies) == {
        "operational-job-failure.json",
        "operational-watchdog-absence.json",
    }
    policy_ids = {
        policy["userLabels"]["mplacas_policy_id"] for policy in policies.values()
    }
    assert policy_ids == {
        "operational_job_failure",
        "operational_watchdog_absence",
    }
    assert all(policy["enabled"] is True for policy in policies.values())
    assert all(policy["userLabels"]["version"] == "v1" for policy in policies.values())
    assert all("name" not in policy for policy in policies.values())

    failure_filter = policies["operational-job-failure.json"]["conditions"][0][
        "conditionThreshold"
    ]["filter"]
    absence = policies["operational-watchdog-absence.json"]["conditions"][0][
        "conditionAbsent"
    ]
    assert "run.googleapis.com/job/completed_execution_count" in failure_filter
    assert 'metric.labels.result!="succeeded"' in failure_filter
    assert absence["duration"] == "7200s"
    assert 'metric.labels.result="succeeded"' in absence["filter"]

    assert "gcloud monitoring policies create" in library
    assert "gcloud monitoring policies update" in library
    assert "gcloud alpha monitoring" not in library
    assert "find_monitoring_policy" in library
    assert "duplicate managed monitoring policy" in library
    assert "validate_monitoring_notification_channels" in provision
    assert '"operational_job_failure"' in provision
    assert '"operational_watchdog_absence"' in provision


def test_monitoring_verification_requires_enabled_policy_and_configured_channel() -> None:
    config = read("infra/gcp/config.example.env")
    library = read("infra/gcp/lib.sh")
    verify = read("infra/gcp/verify-operations.sh")

    assert "GCP_MONITORING_NOTIFICATION_CHANNELS=" in config
    assert "notification channel must be a full resource name in this project" in library
    assert 'policy.get("enabled") is not True' in library
    assert "expected_channels.issubset(actual_channels)" in library
    assert 'verify_monitoring_policy "operational_job_failure"' in verify
    assert 'verify_monitoring_policy "operational_watchdog_absence"' in verify


def _quoted_array(content: str, name: str) -> list[str]:
    start = content.index(f"readonly {name}=(")
    end = content.index(")", start)
    return [line.strip().strip('"') for line in content[start:end].splitlines()[1:]]
