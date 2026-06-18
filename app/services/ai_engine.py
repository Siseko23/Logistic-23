"""
FreightFlow AI Matching Engine
Scores supplier quotes using price, performance, and proximity weighting.
"""
from typing import List
from app.models import Quote, SupplierProfile


def score_quotes(quotes: List[Quote], price_w=0.50, perf_w=0.35, prox_w=0.15) -> List[Quote]:
    """
    Score and rank a list of quotes for a booking.
    Modifies quote.ai_score and quote.rank in place.
    Returns sorted list (best first).
    """
    if not quotes:
        return quotes

    amounts  = [q.amount for q in quotes]
    min_amt  = min(amounts)
    max_amt  = max(amounts)
    amt_range = max_amt - min_amt if max_amt != min_amt else 1

    for q in quotes:
        supplier: SupplierProfile = q.supplier

        # 1. Price score — lower is better (inverted, normalised 0–1)
        price_norm = 1 - ((q.amount - min_amt) / amt_range)

        # 2. Performance score — supplier score 0–5, normalised 0–1
        perf_norm = (supplier.score or 4.0) / 5.0

        # 3. Proximity score — simplified: all get 0.5 (would use geo in prod)
        prox_norm = 0.5

        q.ai_score = round(
            (price_norm * price_w) + (perf_norm * perf_w) + (prox_norm * prox_w),
            4
        )

    # Rank: highest score = rank 1
    sorted_quotes = sorted(quotes, key=lambda q: q.ai_score, reverse=True)
    for i, q in enumerate(sorted_quotes, 1):
        q.rank = i

    return sorted_quotes


def explain_rank(quote: Quote) -> dict:
    """Return human-readable explanation for why a quote is ranked where it is."""
    supplier = quote.supplier
    reasons = []

    if quote.rank == 1:
        reasons.append("Lowest adjusted cost after AI scoring")
    else:
        reasons.append(f"Ranked #{quote.rank} — higher bids from other suppliers score higher")

    if supplier.score >= 4.5:
        reasons.append(f"Excellent reliability score: {supplier.score}/5.0")
    elif supplier.score >= 4.0:
        reasons.append(f"Good reliability score: {supplier.score}/5.0")
    else:
        reasons.append(f"Below-average reliability score: {supplier.score}/5.0")

    reasons.append(f"On-time delivery rate: {supplier.on_time_rate}%")

    return {
        "rank":      quote.rank,
        "ai_score":  quote.ai_score,
        "reasons":   reasons,
        "supplier":  supplier.company_name,
        "amount":    quote.amount,
    }


def compute_health_score(shipper_profile) -> dict:
    """
    Compute the logistics health score for a shipper.
    Returns dict with overall score and component scores.
    """
    bookings = shipper_profile.bookings.all()
    if not bookings:
        return {"health_score": 75, "cost_efficiency": 75, "reliability": 75,
                "performance": 75, "booking_success": 75}

    total = len(bookings)
    delivered = sum(1 for b in bookings if b.status == "Delivered")
    cancelled = sum(1 for b in bookings if b.status == "Cancelled")
    confirmed = sum(1 for b in bookings if b.status not in ("Pending Quotes","Cancelled"))

    delivery_rate   = (delivered / total) * 100 if total else 100
    booking_success = (confirmed / total) * 100 if total else 100

    # Cost efficiency: compare avg cost/km vs a platform baseline of R28/km
    costs_per_km = [
        b.quoted_value / b.distance_km
        for b in bookings
        if b.distance_km and b.quoted_value
    ]
    if costs_per_km:
        avg_cpk = sum(costs_per_km) / len(costs_per_km)
        cost_efficiency = min(100, max(0, 100 - ((avg_cpk - 26) / 26) * 100))
    else:
        cost_efficiency = 80

    # Reliability: based on suppliers used
    supplier_scores = []
    for b in bookings:
        if b.supplier:
            supplier_scores.append(b.supplier.score)
    reliability = (sum(supplier_scores) / len(supplier_scores) / 5.0 * 100) if supplier_scores else 80

    performance = min(100, delivery_rate)
    health_score = int(
        (cost_efficiency * 0.30) +
        (reliability     * 0.30) +
        (performance     * 0.25) +
        (booking_success * 0.15)
    )

    return {
        "health_score":    health_score,
        "cost_efficiency": round(cost_efficiency, 1),
        "reliability":     round(reliability, 1),
        "performance":     round(performance, 1),
        "booking_success": round(booking_success, 1),
        "total_bookings":  total,
        "delivered":       delivered,
    }
