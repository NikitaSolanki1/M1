from extension import db


class Account(db.Model):
    __tablename__ = 'account'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(100), nullable=False)  # student , examinor , admin

    is_verified = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)


class LearnerProfile(db.Model):
    __tablename__ = 'learner_profile'
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(100), nullable=False)
    past_experience = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False, unique=True)


class MarkerProfile(db.Model):
    __tablename__ = 'marker_profile'
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(100), nullable=False)
    past_experience = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False, unique=True)


class Subject(db.Model):
    __tablename__ = 'subject'
    id = db.Column(db.Integer, primary_key=True)
    coures_name = db.Column(db.String(100), nullable=False)
    coures_description = db.Column(db.String(100), nullable=False)
    course_duration = db.Column(db.Integer, nullable=False)


class Assessment(db.Model):
    __tablename__ = 'assessment'
    id = db.Column(db.Integer, primary_key=True)
    exam_name = db.Column(db.String(100), nullable=False)
    exam_description = db.Column(db.String(100), nullable=False)
    exam_date = db.Column(db.Date, nullable=False)
    exam_time = db.Column(db.Time, nullable=False)
    exam_duration = db.Column(db.Integer, nullable=False)
    slot_start_time = db.Column(db.Time, nullable=False)
    slot_end_time = db.Column(db.Time, nullable=False)
    slot_creation_start_date = db.Column(db.Date, nullable=True)
    slot_creation_end_date = db.Column(db.Date, nullable=True)
    is_slot_creation_open = db.Column(db.Boolean, nullable=False, default=False)
    booking_start_time = db.Column(db.Time, nullable=False)
    booking_end_time = db.Column(db.Time, nullable=False)
    booking_open_date = db.Column(db.Date, nullable=True)
    booking_close_date = db.Column(db.Date, nullable=True)
    is_booking_open = db.Column(db.Boolean, nullable=False, default=False)
    results_published = db.Column(db.Boolean, nullable=False, default=False)
    examinor_name = db.Column(db.String(100), nullable=False)
    coures_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    examinor_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    users = db.relationship('Account', backref='exams', lazy=True)


class TimeWindow(db.Model):
    __tablename__ = 'time_window'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('assessment.id'), nullable=False)
    slot_date = db.Column(db.Date, nullable=False)
    slot_time = db.Column(db.Time, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=1)
    is_closed = db.Column(db.Boolean, nullable=False, default=False)


class SeatBooking(db.Model):
    __tablename__ = 'seat_booking'
    id = db.Column(db.Integer, primary_key=True)
    slot_id = db.Column(db.Integer, db.ForeignKey('time_window.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('assessment.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Booked')


class ScoreItem(db.Model):
    __tablename__ = 'score_item'
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(100), nullable=False)
    marks = db.Column(db.Integer, nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('assessment.id'), nullable=False)


class MarkAward(db.Model):
    __tablename__ = 'mark_award'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('assessment.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('score_item.id'), nullable=False)
    marks_awarded = db.Column(db.Integer, nullable=False)
    given_by = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)


class ExamNote(db.Model):
    __tablename__ = 'exam_note'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('assessment.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    remark = db.Column(db.String(500), nullable=False)
    given_by = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
