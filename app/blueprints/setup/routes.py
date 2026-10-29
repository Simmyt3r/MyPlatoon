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
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _is_aiven_configured():
    """Refuse writing to implicit SQLite, another provider or defaultdb."""
    if current_app.testing or current_app.debug:
        return True
    import os
    configured = os.environ.get("AIVEN_DATABASE_URL")
    if not configured:
        return False
    try:
        url = make_url(configured)
        return (url.get_backend_name() == "postgresql"
                and url.database == "myplatoon"
                and url.query.get("sslmode") in
                {"require", "verify-ca", "verify-full"})
    except (ValueError, TypeError):
        return False


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
    if not _is_aiven_configured():
        return render_template("setup/index.html", mode="unconfigured",
                               revision=None, configured_keys=set()), 503
    try:
        admin_exists = _has_admin()
        revision = current_revision()
    except Exception:
        current_app.logger.warning("Setup cannot connect to the configured database.")
        return render_template("setup/index.html", mode="unavailable",
                               revision=None, configured_keys=set()), 503

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
