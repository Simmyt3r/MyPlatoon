"""Gig hiring offers, two-party completion, disputes and reviews.

Revision ID: f82b7e46c3a1
Revises: e71f6c82a9bb
"""
from alembic import op
import sqlalchemy as sa

revision = "f82b7e46c3a1"
down_revision = "e71f6c82a9bb"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gig_deals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey(
            "job_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employer_id", sa.Integer(), sa.ForeignKey(
            "job_employers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("worker_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", sa.String(2500), nullable=False),
        sa.Column("schedule", sa.String(300), nullable=False),
        sa.Column("pay_amount", sa.Integer(), nullable=False),
        sa.Column("pay_unit", sa.String(12), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="offered"),
        sa.Column("payment_status", sa.String(20), nullable=False,
                  server_default="not_reported"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime()),
        sa.Column("completion_requested_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("closed_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("application_id", name="uq_gig_deal_application"),
        sa.CheckConstraint("pay_amount > 0", name="ck_gig_deal_positive_pay"),
    )
    for field in ("application_id", "employer_id", "worker_id", "status"):
        op.create_index("ix_gig_deals_" + field, "gig_deals", [field],
                        unique=(field == "application_id"))
    op.create_table(
        "gig_disputes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey(
            "gig_deals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raised_by_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(1500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("resolution", sa.String(1000)),
        sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
    )
    for field in ("deal_id", "raised_by_id", "status"):
        op.create_index("ix_gig_disputes_" + field, "gig_disputes", [field])
    op.create_table(
        "gig_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey(
            "gig_deals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("deal_id", "reviewer_id",
                            name="uq_gig_review_deal_reviewer"),
        sa.CheckConstraint("stars BETWEEN 1 AND 5", name="ck_gig_review_stars"),
    )
    op.create_index("ix_gig_reviews_deal_id", "gig_reviews", ["deal_id"])
    op.create_index("ix_gig_reviews_reviewer_id", "gig_reviews", ["reviewer_id"])


def downgrade():
    for field in ("reviewer_id", "deal_id"):
        op.drop_index("ix_gig_reviews_" + field, table_name="gig_reviews")
    op.drop_table("gig_reviews")
    for field in ("status", "raised_by_id", "deal_id"):
        op.drop_index("ix_gig_disputes_" + field, table_name="gig_disputes")
    op.drop_table("gig_disputes")
    for field in ("status", "worker_id", "employer_id", "application_id"):
        op.drop_index("ix_gig_deals_" + field, table_name="gig_deals")
    op.drop_table("gig_deals")
