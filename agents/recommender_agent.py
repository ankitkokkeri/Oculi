from crewai import Agent, LLM
from tools.catalog_lookup import catalog_lookup
from tools.attach_rate_lookup import attach_rate_lookup
from tools.product_lookup import product_lookup


def build_recommender_agent(llm: LLM) -> Agent:
    return Agent(
        role="Cross-Sell Recommender",
        goal=(
            "Given customer intent and current cart, select up to 2 in-stock products to recommend "
            "as cross-sells, ranked by relevance and historical attach rate. "
            "Never recommend products already in the cart."
        ),
        backstory=(
            "You are a product recommendation engine trained on attach rate data and customer intent signals. "
            "You select the most relevant complementary products for a customer's specific use case, "
            "balancing intent alignment with historical co-purchase strength."
        ),
        tools=[catalog_lookup, attach_rate_lookup, product_lookup],
        llm=llm,
        verbose=True,
    )
