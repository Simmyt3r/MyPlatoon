"""Silabs Academy courses, ordered lessons, learner progress and certificates."""
from datetime import datetime
from uuid import uuid4

from app.extensions import db


class LearningCourse(db.Model):
    __tablename__ = "learning_courses"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(110), unique=True, nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    summary = db.Column(db.String(320), nullable=False)
    description = db.Column(db.Text, nullable=False)
    level = db.Column(db.String(24), nullable=False, default="Beginner")
    published = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    lessons = db.relationship(
        "LearningLesson", back_populates="course", cascade="all, delete-orphan",
        order_by="LearningLesson.position",
    )
    certificates = db.relationship("LearningCertificate", back_populates="course")


class LearningLesson(db.Model):
    __tablename__ = "learning_lessons"
    __table_args__ = (db.UniqueConstraint("course_id", "position",
                                          name="uq_learning_lesson_position"),)
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey(
        "learning_courses.id", ondelete="CASCADE"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    youtube_id = db.Column(db.String(11), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    course = db.relationship("LearningCourse", back_populates="lessons")
    completions = db.relationship("LearningProgress", back_populates="lesson",
                                  cascade="all, delete-orphan")


class LearningProgress(db.Model):
    __tablename__ = "learning_progress"
    __table_args__ = (db.UniqueConstraint("user_id", "lesson_id",
                                          name="uq_learning_user_lesson"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="CASCADE"), nullable=False, index=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey(
        "learning_lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    lesson = db.relationship("LearningLesson", back_populates="completions")


class LearningCertificate(db.Model):
    __tablename__ = "learning_certificates"
    __table_args__ = (db.UniqueConstraint("user_id", "course_id",
                                          name="uq_learning_user_certificate"),)
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(36), nullable=False, unique=True, index=True,
                     default=lambda: str(uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey(
        "learning_courses.id", ondelete="RESTRICT"), nullable=False, index=True)
    learner_name = db.Column(db.String(120), nullable=False)
    course_title = db.Column(db.String(180), nullable=False)
    lesson_count = db.Column(db.Integer, nullable=False)
    issued_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    course = db.relationship("LearningCourse", back_populates="certificates")
