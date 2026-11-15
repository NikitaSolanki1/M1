from models import *
from flask import Blueprint
control_blueprint = Blueprint('control', __name__)


@control_blueprint.route('/admin_dashboard', methods=['POST', 'GET'])
def control_home():
    course_count = Subject.query.count()
    exam_count = Assessment.query.count()
    student_count = Account.query.filter_by(role='student').count()
    examinor_count = Account.query.filter_by(role='examinor').count()
    return render_template(
        '/control/admin_dashboard.html',
        course_count=course_count,
        exam_count=exam_count,
        student_count=student_count,
        examinor_count=examinor_count
    )


@control_blueprint.route('/manage_courses', methods=['POST', 'GET'])
def list_subjects():
    courses = Subject.query.all()
    print(courses)

    return render_template('/control/manage_courses.html', courses=courses)


def _search_term():
    return (request.args.get('q') or '').strip()


def _name_or_id_match(term, record_id, name):
    if not term:
        return True
    if term.isdigit() and int(term) == record_id:
        return True
    return term.lower() in (name or '').lower()


def _seat_matches(term, booking, exam, student):
    if not term:
        return True
    if _name_or_id_match(term, booking.id, ''):
        return True
    if student and _name_or_id_match(term, student.id, student.name):
        return True
    if exam and _name_or_id_match(term, exam.id, exam.exam_name):
        return True
    return False


@control_blueprint.route('/manage_exams', methods=['POST', 'GET'])
def list_assessments():
    q = _search_term()
    exams = [exam for exam in Assessment.query.all() if _name_or_id_match(q, exam.id, exam.exam_name)]
    phases = {exam.id: assessment_stage(exam) for exam in exams}
    return render_template('/control/manage_exams.html', exams=exams, q=q, phases=phases)


@control_blueprint.route('/edit_course/<int:id>', methods=['POST', 'GET'])
def update_subject(id):
    if request.method == 'POST':
        course_name = request.form['course_name']
        course_description = request.form['course_description']
        course_duration = request.form['course_duration']
        course = Subject.query.get(id)
        course.coures_name = course_name
        course.coures_description = course_description
        course.course_duration = course_duration
        db.session.commit()
        return redirect(url_for('control.control_home'))
    course = Subject.query.get(id)
    return render_template('/control/edit_course.html', course=course)


@control_blueprint.route('/create_course', methods=['POST', 'GET'])
def add_subject():
    if request.method == 'POST':
        course_name = request.form['course_name']
        course_description = request.form['course_description']
        course_duration = request.form['course_duration']
        course = Subject(coures_name=course_name, coures_description=course_description, course_duration=course_duration)
        db.session.add(course)
        db.session.commit()
        return redirect(url_for('control.control_home'))
    return render_template('/control/create_course.html')


@control_blueprint.route('/delete/<int:id>', methods=['POST', 'GET'])
def remove_subject(id):
    exams = Assessment.query.filter_by(coures_id=id).all()
    for exam in exams:
        ScoreItem.query.filter_by(exam_id=exam.id).delete()
        MarkAward.query.filter_by(exam_id=exam.id).delete()
        ExamNote.query.filter_by(exam_id=exam.id).delete()
        SeatBooking.query.filter_by(exam_id=exam.id).delete()
        TimeWindow.query.filter_by(exam_id=exam.id).delete()
        db.session.delete(exam)
    course = Subject.query.get(id)
    db.session.delete(course)
    db.session.commit()
    return redirect(url_for('control.list_subjects'))


from datetime import datetime
from schedule_helpers import assessment_stage, booking_label, sync_window_closed, window_is_full, finish_old_bookings
from flask import request, render_template, redirect, url_for


def _date_order_error(exam_date, slot_start, slot_end, booking_open, booking_close):
    if slot_end < slot_start:
        return 'Slot creation end date must be on or after the start date.'
    if booking_open <= slot_end:
        return 'Booking must open after the slot creation end date.'
    if booking_close < booking_open:
        return 'Booking close date must be on or after the date booking opens.'
    if exam_date < booking_close:
        return 'Exam date must be on or after the day booking closes.'
    return None


@control_blueprint.route('/create_exam', methods=['POST', 'GET'])
def add_assessment():

    examinors = Account.query.filter_by(role='examinor').all()
    courses = Subject.query.all()

    if request.method == 'POST':

        exam_name = request.form['exam_name']
        exam_description = request.form['exam_description']

        exam_date = datetime.strptime(
            request.form['exam_date'], '%Y-%m-%d'
        ).date()

        booking_open_date = datetime.strptime(
            request.form['booking_open_date'], '%Y-%m-%d'
        ).date()
        booking_close_date = datetime.strptime(
            request.form['booking_close_date'], '%Y-%m-%d'
        ).date()
        slot_creation_start_date = datetime.strptime(
            request.form['slot_creation_start_date'], '%Y-%m-%d'
        ).date()
        slot_creation_end_date = datetime.strptime(
            request.form['slot_creation_end_date'], '%Y-%m-%d'
        ).date()
        date_error = _date_order_error(
            exam_date,
            slot_creation_start_date,
            slot_creation_end_date,
            booking_open_date,
            booking_close_date,
        )
        if date_error:
            return render_template(
                '/control/create_exam.html',
                examinors=examinors,
                courses=courses,
                error=date_error
            )

        exam_duration = int(request.form['exam_duration'])
        examinor_id = int(request.form['examinor_id'])
        user = Account.query.get(examinor_id)
        examinor_name = user.name
        course_id = int(request.form['course_id'])

        exam = Assessment(
            exam_name=exam_name,
            exam_description=exam_description,
            exam_date=exam_date,
            exam_time=datetime.strptime('00:00', '%H:%M').time(),
            exam_duration=exam_duration,
            slot_start_time=datetime.strptime('00:00', '%H:%M').time(),
            slot_end_time=datetime.strptime('00:00', '%H:%M').time(),
            slot_creation_start_date=slot_creation_start_date,
            slot_creation_end_date=slot_creation_end_date,
            booking_start_time=datetime.strptime('00:00', '%H:%M').time(),
            booking_end_time=datetime.strptime('00:00', '%H:%M').time(),
            booking_open_date=booking_open_date,
            booking_close_date=booking_close_date,
            examinor_id=examinor_id,
            coures_id=course_id,
            examinor_name=examinor_name
        )

        db.session.add(exam)
        db.session.commit()

        return redirect(url_for('control.control_home'))

    return render_template(
        '/control/create_exam.html',
        examinors=examinors,
        courses=courses
    )


@control_blueprint.route('/create_rubric/<int:id>', methods=['POST', 'GET'])
def add_score_item(id):
    if request.method == 'POST':
        question = request.form['question']
        marks = request.form['marks']
        exam_id = request.form['exam_id']
        rubric = ScoreItem(question=question, marks=marks, exam_id=exam_id)
        db.session.add(rubric)
        db.session.commit()
        return redirect(url_for('control.control_home'))

    return render_template('/control/create_rubic.html', id=id)


@control_blueprint.route('/manage_rubric/<int:id>', methods=['POST', 'GET'])
def list_score_items(id):
    questions = ScoreItem.query.filter_by(exam_id=id).all()
    return render_template('/control/manage_rubric.html', questions=questions, exam_id=id)


@control_blueprint.route('/edit_rubric/<int:id>', methods=['POST', 'GET'])
def update_score_item(id):
    rubric = ScoreItem.query.get(id)
    if request.method == 'POST':
        rubric.question = request.form['question']
        rubric.marks = request.form['marks']
        db.session.commit()
        return redirect(url_for('control.list_score_items', id=rubric.exam_id))
    return render_template('/control/edit_rubric.html', rubric=rubric)


@control_blueprint.route('/delete_rubric/<int:id>', methods=['POST', 'GET'])
def remove_score_item(id):
    rubric = ScoreItem.query.get(id)
    exam_id = rubric.exam_id
    MarkAward.query.filter_by(question_id=rubric.id).delete()
    db.session.delete(rubric)
    db.session.commit()
    return redirect(url_for('control.list_score_items', id=exam_id))


def _assessment_edit_data(exam):
    examinors = Account.query.filter_by(role='examinor').all()
    courses = Subject.query.all()
    booked_rows = db.session.query(Assessment.id, Assessment.examinor_id).join(
        SeatBooking, SeatBooking.exam_id == Assessment.id
    ).all()
    this_exam_booked = any(row.id == exam.id for row in booked_rows)
    busy_examiner_ids = {row.examinor_id for row in booked_rows if row.id != exam.id}
    return examinors, courses, busy_examiner_ids, this_exam_booked


@control_blueprint.route('/edit_exam/<int:id>', methods=['POST', 'GET'])
def update_assessment(id):
    exam = Assessment.query.get(id)
    examinors, courses, busy_examiner_ids, this_exam_booked = _assessment_edit_data(exam)

    def show(error=None):
        return render_template(
            '/control/edit_exam.html',
            exam=exam,
            examinors=examinors,
            courses=courses,
            error=error,
            busy_examiner_ids=busy_examiner_ids,
            this_exam_booked=this_exam_booked
        )

    if request.method == 'POST':
        examinor_id = int(request.form['examinor_id'])
        if examinor_id != exam.examinor_id:
            if this_exam_booked:
                return show('Students have booked slots for this exam. Delete this examination before changing the examiner.')
            if examinor_id in busy_examiner_ids:
                return show('That examiner is not free. They have booked slots on another examination. Delete that examination first.')
        exam.exam_name = request.form['exam_name']
        exam.exam_description = request.form['exam_description']
        exam.exam_date = datetime.strptime(request.form['exam_date'], '%Y-%m-%d').date()
        slot_creation_start_date = datetime.strptime(request.form['slot_creation_start_date'], '%Y-%m-%d').date()
        slot_creation_end_date = datetime.strptime(request.form['slot_creation_end_date'], '%Y-%m-%d').date()
        booking_open_date = datetime.strptime(request.form['booking_open_date'], '%Y-%m-%d').date()
        booking_close_date = datetime.strptime(request.form['booking_close_date'], '%Y-%m-%d').date()
        date_error = _date_order_error(
            exam.exam_date,
            slot_creation_start_date,
            slot_creation_end_date,
            booking_open_date,
            booking_close_date,
        )
        if date_error:
            return show(date_error)
        exam.slot_creation_start_date = slot_creation_start_date
        exam.slot_creation_end_date = slot_creation_end_date
        exam.booking_open_date = booking_open_date
        exam.booking_close_date = booking_close_date
        exam.exam_duration = int(request.form['exam_duration'])
        examinor_id = int(request.form['examinor_id'])
        user = Account.query.get(examinor_id)
        exam.examinor_id = examinor_id
        exam.examinor_name = user.name
        exam.coures_id = int(request.form['course_id'])
        db.session.commit()
        return redirect(url_for('control.list_assessments'))

    return show()


@control_blueprint.route('/delete_exam/<int:id>', methods=['POST', 'GET'])
def remove_assessment(id):
    ScoreItem.query.filter_by(exam_id=id).delete()
    MarkAward.query.filter_by(exam_id=id).delete()
    ExamNote.query.filter_by(exam_id=id).delete()
    SeatBooking.query.filter_by(exam_id=id).delete()
    TimeWindow.query.filter_by(exam_id=id).delete()
    exam = Assessment.query.get(id)
    db.session.delete(exam)
    db.session.commit()
    return redirect(url_for('control.list_assessments'))


@control_blueprint.route('/open_slot_creation/<int:id>')
def enable_slot_making(id):
    exam = Assessment.query.get(id)
    if exam:
        exam.is_slot_creation_open = True
        db.session.commit()
    return redirect(url_for('control.list_assessments'))


@control_blueprint.route('/close_slot_creation/<int:id>')
def disable_slot_making(id):
    exam = Assessment.query.get(id)
    if exam:
        exam.is_slot_creation_open = False
        db.session.commit()
    return redirect(url_for('control.list_assessments'))


@control_blueprint.route('/open_booking/<int:id>')
def enable_booking(id):
    exam = Assessment.query.get(id)
    if exam:
        exam.is_booking_open = True
        db.session.commit()
    return redirect(url_for('control.list_assessments'))


@control_blueprint.route('/close_booking/<int:id>')
def disable_booking(id):
    exam = Assessment.query.get(id)
    if exam:
        exam.is_booking_open = False
        db.session.commit()
        return redirect(url_for('control.list_assessments'))


@control_blueprint.route('/publish_results/<int:id>', methods=['GET', 'POST'])
def show_results(id):
    exam = Assessment.query.get(id)
    if exam:
        exam.results_published = True
        db.session.commit()
    return redirect(url_for('control.list_assessments'))


@control_blueprint.route('/hide_results/<int:id>', methods=['GET', 'POST'])
def hide_results(id):
    exam = Assessment.query.get(id)
    if exam:
        exam.results_published = False
        db.session.commit()
    return redirect(url_for('control.list_assessments'))


@control_blueprint.route('/view_bookings', methods=['GET'])
def list_seat_bookings():
    q = _search_term()
    all_bookings = SeatBooking.query.all()
    exams = {exam.id: exam for exam in Assessment.query.all()}
    students = {user.id: user for user in Account.query.filter(Account.role == 'student').all()}
    bookings = [
        booking for booking in all_bookings
        if _seat_matches(q, booking, exams.get(booking.exam_id), students.get(booking.student_id))
    ]
    slots = {slot.id: slot for slot in TimeWindow.query.filter(TimeWindow.id.in_([booking.slot_id for booking in bookings])).all()} if bookings else {}
    profiles = {profile.user_id: profile for profile in LearnerProfile.query.filter(LearnerProfile.user_id.in_([booking.student_id for booking in bookings])).all()} if bookings else {}
    finish_old_bookings(bookings, exams, slots)
    return render_template(
        '/control/view_bookings.html',
        bookings=bookings,
        exams=exams,
        slots=slots,
        students=students,
        profiles=profiles,
        q=q,
        display_status=booking_label
    )


@control_blueprint.route('/reschedule_booking/<int:booking_id>', methods=['GET', 'POST'])
def move_seat_booking(booking_id):
    booking = SeatBooking.query.get(booking_id)
    exam = Assessment.query.get(booking.exam_id) if booking else None
    if not booking or not exam or booking.status == 'Cancelled':
        return redirect(url_for('control.list_seat_bookings'))
    all_slots = TimeWindow.query.filter_by(exam_id=exam.id).order_by(TimeWindow.slot_date, TimeWindow.slot_time).all()
    slots = [
        slot for slot in all_slots
        if slot.id == booking.slot_id or not window_is_full(slot)
    ]
    error = None
    if request.method == 'POST':
        slot = TimeWindow.query.get(request.form.get('slot_id'))
        if not slot or slot.exam_id != exam.id or slot.created_by != exam.examinor_id:
            error = 'Choose a date the examiner created for this exam.'
        elif slot.id != booking.slot_id and window_is_full(slot):
            error = 'That date is full. Choose a free date.'
        else:
            old = TimeWindow.query.get(booking.slot_id)
            booking.slot_id = slot.id
            booking.status = 'Booked'
            db.session.flush()
            sync_window_closed(slot)
            if old:
                sync_window_closed(old)
            db.session.commit()
            return redirect(url_for('control.list_seat_bookings'))
    return render_template(
        '/control/reschedule_booking.html',
        booking=booking,
        exam=exam,
        slots=slots,
        error=error
    )


@control_blueprint.route('/cancel_booking/<int:booking_id>')
def cancel_seat_booking(booking_id):
    booking = SeatBooking.query.get(booking_id)
    if booking and booking.status == 'Booked':
        booking.status = 'Cancelled'
        slot = TimeWindow.query.get(booking.slot_id)
        if slot:
            sync_window_closed(slot)
        db.session.commit()
    return redirect(url_for('control.list_seat_bookings'))


@control_blueprint.route('/manage_examinors', methods=['POST', 'GET'])
def list_markers():
    q = _search_term()
    examinors = [
        user for user in Account.query.filter_by(role='examinor').all()
        if _name_or_id_match(q, user.id, user.name)
    ]
    return render_template('/control/manage_examinors.html', examinors=examinors, q=q)


@control_blueprint.route('/edit_examinor/<int:id>', methods=['POST', 'GET'])
def update_marker(id):
    examinor = Account.query.get(id)
    return render_template('/control/edit_examinor.html', examinor=examinor)


@control_blueprint.route('/approve_examinor/<int:id>', methods=['POST', 'GET'])
def approve_marker(id):
    examinor = Account.query.get(id)
    examinor.is_verified = True
    db.session.commit()
    return redirect(url_for('control.list_markers'))


@control_blueprint.route('/manage_users', methods=['POST', 'GET'])
def list_learners():
    q = _search_term()
    users = [
        user for user in Account.query.filter(Account.role.in_(['student'])).all()
        if _name_or_id_match(q, user.id, user.name)
    ]
    return render_template('/control/manage_users.html', users=users, q=q)


@control_blueprint.route('/user_details/<int:id>', methods=['GET'])
def learner_info(id):
    user = Account.query.get(id)
    profile = LearnerProfile.query.filter_by(user_id=id).first()
    return render_template('/control/user_details.html', user=user, profile=profile)


@control_blueprint.route('/block_user/<int:id>')
def block_account(id):
    user = Account.query.get(id)
    user.is_active = False
    db.session.commit()
    if user.role == 'examinor':
        return redirect(url_for('control.list_markers'))
    return redirect(url_for('control.list_learners'))


@control_blueprint.route('/unblock_user/<int:id>')
def unblock_account(id):
    user = Account.query.get(id)
    user.is_active = True
    db.session.commit()
    if user.role == 'examinor':
        return redirect(url_for('control.list_markers'))
    return redirect(url_for('control.list_learners'))
