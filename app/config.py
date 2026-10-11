"""Environment-based application configuration.

Never hard-code secrets here. Everything sensitive is read from
environment variables (see .env.example).
"""
import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-not-secure-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
    # "Persistent login" -- once logged in, members stay logged in for a long
    # time (like a mobile app), not just the browser-session default. Login
    # defaults remember_me to True (see LoginForm) and marks the session
    # permanent, so both of these durations are what's actually in effect
    # for most visitors.
    PERMANENT_SESSION_LIFETIME = timedelta(days=365)
    REMEMBER_COOKIE_DURATION = timedelta(days=365)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"

    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5000")
    # Branding -- all overridable via environment variables so this codebase
    # can be deployed for a different group/organization with no code
    # changes. Defaults are intentionally generic (not NYSC/Platoon-specific).
    APP_NAME = os.environ.get("APP_NAME", "MyPlatoon")
    APP_SHORT_NAME = os.environ.get("APP_SHORT_NAME", "MyPlatoon")
    APP_MOTTO = os.environ.get("APP_MOTTO", "")
    APP_TAGLINE = os.environ.get("APP_TAGLINE", "Your NYSC journey. Your platoon. Your people.")
    APP_SUBTITLE = os.environ.get("APP_SUBTITLE", "For PCMs, serving corps members and alumni")
    POWERED_BY = os.environ.get("POWERED_BY", "")
    APP_BRAND_INITIALS = os.environ.get("APP_BRAND_INITIALS", "MP")  # falls back to APP_NAME initials in templates
    APP_MEMBER_LABEL = os.environ.get("APP_MEMBER_LABEL", "Member")
    APP_PRIMARY_COLOR = os.environ.get("APP_PRIMARY_COLOR", "#0b7a3b")
    APP_ACCENT_COLOR = os.environ.get("APP_ACCENT_COLOR", "#c79a2e")
    ENABLE_DATING = os.environ.get("ENABLE_DATING", "true").lower() != "false"

    # MyPlatoon independent help desk, NOT an official NERD/NYSC helpline.
    NERD_HELP_PHONE = os.environ.get("NERD_HELP_PHONE", "09039930006")
    NERD_HELP_WHATSAPP_URL = os.environ.get(
        "NERD_HELP_WHATSAPP_URL", "https://wa.me/2349039930006"
    )

    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")

    MAX_CONTENT_LENGTH = 6 * 1024 * 1024  # 6 MB hard cap on uploads
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
    ALLOWED_IMAGE_MIMETYPES = {"image/jpeg", "image/png", "image/webp"}

    MEMBERS_PER_PAGE = 12
    BUSINESSES_PER_PAGE = 12

    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = "200 per hour"

    ADMIN_INIT_EMAIL = os.environ.get("ADMIN_INIT_EMAIL")
    ADMIN_INIT_PASSWORD = os.environ.get("ADMIN_INIT_PASSWORD")

    # Auto-create missing tables on startup (see app/__init__.py::_ensure_database_schema).
    # Safe to leave on; only fills in tables that don't exist yet, never alters existing
    # ones. Set to "false" to rely solely on `flask db upgrade` migrations.
    AUTO_CREATE_TABLES = os.environ.get("AUTO_CREATE_TABLES", "true").lower() != "false"

    @staticmethod
    def _normalize_db_url(url: str) -> str:
        # Some providers (e.g. old Heroku-style URLs) use postgres:// which
        # SQLAlchemy 1.4+/2.x no longer accepts.
        if url and url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    # Set AIVEN_DATABASE_URL to switch this app to its dedicated Aiven database
    # without inadvertently using an old Neon DATABASE_URL on Vercel.
    SQLALCHEMY_DATABASE_URI = _normalize_db_url.__func__(
        os.environ.get("AIVEN_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "sqlite:///" + os.path.join(basedir, "dev.db")
    )


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config():
    env = os.environ.get("FLASK_ENV", "development")
    return CONFIG_MAP.get(env, DevelopmentConfig)
