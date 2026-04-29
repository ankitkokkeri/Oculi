import json
from pathlib import Path
from crewai.tools import tool

_DATA_DIR = Path(__file__).parent.parent / "data"


def _load_json(filename: str):
    with open(_DATA_DIR / filename) as f:
        return json.load(f)


@tool("customer_lookup")
def customer_lookup(customer_id: str) -> str:
    """Fetch a merged customer object containing profile and full activity history.

    Returns a JSON string with:
    - profile: customer details, AOV, channel preference, previous communications
    - activity: past_orders, recently_browsed, recent_sessions
    """
    customers = _load_json("customers.json")
    activities = _load_json("customer_activity.json")

    profile = next((c for c in customers if c["customer_id"] == customer_id), None)
    if not profile:
        return json.dumps({"error": f"Customer {customer_id} not found."})

    activity = next((a for a in activities if a["customer_id"] == customer_id), {})

    return json.dumps({"profile": profile, "activity": activity}, indent=2)
