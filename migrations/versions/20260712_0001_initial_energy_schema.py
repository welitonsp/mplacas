"""Initial energy schema.

Revision ID: 20260712_0001
Revises:
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa

revision = "20260712_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    data_status = sa.Enum(
        "PROVISIONAL",
        "CONSOLIDATED",
        "INCOMPLETE",
        "UNAVAILABLE",
        name="datastatus",
    )
    data_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "plants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("installed_power_kwp", sa.Numeric(10, 3), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("serial_number", sa.String(length=120), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "serial_number"),
    )
    op.create_table(
        "daily_energy",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("production_date", sa.Date(), nullable=False),
        sa.Column("energy_kwh", sa.Numeric(12, 3), nullable=False),
        sa.Column("status", data_status, nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "production_date"),
    )
    op.create_table(
        "daily_energy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("daily_energy_id", sa.Uuid(), nullable=False),
        sa.Column("energy_kwh", sa.Numeric(12, 3), nullable=False),
        sa.Column("status", data_status, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["daily_energy_id"], ["daily_energy.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("daily_energy_versions")
    op.drop_table("daily_energy")
    op.drop_table("devices")
    op.drop_table("plants")
    sa.Enum(name="datastatus").drop(op.get_bind(), checkfirst=True)
