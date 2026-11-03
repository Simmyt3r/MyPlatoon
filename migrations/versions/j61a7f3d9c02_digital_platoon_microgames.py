"""Digital interplatoon contributions with one record per member/task/day.

Revision ID: j61a7f3d9c02
Revises: h50d2e9a7c14
"""
from alembic import op
import sqlalchemy as sa

revision = "j61a7f3d9c02"
down_revision = "h50d2e9a7c14"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "platoon_game_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("game_key", sa.String(40), nullable=False),
        sa.Column("platoon_id", sa.Integer(), sa.ForeignKey("platoons.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score_day", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "period_start", "game_key", "user_id", "score_day",
            name="uq_platoon_microgame_member_day",
        ),
    )
    for key in ("period_start", "game_key", "platoon_id", "user_id"):
        op.create_index("ix_platoon_game_activities_" + key,
                        "platoon_game_activities", [key])


def downgrade():
    op.drop_table("platoon_game_activities")
