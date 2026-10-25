"""
Tool Library page for managing business-specific receptionist tools.
"""

import streamlit as st
from ui.state import (
    get_active_business,
    get_tools_catalogue,
    set_business_tool_status,
)
from ui.components import render_page_header


def render_tool_library_page() -> None:
    """Render the tool library where businesses enable/disable specific conversational tools."""
    business = get_active_business()
    if not business or not business.get("id"):
        render_page_header(
            title="🧰 Tool Library",
            subtitle="Enable or disable operational capabilities for your receptionist.",
            badge_text="No Business Selected",
            badge_type="warning",
        )
        st.info("Please register or select a business in **⚙️ Business Setup** to manage tools.")
        return

    biz_id = business["id"]
    tools_catalogue = get_tools_catalogue()
    enabled_tools = business.get("enabled_tools", {})

    render_page_header(
        title=f"🧰 Tool Library — {business.get('name', 'Business')}",
        subtitle=f"Enable or disable operational capabilities for this business receptionist.",
        badge_text="Tool Registry",
        badge_type="info",
    )

    st.warning(
        "⚙️ **Configuration Mode**: This library manages tool assignment and access control per business tenant. "
        "Underlying tool execution nodes will be wired to the LangGraph engine in Step 4."
    )

    # Tool categories filter or count
    categories = sorted(list(set(tool["category"] for tool in tools_catalogue.values())))
    active_count = sum(1 for val in enabled_tools.values() if val)
    total_count = len(tools_catalogue)

    st.markdown(
        f"**Active Tools for {business['name']}**: `{active_count} of {total_count} active`"
    )

    # Filter tab or segmented view
    selected_category = st.radio(
        "Filter by Category:",
        options=["All Categories"] + categories,
        horizontal=True,
    )

    st.divider()

    # Render tool cards
    for tool_id, tool_info in tools_catalogue.items():
        if selected_category != "All Categories" and tool_info["category"] != selected_category:
            continue

        is_currently_enabled = enabled_tools.get(tool_id, False)

        with st.container(border=True):
            col_icon, col_info, col_toggle = st.columns([0.08, 0.67, 0.25])

            with col_icon:
                st.markdown(f"### {tool_info.get('icon', '🔧')}")

            with col_info:
                st.markdown(f"**{tool_info['name']}**")
                st.caption(tool_info["description"])
                st.markdown(
                    f"<span style='background-color: #f1f3f4; color: #3c4043; padding: 2px 8px; "
                    f"border-radius: 6px; font-size: 0.75rem; font-weight: 500;'>Category: {tool_info['category']}</span>",
                    unsafe_allow_html=True,
                )

            with col_toggle:
                # Toggle for enabling/disabling
                status_key = f"toggle_{biz_id}_{tool_id}"
                new_status = st.toggle(
                    "Enabled for Business",
                    value=is_currently_enabled,
                    key=status_key,
                )

                if new_status != is_currently_enabled:
                    set_business_tool_status(biz_id, tool_id, new_status)
                    st.rerun()

                if new_status:
                    st.markdown(
                        "<span style='color: #137333; font-weight: 600; font-size: 0.85rem;'>● Active in Workflow</span>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        "<span style='color: #70757a; font-size: 0.85rem;'>○ Disabled</span>",
                        unsafe_allow_html=True,
                    )
