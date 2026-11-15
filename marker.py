from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for
from models import *
from flask import session
from extension import db
from schedule_helpers import finish_old_bookings

marker_blueprint = Blueprint("marker", __name__)


@marker_blueprint.before_request
def need_approved_marker():
    if session.get('role') != 'examinor':
        return redirect(url_for('home_page'))
    user = Account.query.get(session.get('user_id'))
    if not user or not user.is_verified:
        session.pop('user_id', None)
        session.pop('role', None)
        return redirect(url_for('access.sign_in', pending=1))


def _booking_has_started(exam):
    if not exam:
        return True
    if exam.is_booking_open:
        return True
    if exam.booking_open_date and date.today() >= exam.booking_open_date:
        return True
    return False


def _can_make_slots(exam):
    if not exam.slot_creation_start_date or not exam.slot_creation_end_date:
        return False
    return bool(exam.is_slot_creation_open)


def _can_change_slot(exam, slot):
    if _booking_has_started(exam):
        return False
    if SeatBooking.query.filter_by(slot_id=slot.id, status='Booked').first():
        return False
    return True


def _marker_bookings(examinor_id):
    assigned_exams = Assessment.query.filter_by(examinor_id=examinor_id).all()
    exam_ids = [exam.id for exam in assigned_exams]
    bookings = SeatBooking.query.filter(
        SeatBooking.exam_id.in_(exam_ids),
        SeatBooking.status.in_(['Booked', 'Completed'])
    ).all() if exam_ids else []
    exam_map = {exam.id: exam for exam in assigned_exams}
    slot_map = {
        slot.id: slot for slot in TimeWindow.query.filter(TimeWindow.id.in_([booking.slot_id for booking in bookings])).all()
    } if bookings else {}
    student_map = {
        student.id: student for student in Account.query.filter(Account.id.in_([booking.student_id for booking in bookings])).all()
    } if bookings else {}
    finish_old_bookings(bookings, exam_map, slot_map)
    return assigned_exams, bookings, exam_map, slot_map, student_map


def _score_overview(bookings):
    summary = {}
    if not bookings:
        return summary
    exam_ids = {booking.exam_id for booking in bookings}
    student_ids = {booking.student_id for booking in bookings}
    questions = ScoreItem.query.filter(ScoreItem.exam_id.in_(exam_ids)).all()
    possible = {}
    for question in questions:
        possible[question.exam_id] = possible.get(question.exam_id, 0) + question.marks
    marks = MarkAward.query.filter(
        MarkAward.exam_id.in_(exam_ids),
        MarkAward.student_id.in_(student_ids)
    ).all()
    awarded = {}
    for mark in marks:
        key = (mark.exam_id, mark.student_id)
        awarded[key] = awarded.get(key, 0) + mark.marks_awarded
    for booking in bookings:
        key = (booking.exam_id, booking.student_id)
        summary[booking.id] = {
            'awarded': awarded.get(key),
            'possible': possible.get(booking.exam_id, 0)
        }
    return summary


@marker_blueprint.route('/examior_dashboard', methods=['POST', 'GET'])
def marker_home():
    user = Account.query.get(session.get('user_id'))
    profile = MarkerProfile.query.filter_by(user_id=session.get('user_id')).first()
    assigned_exams, bookings, exam_map, slot_map, student_map = _marker_bookings(session.get('user_id'))
    return render_template(
        'marker/examior_dashboard.html',
        user=user,
        profile=profile,
        assigned_exams=assigned_exams,
        bookings=bookings,
        exam_map=exam_map,
        slot_map=slot_map,
        student_map=student_map,
        mark_summary=_score_overview(bookings)
    )


@marker_blueprint.route('/see_bookings', methods=['GET'])
def list_marker_bookings():
    if session.get('role') != 'examinor':
        return redirect(url_for('home_page'))
    assigned_exams, bookings, exam_map, slot_map, student_map = _marker_bookings(session.get('user_id'))
    return render_template(
        'marker/see_bookings.html',
        bookings=bookings,
        exam_map=exam_map,
        slot_map=slot_map,
        student_map=student_map,
        mark_summary=_score_overview(bookings)
    )


@marker_blueprint.route('/view_booking/<int:booking_id>', methods=['GET'])
def show_booking(booking_id):
    if session.get('role') != 'examinor':
        return redirect(url_for('home_page'))
    booking = SeatBooking.query.get(booking_id)
    exam = Assessment.query.get(booking.exam_id) if booking else None
    if not booking or not exam or exam.examinor_id != session.get('user_id') or booking.status == 'Cancelled':
        return redirect(url_for('marker.list_marker_bookings'))
    student = Account.query.get(booking.student_id)
    profile = LearnerProfile.query.filter_by(user_id=student.id).first()
    slot = TimeWindow.query.get(booking.slot_id)
    remark = ExamNote.query.filter_by(exam_id=exam.id, student_id=student.id).first()
    return render_template(
        'marker/view_booking.html',
        booking=booking,
        exam=exam,
        student=student,
        profile=profile,
        slot=slot,
        remark=remark
    )


@marker_blueprint.route('/give_marks/<int:booking_id>', methods=['GET', 'POST'])
def enter_marks(booking_id):
    if session.get('role') != 'examinor':
        return redirect(url_for('home_page'))
    booking = SeatBooking.query.get(booking_id)
    exam = Assessment.query.get(booking.exam_id) if booking else None
    if not booking or not exam or exam.examinor_id != session.get('user_id') or booking.status == 'Cancelled':
        return redirect(url_for('marker.list_marker_bookings'))
    student = Account.query.get(booking.student_id)
    questions = ScoreItem.query.filter_by(exam_id=exam.id).all()
    saved = {
        mark.question_id: mark
        for mark in MarkAward.query.filter_by(exam_id=exam.id, student_id=student.id).all()
    }
    remark = ExamNote.query.filter_by(exam_id=exam.id, student_id=student.id).first()
    error = None
    if request.method == 'POST':
        awarded = {}
        for question in questions:
            raw = (request.form.get(f'marks_{question.id}') or '').strip()
            try:
                value = int(raw)
            except ValueError:
                error = 'Enter a whole number for every question.'
                break
            if value < 0 or value > question.marks:
                error = f'Marks for "{question.question}" must be from 0 to {question.marks}.'
                break
            awarded[question.id] = value
        if not error and not questions:
            error = 'This exam has no rubric yet.'
        if not error:
            for question in questions:
                row = saved.get(question.id)
                if row:
                    row.marks_awarded = awarded[question.id]
                    row.given_by = session.get('user_id')
                else:
                    db.session.add(MarkAward(
                        exam_id=exam.id,
                        student_id=student.id,
                        question_id=question.id,
                        marks_awarded=awarded[question.id],
                        given_by=session.get('user_id')
                    ))
            remark_text = (request.form.get('remark') or '').strip()
            if remark:
                remark.remark = remark_text
                remark.given_by = session.get('user_id')
            elif remark_text:
                db.session.add(ExamNote(
                    exam_id=exam.id,
                    student_id=student.id,
                    remark=remark_text,
                    given_by=session.get('user_id')
                ))
            db.session.commit()
            return redirect(url_for('marker.list_marker_bookings'))
    return render_template(
        'marker/give_marks.html',
        exam=exam,
        student=student,
        questions=questions,
        saved=saved,
        remark=remark,
        error=error
    )


@marker_blueprint.route('/create_profile', methods=['POST', 'GET'])
def make_marker_profile():
    user_id = session.get('user_id')
    user = Account.query.get(user_id)
    profile = MarkerProfile.query.filter_by(user_id=user_id).first()
    if request.method == 'POST':
        user.name = request.form['name']
        user.email = request.form['email']
        address = request.form['address']
        phone = request.form['phone']
        past_experience = request.form['past_experience']
        if profile:
            profile.address = address
            profile.phone = phone
            profile.past_experience = past_experience
        else:
            profile = MarkerProfile(address=address, phone=phone, past_experience=past_experience, user_id=user_id)
            db.session.add(profile)
        db.session.commit()
        return redirect(url_for('marker.marker_home'))
    return render_template('marker/create_profile.html', profile=profile, user=user)


@marker_blueprint.route('/edit_profile', methods=['POST', 'GET'])
def update_marker_profile():
    user_id = session.get('user_id')

    profile = MarkerProfile.query.filter_by(user_id=user_id).first()
    if request.method == 'POST':

        address = request.form['address']
        phone = request.form['phone']
        past_experience = request.form['past_experience']
        profile.address = address
        profile.phone = phone
        profile.past_experience = past_experience
        db.session.commit()
        return redirect(url_for('marker.marker_home'))
    return render_template('marker/edit_profile.html', profile=profile)


@marker_blueprint.route('/see_assigned_exams', methods=['POST', 'GET'])
def list_assigned_tests():
    examior_id = session.get('user_id')
    assigned_exams = Assessment.query.filter_by(examinor_id=examior_id).all()
    courses = {course.id: course for course in Subject.query.all()}
    return render_template('marker/see_assigned_exams.html', assigned_exams=assigned_exams, courses=courses)


def _read_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _read_time(value):
    try:
        return datetime.strptime(value, '%H:%M').time()
    except (TypeError, ValueError):
        return None


@marker_blueprint.route('/provide_slot/<int:exam_id>', methods=['POST', 'GET'])
def offer_time_window(exam_id):
    examior_id = session.get('user_id')
    exam = Assessment.query.get(exam_id)
    if not exam or exam.examinor_id != examior_id:
        return redirect(url_for('marker.list_assigned_tests'))

    error = None
    if request.method == 'POST':
        slot_date = _read_date(request.form.get('slot_date'))
        slot_time = _read_time(request.form.get('slot_time'))
        if not exam.slot_creation_start_date or not exam.slot_creation_end_date:
            error = 'The admin has not set the slot creation dates for this exam yet.'
        elif not slot_date:
            error = 'Select a valid slot date.'
        elif not slot_time:
            error = 'Select a valid slot time.'
        elif not _can_make_slots(exam):
            error = 'The admin has closed slot creation for this exam.'
        elif slot_date < exam.slot_creation_start_date or slot_date > exam.slot_creation_end_date:
            error = (
                'You can create a slot only between '
                f'{exam.slot_creation_start_date} and '
                f'{exam.slot_creation_end_date}, the dates set by the admin.'
            )
        elif TimeWindow.query.filter_by(exam_id=exam.id, slot_date=slot_date, slot_time=slot_time).first():
            error = 'A slot already exists at this date and time.'
        else:
            try:
                capacity = int(request.form.get('capacity') or 1)
            except ValueError:
                capacity = 0
            if capacity < 1:
                error = 'Slot capacity must be at least 1.'
            else:
                slot = TimeWindow(
                    exam_id=exam.id,
                    slot_date=slot_date,
                    slot_time=slot_time,
                    created_by=examior_id,
                    capacity=capacity,
                    is_closed=False
                )
                db.session.add(slot)
                db.session.commit()
                return redirect(url_for('marker.offer_time_window', exam_id=exam.id))

    slots = TimeWindow.query.filter_by(exam_id=exam.id).order_by(TimeWindow.slot_date, TimeWindow.slot_time).all()
    slot_ids = [slot.id for slot in slots]
    bookings = SeatBooking.query.filter(
        SeatBooking.slot_id.in_(slot_ids),
        SeatBooking.status == 'Booked'
    ).all() if slot_ids else []
    booking_by_slot = {}
    for booking in bookings:
        booking_by_slot.setdefault(booking.slot_id, []).append(booking)
    student_map = {
        student.id: student for student in Account.query.filter(Account.id.in_([booking.student_id for booking in bookings])).all()
    } if bookings else {}
    return render_template(
        'marker/provide_slot.html',
        exam=exam,
        slots=slots,
        error=error,
        booking_by_slot=booking_by_slot,
        student_map=student_map,
        booking_started=_booking_has_started(exam),
        creation_open=_can_make_slots(exam),
        locked=request.args.get('locked')
    )


@marker_blueprint.route('/edit_slot/<int:slot_id>', methods=['GET', 'POST'])
def update_time_window(slot_id):
    slot = TimeWindow.query.get(slot_id)
    exam = Assessment.query.get(slot.exam_id) if slot else None
    if not slot or not exam or exam.examinor_id != session.get('user_id'):
        return redirect(url_for('marker.list_assigned_tests'))
    if not _can_change_slot(exam, slot):
        return redirect(url_for('marker.offer_time_window', exam_id=exam.id, locked=1))
    error = None
    if request.method == 'POST':
        slot_date = _read_date(request.form.get('slot_date'))
        slot_time = _read_time(request.form.get('slot_time'))
        if not slot_date:
            error = 'Select a valid slot date.'
        elif not slot_time:
            error = 'Select a valid slot time.'
        elif slot_date < exam.slot_creation_start_date or slot_date > exam.slot_creation_end_date:
            error = (
                'The slot date must stay between '
                f'{exam.slot_creation_start_date} and {exam.slot_creation_end_date}.'
            )
        else:
            taken = TimeWindow.query.filter_by(exam_id=exam.id, slot_date=slot_date, slot_time=slot_time).first()
            if taken and taken.id != slot.id:
                error = 'A slot already exists at this date and time.'
            else:
                slot.slot_date = slot_date
                slot.slot_time = slot_time
                db.session.commit()
                return redirect(url_for('marker.offer_time_window', exam_id=exam.id))
    return render_template('marker/edit_slot.html', exam=exam, slot=slot, error=error)


@marker_blueprint.route('/delete_slot/<int:slot_id>', methods=['POST', 'GET'])
def remove_time_window(slot_id):
    slot = TimeWindow.query.get(slot_id)
    exam = Assessment.query.get(slot.exam_id) if slot else None
    if not slot or not exam or slot.created_by != session.get('user_id'):
        return redirect(url_for('marker.list_assigned_tests'))
    if not _can_change_slot(exam, slot):
        return redirect(url_for('marker.offer_time_window', exam_id=exam.id, locked=1))
    db.session.delete(slot)
    db.session.commit()
    return redirect(url_for('marker.offer_time_window', exam_id=exam.id))
