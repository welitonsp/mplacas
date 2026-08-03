"""Allow canonical legacy UUIDs in the PostgreSQL tenant context.

Revision ID: 20260803_0041
Revises: 20260802_0040
"""

from alembic import op


revision = "20260803_0041"
down_revision = "20260802_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.mplacas_current_organization_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        AS $$
            SELECT CASE
                WHEN current_setting('mplacas.organization_id', true) ~*
                     '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                THEN current_setting('mplacas.organization_id', true)::uuid
                ELSE NULL
            END
        $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.mplacas_current_organization_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        AS $$
            SELECT CASE
                WHEN current_setting('mplacas.organization_id', true) ~*
                     '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
                THEN current_setting('mplacas.organization_id', true)::uuid
                ELSE NULL
            END
        $$
        """
    )
