"""Optional, moderated gig reputation; old reviews remain private.

Revision ID: g93d0f6e2a41
Revises: f82b7e46c3a1
"""
from alembic import op
import sqlalchemy as sa

revision = "g93d0f6e2a41"
down_revision = "f82b7e46c3a1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("gig_reviews", sa.Column(
        "public_consent", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("gig_reviews", sa.Column(
        "moderation_status", sa.String(16), nullable=False,
        server_default="private"))
    op.add_column("gig_reviews", sa.Column("moderation_note", sa.String(500)))
    op.add_column("gig_reviews", sa.Column("reviewed_by_id", sa.Integer(),
        sa.ForeignKey("users.id", ondelete="SET NULL")))
    op.add_column("gig_reviews", sa.Column("reviewed_at", sa.DateTime()))
    op.create_index("ix_gig_reviews_moderation_status",
                    "gig_reviews", ["moderation_status"])


def downgrade():
    op.drop_index("ix_gig_reviews_moderation_status", table_name="gig_reviews")
    for column in ("reviewed_at", "reviewed_by_id", "moderation_note",
                   "moderation_status", "public_consent"):
        op.drop_column("gig_reviews", column)
