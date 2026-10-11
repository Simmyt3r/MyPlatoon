from flask import Blueprint, render_template, request, abort, current_app
from flask_login import current_user
from sqlalchemy import or_, and_

from app.models import Profile, Business, BusinessCategory, Skill, User
from app.services.privacy_service import can_view_full_profile, serialize_contact
from app.services.qr_service import generate_qr_data_uri, profile_public_url

bp = Blueprint("directory", __name__)


@bp.route("/members")
def members():
    query = Profile.query.filter_by(status="approved")

    q = request.args.get("q", "").strip()
    state = request.args.get("state", "").strip()
    profession = request.args.get("profession", "").strip()
    skill = request.args.get("skill", "").strip()
    page = request.args.get("page", 1, type=int)

    if q:
        like = f"%{q}%"
        query = query.join(Profile.user).filter(or_(
            Profile.profession.ilike(like),
            Profile.state_of_origin.ilike(like),
            Profile.lga.ilike(like),
            Profile.current_location.ilike(like),
            User.full_name.ilike(like),
        ))

    if state:
        query = query.filter(Profile.state_of_origin.ilike(f"%{state}%"))
    if profession:
        query = query.filter(Profile.profession.ilike(f"%{profession}%"))
    if skill:
        query = query.join(Profile.skills).filter(Skill.name.ilike(f"%{skill}%"))

    # Joining MyPlatoon does NOT give access to every cohort's private directory.
    if not (current_user.is_authenticated and current_user.is_admin):
        own = current_user.profile if current_user.is_authenticated else None
        if own is not None and own.status == "approved" and own.platoon_id:
            query = query.filter(or_(
                Profile.profile_visibility == "public",
                and_(Profile.profile_visibility == "platoon",
                     Profile.platoon_id == own.platoon_id),
            ))
        else:
            query = query.filter(Profile.profile_visibility == "public")

    pagination = query.order_by(Profile.updated_at.desc()).paginate(
        page=page, per_page=current_app.config["MEMBERS_PER_PAGE"], error_out=False)

    states = [s[0] for s in Profile.query.filter_by(status="approved")
              .with_entities(Profile.state_of_origin).distinct() if s[0]]

    return render_template("directory/members.html", pagination=pagination,
                            states=sorted(states), q=q, state=state,
                            profession=profession, skill=skill)


@bp.route("/member/<slug>")
def member_profile(slug):
    profile = Profile.query.filter_by(slug=slug).first_or_404()

    if not can_view_full_profile(profile):
        abort(404)  # do not confirm existence of private profiles to strangers

    contact = serialize_contact(profile)
    qr_data_uri = generate_qr_data_uri(profile_public_url(profile.slug))
    public_url = profile_public_url(profile.slug)

    return render_template("directory/member_profile.html", profile=profile,
                            contact=contact, qr_data_uri=qr_data_uri, public_url=public_url)


@bp.route("/businesses")
def businesses():
    query = (Business.query.filter_by(is_active=True)
             .join(Profile, Business.profile_id == Profile.id)
             .filter(Profile.status == "approved"))

    q = request.args.get("q", "").strip()
    category_id = request.args.get("category", type=int)
    state = request.args.get("state", "").strip()
    page = request.args.get("page", 1, type=int)

    if q:
        like = f"%{q}%"
        query = query.filter(or_(Business.name.ilike(like), Business.description.ilike(like)))
    if category_id:
        query = query.filter(Business.category_id == category_id)
    if state:
        query = query.filter(Profile.state_of_origin.ilike(f"%{state}%"))

    pagination = query.order_by(Business.name.asc()).paginate(
        page=page, per_page=current_app.config["BUSINESSES_PER_PAGE"], error_out=False)

    categories = BusinessCategory.query.order_by(BusinessCategory.name).all()

    return render_template("directory/businesses.html", pagination=pagination,
                            categories=categories, q=q, category_id=category_id, state=state)


@bp.route("/business/<int:business_id>")
def business_detail(business_id):
    business = Business.query.get_or_404(business_id)
    if not business.is_active or business.profile.status != "approved":
        abort(404)
    if not can_view_full_profile(business.profile):
        abort(404)
    return render_template("directory/business_detail.html", business=business)
