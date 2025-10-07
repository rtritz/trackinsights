from datetime import datetime
try:
    from . import db
except Exception:
    db = None


if db is not None:
    class Athlete(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        first_name = db.Column(db.String(100), nullable=False)
        last_name = db.Column(db.String(100), nullable=False)
        school = db.Column(db.String(200))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

        def __repr__(self):
            return f"<Athlete {self.id} {self.first_name} {self.last_name}>"
else:
    # Lightweight in-memory fallback model
    class Athlete:
        _auto = 1

        def __init__(self, first_name, last_name, school=None):
            self.id = Athlete._auto
            Athlete._auto += 1
            self.first_name = first_name
            self.last_name = last_name
            self.school = school
            self.created_at = datetime.utcnow()

        def __repr__(self):
            return f"<Athlete {self.id} {self.first_name} {self.last_name}>"
