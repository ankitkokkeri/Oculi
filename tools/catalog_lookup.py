import json
from pathlib import Path
from crewai.tools import tool

_DATA_DIR = Path(__file__).parent.parent / "data"


@tool("catalog_lookup")
def catalog_lookup(category: str) -> str:
    """Fetch all products in a given category from the catalog.

    Args:
        category: One of wireless_earbuds, carry_case, sports_accessory,
                  charging_dock, smart_wearable, lifestyle_gadget.

    Returns a JSON string listing all products in that category.
    """
    with open(_DATA_DIR / "products.json") as f:
        products = json.load(f)

    matches = [p for p in products if p["category"] == category]
    if not matches:
        return json.dumps({"error": f"No products found for category '{category}'."})
    return json.dumps(matches, indent=2)
