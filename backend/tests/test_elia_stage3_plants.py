from __future__ import annotations

import json
from copy import deepcopy
import pytest
from shapely.geometry import Polygon

from app.components.elia_engine.plants import (
    get_plant_catalogue,
    get_plant_entry,
    filter_plant_catalogue,
    evaluate_plant_suitability,
    propose_plant_alternatives,
    validate_accepted_alternatives,
)
from app.components.elia_engine.feasibility import (
    CanonicalProjectGeometry,
    extract_canonical_geometry,
)
from app.components.elia_engine.vegetation import place_vegetation
from app.components.elia_engine.requirements import normalize_requirements
from app.components.elia_engine.schemas import (
    PlantAlternativeProposal,
    AcceptedPlantAlternative,
    PlantAlternativeAction,
)


def _make_sample_master(land_coords=None, house_coords=None, with_balcony=True, with_roof=True):
    land = land_coords or [[0.0, 0.0], [25.0, 0.0], [25.0, 20.0], [0.0, 20.0], [0.0, 0.0]]
    house = house_coords or [[5.0, 5.0], [15.0, 5.0], [15.0, 15.0], [5.0, 15.0], [5.0, 5.0]]
    balconies = []
    if with_balcony:
        balconies.append({
            "id": "balcony_f2_01",
            "json_id": "balcony_f2_01",
            "type": "balcony",
            "floor_id": "floor_2",
            "elevation_m": 3.2,
            "coordinates": [[[5.0, 5.0], [8.0, 5.0], [8.0, 7.0], [5.0, 7.0], [5.0, 5.0]]],
            "structural_certified": False,
        })
    roofs = []
    if with_roof:
        roofs.append({
            "id": "terrace_roof_01",
            "json_id": "terrace_roof_01",
            "type": "roof",
            "roof_type": "flat",
            "elevation_m": 6.4,
            "coordinates": [[[5.0, 5.0], [12.0, 5.0], [12.0, 12.0], [5.0, 12.0], [5.0, 5.0]]],
            "live_load_certified": False,
        })
    walls = [
        {
            "id": "wall_east_01",
            "json_id": "wall_east_01",
            "type": "wall",
            "orientation": "east",
            "height_m": 6.0,
            "length_m": 10.0,
        }
    ]
    return {
        "project_id": "p_stage3_test",
        "units": "m",
        "land_boundary_polygon": land,
        "house_exterior_polygon": house,
        "location": {"latitude": 6.9271, "longitude": 79.8612},
        "north_angle": 0.0,
        "road_facing": "south",
        "road_access_edge": 0,
        "balconies": balconies,
        "terraces": roofs,
        "walls": walls,
    }


def _make_narrow_master():
    # Long narrow strip: 1m wide exterior clearance on sides
    land = [[0.0, 0.0], [14.0, 0.0], [14.0, 20.0], [0.0, 20.0], [0.0, 0.0]]
    house = [[1.0, 1.0], [13.0, 1.0], [13.0, 19.0], [1.0, 19.0], [1.0, 1.0]]
    return {
        "project_id": "p_stage3_narrow",
        "units": "m",
        "land_boundary_polygon": land,
        "house_exterior_polygon": house,
        "location": {"latitude": 6.9271, "longitude": 79.8612},
        "north_angle": 0.0,
        "road_facing": "south",
        "road_access_edge": 0,
        "balconies": [],
        "terraces": [],
        "walls": [],
    }


# =========================================================================
# 1. CATALOGUE STRUCTURE & DATA TRUTHFULNESS TESTS
# =========================================================================

def test_catalogue_unique_stable_ids_and_ranges():
    cat = get_plant_catalogue()
    assert "catalogue_version" in cat
    assert "entries" in cat
    entries = cat["entries"]
    assert len(entries) >= 15

    seen_ids = set()
    for entry in entries:
        pid = entry.get("vegetation_id")
        assert pid is not None and len(pid.strip()) > 0
        assert pid not in seen_ids, f"Duplicate vegetation_id found: {pid}"
        seen_ids.add(pid)

        # Check finite numeric ranges if present
        for num_field in ("mature_height_m", "canopy_radius_m", "root_clearance_m", "minimum_spacing_m"):
            val = entry.get(num_field)
            if val is not None:
                assert isinstance(val, (int, float))
                assert val > 0, f"{pid}.{num_field} must be positive"


def test_catalogue_unverified_records_remain_unverified():
    generic_tree = get_plant_entry("shade_tree")
    assert generic_tree is not None
    assert generic_tree.get("verified_species_data") is False
    assert generic_tree.get("mature_height_m") is None
    assert generic_tree.get("canopy_radius_m") is None
    assert generic_tree.get("sun_requirement") == "site_analysis_required"


def test_catalogue_verified_records_have_tracked_sources():
    araliya = get_plant_entry("plumeria_obtusa")
    assert araliya is not None
    assert araliya.get("verified_species_data") is True
    assert araliya.get("source_reference") is not None
    assert "Flora of Ceylon" in araliya["source_reference"] or "Botanic Gardens" in araliya["source_reference"]
    assert araliya.get("canopy_radius_m") == 1.8


def test_catalogue_preserves_cultivar_identity():
    ixora = get_plant_entry("ixora_sri_lanka")
    assert ixora is not None
    assert ixora.get("scientific_name") == "Ixora cv. 'Sri Lanka'"
    assert "cultivar" in ixora or "cv." in ixora.get("scientific_name", "")


# =========================================================================
# 2. PLANT SUITABILITY EVALUATION TESTS
# =========================================================================

def test_suitable_ground_plant_with_sufficient_space():
    master = _make_sample_master()
    geom = extract_canonical_geometry(master, source_revision=1)
    assessment = evaluate_plant_suitability(
        plant="plumeria_obtusa",
        geom=geom,
        placement_type="ground",
    )
    assert assessment.overall_status == "feasible"
    assert assessment.spatial_fit == "feasible"
    assert assessment.plant_suitability == "feasible"
    assert "satisfy evaluated constraints" in assessment.explanation


def test_oversized_canopy_in_narrow_parcel_is_infeasible():
    master = _make_narrow_master()
    geom = extract_canonical_geometry(master, source_revision=1)
    # Lagerstroemia speciosa requires 5.0m canopy radius (10.0m diameter)
    assessment = evaluate_plant_suitability(
        plant="lagerstroemia_speciosa",
        geom=geom,
        placement_type="ground",
    )
    assert assessment.overall_status == "infeasible"
    assert assessment.spatial_fit == "infeasible"
    assert "INSUFFICIENT_CANOPY_CLEARANCE" in assessment.reason_codes
    assert len(assessment.suggested_alternatives) > 0


def test_unsupported_container_species_fails():
    master = _make_sample_master()
    geom = extract_canonical_geometry(master, source_revision=1)
    # Lagerstroemia speciosa is a large deep-rooted tree with container_suitability = False
    assessment = evaluate_plant_suitability(
        plant="lagerstroemia_speciosa",
        geom=geom,
        placement_type="container",
    )
    assert assessment.overall_status == "infeasible"
    assert assessment.surface_eligibility == "infeasible"
    assert "UNSUPPORTED_CONTAINER_SPECIES" in assessment.reason_codes


def test_balcony_plant_with_unverified_structural_evidence_requires_review():
    master = _make_sample_master(with_balcony=True)
    geom = extract_canonical_geometry(master, source_revision=1)
    # Nephrolepis exaltata is suitable for planters, but structural live load certificate is absent
    assessment = evaluate_plant_suitability(
        plant="nephrolepis_exaltata",
        geom=geom,
        placement_type="balcony",
        surface_id="balcony_f2_01",
    )
    assert assessment.overall_status == "review_required"
    assert assessment.surface_eligibility == "review_required"
    assert "BALCONY_STRUCTURAL_LOAD_UNVERIFIED" in assessment.reason_codes
    assert "balcony:structural_load_certificate" in assessment.missing_evidence


def test_balcony_plant_on_project_without_balconies_is_not_applicable():
    master = _make_sample_master(with_balcony=False)
    geom = extract_canonical_geometry(master, source_revision=1)
    assessment = evaluate_plant_suitability(
        plant="nephrolepis_exaltata",
        geom=geom,
        placement_type="balcony",
    )
    assert assessment.overall_status == "not_applicable"
    assert assessment.surface_eligibility == "not_applicable"
    assert "NO_AUTHORITATIVE_BALCONIES" in assessment.reason_codes


def test_wall_climber_habit_enforcement():
    master = _make_sample_master()
    # Add an exterior wall facade
    master["walls"].append({
        "id": "facade_wall_north",
        "json_id": "facade_wall_north",
        "type": "wall",
        "length_m": 10.0,
    })
    geom = extract_canonical_geometry(master, source_revision=1)

    # Areca palm is not a climber
    areca_assessment = evaluate_plant_suitability(
        plant="areca_catechu",
        geom=geom,
        placement_type="wall",
    )
    assert areca_assessment.overall_status == "infeasible"
    assert "SPECIES_LACKS_CLIMBING_HABIT" in areca_assessment.reason_codes

    # Bougainvillea glabra has vertical climbing habit
    boug_assessment = evaluate_plant_suitability(
        plant="bougainvillea_glabra",
        geom=geom,
        placement_type="wall",
    )
    assert boug_assessment.overall_status == "feasible"
    assert boug_assessment.surface_eligibility == "feasible"


def test_non_greeny_users_can_select_plants():
    # Minimalistic or Modern concept allows plant selection
    reqs = {
        "design_style": "minimalistic",
        "preferred_plant_ids": ["areca_catechu"],
    }
    master = _make_sample_master()
    norm = normalize_requirements(reqs, master, "m")
    assert "areca_catechu" in norm["preferred_plant_ids"]


# =========================================================================
# 3. GREENY ALTERNATIVES PROPOSAL & ACCEPTANCE TESTS
# =========================================================================

def test_alternatives_proposal_does_not_mutate_original_intent():
    master = _make_narrow_master()
    geom = extract_canonical_geometry(master, source_revision=1)

    proposals = propose_plant_alternatives(
        original_request="plant:lagerstroemia_speciosa",
        failed_reason="Canopy radius 5.0m exceeds exterior clearance.",
        geom=geom,
        original_plant_id="lagerstroemia_speciosa",
        placement_type="ground",
        catalogue_version="2.1",
    )

    assert len(proposals) > 0
    first_prop = proposals[0]
    assert first_prop.status == "proposed"
    assert first_prop.original_request == "plant:lagerstroemia_speciosa"
    assert first_prop.alternative_plant_id != "lagerstroemia_speciosa"
    # Ensure compact tree proposal is smaller than original
    assert first_prop.alternative_category in {"small_tree", "shrub", "container"}


def test_server_side_validation_of_accepted_alternatives():
    master = _make_sample_master(with_balcony=True)
    geom = extract_canonical_geometry(master, source_revision=1)

    raw_actions = [
        {
            "original_request": "plant:lagerstroemia_speciosa",
            "alternative_plant_id": "plumeria_obtusa",
            "placement_type": "ground",
            "quantity": 2,
            "decision": "accept",
        },
        {
            # Fabricated non-existent plant
            "original_request": "plant:fake_tree",
            "alternative_plant_id": "non_existent_species_999",
            "placement_type": "ground",
            "quantity": 1,
            "decision": "accept",
        },
        {
            # Non-existent balcony surface ID
            "original_request": "plant:boug",
            "alternative_plant_id": "nephrolepis_exaltata",
            "placement_type": "balcony",
            "surface_id": "phantom_balcony_99",
            "quantity": 1,
            "decision": "accept",
        },
    ]

    validated = validate_accepted_alternatives(raw_actions, geom)
    assert len(validated) == 1
    val = validated[0]
    assert val.alternative_plant_id == "plumeria_obtusa"
    assert val.quantity == 2
    assert val.acceptance_status == "accepted"


def test_accepted_alternatives_roundtrip_in_requirements():
    master = _make_sample_master()
    reqs = {
        "landscape": {
            "accepted_plant_alternatives": [
                {
                    "original_request": "plant:lagerstroemia_speciosa",
                    "alternative_plant_id": "plumeria_obtusa",
                    "placement_type": "ground",
                    "quantity": 1,
                }
            ],
            "rejected_plant_alternatives": ["nephrolepis_exaltata"],
        }
    }
    norm = normalize_requirements(reqs, master, "m")
    assert len(norm["accepted_plant_alternatives"]) == 1
    assert norm["accepted_plant_alternatives"][0]["alternative_plant_id"] == "plumeria_obtusa"
    assert "nephrolepis_exaltata" in norm["rejected_plant_alternatives"]


def test_accepted_alternatives_drive_vegetation_placement():
    master = _make_sample_master()
    context_geom = extract_canonical_geometry(master, source_revision=1)

    reqs = {
        "design_style": "greeny",
        "landscape": {
            "greenery_density": "high",
            "trees_required": True,
            "accepted_plant_alternatives": [
                {
                    "original_request": "plant:lagerstroemia_speciosa",
                    "alternative_plant_id": "plumeria_obtusa",
                    "placement_type": "ground",
                    "quantity": 1,
                }
            ],
        },
    }
    norm = normalize_requirements(reqs, master, "m")

    from app.components.elia_engine.rule_repository import elia_rules, vegetation_catalog
    rules = elia_rules()["vegetation"]
    catalog = vegetation_catalog()["entries"]

    land = context_geom.land
    house = context_geom.house
    residual = context_geom.unoccupied_ground
    result = place_vegetation(
        residual=residual,
        land=land,
        blocked=house,
        requirements=norm,
        shadows=[],
    )

    assert len(result.nodes) > 0
    # Plumeria obtusa must be among the placed nodes due to priority boost
    placed_ids = {n.get("plant_id") for n in result.nodes}
    assert "plumeria_obtusa" in placed_ids
