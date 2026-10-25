"""
Reusable presentation components for the AI Receptionist Platform dashboard.
"""

from typing import Optional
import streamlit as st


def render_page_header(
    title: str,
    subtitle: Optional[str] = None,
    badge_text: Optional[str] = None,
    badge_type: str = "success",
) -> None:
    """Render a consistent page header with optional status badge."""
    col1, col2 = st.columns([0.8, 0.2])
    with col1:
        st.title(title)
        if subtitle:
            st.caption(subtitle)
    with col2:
        if badge_text:
            if badge_type == "success":
                st.markdown(
                    f"<div style='text-align: right; padding-top: 1.5rem;'>"
                    f"<span style='background-color: #e6f4ea; color: #137333; font-weight: 600; "
                    f"padding: 6px 12px; border-radius: 16px; border: 1px solid #ceead6; font-size: 0.85rem;'>"
                    f"{badge_text}</span></div>",
                    unsafe_allow_html=True,
                )
            elif badge_type == "warning":
                st.markdown(
                    f"<div style='text-align: right; padding-top: 1.5rem;'>"
                    f"<span style='background-color: #fef7e0; color: #b06000; font-weight: 600; "
                    f"padding: 6px 12px; border-radius: 16px; border: 1px solid #fce8b2; font-size: 0.85rem;'>"
                    f"{badge_text}</span></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div style='text-align: right; padding-top: 1.5rem;'>"
                    f"<span style='background-color: #e8f0fe; color: #1a73e8; font-weight: 600; "
                    f"padding: 6px 12px; border-radius: 16px; border: 1px solid #d2e3fc; font-size: 0.85rem;'>"
                    f"{badge_text}</span></div>",
                    unsafe_allow_html=True,
                )
    st.divider()


def render_mock_badge(context: str = "Showing simulated prototype data") -> None:
    """Render a clean, unobtrusive mock data notice."""
    st.info(f"📊 **Mock Data Demonstration**: {context}. Real telemetry will be enabled in subsequent steps.")


def render_outcome_pill(outcome: str) -> str:
    """Return formatted HTML for call outcomes."""
    colors = {
        "Booking Completed": ("#e6f4ea", "#137333"),
        "Inquiry Resolved": ("#e8f0fe", "#1a73e8"),
        "Transferred to Staff": ("#fef7e0", "#b06000"),
        "Message Recorded": ("#f1f3f4", "#3c4043"),
        "Missed Call": ("#fce8e6", "#c5221f"),
    }
    bg, fg = colors.get(outcome, ("#f1f3f4", "#3c4043"))
    return (
        f"<span style='background-color: {bg}; color: {fg}; font-weight: 600; "
        f"padding: 3px 8px; border-radius: 12px; font-size: 0.8rem;'>{outcome}</span>"
    )
