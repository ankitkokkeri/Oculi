import json
from datetime import datetime, timezone
from pathlib import Path


def capture_event(raw_scenario: dict) -> dict:
    """Parse and normalise a raw scenario payload into a structured signal object."""
    return {
        "customer_id": raw_scenario["customer_id"],
        "event_type": raw_scenario["event_type"],
        "product_id": raw_scenario["product_id"],
        "product_name": raw_scenario["product_name"],
        "product_category": raw_scenario["product_category"],
        "session_depth": raw_scenario.get("session_depth", 1),
        "search_query": raw_scenario.get("search_query"),
        "cart_contents": raw_scenario.get("cart_contents", []),
        "last_outreach_minutes_ago": raw_scenario.get("last_outreach_minutes_ago"),
        "cross_sell_rejected_this_session": raw_scenario.get("cross_sell_rejected_this_session", False),
        "returning_session": raw_scenario.get("returning_session", False),
        "cached_intent": raw_scenario.get("cached_intent"),
        "timestamp": raw_scenario.get("timestamp", datetime.now(timezone.utc).isoformat()),
    }


def load_scenario(scenario_path: str) -> dict:
    path = Path(scenario_path)
    with open(path) as f:
        return json.load(f)
