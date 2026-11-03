"""Blueprint routes for NYSC-inspired quarterly interplatoon competitions."""
from datetime import datetime, timedelta

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db, limiter
from app.models import Platoon
from app.models.platoon_games import (
    PlatoonGameResult, PlatoonLeaderCandidate, PlatoonLeaderVote,
)
from app.services.audit_service import log_action
from app.services.platoon_games import (
    GAMES, GAME_MAP, cohort_match, cohort_platoons, elected_leader,
    election_candidates, election_standings, leadership_term, local_today,
    member_is_eligible, next_election, period_is_live, placement_taken,
    quarter_end, quarter_start, upcoming_period, verified_scoreboard,
)


def register_game_routes(bp):
    @bp.route("/games")
    def games():
        """Digital competition board; no leader-entered placements required."""
        from app.services.platoon_microgames import (
            MICRO_GAMES, challenge_question, has_earned, digital_standings,
        )
        my_platoon = None
        if current_user.is_authenticated and current_user.profile:
            my_platoon = current_user.profile.platoon
        wanted = request.args.get("platoon_id", type=int)
        platoon = db.session.get(Platoon, wanted) if wanted else my_platoon
        period = quarter_start(request.args.get("period")) or upcoming_period()
        cohort = cohort_platoons(platoon) if platoon else []
        table = digital_standings(platoon, period) if platoon else []
        live = period_is_live(period)
        today = local_today()
        eligible = bool(
            live and my_platoon and current_user.is_authenticated
            and member_is_eligible(current_user, my_platoon.id)
        )
        done = {}
        quizzes = {}
        if eligible:
            for key, title, detail, mode, cadence in MICRO_GAMES:
                done[key] = has_earned(current_user.id, key, period, today)
                if mode == "quiz":
                    quizzes[key] = challenge_question(key, today)
        return render_template(
            "platoons/games.html", micro_games=MICRO_GAMES,
            platoon=platoon, my_platoon=my_platoon,
            cohort=cohort, period=period, end=quarter_end(period),
            today=today, live=live, table=table, done=done,
            quizzes=quizzes, eligible=eligible,
        )

    @bp.route("/games/play/<game_key>", methods=["POST"])
    @login_required
    @limiter.limit("60 per hour")
    def play_microgame(game_key):
        from app.services.platoon_microgames import (
            MICRO_GAME_MAP, challenge_question, earned, active_round,
        )
        game = MICRO_GAME_MAP.get(game_key)
        if not game:
            abort(404)
        if not active_round():
            abort(403)
        user = current_user
        if not user.profile or not user.profile.platoon_id or not member_is_eligible(
            user, user.profile.platoon_id,
        ):
            abort(403)
        kind = game[3]
        if kind == "automatic":
            abort(403)
        if kind == "verify":
            if game_key == "profile-ready" and user.profile.completion_percent() < 50:
                flash("Complete at least 50% of your profile first.", "warning")
                return redirect(url_for("profile.edit"))
            if game_key == "photo-finish" and not user.profile.photo_url:
                flash("Upload your profile photograph first.", "warning")
                return redirect(url_for("profile.edit"))
        elif kind == "quiz":
            question = challenge_question(game_key)
            if not question or request.form.get("answer") not in ("A", "B", "C"):
                abort(400)
            if request.form["answer"] != question[2]:
                flash("Not quite right. Try again before the day ends.", "warning")
                return redirect(url_for("platoons.games"))
        elif kind != "tap":
            abort(400)
        if earned(user, game_key):
            flash("Contribution recorded! One point of participation for your platoon.", "success")
        else:
            flash("Already counted for today or this round. Try again when eligible.", "info")
        return redirect(url_for("platoons.games", platoon_id=user.profile.platoon_id))


    @bp.route("/<int:platoon_id>/leaders")
    def leaders(platoon_id):
        platoon = db.get_or_404(Platoon, platoon_id)
        target, starts, deadline, ballot_open = next_election()
        nominees = election_candidates(platoon.id, target)
        active = elected_leader(platoon.id)
        term_start, term_end = leadership_term()
        my_vote = None
        if current_user.is_authenticated:
            my_vote = PlatoonLeaderVote.query.filter_by(
                voter_id=current_user.id, term_start=target,
            ).first()
        return render_template(
            "platoons/leaders.html", platoon=platoon, nominees=nominees,
            active=active, term_start=term_start, term_end=term_end,
            target=target, target_end=target + timedelta(days=13),
            starts=starts, deadline=deadline,
            ballot_open=ballot_open, my_vote=my_vote,
            eligible=member_is_eligible(current_user, platoon.id),
        )

    @bp.route("/<int:platoon_id>/leaders/nominate", methods=["POST"])
    @login_required
    @limiter.limit("5 per hour")
    def nominate(platoon_id):
        platoon = db.get_or_404(Platoon, platoon_id)
        if not member_is_eligible(current_user, platoon.id):
            abort(403)
        target, _, _, open_now = next_election()
        if not open_now:
            abort(403)
        if PlatoonLeaderCandidate.query.filter_by(
            user_id=current_user.id, term_start=target
        ).first():
            flash("You are already nominated for this term.", "info")
        else:
            db.session.add(PlatoonLeaderCandidate(
                user_id=current_user.id, platoon_id=platoon.id,
                term_start=target,
            ))
            try:
                db.session.commit()
                log_action(current_user, "platoon.nominate", "Platoon", platoon.id)
                flash("Your leadership nomination is recorded.", "success")
            except IntegrityError:
                db.session.rollback()
                flash("Your nomination was already recorded.", "info")
        return redirect(url_for("platoons.leaders", platoon_id=platoon.id))

    @bp.route("/<int:platoon_id>/leaders/vote", methods=["POST"])
    @login_required
    @limiter.limit("10 per hour")
    def leader_vote(platoon_id):
        platoon = db.get_or_404(Platoon, platoon_id)
        if not member_is_eligible(current_user, platoon.id):
            abort(403)
        target, _, _, open_now = next_election()
        if not open_now:
            abort(403)
        candidate = db.session.get(
            PlatoonLeaderCandidate, request.form.get("candidate_id", type=int)
        )
        if (not candidate or candidate.platoon_id != platoon.id
                or candidate.term_start != target
                or candidate not in election_candidates(platoon.id, target)):
            abort(400)
        if PlatoonLeaderVote.query.filter_by(
            term_start=target, voter_id=current_user.id,
        ).first():
            flash("Only one ballot per member is permitted each term.", "warning")
        else:
            db.session.add(PlatoonLeaderVote(
                term_start=target, platoon_id=platoon.id,
                voter_id=current_user.id, candidate_id=candidate.id,
            ))
            try:
                db.session.commit()
                log_action(current_user, "platoon.leader_vote", "Platoon", platoon.id)
                flash("Your vote has been counted.", "success")
            except IntegrityError:
                db.session.rollback()
                flash("Your vote was already recorded.", "warning")
        return redirect(url_for("platoons.leaders", platoon_id=platoon.id))

    @bp.route("/games/<int:platoon_id>/submit", methods=["POST"])
    @login_required
    @limiter.limit("25 per hour")
    def submit_game(platoon_id):
        platoon = db.get_or_404(Platoon, platoon_id)
        period = quarter_start(request.form.get("period"))
        game = request.form.get("game")
        if not period or game not in GAME_MAP:
            abort(400)
        try:
            placement = int(request.form.get("placement", ""))
        except ValueError:
            abort(400)
        if not 1 <= placement <= 10:
            abort(400)
        if not period_is_live(period):
            abort(403)
        is_admin = current_user.is_admin
        leader = elected_leader(platoon.id)
        if not is_admin and not (
            member_is_eligible(current_user, platoon.id)
            and leader and leader[0].user_id == current_user.id
        ):
            abort(403)
        details = (request.form.get("details") or "").strip()
        if len(details) > 500:
            abort(400)
        entry = PlatoonGameResult.query.filter_by(
            period_start=period, platoon_id=platoon.id, game_key=game,
        ).first()
        if entry and entry.status == "verified":
            flash("This result is already verified. Ask an admin for corrections.", "warning")
        else:
            if entry is None:
                entry = PlatoonGameResult(
                    period_start=period, platoon_id=platoon.id,
                    game_key=game, submitted_by_id=current_user.id,
                    placement=placement,
                )
                db.session.add(entry)
            entry.placement = placement
            entry.details = details
            entry.status = "pending"
            entry.submitted_by_id = current_user.id
            entry.reviewed_by_id = None
            entry.reviewed_at = None
            db.session.commit()
            log_action(current_user, "platoon.game_submitted", "PlatoonGameResult", entry.id)
            flash("Result submitted for administrator verification.", "success")
        return redirect(url_for(
            "platoons.games", platoon_id=platoon.id, period=period.isoformat(),
        ))

    @bp.route("/games/results/<int:result_id>/review", methods=["POST"])
    @login_required
    @limiter.limit("60 per hour")
    def review_game(result_id):
        if not current_user.is_admin:
            abort(403)
        entry = db.get_or_404(PlatoonGameResult, result_id)
        decision = request.form.get("decision")
        if decision not in ("verified", "rejected"):
            abort(400)
        if decision == "verified" and placement_taken(entry):
            flash("Another platoon already holds that verified placement for this game.", "danger")
        else:
            entry.status = decision
            entry.reviewed_by_id = current_user.id
            entry.reviewed_at = datetime.utcnow()
            db.session.commit()
            log_action(current_user, "platoon.game_reviewed", "PlatoonGameResult", entry.id)
            flash("Game result {}.".format(decision), "success")
        return redirect(url_for(
            "platoons.games", platoon_id=entry.platoon_id,
            period=entry.period_start.isoformat(),
        ))
