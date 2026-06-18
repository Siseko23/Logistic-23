"""Public routes — landing page, public tracking"""
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.models import Booking, Notification, SupplierProfile

public_bp = Blueprint("public", __name__)
api_bp    = Blueprint("api", __name__)


@public_bp.route("/")
def index():
    return render_template("public/landing.html")


@public_bp.route("/track/<ref>")
def public_track(ref):
    booking = Booking.query.filter_by(ref=ref).first_or_404()
    events  = booking.status_events
    return render_template("public_tracking.html", booking=booking, events=events)


@public_bp.route("/onboarding")
def onboarding():
    return render_template("onboarding.html")


# ── JSON API ──────────────────────────────────────────────────────────────────

@api_bp.route("/notifications/unread-count")
@login_required
def notifications_count():
    count = current_user.notifications.filter_by(is_read=False).count()
    return jsonify({"count": count})


@api_bp.route("/notifications/mark-read", methods=["POST"])
@login_required
def mark_notifications_read():
    from app.models import db
    current_user.notifications.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/ai-assistant", methods=["POST"])
@login_required
def ai_assistant():
    """Rule-based AI assistant — in production this would call an LLM."""
    question = (request.json or {}).get("question", "").lower()
    user = current_user

    if user.role == "shipper":
        profile = user.shipper_profile
        bookings = profile.bookings.all() if profile else []
        total_spend = sum(b.quoted_value or 0 for b in bookings)
        delivered   = [b for b in bookings if b.status == "Delivered"]
        in_transit  = [b for b in bookings if b.status == "In Transit"]

        if any(w in question for w in ["delay","late","delayed","problem","risk"]):
            ans = f"You have {len(in_transit)} shipments currently in transit. " + \
                  ("Check the Risk Tracker for detailed risk analysis." if in_transit else "No active transit risks detected.")
        elif any(w in question for w in ["cheap","cheapest","price","cost","lowest"]):
            suppliers = SupplierProfile.query.filter_by(status="Active").order_by(SupplierProfile.score.asc()).all()
            ans = f"For price-competitive quotes, consider requesting from all active suppliers and using the AI quote comparison tool. Currently {len(suppliers)} suppliers are active on the platform."
        elif any(w in question for w in ["spend","total","how much","money"]):
            ans = f"Your total logistics spend across {len(bookings)} bookings is R{total_spend:,.0f}. You've completed {len(delivered)} deliveries."
        elif any(w in question for w in ["supplier","who","best","performance","top"]):
            used = [(b.supplier.company_name, b.supplier.score) for b in bookings if b.supplier]
            if used:
                best = max(used, key=lambda x: x[1])
                ans = f"Your best-performing supplier is {best[0]} with a score of {best[1]}/5.0."
            else:
                ans = "You haven't confirmed any bookings yet. Create a booking to start receiving supplier quotes."
        elif any(w in question for w in ["booking","status","current"]):
            ans = f"You have {len(bookings)} total bookings: {len(in_transit)} in transit, {len(delivered)} delivered."
        elif any(w in question for w in ["save","saving","opportunity","reduce"]):
            ans = "Visit the Opportunity Finder page to see personalised cost-saving recommendations based on your booking history."
        elif any(w in question for w in ["health","score"]):
            ans = "Your Logistics Health Score measures cost efficiency, supplier reliability, delivery performance, and booking success rate. Visit the Health Score page for your full breakdown."
        else:
            ans = "I can help you with: shipment status, total spend, supplier performance, savings opportunities, or delivery risks. Try asking one of those!"
    else:
        ans = "AI assistant is available for shipper accounts."

    return jsonify({"answer": ans})


@api_bp.route("/booking/<ref>/events")
@login_required
def booking_events(ref):
    booking = Booking.query.filter_by(ref=ref).first_or_404()
    events = [{"status": e.status, "note": e.note, "time": str(e.created_at)[:16]}
              for e in booking.status_events]
    return jsonify(events)
