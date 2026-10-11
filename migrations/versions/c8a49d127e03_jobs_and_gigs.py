"""Jobs & Gigs: separate employer identities, reviewed listings and applications.

Revision ID: c8a49d127e03
Revises: b5d917c62a03
No auto-created employer records or imported jobs. All listings start pending.
"""
from alembic import op
import sqlalchemy as sa

revision = "c8a49d127e03"
down_revision = "b5d917c62a03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_employers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("state", sa.String(60), nullable=False),
        sa.Column("lga", sa.String(100), nullable=False),
        sa.Column("address", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1200), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("contact_phone", sa.String(30)),
        sa.Column("website", sa.String(255)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("review_note", sa.String(500)),
        sa.Column("reviewer_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_job_employers_owner_user_id", "job_employers", ["owner_user_id"], unique=True)
    op.create_index("ix_job_employers_status", "job_employers", ["status"])
    op.create_table(
        "job_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employer_id", sa.Integer(),
                  sa.ForeignKey("job_employers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("job_kind", sa.String(16), nullable=False),
        sa.Column("work_mode", sa.String(12), nullable=False),
        sa.Column("state", sa.String(60), nullable=False),
        sa.Column("lga", sa.String(100)),
        sa.Column("location_description", sa.String(255)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("requirements", sa.Text(), nullable=False),
        sa.Column("hours_per_week", sa.Integer()),
        sa.Column("schedule_notes", sa.String(240)),
        sa.Column("pay_min", sa.Integer(), nullable=False),
        sa.Column("pay_max", sa.Integer(), nullable=False),
        sa.Column("pay_unit", sa.String(12), nullable=False),
        sa.Column("closing_date", sa.Date(), nullable=False),
        sa.Column("serving_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("review_note", sa.String(500)),
        sa.Column("reviewer_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("pay_min > 0 AND pay_max >= pay_min", name="ck_job_valid_pay"),
        sa.CheckConstraint("hours_per_week IS NULL OR (hours_per_week BETWEEN 1 AND 84)",
                           name="ck_job_hours"),
    )
    op.create_index("ix_job_listings_employer_id", "job_listings", ["employer_id"])
    op.create_index("ix_job_listings_status", "job_listings", ["status"])
    op.create_index("ix_job_listings_state", "job_listings", ["state"])
    op.create_index("ix_job_listings_job_kind", "job_listings", ["job_kind"])
    op.create_table(
        "job_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(),
                  sa.ForeignKey("job_listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("applicant_user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cover_note", sa.String(1500), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("contact_phone", sa.String(30)),
        sa.Column("status", sa.String(12), nullable=False, server_default="submitted"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("job_id", "applicant_user_id", name="uq_job_one_application"),
    )
    op.create_index("ix_job_applications_job_id", "job_applications", ["job_id"])
    op.create_index("ix_job_applications_applicant_user_id",
                    "job_applications", ["applicant_user_id"])
    op.create_index("ix_job_applications_status", "job_applications", ["status"])


def downgrade():
    op.drop_index("ix_job_applications_status", table_name="job_applications")
    op.drop_index("ix_job_applications_applicant_user_id", table_name="job_applications")
    op.drop_index("ix_job_applications_job_id", table_name="job_applications")
    op.drop_table("job_applications")
    for name in ("ix_job_listings_job_kind", "ix_job_listings_state",
                 "ix_job_listings_status", "ix_job_listings_employer_id"):
        op.drop_index(name, table_name="job_listings")
    op.drop_table("job_listings")
    op.drop_index("ix_job_employers_status", table_name="job_employers")
    op.drop_index("ix_job_employers_owner_user_id", table_name="job_employers")
    op.drop_table("job_employers")
