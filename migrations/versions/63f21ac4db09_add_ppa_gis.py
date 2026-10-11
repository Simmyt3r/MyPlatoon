"""Nationwide PPA lookup and crowdsourced GIS records.

Revision ID: 63f21ac4db09
Revises: 0d842ac781b6
PostGIS functional spatial index is used on PostgreSQL; SQLite test DB is
supported without the extension. No member data is backfilled.
"""
from alembic import op
import sqlalchemy as sa

revision = "63f21ac4db09"
down_revision = "0d842ac781b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ppas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("name_key", sa.String(length=180), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("lga", sa.String(length=100), nullable=False),
        sa.Column("town", sa.String(length=120)),
        sa.Column("address", sa.String(length=250)),
        sa.Column("sector", sa.String(length=24), nullable=False, server_default="other"),
        sa.Column("website", sa.String(length=250)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("accommodation", sa.String(length=12), nullable=False, server_default="unknown"),
        sa.Column("allowance", sa.String(length=12), nullable=False, server_default="unknown"),
        sa.Column("experience_notes", sa.Text()),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("submitted_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("verified_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("verified_at", sa.DateTime()),
        sa.Column("rejection_reason", sa.String(length=500)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("latitude IS NULL OR (latitude BETWEEN -90 AND 90)",
                           name="ck_ppa_latitude"),
        sa.CheckConstraint("longitude IS NULL OR (longitude BETWEEN -180 AND 180)",
                           name="ck_ppa_longitude"),
        sa.CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL)",
            name="ck_ppa_coordinates_both"),
    )
    op.create_index("ix_ppas_name_key", "ppas", ["name_key"])
    op.create_index("ix_ppas_state", "ppas", ["state"])
    op.create_index("ix_ppas_status", "ppas", ["status"])
    op.create_index("ix_ppas_submitted_by_id", "ppas", ["submitted_by_id"])
    op.create_index("ix_ppas_state_lga_status", "ppas", ["state", "lga", "status"])

    op.create_table(
        "ppa_experiences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ppa_id", sa.Integer(), sa.ForeignKey("ppas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submitted_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("service_year", sa.Integer(), nullable=False),
        sa.Column("accommodation", sa.String(length=12), nullable=False, server_default="unknown"),
        sa.Column("allowance", sa.String(length=12), nullable=False, server_default="unknown"),
        sa.Column("notes", sa.String(length=1200)),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("rejection_reason", sa.String(length=500)),
        sa.Column("verified_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("ppa_id", "submitted_by_id", name="uq_ppa_experience_member"),
    )
    op.create_index("ix_ppa_experiences_ppa_id", "ppa_experiences", ["ppa_id"])
    op.create_index("ix_ppa_experiences_submitted_by_id", "ppa_experiences", ["submitted_by_id"])
    op.create_index("ix_ppa_experiences_status", "ppa_experiences", ["status"])

    # Aiven PostgreSQL supports PostGIS, installed in the target database
    # separately. Do not add a spatial dependency to local SQLite tests.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        op.execute(
            "CREATE INDEX ix_ppas_geo_gist ON ppas USING GIST "
            "((ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography)) "
            "WHERE longitude IS NOT NULL AND latitude IS NOT NULL AND status = 'verified'"
        )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_ppas_geo_gist")
    op.drop_index("ix_ppa_experiences_status", table_name="ppa_experiences")
    op.drop_index("ix_ppa_experiences_submitted_by_id", table_name="ppa_experiences")
    op.drop_index("ix_ppa_experiences_ppa_id", table_name="ppa_experiences")
    op.drop_table("ppa_experiences")
    op.drop_index("ix_ppas_state_lga_status", table_name="ppas")
    op.drop_index("ix_ppas_submitted_by_id", table_name="ppas")
    op.drop_index("ix_ppas_status", table_name="ppas")
    op.drop_index("ix_ppas_state", table_name="ppas")
    op.drop_index("ix_ppas_name_key", table_name="ppas")
    op.drop_table("ppas")
