"""Backfill organization_id: one org per operational_user, orphans to default org.

Revision ID: 20260720_0021
Revises: 20260720_0020
Create Date: 2026-07-20
"""

import re
import uuid

from alembic import op
import sqlalchemy as sa

revision = "20260720_0021"
down_revision = "20260720_0020"
branch_labels = None
depends_on = None

# Lightweight table references — never import ORM models in migrations.
_orgs = sa.table(
    "organizations",
    sa.column("id", sa.Uuid()),
    sa.column("name", sa.String()),
    sa.column("slug", sa.String()),
    sa.column("active", sa.Boolean()),
)
_users = sa.table(
    "operational_users",
    sa.column("id", sa.Uuid()),
    sa.column("name", sa.String()),
    sa.column("organization_id", sa.Uuid()),
)
_plants = sa.table(
    "plants",
    sa.column("id", sa.Uuid()),
    sa.column("organization_id", sa.Uuid()),
)
_creds = sa.table(
    "api_credentials",
    sa.column("id", sa.Uuid()),
    sa.column("user_id", sa.Uuid()),
    sa.column("organization_id", sa.Uuid()),
)


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:80] or "org"


def upgrade() -> None:
    bind = op.get_bind()

    # 1 org per user
    users = bind.execute(sa.select(_users.c.id, _users.c.name)).fetchall()
    user_org: dict[uuid.UUID, uuid.UUID] = {}
    for user_id, user_name in users:
        org_id = uuid.uuid4()
        slug = _slugify(user_name)
        # ensure slug is unique in case of collision
        existing = bind.execute(
            sa.select(_orgs.c.id).where(_orgs.c.slug == slug)
        ).fetchone()
        if existing:
            slug = f"{slug}-{org_id.hex[:6]}"
        bind.execute(
            _orgs.insert().values(id=org_id, name=user_name, slug=slug, active=True)
        )
        bind.execute(
            _users.update()
            .where(_users.c.id == user_id)
            .values(organization_id=org_id)
        )
        user_org[user_id] = org_id

    # propagate org from credential's user to the credential itself
    creds = bind.execute(sa.select(_creds.c.id, _creds.c.user_id)).fetchall()
    for cred_id, user_id in creds:
        org_id = user_org.get(user_id) if user_id else None
        if org_id:
            bind.execute(
                _creds.update()
                .where(_creds.c.id == cred_id)
                .values(organization_id=org_id)
            )

    # orphan plants/credentials → default org (created only if needed)
    orphan_plants = bind.execute(
        sa.select(_plants.c.id).where(_plants.c.organization_id.is_(None))
    ).fetchall()
    orphan_creds = bind.execute(
        sa.select(_creds.c.id).where(_creds.c.organization_id.is_(None))
    ).fetchall()

    if orphan_plants or orphan_creds:
        default_org_id = uuid.uuid4()
        bind.execute(
            _orgs.insert().values(
                id=default_org_id, name="Default", slug="default", active=True
            )
        )
        if orphan_plants:
            bind.execute(
                _plants.update()
                .where(_plants.c.organization_id.is_(None))
                .values(organization_id=default_org_id)
            )
        if orphan_creds:
            bind.execute(
                _creds.update()
                .where(_creds.c.organization_id.is_(None))
                .values(organization_id=default_org_id)
            )


def downgrade() -> None:
    # Data migrations are not reversed — backfill is idempotent on re-run.
    pass
