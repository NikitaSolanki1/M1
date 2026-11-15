from datetime import date

from extension import db
from models import SeatBooking


def assessment_stage(exam, today=None):
    today = today or date.today()
    if not exam:
        return 'Draft'
    if exam.exam_date and exam.exam_date < today:
        return 'Completed'
    if booking_is_open(exam, today):
        return 'Booking Open'
    if getattr(exam, 'is_slot_creation_open', False):
        return 'Slot Creation'
    if exam.booking_close_date and today > exam.booking_close_date:
        return 'Closed'
    if exam.is_booking_open and exam.booking_open_date and today < exam.booking_open_date:
        return 'Booking scheduled'
    if exam.booking_open_date and today >= exam.booking_open_date:
        return 'Closed'
    return 'Draft'


def booking_is_open(exam, today=None):
    today = today or date.today()
    if not exam or not exam.is_booking_open:
        return False
    if exam.booking_close_date and today > exam.booking_close_date:
        return False
    if exam.booking_open_date and today < exam.booking_open_date:
        from models import TimeWindow
        if not TimeWindow.query.filter_by(exam_id=exam.id).first():
            return False
    return True


def live_booking_counts():
    rows = SeatBooking.query.filter_by(status='Booked').all()
    counts = {}
    for row in rows:
        counts[row.slot_id] = counts.get(row.slot_id, 0) + 1
    return counts


def booked_seats(slot, counts=None):
    counts = live_booking_counts() if counts is None else counts
    return counts.get(slot.id, 0)


def window_is_full(slot, counts=None):
    return booked_seats(slot, counts) >= (slot.capacity or 1)


def sync_window_closed(slot, counts=None):
    slot.is_closed = window_is_full(slot, counts)


def finish_old_bookings(bookings, exams, slots, today=None):
    today = today or date.today()
    changed = False
    for booking in bookings:
        if booking.status != 'Booked':
            continue
        exam = exams.get(booking.exam_id)
        slot = slots.get(booking.slot_id)
        exam_done = exam and exam.exam_date and exam.exam_date < today
        slot_done = slot and slot.slot_date and slot.slot_date < today
        if exam_done or slot_done:
            booking.status = 'Completed'
            changed = True
    if changed:
        db.session.commit()


def booking_label(booking):
    return booking.status if booking and booking.status else 'Booked'
