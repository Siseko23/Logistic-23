"""
v19 Template Adapter
Converts SQLAlchemy model instances into flat dicts that match
the variable shapes the v19 Jinja templates expect.
"""
from app.models import Booking, SupplierProfile


def booking_to_v19(b: Booking) -> dict:
    """Convert a Booking ORM object to a v19-compatible dict."""
    return {
        "ref":         b.ref,
        "route":       b.route or "",
        "status":      b.status or "",
        "value":       b.quoted_value or 0,
        "shipper":     b.shipper.user.full_name if b.shipper and b.shipper.user else "—",
        "supplier":    b.supplier.company_name if b.supplier else "—",
        "supplierId":  b.supplier_id,
        "commodity":   b.commodity or "",
        "pieces":      b.pieces or 0,
        "unitType":    "pallets",
        "collectionAddress": b.collection_address or "",
        "collectionCity":    b.collection_city or "",
        "deliveryAddress":   b.delivery_address or "",
        "deliveryCity":      b.delivery_city or "",
        "collectionContact": b.collection_contact or "",
        "collectionPhone":   b.collection_phone or "",
        "deliveryContact":   b.delivery_contact or "",
        "deliveryPhone":     b.delivery_phone or "",
        "vehicleType":       b.vehicle_type_req or "",
        "driverName":        b.driver.name if b.driver else "—",
        "vehicleReg":        b.vehicle.reg_number if b.vehicle else "—",
        "collectedAt":       b.collected_at.strftime("%d %b %H:%M") if b.collected_at else "",
        "deliveredAt":       b.delivered_at.strftime("%d %b %H:%M") if b.delivered_at else "",
        "createdAt":         b.created_at.strftime("%d %b %Y") if b.created_at else "",
        "collectionDate":    str(b.collection_date) if b.collection_date else "",
        "distance_km":       b.distance_km or 0,
        "platformFee":       b.platform_fee or 0,
        "supplierPayout":    b.supplier_payout or 0,
        "riskLevel":         b.risk_level or "Low",
        "notes":             b.notes or "",
        "supplierResponseWindow": "4h remaining",
        "destinationType":   b.destination_type or "Direct",
        "weightPerItem":     b.weight_per_item_kg or 0,
        "totalWeight":       b.total_weight_kg or 0,
        # status event timeline
        "statusEvents": [
            {"status": e.status, "note": e.note or "", "time": e.created_at.strftime("%d %b %H:%M")}
            for e in (b.status_events or [])
        ],
    }


def supplier_to_v19(s: SupplierProfile) -> dict:
    """Convert a SupplierProfile to a v19-compatible dict."""
    return {
        "id":             s.id,
        "name":           s.company_name,
        "baseCity":       s.base_city or "",
        "region":         s.operating_region or "",
        "status":         s.status,
        "score":          s.score,
        "totalJobs":      s.total_jobs,
        "onTimeRate":     s.on_time_rate,
        "cancellationRate": s.cancellation_rate,
        "acceptanceRate": s.acceptance_rate,
        "approvedAt":     s.approved_at.strftime("%d %b %Y") if s.approved_at else "—",
        "createdAt":      s.created_at.strftime("%d %b %Y") if s.created_at else "—",
    }


def quote_to_v19(q, rank=None) -> dict:
    """Convert a Quote + SupplierProfile to v19-compatible dict."""
    sup = q.supplier
    return {
        "id":            q.id,
        "supplier":      sup.company_name if sup else "—",
        "supplierId":    q.supplier_id,
        "amount":        q.amount,
        "transitDays":   q.transit_days or 1,
        "notes":         q.notes or "",
        "status":        q.status,
        "aiScore":       q.ai_score or 0,
        "rank":          q.rank or rank or 1,
        "supplierScore": sup.score if sup else 0,
        "onTimeRate":    sup.on_time_rate if sup else 0,
        "reasons":       _explain_rank(q),
    }


def _explain_rank(q) -> list:
    sup = q.supplier
    reasons = []
    if q.rank == 1:
        reasons.append("Lowest adjusted cost after AI scoring")
    if sup and sup.score >= 4.5:
        reasons.append(f"Excellent reliability: {sup.score}/5.0")
    elif sup and sup.score >= 4.0:
        reasons.append(f"Good reliability: {sup.score}/5.0")
    elif sup:
        reasons.append(f"Below-average reliability: {sup.score}/5.0")
    if sup:
        reasons.append(f"On-time delivery: {sup.on_time_rate}%")
    return reasons
