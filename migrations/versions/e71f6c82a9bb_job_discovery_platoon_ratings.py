"""Job discovery preferences and fair platoon mini-ratings.

Revision ID: e71f6c82a9bb
Revises: d6ee891f0d42
No existing member is auto-subscribed to alerts or given a platoon vote.
"""
from alembic import op
import sqlalchemy as sa

revision = "e71f6c82a9bb"
down_revision = "d6ee891f0d42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "saved_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("job_listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "job_id", name="uq_saved_job_user"),
    )
    op.create_index("ix_saved_jobs_user_id", "saved_jobs", ["user_id"])
    op.create_index("ix_saved_jobs_job_id", "saved_jobs", ["job_id"])
    op.create_table(
        "job_alert_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("preferred_state", sa.String(40)),
        sa.Column("preferred_kinds", sa.String(120), nullable=False, server_default="gig,part_time"),
        sa.Column("available_hours", sa.Integer()),
        sa.Column("remote_ok", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_job_alert_preferences_user_id", "job_alert_preferences", ["user_id"], unique=True)
    op.create_table(
        "job_alert_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("job_listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "job_id", name="uq_alert_delivery_user_job"),
    )
    op.create_index("ix_job_alert_deliveries_user_id", "job_alert_deliveries", ["user_id"])
    op.create_index("ix_job_alert_deliveries_job_id", "job_alert_deliveries", ["job_id"])
    op.create_table(
        "platoon_ratings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platoon_id", sa.Integer(), sa.ForeignKey("platoons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("platoon_id", "user_id", name="uq_platoon_rating_member"),
        sa.CheckConstraint("stars BETWEEN 1 AND 5", name="ck_platoon_rating_stars"),
    )
    op.create_index("ix_platoon_ratings_platoon_id", "platoon_ratings", ["platoon_id"])
    op.create_index("ix_platoon_ratings_user_id", "platoon_ratings", ["user_id"], unique=True)


def downgrade():
    for index in ("ix_platoon_ratings_user_id", "ix_platoon_ratings_platoon_id"):
        op.drop_index(index, table_name="platoon_ratings")
    op.drop_table("platoon_ratings")
    for index in ("ix_job_alert_deliveries_job_id", "ix_job_alert_deliveries_user_id"):
        op.drop_index(index, table_name="job_alert_deliveries")
    op.drop_table("job_alert_deliveries")
    op.drop_index("ix_job_alert_preferences_user_id", table_name="job_alert_preferences")
    op.drop_table("job_alert_preferences")
    for index in ("ix_saved_jobs_job_id", "ix_saved_jobs_user_id"):
        op.drop_index(index, table_name="saved_jobs")
    op.drop_table("saved_jobs")
