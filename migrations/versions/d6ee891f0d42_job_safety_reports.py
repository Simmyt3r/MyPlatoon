"""Confidential reports about fraudulent or unsafe job postings.

Revision ID: d6ee891f0d42
Revises: c8a49d127e03
"""
from alembic import op
import sqlalchemy as sa

revision = "d6ee891f0d42"
down_revision = "c8a49d127e03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(),
                  sa.ForeignKey("job_listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reporter_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.UniqueConstraint("job_id", "reporter_id", name="uq_job_report_per_user"),
    )
    op.create_index("ix_job_reports_job_id", "job_reports", ["job_id"])
    op.create_index("ix_job_reports_reporter_id", "job_reports", ["reporter_id"])
    op.create_index("ix_job_reports_status", "job_reports", ["status"])


def downgrade():
    op.drop_index("ix_job_reports_status", table_name="job_reports")
    op.drop_index("ix_job_reports_reporter_id", table_name="job_reports")
    op.drop_index("ix_job_reports_job_id", table_name="job_reports")
    op.drop_table("job_reports")
