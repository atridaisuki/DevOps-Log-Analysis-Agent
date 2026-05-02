"""Streamlit UI for the DevOps Log Analysis Agent."""

import json
import os

import httpx
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="DevOps Log Agent", layout="wide")
st.title("DevOps Log Analysis Agent")

# ── sidebar: scenario + settings ─────────────────────────────────────
with st.sidebar:
    st.header("Settings")

    scenario = st.selectbox(
        "Scenario",
        [
            "scenario_01_db_pool",
            "scenario_02_oom",
            "scenario_03_config",
            "scenario_04_cascade",
            "scenario_05_disk",
        ],
    )
    max_iter = st.slider("Max iterations", 1, 20, 8)
    auto_approve = st.checkbox("Auto-approve (skip HITL)", value=True)

# ── main area ────────────────────────────────────────────────────────
goal = st.text_area(
    "Describe the incident",
    placeholder="例如：API 响应超时，用户投诉很多请求 5xx ...",
    height=80,
)

col1, col2 = st.columns([1, 5])
with col1:
    run_btn = st.button("Run Analysis", type="primary", disabled=not goal)

if run_btn and goal:
    payload = {
        "goal": goal,
        "scenario": scenario,
        "max_iterations": max_iter,
        "auto_approve": auto_approve,
    }

    with st.spinner("Agent is investigating ..."):
        try:
            resp = httpx.post(
                f"{API_BASE}/agent/analyze",
                json=payload,
                timeout=300.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            st.error(f"Request failed: {exc}")
            st.stop()

    # ── results ──────────────────────────────────────────────────────
    st.success(f"Done — status: {data['status']}, {data['iterations']} iterations")

    st.subheader("Root Cause Analysis")
    st.markdown(data["root_cause"])

    # tool trace
    st.subheader("Tool Trace")
    trace = data.get("tool_trace", [])
    if trace:
        for i, t in enumerate(trace, 1):
            icon = "✅" if t["success"] else "❌"
            with st.expander(f"{icon} {i}. {t['tool_name']} — {t['duration_ms']:.0f}ms"):
                st.json(t["tool_input"])
                st.text(json.dumps(t["tool_output"], indent=2, ensure_ascii=False)[:2000])
    else:
        st.info("No tool calls recorded.")

    # raw JSON
    with st.expander("Raw response JSON"):
        st.json(data)
