"""
Admin blueprint — platform oversight, approvals, analytics, user management.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, date
import io, csv

from app.models import (db, User, Booking, Quote, SupplierProfile, ShipperProfile,
                         Driver, Vehicle, Invoice, PurchaseOrder,
                         Notification, AuditLog, SupplierScoreHistory)
from app.services.notifications import push_notification
from app.services.v19_adapter import booking_to_v19, supplier_to_v19
from app.services.audit import log_action

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "admin":
            flash("Access denied.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ─────────────────────────────────────────────────────────────────

@admin_bp.route("/")
@admin_required
def dashboard():
    total_bookings  = Booking.query.count()
    active          = Booking.query.filter(
                        Booking.status.in_(["Confirmed","Driver Assigned","Collected","In Transit"])).count()
    delivered_today = Booking.query.filter(
                        Booking.status=="Delivered",
                        db.func.date(Booking.delivered_at)==date.today()).count()
    pending_approval= SupplierProfile.query.filter_by(status="Under Review").count()
    total_suppliers = SupplierProfile.query.filter_by(status="Active").count()
    total_shippers  = ShipperProfile.query.count()
    platform_revenue= db.session.query(db.func.sum(Booking.platform_fee)).scalar() or 0
    recent_bookings = Booking.query.order_by(Booking.created_at.desc()).limit(10).all()
    recent_logs     = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(15).all()

    # Build v19 notification console items
    from app.models import Notification, User as _User
    admin_notifs = []
    for log in recent_logs[:5]:
        u = _User.query.get(log.user_id) if log.user_id else None
        admin_notifs.append({
            "title": f"{log.action} — {log.entity_id or ''}",
            "detail": log.detail or "",
            "audience": log.entity_type or "System",
            "channel": "Platform",
            "time": log.created_at.strftime("%H:%M") if log.created_at else "",
        })
    return render_template("admin/dashboard.html",
        title="Platform Overview",
        total_bookings=total_bookings, active=active,
        delivered_today=delivered_today, pending_approval=pending_approval,
        total_suppliers=total_suppliers, total_shippers=total_shippers,
        platform_revenue=platform_revenue,
        recent_bookings=[booking_to_v19(b) for b in recent_bookings],
        recent_logs=recent_logs,
        notifications=admin_notifs)


# ── Bookings ──────────────────────────────────────────────────────────────────

@admin_bp.route("/bookings")
@admin_required
def bookings():
    status = request.args.get("status","")
    q      = request.args.get("q","")
    query  = Booking.query.order_by(Booking.created_at.desc())
    if status:
        query = query.filter_by(status=status)
    if q:
        query = query.filter(Booking.ref.ilike(f"%{q}%") | Booking.route.ilike(f"%{q}%"))
    bookings = query.limit(200).all()
    return render_template("admin/bookings.html",
        title="All Bookings",
        bookings=[booking_to_v19(b) for b in bookings],
        status_filter=status, search=q)


@admin_bp.route("/bookings/<ref>/force-status", methods=["POST"])
@admin_required
def force_status(ref):
    booking    = Booking.query.filter_by(ref=ref).first_or_404()
    new_status = request.form.get("status")
    note       = request.form.get("note","Admin override")
    booking.status = new_status
    from app.models import BookingStatusEvent
    event = BookingStatusEvent(booking_id=booking.id, status=new_status,
                                note=note, actor=f"ADMIN:{current_user.full_name}")
    db.session.add(event)
    db.session.commit()
    log_action(current_user.id, "FORCE_STATUS", "Booking", ref, f"→ {new_status}")
    flash(f"Booking {ref} status set to {new_status}.", "success")
    return redirect(url_for("admin.bookings"))


# ── Supplier Management ───────────────────────────────────────────────────────

@admin_bp.route("/suppliers")
@admin_required
def suppliers():
    status = request.args.get("status","")
    query  = SupplierProfile.query
    if status:
        query = query.filter_by(status=status)
    suppliers = query.order_by(SupplierProfile.created_at.desc()).all()
    return render_template("admin/approvals.html",
        title="Supplier Approvals",
        suppliers=suppliers, status_filter=status)


@admin_bp.route("/suppliers/<int:sid>/approve", methods=["POST"])
@admin_required
def approve_supplier(sid):
    supplier = SupplierProfile.query.get_or_404(sid)
    supplier.status      = "Active"
    supplier.approved_at = datetime.utcnow()
    push_notification(supplier.user_id,
                      "Your supplier account is approved! 🎉",
                      "You can now receive booking requests on FreightFlow Nexus.",
                      type="success")
    db.session.commit()
    log_action(current_user.id, "APPROVE_SUPPLIER", "SupplierProfile", str(sid))
    flash(f"{supplier.company_name} approved.", "success")
    return redirect(url_for("admin.suppliers"))


@admin_bp.route("/suppliers/<int:sid>/suspend", methods=["POST"])
@admin_required
def suspend_supplier(sid):
    supplier        = SupplierProfile.query.get_or_404(sid)
    reason          = request.form.get("reason","Score below threshold")
    supplier.status = "Suspended"
    push_notification(supplier.user_id,
                      "Your supplier account has been suspended",
                      f"Reason: {reason}. Contact support@movement.com to appeal.",
                      type="error")
    db.session.commit()
    log_action(current_user.id, "SUSPEND_SUPPLIER", "SupplierProfile", str(sid), reason)
    flash(f"{supplier.company_name} suspended.", "warning")
    return redirect(url_for("admin.suppliers"))


@admin_bp.route("/suppliers/<int:sid>")
@admin_required
def supplier_detail(sid):
    supplier   = SupplierProfile.query.get_or_404(sid)
    bookings   = supplier.bookings.order_by(Booking.created_at.desc()).limit(20).all()
    score_hist = supplier.score_history.order_by(SupplierScoreHistory.recorded_at).all()
    return render_template("admin/supplier_insights.html",
        title=supplier.company_name,
        supplier=supplier_to_v19(supplier),
        supplier_obj=supplier,
        bookings=[booking_to_v19(b) for b in bookings],
        score_hist=score_hist)


# ── Shipper Management ────────────────────────────────────────────────────────

@admin_bp.route("/shippers")
@admin_required
def shippers():
    shippers = ShipperProfile.query.order_by(ShipperProfile.created_at.desc()).all()
    return render_template("admin/shipping_agents.html",
        title="Shippers", shippers=shippers)


# ── User Management ───────────────────────────────────────────────────────────

@admin_bp.route("/users")
@admin_required
def users():
    role  = request.args.get("role","")
    query = User.query
    if role:
        query = query.filter_by(role=role)
    users = query.order_by(User.created_at.desc()).all()
    return render_template("admin/admins.html",
        title="Users", users=users, role_filter=role)


@admin_bp.route("/users/<int:uid>/toggle", methods=["POST"])
@admin_required
def toggle_user(uid):
    user = User.query.get_or_404(uid)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin.users"))
    user.is_active = not user.is_active
    db.session.commit()
    state = "activated" if user.is_active else "deactivated"
    log_action(current_user.id, f"USER_{state.upper()}", "User", str(uid))
    flash(f"User {user.email} {state}.", "info")
    return redirect(url_for("admin.users"))


# ── Marketplace Intelligence ──────────────────────────────────────────────────

@admin_bp.route("/marketplace")
@admin_required
def marketplace():
    # Real aggregated route data from bookings
    from sqlalchemy import func
    route_data = db.session.query(
        Booking.route,
        func.count(Booking.id).label("volume"),
        func.avg(Booking.quoted_value).label("avg_rate"),
        func.sum(Booking.quoted_value).label("total_value"),
    ).filter(Booking.status == "Delivered")\
     .group_by(Booking.route)\
     .order_by(func.count(Booking.id).desc())\
     .limit(10).all()

    total_volume    = sum(r.volume for r in route_data)
    platform_revenue= db.session.query(func.sum(Booking.platform_fee)).scalar() or 0
    total_bookings  = Booking.query.count()

    # Supplier market share
    supplier_share = db.session.query(
        SupplierProfile.company_name,
        func.count(Booking.id).label("bookings"),
    ).join(Booking, Booking.supplier_id == SupplierProfile.id)\
     .group_by(SupplierProfile.id)\
     .order_by(func.count(Booking.id).desc()).limit(5).all()

    avg_platform_rate = int(sum(r.avg_rate or 0 for r in route_data) / len(route_data)) if route_data else 0

    return render_template("admin/marketplace.html",
        title="Marketplace Intelligence",
        route_data=route_data, total_volume=total_volume,
        platform_revenue=platform_revenue, total_bookings=total_bookings,
        supplier_share=supplier_share, avg_platform_rate=avg_platform_rate,
        routes=[{"route": r.route, "volume": r.volume, "avgRate": r.avg_rate or 0,
                 "currentAvg": r.avg_rate or 0, "demand": "High" if r.volume > 20 else "Medium",
                 "priceChange": 2.1, "topSupplier": "—", "trend": "up"} for r in route_data])


# ── Supplier Risk Monitor ─────────────────────────────────────────────────────

@admin_bp.route("/supplier-risk")
@admin_required
def supplier_risk():
    suppliers = SupplierProfile.query.filter_by(status="Active").all()
    risk_data = []
    for sup in suppliers:
        hist  = sup.score_history.order_by(SupplierScoreHistory.recorded_at).all()
        traj  = [h.score for h in hist[-6:]] if hist else [sup.score]
        delta = round(traj[-1] - traj[0], 2) if len(traj) >= 2 else 0

        if sup.score < 3.5 or delta < -0.5:  risk = "High"
        elif sup.score < 4.0 or delta < -0.2: risk = "Medium"
        else:                                   risk = "Low"

        risk_data.append({
            "id":            sup.id,
            "name":          sup.company_name,
            "baseCity":      sup.base_city or "",
            "status":        sup.status,
            "score":         sup.score,
            "scoreChange":   delta,
            "onTimeRate":    sup.on_time_rate,
            "cancelRate":    sup.cancellation_rate,
            "totalJobs":     sup.total_jobs,
            "trajectory":    traj,
            "risk":          risk,
            "supplier":      sup,
            # Nested stats dict used by template as s.stats.acceptanceRate
            "stats": {
                "acceptanceRate":    sup.acceptance_rate,
                "onTimeRate":        sup.on_time_rate,
                "cancellationRate":  sup.cancellation_rate,
                "totalJobs":         sup.total_jobs,
                "rejectionRate":     round(100 - sup.acceptance_rate, 1),
            },
        })
    risk_data.sort(key=lambda x: {"High":0,"Medium":1,"Low":2}[x["risk"]])
    return render_template("admin/supplier_risk.html",
        title="Supplier Risk Monitor", risk_data=risk_data)


# ── Executive Reports ─────────────────────────────────────────────────────────

@admin_bp.route("/executive-reports")
@admin_required
def executive_reports():
    from sqlalchemy import func
    total_revenue   = db.session.query(func.sum(Booking.quoted_value)).scalar() or 0
    platform_fees   = db.session.query(func.sum(Booking.platform_fee)).scalar() or 0
    supplier_payouts= db.session.query(func.sum(Booking.supplier_payout)).scalar() or 0
    total_bookings  = Booking.query.count()
    total_shippers  = ShipperProfile.query.count()
    total_suppliers = SupplierProfile.query.filter_by(status="Active").count()
    return render_template("admin/executive_reports.html",
        title="Executive Reports",
        total_revenue=total_revenue,
        platform_fee_total=platform_fees,  # template uses platform_fee_total
        platform_fees=platform_fees,
        supplier_payouts=supplier_payouts, total_bookings=total_bookings,
        total_shippers=total_shippers, total_suppliers=total_suppliers,
        reports=[
            {"id":"RPT-001","title":"Monthly Logistics — June 2026","type":"monthly","generated":"01 Jun 2026","size":"2.4 MB"},
            {"id":"RPT-002","title":"Supplier Performance — Q2 2026","type":"supplier","generated":"01 Jun 2026","size":"1.8 MB"},
            {"id":"RPT-003","title":"Financial Summary — May 2026","type":"financial","generated":"01 May 2026","size":"0.9 MB"},
        ])


@admin_bp.route("/executive-reports/export-csv")
@admin_required
def export_bookings_csv():
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    output   = io.StringIO()
    writer   = csv.writer(output)
    writer.writerow(["Ref","Route","Shipper","Supplier","Status","Value","Platform Fee",
                      "Supplier Payout","Collection Date","Created"])
    for b in bookings:
        writer.writerow([
            b.ref, b.route,
            b.shipper.user.full_name if b.shipper else "",
            b.supplier.company_name if b.supplier else "",
            b.status, f"{b.quoted_value:.2f}", f"{b.platform_fee:.2f}",
            f"{b.supplier_payout:.2f}",
            str(b.collection_date or ""), str(b.created_at)[:10]
        ])
    output.seek(0)
    log_action(current_user.id, "EXPORT_CSV", "Booking", "ALL")
    return send_file(
        io.BytesIO(output.read().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"ffn_bookings_{date.today()}.csv"
    )


# ── Audit Log ─────────────────────────────────────────────────────────────────

@admin_bp.route("/audit-log")
@admin_required
def audit_log():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all()
    return render_template("admin/reports.html",
        title="Audit Log", logs=logs)


# ── Complaints ─────────────────────────────────────────────────────────────────

from app.models import Complaint  # local import

@admin_bp.route("/complaints")
@admin_required
def complaints():
    status_filter = request.args.get("status", "")
    q = Complaint.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    all_complaints = q.order_by(Complaint.created_at.desc()).all()
    status_options = ["Submitted", "Under Admin Review", "Forwarded to Supplier",
                      "Supplier Responded", "Resolved", "Closed"]
    counts = {s: Complaint.query.filter_by(status=s).count() for s in status_options}
    return render_template("admin/complaints.html",
        title="Complaints", complaints=all_complaints,
        status_filter=status_filter, status_options=status_options, counts=counts)


@admin_bp.route("/complaints/<ref>", methods=["GET", "POST"])
@admin_required
def complaint_detail(ref):
    c = Complaint.query.filter_by(ref=ref).first_or_404()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_notes":
            c.admin_notes = request.form.get("admin_notes", "").strip()
            c.status = "Under Admin Review"
            db.session.commit()
            flash("Notes saved.", "success")

        elif action == "forward":
            # Forward complaint to supplier
            c.status       = "Forwarded to Supplier"
            c.forwarded_at = datetime.utcnow()
            c.forwarded_by_id = current_user.id
            c.admin_notes  = request.form.get("admin_notes", c.admin_notes or "").strip()
            db.session.commit()

            # Notify supplier
            if c.supplier:
                push_notification(
                    c.supplier.user_id,
                    f"Complaint {c.ref} — action required",
                    f"A complaint has been reviewed by admin and forwarded to you. Category: {c.category}. Please respond within 4 hours.",
                    notif_type="error", ref_type="complaint", ref_id=c.ref)

            # Notify shipper
            push_notification(
                c.shipper.user_id,
                f"Complaint {c.ref} forwarded to supplier",
                "Our support team has reviewed your complaint and forwarded it to the supplier for their response.",
                notif_type="info", ref_type="complaint", ref_id=c.ref)

            log_action(current_user.id, "complaint_forwarded", "complaint", c.ref,
                       f"Forwarded {c.ref} to supplier {c.supplier.company_name if c.supplier else 'N/A'}")
            flash(f"Complaint {c.ref} forwarded to supplier.", "success")

        elif action == "resolve":
            c.status           = "Resolved"
            c.resolution_notes = request.form.get("resolution_notes", "").strip()
            c.resolved_at      = datetime.utcnow()
            db.session.commit()

            push_notification(c.shipper.user_id,
                f"Complaint {c.ref} resolved",
                c.resolution_notes or "Your complaint has been resolved by our support team.",
                notif_type="success", ref_type="complaint", ref_id=c.ref)
            flash("Complaint marked as resolved.", "success")

        elif action == "close":
            c.status = "Closed"
            db.session.commit()
            flash("Complaint closed.", "info")

        return redirect(url_for("admin.complaint_detail", ref=ref))

    return render_template("admin/complaint_detail.html", title=f"Complaint {ref}", complaint=c)
