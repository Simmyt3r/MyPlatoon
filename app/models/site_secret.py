"""Encrypted optional integration credentials. Never store bootstrap secrets here."""
from datetime import datetime
from app.extensions import db


class SiteSecret(db.Model):
    __tablename__ = "site_secrets"

    key = db.Column(db.String(80), primary_key=True)
    ciphertext = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
