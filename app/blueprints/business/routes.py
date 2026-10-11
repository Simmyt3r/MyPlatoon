from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.forms.business_forms import BusinessForm
from app.models import Business, BusinessCategory
from app.services.cloudinary_service import upload_image, delete_image, ImageUploadError
from app.services.audit_service import log_action
from app.utils.urls import ensure_scheme

bp = Blueprint("business", __name__)

_TEXT_FIELDS = ("name", "description", "address", "phone", "whatsapp", "email")
_URL_FIELDS = ("website", "facebook", "instagram", "tiktok", "twitter_x")


def _category_choices():
    return [(c.id, c.name) for c in BusinessCategory.query.order_by(BusinessCategory.name).all()]


def _apply_form(business, form):
    for field in _TEXT_FIELDS:
        setattr(business, field, getattr(form, field).data)
    for field in _URL_FIELDS:
        setattr(business, field, ensure_scheme(getattr(form, field).data))
    business.category_id = form.category_id.data


@bp.route("/mine")
@login_required
def my_businesses():
    businesses = current_user.profile.businesses
    return render_template("profile/my_businesses.html", businesses=businesses)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = BusinessForm()
    form.category_id.choices = _category_choices()

    if form.validate_on_submit():
        business = Business(profile_id=current_user.profile.id)
        _apply_form(business, form)

        photo_error = None
        if form.logo.data:
            try:
                result = upload_image(form.logo.data, folder="platoon5/businesses")
                business.logo_url = result["url"]
                business.logo_public_id = result["public_id"]
            except ImageUploadError as exc:
                photo_error = str(exc)

        db.session.add(business)
        db.session.commit()
        log_action(current_user, "business.create", "Business", business.id)

        if photo_error:
            flash(photo_error, "warning")
        else:
            flash("Business added successfully.", "success")
        return redirect(url_for("business.my_businesses"))

    return render_template("profile/business_form.html", form=form, business=None)


def _get_owned_business_or_404(business_id):
    business = Business.query.get_or_404(business_id)
    if business.profile_id != current_user.profile.id and not current_user.is_admin:
        abort(403)
    return business


@bp.route("/<int:business_id>/edit", methods=["GET", "POST"])
@login_required
def edit(business_id):
    business = _get_owned_business_or_404(business_id)
    form = BusinessForm(obj=business)
    form.category_id.choices = _category_choices()
    if not form.is_submitted():
        form.category_id.data = business.category_id

    if form.validate_on_submit():
        _apply_form(business, form)

        photo_error = None
        if form.logo.data:
            try:
                result = upload_image(form.logo.data, folder="platoon5/businesses")
                old_public_id = business.logo_public_id
                business.logo_url = result["url"]
                business.logo_public_id = result["public_id"]
                if old_public_id:
                    delete_image(old_public_id)
            except ImageUploadError as exc:
                photo_error = str(exc)

        db.session.commit()
        log_action(current_user, "business.update", "Business", business.id)

        if photo_error:
            flash(photo_error, "warning")
        else:
            flash("Business updated successfully.", "success")
        return redirect(url_for("business.my_businesses"))

    return render_template("profile/business_form.html", form=form, business=business)


@bp.route("/<int:business_id>/delete", methods=["POST"])
@login_required
def delete(business_id):
    business = _get_owned_business_or_404(business_id)
    if business.logo_public_id:
        delete_image(business.logo_public_id)
    db.session.delete(business)
    db.session.commit()
    log_action(current_user, "business.delete", "Business", business_id)
    flash("Business removed.", "info")
    return redirect(url_for("business.my_businesses"))
