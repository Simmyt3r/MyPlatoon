import io

from flask import Blueprint, render_template, redirect, url_for, flash, send_file, current_app, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import AlbumVersion, Platoon
from app.services.album_service import (
    generate_new_album_version, latest_published_album, fetch_album_pdf_bytes, AlbumFetchError,
)
from app.services.audit_service import log_action

bp = Blueprint("album", __name__)


@bp.route("/")
@login_required
def view():
    own = current_user.profile
    platoon_id = own.platoon_id if own and own.status == "approved" else None
    latest = latest_published_album(platoon_id)
    history_query = AlbumVersion.query
    if not current_user.is_admin:
        if platoon_id is None:
            history_query = history_query.filter(AlbumVersion.id == -1)
        else:
            history_query = history_query.filter_by(platoon_id=platoon_id)
    history = history_query.order_by(AlbumVersion.generated_at.desc()).limit(10).all()
    platoons = Platoon.query.order_by(Platoon.state, Platoon.service_year.desc(),
                                      Platoon.batch, Platoon.stream, Platoon.number).all() if current_user.is_admin else []
    return render_template("album/view.html", latest=latest, history=history, platoons=platoons)


@bp.route("/generate", methods=["POST"])
@login_required
def generate():
    if not current_user.is_admin:
        flash("Only administrators can generate a new album version.", "danger")
        return redirect(url_for("album.view"))

    platoon_id = request.form.get("platoon_id", type=int)
    if not platoon_id or db.session.get(Platoon, platoon_id) is None:
        flash("Select the platoon to publish this album for.", "warning")
        return redirect(url_for("album.view"))
    version, pdf_bytes = generate_new_album_version(current_user, platoon_id)
    log_action(current_user, "album.generate", "AlbumVersion", version.id,
               detail=f"{version.member_count} members")
    flash(f"Album v{version.version_label} generated with {version.member_count} members.",
          "success")

    if not version.pdf_url and current_user.is_admin:
        # Purely informational -- the PDF itself is safely stored in the
        # database either way (version.pdf_data), so downloads work
        # regardless. This just means there's no secondary copy on
        # Cloudinary for e.g. sharing a link outside the app.
        flash("Note: no Cloudinary backup copy was created for this version "
              "(Cloudinary isn't configured, or the upload failed) -- this "
              "doesn't affect downloading it from here.", "info")

    return redirect(url_for("album.view"))


@bp.route("/download/<int:version_id>")
@login_required
def download(version_id):
    version = AlbumVersion.query.get_or_404(version_id)
    own = current_user.profile
    if not current_user.is_admin and not (
        version.platoon_id is not None and own and own.status == "approved"
        and own.platoon_id == version.platoon_id
    ):
        abort(403)  # legacy national albums are admin-only.

    if version.pdf_data:
        # Source of truth: served directly from the database, so this
        # never depends on Cloudinary being configured, reachable, or
        # willing to deliver PDF/raw files (see DEPLOYMENT.md) -- it's
        # always correct and always available.
        pdf_bytes = version.pdf_data
    elif version.pdf_url:
        # Fallback for album versions generated before pdf_data existed,
        # which only ever had a Cloudinary copy. Fetch and re-serve the
        # bytes ourselves (rather than redirecting the browser straight to
        # Cloudinary) so we control the Content-Type and filename
        # explicitly.
        try:
            pdf_bytes = fetch_album_pdf_bytes(version.pdf_url)
        except AlbumFetchError as exc:
            current_app.logger.error("Album PDF v%s fetch failed: %s", version.version_label, exc.admin_hint)
            if current_user.is_admin:
                flash(exc.admin_hint, "danger")
            else:
                flash("This album isn't available for download right now. "
                      "An administrator has been made aware.", "danger")
            return redirect(url_for("album.view"))
    else:
        flash("This album version is not available for download.", "danger")
        return redirect(url_for("album.view"))

    version.download_count += 1
    db.session.commit()
    log_action(current_user, "album.download", "AlbumVersion", version.id)

    return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf",
                      as_attachment=True,
                      download_name=f"myplatoon-{version.platoon_id or 'legacy'}-album-v{version.version_label}.pdf")
