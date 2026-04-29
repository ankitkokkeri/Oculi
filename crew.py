import json
import os
from crewai import Crew, Task, LLM
from agents.intent_agent import build_intent_agent
from agents.recommender_agent import build_recommender_agent
from agents.outreach_agent import build_outreach_agent


def _make_llm(model: str) -> LLM:
    return LLM(model=model, api_key=os.environ.get("OPENAI_API_KEY"))


def _intent_task(agent, signal: dict, customer_id: str, on_complete=None) -> Task:
    return Task(
        description=(
            f"Analyse the following session signal and customer activity to determine intent.\n\n"
            f"Session Signal:\n{json.dumps(signal, indent=2)}\n\n"
            f"Use the customer_lookup tool with customer_id='{customer_id}' to retrieve the customer's "
            f"profile (AOV, lifecycle stage, channel preference) AND their full activity history "
            f"(past_orders, recently_browsed, recent_sessions).\n"
            f"Use the product_lookup tool with product_id='{signal['product_id']}' to get product details.\n\n"
            f"Pay close attention to recently_browsed: if a product has been viewed multiple times in "
            f"the last 7 days without being purchased, this signals latent intent — factor this into "
            f"your goal inference.\n\n"
            f"Determine: What is the customer trying to accomplish? What is their job-to-be-done? "
            f"What browsing or purchase context would help a recommender select the right cross-sell products?"
        ),
        expected_output=(
            "A JSON object with keys: inferred_goal (string), use_case_context (string), "
            "customer_context (string), confidence (float 0–1)."
        ),
        agent=agent,
        callback=on_complete,
    )


def _recommender_task(agent, signal: dict, intent_context: str = "", on_complete=None) -> Task:
    cart_ids = [item["product_id"] for item in signal.get("cart_contents", [])]
    primary_category = signal.get("product_category", "")
    return Task(
        description=(
            f"Based on the following intent analysis, select up to 2 cross-sell products.\n\n"
            f"Intent Analysis:\n{intent_context}\n\n"
            f"Current cart product IDs (do NOT recommend these): {cart_ids}\n"
            f"Primary product category in cart: {primary_category}\n\n"
            f"Use catalog_lookup to find products in complementary categories. "
            f"Use attach_rate_lookup to check co-purchase rates. "
            f"Use product_lookup to verify stock status. "
            f"Only recommend in-stock products not already in the cart. Maximum 2 recommendations."
        ),
        expected_output=(
            "A JSON object with key 'recommendations': a list of up to 2 objects, each with: "
            "product_id, name, category, price, attach_rate, recommendation_reason."
        ),
        agent=agent,
        callback=on_complete,
    )


def _outreach_task(agent, signal: dict, customer_id: str, on_complete=None) -> Task:
    return Task(
        description=(
            f"Given the recommendations from the previous task, craft the outreach message.\n\n"
            f"Customer ID: {customer_id}\n"
            f"Use customer_lookup to retrieve their full profile (lifecycle stage, AOV, channel "
            f"preference, previous_communications) AND their activity (past_orders, recently_browsed, "
            f"recent_sessions).\n\n"
            f"Use the activity data to calibrate tone and urgency:\n"
            f"- If a recommended product appears in recently_browsed, the customer is already warm "
            f"to it — be more direct and confident, no need to introduce it from scratch.\n"
            f"- If recent_sessions shows high activity in the last 48 hours, the customer is in an "
            f"active consideration phase — time the outreach accordingly.\n\n"
            f"Decide: channel (in_app / whatsapp / email), tone (confident/gentle), "
            f"whether to apply a bundle incentive (only for mid-AOV customers with moderate signals — "
            f"do NOT offer discounts to high-AOV loyal buyers unprompted).\n\n"
            f"Generate the full notification message ready for rendering."
        ),
        expected_output=(
            "A JSON object with keys: channel, tone, incentive_applied (bool), message_header, "
            "message_body, cta, secondary_recommendation (object with name and message), reasoning."
        ),
        agent=agent,
        callback=on_complete,
    )


def run_full_pipeline(signal: dict, callbacks: dict = None) -> Crew:
    """Build and return a Crew for the FULL pipeline (all 3 agents)."""
    callbacks = callbacks or {}
    llm_4o = _make_llm("gpt-4o")
    llm_mini = _make_llm("gpt-4o-mini")

    intent_agent = build_intent_agent(llm_4o)
    recommender_agent = build_recommender_agent(llm_4o)
    outreach_agent = build_outreach_agent(llm_mini)

    customer_id = signal["customer_id"]

    intent = _intent_task(intent_agent, signal, customer_id, callbacks.get("intent"))
    recommender = _recommender_task(recommender_agent, signal, on_complete=callbacks.get("recommender"))
    outreach = _outreach_task(outreach_agent, signal, customer_id, callbacks.get("outreach"))

    return Crew(
        agents=[intent_agent, recommender_agent, outreach_agent],
        tasks=[intent, recommender, outreach],
        verbose=True,
    )


def run_lightweight_pipeline(signal: dict, cached_intent: dict, callbacks: dict = None) -> Crew:
    """Build and return a Crew for LIGHTWEIGHT pipeline (Recommender + Outreach only)."""
    callbacks = callbacks or {}
    llm_4o = _make_llm("gpt-4o")
    llm_mini = _make_llm("gpt-4o-mini")

    recommender_agent = build_recommender_agent(llm_4o)
    outreach_agent = build_outreach_agent(llm_mini)

    customer_id = signal["customer_id"]
    intent_context = json.dumps(cached_intent, indent=2)

    recommender = _recommender_task(
        recommender_agent, signal, intent_context=intent_context, on_complete=callbacks.get("recommender")
    )
    outreach = _outreach_task(outreach_agent, signal, customer_id, callbacks.get("outreach"))

    return Crew(
        agents=[recommender_agent, outreach_agent],
        tasks=[recommender, outreach],
        verbose=True,
    )
