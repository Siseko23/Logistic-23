"""Driver blueprint"""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime

from app.models import db, Booking, Driver, BookingStatusEvent
from app.services.notifications import push_notification

driver_bp = Blueprint("driver", __name__)

def driver_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "driver":
            flash("Access denied.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated

@driver_bp.route("/")
@driver_required
def dashboard():
    driver   = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    active   = driver.bookings.filter(
                Booking.status.in_(["Driver Assigned","Collected","In Transit"])).all()
    completed = driver.bookings.filter_by(status="Delivered").count()
    return render_template("driver/dashboard.html",
        driver=driver, active_bookings=active, completed=completed)

@driver_bp.route("/bookings/<ref>/update", methods=["POST"])
@driver_required
def update_status(ref):
    driver  = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    booking = Booking.query.filter_by(ref=ref, driver_id=driver.id).first_or_404()
    new_status = request.form.get("status")
    note       = request.form.get("note","")
    valid      = ["Collected","In Transit","Approaching Destination","Delivered"]
    if new_status in valid:
        booking.status = new_status
        if new_status == "Delivered":
            booking.delivered_at = datetime.utcnow()
            booking.pod_signed   = True
            driver.total_trips  += 1
        event = BookingStatusEvent(booking_id=booking.id, status=new_status,
                                    note=note, actor=current_user.full_name)
        db.session.add(event)
        push_notification(booking.shipper.user_id, f"Shipment update — {booking.ref}",
                          f"Your shipment status: {new_status}",
                          type="info", ref_type="booking", ref_id=booking.ref)
        db.session.commit()
        flash(f"Status updated to {new_status}.", "success")
    return redirect(url_for("driver.dashboard"))
