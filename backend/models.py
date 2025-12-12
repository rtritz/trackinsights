from datetime import datetime
from . import db

class School(db.Model):
    __tablename__ = "school"
    school_id = db.Column(db.Integer, primary_key=True)
    school_name = db.Column(db.String)
    team_name = db.Column(db.String)
    school_type = db.Column(db.String, db.ForeignKey("school_type.school_type"))
    nickname = db.Column(db.String, db.ForeignKey("nickname.nickname"))
    address = db.Column(db.String)
    city = db.Column(db.String)
    zip = db.Column(db.Integer)
    longitude = db.Column(db.Integer)
    latitude = db.Column(db.Integer)
    athletes = db.relationship("Athlete", backref="school")
    relay_results = db.relationship("RelayResult", backref="school")
    enrollments = db.relationship("SchoolEnrollment", backref="school")

class Nickname(db.Model):
    __tablename__ = "nickname"
    nickname = db.Column(db.String, primary_key=True)
    schools = db.relationship("School", backref="nickname_ref")

class SchoolType(db.Model):
    __tablename__ = "school_type"
    school_type = db.Column(db.String, primary_key=True)
    schools = db.relationship("School", backref="school_type_ref")

class SchoolClassification(db.Model):
    __tablename__ = "school_classification"
    school_classification = db.Column(db.String, primary_key=True)
    min_enrollment = db.Column(db.Integer)
    max_enrollment = db.Column(db.Integer)

class Athlete(db.Model):
    __tablename__ = "athlete"
    athlete_id = db.Column(db.Integer, primary_key=True)
    first = db.Column(db.String)
    last = db.Column(db.String)
    school_id = db.Column(db.Integer, db.ForeignKey("school.school_id"))
    gender = db.Column(db.String, db.ForeignKey("gender.gender"))
    graduation_year = db.Column("grad_year", db.Integer)
    results = db.relationship("AthleteResult", backref="athlete")
    relay_entries = db.relationship("RelayAthlete", backref="athlete")

class AthleteResult(db.Model):
    __tablename__ = "athlete_result"
    athlete_id = db.Column(db.Integer, db.ForeignKey("athlete.athlete_id"), primary_key=True)
    meet_id = db.Column(db.Integer, db.ForeignKey("meet.meet_id"), primary_key=True)
    event = db.Column(db.String, db.ForeignKey("event.event"), primary_key=True)
    result_type = db.Column(db.String, db.ForeignKey("result_type.result_type"), primary_key=True)
    grade = db.Column(db.String, db.ForeignKey("grade.grade"))
    result = db.Column(db.String)
    result2 = db.Column(db.Float)
    place = db.Column(db.Integer)

class RelayResult(db.Model):
    __tablename__ = "relay_result"
    school_id = db.Column(db.Integer, db.ForeignKey("school.school_id"), primary_key=True)
    meet_id = db.Column(db.Integer, db.ForeignKey("meet.meet_id"), primary_key=True)
    event = db.Column(db.String, db.ForeignKey("event.event"), primary_key=True)
    result = db.Column(db.String)
    result2 = db.Column(db.Float)
    place = db.Column(db.Integer)
    athlete_names = db.Column(db.String)

class RelayAthlete(db.Model):
    __tablename__ = "relay_athlete"
    relay_id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athlete.athlete_id"), primary_key=True)

class Event(db.Model):
    __tablename__ = "event"
    event = db.Column(db.String, primary_key=True)
    event_type = db.Column(db.String, db.ForeignKey("event_type.event_type"))

class Meet(db.Model):
    __tablename__ = "meet"
    meet_id = db.Column(db.Integer, primary_key=True)
    host = db.Column(db.String)
    meet_type = db.Column(db.String, db.ForeignKey("meet_type.meet_type"))
    meet_num = db.Column(db.Integer)
    gender = db.Column(db.String, db.ForeignKey("gender.gender"))
    year = db.Column(db.Integer)
    athlete_results = db.relationship("AthleteResult", backref="meet")
    relay_results = db.relationship("RelayResult", backref="meet")

class MeetType(db.Model):
    __tablename__ = "meet_type"
    meet_type = db.Column(db.String, primary_key=True)
    meets = db.relationship("Meet", backref="meet_type_ref")

class Gender(db.Model):
    __tablename__ = "gender"
    gender = db.Column(db.String, primary_key=True)
    athletes = db.relationship("Athlete", backref="gender_ref")
    meets = db.relationship("Meet", backref="gender_ref")

class EventType(db.Model):
    __tablename__ = "event_type"
    event_type = db.Column(db.String, primary_key=True)
    events = db.relationship("Event", backref="event_type_ref")

class ResultType(db.Model):
    __tablename__ = "result_type"
    result_type = db.Column(db.String, primary_key=True)
    athlete_results = db.relationship("AthleteResult", backref="result_type_ref")

class Grade(db.Model):
    __tablename__ = "grade"
    grade = db.Column(db.String, primary_key=True)
    athlete_results = db.relationship("AthleteResult", backref="grade_ref")

class SchoolEnrollment(db.Model):
    __tablename__ = "school_enrollment"
    school_id = db.Column(db.Integer, db.ForeignKey("school.school_id"), primary_key=True)
    year = db.Column(db.Integer, primary_key=True)
    enrollment = db.Column(db.Integer)

class HouseValues(db.Model):
    __tablename__ = "house_values"
    zip = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, primary_key=True)
    avg_value = db.Column(db.Integer)

