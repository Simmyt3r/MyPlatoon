"""Silabs Academy: publisher permissions, YouTube safety, completion and PDFs."""
from app.extensions import db
from app.models import User
from app.models.learning import (
    LearningCertificate, LearningCourse, LearningLesson, LearningProgress,
)
from app.services.learning_service import parse_youtube_id
from tests.conftest import _create_user, login


VIDEO_ID = "dQw4w9WgXcQ"


def create_course(db, admin_user, published=True, lessons=2):
    course = LearningCourse(
        slug="ai-beginners", title="Introduction to Artificial Intelligence",
        summary="Practical beginner lessons in AI.", description="Learn how to use AI.",
        level="Beginner", created_by_id=admin_user.id, published=published,
    )
    db.session.add(course)
    db.session.flush()
    for position in range(1, lessons + 1):
        db.session.add(LearningLesson(
            course_id=course.id, position=position,
            title=f"Lesson {position}", description="Video lesson",
            youtube_id=VIDEO_ID,
        ))
    db.session.commit()
    return course


def test_youtube_parser_accepts_only_supported_youtube_links():
    accepted = (
        f"https://www.youtube.com/watch?v={VIDEO_ID}&t=30",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://youtube.com/embed/{VIDEO_ID}",
        f"https://www.youtube-nocookie.com/embed/{VIDEO_ID}",
        f"https://youtube.com/shorts/{VIDEO_ID}",
    )
    for url in accepted:
        assert parse_youtube_id(url) == VIDEO_ID
    rejected = (
        f"http://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtube.com.evil.example/watch?v={VIDEO_ID}",
        "javascript:alert(1)",
        "https://youtu.be/invalid",
        "https://vimeo.com/12345678",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&v=AAAAAAAAAAA",
        f"https://test@youtUbe.com/watch?v={VIDEO_ID}",
        f"https://youtube.com:443/watch?v={VIDEO_ID}",
        f"https://youtube.com/playlist?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}/other",
    )
    for url in rejected:
        assert parse_youtube_id(url) is None


def test_catalog_lists_only_published_courses(client, db, admin_user):
    create_course(db, admin_user, published=False)
    assert b"Introduction to Artificial Intelligence" not in client.get("/learn/").data
    assert client.get("/learn/courses/ai-beginners").status_code == 404
    login(client, admin_user.email)
    assert client.get("/learn/courses/ai-beginners").status_code == 200
    assert b"Manage Silabs Academy" in client.get("/admin/").data


def test_admin_course_create_publish_and_lesson_series(client, db, admin_user):
    login(client, admin_user.email)
    response = client.post("/learn/admin/courses/new", data={
        "title": "Cyber Security Fundamentals",
        "summary": "Learn safe cyber security practices.",
        "description": "Structured videos for beginners.",
        "level": "Beginner",
    })
    assert response.status_code == 302
    course = LearningCourse.query.filter_by(slug="cyber-security-fundamentals").one()
    assert course.published is False
    assert client.post(f"/learn/admin/courses/{course.id}", data={
        "action": "publish",
    }).status_code == 302
    assert course.published is False

    response = client.post(f"/learn/admin/courses/{course.id}/lessons", data={
        "lesson_title": "First lecture",
        "lesson_description": "Understand security concepts",
        "youtube_url": f"https://www.youtube.com/watch?v={VIDEO_ID}",
    })
    assert response.status_code == 302
    assert len(course.lessons) == 1
    assert course.lessons[0].youtube_id == VIDEO_ID

    client.post(f"/learn/admin/courses/{course.id}", data={"action": "publish"})
    assert course.published is True
    client.post("/auth/logout")
    assert b"Cyber Security Fundamentals" in client.get("/learn/").data


def test_invalid_youtube_link_is_rejected(client, admin_user, db):
    course = create_course(db, admin_user, published=False, lessons=0)
    login(client, admin_user.email)
    response = client.post(f"/learn/admin/courses/{course.id}/lessons", data={
        "lesson_title": "Malicious video URL",
        "youtube_url": "https://youtube.com.evil.example/watch?v=" + VIDEO_ID,
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"valid HTTPS YouTube video link" in response.data
    assert LearningLesson.query.count() == 0


def test_course_completion_issues_one_certificate_with_valid_pdf(
    client, db, admin_user, member_user,
):
    course = create_course(db, admin_user)
    login(client, member_user.email)
    lesson1, lesson2 = course.lessons

    page = client.get(f"/learn/courses/{course.slug}/lessons/{lesson1.id}")
    assert page.status_code == 200
    assert b"youtube-nocookie.com/embed/" + VIDEO_ID.encode() in page.data
    assert b"Marking a lesson complete is your declaration" in page.data

    first = client.post(
        f"/learn/courses/{course.slug}/lessons/{lesson1.id}/complete",
    )
    assert first.status_code == 302
    assert LearningCertificate.query.count() == 0
    assert LearningProgress.query.count() == 1

    second = client.post(
        f"/learn/courses/{course.slug}/lessons/{lesson2.id}/complete",
        follow_redirects=True,
    )
    assert b"Your Silabs certificate is ready" in second.data
    assert LearningCertificate.query.count() == 1
    certificate = LearningCertificate.query.one()
    assert certificate.learner_name == member_user.full_name
    assert certificate.course_title == course.title
    assert certificate.lesson_count == 2
    assert len(certificate.code) == 36

    client.post(f"/learn/courses/{course.slug}/lessons/{lesson2.id}/complete")
    assert LearningCertificate.query.count() == 1
    assert LearningProgress.query.count() == 2

    pdf = client.get(f"/learn/certificates/{certificate.code}/download")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")
    assert len(pdf.data) > 2500
    assert pdf.headers["Cache-Control"] == "private, no-store"
    public = client.get(f"/learn/certificates/{certificate.code}")
    assert public.status_code == 200
    assert member_user.full_name.encode() in public.data
    assert b"proctored" not in public.data.lower() or b"supervised assessment" in public.data.lower()


def test_cannot_forge_certificate_or_download_another_users_pdf(
    client, db, admin_user, member_user,
):
    course = create_course(db, admin_user)
    extra = _create_user(db, "other-learner@example.com")
    login(client, member_user.email)
    assert client.get("/learn/my-certificates").status_code == 200
    assert client.get("/learn/certificates/unknown/download").status_code == 404
    assert LearningCertificate.query.count() == 0

    for lesson in course.lessons:
        client.post(f"/learn/courses/{course.slug}/lessons/{lesson.id}/complete")
    certificate = LearningCertificate.query.one()
    client.post("/auth/logout")

    login(client, extra.email)
    assert client.get(f"/learn/certificates/{certificate.code}").status_code == 200
    assert client.get(f"/learn/certificates/{certificate.code}/download").status_code == 403
    assert LearningCertificate.query.count() == 1


def test_admin_only_course_writes_and_course_revision_lock(
    client, db, admin_user, member_user,
):
    course = create_course(db, admin_user)
    lesson = course.lessons[0]
    new_lesson = {
        "lesson_title": "Injected lesson",
        "youtube_url": f"https://youtu.be/{VIDEO_ID}",
    }
    assert client.post("/learn/admin/courses/new", data={
        "title": "Inauthentic", "summary": "No", "description": "No",
        "level": "Beginner",
    }).status_code in (302, 401)
    login(client, member_user.email)
    assert client.get("/learn/admin").status_code == 403
    assert client.post(f"/learn/admin/courses/{course.id}/lessons",
                       data=new_lesson).status_code == 403
    for item in course.lessons:
        client.post(f"/learn/courses/{course.slug}/lessons/{item.id}/complete")
    assert LearningCertificate.query.count() == 1

    client.post("/auth/logout")
    login(client, admin_user.email)
    response = client.post(f"/learn/admin/courses/{course.id}/lessons",
                           data=new_lesson, follow_redirects=True)
    assert b"locked after certificates" in response.data
    assert len(course.lessons) == 2
    response = client.post(
        f"/learn/admin/courses/{course.id}/lessons/{lesson.id}",
        data={"action": "delete"}, follow_redirects=True,
    )
    assert b"locked after certificates" in response.data
    assert LearningCertificate.query.count() == 1
    client.post(f"/learn/admin/courses/{course.id}",
                data={"action": "unpublish"})
    assert client.get(f"/learn/certificates/{LearningCertificate.query.one().code}").status_code == 200


def test_missing_foreign_lesson_and_unpublished_course_never_earn_award(
    client, db, admin_user, member_user,
):
    course = create_course(db, admin_user, published=False)
    other = LearningCourse(
        slug="second-course", title="Second Course", summary="Another course",
        description="Second description", level="Beginner", published=True,
        created_by_id=admin_user.id,
    )
    db.session.add(other)
    db.session.flush()
    foreign_lesson = LearningLesson(
        course_id=other.id, position=1, title="Foreign lesson",
        description="Independent", youtube_id=VIDEO_ID,
    )
    db.session.add(foreign_lesson)
    db.session.commit()

    login(client, member_user.email)
    assert client.post(
        f"/learn/courses/{course.slug}/lessons/{course.lessons[0].id}/complete",
    ).status_code == 404
    assert client.post(
        f"/learn/courses/{other.slug}/lessons/{course.lessons[0].id}/complete",
    ).status_code == 404
    assert LearningCertificate.query.count() == 0


def test_school_account_does_not_get_member_learning_workspace(client, db):
    school = _create_user(db, "school-academy@example.com", role="employer")
    login(client, school.email)
    assert client.get("/learn/").status_code == 200
    assert client.get("/learn/my-certificates").status_code == 403
    assert b"Silabs Academy" not in client.get("/jobs/employer", follow_redirects=True).data
