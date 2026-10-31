"""Silabs Academy: courses, lessons, progress, certificates.

Revision ID: e2c5a84f9b31
Revises: c4c0e21ac7b8
"""
from alembic import op
import sqlalchemy as sa

revision = "e2c5a84f9b31"
down_revision = "c4c0e21ac7b8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(110), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("summary", sa.String(320), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("level", sa.String(24), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_learning_courses_slug", "learning_courses", ["slug"], unique=True)
    op.create_index("ix_learning_courses_published", "learning_courses", ["published"])

    op.create_table(
        "learning_lessons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey(
            "learning_courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("youtube_id", sa.String(11), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("course_id", "position", name="uq_learning_lesson_position"),
    )
    op.create_index("ix_learning_lessons_course_id", "learning_lessons", ["course_id"])

    op.create_table(
        "learning_progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey(
            "learning_lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "lesson_id", name="uq_learning_user_lesson"),
    )
    op.create_index("ix_learning_progress_user_id", "learning_progress", ["user_id"])
    op.create_index("ix_learning_progress_lesson_id", "learning_progress", ["lesson_id"])

    op.create_table(
        "learning_certificates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(36), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey(
            "learning_courses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("learner_name", sa.String(120), nullable=False),
        sa.Column("course_title", sa.String(180), nullable=False),
        sa.Column("lesson_count", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "course_id", name="uq_learning_user_certificate"),
    )
    op.create_index("ix_learning_certificates_code", "learning_certificates", ["code"], unique=True)
    op.create_index("ix_learning_certificates_user_id", "learning_certificates", ["user_id"])
    op.create_index("ix_learning_certificates_course_id", "learning_certificates", ["course_id"])


def downgrade():
    op.drop_table("learning_certificates")
    op.drop_table("learning_progress")
    op.drop_table("learning_lessons")
    op.drop_table("learning_courses")
