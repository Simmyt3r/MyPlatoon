"""Operator-controlled, forward-only Alembic upgrades for Aiven.

Do not autogenerate migrations, execute arbitrary SQL, or allow downgrades.
Refuse ambiguous unversioned databases instead of guessing their schema.
"""
from contextlib import contextmanager

from flask_migrate import upgrade, stamp
from sqlalchemy import inspect, text

from app.extensions import db

LEGACY_REVISION = "bdb5eaa735f6"
NATIONAL_REVISION = "0d842ac781b6"
BASE_TABLES = {
    "users", "profiles", "album_versions", "announcements",
    "business_categories", "businesses", "audit_logs", "notifications",
    "skills", "profile_skills", "dating_personas", "dating_matches",
    "announcement_reactions", "announcement_comments",
}


@contextmanager
def _migration_lock():
    # PostgreSQL session lock prevents two Vercel instances upgrading at once.
    # Hold the connection open while Alembic runs on its own connection.
    with db.engine.connect() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_lock(78120261029)"))
            conn.commit()
        try:
            yield
        finally:
            if conn.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_advisory_unlock(78120261029)"))
                conn.commit()


def current_revision():
    with db.engine.connect() as conn:
        if "alembic_version" not in inspect(conn).get_table_names():
            return None
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def upgrade_to_head():
    """Safe bootstrap or upgrade. Caller must have passed setup/admin checks."""
    with _migration_lock():
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())
        if "alembic_version" not in tables:
            if not tables or tables == {"spatial_ref_sys"}:
                pass  # newly provisioned Aiven, including PostGIS-only database
            else:
                missing = BASE_TABLES - tables
                if missing:
                    raise RuntimeError("Partial or unknown legacy schema: manual migration review required.")

                profile_cols = {c["name"] for c in inspector.get_columns("profiles")}
                album_cols = {c["name"] for c in inspector.get_columns("album_versions")}
                if "pdf_data" not in album_cols:
                    raise RuntimeError("Legacy album schema requires manual migration review.")
                national = {"platoon_id", "service_stage"} <= profile_cols
                legacy = not ({"platoon_id", "service_stage"} & profile_cols)
                if national and {"platoons"} <= tables and "platoon_id" in album_cols:
                    stamp(revision=NATIONAL_REVISION)
                elif legacy and "platoons" not in tables and "platoon_id" not in album_cols:
                    stamp(revision=LEGACY_REVISION)
                else:
                    raise RuntimeError("Partially migrated database detected; upgrade blocked.")
        elif current_revision() is None and (tables - {"alembic_version", "spatial_ref_sys"}):
            raise RuntimeError("Existing tables with an empty Alembic revision; manual review required.")

        upgrade(revision="head")
        from scripts.check_release_schema import validate_schema
        with db.engine.connect() as conn:
            errors = validate_schema(conn)
        if errors:
            raise RuntimeError("Migration finished but release schema validation failed: " + "; ".join(errors))
        return current_revision()
