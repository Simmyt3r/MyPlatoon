"""Dating v2: adult-use confirmation and individual blocks.

Revision ID: f1a9c3de7b21
Revises: 63f21ac4db09
Existing persona rows deliberately remain unconfirmed (NULL) so
previously enrolled users must acknowledge the adults-only rule.
"""
from alembic import op
import sqlalchemy as sa

revision = "f1a9c3de7b21"
down_revision = "63f21ac4db09"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("dating_personas") as b:
        b.add_column(sa.Column("age_confirmed_at", sa.DateTime(), nullable=True))
    op.create_table(
        "dating_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("blocker_id", sa.Integer(),
                  sa.ForeignKey("dating_personas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blocked_id", sa.Integer(),
                  sa.ForeignKey("dating_personas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_dating_block_pair"),
        sa.CheckConstraint("blocker_id != blocked_id", name="ck_dating_no_self_block"),
    )
    op.create_index("ix_dating_blocks_blocker_id", "dating_blocks", ["blocker_id"])
    op.create_index("ix_dating_blocks_blocked_id", "dating_blocks", ["blocked_id"])


def downgrade():
    op.drop_index("ix_dating_blocks_blocked_id", table_name="dating_blocks")
    op.drop_index("ix_dating_blocks_blocker_id", table_name="dating_blocks")
    op.drop_table("dating_blocks")
    with op.batch_alter_table("dating_personas") as b:
        b.drop_column("age_confirmed_at")
