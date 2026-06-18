"""
Supplier blueprint — quote submission, dispatch, fleet, compliance.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, date

from app.models import (db, Booking, Quote, SupplierProfile, Driver,
                         Vehicle, BookingStatusEvent, AvailabilitySlot,
                         SupplierScoreHistory, User)
from app.services.ai_engine import score_quotes
from app.services.v19_adapter import booking_to_v19, quote_to_v19
from app.services.notifications import push_notification
from app.services.audit import log_action

supplier_bp = Blueprint("supplier", __name__)


def supplier_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "supplier":
            flash("Access denied.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def get_supplier():
    return SupplierProfile.query.filter_by(user_id=current_user.id).first_or_404()


# ── Dashboard ─────────────────────────────────────────────────────────────────

@supplier_bp.route("/")
@supplier_required
def dashboard():
    supplier = get_supplier()
    active_bookings = supplier.bookings.filter(
        Booking.status.in_(["Confirmed","Driver Assigned","Collected","In Transit"])).all()
    pending_quotes  = supplier.quotes.filter_by(status="Pending").count()
    total_jobs      = supplier.total_jobs
    revenue         = db.session.query(db.func.sum(Booking.supplier_payout))\
                        .filter_by(supplier_id=supplier.id).scalar() or 0
    fleet_available = supplier.vehicles.filter_by(availability="Available").count()
    drivers_active  = supplier.drivers.filter_by(status="Active").count()
    score_hist      = supplier.score_history.order_by(
                        SupplierScoreHistory.recorded_at).limit(6).all()
        # Build v19-compatible fleet and pending booking lists
    fleet_v19 = [{"type": v.vehicle_type, "reg": v.reg_number, "payload": f"{v.payload_ton}T",
                   "cbm": f"{v.cbm} CBM", "availability": v.availability}
                  for v in supplier.vehicles.limit(5).all()]
    rate_cards = [{"route": "Durban → Johannesburg", "version": "v2.1", "vehicleType": "Superlink",
                    "baseRate": 14800, "minimumCharge": 12000, "fuelSurcharge": 8}]
    pending_v19 = [{"ref": b.ref, "route": b.route, "shipper": b.shipper.user.full_name if b.shipper and b.shipper.user else "—",
                     "supplierResponseWindow": "4h remaining", "status": b.status}
                    for b in supplier.bookings.filter_by(status="Confirmed").limit(5).all()]
    return render_template("supplier/dashboard.html",
        title="Supplier Dashboard",
        supplier=supplier, active_bookings=[booking_to_v19(b) for b in active_bookings],
        pending=pending_v19, fleet=fleet_v19, rate_cards=rate_cards,
        pending_quotes=pending_quotes, total_jobs=total_jobs,
        revenue=revenue, fleet_available=fleet_available,
        drivers_active=drivers_active, score_hist=score_hist)


# ── Quotes ────────────────────────────────────────────────────────────────────

@supplier_bp.route("/quote-requests")
@supplier_required
def quote_requests():
    supplier = get_supplier()
    if supplier.status != "Active":
        flash("Your account is under review. You'll be able to submit quotes once approved.", "warning")
        return render_template("supplier/bookings.html",
            title="Quote Requests",
            supplier=supplier, bookings=[], quoted_refs=[])

    # All open bookings needing quotes
    bookings    = Booking.query.filter_by(status="Pending Quotes").order_by(
                    Booking.created_at.desc()).all()
    quoted_refs = {q.booking_id for q in supplier.quotes.all()}
    return render_template("supplier/bookings.html",
        title="Quote Requests",
        supplier=supplier,
        bookings=[booking_to_v19(b) for b in bookings],
        quoted_refs=quoted_refs)


@supplier_bp.route("/quote-requests/<int:booking_id>/submit", methods=["POST"])
@supplier_required
def submit_quote(booking_id):
    supplier = get_supplier()
    booking  = Booking.query.get_or_404(booking_id)

    # Check not already quoted
    existing = Quote.query.filter_by(booking_id=booking_id,
                                      supplier_id=supplier.id).first()
    if existing:
        flash("You have already submitted a quote for this booking.", "warning")
        return redirect(url_for("supplier.quote_requests"))

    amount       = float(request.form.get("amount", 0))
    transit_days = int(request.form.get("transit_days", 1))
    notes        = request.form.get("notes", "")

    if amount <= 0:
        flash("Quote amount must be greater than zero.", "error")
        return redirect(url_for("supplier.quote_requests"))

    q = Quote(booking_id=booking_id, supplier_id=supplier.id,
              amount=amount, transit_days=transit_days, notes=notes)
    db.session.add(q)
    booking.status = "Quotes Received"

    # Notify shipper
    push_notification(booking.shipper.user_id,
                      f"New quote received for {booking.ref}",
                      f"{supplier.company_name} quoted R{amount:,.2f} for {booking.route}.",
                      type="info", ref_type="booking", ref_id=booking.ref)

    db.session.commit()
    log_action(current_user.id, "SUBMIT_QUOTE", "Booking", booking.ref,
               f"Amount R{amount:,.2f}")
    flash(f"Quote of R{amount:,.2f} submitted for {booking.ref}.", "success")
    return redirect(url_for("supplier.quote_requests"))


# ── Active Bookings ───────────────────────────────────────────────────────────

@supplier_bp.route("/bookings")
@supplier_required
def bookings():
    supplier = get_supplier()
    status   = request.args.get("status", "")
    query    = supplier.bookings.order_by(Booking.created_at.desc())
    if status:
        query = query.filter_by(status=status)
    return render_template("supplier/bookings.html",
        title="Bookings",
        supplier=supplier,
        bookings=[booking_to_v19(b) for b in query.all()],
        status_filter=status)


# ── Dispatch ──────────────────────────────────────────────────────────────────

@supplier_bp.route("/dispatch")
@supplier_required
def dispatch():
    supplier = get_supplier()
    pending  = supplier.bookings.filter(
        Booking.status.in_(["Confirmed","Pending Dispatch"])).all()
    drivers  = supplier.drivers.filter_by(status="Active").all()
    fleet    = supplier.vehicles.filter_by(availability="Available").all()
    return render_template("supplier/dispatch.html",
        title="Dispatch Centre",
        supplier=supplier,
        pending_jobs=[booking_to_v19(b) for b in pending],
        available_drivers=drivers, available_fleet=fleet)


@supplier_bp.route("/dispatch/<ref>/assign", methods=["POST"])
@supplier_required
def dispatch_assign(ref):
    supplier = get_supplier()
    booking  = Booking.query.filter_by(ref=ref, supplier_id=supplier.id).first_or_404()
    driver_id  = request.form.get("driver_id")
    vehicle_id = request.form.get("vehicle_id")

    if driver_id:
        driver = Driver.query.filter_by(id=driver_id, supplier_id=supplier.id).first()
        if driver:
            booking.driver_id = driver.id
            driver.status = "On Trip"

    if vehicle_id:
        vehicle = Vehicle.query.filter_by(id=vehicle_id, supplier_id=supplier.id).first()
        if vehicle:
            booking.vehicle_id = vehicle.id
            vehicle.availability = "On Trip"

    booking.status = "Driver Assigned"
    event = BookingStatusEvent(booking_id=booking.id, status="Driver Assigned",
                                note=f"Driver and vehicle assigned by {supplier.company_name}",
                                actor=current_user.full_name)
    db.session.add(event)

    push_notification(booking.shipper.user_id,
                      f"Driver assigned — {booking.ref}",
                      f"A driver has been assigned for your shipment from {booking.collection_city}.",
                      type="success", ref_type="booking", ref_id=booking.ref)

    db.session.commit()
    log_action(current_user.id, "DISPATCH", "Booking", ref)
    flash(f"Driver assigned for {ref}.", "success")
    return redirect(url_for("supplier.dispatch"))


@supplier_bp.route("/bookings/<ref>/update-status", methods=["POST"])
@supplier_required
def update_status(ref):
    supplier  = get_supplier()
    booking   = Booking.query.filter_by(ref=ref, supplier_id=supplier.id).first_or_404()
    new_status = request.form.get("status")
    note       = request.form.get("note", "")
    valid = ["Collected","In Transit","Approaching Destination","Delivered"]

    if new_status not in valid:
        flash("Invalid status.", "error")
        return redirect(url_for("supplier.bookings"))

    booking.status = new_status
    if new_status == "Collected":
        booking.collected_at = datetime.utcnow()
    elif new_status == "Delivered":
        booking.delivered_at = datetime.utcnow()
        booking.pod_signed   = True
        booking.pod_signed_at = datetime.utcnow()
        # Update supplier stats
        supplier.total_jobs   += 1
        supplier.on_time_jobs += 1
        # Recalc score
        new_score = min(5.0, supplier.score + 0.02)
        supplier.score = round(new_score, 2)
        hist = SupplierScoreHistory(supplier_id=supplier.id, score=supplier.score,
                                     on_time_rate=supplier.on_time_rate)
        db.session.add(hist)

    event = BookingStatusEvent(booking_id=booking.id, status=new_status,
                                note=note, actor=current_user.full_name)
    db.session.add(event)

    push_notification(booking.shipper.user_id,
                      f"Shipment update — {booking.ref}",
                      f"Status changed to: {new_status}.",
                      type="info", ref_type="booking", ref_id=booking.ref)

    db.session.commit()
    flash(f"Status updated to {new_status}.", "success")
    return redirect(url_for("supplier.bookings"))


# ── Fleet ─────────────────────────────────────────────────────────────────────

@supplier_bp.route("/fleet")
@supplier_required
def fleet():
    supplier = get_supplier()
    vehicles = supplier.vehicles.all()
    return render_template("supplier/fleet.html", title="Fleet", supplier=supplier, vehicles=vehicles)


@supplier_bp.route("/fleet/add", methods=["POST"])
@supplier_required
def add_vehicle():
    supplier = get_supplier()
    reg      = request.form.get("reg_number","").strip().upper()
    if Vehicle.query.filter_by(reg_number=reg).first():
        flash(f"Vehicle {reg} already exists.", "error")
        return redirect(url_for("supplier.fleet"))
    v = Vehicle(
        supplier_id  = supplier.id,
        reg_number   = reg,
        vehicle_type = request.form.get("vehicle_type",""),
        payload_ton  = float(request.form.get("payload_ton", 0) or 0),
        cbm          = float(request.form.get("cbm", 0) or 0),
        year         = int(request.form.get("year", 2020) or 2020),
    )
    rw = request.form.get("roadworthy_expiry","")
    if rw:
        v.roadworthy_expiry = date.fromisoformat(rw)
    db.session.add(v)
    db.session.commit()
    flash(f"Vehicle {reg} added.", "success")
    return redirect(url_for("supplier.fleet"))


@supplier_bp.route("/fleet/<int:vid>/delete", methods=["POST"])
@supplier_required
def delete_vehicle(vid):
    supplier = get_supplier()
    v = Vehicle.query.filter_by(id=vid, supplier_id=supplier.id).first_or_404()
    db.session.delete(v)
    db.session.commit()
    flash("Vehicle removed.", "info")
    return redirect(url_for("supplier.fleet"))


# ── Drivers ───────────────────────────────────────────────────────────────────

@supplier_bp.route("/drivers")
@supplier_required
def drivers():
    supplier = get_supplier()
    return render_template("supplier/drivers.html",
        title="Drivers", supplier=supplier, drivers=supplier.drivers.all())


@supplier_bp.route("/drivers/add", methods=["POST"])
@supplier_required
def add_driver():
    supplier = get_supplier()
    d = Driver(
        supplier_id  = supplier.id,
        name         = request.form.get("name","").strip(),
        id_number    = request.form.get("id_number","").strip(),
        license_code = request.form.get("license_code","EC"),
        phone        = request.form.get("phone","").strip(),
    )
    exp = request.form.get("license_expiry","")
    if exp:
        d.license_expiry = date.fromisoformat(exp)
    db.session.add(d)
    db.session.commit()
    flash(f"Driver {d.name} added.", "success")
    return redirect(url_for("supplier.drivers"))


# ── Availability ──────────────────────────────────────────────────────────────

@supplier_bp.route("/availability")
@supplier_required
def availability():
    supplier = get_supplier()
    slots    = supplier.availability.order_by(AvailabilitySlot.date).all()
    return render_template("supplier/availability.html",
        title="Availability", supplier=supplier, slots=slots)


@supplier_bp.route("/availability/add", methods=["POST"])
@supplier_required
def add_availability():
    supplier = get_supplier()
    slot = AvailabilitySlot(
        supplier_id  = supplier.id,
        date         = date.fromisoformat(request.form.get("date")),
        vehicle_type = request.form.get("vehicle_type",""),
        slots_total  = int(request.form.get("slots", 1)),
        note         = request.form.get("note",""),
    )
    db.session.add(slot)
    db.session.commit()
    flash("Availability slot added.", "success")
    return redirect(url_for("supplier.availability"))


# ── Performance ───────────────────────────────────────────────────────────────

@supplier_bp.route("/performance")
@supplier_required
def performance():
    supplier   = get_supplier()
    score_hist = supplier.score_history.order_by(
                    SupplierScoreHistory.recorded_at).all()
    platform_settings = {
        "delayUnder1hDeduction":    0.05,
        "delay1to3hDeduction":      0.10,
        "delayOver3hDeduction":     0.20,
        "dcSlotMissedDeduction":    0.25,
        "bookingRejectedDeduction": 0.15,
        "bookingTimedOutDeduction": 0.10,
        "cargoDamageDeduction":     0.50,
        "fiveStarBonus":            0.10,
        "oneStarDeduction":         0.20,
        "newSupplierStartScore":    4.0,
        "rollingWindowBookings":    50,
    }
    return render_template("supplier/performance.html",
        title="Performance", supplier=supplier,
        score_hist=score_hist, min_score=3.0, settings=platform_settings)


# ── Complaints ─────────────────────────────────────────────────────────────────

from app.models import Complaint  # local import

@supplier_bp.route("/complaints")
@supplier_required
def complaints():
    supplier = get_supplier()
    # Only show complaints that admin has forwarded to this supplier
    forwarded = supplier.complaints.filter(
        Complaint.status.in_(["Forwarded to Supplier", "Supplier Responded", "Resolved", "Closed"])
    ).order_by(Complaint.created_at.desc()).all()
    return render_template("supplier/complaints.html",
        title="Complaints", complaints=forwarded)


@supplier_bp.route("/complaints/<ref>", methods=["GET", "POST"])
@supplier_required
def complaint_detail(ref):
    supplier = get_supplier()
    c = Complaint.query.filter_by(ref=ref, supplier_id=supplier.id).first_or_404()

    # Supplier may only view/respond if forwarded
    if c.status not in ("Forwarded to Supplier", "Supplier Responded", "Resolved", "Closed"):
        flash("This complaint is not yet available for your review.", "warning")
        return redirect(url_for("supplier.complaints"))

    if request.method == "POST":
        response_text = request.form.get("supplier_response", "").strip()
        if response_text:
            c.supplier_response    = response_text
            c.supplier_responded_at = datetime.utcnow()
            c.status               = "Supplier Responded"
            db.session.commit()

            # Notify admins
            admins = User.query.filter_by(role="admin").all()
            for adm in admins:
                push_notification(adm.id,
                    f"Supplier responded — {c.ref}",
                    f"{supplier.company_name} has submitted their response to complaint {c.ref}.",
                    notif_type="info", ref_type="complaint", ref_id=c.ref)

            flash("Your response has been submitted. Admin will review and resolve the complaint.", "success")
            return redirect(url_for("supplier.complaint_detail", ref=ref))
        else:
            flash("Please enter a response before submitting.", "error")

    return render_template("supplier/complaint_detail.html",
        title=f"Complaint {ref}", complaint=c)
