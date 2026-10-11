"""Make MyPlatoon nationwide with cohort-scoped platoon memberships.

Revision ID: 0d842ac781b6
Revises: bdb5eaa735f6

Existing members have no reliable cohort data. Keep their platoon NULL and
stage PCM until they confirm an assignment; NEVER invent a platoon.
Legacy albums remain unscoped and are accessible to admins only.
"""
from alembic import op
import sqlalchemy as sa

revision = "0d842ac781b6"
down_revision = "bdb5eaa735f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "platoons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("service_year", sa.Integer(), nullable=False),
        sa.Column("batch", sa.String(1), nullable=False),
        sa.Column("stream", sa.String(2), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.UniqueConstraint("state", "service_year", "batch", "stream", "number",
                            name="uq_nysc_platoon_identity"),
        sa.CheckConstraint("number >= 1 AND number <= 99", name="ck_platoon_number"),
    )
    op.create_index("ix_platoons_state", "platoons", ["state"])
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.add_column(sa.Column("service_stage", sa.String(12),
                                      nullable=False, server_default="pcm"))
        batch_op.add_column(sa.Column("platoon_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_profile_platoon", "platoons",
                                    ["platoon_id"], ["id"])
        batch_op.create_index("ix_profiles_platoon_id", ["platoon_id"])
    with op.batch_alter_table("album_versions") as batch_op:
        batch_op.add_column(sa.Column("platoon_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_album_platoon", "platoons",
                                    ["platoon_id"], ["id"])
        batch_op.create_index("ix_album_platoon_id", ["platoon_id"])


def downgrade():
    with op.batch_alter_table("album_versions") as batch_op:
        batch_op.drop_index("ix_album_platoon_id")
        batch_op.drop_constraint("fk_album_platoon", type_="foreignkey")
        batch_op.drop_column("platoon_id")
    with op.batch_alter_table("profiles") as batch_op:
        batch_op.drop_index("ix_profiles_platoon_id")
        batch_op.drop_constraint("fk_profile_platoon", type_="foreignkey")
        batch_op.drop_column("platoon_id")
        batch_op.drop_column("service_stage")
    op.drop_index("ix_platoons_state", table_name="platoons")
    op.drop_table("platoons")
