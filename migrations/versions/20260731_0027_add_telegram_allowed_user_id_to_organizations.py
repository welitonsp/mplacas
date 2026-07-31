"""Add telegram_allowed_user_id to organizations.

Revision ID: 20260731_0027
Revises: 20260731_0026
Create Date: 2026-07-31

Adds a per-organization Telegram authorized-user column, closing the gap
left after PR-6 (``telegram_chat_id`` routing): a single, process-wide
``MPLACAS_TELEGRAM_ALLOWED_USER_ID`` env var authorized *any* chat linked to
*any* organization, so an organization's Telegram user could interact with
another organization's bot chat as long as both used the same bot process.

One-time backfill: for organizations that already had a ``telegram_chat_id``
configured *before* this migration (i.e. their Telegram integration was
already in production use), copy the current process-wide
``MPLACAS_TELEGRAM_ALLOWED_USER_ID`` value into their new
``telegram_allowed_user_id`` column, so the upgrade does not immediately
break existing integrations. This is a one-time, deploy-time backfill only —
it does not become a runtime fallback (see ``telegram/router.py``, which
fails closed for any organization without its own configured value once this
migration has run). Organizations created after this migration must have
``telegram_allowed_user_id`` set explicitly (directly in the database until
an admin endpoint exists for it).
"""

import os

from alembic import op
import sqlalchemy as sa

revision = "20260731_0027"
down_revision = "20260731_0026"
branch_labels = None
depends_on = None

# Lightweight table reference — never import ORM models in migrations.
_orgs = sa.table(
    "organizations",
    sa.column("id", sa.Uuid()),
    sa.column("telegram_chat_id", sa.BigInteger()),
    sa.column("telegram_allowed_user_id", sa.BigInteger()),
)


def upgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(
            sa.Column("telegram_allowed_user_id", sa.BigInteger(), nullable=True)
        )

    bootstrap_value = os.environ.get("MPLACAS_TELEGRAM_ALLOWED_USER_ID")
    if bootstrap_value:
        try:
            bootstrap_user_id = int(bootstrap_value)
        except ValueError:
            bootstrap_user_id = None
        if bootstrap_user_id is not None:
            bind = op.get_bind()
            bind.execute(
                _orgs.update()
                .where(_orgs.c.telegram_chat_id.is_not(None))
                .where(_orgs.c.telegram_allowed_user_id.is_(None))
                .values(telegram_allowed_user_id=bootstrap_user_id)
            )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("telegram_allowed_user_id")
