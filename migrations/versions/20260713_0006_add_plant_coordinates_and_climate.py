"""Add plant coordinates and daily climate observations.

Revision ID: 20260713_0006
Revises: 20260713_0005
"""

from alembic import op
import sqlalchemy as sa

revision = "20260713_0006"
down_revision = "20260713_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("plants") as batch_op:
        batch_op.add_column(sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Numeric(9, 6), nullable=True))

    op.create_table(
        "daily_climate_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("irradiation_kwh_m2", sa.Numeric(10, 3), nullable=True),
        sa.Column("cloud_cover_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("precipitation_mm", sa.Numeric(10, 2), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plant_id",
            "observation_date",
            "source",
            name="uq_daily_climate_plant_date_source",
        ),
    )
    op.create_index(
        "ix_daily_climate_observations_plant_date",
        "daily_climate_observations",
        ["plant_id", "observation_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_daily_climate_observations_plant_date",
        table_name="daily_climate_observations",
    )
    op.drop_table("daily_climate_observations")
    with op.batch_alter_table("plants") as batch_op:
        batch_op.drop_column("longitude")
        batch_op.drop_column("latitude")
