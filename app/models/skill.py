from app.extensions import db

profile_skills = db.Table(
    "profile_skills",
    db.Column("profile_id", db.Integer, db.ForeignKey("profiles.id", ondelete="CASCADE"),
               primary_key=True),
    db.Column("skill_id", db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"),
               primary_key=True),
)


class Skill(db.Model):
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)

    profiles = db.relationship("Profile", secondary=profile_skills,
                                back_populates="skills")

    def __repr__(self):
        return f"<Skill {self.name}>"
