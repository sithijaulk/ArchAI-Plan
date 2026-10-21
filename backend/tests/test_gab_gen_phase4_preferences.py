import pytest
from shapely.geometry import Polygon

from app.components.gab_gen.schemas import (
    ClientRequirementsInput,
    RoomRequirement,
    RoomAdjacencyRequirement,
    AdjacencyRelationshipType,
    FloorAssignmentType,
    PreferenceEvaluationStatus,
    RoofPreference,
    RoofType,
    ManualSurveyExtractionRequest,
    SurveyEdgeInput,
)
from app.components.gab_gen.input.validator import reconcile_and_validate_requirements
from app.components.gab_gen.space_allocation.allocator import RuleBasedSpaceAllocationProvider
from app.components.gab_gen.blueprint.generator import generate_blueprint_floors
from app.components.gab_gen.validation.preference_evaluator import evaluate_architectural_preferences
from app.components.gab_gen.service import GabGenService


def create_mock_survey_request(north_origin: str = "ocr_arrow") -> ManualSurveyExtractionRequest:
    edges = [
        SurveyEdgeInput(edge_id="E01", distance={"value": 20.0, "unit": "m"}, bearing={"raw": "090°", "normalized_degrees": 90.0}, edge_type="road_front"),
        SurveyEdgeInput(edge_id="E02", distance={"value": 15.0, "unit": "m"}, bearing={"raw": "180°", "normalized_degrees": 180.0}, edge_type="side_right"),
        SurveyEdgeInput(edge_id="E03", distance={"value": 20.0, "unit": "m"}, bearing={"raw": "270°", "normalized_degrees": 270.0}, edge_type="rear"),
        SurveyEdgeInput(edge_id="E04", distance={"value": 15.0, "unit": "m"}, bearing={"raw": "000°", "normalized_degrees": 0.0}, edge_type="side_left"),
    ]
    return ManualSurveyExtractionRequest(
        edges=edges,
        north_angle=0.0,
        north_angle_origin=north_origin,
        drawing_scale="1:100",
        drawing_scale_origin="ocr_text",
        verified_by_user=True
    )


def test_requirements_duplicate_room_ids_rejected():
    """Verify that duplicate room requirement IDs are rejected by the validator."""
    req = ClientRequirementsInput(
        declared_land_extent=10.0,
        rooms=[
            RoomRequirement(id="ROOM_DUP", type="living_room", quantity=1),
            RoomRequirement(id="ROOM_DUP", type="bedroom", quantity=1),
        ]
    )
    res = reconcile_and_validate_requirements(req)
    assert res["valid"] is False
    assert any("Duplicate room requirement ID 'ROOM_DUP'" in err for err in res["errors"])


def test_requirements_dimension_minimum_exceeds_preferred_rejected():
    """Verify that room requirements with minimum width > preferred width are rejected."""
    req = ClientRequirementsInput(
        declared_land_extent=10.0,
        rooms=[
            RoomRequirement(
                id="RM_01",
                type="bedroom",
                quantity=1,
                minimum_width_m=4.5,
                preferred_width_m=3.0  # Invalid: min > preferred
            )
        ]
    )
    res = reconcile_and_validate_requirements(req)
    assert res["valid"] is False
    assert any("minimum width" in err for err in res["errors"])


def test_requirements_adjacency_validation():
    """Verify adjacency references, duplicate detection, and self-adjacency rejection."""
    # 1. Unknown room reference
    req_unknown = ClientRequirementsInput(
        declared_land_extent=10.0,
        rooms=[RoomRequirement(id="RM_01", type="living_room", quantity=1)],
        adjacencies=[
            RoomAdjacencyRequirement(
                adjacency_id="ADJ_01",
                source_room_id="RM_01",
                target_room_id="RM_NON_EXISTENT",
                relationship=AdjacencyRelationshipType.PREFER_NEAR
            )
        ]
    )
    res_unknown = reconcile_and_validate_requirements(req_unknown)
    assert res_unknown["valid"] is False
    assert any("unknown target room ID" in err for err in res_unknown["errors"])

    # 2. Self adjacency
    req_self = ClientRequirementsInput(
        declared_land_extent=10.0,
        rooms=[RoomRequirement(id="RM_01", type="living_room", quantity=1)],
        adjacencies=[
            RoomAdjacencyRequirement(
                adjacency_id="ADJ_01",
                source_room_id="RM_01",
                target_room_id="RM_01",
                relationship=AdjacencyRelationshipType.PREFER_NEAR
            )
        ]
    )
    res_self = reconcile_and_validate_requirements(req_self)
    assert res_self["valid"] is False
    assert any("self-adjacency" in err for err in res_self["errors"])


def test_allocator_respects_floor_assignment_and_dimensions():
    """Verify rule-based space allocator respects floor assignments and dimensions."""
    allocator = RuleBasedSpaceAllocationProvider()
    req = ClientRequirementsInput(
        declared_land_extent=15.0,
        storey_count=2,
        rooms=[
            RoomRequirement(id="RM_LIV", type="living_room", quantity=1, preferred_min_area=20.0, floor_preference=0),
            RoomRequirement(id="RM_KIT", type="kitchen", quantity=1, preferred_min_area=12.0, floor_preference=0),
            RoomRequirement(id="RM_BED", type="bedroom", quantity=1, preferred_min_area=14.0, floor_preference=1),
        ]
    )
    alloc_res = allocator.allocate_space(buildable_area=150.0, requirements=req)
    assert alloc_res["feasible"] is True
    floors = alloc_res["floors"]
    assert len(floors) == 2

    # Verify ground floor has Living and Kitchen
    gf_types = {r["type"] for r in floors[0]["rooms"]}
    assert "living_room" in gf_types
    assert "kitchen" in gf_types
    assert "staircase" in gf_types

    # Verify first floor has Bedroom
    ff_types = {r["type"] for r in floors[1]["rooms"]}
    assert "bedroom" in ff_types
    assert "staircase" in ff_types


def test_preference_evaluator_room_adjacency_and_fulfillment():
    """Verify preference evaluator evaluates shared boundary and distance accurately."""
    # Synthetic 20x15 buildable footprint
    buildable_poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])
    allocator = RuleBasedSpaceAllocationProvider()
    req = ClientRequirementsInput(
        declared_land_extent=15.0,
        storey_count=1,
        rooms=[
            RoomRequirement(id="REQ_LIV", type="living_room", quantity=1, preferred_min_area=25.0),
            RoomRequirement(id="REQ_DIN", type="dining_area", quantity=1, preferred_min_area=15.0),
        ],
        adjacencies=[
            RoomAdjacencyRequirement(
                adjacency_id="ADJ_LIV_DIN",
                source_room_id="REQ_LIV",
                target_room_id="REQ_DIN",
                relationship=AdjacencyRelationshipType.SHARED_BOUNDARY,
                is_hard_constraint=False
            )
        ]
    )
    alloc_res = allocator.allocate_space(buildable_area=200.0, requirements=req)
    blueprint_floors = generate_blueprint_floors(buildable_poly, alloc_res["floors"])

    eval_results = evaluate_architectural_preferences(
        requirements=req,
        floors=blueprint_floors,
        survey_request=create_mock_survey_request(),
        buildable_poly=buildable_poly
    )

    # Room fulfillment check
    liv_fulfillment = next((p for p in eval_results if p.preference_id == "PREF_ROOM_REQ_LIV"), None)
    assert liv_fulfillment is not None
    assert liv_fulfillment.status == PreferenceEvaluationStatus.SATISFIED

    # Adjacency check
    adj_eval = next((p for p in eval_results if p.preference_id == "PREF_ADJ_ADJ_LIV_DIN"), None)
    assert adj_eval is not None
    assert adj_eval.status == PreferenceEvaluationStatus.SATISFIED


def test_preference_evaluator_unknown_north_orientation_not_falsely_satisfied():
    """Verify that unknown North direction evaluates entrance orientation as NOT_EVALUABLE rather than SATISFIED."""
    buildable_poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])
    req = ClientRequirementsInput(
        declared_land_extent=15.0,
        storey_count=1,
        preferred_entrance_orientation="north",
        rooms=[RoomRequirement(id="REQ_LIV", type="living_room", quantity=1)]
    )
    allocator = RuleBasedSpaceAllocationProvider()
    alloc_res = allocator.allocate_space(buildable_area=200.0, requirements=req)
    blueprint_floors = generate_blueprint_floors(buildable_poly, alloc_res["floors"])

    # Survey with UNVERIFIED North
    survey_unknown_north = create_mock_survey_request(north_origin="default_unknown")

    eval_results = evaluate_architectural_preferences(
        requirements=req,
        floors=blueprint_floors,
        survey_request=survey_unknown_north,
        buildable_poly=buildable_poly
    )

    entrance_eval = next((p for p in eval_results if p.preference_id == "PREF_ENTRANCE_ORIENTATION"), None)
    assert entrance_eval is not None
    # MUST NOT be marked SATISFIED
    assert entrance_eval.status == PreferenceEvaluationStatus.NOT_EVALUABLE
    assert "unverified" in entrance_eval.explanation.lower()


def test_full_service_pipeline_phase4_end_to_end():
    """Verify full GAB-Gen service pipeline execution with Phase 4 preferences persisted in Master JSON."""
    service = GabGenService()
    survey = create_mock_survey_request(north_origin="ocr_arrow")
    req = ClientRequirementsInput(
        declared_land_extent=15.0,
        storey_count=2,
        parking_capacity=1,
        roof_preference=RoofPreference(roof_type=RoofType.GABLE, pitch_angle_deg=20.0),
        rooms=[
            RoomRequirement(id="REQ_LIV", type="living_room", quantity=1, floor_preference=0),
            RoomRequirement(id="REQ_KIT", type="kitchen", quantity=1, floor_preference=0),
            RoomRequirement(id="REQ_BED1", type="master_bedroom", quantity=1, floor_preference=1),
            RoomRequirement(id="REQ_BED2", type="bedroom", quantity=1, floor_preference=1),
        ],
        adjacencies=[
            RoomAdjacencyRequirement(
                adjacency_id="ADJ_LIV_KIT",
                source_room_id="REQ_LIV",
                target_room_id="REQ_KIT",
                relationship=AdjacencyRelationshipType.NEAR
            )
        ]
    )

    output = service.run_pipeline(
        project_id="PROJ_P4_E2E",
        project_name="Phase 4 End-to-End Test Residence",
        survey_request=survey,
        requirements=req,
        allow_research_test=True
    )

    assert output.status in ("completed", "needs_verification")
    assert output.validation.preference_evaluations is not None
    assert len(output.validation.preference_evaluations) > 0

    # Master JSON checks
    mj = output.master_json
    assert "client_requirements" in mj
    assert "adjacencies" in mj["client_requirements"]
    assert len(mj["client_requirements"]["adjacencies"]) == 1
    assert mj["client_requirements"]["adjacencies"][0]["adjacency_id"] == "ADJ_LIV_KIT"

    # Roof reflection
    assert mj["roof_geometry"]["roof_type"] == "gable"

    # Multi-floor staircase validation
    assert len(mj["floor_plan"]["floors"]) == 2
    f0_types = [r["type"] for r in mj["floor_plan"]["floors"][0]["rooms"]]
    f1_types = [r["type"] for r in mj["floor_plan"]["floors"][1]["rooms"]]
    assert "staircase" in f0_types
    assert "staircase" in f1_types
