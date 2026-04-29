import json
from pathlib import Path
from crewai.tools import tool

_DATA_DIR = Path(__file__).parent.parent / "data"


@tool("attach_rate_lookup")
def attach_rate_lookup(category_a: str, category_b: str) -> str:
    """Look up historical attach rate between two product categories.

    Args:
        category_a: Source product category (e.g. wireless_earbuds).
        category_b: Target product category to check co-purchase rate for.

    Returns a JSON string with the attach rate value (0.0–1.0).
    """
    with open(_DATA_DIR / "attach_rates.json") as f:
        rates = json.load(f)

    rate = rates.get(category_a, {}).get(category_b)
    if rate is None:
        return json.dumps({"attach_rate": 0.0, "note": f"No data for {category_a} → {category_b}."})
    return json.dumps({"category_a": category_a, "category_b": category_b, "attach_rate": rate})
