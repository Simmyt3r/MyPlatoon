"""Interplatoon game results and elected two-week leadership.

Revision ID: h50d2e9a7c14
Revises: f49a1d8e2c90
"""
from alembic import op
import sqlalchemy as sa

revision = "h50d2e9a7c14"
down_revision = "f49a1d8e2c90"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "platoon_leader_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platoon_id", sa.Integer(), sa.ForeignKey("platoons.id"), nullable=False),
        sa.Column("term_start", sa.Date(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("nominated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("term_start", "user_id", name="uq_platoon_leader_candidate_term_user"),
    )
    op.create_index("ix_platoon_leader_candidates_platoon_id",
                    "platoon_leader_candidates", ["platoon_id"])
    op.create_index("ix_platoon_leader_candidates_term_start",
                    "platoon_leader_candidates", ["term_start"])
    op.create_table(
        "platoon_leader_votes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platoon_id", sa.Integer(), sa.ForeignKey("platoons.id"), nullable=False),
        sa.Column("term_start", sa.Date(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey(
            "platoon_leader_candidates.id"), nullable=False),
        sa.Column("voter_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("term_start", "voter_id", name="uq_platoon_leader_term_voter"),
    )
    op.create_index("ix_platoon_leader_votes_platoon_id", "platoon_leader_votes", ["platoon_id"])
    op.create_index("ix_platoon_leader_votes_term_start", "platoon_leader_votes", ["term_start"])
    op.create_table(
        "platoon_game_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("platoon_id", sa.Integer(), sa.ForeignKey("platoons.id"), nullable=False),
        sa.Column("game_key", sa.String(40), nullable=False),
        sa.Column("placement", sa.Integer(), nullable=False),
        sa.Column("details", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("submitted_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("period_start", "game_key", "platoon_id",
                            name="uq_platoon_game_period_entry"),
        sa.CheckConstraint("placement >= 1 AND placement <= 10",
                           name="ck_platoon_game_placement"),
    )
    op.create_index("ix_platoon_game_results_period_start",
                    "platoon_game_results", ["period_start"])
    op.create_index("ix_platoon_game_results_platoon_id",
                    "platoon_game_results", ["platoon_id"])
    op.create_index("ix_platoon_game_results_status",
                    "platoon_game_results", ["status"])


def downgrade():
    op.drop_table("platoon_game_results")
    op.drop_table("platoon_leader_votes")
    op.drop_table("platoon_leader_candidates")
