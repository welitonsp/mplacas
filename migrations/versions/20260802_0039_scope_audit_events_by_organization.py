"""Scope audit and alert delivery records while preserving platform history.

Revision ID: 20260802_0039
Revises: 20260802_0038
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_0039"
down_revision = "20260802_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_audit_events_organization_id_organizations",
        "audit_events",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_audit_events_organization_id",
        "audit_events",
        ["organization_id"],
        unique=False,
    )
    op.drop_index(
        "ix_alert_delivery_records_fingerprint",
        table_name="alert_delivery_records",
    )
    op.drop_constraint(
        "alert_delivery_records_fingerprint_key",
        "alert_delivery_records",
        type_="unique",
    )
    op.add_column(
        "alert_delivery_records",
        sa.Column("plant_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_alert_delivery_records_plant_id_plants",
        "alert_delivery_records",
        "plants",
        ["plant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        """
        WITH fingerprint_ownership AS (
            SELECT aggregate_id AS fingerprint, min(plant_id::text)::uuid AS plant_id
            FROM outbox_events
            WHERE event_type = 'alert.delivery.requested'
              AND aggregate_type = 'alert'
            GROUP BY aggregate_id
            HAVING count(DISTINCT plant_id) = 1
        )
        UPDATE alert_delivery_records AS delivery
        SET plant_id = ownership.plant_id
        FROM fingerprint_ownership AS ownership
        WHERE delivery.fingerprint = ownership.fingerprint
          AND delivery.plant_id IS NULL
        """
    )
    op.create_index(
        "ix_alert_delivery_records_plant_id",
        "alert_delivery_records",
        ["plant_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_alert_delivery_records_plant_fingerprint",
        "alert_delivery_records",
        ["plant_id", "fingerprint"],
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM alert_delivery_records
                GROUP BY fingerprint HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'cannot restore global alert fingerprint uniqueness: duplicates exist';
            END IF;
        END
        $$
        """
    )
    op.drop_constraint(
        "uq_alert_delivery_records_plant_fingerprint",
        "alert_delivery_records",
        type_="unique",
    )
    op.drop_index(
        "ix_alert_delivery_records_plant_id",
        table_name="alert_delivery_records",
    )
    op.drop_constraint(
        "fk_alert_delivery_records_plant_id_plants",
        "alert_delivery_records",
        type_="foreignkey",
    )
    op.drop_column("alert_delivery_records", "plant_id")
    op.create_unique_constraint(
        "alert_delivery_records_fingerprint_key",
        "alert_delivery_records",
        ["fingerprint"],
    )
    op.create_index(
        "ix_alert_delivery_records_fingerprint",
        "alert_delivery_records",
        ["fingerprint"],
        unique=True,
    )
    op.drop_index("ix_audit_events_organization_id", table_name="audit_events")
    op.drop_constraint(
        "fk_audit_events_organization_id_organizations",
        "audit_events",
        type_="foreignkey",
    )
    op.drop_column("audit_events", "organization_id")
