"""Add organizations.default_plant_id with single-plant backfill.

Revision ID: 20260805_0043
Revises: 20260804_0042

ADR-069, Etapa E: nova coluna `organizations.default_plant_id` (nullable,
FK `plants.id` com `ON DELETE SET NULL`, sem índice adicional — o acesso é
sempre pela PK da organização). Ela é a "usina ativa" usada pelo resolvedor
de usina (Etapa E2, fora do escopo desta migration) para responder sem 409
quando o chamador (bot do Telegram, endpoints administrativos) omite
`plant_id`.

Backfill na própria migration: hoje, em produção, toda organização tem
exatamente uma usina (ADR-069, §E.4), então a atualização abaixo preenche
100% das linhas existentes. Organizações com zero ou mais de uma usina
permanecem com `default_plant_id IS NULL` — o resolvedor cai no fallback de
usina única (zero ou uma usina) ou no 409 residual (mais de uma sem default
explícito), nenhuma escrita cega aqui.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260805_0043"
down_revision = "20260804_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(sa.Column("default_plant_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_organizations_default_plant_id",
            "plants",
            ["default_plant_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute(
        sa.text(
            "UPDATE organizations SET default_plant_id = ("
            "SELECT p.id FROM plants p WHERE p.organization_id = organizations.id"
            ") WHERE ("
            "SELECT count(*) FROM plants p WHERE p.organization_id = organizations.id"
            ") = 1"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_constraint("fk_organizations_default_plant_id", type_="foreignkey")
        batch.drop_column("default_plant_id")
