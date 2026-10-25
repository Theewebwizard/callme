"""
Session-state management and multi-tenant data access helpers.
Delegates all data operations to the FastAPI REST API layer via ApiClient.
"""

import copy
from typing import Dict, List, Any, Optional, Tuple
import streamlit as st

from ui.mock_data import INITIAL_BUSINESSES, INITIAL_TOOLS, MOCK_CALL_HISTORY
from ui.api_client import get_api_client, ApiClient, ApiClientError, ApiConnectionError


def init_session_state(api_client: Optional[ApiClient] = None) -> None:
    """
    Initialize Streamlit session state once per user session.
    Hydrates tenant data from the FastAPI REST API layer.
    """
    client = api_client or get_api_client()
    backend_online = False
    db_connected = False
    api_err_msg = None

    try:
        health = client.health_check()
        backend_online = True
        db_connected = health.get("database", {}).get("connected", False)
    except ApiConnectionError as conn_err:
        backend_online = False
        api_err_msg = str(conn_err)
    except Exception as exc:
        backend_online = False
        api_err_msg = f"API Error: {exc}"

    st.session_state["backend_connected"] = backend_online
    st.session_state["db_connected"] = db_connected
    st.session_state["api_error"] = api_err_msg

    if "selected_business_id" not in st.session_state:
        st.session_state["selected_business_id"] = "biz_spice_garden"

    if "tools_catalogue" not in st.session_state:
        st.session_state["tools_catalogue"] = copy.deepcopy(INITIAL_TOOLS)

    if "pending_actions" not in st.session_state:
        st.session_state["pending_actions"] = {}

    # Hydrate businesses from API if online
    if "businesses" not in st.session_state:
        st.session_state["businesses"] = {}
        if backend_online:
            try:
                biz_list = client.list_businesses()
                for b_summary in biz_list:
                    b_id = b_summary["id"]
                    detail = client.get_business(b_id)
                    st.session_state["businesses"][b_id] = detail
            except Exception as e:
                st.session_state["api_error"] = f"Failed to fetch businesses: {e}"
                st.session_state["businesses"] = copy.deepcopy(INITIAL_BUSINESSES)
        else:
            st.session_state["businesses"] = copy.deepcopy(INITIAL_BUSINESSES)

    # Hydrate call history from API if online
    if "call_history" not in st.session_state:
        st.session_state["call_history"] = {}
        if backend_online:
            try:
                for b_id in st.session_state["businesses"].keys():
                    calls_resp = client.get_call_history(b_id)
                    st.session_state["call_history"][b_id] = calls_resp.get("calls", [])
            except Exception:
                st.session_state["call_history"] = copy.deepcopy(MOCK_CALL_HISTORY)
        else:
            st.session_state["call_history"] = copy.deepcopy(MOCK_CALL_HISTORY)

    # Hydrate conversation messages
    if "playground_messages" not in st.session_state:
        st.session_state["playground_messages"] = {}
        for b_id, b_data in st.session_state["businesses"].items():
            greeting = b_data.get("greeting_message", "Hello! How can I assist you?")
            st.session_state["playground_messages"][b_id] = [
                {"role": "assistant", "content": greeting, "timestamp": "Just now"}
            ]


def is_backend_connected() -> bool:
    """Return whether the Streamlit UI is connected to the FastAPI backend."""
    return st.session_state.get("backend_connected", False)


def is_database_connected() -> bool:
    """Return whether the backend database is connected."""
    return st.session_state.get("db_connected", False)


def get_api_status_badge() -> Tuple[str, str]:
    """Return badge text and badge type representing backend & database connectivity."""
    if is_backend_connected():
        if is_database_connected():
            return ("FastAPI + Supabase PostgreSQL: Online", "success")
        return ("FastAPI Online (DB Offline)", "warning")
    return ("FastAPI Backend: Offline", "error")


# Backward compatibility alias
get_database_status_badge = get_api_status_badge


def get_active_business_id() -> str:
    """Return the ID of the currently active business."""
    selected = st.session_state.get("selected_business_id")
    businesses = st.session_state.get("businesses", {})
    if selected and selected in businesses:
        return selected
    if businesses:
        first_id = next(iter(businesses.keys()))
        st.session_state["selected_business_id"] = first_id
        return first_id
    return ""


def set_active_business_id(business_id: str) -> None:
    """Set the currently active business ID."""
    if business_id in st.session_state.get("businesses", {}):
        st.session_state["selected_business_id"] = business_id


def get_all_businesses() -> Dict[str, Dict[str, Any]]:
    """Return dictionary of all registered businesses."""
    return st.session_state.get("businesses", {})


def get_active_business() -> Dict[str, Any]:
    """Return configuration dictionary for the currently active business."""
    biz_id = get_active_business_id()
    if not biz_id:
        return {}
    return st.session_state.get("businesses", {}).get(biz_id, {})


def create_new_business(business_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Register a new business tenant via FastAPI POST /api/businesses.
    Updates local session state upon successful response.
    """
    client = get_api_client()
    if is_backend_connected():
        try:
            created = client.create_business(business_data)
            biz_id = created["id"]
            if "businesses" not in st.session_state:
                st.session_state["businesses"] = {}
            st.session_state["businesses"][biz_id] = created
            st.session_state["selected_business_id"] = biz_id
            return created
        except ApiClientError as err:
            st.session_state["api_error"] = str(err)
            raise

    # Fallback in offline mode
    biz_id = business_data.get("id") or f"biz_{business_data['name'].lower().replace(' ', '_')}"
    new_biz = dict(business_data)
    new_biz["id"] = biz_id
    new_biz.setdefault("stats", {"total_calls": 0, "bookings_completed": 0, "escalated_calls": 0, "active_status": "Active"})
    new_biz.setdefault("enabled_tools", {"lookup_faq": True, "book_appointment": True, "take_message": True, "transfer_call": True})
    st.session_state.setdefault("businesses", {})[biz_id] = new_biz
    st.session_state["selected_business_id"] = biz_id
    return new_biz


def delete_business_tenant(business_id: str) -> bool:
    """
    Delete a business tenant via FastAPI DELETE /api/businesses/{id}.
    Cleans up local session state.
    """
    client = get_api_client()
    if is_backend_connected():
        try:
            client.delete_business(business_id)
        except ApiClientError as err:
            st.session_state["api_error"] = str(err)
            raise

    # Clean local session state
    if "businesses" in st.session_state and business_id in st.session_state["businesses"]:
        del st.session_state["businesses"][business_id]

    if st.session_state.get("selected_business_id") == business_id:
        remaining = list(st.session_state.get("businesses", {}).keys())
        st.session_state["selected_business_id"] = remaining[0] if remaining else ""

    return True


def update_business_config(business_id: str, updated_data: Dict[str, Any]) -> None:
    """
    Update configuration fields for a specific business via FastAPI PUT /api/businesses/{id}.
    Updates local session state on successful response.
    """
    client = get_api_client()
    if is_backend_connected():
        try:
            persisted = client.update_business(business_id, updated_data)
            if business_id in st.session_state.get("businesses", {}):
                st.session_state["businesses"][business_id] = persisted
            return
        except ApiClientError as err:
            st.session_state["api_error"] = str(err)
            raise

    # Fallback to local session state if backend is offline
    if business_id in st.session_state.get("businesses", {}):
        st.session_state["businesses"][business_id].update(updated_data)


def get_tools_catalogue() -> Dict[str, Dict[str, Any]]:
    """Return the master catalogue of available receptionist tools."""
    return st.session_state.get("tools_catalogue", {})


def set_business_tool_status(business_id: str, tool_id: str, enabled: bool) -> None:
    """
    Update tool enabled/disabled status via FastAPI PUT /api/businesses/{id}/tools.
    """
    client = get_api_client()
    if is_backend_connected():
        try:
            resp = client.update_tools(business_id, {tool_id: enabled})
            if business_id in st.session_state.get("businesses", {}):
                st.session_state["businesses"][business_id]["enabled_tools"][tool_id] = enabled
            return
        except ApiClientError as err:
            st.session_state["api_error"] = str(err)
            raise

    # Fallback to session state
    if business_id in st.session_state.get("businesses", {}):
        if "enabled_tools" not in st.session_state["businesses"][business_id]:
            st.session_state["businesses"][business_id]["enabled_tools"] = {}
        st.session_state["businesses"][business_id]["enabled_tools"][tool_id] = enabled


def get_call_history_for_business(business_id: str, outcome: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return call records for the designated business via GET /api/businesses/{id}/calls."""
    client = get_api_client()
    if is_backend_connected():
        try:
            resp = client.get_call_history(business_id, outcome=outcome, limit=100)
            calls = resp.get("calls", [])
            st.session_state.setdefault("call_history", {})[business_id] = calls
            return calls
        except Exception:
            pass

    return st.session_state.get("call_history", {}).get(business_id, [])


def get_playground_messages(business_id: str) -> List[Dict[str, str]]:
    """Return chat conversation history for the playground of a specific business."""
    if business_id not in st.session_state.get("playground_messages", {}):
        greeting = st.session_state.get("businesses", {}).get(business_id, {}).get("greeting_message", "Hello!")
        st.session_state.setdefault("playground_messages", {})[business_id] = [
            {"role": "assistant", "content": greeting, "timestamp": "Just now"}
        ]
    return st.session_state["playground_messages"][business_id]


def add_playground_message(business_id: str, role: str, content: str) -> None:
    """Append a chat message to the local playground conversation history."""
    if business_id not in st.session_state.get("playground_messages", {}):
        st.session_state.setdefault("playground_messages", {})[business_id] = []

    st.session_state["playground_messages"][business_id].append({
        "role": role,
        "content": content,
    })


def reset_playground_messages(business_id: str) -> None:
    """Reset playground conversation history back to the initial greeting."""
    greeting = st.session_state.get("businesses", {}).get(business_id, {}).get("greeting_message", "Hello!")
    st.session_state.setdefault("playground_messages", {})[business_id] = [
        {"role": "assistant", "content": greeting, "timestamp": "Just now"}
    ]
    clear_pending_action(business_id)


def get_pending_action(business_id: str) -> Optional[Dict[str, Any]]:
    """Return any unconfirmed pending tool action for the given business."""
    return st.session_state.get("pending_actions", {}).get(business_id)


def set_pending_action(business_id: str, action: Optional[Dict[str, Any]]) -> None:
    """Set or update pending tool action awaiting explicit user confirmation."""
    if "pending_actions" not in st.session_state:
        st.session_state["pending_actions"] = {}

    if action is None:
        st.session_state["pending_actions"].pop(business_id, None)
    else:
        st.session_state["pending_actions"][business_id] = action


def clear_pending_action(business_id: str) -> None:
    """Clear any pending action for the designated business."""
    if "pending_actions" in st.session_state:
        st.session_state["pending_actions"].pop(business_id, None)


def send_api_playground_message(business_id: str, message: str) -> Dict[str, Any]:
    """Submit a customer message via POST /api/businesses/{id}/playground/messages."""
    client = get_api_client()
    return client.send_playground_message(business_id, message)


def confirm_api_pending_action(business_id: str, action_id: str) -> Dict[str, Any]:
    """Confirm a pending action via POST /api/businesses/{id}/pending-actions/{action_id}/confirm."""
    client = get_api_client()
    return client.confirm_pending_action(business_id, action_id)


def cancel_api_pending_action(business_id: str, action_id: str) -> Dict[str, Any]:
    """Cancel a pending action via POST /api/businesses/{id}/pending-actions/{action_id}/cancel."""
    client = get_api_client()
    return client.cancel_pending_action(business_id, action_id)
