from crewai import Agent, LLM
from tools.customer_lookup import customer_lookup
from tools.product_lookup import product_lookup


def build_intent_agent(llm: LLM) -> Agent:
    return Agent(
        role="Customer Intent Analyst",
        goal=(
            "Deeply understand what the customer is trying to accomplish in their current session. "
            "Identify their job-to-be-done, use case context, and any information that would help "
            "a recommender decide what to cross-sell."
        ),
        backstory=(
            "You are a behavioural analyst specialised in e-commerce intent inference. "
            "You look at a customer's session signals, purchase history, and profile to construct "
            "a precise picture of their current goal — not what they clicked, but why."
        ),
        tools=[customer_lookup, product_lookup],
        llm=llm,
        verbose=True,
    )
