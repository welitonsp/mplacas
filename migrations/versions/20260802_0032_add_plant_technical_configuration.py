"""Add plant and inverter technical configuration.

Revision ID: 20260802_0032
Revises: 20260801_0031
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_0032"
down_revision = "20260801_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    invalid_installed_power = op.get_bind().execute(
        sa.text(
            "SELECT COUNT(*) FROM plants "
            "WHERE installed_power_kwp IS NOT NULL AND installed_power_kwp <= 0"
        )
    ).scalar_one()
    if invalid_installed_power:
        raise RuntimeError(
            "plants.installed_power_kwp contains non-positive values; "
            "correct them before applying technical configuration constraints"
        )

    with op.batch_alter_table("plants") as batch:
        batch.add_column(sa.Column("ac_capacity_kw", sa.Numeric(10, 3), nullable=True))
        batch.add_column(sa.Column("array_tilt_degrees", sa.Numeric(5, 2), nullable=True))
        batch.add_column(sa.Column("array_azimuth_degrees", sa.Numeric(5, 2), nullable=True))
        batch.add_column(sa.Column("module_technology", sa.String(40), nullable=True))
        batch.add_column(sa.Column("commissioned_on", sa.Date(), nullable=True))
        batch.create_check_constraint(
            "ck_plants_installed_power_positive",
            "installed_power_kwp IS NULL OR installed_power_kwp > 0",
        )
        batch.create_check_constraint(
            "ck_plants_ac_capacity_positive",
            "ac_capacity_kw IS NULL OR ac_capacity_kw > 0",
        )
        batch.create_check_constraint(
            "ck_plants_array_tilt_range",
            "array_tilt_degrees IS NULL OR "
            "(array_tilt_degrees >= 0 AND array_tilt_degrees <= 90)",
        )
        batch.create_check_constraint(
            "ck_plants_array_azimuth_range",
            "array_azimuth_degrees IS NULL OR "
            "(array_azimuth_degrees >= 0 AND array_azimuth_degrees < 360)",
        )
        batch.create_check_constraint(
            "ck_plants_module_technology",
            "module_technology IS NULL OR module_technology IN "
            "('MONOCRYSTALLINE_SILICON', 'POLYCRYSTALLINE_SILICON', "
            "'THIN_FILM', 'OTHER')",
        )

    with op.batch_alter_table("devices") as batch:
        batch.add_column(sa.Column("dc_capacity_kwp", sa.Numeric(10, 3), nullable=True))
        batch.add_column(sa.Column("ac_capacity_kw", sa.Numeric(10, 3), nullable=True))
        batch.create_check_constraint(
            "ck_devices_dc_capacity_positive",
            "dc_capacity_kwp IS NULL OR dc_capacity_kwp > 0",
        )
        batch.create_check_constraint(
            "ck_devices_ac_capacity_positive",
            "ac_capacity_kw IS NULL OR ac_capacity_kw > 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("devices") as batch:
        batch.drop_constraint("ck_devices_ac_capacity_positive", type_="check")
        batch.drop_constraint("ck_devices_dc_capacity_positive", type_="check")
        batch.drop_column("ac_capacity_kw")
        batch.drop_column("dc_capacity_kwp")

    with op.batch_alter_table("plants") as batch:
        batch.drop_constraint("ck_plants_module_technology", type_="check")
        batch.drop_constraint("ck_plants_array_azimuth_range", type_="check")
        batch.drop_constraint("ck_plants_array_tilt_range", type_="check")
        batch.drop_constraint("ck_plants_ac_capacity_positive", type_="check")
        batch.drop_constraint("ck_plants_installed_power_positive", type_="check")
        batch.drop_column("commissioned_on")
        batch.drop_column("module_technology")
        batch.drop_column("array_azimuth_degrees")
        batch.drop_column("array_tilt_degrees")
        batch.drop_column("ac_capacity_kw")
