"""
Dashboard overview page for the active business receptionist.
"""

import streamlit as st
import pandas as pd
from ui.state import get_active_business, get_tools_catalogue, get_call_history_for_business
from ui.components import render_page_header, render_mock_badge


def render_dashboard_page() -> None:
    """Render the main operations dashboard for the selected business."""
    business = get_active_business()
    if not business or not business.get("id"):
        render_page_header(
            title="📊 Receptionist Dashboard",
            subtitle="Register your business to begin viewing call telemetry and configuring receptionists.",
            badge_text="No Business Configured",
            badge_type="warning",
        )
        st.info("👋 **Welcome to AI Receptionist Platform!**\n\nNo businesses are currently registered. Please go to **⚙️ Business Setup** in the sidebar to register your business profile.")
        return

    tools_catalogue = get_tools_catalogue()
    call_history = get_call_history_for_business(business["id"])

    # Header with active business status
    status_label = f"🟢 {business.get('stats', {}).get('active_status', 'Active')} & Ready"
    render_page_header(
        title=f"📊 Receptionist Dashboard — {business.get('name', 'My Business')}",
        subtitle=f"Industry: {business.get('industry', 'Other')} | Operating Schedule: {business.get('opening_time', '09:00')} - {business.get('closing_time', '21:00')} ({business.get('timezone', 'Asia/Kolkata')})",
        badge_text=status_label,
        badge_type="success",
    )

    render_mock_badge("Simulated call telemetry and receptionist engagement metrics")

    # High-level KPIs
    stats = business.get("stats", {})
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Total Calls Handled",
            value=stats.get("total_calls", 0),
            delta="+18% this week",
        )
    with col2:
        st.metric(
            label="Bookings Completed",
            value=stats.get("bookings_completed", 0),
            delta="+12% conversion",
        )
    with col3:
        st.metric(
            label="Escalated / Missed",
            value=stats.get("escalated_calls", 0),
            delta="-3% escalation",
            delta_color="inverse",
        )
    with col4:
        st.metric(
            label="Avg Call Duration",
            value=stats.get("avg_duration", "2m 00s"),
            delta="-15s vs benchmark",
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Secondary split: Enabled Tools & Configuration Summary
    left_col, right_col = st.columns([0.55, 0.45])

    with left_col:
        st.subheader("🛠️ Enabled Tools Summary")
        enabled_tool_ids = [
            t_id for t_id, enabled in business.get("enabled_tools", {}).items() if enabled
        ]
        total_tools_count = len(tools_catalogue)

        st.caption(f"{len(enabled_tool_ids)} of {total_tools_count} platform tools enabled for this tenant")

        if not enabled_tool_ids:
            st.warning("No tools currently enabled. Go to the Tool Library to activate capabilities.")
        else:
            for tool_id in enabled_tool_ids:
                tool_info = tools_catalogue.get(tool_id, {})
                icon = tool_info.get("icon", "🔧")
                name = tool_info.get("name", tool_id)
                category = tool_info.get("category", "General")
                desc = tool_info.get("description", "")
                
                with st.container(border=True):
                    c1, c2 = st.columns([0.75, 0.25])
                    with c1:
                        st.markdown(f"**{icon} {name}**")
                        st.caption(desc)
                    with c2:
                        st.markdown(f"<span style='background-color: #e8f0fe; color: #1a73e8; padding: 2px 8px; border-radius: 8px; font-size: 0.75rem; font-weight: 600;'>{category}</span>", unsafe_allow_html=True)

    with right_col:
        st.subheader("📞 Virtual Receptionist Info")
        with st.container(border=True):
            st.markdown(f"**Assigned Phone**: `{business['phone_number']}`")
            st.markdown(f"**Line Connection**: `{business['assigned_number_status']}`")
            st.markdown(f"**Languages Supported**: {', '.join(business['languages'])}")
            st.markdown(f"**Default Greeting Prompt**:")
            st.info(f"\"{business['greeting_message']}\"")
            st.markdown(f"**Transfer Escalation Policy**:")
            st.caption(business["transfer_instructions"])

    st.divider()

    # Recent Call Activity
    st.subheader("🕒 Recent Call Activity")
    st.caption("Latest inbound voice calls handled by the AI receptionist")

    if not call_history:
        st.info("No recent call activity recorded for this business.")
    else:
        recent_records = call_history[:5]
        
        # Display as clean summary table
        table_data = []
        for call in recent_records:
            table_data.append({
                "Date & Time": call["datetime"],
                "Caller": call["caller_number"],
                "Duration": call["duration"],
                "Outcome": call["outcome"],
                "Summary": call["summary"],
                "Tools Used": ", ".join(call["tools_used"]) if call["tools_used"] else "None",
            })
        
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
