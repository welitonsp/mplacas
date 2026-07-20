"""Set or reset the password for an active operational user.

Usage
-----
    python scripts/set-admin-password.py --username <name>

The password is never accepted on the command line.  It is read from:
  1. Google Cloud Secret Manager when MPLACAS_ADMIN_PASSWORD_SECRET is set.
  2. An interactive prompt (getpass, no echo) otherwise.

Environment variables required
-------------------------------
    MPLACAS_DATABASE_URL          Synchronous DSN (postgresql+psycopg2://...).

Optional environment variables
-------------------------------
    MPLACAS_ADMIN_PASSWORD_SECRET  Name of a Secret Manager secret whose latest
                                   enabled version contains the plain-text password.
                                   When set, interactive input is skipped.
    GOOGLE_CLOUD_PROJECT           GCP project for Secret Manager lookups.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys


def _read_from_secret_manager(secret_name: str) -> str:
    """Fetch the latest enabled version of *secret_name* from Secret Manager."""
    try:
        from google.cloud import secretmanager  # type: ignore[import-untyped]
    except ImportError:
        print(
            "google-cloud-secret-manager is not installed. "
            "Install it or unset MPLACAS_ADMIN_PASSWORD_SECRET to use interactive input.",
            file=sys.stderr,
        )
        sys.exit(1)

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
    if not project:
        print(
            "GOOGLE_CLOUD_PROJECT must be set when MPLACAS_ADMIN_PASSWORD_SECRET is used.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = secretmanager.SecretManagerServiceClient()
    resource = f"projects/{project}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": resource})
    value = response.payload.data.decode("utf-8").strip()
    if not value:
        print("Secret Manager returned an empty password — aborting.", file=sys.stderr)
        sys.exit(1)
    return value


def _read_password_interactively() -> str:
    password = getpass.getpass("New password (no echo): ")
    if not password:
        print("Empty password rejected.", file=sys.stderr)
        sys.exit(1)
    confirm = getpass.getpass("Confirm password (no echo): ")
    if password != confirm:
        print("Passwords do not match — aborting.", file=sys.stderr)
        sys.exit(1)
    return password


def _read_password() -> str:
    secret_name = os.environ.get("MPLACAS_ADMIN_PASSWORD_SECRET", "").strip()
    if secret_name:
        print(f"Reading password from Secret Manager secret: {secret_name}", file=sys.stderr)
        return _read_from_secret_manager(secret_name)
    return _read_password_interactively()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set the password for an active Mplacas operational user.",
    )
    parser.add_argument(
        "--username",
        required=True,
        help="Name of the operational user to update.",
    )
    args = parser.parse_args()
    username: str = args.username.strip()
    if not username:
        print("--username must not be blank.", file=sys.stderr)
        sys.exit(1)

    database_url = os.environ.get("MPLACAS_DATABASE_URL", "").strip()
    if not database_url:
        print(
            "MPLACAS_DATABASE_URL is not set. "
            "Export a synchronous DSN (postgresql+psycopg2://...) before running this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    password = _read_password()

    # Import here so import errors surface after argument parsing.
    from mplacas.auth.password import hash_password

    import sqlalchemy as sa
    from sqlalchemy import create_engine, text

    # Normalise asyncpg DSN to psycopg2 for synchronous use.
    sync_url = database_url.replace("+asyncpg", "+psycopg2").replace(
        "postgresql+psycopg2://", "postgresql+psycopg2://"
    )
    # Fallback: plain postgres:// → psycopg2
    if sync_url.startswith("postgres://"):
        sync_url = "postgresql+psycopg2://" + sync_url[len("postgres://"):]

    engine = create_engine(sync_url, pool_pre_ping=True)

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT id, active FROM operational_users WHERE name = :name LIMIT 1"
            ),
            {"name": username},
        ).fetchone()

        if row is None:
            print(f"User '{username}' not found.", file=sys.stderr)
            sys.exit(1)

        # row is a Row; access positionally (id=0, active=1).
        if not row[1]:
            print(f"User '{username}' is inactive — refusing to set password.", file=sys.stderr)
            sys.exit(1)

        user_id = row[0]
        password_hash = hash_password(password)

        conn.execute(
            text(
                "UPDATE operational_users SET password_hash = :hash WHERE id = :id"
            ),
            {"hash": password_hash, "id": user_id},
        )

    # Confirm success — never log the password or the hash.
    print(f"Password updated for user '{username}'.")


if __name__ == "__main__":
    main()
