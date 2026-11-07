"""Administrator-only recruitment pilot dashboard."""
from flask import abort, current_app, render_template
from flask_login import current_user, login_required

from app.services.recruitment_insights import recruitment_metrics, security_readiness


def register_insights_routes(bp):
    @bp.route("/insights")
    @login_required
    def insights():
        if not current_user.is_admin:
            abort(403)
        metrics = recruitment_metrics()
        security = security_readiness(current_app.config)
        response = render_template(
            "admin/insights.html", metrics=metrics, security=security,
        )
        return response, 200, {"Cache-Control": "private, no-store"}
