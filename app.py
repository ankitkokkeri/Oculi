import json
import os
import random
import sys
import threading
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from services.event_capture import load_scenario, capture_event
from services.orchestration import route
from services.feedback_capture import capture_feedback
from crew import run_full_pipeline, run_lightweight_pipeline

SCENARIOS = {
    "Scenario 1 — Full Pipeline (Priya, gym earbuds)": "scenarios/scenario_1.json",
    "Scenario 2 — Suppress (Rohan, cross-sell already in cart)": "scenarios/scenario_2.json",
    "Scenario 3 — Lightweight Pipeline (Ayesha, returning session)": "scenarios/scenario_3.json",
}

BASE_DIR = Path(__file__).parent


def _fresh_pipeline_state() -> dict:
    """Return a plain dict that is safe to share with a background thread."""
    return {
        "running": False,
        "pipeline_decision": None,
        "event_output": None,
        "orchestration_output": None,
        "intent_output": None,
        "recommender_output": None,
        "outreach_output": None,
        "feedback_output": None,
        "error": None,
        "step_statuses": {
            "event": "pending",
            "orchestration": "pending",
            "intent": "pending",
            "recommender": "pending",
            "outreach": "pending",
            "feedback": "pending",
        },
    }


def _parse_json_output(raw) -> dict:
    text = str(raw)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return {"raw": text}
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return {"raw": text}


def _run_pipeline(scenario_path: str, state: dict):
    """Background thread — writes only to `state` (a plain dict), never to st.session_state."""
    try:
        raw = load_scenario(str(BASE_DIR / scenario_path))
        signal = capture_event(raw)

        state["event_output"] = signal
        state["step_statuses"]["event"] = "complete"

        decision = route(signal)
        state["orchestration_output"] = decision
        state["step_statuses"]["orchestration"] = "complete"
        state["pipeline_decision"] = decision["decision"]

        if decision["decision"] == "SUPPRESS":
            for step in ["intent", "recommender", "outreach", "feedback"]:
                state["step_statuses"][step] = "suppressed"
            state["running"] = False
            return

        def on_intent(output):
            state["intent_output"] = _parse_json_output(output)
            state["step_statuses"]["intent"] = "complete"
            state["step_statuses"]["recommender"] = "running"

        def on_recommender(output):
            state["recommender_output"] = _parse_json_output(output)
            state["step_statuses"]["recommender"] = "complete"
            state["step_statuses"]["outreach"] = "running"

        def on_outreach(output):
            parsed = _parse_json_output(output)
            state["outreach_output"] = parsed
            state["step_statuses"]["outreach"] = "complete"

            outcome = random.choices(["ACCEPTED", "IGNORED", "REJECTED"], weights=[60, 30, 10])[0]
            rec_output = state.get("recommender_output") or {}
            feedback = capture_feedback(
                {
                    "recommendations": rec_output.get("recommendations", []),
                    "channel": parsed.get("channel", "unknown"),
                    "message_header": parsed.get("message_header", ""),
                },
                signal["customer_id"],
                outcome,
            )
            state["feedback_output"] = feedback
            state["step_statuses"]["feedback"] = "complete"
            state["running"] = False

        callbacks = {"intent": on_intent, "recommender": on_recommender, "outreach": on_outreach}

        if decision["decision"] == "FULL_PIPELINE":
            state["step_statuses"]["intent"] = "running"
            crew = run_full_pipeline(signal, callbacks)
        else:
            state["step_statuses"]["intent"] = "suppressed"
            state["intent_output"] = signal.get("cached_intent")
            state["step_statuses"]["recommender"] = "running"
            crew = run_lightweight_pipeline(signal, signal["cached_intent"], callbacks)

        crew.kickoff()

    except Exception as e:
        state["error"] = str(e)
        state["running"] = False


# ─── UI ──────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="ArcCommerce Cross-Sell Engine", layout="wide", page_icon="🎯")

# Initialise once — `pipeline` is the shared plain dict
if "pipeline" not in st.session_state:
    st.session_state["pipeline"] = _fresh_pipeline_state()

st.markdown(
    """
    <style>
    .step-card { border-radius: 8px; padding: 12px 16px; margin: 6px 0; font-size: 14px; }
    .step-pending { background: #f0f2f6; color: #666; }
    .step-running { background: #fff3cd; color: #856404; }
    .step-complete { background: #d1e7dd; color: #0f5132; }
    .step-suppressed { background: #e2e3e5; color: #495057; text-decoration: line-through; }
    .notif-card { border: 1.5px solid #dee2e6; border-radius: 12px; padding: 20px 24px;
                  background: #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
    .suppress-card { border: 2px solid #f8d7da; border-radius: 12px; padding: 20px 24px;
                     background: #fff5f5; }
    .rec-card { border: 1px solid #dee2e6; border-radius: 10px; padding: 14px 18px;
                background: #f8f9fa; margin: 6px 0; }
    .tag { display: inline-block; padding: 2px 10px; border-radius: 20px;
           font-size: 11px; font-weight: 600; margin-right: 6px; }
    .tag-in_app { background: #cfe2ff; color: #084298; }
    .tag-whatsapp { background: #d1e7dd; color: #0f5132; }
    .tag-email { background: #fff3cd; color: #664d03; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🎯 ArcCommerce — Agentic Cross-Sell Engine")
st.caption("Real-time cross-sell recommendations powered by CrewAI + GPT-4o")

# ── Top bar ──────────────────────────────────────────────────────────────────
col_sel, col_btn = st.columns([4, 1])
with col_sel:
    selected_label = st.selectbox("Select demo scenario", list(SCENARIOS.keys()), label_visibility="collapsed")
with col_btn:
    p = st.session_state["pipeline"]
    run_clicked = st.button("▶ Run Demo", type="primary", disabled=p["running"], use_container_width=True)

if run_clicked:
    # Replace the shared dict with a fresh one and kick off the thread
    fresh = _fresh_pipeline_state()
    fresh["running"] = True
    st.session_state["pipeline"] = fresh
    thread = threading.Thread(
        target=_run_pipeline,
        args=(SCENARIOS[selected_label], fresh),
        daemon=True,
    )
    thread.start()
    st.rerun()

# Grab a stable reference for this render pass
p = st.session_state["pipeline"]
statuses = p["step_statuses"]

st.divider()

# ── Main layout ──────────────────────────────────────────────────────────────
left_col, right_col = st.columns([1, 1], gap="large")

with left_col:
    st.subheader("Customer Context")
    event = p["event_output"]
    if event:
        customers_path = BASE_DIR / "data" / "customers.json"
        with open(customers_path) as f:
            all_customers = json.load(f)
        customer = next((c for c in all_customers if c["customer_id"] == event["customer_id"]), {})

        st.markdown(f"**{customer.get('name', event['customer_id'])}**")
        tier_color = {"new": "🟡", "repeat": "🟠", "loyal": "🟢"}.get(customer.get("lifecycle_stage", ""), "⚪")
        st.markdown(
            f"{tier_color} **Tier:** {customer.get('lifecycle_stage', '—').capitalize()} &nbsp;|&nbsp; "
            f"**AOV:** ₹{customer.get('aov_inr', '—'):,} &nbsp;|&nbsp; "
            f"**Channel:** {customer.get('preferred_channel', '—').replace('_', ' ').title()}"
        )
        st.markdown("**Session Event**")
        st.markdown(
            f"- **Event:** `{event['event_type']}` &nbsp; **Product:** {event['product_name']}\n"
            f"- **Search:** {event.get('search_query') or '—'} &nbsp; **Session depth:** {event['session_depth']}"
        )
        cart = event.get("cart_contents", [])
        if cart:
            st.markdown("**Cart Contents**")
            for item in cart:
                st.markdown(f"- {item['name']} — ₹{item['price']:,}")
        else:
            st.markdown("**Cart:** Empty")
    else:
        st.info("Run a scenario to see customer context.")

with right_col:
    st.subheader("Agent Pipeline")

    _STEP_LABELS = {
        "event": "Event Capture",
        "orchestration": "Orchestration",
        "intent": "Intent Agent",
        "recommender": "Recommender Agent",
        "outreach": "Outreach Agent",
        "feedback": "Feedback Capture",
    }
    _STATUS_ICONS = {"pending": "⬜", "running": "🔄", "complete": "✅", "suppressed": "🚫"}

    orch_output = p["orchestration_output"]
    intent_output = p["intent_output"]
    rec_output = p["recommender_output"]
    out_output = p["outreach_output"]
    fb_output = p["feedback_output"]

    summaries = {
        "event": (f"Signal: `{event['event_type']}` captured" if event else None),
        "orchestration": (f"Route: **{orch_output['decision']}** — {orch_output['reason']}" if orch_output else None),
        "intent": (
            f"Goal: {intent_output.get('inferred_goal', '—')} — confidence {intent_output.get('confidence', '—')}"
            if isinstance(intent_output, dict) and "inferred_goal" in intent_output
            else ("Skipped (cached intent used)" if statuses["intent"] == "suppressed" else None)
        ),
        "recommender": (f"{len(rec_output.get('recommendations', []))} product(s) recommended" if rec_output else None),
        "outreach": (
            f"Channel: `{out_output.get('channel', '—')}` | Header: \"{out_output.get('message_header', '—')}\""
            if out_output else None
        ),
        "feedback": (
            f"Outcome: **{fb_output.get('simulated_outcome', '—')}** — {fb_output.get('note', '')}"
            if fb_output else None
        ),
    }

    for step_key, label in _STEP_LABELS.items():
        status = statuses[step_key]
        icon = _STATUS_ICONS[status]
        summary = summaries.get(step_key)
        detail = f"<br><small>{summary}</small>" if summary else ""
        st.markdown(
            f'<div class="step-card step-{status}">{icon} <strong>{label}</strong>{detail}</div>',
            unsafe_allow_html=True,
        )

st.divider()

# ── Final Output ─────────────────────────────────────────────────────────────
st.subheader("Final Output")

pipeline_decision = p["pipeline_decision"]
outreach = p["outreach_output"]
orch_out = p["orchestration_output"]

if pipeline_decision == "SUPPRESS" and orch_out:
    st.markdown(
        f'<div class="suppress-card">'
        f'<div style="font-size:18px;font-weight:700;color:#842029;margin-bottom:8px;">🚫 Pipeline Suppressed</div>'
        f'<div style="font-size:14px;color:#444;">{orch_out["reason"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

elif outreach:
    channel = outreach.get("channel", "in_app")
    secondary = outreach.get("secondary_recommendation")
    secondary_html = ""
    if secondary:
        secondary_html = (
            f'<div style="border-top:1px solid #eee;padding-top:10px;margin-top:4px;font-size:13px;color:#666;">'
            f'Also: {secondary.get("message", "")} — <strong>{secondary.get("name", "")}</strong></div>'
        )
    incentive_html = (
        '<span style="font-size:12px;color:#198754;font-weight:600;">🏷️ Bundle offer</span>'
        if outreach.get("incentive_applied") else ""
    )
    st.markdown(
        f'<div class="notif-card">'
        f'<span class="tag tag-{channel}">{channel.replace("_"," ").upper()}</span>{incentive_html}'
        f'<div style="font-size:17px;font-weight:700;color:#1a1a2e;margin-top:10px;">{outreach.get("message_header","")}</div>'
        f'<div style="font-size:14px;color:#444;line-height:1.5;margin:8px 0 12px;">{outreach.get("message_body","")}</div>'
        f'{secondary_html}'
        f'<div style="margin-top:14px;"><button style="background:#0d6efd;color:white;border:none;'
        f'border-radius:6px;padding:8px 20px;font-size:14px;">{outreach.get("cta","Add to Cart")}</button></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    recs = (p.get("recommender_output") or {}).get("recommendations", [])
    if recs:
        st.markdown("**Recommended Products**")
        rec_cols = st.columns(len(recs))
        for col, rec in zip(rec_cols, recs):
            with col:
                st.markdown(
                    f'<div class="rec-card">'
                    f'<div style="font-weight:700;font-size:15px;">{rec.get("name","")}</div>'
                    f'<div style="color:#198754;font-weight:600;font-size:14px;">₹{rec.get("price",0):,}</div>'
                    f'<div style="font-size:12px;color:#666;margin-top:4px;">Attach rate: <strong>{int(rec.get("attach_rate",0)*100)}%</strong></div>'
                    f'<div style="font-size:12px;color:#444;margin-top:6px;">{rec.get("recommendation_reason","")}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
else:
    if not p["running"] and pipeline_decision is None:
        st.info("Select a scenario and click **Run Demo** to see the output.")
    elif p["running"]:
        st.info("⏳ Pipeline running — agents are reasoning…")

# ── Agent Reasoning Logs ──────────────────────────────────────────────────────
st.divider()
st.subheader("Agent Reasoning Logs")

log_sections = [
    ("Intent Agent", p["intent_output"]),
    ("Recommender Agent", p["recommender_output"]),
    ("Outreach Agent", p["outreach_output"]),
    ("Feedback Log", p["feedback_output"]),
]

any_log = any(data for _, data in log_sections)
for label, data in log_sections:
    if data:
        with st.expander(f"View {label} output"):
            st.json(data)

if not any_log:
    st.caption("Logs will appear here after the pipeline runs.")

# ── Error display ─────────────────────────────────────────────────────────────
if p.get("error"):
    st.error(f"Pipeline error: {p['error']}")

# ── Auto-refresh while running ────────────────────────────────────────────────
if p["running"]:
    time.sleep(1)
    st.rerun()
