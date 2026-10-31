"""Read-only release schema gate. Never migrates or stamps databases.

Run after an operator-approved Alembic migration. Emits only revision,
table and column names, never connection credentials or data records.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["AUTO_CREATE_TABLES"] = "false"

from sqlalchemy import inspect, text
from app import create_app
from app.extensions import db

EXPECTED_REVISION = "f49a1d8e2c90"
REQUIRED_COLUMNS = {
    "site_secrets": {"key", "ciphertext", "updated_at", "updated_by_id"},
    "learning_courses": {"id", "slug", "title", "published"},
    "learning_lessons": {"id", "course_id", "youtube_id", "position"},
    "learning_progress": {"id", "user_id", "lesson_id"},
    "learning_watch": {"id", "user_id", "lesson_id", "watched_seconds", "session_id", "last_seen_at", "last_position"},
    "learning_certificates": {"id", "code", "user_id", "course_id", "issued_at"},
    "users": {"id", "email", "role", "is_suspended"},
    "job_employers": {"id", "owner_user_id", "status"},
    "job_listings": {"id", "employer_id", "job_kind", "status"},
    "job_applications": {"id", "job_id", "applicant_user_id", "status"},
    "gig_deals": {"id", "application_id", "status", "worker_id",
                  "employer_id", "scope", "pay_amount", "payment_status"},
    "gig_disputes": {"id", "deal_id", "raised_by_id", "status",
                     "category", "outcome_code", "resolution"},
    "gig_dispute_evidence": {"id", "dispute_id", "submitted_by_id",
                             "description", "attachment", "sha256",
                             "content_type", "file_size"},
    "gig_dispute_events": {"id", "dispute_id", "kind", "description",
                           "visibility", "created_at"},
    "gig_reviews": {"id", "deal_id", "reviewer_id", "public_consent",
                    "moderation_status"},
    "gig_work_updates": {"id", "deal_id", "author_id", "body"},
    "gig_termination_requests": {"id", "deal_id", "status", "proposer_id"},
    "audit_logs": {"id", "user_id", "action"},
}
REQUIRED_INDEXES = {
    "gig_dispute_evidence": {"ix_gig_dispute_evidence_dispute_id"},
    "gig_dispute_events": {"ix_gig_dispute_events_dispute_id"},
    "gig_disputes": {"ix_gig_disputes_deal_id"},
    "gig_deals": {"ix_gig_deals_worker_id"},
}


def validate_schema(connection):
    """Return a list of safe, concise errors without modifying data."""
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    problems = []
    if "alembic_version" not in tables:
        return ["Alembic revision table is absent; manual migration review required."]
    revisions = [row[0] for row in connection.execute(
        text("SELECT version_num FROM alembic_version")).all()]
    if revisions != [EXPECTED_REVISION]:
        problems.append("Revision mismatch: expected the current release head.")
    for table, required in REQUIRED_COLUMNS.items():
        if table not in tables:
            problems.append("Required table is missing: " + table)
            continue
        columns = {col["name"] for col in inspector.get_columns(table)}
        for column in sorted(required - columns):
            problems.append("Missing column: {}.{}".format(table, column))
    for table, indexes in REQUIRED_INDEXES.items():
        if table not in tables:
            continue
        existing = {idx["name"] for idx in inspector.get_indexes(table)}
        for index in sorted(indexes - existing):
            problems.append("Missing index: {}.{}".format(table, index))
    return problems


def main():
    app = create_app(os.environ.get("FLASK_ENV", "production"))
    with app.app_context():
        with db.engine.connect() as connection:
            errors = validate_schema(connection)
    if errors:
        print("RELEASE SCHEMA CHECK FAILED. No changes have been made.", file=sys.stderr)
        for message in errors:
            print(" - " + message, file=sys.stderr)
        raise SystemExit(1)
    print("RELEASE SCHEMA CHECK PASSED: revision {} and required structures verified.".format(
        EXPECTED_REVISION))
    print("No database changes were made. Functional smoke testing is still required.")


if __name__ == "__main__":
    main()
