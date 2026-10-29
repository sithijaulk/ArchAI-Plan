"""
Comprehensive Stage 1 Preference Contract Tests for Component 4 - ELIA Engine.

Covers:
- Strict validation across all 11 preference groups (A-K)
- Rejection of invalid types and non-numeric counts
- Contradictory requirement detection (e.g. 0 vehicles or parking disabled with garage required)
- Canonical concept style normalization ("minimalist" -> "minimalistic", "contemporary" -> "modern")
- Child field omission when parent feature is disabled
- Botanical catalogue validation against authoritative vegetation species
- Explicit tracking and reporting of unsupported generation features
- Persistence in Master JSON root and processing blocks
"""
import pytest
from app.components.elia_engine.exceptions import ELIAError
from app.components.elia_engine.schemas import ELIARequirements
from app.components.elia_engine.requirements import normalize_requirements
from app.components.elia_engine.service import run_elia
from app.components.elia_engine.output import build_updated_master


def _minimal_valid_master() -> dict:
    return {
        "units": "m",
        "location": {"latitude": 6.9271, "longitude": 79.8612},
        "land_info": {
            "boundary_polygon": [[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 30.0], [0.0, 0.0]],
            "road_facing": "south",
            "calculated_north_bearing": 0.0,
        },
        "house_exterior_polygon": [[10.0, 8.0], [25.0, 8.0], [25.0, 20.0], [10.0, 20.0], [10.0, 8.0]],
        "doors": [{"id": "door_main", "type": "main_entrance", "position": [17.5, 8.0]}],
    }


def test_complete_11_groups_schema_valid():
    """Verify that ELIARequirements accepts all 11 groups with their full typed contracts."""
    payload = {
        "design_style": "modern",
        "maintenance_preference": "low",
        "water_availability": "regular",
        "access": {
            "parking_required": True,
            "vehicle_count": 2,
            "vehicle_type": "car",
            "garage_required": True,
            "garage_capacity": 2,
            "parking_type": "garage",
            "driveway_required": True,
            "driveway_style": "straight",
            "driveway_surface": "concrete",
            "pedestrian_path_required": True,
            "garden_path_required": True,
            "walking_path_surface": "pavers",
            "gate_required": True,
            "gate_opening_mechanism": "sliding",
            "gate_style": "modern_slat",
            "gate_width_m": 4.5,
        },
        "landscape": {
            "garden_ground_finish": "grass",
            "garden_required": True,
            "lawn_required": True,
            "greenery_density": "medium",
            "open_space_ratio": 0.35,
            "trees_required": True,
            "tree_quantity": 4,
            "compact_trees_preference": True,
            "shade_tree_preference": True,
            "shrubs_required": True,
            "shrubs_quantity": 10,
            "flower_beds_required": True,
            "ground_planters_required": True,
            "ground_planters_count": 4,
            "garden_seating_required": True,
            "garden_seating_count": 2,
            "garden_table_set_required": True,
            "garden_table_set_count": 1,
            "preferred_plant_ids": ["areca_catechu", "bougainvillea_spectabilis"],
        },
        "vertical_greenery": {
            "mode": "automatic",
            "wall_climbing_plants": True,
            "wall_mounted_greenery": True,
            "hanging_trailing_greenery": True,
            "accept_vertical_alternatives": True,
        },
        "balconies": {
            "planting_required": True,
            "potted_plants": True,
            "hanging_plants": True,
            "seating_required": True,
            "preferred_plant_ids": ["bougainvillea_spectabilis"],
            "target_balcony_ids": ["balc_1"],
        },
        "terrace": {
            "planting_required": True,
            "planters_required": True,
            "seating_required": True,
            "tables_required": True,
            "target_terrace_ids": ["roof_1"],
        },
        "lighting": {
            "required": True,
            "style": "minimal",
            "desired_fixture_count": 6,
            "preferred_spacing_m": 4.0,
            "garden_lighting": True,
            "pathway_lighting": True,
            "seating_lighting": True,
            "wall_lighting": True,
        },
        "water_features": {
            "well_required": True,
            "garden_taps_required": True,
            "garden_taps_count": 3,
            "pond_required": True,
            "swimming_pool_required": False,
            "septic_tank_required": True,
        },
        "solar": {
            "panels_required": True,
            "preferred_roof_surface": "flat_roof",
            "placement_priority": "maximum_yield",
            "include_live_solar": False,
        },
    }

    req = ELIARequirements(**payload)
    assert req.design_style == "modern"
    assert req.access.vehicle_count == 2
    assert req.landscape.garden_ground_finish == "grass"
    assert req.vertical_greenery.mode == "automatic"
    assert req.balconies.planting_required is True
    assert req.terrace.planters_required is True
    assert req.lighting.desired_fixture_count == 6
    assert req.water_features.garden_taps_count == 3
    assert req.solar.panels_required is True


def test_contradictory_parking_and_garage_rejected():
    """Requiring a garage when vehicle_count is 0 or parking_required is False must raise ELIA_CONTRADICTORY_REQUIREMENTS."""
    with pytest.raises((ELIAError, ValueError)) as exc_info:
        ELIARequirements(
            access={
                "parking_required": False,
                "garage_required": True,
            }
        )
    assert "ELIA_CONTRADICTORY_REQUIREMENTS" in str(exc_info.value)

    with pytest.raises((ELIAError, ValueError)) as exc_info2:
        ELIARequirements(
            access={
                "parking_required": True,
                "vehicle_count": 0,
                "garage_required": True,
            }
        )
    assert "ELIA_CONTRADICTORY_REQUIREMENTS" in str(exc_info2.value)


def test_boolean_passed_as_count_rejected():
    """Booleans must not be silently accepted as counts (e.g. True == 1)."""
    with pytest.raises((ELIAError, ValueError)) as exc_info:
        ELIARequirements(
            access={
                "vehicle_count": True,
            }
        )
    assert "vehicle_count must be an integer, not a boolean" in str(exc_info.value)

    with pytest.raises((ELIAError, ValueError)) as exc_info2:
        ELIARequirements(
            landscape={
                "tree_quantity": True,
            }
        )
    assert "tree_quantity must be an integer, not a boolean" in str(exc_info2.value)


def test_concept_alias_normalization():
    """Legacy/variant aliases like 'minimalist' and 'contemporary' must normalize to canonical keys."""
    master = _minimal_valid_master()
    norm1 = normalize_requirements({"design_style": "minimalist"}, master, "m")
    assert norm1["design_style"] == "minimalistic"

    norm2 = normalize_requirements({"design_style": "contemporary"}, master, "m")
    assert norm2["design_style"] == "modern"

    norm3 = normalize_requirements({"design_style": "greeny"}, master, "m")
    assert norm3["design_style"] == "greeny"


def test_inactive_parent_child_field_omission():
    """When a parent feature is disabled, child fields must be omitted from normalized output."""
    master = _minimal_valid_master()
    raw = {
        "access": {
            "parking_required": False,
            "vehicle_count": 4,
            "vehicle_type": "suv",
            "parking_type": "covered",
            "garage_required": False,
            "garage_capacity": 4,
            "turning_space_required": True,
            "driveway_required": False,
            "driveway_surface": "asphalt",
            "gate_required": False,
            "gate_opening_mechanism": "sliding",
            "gate_width_m": 4.5,
        },
        "landscape": {
            "trees_required": False,
            "tree_quantity": 10,
            "compact_trees_preference": True,
            "shrubs_required": False,
            "shrubs_quantity": 25,
            "ground_planters_required": False,
            "ground_planters_count": 5,
            "garden_seating_required": False,
            "garden_seating_count": 3,
            "garden_table_set_required": False,
            "garden_table_set_count": 2,
        },
        "lighting": {
            "required": False,
            "style": "accent",
            "desired_fixture_count": 10,
            "garden_lighting": True,
        },
    }

    norm = normalize_requirements(raw, master, "m")
    acc = norm["access"]
    assert acc["parking_required"] is False
    assert "vehicle_type" not in acc
    assert "parking_type" not in acc
    assert "turning_space_required" not in acc
    assert acc["driveway_required"] is False
    assert "driveway_surface" not in acc
    assert acc["gate_required"] is False
    assert "gate_opening_mechanism" not in acc

    lnd = norm["landscape"]
    assert lnd["trees_required"] is False
    assert "tree_quantity" not in lnd
    assert "compact_trees_preference" not in lnd
    assert lnd["shrubs_required"] is False
    assert "shrubs_quantity" not in lnd
    assert lnd["ground_planters_required"] is False
    assert "ground_planters_count" not in lnd

    lgt = norm["lighting"]
    assert lgt["required"] is False
    assert "style" not in lgt
    assert "desired_fixture_count" not in lgt
    assert "garden_lighting" not in lgt


def test_surface_material_validation():
    """Invalid ground finishes or walking surfaces must raise ELIA_INVALID_GROUND_FINISH or ELIA_INVALID_SURFACE_MATERIAL."""
    master = _minimal_valid_master()
    with pytest.raises(ELIAError) as exc_info:
        normalize_requirements({
            "landscape": {"garden_ground_finish": "molten_lava"}
        }, master, "m")
    assert exc_info.value.code in ("ELIA_INVALID_GROUND_FINISH", "ELIA_INVALID_SURFACE_MATERIAL")

    with pytest.raises(ELIAError) as exc_info2:
        normalize_requirements({
            "access": {"walking_path_surface": "quicksand"}
        }, master, "m")
    assert exc_info2.value.code in ("ELIA_INVALID_SURFACE_MATERIAL", "ELIA_INVALID_GROUND_FINISH")


def test_gate_opening_mechanism_validation():
    """Invalid gate opening mechanism must raise ELIA_INVALID_GATE_MECHANISM."""
    master = _minimal_valid_master()
    with pytest.raises(ELIAError) as exc_info:
        normalize_requirements({
            "access": {"gate_opening_mechanism": "teleportation"}
        }, master, "m")
    assert exc_info.value.code in ("ELIA_INVALID_GATE_MECHANISM", "ELIA_INVALID_OPENING_MECHANISM")


def test_botanical_catalogue_validation():
    """Plant IDs must exist in the authoritative botanical catalog; unknown species raise ELIA_INVALID_PLANT_ID."""
    master = _minimal_valid_master()
    # Valid botanical entries pass
    norm = normalize_requirements({
        "landscape": {"preferred_plant_ids": ["areca_catechu", "mesua_ferrea"]}
    }, master, "m")
    assert "areca_catechu" in norm["landscape"]["preferred_plant_ids"]

    # Unknown plant entry raises explicit error
    with pytest.raises(ELIAError) as exc_info:
        normalize_requirements({
            "landscape": {"preferred_plant_ids": ["fictional_alien_palm_99"]}
        }, master, "m")
    assert exc_info.value.code == "ELIA_INVALID_PLANT_ID"


def test_unsupported_preferences_tracked_and_reported():
    """Features whose spatial layout generation is deferred to Stage 2 must be reported in unsupported_preferences."""
    master = _minimal_valid_master()
    requirements = {
        "water_features": {
            "well_required": True,
            "swimming_pool_required": True,
            "pond_required": True,
            "garden_taps_required": True,
        },
        "solar": {
            "panels_required": True,
        },
        "balconies": {
            "planting_required": True,
            "seating_required": True,
        },
        "terrace": {
            "planting_required": True,
            "seating_required": True,
        },
    }
    output, outcome = run_elia(master, requirements, "test_run_1")
    fulfillment = output.get("preference_fulfillment", {})
    unsupported = fulfillment.get("unsupported_preferences", [])

    assert "swimming_pool" in unsupported
    assert "pond" in unsupported
    assert "well" in unsupported
    assert "garden_taps" in unsupported
    assert "solar_panels" in unsupported
    assert "rooftop_planting" in unsupported
    assert "balcony_planting" in unsupported


def test_requirements_persistence_in_master_json():
    """build_updated_master must persist exterior_requirements in root and in processing.elia_engine.requirements."""
    master = _minimal_valid_master()
    requirements = {
        "design_style": "modern",
        "access": {"parking_required": True, "vehicle_count": 2},
        "landscape": {"garden_ground_finish": "grass"},
    }

    output, outcome = run_elia(master, requirements, "test_run_2")

    updated = build_updated_master(master, output, "test_run_2", "valid", requirements=requirements)

    assert "exterior_requirements" in updated
    assert updated["exterior_requirements"]["design_style"] == "modern"
    assert updated["exterior_requirements"]["access"]["vehicle_count"] == 2
    assert updated["processing"]["elia_engine"]["requirements"]["design_style"] == "modern"
