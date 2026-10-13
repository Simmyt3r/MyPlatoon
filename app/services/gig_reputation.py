"""Conservative, non-official employer reputation from completed gigs.

No automated trust claim, payment verification or disclosure of worker
identities. Stars require distinct independent workers, consent and review.
"""
from app.models import Employer, GigDeal, GigReview, User, Profile

MIN_DISTINCT_WORKERS = 3
MIN_APPROVED_REVIEWS = 2
BAYESIAN_PRIOR_COUNT = 5
BAYESIAN_PRIOR_STARS = 3.5


def employer_reputation(employer):
    if employer.status != "approved" or not employer.owner.is_active:
        return None

    completed = (GigDeal.query.join(User, User.id == GigDeal.worker_id)
                 .join(Profile, Profile.user_id == User.id)
                 .filter(GigDeal.employer_id == employer.id,
                         GigDeal.status == "completed",
                         GigDeal.completed_at.isnot(None),
                         GigDeal.worker_id != employer.owner_user_id,
                         User.role == "member",
                         User.is_active_account.is_(True),
                         User.is_suspended.is_(False),
                         Profile.status == "approved").all())
    eligible = {d.id: d for d in completed}
    independent = {d.worker_id for d in completed}
    acknowledged = sum(d.payment_status == "confirmed_paid" for d in completed)

    # Moderation, worker's explicit permission and a completed two-party
    # deal are all mandatory. Distinct workers each get only ONE vote in
    # the public aggregate, preventing one worker's repeated gigs from
    # inflating the displayed score.
    candidates = (GigReview.query.join(GigDeal, GigReview.deal_id == GigDeal.id)
                  .filter(GigDeal.employer_id == employer.id,
                          GigReview.role == "worker",
                          GigReview.public_consent.is_(True),
                          GigReview.moderation_status == "approved")
                  .order_by(GigReview.created_at.desc(),
                            GigReview.id.desc()).all())
    chosen = []
    workers = set()
    for review in candidates:
        deal = eligible.get(review.deal_id)
        if deal is None or review.reviewer_id != deal.worker_id:
            continue
        if deal.worker_id in workers:
            continue
        workers.add(deal.worker_id)
        chosen.append(review)

    qualified = (len(independent) >= MIN_DISTINCT_WORKERS and
                 len(chosen) >= MIN_APPROVED_REVIEWS)
    score = (round((sum(r.stars for r in chosen) +
                    BAYESIAN_PRIOR_COUNT * BAYESIAN_PRIOR_STARS) /
                   (len(chosen) + BAYESIAN_PRIOR_COUNT), 1)
             if qualified else None)
    return {
        "qualified": qualified,
        "score": score,
        "completed_gigs": len(completed),
        "unique_workers": len(independent),
        "payment_acknowledgments": acknowledged,
        "public_reviews": len(chosen),
        "reviews": chosen[:20] if qualified else [],
        "minimum_workers": MIN_DISTINCT_WORKERS,
        "minimum_reviews": MIN_APPROVED_REVIEWS,
    }
