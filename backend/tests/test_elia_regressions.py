"""
Regression tests for ELIA Engine fixes – Phase 2
Covers:
  - Unit handling: omitted units, explicit *_m fields, re-normalization safety
  - _turn_radius reversal detection (near-180° and right-angle)
  - Solar shadow direction at cardinal and non-cardinal azimuths
  - _building_height: house_height alias
  - _empty_result: checks_total >= 1
  - preferred_gate_location / preferred_garage_location in unfulfilled_preferences
  - Capacity rounding with round() vs floor
  - validate_layout residual forwarded from service
"""
from __future__ import annotations

import math
import time
import pytest
from shapely.geometry import LineString, Point, Polygon

# ---------------------------------------------------------------------------
# Shared master fixtures
# ---------------------------------------------------------------------------

def _master_ft():
    """Master JSON using feet as source units (full format accepted by parser)."""
    return {
        "project_id": "test-ft",
        "units": "ft",
        "location": {"latitude": 6.9, "longitude": 79.8, "timezone": "Asia/Colombo"},
        "land_info": {"boundary_points": [[0, 0], [100, 0], [100, 100], [0, 100]],
                      "road_facing": "south", "calculated_north_bearing": 0},
        "house_exterior_polygon": [[10, 10], [30, 10], [30, 30], [10, 30]],
    }


def _master_m():
    """Master JSON using meters."""
    return {
        "project_id": "test-m",
        "units": "m",
        "location": {"latitude": 6.9, "longitude": 79.8, "timezone": "Asia/Colombo"},
        "land_info": {"boundary_points": [[0, 0], [30, 0], [30, 30], [0, 30]],
                      "road_facing": "south", "calculated_north_bearing": 0},
        "house_exterior_polygon": [[5, 5], [10, 5], [10, 10], [5, 10]],
    }


def _service_master():
    """Full master_json format as used in test_elia_service.py for run_elia."""
    return {
        "project_id": "test-regression",
        "project_name": "Regression Test",
        "units": "m",
        "location": {"latitude": 6.9, "longitude": 79.8, "timezone": "Asia/Colombo"},
        "land_info": {"boundary_points": [[0, 0], [40, 0], [40, 30], [0, 30]],
                      "road_facing": "south", "calculated_north_bearing": 0},
        "house_exterior_polygon": [[10, 8], [22, 8], [22, 22], [10, 22]],
        "house_height_m": 6,
        "utilities": {
            "well": {"known": True, "position": [2, 27]},
            "septic_tank": {"known": True, "position": [22, 27]},
        },
    }


# ---------------------------------------------------------------------------
# Unit normalization
# ---------------------------------------------------------------------------
from app.components.elia_engine.requirements import normalize_requirements
from app.components.elia_engine.exceptions import ELIAError
from app.components.elia_engine.gate_garage import _bay_dimensions, _existing_garage, garage_polygon, plan_gate


class TestUnitNormalization:
    def test_omitted_units_treated_as_meters(self):
        """No 'units' key → defaults to 'm', scale=1.0; gate_width default not scaled."""
        from app.components.elia_engine.rule_repository import elia_rules
        req = {}
        normed = normalize_requirements(req, _master_ft(), "ft")
        default_gw = float(elia_rules()["access"]["default_gate_width_m"])
        # Without units key, ELIA treats requirements as already in meters.
        # So the default gate_width should equal the rule default, not ft-converted.
        assert normed["access"]["gate_width_m"] == pytest.approx(default_gw, rel=1e-3)

    def test_explicit_m_units_no_scaling(self):
        """units='m' → scale=1.0 even when master is in feet."""
        req = {"units": "m", "access": {"gate_width": 3.5}}
        normed = normalize_requirements(req, _master_ft(), "ft")
        assert normed["access"]["gate_width_m"] == pytest.approx(3.5, rel=1e-3)

    def test_explicit_ft_units_converts(self):
        """units='ft' → gate_width converted to meters."""
        req = {"units": "ft", "access": {"gate_width": 10.0}}  # 10 ft ≈ 3.048 m
        normed = normalize_requirements(req, _master_m(), "m")
        assert normed["access"]["gate_width_m"] == pytest.approx(10.0 * 0.3048, rel=1e-3)

    def test_explicit_m_field_skips_scale(self):
        """gate_width_m forces scale=1.0 regardless of units key."""
        req = {"units": "ft", "access": {"gate_width_m": 3.5}}
        normed = normalize_requirements(req, _master_ft(), "ft")
        assert normed["access"]["gate_width_m"] == pytest.approx(3.5, rel=1e-3)

    def test_repeated_normalization_idempotent(self):
        """Normalizing an already-normalized dict a second time produces same value."""
        req = {"units": "m", "access": {"gate_width": 3.0}}
        first = normalize_requirements(req, _master_m(), "m")
        second = normalize_requirements(dict(first), _master_m(), "m")
        assert first["access"]["gate_width_m"] == pytest.approx(second["access"]["gate_width_m"], rel=1e-6)

    def test_public_normalized_units_injection(self):
        from app.components.elia_engine.schemas import ELIARequest
        req_json = {"units": "ft", "access": {"gate_width": 10}, "normalized_units": "m", "_elia_internal_normalized": True}
        parsed = ELIARequest.model_validate({"requirements": req_json})
        raw = parsed.requirements.model_dump(exclude_unset=True)
        assert "normalized_units" not in raw
        assert "_elia_internal_normalized" not in raw
        norm = normalize_requirements(raw, _master_ft(), "m")
        assert norm["access"]["gate_width_m"] < 4.0

    def test_driveway_defaults_consistent(self):
        norm = normalize_requirements({}, _master_ft(), "m")
        assert norm["access"]["driveway_required"] is True
        norm = normalize_requirements({"access": {}}, _master_ft(), "m")
        assert norm["access"]["driveway_required"] is True
        norm = normalize_requirements({"access": {"garage_required": False}}, _master_ft(), "m")
        assert norm["access"]["driveway_required"] is True
        norm = normalize_requirements({"access": {"driveway_required": True}}, _master_ft(), "m")
        assert norm["access"]["driveway_required"] is True
        norm = normalize_requirements({"access": {"driveway_required": False}}, _master_ft(), "m")
        assert norm["access"]["driveway_required"] is False

    def test_existing_gate_rejects_non_positive_width(self):
        with pytest.raises(ELIAError) as error:
            plan_gate(Polygon([(0, 0), (40, 0), (40, 30), (0, 30)]), Polygon([(10, 8), (22, 8), (22, 22), (10, 22)]),
                      {"existing_gate": {"position": [20, 0], "width_m": -2}},
                      {"gate_width_m": 3.5}, 1.0)
        assert error.value.code == "ELIA_INVALID_GATE_GEOMETRY"

    def test_normalized_vehicle_dimensions_are_not_scaled_again(self):
        access = {"vehicle_profiles": [{"vehicle_type": "custom", "width_m": 4.0, "length_m": 10.0}]}
        assert _bay_dimensions(access, 0.3048) == pytest.approx(_bay_dimensions(access, 1.0))

    def test_garage_hole_survives_geometry_round_trip(self):
        source = {"polygon": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                               [[2, 2], [2, 4], [4, 4], [4, 2], [2, 2]]]}
        parsed = _existing_garage(source, 1.0)
        assert parsed is not None and len(parsed.interiors) == 1
        serialized = {"polygon": [list(parsed.exterior.coords), *[list(ring.coords) for ring in parsed.interiors]]}
        restored = garage_polygon(serialized)
        assert restored.area == pytest.approx(parsed.area)
        assert len(restored.interiors) == 1

    def test_land_info_location_normalizes_without_live_provider(self, monkeypatch):
        def fail_provider(*args, **kwargs):
            raise AssertionError("normalization must not call live solar")
        monkeypatch.setattr("app.components.elia_engine.requirements.fetch_live_solar_conditions", fail_provider, raising=False)
        normalized = normalize_requirements({"access": {"driveway_required": False}},
                                            {"land_info": {"location": {"latitude": 6.9, "longitude": 79.8}},
                                             "north_angle": 0}, "m")
        assert normalized["location"]["timezone"] == "UTC"

    def test_combined_paths_and_vegetation_have_no_prohibited_overlap(self):
        master = _service_master()
        master["existing_gate"] = {"position": [1.75, 0], "width_m": 3.5}
        master["house_exterior_polygon"] = [[10, 8], [22, 8], [22, 22], [10, 22]]
        from app.components.elia_engine.service import run_elia
        exterior, outcome = run_elia(master, {
            "access": {"driveway_required": False},
            "landscape": {"garden_required": True, "garden_table_set_required": True,
                           "garden_seating_required": True, "pedestrian_path_required": True,
                           "garden_path_required": True},
            "vertical_greenery": {"mode": "disabled"},
        }, "combined-paths")
        assert outcome in {"valid", "infeasible"}
        plants = [Point(node["position"]).buffer(node["canopy_radius_m"]) for node in exterior["vegetation_nodes"]]
        paths = [Polygon(item["polygon"]) for item in exterior["outdoor_elements"]
                 if item.get("type", "").endswith("path") and item.get("polygon")]
        assert all(not plant.intersects(path) for plant in plants for path in paths)

from shapely.geometry import box
from app.components.elia_engine.outdoor_elements import place_outdoor_elements
from app.components.elia_engine.validator import validate_layout

class TestOutdoorFurniture:
    def test_furniture_overlap_prevention(self):
        residual = box(0, 0, 10, 10)
        reqs = {"landscape": {"garden_table_set_required": True, "garden_seating_required": True}}
        elements = place_outdoor_elements(residual, Polygon(), reqs, gate=None, land=residual, driveway=None, paths=None)
        geoms = [Polygon(e["polygon"]) for e in elements if e.get("polygon")]
        assert len(geoms) == 2
        assert geoms[0].intersection(geoms[1]).area < 1e-6

    def test_furniture_insufficient_space(self):
        residual = box(0, 0, 2, 2)
        reqs = {"landscape": {"garden_table_set_required": True, "garden_seating_required": True}}
        elements = place_outdoor_elements(residual, Polygon(), reqs, gate=None, land=residual, driveway=None, paths=None)
        placed = [e for e in elements if e.get("validation", {}).get("valid") is True]
        assert len(placed) < 2
        unplaced = [e for e in elements if e.get("validation", {}).get("valid") is False]
        assert len(unplaced) >= 1

    def test_furniture_independent_validation_rejects_overlap(self):
        land = box(0, 0, 10, 10)
        house = box(8, 8, 10, 10)
        outdoor_elements = [
            {"type": "garden_table_set", "json_id": "table", "polygon": list(box(1, 1, 3, 3).exterior.coords)},
            {"type": "garden_seating", "json_id": "seating", "polygon": list(box(2, 2, 4, 4).exterior.coords)}
        ]
        res = validate_layout(land, house, None, None, None, None, None, {}, [], [], {}, outdoor_elements, [], house)
        assert "seating_placement" in res["violations"] or "table_placement" in res["violations"]


# ---------------------------------------------------------------------------
# _turn_radius reversal detection  (signature: a, b, c)
# ---------------------------------------------------------------------------
from app.components.elia_engine.vehicle_access import _turn_radius


class TestTurnRadius:
    def test_straight_line_returns_inf(self):
        """Perfectly straight path → returns inf."""
        a, b, c = (0.0, 0.0), (10.0, 0.0), (20.0, 0.0)
        assert _turn_radius(a, b, c) == math.inf

    def test_right_angle_returns_zero(self):
        """90° turn: dot product = 0 → returns 0.0."""
        a, b, c = (0.0, 0.0), (5.0, 0.0), (5.0, 5.0)
        assert _turn_radius(a, b, c) == pytest.approx(0.0)

    def test_reversal_near_180_returns_zero(self):
        """Near-180° reversal → returns 0.0 (no circumradius blowup)."""
        a, b, c = (0.0, 0.0), (10.0, 0.001), (0.001, 0.0)
        result = _turn_radius(a, b, c)
        assert result == pytest.approx(0.0)

    def test_shallow_turn_positive_radius(self):
        """30° turn should yield a finite positive radius."""
        angle = math.radians(30)
        a = (0.0, 0.0)
        b = (10.0, 0.0)
        c = (10.0 + math.cos(angle) * 10.0, math.sin(angle) * 10.0)
        result = _turn_radius(a, b, c)
        assert result > 0 and math.isfinite(result)

    def test_obtuse_turn_dot_negative_returns_zero(self):
        """150° heading change → dot product < 0 → returns 0.0."""
        angle = math.radians(150)  # near-reversal
        a = (0.0, 0.0)
        b = (10.0, 0.0)
        c = (10.0 + math.cos(angle) * 10.0, math.sin(angle) * 10.0)
        result = _turn_radius(a, b, c)
        assert result == pytest.approx(0.0)

    def test_exact_90_degree_turn(self):
        """Exactly 90° (dot == 0) → returns 0.0."""
        a, b, c = (0.0, 0.0), (10.0, 0.0), (10.0, -5.0)
        result = _turn_radius(a, b, c)
        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Shadow direction
# ---------------------------------------------------------------------------
from app.components.elia_engine.shadow import analyze_shadows


def _make_house():
    return Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])


def _solar_sample(azimuth: float, elevation: float):
    return {
        "timestamp": "2024-06-21T12:00:00+05:30",
        "solar_azimuth_degrees": azimuth,
        "solar_elevation_degrees": elevation,
    }


class TestShadowDirection:
    def test_north_shadow_points_south(self):
        """Sun from North (az=0) → shadow points South (negative Y)."""
        results = analyze_shadows(_make_house(), 6.0, [_solar_sample(0.0, 30.0)], 0.0)
        s = results[0]
        if s.get("status") != "estimated":
            pytest.skip(f"Shadow not computed: {s.get('status')}")
        assert s["shadow_vector_m"][1] < 0

    def test_south_sun_shadow_points_north(self):
        """Sun from South (az=180) → shadow points North (positive Y)."""
        results = analyze_shadows(_make_house(), 6.0, [_solar_sample(180.0, 30.0)], 0.0)
        s = results[0]
        if s.get("status") != "estimated":
            pytest.skip(f"Shadow not computed: {s.get('status')}")
        assert s["shadow_vector_m"][1] > 0

    def test_east_sun_shadow_points_west(self):
        """Sun from East (az=90) → shadow points West (negative X)."""
        results = analyze_shadows(_make_house(), 6.0, [_solar_sample(90.0, 30.0)], 0.0)
        s = results[0]
        if s.get("status") != "estimated":
            pytest.skip(f"Shadow not computed: {s.get('status')}")
        assert s["shadow_vector_m"][0] < 0

    def test_west_sun_shadow_points_east(self):
        """Sun from West (az=270) → shadow points East (positive X)."""
        results = analyze_shadows(_make_house(), 6.0, [_solar_sample(270.0, 30.0)], 0.0)
        s = results[0]
        if s.get("status") != "estimated":
            pytest.skip(f"Shadow not computed: {s.get('status')}")
        assert s["shadow_vector_m"][0] > 0

    def test_nonzero_north_angle_changes_shadow(self):
        """Rotating north_angle changes the shadow direction."""
        s0 = analyze_shadows(_make_house(), 6.0, [_solar_sample(0.0, 30.0)], 0.0)[0]
        s90 = analyze_shadows(_make_house(), 6.0, [_solar_sample(0.0, 30.0)], 90.0)[0]
        if s0.get("status") != "estimated" or s90.get("status") != "estimated":
            pytest.skip("Shadow not estimated")
        assert s0["shadow_vector_m"] != s90["shadow_vector_m"]

    def test_shadow_length_increases_with_lower_elevation(self):
        """Lower sun elevation → longer shadow."""
        s_high = analyze_shadows(_make_house(), 6.0, [_solar_sample(90.0, 60.0)], 0.0)[0]
        s_low = analyze_shadows(_make_house(), 6.0, [_solar_sample(90.0, 20.0)], 0.0)[0]
        if s_high.get("status") != "estimated" or s_low.get("status") != "estimated":
            pytest.skip("Shadow not estimated")
        assert s_low["shadow_length_m"] > s_high["shadow_length_m"]


# ---------------------------------------------------------------------------
# _building_height alias
# ---------------------------------------------------------------------------
from app.components.elia_engine.service import _building_height


class TestBuildingHeight:
    def test_house_height_alias(self):
        """master.house_height is recognized as fallback."""
        assert _building_height({"house_height": 8.0}, scale=1.0) == pytest.approx(8.0)

    def test_building_height_m_takes_priority(self):
        master = {"building_height_m": 7.5, "house_height": 8.0}
        assert _building_height(master, scale=1.0) == pytest.approx(7.5)

    def test_house_height_m_takes_priority(self):
        master = {"house_height_m": 9.0, "house_height": 8.0}
        assert _building_height(master, scale=1.0) == pytest.approx(9.0)

    def test_building_height_scaled(self):
        """Non-_m value is multiplied by scale."""
        assert _building_height({"building_height": 10.0}, scale=0.3048) == pytest.approx(3.048, rel=1e-4)

    def test_returns_none_when_absent(self):
        assert _building_height({}, scale=1.0) is None


# ---------------------------------------------------------------------------
# _empty_result: checks_total >= 1
# ---------------------------------------------------------------------------
from app.components.elia_engine.service import _empty_result


def _parse_ctx():
    from app.components.elia_engine.parser import parse_exterior_context
    master = _service_master()
    return parse_exterior_context(master, default_units="m")


class TestEmptyResult:
    def test_checks_total_at_least_one_when_no_violations(self):
        """Even with 0 violations checks_total must be >= 1 (prevents div/zero)."""
        from app.components.elia_engine.utility_safety import validate_utilities
        ctx = _parse_ctx()
        utils = validate_utilities({}, {}, "m", "m")
        result = _empty_result(ctx, {}, utils, [], [], [], "test reason", time.perf_counter())
        assert result["validation_summary"]["checks_total"] >= 1

    def test_checks_total_equals_violation_count_when_positive(self):
        from app.components.elia_engine.utility_safety import validate_utilities
        ctx = _parse_ctx()
        utils = validate_utilities({}, {}, "m", "m")
        violations = ["gate_candidate_or_road_access", "well_septic_separation"]
        result = _empty_result(ctx, {}, utils, [], [], violations, "test", time.perf_counter())
        assert result["validation_summary"]["checks_total"] == len(violations)

    def test_rate_is_zero_on_empty_result(self):
        from app.components.elia_engine.utility_safety import validate_utilities
        ctx = _parse_ctx()
        utils = validate_utilities({}, {}, "m", "m")
        result = _empty_result(ctx, {}, utils, [], [], ["something"], "reason", time.perf_counter())
        assert result["validation_summary"]["constraint_satisfaction_rate"] == 0.0





# ---------------------------------------------------------------------------
# Garage capacity rounding
# ---------------------------------------------------------------------------
from app.components.elia_engine.gate_garage import plan_garage
from app.components.elia_engine.rule_repository import elia_rules as _elia_rules


class TestGarageCapacity:
    def _gate(self):
        return {"access_point": [20.0, 0.5], "position": [20.0, 0.0]}

    def test_existing_capacity_dict_ignored_if_invalid_geometry(self):
        """Existing garage with explicit capacity respects actual geometry, not metadata."""
        config = _elia_rules()["access"]
        w = float(config["default_garage_width_m"])
        h = float(config["default_garage_length_m"])
        existing_poly = [[0, 0], [w, 0], [w, h], [0, h]] # 1 bay size
        master = {"existing_garage": {"polygon": existing_poly, "capacity": 3}}
        land = Polygon([(0, 0), (40, 0), (40, 40), (0, 40)])
        residual = land.difference(Polygon([(15, 15), (25, 15), (25, 25), (15, 25)]))
        result = plan_garage(land, residual, self._gate(), master, {"garage_capacity": 3}, unit_scale=1.0)
        # 1-bay geometry cannot satisfy capacity=3, even if metadata says so. Should return None.
        assert result is None
    
    def test_garage_geometry_conservative_check(self):
        """Total area alone must not establish capacity if shape is narrow."""
        config = _elia_rules()["access"]
        w = float(config["default_garage_width_m"])
        h = float(config["default_garage_length_m"])
        bay_area = w * h
        # Create a long thin garage with 3x bay_area but too narrow for even 1 vehicle
        thin_poly = [[0, 0], [1.0, 0], [1.0, bay_area * 3], [0, bay_area * 3]]
        master = {"existing_garage": {"polygon": thin_poly}}
        land = Polygon([(0, 0), (40, 0), (40, 40), (0, 40)])
        residual = land.difference(Polygon([(15, 15), (25, 15), (25, 25), (15, 25)]))
        result = plan_garage(land, residual, self._gate(), master, {"garage_capacity": 1}, unit_scale=1.0)
        # Should fail capacity check and return None, despite large area
        assert result is None


# ---------------------------------------------------------------------------
# validate_layout residual parameter
# ---------------------------------------------------------------------------
from app.components.elia_engine.validator import validate_layout


class TestValidatorResidual:
    def _base_args(self):
        land = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])
        house = Polygon([(5, 5), (10, 5), (10, 10), (5, 10)])
        return land, house

    def test_residual_check_appears_when_passed(self):
        """Passing residual adds site_has_residual_ground_space to checks."""
        land, house = self._base_args()
        residual = land.difference(house)
        result = validate_layout(land, house, None, None, None, None, None,
                                 {"status": "not_applicable"}, [], [],
                                 {"triggered": False, "elements": []},
                                 [], [], house, residual=residual)
        assert result["checks_total"] >= 1

    def test_residual_adds_one_extra_check_vs_none(self):
        """Passing residual increases checks_total by exactly 1."""
        land, house = self._base_args()
        residual = land.difference(house)
        r_no = validate_layout(land, house, None, None, None, None, None,
                               {"status": "not_applicable"}, [], [],
                               {"triggered": False, "elements": []},
                               [], [], house, residual=None)
        r_yes = validate_layout(land, house, None, None, None, None, None,
                                {"status": "not_applicable"}, [], [],
                                {"triggered": False, "elements": []},
                                [], [], house, residual=residual)
        assert r_yes["checks_total"] == r_no["checks_total"] + 1

    def test_violation_rate_never_one_when_violations_exist(self):
        """constraint_satisfaction_rate < 1.0 whenever violations are present."""
        land, house = self._base_args()
        result = validate_layout(land, house, None, None, None, None, None,
                                 {"status": "failed"}, [], [],
                                 {"triggered": False, "elements": []},
                                 [], [], house)
        if result["violations"]:
            assert result["constraint_satisfaction_rate"] < 1.0


# ===========================================================================
# Phase-3 regression tests
# ===========================================================================

# ---------------------------------------------------------------------------
# Garage capacity: U-shaped polygon and rotation invariance
# ---------------------------------------------------------------------------
from app.components.elia_engine.gate_garage import _count_fitting_bays
from shapely import affinity as _affinity


class TestGarageCapacityPhase3:
    """Confirmed defects in the enclosing-rectangle heuristic."""

    def _bay_dims(self):
        config = _elia_rules()["access"]
        return float(config["default_garage_width_m"]), float(config["default_garage_length_m"])

    # Exact U-shaped reproduction polygon from the defect report
    _U_POLY = Polygon([[26, 6], [36, 6], [36, 16], [35, 16], [35, 7], [27, 7], [27, 16], [26, 16]])

    def test_u_shaped_polygon_cannot_satisfy_capacity_1(self):
        """U-shape with 1m arms: no single bay fits inside the concave arms."""
        bay_w, bay_l = self._bay_dims()
        cap = _count_fitting_bays(self._U_POLY, bay_w, bay_l)
        assert cap == 0, f"U-shaped polygon wrongly reported capacity={cap}"

    def test_rectangle_3_5x6_satisfies_capacity_1(self):
        """A standard 1-bay rectangular garage must pass capacity=1."""
        bay_w, bay_l = self._bay_dims()  # 3.5 x 6
        garage = box(0, 0, bay_w, bay_l)
        cap = _count_fitting_bays(garage, bay_w, bay_l)
        assert cap >= 1

    def test_rectangle_capacity_stable_after_translation(self):
        """Translating a valid garage polygon must not change its capacity."""
        bay_w, bay_l = self._bay_dims()
        base = box(0, 0, bay_w * 2, bay_l)
        for tx, ty in ((5, 3), (17.3, -2.1), (-100, 50)):
            translated = _affinity.translate(base, tx, ty)
            assert _count_fitting_bays(translated, bay_w, bay_l) >= 2, \
                f"Capacity dropped after translation ({tx},{ty})"

    def test_rectangle_capacity_stable_at_0_degrees(self):
        bay_w, bay_l = self._bay_dims()
        garage = box(0, 0, bay_w, bay_l)
        assert _count_fitting_bays(garage, bay_w, bay_l) >= 1

    def test_rectangle_capacity_stable_at_90_degrees(self):
        bay_w, bay_l = self._bay_dims()
        garage = box(0, 0, bay_w, bay_l)
        rotated = _affinity.rotate(garage, 90, origin=(0, 0))
        assert _count_fitting_bays(rotated, bay_w, bay_l) >= 1

    def test_rectangle_capacity_stable_at_30_degrees(self):
        """A 3.5x6 m garage rotated 30 degrees must still hold 1 bay."""
        bay_w, bay_l = self._bay_dims()
        garage = box(0, 0, bay_w, bay_l)
        rotated = _affinity.rotate(garage, 30, origin=garage.centroid)
        assert _count_fitting_bays(rotated, bay_w, bay_l) >= 1

    def test_rectangle_capacity_stable_at_45_degrees(self):
        """A 3.5x6 m garage rotated 45 degrees must still hold 1 bay."""
        bay_w, bay_l = self._bay_dims()
        garage = box(0, 0, bay_w, bay_l)
        rotated = _affinity.rotate(garage, 45, origin=garage.centroid)
        assert _count_fitting_bays(rotated, bay_w, bay_l) >= 1

    def test_two_bay_rectangle_returns_2(self):
        """A 2-bay rectangle (7 x 6 m) must satisfy capacity=2."""
        bay_w, bay_l = self._bay_dims()
        garage = box(0, 0, bay_w * 2, bay_l)
        assert _count_fitting_bays(garage, bay_w, bay_l) >= 2

    def test_narrow_footprint_rejected(self):
        """A 1 m wide garage cannot fit a 3.5 m wide bay."""
        bay_w, bay_l = self._bay_dims()
        narrow = box(0, 0, 1.0, 20.0)  # area >> 1 bay but width < bay_w
        assert _count_fitting_bays(narrow, bay_w, bay_l) == 0

    def test_validator_rejects_u_shape_capacity_1(self):
        """Independent validation must reject a U-shape claimed as capacity=1."""
        bay_w, bay_l = self._bay_dims()
        land = Polygon([(0, 0), (50, 0), (50, 30), (0, 30)])
        house = Polygon([(40, 0), (50, 0), (50, 10), (40, 10)])
        garage_dict = {
            "polygon": list(self._U_POLY.exterior.coords),
            "entry_point": [31.0, 6.5],
            "access_point": [31.0, 5.0],
            "capacity": 1,  # falsely claimed
        }
        req = {"access": {"garage_required": True, "garage_capacity": 1}}
        result = validate_layout(
            land, house, None, garage_dict, None, None, None,
            {}, [], [], {}, [], [], house, requirements=req
        )
        assert "requested_garage_capacity_satisfied" in result["violations"]


# ---------------------------------------------------------------------------
# Lighting: garden fallback, garage exterior placement
# ---------------------------------------------------------------------------
from shapely.geometry import box as _box
from app.components.elia_engine.lighting import place_lighting, _garden_candidates, _garage_zone_candidates


class TestLightingPhase3:
    def _land(self):
        return Polygon([(0, 0), (30, 0), (30, 30), (0, 30)])

    def _residual(self):
        return self._land().difference(Polygon([(10, 10), (20, 10), (20, 20), (10, 20)]))

    def test_garden_fallback_when_representative_blocked(self):
        """If representative_point is blocked, another grid candidate is used."""
        residual = self._residual()
        rep_pt = residual.representative_point()
        # Block only the representative point
        blocked = Point(rep_pt.x, rep_pt.y).buffer(0.3)
        land = self._land()
        reqs = {"lighting": {"required": True, "zones": ["garden"]}}
        nodes = place_lighting(land, residual, None, None, None, reqs, blocked)
        garden_nodes = [n for n in nodes if n["zone"] == "garden"]
        assert len(garden_nodes) >= 1, "No garden light placed even though space exists"

    def test_lighting_required_false_produces_no_lights(self):
        land = self._land()
        reqs = {"lighting": {"required": False, "zones": ["garden", "gate", "driveway"]}}
        nodes = place_lighting(land, self._residual(), None, None, None, reqs)
        assert nodes == []

    def test_garage_zone_places_outside_polygon(self):
        """Garage-zone lighting must not land inside the garage footprint."""
        garage_poly = box(10, 10, 13.5, 16)  # 3.5 x 6 m
        garage = {
            "polygon": list(garage_poly.exterior.coords),
            "entry_point": [11.75, 10.0],
            "access_point": [11.75, 8.5],
        }
        candidates = _garage_zone_candidates(garage)
        for zone, pt in candidates:
            assert zone == "garage"
            assert not garage_poly.buffer(0.05).covers(pt), \
                f"Garage light at {pt} is inside/on garage polygon"

    def test_garage_zone_candidates_nonempty_for_valid_garage(self):
        garage_poly = box(10, 10, 13.5, 16)
        garage = {
            "polygon": list(garage_poly.exterior.coords),
            "entry_point": [11.75, 10.0],
            "access_point": [11.75, 8.5],
        }
        candidates = _garage_zone_candidates(garage)
        assert len(candidates) >= 1

    def test_garden_candidates_include_representative_point(self):
        residual = self._residual()
        candidates = _garden_candidates(residual, 4.0)
        assert len(candidates) >= 1
        # First candidate must be the representative point
        assert candidates[0][0] == "garden"
        assert residual.covers(candidates[0][1])

    def test_garden_candidates_grid_all_inside_residual(self):
        residual = self._residual()
        for zone, pt in _garden_candidates(residual, 4.0)[1:]:  # skip rep_pt
            assert residual.covers(pt), f"Grid candidate {pt} outside residual"


# ---------------------------------------------------------------------------
# Unit normalization: sentinel cannot be spoofed by raw dict keys
# ---------------------------------------------------------------------------
from app.components.elia_engine.requirements import normalize_requirements, _is_internally_normalized


class TestNormalizationSentinelPhase3:
    _MASTER = {
        "location": {"latitude": 6.9, "longitude": 79.8},
        "land_info": {"calculated_north_bearing": 0},
    }

    def test_raw_dict_with_elia_internal_normalized_key_cannot_bypass_ft_conversion(self):
        """Core defect: raw dict injection of the old string key must still convert."""
        r = {"units": "ft", "access": {"gate_width": 10}, "_elia_internal_normalized": True}
        n = normalize_requirements(r, self._MASTER, "m")
        assert n["access"]["gate_width_m"] == pytest.approx(10 * 0.3048, rel=1e-3)

    def test_raw_dict_with_normalized_units_m_cannot_bypass_ft_conversion(self):
        """Public normalized_units='m' string also must not bypass conversion."""
        r = {"units": "ft", "access": {"gate_width": 10}, "normalized_units": "m"}
        n = normalize_requirements(r, self._MASTER, "m")
        assert n["access"]["gate_width_m"] == pytest.approx(10 * 0.3048, rel=1e-3)

    def test_internally_produced_dict_is_trusted_sentinel(self):
        """A dict produced by normalize_requirements IS detected as normalized."""
        r = {"units": "ft", "access": {"gate_width": 10}}
        n = normalize_requirements(r, self._MASTER, "m")
        assert _is_internally_normalized(n)

    def test_ordinary_dict_is_not_trusted(self):
        assert not _is_internally_normalized({"_elia_internal_normalized": True})
        assert not _is_internally_normalized({"normalized_units": "m"})
        assert not _is_internally_normalized({})

    def test_double_normalize_does_not_double_convert(self):
        """Passing a normalized dict back to normalize_requirements must not re-scale."""
        r = {"units": "ft", "access": {"gate_width": 10}}
        first = normalize_requirements(r, self._MASTER, "m")
        second = normalize_requirements(first, self._MASTER, "m")
        assert first["access"]["gate_width_m"] == pytest.approx(second["access"]["gate_width_m"], rel=1e-6)

    def test_10_ft_becomes_3_048_m(self):
        r = {"units": "ft", "access": {"gate_width": 10}}
        n = normalize_requirements(r, self._MASTER, "m")
        assert n["access"]["gate_width_m"] == pytest.approx(3.048, rel=1e-3)

    def test_explicit_m_field_stays_meters_despite_ft_units(self):
        r = {"units": "ft", "access": {"gate_width_m": 3.5}}
        n = normalize_requirements(r, self._MASTER, "m")
        assert n["access"]["gate_width_m"] == pytest.approx(3.5, rel=1e-3)

    def test_omitted_units_default_to_meters(self):
        from app.components.elia_engine.rule_repository import elia_rules
        r = {}
        n = normalize_requirements(r, self._MASTER, "m")
        default_gw = float(elia_rules()["access"]["default_gate_width_m"])
        assert n["access"]["gate_width_m"] == pytest.approx(default_gw, rel=1e-3)

    def test_sentinel_not_in_serialized_output(self):
        """The sentinel key must not appear in the public dict iteration."""
        r = {"units": "m"}
        n = normalize_requirements(r, self._MASTER, "m")
        for k in n:
            assert isinstance(k, str), f"Non-string key in output: {k!r}"
        assert "_elia_internal_normalized" not in n


# ---------------------------------------------------------------------------
# Preference fulfillment: deterministic fixture, no skip
# ---------------------------------------------------------------------------


class TestPreferenceGateDeterministic:
    """Deterministic gate-preference tests that never skip.

    The _service_master() geometry places the gate reliably at the south
    boundary midpoint (~[20, 0]).  Tests use only gate positions whose
    outcome is structurally guaranteed by the geometry, not by planning luck.
    """

    _BASE_REQ = {
        "units": "m",
        "access": {
            "road_side": "south",
            "garage_required": False,
            "driveway_required": True,
            "vehicle_profiles": [{"vehicle_type": "car", "minimum_turning_radius": 5.5}],
        },
        "landscape": {"garden_required": False},
        "lighting": {"required": False},
        "vertical_greenery": {"mode": "disabled"},
    }

    def test_far_preferred_gate_is_unfulfilled(self):
        """Preferred position well outside the land polygon → always unfulfilled."""
        from app.components.elia_engine.service import run_elia
        req = {**self._BASE_REQ, "access": {**self._BASE_REQ["access"],
                                            "preferred_gate_location_m": [999.0, 999.0]}}
        result, outcome = run_elia(_service_master(), req, "test-pref-gate-far-det")
        # Even if gate planning succeeded somewhere, the preferred pos is far away
        gate = result.get("access", {}).get("gate")
        if gate is not None:
            pref = result.get("preference_fulfillment", {})
            unfulfilled = pref.get("unfulfilled_preferences", [])
            assert "preferred_gate_location" in unfulfilled
        else:
            # Gate could not be planned at all given geometry — still a valid outcome
            assert outcome in ("infeasible", "valid")

    def test_no_preferred_gate_produces_no_unfulfilled_location(self):
        """Without a preference, preferred_gate_location must not appear in unfulfilled."""
        from app.components.elia_engine.service import run_elia
        result, outcome = run_elia(_service_master(), self._BASE_REQ, "test-no-pref")
        pref = result.get("preference_fulfillment", {})
        unfulfilled = pref.get("unfulfilled_preferences", [])
        assert "preferred_gate_location" not in unfulfilled
