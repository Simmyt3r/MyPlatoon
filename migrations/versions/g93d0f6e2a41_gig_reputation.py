"""Optional moderated gig reputation. Historic ratings remain private.

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
    # Batch mode handles the new moderator ForeignKey on SQLite (used by
    # our fresh-migration CI) while emitting normal ALTER TABLE on Aiven PG.
    with op.batch_alter_table("gig_reviews", schema=None) as batch:
        batch.add_column(sa.Column(
            "public_consent", sa.Boolean(), nullable=False,
            server_default=sa.false()))
        batch.add_column(sa.Column(
            "moderation_status", sa.String(16), nullable=False,
            server_default="private"))
        batch.add_column(sa.Column("moderation_note", sa.String(500)))
        batch.add_column(sa.Column(
            "reviewed_by_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL")))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime()))
    op.create_index("ix_gig_reviews_moderation_status",
                    "gig_reviews", ["moderation_status"])


def downgrade():
    op.drop_index("ix_gig_reviews_moderation_status", table_name="gig_reviews")
    with op.batch_alter_table("gig_reviews", schema=None) as batch:
        for column in ("reviewed_at", "reviewed_by_id", "moderation_note",
                       "moderation_status", "public_consent"):
            batch.drop_column(column)
