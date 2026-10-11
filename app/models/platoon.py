"""Nationwide NYSC orientation platoons.

A number on its own is not a unique platoon. The same number is used
across different states, batches, years and streams. A PCM can sign up
without a platoon until NYSC assigns them at orientation camp.
"""
from app.extensions import db

SERVICE_STAGES = (
    ("pcm", "Prospective Corps Member (PCM)"),
    ("serving", "Serving Corps Member"),
    ("alumni", "Ex-Corps Member / Alumni"),
)

NYSC_STATES = (
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa",
    "Benue", "Borno", "Cross River", "Delta", "Ebonyi", "Edo",
    "Ekiti", "Enugu", "FCT", "Gombe", "Imo", "Jigawa", "Kaduna",
    "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa",
    "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers",
    "Sokoto", "Taraba", "Yobe", "Zamfara",
)

BATCH_CHOICES = ("A", "B", "C")
STREAM_CHOICES = ("I", "II")


class Platoon(db.Model):
    __tablename__ = "platoons"
    __table_args__ = (
        db.UniqueConstraint(
            "state", "service_year", "batch", "stream", "number",
            name="uq_nysc_platoon_identity"
        ),
        db.CheckConstraint("number >= 1 AND number <= 99", name="ck_platoon_number"),
    )

    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.String(40), nullable=False, index=True)
    service_year = db.Column(db.Integer, nullable=False)
    batch = db.Column(db.String(1), nullable=False)
    stream = db.Column(db.String(2), nullable=False)
    number = db.Column(db.Integer, nullable=False)

    members = db.relationship("Profile", back_populates="platoon")

    @property
    def label(self):
        return (f"{self.state} · {self.service_year} Batch {self.batch} "
                f"Stream {self.stream} · Platoon {self.number}")

    @classmethod
    def find_or_create(cls, state, service_year, batch, stream, number):
        """Return one cohort-scoped platoon. Call inside an existing transaction."""
        filters = dict(state=state, service_year=service_year, batch=batch,
                       stream=stream, number=number)
        obj = cls.query.filter_by(**filters).first()
        if obj is None:
            obj = cls(**filters)
            db.session.add(obj)
            db.session.flush()
        return obj
