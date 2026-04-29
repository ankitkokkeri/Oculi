SUPPRESS_COOLDOWN_MINUTES = 20
MIN_SESSION_DEPTH = 2
HIGH_SIGNAL_EVENTS = {"cart_addition", "checkout_start", "wishlist_add"}


def _cart_has_cross_sell(cart_contents: list, primary_category: str) -> bool:
    """Return True if the cart already contains a product from a different category."""
    categories_in_cart = {item["category"] for item in cart_contents}
    return len(categories_in_cart - {primary_category}) > 0


def route(signal: dict) -> dict:
    cart = signal.get("cart_contents", [])
    last_outreach = signal.get("last_outreach_minutes_ago")
    rejected = signal.get("cross_sell_rejected_this_session", False)
    returning = signal.get("returning_session", False)
    cached_intent = signal.get("cached_intent")
    event_type = signal.get("event_type", "")
    session_depth = signal.get("session_depth", 1)
    primary_category = signal.get("product_category", "")

    # Suppression checks (in order)
    if _cart_has_cross_sell(cart, primary_category):
        return {
            "decision": "SUPPRESS",
            "reason": "A complementary product is already present in the cart.",
        }

    if last_outreach is not None and last_outreach < SUPPRESS_COOLDOWN_MINUTES:
        return {
            "decision": "SUPPRESS",
            "reason": f"Outreach was sent {last_outreach} minutes ago — cooldown of {SUPPRESS_COOLDOWN_MINUTES} minutes not yet elapsed.",
        }

    if rejected:
        return {
            "decision": "SUPPRESS",
            "reason": "Customer rejected a cross-sell recommendation earlier this session.",
        }

    if event_type not in HIGH_SIGNAL_EVENTS and session_depth < MIN_SESSION_DEPTH:
        return {
            "decision": "SUPPRESS",
            "reason": "Signal strength too low — passive page view or app open only.",
        }

    # Lightweight: returning session within window with cached intent
    if returning and cached_intent is not None:
        return {
            "decision": "LIGHTWEIGHT_PIPELINE",
            "reason": "Returning session with cached intent available — skipping Intent Agent.",
        }

    return {
        "decision": "FULL_PIPELINE",
        "reason": "High-signal event detected, no active cooldown, no cross-sell in cart.",
    }
