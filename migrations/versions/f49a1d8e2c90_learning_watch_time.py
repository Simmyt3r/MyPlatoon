"""Persist server-capped lesson playback time before completion.

Revision ID: f49a1d8e2c90
Revises: e2c5a84f9b31
"""
from alembic import op
import sqlalchemy as sa

revision = "f49a1d8e2c90"
down_revision = "e2c5a84f9b31"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_watch",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey(
            "learning_lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("watched_seconds", sa.Float(), nullable=False,
                  server_default="0"),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("last_position", sa.Float(), nullable=True),
        sa.UniqueConstraint("user_id", "lesson_id",
                            name="uq_learning_watch_user_lesson"),
    )
    op.create_index("ix_learning_watch_user_id", "learning_watch", ["user_id"])
    op.create_index("ix_learning_watch_lesson_id", "learning_watch", ["lesson_id"])


def downgrade():
    op.drop_table("learning_watch")
