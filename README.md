# Oculi — Agentic Cross-Sell Recommendation Engine

Oculi is an agentic cross-sell recommendation system for a D2C electronics brand. It monitors real-time session signals, reasons over customer history and intent using LLM agents, and generates personalised cross-sell outreach — at the right moment, on the right channel, with the right message.

Built as a demo prototype using [CrewAI](https://crewai.com) and [Streamlit](https://streamlit.io).

---

## What It Does

Traditional e-commerce cross-sell logic relies on static co-purchase tables. Oculi replaces this with a reasoning pipeline:

1. **Captures** a session event (e.g. a cart addition)
2. **Orchestrates** routing — decides whether to run the full pipeline, a lightweight pipeline, or suppress entirely
3. **Infers intent** — an LLM agent reasons about what the customer is trying to accomplish
4. **Recommends** — an LLM agent selects the best cross-sell products given intent and cart context
5. **Generates outreach** — an LLM agent crafts the message, picks the channel, and decides on incentives
6. **Logs feedback** — simulates the recommendation outcome for the feedback loop

---

## Architecture

```
[Session Event]
      ↓
Event Capture Service        ← Deterministic data normalisation
      ↓
Orchestration Logic          ← Rule-based routing
      ↓ (if FULL or LIGHTWEIGHT)
Intent Agent (GPT-4o)        ← LLM: what is the customer trying to accomplish?
      ↓
Recommender Agent (GPT-4o)   ← LLM: what should be cross-sold?
      ↓
Outreach Agent (GPT-4o-mini) ← LLM: how and when to reach out?
      ↓
Feedback Capture Service     ← Simulated outcome logging
```

### Routing Decisions

| Route | Condition |
|---|---|
| `FULL_PIPELINE` | High-signal event, no cooldown, no cross-sell already in cart |
| `LIGHTWEIGHT_PIPELINE` | Returning session within 30 mins, intent already cached |
| `SUPPRESS` | Cross-sell in cart, outreach sent < 20 mins ago, or prior rejection this session |

---

## Project Structure

```
crosssell-agent/
├── app.py                      # Streamlit UI + threading logic
├── crew.py                     # CrewAI crew assembly (full + lightweight variants)
├── agents/
│   ├── intent_agent.py
│   ├── recommender_agent.py
│   └── outreach_agent.py
├── services/
│   ├── event_capture.py
│   ├── orchestration.py
│   └── feedback_capture.py
├── tools/
│   ├── customer_lookup.py      # Merges customers.json + customer_activity.json
│   ├── product_lookup.py
│   ├── catalog_lookup.py
│   └── attach_rate_lookup.py
├── data/
│   ├── products.json           # 15 products across 6 categories
│   ├── customers.json          # 3 demo customers
│   ├── customer_activity.json  # Past orders, browsing history, recent sessions
│   └── attach_rates.json       # Product-pair co-purchase rates
├── scenarios/
│   ├── scenario_1.json         # Full pipeline — high signal
│   ├── scenario_2.json         # Suppress — cross-sell already in cart
│   └── scenario_3.json         # Lightweight — returning session
├── .env
└── requirements.txt
```

---

## Demo Scenarios

**Scenario 1 — Full Pipeline**
Priya (repeat buyer) adds ArcBuds Pro after searching "wireless earbuds for gym". Session depth: 4 pages, no prior outreach. Runs all three agents → in-app nudge with carry case + armband recommendation.

**Scenario 2 — Suppress**
Rohan (first-time buyer) adds ArcBuds Pro, but ArcCase Pro is already in the cart. Pipeline suppresses immediately and displays the suppression reason.

**Scenario 3 — Lightweight Pipeline**
Ayesha (loyal customer) returns 18 minutes after her last session with cached intent. Intent Agent is skipped — Recommender and Outreach agents run with the cached intent.

---

## Setup

### Prerequisites

- Python 3.10+
- An OpenAI API key

### Install

```bash
git clone <repo-url>
cd crosssell-agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configure

Create a `.env` file in the project root:

```
OPENAI_API_KEY=your_key_here
```

### Run

```bash
streamlit run app.py
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | Demo UI |
| `crewai` | LLM agent orchestration |
| `crewai-tools` | Tool support for CrewAI agents |
| `openai` | GPT-4o / GPT-4o-mini inference |
| `python-dotenv` | API key loading from `.env` |

---

## Constraints

- **Cross-sell only.** The system does not optimise for checkout completion or cart abandonment recovery.
- **No real outreach.** WhatsApp, push, and email are fully simulated — no external API calls.
- **No database.** All state lives in JSON files and `st.session_state`.
- **All data is fabricated.** Product names, prices, customer profiles, and attach rates are fictional.
