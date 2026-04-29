SUPPRESS_COOLDOWN_MINUTES = 20
HIGH_SIGNAL_EVENTS = {"cart_addition", "checkout_start", "wishlist_add"}

# session_depth tiers:
#   >= 4  → HIGH   — customer actively exploring, strong cross-sell receptivity
#   2–3   → MEDIUM — moderate intent, proceed with standard pipeline
#   1     → LOW    — likely impulsive/direct-link, suppress unless event is high-signal
_DEPTH_HIGH = 4
_DEPTH_MEDIUM_MIN = 2


def _signal_strength(event_type: str, session_depth: int) -> str:
    if session_depth >= _DEPTH_HIGH:
        return "HIGH"
    if session_depth >= _DEPTH_MEDIUM_MIN:
        return "MEDIUM"
    return "HIGH" if event_type in HIGH_SIGNAL_EVENTS else "LOW"


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

    strength = _signal_strength(event_type, session_depth)

    # Suppression checks (in order)
    if _cart_has_cross_sell(cart, primary_category):
        return {
            "decision": "SUPPRESS",
            "signal_strength": strength,
            "reason": "A complementary product is already present in the cart.",
        }

    if last_outreach is not None and last_outreach < SUPPRESS_COOLDOWN_MINUTES:
        return {
            "decision": "SUPPRESS",
            "signal_strength": strength,
            "reason": f"Outreach was sent {last_outreach} minutes ago — cooldown of {SUPPRESS_COOLDOWN_MINUTES} minutes not yet elapsed.",
        }

    if rejected:
        return {
            "decision": "SUPPRESS",
            "signal_strength": strength,
            "reason": "Customer rejected a cross-sell recommendation earlier this session.",
        }

    if strength == "LOW":
        return {
            "decision": "SUPPRESS",
            "signal_strength": strength,
            "reason": f"Signal strength too low — session depth {session_depth} with non-high-signal event '{event_type}'.",
        }

    if returning and cached_intent is not None:
        return {
            "decision": "LIGHTWEIGHT_PIPELINE",
            "signal_strength": strength,
            "reason": "Returning session with cached intent available — skipping Intent Agent.",
        }

    return {
        "decision": "FULL_PIPELINE",
        "signal_strength": strength,
        "reason": f"Signal strength {strength} (session depth {session_depth}), no active cooldown, no cross-sell in cart.",
    }
