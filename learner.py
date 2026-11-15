from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for
from models import *
from flask import session
from extension import db
from schedule_helpers import (
    booking_is_open,
    assessment_stage,
    booking_label,
    finish_old_bookings,
    window_is_full,
    sync_window_closed,
    live_booking_counts,
)


def _slot_is_visible(exam, today=None):
    today = today or date.today()
    if booking_is_open(exam, today):
        return True
    return bool(exam and exam.is_slot_creation_open)


def can_cancel_now(exam, today=None):
    today = today or date.today()
    if not exam:
        return False
    if exam.booking_close_date:
        return today <= exam.booking_close_date
    return bool(exam.is_booking_open)


def _exam_matches(term, exam):
    if not term:
        return True
    if term.isdigit():
        return str(exam.id) == term
    return term.lower() in (exam.exam_name or '').lower()


learner_blueprint = Blueprint("learner", __name__)


@learner_blueprint.route('/user_dashboard', methods=['GET'])
def learner_home():
    if session.get('role') != 'student':
        return redirect(url_for('home_page'))
    user_id = session.get('user_id')
    user = Account.query.get(user_id)
    profile = LearnerProfile.query.filter_by(user_id=user_id).first()
    exams = Assessment.query.order_by(Assessment.exam_date).all()
    courses = {course.id: course for course in Subject.query.all()}
    bookings = SeatBooking.query.filter_by(student_id=user_id).all()
    exam_map = {exam.id: exam for exam in exams}
    slot_map = {slot.id: slot for slot in TimeWindow.query.all()}
    finish_old_bookings(bookings, exam_map, slot_map)
    counts = live_booking_counts()
    booked_exam_ids = {booking.exam_id for booking in bookings if booking.status == 'Booked'}
    open_slots = [
        slot for slot in TimeWindow.query.order_by(TimeWindow.slot_date).all()
        if not window_is_full(slot, counts)
        and slot.exam_id not in booked_exam_ids
        and _slot_is_visible(exam_map.get(slot.exam_id))
    ]
    mark_summary = {}
    if bookings:
        exam_ids = {booking.exam_id for booking in bookings}
        questions = ScoreItem.query.filter(ScoreItem.exam_id.in_(exam_ids)).all()
        possible = {}
        for question in questions:
            possible[question.exam_id] = possible.get(question.exam_id, 0) + question.marks
        marks = MarkAward.query.filter(
            MarkAward.student_id == user_id,
            MarkAward.exam_id.in_(exam_ids)
        ).all()
        awarded = {}
        for mark in marks:
            awarded[mark.exam_id] = awarded.get(mark.exam_id, 0) + mark.marks_awarded
        for booking in bookings:
            mark_summary[booking.id] = {
                'awarded': awarded.get(booking.exam_id) if exam_map[booking.exam_id].results_published else None,
                'possible': possible.get(booking.exam_id, 0),
                'published': bool(exam_map[booking.exam_id].results_published)
            }
    cancel_open = {
        booking.id: booking.status == 'Booked' and can_cancel_now(exam_map.get(booking.exam_id), date.today())
        for booking in bookings
    }
    statuses = {booking.id: booking_label(booking) for booking in bookings}
    return render_template(
        'learner/user_dashboard.html',
        user=user,
        profile=profile,
        exams=exams,
        courses=courses,
        open_slots=open_slots,
        bookings=bookings,
        exam_map=exam_map,
        slot_map=slot_map,
        mark_summary=mark_summary,
        cancel_open=cancel_open,
        statuses=statuses,
        phases={exam.id: assessment_stage(exam) for exam in exams},
        can_book={exam.id: booking_is_open(exam) for exam in exams},
        today=date.today()
    )


def _learner_records(user_id):
    bookings = SeatBooking.query.filter_by(student_id=user_id).all()
    exam_ids = {booking.exam_id for booking in bookings}
    exams = {exam.id: exam for exam in (Assessment.query.filter(Assessment.id.in_(exam_ids)).all() if exam_ids else [])}
    slots = {slot.id: slot for slot in TimeWindow.query.filter(TimeWindow.id.in_({booking.slot_id for booking in bookings})).all()} if bookings else {}
    return bookings, exams, slots


@learner_blueprint.route('/exams', methods=['GET'])
def list_tests():
    if session.get('role') != 'student':
        return redirect(url_for('home_page'))
    term = (request.args.get('q') or '').strip()
    course_filter = (request.args.get('course') or '').strip()
    booking_filter = (request.args.get('booking') or 'all').strip()
    when_filter = (request.args.get('when') or 'all').strip()
    today = date.today()
    courses = Subject.query.order_by(Subject.coures_name).all()
    course_map = {course.id: course for course in courses}
    user_id = session.get('user_id')
    student_bookings = SeatBooking.query.filter_by(student_id=user_id, status='Booked').all()
    booked_exam_ids = {booking.exam_id for booking in student_bookings}
    counts = live_booking_counts()
    exam_lookup = {exam.id: exam for exam in Assessment.query.all()}
    slots_by_exam = {}
    for slot in TimeWindow.query.order_by(TimeWindow.slot_date).all():
        if (
            _slot_is_visible(exam_lookup.get(slot.exam_id))
            and not window_is_full(slot, counts)
            and slot.exam_id not in booked_exam_ids
        ):
            slots_by_exam.setdefault(slot.exam_id, []).append(slot)
    visible = []
    for exam in Assessment.query.order_by(Assessment.exam_date).all():
        if not _exam_matches(term, exam):
            continue
        if course_filter and str(exam.coures_id) != course_filter:
            continue
        if booking_filter == 'open' and not exam.is_booking_open:
            continue
        if booking_filter == 'closed' and exam.is_booking_open:
            continue
        if when_filter == 'upcoming' and exam.exam_date < today:
            continue
        if when_filter == 'past' and exam.exam_date >= today:
            continue
        visible.append(exam)
    return render_template(
        'learner/exams.html',
        exams=visible,
        courses=courses,
        course_map=course_map,
        slots_by_exam=slots_by_exam,
        booked_exam_ids=booked_exam_ids,
        q=term,
        course_filter=course_filter,
        booking_filter=booking_filter,
        when_filter=when_filter,
        phases={exam.id: assessment_stage(exam) for exam in visible},
        can_book={exam.id: booking_is_open(exam) for exam in visible},
        today=today
    )


@learner_blueprint.route('/bookings', methods=['GET'])
def list_my_bookings():
    if session.get('role') != 'student':
        return redirect(url_for('home_page'))
    user_id = session.get('user_id')
    rows, exams, slots = _learner_records(user_id)
    today = date.today()
    finish_old_bookings(rows, exams, slots, today)
    details = []
    for booking in rows:
        exam = exams.get(booking.exam_id)
        slot = slots.get(booking.slot_id)
        details.append({
            'booking': booking,
            'exam': exam,
            'slot': slot,
            'status': booking_label(booking),
            'can_cancel': booking.status == 'Booked' and can_cancel_now(exam, today),
            'published': bool(exam and exam.results_published)
        })
    return render_template('learner/bookings.html', details=details)


@learner_blueprint.route('/history', methods=['GET'])
def past_bookings():
    if session.get('role') != 'student':
        return redirect(url_for('home_page'))
    user_id = session.get('user_id')
    rows, exams, slots = _learner_records(user_id)
    today = date.today()
    finish_old_bookings(rows, exams, slots, today)
    past = []
    for booking in rows:
        exam = exams.get(booking.exam_id)
        slot = slots.get(booking.slot_id)
        if booking.status in ('Completed', 'Cancelled'):
            past.append({
                'booking': booking,
                'exam': exam,
                'slot': slot,
                'status': booking_label(booking),
                'published': bool(exam and exam.results_published)
            })
    past.sort(key=lambda item: item['exam'].exam_date if item['exam'] else date.min, reverse=True)
    return render_template('learner/history.html', past=past)


@learner_blueprint.route('/my_marks', methods=['GET'])
def my_scores():
    if session.get('role') != 'student':
        return redirect(url_for('home_page'))
    user_id = session.get('user_id')
    bookings = SeatBooking.query.filter_by(student_id=user_id).all()
    marks = MarkAward.query.filter_by(student_id=user_id).all()
    exam_ids = {booking.exam_id for booking in bookings}
    exam_ids.update(mark.exam_id for mark in marks)
    exams = Assessment.query.filter(Assessment.id.in_(exam_ids)).order_by(Assessment.exam_date).all() if exam_ids else []
    published_ids = {exam.id for exam in exams if exam.results_published}
    questions = ScoreItem.query.filter(ScoreItem.exam_id.in_(published_ids)).all() if published_ids else []
    questions_by_exam = {}
    for question in questions:
        questions_by_exam.setdefault(question.exam_id, []).append(question)
    marks_by_question = {
        mark.question_id: mark.marks_awarded
        for mark in marks
        if mark.exam_id in published_ids
    }
    remarks = {
        item.exam_id: item.remark
        for item in ExamNote.query.filter_by(student_id=user_id).all()
        if item.exam_id in published_ids
    }
    return render_template(
        'learner/my_marks.html',
        exams=exams,
        questions_by_exam=questions_by_exam,
        marks_by_question=marks_by_question,
        remarks=remarks
    )


@learner_blueprint.route('/book_slot/<int:slot_id>', methods=['GET'])
def reserve_seat(slot_id):
    if session.get('role') != 'student':
        return redirect(url_for('home_page'))
    student_id = session.get('user_id')
    slot = TimeWindow.query.get(slot_id)
    if not slot:
        return redirect(url_for('learner.learner_home'))
    exam = Assessment.query.get(slot.exam_id)
    already_booked_exam = SeatBooking.query.filter_by(
        student_id=student_id, exam_id=slot.exam_id, status='Booked'
    ).first()
    if booking_is_open(exam) and not window_is_full(slot) and not already_booked_exam:
        booking = SeatBooking(
            slot_id=slot.id,
            exam_id=slot.exam_id,
            student_id=student_id,
            status='Booked'
        )
        db.session.add(booking)
        db.session.flush()
        sync_window_closed(slot)
        db.session.commit()
    return redirect(url_for('learner.learner_home'))


@learner_blueprint.route('/cancel_booking/<int:booking_id>', methods=['GET'])
def drop_booking(booking_id):
    if session.get('role') != 'student':
        return redirect(url_for('home_page'))
    booking = SeatBooking.query.get(booking_id)
    if booking and booking.student_id == session.get('user_id'):
        exam = Assessment.query.get(booking.exam_id)
        if booking.status == 'Booked' and can_cancel_now(exam):
            booking.status = 'Cancelled'
            slot = TimeWindow.query.get(booking.slot_id)
            if slot:
                sync_window_closed(slot)
            db.session.commit()
    return redirect(url_for('learner.list_my_bookings'))


@learner_blueprint.route('/create_profile', methods=['POST', 'GET'])
def make_learner_profile():
    user_id = session.get('user_id')
    user = Account.query.get(user_id)
    profile = LearnerProfile.query.filter_by(user_id=user_id).first()
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
            profile = LearnerProfile(address=address, phone=phone, past_experience=past_experience, user_id=user_id)
            db.session.add(profile)
        db.session.commit()
        return redirect(url_for('learner.learner_home'))
    return render_template('learner/create_profile.html', profile=profile, user=user)


@learner_blueprint.route('/edit_profile', methods=['POST', 'GET'])
def update_learner_profile():
    user_id = session.get('user_id')
    profile = LearnerProfile.query.filter_by(user_id=user_id).first()
    if request.method == 'POST':
        address = request.form['address']
        phone = request.form['phone']
        past_experience = request.form['past_experience']
        profile.address = address
        profile.phone = phone
        profile.past_experience = past_experience
        db.session.commit()
        return redirect(url_for('learner.learner_home'))
    return render_template('learner/edit_profile.html', profile=profile)
