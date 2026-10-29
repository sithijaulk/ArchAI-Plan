from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Sequence

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from .exceptions import ELIAError
from .rule_repository import elia_rules, vegetation_catalog


class VegetationResult(list):
    """Subclass of list carrying applied concept rules and unmet reasons while remaining fully compatible as a list."""
    def __init__(self, nodes: Sequence[Mapping[str, Any]], concept_rules: Sequence[str] | None = None, unmet_reasons: Sequence[str] | None = None):
        super().__init__(nodes)
        self.concept_rules = list(concept_rules or [])
        self.unmet_reasons = list(unmet_reasons or [])

    @property
    def nodes(self) -> list:
        return list(self)


def _calculate_afternoon_sun_score(point: Point, shadows: Sequence[Mapping[str, Any]]) -> float | None:
    afternoon_start = int(elia_rules()["vegetation"]["afternoon_start_hour"])
    afternoon = [
        sample for sample in shadows
        if int(str(sample.get("timestamp", "T12:")).split("T")[-1][:2]) >= afternoon_start
    ]
    usable = [sample for sample in afternoon if sample.get("status") == "estimated" and sample.get("geometry")]
    if not usable:
        return None
    shaded = 0
    for sample in usable:
        shadow_polygon = sample.get("geometry", {}).get("coordinates", [[]])[0]
        if shadow_polygon:
            from shapely.geometry import Polygon
            if Polygon(shadow_polygon).covers(point):
                shaded += 1
    return 1.0 - shaded / len(usable)


def _afternoon_sun_score(point: Point, shadows: Sequence[Mapping[str, Any]]) -> float | None:
    return _calculate_afternoon_sun_score(point, shadows)


def _score_plant_entry(
    entry: Mapping[str, Any],
    sun_score: float | None,
    water_avail: str | None,
    maint_pref: str | None,
    climate_zone: str | None,
    preferred_ids: Sequence[str],
    accepted_alternative_ids: Sequence[str] = (),
) -> float:
    score = 1.0

    # Plant ID preference & accepted alternatives
    veg_id = entry.get("vegetation_id", "")
    if veg_id in accepted_alternative_ids:
        score += 10.0
    elif veg_id in preferred_ids:
        score += 50.0

    # Sunlight match - only score if sunlight evidence is available
    if sun_score is not None:
        sun_req = entry.get("sun_requirement", "adaptable")
        if sun_req == "full_sun":
            score += 2.0 if sun_score >= 0.5 else -1.5
        elif sun_req == "full_shade":
            score += 2.0 if sun_score <= 0.4 else -1.5
        elif sun_req == "partial_shade":
            score += 2.0 if 0.25 <= sun_score <= 0.75 else 0.0

    # Water demand match
    water_demand = entry.get("water_demand", "moderate")
    if water_avail == "limited":
        if water_demand == "low":
            score += 2.5
        elif water_demand == "high":
            score -= 3.0
    elif water_avail in {"irrigation_available", "regular"}:
        if water_demand in {"moderate", "high"}:
            score += 1.0

    # Maintenance level match
    maint_level = entry.get("maintenance_level", "unverified")
    if maint_pref == "low":
        if maint_level == "low":
            score += 2.5
        elif maint_level == "high":
            score -= 2.0
    elif maint_pref == "high":
        if maint_level == "high":
            score += 1.5

    # Climate zone match
    if climate_zone and climate_zone != "unknown":
        climates = entry.get("climate_suitability", [])
        if climate_zone in climates:
            score += 2.0
        elif climates and climate_zone not in climates:
            score -= 2.0

    return score


def place_vegetation(
    residual: BaseGeometry,
    land: BaseGeometry,
    blocked: BaseGeometry,
    requirements: Mapping[str, Any],
    shadows: Sequence[Mapping[str, Any]],
    locked_nodes: Sequence[Mapping[str, Any]] | None = None
) -> VegetationResult:
    """Place vegetation nodes based on geometry, solar exposure, climate, water, and concept rules.
    
    Returns:
        VegetationResult containing placed node dicts and concept_rules applied.
    """
    if residual is None or residual.is_empty:
        return VegetationResult([], [])

    if locked_nodes is None:
        locked_nodes = requirements.get("locked_features") or []

    landscape = requirements.get("landscape", {})
    if not (
        landscape.get("garden_required") or
        landscape.get("preferred_vegetation_categories") or
        landscape.get("shade_tree_preference") or
        landscape.get("trees_required") or
        landscape.get("tree_count") or
        landscape.get("tree_quantity") or
        landscape.get("accepted_plant_alternatives") or
        locked_nodes
    ):
        return VegetationResult([], [])

    catalogue_entries = vegetation_catalog()["entries"]
    rules = elia_rules()["vegetation"]
    concept_rules_applied: list[str] = []

    # Requirements preferences
    water_avail = requirements.get("water_availability") or landscape.get("water_availability")
    maint_pref = requirements.get("maintenance_preference") or landscape.get("maintenance_preference")
    if not maint_pref and landscape.get("low_maintenance_preference") is True:
        maint_pref = "low"
    climate_zone = requirements.get("climate_zone") or landscape.get("climate_zone")

    preferred_ids = set(landscape.get("preferred_plant_ids", []) or requirements.get("preferred_plant_ids", []))
    avoided_ids = set(landscape.get("plant_ids_to_avoid", []))
    avoided_categories = set(landscape.get("vegetation_to_avoid", []))

    # Accepted Greeny alternatives for ground/container placement
    raw_alts = list(landscape.get("accepted_plant_alternatives") or requirements.get("accepted_plant_alternatives") or [])
    accepted_ids = {
        str(a.get("alternative_plant_id") if isinstance(a, Mapping) else getattr(a, "alternative_plant_id", ""))
        for a in raw_alts
        if (isinstance(a, Mapping) and a.get("placement_type") in {"ground", "container"})
        or getattr(a, "placement_type", "") in {"ground", "container"}
    }
    accepted_ids.discard("")

    # Concept influence on target density and category mix
    concept = str(requirements.get("design_style") or "contemporary").lower()
    density = str(landscape.get("greenery_density", requirements.get("greenery_level", "medium"))).lower()
    explicit_density = bool(
        requirements.get("explicit_greenery_density")
        or landscape.get("explicit_greenery_density")
    )
    targets = dict(rules["density_targets"])

    # Precedence: 1. Physical constraints, 2. Explicit user requirements, 3. Concept defaults.
    # An explicit density choice must NOT be overridden by concept defaults.
    if not explicit_density:
        if concept in {"minimalist", "minimalistic"}:
            density = "low"
            concept_rules_applied.append("Minimalistic concept: restricted planting density to preserve expansive open ground")
        elif concept == "greeny":
            density = "high"
            concept_rules_applied.append("Greeny concept: elevated density target to foster rich canopy layers")

    target_count = targets.get(density, targets["medium"])
    if requirements.get("landscape_priority") == "maximum_open_space":
        target_count = min(target_count, targets["low"])
    elif requirements.get("landscape_priority") == "maximum_greenery":
        target_count = max(target_count, targets["high"])

    nodes: list[dict[str, Any]] = []
    occupied_obstacles = blocked
    used_ids: set[str] = set()

    # 1. Process Locked Vegetation Nodes First (validate coordinates, finite radius, pairwise conflicts)
    if locked_nodes:
        for locked in locked_nodes:
            cat = str(locked.get("category") or locked.get("feature_type") or "vegetation").lower()
            if cat in {"seating", "outdoor_seating", "dining", "light", "luminaire", "lighting", "fixture"}:
                continue
            jid = str(locked.get("json_id") or "").strip()
            if not jid:
                raise ELIAError("ELIA_INVALID_LOCKED_FEATURE", "Locked feature missing valid identifier.")
            pos = locked.get("position")
            if not (isinstance(pos, (list, tuple)) and len(pos) == 2):
                raise ELIAError("ELIA_INVALID_LOCKED_FEATURE", f"Locked feature '{jid}' has invalid position.")
            try:
                px, py = float(pos[0]), float(pos[1])
            except (TypeError, ValueError) as exc:
                raise ELIAError("ELIA_INVALID_LOCKED_FEATURE", f"Locked feature '{jid}' coordinates must be numeric.") from exc
            if not (isfinite(px) and isfinite(py)):
                raise ELIAError("ELIA_INVALID_LOCKED_FEATURE", f"Locked feature '{jid}' coordinates must be finite.")

            raw_radius = locked.get("canopy_radius_m", 1.0)
            try:
                radius = float(raw_radius)
            except (TypeError, ValueError) as exc:
                raise ELIAError("ELIA_INVALID_LOCKED_FEATURE", f"Locked feature '{jid}' radius must be numeric.") from exc
            if radius <= 0 or not isfinite(radius):
                raise ELIAError("ELIA_INVALID_LOCKED_FEATURE", f"Locked feature '{jid}' radius must be positive and finite.")

            pt = Point(px, py)
            canopy = pt.buffer(radius)

            # Check boundary and obstacle conflicts for locked node (including against previously placed locks)
            if not land.covers(canopy) or not residual.covers(pt):
                raise ELIAError(
                    "ELIA_LOCKED_FEATURE_CONFLICT",
                    f"Locked feature '{jid}' at ({px:.2f}, {py:.2f}) falls outside permissible land boundary."
                )
            if canopy.intersects(occupied_obstacles):
                raise ELIAError(
                    "ELIA_LOCKED_FEATURE_CONFLICT",
                    f"Locked feature '{jid}' conflicts with boundary, obstacle, or prior locked feature."
                )

            locked_entry = dict(locked)
            locked_entry["locked"] = True
            locked_entry["position"] = [px, py]
            locked_entry["canopy_radius_m"] = radius
            nodes.append(locked_entry)
            used_ids.add(jid)
            occupied_obstacles = occupied_obstacles.union(canopy)

    # 2. Filter Candidate Plant Entries (Honor exclusions strictly without fallback)
    available_catalog = [
        e for e in catalogue_entries
        if e.get("vegetation_id") not in avoided_ids and e.get("category") not in avoided_categories
    ]
    if not available_catalog:
        exclusion_msg = "Plant exclusions: All catalogue entries excluded by user preferences; no new vegetation placed."
        concept_rules_applied.append(exclusion_msg)
        return VegetationResult(nodes, concept_rules_applied, unmet_reasons=[exclusion_msg])

    # Candidate Grid Search
    min_x, min_y, max_x, max_y = residual.bounds
    step = float(rules["candidate_grid_spacing_m"])
    estimated_cells = ((max_x - min_x) / step) * ((max_y - min_y) / step)
    if estimated_cells > elia_rules()["access"].get("max_grid_cells", 200000):
        raise ELIAError("ELIA_PLANNING_LIMIT_EXCEEDED", "Search limit exhausted for vegetation placement.")

    candidates: list[Point] = []
    y = min_y + step / 2
    while y < max_y:
        x = min_x + step / 2
        while x < max_x:
            point = Point(x, y)
            if residual.covers(point) and not occupied_obstacles.buffer(0.05).covers(point):
                candidates.append(point)
            x += step
        y += step

    candidates.sort(key=lambda pt: (-(_calculate_afternoon_sun_score(pt, shadows) or 0.0), pt.y, pt.x))

    # Remaining slots to fulfill (only if eligible plants exist)
    remaining_count = max(0, target_count - len(nodes)) if available_catalog else 0
    preferred_categories = landscape.get("preferred_vegetation_categories") or (
        ["shade_tree", "small_tree", "palm_tree", "flowering_tree", "shrub"] if (landscape.get("trees_required") or landscape.get("shade_tree_preference")) else ["shrub", "ground_cover", "small_tree"]
    )

    for index in range(remaining_count):
        preferred_cat = preferred_categories[index % len(preferred_categories)]
        pref_matches = [e for e in available_catalog if e.get("vegetation_id") in preferred_ids]
        cat_matches = [e for e in available_catalog if e.get("category") == preferred_cat]
        matching_entries = pref_matches + [e for e in cat_matches if e not in pref_matches]
        if not matching_entries:
            matching_entries = available_catalog

        best_candidate: Point | None = None
        best_entry: dict[str, Any] | None = None
        best_score = -9999.0

        # Compare across candidate points rather than terminating on first feasible point
        search_candidates = candidates
        for pt in search_candidates:
            sun = _calculate_afternoon_sun_score(pt, shadows)
            for entry in matching_entries:
                cat = entry.get("category", preferred_cat)
                envelope = rules["generic_planning_envelopes_m"].get(cat, {"height": 2.0, "canopy_radius": 1.0, "clearance": 1.0})
                radius = float(entry.get("canopy_radius_m") or envelope["canopy_radius"])
                canopy = pt.buffer(radius)

                # Check containment & obstacle clearance
                if not land.covers(canopy) or not residual.covers(canopy) or canopy.intersects(occupied_obstacles):
                    continue

                # Spacing against existing nodes
                min_spacing = float(entry.get("minimum_spacing_m") or rules["minimum_spacing_m"].get(cat, radius * 2))
                if any(pt.distance(Point(n["position"])) < max(min_spacing, radius + float(n.get("canopy_radius_m", 1.0))) for n in nodes):
                    continue

                # Root clearance check against house and utilities
                raw_rc = entry.get("root_clearance_m")
                root_clearance = float(raw_rc) if raw_rc is not None else 1.0
                if pt.buffer(root_clearance).intersects(blocked):
                    continue

                entry_score = _score_plant_entry(
                    entry, sun, water_avail, maint_pref, climate_zone, preferred_ids, accepted_ids
                )
                if entry_score > best_score:
                    best_score = entry_score
                    best_candidate = pt
                    best_entry = entry

        if best_candidate is None or best_entry is None:
            continue

        cat = best_entry.get("category", preferred_cat)
        envelope = rules["generic_planning_envelopes_m"].get(cat, {"height": 2.0, "canopy_radius": 1.0})
        radius = float(best_entry.get("canopy_radius_m") or envelope["canopy_radius"])
        height = float(best_entry.get("mature_height_m") or envelope["height"])
        sun_score = _calculate_afternoon_sun_score(best_candidate, shadows)

        # Suitability narrative
        is_verified = bool(best_entry.get("verified_species_data", False))
        if is_verified:
            sun_text = f"Sunlight exposure {sun_score * 100:.0f}%" if sun_score is not None else "Sunlight exposure unmeasured/unknown"
            suitability_reason = (
                f"Species '{best_entry.get('scientific_name') or best_entry.get('display_name')}': "
                f"{sun_text}, Water need '{best_entry.get('water_demand', 'unknown')}', "
                f"Maintenance '{best_entry.get('maintenance_level', 'unknown')}'."
            )
        else:
            suitability_reason = "Procedural planning envelope; species suitability not assessed."

        # Unique ID generation preventing collision with locked features
        node_num = len(nodes) + 1
        node_id = f"{cat.upper()}_{node_num:03d}"
        while node_id in used_ids:
            node_num += 1
            node_id = f"{cat.upper()}_{node_num:03d}"
        used_ids.add(node_id)

        node_dict = {
            "json_id": node_id,
            "category": cat,
            "plant_id": best_entry.get("vegetation_id"),
            "display_name": best_entry.get("display_name"),
            "scientific_name": best_entry.get("scientific_name"),
            "is_preferred": best_entry.get("vegetation_id") in preferred_ids,
            "position": [round(best_candidate.x, 3), round(best_candidate.y, 3)],
            "height_m": height,
            "canopy_radius_m": radius,
            "root_clearance_m": float(best_entry.get("root_clearance_m") or 1.0) if best_entry.get("root_clearance_m") is not None else 1.0,
            "height_basis": (
                "verified_botanical_mature_dimensions"
                if is_verified else
                "configurable_procedural_planning_envelope_not_botanical_data"
            ),
            "solar_suitability": round(sun_score, 3) if sun_score is not None else None,
            "exposure_status": "estimated" if sun_score is not None else "unknown",
            "water_demand": best_entry.get("water_demand", "unknown"),
            "maintenance_level": best_entry.get("maintenance_level", "unverified"),
            "validation": {"inside_land": True, "outside_driveway_and_utilities": True},
            "render": {"asset_id": best_entry.get("render_asset_id", "shrub_generic_01"), "visible": True},
            "verified_species_data": is_verified,
            "source_reference": best_entry.get("source_reference"),
            "suitability_explanation": suitability_reason,
            "locked": False,
        }

        nodes.append(node_dict)
        occupied_obstacles = occupied_obstacles.union(best_candidate.buffer(radius))
        candidates.remove(best_candidate)

    return VegetationResult(nodes, concept_rules_applied)

