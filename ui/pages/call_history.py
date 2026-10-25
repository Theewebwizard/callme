"""
Call History page displaying simulated inbound call logs and transcript summaries.
"""

from typing import List, Dict, Any
import streamlit as st
import pandas as pd
from ui.state import get_active_business, get_call_history_for_business
from ui.components import render_page_header, render_mock_badge


def render_call_history_page() -> None:
    """Render call history records with filters and conversation summary details."""
    business = get_active_business()
    if not business or not business.get("id"):
        render_page_header(
            title="📞 Call History",
            subtitle="Recent call logs, caller details, outcomes, and automated tool interventions.",
            badge_text="No Business Selected",
            badge_type="warning",
        )
        st.info("Please register or select a business in **⚙️ Business Setup** to view call history logs.")
        return

    biz_id = business["id"]
    calls: List[Dict[str, Any]] = get_call_history_for_business(biz_id)

    render_page_header(
        title=f"📞 Call History — {business.get('name', 'Business')}",
        subtitle=f"Recent call logs, caller details, outcomes, and automated tool interventions.",
        badge_text="Audit Log",
        badge_type="info",
    )

    render_mock_badge("Sample call records with masked caller identifiers")

    if not calls:
        st.info("No call records found for this business.")
        return

    # Filters
    col_filter_outcome, col_search = st.columns([0.4, 0.6])

    all_outcomes = sorted(list(set(c["outcome"] for c in calls)))
    with col_filter_outcome:
        selected_outcome = st.selectbox(
            "Filter by Call Outcome:",
            options=["All Outcomes"] + all_outcomes,
        )

    with col_search:
        search_query = st.text_input(
            "Search Summaries or Numbers:",
            placeholder="e.g. reservation, alignment, 98765...",
        )

    # Apply filters
    filtered_calls = calls
    if selected_outcome != "All Outcomes":
        filtered_calls = [c for c in filtered_calls if c["outcome"] == selected_outcome]

    if search_query.strip():
        q = search_query.strip().lower()
        filtered_calls = [
            c
            for c in filtered_calls
            if q in c["summary"].lower() or q in c["caller_number"].lower() or q in c["outcome"].lower()
        ]

    st.markdown(f"**Showing {len(filtered_calls)} records**")

    # Display as a dataframe
    table_rows = []
    for c in filtered_calls:
        table_rows.append({
            "Date / Time": c["datetime"],
            "Caller Number": c["caller_number"],
            "Duration": c["duration"],
            "Outcome": c["outcome"],
            "Tools Utilized": ", ".join(c["tools_used"]) if c["tools_used"] else "None",
            "Call Summary": c["summary"],
        })

    df = pd.DataFrame(table_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # Detailed record expansion
    st.subheader("🔍 Call Transcript & Audit Details")
    st.caption("Click any record below to inspect the call recap and tool actions.")

    for call in filtered_calls:
        title = f"{call['datetime']} | {call['caller_number']} — {call['outcome']} ({call['duration']})"
        with st.expander(title):
            c1, c2 = st.columns([0.7, 0.3])
            with c1:
                st.markdown(f"**Call Summary**:")
                st.write(call["summary"])
            with c2:
                st.markdown(f"**Tools Triggered**:")
                if call["tools_used"]:
                    for tool in call["tools_used"]:
                        st.markdown(f"- `{tool}`")
                else:
                    st.caption("No automated tools called.")
