"""Private gig work updates and two-party cancellation records.

Revision ID: a14b82a0d7e6
Revises: g93d0f6e2a41
"""
from alembic import op
import sqlalchemy as sa

revision = "a14b82a0d7e6"
down_revision = "g93d0f6e2a41"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gig_work_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey(
            "gig_deals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False, server_default="message"),
        sa.Column("body", sa.String(1200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_gig_work_updates_deal_id", "gig_work_updates", ["deal_id"])
    op.create_index("ix_gig_work_updates_author_id", "gig_work_updates", ["author_id"])
    op.create_table(
        "gig_termination_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey(
            "gig_deals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proposer_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("respondent_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("responded_at", sa.DateTime()),
    )
    op.create_index("ix_gig_termination_requests_deal_id",
                    "gig_termination_requests", ["deal_id"])
    op.create_index("ix_gig_termination_requests_proposer_id",
                    "gig_termination_requests", ["proposer_id"])
    op.create_index("uq_pending_gig_termination",
                    "gig_termination_requests", ["deal_id"], unique=True,
                    postgresql_where=sa.text("status = 'pending'"),
                    sqlite_where=sa.text("status = 'pending'"))


def downgrade():
    op.drop_index("uq_pending_gig_termination",
                  table_name="gig_termination_requests")
    op.drop_index("ix_gig_termination_requests_proposer_id",
                  table_name="gig_termination_requests")
    op.drop_index("ix_gig_termination_requests_deal_id",
                  table_name="gig_termination_requests")
    op.drop_table("gig_termination_requests")
    op.drop_index("ix_gig_work_updates_author_id", table_name="gig_work_updates")
    op.drop_index("ix_gig_work_updates_deal_id", table_name="gig_work_updates")
    op.drop_table("gig_work_updates")
