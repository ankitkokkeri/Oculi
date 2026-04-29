import json
from pathlib import Path
from crewai.tools import tool

_DATA_DIR = Path(__file__).parent.parent / "data"


def _load_json(filename: str) -> list:
    with open(_DATA_DIR / filename) as f:
        return json.load(f)


@tool("customer_lookup")
def customer_lookup(customer_id: str) -> str:
    """Fetch customer profile and order history by customer_id.

    Returns a JSON string containing the customer profile and their past orders.
    """
    customers = _load_json("customers.json")
    orders = _load_json("order_history.json")

    profile = next((c for c in customers if c["customer_id"] == customer_id), None)
    if not profile:
        return json.dumps({"error": f"Customer {customer_id} not found."})

    customer_orders = [o for o in orders if o["customer_id"] == customer_id]
    return json.dumps({"profile": profile, "order_history": customer_orders}, indent=2)
