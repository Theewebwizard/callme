"""
Unit and integration tests for Clinic / Medical domain tool parity.
Tests MedicalTreatment model, TreatmentRepository semantic search,
query_treatment_pricing tool handler, BuiltinClinicTreatmentsAdapter,
and service methods for clinical fee catalog management.
"""

import pytest
from datetime import datetime

from backend.database.models import MedicalTreatment
from backend.database.repositories.treatment_repo import TreatmentRepository, rank_treatments_semantic
from backend.database.service import get_database_service
from backend.tools.definitions import QueryTreatmentPricingInput, CheckAppointmentAvailabilityInput, CreateAppointmentInput
from backend.tools.implementations.healthcare import (
    handle_query_treatment_pricing,
    handle_check_appointment_availability,
    handle_create_appointment,
)
from backend.tools.registry import get_tool_registry
from backend.capabilities.specs import get_capability_spec
from backend.integrations.resolver import resolve_tool_adapter


def test_treatment_semantic_ranking():
    """Verify semantic ranking engine accurately matches procedures, symptoms, categories, and doctors."""
    mock_treatments = [
        {
            "id": "treat_1",
            "name": "Comprehensive Dental Examination & OPG X-Ray",
            "category": "Consultation",
            "base_fee": 500.0,
            "fee_range_max": 500.0,
            "currency": "INR",
            "duration_minutes": 30,
            "practitioner_type": "General Dentist",
            "description": "Full clinical oral cavity examination and diagnostic digital OPG X-ray.",
            "preparation_instructions": "Bring any prior dental records.",
            "is_available": True,
        },
        {
            "id": "treat_2",
            "name": "Ultrasonic Teeth Scaling & Polishing",
            "category": "Preventive",
            "base_fee": 1200.0,
            "fee_range_max": 1500.0,
            "currency": "INR",
            "duration_minutes": 45,
            "practitioner_type": "Dental Hygienist",
            "description": "Deep tartar and calculus removal using ultrasonic scaler.",
            "preparation_instructions": "Avoid staining foods for 2 hours.",
            "is_available": True,
        },
        {
            "id": "treat_3",
            "name": "Single-Sitting Root Canal Therapy (RCT)",
            "category": "Restoration",
            "base_fee": 4500.0,
            "fee_range_max": 6500.0,
            "currency": "INR",
            "duration_minutes": 60,
            "practitioner_type": "Endodontist",
            "description": "Microscopic rotary root canal therapy for infected teeth.",
            "preparation_instructions": "Take a light meal before the procedure.",
            "is_available": True,
        },
        {
            "id": "treat_4",
            "name": "Invisible Clear Aligners (Full Course)",
            "category": "Orthodontics",
            "base_fee": 45000.0,
            "fee_range_max": 75000.0,
            "currency": "INR",
            "duration_minutes": 45,
            "practitioner_type": "Orthodontist",
            "description": "Custom transparent aligners to straighten teeth and correct bite.",
            "preparation_instructions": "Includes 3D intraoral scan.",
            "is_available": True,
        },
    ]

    # Test 1: Query for root canal via symptom / abbreviation 'rct'
    ranked1 = rank_treatments_semantic(mock_treatments, query="rct tooth pain")
    assert len(ranked1) > 0
    assert "Root Canal" in ranked1[0]["name"]

    # Test 2: Query for cleaning / tartar
    ranked2 = rank_treatments_semantic(mock_treatments, query="teeth cleaning and tartar removal")
    assert len(ranked2) > 0
    assert "Scaling" in ranked2[0]["name"]

    # Test 3: Query for braces / aligners
    ranked3 = rank_treatments_semantic(mock_treatments, query="braces teeth straightening")
    assert len(ranked3) > 0
    assert "Aligners" in ranked3[0]["name"]

    # Test 4: Budget constraint (under 2,000)
    ranked4 = rank_treatments_semantic(mock_treatments, query="checkup or cleaning", max_budget=2000.0)
    assert len(ranked4) > 0
    for t in ranked4:
        assert t["base_fee"] <= 2000.0

    # Test 5: Specialist doctor filter
    ranked5 = rank_treatments_semantic(mock_treatments, query="procedure", practitioner_type="Endodontist")
    assert len(ranked5) > 0
    assert ranked5[0]["practitioner_type"] == "Endodontist"


def test_query_treatment_pricing_tool_execution():
    """Verify handle_query_treatment_pricing queries clinic procedures and formats natural language response."""
    biz_config = {
        "id": "biz_apex_dental",
        "name": "Apex Dental & Orthodontics",
        "execution_mode": "mock",
    }

    input_payload = QueryTreatmentPricingInput(
        query="how much for root canal treatment?",
    )

    result = handle_query_treatment_pricing(input_payload, biz_config)
    assert result.success is True
    assert result.is_business_accepted is True
    assert result.data["count"] > 0
    assert "Root Canal" in result.message
    assert "Endodontist" in result.message


def test_clinic_tools_and_capabilities_registered():
    """Verify all clinic tools are registered in ToolRegistry and have capability specifications."""
    reg = get_tool_registry()

    for tool_id in ["query_treatment_pricing", "check_appointment_availability", "create_appointment"]:
        tool = reg.get_tool(tool_id)
        assert tool is not None, f"Tool {tool_id} must be registered"
        assert "clinic" in tool.allowed_canonical_industries
        assert tool.category.value == "Healthcare & Services"

    # Verify capability specifications
    for tool_id in ["query_treatment_pricing", "check_appointment_availability", "create_appointment"]:
        spec = get_capability_spec(tool_id)
        assert spec is not None, f"Capability spec for {tool_id} must exist"
        assert "clinic" in spec.allowed_canonical_industries


def test_builtin_clinic_treatments_adapter():
    """Verify BuiltinClinicTreatmentsAdapter resolves and passes readiness assessments."""
    adapter = resolve_tool_adapter("biz_apex_dental", "query_treatment_pricing")
    assert adapter is not None

    report = adapter.assess_readiness()
    assert report.is_ready is True
    assert len(report.checks) >= 3

    # Verify discovered resources
    resources = adapter.discover_resources()
    assert len(resources) >= 6


def test_database_service_treatment_methods():
    """Verify DatabaseService provides full tenant-scoped treatment CRUD and semantic search."""
    db_service = get_database_service()
    treatments = db_service.list_treatments("biz_apex_dental")
    assert len(treatments) >= 6

    # Test semantic search through service
    search_res = db_service.search_treatments_semantic(
        business_id="biz_apex_dental",
        query="whitening",
    )
    assert len(search_res) > 0
    assert "Whitening" in search_res[0]["name"]
