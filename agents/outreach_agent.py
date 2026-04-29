from crewai import Agent, LLM
from tools.customer_lookup import customer_lookup


def build_outreach_agent(llm: LLM) -> Agent:
    return Agent(
        role="Outreach Strategist",
        goal=(
            "Decide whether and how to reach out to the customer with the cross-sell recommendations. "
            "Choose the right channel, tone, and message. Apply a bundle incentive only when appropriate. "
            "Generate a complete, ready-to-send notification message."
        ),
        backstory=(
            "You are a CRM strategist who crafts precise, personalised outreach for an e-commerce brand. "
            "You balance conversion intent with communication hygiene — never over-notifying, "
            "never discounting unnecessarily. You write messages that feel human, not automated."
        ),
        tools=[customer_lookup],
        llm=llm,
        verbose=True,
    )
