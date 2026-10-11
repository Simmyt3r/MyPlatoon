"""Safe Alembic upgrade for MyPlatoon deployments that used db.create_all().

Run through GitHub Actions > Apply MyPlatoon production migrations. Existing
user rows are NOT deleted and platoon numbers are never guessed.

We only stamp an unversioned database when the full legacy table layout has
been verified. Refuse ambiguous/partly migrated schemas.
"""
import os
import subprocess
import sys

os.environ["AUTO_CREATE_TABLES"] = "false"

from sqlalchemy import inspect
from app import create_app
from app.extensions import db

LEGACY_REVISION = "bdb5eaa735f6"
NATIONAL_REVISION = "0d842ac781b6"
BASE_TABLES = {
    "users", "profiles", "album_versions", "announcements",
    "business_categories", "businesses", "audit_logs", "notifications",
    "skills", "dating_personas", "dating_matches",
    "announcement_reactions", "announcement_comments",
}


def cli(*args):
    print("Running flask db", " ".join(args), flush=True)
    subprocess.run([sys.executable, "-m", "flask", "db", *args], check=True)


def main():
    app = create_app(os.environ.get("FLASK_ENV", "production"))
    with app.app_context():
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())

        if "alembic_version" in tables:
            print("Alembic revision table exists. Upgrading normally.")
        elif not tables.intersection(BASE_TABLES):
            print("New empty database. Migrating from baseline.")
        else:
            missing = BASE_TABLES - tables
            if missing:
                raise RuntimeError(
                    "Cannot auto-stamp partially initialized legacy database; "
                    f"missing tables: {', '.join(sorted(missing))}. Review migration state manually."
                )

            profile_columns = {c["name"] for c in inspector.get_columns("profiles")}
            album_columns = {c["name"] for c in inspector.get_columns("album_versions")}
            if "pdf_data" not in album_columns:
                raise RuntimeError("Legacy schema is missing album_versions.pdf_data; manual review required.")

            is_national = "platoon_id" in profile_columns and "service_stage" in profile_columns
            is_legacy = not ("platoon_id" in profile_columns or "service_stage" in profile_columns)

            if is_national and "platoons" in tables and "platoon_id" in album_columns:
                print("Schema already includes nationwide platoons; stamping national revision.")
                cli("stamp", NATIONAL_REVISION)
            elif is_legacy and "platoons" not in tables and "platoon_id" not in album_columns:
                print("Verified legacy db.create_all schema; stamping legacy revision.")
                cli("stamp", LEGACY_REVISION)
            else:
                raise RuntimeError("Partially migrated database detected. No changes made; inspect schema manually.")

    cli("upgrade")
    cli("current")
    print("MyPlatoon migrations completed.")


if __name__ == "__main__":
    main()
