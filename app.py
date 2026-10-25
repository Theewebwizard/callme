"""
Streamlit application entry point for AI Receptionist Platform prototype dashboard.
"""

import streamlit as st

from ui.state import (
    init_session_state,
    get_all_businesses,
    get_active_business_id,
    set_active_business_id,
    get_active_business,
    is_backend_connected,
    get_api_status_badge,
)
from ui.pages.dashboard import render_dashboard_page
from ui.pages.business_setup import render_business_setup_page
from ui.pages.tool_library import render_tool_library_page
from ui.pages.agent_playground import render_agent_playground_page
from ui.pages.call_history import render_call_history_page

# Configure global page properties
st.set_page_config(
    page_title="AI Receptionist Platform",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize multi-tenant session state
init_session_state()

# Sidebar: Tenant Selection & Navigation
with st.sidebar:
    st.markdown("## 📞 AI Receptionist")
    st.caption("Multi-Tenant Voice Platform Prototype")
    st.divider()

    # 1. Multi-Tenant Business Selector
    st.subheader("🏢 Active Business")
    businesses = get_all_businesses()
    current_biz_id = get_active_business_id()
    biz_options = list(businesses.keys())

    if not biz_options:
        st.info("No businesses registered yet. Go to **Business Setup** to register your business.")
    else:
        selected_biz_idx = biz_options.index(current_biz_id) if current_biz_id in biz_options else 0

        def format_biz_label(b_id: str) -> str:
            b = businesses.get(b_id, {})
            return f"{b.get('name', b_id)} ({b.get('industry', 'General')})"

        selected_biz_id = st.selectbox(
            "Switch Tenant / Business:",
            options=biz_options,
            index=selected_biz_idx,
            format_func=format_biz_label,
            key="sidebar_biz_selector",
        )

        if selected_biz_id != current_biz_id:
            set_active_business_id(selected_biz_id)
            st.rerun()

        active_biz = get_active_business()
        if active_biz:
            st.markdown(
                f"<div style='background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; padding: 10px; margin-top: 5px; margin-bottom: 15px;'>"
                f"<strong style='color: #202124;'>{active_biz.get('name', 'Registered Business')}</strong><br>"
                f"<span style='color: #5f6368; font-size: 0.85rem;'>{active_biz.get('phone_number', '')}</span><br>"
                f"<span style='color: #137333; font-size: 0.8rem; font-weight: 600;'>● {active_biz.get('stats', {}).get('active_status', 'Active')}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.divider()

    # 2. Main Navigation Menu
    st.subheader("🧭 Navigation")
    NAV_OPTIONS = [
        "📊 Dashboard",
        "⚙️ Business Setup",
        "🧰 Tool Library",
        "💬 Agent Playground",
        "📞 Call History",
    ]

    selected_page = st.radio(
        "Go to page:",
        options=NAV_OPTIONS,
        label_visibility="collapsed",
    )

    st.divider()

    # API & Database persistence status badge
    badge_label, badge_type = get_api_status_badge()
    if badge_type == "success":
        st.success(f"🟢 **{badge_label}**")
    elif badge_type == "warning":
        st.warning(f"🟡 **{badge_label}**")
    else:
        st.error(f"🔴 **{badge_label}**")
        st.caption("Start API: `uvicorn backend.main:app --port 8000`")

    # Sidebar Platform Footnote
    st.caption("AI Receptionist Platform v0.4.0")
    st.caption("Step 8: FastAPI Layer & UI Integration")


# Disconnected backend alert banner
if not is_backend_connected():
    st.warning(
        "⚠️ **FastAPI Backend Offline**: Dashboard is running in disconnected mode. "
        "Start the REST API server using: `uvicorn backend.main:app --port 8000` to enable full persistence and workflow orchestration."
    )

# Route to selected page
if selected_page == "📊 Dashboard":
    render_dashboard_page()
elif selected_page == "⚙️ Business Setup":
    render_business_setup_page()
elif selected_page == "🧰 Tool Library":
    render_tool_library_page()
elif selected_page == "💬 Agent Playground":
    render_agent_playground_page()
elif selected_page == "📞 Call History":
    render_call_history_page()
