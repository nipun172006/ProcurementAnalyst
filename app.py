from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.action_store import ALLOWED_ACTIONS, record_handoff
from src.solution import handle_request

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = "gemini-3.5-flash-lite"
load_dotenv(ROOT / ".env", override=True)
REQUESTS = json.loads((ROOT / "data" / "requests.json").read_text(encoding="utf-8"))
BY_ID = {request["request_id"]: request for request in REQUESTS}


def money(value: object) -> str:
    return "Unknown" if value is None else f"${float(value):,.0f}"


def safe(value: object) -> str:
    return escape(str(value if value not in (None, "") else "Unknown"))


def metric_card(label: str, value: object, detail: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{safe(label)}</div>
            <div class="metric-value">{safe(value)}</div>
            <div class="metric-detail">{safe(detail)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def control_card(title: str, items: list[str], empty_text: str, tone: str) -> None:
    values = items or [empty_text]
    empty_class = " is-empty" if not items else ""
    pills = "".join(
        f'<span class="control-pill {tone}{empty_class}">{safe(item).replace("_", " ")}</span>'
        for item in values
    )
    st.markdown(
        f'<div class="control-card"><div class="control-title">{safe(title)}</div>'
        f'<div class="pill-list">{pills}</div></div>',
        unsafe_allow_html=True,
    )


st.set_page_config(
    page_title="Procurement Copilot",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --pc-bg: #08090a;
        --pc-panel: #0f1012;
        --pc-panel-2: #121316;
        --pc-panel-hover: #16171b;
        --pc-border: #24262b;
        --pc-border-strong: #343740;
        --pc-text: #f4f4f5;
        --pc-muted: #8b8f98;
        --pc-dim: #666a73;
        --pc-violet: #8b7cf6;
        --pc-violet-soft: rgba(139, 124, 246, .12);
        --pc-green: #56c890;
        --pc-amber: #e7b65c;
        --pc-red: #eb6f7a;
        --pc-glass: rgba(17, 18, 23, .54);
        --pc-glass-strong: rgba(20, 21, 27, .72);
        --pc-glass-border: rgba(255, 255, 255, .095);
        --pc-glass-highlight: rgba(255, 255, 255, .055);
    }

    html, body, [class*="css"] {
        font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .stApp {
        color: var(--pc-text);
        background:
            radial-gradient(circle at 68% -12%, rgba(128, 105, 255, .20), transparent 31rem),
            radial-gradient(circle at 10% 82%, rgba(62, 103, 165, .10), transparent 34rem),
            linear-gradient(155deg, #0a0b0f 0%, #08090c 54%, #090a0e 100%);
        background-attachment: fixed;
    }

    header[data-testid="stHeader"] {
        height: 0 !important; min-height: 0 !important; background: transparent !important;
        border: 0 !important; box-shadow: none !important; pointer-events: none;
    }

    #MainMenu, footer {visibility: hidden;}
    [data-testid="stDecoration"] {display: none;}
    [data-testid="stAppDeployButton"], [data-testid="stMainMenu"] {display: none !important;}
    [data-testid="stToolbar"] {
        display: flex !important; height: 0 !important; min-height: 0 !important;
        background: transparent !important; pointer-events: none;
    }
    [data-testid="stExpandSidebarButton"] {
        display: flex !important; position: fixed !important; top: 16px !important; left: 16px !important;
        width: 36px !important; height: 36px !important; padding: 0 !important; border-radius: 10px !important;
        color: rgba(244,244,245,.85) !important; background: rgba(20,21,27,.72) !important;
        border: 1px solid rgba(255,255,255,.12) !important; box-shadow: 0 12px 34px rgba(0,0,0,.34), inset 0 1px rgba(255,255,255,.06) !important;
        backdrop-filter: blur(18px) saturate(145%); -webkit-backdrop-filter: blur(18px) saturate(145%);
        pointer-events: auto !important; z-index: 1000001 !important;
    }
    [data-testid="stExpandSidebarButton"]:hover {background: rgba(32,33,42,.84) !important; border-color: rgba(255,255,255,.19) !important;}
    [data-testid="stSidebarCollapseButton"] {
        visibility: visible !important; opacity: 1 !important;
    }
    [data-testid="stSidebarCollapseButton"] button {
        width: 34px !important; height: 34px !important; border-radius: 9px !important;
        background: rgba(255,255,255,.045) !important; border: 1px solid rgba(255,255,255,.08) !important;
    }
    .block-container {padding: 1.15rem 2.2rem 4rem; max-width: 1320px;}

    section[data-testid="stSidebar"] {
        width: 302px !important;
        overflow: hidden !important;
        background: rgba(10, 11, 15, .72);
        border-right: 1px solid var(--pc-glass-border);
        box-shadow: 16px 0 54px rgba(0,0,0,.18);
        backdrop-filter: blur(26px) saturate(135%); -webkit-backdrop-filter: blur(26px) saturate(135%);
    }
    section[data-testid="stSidebar"] > div {width: 302px !important;}
    section[data-testid="stSidebar"] .block-container {padding: 1.35rem 1.05rem 2rem;}

    .brand-lockup {display: flex; align-items: center; gap: .72rem; margin: .15rem 0 1.65rem;}
    .brand-mark {
        width: 28px; height: 28px; border-radius: 8px; display: grid; place-items: center;
        background: linear-gradient(145deg, rgba(255,255,255,.98), rgba(210,208,225,.82)); color: #0b0c0e;
        font-size: .78rem; font-weight: 800; box-shadow: 0 8px 22px rgba(0,0,0,.22), inset 0 1px rgba(255,255,255,.75);
    }
    .brand-name {font-size: .91rem; font-weight: 650; letter-spacing: -.015em; color: var(--pc-text);}
    .brand-workspace {font-size: .66rem; color: var(--pc-muted); margin-top: .04rem;}

    .sidebar-label, .eyebrow {
        color: var(--pc-dim); font-size: .66rem; font-weight: 700; letter-spacing: .105em;
        text-transform: uppercase;
    }
    .sidebar-label {margin: .9rem 0 .45rem;}

    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
        color: #b9bbc1 !important; font-size: .75rem !important;
    }

    div[data-baseweb="select"] > div,
    div[data-baseweb="base-input"],
    textarea {
        background: rgba(255,255,255,.035) !important;
        border-color: var(--pc-glass-border) !important;
        color: var(--pc-text) !important;
        border-radius: 7px !important;
        min-height: 2.5rem;
    }
    div[data-baseweb="select"] > div:hover,
    div[data-baseweb="base-input"]:hover,
    textarea:hover {border-color: var(--pc-border-strong) !important;}

    .stSelectbox .react-aria-ComboBox [role="group"] {
        overflow: hidden; background: rgba(255,255,255,.045) !important; border: 1px solid var(--pc-glass-border) !important;
        border-radius: 8px !important; box-shadow: inset 0 1px rgba(255,255,255,.025), 0 8px 22px rgba(0,0,0,.10) !important;
        backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    }
    .stSelectbox .react-aria-ComboBox input {
        color: #e7e7e9 !important; background: transparent !important; border: 0 !important;
        -webkit-text-fill-color: #e7e7e9 !important;
    }
    .stSelectbox .react-aria-ComboBox button {color: var(--pc-muted) !important; background: transparent !important;}
    .stSelectbox .react-aria-ComboBox [role="group"]:focus-within {border-color: #555861 !important;}

    div[role="radiogroup"] {gap: .32rem;}
    div[role="radiogroup"] label {
        background: rgba(255,255,255,.025); border: 1px solid rgba(255,255,255,.075); border-radius: 8px;
        padding: .44rem .58rem; transition: border-color .15s, background .15s;
    }
    div[role="radiogroup"] label:hover {background: rgba(255,255,255,.055); border-color: rgba(255,255,255,.14);}

    .model-status {
        display: flex; gap: .55rem; align-items: center; padding: .7rem .72rem; margin: .9rem 0 .72rem;
        border: 1px solid var(--pc-glass-border); background: rgba(255,255,255,.035); border-radius: 9px;
        color: #b6b8bf; font-size: .7rem; line-height: 1.35;
        box-shadow: inset 0 1px rgba(255,255,255,.03); backdrop-filter: blur(14px);
    }
    .status-dot {width: 7px; height: 7px; border-radius: 50%; flex: 0 0 7px;}
    .status-dot.live {background: var(--pc-green); box-shadow: 0 0 12px rgba(86,200,144,.7);}
    .status-dot.fallback {background: var(--pc-amber); box-shadow: 0 0 12px rgba(231,182,92,.55);}

    .stButton > button, .stFormSubmitButton > button {
        min-height: 2.55rem; border-radius: 7px; border: 1px solid #e7e7e9 !important;
        background: #f5f5f6 !important; color: #111216 !important; font-weight: 650;
        box-shadow: 0 1px 0 rgba(255,255,255,.25) inset, 0 6px 18px rgba(0,0,0,.22);
        transition: transform .15s ease, background .15s ease;
    }
    .stButton > button:hover, .stFormSubmitButton > button:hover {
        background: #ffffff !important; transform: translateY(-1px); border-color: #ffffff !important;
    }

    .sidebar-note {
        color: var(--pc-dim); font-size: .68rem; line-height: 1.48; padding-top: .85rem;
        border-top: 1px solid var(--pc-border);
    }

    .topbar {
        display: flex; align-items: center; justify-content: space-between; gap: 1rem;
        min-height: 42px; padding: .15rem .15rem .9rem; border-bottom: 1px solid rgba(255,255,255,.075); margin-bottom: 2.15rem;
    }
    .stApp:has([data-testid="stExpandSidebarButton"]) .topbar {padding-left: 3.2rem;}
    .breadcrumb {display: flex; align-items: center; gap: .48rem; color: var(--pc-muted); font-size: .76rem;}
    .breadcrumb strong {color: #d8d9dc; font-weight: 560;}
    .slash {color: #3e4148;}
    .advisory-badge {
        display: inline-flex; align-items: center; gap: .42rem; padding: .3rem .56rem;
        border: 1px solid var(--pc-glass-border); border-radius: 999px; color: #b5b7bf; font-size: .66rem;
        background: rgba(255,255,255,.035); box-shadow: inset 0 1px rgba(255,255,255,.035);
        backdrop-filter: blur(14px);
    }
    .advisory-badge::before {content: ""; width: 5px; height: 5px; border-radius: 50%; background: var(--pc-violet);}

    .hero {margin: 0 0 1.65rem; max-width: 850px;}
    .hero h1 {
        color: #f6f6f7; margin: .55rem 0 .55rem; font-size: clamp(2rem, 4vw, 3.3rem);
        line-height: 1.04; letter-spacing: -.052em; font-weight: 590;
    }
    .hero p {color: var(--pc-muted); max-width: 660px; font-size: .94rem; line-height: 1.55; margin: 0;}
    .hero .accent {color: #b8aefc;}

    .section-kicker {margin: 1.45rem 0 .68rem; color: #b8bac0; font-size: .76rem; font-weight: 600;}
    .section-kicker span {color: var(--pc-dim); font-weight: 450; margin-left: .38rem;}

    .metric-card {
        min-height: 105px; padding: .9rem 1rem; border: 1px solid var(--pc-glass-border);
        border-radius: 11px; background: linear-gradient(145deg, rgba(255,255,255,.055), rgba(255,255,255,.022));
        box-shadow: inset 0 1px rgba(255,255,255,.045), 0 18px 48px rgba(0,0,0,.14);
        backdrop-filter: blur(18px) saturate(125%); -webkit-backdrop-filter: blur(18px) saturate(125%);
        transition: transform .18s ease, border-color .18s ease, background .18s ease;
    }
    .metric-card:hover {transform: translateY(-1px); border-color: rgba(255,255,255,.15); background: linear-gradient(145deg, rgba(255,255,255,.07), rgba(255,255,255,.026));}
    .metric-label {font-size: .67rem; color: var(--pc-muted); margin-bottom: .62rem;}
    .metric-value {font-size: 1.35rem; letter-spacing: -.035em; font-weight: 590; color: var(--pc-text);}
    .metric-detail {font-size: .64rem; color: var(--pc-dim); margin-top: .22rem;}

    [data-testid="stExpander"] {
        background: rgba(255,255,255,.026); border: 1px solid var(--pc-glass-border) !important;
        border-radius: 10px !important; overflow: hidden; box-shadow: inset 0 1px rgba(255,255,255,.025);
        backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
    }
    [data-testid="stExpander"] summary {color: #c8c9ce; font-size: .78rem;}

    .detail-grid {display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 2rem;}
    .detail-row {display: flex; justify-content: space-between; gap: 1rem; padding: .56rem 0; border-bottom: 1px solid #1e2025;}
    .detail-key {color: var(--pc-muted); font-size: .71rem;}
    .detail-value {color: #d8d9dd; font-size: .72rem; text-align: right; max-width: 65%;}

    .empty-state {
        text-align: center; padding: 4.3rem 1.5rem; margin-top: 1.35rem;
        border: 1px solid var(--pc-glass-border); border-radius: 13px;
        background: radial-gradient(circle at 50% -5%, rgba(139,124,246,.13), transparent 48%), rgba(255,255,255,.018);
        box-shadow: inset 0 1px rgba(255,255,255,.035), 0 22px 55px rgba(0,0,0,.12);
        backdrop-filter: blur(20px) saturate(120%); -webkit-backdrop-filter: blur(20px) saturate(120%);
    }
    .empty-icon {
        width: 42px; height: 42px; margin: 0 auto .9rem; display: grid; place-items: center;
        border: 1px solid rgba(174,162,255,.22); border-radius: 11px; color: #b7adff; background: rgba(139,124,246,.08);
        box-shadow: inset 0 1px rgba(255,255,255,.05), 0 12px 28px rgba(0,0,0,.18);
    }
    .empty-title {font-size: .9rem; font-weight: 600; color: #dedfe2; margin-bottom: .28rem;}
    .empty-copy {font-size: .74rem; color: var(--pc-muted);}

    .decision-hero {
        position: relative; overflow: hidden; padding: 1.1rem 1.2rem; margin: 1rem 0 1.1rem;
        border: 1px solid var(--pc-glass-border); border-radius: 12px;
        background: linear-gradient(135deg, rgba(255,255,255,.055), rgba(255,255,255,.018));
        box-shadow: inset 0 1px rgba(255,255,255,.045), 0 22px 56px rgba(0,0,0,.15);
        backdrop-filter: blur(22px) saturate(130%); -webkit-backdrop-filter: blur(22px) saturate(130%);
    }
    .decision-hero::before {
        content: ""; position: absolute; inset: -80px auto auto 35%; width: 260px; height: 160px;
        background: rgba(139,124,246,.09); filter: blur(55px); border-radius: 50%; pointer-events: none;
    }
    .decision-top {display: flex; justify-content: space-between; gap: 1rem; align-items: center; position: relative;}
    .decision-label {color: var(--pc-dim); font-size: .64rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase;}
    .decision-status {padding: .27rem .52rem; border: 1px solid var(--pc-border); border-radius: 999px; font-size: .63rem;}
    .decision-status.normal {color: var(--pc-green); background: rgba(86,200,144,.065);}
    .decision-status.warning {color: var(--pc-amber); background: rgba(231,182,92,.065);}
    .decision-status.critical {color: var(--pc-red); background: rgba(235,111,122,.065);}
    .decision-copy {position: relative; margin: .76rem 0 .72rem; color: #e4e4e7; font-size: .94rem; line-height: 1.55; max-width: 920px;}
    .next-step {position: relative; color: #9fa2aa; font-size: .72rem;}
    .next-step strong {color: #c8c9ce;}

    [data-testid="stTabs"] [data-baseweb="tab-list"] {gap: .15rem; border-bottom: 1px solid var(--pc-border);}
    [data-testid="stTabs"] [data-baseweb="tab"] {
        height: 2.6rem; padding: 0 .8rem; color: var(--pc-muted); font-size: .73rem;
    }
    [data-testid="stTabs"] [aria-selected="true"] {color: #f1f1f2 !important;}
    [data-testid="stTabs"] [data-baseweb="tab-highlight"] {background: var(--pc-violet); height: 1px;}
    [data-testid="stTabs"] [data-baseweb="tab-panel"] {padding-top: 1.1rem;}

    .control-card {
        min-height: 150px; padding: .9rem; border: 1px solid var(--pc-glass-border);
        border-radius: 11px; background: rgba(255,255,255,.025);
        box-shadow: inset 0 1px rgba(255,255,255,.035), 0 16px 40px rgba(0,0,0,.10);
        backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
    }
    .control-title {font-size: .7rem; font-weight: 650; color: #cbccd0; margin-bottom: .72rem;}
    .pill-list {display: flex; flex-wrap: wrap; gap: .38rem;}
    .control-pill {
        display: inline-flex; padding: .3rem .48rem; border-radius: 5px; border: 1px solid var(--pc-border);
        background: #121317; color: #b5b7bd; font-size: .65rem; text-transform: capitalize;
    }
    .control-pill.approval {border-color: rgba(139,124,246,.3); color: #bcb4fb; background: rgba(139,124,246,.07);}
    .control-pill.risk {border-color: rgba(235,111,122,.25); color: #ed969e; background: rgba(235,111,122,.055);}
    .control-pill.unknown {border-color: rgba(231,182,92,.25); color: #e9c77f; background: rgba(231,182,92,.055);}
    .control-pill.is-empty {border-color: rgba(86,200,144,.22); color: #87d5aa; background: rgba(86,200,144,.05);}

    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        border-color: var(--pc-glass-border) !important; border-radius: 11px !important;
        background: rgba(255,255,255,.025); box-shadow: inset 0 1px rgba(255,255,255,.03), 0 14px 36px rgba(0,0,0,.09);
        backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
    }
    .evidence-source {display: flex; align-items: center; gap: .5rem; margin-bottom: .38rem;}
    .source-index {
        display: grid; place-items: center; width: 21px; height: 21px; border-radius: 6px;
        background: var(--pc-violet-soft); color: #b9b0fb; font-size: .61rem; font-weight: 700;
    }
    .source-name {color: #d8d9dc; font-size: .72rem; font-weight: 600;}
    .evidence-finding {color: #d8d9dd; font-size: .78rem; line-height: 1.52;}
    .evidence-reference {color: var(--pc-dim); font-size: .63rem; margin-top: .42rem;}

    div[data-testid="stForm"] {
        border: 1px solid var(--pc-glass-border); border-radius: 11px; background: rgba(255,255,255,.025);
        box-shadow: inset 0 1px rgba(255,255,255,.03); backdrop-filter: blur(18px);
    }
    div[data-testid="stCode"] {border: 1px solid var(--pc-border); border-radius: 8px;}

    div[data-testid="stAlert"] {
        border-radius: 10px; border-color: var(--pc-glass-border); background: rgba(255,255,255,.035);
        color: #c9cace;
        backdrop-filter: blur(16px);
    }
    hr {border-color: var(--pc-border) !important;}
    .assumption-note, .page-footer {color: var(--pc-dim); font-size: .66rem; line-height: 1.45;}
    .page-footer {margin-top: 2.6rem; padding-top: 1rem; border-top: 1px solid var(--pc-border); display: flex; justify-content: space-between;}

    @media (max-width: 900px) {
        .block-container {padding: 1rem 1rem 3rem;}
        [data-testid="stExpandSidebarButton"] {top: 12px !important; left: 12px !important;}
        .detail-grid {grid-template-columns: 1fr;}
        .hero h1 {font-size: 2.2rem;}
        .page-footer {flex-direction: column; gap: .35rem;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        """
        <div class="brand-lockup">
            <div class="brand-mark">P</div>
            <div><div class="brand-name">Procurement Copilot</div><div class="brand-workspace">Nipun's FDE workspace</div></div>
        </div>
        <div class="sidebar-label">Request queue</div>
        """,
        unsafe_allow_html=True,
    )
    request_id = st.selectbox(
        "Purchase request",
        list(BY_ID),
        format_func=lambda rid: f"{rid} · {BY_ID[rid]['product_name']}",
        label_visibility="collapsed",
    )
    st.markdown('<div class="sidebar-label">Architecture</div>', unsafe_allow_html=True)
    architecture = st.radio(
        "Reasoning architecture",
        ["single", "staged"],
        format_func=lambda value: "A · Single agent" if value == "single" else "B · Analyst + reviewer",
        label_visibility="collapsed",
    )
    st.caption("Use the staged flow for comparison; the single-agent path is the recommended MVP.")

    model_enabled = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    status_class = "live" if model_enabled else "fallback"
    status_title = "AI reasoning online" if model_enabled else "Deterministic fallback"
    status_detail = os.getenv("MODEL_NAME", DEFAULT_MODEL) if model_enabled else "No model key configured"
    st.markdown(
        f"""
        <div class="model-status">
            <span class="status-dot {status_class}"></span>
            <span><strong>{safe(status_title)}</strong><br>{safe(status_detail)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    run_clicked = st.button("Analyse request", type="primary", use_container_width=True)
    st.markdown(
        '<div class="sidebar-note">Advisory system only.<br>Final authority always stays with people.</div>',
        unsafe_allow_html=True,
    )

request = BY_ID[request_id]
if st.session_state.get("selected_request") != request_id:
    st.session_state.pop("decision", None)
    st.session_state.pop("decision_architecture", None)
    st.session_state["selected_request"] = request_id

st.markdown(
    f"""
    <div class="topbar">
        <div class="breadcrumb"><span>Procurement</span><span class="slash">/</span><strong>{safe(request_id)}</strong></div>
        <div class="advisory-badge">Human-controlled decision</div>
    </div>
    <div class="hero">
        <div class="eyebrow">Evidence-led procurement intelligence</div>
        <h1>Make the next <span class="accent">safe decision.</span></h1>
        <p>Bring request context, budget, existing tools, vendor risk and policy into one defensible human handoff.</p>
    </div>
    <div class="section-kicker">Request overview <span>{safe(request.get('product_name'))} · {safe(request.get('vendor_name'))}</span></div>
    """,
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card("Annual cost", money(request.get("annual_cost_usd")), "Requested recurring spend")
with c2:
    metric_card("Users", request.get("user_count") or "Unknown", "Expected licence count")
with c3:
    metric_card("Urgency", str(request.get("urgency", "Unknown")).title(), "Requester priority")
with c4:
    access = str(request.get("data_access_level", "Unknown")).replace("_", " ").title()
    metric_card("Data access", access, "Requested exposure level")

with st.expander("Request details", expanded=False):
    integrations = request.get("requested_integrations") or []
    st.markdown(
        f"""
        <div class="detail-grid">
            <div class="detail-row"><span class="detail-key">Product</span><span class="detail-value">{safe(request.get('product_name'))}</span></div>
            <div class="detail-row"><span class="detail-key">Vendor</span><span class="detail-value">{safe(request.get('vendor_name'))}</span></div>
            <div class="detail-row"><span class="detail-key">Category</span><span class="detail-value">{safe(request.get('category'))}</span></div>
            <div class="detail-row"><span class="detail-key">Requester</span><span class="detail-value">{safe(request.get('requester_id'))}</span></div>
            <div class="detail-row"><span class="detail-key">Integrations</span><span class="detail-value">{safe(', '.join(integrations) if integrations else 'None')}</span></div>
            <div class="detail-row"><span class="detail-key">Purpose</span><span class="detail-value">{safe(request.get('business_justification'))}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if run_clicked:
    with st.spinner("Gathering evidence · applying policy · drafting next action"):
        try:
            st.session_state["decision"] = handle_request(request_id, architecture=architecture)
            st.session_state["decision_architecture"] = architecture
        except Exception as exc:
            st.error(f"Analysis could not complete: {type(exc).__name__}: {exc}")

decision = st.session_state.get("decision")
if decision is None:
    st.markdown(
        """
        <div class="empty-state">
            <div class="empty-icon">◇</div>
            <div class="empty-title">Ready to build the evidence pack</div>
            <div class="empty-copy">Choose an architecture and analyse this request to reveal the grounded next action.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    if st.session_state.get("decision_architecture") != architecture:
        st.warning("This result used the previously selected architecture. Analyse again to compare the new selection.")

    critical_flags = {"budget_insufficient", "vendor_risk_unavailable", "conflicting_vendor_evidence"}
    if decision.missing_information:
        decision_tone, decision_status = "warning", "Clarification required"
    elif critical_flags.intersection(decision.risk_flags):
        decision_tone, decision_status = "critical", "Specialist review required"
    else:
        decision_tone, decision_status = "normal", "Ready for human review"

    st.markdown(
        f"""
        <div class="section-kicker">Decision <span>{safe(st.session_state.get('decision_architecture', architecture).title())} architecture</span></div>
        <div class="decision-hero">
            <div class="decision-top">
                <div class="decision-label">Recommended next action</div>
                <div class="decision-status {decision_tone}">{safe(decision_status)}</div>
            </div>
            <div class="decision-copy">{safe(decision.recommendation)}</div>
            <div class="next-step"><strong>Next human step</strong> · {safe(decision.next_step)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    decision_tab, evidence_tab, handoff_tab, trace_tab = st.tabs(
        ["Decision controls", "Evidence", "Human handoff", "Run trace"]
    )

    with decision_tab:
        approvals_col, risks_col, unknowns_col = st.columns(3)
        with approvals_col:
            control_card("Required approvals", decision.required_approvals, "No approval band calculated", "approval")
        with risks_col:
            control_card("Risk flags", decision.risk_flags, "No material risk flags", "risk")
        with unknowns_col:
            control_card("Unknowns", decision.missing_information, "No material fields missing", "unknown")
        st.markdown(
            '<div class="assumption-note">Assumption · the supplied data snapshot and policy version are the authoritative classroom sources.</div>',
            unsafe_allow_html=True,
        )

    with evidence_tab:
        st.caption("Every material finding below comes from a named tool or deterministic policy section.")
        for index, item in enumerate(decision.evidence, start=1):
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div class="evidence-source">
                        <span class="source-index">{index:02}</span>
                        <span class="source-name">{safe(item.source.replace('_', ' ').title())}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="evidence-finding">{safe(item.finding)}</div>',
                    unsafe_allow_html=True,
                )
                if item.reference:
                    st.markdown(
                        f'<div class="evidence-reference">Reference · {safe(item.reference)}</div>',
                        unsafe_allow_html=True,
                    )

    with handoff_tab:
        st.markdown("Record the next human-owned action. Approval and purchasing are intentionally unavailable.")
        default_action = "Request clarification" if decision.missing_information else "Send for specialist review"
        choices = sorted(ALLOWED_ACTIONS)
        with st.form("handoff_form", clear_on_submit=True):
            action = st.selectbox("Action", choices, index=choices.index(default_action))
            note = st.text_area(
                "Handoff note",
                placeholder="Example: Security to verify the expired external assessment before Procurement continues.",
                max_chars=500,
            )
            submitted = st.form_submit_button("Record handoff", type="primary")
        if submitted:
            try:
                record = record_handoff(request_id, architecture, action, note)
            except ValueError as exc:
                st.warning(str(exc))
            else:
                st.success(f"Recorded: {record['action']} · {record['timestamp_utc']}")

    with trace_tab:
        telemetry = decision.telemetry
        if telemetry:
            t1, t2, t3 = st.columns(3)
            with t1:
                metric_card("Tool calls", telemetry.tool_calls if telemetry.tool_calls is not None else "-", "Evidence retrieval")
            with t2:
                metric_card("LLM calls", telemetry.llm_calls if telemetry.llm_calls is not None else "-", "Bounded reasoning")
            with t3:
                metric_card("Architecture", st.session_state.get("decision_architecture", architecture).title(), "Current execution")
            st.markdown('<div class="section-kicker">Tools used</div>', unsafe_allow_html=True)
            st.code("  →  ".join(telemetry.tool_names), language=None)
        st.caption("No API keys, secrets or hidden model reasoning are stored in the trace.")

st.markdown(
    """
    <div class="page-footer">
        <span>Synthetic assessment data · Policy snapshot 30 Sep 2026</span>
        <span>Evidence first · Human authority preserved</span>
    </div>
    """,
    unsafe_allow_html=True,
)
