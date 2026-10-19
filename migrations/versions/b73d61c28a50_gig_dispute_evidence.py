"""Private dispute evidence and traceable case outcomes.

Revision ID: b73d61c28a50
Revises: a14b82a0d7e6
"""
from alembic import op
import sqlalchemy as sa

revision = "b73d61c28a50"
down_revision = "a14b82a0d7e6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("gig_disputes") as batch:
        batch.add_column(sa.Column("category", sa.String(32),
                                   nullable=False, server_default="other"))
        batch.add_column(sa.Column("outcome_code", sa.String(32)))
    op.create_table(
        "gig_dispute_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dispute_id", sa.Integer(), sa.ForeignKey(
            "gig_disputes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submitted_by_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("description", sa.String(1800), nullable=False),
        sa.Column("filename", sa.String(180)),
        sa.Column("content_type", sa.String(48)),
        sa.Column("file_size", sa.Integer()),
        sa.Column("sha256", sa.String(64)),
        sa.Column("attachment", sa.LargeBinary()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_gig_dispute_evidence_dispute_id",
                    "gig_dispute_evidence", ["dispute_id"])
    op.create_index("ix_gig_dispute_evidence_submitted_by_id",
                    "gig_dispute_evidence", ["submitted_by_id"])
    op.create_table(
        "gig_dispute_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dispute_id", sa.Integer(), sa.ForeignKey(
            "gig_disputes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey(
            "users.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("description", sa.String(750), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False,
                  server_default="participants"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_gig_dispute_events_dispute_id",
                    "gig_dispute_events", ["dispute_id"])


def downgrade():
    op.drop_index("ix_gig_dispute_events_dispute_id",
                  table_name="gig_dispute_events")
    op.drop_table("gig_dispute_events")
    op.drop_index("ix_gig_dispute_evidence_submitted_by_id",
                  table_name="gig_dispute_evidence")
    op.drop_index("ix_gig_dispute_evidence_dispute_id",
                  table_name="gig_dispute_evidence")
    op.drop_table("gig_dispute_evidence")
    with op.batch_alter_table("gig_disputes") as batch:
        batch.drop_column("outcome_code")
        batch.drop_column("category")
