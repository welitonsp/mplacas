#!/usr/bin/env bash
set -Eeuo pipefail

require_value() {
  local name="$1"
  local value="$2"
  [[ -n "$value" ]] || { printf 'error: %s is required\n' "$name" >&2; exit 1; }
}

for command_name in pg_dump pg_restore psql python gpg curl; do
  command -v "$command_name" >/dev/null 2>&1 || {
    printf 'error: %s is required\n' "$command_name" >&2
    exit 1
  }
done

require_value "MPLACAS_BACKUP_SOURCE_URL" "${MPLACAS_BACKUP_SOURCE_URL:-}"
require_value "MPLACAS_RESTORE_DATABASE_URL" "${MPLACAS_RESTORE_DATABASE_URL:-}"
require_value "MPLACAS_RESTORE_CONFIRM_HOST" "${MPLACAS_RESTORE_CONFIRM_HOST:-}"
require_value \
  "MPLACAS_BACKUP_ENCRYPTION_PASSPHRASE" \
  "${MPLACAS_BACKUP_ENCRYPTION_PASSPHRASE:-}"
require_value "MPLACAS_RESTORE_DRILL_OWNER" "${MPLACAS_RESTORE_DRILL_OWNER:-}"

ARTIFACT_DIR="${MPLACAS_RESTORE_ARTIFACT_DIR:-artifacts/restore-drill}"
mkdir -p "$ARTIFACT_DIR"
chmod 700 "$ARTIFACT_DIR"

mapfile -d '' -t VALIDATED_CONNECTIONS < <(python - \
  "$MPLACAS_BACKUP_SOURCE_URL" \
  "$MPLACAS_RESTORE_DATABASE_URL" \
  "$MPLACAS_RESTORE_CONFIRM_HOST" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit

source, target, confirmation = sys.argv[1:]
source_url = urlsplit(source)
target_url = urlsplit(target)
if source_url.scheme not in {"postgres", "postgresql", "postgresql+asyncpg"}:
    raise SystemExit("source must be a PostgreSQL URL")
if not source_url.hostname:
    raise SystemExit("source must be a PostgreSQL URL")
if target_url.scheme not in {"postgres", "postgresql"} or not target_url.hostname:
    raise SystemExit("target must be a PostgreSQL URL")
if source_url.hostname == target_url.hostname:
    raise SystemExit("restore target must use a different host/branch than production")
if target_url.hostname != confirmation:
    raise SystemExit("MPLACAS_RESTORE_CONFIRM_HOST does not match the discardable target")
source_url = source_url._replace(scheme="postgresql")
values = (urlunsplit(source_url), target_url.hostname)
sys.stdout.buffer.write(b"\0".join(value.encode() for value in values) + b"\0")
PY
)
[[ "${#VALIDATED_CONNECTIONS[@]}" -eq 2 ]] || {
  printf 'error: source/target URL validation did not return a connection\n' >&2
  exit 1
}
SOURCE_DSN="${VALIDATED_CONNECTIONS[0]}"
TARGET_HOST="${VALIDATED_CONNECTIONS[1]}"

mapfile -d '' -t RESTORE_CONNECTION < <(python - "$MPLACAS_RESTORE_DATABASE_URL" <<'PY'
import sys
from urllib.parse import parse_qs, unquote, urlsplit

parsed = urlsplit(sys.argv[1])
host = parsed.hostname or ""
password = unquote(parsed.password or "")
loopback_hosts = {"localhost", "127.0.0.1", "::1"}
default_sslmode = "disable" if host in loopback_hosts else "require"
sslmode = parse_qs(parsed.query).get("sslmode", [default_sslmode])[0]
values = (
    host,
    str(parsed.port or 5432),
    unquote(parsed.username or ""),
    password,
    unquote(parsed.path.lstrip("/")),
    sslmode,
)
if not all((values[0], values[1], values[2], values[4])):
    raise SystemExit("restore URL must contain host, port/default, user and database")
if not password and host not in loopback_hosts:
    raise SystemExit("remote restore URL must contain a password")
if host not in loopback_hosts and sslmode not in {"require", "verify-ca", "verify-full"}:
    raise SystemExit("remote restore URL must require TLS")
sys.stdout.buffer.write(b"\0".join(value.encode() for value in values) + b"\0")
PY
)

WORK_DIR="$(mktemp -d)"
API_PID=""
cleanup() {
  if [[ -n "$API_PID" ]]; then
    kill "$API_PID" >/dev/null 2>&1 || true
    wait "$API_PID" >/dev/null 2>&1 || true
  fi
  find "$WORK_DIR" -type f -delete
  rmdir "$WORK_DIR"
}
trap cleanup EXIT

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP_FILE="${WORK_DIR}/mplacas-${TIMESTAMP}.dump"
ENCRYPTED_FILE="${ARTIFACT_DIR}/mplacas-${TIMESTAMP}.dump.gpg"
MANIFEST_FILE="${ARTIFACT_DIR}/restore-drill-${TIMESTAMP}.json"

pg_dump \
  --dbname "$SOURCE_DSN" \
  --format=custom \
  --no-owner \
  --no-acl \
  --file "$DUMP_FILE"
[[ -s "$DUMP_FILE" ]] || { printf 'error: pg_dump produced an empty file\n' >&2; exit 1; }
pg_restore --list "$DUMP_FILE" >/dev/null

DUMP_SHA256="$(python - "$DUMP_FILE" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
digest = hashlib.sha256()
with path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
)"
DUMP_BYTES="$(wc -c < "$DUMP_FILE" | tr -d ' ')"

printf '%s' "$MPLACAS_BACKUP_ENCRYPTION_PASSPHRASE" | gpg \
  --batch \
  --yes \
  --pinentry-mode loopback \
  --passphrase-fd 0 \
  --symmetric \
  --cipher-algo AES256 \
  --output "$ENCRYPTED_FILE" \
  "$DUMP_FILE"
[[ -s "$ENCRYPTED_FILE" ]] || { printf 'error: encrypted backup is empty\n' >&2; exit 1; }

PGHOST="${RESTORE_CONNECTION[0]}" \
PGPORT="${RESTORE_CONNECTION[1]}" \
PGUSER="${RESTORE_CONNECTION[2]}" \
PGPASSWORD="${RESTORE_CONNECTION[3]}" \
PGDATABASE="${RESTORE_CONNECTION[4]}" \
PGSSLMODE="${RESTORE_CONNECTION[5]}" \
pg_restore \
  --dbname "${RESTORE_CONNECTION[4]}" \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  --exit-on-error \
  "$DUMP_FILE"

MPLACAS_DATABASE_URL="$MPLACAS_RESTORE_DATABASE_URL" \
  python -m alembic -c alembic.ini upgrade head

INVARIANTS="$({ PGHOST="${RESTORE_CONNECTION[0]}" \
  PGPORT="${RESTORE_CONNECTION[1]}" \
  PGUSER="${RESTORE_CONNECTION[2]}" \
  PGPASSWORD="${RESTORE_CONNECTION[3]}" \
  PGDATABASE="${RESTORE_CONNECTION[4]}" \
  PGSSLMODE="${RESTORE_CONNECTION[5]}" \
  psql \
  --tuples-only \
  --no-align \
  --set ON_ERROR_STOP=1 <<'SQL'
SELECT CASE WHEN to_regclass('public.plants') IS NOT NULL THEN 'plants:ok' ELSE 'plants:missing' END;
SELECT CASE WHEN to_regclass('public.operational_users') IS NOT NULL THEN 'users:ok' ELSE 'users:missing' END;
SELECT CASE WHEN to_regclass('public.api_credentials') IS NOT NULL THEN 'credentials:ok' ELSE 'credentials:missing' END;
SELECT CASE WHEN to_regclass('public.alembic_version') IS NOT NULL THEN 'migrations:ok' ELSE 'migrations:missing' END;
SQL
} )"
if grep -q ':missing' <<<"$INVARIANTS"; then
  printf 'error: restored database invariant failed\n' >&2
  exit 1
fi

PORT=18080 \
MPLACAS_ENVIRONMENT=production \
MPLACAS_DATABASE_URL="$MPLACAS_RESTORE_DATABASE_URL" \
MPLACAS_JWT_SECRET="restore-drill-jwt-secret-at-least-32-bytes" \
MPLACAS_OPERATIONS_API_KEY="restore-drill-operations-key" \
MPLACAS_CLOUD_TRACE_ENABLED=false \
MPLACAS_CLOUD_METRICS_ENABLED=false \
python -m mplacas.server >"${WORK_DIR}/api.log" 2>&1 &
API_PID="$!"

READY=false
for _attempt in $(seq 1 30); do
  if curl --fail --silent --show-error \
    --connect-timeout 1 \
    --max-time 3 \
    http://127.0.0.1:18080/ready >"${WORK_DIR}/ready.json"; then
    READY=true
    break
  fi
  sleep 1
done
[[ "$READY" == "true" ]] || {
  printf 'error: restored database did not pass /ready\n' >&2
  exit 1
}

python - \
  "$MANIFEST_FILE" \
  "$TIMESTAMP" \
  "$MPLACAS_RESTORE_DRILL_OWNER" \
  "$TARGET_HOST" \
  "$DUMP_SHA256" \
  "$DUMP_BYTES" <<'PY'
import hashlib
import json
import pathlib
import sys

path, timestamp, owner, target_host, checksum, size = sys.argv[1:]
payload = {
    "schema_version": 1,
    "executed_at_utc": timestamp,
    "owner": owner,
    "target_host_sha256": hashlib.sha256(target_host.encode()).hexdigest(),
    "backup_sha256": checksum,
    "backup_bytes": int(size),
    "pg_restore": "passed",
    "migrations": "passed",
    "critical_invariants": "passed",
    "ready_endpoint": "passed",
    "decision": "approved",
}
pathlib.Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

printf 'restore drill approved; manifest=%s\n' "$MANIFEST_FILE"
