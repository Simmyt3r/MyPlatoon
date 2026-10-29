"""One-time Aiven bootstrap and authenticated infrastructure maintenance."""
import hmac

from email_validator import EmailNotValidError, validate_email
from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_user
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.extensions import db, limiter
from app.models import BusinessCategory, DEFAULT_CATEGORIES, Profile, User
from app.services.audit_service import log_action
from app.services.schema_manager import current_revision, upgrade_to_head
from app.services.site_secrets import ALLOWED_KEYS, save_cloudinary, saved_keys

bp = Blueprint("setup", __name__)


@bp.after_request
def secure_setup_response(response):
    response.headers["Cache-Control"] = "no-store, private"
    # HTTPS CSRF checks need a same-origin Referer. Do not suppress it on setup.
    # No referrer is sent to external sites with this privacy-preserving policy.
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _aiven_configuration_issue():
    """Describe the exact non-secret URL validation problem.

    This function must never return the DSN, hostname, username, password,
    port, or raw SQLAlchemy exception to an unauthenticated visitor.
    """
    if current_app.testing or current_app.debug:
        return None

    import os
    configured = (os.environ.get("AIVEN_DATABASE_URL") or "").strip()
    if not configured:
        return ("AIVEN_DATABASE_URL is missing from this running deployment. "
                "Add it to the Vercel Production environment and redeploy "
                "the production deployment.")
    if configured.startswith("postgres://"):
        configured = "postgresql://" + configured[len("postgres://"):]
    try:
        url = make_url(configured)
    except Exception:
        # Intentionally don't include the exception, which can contain the DSN.
        return ("AIVEN_DATABASE_URL cannot be parsed. Copy the PostgreSQL "
                "Service URI from Aiven, use URL-encoded credentials, and "
                "remove surrounding quotes.")

    if url.get_backend_name() != "postgresql":
        return ("AIVEN_DATABASE_URL is not a PostgreSQL connection URL. "
                "Use an Aiven PostgreSQL service URI starting with postgresql://.")
    if not url.host or not url.username:
        return ("AIVEN_DATABASE_URL is missing a database host or username. "
                "Use the complete Aiven PostgreSQL service URI.")
    if url.database != "myplatoon":
        return ("The Aiven connection URL is not targeting database 'myplatoon'. "
                "If Aiven supplied /defaultdb, replace that path with "
                "/myplatoon after creating the database in Aiven.")
    if url.query.get("sslmode") not in ("require", "verify-ca", "verify-full"):
        return ("The Aiven connection URL is missing a supported sslmode. "
                "Append ?sslmode=require (or &sslmode=require when the "
                "URL already has query parameters).")
    return None


def _is_aiven_configured():
    """Backward-compatible boolean check used by the setup view."""
    return _aiven_configuration_issue() is None


def _has_admin():
    with db.engine.connect() as conn:
        if "users" not in inspect(conn).get_table_names():
            return False
        return conn.execute(text(
            "SELECT 1 FROM users WHERE role = 'admin' LIMIT 1"
        )).scalar() is not None


def _valid_setup_token(candidate):
    configured = current_app.config.get("SETUP_TOKEN") or ""
    return (len(configured) >= 32
            and hmac.compare_digest(configured, candidate or ""))


def _bootstrap(data):
    name = (data.get("name") or "").strip()
    email_text = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if len(name) < 2 or len(name) > 120 or len(password) < 16:
        raise ValueError("Use a name and a password of at least 16 characters.")
    try:
        email = validate_email(email_text, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError("Enter a valid administrator email address.") from exc
    if data.get("backup_confirm") != "yes":
        raise ValueError("Confirm you have backed up any existing database first.")

    upgrade_to_head()
    if _has_admin():
        raise ValueError("An administrator already exists; setup is locked.")
    if User.query.filter_by(email=email).first() is not None:
        raise ValueError("That email belongs to an existing member. Use a different address.")

    admin = User(full_name=name, email=email, role="admin")
    admin.set_password(password)
    db.session.add(admin)
    db.session.flush()
    db.session.add(Profile(user_id=admin.id, status="approved"))
    for label in DEFAULT_CATEGORIES:
        if not BusinessCategory.query.filter_by(name=label).first():
            db.session.add(BusinessCategory(name=label))
    db.session.commit()
    log_action(admin, "site.bootstrap", "site", "initial", "First admin created through setup")
    login_user(admin, remember=False)
    return admin


@bp.route("/setup", methods=["GET", "POST"])
@limiter.limit("8 per hour", methods=["POST"])
def setup():
    issue = _aiven_configuration_issue()
    if issue:
        return render_template("setup/index.html", mode="unconfigured",
                               config_issue=issue,
                               revision=None, configured_keys=set()), 503
    try:
        admin_exists = _has_admin()
        revision = current_revision()
    except Exception as exc:
        from app.services.aiven_diagnostics import diagnose_database_error

        category, summary, guidance = diagnose_database_error(exc)
        # Only log the sanitized category and exception class, never
        # str(exc), which may include a DSN or server-side details.
        current_app.logger.warning(
            "Aiven setup database check failed [%s] (%s)",
            category, type(exc).__name__,
        )
        return render_template(
            "setup/index.html", mode="unavailable",
            db_error_code=category, db_error_summary=summary,
            db_error_guidance=guidance,
            revision=None, configured_keys=set(),
        ), 503

    if not admin_exists:
        if request.method == "POST":
            if not _valid_setup_token(request.form.get("setup_token")):
                flash("Invalid or unavailable one-time setup token.", "danger")
                return redirect(url_for("setup.setup"))
            try:
                _bootstrap(request.form)
                flash("MyPlatoon database initialized and administrator created.", "success")
                return redirect(url_for("setup.setup"))
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), "danger")
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Initial schema setup failed.")
                flash("Database initialization failed. Verify Aiven access and migration prerequisites.", "danger")
            return redirect(url_for("setup.setup"))
        return render_template("setup/index.html", mode="bootstrap",
                               revision=revision, configured_keys=set())

    # Setup token is permanently ineffective once an admin exists.
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next="/setup"))
    if not current_user.is_admin or not current_user.is_active:
        abort(403)

    if request.method == "POST":
        if not current_user.check_password(request.form.get("admin_password") or ""):
            flash("Administrator password verification failed.", "danger")
            return redirect(url_for("setup.setup"))
        action = request.form.get("action")
        if action == "upgrade":
            if (request.form.get("confirmation") != "MIGRATE MYPLATOON"
                    or request.form.get("backup_confirm") != "yes"):
                flash("Confirm the backup and enter the exact migration phrase.", "danger")
                return redirect(url_for("setup.setup"))
            try:
                admin_id = current_user.id
                db.session.remove()
                upgraded = upgrade_to_head()
                log_action(db.session.get(User, admin_id), "schema.upgrade",
                           "database", upgraded, "Admin-approved forward-only upgrade")
                flash("Database migrated and schema verified: " + upgraded, "success")
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Admin-approved schema upgrade failed.")
                flash("Upgrade failed. Check runtime logs and review the schema before retrying.", "danger")
        elif action == "cloudinary":
            values = {key: (request.form.get(key) or "").strip()
                      for key in ALLOWED_KEYS}
            try:
                if not any(values.values()):
                    raise ValueError("Enter at least one Cloudinary setting to update.")
                save_cloudinary(values, current_user)
                log_action(current_user, "integrations.update", "site",
                           "cloudinary", "Updated encrypted integration configuration")
                flash("Cloudinary settings saved securely.", "success")
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), "danger")
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Encrypted integration settings update failed.")
                flash("Could not update Cloudinary settings. Check server logs.", "danger")
        else:
            abort(400)
        return redirect(url_for("setup.setup"))

    try:
        keys = saved_keys()
    except Exception:
        keys = set()
    return render_template("setup/index.html", mode="admin",
                           revision=revision, configured_keys=keys)


@bp.route("/setup/form-check", methods=["POST"])
@limiter.limit("12 per hour")
def form_check():
    """Read-only same-origin CSRF round-trip probe, with no DB access.

    Flask-WTF global CSRFProtect rejects this request before the view
    unless its csrf_token matches the browser's signed session.
    """
    return render_template(
        "setup/index.html", mode="form_check_success",
        revision=None, configured_keys=set(),
    )
