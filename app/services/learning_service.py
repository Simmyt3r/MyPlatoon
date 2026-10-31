"""YouTube link validation and certificate issuance for Silabs Academy."""
import re
from urllib.parse import urlsplit, parse_qs

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.learning import LearningCertificate, LearningLesson, LearningProgress


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
