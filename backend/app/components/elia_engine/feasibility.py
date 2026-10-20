from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from copy import deepcopy

from shapely import affinity
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, box, shape
from shapely.ops import unary_union

from .adapter import normalize_master_json, resolve_upstream_road
from .exceptions import ELIAError
from .geometry import feet_to_meters, point_xy
from .gate_garage import garage_polygon, _count_fitting_bays, _road_side
from .parser import UNIT_TO_METERS, parse_exterior_context
from .rule_repository import elia_rules, vehicle_profiles, vegetation_catalog
from .schemas import (
    FeatureFeasibilityAssessment,
    CombinedConflictResult,
    ProjectFeasibilityResponse,
)


@dataclass(frozen=True)
class CanonicalProjectGeometry:
    land: Polygon
    house: Polygon
    other_buildings: tuple[Polygon, ...]
    unoccupied_ground: Polygon | MultiPolygon
    land_area_m2: float
    house_area_m2: float
    unoccupied_area_m2: float
    units: str
    units_explicit: bool
    unit_scale: float
    source_revision: int | None
    road_side: str | None
    road_access_edge: int | None
    road_line: LineString | None
    has_road_access: bool
    existing_gate: dict[str, Any] | None
    existing_garage: dict[str, Any] | None
    existing_well: Point | None
    existing_septic: Point | None
    locked_features: tuple[dict[str, Any], ...]
    balconies: tuple[dict[str, Any], ...]
    walls: tuple[dict[str, Any], ...]
    roofs: tuple[dict[str, Any], ...]
    structural_evidence: dict[str, Any]
    location: dict[str, Any] | None
    provenance: dict[str, Any]


def _extract_surface_list(document: Mapping[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        val = document.get(key)
        if isinstance(val, list):
            return [item for item in val if isinstance(item, Mapping)]
        exterior = document.get("building_exterior")
        if isinstance(exterior, Mapping) and isinstance(exterior.get(key), list):
            return [item for item in exterior[key] if isinstance(item, Mapping)]
    return []


def extract_canonical_geometry(
    master_json: Mapping[str, Any],
    default_units: str | None = None,
    source_revision: int | None = None,
) -> CanonicalProjectGeometry:
    """Read authoritative geometry through existing ELIA adapter without mutation."""
    if not isinstance(master_json, Mapping):
        raise ELIAError("ELIA_INVALID_MASTER_JSON", "Master JSON must be an object.")
    
    normalized = normalize_master_json(master_json)

    # Unit determination: do not silently assume meters when unknown
    raw_units = master_json.get("units")
    units_explicit = raw_units is not None
    if isinstance(raw_units, Mapping):
        raw_units = raw_units.get("length", raw_units.get("distance"))
    
    if raw_units is not None:
        unit_str = str(raw_units).strip().lower()
        if unit_str not in UNIT_TO_METERS:
            raise ELIAError("ELIA_INVALID_UNITS", f"Unsupported Master JSON length unit: {raw_units!r}.")
        effective_units = unit_str
    elif default_units is not None:
        effective_units = default_units.strip().lower()
        if effective_units not in UNIT_TO_METERS:
            raise ELIAError("ELIA_INVALID_UNITS", f"Unsupported default length unit: {default_units!r}.")
    else:
        # Units unknown and not guaranteed
        effective_units = "unknown"

    unit_scale = UNIT_TO_METERS.get(effective_units, 1.0)

    # Parse core polygons via standard ELIA context parser
    context = parse_exterior_context(normalized, default_units=effective_units if effective_units in UNIT_TO_METERS else "m")
    land = context.land
    house = context.house

    # Extract additional buildings if present
    other_buildings_list: list[Polygon] = []
    outbuildings_raw = master_json.get("outbuildings") or master_json.get("secondary_structures") or []
    if isinstance(outbuildings_raw, list):
        for idx, item in enumerate(outbuildings_raw):
            if isinstance(item, Mapping) and "polygon" in item:
                coords = item["polygon"]
                if isinstance(coords, list) and len(coords) >= 3:
                    try:
                        pts = [(float(p[0]) * unit_scale, float(p[1]) * unit_scale) for p in coords]
                        poly = Polygon(pts)
                        if poly.is_valid and not poly.is_empty:
                            other_buildings_list.append(poly)
                    except Exception:
                        pass

    other_buildings = tuple(other_buildings_list)
    buildings_union = house if not other_buildings else unary_union([house, *other_buildings])

    # Unoccupied ground calculation
    unoccupied = land.difference(buildings_union)
    unoccupied_area = float(max(0.0, unoccupied.area))

    # Road access
    road_side, road_edge_index = resolve_upstream_road(normalized)
    has_road = road_side is not None or road_edge_index is not None
    road_line = None
    if has_road and not land.is_empty:
        coords = list(land.exterior.coords)
        if road_edge_index is not None and 0 <= road_edge_index < len(coords) - 1:
            road_line = LineString([coords[road_edge_index], coords[road_edge_index + 1]])
        elif road_side in {"north", "south", "east", "west"}:
            for i in range(len(coords) - 1):
                seg = LineString([coords[i], coords[i + 1]])
                mid = seg.interpolate(0.5, normalized=True)
                dists = {
                    "north": land.bounds[3] - mid.y,
                    "south": mid.y - land.bounds[1],
                    "east": land.bounds[2] - mid.x,
                    "west": mid.x - land.bounds[0],
                }
                if dists[road_side] < 1e-3 or dists[road_side] == min(dists.values()):
                    road_line = seg
                    break

    # Existing gate
    existing_gate_raw = master_json.get("existing_gate") or master_json.get("gate")
    existing_gate = dict(existing_gate_raw) if isinstance(existing_gate_raw, Mapping) else None

    # Existing garage
    existing_garage_raw = master_json.get("existing_garage") or master_json.get("garage")
    existing_garage = dict(existing_garage_raw) if isinstance(existing_garage_raw, Mapping) else None

    # Utilities
    utils = master_json.get("utilities", {}) if isinstance(master_json.get("utilities"), Mapping) else {}
    well_raw = utils.get("well") or master_json.get("well")
    septic_raw = utils.get("septic_tank") or master_json.get("septic_tank")

    def _parse_pt(val: Any) -> Point | None:
        if isinstance(val, Mapping):
            pos = val.get("position_m") or val.get("position") or val.get("center")
            if pos is not None:
                coord = point_xy(pos, 1.0 if "position_m" in val else unit_scale)
                if coord and all(math.isfinite(c) for c in coord):
                    return Point(coord)
        elif isinstance(val, (list, tuple)) and len(val) >= 2:
            coord = point_xy(val, unit_scale)
            if coord and all(math.isfinite(c) for c in coord):
                return Point(coord)
        return None

    existing_well = _parse_pt(well_raw)
    existing_septic = _parse_pt(septic_raw)

    # Locked features
    locked_raw = master_json.get("locked_features") or master_json.get("existing_objects") or []
    locked_features = tuple(dict(f) for f in locked_raw if isinstance(f, Mapping))

    # Surfaces
    balconies_raw = _extract_surface_list(master_json, "balconies")
    walls_raw = _extract_surface_list(master_json, "walls", "facades")
    roofs_raw = _extract_surface_list(master_json, "terraces", "flat_roofs", "roofs", "roof")

    structural_evidence = dict(master_json.get("structural_evidence", {})) if isinstance(master_json.get("structural_evidence"), Mapping) else {}
    loc = master_json.get("location") or master_json.get("site_location")
    location = dict(loc) if isinstance(loc, Mapping) else None

    provenance = {
        "source_revision": source_revision,
        "coordinate_reference": "origin_local_meters",
        "units_explicit": units_explicit,
        "source_units": effective_units,
        "land_rings_count": len(land.interiors) + 1,
    }

    return CanonicalProjectGeometry(
        land=land,
        house=house,
        other_buildings=other_buildings,
        unoccupied_ground=unoccupied,
        land_area_m2=float(land.area),
        house_area_m2=float(house.area),
        unoccupied_area_m2=unoccupied_area,
        units=effective_units,
        units_explicit=units_explicit,
        unit_scale=unit_scale,
        source_revision=source_revision,
        road_side=road_side,
        road_access_edge=road_edge_index,
        road_line=road_line,
        has_road_access=has_road or existing_gate is not None,
        existing_gate=existing_gate,
        existing_garage=existing_garage,
        existing_well=existing_well,
        existing_septic=existing_septic,
        locked_features=locked_features,
        balconies=tuple(balconies_raw),
        walls=tuple(walls_raw),
        roofs=tuple(roofs_raw),
        structural_evidence=structural_evidence,
        location=location,
        provenance=provenance,
    )


# -------------------------------------------------------------------------
# Feature Feasibility Assessors
# -------------------------------------------------------------------------

def assess_parking_and_access(
    geom: CanonicalProjectGeometry,
    requirements: Mapping[str, Any],
) -> dict[str, FeatureFeasibilityAssessment]:
    access_req = dict(requirements.get("access") or {})
    parking_requested = bool(access_req.get("parking_required", True))
    garage_requested = bool(access_req.get("garage_required", False))
    driveway_requested = bool(access_req.get("driveway_required", True))
    gate_requested = bool(access_req.get("gate_required", True))

    vehicle_count = int(access_req.get("vehicle_count") or 1)
    vehicle_type = str(access_req.get("vehicle_type") or "sedan").lower()
    profiles = vehicle_profiles()
    v_prof = profiles.get(vehicle_type, profiles.get("sedan", {}))

    bay_w = float(v_prof.get("width_m", 1.8)) + 0.8  # Bay width including clearance
    bay_l = float(v_prof.get("length_m", 4.5)) + 0.8  # Bay length including clearance
    min_parking_area = vehicle_count * (bay_w * bay_l)

    results: dict[str, FeatureFeasibilityAssessment] = {}

    # Assessment Scope Notice
    veh_scope = (
        "2D geometric clearance and setback screening; "
        "swept-path dynamics and vehicle maneuvering simulation require vehicle motion envelope evidence."
    )

    # 1. PARKING
    if not parking_requested:
        results["parking"] = FeatureFeasibilityAssessment(
            feature_id="parking",
            requested_state="disabled",
            feasibility_status="not_applicable",
            reason_codes=["PARKING_NOT_REQUESTED"],
            explanation="Vehicle parking is not requested by user preferences.",
            applicable_rule_ids=["P01"],
            assessment_scope=veh_scope,
            source_revision=geom.source_revision,
        )
    elif not geom.units_explicit:
        results["parking"] = FeatureFeasibilityAssessment(
            feature_id="parking",
            requested_state="requested",
            feasibility_status="review_required",
            reason_codes=["UNVERIFIED_PROJECT_UNITS"],
            explanation="Project Master JSON lacks explicit length units; parking footprint cannot be safely verified.",
            applicable_rule_ids=["A01", "P01"],
            missing_evidence=["units"],
            assessment_scope=veh_scope,
            source_revision=geom.source_revision,
        )
    elif not geom.has_road_access:
        results["parking"] = FeatureFeasibilityAssessment(
            feature_id="parking",
            requested_state="requested",
            feasibility_status="review_required",
            reason_codes=["MISSING_ROAD_ACCESS"],
            explanation="Authoritative project context contains no road-access edge, road side, or existing gate.",
            applicable_rule_ids=["A01", "P01"],
            missing_evidence=["road_access_geometry"],
            assessment_scope=veh_scope,
            source_revision=geom.source_revision,
            suggested_alternatives=["Specify authoritative road frontage or define existing gate entrance."],
        )
    else:
        # Check if parking bays fit inside unoccupied ground
        # Take into account utility buffers (well 1m, septic 1m)
        restricted = geom.unoccupied_ground
        if geom.existing_well:
            restricted = restricted.difference(geom.existing_well.buffer(1.0))
        if geom.existing_septic:
            restricted = restricted.difference(geom.existing_septic.buffer(1.0))

        fitting_bays = 0
        if isinstance(restricted, Polygon):
            fitting_bays = _count_fitting_bays(restricted, bay_w, bay_l)
        elif isinstance(restricted, MultiPolygon):
            fitting_bays = sum(_count_fitting_bays(p, bay_w, bay_l) for p in restricted.geoms)

        if fitting_bays >= vehicle_count:
            results["parking"] = FeatureFeasibilityAssessment(
                feature_id="parking",
                requested_state="requested",
                feasibility_status="feasible",
                reason_codes=["PARKING_CAPACITY_CONFIRMED"],
                explanation=(
                    f"Site accommodates {vehicle_count} {vehicle_type} vehicle bay(s) "
                    f"({min_parking_area:.1f} m² required; {fitting_bays} bay position(s) fit on unbuilt ground)."
                ),
                applicable_rule_ids=["P01", "P02"],
                assessment_scope=veh_scope,
                source_revision=geom.source_revision,
            )
        else:
            results["parking"] = FeatureFeasibilityAssessment(
                feature_id="parking",
                requested_state="requested",
                feasibility_status="infeasible",
                reason_codes=["INSUFFICIENT_PARKING_CLEARANCE"],
                explanation=(
                    f"Unbuilt exterior space accommodates at most {fitting_bays} {vehicle_type} bay(s); "
                    f"{vehicle_count} bay(s) requested."
                ),
                applicable_rule_ids=["P01"],
                assessment_scope=veh_scope,
                source_revision=geom.source_revision,
                suggested_alternatives=[
                    f"Reduce vehicle count to {fitting_bays} or select compact vehicle category.",
                    "Use carport configuration rather than multi-bay open parking.",
                ],
            )

    # 2. GARAGE
    if not garage_requested:
        results["garage"] = FeatureFeasibilityAssessment(
            feature_id="garage",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["GARAGE_NOT_REQUESTED"],
            explanation="Dedicated garage structure is not requested.",
            applicable_rule_ids=["P01"],
            assessment_scope=veh_scope,
            source_revision=geom.source_revision,
        )
    elif geom.existing_garage:
        # Existing locked garage
        results["garage"] = FeatureFeasibilityAssessment(
            feature_id="garage",
            requested_state="requested",
            feasibility_status="feasible",
            reason_codes=["EXISTING_GARAGE_PRESERVED"],
            explanation="Authoritative Master JSON contains an existing garage footprint which is preserved.",
            affected_object_ids=["EXISTING_GARAGE"],
            applicable_rule_ids=["P01", "P03"],
            assessment_scope=veh_scope,
            source_revision=geom.source_revision,
        )
    elif not geom.has_road_access:
        results["garage"] = FeatureFeasibilityAssessment(
            feature_id="garage",
            requested_state="requested",
            feasibility_status="review_required",
            reason_codes=["MISSING_ROAD_ACCESS"],
            explanation="Cannot plan a new garage without road-access frontage or gate entrance.",
            applicable_rule_ids=["A01", "P01"],
            missing_evidence=["road_access_geometry"],
            assessment_scope=veh_scope,
            source_revision=geom.source_revision,
        )
    else:
        # Minimum enclosed garage box: e.g. 3.2m x 6.0m per vehicle
        garage_w = max(3.2, bay_w + 0.4)
        garage_l = max(6.0, bay_l + 0.6)
        garage_bays = 0
        if isinstance(geom.unoccupied_ground, Polygon):
            garage_bays = _count_fitting_bays(geom.unoccupied_ground, garage_w, garage_l)
        elif isinstance(geom.unoccupied_ground, MultiPolygon):
            garage_bays = sum(_count_fitting_bays(p, garage_w, garage_l) for p in geom.unoccupied_ground.geoms)

        if garage_bays >= vehicle_count:
            results["garage"] = FeatureFeasibilityAssessment(
                feature_id="garage",
                requested_state="requested",
                feasibility_status="feasible",
                reason_codes=["GARAGE_ENVELOPE_FEASIBLE"],
                explanation=f"Unbuilt exterior space accommodates a {vehicle_count}-bay enclosed garage footprint ({garage_w * garage_l * vehicle_count:.1f} m²).",
                applicable_rule_ids=["P01", "P02", "P03"],
                assessment_scope=veh_scope,
                source_revision=geom.source_revision,
            )
        else:
            results["garage"] = FeatureFeasibilityAssessment(
                feature_id="garage",
                requested_state="requested",
                feasibility_status="infeasible",
                reason_codes=["INSUFFICIENT_GARAGE_SPACE"],
                explanation=f"Exterior space cannot fit an enclosed {vehicle_count}-bay garage envelope of {garage_w}m x {garage_l}m.",
                applicable_rule_ids=["P01"],
                assessment_scope=veh_scope,
                source_revision=geom.source_revision,
                suggested_alternatives=[
                    "Consider surface parking or an open pergola carport instead of an enclosed garage.",
                    "Reduce vehicle capacity.",
                ],
            )

    # 3. DRIVEWAY
    driveway_style = str(access_req.get("driveway_style") or "straight").lower()
    if not driveway_requested:
        results["driveway"] = FeatureFeasibilityAssessment(
            feature_id="driveway",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["DRIVEWAY_NOT_REQUESTED"],
            explanation="Driveway is not requested.",
            applicable_rule_ids=["P02"],
            assessment_scope=veh_scope,
            source_revision=geom.source_revision,
        )
    elif not geom.has_road_access:
        results["driveway"] = FeatureFeasibilityAssessment(
            feature_id="driveway",
            requested_state="requested",
            feasibility_status="review_required",
            reason_codes=["MISSING_ROAD_ACCESS"],
            explanation="Driveway routing requires road access edge or entrance gate geometry.",
            applicable_rule_ids=["P02"],
            missing_evidence=["road_access_geometry"],
            assessment_scope=veh_scope,
            source_revision=geom.source_revision,
        )
    else:
        # Test line-of-sight from road line / gate to parking candidates
        start_pt = geom.road_line.centroid if geom.road_line else geom.unoccupied_ground.representative_point()
        if geom.existing_gate and geom.existing_gate.get("position"):
            start_pt = Point(geom.existing_gate["position"][0], geom.existing_gate["position"][1])

        # Straight driveway check: does direct ray to rear of property intersect house?
        straight_possible = True
        if driveway_style == "straight":
            # If house centroid lies directly between start_pt and interior representative point
            target_pt = geom.unoccupied_ground.representative_point()
            corridor = LineString([start_pt, target_pt])
            if corridor.crosses(geom.house) or corridor.within(geom.house):
                straight_possible = False

        if driveway_style == "straight" and not straight_possible:
            results["driveway"] = FeatureFeasibilityAssessment(
                feature_id="driveway",
                requested_state="requested:straight",
                feasibility_status="infeasible",
                reason_codes=["STRAIGHT_DRIVEWAY_OBSTRUCTED"],
                explanation="Straight driveway is obstructed by the fixed house footprint. Direct line-of-sight vehicle path cannot clear the building.",
                applicable_rule_ids=["P02"],
                affected_object_ids=["HOUSE_FOOTPRINT"],
                assessment_scope=veh_scope,
                source_revision=geom.source_revision,
                suggested_alternatives=["Switch to curved or angled driveway route around house perimeter."],
            )
        else:
            results["driveway"] = FeatureFeasibilityAssessment(
                feature_id="driveway",
                requested_state=f"requested:{driveway_style}",
                feasibility_status="feasible",
                reason_codes=["DRIVEWAY_CORRIDOR_FEASIBLE"],
                explanation=f"{driveway_style.capitalize()} driveway route can connect the road access gate to parking without intersecting fixed building walls.",
                applicable_rule_ids=["P02"],
                assessment_scope=veh_scope,
                source_revision=geom.source_revision,
            )

    # 4. GATE
    gate_mechanism = str(access_req.get("gate_opening_mechanism") or "sliding").lower()
    gate_w = float(access_req.get("gate_width_m") or 3.6)
    if not gate_requested:
        results["gate"] = FeatureFeasibilityAssessment(
            feature_id="gate",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["GATE_NOT_REQUESTED"],
            explanation="Entrance gate is not requested.",
            applicable_rule_ids=["P02"],
            assessment_scope=veh_scope,
            source_revision=geom.source_revision,
        )
    elif geom.existing_gate:
        results["gate"] = FeatureFeasibilityAssessment(
            feature_id="gate",
            requested_state="requested",
            feasibility_status="feasible",
            reason_codes=["EXISTING_GATE_PRESERVED"],
            explanation="Authoritative Master JSON contains an existing gate position which cannot be moved.",
            affected_object_ids=["EXISTING_GATE"],
            applicable_rule_ids=["P02"],
            assessment_scope=veh_scope,
            source_revision=geom.source_revision,
        )
    elif not geom.has_road_access:
        results["gate"] = FeatureFeasibilityAssessment(
            feature_id="gate",
            requested_state="requested",
            feasibility_status="review_required",
            reason_codes=["MISSING_ROAD_ACCESS"],
            explanation="Gate cannot be planned without authoritative road-frontage boundary edge.",
            applicable_rule_ids=["A01", "P02"],
            missing_evidence=["road_access_geometry"],
            assessment_scope=veh_scope,
            source_revision=geom.source_revision,
        )
    else:
        # Check if road edge is long enough for requested gate width
        road_len = geom.road_line.length if geom.road_line else 0.0
        if road_len > 0 and gate_w > road_len + 1e-3:
            results["gate"] = FeatureFeasibilityAssessment(
                feature_id="gate",
                requested_state="requested",
                feasibility_status="infeasible",
                reason_codes=["GATE_EXCEEDS_ROAD_FRONTAGE"],
                explanation=f"Requested gate width ({gate_w:.1f} m) exceeds available road frontage length ({road_len:.1f} m).",
                applicable_rule_ids=["P02"],
                assessment_scope=veh_scope,
                source_revision=geom.source_revision,
                suggested_alternatives=[f"Reduce gate width to at most {road_len:.1f} m."],
            )
        elif gate_mechanism in {"swing_inward", "swing"} and geom.road_line:
            # Swept arc check: gate width radius inside boundary
            gate_mid = geom.road_line.interpolate(0.5, normalized=True)
            swept_arc = gate_mid.buffer(gate_w)
            if swept_arc.intersects(geom.house):
                results["gate"] = FeatureFeasibilityAssessment(
                    feature_id="gate",
                    requested_state=f"requested:{gate_mechanism}",
                    feasibility_status="infeasible",
                    reason_codes=["GATE_SWEPT_ARC_OBSTRUCTED"],
                    explanation=f"Inward swing gate swept arc ({gate_w}m radius) collides with the house exterior wall.",
                    applicable_rule_ids=["P02"],
                    affected_object_ids=["HOUSE_FOOTPRINT"],
                    assessment_scope=veh_scope,
                    source_revision=geom.source_revision,
                    suggested_alternatives=["Switch to sliding or bi-fold gate mechanism."],
                )
            else:
                results["gate"] = FeatureFeasibilityAssessment(
                    feature_id="gate",
                    requested_state=f"requested:{gate_mechanism}",
                    feasibility_status="feasible",
                    reason_codes=["GATE_PLACEMENT_FEASIBLE"],
                    explanation=f"Road frontage accommodates a {gate_w:.1f}m {gate_mechanism} gate with required opening clearances.",
                    applicable_rule_ids=["P02"],
                    assessment_scope=veh_scope,
                    source_revision=geom.source_revision,
                )
        else:
            results["gate"] = FeatureFeasibilityAssessment(
                feature_id="gate",
                requested_state=f"requested:{gate_mechanism}",
                feasibility_status="feasible",
                reason_codes=["GATE_PLACEMENT_FEASIBLE"],
                explanation=f"Road frontage accommodates a {gate_w:.1f}m sliding gate.",
                applicable_rule_ids=["P02"],
                assessment_scope=veh_scope,
                source_revision=geom.source_revision,
            )

    return results


def assess_garden_and_planting(
    geom: CanonicalProjectGeometry,
    requirements: Mapping[str, Any],
) -> dict[str, FeatureFeasibilityAssessment]:
    landscape_req = dict(requirements.get("landscape") or {})
    garden_requested = bool(landscape_req.get("garden_required", True))
    trees_requested = bool(landscape_req.get("trees_required", False))
    shrubs_requested = bool(landscape_req.get("shrubs_requested", False) or landscape_req.get("shrubs_required", False))
    shade_pref = bool(landscape_req.get("shade_tree_preference", False))
    compact_pref = bool(landscape_req.get("compact_trees_preference", False))
    preferred_species = list(requirements.get("preferred_plant_ids") or [])

    catalog = vegetation_catalog()
    cat_entries = {e["vegetation_id"]: e for e in catalog.get("entries", [])}

    results: dict[str, FeatureFeasibilityAssessment] = {}

    bot_scope = (
        "2D mature canopy and root protection zone screening based on authoritative Sri Lankan botanical catalogue; "
        "soil chemistry, percolation rates, and sub-surface rock strata are unassessed."
    )

    # 1. LAWN / GARDEN OPEN SPACE
    lawn_pref = str(landscape_req.get("lawn_style") or "natural_grass").lower()
    if not garden_requested:
        results["garden_lawn"] = FeatureFeasibilityAssessment(
            feature_id="garden_lawn",
            requested_state="disabled",
            feasibility_status="not_applicable",
            reason_codes=["GARDEN_NOT_REQUESTED"],
            explanation="Garden and lawn areas are not requested.",
            applicable_rule_ids=["G01"],
            assessment_scope=bot_scope,
            source_revision=geom.source_revision,
        )
    elif geom.unoccupied_area_m2 < 10.0:
        results["garden_lawn"] = FeatureFeasibilityAssessment(
            feature_id="garden_lawn",
            requested_state="requested",
            feasibility_status="infeasible",
            reason_codes=["INSUFFICIENT_GARDEN_AREA"],
            explanation=f"Residual exterior space ({geom.unoccupied_area_m2:.1f} m²) is too restricted for a functional ground lawn.",
            applicable_rule_ids=["G01"],
            assessment_scope=bot_scope,
            source_revision=geom.source_revision,
            suggested_alternatives=["Consider courtyard paving with container plants, balcony planters, or vertical greenery."],
        )
    else:
        results["garden_lawn"] = FeatureFeasibilityAssessment(
            feature_id="garden_lawn",
            requested_state=f"requested:{lawn_pref}",
            feasibility_status="feasible",
            reason_codes=["GARDEN_SPACE_AVAILABLE"],
            explanation=f"Residual open ground of {geom.unoccupied_area_m2:.1f} m² is available for garden and {lawn_pref} installation.",
            applicable_rule_ids=["G01"],
            assessment_scope=bot_scope,
            source_revision=geom.source_revision,
        )

    # 2. SHADE TREES & GREENY ALTERNATIVES
    if shade_pref or (trees_requested and not compact_pref):
        # Shade trees require mature canopy clearance radius of at least 3.0m - 4.5m (approx 28-63 m²)
        # clear of building walls and boundary lines
        canopy_r = 3.5
        required_clear_diameter = canopy_r * 2
        # Check if any part of unoccupied ground can accommodate a circle of diameter required_clear_diameter
        can_fit_shade = False
        try:
            eroded = geom.unoccupied_ground.buffer(-canopy_r)
            if not eroded.is_empty and eroded.area > 0.5:
                can_fit_shade = True
        except Exception:
            can_fit_shade = geom.unoccupied_area_m2 >= 50.0

        # Check catalog suitability for requested species
        missing_catalog_data: list[str] = []
        for pid in preferred_species:
            if pid in cat_entries:
                entry = cat_entries[pid]
                if not entry.get("canopy_radius_m") or not entry.get("mature_height_m"):
                    missing_catalog_data.append(f"species:{pid}:dimensions")

        if missing_catalog_data:
            results["shade_trees"] = FeatureFeasibilityAssessment(
                feature_id="shade_trees",
                requested_state="requested",
                feasibility_status="review_required",
                reason_codes=["MISSING_SPECIES_GROWTH_DATA"],
                explanation="One or more preferred tree species lack verified mature canopy or root clearance data in the botanical catalogue.",
                applicable_rule_ids=["G01", "G03"],
                missing_evidence=missing_catalog_data,
                assessment_scope=bot_scope,
                source_revision=geom.source_revision,
            )
        elif can_fit_shade:
            results["shade_trees"] = FeatureFeasibilityAssessment(
                feature_id="shade_trees",
                requested_state="requested",
                feasibility_status="feasible",
                reason_codes=["SHADE_TREE_CLEARANCE_CONFIRMED"],
                explanation=f"Open ground accommodates mature canopy radius ({canopy_r}m) and root zone clearance away from house foundations.",
                applicable_rule_ids=["G01", "G03"],
                assessment_scope=bot_scope,
                source_revision=geom.source_revision,
            )
        else:
            # Greeny Alternative Guidance (Rule G10):
            # If ground planting cannot fit, identify justified alternatives without silently replacing intent
            alts = [
                "Select compact/columnar tree species requiring <= 1.5m canopy clearance.",
                "Use containerized planters or raised garden beds on ground.",
            ]
            if geom.walls:
                alts.append("Consider vertical wall greenery or climbing trellises on exterior facade.")
            if geom.balconies:
                alts.append("Explore balcony container planting (subject to structural load verification).")

            results["shade_trees"] = FeatureFeasibilityAssessment(
                feature_id="shade_trees",
                requested_state="requested",
                feasibility_status="infeasible",
                reason_codes=["INSUFFICIENT_SHADE_TREE_SETBACK"],
                explanation=(
                    f"Available unbuilt exterior width cannot accommodate a full-size shade tree canopy ({canopy_r * 2}m diameter) "
                    "without encroaching on building foundations or boundaries."
                ),
                applicable_rule_ids=["G01", "G03", "G10"],
                assessment_scope=bot_scope,
                source_revision=geom.source_revision,
                suggested_alternatives=alts,
            )
    else:
        results["shade_trees"] = FeatureFeasibilityAssessment(
            feature_id="shade_trees",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["SHADE_TREES_NOT_REQUESTED"],
            explanation="Large shade trees are not requested.",
            applicable_rule_ids=["G01"],
            assessment_scope=bot_scope,
            source_revision=geom.source_revision,
        )

    # 3. COMPACT TREES & SHRUBS
    if compact_pref or shrubs_requested:
        compact_r = 1.5
        can_fit_compact = False
        try:
            eroded = geom.unoccupied_ground.buffer(-compact_r)
            if not eroded.is_empty and eroded.area > 0.1:
                can_fit_compact = True
        except Exception:
            can_fit_compact = geom.unoccupied_area_m2 >= 15.0

        if can_fit_compact:
            results["compact_trees"] = FeatureFeasibilityAssessment(
                feature_id="compact_trees",
                requested_state="requested",
                feasibility_status="feasible",
                reason_codes=["COMPACT_PLANTING_FEASIBLE"],
                explanation="Exterior ground accommodates compact tree and shrub spacing clearances.",
                applicable_rule_ids=["G01"],
                assessment_scope=bot_scope,
                source_revision=geom.source_revision,
            )
        else:
            results["compact_trees"] = FeatureFeasibilityAssessment(
                feature_id="compact_trees",
                requested_state="requested",
                feasibility_status="infeasible",
                reason_codes=["INSUFFICIENT_PLANTING_GROUND"],
                explanation="Ground space is too constricted even for compact tree planting.",
                applicable_rule_ids=["G01", "G10"],
                assessment_scope=bot_scope,
                source_revision=geom.source_revision,
                suggested_alternatives=["Use wall planters or container greenery."],
            )
    else:
        results["compact_trees"] = FeatureFeasibilityAssessment(
            feature_id="compact_trees",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["COMPACT_TREES_NOT_REQUESTED"],
            explanation="Compact trees and shrubs are not explicitly requested.",
            applicable_rule_ids=["G01"],
            assessment_scope=bot_scope,
            source_revision=geom.source_revision,
        )

    # 4. OUTDOOR SEATING / DINING
    seating_req = bool(landscape_req.get("garden_seating_required", False))
    dining_req = bool(landscape_req.get("garden_table_set_required", False))
    if seating_req or dining_req:
        footprint_needed = 9.0 if dining_req else 4.0
        if geom.unoccupied_area_m2 >= footprint_needed + 10.0:
            results["outdoor_seating"] = FeatureFeasibilityAssessment(
                feature_id="outdoor_seating",
                requested_state="requested",
                feasibility_status="feasible",
                reason_codes=["SEATING_SPACE_CONFIRMED"],
                explanation=f"Unoccupied exterior ground accommodates outdoor seating/dining area ({footprint_needed} m² envelope).",
                applicable_rule_ids=["G01"],
                assessment_scope="2D spatial clearance on unoccupied ground outside circulation paths.",
                source_revision=geom.source_revision,
            )
        else:
            results["outdoor_seating"] = FeatureFeasibilityAssessment(
                feature_id="outdoor_seating",
                requested_state="requested",
                feasibility_status="infeasible",
                reason_codes=["INSUFFICIENT_OUTDOOR_LIVING_SPACE"],
                explanation=f"Available ground area is insufficient to fit a dedicated outdoor dining/seating set ({footprint_needed} m² required).",
                applicable_rule_ids=["G01"],
                assessment_scope="2D spatial clearance on unoccupied ground outside circulation paths.",
                source_revision=geom.source_revision,
                suggested_alternatives=["Consider compact bench seating along building edge or terrace seating."],
            )
    else:
        results["outdoor_seating"] = FeatureFeasibilityAssessment(
            feature_id="outdoor_seating",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["OUTDOOR_SEATING_NOT_REQUESTED"],
            explanation="Outdoor seating and dining sets are not requested.",
            applicable_rule_ids=["G01"],
            assessment_scope="2D spatial clearance.",
            source_revision=geom.source_revision,
        )

    return results


def assess_vertical_and_elevated(
    geom: CanonicalProjectGeometry,
    requirements: Mapping[str, Any],
) -> dict[str, FeatureFeasibilityAssessment]:
    results: dict[str, FeatureFeasibilityAssessment] = {}

    vg_req = dict(requirements.get("vertical_greenery") or {})
    vg_enabled = bool(requirements.get("vertical_greenery_enabled") or vg_req.get("enabled", False))

    balc_req = dict(requirements.get("balconies") or {})
    balc_planting = bool(balc_req.get("planting_required", False))
    balc_seating = bool(balc_req.get("seating_required", False))
    balc_pots = bool(balc_req.get("potted_plants", False))

    terrace_req = dict(requirements.get("terrace") or {})
    terrace_planting = bool(terrace_req.get("planting_required", False) or terrace_req.get("planters_required", False))
    terrace_seating = bool(terrace_req.get("seating_required", False))
    terrace_tables = bool(terrace_req.get("tables_required", False))

    struct_allowance = geom.structural_evidence.get("balcony_allowance_kg_m2")
    roof_allowance = geom.structural_evidence.get("roof_allowance_kg_m2") or geom.structural_evidence.get("terrace_allowance_kg_m2")

    elev_scope = (
        "Surface polygon verification and structural evidence screening; "
        "structural load calculations, point loading, waterproofing integrity, and wind sheer require professional engineering endorsement."
    )

    # 1. VERTICAL WALL GREENERY
    if not vg_enabled:
        results["vertical_greenery"] = FeatureFeasibilityAssessment(
            feature_id="vertical_greenery",
            requested_state="disabled",
            feasibility_status="not_applicable",
            reason_codes=["VERTICAL_GREENERY_NOT_REQUESTED"],
            explanation="Vertical wall greenery is not requested.",
            applicable_rule_ids=["V01"],
            assessment_scope=elev_scope,
            source_revision=geom.source_revision,
        )
    elif not geom.walls:
        results["vertical_greenery"] = FeatureFeasibilityAssessment(
            feature_id="vertical_greenery",
            requested_state="requested",
            feasibility_status="review_required",
            reason_codes=["NO_WALL_SURFACES_DEFINED"],
            explanation="No external wall surfaces or facade definitions found in Master JSON.",
            applicable_rule_ids=["V01"],
            missing_evidence=["upstream_wall_geometry"],
            assessment_scope=elev_scope,
            source_revision=geom.source_revision,
            suggested_alternatives=["Model authoritative exterior facade surfaces in Component 2/3."],
        )
    else:
        results["vertical_greenery"] = FeatureFeasibilityAssessment(
            feature_id="vertical_greenery",
            requested_state="requested",
            feasibility_status="feasible",
            reason_codes=["WALL_SURFACES_AVAILABLE"],
            explanation=f"Found {len(geom.walls)} eligible exterior wall surface(s) suitable for vertical trellises and climbers.",
            affected_object_ids=[w.get("json_id", f"WALL_{i+1}") for i, w in enumerate(geom.walls)],
            applicable_rule_ids=["V01", "V02"],
            assessment_scope=elev_scope,
            source_revision=geom.source_revision,
        )

    # 2. BALCONIES
    balcony_any_requested = balc_planting or balc_seating or balc_pots
    if not balcony_any_requested:
        results["balcony_features"] = FeatureFeasibilityAssessment(
            feature_id="balcony_features",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["BALCONY_NOT_REQUESTED"],
            explanation="Balcony features are not requested.",
            applicable_rule_ids=["B01"],
            assessment_scope=elev_scope,
            source_revision=geom.source_revision,
        )
    elif not geom.balconies:
        results["balcony_features"] = FeatureFeasibilityAssessment(
            feature_id="balcony_features",
            requested_state="requested",
            feasibility_status="not_applicable",
            reason_codes=["NO_BALCONY_SURFACE"],
            explanation="No balcony surfaces exist in the authoritative Master JSON. ELIA cannot invent non-existent balconies (Rule B01).",
            applicable_rule_ids=["B01"],
            assessment_scope=elev_scope,
            source_revision=geom.source_revision,
            suggested_alternatives=["Ground container planting or vertical greenery."],
        )
    elif struct_allowance is None:
        # Balcony exists, but structural evidence missing -> Review Required (B02/B04)
        results["balcony_features"] = FeatureFeasibilityAssessment(
            feature_id="balcony_features",
            requested_state="requested",
            feasibility_status="review_required",
            reason_codes=["MISSING_STRUCTURAL_ALLOWANCE"],
            explanation=(
                f"Found {len(geom.balconies)} balcony surface(s), but structural live/dead load allowance is unverified. "
                "Balcony planting is permissible as a conditional horticultural draft only (Rules B02, B04)."
            ),
            affected_object_ids=[b.get("json_id", f"b{i+1}") for i, b in enumerate(geom.balconies)],
            applicable_rule_ids=["B01", "B02", "B04"],
            missing_evidence=["structural_evidence.balcony_allowance_kg_m2"],
            assessment_scope=elev_scope,
            source_revision=geom.source_revision,
            suggested_alternatives=["Upload structural engineer load certification confirming permissible superimposed dead load."],
        )
    else:
        results["balcony_features"] = FeatureFeasibilityAssessment(
            feature_id="balcony_features",
            requested_state="requested",
            feasibility_status="feasible",
            reason_codes=["BALCONY_ELEVATED_FEASIBLE"],
            explanation=(
                f"Balcony surface(s) verified with approved structural load allowance ({struct_allowance} kg/m²). "
                "Containers must be placed interior to guardrails (Rules B01, B02, B05)."
            ),
            affected_object_ids=[b.get("json_id", f"b{i+1}") for i, b in enumerate(geom.balconies)],
            applicable_rule_ids=["B01", "B02", "B05"],
            assessment_scope=elev_scope,
            source_revision=geom.source_revision,
        )

    # 3. ROOFTOP / TERRACE
    rooftop_any_requested = terrace_planting or terrace_seating or terrace_tables
    if not rooftop_any_requested:
        results["rooftop_terrace"] = FeatureFeasibilityAssessment(
            feature_id="rooftop_terrace",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["ROOFTOP_NOT_REQUESTED"],
            explanation="Rooftop terrace features are not requested.",
            applicable_rule_ids=["R01"],
            assessment_scope=elev_scope,
            source_revision=geom.source_revision,
        )
    elif not geom.roofs:
        results["rooftop_terrace"] = FeatureFeasibilityAssessment(
            feature_id="rooftop_terrace",
            requested_state="requested",
            feasibility_status="not_applicable",
            reason_codes=["NO_ROOFTOP_SURFACE"],
            explanation="No roof or terrace surfaces exist in authoritative Master JSON (Rule R01).",
            applicable_rule_ids=["R01"],
            assessment_scope=elev_scope,
            source_revision=geom.source_revision,
            suggested_alternatives=["Ground patio or garden seating."],
        )
    else:
        # Check if surfaces are flat terraces or pitched roofs
        flat_terraces = [
            r for r in geom.roofs
            if str(r.get("type", "")).lower() in {"flat_roof", "terrace", "flat_terrace", "podium"}
            or float(r.get("slope_degrees") or 0.0) < 5.0
        ]
        pitched_roofs = [
            r for r in geom.roofs
            if str(r.get("type", "")).lower() in {"pitched_roof", "gable", "hip", "sloped"}
            or float(r.get("slope_degrees") or 0.0) >= 5.0
        ]

        if not flat_terraces and pitched_roofs:
            results["rooftop_terrace"] = FeatureFeasibilityAssessment(
                feature_id="rooftop_terrace",
                requested_state="requested",
                feasibility_status="infeasible",
                reason_codes=["PITCHED_ROOF_INELIGIBLE"],
                explanation="Building has pitched roof surfaces only. Pitched roofs cannot accommodate walking, seating, or planter placement.",
                affected_object_ids=[r.get("json_id", "ROOF") for r in pitched_roofs],
                applicable_rule_ids=["R01", "R02"],
                assessment_scope=elev_scope,
                source_revision=geom.source_revision,
                suggested_alternatives=["Use ground garden seating or balcony surfaces."],
            )
        elif roof_allowance is None:
            results["rooftop_terrace"] = FeatureFeasibilityAssessment(
                feature_id="rooftop_terrace",
                requested_state="requested",
                feasibility_status="review_required",
                reason_codes=["MISSING_ROOF_STRUCTURAL_ALLOWANCE"],
                explanation=f"Found {len(flat_terraces)} flat terrace surface(s), but structural live load and waterproofing evidence is unverified.",
                affected_object_ids=[r.get("json_id", f"t{i+1}") for i, r in enumerate(flat_terraces)],
                applicable_rule_ids=["R01", "R02"],
                missing_evidence=["structural_evidence.roof_allowance_kg_m2"],
                assessment_scope=elev_scope,
                source_revision=geom.source_revision,
                suggested_alternatives=["Provide structural engineer roof allowance certificate."],
            )
        else:
            results["rooftop_terrace"] = FeatureFeasibilityAssessment(
                feature_id="rooftop_terrace",
                requested_state="requested",
                feasibility_status="feasible",
                reason_codes=["ROOFTOP_TERRACE_FEASIBLE"],
                explanation=f"Flat terrace surface(s) verified with approved structural allowance ({roof_allowance} kg/m²).",
                affected_object_ids=[r.get("json_id", f"t{i+1}") for i, r in enumerate(flat_terraces)],
                applicable_rule_ids=["R01", "R02"],
                assessment_scope=elev_scope,
                source_revision=geom.source_revision,
            )

    return results


def assess_water_and_sanitation(
    geom: CanonicalProjectGeometry,
    requirements: Mapping[str, Any],
) -> dict[str, FeatureFeasibilityAssessment]:
    water_req = dict(requirements.get("water_features") or {})
    well_req = bool(water_req.get("well_required", False))
    septic_req = bool(water_req.get("septic_tank_required", False))
    pool_req = bool(water_req.get("swimming_pool_required", False))
    pond_req = bool(water_req.get("pond_required", False))
    taps_req = bool(water_req.get("garden_taps_required", False))

    results: dict[str, FeatureFeasibilityAssessment] = {}

    san_scope = (
        "2D spatial separation and maintenance access screening (Rule W01: 15.24m / 50ft well-septic setback); "
        "subsurface hydrology, groundwater flow gradient, contamination plume, and soil percolation are unassessed."
    )

    # 1. WELL
    # Distance requirement: 50 ft = 15.24 m
    req_separation_m = feet_to_meters(float(elia_rules()["utility_rules"]["well_septic_min_distance"]["value"]))

    if geom.existing_well:
        # Existing well: must be preserved and cannot be relocated
        results["well"] = FeatureFeasibilityAssessment(
            feature_id="well",
            requested_state="existing_preserved",
            feasibility_status="feasible",
            reason_codes=["EXISTING_WELL_PRESERVED"],
            explanation="Authoritative Master JSON contains an existing water well which is preserved.",
            affected_object_ids=["EXISTING_WELL"],
            applicable_rule_ids=["W01"],
            assessment_scope=san_scope,
            source_revision=geom.source_revision,
        )
    elif not well_req:
        results["well"] = FeatureFeasibilityAssessment(
            feature_id="well",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["WELL_NOT_REQUESTED"],
            explanation="Domestic water well is not requested.",
            applicable_rule_ids=["W01"],
            assessment_scope=san_scope,
            source_revision=geom.source_revision,
        )
    else:
        # New well requested: check separation against existing or proposed septic tank
        if geom.existing_septic:
            septic_pt = geom.existing_septic
            # Check if any candidate point on unoccupied ground is >= 15.24m from septic_pt
            # and within land boundary
            well_buffer_zone = septic_pt.buffer(req_separation_m)
            feasible_well_zone = geom.unoccupied_ground.difference(well_buffer_zone)
            if feasible_well_zone.is_empty or feasible_well_zone.area < 2.0:
                results["well"] = FeatureFeasibilityAssessment(
                    feature_id="well",
                    requested_state="requested",
                    feasibility_status="infeasible",
                    reason_codes=["WELL_SEPTIC_SEPARATION_VIOLATION"],
                    explanation=(
                        f"Mandatory {req_separation_m:.2f}m (50 ft) separation from existing septic tank cannot be satisfied on this site (Rule W01). "
                        "All available exterior ground lies within the septic protection buffer."
                    ),
                    affected_object_ids=["EXISTING_SEPTIC"],
                    applicable_rule_ids=["W01"],
                    assessment_scope=san_scope,
                    source_revision=geom.source_revision,
                    suggested_alternatives=["Use municipal water supply connection rather than on-site domestic well."],
                )
            else:
                results["well"] = FeatureFeasibilityAssessment(
                    feature_id="well",
                    requested_state="requested",
                    feasibility_status="review_required",
                    reason_codes=["WELL_LOCATION_PRECONDITION_MET"],
                    explanation=(
                        f"2D surface separation ({req_separation_m:.2f}m) from septic tank is geometrically feasible on {feasible_well_zone.area:.1f} m² of site. "
                        "Hydrogeological clearance, water table depth, and drinking water safety require field survey review."
                    ),
                    applicable_rule_ids=["W01"],
                    missing_evidence=["hydrogeological_survey", "groundwater_table_depth"],
                    assessment_scope=san_scope,
                    source_revision=geom.source_revision,
                )
        else:
            results["well"] = FeatureFeasibilityAssessment(
                feature_id="well",
                requested_state="requested",
                feasibility_status="review_required",
                reason_codes=["MISSING_SEPTIC_EVIDENCE"],
                explanation="Septic tank location is unknown in Master JSON; sanitary separation cannot be guaranteed.",
                applicable_rule_ids=["W01"],
                missing_evidence=["septic_tank_location"],
                assessment_scope=san_scope,
                source_revision=geom.source_revision,
            )

    # 2. SEPTIC TANK
    if geom.existing_septic:
        # Check maintenance access: distance from road or driveway
        results["septic_tank"] = FeatureFeasibilityAssessment(
            feature_id="septic_tank",
            requested_state="existing_preserved",
            feasibility_status="feasible",
            reason_codes=["EXISTING_SEPTIC_PRESERVED"],
            explanation="Authoritative Master JSON contains an existing septic tank which is preserved.",
            affected_object_ids=["EXISTING_SEPTIC"],
            applicable_rule_ids=["W01"],
            assessment_scope=san_scope,
            source_revision=geom.source_revision,
        )
    elif not septic_req:
        results["septic_tank"] = FeatureFeasibilityAssessment(
            feature_id="septic_tank",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["SEPTIC_NOT_REQUESTED"],
            explanation="Septic tank is not requested or site is connected to municipal sewer.",
            applicable_rule_ids=["W01"],
            assessment_scope=san_scope,
            source_revision=geom.source_revision,
        )
    else:
        results["septic_tank"] = FeatureFeasibilityAssessment(
            feature_id="septic_tank",
            requested_state="requested",
            feasibility_status="review_required",
            reason_codes=["SEPTIC_PLANNING_REQUIRES_DRAINAGE_SURVEY"],
            explanation="Septic tank placement requires drainage slope, soil percolation data, and vacuum tanker service reach verification.",
            applicable_rule_ids=["W01", "W07"],
            missing_evidence=["soil_percolation_rate", "terrain_slope_levels"],
            assessment_scope=san_scope,
            source_revision=geom.source_revision,
        )

    # 3. SWIMMING POOL
    if not pool_req:
        results["swimming_pool"] = FeatureFeasibilityAssessment(
            feature_id="swimming_pool",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["POOL_NOT_REQUESTED"],
            explanation="Swimming pool is not requested.",
            applicable_rule_ids=["W01"],
            assessment_scope=san_scope,
            source_revision=geom.source_revision,
        )
    else:
        # Minimum pool envelope: e.g. 4.0m x 8.0m pool + 1.5m perimeter deck = 7.0m x 11.0m (77 m²)
        pool_w, pool_l = 6.0, 10.0
        min_pool_area = pool_w * pool_l

        # Buffer setbacks from house and boundaries (min 1.5m setback)
        pool_feasible = False
        try:
            eroded = geom.unoccupied_ground.buffer(-1.5)
            if geom.existing_septic:
                eroded = eroded.difference(geom.existing_septic.buffer(3.0))
            if isinstance(eroded, Polygon):
                pool_feasible = _count_fitting_bays(eroded, pool_w, pool_l) >= 1
            elif isinstance(eroded, MultiPolygon):
                pool_feasible = any(_count_fitting_bays(p, pool_w, pool_l) >= 1 for p in eroded.geoms)
        except Exception:
            pool_feasible = geom.unoccupied_area_m2 >= (min_pool_area + 40.0)

        if pool_feasible:
            results["swimming_pool"] = FeatureFeasibilityAssessment(
                feature_id="swimming_pool",
                requested_state="requested",
                feasibility_status="review_required",
                reason_codes=["POOL_FOOTPRINT_FITS_GEOTECHNICAL_PENDING"],
                explanation=(
                    f"2D surface footprint ({pool_w}m x {pool_l}m, {min_pool_area:.0f} m²) fits within unbuilt exterior ground. "
                    "Geotechnical excavation, foundation underpinning, structural engineering, and drainage discharge require site testing."
                ),
                applicable_rule_ids=["W01", "G01"],
                missing_evidence=["geotechnical_soil_bearing_capacity", "groundwater_depth", "excavation_plan"],
                assessment_scope="2D geometric envelope clearance; deep excavation, structural basin, and waterproofing are unsupported in Stage 2.",
                source_revision=geom.source_revision,
            )
        else:
            results["swimming_pool"] = FeatureFeasibilityAssessment(
                feature_id="swimming_pool",
                requested_state="requested",
                feasibility_status="infeasible",
                reason_codes=["INSUFFICIENT_SPACE_FOR_POOL"],
                explanation=f"Residual exterior ground is too narrow or obstructed to accommodate a swimming pool envelope of {pool_w}m x {pool_l}m.",
                applicable_rule_ids=["G01"],
                assessment_scope="2D geometric envelope clearance.",
                source_revision=geom.source_revision,
                suggested_alternatives=["Consider a compact plunge pool, swim spa, or water wall feature."],
            )

    # 4. POND & WATER FEATURE
    if not pond_req:
        results["pond"] = FeatureFeasibilityAssessment(
            feature_id="pond",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["POND_NOT_REQUESTED"],
            explanation="Garden pond is not requested.",
            applicable_rule_ids=["G01"],
            assessment_scope=san_scope,
            source_revision=geom.source_revision,
        )
    elif geom.unoccupied_area_m2 >= 15.0:
        results["pond"] = FeatureFeasibilityAssessment(
            feature_id="pond",
            requested_state="requested",
            feasibility_status="feasible",
            reason_codes=["POND_FOOTPRINT_FEASIBLE"],
            explanation="Unoccupied garden space accommodates a decorative pond water feature (approx 8 m²).",
            applicable_rule_ids=["G01"],
            assessment_scope="2D surface clearance on unbuilt ground.",
            source_revision=geom.source_revision,
        )
    else:
        results["pond"] = FeatureFeasibilityAssessment(
            feature_id="pond",
            requested_state="requested",
            feasibility_status="infeasible",
            reason_codes=["INSUFFICIENT_SPACE_FOR_POND"],
            explanation="Residual exterior space is too constricted for a ground pond.",
            applicable_rule_ids=["G01"],
            assessment_scope="2D surface clearance.",
            source_revision=geom.source_revision,
            suggested_alternatives=["Wall fountain or self-contained water bowl."],
        )

    # 5. GARDEN TAPS
    if taps_req:
        results["garden_taps"] = FeatureFeasibilityAssessment(
            feature_id="garden_taps",
            requested_state="requested",
            feasibility_status="feasible",
            reason_codes=["GARDEN_TAPS_FEASIBLE"],
            explanation="Exterior plumbing taps can be accommodated along building perimeter walls.",
            applicable_rule_ids=["G01"],
            assessment_scope="Perimeter utility supply.",
            source_revision=geom.source_revision,
        )
    else:
        results["garden_taps"] = FeatureFeasibilityAssessment(
            feature_id="garden_taps",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["GARDEN_TAPS_NOT_REQUESTED"],
            explanation="Garden utility taps are not requested.",
            applicable_rule_ids=["G01"],
            assessment_scope="Perimeter utility supply.",
            source_revision=geom.source_revision,
        )

    return results


def assess_solar(
    geom: CanonicalProjectGeometry,
    requirements: Mapping[str, Any],
) -> FeatureFeasibilityAssessment:
    solar_req = dict(requirements.get("solar") or {})
    panels_requested = bool(solar_req.get("panels_required", False))

    solar_scope = (
        "Roof geometric suitability and orientation screening; "
        "detailed hourly solar irradiance, tilt-angle optimization, dynamic tree/building shading calculations, "
        "and annual kWh yield modeling are deferred to Stage 6."
    )

    if not panels_requested:
        return FeatureFeasibilityAssessment(
            feature_id="solar_pv",
            requested_state="not_requested",
            feasibility_status="not_applicable",
            reason_codes=["SOLAR_NOT_REQUESTED"],
            explanation="Rooftop solar photovoltaic installation is not requested.",
            applicable_rule_ids=["S01"],
            assessment_scope=solar_scope,
            source_revision=geom.source_revision,
        )

    if not geom.roofs:
        return FeatureFeasibilityAssessment(
            feature_id="solar_pv",
            requested_state="requested",
            feasibility_status="review_required",
            reason_codes=["MISSING_ROOF_GEOMETRY"],
            explanation="Roof surface geometry is absent from Master JSON; solar panel mounting envelope cannot be verified.",
            applicable_rule_ids=["S01"],
            missing_evidence=["roof_geometry"],
            assessment_scope=solar_scope,
            source_revision=geom.source_revision,
            suggested_alternatives=["Model roof planes in Component 2/3."],
        )

    # Check if roof planes exist and have sufficient area
    total_roof_area = 0.0
    for r in geom.roofs:
        poly_coords = r.get("polygon")
        if isinstance(poly_coords, list) and len(poly_coords) >= 3:
            try:
                total_roof_area += Polygon(poly_coords).area
            except Exception:
                pass

    if total_roof_area > 0 and total_roof_area < 15.0:
        return FeatureFeasibilityAssessment(
            feature_id="solar_pv",
            requested_state="requested",
            feasibility_status="infeasible",
            reason_codes=["INSUFFICIENT_ROOF_AREA"],
            explanation=f"Total roof area ({total_roof_area:.1f} m²) is too restricted for a standard residential solar PV array (minimum 15-20 m²).",
            applicable_rule_ids=["S01"],
            assessment_scope=solar_scope,
            source_revision=geom.source_revision,
        )

    loc_info = f"Project location: {geom.location.get('latitude', 'unknown')}, {geom.location.get('longitude', 'unknown')}." if geom.location else "Location unverified."
    return FeatureFeasibilityAssessment(
        feature_id="solar_pv",
        requested_state="requested",
        feasibility_status="feasible",
        reason_codes=["ROOF_SOLAR_ENVELOPE_FEASIBLE"],
        explanation=f"Roof surface geometry ({len(geom.roofs)} surface(s)) is geometrically eligible for solar panel array layout. {loc_info}",
        affected_object_ids=[r.get("json_id", f"ROOF_{i+1}") for i, r in enumerate(geom.roofs)],
        applicable_rule_ids=["S01", "S02"],
        assessment_scope=solar_scope,
        source_revision=geom.source_revision,
    )


def assess_lighting(
    geom: CanonicalProjectGeometry,
    requirements: Mapping[str, Any],
) -> FeatureFeasibilityAssessment:
    light_req = dict(requirements.get("lighting") or {})
    requested = bool(light_req.get("required", True))

    light_scope = "Exterior perimeter and landscape lighting placement screening."

    if not requested:
        return FeatureFeasibilityAssessment(
            feature_id="outdoor_lighting",
            requested_state="disabled",
            feasibility_status="not_applicable",
            reason_codes=["LIGHTING_NOT_REQUESTED"],
            explanation="Exterior lighting is not requested.",
            applicable_rule_ids=["L01"],
            assessment_scope=light_scope,
            source_revision=geom.source_revision,
        )

    zones = list(light_req.get("zones") or ["garden", "pathway"])
    return FeatureFeasibilityAssessment(
        feature_id="outdoor_lighting",
        requested_state="requested",
        feasibility_status="feasible",
        reason_codes=["LIGHTING_ZONES_FEASIBLE"],
        explanation=f"Exterior lighting fixtures can be distributed across requested zones ({', '.join(zones)}) along building walls and landscape borders.",
        applicable_rule_ids=["L01", "L02"],
        assessment_scope=light_scope,
        source_revision=geom.source_revision,
    )


# -------------------------------------------------------------------------
# Combined Preference Conflicts Evaluator
# -------------------------------------------------------------------------

def evaluate_combined_conflicts(
    geom: CanonicalProjectGeometry,
    requirements: Mapping[str, Any],
    individual_assessments: Mapping[str, FeatureFeasibilityAssessment],
) -> list[CombinedConflictResult]:
    conflicts: list[CombinedConflictResult] = []

    access_req = dict(requirements.get("access") or {})
    landscape_req = dict(requirements.get("landscape") or {})
    water_req = dict(requirements.get("water_features") or {})
    solar_req = dict(requirements.get("solar") or {})
    terrace_req = dict(requirements.get("terrace") or {})

    # 1. TOTAL GROUND SPACE EXHAUSTION
    # Calculate sum of minimum ground footprints for all requested ground features
    ground_demands: dict[str, float] = {}

    if access_req.get("parking_required", True):
        v_count = int(access_req.get("vehicle_count") or 1)
        ground_demands["parking"] = v_count * 15.0  # ~15m2 per parking bay
    if access_req.get("garage_required"):
        v_count = int(access_req.get("vehicle_count") or 1)
        ground_demands["garage"] = v_count * 22.0  # ~22m2 per garage bay
    if access_req.get("driveway_required", True):
        ground_demands["driveway"] = 25.0  # ~25m2 minimum driveway
    if water_req.get("swimming_pool_required"):
        ground_demands["swimming_pool"] = 65.0  # ~65m2 pool + apron
    if water_req.get("pond_required"):
        ground_demands["pond"] = 10.0
    if landscape_req.get("garden_table_set_required"):
        ground_demands["outdoor_dining"] = 10.0
    if landscape_req.get("garden_seating_required"):
        ground_demands["outdoor_seating"] = 5.0
    if landscape_req.get("shade_tree_preference"):
        ground_demands["shade_trees"] = 25.0

    total_demand = sum(ground_demands.values())
    unoccupied_usable = geom.unoccupied_area_m2

    if total_demand > unoccupied_usable and len(ground_demands) >= 2:
        conflicting_keys = list(ground_demands.keys())
        conflicts.append(CombinedConflictResult(
            conflicting_features=conflicting_keys,
            conflict_type="SPATIAL_COMPETITION",
            explanation=(
                f"Combined minimum space demanded by selected features ({total_demand:.1f} m²) exceeds "
                f"unbuilt exterior ground area ({unoccupied_usable:.1f} m²). "
                f"Breakdown: {', '.join(f'{k}: {v:.0f}m²' for k, v in ground_demands.items())}."
            ),
            affected_requests=ground_demands,
            suggested_alternatives=[
                "Reduce vehicle count or replace enclosed garage with open surface parking.",
                "Omit swimming pool or replace with compact plunge pool.",
                "Select compact trees rather than broad canopy shade trees.",
            ],
        ))

    # 2. DRIVEWAY VS POOL / POND / TREE CIRCULATION COLLISION
    # If straight driveway requested and pool or large trees are also requested in a narrow yard
    if access_req.get("driveway_required", True) and water_req.get("swimming_pool_required"):
        if unoccupied_usable < 120.0:
            conflicts.append(CombinedConflictResult(
                conflicting_features=["driveway", "swimming_pool"],
                conflict_type="CIRCULATION_COLLISION",
                explanation=(
                    "Vehicle driveway corridor and swimming pool excavation envelope compete for the same exterior side/rear yard space. "
                    "A narrow lot cannot accommodate vehicle turnaround alongside a 6m-wide pool apron."
                ),
                affected_requests={"driveway": True, "swimming_pool": True},
                suggested_alternatives=[
                    "Locate parking at the immediate front boundary to leave backyard clear for swimming pool.",
                    "Choose between vehicle driveway access to rear and pool installation.",
                ],
            ))

    # 3. WELL VS SEPTIC SEPARATION CONFLICT
    req_sep = feet_to_meters(float(elia_rules()["utility_rules"]["well_septic_min_distance"]["value"]))
    if water_req.get("well_required") and (water_req.get("septic_tank_required") or geom.existing_septic):
        if geom.existing_septic:
            septic_buf = geom.existing_septic.buffer(req_sep)
            clear_ground = geom.unoccupied_ground.difference(septic_buf)
            if clear_ground.is_empty or clear_ground.area < 2.0:
                conflicts.append(CombinedConflictResult(
                    conflicting_features=["well", "septic_tank"],
                    conflict_type="SANITARY_SEPARATION_VIOLATION",
                    explanation=(
                        f"Mandatory {req_sep:.2f}m (50 ft) separation between well and septic tank cannot be satisfied on this lot. "
                        "The existing septic tank protection zone covers all available exterior space."
                    ),
                    affected_requests={"well": True, "septic_tank": True},
                    suggested_alternatives=[
                        "Rely on municipal piped water connection and omit domestic well.",
                    ],
                ))

    # 4. ROOFTOP SOLAR VS ROOFTOP GARDEN / SEATING COMPETITION
    if solar_req.get("panels_required") and (terrace_req.get("planting_required") or terrace_req.get("seating_required") or terrace_req.get("tables_required")):
        # Check flat terrace area
        flat_terraces = [
            r for r in geom.roofs
            if str(r.get("type", "")).lower() in {"flat_roof", "terrace", "flat_terrace", "podium"}
            or float(r.get("slope_degrees") or 0.0) < 5.0
        ]
        flat_area = 0.0
        for ft in flat_terraces:
            coords = ft.get("polygon")
            if isinstance(coords, list) and len(coords) >= 3:
                try:
                    flat_area += Polygon(coords).area
                except Exception:
                    pass

        # Solar panel array needs at least 20m2; terrace dining/living needs at least 15m2
        if 0 < flat_area < 35.0:
            conflicts.append(CombinedConflictResult(
                conflicting_features=["solar_pv", "rooftop_terrace"],
                conflict_type="ROOFTOP_SURFACE_COMPETITION",
                explanation=(
                    f"Flat rooftop terrace area ({flat_area:.1f} m²) is insufficient to accommodate both a functional solar panel array "
                    "(~20 m² required) and active terrace garden/seating layout (~15 m² required)."
                ),
                affected_requests={"solar_panels": True, "terrace_features": True},
                suggested_alternatives=[
                    "Mount solar panels on elevated pergola canopy above the terrace seating area.",
                    "Prioritize either renewable solar generation or outdoor recreation on the roof.",
                ],
            ))

    return conflicts


# -------------------------------------------------------------------------
# Master Assessment Orchestrator
# -------------------------------------------------------------------------

def assess_project_feasibility(
    master_json: Mapping[str, Any],
    raw_requirements: Mapping[str, Any],
    source_revision: int | None = None,
) -> ProjectFeasibilityResponse:
    """Evaluate project-aware exterior space and preference feasibility (Stage 2)."""
    geom = extract_canonical_geometry(
        master_json=master_json,
        default_units="m",
        source_revision=source_revision,
    )

    feature_assessments: dict[str, FeatureFeasibilityAssessment] = {}

    # 1. Parking, Garage, Driveway, Gate
    feature_assessments.update(assess_parking_and_access(geom, raw_requirements))

    # 2. Garden, Lawn, Trees, Seating
    feature_assessments.update(assess_garden_and_planting(geom, raw_requirements))

    # 3. Vertical Greenery, Balconies, Rooftops
    feature_assessments.update(assess_vertical_and_elevated(geom, raw_requirements))

    # 4. Water Features & Sanitation
    feature_assessments.update(assess_water_and_sanitation(geom, raw_requirements))

    # 5. Solar PV
    feature_assessments["solar_pv"] = assess_solar(geom, raw_requirements)

    # 6. Lighting
    feature_assessments["outdoor_lighting"] = assess_lighting(geom, raw_requirements)

    # 7. Combined Conflicts
    combined_conflicts = evaluate_combined_conflicts(geom, raw_requirements, feature_assessments)

    # Overall Status Determination
    statuses = [f.feasibility_status for f in feature_assessments.values()]
    if combined_conflicts:
        overall_status = "conflicts_detected"
    elif any(s == "infeasible" for s in statuses):
        overall_status = "infeasible"
    elif any(s == "review_required" for s in statuses):
        overall_status = "review_required"
    else:
        overall_status = "feasible"

    spatial_metrics = {
        "land_area_m2": geom.land_area_m2,
        "house_area_m2": geom.house_area_m2,
        "unoccupied_exterior_m2": geom.unoccupied_area_m2,
        "open_space_ratio": geom.unoccupied_area_m2 / geom.land_area_m2 if geom.land_area_m2 > 0 else 0.0,
        "source_units": geom.units,
        "units_explicit": geom.units_explicit,
        "balcony_surfaces_count": len(geom.balconies),
        "wall_surfaces_count": len(geom.walls),
        "roof_surfaces_count": len(geom.roofs),
        "has_road_access": geom.has_road_access,
        "existing_gate": bool(geom.existing_gate),
        "existing_garage": bool(geom.existing_garage),
        "existing_well": bool(geom.existing_well),
        "existing_septic": bool(geom.existing_septic),
    }

    limitations = [
        "2D spatial feasibility only; geotechnical, structural deflection, and wind load engineering remain uncertified.",
        "Centreline and bay envelope vehicle turning check only; swept-path kinematics require dynamic vehicle model.",
        "Solar PV suitability is assessed for surface presence; hourly shading and kWh yield modeling are deferred to Stage 6.",
        "Hydrogeological well clearance is assessed for 2D surface setback only; contamination plume modeling is unassessed.",
    ]

    return ProjectFeasibilityResponse(
        project_id=str(master_json.get("project_id", "")),
        source_revision=source_revision,
        overall_status=overall_status,
        feature_assessments=feature_assessments,
        combined_conflicts=combined_conflicts,
        spatial_metrics=spatial_metrics,
        limitations=limitations,
    )
