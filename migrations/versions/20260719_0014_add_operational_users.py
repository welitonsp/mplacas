"""Add operational users and credential expiration.

Revision ID: 20260719_0014
Revises: 20260719_0013
"""

from alembic import op
import sqlalchemy as sa

revision = "20260719_0014"
down_revision = "20260719_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operational_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_operational_users_name"),
    )
    op.create_index(
        "ix_operational_users_active",
        "operational_users",
        ["active"],
        unique=False,
    )
    with op.batch_alter_table("api_credentials") as batch:
        batch.add_column(sa.Column("user_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_foreign_key(
            "fk_api_credentials_user_id",
            "operational_users",
            ["user_id"],
            ["id"],
        )
        batch.create_index(
            "ix_api_credentials_user_id",
            ["user_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("api_credentials") as batch:
        batch.drop_index("ix_api_credentials_user_id")
        batch.drop_constraint("fk_api_credentials_user_id", type_="foreignkey")
        batch.drop_column("expires_at")
        batch.drop_column("user_id")
    op.drop_index("ix_operational_users_active", table_name="operational_users")
    op.drop_table("operational_users")
