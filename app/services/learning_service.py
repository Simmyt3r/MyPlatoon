"""YouTube link validation and certificate issuance for Silabs Academy."""
import re
import math
from datetime import datetime
from uuid import uuid4
from urllib.parse import urlsplit, parse_qs

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.learning import LearningCertificate, LearningLesson, LearningProgress, LearningWatch


_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com",
                  "youtube-nocookie.com", "www.youtube-nocookie.com"}
_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}


def parse_youtube_id(value):
    """Accept only bona fide HTTPS YouTube video links (no arbitrary embeds)."""
    if not value or len(value) > 500:
        return None
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
            return None
        host = (parsed.hostname or "").lower()
        segments = [part for part in parsed.path.split("/") if part]
        if host in _SHORT_HOSTS and len(segments) == 1:
            video_id = segments[0]
        elif host in _YOUTUBE_HOSTS and parsed.path == "/watch":
            videos = parse_qs(parsed.query).get("v", [])
            video_id = videos[0] if len(videos) == 1 else ""
        elif host in _YOUTUBE_HOSTS and len(segments) == 2 and segments[0] in (
            "embed", "shorts", "live",
        ):
            video_id = segments[1]
        else:
            return None
        return video_id if _YOUTUBE_ID.fullmatch(video_id) else None
    except ValueError:
        return None


def completed_lesson_ids(user_id, course):
    ids = [lesson.id for lesson in course.lessons]
    if not ids:
        return set()
    return {
        record[0] for record in db.session.query(LearningProgress.lesson_id).filter(
            LearningProgress.user_id == user_id,
            LearningProgress.lesson_id.in_(ids),
        ).all()
    }


def issue_certificate_if_complete(user, course):
    """Issue once; completion is self-reported, not an exam assessment."""
    existing = LearningCertificate.query.filter_by(
        user_id=user.id, course_id=course.id,
    ).first()
    if existing:
        return existing
    if not course.published or not course.lessons:
        return None
    if len(completed_lesson_ids(user.id, course)) != len(course.lessons):
        return None
    certificate = LearningCertificate(
        user_id=user.id, course_id=course.id,
        learner_name=user.full_name, course_title=course.title,
        lesson_count=len(course.lessons),
    )
    db.session.add(certificate)
    try:
        db.session.commit()
    except IntegrityError:
        # Concurrent final-lesson requests cannot issue duplicate awards.
        db.session.rollback()
        return LearningCertificate.query.filter_by(
            user_id=user.id, course_id=course.id,
        ).first()
    return certificate


REQUIRED_WATCH_SECONDS = 90
# Heartbeats arrive approximately every five seconds. Server time always
# limits credit; no single heartbeat can earn more than six seconds.
MAX_HEARTBEAT_GAP = 12
MAX_HEARTBEAT_CREDIT = 6


def clock_now():
    return datetime.utcnow()


def watch_time(user_id, lesson_id):
    record = LearningWatch.query.filter_by(
        user_id=user_id, lesson_id=lesson_id,
    ).first()
    return record.watched_seconds if record is not None else 0.0


def start_watch_session(user_id, lesson_id):
    """Rotate the tab token so multiple open tabs cannot double count time."""
    record = LearningWatch.query.filter_by(
        user_id=user_id, lesson_id=lesson_id,
    ).with_for_update().first()
    if record is None:
        record = LearningWatch(user_id=user_id, lesson_id=lesson_id)
        db.session.add(record)
    record.session_id = str(uuid4())
    record.last_position = None
    record.last_seen_at = None
    db.session.commit()
    return record


def record_watch_heartbeat(user_id, lesson_id, session_id, position,
                           playing, visible):
    """Meter plausible active playback, never trust claimed elapsed seconds.

    This is still client-observed YouTube playback, *not* tamper-proof evidence
    of attention, but replaying posts or changing client timers cannot instantly
    complete a lesson. All credits are limited by the server's elapsed time.
    """
    record = LearningWatch.query.filter_by(
        user_id=user_id, lesson_id=lesson_id,
    ).with_for_update().first()
    if record is None or session_id != record.session_id:
        return None
    now = clock_now()
    if (not isinstance(position, (int, float)) or isinstance(position, bool)
            or not math.isfinite(position) or position < 0 or position > 86400):
        return None
    if playing is not True or visible is not True:
        record.last_seen_at = None
        record.last_position = None
        db.session.commit()
        return record.watched_seconds

    if record.last_seen_at is not None and record.last_position is not None:
        elapsed = (now - record.last_seen_at).total_seconds()
        advance = position - record.last_position
        if (1 <= elapsed <= MAX_HEARTBEAT_GAP
                and advance >= elapsed * 0.20
                and advance <= elapsed * 2.3 + 0.75):
            record.watched_seconds = min(
                float(REQUIRED_WATCH_SECONDS),
                record.watched_seconds + min(elapsed, MAX_HEARTBEAT_CREDIT),
            )
    record.last_seen_at = now
    record.last_position = float(position)
    db.session.commit()
    return record.watched_seconds
