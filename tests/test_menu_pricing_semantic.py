"""
Unit and integration tests for dynamic restaurant menu upload,
semantic concept retrieval, dietary/budget filtering, and AI receptionist tool execution.
"""

import pytest
from typing import Dict, Any, List
from fastapi.testclient import TestClient

from backend.main import app
from backend.database.service import get_database_service
from backend.database.repositories.menu_repo import MenuItemRepository
from backend.database.models import MenuItem
from backend.database.engine import session_scope
from backend.tools.registry import get_tool_registry
from backend.tools.definitions import QueryMenuPricingInput
from backend.tools.base import ToolExecutionStatus
from backend.auth import create_access_token, ROLE_BUSINESS_OWNER


SAMPLE_MENU_ITEMS: List[Dict[str, Any]] = [
    {
        "name": "Paneer Tikka Angaare",
        "category": "Starters",
        "price": 320.0,
        "currency": "INR",
        "description": "Charcoal grilled cottage cheese marinated in Kashmiri chillies, mustard oil, and hung yogurt.",
        "dietary_tags": ["vegetarian", "gluten-free"],
        "spice_level": "spicy",
        "is_available": True,
    },
    {
        "name": "Murgh Malai Tikka",
        "category": "Starters",
        "price": 380.0,
        "currency": "INR",
        "description": "Tender boneless chicken morsels steeped in cream, cardamom, and gentle cheese marinade.",
        "dietary_tags": ["non-vegetarian", "gluten-free"],
        "spice_level": "mild",
        "is_available": True,
    },
    {
        "name": "Dal Makhani",
        "category": "Mains",
        "price": 280.0,
        "currency": "INR",
        "description": "Slow-cooked black lentils simmered overnight with farm butter, vine tomatoes, and dairy cream.",
        "dietary_tags": ["vegetarian", "gluten-free"],
        "spice_level": "mild",
        "is_available": True,
    },
    {
        "name": "Butter Chicken",
        "category": "Mains",
        "price": 420.0,
        "currency": "INR",
        "description": "Tandoor roasted boneless chicken in an aromatic, velvety makhani gravy.",
        "dietary_tags": ["non-vegetarian", "gluten-free"],
        "spice_level": "mild",
        "is_available": True,
    },
    {
        "name": "Paneer Butter Masala",
        "category": "Mains",
        "price": 340.0,
        "currency": "INR",
        "description": "Velvety cottage cheese cubes bathed in rich cashew-tomato gravy infused with dried fenugreek.",
        "dietary_tags": ["vegetarian", "gluten-free", "jain-available"],
        "spice_level": "mild",
        "is_available": True,
    },
    {
        "name": "Butter Naan",
        "category": "Breads",
        "price": 60.0,
        "currency": "INR",
        "description": "Traditional tandoor-baked leavened flatbread brushed with molten farm butter.",
        "dietary_tags": ["vegetarian"],
        "spice_level": "mild",
        "is_available": True,
    },
    {
        "name": "Gulab Jamun (2 pcs)",
        "category": "Desserts",
        "price": 90.0,
        "currency": "INR",
        "description": "Warm caramelized milk dumplings infused with green cardamom and rose sugar syrup.",
        "dietary_tags": ["vegetarian"],
        "spice_level": "mild",
        "is_available": True,
    },
    {
        "name": "Rasmalai (2 pcs)",
        "category": "Desserts",
        "price": 130.0,
        "currency": "INR",
        "description": "Delicate saffron-soaked cottage cheese patties steeped in sweetened reduced pistachio milk.",
        "dietary_tags": ["vegetarian", "gluten-free"],
        "spice_level": "mild",
        "is_available": True,
    },
    {
        "name": "Mango Lassi",
        "category": "Beverages",
        "price": 120.0,
        "currency": "INR",
        "description": "Thick creamy yogurt smoothie blended with ripe Alphonso mango pulp.",
        "dietary_tags": ["vegetarian", "gluten-free"],
        "spice_level": "mild",
        "is_available": True,
    },
]


# ==============================================================================
# 1. Repository & Semantic Search Engine Tests
# ==============================================================================

def test_menu_repo_crud_and_bulk_upload():
    """Verify CRUD operations and bulk upload replacement for tenant menu items."""
    db_service = get_database_service()
    biz_id = "biz_spice_garden"

    # Upload menu items
    persisted = db_service.upload_menu_items(biz_id, SAMPLE_MENU_ITEMS, replace=True)
    assert len(persisted) == len(SAMPLE_MENU_ITEMS)

    # List all items
    items = db_service.list_menu_items(biz_id)
    assert len(items) == len(SAMPLE_MENU_ITEMS)

    # Filter by category
    desserts = db_service.list_menu_items(biz_id, category="Desserts")
    assert len(desserts) == 2
    assert {d["name"] for d in desserts} == {"Gulab Jamun (2 pcs)", "Rasmalai (2 pcs)"}

    # Update item
    item_to_update = desserts[0]
    updated = db_service.update_menu_item(biz_id, item_to_update["id"], {"price": 95.0, "spice_level": "mild"})
    assert updated is not None
    assert updated["price"] == 95.0

    # Delete item
    del_ok = db_service.delete_menu_item(biz_id, item_to_update["id"])
    assert del_ok is True
    post_delete_desserts = db_service.list_menu_items(biz_id, category="Desserts")
    assert len(post_delete_desserts) == 1


def test_semantic_concept_sweet_dishes():
    """Verify semantic concept expansion for sweet dishes / desserts across English & Hindi."""
    db_service = get_database_service()
    biz_id = "biz_spice_garden"
    db_service.upload_menu_items(biz_id, SAMPLE_MENU_ITEMS, replace=True)

    # 1. Natural English query: 'sweet dishes'
    results_en = db_service.search_menu_items_semantic(biz_id, query="sweet dishes")
    assert len(results_en) > 0
    names = [r["name"] for r in results_en]
    assert any("Gulab Jamun" in n for n in names)
    assert any("Rasmalai" in n for n in names)

    # 2. Hindi / Hinglish query: 'kuch meetha'
    results_hi = db_service.search_menu_items_semantic(biz_id, query="kuch meetha")
    assert len(results_hi) > 0
    names_hi = [r["name"] for r in results_hi]
    assert any("Gulab Jamun" in n for n in names_hi)

    # 3. Direct dish inquiry: 'rasmalai'
    results_exact = db_service.search_menu_items_semantic(biz_id, query="rasmalai")
    assert len(results_exact) > 0
    assert "Rasmalai (2 pcs)" in results_exact[0]["name"]
    assert results_exact[0]["price"] == 130.0


def test_semantic_concept_breads_and_beverages():
    """Verify semantic concept matching for Indian breads and beverages."""
    db_service = get_database_service()
    biz_id = "biz_spice_garden"
    db_service.upload_menu_items(biz_id, SAMPLE_MENU_ITEMS, replace=True)

    # Bread inquiry
    bread_results = db_service.search_menu_items_semantic(biz_id, query="what breads or rotis do you have")
    assert len(bread_results) > 0
    assert any("Naan" in r["name"] for r in bread_results)

    # Beverage inquiry
    drink_results = db_service.search_menu_items_semantic(biz_id, query="refreshing drink or lassi")
    assert len(drink_results) > 0
    assert any("Mango Lassi" in r["name"] for r in drink_results)


def test_semantic_dietary_and_budget_filtering():
    """Verify strict dietary filtering (veg/jain) and max budget constraints."""
    db_service = get_database_service()
    biz_id = "biz_spice_garden"
    db_service.upload_menu_items(biz_id, SAMPLE_MENU_ITEMS, replace=True)

    # 1. Vegetarian filter on curries (must exclude Butter Chicken)
    veg_results = db_service.search_menu_items_semantic(
        biz_id,
        query="curry",
        dietary_preference="vegetarian",
    )
    for it in veg_results:
        assert "vegetarian" in it["dietary_tags"]
        assert it["name"] != "Butter Chicken"

    # 2. Budget constraint (under ₹300)
    budget_results = db_service.search_menu_items_semantic(
        biz_id,
        query="curry gravy",
        max_budget=300.0,
    )
    for it in budget_results:
        assert it["price"] <= 300.0
    # Dal Makhani (₹280) should match; Paneer Butter Masala (₹340) and Butter Chicken (₹420) must be excluded
    matched_names = [it["name"] for it in budget_results]
    assert "Dal Makhani" in matched_names
    assert "Butter Chicken" not in matched_names
    assert "Paneer Butter Masala" not in matched_names

    # 3. Sweet dishes under ₹100
    sweet_budget = db_service.search_menu_items_semantic(
        biz_id,
        query="sweet dessert",
        max_budget=100.0,
    )
    sweet_names = [it["name"] for it in sweet_budget]
    assert "Gulab Jamun (2 pcs)" in sweet_names
    assert "Rasmalai (2 pcs)" not in sweet_names  # ₹130 > ₹100


# ==============================================================================
# 2. Tool Registry & Agent Execution Tests
# ==============================================================================

def test_query_menu_pricing_tool_execution():
    """Verify query_menu_pricing tool execution via ToolRegistry."""
    registry = get_tool_registry()
    db_service = get_database_service()
    biz_id = "biz_spice_garden"
    db_service.upload_menu_items(biz_id, SAMPLE_MENU_ITEMS, replace=True)

    biz_profile = db_service.get_business_profile(biz_id)
    assert biz_profile is not None

    # Execute tool for price inquiry
    result = registry.execute_tool(
        business_id=biz_id,
        business_config=biz_profile,
        tool_id="query_menu_pricing",
        input_data={"query": "how much is dal makhani"},
        confirmed=False,
    )

    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.success is True
    assert result.is_business_accepted is True
    assert "Dal Makhani" in result.message
    assert "₹280" in result.message
    assert result.data["found"] is True
    assert len(result.data["items"]) >= 1


def test_query_menu_pricing_non_existent_dish():
    """Verify tool gracefully informs caller when no dish matches without hallucinating."""
    registry = get_tool_registry()
    db_service = get_database_service()
    biz_id = "biz_spice_garden"
    db_service.upload_menu_items(biz_id, SAMPLE_MENU_ITEMS, replace=True)

    biz_profile = db_service.get_business_profile(biz_id)

    result = registry.execute_tool(
        business_id=biz_id,
        business_config=biz_profile,
        tool_id="query_menu_pricing",
        input_data={"query": "japanese sushi dragon roll"},
        confirmed=False,
    )

    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.data["found"] is False
    assert "currently do not have" in result.message.lower()


def test_query_menu_pricing_disabled_for_non_dining():
    """Verify clinic tenant cannot execute dining menu tool."""
    registry = get_tool_registry()
    db_service = get_database_service()
    clinic_profile = db_service.get_business_profile("biz_apex_dental")
    assert clinic_profile is not None

    result = registry.execute_tool(
        business_id="biz_apex_dental",
        business_config=clinic_profile,
        tool_id="query_menu_pricing",
        input_data={"query": "dal makhani"},
        confirmed=False,
    )

    assert result.status == ToolExecutionStatus.DISABLED
    assert result.success is False
    assert ("not enabled" in result.message.lower() or "only available" in result.message.lower())


# ==============================================================================
# 3. HTTP REST API Tests
# ==============================================================================

def test_api_menu_endpoints():
    """Verify REST API endpoints for menu get, upload, search, and delete."""
    client = TestClient(app)
    biz_id = "biz_spice_garden"

    token = create_access_token({
        "sub": biz_id,
        "role": ROLE_BUSINESS_OWNER,
        "email": "haveli.restaurant@gmail.com",
    })
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 1. Upload menu items via POST /api/businesses/{biz_id}/menu/upload
    upload_res = client.post(
        f"/api/businesses/{biz_id}/menu/upload",
        json={"items": SAMPLE_MENU_ITEMS, "replace": True},
        headers=auth_headers,
    )
    assert upload_res.status_code == 200
    upload_data = upload_res.json()
    assert upload_data["success"] is True
    assert upload_data["count"] == len(SAMPLE_MENU_ITEMS)

    # 2. Get menu items via GET /api/businesses/{biz_id}/menu
    get_res = client.get(f"/api/businesses/{biz_id}/menu")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["success"] is True
    assert get_data["count"] == len(SAMPLE_MENU_ITEMS)

    # 3. Semantic search via POST /api/businesses/{biz_id}/menu/search
    search_res = client.post(
        f"/api/businesses/{biz_id}/menu/search?query=sweet+dessert",
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["success"] is True
    assert search_data["count"] >= 1
    assert any("Gulab Jamun" in it["name"] for it in search_data["items"])

    # 4. Delete item via DELETE /api/businesses/{biz_id}/menu/{item_id}
    item_id = get_data["items"][0]["id"]
    del_res = client.delete(
        f"/api/businesses/{biz_id}/menu/{item_id}",
        headers=auth_headers,
    )
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Verify item count decreased by 1
    get_after_del = client.get(f"/api/businesses/{biz_id}/menu")
    assert get_after_del.json()["count"] == len(SAMPLE_MENU_ITEMS) - 1


# ==============================================================================
# 4. LangGraph Receptionist Agent Workflow Test
# ==============================================================================

def test_receptionist_workflow_executes_menu_pricing_tool():
    """
    End-to-end verification of LangGraph agent executing query_menu_pricing tool
    when a caller asks about restaurant dishes and prices.
    """
    from unittest.mock import MagicMock
    from backend.agent.graph import invoke_receptionist_workflow
    from backend.services.groq_service import GroqService
    from backend.database.seed_data import INITIAL_TOOLS

    db_service = get_database_service()
    biz_id = "biz_spice_garden"
    db_service.upload_menu_items(biz_id, SAMPLE_MENU_ITEMS, replace=True)
    biz_profile = db_service.get_business_profile(biz_id)

    # 1. First turn: LLM decides to call query_menu_pricing tool
    mock_tc = MagicMock()
    mock_tc.id = "call_menu_123"
    mock_tc.function.name = "query_menu_pricing"
    mock_tc.function.arguments = '{"query": "sweet dishes"}'

    first_turn_msg = MagicMock()
    first_turn_msg.content = ""
    first_turn_msg.tool_calls = [mock_tc]

    # 2. Second turn: After tool result, LLM returns grounded telephone response
    second_turn_msg = MagicMock()
    second_turn_msg.content = "We have warm Gulab Jamun for ₹90 and saffron Rasmalai for ₹130. Would you like to book a table?"
    second_turn_msg.tool_calls = None

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=first_turn_msg)]),
        MagicMock(choices=[MagicMock(message=second_turn_msg)]),
    ]
    mock_groq = GroqService(client=mock_client)

    result = invoke_receptionist_workflow(
        business_id=biz_id,
        business_config=biz_profile,
        enabled_tools=INITIAL_TOOLS,
        messages=[{"role": "user", "content": "What sweet dishes do you have and what are their prices?"}],
        groq_service=mock_groq,
    )

    assert result["success"] is True
    assert "query_menu_pricing" in (result.get("tools_called") or [])
    assert "Gulab Jamun" in result["response_content"]
    assert "₹90" in result["response_content"]
    assert "Rasmalai" in result["response_content"]
