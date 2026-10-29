from datetime import datetime
from urllib.parse import unquote, urlsplit

from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db, limiter
from app.forms.auth_forms import RegistrationForm, LoginForm
from app.models import User, Profile
from app.services.platoon_membership import assign_platoon
from app.services.audit_service import log_action
from app.services.notification_service import notify

bp = Blueprint("auth", __name__)


def _safe_next_path(target):
    """Permit only local absolute paths after login (never network-path URLs)."""
    if not target or not target.startswith("/"):
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in target):
        return False
    # Browsers normalize backslashes and some encoded slashes as separators.
    decoded = unquote(target)
    if decoded.startswith("//") or "\\" in decoded:
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("jobs.employer_dashboard" if current_user.role == "employer" else "profile.dashboard"))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            full_name=form.full_name.data.strip(),
            email=form.email.data.lower().strip(),
            role="member",
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()  # get user.id before creating the profile

        profile = Profile(user_id=user.id)
        assign_platoon(profile, form)
        db.session.add(profile)
        db.session.commit()

        log_action(user, "user.register", "User", user.id)
        notify(user, f"Welcome to {current_app.config['APP_SHORT_NAME']}! "
                     "Complete your profile to get started.")
        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("15 per 15 minutes")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("jobs.employer_dashboard" if current_user.role == "employer" else "profile.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()

        if user is None or not user.check_password(form.password.data):
            flash("Invalid email or password.", "danger")
            log_action(None, "auth.login_failed", "User", None,
                       detail=f"attempted email={form.email.data.lower().strip()}")
            return render_template("auth/login.html", form=form)

        if user.is_suspended:
            flash("This account has been suspended. Contact an administrator.", "danger")
            return render_template("auth/login.html", form=form)

        if user.role != "employer":
            from app.services.profile_service import ensure_profile
            ensure_profile(user)

        login_user(user, remember=form.remember_me.data)
        session.permanent = True
        user.last_login_at = datetime.utcnow()
        db.session.commit()
        log_action(user, "auth.login", "User", user.id)

        next_page = request.args.get("next")
        if not _safe_next_path(next_page):
            next_page = None
        return redirect(next_page or url_for("jobs.employer_dashboard" if user.role == "employer" else "profile.dashboard"))

    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    log_action(current_user, "auth.logout", "User", current_user.id)
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))
