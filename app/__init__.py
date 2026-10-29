import logging
import os

from flask import Flask, render_template, request
from sqlalchemy import or_, and_

from app.config import CONFIG_MAP
from app.extensions import db, migrate, login_manager, csrf, limiter


def create_app(config_name: str = None):
    app = Flask(__name__, instance_relative_config=False)

    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(CONFIG_MAP.get(config_name, CONFIG_MAP["default"]))

    # Never run a public deployment with the predictable development secret:
    # it protects signed session and CSRF tokens. Fail before serving requests.
    if config_name == "production":
        secret = app.config.get("SECRET_KEY")
        if (not isinstance(secret, (str, bytes)) or len(secret) < 32
                or secret == "dev-key-not-secure-change-me"):
            raise RuntimeError(
                "Production requires a unique SECRET_KEY of at least 32 characters. "
                "Set it in the deployment environment before starting MyPlatoon."
            )

    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_cli(app)
    _register_context_processors(app)
    _register_template_globals(app)
    _configure_logging(app)
    _ensure_database_schema(app)

    return app


def _init_extensions(app):
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        if user is not None and user.role != "employer" and user.profile is None:
            # Self-heal: see app/services/profile_service.py for why this
            # is needed and why it's written this specific way.
            from app.services.profile_service import ensure_profile
            ensure_profile(user)
        return user


def _register_blueprints(app):
    from app.blueprints.main.routes import bp as main_bp
    from app.blueprints.auth.routes import bp as auth_bp
    from app.blueprints.profile.routes import bp as profile_bp
    from app.blueprints.business.routes import bp as business_bp
    from app.blueprints.directory.routes import bp as directory_bp
    from app.blueprints.admin.routes import bp as admin_bp
    from app.blueprints.album.routes import bp as album_bp
    from app.blueprints.ppa.routes import bp as ppa_bp
    from app.blueprints.dating.routes import bp as dating_bp
    from app.blueprints.jobs.routes import bp as jobs_bp
    from app.blueprints.gig_deals.routes import bp as gig_deals_bp
    from app.blueprints.platoons.routes import bp as platoons_bp
    from app.blueprints.setup.routes import bp as setup_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(profile_bp, url_prefix="/profile")
    app.register_blueprint(business_bp, url_prefix="/business")
    app.register_blueprint(directory_bp, url_prefix="/directory")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(album_bp, url_prefix="/album")
    app.register_blueprint(ppa_bp, url_prefix="/ppas")
    app.register_blueprint(dating_bp, url_prefix="/dating")
    app.register_blueprint(jobs_bp, url_prefix="/jobs")
    app.register_blueprint(gig_deals_bp, url_prefix="/jobs/deals")
    app.register_blueprint(platoons_bp, url_prefix="/platoons")
    app.register_blueprint(setup_bp)


def _register_error_handlers(app):
    from flask_wtf.csrf import CSRFError

    def _render(code, *, setup_mode="error", **kwargs):
        # /setup must remain standalone before the database has any tables.
        if request.endpoint == "setup.setup":
            return render_template(
                "setup/index.html", mode=setup_mode,
                error_code=code, revision=None, configured_keys=set(),
                **kwargs,
            ), code
        return render_template(f"errors/{code}.html"), code

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        if request.endpoint != "setup.setup":
            return _render(400)
        # Only expose curated messages. Never show raw exception detail or
        # any cookie, session, or signing-key value to the browser.
        description = str(getattr(e, "description", "")).lower()
        if "missing" in description and "session" in description:
            reason = "The original form session is no longer available."
        elif "missing" in description:
            reason = "The form security token was missing."
        elif "expired" in description:
            reason = "The form security token has expired."
        elif "match" in description:
            reason = "The form security token no longer matches your session."
        else:
            reason = "The form security token could not be validated."
        app.logger.info("Setup CSRF rejected [%s]", reason)
        return _render(400, setup_mode="csrf_error", csrf_reason=reason)

    @app.errorhandler(400)
    def bad_request(e):
        return _render(400)

    @app.errorhandler(403)
    def forbidden(e):
        return _render(403)

    @app.errorhandler(404)
    def not_found(e):
        return _render(404)

    @app.errorhandler(429)
    def rate_limited(e):
        return _render(429)

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Unhandled server error on %s", request.path)
        db.session.rollback()
        return _render(500)


def _register_cli(app):
    from app.cli import register_cli_commands
    register_cli_commands(app)


def _register_context_processors(app):
    from app.utils.urls import ensure_scheme
    app.jinja_env.filters["ensure_scheme"] = ensure_scheme

    @app.context_processor
    def inject_globals():
        # The marketing landing is deliberately standalone: this template
        # needs no app-shell variables, login-manager user lookup, database
        # or deployment-specific branding. Keep "/" usable before setup.
        if request.endpoint in ("main.index", "setup.setup"):
            return {}
        from flask_login import current_user
        from app.services.notification_service import unread_count
        from app.models import Profile, Notification

        suggested_profiles = []
        recent_notifications = []
        if current_user and getattr(current_user, "is_authenticated", False):
            query = Profile.query.filter_by(status="approved")
            own = current_user.profile
            if current_user.is_admin:
                query = query.filter(Profile.profile_visibility.in_(["public", "platoon"]))
            elif own and own.status == "approved" and own.platoon_id:
                query = query.filter(or_(
                    Profile.profile_visibility == "public",
                    and_(Profile.profile_visibility == "platoon",
                         Profile.platoon_id == own.platoon_id),
                ))
            else:
                query = query.filter(Profile.profile_visibility == "public")
            if own:
                query = query.filter(Profile.id != own.id)
            suggested_profiles = query.order_by(Profile.updated_at.desc()).limit(5).all()

            recent_notifications = (Notification.query
                                     .filter_by(user_id=current_user.id)
                                     .order_by(Notification.created_at.desc())
                                     .limit(6).all())

        return {
            "APP_NAME": app.config["APP_NAME"],
            "APP_SHORT_NAME": app.config["APP_SHORT_NAME"],
            "APP_MOTTO": app.config["APP_MOTTO"],
            "APP_TAGLINE": app.config["APP_TAGLINE"],
            "APP_SUBTITLE": app.config["APP_SUBTITLE"],
            "POWERED_BY": app.config["POWERED_BY"],
            "APP_BRAND_INITIALS": app.config["APP_BRAND_INITIALS"],
            "APP_MEMBER_LABEL": app.config["APP_MEMBER_LABEL"],
            "APP_PRIMARY_COLOR": app.config["APP_PRIMARY_COLOR"],
            "APP_ACCENT_COLOR": app.config["APP_ACCENT_COLOR"],
            "ENABLE_DATING": app.config["ENABLE_DATING"],
            "NERD_HELP_PHONE": app.config["NERD_HELP_PHONE"],
            "NERD_HELP_WHATSAPP_URL": app.config["NERD_HELP_WHATSAPP_URL"],
            "unread_notifications": unread_count(current_user) if current_user else 0,
            "suggested_profiles": suggested_profiles,
            "recent_notifications": recent_notifications,
        }


def _register_template_globals(app):
    from app.models import score_label
    app.jinja_env.globals["score_label"] = score_label


def _configure_logging(app):
    if not app.debug and not app.testing:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)


def _ensure_database_schema(app):
    """Create any missing tables on startup.

    This exists so a fresh database (e.g. a brand-new Neon project) works
    immediately without requiring a separate `flask db upgrade` step from a
    machine with network access to the database — handy for serverless
    deploys where that extra step is easy to forget or hard to run.

    `db.create_all()` only issues CREATE TABLE for tables that don't already
    exist; it never touches or alters existing tables, so it's safe to run
    on every cold start and won't conflict with tables created by Alembic
    migrations. It does NOT replace migrations for schema *changes* to
    existing tables (adding/renaming a column, etc.) — use `flask db
    migrate`/`upgrade` for those, same as before.

    Set AUTO_CREATE_TABLES=false to disable this and rely solely on
    Alembic migrations.
    """
    if not app.config.get("AUTO_CREATE_TABLES", True):
        return
    if _running_flask_db_cli():
        # `flask db migrate`/`upgrade`/`init` etc. also import the app (Flask-Migrate
        # needs `current_app`), which would otherwise trigger auto-create *before*
        # Alembic runs -- silently creating tables outside Alembic's bookkeeping and
        # leaving it unable to tell what's actually been migrated. Skip auto-create
        # for these invocations so `flask db ...` always sees the database's true,
        # unmodified state.
        return
    try:
        with app.app_context():
            db.create_all()
            _seed_default_categories()
            _seed_initial_admin(app)
    except Exception as exc:  # pragma: no cover - depends on live DB reachability
        # Don't crash app startup over this -- a transient connection issue
        # here shouldn't take down the whole function; individual requests
        # will still surface a clear error if the database is genuinely
        # unreachable.
        app.logger.warning("Could not verify/create database tables on startup: %s", exc)


def _running_flask_db_cli():
    import sys
    # Works regardless of how the CLI was invoked (`flask db ...`,
    # `python -m flask db ...`, etc.) since argv[0]'s exact form varies,
    # but the "db" subcommand argument itself is a reliable signal.
    return "db" in sys.argv


def _seed_default_categories():
    """Populate the default business categories if the table is empty.

    Without this, a fresh database has a `business_categories` table (created
    by `_ensure_database_schema` above) with zero rows, so the business
    creation/edit form's category dropdown has nothing to select — the
    business form still validates a category as required, so members simply
    can't add a business until someone manually runs `flask init-categories`.
    Seeding here means a brand-new deploy works with no manual step.
    """
    from app.models import BusinessCategory, DEFAULT_CATEGORIES

    if BusinessCategory.query.first() is not None:
        return  # already seeded (or admin has customized the list) - leave it alone
    for name in DEFAULT_CATEGORIES:
        db.session.add(BusinessCategory(name=name))
    db.session.commit()


def _seed_initial_admin(app):
    """Create the first administrator account from environment variables,
    if one doesn't already exist.

    This is opt-in and does nothing unless BOTH ADMIN_INIT_EMAIL and
    ADMIN_INIT_PASSWORD are set (in .env locally, or in your Vercel/host's
    environment variables) -- there is no hardcoded default password
    anywhere. It's idempotent: once an account with that email exists, this
    is a no-op on every subsequent startup, so it never resets a password
    you've since changed. Prefer `flask create-admin` if you'd rather type
    the password interactively instead of putting it in an env var.
    """
    from app.models import User

    email = (app.config.get("ADMIN_INIT_EMAIL") or "").strip().lower()
    password = app.config.get("ADMIN_INIT_PASSWORD") or ""
    if not email or not password:
        return

    if User.query.filter_by(email=email).first() is not None:
        return  # already created (or a user already registered this email) -- leave it alone

    if len(password) < 8:
        app.logger.warning(
            "ADMIN_INIT_PASSWORD is set but shorter than 8 characters -- "
            "skipping automatic admin creation. Set a stronger password."
        )
        return

    admin = User(full_name=f"{app.config.get('APP_SHORT_NAME', 'Platform')} Administrator",
                 email=email, role="admin")
    admin.set_password(password)
    db.session.add(admin)
    db.session.flush()
    from app.models import Profile
    db.session.add(Profile(user_id=admin.id, status="approved"))
    db.session.commit()
    app.logger.info("Created initial administrator account for %s", email)
