"""Encrypted admin-managed integration credentials.

Revision ID: c4c0e21ac7b8
Revises: b73d61c28a50
"""
from alembic import op
import sqlalchemy as sa

revision = "c4c0e21ac7b8"
down_revision = "b73d61c28a50"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "site_secrets",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
    )


def downgrade():
    # A deliberate rollback removes encrypted credentials; never execute
    # against production without a data-preserving migration plan.
    op.drop_table("site_secrets")
