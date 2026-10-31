"""Silabs Academy: curated courses, embedded YouTube lessons and certificates."""
import re
from datetime import datetime

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, send_file, url_for)
from flask_login import current_user, login_required
from sqlalchemy import func

from app.extensions import db, limiter
from app.models.learning import (
    LearningCertificate, LearningCourse, LearningLesson, LearningProgress,
)
from app.services.audit_service import log_action
from app.services.learning_service import (
    completed_lesson_ids, issue_certificate_if_complete, parse_youtube_id,
)

bp = Blueprint("learning", __name__)


def _admin():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


def _learner():
    if not current_user.is_active or current_user.role == "employer":
        abort(403)


def _field(name, max_length, *, required=True):
    value = (request.form.get(name) or "").strip()
    if (required and not value) or len(value) > max_length:
        raise ValueError(name.replace("_", " ").capitalize() + " is missing or too long.")
    return value


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:100]


@bp.route("/")
def catalog():
    courses = LearningCourse.query.filter_by(published=True).order_by(
        LearningCourse.created_at.desc(),
    ).all()
    done = {}
    certs = {}
    if current_user.is_authenticated and current_user.role != "employer":
        for course in courses:
            done[course.id] = len(completed_lesson_ids(current_user.id, course))
        certs = {
            certificate.course_id: certificate
            for certificate in LearningCertificate.query.filter_by(
                user_id=current_user.id,
            ).all()
        }
    return render_template("learning/catalog.html", courses=courses,
                           done=done, certs=certs)


@bp.route("/my-certificates")
@login_required
def my_certificates():
    _learner()
    certificates = LearningCertificate.query.filter_by(
        user_id=current_user.id,
    ).order_by(LearningCertificate.issued_at.desc()).all()
    return render_template("learning/my_certificates.html", certificates=certificates)


@bp.route("/courses/<slug>")
def course_detail(slug):
    course = LearningCourse.query.filter_by(slug=slug).first_or_404()
    if not course.published and not (
        current_user.is_authenticated and current_user.is_admin
    ):
        abort(404)
    done = set()
    certificate = None
    if current_user.is_authenticated and current_user.role != "employer":
        done = completed_lesson_ids(current_user.id, course)
        certificate = LearningCertificate.query.filter_by(
            user_id=current_user.id, course_id=course.id,
        ).first()
    return render_template("learning/course.html", course=course,
                           done=done, certificate=certificate)


@bp.route("/courses/<slug>/lessons/<int:lesson_id>")
@login_required
def lesson_detail(slug, lesson_id):
    _learner()
    course = LearningCourse.query.filter_by(slug=slug).first_or_404()
    if not course.published and not current_user.is_admin:
        abort(404)
    lesson = LearningLesson.query.filter_by(
        course_id=course.id, id=lesson_id,
    ).first_or_404()
    done = completed_lesson_ids(current_user.id, course)
    certificate = LearningCertificate.query.filter_by(
        user_id=current_user.id, course_id=course.id,
    ).first()
    return render_template("learning/lesson.html", course=course, lesson=lesson,
                           done=done, certificate=certificate)


@bp.route("/courses/<slug>/lessons/<int:lesson_id>/complete", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def complete_lesson(slug, lesson_id):
    _learner()
    course = LearningCourse.query.filter_by(slug=slug, published=True).first_or_404()
    lesson = LearningLesson.query.filter_by(
        course_id=course.id, id=lesson_id,
    ).first_or_404()
    progress = LearningProgress.query.filter_by(
        user_id=current_user.id, lesson_id=lesson.id,
    ).first()
    if progress is None:
        db.session.add(LearningProgress(
            user_id=current_user.id, lesson_id=lesson.id,
        ))
        db.session.commit()
    certificate = issue_certificate_if_complete(current_user, course)
    if certificate:
        flash("Course complete! Your Silabs certificate is ready.", "success")
        return redirect(url_for("learning.my_certificates"))
    flash("Lesson marked complete. Continue with the next lesson.", "success")
    index = next((i for i, part in enumerate(course.lessons)
                  if part.id == lesson.id), -1)
    if 0 <= index < len(course.lessons) - 1:
        return redirect(url_for(
            "learning.lesson_detail", slug=slug,
            lesson_id=course.lessons[index + 1].id,
        ))
    return redirect(url_for("learning.course_detail", slug=slug))


@bp.route("/certificates/<code>")
def verify_certificate(code):
    certificate = LearningCertificate.query.filter_by(code=code).first_or_404()
    response = render_template("learning/verify.html", certificate=certificate)
    return response


@bp.route("/certificates/<code>/download")
@login_required
def download_certificate(code):
    _learner()
    certificate = LearningCertificate.query.filter_by(code=code).first_or_404()
    if certificate.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    from app.services.learning_certificate import render_certificate
    pdf_buffer = render_certificate(certificate)
    response = send_file(
        pdf_buffer, mimetype="application/pdf", as_attachment=True,
        download_name="Silabs-Certificate-{}.pdf".format(
            certificate.code[:8].upper()),
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@bp.route("/admin")
@login_required
def admin_courses():
    _admin()
    courses = LearningCourse.query.order_by(LearningCourse.created_at.desc()).all()
    return render_template("learning/admin_courses.html", courses=courses)


@bp.route("/admin/courses/new", methods=["GET", "POST"])
@login_required
def admin_create_course():
    _admin()
    if request.method == "POST":
        try:
            title = _field("title", 180)
            slug = _slug(title)
            summary = _field("summary", 320)
            description = _field("description", 6000)
            level = _field("level", 24)
            if level not in ("Beginner", "Intermediate", "Advanced") or not slug:
                raise ValueError("Choose a valid level and course title.")
            if LearningCourse.query.filter_by(slug=slug).first():
                raise ValueError("This course title already exists.")
        except ValueError as exc:
            flash(str(exc), "danger")
        else:
            course = LearningCourse(
                title=title, slug=slug, summary=summary,
                description=description, level=level,
                created_by_id=current_user.id,
            )
            db.session.add(course)
            db.session.commit()
            log_action(current_user, "learning.course_created", "LearningCourse", course.id)
            flash("Draft course created. Add YouTube lessons before publishing.", "success")
            return redirect(url_for("learning.admin_edit_course", course_id=course.id))
    return render_template("learning/admin_edit_course.html", course=None)


@bp.route("/admin/courses/<int:course_id>", methods=["GET", "POST"])
@login_required
def admin_edit_course(course_id):
    _admin()
    course = db.get_or_404(LearningCourse, course_id)
    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "publish":
            if not course.lessons:
                flash("Add at least one YouTube lesson before publishing.", "warning")
            else:
                course.published = True
                db.session.commit()
                log_action(current_user, "learning.published", "LearningCourse", course.id)
                flash("Course published and visible to learners.", "success")
        elif action == "unpublish":
            course.published = False
            db.session.commit()
            log_action(current_user, "learning.unpublished", "LearningCourse", course.id)
            flash("Course hidden from new learners. Existing certificates remain valid.", "info")
        elif action == "save":
            try:
                title = _field("title", 180)
                summary = _field("summary", 320)
                description = _field("description", 6000)
                level = _field("level", 24)
                if level not in ("Beginner", "Intermediate", "Advanced"):
                    raise ValueError("Choose a valid course level.")
            except ValueError as exc:
                flash(str(exc), "danger")
            else:
                course.title, course.summary = title, summary
                course.description, course.level = description, level
                db.session.commit()
                log_action(current_user, "learning.course_updated", "LearningCourse", course.id)
                flash("Course details saved.", "success")
        else:
            abort(400)
        return redirect(url_for("learning.admin_edit_course", course_id=course.id))
    return render_template("learning/admin_edit_course.html", course=course)


@bp.route("/admin/courses/<int:course_id>/lessons", methods=["POST"])
@login_required
def admin_add_lesson(course_id):
    _admin()
    course = db.get_or_404(LearningCourse, course_id)
    if course.certificates:
        flash("Lessons are locked after certificates have been issued. Create a new course edition.", "warning")
        return redirect(url_for("learning.admin_edit_course", course_id=course.id))
    try:
        title = _field("lesson_title", 180)
        description = _field("lesson_description", 3000, required=False)
        video_id = parse_youtube_id(_field("youtube_url", 500))
        if not video_id:
            raise ValueError("Enter a valid HTTPS YouTube video link.")
    except ValueError as exc:
        flash(str(exc), "danger")
    else:
        last = db.session.query(func.max(LearningLesson.position)).filter_by(
            course_id=course.id).scalar() or 0
        lesson = LearningLesson(course_id=course.id, title=title,
                                description=description, youtube_id=video_id,
                                position=last + 1)
        db.session.add(lesson)
        db.session.commit()
        log_action(current_user, "learning.lesson_created", "LearningLesson", lesson.id)
        flash("YouTube lesson added to the course series.", "success")
    return redirect(url_for("learning.admin_edit_course", course_id=course.id))


@bp.route("/admin/courses/<int:course_id>/lessons/<int:lesson_id>", methods=["POST"])
@login_required
def admin_modify_lesson(course_id, lesson_id):
    _admin()
    course = db.get_or_404(LearningCourse, course_id)
    lesson = LearningLesson.query.filter_by(id=lesson_id, course_id=course.id).first_or_404()
    if course.certificates:
        flash("Lesson content is locked after certificates are issued.", "warning")
        return redirect(url_for("learning.admin_edit_course", course_id=course.id))
    action = request.form.get("action")
    if action == "delete":
        if course.published:
            flash("Unpublish the course before removing a lesson.", "warning")
        else:
            # Maintain a stable ordered series with no position gaps.
            position = lesson.position
            db.session.delete(lesson)
            db.session.flush()
            for row in course.lessons:
                if row.id != lesson_id and row.position > position:
                    row.position -= 1
            db.session.commit()
            log_action(current_user, "learning.lesson_deleted", "LearningCourse", course.id)
            flash("Lesson deleted.", "success")
    elif action == "edit":
        try:
            title = _field("lesson_title", 180)
            description = _field("lesson_description", 3000, required=False)
            video_id = parse_youtube_id(_field("youtube_url", 500))
            if not video_id:
                raise ValueError("Enter a valid HTTPS YouTube video link.")
        except ValueError as exc:
            flash(str(exc), "danger")
        else:
            lesson.title, lesson.description, lesson.youtube_id = title, description, video_id
            db.session.commit()
            log_action(current_user, "learning.lesson_updated", "LearningLesson", lesson.id)
            flash("Lesson saved.", "success")
    else:
        abort(400)
    return redirect(url_for("learning.admin_edit_course", course_id=course.id))
