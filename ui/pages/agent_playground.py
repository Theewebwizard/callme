"""
Agent Playground: Business-aware conversation playground powered by LangGraph & Groq LLM.
"""

import streamlit as st
from ui.state import (
    get_active_business,
    get_tools_catalogue,
    get_playground_messages,
    add_playground_message,
    reset_playground_messages,
    get_pending_action,
    set_pending_action,
    clear_pending_action,
    send_api_playground_message,
    confirm_api_pending_action,
    cancel_api_pending_action,
    is_backend_connected,
)
from ui.components import render_page_header
from ui.api_client import ApiClientError, ApiConnectionError
from backend.services.groq_service import get_groq_service


def render_agent_playground_page() -> None:
    """Render the business-aware conversation playground orchestrated by LangGraph."""
    business = get_active_business()
    if not business or not business.get("id"):
        render_page_header(
            title="💬 Agent Playground",
            subtitle="Test conversation responses with your AI receptionist.",
            badge_text="No Business Selected",
            badge_type="warning",
        )
        st.info("Please register or select a business in **⚙️ Business Setup** to test the conversational agent.")
        return

    biz_id = business["id"]
    tools_catalogue = get_tools_catalogue()
    groq_service = get_groq_service()

    # Enabled tools list for display
    enabled_tools = [
        tools_catalogue[t_id]["name"]
        for t_id, enabled in business.get("enabled_tools", {}).items()
        if enabled and t_id in tools_catalogue
    ]

    badge_text = (
        f"LangGraph + Groq ({groq_service.model})"
        if groq_service.is_configured
        else "LangGraph: Awaiting Groq Key"
    )
    badge_type = "success" if groq_service.is_configured else "warning"

    render_page_header(
        title=f"💬 Agent Playground — {business['name']}",
        subtitle=f"Live conversational testing orchestrated by LangGraph for {business['name']}.",
        badge_text=badge_text,
        badge_type=badge_type,
    )

    # API Configuration Notice
    if not is_backend_connected():
        st.warning(
            "⚠️ **FastAPI Backend Offline**: The Agent Playground sends messages via the REST API layer. "
            "Start the API server (`uvicorn backend.main:app --port 8000`) to enable live conversation orchestration."
        )

    if not groq_service.is_configured:
        st.warning(
            "⚠️ **Groq API Not Configured**: Live LLM responses require a valid API key. "
            "To activate real conversations, add `GROQ_API_KEY=gsk_...` to your `.env` file in the project root. "
            f"Configured model: `{groq_service.model}`."
        )
    else:
        st.caption(
            f"🟢 **LangGraph Conversation Workflow Active**: Connected to Groq model `{groq_service.model}`. "
            f"State graph processes dialogue parameterized by {business['name']}'s profile, hours, FAQs, and enabled tools."
        )

    # Context Header: Current business profile & active tools
    with st.container(border=True):
        c1, c2 = st.columns([0.72, 0.28])
        with c1:
            st.markdown(f"**Tenant Profile**: `{business['name']}` ({business['industry']})")
            tools_str = ", ".join(enabled_tools) if enabled_tools else "None"
            st.caption(f"**Enabled Business Tools**: {tools_str}")
        with c2:
            if st.button("🔄 Reset Conversation", use_container_width=True):
                reset_playground_messages(biz_id)
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Render persistent conversation history
    messages = get_playground_messages(biz_id)
    for msg in messages:
        role = msg.get("role", "assistant")
        with st.chat_message(role):
            st.markdown(msg.get("content", ""))

    # Render pending confirmation card if Phase B confirmation is awaiting approval
    pending_action = get_pending_action(biz_id)
    if pending_action:
        with st.container(border=True):
            st.warning("⚠️ **Confirmation Required Before Execution**")
            st.markdown(
                f"The receptionist has prepared the **{pending_action.get('tool_name', pending_action.get('tool_id'))}** action. "
                "Because this operation updates appointment or reservation records, please confirm or reject it below."
            )
            if pending_action.get("summary"):
                st.info(pending_action["summary"])
            elif pending_action.get("arguments"):
                st.markdown("**Action Arguments:**")
                for k, v in pending_action["arguments"].items():
                    st.markdown(f"- **{k.replace('_', ' ').title()}**: `{v}`")

            col_confirm, col_cancel = st.columns(2)
            with col_confirm:
                if st.button(
                    "✅ Confirm Action",
                    type="primary",
                    use_container_width=True,
                    key=f"btn_confirm_{pending_action.get('action_id')}",
                ):
                    with st.spinner("Executing confirmed action via API..."):
                        try:
                            res = confirm_api_pending_action(biz_id, pending_action["action_id"])
                            clear_pending_action(biz_id)
                            ref_id = res.get("reference_id")
                            ref_text = f" (Ref: `{ref_id}`)" if ref_id else ""
                            msg = res.get("message", "Action confirmed and executed successfully.")
                            add_playground_message(
                                biz_id,
                                "assistant",
                                f"✅ **Confirmed**: {msg}{ref_text}",
                            )
                            st.rerun()
                        except (ApiClientError, ApiConnectionError) as exc:
                            st.error(f"❌ Failed to confirm action: {exc}")

            with col_cancel:
                if st.button(
                    "❌ Cancel / Reject",
                    type="secondary",
                    use_container_width=True,
                    key=f"btn_cancel_{pending_action.get('action_id')}",
                ):
                    with st.spinner("Cancelling action via API..."):
                        try:
                            res = cancel_api_pending_action(biz_id, pending_action["action_id"])
                            clear_pending_action(biz_id)
                            add_playground_message(
                                biz_id,
                                "assistant",
                                "🚫 **Action Cancelled**: The requested action was cancelled. How else may I assist you?",
                            )
                            st.rerun()
                        except (ApiClientError, ApiConnectionError) as exc:
                            st.error(f"❌ Failed to cancel action: {exc}")

    # Chat input
    user_input = st.chat_input(f"Type a message to {business['name']}'s receptionist...")
    if user_input:
        cleaned_input = user_input.strip()
        if not cleaned_input:
            return

        # Check backend connectivity
        if not is_backend_connected():
            st.error(
                "Cannot send message: FastAPI backend server is offline. "
                "Please start the backend with `uvicorn backend.main:app --port 8000`."
            )
            return

        # Check API key before sending
        if not groq_service.is_configured:
            st.error(
                "Cannot send message: `GROQ_API_KEY` is not configured in `.env`. "
                "Please configure your key and restart the server to chat."
            )
            return

        # A new message clears any prior pending action
        clear_pending_action(biz_id)

        # Record user message in tenant's conversation history
        add_playground_message(biz_id, "user", cleaned_input)

        # Execute conversation workflow via FastAPI REST API
        with st.spinner(f"Sending message via API to {business['name']}'s receptionist..."):
            try:
                resp = send_api_playground_message(biz_id, cleaned_input)

                # If a two-phase confirmation action was yielded, store it
                if resp.get("pending_action"):
                    set_pending_action(biz_id, resp["pending_action"])

                if resp.get("success") and resp.get("content"):
                    add_playground_message(biz_id, "assistant", resp["content"])
                    st.rerun()
                else:
                    error_msg = resp.get("error") or "Unknown API response error."
                    st.error(f"⚠️ Orchestration Error: {error_msg}")
            except (ApiClientError, ApiConnectionError) as exc:
                st.error(f"⚠️ API Communication Error: {exc}")
