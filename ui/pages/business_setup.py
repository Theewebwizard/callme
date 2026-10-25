"""
Business setup and receptionist configuration page.
Supports registering new business profiles, editing active tenants, and purging mock demo data.
"""

from typing import List, Dict
import streamlit as st
from ui.state import (
    get_active_business,
    update_business_config,
    create_new_business,
    delete_business_tenant,
    get_all_businesses,
    is_database_connected,
)
from ui.components import render_page_header

INDUSTRY_OPTIONS = [
    "Astrology / Spiritual",
    "Consulting / Services",
    "Restaurant",
    "Clinic",
    "Salon",
    "Real Estate",
    "Retail / E-commerce",
    "Legal",
    "Other",
]
LANGUAGE_OPTIONS = [
    "English",
    "Hindi",
    "Kannada",
    "Tamil",
    "Telugu",
    "Marathi",
    "Bengali",
    "Gujarati",
    "Spanish",
    "French",
]
TIMEZONE_OPTIONS = [
    "Asia/Kolkata",
    "UTC",
    "America/New_York",
    "America/Los_Angeles",
    "Europe/London",
    "Asia/Dubai",
    "Asia/Singapore",
]


def render_business_setup_page() -> None:
    """Render the configuration form for business profile and receptionist policies."""
    business = get_active_business()
    biz_id = business.get("id", "")
    biz_name = business.get("name", "No Business Configured")

    render_page_header(
        title=f"⚙️ Business Setup — {biz_name}",
        subtitle="Register your real business profile, configure reception greetings, operating hours, and knowledge base.",
        badge_text="Config Mode",
        badge_type="info",
    )

    tab_register, tab_edit, tab_cleanup = st.tabs([
        "➕ Register New Business",
        "⚙️ Configure Active Business",
        "🗑️ Purge Mock Tenants",
    ])

    # =========================================================================
    # TAB 1: REGISTER NEW BUSINESS
    # =========================================================================
    with tab_register:
        st.subheader("Register Your Business")
        st.caption("Onboard your real business into the multi-tenant AI Receptionist platform.")

        with st.form(key="register_new_business_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input(
                    "Business Name *",
                    placeholder="e.g. Astro Coach",
                    help="Official trading name of your business spoken by the AI receptionist.",
                )
                new_industry = st.selectbox(
                    "Industry Category *",
                    options=INDUSTRY_OPTIONS,
                    index=0,
                )
                new_phone = st.text_input(
                    "Inbound Phone Number",
                    value="+919513886363",
                    help="Virtual telephony or Exotel DID routing calls to this receptionist.",
                )

            with col2:
                new_description = st.text_area(
                    "Business Description & Core Offerings *",
                    placeholder="e.g. Vedic astrology consultations, birth chart analysis, planetary gem consultations, and relationship guidance.",
                    height=125,
                    help="Context used by the AI agent to understand your domain.",
                )

            st.divider()
            st.subheader("Operating Hours & Languages")
            c1, c2, c3 = st.columns(3)
            with c1:
                new_open = st.text_input("Opening Time (HH:MM) *", value="09:00")
            with c2:
                new_close = st.text_input("Closing Time (HH:MM) *", value="21:00")
            with c3:
                new_tz = st.selectbox("Business Timezone *", options=TIMEZONE_OPTIONS, index=0)

            new_languages = st.multiselect(
                "Supported Languages *",
                options=LANGUAGE_OPTIONS,
                default=["English", "Hindi"],
            )

            st.divider()
            st.subheader("Receptionist Greeting & Escalation Rules")
            new_greeting = st.text_area(
                "Inbound Call Greeting *",
                value="Namaste! Welcome to our reception. I am your AI virtual assistant. How can I help you today?",
                height=80,
                help="Spoken immediately when a caller dials your phone line or connects on web.",
            )
            new_transfer = st.text_area(
                "Human Escalation & Transfer Rules *",
                value="Transfer call to human manager if caller asks for urgent personal attention or questions outside our services.",
                height=80,
            )

            st.divider()
            st.subheader("Initial FAQs (Knowledge Base)")
            new_faq_q = st.text_input("Initial Question #1", placeholder="e.g. What are your consultation charges?")
            new_faq_a = st.text_area("Initial Answer #1", placeholder="e.g. 15-minute consultations start at Rs. 499, and full birth chart analysis is Rs. 1,499.", height=65)

            new_faq_q2 = st.text_input("Initial Question #2 (Optional)", placeholder="e.g. How can I book an appointment?")
            new_faq_a2 = st.text_area("Initial Answer #2 (Optional)", placeholder="e.g. You can book an appointment right now on this call or on our website.", height=65)

            submitted_new = st.form_submit_button("🚀 Register & Activate Business", type="primary", use_container_width=True)

            if submitted_new:
                val_errors = []
                if not new_name.strip():
                    val_errors.append("Business Name cannot be empty.")
                if not new_description.strip():
                    val_errors.append("Business Description is required.")
                if not new_greeting.strip():
                    val_errors.append("Greeting message is required.")
                if not new_languages:
                    val_errors.append("At least one language must be selected.")

                if val_errors:
                    for err in val_errors:
                        st.error(f"⚠️ {err}")
                else:
                    faqs = []
                    if new_faq_q.strip() and new_faq_a.strip():
                        faqs.append({"question": new_faq_q.strip(), "answer": new_faq_a.strip(), "category": "General"})
                    if new_faq_q2.strip() and new_faq_a2.strip():
                        faqs.append({"question": new_faq_q2.strip(), "answer": new_faq_a2.strip(), "category": "General"})

                    create_payload = {
                        "name": new_name.strip(),
                        "industry": new_industry,
                        "description": new_description.strip(),
                        "phone_number": new_phone.strip(),
                        "opening_time": new_open.strip(),
                        "closing_time": new_close.strip(),
                        "timezone": new_tz,
                        "languages": new_languages,
                        "greeting_message": new_greeting.strip(),
                        "transfer_instructions": new_transfer.strip(),
                        "faqs": faqs,
                        "enabled_tools": {
                            "lookup_faq": True,
                            "book_appointment": True,
                            "take_message": True,
                            "transfer_call": True,
                        },
                    }

                    try:
                        res = create_new_business(create_payload)
                        st.success(f"🎉 Business **{res['name']}** successfully registered!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"❌ Failed to register business: {exc}")

    # =========================================================================
    # TAB 2: CONFIGURE ACTIVE BUSINESS
    # =========================================================================
    with tab_edit:
        if not biz_id or not business:
            st.warning("⚠️ No business is currently active or selected. Please register a business in the **Register New Business** tab.")
        else:
            with st.form(key=f"business_setup_form_{biz_id}"):
                st.subheader(f"1. Profile: {business.get('name')}")

                col1, col2 = st.columns(2)
                with col1:
                    biz_name_edit = st.text_input(
                        "Business Name *",
                        value=business.get("name", ""),
                        help="Official trading name of the business spoken by the AI receptionist.",
                    )
                    
                    industry_val = business.get("industry", "Other")
                    industry_idx = INDUSTRY_OPTIONS.index(industry_val) if industry_val in INDUSTRY_OPTIONS else len(INDUSTRY_OPTIONS) - 1
                    industry_edit = st.selectbox(
                        "Industry Category *",
                        options=INDUSTRY_OPTIONS,
                        index=industry_idx,
                    )

                    phone_number_edit = st.text_input(
                        "Assigned Inbound Phone Number",
                        value=business.get("phone_number", "+919513886363"),
                        help="Virtual telephony or Exotel DID number routing calls to this receptionist.",
                    )

                with col2:
                    description_edit = st.text_area(
                        "Business Description & Core Offerings *",
                        value=business.get("description", ""),
                        height=100,
                        help="Summary of business services used by the agent to understand context.",
                    )

                    st.text_input(
                        "Telephony Line Status",
                        value=business.get("assigned_number_status", "Active & Connected"),
                        disabled=True,
                    )

                st.divider()
                st.subheader("2. Schedule & Localization")
                c1, c2, c3 = st.columns(3)
                with c1:
                    opening_time_edit = st.text_input(
                        "Opening Time (HH:MM) *",
                        value=business.get("opening_time", "09:00"),
                    )
                with c2:
                    closing_time_edit = st.text_input(
                        "Closing Time (HH:MM) *",
                        value=business.get("closing_time", "21:00"),
                    )
                with c3:
                    tz_val = business.get("timezone", "Asia/Kolkata")
                    tz_idx = TIMEZONE_OPTIONS.index(tz_val) if tz_val in TIMEZONE_OPTIONS else 0
                    timezone_edit = st.selectbox(
                        "Business Timezone *",
                        options=TIMEZONE_OPTIONS,
                        index=tz_idx,
                    )

                supported_languages_edit = st.multiselect(
                    "Languages Supported *",
                    options=LANGUAGE_OPTIONS,
                    default=business.get("languages", ["English"]),
                )

                st.divider()
                st.subheader("3. Conversational Behavior & Human Escalation")
                greeting_message_edit = st.text_area(
                    "Initial Inbound Greeting Prompt *",
                    value=business.get("greeting_message", ""),
                    height=80,
                )

                transfer_instructions_edit = st.text_area(
                    "Human Transfer & Escalation Rules *",
                    value=business.get("transfer_instructions", ""),
                    height=80,
                )

                st.divider()
                st.subheader("4. Business FAQs & Knowledge Base")
                st.caption("Frequently asked questions referenced by the 'Answer Business FAQs' tool.")

                current_faqs: List[Dict[str, str]] = business.get("faqs", [])
                faq_entries = []
                for idx, faq in enumerate(current_faqs):
                    with st.expander(f"FAQ #{idx + 1}: {faq.get('question', 'New Question')[:40]}...", expanded=(idx == 0)):
                        q = st.text_input(f"Question #{idx + 1}", value=faq.get("question", ""), key=f"faq_q_{biz_id}_{idx}")
                        a = st.text_area(f"Answer #{idx + 1}", value=faq.get("answer", ""), height=75, key=f"faq_a_{biz_id}_{idx}")
                        faq_entries.append({"question": q, "answer": a})

                with st.expander("➕ Add Another FAQ Entry", expanded=False):
                    new_q = st.text_input("New Question", value="", key=f"new_faq_q_{biz_id}")
                    new_a = st.text_area("New Answer", value="", height=75, key=f"new_faq_a_{biz_id}")
                    if new_q.strip() and new_a.strip():
                        faq_entries.append({"question": new_q.strip(), "answer": new_a.strip()})

                st.markdown("<br>", unsafe_allow_html=True)
                submitted_edit = st.form_submit_button("💾 Save Business Configuration", type="primary", use_container_width=True)

                if submitted_edit:
                    updated_data = {
                        "name": biz_name_edit.strip(),
                        "industry": industry_edit,
                        "description": description_edit.strip(),
                        "phone_number": phone_number_edit.strip(),
                        "opening_time": opening_time_edit.strip(),
                        "closing_time": closing_time_edit.strip(),
                        "timezone": timezone_edit,
                        "languages": supported_languages_edit,
                        "greeting_message": greeting_message_edit.strip(),
                        "transfer_instructions": transfer_instructions_edit.strip(),
                        "faqs": [faq for faq in faq_entries if faq["question"].strip()],
                    }
                    try:
                        update_business_config(biz_id, updated_data)
                        st.success(f"✅ Configuration for '{biz_name_edit.strip()}' saved successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to save configuration: {e}")

    # =========================================================================
    # TAB 3: PURGE MOCK TENANTS
    # =========================================================================
    with tab_cleanup:
        st.subheader("Manage & Purge Mock Tenants")
        st.caption("Remove prototype mock tenants (`Royal Spice Garden`, `Apex Dental Clinic`, simulated call histories).")

        all_bizs = get_all_businesses()
        mock_keys = [k for k in ["biz_spice_garden", "biz_apex_dental"] if k in all_bizs]

        if not mock_keys:
            st.success("✅ **Clean State**: No mock sample tenants (`biz_spice_garden`, `biz_apex_dental`) are present in the system!")
        else:
            st.warning(f"Found {len(mock_keys)} mock tenant(s) in database: `{', '.join(mock_keys)}`.")

            for m_key in mock_keys:
                m_biz = all_bizs[m_key]
                st.markdown(f"- **{m_biz.get('name')}** (`{m_key}`) — Industry: *{m_biz.get('industry')}*")

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ Purge All Mock Data Now", type="secondary", use_container_width=True):
                deleted_count = 0
                for m_key in mock_keys:
                    try:
                        delete_business_tenant(m_key)
                        deleted_count += 1
                    except Exception as del_err:
                        st.error(f"Failed to delete {m_key}: {del_err}")

                if deleted_count > 0:
                    st.success(f"✅ Successfully purged {deleted_count} mock tenant(s) and their cascading records!")
                    st.rerun()
