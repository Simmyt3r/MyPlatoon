"""Centralized Flask extension instances.

Extensions are instantiated here (unbound) and initialized against the
app inside the application factory (app/__init__.py). This avoids
circular imports across blueprints/models.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)

login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access that page."
login_manager.login_message_category = "warning"
