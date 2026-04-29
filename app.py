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
from tools.customer_lookup import set_overrides

BASE_DIR = Path(__file__).parent

SCENARIOS = [
    {
        "path": "scenarios/scenario_1.json",
        "customer_name": "Priya Sharma",
        "customer_id": "C001",
        "lifecycle": "repeat",
        "scenario_label": "Scenario 1",
        "scenario_desc": "High-signal cart addition — gym earbuds",
        "route_tag": "FULL PIPELINE",
    },
    {
        "path": "scenarios/scenario_2.json",
        "customer_name": "Rohan Verma",
        "customer_id": "C002",
        "lifecycle": "new",
        "scenario_label": "Scenario 2",
        "scenario_desc": "Cross-sell already in cart",
        "route_tag": "SUPPRESS",
    },
    {
        "path": "scenarios/scenario_3.json",
        "customer_name": "Ayesha Khan",
        "customer_id": "C003",
        "lifecycle": "loyal",
        "scenario_label": "Scenario 3",
        "scenario_desc": "Returning session — cached intent",
        "route_tag": "LIGHTWEIGHT",
    },
]

_TIER_ICON = {"new": "🟡", "repeat": "🟠", "loyal": "🟢"}
_ROUTE_COLORS = {
    "FULL PIPELINE": ("#0d6efd", "#e7f0ff"),
    "SUPPRESS": ("#dc3545", "#fff0f0"),
    "LIGHTWEIGHT": ("#198754", "#e8f5e9"),
}


def _fresh_pipeline_state() -> dict:
    return {
        "running": False,
        "selected_scenario": None,
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


_PIPELINE_STEPS = [
    ("event",        "Event Capture",      "📡", False),
    ("orchestration","Orchestration",      "🧭", False),
    ("intent",       "Intent Agent",       "🤖", True),
    ("recommender",  "Recommender Agent",  "🤖", True),
    ("outreach",     "Outreach Agent",     "🤖", True),
    ("feedback",     "Feedback Capture",   "📋", False),
]


def _build_pipeline_html(statuses: dict, summaries: dict) -> str:
    parts = ['<div style="display:flex;flex-direction:column;">']
    for i, (key, label, icon, is_agent) in enumerate(_PIPELINE_STEPS):
        status = statuses.get(key, "pending")
        raw_summary = summaries.get(key) or ""
        summary = raw_summary.replace("**", "").replace("`", "")
        badge_text = {"pending": "Waiting", "running": "Running…", "complete": "Done", "suppressed": "Skipped"}[status]

        agent_tag = (
            '<span style="font-size:9px;font-weight:700;letter-spacing:0.6px;'
            'background:#e0e7ff;color:#3730a3;padding:1px 7px;border-radius:10px;'
            'margin-left:8px;vertical-align:middle;">AI AGENT</span>'
            if is_agent else ""
        )
        summary_html = (
            f'<div class="pipeline-summary">{summary}</div>' if summary else ""
        )

        parts.append(
            f'<div class="pipeline-node pipeline-node-{status}">'
            f'  <div class="pipeline-icon icon-{status}">{icon}</div>'
            f'  <div style="flex:1;min-width:0;">'
            f'    <div class="pipeline-label label-{status}">{label}{agent_tag}</div>'
            f'    {summary_html}'
            f'  </div>'
            f'  <div class="pipeline-badge badge-{status}">{badge_text}</div>'
            f'</div>'
        )

        if i < len(_PIPELINE_STEPS) - 1:
            conn_cls = f"conn-{status}"
            parts.append(
                f'<div class="connector {conn_cls}">'
                f'  <div class="connector-line" style="background:currentColor;"></div>'
                f'  <div class="connector-arrow">▼</div>'
                f'</div>'
            )

    parts.append("</div>")
    return "".join(parts)


# ─── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(page_title="ArcCommerce Cross-Sell Engine", layout="wide", page_icon="🎯")

if "pipeline" not in st.session_state:
    st.session_state["pipeline"] = _fresh_pipeline_state()
if "customer_overrides" not in st.session_state:
    st.session_state["customer_overrides"] = {}
if "activity_overrides" not in st.session_state:
    st.session_state["activity_overrides"] = {}


_LIFECYCLE_OPTIONS  = ["new", "repeat", "loyal"]
_CHANNEL_OPTIONS    = ["in_app", "whatsapp", "email"]


@st.dialog("Edit Customer Data", width="large")
def _edit_customer_modal(cid: str, name: str):
    customers_path = BASE_DIR / "data" / "customers.json"
    activity_path  = BASE_DIR / "data" / "customer_activity.json"
    with open(customers_path) as f:
        all_customers = json.load(f)
    with open(activity_path) as f:
        all_activities = json.load(f)

    cust_ovr = st.session_state.get("customer_overrides", {})
    act_ovr  = st.session_state.get("activity_overrides", {})
    current_profile  = cust_ovr.get(cid) or next(
        (c for c in all_customers  if c["customer_id"] == cid), {}
    )
    current_activity = act_ovr.get(cid) or next(
        (a for a in all_activities if a["customer_id"] == cid), {}
    )

    is_overridden = cid in cust_ovr or cid in act_ovr
    hdr_col, toggle_col = st.columns([3, 2])
    with hdr_col:
        st.markdown(
            f"Editing mock data for **{name}**.  \n"
            "<small style='color:#888;'>Temporary — discarded on page refresh.</small>",
            unsafe_allow_html=True,
        )
        if is_overridden:
            st.info("This customer has active overrides.", icon="✏️")
    with toggle_col:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        json_mode = st.toggle("{ } Raw JSON", key=f"modal_json_mode_{cid}")

    st.divider()

    tab_profile, tab_activity = st.tabs(["👤 Customer Profile", "📋 Activity Data"])

    # ── Profile tab ──────────────────────────────────────────────────────────
    with tab_profile:
        if json_mode:
            st.text_area(
                "Profile JSON",
                value=json.dumps(current_profile, indent=2),
                height=380,
                key=f"modal_profile_json_{cid}",
            )
        else:
            col_l, col_r = st.columns(2)
            with col_l:
                st.text_input(
                    "Name",
                    value=current_profile.get("name", ""),
                    key=f"form_name_{cid}",
                )
                lc = current_profile.get("lifecycle_stage", "new")
                st.selectbox(
                    "Lifecycle Stage",
                    options=_LIFECYCLE_OPTIONS,
                    index=_LIFECYCLE_OPTIONS.index(lc) if lc in _LIFECYCLE_OPTIONS else 0,
                    format_func=str.capitalize,
                    key=f"form_lifecycle_{cid}",
                )
            with col_r:
                st.number_input(
                    "Avg Order Value (₹)",
                    min_value=0,
                    max_value=100_000,
                    step=100,
                    value=int(current_profile.get("aov_inr", 0)),
                    key=f"form_aov_{cid}",
                )
                ch = current_profile.get("preferred_channel", "in_app")
                st.selectbox(
                    "Preferred Channel",
                    options=_CHANNEL_OPTIONS,
                    index=_CHANNEL_OPTIONS.index(ch) if ch in _CHANNEL_OPTIONS else 0,
                    format_func=lambda x: x.replace("_", " ").title(),
                    key=f"form_channel_{cid}",
                )

            st.toggle(
                "Opted into WhatsApp",
                value=bool(current_profile.get("opted_in_whatsapp", False)),
                key=f"form_whatsapp_{cid}",
            )

            st.markdown(
                "<div style='font-size:13px;font-weight:600;margin-top:12px;margin-bottom:4px;'>"
                "Previous Communications <span style='font-weight:400;color:#888;font-size:11px;'>(JSON)</span>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.text_area(
                "previous_communications",
                value=json.dumps(current_profile.get("previous_communications", []), indent=2),
                height=160,
                label_visibility="collapsed",
                key=f"form_comms_{cid}",
            )

    # ── Activity tab — always JSON (nested arrays) ────────────────────────────
    with tab_activity:
        st.caption("Past orders, browsing history, and session events — edited as JSON.")
        st.text_area(
            "Activity JSON",
            value=json.dumps(current_activity, indent=2),
            height=400,
            key=f"modal_activity_json_{cid}",
        )

    # ── Actions ───────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    col_apply, col_reset, _ = st.columns([1, 1, 3])

    with col_apply:
        if st.button("Apply Changes", type="primary", key=f"modal_apply_{cid}", use_container_width=True):
            errors     = []
            new_profile  = None
            new_activity = None

            # Build profile from active view
            if json_mode:
                try:
                    new_profile = json.loads(st.session_state[f"modal_profile_json_{cid}"])
                except json.JSONDecodeError as e:
                    errors.append(f"Profile JSON error: {e}")
            else:
                try:
                    comms = json.loads(st.session_state[f"form_comms_{cid}"])
                except json.JSONDecodeError as e:
                    errors.append(f"Previous Communications JSON error: {e}")
                    comms = current_profile.get("previous_communications", [])
                if not errors:
                    new_profile = {
                        **current_profile,
                        "name":                   st.session_state[f"form_name_{cid}"],
                        "lifecycle_stage":         st.session_state[f"form_lifecycle_{cid}"],
                        "aov_inr":                st.session_state[f"form_aov_{cid}"],
                        "preferred_channel":       st.session_state[f"form_channel_{cid}"],
                        "opted_in_whatsapp":       st.session_state[f"form_whatsapp_{cid}"],
                        "previous_communications": comms,
                    }

            # Activity always from JSON text area
            try:
                new_activity = json.loads(st.session_state[f"modal_activity_json_{cid}"])
            except json.JSONDecodeError as e:
                errors.append(f"Activity JSON error: {e}")

            if errors:
                for err in errors:
                    st.error(err)
            else:
                st.session_state["customer_overrides"][cid] = new_profile
                st.session_state["activity_overrides"][cid] = new_activity
                st.rerun()

    with col_reset:
        if st.button("Reset to Default", key=f"modal_reset_{cid}", use_container_width=True):
            st.session_state["customer_overrides"].pop(cid, None)
            st.session_state["activity_overrides"].pop(cid, None)
            st.rerun()

st.markdown(
    """
    <style>
    /* ── Remove Streamlit's default top padding ── */
    .block-container {
        padding-top: 3rem !important;
    }
    /* ── Sidebar width — default 25vw, resizable by dragging ── */
    section[data-testid="stSidebar"] {
        width: 25vw;
        min-width: 25vw !important;
    }
    section[data-testid="stSidebar"] > div:first-child {
        width: 25vw;
        min-width: 25vw !important;
    }
    /* ── Sidebar dark background + remove top gap ── */
    section[data-testid="stSidebar"] > div:first-child {
        background-color: #000000 !important;
        padding-top: 0 !important;
    }
    /* Collapse the sidebar header (collapse-arrow row) to minimal height */
    [data-testid="stSidebarHeader"] {
        min-height: 0 !important;
        height: 2rem !important;
        padding: 0 !important;
    }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown small,
    section[data-testid="stSidebar"] .stCaption p {
        color: #aaa !important;
    }
    /* Sidebar container cards (border=True) */
    section[data-testid="stSidebar"] .stContainer > div:first-child {
        background: #111118 !important;
        border-color: #2a2a3a !important;
        border-radius: 12px !important;
        padding: 14px 16px 12px !important;
    }
    /* Simulate Event button inside sidebar */
    section[data-testid="stSidebar"] .stButton > button {
        background: #1a1aff;
        color: #ffffff;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        font-size: 13px;
        width: 100%;
        padding: 8px 0;
        margin-top: 2px;
        transition: background 0.15s;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: #3333ff;
        color: #ffffff;
        border: none;
    }
    section[data-testid="stSidebar"] .stButton > button:disabled {
        background: #2a2a3a !important;
        color: #555 !important;
    }
    /* Edit Data button — secondary style */
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] > div:last-child .stButton > button {
        background: #1e1e2e;
        color: #aaa;
        border: 1px solid #3a3a4a;
    }
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] > div:last-child .stButton > button:hover {
        background: #2a2a3e;
        color: #ccc;
        border-color: #5a5a7a;
    }

    /* ── Sidebar user card text ── */
    .user-card-name {
        font-size: 15px;
        font-weight: 700;
        color: #f0f0f0;
        margin-bottom: 2px;
    }
    .user-card-scenario {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        margin-bottom: 2px;
    }
    .user-card-desc {
        font-size: 12px;
        color: #888;
        margin-bottom: 10px;
    }
    .route-badge {
        display: inline-block;
        padding: 2px 9px;
        border-radius: 20px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.4px;
        margin-bottom: 4px;
    }

    /* ── Customer context card ── */
    .ctx-card {
        border: 1px solid #e0e4ea;
        border-radius: 14px;
        padding: 20px 22px;
        background: #ffffff;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .ctx-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 16px;
    }
    .ctx-avatar {
        width: 44px; height: 44px;
        border-radius: 50%;
        background: linear-gradient(135deg, #667eea, #764ba2);
        display: flex; align-items: center; justify-content: center;
        font-size: 18px; flex-shrink: 0;
    }
    .ctx-name { font-size: 18px; font-weight: 700; color: #1a1a2e; }
    .ctx-tier { font-size: 12px; color: #6c757d; margin-top: 1px; }
    .ctx-stats {
        display: flex; gap: 0;
        border: 1px solid #e8eaed;
        border-radius: 10px;
        overflow: hidden;
        margin-bottom: 16px;
    }
    .ctx-stat {
        flex: 1; padding: 10px 14px; text-align: center;
        border-right: 1px solid #e8eaed;
        background: #f8f9fa;
    }
    .ctx-stat:last-child { border-right: none; }
    .ctx-stat-label { font-size: 10px; color: #888; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px; }
    .ctx-stat-value { font-size: 15px; font-weight: 700; color: #1a1a2e; margin-top: 2px; }
    .ctx-section-title {
        font-size: 11px; font-weight: 700; color: #888;
        text-transform: uppercase; letter-spacing: 0.5px;
        margin: 14px 0 8px;
    }
    .ctx-event-box {
        background: #f4f6ff;
        border: 1px solid #d8deff;
        border-radius: 10px;
        padding: 12px 14px;
    }
    .ctx-event-row {
        display: flex; align-items: center; gap: 8px;
        font-size: 13px; color: #333; margin-bottom: 6px;
    }
    .ctx-event-row:last-child { margin-bottom: 0; }
    .ctx-event-label { font-size: 11px; font-weight: 600; color: #888; width: 90px; flex-shrink: 0; }
    .ctx-event-val { font-weight: 500; color: #1a1a2e; }
    .ctx-event-code {
        background: #e8ecff; color: #3451b2;
        padding: 1px 8px; border-radius: 5px;
        font-size: 12px; font-family: monospace; font-weight: 600;
    }
    .ctx-search-pill {
        background: #fff3cd; color: #664d03;
        padding: 2px 10px; border-radius: 20px;
        font-size: 12px; font-style: italic;
    }
    .ctx-depth-badge {
        padding: 1px 9px; border-radius: 20px; font-size: 11px; font-weight: 700;
    }
    .depth-high { background: #d1f5e3; color: #0c6636; }
    .depth-med  { background: #fff3cd; color: #664d03; }
    .depth-low  { background: #f8d7da; color: #842029; }
    .cart-item {
        display: flex; justify-content: space-between; align-items: center;
        padding: 8px 12px;
        background: #f8f9fa;
        border: 1px solid #e8eaed;
        border-radius: 8px;
        margin-bottom: 6px;
        font-size: 13px;
    }
    .cart-item-name { font-weight: 600; color: #1a1a2e; }
    .cart-item-price { color: #198754; font-weight: 700; }
    .cart-empty { font-size: 13px; color: #aaa; font-style: italic; }

    /* ── Pipeline flow ── */
    @keyframes pulse-ring {
        0%   { box-shadow: 0 0 0 0 rgba(251,191,36,0.5); }
        70%  { box-shadow: 0 0 0 8px rgba(251,191,36,0); }
        100% { box-shadow: 0 0 0 0 rgba(251,191,36,0); }
    }
    .pipeline-node {
        display: flex; align-items: center; gap: 14px;
        border-radius: 12px; padding: 13px 16px;
        border: 1.5px solid transparent; transition: all 0.3s;
    }
    .pipeline-node-pending    { background:#f4f6fa; border-color:#dde1ea; }
    .pipeline-node-running    { background:#fffbeb; border-color:#f59e0b; animation: pulse-ring 1.4s ease-out infinite; }
    .pipeline-node-complete   { background:#f0fdf4; border-color:#22c55e; }
    .pipeline-node-suppressed { background:#fff1f2; border-color:#fca5a5; opacity:0.75; }
    .pipeline-icon {
        width:44px; height:44px; border-radius:50%;
        display:flex; align-items:center; justify-content:center;
        font-size:20px; flex-shrink:0; border:2px solid transparent;
    }
    .icon-pending    { background:#eaecf0; border-color:#d1d5db; }
    .icon-running    { background:#fef3c7; border-color:#f59e0b; }
    .icon-complete   { background:#dcfce7; border-color:#22c55e; }
    .icon-suppressed { background:#ffe4e6; border-color:#fca5a5; }
    .pipeline-label {
        font-size:14px; font-weight:700; line-height:1.2;
    }
    .label-pending    { color:#6b7280; }
    .label-running    { color:#92400e; }
    .label-complete   { color:#15803d; }
    .label-suppressed { color:#be123c; text-decoration:line-through; }
    .pipeline-summary { font-size:12px; color:#888; margin-top:3px; line-height:1.4; }
    .pipeline-badge {
        margin-left:auto; padding:3px 11px; border-radius:20px;
        font-size:11px; font-weight:700; white-space:nowrap; flex-shrink:0;
    }
    .badge-pending    { background:#f3f4f6; color:#9ca3af; }
    .badge-running    { background:#fde68a; color:#92400e; }
    .badge-complete   { background:#bbf7d0; color:#15803d; }
    .badge-suppressed { background:#fecdd3; color:#be123c; }
    .connector {
        display:flex; flex-direction:column; align-items:center;
        height:28px; gap:0; margin: 1px 0;
    }
    .connector-line { width:2px; flex:1; }
    .connector-arrow { font-size:9px; line-height:1; }
    .conn-pending    { color:#d1d5db; }
    .conn-running    { color:#f59e0b; }
    .conn-complete   { color:#22c55e; }
    .conn-suppressed { color:#fca5a5; }

    /* ── Notification card ── */
    .notif-card {
        border: 1.5px solid #dee2e6; border-radius: 14px;
        padding: 22px 26px; background: #ffffff;
        box-shadow: 0 3px 12px rgba(0,0,0,0.08);
    }
    .suppress-card {
        border: 2px solid #f8d7da; border-radius: 14px;
        padding: 22px 26px; background: #fff5f5;
    }
    .rec-card {
        border: 1px solid #dee2e6; border-radius: 10px;
        padding: 14px 18px; background: #f8f9fa; margin: 6px 0;
    }
    .tag { display: inline-block; padding: 3px 12px; border-radius: 20px;
           font-size: 11px; font-weight: 700; margin-right: 6px; letter-spacing: 0.4px; }
    .tag-in_app   { background: #cfe2ff; color: #084298; }
    .tag-whatsapp { background: #d1e7dd; color: #0f5132; }
    .tag-email    { background: #fff3cd; color: #664d03; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        '<div style="font-size:52px;font-weight:900;color:#7dd3fc;margin-bottom:2px;letter-spacing:-1px;">Oculi</div>'
        '<div style="font-size:12px;color:#666;margin-bottom:20px;">Agentic Cross-Sell Engine</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<span style="font-size:13px;font-weight:700;color:#ccc;">Demo Scenarios</span>', unsafe_allow_html=True)
    st.caption("Select a customer and simulate an incoming session event.")
    st.markdown("<br>", unsafe_allow_html=True)

    p = st.session_state["pipeline"]

    for scenario in SCENARIOS:
        cid = scenario["customer_id"]
        tier_icon = _TIER_ICON.get(scenario["lifecycle"], "⚪")
        route_color, route_bg = _ROUTE_COLORS.get(scenario["route_tag"], ("#555", "#eee"))
        is_overridden = cid in st.session_state.get("customer_overrides", {}) or \
                        cid in st.session_state.get("activity_overrides", {})
        override_badge = (
            ' <span style="font-size:10px;background:#fff3cd;color:#664d03;'
            'padding:1px 7px;border-radius:10px;font-weight:700;">EDITED</span>'
            if is_overridden else ""
        )
        display_name = st.session_state.get("customer_overrides", {}).get(cid, {}).get(
            "name", scenario["customer_name"]
        )

        with st.container(border=True):
            st.markdown(
                f'<div class="user-card-name">{tier_icon} {display_name}{override_badge}</div>'
                f'<div class="user-card-scenario" style="color:{route_color};">{scenario["scenario_label"]}</div>'
                f'<div class="user-card-desc">{scenario["scenario_desc"]}</div>'
                f'<span class="route-badge" style="color:{route_color};background:{route_bg};">'
                f'{scenario["route_tag"]}</span>',
                unsafe_allow_html=True,
            )
            btn_col, edit_col = st.columns([3, 2])
            with btn_col:
                simulate_clicked = st.button(
                    "⚡ Simulate Event",
                    key=f"btn_{cid}",
                    disabled=p["running"],
                    use_container_width=True,
                )
            with edit_col:
                edit_clicked = st.button(
                    "✏️ Edit Data",
                    key=f"edit_{cid}",
                    disabled=p["running"],
                    use_container_width=True,
                )

            if edit_clicked:
                _edit_customer_modal(cid, scenario["customer_name"])

            if simulate_clicked:
                # Merge disk data with any in-memory overrides before starting
                with open(BASE_DIR / "data" / "customers.json") as f:
                    all_customers = json.load(f)
                with open(BASE_DIR / "data" / "customer_activity.json") as f:
                    all_activities = json.load(f)
                cust_ovr = st.session_state.get("customer_overrides", {})
                act_ovr = st.session_state.get("activity_overrides", {})
                merged_customers = [cust_ovr.get(c["customer_id"], c) for c in all_customers]
                merged_activities = [act_ovr.get(a["customer_id"], a) for a in all_activities]
                set_overrides(merged_customers, merged_activities)

                fresh = _fresh_pipeline_state()
                fresh["running"] = True
                fresh["selected_scenario"] = cid
                st.session_state["pipeline"] = fresh
                thread = threading.Thread(
                    target=_run_pipeline,
                    args=(scenario["path"], fresh),
                    daemon=True,
                )
                thread.start()
                st.rerun()

# ─── Main area ────────────────────────────────────────────────────────────────

st.markdown(
    '<h2 style="margin-bottom:4px;">Cross-Sell Pipeline</h2>'
    '<p style="color:#888;font-size:13px;margin-top:0;">Oculi · Real-time recommendations powered by CrewAI + GPT-4o</p>',
    unsafe_allow_html=True,
)

p = st.session_state["pipeline"]
statuses = p["step_statuses"]

st.divider()

left_col, right_col = st.columns([1, 1], gap="large")

# ─── Customer Context ─────────────────────────────────────────────────────────

with left_col:
    st.subheader("Customer Context")
    event = p["event_output"]

    if event:
        customers_path = BASE_DIR / "data" / "customers.json"
        with open(customers_path) as f:
            all_customers = json.load(f)
        cid_active = event["customer_id"]
        customer = st.session_state.get("customer_overrides", {}).get(cid_active) or \
                   next((c for c in all_customers if c["customer_id"] == cid_active), {})

        tier = customer.get("lifecycle_stage", "")
        tier_icon = _TIER_ICON.get(tier, "⚪")
        tier_label = tier.capitalize()
        channel_label = customer.get("preferred_channel", "—").replace("_", " ").title()
        aov = customer.get("aov_inr", 0)

        # ── Header: avatar + name ──────────────────────────────────────────
        initials = "".join(w[0] for w in customer.get("name", "?").split()[:2]).upper()
        st.markdown(
            f'<div class="ctx-card">'
            f'  <div class="ctx-header">'
            f'    <div class="ctx-avatar">{initials}</div>'
            f'    <div>'
            f'      <div class="ctx-name">{customer.get("name", event["customer_id"])}</div>'
            f'      <div class="ctx-tier">{tier_icon} {tier_label} customer &nbsp;·&nbsp; {channel_label} preferred</div>'
            f'    </div>'
            f'  </div>'
            # Stats row
            f'  <div class="ctx-stats">'
            f'    <div class="ctx-stat">'
            f'      <div class="ctx-stat-label">Lifecycle</div>'
            f'      <div class="ctx-stat-value">{tier_icon} {tier_label}</div>'
            f'    </div>'
            f'    <div class="ctx-stat">'
            f'      <div class="ctx-stat-label">Avg Order Value</div>'
            f'      <div class="ctx-stat-value">₹{aov:,}</div>'
            f'    </div>'
            f'    <div class="ctx-stat">'
            f'      <div class="ctx-stat-label">Channel</div>'
            f'      <div class="ctx-stat-value">{channel_label}</div>'
            f'    </div>'
            f'    <div class="ctx-stat">'
            f'      <div class="ctx-stat-label">WhatsApp</div>'
            f'      <div class="ctx-stat-value">{"✅" if customer.get("opted_in_whatsapp") else "❌"}</div>'
            f'    </div>'
            f'  </div>',
            unsafe_allow_html=True,
        )

        # ── Session event box ──────────────────────────────────────────────
        orch = p.get("orchestration_output") or {}
        strength = orch.get("signal_strength")
        depth = event["session_depth"]
        depth_class = {"HIGH": "depth-high", "MEDIUM": "depth-med", "LOW": "depth-low"}.get(strength, "depth-med")
        depth_label = f"{strength}" if strength else str(depth)

        search_html = (
            f'<span class="ctx-search-pill">"{event["search_query"]}"</span>'
            if event.get("search_query")
            else '<span style="color:#aaa;font-size:12px;">—</span>'
        )

        st.markdown(
            f'  <div class="ctx-section-title">Session Event</div>'
            f'  <div class="ctx-event-box">'
            f'    <div class="ctx-event-row">'
            f'      <span class="ctx-event-label">Event type</span>'
            f'      <span class="ctx-event-code">{event["event_type"]}</span>'
            f'    </div>'
            f'    <div class="ctx-event-row">'
            f'      <span class="ctx-event-label">Product</span>'
            f'      <span class="ctx-event-val">{event["product_name"]}</span>'
            f'    </div>'
            f'    <div class="ctx-event-row">'
            f'      <span class="ctx-event-label">Search query</span>'
            f'      {search_html}'
            f'    </div>'
            f'    <div class="ctx-event-row">'
            f'      <span class="ctx-event-label">Session depth</span>'
            f'      <span class="ctx-depth-badge {depth_class}">{depth} pages · {depth_label}</span>'
            f'    </div>'
            f'  </div>',
            unsafe_allow_html=True,
        )

        # ── Cart contents ──────────────────────────────────────────────────
        cart = event.get("cart_contents", [])
        st.markdown('<div class="ctx-section-title">Cart Contents</div>', unsafe_allow_html=True)
        if cart:
            cart_html = "".join(
                f'<div class="cart-item">'
                f'  <span class="cart-item-name">🛒 {item["name"]}</span>'
                f'  <span class="cart-item-price">₹{item["price"]:,}</span>'
                f'</div>'
                for item in cart
            )
            st.markdown(cart_html, unsafe_allow_html=True)
        else:
            st.markdown('<div class="cart-empty">Cart is empty</div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)  # close ctx-card

    else:
        st.markdown(
            '<div style="color:#aaa;font-size:14px;padding:32px 0;text-align:center;">'
            '⬅️ Select a customer from the sidebar to begin.'
            '</div>',
            unsafe_allow_html=True,
        )

# ─── Agent Pipeline ───────────────────────────────────────────────────────────

with right_col:
    st.subheader("Agent Pipeline")

    orch_output = p["orchestration_output"]
    intent_output = p["intent_output"]
    rec_output = p["recommender_output"]
    out_output = p["outreach_output"]
    fb_output = p["feedback_output"]

    summaries = {
        "event": (f"Signal: {event['event_type']} captured" if event else None),
        "orchestration": (
            f"Route: {orch_output['decision']} — {orch_output['reason']}" if orch_output else None
        ),
        "intent": (
            f"Goal: {intent_output.get('inferred_goal', '—')} · confidence {intent_output.get('confidence', '—')}"
            if isinstance(intent_output, dict) and "inferred_goal" in intent_output
            else ("Skipped — cached intent used" if statuses["intent"] == "suppressed" else None)
        ),
        "recommender": (
            f"{len(rec_output.get('recommendations', []))} product(s) recommended" if rec_output else None
        ),
        "outreach": (
            f"Channel: {out_output.get('channel', '—')} · \"{out_output.get('message_header', '—')}\""
            if out_output else None
        ),
        "feedback": (
            f"Outcome: {fb_output.get('simulated_outcome', '—')} — {fb_output.get('note', '')}"
            if fb_output else None
        ),
    }

    st.markdown(_build_pipeline_html(statuses, summaries), unsafe_allow_html=True)

st.divider()

# ─── Final Output ─────────────────────────────────────────────────────────────

st.subheader("Final Output")

pipeline_decision = p["pipeline_decision"]
outreach = p["outreach_output"]
orch_out = p["orchestration_output"]

if pipeline_decision == "SUPPRESS" and orch_out:
    st.markdown(
        f'<div class="suppress-card">'
        f'<div style="font-size:18px;font-weight:700;color:#842029;margin-bottom:8px;">🚫 Pipeline Suppressed</div>'
        f'<div style="font-size:14px;color:#555;">{orch_out["reason"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

elif outreach:
    channel = outreach.get("channel", "in_app")
    secondary = outreach.get("secondary_recommendation")
    secondary_html = ""
    if secondary:
        secondary_html = (
            f'<div style="border-top:1px solid #eee;padding-top:10px;margin-top:8px;font-size:13px;color:#666;">'
            f'Also: {secondary.get("message", "")} — <strong>{secondary.get("name", "")}</strong></div>'
        )
    incentive_html = (
        '<span style="font-size:12px;color:#198754;font-weight:600;margin-left:4px;">🏷️ Bundle offer</span>'
        if outreach.get("incentive_applied") else ""
    )
    st.markdown(
        f'<div class="notif-card">'
        f'<div style="margin-bottom:12px;">'
        f'<span class="tag tag-{channel}">{channel.replace("_"," ").upper()}</span>{incentive_html}'
        f'</div>'
        f'<div style="font-size:19px;font-weight:700;color:#1a1a2e;">{outreach.get("message_header","")}</div>'
        f'<div style="font-size:14px;color:#444;line-height:1.6;margin:10px 0 14px;">{outreach.get("message_body","")}</div>'
        f'{secondary_html}'
        f'<div style="margin-top:16px;">'
        f'<button style="background:#0d6efd;color:white;border:none;border-radius:8px;'
        f'padding:9px 22px;font-size:14px;font-weight:600;cursor:pointer;">'
        f'{outreach.get("cta","Add to Cart")}</button>'
        f'</div>'
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
                    f'<div style="font-weight:700;font-size:15px;color:#1a1a2e;">{rec.get("name","")}</div>'
                    f'<div style="color:#198754;font-weight:700;font-size:14px;margin-top:2px;">₹{rec.get("price",0):,}</div>'
                    f'<div style="font-size:12px;color:#666;margin-top:4px;">Attach rate: <strong>{int(rec.get("attach_rate",0)*100)}%</strong></div>'
                    f'<div style="font-size:12px;color:#555;margin-top:6px;line-height:1.4;">{rec.get("recommendation_reason","")}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
else:
    if not p["running"] and pipeline_decision is None:
        st.info("⬅️ Select a customer from the sidebar and click **Simulate Event** to run the pipeline.")
    elif p["running"]:
        st.info("⏳ Pipeline running — agents are reasoning…")

# ─── Agent Reasoning Logs ─────────────────────────────────────────────────────

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

# ─── Error display ────────────────────────────────────────────────────────────

if p.get("error"):
    st.error(f"Pipeline error: {p['error']}")

# ─── Auto-refresh while running ───────────────────────────────────────────────

if p["running"]:
    time.sleep(1)
    st.rerun()
