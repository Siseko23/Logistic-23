"""
Shipper blueprint — all routes backed by real SQLAlchemy queries.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from datetime import date, datetime, timedelta
from functools import wraps
import io, csv

from app.models import (db, Booking, Quote, Invoice, Notification,
                         ShipperProfile, SupplierProfile, AddressBook,
                         BookingStatusEvent, User)
from app.services.ai_engine import score_quotes, explain_rank, compute_health_score
from app.services.notifications import push_notification
from app.services.v19_adapter import booking_to_v19, quote_to_v19
from app.services.audit import log_action

shipper_bp = Blueprint("shipper", __name__)


def shipper_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "shipper":
            flash("Access denied.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def get_shipper():
    return ShipperProfile.query.filter_by(user_id=current_user.id).first_or_404()


# ── Dashboard ─────────────────────────────────────────────────────────────────

@shipper_bp.route("/")
@shipper_required
def dashboard():
    shipper = get_shipper()
    bookings = shipper.bookings.order_by(Booking.created_at.desc()).limit(5).all()
    total_bookings = shipper.bookings.count()
    active = shipper.bookings.filter(
        Booking.status.in_(["Confirmed","Driver Assigned","Collected","In Transit"])).count()
    delivered = shipper.bookings.filter_by(status="Delivered").count()
    total_spend = db.session.query(db.func.sum(Booking.quoted_value))\
                    .filter_by(shipper_id=shipper.id).scalar() or 0
    notifications = current_user.notifications.filter_by(is_read=False)\
                        .order_by(Notification.created_at.desc()).limit(5).all()
    return render_template("shipper/dashboard.html",
        title="Dashboard",
        shipper=shipper,
        bookings=[booking_to_v19(b) for b in bookings],
        total_bookings=total_bookings, active=active,
        delivered=delivered, total_spend=total_spend,
        notifications=notifications)


# ── Bookings ──────────────────────────────────────────────────────────────────

@shipper_bp.route("/bookings")
@shipper_required
def bookings():
    shipper  = get_shipper()
    status   = request.args.get("status", "")
    q_search = request.args.get("q", "")
    query    = shipper.bookings.order_by(Booking.created_at.desc())
    if status:
        query = query.filter_by(status=status)
    if q_search:
        query = query.filter(Booking.ref.ilike(f"%{q_search}%") |
                             Booking.route.ilike(f"%{q_search}%") |
                             Booking.commodity.ilike(f"%{q_search}%"))
    all_bookings = query.all()
    return render_template("shipper/bookings.html",
        title="My Bookings",
        bookings=[booking_to_v19(b) for b in all_bookings],
        shipper=shipper, status_filter=status, search=q_search)


@shipper_bp.route("/bookings/new", methods=["GET","POST"])
@shipper_required
def new_booking():
    shipper = get_shipper()
    address_book = shipper.address_book.all()
    suppliers    = SupplierProfile.query.filter_by(status="Active").all()

    if request.method == "POST":
        b = Booking(shipper_id=shipper.id)
        b.generate_ref()
        b.collection_address = request.form.get("collection_address","")
        b.collection_city    = request.form.get("collection_city","")
        b.delivery_address   = request.form.get("delivery_address","")
        b.delivery_city      = request.form.get("delivery_city","")
        b.route              = f"{b.collection_city} → {b.delivery_city}"
        b.commodity          = request.form.get("commodity","")
        b.pieces             = int(request.form.get("pieces", 1) or 1)
        b.weight_per_item_kg = float(request.form.get("weight_per_item", 0) or 0)
        b.total_weight_kg    = b.pieces * b.weight_per_item_kg
        b.vehicle_type_req   = request.form.get("vehicle_type","")
        b.destination_type   = request.form.get("destination_type","Direct")
        b.collection_contact = request.form.get("collection_contact","")
        b.collection_phone   = request.form.get("collection_phone","")
        b.delivery_contact   = request.form.get("delivery_contact","")
        b.delivery_phone     = request.form.get("delivery_phone","")
        b.notes              = request.form.get("notes","")

        col_date = request.form.get("collection_date","")
        if col_date:
            b.collection_date = date.fromisoformat(col_date)

        b.status = "Pending Quotes"
        db.session.add(b)

        # Auto-invite all active suppliers to quote
        active_suppliers = SupplierProfile.query.filter_by(status="Active").all()
        for sup in active_suppliers:
            push_notification(sup.user_id, f"New quote request: {b.ref}",
                              f"New load on {b.route} — submit your quote now.",
                              type="info", ref_type="booking", ref_id=b.ref)

        db.session.commit()
        log_action(current_user.id, "CREATE_BOOKING", "Booking", b.ref)
        flash(f"Booking {b.ref} created. Suppliers will be notified.", "success")
        return redirect(url_for("shipper.booking_detail", ref=b.ref))

    sa_cities = ["Durban","Johannesburg","Cape Town","Pretoria","Gqeberha",
                  "Bloemfontein","Polokwane","Nelspruit","Kimberley","East London",
                  "Pietermaritzburg","Richards Bay","Rustenburg","Soweto","Midrand"]
    return render_template("shipper/shipment.html",
        title="New Shipment",
        shipper=shipper, address_book=address_book, suppliers=suppliers,
        form={},
        cities=sa_cities,
        settings={"volumetricDivisor": 4000})


@shipper_bp.route("/bookings/<ref>")
@shipper_required
def booking_detail(ref):
    shipper = get_shipper()
    booking = Booking.query.filter_by(ref=ref, shipper_id=shipper.id).first_or_404()
    quotes  = score_quotes(booking.quotes.filter_by(status="Pending").all())
    explanations = {q.id: explain_rank(q) for q in quotes}
    return render_template("shipper/booking_detail.html",
        title=booking.ref,
        booking=booking_to_v19(booking),
        booking_obj=booking,
        quotes=[quote_to_v19(q) for q in quotes],
        explanations=explanations, shipper=shipper)


@shipper_bp.route("/bookings/<ref>/accept-quote/<int:quote_id>", methods=["POST"])
@shipper_required
def accept_quote(ref, quote_id):
    shipper = get_shipper()
    booking = Booking.query.filter_by(ref=ref, shipper_id=shipper.id).first_or_404()
    quote   = Quote.query.get_or_404(quote_id)

    if quote.booking_id != booking.id:
        flash("Quote does not belong to this booking.", "error")
        return redirect(url_for("shipper.booking_detail", ref=ref))

    # Accept this quote, reject others
    for q in booking.quotes:
        q.status = "Rejected"
    quote.status = "Accepted"

    booking.supplier_id      = quote.supplier_id
    booking.accepted_quote_id = quote.id
    booking.quoted_value     = quote.amount
    booking.calculate_platform_fee()
    booking.status           = "Confirmed"
    booking.confirmed_at     = datetime.utcnow()

    # Status event
    event = BookingStatusEvent(booking_id=booking.id, status="Confirmed",
                                note=f"Quote accepted: R{quote.amount:,.2f}",
                                actor=current_user.full_name)
    db.session.add(event)

    # Notify supplier
    push_notification(quote.supplier.user_id,
                      f"Quote accepted! Booking {booking.ref}",
                      f"Your quote of R{quote.amount:,.2f} was accepted for {booking.route}.",
                      type="success", ref_type="booking", ref_id=booking.ref)

    # Update shipper spend
    shipper.total_spend = (shipper.total_spend or 0) + booking.quoted_value

    db.session.commit()
    log_action(current_user.id, "ACCEPT_QUOTE", "Booking", ref,
               f"Quote ID {quote_id}, amount R{quote.amount:,.2f}")
    flash(f"Quote accepted. {quote.supplier.company_name} has been notified.", "success")
    return redirect(url_for("shipper.booking_detail", ref=ref))


@shipper_bp.route("/bookings/<ref>/cancel", methods=["POST"])
@shipper_required
def cancel_booking(ref):
    shipper = get_shipper()
    booking = Booking.query.filter_by(ref=ref, shipper_id=shipper.id).first_or_404()
    if booking.status in ("Collected", "In Transit", "Delivered"):
        flash("Cannot cancel a booking that is already in transit or delivered.", "error")
        return redirect(url_for("shipper.booking_detail", ref=ref))
    reason = request.form.get("reason", "Cancelled by shipper")
    booking.status = "Cancelled"
    event = BookingStatusEvent(booking_id=booking.id, status="Cancelled",
                                note=reason, actor=current_user.full_name)
    db.session.add(event)
    db.session.commit()
    flash(f"Booking {ref} cancelled.", "info")
    return redirect(url_for("shipper.bookings"))


@shipper_bp.route("/bookings/<ref>/reorder")
@shipper_required
def reorder(ref):
    shipper = get_shipper()
    original = Booking.query.filter_by(ref=ref, shipper_id=shipper.id).first_or_404()
    return render_template("shipper/reorder.html",
        title="Reorder Shipment",
        original=booking_to_v19(original), shipper=shipper)


@shipper_bp.route("/bookings/<ref>/reorder/confirm", methods=["POST"])
@shipper_required
def reorder_confirm(ref):
    shipper  = get_shipper()
    original = Booking.query.filter_by(ref=ref, shipper_id=shipper.id).first_or_404()

    b = Booking(shipper_id=shipper.id)
    b.generate_ref()
    b.collection_address = request.form.get("collection_address", original.collection_address)
    b.collection_city    = request.form.get("collection_city", original.collection_city)
    b.delivery_address   = request.form.get("delivery_address", original.delivery_address)
    b.delivery_city      = request.form.get("delivery_city", original.delivery_city)
    b.route              = f"{b.collection_city} → {b.delivery_city}"
    b.commodity          = original.commodity
    b.pieces             = original.pieces
    b.weight_per_item_kg = original.weight_per_item_kg
    b.total_weight_kg    = original.total_weight_kg
    b.vehicle_type_req   = original.vehicle_type_req
    b.collection_contact = original.collection_contact
    b.collection_phone   = original.collection_phone
    b.delivery_contact   = original.delivery_contact
    b.delivery_phone     = original.delivery_phone
    b.status = "Pending Quotes"

    col_date = request.form.get("collection_date", "")
    if col_date:
        b.collection_date = date.fromisoformat(col_date)

    db.session.add(b)
    db.session.commit()
    log_action(current_user.id, "REORDER", "Booking", b.ref, f"Cloned from {ref}")
    flash(f"Re-booking created: {b.ref}", "success")
    return redirect(url_for("shipper.booking_detail", ref=b.ref))


# ── Analytics & Intelligence ──────────────────────────────────────────────────

@shipper_bp.route("/analytics")
@shipper_required
def analytics():
    shipper  = get_shipper()
    bookings = shipper.bookings.filter_by(status="Delivered").all()

    # Build per-month buckets: {label: {total, routes, commodities, bookings}}
    monthly_buckets = {}
    for b in bookings:
        key = b.created_at.strftime("%b %Y") if b.created_at else "Unknown"
        if key not in monthly_buckets:
            monthly_buckets[key] = {"total": 0, "routes": {}, "commodities": {}}
        monthly_buckets[key]["total"] += (b.quoted_value or 0)
        r = b.route or "Unknown"
        monthly_buckets[key]["routes"][r] = monthly_buckets[key]["routes"].get(r, 0) + (b.quoted_value or 0)
        c = b.commodity or "General"
        monthly_buckets[key]["commodities"][c] = monthly_buckets[key]["commodities"].get(c, 0) + (b.quoted_value or 0)

    # Keep last 6 months
    monthly_labels = list(monthly_buckets.keys())[-6:]
    monthly_values = [monthly_buckets[k]["total"] for k in monthly_labels]

    # Top routes
    route_spend = {}
    for b in bookings:
        route_spend[b.route] = route_spend.get(b.route, 0) + (b.quoted_value or 0)
    top_routes = sorted(route_spend.items(), key=lambda x: x[1], reverse=True)[:5]

    # Top supplier per month (simplified)
    supplier_counts = {}
    for b in bookings:
        sname = b.supplier.company_name if b.supplier else "Unknown"
        supplier_counts[sname] = supplier_counts.get(sname, 0) + 1
    top_supplier = max(supplier_counts, key=supplier_counts.get) if supplier_counts else "—"

    total_spend    = sum(b.quoted_value or 0 for b in bookings)
    total_bookings = len(bookings)
    avg_cost       = total_spend / total_bookings if total_bookings else 0
    cpk_list       = [b.quoted_value / b.distance_km for b in bookings if b.distance_km and b.quoted_value]
    avg_cpk        = sum(cpk_list) / len(cpk_list) if cpk_list else 0

    # Full spend.monthly shape: month, total, routes{}, commodities{}, topSupplier
    spend_monthly = [
        {
            "month":       monthly_labels[i],
            "total":       monthly_buckets[monthly_labels[i]]["total"],
            "routes":      monthly_buckets[monthly_labels[i]]["routes"],
            "commodities": monthly_buckets[monthly_labels[i]]["commodities"],
            "topSupplier": top_supplier,
        }
        for i in range(len(monthly_labels))
    ]

    # Pad to at least 1 entry so template never crashes on empty
    if not spend_monthly:
        spend_monthly = [{"month": "—", "total": 0, "routes": {}, "commodities": {}, "topSupplier": "—"}]

    spend = {"monthly": spend_monthly}

    return render_template("shipper/analytics.html",
        title="Spend Analytics",
        shipper=shipper,
        bookings=[booking_to_v19(b) for b in bookings],
        spend=spend,
        monthly_labels=monthly_labels, monthly_values=monthly_values,
        top_routes=top_routes, total_spend=total_spend,
        total_bookings=total_bookings, avg_cost=avg_cost, avg_cpk=avg_cpk)


@shipper_bp.route("/analytics/export")
@shipper_required
def analytics_export():
    shipper  = get_shipper()
    bookings = shipper.bookings.filter_by(status="Delivered").all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Booking Ref","Route","Commodity","Date","Status","Value (R)","Platform Fee (R)","Distance (km)"])
    for b in bookings:
        writer.writerow([
            b.ref, b.route, b.commodity,
            b.created_at.strftime("%Y-%m-%d") if b.created_at else "",
            b.status, f"{b.quoted_value:.2f}", f"{b.platform_fee:.2f}",
            b.distance_km or ""
        ])

    output.seek(0)
    return send_file(
        io.BytesIO(output.read().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"freightflow_spend_{date.today()}.csv"
    )


@shipper_bp.route("/health-score")
@shipper_required
def health_score():
    shipper = get_shipper()
    scores  = compute_health_score(shipper)
    return render_template("shipper/health_score.html",
        title="Health Score", shipper=shipper, **scores)


@shipper_bp.route("/ai-insights")
@shipper_required
def ai_insights():
    shipper  = get_shipper()
    bookings = shipper.bookings.all()
    scores   = compute_health_score(shipper)

    insights = []
    total_spend = sum(b.quoted_value or 0 for b in bookings)

    if total_spend > 0:
        insights.append({
            "icon":"📊","type":"trend","impact":"neutral",
            "title": f"Total logistics spend: R{total_spend:,.0f}",
            "detail": f"Across {len(bookings)} bookings. Your average booking value is R{total_spend/len(bookings):,.0f}." if bookings else ""
        })

    # Supplier reliability
    supplier_scores = [(b.supplier.company_name, b.supplier.score) for b in bookings if b.supplier]
    if supplier_scores:
        worst = min(supplier_scores, key=lambda x: x[1])
        if worst[1] < 4.0:
            insights.append({
                "icon":"⚠️","type":"risk","impact":"negative",
                "title": f"{worst[0]} has a below-average score ({worst[1]}/5.0)",
                "detail": "Consider switching suppliers for this route to improve your reliability score."
            })

    # Cost
    if scores["cost_efficiency"] > 85:
        insights.append({
            "icon":"💰","type":"opportunity","impact":"positive",
            "title": "Your cost efficiency is above platform average",
            "detail": "You're spending less per km than 72% of FreightFlow shippers. Keep using your preferred suppliers."
        })
    else:
        insights.append({
            "icon":"💡","type":"opportunity","impact":"positive",
            "title": "Consolidating loads could reduce your per-km cost",
            "detail": "Combining partial loads on the same route could reduce cost per kg by up to 22%."
        })

    insights.append({
        "icon":"🔮","type":"trend","impact":"neutral",
        "title": "Peak season approaching — July volumes typically increase 28%",
        "detail": "Based on historical platform data, July sees significantly higher freight demand. Book capacity early."
    })

    return render_template("shipper/ai_insights.html",
        title="AI Insights",
        shipper=shipper, insights=insights, scores=scores,
        spend=[], pct_change=0)


@shipper_bp.route("/opportunities")
@shipper_required
def opportunities():
    shipper  = get_shipper()
    bookings = shipper.bookings.all()

    # Generate opportunities based on real data
    opps = []
    route_counts = {}
    route_spend  = {}
    for b in bookings:
        if b.route:
            route_counts[b.route] = route_counts.get(b.route, 0) + 1
            route_spend[b.route]  = route_spend.get(b.route, 0) + (b.quoted_value or 0)

    for route, count in route_counts.items():
        if count >= 3:
            annual_est = route_spend[route] * 2  # extrapolate
            saving = round(annual_est * 0.14)
            opps.append({
                "title": "Preferred supplier contract",
                "route": route,
                "detail": f"You ship this route {count} times. A preferred rate agreement could unlock 14% savings.",
                "saving": f"R {saving:,}",
                "savingPct": 14,
                "urgency": "High",
                "action": "Book new shipment"
            })

    if not opps:
        opps = [
            {"title":"Book more frequently to unlock contract pricing","route":"All routes",
             "detail":"Suppliers offer preferential rates to high-volume shippers. Book 5+ loads to start negotiating.","saving":"R 0","savingPct":0,"urgency":"Low","action":"New booking"}
        ]

    total_savings = sum(int(o["saving"].replace("R ","").replace(",","")) for o in opps)
    return render_template("shipper/opportunities.html",
        title="Opportunities",
        shipper=shipper, opportunities=opps, total_savings=total_savings)


@shipper_bp.route("/risk")
@shipper_required
def risk():
    shipper = get_shipper()
    active_bookings = shipper.bookings.filter(
        Booking.status.in_(["Confirmed","Driver Assigned","Collected","In Transit"])
    ).all()
    booking_risks = []
    for b in active_bookings:
        if b.supplier:
            sc = b.supplier.score
            if sc >= 4.5:   risk, risk_pct, color = "Low",    8,  "#27ae60"
            elif sc >= 3.5: risk, risk_pct, color = "Medium", 28, "#e67e22"
            else:           risk, risk_pct, color = "High",   62, "#c0392b"
        else:
            risk, risk_pct, color = "Medium", 35, "#e67e22"
        factors = []
        if b.supplier and b.supplier.score < 4.0:
            factors.append("Supplier score below platform average")
        if b.status == "In Transit":
            factors.append("Long-haul active transit")
        if b.destination_type == "DC":
            factors.append("DC slot delivery — time-critical")
        booking_risks.append({
            "ref":           b.ref,
            "route":         b.route or "",
            "shipper":       b.shipper.user.full_name if b.shipper and b.shipper.user else "—",
            "supplier":      b.supplier.company_name if b.supplier else "—",
            "status":        b.status,
            "value":         b.quoted_value or 0,
            "supplierScore": b.supplier.score if b.supplier else 0,
            "risk":          risk,
            "risk_pct":      risk_pct,
            "color":         color,
            "factors":       factors,
        })
    return render_template("shipper/risk.html",
        title="Risk Tracker",
        shipper=shipper, booking_risks=booking_risks)


@shipper_bp.route("/ai-assistant")
@shipper_required
def ai_assistant():
    shipper = get_shipper()
    return render_template("shipper/ai_assistant.html",
        title="AI Assistant", shipper=shipper, bookings=[], suppliers=[])


@shipper_bp.route("/address-book")
@shipper_required
def address_book():
    shipper   = get_shipper()
    addresses = shipper.address_book.order_by(AddressBook.label).all()
    return render_template("shipper/address_book.html",
        title="Address Book",
        shipper=shipper, addresses=addresses)


@shipper_bp.route("/address-book/add", methods=["POST"])
@shipper_required
def add_address():
    shipper = get_shipper()
    addr = AddressBook(
        shipper_id=shipper.id,
        label        = request.form.get("label",""),
        address      = request.form.get("address",""),
        city         = request.form.get("city",""),
        contact_name = request.form.get("contact_name",""),
        contact_phone= request.form.get("contact_phone",""),
        type         = request.form.get("type","Delivery"),
    )
    db.session.add(addr)
    db.session.commit()
    flash("Address saved to address book.", "success")
    return redirect(url_for("shipper.address_book"))


@shipper_bp.route("/address-book/<int:addr_id>/delete", methods=["POST"])
@shipper_required
def delete_address(addr_id):
    shipper = get_shipper()
    addr    = AddressBook.query.filter_by(id=addr_id, shipper_id=shipper.id).first_or_404()
    db.session.delete(addr)
    db.session.commit()
    flash("Address removed.", "info")
    return redirect(url_for("shipper.address_book"))


# ── Notifications ─────────────────────────────────────────────────────────────

@shipper_bp.route("/notifications")
@shipper_required
def notifications():
    notes = current_user.notifications.order_by(
        Notification.created_at.desc()).limit(50).all()
    # Mark all as read
    current_user.notifications.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    return render_template("shipper/reports.html",
        title="Notifications", notifications=notes)


# ── Complaints ────────────────────────────────────────────────────────────────

from app.models import Complaint  # local import to avoid circular at top

@shipper_bp.route("/complaints")
@shipper_required
def complaints():
    shipper = get_shipper()
    all_complaints = shipper.complaints.order_by(Complaint.created_at.desc()).all()
    return render_template("shipper/complaints.html",
        title="My Complaints", complaints=all_complaints)


@shipper_bp.route("/complaints/new", methods=["GET", "POST"])
@shipper_required
def complaint_new():
    shipper  = get_shipper()
    bookings = shipper.bookings.order_by(Booking.created_at.desc()).limit(50).all()
    selected_ref = request.args.get("ref", "")

    if request.method == "POST":
        booking_ref  = request.form.get("bookingRef", "").strip()
        category     = request.form.get("category", "").strip()
        priority     = request.form.get("priority", "Normal").strip()
        description  = request.form.get("description", "").strip()

        if not category or not description:
            flash("Please fill in all required fields.", "error")
            return render_template("shipper/complaint_new.html",
                title="New Complaint", bookings=bookings, selected_ref=selected_ref)

        # Resolve booking & supplier
        booking  = Booking.query.filter_by(ref=booking_ref).first() if booking_ref else None
        supplier = booking.supplier if booking else None

        c = Complaint(
            shipper_id  = shipper.id,
            booking_id  = booking.id if booking else None,
            supplier_id = supplier.id if supplier else None,
            category    = category,
            priority    = priority,
            description = description,
            status      = "Submitted",
        )
        c.generate_ref()
        db.session.add(c)
        db.session.flush()   # get id before commit

        # Handle file uploads (store filenames only)
        files = request.files.getlist("evidence")
        saved = []
        import os, werkzeug.utils
        upload_dir = os.path.join("app", "static", "complaint_evidence")
        os.makedirs(upload_dir, exist_ok=True)
        for f in files:
            if f and f.filename:
                fname = werkzeug.utils.secure_filename(f"{c.ref}_{f.filename}")
                f.save(os.path.join(upload_dir, fname))
                saved.append(fname)
        if saved:
            c.evidence_files = ",".join(saved)

        db.session.commit()

        # Notify all admins
        admins = User.query.filter_by(role="admin").all()
        for adm in admins:
            push_notification(adm.id,
                f"New complaint {c.ref}",
                f"{shipper.company_name or current_user.full_name} filed a {c.priority} complaint: {c.category}",
                notif_type="warning", ref_type="complaint", ref_id=c.ref)

        flash(f"Complaint {c.ref} submitted. Our support team will review it shortly.", "success")
        return redirect(url_for("shipper.complaint_detail", ref=c.ref))

    return render_template("shipper/complaint_new.html",
        title="New Complaint", bookings=bookings, selected_ref=selected_ref)


@shipper_bp.route("/complaints/<ref>")
@shipper_required
def complaint_detail(ref):
    shipper = get_shipper()
    c = Complaint.query.filter_by(ref=ref, shipper_id=shipper.id).first_or_404()
    return render_template("shipper/complaint_detail.html", title=f"Complaint {ref}", complaint=c)
