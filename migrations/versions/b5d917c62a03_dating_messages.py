"""Mutual-consent text conversations and recipient-only abuse reports.

Revision ID: b5d917c62a03
Revises: f1a9c3de7b21

All data stays in the configured Aiven PostgreSQL database. No external
messaging service/API credentials are needed.
"""
from alembic import op
import sqlalchemy as sa

revision = "b5d917c62a03"
down_revision = "f1a9c3de7b21"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dating_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("persona_low_id", sa.Integer(), sa.ForeignKey("dating_personas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("persona_high_id", sa.Integer(), sa.ForeignKey("dating_personas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("dating_personas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("body", sa.String(length=1500), nullable=False),
        sa.Column("is_removed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("persona_low_id < persona_high_id", name="ck_dating_message_pair_order"),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 1500", name="ck_dating_message_body_length"),
    )
    op.create_index("ix_dating_messages_thread", "dating_messages",
                    ["persona_low_id", "persona_high_id", "created_at", "id"])
    op.create_index("ix_dating_messages_sender_id", "dating_messages", ["sender_id"])
    op.create_table(
        "dating_message_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.Integer(),
                  sa.ForeignKey("dating_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reporter_id", sa.Integer(),
                  sa.ForeignKey("dating_personas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.UniqueConstraint("message_id", "reporter_id", name="uq_dating_message_report"),
    )
    op.create_index("ix_dating_message_reports_message_id", "dating_message_reports", ["message_id"])
    op.create_index("ix_dating_message_reports_status", "dating_message_reports", ["status"])


def downgrade():
    op.drop_index("ix_dating_message_reports_status", table_name="dating_message_reports")
    op.drop_index("ix_dating_message_reports_message_id", table_name="dating_message_reports")
    op.drop_table("dating_message_reports")
    op.drop_index("ix_dating_messages_sender_id", table_name="dating_messages")
    op.drop_index("ix_dating_messages_thread", table_name="dating_messages")
    op.drop_table("dating_messages")
