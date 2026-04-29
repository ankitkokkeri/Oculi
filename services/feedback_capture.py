import uuid
from datetime import datetime, timezone


def capture_feedback(outreach_output: dict, customer_id: str, simulated_outcome: str) -> dict:
    """Simulate logging the recommendation outcome."""
    recommendations = outreach_output.get("recommendations", [])
    product_ids = [r.get("product_id") for r in recommendations if r.get("product_id")]

    log_entry = {
        "recommendation_id": f"REC_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{customer_id}_{uuid.uuid4().hex[:6].upper()}",
        "customer_id": customer_id,
        "recommended_products": product_ids,
        "channel": outreach_output.get("channel", "unknown"),
        "simulated_outcome": simulated_outcome,
        "note": _generate_note(simulated_outcome, outreach_output),
    }
    return log_entry


def _generate_note(outcome: str, outreach: dict) -> str:
    channel = outreach.get("channel", "unknown")
    header = outreach.get("message_header", "")
    if outcome == "ACCEPTED":
        return f"Attach rate event logged. Customer responded to '{header}' via {channel}."
    if outcome == "REJECTED":
        return f"Customer dismissed recommendation via {channel}. Suppression flag set for session."
    return f"No response recorded for {channel} outreach. Will retry in next session if eligible."
