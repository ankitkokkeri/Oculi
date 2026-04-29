import json
from pathlib import Path
from crewai.tools import tool

_DATA_DIR = Path(__file__).parent.parent / "data"


@tool("product_lookup")
def product_lookup(product_id: str) -> str:
    """Fetch full product details by product_id.

    Returns a JSON string with product metadata including category, price, stock status, and compatibility.
    """
    with open(_DATA_DIR / "products.json") as f:
        products = json.load(f)

    product = next((p for p in products if p["product_id"] == product_id), None)
    if not product:
        return json.dumps({"error": f"Product {product_id} not found."})
    return json.dumps(product, indent=2)
