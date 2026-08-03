"""Enable fail-closed PostgreSQL RLS for all application tables.

Revision ID: 20260802_0040
Revises: 20260802_0039
"""

import os

from alembic import op


revision = "20260802_0040"
down_revision = "20260802_0039"
branch_labels = None
depends_on = None


POLICY_NAME = "mplacas_rls_isolation"
PLATFORM_ROLE = "mplacas_platform"
ACTIVATION_APPROVAL = "ENABLE-RLS-20260802"

ORGANIZATION_TABLES = {
    "organizations": "id",
    "plants": "organization_id",
    "api_credentials": "organization_id",
    "auth_sessions": "organization_id",
    "operational_users": "organization_id",
    "user_invitations": "organization_id",
    "audit_events": "organization_id",
}

PLANT_TABLES = (
    "alert_delivery_records",
    "collection_tasks",
    "daily_climate_observations",
    "daily_pv_loss_assessments",
    "daily_pv_performance_results",
    "daily_solar_model_results",
    "devices",
    "monthly_report_snapshots",
    "outbox_events",
    "pipeline_executions",
    "report_export_tasks",
    "seasonal_pv_baseline_results",
    "utility_bills",
)

PLATFORM_TABLES = (
    "job_runs",
    "login_rate_limits",
)

ALL_TABLES = (
    *ORGANIZATION_TABLES,
    *PLANT_TABLES,
    "daily_energy",
    "daily_energy_versions",
    *PLATFORM_TABLES,
)


def _policy_expression(table_name: str) -> str:
    platform = "public.mplacas_platform_bypass_allowed()"
    if table_name in ORGANIZATION_TABLES:
        column = ORGANIZATION_TABLES[table_name]
        tenant = f"{column} = public.mplacas_current_organization_id()"
    elif table_name in PLANT_TABLES:
        tenant = (
            "EXISTS ("
            "SELECT 1 FROM public.plants AS rls_plant "
            f"WHERE rls_plant.id = {table_name}.plant_id "
            "AND rls_plant.organization_id = public.mplacas_current_organization_id()"
            ")"
        )
    elif table_name == "daily_energy":
        tenant = (
            "EXISTS ("
            "SELECT 1 FROM public.devices AS rls_device "
            "JOIN public.plants AS rls_plant ON rls_plant.id = rls_device.plant_id "
            "WHERE rls_device.id = daily_energy.device_id "
            "AND rls_plant.organization_id = public.mplacas_current_organization_id()"
            ")"
        )
    elif table_name == "daily_energy_versions":
        tenant = (
            "EXISTS ("
            "SELECT 1 FROM public.daily_energy AS rls_energy "
            "JOIN public.devices AS rls_device ON rls_device.id = rls_energy.device_id "
            "JOIN public.plants AS rls_plant ON rls_plant.id = rls_device.plant_id "
            "WHERE rls_energy.id = daily_energy_versions.daily_energy_id "
            "AND rls_plant.organization_id = public.mplacas_current_organization_id()"
            ")"
        )
    else:
        return platform
    return f"(({tenant}) OR {platform})"


def upgrade() -> None:
    if os.getenv("MPLACAS_RLS_ACTIVATION_APPROVED") != ACTIVATION_APPROVAL:
        raise RuntimeError(
            "RLS activation requires MPLACAS_RLS_ACTIVATION_APPROVED="
            f"{ACTIVATION_APPROVAL} after the isolated canary and platform-role preflight"
        )

    op.execute(
        """
        CREATE FUNCTION public.mplacas_current_organization_id()
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
    op.execute(
        f"""
        CREATE FUNCTION public.mplacas_platform_bypass_allowed()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        AS $$
            SELECT COALESCE(
                current_setting('mplacas.platform_bypass', true) = 'on',
                false
            )
            AND COALESCE(
                pg_has_role(current_user, to_regrole('{PLATFORM_ROLE}'), 'member'),
                false
            )
        $$
        """
    )

    for table_name in ALL_TABLES:
        expression = _policy_expression(table_name)
        op.execute(f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public."{table_name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{POLICY_NAME}" ON public."{table_name}" '
            f"FOR ALL USING ({expression}) WITH CHECK ({expression})"
        )


def downgrade() -> None:
    for table_name in reversed(ALL_TABLES):
        op.execute(
            f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON public."{table_name}"'
        )
        op.execute(f'ALTER TABLE public."{table_name}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public."{table_name}" DISABLE ROW LEVEL SECURITY')

    op.execute("DROP FUNCTION IF EXISTS public.mplacas_platform_bypass_allowed()")
    op.execute("DROP FUNCTION IF EXISTS public.mplacas_current_organization_id()")
