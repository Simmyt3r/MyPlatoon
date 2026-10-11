from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.forms.admin_forms import RejectionForm, AnnouncementForm, CategoryForm
from app.models import User, Profile, Business, BusinessCategory, AlbumVersion, Announcement, AuditLog
from app.services.audit_service import log_action
from app.services.notification_service import notify

bp = Blueprint("admin", __name__)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@bp.route("/")
@login_required
@admin_required
def dashboard():
    stats = {
        "total_members": User.query.filter_by(role="member").count(),
        "approved_members": Profile.query.filter_by(status="approved").count(),
        "pending_approval": Profile.query.filter_by(status="pending").count(),
        "incomplete_profiles": Profile.query.filter_by(status="draft").count(),
        "registered_businesses": Business.query.count(),
        "album_downloads": sum(v.download_count for v in AlbumVersion.query.all()),
    }
    recent_registrations = User.query.filter_by(role="member").order_by(
        User.created_at.desc()).limit(5).all()
    pending_profiles = Profile.query.filter_by(status="pending").order_by(
        Profile.updated_at.desc()).limit(8).all()
    recent_updates = Profile.query.filter_by(status="approved").order_by(
        Profile.updated_at.desc()).limit(5).all()

    return render_template("admin/dashboard.html", stats=stats,
                            recent_registrations=recent_registrations,
                            pending_profiles=pending_profiles,
                            recent_updates=recent_updates)


@bp.route("/members")
@login_required
@admin_required
def members():
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Profile.query.join(Profile.user)
    if status:
        query = query.filter(Profile.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(User.full_name.ilike(like), User.email.ilike(like)))

    pagination = query.order_by(Profile.updated_at.desc()).paginate(
        page=page, per_page=20, error_out=False)

    return render_template("admin/members.html", pagination=pagination, status=status, q=q)


@bp.route("/members/<int:profile_id>")
@login_required
@admin_required
def member_detail(profile_id):
    profile = Profile.query.get_or_404(profile_id)
    reject_form = RejectionForm()
    return render_template("admin/member_detail.html", profile=profile, reject_form=reject_form)


@bp.route("/members/<int:profile_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_member(profile_id):
    profile = Profile.query.get_or_404(profile_id)
    profile.status = "approved"
    profile.rejection_reason = None
    profile.reviewed_by_id = current_user.id
    from datetime import datetime
    profile.reviewed_at = datetime.utcnow()
    db.session.commit()

    log_action(current_user, "profile.approve", "Profile", profile.id)
    notify(profile.user, f"Your {current_app.config['APP_SHORT_NAME']} profile has been approved!",
           category="success")
    flash(f"{profile.user.full_name}'s profile has been approved.", "success")
    return redirect(url_for("admin.member_detail", profile_id=profile.id))


@bp.route("/members/<int:profile_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_member(profile_id):
    profile = Profile.query.get_or_404(profile_id)
    form = RejectionForm()
    if form.validate_on_submit():
        from datetime import datetime
        profile.status = "rejected"
        profile.rejection_reason = form.reason.data
        profile.reviewed_by_id = current_user.id
        profile.reviewed_at = datetime.utcnow()
        db.session.commit()

        log_action(current_user, "profile.reject", "Profile", profile.id, detail=form.reason.data)
        notify(profile.user, f"Your profile was not approved: {form.reason.data}", category="warning")
        flash(f"{profile.user.full_name}'s profile has been rejected.", "info")
    else:
        flash("Please provide a rejection reason.", "danger")
    return redirect(url_for("admin.member_detail", profile_id=profile.id))


@bp.route("/members/<int:profile_id>/suspend", methods=["POST"])
@login_required
@admin_required
def suspend_member(profile_id):
    profile = Profile.query.get_or_404(profile_id)
    profile.status = "suspended"
    profile.user.is_suspended = True
    db.session.commit()
    log_action(current_user, "profile.suspend", "Profile", profile.id)
    notify(profile.user, "Your account has been suspended by an administrator.", category="danger")
    flash(f"{profile.user.full_name}'s account has been suspended.", "warning")
    return redirect(url_for("admin.member_detail", profile_id=profile.id))


@bp.route("/members/<int:profile_id>/reinstate", methods=["POST"])
@login_required
@admin_required
def reinstate_member(profile_id):
    profile = Profile.query.get_or_404(profile_id)
    profile.user.is_suspended = False
    profile.status = "approved" if profile.reviewed_at else "pending"
    db.session.commit()
    log_action(current_user, "profile.reinstate", "Profile", profile.id)
    notify(profile.user, "Your account has been reinstated.", category="success")
    flash(f"{profile.user.full_name}'s account has been reinstated.", "success")
    return redirect(url_for("admin.member_detail", profile_id=profile.id))


@bp.route("/members/<int:profile_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_member(profile_id):
    profile = Profile.query.get_or_404(profile_id)
    user = profile.user
    name = user.full_name
    log_action(current_user, "user.delete", "User", user.id, detail=f"deleted {name}")
    db.session.delete(user)  # cascades to profile + businesses
    db.session.commit()
    flash(f"{name}'s account has been permanently deleted.", "info")
    return redirect(url_for("admin.members"))


@bp.route("/categories", methods=["GET", "POST"])
@login_required
@admin_required
def categories():
    form = CategoryForm()
    if form.validate_on_submit():
        if BusinessCategory.query.filter_by(name=form.name.data.strip()).first():
            flash("That category already exists.", "warning")
        else:
            cat = BusinessCategory(name=form.name.data.strip())
            db.session.add(cat)
            db.session.commit()
            log_action(current_user, "category.create", "BusinessCategory", cat.id)
            flash("Category added.", "success")
        return redirect(url_for("admin.categories"))

    all_categories = BusinessCategory.query.order_by(BusinessCategory.name).all()
    return render_template("admin/categories.html", form=form, categories=all_categories)


@bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_category(category_id):
    category = BusinessCategory.query.get_or_404(category_id)
    if category.businesses:
        flash("Cannot delete a category that has businesses assigned to it.", "danger")
    else:
        db.session.delete(category)
        db.session.commit()
        log_action(current_user, "category.delete", "BusinessCategory", category_id)
        flash("Category deleted.", "info")
    return redirect(url_for("admin.categories"))


@bp.route("/announcements", methods=["GET", "POST"])
@login_required
@admin_required
def announcements():
    form = AnnouncementForm()
    if form.validate_on_submit():
        ann = Announcement(title=form.title.data.strip(), body=form.body.data.strip(),
                            created_by_id=current_user.id)
        db.session.add(ann)
        db.session.commit()
        log_action(current_user, "announcement.create", "Announcement", ann.id)
        flash("Announcement published.", "success")
        return redirect(url_for("admin.announcements"))

    all_announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("admin/announcements.html", form=form, announcements=all_announcements)


@bp.route("/announcements/<int:announcement_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_announcement(announcement_id):
    ann = Announcement.query.get_or_404(announcement_id)
    ann.is_active = not ann.is_active
    db.session.commit()
    log_action(current_user, "announcement.toggle", "Announcement", ann.id)
    return redirect(url_for("admin.announcements"))


@bp.route("/businesses")
@login_required
@admin_required
def businesses():
    page = request.args.get("page", 1, type=int)
    pagination = Business.query.order_by(Business.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)
    return render_template("admin/businesses.html", pagination=pagination)


@bp.route("/audit-logs")
@login_required
@admin_required
def audit_logs():
    page = request.args.get("page", 1, type=int)
    pagination = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=40, error_out=False)
    return render_template("admin/audit_logs.html", pagination=pagination)


@bp.route("/export/members.csv")
@login_required
@admin_required
def export_members_csv():
    import csv
    import io
    from flask import Response

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Full Name", "Email", "Status", "State", "LGA", "Profession",
                      "Phone", "WhatsApp", "Registered"])
    for profile in Profile.query.join(Profile.user).all():
        writer.writerow([
            profile.user.full_name, profile.user.email, profile.status,
            profile.state_of_origin or "", profile.lga or "", profile.profession or "",
            profile.phone_number or "", profile.whatsapp_number or "",
            profile.user.created_at.strftime("%Y-%m-%d"),
        ])
    log_action(current_user, "data.export", "Profile", None, detail="members.csv")
    return Response(output.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition": "attachment; filename=platoon5_members.csv"})


@bp.route("/dating")
@login_required
@admin_required
def dating_moderation():
    from app.models import DatingPersona
    reported = (DatingPersona.query.filter_by(is_reported=True)
                .order_by(DatingPersona.updated_at.desc()).all())
    return render_template("admin/dating.html", reported=reported)


@bp.route("/dating/<int:persona_id>/clear", methods=["POST"])
@login_required
@admin_required
def dating_clear_report(persona_id):
    from app.models import DatingPersona
    persona = DatingPersona.query.get_or_404(persona_id)
    persona.is_reported = False
    persona.report_reason = None
    db.session.commit()
    log_action(current_user, "dating.report_cleared", "DatingPersona", persona.id)
    flash("Report cleared -- this persona is visible in matching again.", "success")
    return redirect(url_for("admin.dating_moderation"))


@bp.route("/dating/<int:persona_id>/remove", methods=["POST"])
@login_required
@admin_required
def dating_remove_persona(persona_id):
    from app.models import DatingPersona
    persona = DatingPersona.query.get_or_404(persona_id)
    owner_name = persona.profile.user.full_name
    db.session.delete(persona)
    db.session.commit()
    log_action(current_user, "dating.persona_removed", "DatingPersona", persona_id,
               detail=f"removed persona belonging to {owner_name}")
    flash(f"Removed the dating persona belonging to {owner_name}.", "info")
    return redirect(url_for("admin.dating_moderation"))
