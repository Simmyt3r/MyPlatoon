from flask import Blueprint, render_template, redirect, url_for, request, jsonify, current_app
import json
from flask_login import login_required, current_user
from sqlalchemy import or_, and_

from app.extensions import db, limiter
from app.models import (
    Profile, Business, Announcement, Notification,
    AnnouncementReaction, AnnouncementComment, REACTION_TYPES,
)
from app.services.audit_service import log_action

bp = Blueprint("main", __name__)


def _wants_json():
    return request.headers.get("Accept", "").find("application/json") != -1 \
        or request.headers.get("X-Requested-With") == "fetch"


@bp.route("/")
def index():
    from app.models import Platoon
    member_count = Profile.query.filter_by(status="approved").count()
    business_count = Business.query.filter_by(is_active=True).count()
    platoon_count = Platoon.query.count()

    # Show only public or same-platoon profiles in the national activity strip.
    visible_query = Profile.query.filter_by(status="approved")
    own = current_user.profile if current_user.is_authenticated else None
    if current_user.is_authenticated and current_user.is_admin:
        visible_query = visible_query.filter(Profile.profile_visibility.in_(["public", "platoon"]))
    elif own and own.status == "approved" and own.platoon_id:
        visible_query = visible_query.filter(or_(
            Profile.profile_visibility == "public",
            and_(Profile.profile_visibility == "platoon",
                 Profile.platoon_id == own.platoon_id),
        ))
    else:
        visible_query = visible_query.filter(Profile.profile_visibility == "public")
    stories = (visible_query.filter(Profile.photo_url.isnot(None))
               .order_by(Profile.updated_at.desc()).limit(12).all())

    feed_announcements = (Announcement.query.filter_by(is_active=True)
                           .order_by(Announcement.created_at.desc()).limit(15).all())

    featured = (Profile.query.filter_by(status="approved")
                .filter(Profile.profile_visibility.in_(["public", "platoon"]))
                .order_by(Profile.updated_at.desc()).limit(6).all())

    return render_template("main/index.html", member_count=member_count,
                            business_count=business_count, stories=stories,
                            feed_announcements=feed_announcements, featured=featured,
                            reaction_types=REACTION_TYPES)


@bp.route("/nerd")
def nerd():
    """Public guidance to the official NERD process; not a NERD API proxy."""
    return render_template("main/nerd.html")


@bp.route("/platoons/guide")
def platoon_guide():
    return render_template("main/platoon_guide.html")


@bp.route("/about")
def about():
    return render_template("main/about.html")


@bp.route("/offline")
def offline():
    return render_template("main/offline.html")


@bp.route("/profile/<slug>")
def public_profile(slug):
    # Short, QR-friendly URL (shorter data = a less dense, more reliably
    # scannable QR code) that redirects to the canonical profile page. Kept
    # as a redirect rather than duplicating the view so there's exactly one
    # place that resolves privacy/visibility rules.
    return redirect(url_for("directory.member_profile", slug=slug))


@bp.route("/sw.js")
def service_worker():
    # Served directly by Vercel's static CDN from public/sw.js in production
    # (see vercel.json/public/); this route just makes the same file work
    # for local development and any non-Vercel host, from one source file.
    import os
    from flask import send_from_directory, current_app
    public_dir = os.path.join(current_app.root_path, "..", "public")
    return send_from_directory(public_dir, "sw.js", mimetype="application/javascript")


@bp.route("/manifest.webmanifest")
def web_manifest():
    # Dynamic so a deployer's branding (APP_NAME/APP_SHORT_NAME/theme colors
    # in .env) shows up correctly in the install prompt / home-screen icon,
    # without editing a static JSON file.
    cfg = current_app.config
    manifest = {
        "name": cfg["APP_NAME"],
        "short_name": cfg["APP_SHORT_NAME"],
        "description": f"{cfg['APP_NAME']} — {cfg['APP_SUBTITLE'] or cfg['APP_MOTTO'] or 'digital directory and album'}.",
        "start_url": "/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#f7f8f6",
        "theme_color": cfg["APP_PRIMARY_COLOR"],
        "icons": [
            {"src": url_for("static", filename="img/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": url_for("static", filename="img/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": url_for("static", filename="img/icon-512-maskable.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return current_app.response_class(
        response=json.dumps(manifest),
        mimetype="application/manifest+json",
    )


@bp.route("/search")
def search():
    q = request.args.get("q", "").strip()
    profiles, businesses = [], []
    if q:
        like = f"%{q}%"
        from app.models import User
        profiles_query = (
            Profile.query.filter_by(status="approved")
            .join(Profile.user)
            .filter(or_(User.full_name.ilike(like), Profile.profession.ilike(like),
                        Profile.state_of_origin.ilike(like)))
        )
        own = current_user.profile if current_user.is_authenticated else None
        if current_user.is_authenticated and current_user.is_admin:
            profiles_query = profiles_query.filter(
                Profile.profile_visibility.in_(["public", "platoon"]))
        elif own and own.status == "approved" and own.platoon_id:
            profiles_query = profiles_query.filter(or_(
                Profile.profile_visibility == "public",
                and_(Profile.profile_visibility == "platoon",
                     Profile.platoon_id == own.platoon_id),
            ))
        else:
            profiles_query = profiles_query.filter(Profile.profile_visibility == "public")
        profiles = profiles_query.limit(20).all()
        businesses = (Business.query.filter_by(is_active=True)
                      .join(Profile, Business.profile_id == Profile.id)
                      .filter(Profile.status == "approved")
                      .filter(or_(Business.name.ilike(like), Business.description.ilike(like)))
                      .limit(20).all())
    return render_template("main/search.html", q=q, profiles=profiles, businesses=businesses)


@bp.route("/feed/announcement/<int:announcement_id>/react", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def react_to_announcement(announcement_id):
    announcement = Announcement.query.get_or_404(announcement_id)
    reaction_type = request.form.get("reaction_type", "like")
    if reaction_type not in REACTION_TYPES:
        reaction_type = "like"

    existing = AnnouncementReaction.query.filter_by(
        announcement_id=announcement.id, user_id=current_user.id).first()

    if existing and existing.reaction_type == reaction_type:
        db.session.delete(existing)  # toggle off
        db.session.commit()
        state = "removed"
    elif existing:
        existing.reaction_type = reaction_type
        db.session.commit()
        state = "updated"
    else:
        db.session.add(AnnouncementReaction(announcement_id=announcement.id,
                                             user_id=current_user.id,
                                             reaction_type=reaction_type))
        db.session.commit()
        state = "added"

    if _wants_json():
        return jsonify({
            "state": state,
            "counts": announcement.reaction_counts(),
            "total": announcement.total_reactions(),
            "your_reaction": announcement.reaction_for(current_user),
        })
    return redirect(request.referrer or url_for("main.index"))


@bp.route("/feed/announcement/<int:announcement_id>/comment", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def comment_on_announcement(announcement_id):
    announcement = Announcement.query.get_or_404(announcement_id)
    body = (request.form.get("body") or "").strip()

    if body and len(body) <= 1000:
        comment = AnnouncementComment(announcement_id=announcement.id,
                                       user_id=current_user.id, body=body)
        db.session.add(comment)
        db.session.commit()
        log_action(current_user, "announcement.comment", "Announcement", announcement.id)

        if _wants_json():
            return jsonify({
                "ok": True,
                "comment": {
                    "author": current_user.full_name,
                    "body": comment.body,
                    "created_at": comment.created_at.strftime("%d %b, %H:%M"),
                },
                "comment_count": len(announcement.comments),
            })

    return redirect(request.referrer or url_for("main.index"))


@bp.route("/notifications")
@login_required
def notifications():
    items = (Notification.query.filter_by(user_id=current_user.id)
              .order_by(Notification.created_at.desc()).limit(50).all())
    unread_ids = [n.id for n in items if not n.is_read]
    if unread_ids:
        Notification.query.filter(Notification.id.in_(unread_ids)).update(
            {"is_read": True}, synchronize_session=False)
        db.session.commit()
    return render_template("main/notifications.html", notifications=items)
