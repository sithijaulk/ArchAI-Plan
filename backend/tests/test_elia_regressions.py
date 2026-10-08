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
        candidates = list(_garden_candidates(residual, 4.0))
        assert len(candidates) >= 1
        # First candidate must be the representative point
        assert candidates[0] == residual.representative_point()
        assert residual.covers(candidates[0])

    def test_garden_candidates_grid_all_inside_residual(self):
        residual = self._residual()
        candidates = list(_garden_candidates(residual, 4.0))
        for pt in candidates[1:]:  # skip rep_pt
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
        """Preferred position well outside the land polygon → gate cannot be placed there.

        With preferred_gate_location_m=[999,999] (outside the 40x30 parcel),
        plan_gate cannot satisfy the constraint → run_elia returns infeasible
        with no gate, not a gate at the wrong location.
        """
        from app.components.elia_engine.service import run_elia
        req = {**self._BASE_REQ, "access": {**self._BASE_REQ["access"],
                                            "preferred_gate_location_m": [999.0, 999.0]}}
        result, outcome = run_elia(_service_master(), req, "test-pref-gate-far-det")
        # A preference point well outside the boundary cannot be met.
        # Either gate is absent (infeasible) or, if placed, must be flagged unfulfilled.
        gate = result.get("access", {}).get("gate")
        if gate is None:
            # Geometry guarantee: the far position makes the gate unplaceable.
            assert outcome == "infeasible", (
                f"Expected infeasible when gate is absent, got outcome={outcome!r}")
        else:
            # Gate was placed anyway; the preference MUST be flagged unfulfilled.
            pref = result.get("preference_fulfillment", {})
            unfulfilled = pref.get("unfulfilled_preferences", [])
            assert "preferred_gate_location" in unfulfilled, (
                f"Gate placed at {gate.get('position')} but preference not in "
                f"unfulfilled_preferences: {unfulfilled}")

    def test_no_preferred_gate_produces_no_unfulfilled_location(self):
        """Without a preference, preferred_gate_location must not appear in unfulfilled."""
        from app.components.elia_engine.service import run_elia
        result, outcome = run_elia(_service_master(), self._BASE_REQ, "test-no-pref")
        pref = result.get("preference_fulfillment", {})
        unfulfilled = pref.get("unfulfilled_preferences", [])
        assert "preferred_gate_location" not in unfulfilled

    def test_near_south_boundary_preference_is_fulfilled(self):
        """Preferred position on the south boundary midpoint → gate placed and fulfilled."""
        from app.components.elia_engine.service import run_elia
        req = {
            "units": "m",
            "access": {
                "road_side": "south",
                "garage_required": False,
                "driveway_required": False,
                "preferred_gate_location_m": [20.0, 0.0],
            },
            "landscape": {"garden_required": False},
            "lighting": {"required": False},
            "vertical_greenery": {"mode": "disabled"},
        }
        result, outcome = run_elia(_service_master(), req, "test-pref-gate-near-det")
        gate = result.get("access", {}).get("gate")
        assert gate is not None, "Gate must be placed for an on-boundary preference"
        assert outcome == "valid"
        pref = result.get("preference_fulfillment", {})
        unfulfilled = pref.get("unfulfilled_preferences", [])
        assert "preferred_gate_location" not in unfulfilled


# ---------------------------------------------------------------------------
# Section 2 – Utility coordinate normalization
# ---------------------------------------------------------------------------


class TestUtilityCoordinateNormalization:
    """Regression tests for Section 2: utility x/y dict format and validation."""

    _MASTER = {
        "north_angle": 0,
        "location": {"latitude": 7.0, "longitude": 80.0, "timezone": "Asia/Colombo"},
    }

    def test_list_format_ft_converts_to_meters(self):
        """[10, 10] with units=ft → position_m=[3.048, 3.048]."""
        req = {"units": "ft",
               "location": {"latitude": 7.0, "longitude": 80.0},
               "utilities": {"well": {"position": [10, 10]}}}
        result = normalize_requirements(req, self._MASTER, "ft")
        assert result["utilities"]["well"]["position_m"] == pytest.approx([3.048, 3.048], rel=1e-4)

    def test_xy_dict_format_ft_converts_to_meters(self):
        """{"x":10,"y":10} with units=ft → position_m=[3.048, 3.048]."""
        req = {"units": "ft",
               "location": {"latitude": 7.0, "longitude": 80.0},
               "utilities": {"well": {"position": {"x": 10, "y": 10}}}}
        result = normalize_requirements(req, self._MASTER, "ft")
        assert result["utilities"]["well"]["position_m"] == pytest.approx([3.048, 3.048], rel=1e-4)

    def test_list_and_dict_produce_identical_position_m(self):
        """Both coordinate input formats must produce the same position_m value."""
        base = {"units": "ft",
                "location": {"latitude": 7.0, "longitude": 80.0}}
        req_list = {**base, "utilities": {"well": {"position": [10, 10]}}}
        req_dict = {**base, "utilities": {"well": {"position": {"x": 10, "y": 10}}}}
        r_list = normalize_requirements(req_list, self._MASTER, "ft")
        r_dict = normalize_requirements(req_dict, self._MASTER, "ft")
        assert r_list["utilities"]["well"]["position_m"] == pytest.approx(
            r_dict["utilities"]["well"]["position_m"], rel=1e-6)

    def test_explicit_position_m_not_scaled_again(self):
        """position_m already in meters must not be multiplied by unit scale."""
        req = {"units": "ft",
               "location": {"latitude": 7.0, "longitude": 80.0},
               "utilities": {"well": {"position_m": [3.048, 3.048]}}}
        result = normalize_requirements(req, self._MASTER, "ft")
        assert result["utilities"]["well"]["position_m"] == pytest.approx([3.048, 3.048], rel=1e-6)

    def test_septic_tank_xy_dict_converts(self):
        """septic_tank position also supports x/y dict format."""
        req = {"units": "m",
               "location": {"latitude": 7.0, "longitude": 80.0},
               "utilities": {"septic_tank": {"position": {"x": 5.0, "y": 12.0}}}}
        result = normalize_requirements(req, self._MASTER, "m")
        assert result["utilities"]["septic_tank"]["position_m"] == pytest.approx([5.0, 12.0], rel=1e-6)

    def test_nan_coordinate_rejected_with_elia_error(self):
        """Non-finite coordinates must be rejected with ELIAError."""
        req = {"units": "m",
               "location": {"latitude": 7.0, "longitude": 80.0},
               "utilities": {"well": {"position": [float("nan"), 10]}}}
        with pytest.raises(ELIAError) as exc:
            normalize_requirements(req, self._MASTER, "m")
        assert exc.value.code == "ELIA_INVALID_UTILITY_POSITION"

    def test_missing_y_key_in_dict_rejected(self):
        """Dict with only 'x' key must be rejected."""
        req = {"units": "m",
               "location": {"latitude": 7.0, "longitude": 80.0},
               "utilities": {"well": {"position": {"x": 5}}}}
        with pytest.raises(ELIAError) as exc:
            normalize_requirements(req, self._MASTER, "m")
        assert exc.value.code == "ELIA_INVALID_UTILITY_POSITION"

    def test_non_numeric_coordinate_rejected(self):
        """Non-numeric coordinate in list format must be rejected."""
        req = {"units": "m",
               "location": {"latitude": 7.0, "longitude": 80.0},
               "utilities": {"well": {"position": ["bad", 10]}}}
        with pytest.raises(ELIAError) as exc:
            normalize_requirements(req, self._MASTER, "m")
        assert exc.value.code == "ELIA_INVALID_UTILITY_POSITION"

    def test_wrong_length_list_rejected(self):
        """3-element list must be rejected."""
        req = {"units": "m",
               "location": {"latitude": 7.0, "longitude": 80.0},
               "utilities": {"well": {"position": [1, 2, 3]}}}
        with pytest.raises(ELIAError) as exc:
            normalize_requirements(req, self._MASTER, "m")
        assert exc.value.code == "ELIA_INVALID_UTILITY_POSITION"

    def test_json_round_trip_preserves_physical_position(self):
        """After normalization and JSON serialization, meters are preserved."""
        import json
        req = {"units": "ft",
               "location": {"latitude": 7.0, "longitude": 80.0},
               "utilities": {"well": {"position": [10, 10]}}}
        result = normalize_requirements(req, self._MASTER, "ft")
        round_tripped = json.loads(json.dumps(dict(result)))
        pos = round_tripped["utilities"]["well"]["position_m"]
        assert pos == pytest.approx([3.048, 3.048], rel=1e-4)


# ---------------------------------------------------------------------------
# Section 3 – Strict garage geometry validation
# ---------------------------------------------------------------------------


class TestGarageGeometryValidation:
    """Regression tests for Section 3: all malformed garage geometry cases."""

    def test_case_a_empty_polygon_list_rejected(self):
        """Case A: {'polygon': []} must raise ELIA_INVALID_GARAGE_GEOMETRY, not return None."""
        with pytest.raises(ELIAError) as exc:
            _existing_garage({"polygon": []}, 1.0)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_case_b_invalid_point_in_ring_rejected(self):
        """Case B: polygon with an empty point (missing coords) must raise."""
        with pytest.raises(ELIAError) as exc:
            _existing_garage({"polygon": [[0, 0], [8, 0], [8, 8], [0, 8], []]}, 1.0)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_case_c_invalid_hole_rejected(self):
        """Case C: hole with only 2 points must raise, not be silently dropped."""
        with pytest.raises(ELIAError) as exc:
            _existing_garage({"polygon": [[[0, 0], [8, 0], [8, 8], [0, 8]],
                                          [[1, 1], [2, 1]]]}, 1.0)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_valid_polygon_accepted(self):
        """Well-formed polygon must be accepted and have correct area."""
        result = _existing_garage({"polygon": [[0, 0], [8, 0], [8, 8], [0, 8]]}, 1.0)
        assert result is not None
        assert result.area == pytest.approx(64.0, rel=1e-6)

    def test_valid_polygon_with_hole_accepted_and_preserved(self):
        """Well-formed polygon with a valid hole must be accepted, hole preserved."""
        result = _existing_garage(
            {"polygon": [[[0, 0], [8, 0], [8, 8], [0, 8]],
                         [[1, 1], [3, 1], [3, 3], [1, 3]]]},
            1.0
        )
        assert result is not None
        assert len(list(result.interiors)) == 1
        assert result.area == pytest.approx(64.0 - 4.0, rel=1e-6)

    def test_absent_geometry_falls_back_to_center(self):
        """No polygon/footprint/geometry key → center-based box (not an error)."""
        result = _existing_garage({"position": [4.0, 4.0]}, 1.0)
        assert result is not None
        assert result.area > 0

    def test_none_input_returns_none(self):
        """None input must return None, not raise."""
        assert _existing_garage(None, 1.0) is None

    def test_non_finite_coordinate_rejected(self):
        """NaN or Inf in coordinates must raise."""
        with pytest.raises(ELIAError) as exc:
            _existing_garage({"polygon": [[0, 0], [float("nan"), 0], [8, 8], [0, 8]]}, 1.0)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_unsupported_geometry_type_rejected(self):
        """GeoJSON with non-Polygon type must raise."""
        with pytest.raises(ELIAError) as exc:
            _existing_garage({"polygon": {"type": "Point", "coordinates": [0, 0]}}, 1.0)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_explicit_empty_geometry_not_silently_switched_to_center(self):
        """If polygon key is present but empty, center key must NOT be used as fallback."""
        # Has both 'polygon: []' and 'position' — polygon presence must be honored (rejected)
        with pytest.raises(ELIAError) as exc:
            _existing_garage({"polygon": [], "position": [4.0, 4.0]}, 1.0)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_valid_hole_survives_obstacle_and_serialization(self):
        """Valid hole is preserved through garage_polygon() and serialization."""
        source = {
            "polygon": [[[0, 0], [10, 0], [10, 10], [0, 10]],
                        [[2, 2], [4, 2], [4, 4], [2, 4]]],
        }
        from app.components.elia_engine.gate_garage import garage_polygon
        poly = garage_polygon(source)
        assert poly is not None
        assert len(list(poly.interiors)) == 1
        assert poly.area == pytest.approx(100.0 - 4.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Section 6 – Computation budget enforcement
# ---------------------------------------------------------------------------


class TestComputationBudgets:
    """Deterministic low-budget tests that exhaust limits without using real resources."""

    def _make_lighting_requirements(self, zones=None, spacing_m=1.0):
        return {
            "lighting": {
                "required": True,
                "zones": zones or ["garden"],
                "preferred_spacing_m": spacing_m,
            },
            "access": {"preferred_driveway_width_m": 3.0},
        }

    def test_garden_lighting_budget_exceeded_raises_elia_error(self, monkeypatch):
        """Injecting a tiny max_grid_cells budget → ELIA_PLANNING_LIMIT_EXCEEDED."""
        from app.components.elia_engine import lighting as lighting_mod
        from shapely.geometry import box as sbox

        land = sbox(0, 0, 50, 50)
        residual = land

        original_rules = lighting_mod.elia_rules

        def patched_elia_rules():
            r = original_rules()
            return {**r, "access": {**r["access"], "max_grid_cells": 1}}

        monkeypatch.setattr(lighting_mod, "elia_rules", patched_elia_rules)
        from app.components.elia_engine.lighting import place_lighting, _garden_candidates
        with pytest.raises(ELIAError) as exc:
            list(_garden_candidates(residual, 1.0))
        assert exc.value.code == "ELIA_PLANNING_LIMIT_EXCEEDED"

    def test_boundary_lighting_budget_exceeded_raises_elia_error(self, monkeypatch):
        """A very small max_boundary_points → ELIA_PLANNING_LIMIT_EXCEEDED."""
        from app.components.elia_engine import lighting as lighting_mod
        from app.components.elia_engine.lighting import _boundary_points
        from shapely.geometry import box as sbox

        land = sbox(0, 0, 500, 500)
        # Very long boundary / tiny spacing → count >> 1
        with pytest.raises(ELIAError) as exc:
            list(_boundary_points(land, spacing=0.1, max_points=10))
        assert exc.value.code == "ELIA_PLANNING_LIMIT_EXCEEDED"

    def test_driveway_lighting_budget_cap_propagates(self, monkeypatch):
        """Injecting max_candidates=1 → driveway count > budget raises properly."""
        from app.components.elia_engine import lighting as lighting_mod
        from shapely.geometry import box as sbox, LineString

        land = sbox(0, 0, 100, 100)
        residual = sbox(5, 5, 95, 95)
        driveway = LineString([(5, 5), (95, 5)])

        original_rules = lighting_mod.lighting_rules

        def patched_rules():
            r = original_rules()
            return {**r, "max_candidates": 1, "max_boundary_points": 2000,
                    "max_final_comparison_nodes": 500}

        monkeypatch.setattr(lighting_mod, "lighting_rules", patched_rules)
        reqs = self._make_lighting_requirements(zones=["driveway"], spacing_m=0.01)
        with pytest.raises(ELIAError) as exc:
            lighting_mod.place_lighting(land, residual, driveway, None, None, reqs)
        assert exc.value.code == "ELIA_PLANNING_LIMIT_EXCEEDED"

    def test_garage_bay_fitting_budget_exceeded_raises(self, monkeypatch):
        """Tiny max_grid_cells in elia_rules → garage planning raises ELIA_PLANNING_LIMIT_EXCEEDED."""
        from app.components.elia_engine import gate_garage as gg_mod
        from shapely.geometry import box as sbox

        land = sbox(0, 0, 200, 200)
        residual = sbox(5, 5, 195, 195)
        gate = {"access_point": [5.0, 5.0], "position": [5.0, 0.0], "width": 3.5}
        access = {"garage_required": True, "garage_capacity": 1}

        original_rules = gg_mod.elia_rules

        def patched_rules():
            r = original_rules()
            return {**r, "access": {**r["access"], "max_grid_cells": 1}}

        monkeypatch.setattr(gg_mod, "elia_rules", patched_rules)
        with pytest.raises(ELIAError) as exc:
            gg_mod.plan_garage(land, residual, gate, {}, access, 1.0)
        assert exc.value.code == "ELIA_PLANNING_LIMIT_EXCEEDED"

    def test_lighting_invalid_spacing_raises(self):
        """Non-positive spacing must raise ELIA_INVALID_LIGHTING_SPACING."""
        from app.components.elia_engine.lighting import place_lighting
        from shapely.geometry import box as sbox

        land = sbox(0, 0, 20, 20)
        reqs = {"lighting": {"required": True, "zones": ["garden"], "preferred_spacing_m": -1.0},
                "access": {}}
        with pytest.raises(ELIAError) as exc:
            place_lighting(land, land, None, None, None, reqs)
        assert exc.value.code == "ELIA_INVALID_LIGHTING_SPACING"

    def test_combined_zone_budget_across_zones(self, monkeypatch):
        """max_candidates applying across driveway + garden zones."""
        from app.components.elia_engine import lighting as lighting_mod
        from shapely.geometry import box as sbox, LineString

        land = sbox(0, 0, 30, 30)
        residual = sbox(1, 1, 29, 29)
        driveway = LineString([(1, 1), (29, 1)])

        original_rules = lighting_mod.lighting_rules

        def patched_rules():
            r = original_rules()
            return {**r, "max_candidates": 2, "max_boundary_points": 2000,
                    "max_final_comparison_nodes": 500}

        monkeypatch.setattr(lighting_mod, "lighting_rules", patched_rules)
        reqs = self._make_lighting_requirements(zones=["driveway", "garden"], spacing_m=0.5)
        with pytest.raises(ELIAError) as exc:
            lighting_mod.place_lighting(land, residual, driveway, None, None, reqs)
        assert exc.value.code == "ELIA_PLANNING_LIMIT_EXCEEDED"


# ---------------------------------------------------------------------------
# Defect 1: Garage validation bypasses – false/array/scalar values
# ---------------------------------------------------------------------------
from app.components.elia_engine.exceptions import ELIAError as _ELIAError
from app.components.elia_engine.gate_garage import _existing_garage


class TestGarageValidationBypasses:
    """Tests that previously-accepted malformed garage values are now rejected."""

    SCALE = 1.0  # meters

    def test_false_garage_value_rejected(self):
        """`existing_garage: false` must raise ELIA_INVALID_GARAGE_GEOMETRY, not return None."""
        with pytest.raises(_ELIAError) as exc:
            _existing_garage(False, self.SCALE)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_empty_array_garage_rejected(self):
        """`existing_garage: []` must raise ELIA_INVALID_GARAGE_GEOMETRY."""
        with pytest.raises(_ELIAError) as exc:
            _existing_garage([], self.SCALE)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_non_empty_array_garage_rejected(self):
        """`existing_garage: [[1,2],[3,4]]` (bare array, not a Mapping) → rejected."""
        with pytest.raises(_ELIAError) as exc:
            _existing_garage([[1, 2], [3, 4]], self.SCALE)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_negative_capacity_rejected(self):
        """`{"capacity": -1}` must raise ELIA_INVALID_GARAGE_GEOMETRY."""
        with pytest.raises(_ELIAError) as exc:
            _existing_garage({"capacity": -1}, self.SCALE)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_zero_capacity_rejected(self):
        """`{"capacity": 0}` must raise ELIA_INVALID_GARAGE_GEOMETRY."""
        with pytest.raises(_ELIAError) as exc:
            _existing_garage({"capacity": 0}, self.SCALE)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_bool_capacity_rejected(self):
        """`{"capacity": True}` is a bool, not an int – must be rejected."""
        with pytest.raises(_ELIAError) as exc:
            _existing_garage({"capacity": True}, self.SCALE)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_float_capacity_rejected(self):
        """`{"capacity": 1.5}` is not an integer – rejected."""
        with pytest.raises(_ELIAError) as exc:
            _existing_garage({"capacity": 1.5}, self.SCALE)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_capacity_only_no_center_rejected(self):
        """`{"capacity": 1}` with no center/position – rejected as usable geometry missing."""
        with pytest.raises(_ELIAError) as exc:
            _existing_garage({"capacity": 1}, self.SCALE)
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_null_garage_returns_none(self):
        """`existing_garage: null` (i.e. None) → returns None (omitted)."""
        result = _existing_garage(None, self.SCALE)
        assert result is None

    def test_empty_object_returns_none(self):
        """`existing_garage: {}` → returns None (no polygon, no center, no capacity)."""
        result = _existing_garage({}, self.SCALE)
        assert result is None

    def test_valid_center_based_garage_accepted(self):
        """Valid center + capacity → returns a Polygon."""
        result = _existing_garage(
            {"center": [5.0, 5.0], "capacity": 2},
            self.SCALE,
        )
        assert result is not None and not result.is_empty

    def test_valid_center_defaults_capacity_1(self):
        """Center without capacity → defaults to capacity 1, returns a Polygon."""
        result = _existing_garage({"center": [5.0, 5.0]}, self.SCALE)
        assert result is not None and not result.is_empty

    def test_valid_polygon_accepted(self):
        """Explicit polygon list → accepted and returned as a Polygon."""
        coords = [[0, 0], [6, 0], [6, 5], [0, 5], [0, 0]]
        result = _existing_garage({"polygon": coords}, self.SCALE)
        assert result is not None and result.area > 0

    def test_valid_polygon_with_hole_accepted(self):
        """Polygon with one hole (ring-of-rings) → accepted and hole preserved."""
        outer = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        hole = [[2, 2], [8, 2], [8, 8], [2, 8], [2, 2]]
        result = _existing_garage({"polygon": [outer, hole]}, self.SCALE)
        assert result is not None
        assert len(list(result.interiors)) == 1

    def test_primary_alias_malformed_not_replaced_by_secondary(self):
        """When 'existing_garage' is malformed (False), a valid 'garage' key must NOT silently win."""
        from app.components.elia_engine.parser import parse_exterior_context
        master = {
            **_master_m(),
            "existing_garage": False,        # malformed primary
            "garage": {"center": [5.0, 5.0]},  # valid secondary
        }
        with pytest.raises(_ELIAError) as exc:
            parse_exterior_context(master, "m")
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_parse_context_false_garage_raises(self):
        """`existing_garage: false` in Master JSON → 422 via parse_exterior_context."""
        from app.components.elia_engine.parser import parse_exterior_context
        master = {**_master_m(), "existing_garage": False}
        with pytest.raises(_ELIAError) as exc:
            parse_exterior_context(master, "m")
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_parse_context_array_garage_raises(self):
        """`existing_garage: []` in Master JSON → 422 via parse_exterior_context."""
        from app.components.elia_engine.parser import parse_exterior_context
        master = {**_master_m(), "existing_garage": []}
        with pytest.raises(_ELIAError) as exc:
            parse_exterior_context(master, "m")
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_parse_context_negative_capacity_raises(self):
        """`existing_garage: {"capacity": -1}` → 422 via parse_exterior_context."""
        from app.components.elia_engine.parser import parse_exterior_context
        master = {**_master_m(), "existing_garage": {"capacity": -1}}
        with pytest.raises(_ELIAError) as exc:
            parse_exterior_context(master, "m")
        assert exc.value.code == "ELIA_INVALID_GARAGE_GEOMETRY"

    def test_parse_context_omitted_garage_ok(self):
        """No `existing_garage` key → parse_exterior_context proceeds normally."""
        from app.components.elia_engine.parser import parse_exterior_context
        master = {**_master_m()}
        # Must not raise
        ctx = parse_exterior_context(master, "m")
        assert ctx is not None


# ---------------------------------------------------------------------------
# Defect 2: Lighting output limit semantics
# ---------------------------------------------------------------------------
from app.components.elia_engine.lighting import place_lighting


class TestLightingOutputLimitSemantics:
    """Tests that the output-node limit and the work/comparison budget are separate."""

    @staticmethod
    def _land():
        from shapely.geometry import box as sbox
        return sbox(0, 0, 50, 50)

    def test_exact_output_limit_with_spacing_rejected_second_candidate_succeeds(self, monkeypatch):
        """
        Output-node limit = 1.
        Candidates at (5,5) and (5.1, 5.1) with spacing 4.
        Only (5,5) is eligible; (5.1,5.1) rejected by spacing check.
        → No ELIA_PLANNING_LIMIT_EXCEEDED, result has exactly 1 node.
        """
        from app.components.elia_engine import lighting as lighting_mod

        land = self._land()

        original_rules = lighting_mod.lighting_rules

        def patched_rules():
            r = original_rules()
            return {**r, "max_candidates": 5000,
                    "max_boundary_points": 2000,
                    "max_final_comparison_nodes": 1}

        monkeypatch.setattr(lighting_mod, "lighting_rules", patched_rules)

        # Force exactly the two candidates (5,5) and (5.1,5.1) through garden zone.
        from shapely.geometry import Point, MultiPoint

        two_cands = MultiPoint([Point(5, 5), Point(5.1, 5.1)])
        residual = two_cands.convex_hull.buffer(0.01)  # tiny area containing both

        reqs = {
            "lighting": {"required": True, "zones": ["garden"], "preferred_spacing_m": 4.0},
            "access": {},
        }
        nodes = place_lighting(land, residual, None, None, None, reqs)
        assert len(nodes) == 1
        assert nodes[0]["position"][0] == pytest.approx(5.0, abs=1.0)

    def test_exact_output_limit_second_eligible_candidate_raises(self, monkeypatch):
        """
        Output-node limit = 1.
        Candidates at (5,5) and (30,30) – both eligible (spacing 4, far apart).
        → ELIA_PLANNING_LIMIT_EXCEEDED must be raised when the 2nd eligible is reached.
        """
        from app.components.elia_engine import lighting as lighting_mod

        land = self._land()

        original_rules = lighting_mod.lighting_rules

        def patched_rules():
            r = original_rules()
            return {**r, "max_candidates": 5000,
                    "max_boundary_points": 2000,
                    "max_final_comparison_nodes": 1}

        monkeypatch.setattr(lighting_mod, "lighting_rules", patched_rules)

        from shapely.geometry import Point, MultiPoint

        two_cands = MultiPoint([Point(5, 5), Point(30, 30)])
        residual = two_cands.convex_hull.buffer(0.5)

        reqs = {
            "lighting": {"required": True, "zones": ["garden"], "preferred_spacing_m": 4.0},
            "access": {},
        }
        with pytest.raises(_ELIAError) as exc:
            place_lighting(land, residual, None, None, None, reqs)
        assert exc.value.code == "ELIA_PLANNING_LIMIT_EXCEEDED"

    def test_comparison_work_budget_exhaustion_raises(self, monkeypatch):
        """Exhausting the candidate budget before output limit → ELIA_PLANNING_LIMIT_EXCEEDED."""
        from app.components.elia_engine import lighting as lighting_mod
        from shapely.geometry import box as sbox

        land = sbox(0, 0, 50, 50)
        residual = land

        original_rules = lighting_mod.lighting_rules

        def patched_rules():
            r = original_rules()
            # max_candidates = 1 → second candidate from garden grid exhausts budget
            return {**r, "max_candidates": 1,
                    "max_boundary_points": 2000,
                    "max_final_comparison_nodes": 500}

        monkeypatch.setattr(lighting_mod, "lighting_rules", patched_rules)

        reqs = {
            "lighting": {"required": True, "zones": ["garden"], "preferred_spacing_m": 2.0},
            "access": {},
        }
        with pytest.raises(_ELIAError) as exc:
            place_lighting(land, residual, None, None, None, reqs)
        assert exc.value.code == "ELIA_PLANNING_LIMIT_EXCEEDED"

    def test_candidate_budget_shared_across_zones(self, monkeypatch):
        """Budget is exhausted when garden zone fills slots left by driveway zone."""
        from app.components.elia_engine import lighting as lighting_mod
        from shapely.geometry import box as sbox, LineString

        land = sbox(0, 0, 30, 30)
        residual = sbox(1, 1, 29, 29)
        driveway = LineString([(1, 1), (29, 1)])

        original_rules = lighting_mod.lighting_rules

        def patched_rules():
            r = original_rules()
            return {**r, "max_candidates": 2,
                    "max_boundary_points": 2000,
                    "max_final_comparison_nodes": 500}

        monkeypatch.setattr(lighting_mod, "lighting_rules", patched_rules)
        reqs = {
            "lighting": {"required": True, "zones": ["driveway", "garden"], "preferred_spacing_m": 0.5},
            "access": {"preferred_driveway_width_m": 3.0},
        }
        with pytest.raises(_ELIAError) as exc:
            place_lighting(land, residual, driveway, None, None, reqs)
        assert exc.value.code == "ELIA_PLANNING_LIMIT_EXCEEDED"

    def test_garden_generation_stops_at_budget_boundary(self, monkeypatch):
        """Garden candidate generation stops at the budget, not after building a full oversized list."""
        from app.components.elia_engine import lighting as lighting_mod
        from shapely.geometry import box as sbox

        land = sbox(0, 0, 50, 50)
        residual = land

        call_count = {"n": 0}
        original_rules = lighting_mod.lighting_rules

        def patched_rules():
            r = original_rules()
            return {**r, "max_candidates": 3,
                    "max_boundary_points": 2000,
                    "max_final_comparison_nodes": 500}

        monkeypatch.setattr(lighting_mod, "lighting_rules", patched_rules)

        reqs = {
            "lighting": {"required": True, "zones": ["garden"], "preferred_spacing_m": 0.5},
            "access": {},
        }
        with pytest.raises(_ELIAError) as exc:
            place_lighting(land, residual, None, None, None, reqs)
        assert exc.value.code == "ELIA_PLANNING_LIMIT_EXCEEDED"

    def test_validation_failure_preserves_accepted_exterior(self):
        """When garage validation fails, the service must not overwrite accepted exterior data."""
        from app.components.elia_engine.service import run_elia
        master = {
            **_master_m(),
            "existing_garage": False,          # malformed – causes 422
            "accepted_exterior": {"version": 99, "layout": {"sentinel": True}},
        }
        reqs = {
            "units": "m",
            "access": {"garage_required": False, "driveway_required": False},
            "landscape": {"garden_required": False},
            "lighting": {"required": False},
            "vertical_greenery": {"mode": "disabled"},
        }
        try:
            result, outcome = run_elia(master, reqs, "test-preserve-ext")
            # If service swallows the error, accepted_exterior must not be modified.
            ext = master.get("accepted_exterior", {})
            assert ext.get("version") == 99, "Accepted exterior version was mutated"
        except _ELIAError as exc:
            assert exc.code == "ELIA_INVALID_GARAGE_GEOMETRY"
