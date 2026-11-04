"""
Unit and integration tests for Hotel & Hospitality tool parity with Restaurant domain.
Tests RoomType model, RoomTypeRepository semantic search, query_room_pricing tool,
and API routes for room catalog management.
"""

import pytest
from datetime import datetime, date

from backend.database.models import RoomType
from backend.database.repositories.room_repo import RoomTypeRepository, rank_room_types_semantic
from backend.database.service import get_database_service
from backend.tools.definitions import QueryRoomPricingInput, CheckRoomAvailabilityInput, CreateRoomBookingInput
from backend.tools.implementations.hospitality import (
    handle_query_room_pricing,
    handle_check_room_availability,
    handle_create_room_booking,
)
from backend.tools.registry import get_tool_registry
from backend.capabilities.specs import get_capability_spec


def test_room_type_model_and_semantic_ranking():
    """Verify semantic ranking engine accurately identifies category, bed type, and amenities."""
    mock_rooms = [
        {
            "name": "Deluxe King (Garden View)",
            "category": "Rooms",
            "base_price": 6500.0,
            "bed_type": "1 King Bed",
            "max_occupancy": 3,
            "amenities": ["Garden View", "Private Balcony", "High-Speed Wi-Fi"],
            "inclusions": ["Complimentary Buffet Breakfast"],
            "is_available": True,
        },
        {
            "name": "Deluxe Twin (Garden View)",
            "category": "Rooms",
            "base_price": 6500.0,
            "bed_type": "2 Twin Beds",
            "max_occupancy": 3,
            "amenities": ["Garden View", "Work Desk", "High-Speed Wi-Fi"],
            "inclusions": ["Complimentary Buffet Breakfast"],
            "is_available": True,
        },
        {
            "name": "Executive Oceanfront Suite",
            "category": "Suites",
            "base_price": 14000.0,
            "bed_type": "1 King Bed",
            "max_occupancy": 4,
            "amenities": ["Panoramic Ocean View", "Spacious Balcony", "Deep Soaking Bathtub"],
            "inclusions": ["Executive Lounge Access", "Complimentary Buffet Breakfast"],
            "is_available": True,
        },
        {
            "name": "Private Pool Beach Villa",
            "category": "Villas",
            "base_price": 45000.0,
            "bed_type": "2 King Beds",
            "max_occupancy": 8,
            "amenities": ["Direct Beach Access", "Private Infinity Plunge Pool"],
            "inclusions": ["Roundtrip Luxury Airport Transfer"],
            "is_available": True,
        },
    ]

    # Test 1: Query for ocean view suite
    ranked1 = rank_room_types_semantic(mock_rooms, query="ocean view suite")
    assert len(ranked1) > 0
    assert ranked1[0]["name"] == "Executive Oceanfront Suite"

    # Test 2: Query for two beds
    ranked2 = rank_room_types_semantic(mock_rooms, query="two beds room")
    assert len(ranked2) > 0
    assert ranked2[0]["name"] == "Deluxe Twin (Garden View)"

    # Test 3: Budget constraint
    ranked3 = rank_room_types_semantic(mock_rooms, query="room", max_budget_per_night=10000.0)
    for r in ranked3:
        assert r["base_price"] <= 10000.0


def test_query_room_pricing_tool_execution():
    """Verify handle_query_room_pricing returns calculated stay pricing and natural language summary."""
    biz_config = {
        "id": "biz_grand_hotel",
        "name": "The Grand Azure Resort & Suites",
        "execution_mode": "mock",
    }

    input_payload = QueryRoomPricingInput(
        query="oceanfront suite with breakfast",
        check_in_date="2026-12-01",
        check_out_date="2026-12-04",
    )

    result = handle_query_room_pricing(input_payload, biz_config)
    assert result.success is True
    assert result.is_business_accepted is True
    assert "3 night" in result.message
    assert result.data["count"] > 0
    assert result.data["nights"] == 3


def test_hotel_tools_registered():
    """Verify all 3 core hotel tools are registered with canonical sector allowlists."""
    reg = get_tool_registry()

    for tool_id in ["query_room_pricing", "check_room_availability", "create_room_booking"]:
        tool = reg.get_tool(tool_id)
        assert tool is not None, f"Tool {tool_id} must be registered"
        assert "hotel" in tool.allowed_canonical_industries
        assert tool.category.value == "Hospitality & Lodging"

    # Verify specs exist
    for tool_id in ["query_room_pricing", "check_room_availability", "create_room_booking"]:
        spec = get_capability_spec(tool_id)
        assert spec is not None
        assert "hotel" in spec.allowed_canonical_industries
