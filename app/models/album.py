from datetime import datetime

from app.extensions import db


class AlbumVersion(db.Model):
    __tablename__ = "album_versions"

    id = db.Column(db.Integer, primary_key=True)
    version_label = db.Column(db.String(20), nullable=False)  # e.g. "1.0"
    # pdf_data is the source of truth for in-app downloads (see
    # app/services/album_service.py) -- it means downloads never depend on
    # Cloudinary's delivery rules for raw/PDF files, which some accounts
    # restrict by default (see DEPLOYMENT.md). pdf_url/pdf_public_id are
    # kept as a best-effort *secondary* copy on Cloudinary (e.g. for
    # sharing a link outside the app, or as an off-site backup) -- upload
    # failures there never block generation or break downloads.
    pdf_url = db.Column(db.String(500), nullable=False)
    pdf_public_id = db.Column(db.String(255))
    pdf_data = db.Column(db.LargeBinary)
    member_count = db.Column(db.Integer, default=0, nullable=False)
    generated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(20), default="published", nullable=False)  # draft|published|archived
    download_count = db.Column(db.Integer, default=0, nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    generated_by = db.relationship("User")

    def __repr__(self):
        return f"<AlbumVersion v{self.version_label}>"


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    created_by = db.relationship("User")
    reactions = db.relationship("AnnouncementReaction", back_populates="announcement",
                                 cascade="all, delete-orphan")
    comments = db.relationship("AnnouncementComment", back_populates="announcement",
                                cascade="all, delete-orphan",
                                order_by="AnnouncementComment.created_at")

    def reaction_counts(self):
        counts = {}
        for r in self.reactions:
            counts[r.reaction_type] = counts.get(r.reaction_type, 0) + 1
        return counts

    def total_reactions(self):
        return len(self.reactions)

    def reaction_for(self, user):
        if not user or not getattr(user, "is_authenticated", False):
            return None
        for r in self.reactions:
            if r.user_id == user.id:
                return r.reaction_type
        return None


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    target_type = db.Column(db.String(50))
    target_id = db.Column(db.String(50))
    detail = db.Column(db.Text)
    ip_address = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User")

    def __repr__(self):
        return f"<AuditLog {self.action} by user={self.user_id}>"


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    message = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(40), default="info", nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="notifications")
