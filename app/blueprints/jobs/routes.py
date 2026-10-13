"""Nationwide Jobs & Gigs board for verified employers and approved NYSC members.

The board is a voluntary employment marketplace. Organisations are separate
from corps-member identities. It never claims NYSC placement authority and
never collects recruitment/activation/application payments.
"""
from datetime import datetime, date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.extensions import db, limiter
from app.models import (
    Employer, JobListing, JobApplication, JobReport, User, Profile,
    EMPLOYER_KINDS, JOB_KINDS, WORK_MODES, PAY_UNITS, APP_STATUSES,
)
from app.models.platoon import NYSC_STATES
from app.forms.job_forms import (
    EmployerRegistrationForm, EmployerEditForm, JobForm,
    JobApplicationForm, JobReviewForm, JobPreferenceForm,
)
from app.services.audit_service import log_action
from app.services.notification_service import notify

bp = Blueprint("jobs", __name__)


def _employer():
    if not current_user.is_authenticated:
        return None
    return Employer.query.filter_by(owner_user_id=current_user.id).first()


def _needs_employer():
    employer = _employer()
    if employer is None:
        abort(403)
    return employer


def _admin():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


def _applicant_ok(job):
    user = current_user
    if not user.is_authenticated or not user.is_active or user.role != "member":
        return False
    profile = user.profile
    if job.employer.owner_user_id == user.id:
        return False  # A member who owns a hiring profile cannot hire themselves.
    return bool(profile and profile.status == "approved"
                and (not job.serving_only or profile.service_stage == "serving"))


def _listed_job(job):
    return job.is_open


def _copy_fields(form, record, names):
    for name in names:
        value = getattr(form, name).data
        if isinstance(value, str):
            value = value.strip()
        setattr(record, name, value)


EMPLOYER_FIELDS = ("name", "kind", "state", "lga", "address",
                   "description", "contact_email", "contact_phone", "website")
JOB_FIELDS = ("title", "job_kind", "work_mode", "state", "lga",
              "location_description", "description", "requirements",
              "hours_per_week", "schedule_notes", "pay_min", "pay_max",
              "pay_unit", "closing_date", "serving_only")


@bp.route("/")
def index():
    """Public vacancies only: reviewed employer + published unexpired listing."""
    today = date.today()
    query = (JobListing.query.join(Employer)
             .join(User, Employer.owner_user_id == User.id)
             .filter(JobListing.status == "published",
                     Employer.status == "approved",
                     JobListing.closing_date >= today,
                     User.is_active_account.is_(True),
                     User.is_suspended.is_(False)))
    q = request.args.get("q", "").strip()[:90]
    state = request.args.get("state", "")
    kind = request.args.get("kind", "")
    mode = request.args.get("mode", "")
    serving = request.args.get("serving") == "1"
    if q:
        query = query.filter(or_(
            JobListing.title.ilike(f"%{q}%"),
            JobListing.description.ilike(f"%{q}%"),
            Employer.name.ilike(f"%{q}%"),
        ))
    if state in NYSC_STATES:
        query = query.filter(JobListing.state == state)
    else:
        state = ""
    if kind in dict(JOB_KINDS):
        query = query.filter(JobListing.job_kind == kind)
    else:
        kind = ""
    if mode in dict(WORK_MODES):
        query = query.filter(JobListing.work_mode == mode)
    else:
        mode = ""
    if serving:
        query = query.filter(JobListing.job_kind.in_(("gig", "part_time")))
    page = max(1, request.args.get("page", 1, type=int))
    pagination = query.order_by(JobListing.created_at.desc()).paginate(
        page=page, per_page=12, error_out=False)
    return render_template("jobs/index.html", pagination=pagination, q=q,
        state=state, kind=kind, mode=mode, serving=serving,
        states=NYSC_STATES, kinds=JOB_KINDS, modes=WORK_MODES)


@bp.route("/<int:job_id>")
def detail(job_id):
    job = JobListing.query.get_or_404(job_id)
    employer = _employer()
    owner = employer is not None and employer.id == job.employer_id
    if not _listed_job(job) and not (owner or
            (current_user.is_authenticated and current_user.is_admin)):
        abort(404)
    already = (JobApplication.query.filter_by(
        job_id=job.id, applicant_user_id=current_user.id).first()
        if current_user.is_authenticated else None)
    return render_template("jobs/detail.html", job=job, owner=owner,
        can_apply=_applicant_ok(job) and job.is_open and already is None,
        already=already)


@bp.route("/employers/register", methods=["GET", "POST"])
@limiter.limit("8 per hour")
def employer_register():
    """Dedicated employer account, without pretending to have an NYSC camp."""
    if current_user.is_authenticated:
        if _employer() is not None:
            return redirect(url_for("jobs.employer_dashboard"))
        return redirect(url_for("jobs.employer_claim"))
    form = EmployerRegistrationForm()
    if form.validate_on_submit():
        owner = User(full_name=form.full_name.data.strip(),
                     email=form.email.data.strip().lower(), role="employer")
        owner.set_password(form.password.data)
        db.session.add(owner)
        db.session.flush()
        employer = Employer(owner_user_id=owner.id)
        _copy_fields(form, employer, EMPLOYER_FIELDS)
        db.session.add(employer)
        db.session.commit()
        log_action(owner, "jobs.employer_register", "Employer", employer.id)
        flash("Organisation registered. Sign in to track admin review. No recruitment fees are charged.", "success")
        return redirect(url_for("auth.login"))
    return render_template("jobs/employer_form.html", form=form,
                           registering=True, employer=None)


@bp.route("/employers/claim", methods=["GET", "POST"])
@login_required
@limiter.limit("8 per hour")
def employer_claim():
    """Allow an existing member/business owner to also operate one organisation."""
    if _employer():
        return redirect(url_for("jobs.employer_dashboard"))
    form = EmployerEditForm()
    if form.validate_on_submit():
        employer = Employer(owner_user_id=current_user.id)
        _copy_fields(form, employer, EMPLOYER_FIELDS)
        db.session.add(employer)
        db.session.commit()
        log_action(current_user, "jobs.employer_register", "Employer", employer.id)
        flash("Organisation submitted for review. You can continue using your member account.", "success")
        return redirect(url_for("jobs.employer_dashboard"))
    return render_template("jobs/employer_form.html", form=form,
                           registering=False, employer=None)


@bp.route("/employer")
@login_required
def employer_dashboard():
    employer = _employer()
    if employer is None:
        return redirect(url_for("jobs.employer_claim"))
    listings = (JobListing.query.filter_by(employer_id=employer.id)
                .order_by(JobListing.created_at.desc()).all())
    return render_template("jobs/employer_dashboard.html",
                           employer=employer, listings=listings)


@bp.route("/employer/edit", methods=["GET", "POST"])
@login_required
def employer_edit():
    employer = _needs_employer()
    form = EmployerEditForm(obj=employer)
    if form.validate_on_submit():
        _copy_fields(form, employer, EMPLOYER_FIELDS)
        employer.status = "pending"
        employer.reviewer_id = None
        employer.reviewed_at = None
        employer.review_note = None
        db.session.commit()
        log_action(current_user, "jobs.employer_edit", "Employer", employer.id)
        flash("Changes saved. Your organisation must be reviewed again before its jobs are public.", "info")
        return redirect(url_for("jobs.employer_dashboard"))
    return render_template("jobs/employer_form.html", form=form,
                           registering=False, employer=employer)


@bp.route("/new", methods=["GET", "POST"])
@login_required
@limiter.limit("15 per hour", methods=["POST"])
def create():
    employer = _needs_employer()
    form = JobForm()
    if request.method == "GET":
        form.state.data = employer.state
    if form.validate_on_submit():
        job = JobListing(employer_id=employer.id)
        _copy_fields(form, job, JOB_FIELDS)
        db.session.add(job)
        db.session.commit()
        log_action(current_user, "jobs.post", "JobListing", job.id)
        flash("Vacancy submitted for admin review. It is not public yet.", "success")
        return redirect(url_for("jobs.employer_dashboard"))
    return render_template("jobs/form.html", form=form, job=None, employer=employer)


@bp.route("/<int:job_id>/edit", methods=["GET", "POST"])
@login_required
def edit(job_id):
    employer = _needs_employer()
    job = JobListing.query.get_or_404(job_id)
    if job.employer_id != employer.id:
        abort(403)
    if job.status == "closed":
        abort(403)
    form = JobForm(obj=job)
    if form.validate_on_submit():
        _copy_fields(form, job, JOB_FIELDS)
        job.status = "pending"
        job.reviewer_id = None
        job.reviewed_at = None
        job.review_note = None
        db.session.commit()
        log_action(current_user, "jobs.edit", "JobListing", job.id)
        flash("Edits saved. Your listing is hidden until reviewed again.", "info")
        return redirect(url_for("jobs.employer_dashboard"))
    return render_template("jobs/form.html", form=form, job=job, employer=employer)


@bp.route("/<int:job_id>/close", methods=["POST"])
@login_required
def close(job_id):
    employer = _needs_employer()
    job = JobListing.query.get_or_404(job_id)
    if job.employer_id != employer.id:
        abort(403)
    job.status = "closed"
    db.session.commit()
    log_action(current_user, "jobs.close", "JobListing", job.id)
    flash("Listing closed to new applications.", "success")
    return redirect(url_for("jobs.employer_dashboard"))


@bp.route("/<int:job_id>/apply", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per hour", methods=["POST"])
def apply(job_id):
    job = JobListing.query.get_or_404(job_id)
    if not job.is_open:
        abort(404)
    if not _applicant_ok(job):
        flash("To apply, complete your member profile and get it approved. Some roles are for serving corps members only.", "warning")
        return redirect(url_for("jobs.detail", job_id=job.id))
    if JobApplication.query.filter_by(
            job_id=job.id, applicant_user_id=current_user.id).first():
        flash("You have already applied to this opportunity.", "info")
        return redirect(url_for("jobs.my_applications"))
    form = JobApplicationForm()
    if request.method == "GET":
        form.contact_email.data = current_user.email
    if form.validate_on_submit():
        application = JobApplication(
            job_id=job.id, applicant_user_id=current_user.id,
            cover_note=form.cover_note.data.strip(),
            contact_email=form.contact_email.data.strip().lower(),
            contact_phone=(form.contact_phone.data or "").strip() or None,
        )
        db.session.add(application)
        db.session.commit()
        log_action(current_user, "jobs.apply", "JobApplication", application.id)
        notify(job.employer.owner,
               "A new application was submitted for your job: " + job.title,
               category="info")
        flash("Application sent. The employer can see only the contact details you chose to share.", "success")
        return redirect(url_for("jobs.my_applications"))
    return render_template("jobs/apply.html", form=form, job=job)


@bp.route("/my-applications")
@login_required
def my_applications():
    if current_user.role != "member":
        abort(403)
    rows = JobApplication.query.filter_by(
        applicant_user_id=current_user.id).order_by(
        JobApplication.created_at.desc()).all()
    return render_template("jobs/my_applications.html", applications=rows)


@bp.route("/<int:job_id>/applications")
@login_required
def employer_applications(job_id):
    employer = _needs_employer()
    job = JobListing.query.get_or_404(job_id)
    if job.employer_id != employer.id:
        abort(403)
    rows = JobApplication.query.filter_by(job_id=job.id).order_by(
        JobApplication.created_at.desc()).all()
    return render_template("jobs/applicants.html", applications=rows, job=job)


@bp.route("/applications/<int:application_id>/status", methods=["POST"])
@login_required
def application_status(application_id):
    employer = _needs_employer()
    application = JobApplication.query.get_or_404(application_id)
    if application.listing.employer_id != employer.id:
        abort(403)
    status = request.form.get("status", "")
    if status not in APP_STATUSES:
        abort(400)
    if application.gig_deal is not None:
        # Accepted terms, hiring and deal closure belong to the worker-
        # consented gig workflow, not a unilateral application dropdown.
        abort(409)
    if application.listing.job_kind == "gig" and status == "hired":
        flash("Send a formal gig offer. Only the worker can accept it.", "warning")
        return redirect(url_for("jobs.employer_applications", job_id=application.job_id))
    application.status = status
    db.session.commit()
    log_action(current_user, "jobs.application_status", "JobApplication", application.id)
    notify(application.applicant,
           "Your application for {} was updated: {}.".format(
               application.listing.title, status), category="info")
    flash("Applicant status updated.", "success")
    return redirect(url_for("jobs.employer_applications", job_id=application.job_id))


@bp.route("/admin/employers")
@login_required
def admin_employers():
    _admin()
    records = Employer.query.filter_by(status="pending").order_by(
        Employer.created_at.asc()).limit(100).all()
    return render_template("jobs/admin_employers.html", employers=records)


@bp.route("/admin/employers/<int:employer_id>/review", methods=["POST"])
@login_required
def review_employer(employer_id):
    _admin()
    employer = Employer.query.get_or_404(employer_id)
    if employer.status not in ("pending", "approved", "rejected"):
        abort(403)
    decision = request.form.get("decision")
    if decision not in ("approved", "rejected", "suspended"):
        abort(400)
    note = request.form.get("note", "").strip()[:500]
    if decision in ("rejected", "suspended") and len(note) < 10:
        flash("Provide at least 10 characters explaining rejection or suspension.", "warning")
        return redirect(url_for("jobs.admin_employers"))
    employer.status = decision
    employer.review_note = note or None
    employer.reviewer_id = current_user.id
    employer.reviewed_at = datetime.utcnow()
    db.session.commit()
    log_action(current_user, "jobs.employer_" + decision, "Employer", employer.id)
    notify(employer.owner, "Organisation review status: {}.".format(decision),
           category="info")
    return redirect(url_for("jobs.admin_employers"))


@bp.route("/admin/listings")
@login_required
def admin_listings():
    _admin()
    listings = JobListing.query.filter_by(status="pending").order_by(
        JobListing.created_at.asc()).limit(100).all()
    return render_template("jobs/admin_listings.html", listings=listings)


@bp.route("/admin/listings/<int:job_id>/review", methods=["POST"])
@login_required
def review_listing(job_id):
    _admin()
    job = JobListing.query.get_or_404(job_id)
    if job.status not in ("pending", "published", "rejected"):
        abort(403)
    decision = request.form.get("decision")
    if decision not in ("published", "rejected", "closed"):
        abort(400)
    note = request.form.get("note", "").strip()[:500]
    if decision in ("rejected", "closed") and len(note) < 10:
        flash("Provide at least 10 characters explaining rejection or closure.", "warning")
        return redirect(url_for("jobs.admin_listings"))
    if decision == "published" and (job.employer.status != "approved"
                                    or job.closing_date < date.today()):
        flash("Approve the organisation and confirm that the deadline has not passed.", "warning")
        return redirect(url_for("jobs.admin_listings"))
    job.status = decision
    job.review_note = note or None
    job.reviewer_id = current_user.id
    job.reviewed_at = datetime.utcnow()
    db.session.commit()
    log_action(current_user, "jobs.listing_" + decision, "JobListing", job.id)
    notify(job.employer.owner, "Listing {}: {}.".format(job.title, decision),
           category="info")
    if decision == "published":
        from app.services.job_discovery import dispatch_job_alerts
        dispatch_job_alerts(job)
    return redirect(url_for("jobs.admin_listings"))



@bp.route("/<int:job_id>/report", methods=["GET", "POST"])
@login_required
@limiter.limit("5 per day", methods=["POST"])
def report_job(job_id):
    """A member may flag a suspicious paid vacancy without contacting its owner."""
    from app.forms.job_forms import JobReportForm
    from app.models import JobReport
    job = JobListing.query.get_or_404(job_id)
    if current_user.role != "member" or not current_user.is_active:
        abort(403)
    # Permit an applicant to report a listing even if closed since applying.
    applicant = JobApplication.query.filter_by(
        job_id=job_id, applicant_user_id=current_user.id).first()
    if not job.is_open and applicant is None:
        abort(404)
    previous = JobReport.query.filter_by(
        job_id=job_id, reporter_id=current_user.id).first()
    if previous:
        flash("Your report is already in the moderation queue.", "info")
        return redirect(url_for("jobs.index"))
    form = JobReportForm()
    if form.validate_on_submit():
        report = JobReport(job_id=job_id, reporter_id=current_user.id,
                           reason=form.reason.data.strip())
        db.session.add(report)
        db.session.commit()
        log_action(current_user, "jobs.report", "JobReport", report.id)
        for admin in User.query.filter_by(role="admin").all():
            notify(admin, "A job or gig listing requires fraud/safety review.",
                   category="warning")
        flash("Your report has been sent confidentially for review.", "success")
        return redirect(url_for("jobs.index"))
    return render_template("jobs/report.html", form=form, job=job)


@bp.route("/admin/reports")
@login_required
def admin_reports():
    _admin()
    reports = (JobReport.query.filter_by(status="pending")
               .order_by(JobReport.created_at.asc()).limit(100).all())
    return render_template("jobs/admin_reports.html", reports=reports)


@bp.route("/admin/reports/<int:report_id>/review", methods=["POST"])
@login_required
def review_report(report_id):
    _admin()
    from app.models import JobReport
    report = JobReport.query.get_or_404(report_id)
    if report.status != "pending":
        abort(403)
    decision = request.form.get("decision")
    if decision not in ("dismissed", "actioned"):
        abort(400)
    if decision == "actioned":
        report.listing.status = "closed"
    report.status = decision
    report.reviewed_at = datetime.utcnow()
    report.reviewed_by_id = current_user.id
    db.session.commit()
    log_action(current_user, "jobs.report_" + decision, "JobReport", report.id)
    if decision == "actioned":
        notify(report.listing.employer.owner,
               "Your job listing '{}' was closed after a safety review.".format(
                   report.listing.title), category="warning")
    flash("Report reviewed.", "success")
    return redirect(url_for("jobs.admin_reports"))



@bp.route("/for-me")
@login_required
def for_me():
    """Personal suggestions based on opt-in preferences and recorded NYSC camp state."""
    from app.services.job_discovery import recommended_jobs, member_eligible, service_state
    from app.models import JobAlertPreference, SavedJob
    if current_user.role != "member":
        return redirect(url_for("jobs.employer_dashboard"))
    if not member_eligible(current_user):
        flash("An approved MyPlatoon member profile is needed for personalised suggestions.", "warning")
        return redirect(url_for("jobs.index"))
    results = recommended_jobs(current_user)
    saved = {row.job_id for row in SavedJob.query.filter_by(user_id=current_user.id).all()}
    pref = JobAlertPreference.query.filter_by(user_id=current_user.id).first()
    return render_template("jobs/for_me.html", results=results,
                           saved_ids=saved, preference=pref,
                           posting_state=service_state(current_user.profile))


@bp.route("/saved")
@login_required
def saved():
    from app.models import SavedJob
    if current_user.role != "member":
        abort(403)
    records = (SavedJob.query.filter_by(user_id=current_user.id)
               .order_by(SavedJob.created_at.desc()).all())
    return render_template("jobs/saved.html", records=records)


@bp.route("/<int:job_id>/save", methods=["POST"])
@login_required
@limiter.limit("40 per hour")
def save(job_id):
    from app.models import SavedJob
    if current_user.role != "member" or not current_user.is_active:
        abort(403)
    job = JobListing.query.get_or_404(job_id)
    if not job.is_open:
        abort(404)
    if not SavedJob.query.filter_by(user_id=current_user.id, job_id=job_id).first():
        db.session.add(SavedJob(user_id=current_user.id, job_id=job_id))
        db.session.commit()
    flash("Job saved privately to your list.", "success")
    return redirect(url_for("jobs.detail", job_id=job_id))


@bp.route("/<int:job_id>/unsave", methods=["POST"])
@login_required
@limiter.limit("40 per hour")
def unsave(job_id):
    from app.models import SavedJob
    if current_user.role != "member":
        abort(403)
    entry = SavedJob.query.filter_by(user_id=current_user.id, job_id=job_id).first()
    if entry is not None:
        db.session.delete(entry)
        db.session.commit()
    flash("Removed from your saved opportunities.", "info")
    return redirect(url_for("jobs.saved"))


@bp.route("/preferences", methods=["GET", "POST"])
@login_required
def preferences():
    from app.models import JobAlertPreference
    if current_user.role != "member":
        abort(403)
    record = JobAlertPreference.query.filter_by(user_id=current_user.id).first()
    form = JobPreferenceForm()
    if request.method == "GET" and record:
        form.preferred_state.data = record.preferred_state or ""
        form.preferred_kinds.data = [item for item in record.preferred_kinds.split(",") if item]
        form.available_hours.data = record.available_hours
        form.remote_ok.data = record.remote_ok
        form.enabled.data = record.enabled
    elif request.method == "GET":
        form.preferred_kinds.data = ["gig", "part_time"]
        form.enabled.data = False
    if form.validate_on_submit():
        if record is None:
            record = JobAlertPreference(user_id=current_user.id)
            db.session.add(record)
        record.preferred_state = form.preferred_state.data or None
        record.preferred_kinds = ",".join(form.preferred_kinds.data or [])
        record.available_hours = form.available_hours.data
        record.remote_ok = bool(form.remote_ok.data)
        # Only requested, approved members receive in-app alerts.
        record.enabled = bool(form.enabled.data)
        db.session.commit()
        log_action(current_user, "jobs.preferences", "JobAlertPreference", record.id)
        flash("Preferences updated. New-job alerts are {}.".format(
            "on" if record.enabled else "off"), "success")
        return redirect(url_for("jobs.for_me"))
    return render_template("jobs/preferences.html", form=form, record=record)



# ---------------------------------------------------------------------------
# Gig owner onboarding: a short route through the existing reviewed
# employer + job workflow, not a second unmoderated marketplace.
# ---------------------------------------------------------------------------


def _gig_owner_form_labels(form):
    """Make the existing, validated employer fields approachable to
    individual gig owners without weakening identity-review requirements.
    """
    form.kind.label.text = "Who is hiring?"
    form.name.label.text = "Gig owner or organisation name"
    form.address.label.text = "Operating address (for verification only)"
    form.description.label.text = "Describe your work or organisation"
    form.contact_email.label.text = "Recruiting contact email"


@bp.route("/gig-owners")
def gig_owners():
    """Public explanation and entry point for individuals and organisations."""
    return render_template("jobs/gig_owners.html")


@bp.route("/gig-owners/register", methods=["GET", "POST"])
@limiter.limit("6 per hour", methods=["POST"])
def gig_owner_register():
    """Create a genuine employer-only account; no invented NYSC profile."""
    from flask_login import login_user
    from app.forms.job_forms import GigOwnerRegistrationForm

    if current_user.is_authenticated:
        return redirect(url_for(
            "jobs.gig_owner_dashboard" if _employer() else "jobs.gig_owner_claim"
        ))
    form = GigOwnerRegistrationForm()
    _gig_owner_form_labels(form)
    if form.validate_on_submit():
        owner = User(
            full_name=form.full_name.data.strip(),
            email=form.email.data.strip().lower(),
            role="employer",
        )
        owner.set_password(form.password.data)
        db.session.add(owner)
        db.session.flush()
        employer = Employer(owner_user_id=owner.id)
        _copy_fields(form, employer, EMPLOYER_FIELDS)
        db.session.add(employer)
        db.session.commit()
        log_action(owner, "jobs.gig_owner_registered", "Employer", employer.id)
        # The organisation is pending; logging in does not grant approval.
        login_user(owner)
        flash("Gig owner profile created. Add your first paid gig; your profile and gig must both be approved before publication.", "success")
        return redirect(url_for("jobs.create_gig"))
    return render_template(
        "jobs/gig_owner_register.html", form=form, existing_member=False,
    )


@bp.route("/gig-owners/claim", methods=["GET", "POST"])
@login_required
@limiter.limit("6 per hour", methods=["POST"])
def gig_owner_claim():
    """Let existing corps members post gigs without losing their NYSC identity."""
    from app.forms.job_forms import GigOwnerClaimForm

    if _employer() is not None:
        return redirect(url_for("jobs.gig_owner_dashboard"))
    form = GigOwnerClaimForm()
    _gig_owner_form_labels(form)
    if request.method == "GET":
        form.contact_email.data = current_user.email
    if form.validate_on_submit():
        employer = Employer(owner_user_id=current_user.id)
        _copy_fields(form, employer, EMPLOYER_FIELDS)
        db.session.add(employer)
        db.session.commit()
        log_action(current_user, "jobs.gig_owner_registered", "Employer", employer.id)
        flash("Gig owner profile submitted. Add your first paid gig while we review your profile.", "success")
        return redirect(url_for("jobs.create_gig"))
    return render_template(
        "jobs/gig_owner_register.html", form=form, existing_member=True,
    )


@bp.route("/gig-owners/dashboard")
@login_required
def gig_owner_dashboard():
    employer = _employer()
    if employer is None:
        return redirect(url_for("jobs.gig_owner_claim"))
    listings = (JobListing.query.filter_by(employer_id=employer.id)
                .order_by(JobListing.created_at.desc()).all())
    return render_template("jobs/gig_owner_dashboard.html",
                           employer=employer, listings=listings)


@bp.route("/gigs/new", methods=["GET", "POST"])
@login_required
@limiter.limit("15 per hour", methods=["POST"])
def create_gig():
    """Publish request, not instant publication. Moderators approve each gig."""
    from app.forms.job_forms import GigPostingForm

    employer = _employer()
    if employer is None:
        return redirect(url_for("jobs.gig_owner_claim"))
    if employer.status in ("rejected", "suspended"):
        flash("Your employer profile must be reviewed before you can submit more gigs.", "warning")
        return redirect(url_for("jobs.gig_owner_dashboard"))
    form = GigPostingForm()
    if request.method == "GET":
        form.state.data = employer.state
        form.lga.data = employer.lga
    if form.validate_on_submit():
        gig = JobListing(
            employer_id=employer.id,
            title=form.title.data.strip(),
            job_kind="gig",  # cannot be submitted as an unrelated listing type
            work_mode=form.work_mode.data,
            state=form.state.data,
            lga=(form.lga.data or "").strip() or None,
            location_description=(form.location_description.data or "").strip() or None,
            description=form.description.data.strip(),
            requirements=form.requirements.data.strip(),
            hours_per_week=form.hours_per_week.data,
            schedule_notes=form.schedule_notes.data.strip(),
            pay_min=form.pay_amount.data,
            pay_max=form.pay_amount.data,
            pay_unit=form.pay_unit.data,
            closing_date=form.closing_date.data,
            serving_only=bool(form.serving_only.data),
            status="pending",
        )
        db.session.add(gig)
        db.session.commit()
        log_action(current_user, "jobs.gig_submitted", "JobListing", gig.id)
        flash("Your gig has been submitted for publication. It will become visible only when both your profile and listing are approved.", "success")
        return redirect(url_for("jobs.gig_owner_dashboard"))
    return render_template("jobs/gig_post.html", form=form, employer=employer)


@bp.route("/employers/<int:employer_id>/reputation")
def employer_reputation(employer_id):
    """Public employer-only history, never applicant or private worker data."""
    from app.services.gig_reputation import employer_reputation as get_reputation
    employer = Employer.query.get_or_404(employer_id)
    stats = get_reputation(employer)
    if stats is None:
        abort(404)
    return render_template("jobs/employer_reputation.html",
                           employer=employer, stats=stats)
