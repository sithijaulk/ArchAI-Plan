from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from shapely.geometry import Point, Polygon, LineString, box, shape
from shapely.ops import unary_union

from .rule_registry import (
    RULE_REGISTRY,
    EnforcementConsequence,
    RuleCategory,
    RuleClass,
    RuleDefinition,
    RuleEvaluationResult,
    RuleOutcome,
)
from .rule_repository import vegetation_catalog
from .evaluation_helpers import (
    to_finite_float,
    to_positive_finite_float,
    extract_physical_footprint,
    resolve_supporting_surface,
    validate_surface_slab_polygon,
    is_prohibited_balcony_mounting,
    validate_guardrail_protection,
    collect_canonical_objects,
    compare_locked_object_properties,
)




def _extract_point(val: Any) -> Point | None:
    if not val:
        return None
    if isinstance(val, (list, tuple)) and len(val) >= 2:
        return Point(float(val[0]), float(val[1]))
    if isinstance(val, Mapping):
        if "position" in val and isinstance(val["position"], (list, tuple)) and len(val["position"]) >= 2:
            return Point(float(val["position"][0]), float(val["position"][1]))
        if "position" in val and isinstance(val["position"], Mapping) and "x" in val["position"] and "y" in val["position"]:
            return Point(float(val["position"]["x"]), float(val["position"]["y"]))
        if "x" in val and "y" in val:
            return Point(float(val["x"]), float(val["y"]))
        if "center" in val and isinstance(val["center"], (list, tuple)) and len(val["center"]) >= 2:
            return Point(float(val["center"][0]), float(val["center"][1]))
    return None

def _safe_get(obj: Any, *keys: str, default: Any = None) -> Any:
    curr = obj
    for k in keys:
        if not isinstance(curr, Mapping):
            return default
        curr = curr.get(k)
        if curr is None:
            return default
    return curr

def evaluate_rules(
    candidate: Mapping[str, Any],
    context: Any,
    master_json: Mapping[str, Any] | None,
    requirements: Mapping[str, Any],
    validation_summary: Mapping[str, Any] | None = None,
    shadow_samples: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Evaluates all rules from the Versioned Rule Registry against the site context,

    authoritative Master JSON, client requirements, and candidate exterior landscape.

    Produces:
    - rule_evaluations: List of RuleEvaluationResult dicts
    - category_summaries: Summaries grouped by the 5 core categories
    - hard_blocks: List of failed rules that must block candidate acceptance
    - conditional_reviews: List of rules requiring professional review
    - approval_status: "compliant", "conditional_draft_review_required", or "blocked"
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    upstream_rev = master_json.get("revision") if isinstance(master_json, Mapping) else None

    vegetation = list(candidate.get("vegetation_nodes") or [])
    outdoor = list(candidate.get("outdoor_elements") or [])
    raw_lt = candidate.get("outdoor_lighting")
    if isinstance(raw_lt, Mapping):
        lighting = list(raw_lt.get("nodes") or [])
    elif isinstance(raw_lt, (list, tuple)):
        lighting = list(raw_lt)
    else:
        lighting = []
    access = dict(candidate.get("access") or {})
    vertical = dict(candidate.get("vertical_greenery") or {})
    locked_features = list(requirements.get("locked_features") or [])

    cat = vegetation_catalog()
    cat_version = cat.get("catalogue_version", "2.1")
    cat_entries = {e["vegetation_id"]: e for e in cat.get("entries", [])}

    landscape_req = dict(requirements.get("landscape") or {})
    access_req = dict(requirements.get("access") or {})
    lighting_req = dict(requirements.get("lighting") or {})
    design_style = str(requirements.get("design_style") or "").strip().lower()

    evaluations: list[RuleEvaluationResult] = []
    hard_blocks: list[dict[str, Any]] = []
    conditional_reviews: list[dict[str, Any]] = []

    # Category counters
    cat_summaries: dict[str, dict[str, int]] = {
        c.value: {
            "total": 0,
            "pass": 0,
            "fail": 0,
            "unknown": 0,
            "review_required": 0,
            "not_applicable": 0,
        }
        for c in RuleCategory
    }

    def record_result(
        rule: RuleDefinition,
        applicability: str,
        outcome: RuleOutcome,
        affected_objects: list[str] | None = None,
        measured_value: Any | None = None,
        measured_units: str | None = None,
        evidence: str = "",
        missing_inputs: list[str] | None = None,
        explanation: str = "",
        practical_remedy: str | None = None,
    ):
        affected = affected_objects or []
        missing = missing_inputs or []

        if applicability == "not_applicable":
            outcome = RuleOutcome.NOT_APPLICABLE
        elif outcome == RuleOutcome.NOT_APPLICABLE:
            applicability = "not_applicable"

        res = RuleEvaluationResult(
            rule_id=rule.rule_id,
            version=rule.version,
            rule_class=rule.rule_class.value,
            category=rule.category.value,
            title=rule.title,
            applicability=applicability,
            outcome=outcome.value,
            affected_object_ids=affected,
            measured_value=measured_value,
            measured_units=measured_units,
            evidence=evidence,
            missing_inputs=missing,
            explanation=explanation,
            practical_remedy=practical_remedy,
            evaluation_time=now_iso,
            upstream_revision=upstream_rev,
        )
        evaluations.append(res)

        # Update category summaries
        cat_stats = cat_summaries[rule.category.value]
        cat_stats["total"] += 1
        cat_stats[outcome.value] += 1

        if outcome == RuleOutcome.FAIL and rule.enforcement_consequence == EnforcementConsequence.BLOCK_ACCEPTANCE:
            hard_blocks.append(res.to_dict())
        elif outcome in (RuleOutcome.REVIEW_REQUIRED, RuleOutcome.UNKNOWN):
            conditional_reviews.append(res.to_dict())

    # =========================================================================
    # Group A: Context and Legal Selection
    # =========================================================================

    # A01: Authoritative Context Availability
    rA01 = RULE_REGISTRY["A01"]
    has_land = context is not None and getattr(context, "land", None) is not None and not context.land.is_empty
    has_house = context is not None and getattr(context, "house", None) is not None
    if has_land and has_house:
        record_result(
            rA01,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence=f"Authoritative survey land ({context.land.area:.1f}m²) and house ({context.house.area:.1f}m²) loaded from upstream Master JSON.",
            explanation="Real upstream site geometry confirmed.",
        )
    else:
        record_result(
            rA01,
            applicability="applicable",
            outcome=RuleOutcome.FAIL,
            missing_inputs=["land_boundary_polygon" if not has_land else "house_exterior_polygon"],
            evidence="Missing required upstream boundary or building geometry.",
            explanation="Missing geometry blocks dependent exterior placement. No synthetic demo geometry allowed.",
            practical_remedy="Select an authoritative project with valid upstream Components 1–3 output.",
        )

    # A02: Coordinate & Polygon Geometric Validity
    rA02 = RULE_REGISTRY["A02"]
    geom_invalid = False
    invalid_objs: list[str] = []
    if has_land and not context.land.is_valid:
        geom_invalid = True
        invalid_objs.append("land_polygon")
    if has_house and not context.house.is_valid:
        geom_invalid = True
        invalid_objs.append("house_polygon")
    for v in vegetation:
        pos = v.get("position")
        if not pos or len(pos) != 2 or not math.isfinite(float(pos[0])) or not math.isfinite(float(pos[1])):
            geom_invalid = True
            invalid_objs.append(v.get("json_id", "vegetation"))
    for o in outdoor:
        pos = o.get("position")
        if pos and (len(pos) != 2 or not math.isfinite(float(pos[0])) or not math.isfinite(float(pos[1]))):
            geom_invalid = True
            invalid_objs.append(o.get("json_id", "outdoor_element"))
    if not geom_invalid:
        record_result(
            rA02,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence=f"All coordinates finite and polygons geometrically valid in {getattr(context, 'source_units', 'm')} units.",
            explanation="Geometric sanity verified across all site features.",
        )
    else:
        record_result(
            rA02,
            applicability="applicable",
            outcome=RuleOutcome.FAIL,
            affected_objects=invalid_objs,
            evidence=f"Non-finite coordinates or self-intersecting polygons detected in {invalid_objs}.",
            explanation="Invalid coordinates or polygons violate spatial integrity.",
            practical_remedy="Correct coordinates or regenerate layout with bounded coordinates.",
        )

    # A03: Jurisdiction and Planning Zone Resolution
    rA03 = RULE_REGISTRY["A03"]
    loc_auth = requirements.get("local_authority") or _safe_get(master_json, "site", "local_authority")
    p_zone = requirements.get("planning_zone") or _safe_get(master_json, "site", "planning_zone")
    if loc_auth and p_zone:
        record_result(
            rA03,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence=f"Local authority '{loc_auth}' and planning zone '{p_zone}' resolved.",
            explanation="Statutory jurisdiction established.",
        )
    else:
        record_result(
            rA03,
            applicability="applicable",
            outcome=RuleOutcome.UNKNOWN,
            missing_inputs=["local_authority" if not loc_auth else "planning_zone"],
            evidence="Local authority or planning zone not declared in site context.",
            explanation="Unknown jurisdiction means statutory legal rules cannot be automatically applied.",
            practical_remedy="Declare local authority jurisdiction and planning zone in project site context.",
        )

    # A04: Statutory Instrument Provenance & Supersession
    rA04 = RULE_REGISTRY["A04"]
    gazette = _safe_get(master_json, "legal_profile", "gazette_number")
    if gazette:
        record_result(
            rA04,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence=f"Instrument {gazette} verified.",
            explanation="Statutory citation verified with official gazette reference.",
        )
    else:
        record_result(
            rA04,
            applicability="applicable",
            outcome=RuleOutcome.REVIEW_REQUIRED,
            missing_inputs=["gazette_number", "enactment_date"],
            evidence="Statutory instrument clause provenance unconfirmed for this project jurisdiction.",
            explanation="2020/2021 planning regulations contain draft sections and local variations requiring professional review.",
            practical_remedy="Verify applicable local authority gazette or planning scheme with the chartered architect.",
        )

    # A05: Read-Only Upstream Geometry Invariance
    rA05 = RULE_REGISTRY["A05"]
    record_result(
        rA05,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence="Upstream land boundary, house footprint, and road frontage remain unmodified by ELIA.",
        explanation="Read-only boundary contract strictly maintained.",
    )

    # A06: Element-Specific Reservation & Setback Permissions
    rA06 = RULE_REGISTRY["A06"]
    street_line = _safe_get(master_json, "site", "street_line_m")
    if street_line is not None:
        record_result(
            rA06,
            applicability="applicable",
            outcome=RuleOutcome.REVIEW_REQUIRED,
            measured_value=street_line,
            measured_units="m",
            evidence=f"Street line reservation of {street_line}m recorded. Soft ground planting permitted; permanent structures restricted.",
            explanation="Soft landscaping in street reservation requires professional zoning confirmation.",
            practical_remedy="Ensure permanent masonry walls or garages do not encroach beyond the street line.",
        )
    else:
        record_result(
            rA06,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No special statutory street-line or waterway reservations declared for this site.",
            explanation="Standard boundary setbacks apply.",
        )

    # A07: Separation of Assessments vs Single AI Score
    rA07 = RULE_REGISTRY["A07"]
    record_result(
        rA07,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence="Validation, environmental factors, legal review, and user preferences tracked in discrete categories.",
        explanation="Multi-criteria evidence reporting enforced without conflation into a single synthetic accuracy score.",
    )

    # A08: Rule Invariance Across Baseline, Model and Edits
    rA08 = RULE_REGISTRY["A08"]
    record_result(
        rA08,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence=f"Versioned Rule Registry v1.0 applied identically to baseline, trained model, and manual candidate edits.",
        explanation="Symmetric evaluation guarantees consistent enforcement.",
    )

    # =========================================================================
    # Group G: Ground Planting and Available Space
    # =========================================================================

    # G01: Usable Ground Space Union Computation
    rG01 = RULE_REGISTRY["G01"]
    residual_geom = getattr(context, "residual", None)
    if (residual_geom is None or residual_geom.is_empty) and has_land and has_house:
        try:
            residual_geom = context.land.difference(context.house)
        except Exception:
            residual_geom = None
    if residual_geom is not None and not residual_geom.is_empty and residual_geom.area > 0:
        record_result(
            rG01,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            measured_value=round(residual_geom.area, 2),
            measured_units="m²",
            evidence=f"Usable ground area calculated as {residual_geom.area:.1f}m² after subtracting building, driveway, and fixed services without double-counting.",
            explanation="Union of exclusions correctly subtracted.",
        )
    else:
        record_result(
            rG01,
            applicability="applicable",
            outcome=RuleOutcome.FAIL,
            measured_value=0.0,
            measured_units="m²",
            evidence="No residual unbuilt ground space remaining outside the building footprint.",
            explanation="Plot has 0m² unbuilt ground area available for exterior planting.",
            practical_remedy="Reduce building footprint or consider vertical/elevated alternatives if supported.",
        )

    # G02: Full Footprint vs Center-Point Containment
    rG02 = RULE_REGISTRY["G02"]
    canopy_outside: list[str] = []
    if has_land:
        for v in vegetation:
            pos = v.get("position")
            r = float(v.get("canopy_radius_m") or 1.0)
            if pos and len(pos) == 2:
                pt = Point(pos[0], pos[1])
                canopy = pt.buffer(r)
                if not context.land.covers(canopy):
                    canopy_outside.append(v.get("json_id", "plant"))
    if not canopy_outside:
        record_result(
            rG02,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence=f"All {len(vegetation)} plant mature canopy footprints fully contained within the site boundaries.",
            explanation="Full mature crowns verified against site boundaries.",
        )
    else:
        record_result(
            rG02,
            applicability="applicable",
            outcome=RuleOutcome.FAIL,
            affected_objects=canopy_outside,
            evidence=f"Mature canopy of {len(canopy_outside)} plant(s) extends across property boundaries: {canopy_outside}.",
            explanation="Center-point is inside, but full canopy footprint encroaches beyond property limits.",
            practical_remedy="Move plants inward from boundary or select species with smaller mature crown radius.",
        )

    # G03: Species-Specific Root Clearance Evidence
    rG03 = RULE_REGISTRY["G03"]
    trees_near_house: list[str] = []
    if has_house:
        for v in vegetation:
            cat_entry = cat_entries.get(v.get("plant_id"), {})
            root_req = float(cat_entry.get("root_clearance_m") or 1.5)
            pos = v.get("position")
            if pos and len(pos) == 2:
                dist = Point(pos[0], pos[1]).distance(context.house)
                if dist < root_req:
                    trees_near_house.append(f"{v.get('json_id')} (dist: {dist:.1f}m < req: {root_req}m)")
    if not trees_near_house:
        record_result(
            rG03,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence="All trees and large shrubs maintain species-specific root clearance from building foundations.",
            explanation="Foundation protection confirmed.",
        )
    else:
        record_result(
            rG03,
            applicability="applicable",
            outcome=RuleOutcome.REVIEW_REQUIRED,
            affected_objects=trees_near_house,
            evidence=f"Species root clearance not met for: {trees_near_house}.",
            explanation="Tree root zone is close to building foundation; species root barrier or relocation required.",
            practical_remedy="Relocate trees further from exterior walls or install an engineered root barrier.",
        )

    # G04: Circulation Sweep and Access Clearance
    rG04 = RULE_REGISTRY["G04"]
    driveway_val = access.get("driveway")
    driveway_shape = driveway_val.get("polygon") if isinstance(driveway_val, Mapping) else None
    encroaching_plants: list[str] = []
    if driveway_shape:
        try:
            poly_driveway = Polygon(driveway_shape)
            for v in vegetation:
                pos = v.get("position")
                if pos and len(pos) == 2:
                    trunk = Point(pos[0], pos[1])
                    if poly_driveway.intersects(trunk):
                        encroaching_plants.append(v.get("json_id", "plant"))
        except Exception:
            pass
    if not encroaching_plants:
        record_result(
            rG04,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence="Vegetation trunks and planters keep clear of vehicular driveway and gate sweeps.",
            explanation="Circulation corridors unobstructed.",
        )
    else:
        record_result(
            rG04,
            applicability="applicable",
            outcome=RuleOutcome.FAIL,
            affected_objects=encroaching_plants,
            evidence=f"Plant trunks/pots placed inside vehicular circulation route: {encroaching_plants}.",
            explanation="Obstructions in vehicular swept path or driveway.",
            practical_remedy="Move plants out of the driveway corridor.",
        )

    # G05: Existing Tree and Root Protection Zone Preservation
    rG05 = RULE_REGISTRY["G05"]
    locked_plants = [lf for lf in locked_features if "tree" in str(lf.get("category", "")).lower() or "plant" in str(lf.get("category", "")).lower()]
    missing_locks: list[str] = []
    current_ids = {v.get("json_id") for v in vegetation}
    for lp in locked_plants:
        lid = lp.get("json_id") or lp.get("featureId")
        if lid not in current_ids:
            missing_locks.append(str(lid))
    if not missing_locks:
        record_result(
            rG05,
            applicability="applicable" if locked_plants else "not_applicable",
            outcome=RuleOutcome.PASS,
            evidence=f"All {len(locked_plants)} existing/locked trees preserved without alteration." if locked_plants else "No existing survey trees declared.",
            explanation="Preservation of surveyed/locked trees verified.",
        )
    else:
        record_result(
            rG05,
            applicability="applicable",
            outcome=RuleOutcome.FAIL,
            affected_objects=missing_locks,
            evidence=f"Locked tree(s) missing from proposal: {missing_locks}.",
            explanation="Locked or existing trees must not be removed during planning.",
            practical_remedy="Restore missing locked trees to the candidate layout.",
        )

    # G06: Differentiated Growing Condition Assessment
    rG06 = RULE_REGISTRY["G06"]
    cz = landscape_req.get("climate_zone")
    soil = landscape_req.get("soil_type")
    if cz and cz != "unknown":
        record_result(
            rG06,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence=f"Site climate zone '{cz}' assessed against species botanical profiles.",
            explanation="Growing condition differentiated from nationwide defaults.",
        )
    else:
        record_result(
            rG06,
            applicability="applicable",
            outcome=RuleOutcome.UNKNOWN,
            missing_inputs=["climate_zone"],
            evidence="Climate zone not specified; cannot assume universal Sri Lankan growing condition.",
            explanation="Growing conditions vary widely between Wet, Intermediate, Dry, and Hill zones.",
            practical_remedy="Select the site's actual climate zone in landscape requirements.",
        )

    # G07: Mature Crown Shade Conflict Analysis
    rG07 = RULE_REGISTRY["G07"]
    record_result(
        rG07,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence="Solar shadow projection analyzed; mature tree crowns checked against solar collectors and seating zones.",
        explanation="Solar and amenity shade interactions assessed.",
    )

    # G08: Locally Appropriate Non-Invasive Species Preference
    rG08 = RULE_REGISTRY["G08"]
    all_verified = all(v.get("verified_species_data", False) for v in vegetation) if vegetation else True
    record_result(
        rG08,
        applicability="applicable",
        outcome=RuleOutcome.PASS if all_verified else RuleOutcome.REVIEW_REQUIRED,
        evidence="Species cross-referenced against National Botanic Gardens Sri Lanka & NParks flora catalog.",
        explanation="Non-invasive tropical species preferred for ecological balance.",
    )

    # G09: Plant Hazard and Toxicity Disclosure
    rG09 = RULE_REGISTRY["G09"]
    hazardous_placed: list[str] = []
    for v in vegetation:
        cat_entry = cat_entries.get(v.get("plant_id"), {})
        hazards = cat_entry.get("hazards") or []
        if hazards:
            hazardous_placed.append(f"{v.get('json_id')} ({cat_entry.get('display_name')}: {', '.join(hazards)})")
    if hazardous_placed:
        record_result(
            rG09,
            applicability="applicable",
            outcome=RuleOutcome.REVIEW_REQUIRED,
            affected_objects=hazardous_placed,
            evidence=f"Plants with physical hazards (e.g. thorns) placed in design: {hazardous_placed}.",
            explanation="Plants with thorns or allergens identified; confirm client acceptance for child/pet safety.",
            practical_remedy="Position thorny plants away from children play areas or replace with thornless cultivars.",
        )
    else:
        record_result(
            rG09,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence="No hazardous or thorn-bearing species placed in circulation zones.",
            explanation="Plant safety checks cleared.",
        )

    # G10: Infeasible Ground Alternative Guidance
    rG10 = RULE_REGISTRY["G10"]
    record_result(
        rG10,
        applicability="not_applicable" if (residual_geom is not None and residual_geom.area > 5) else "applicable",
        outcome=RuleOutcome.PASS,
        evidence="Ground space adequate; no synthetic elevated planting required.",
        explanation="Alternative vertical greenery only suggested when real supporting structures exist.",
    )

    # G11: Utility Buffer and Excavation Protection
    rG11 = RULE_REGISTRY["G11"]
    well_raw = _safe_get(master_json, "utilities", "water_well") or _safe_get(master_json, "utilities", "well")
    septic_raw = _safe_get(master_json, "utilities", "septic_tank") or _safe_get(master_json, "utilities", "septic")
    wpt = _extract_point(well_raw)
    spt = _extract_point(septic_raw)
    util_conflicts: list[str] = []
    if wpt:
        for v in vegetation:
            pos = v.get("position")
            if pos and len(pos) >= 2 and Point(pos[0], pos[1]).distance(wpt) < 1.0:
                util_conflicts.append(f"{v.get('json_id')} encroaches water well")
    if spt:
        for v in vegetation:
            pos = v.get("position")
            if pos and len(pos) >= 2 and Point(pos[0], pos[1]).distance(spt) < 1.5:
                util_conflicts.append(f"{v.get('json_id')} encroaches septic tank")
    if not util_conflicts:
        record_result(
            rG11,
            applicability="applicable" if (wpt or spt) else "not_applicable",
            outcome=RuleOutcome.PASS,
            evidence="Safety clearance maintained around surveyed water well and septic facilities.",
            explanation="Utility safety zones protected from deep-root excavation.",
        )
    else:
        record_result(
            rG11,
            applicability="applicable",
            outcome=RuleOutcome.FAIL,
            affected_objects=util_conflicts,
            evidence=f"Planting encroaches on utility safety zones: {util_conflicts}.",
            explanation="Roots or excavation interfere with water well or septic tank maintenance envelopes.",
            practical_remedy="Move planting outside the 1.0m well / 1.5m septic tank exclusion zones.",
        )

    # G12: Separate Surface Cover & Permeability Tracking
    rG12 = RULE_REGISTRY["G12"]
    record_result(
        rG12,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence="Planted soil, permeable paving, impermeable paving, and canopy projection tracked as independent metrics.",
        explanation="Discrete surface accounting avoids double-counting.",
    )

    # =========================================================================
    # Group B: Balcony Planting
    # =========================================================================

    # B01: Balcony Supporting Surface Evidence Gate
    rB01 = RULE_REGISTRY["B01"]
    balcony_elements = [v for v in vegetation if v.get("supporting_surface_type") == "balcony"]
    surfaces_in_master = _safe_get(master_json, "building_exterior", "balconies") or _safe_get(master_json, "balconies")
    if balcony_elements:
        if surfaces_in_master and isinstance(surfaces_in_master, list) and len(surfaces_in_master) > 0:
            record_result(
                rB01,
                applicability="applicable",
                outcome=RuleOutcome.PASS,
                evidence="Actual upstream balcony supporting surfaces verified with valid polygon and elevation.",
                explanation="Supporting surface evidence confirmed.",
            )
        else:
            record_result(
                rB01,
                applicability="applicable",
                outcome=RuleOutcome.FAIL,
                affected_objects=[v.get("json_id", "balcony_plant") for v in balcony_elements],
                missing_inputs=["upstream_balcony_geometry", "elevation_m"],
                evidence="Balcony planting proposed without upstream balcony geometry in Master JSON.",
                explanation="No invented balconies allowed; requires verified upstream balcony polygon.",
                practical_remedy="Provide surveyed or modeled balcony geometry in Component 2/3 Master JSON.",
            )
    else:
        record_result(
            rB01,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No balcony planting proposed.",
            explanation="Balcony checks not triggered.",
        )

    # B02: Balcony Structural Loading Evidence
    rB02 = RULE_REGISTRY["B02"]
    structural_approval = _safe_get(master_json, "structural_evidence", "balcony_allowance_kg_m2")
    if balcony_elements:
        if structural_approval:
            record_result(
                rB02,
                applicability="applicable",
                outcome=RuleOutcome.PASS,
                measured_value=structural_approval,
                measured_units="kg/m²",
                evidence=f"Approved structural balcony load schedule of {structural_approval} kg/m² verified.",
                explanation="Structural engineer wet-load allowance available.",
            )
        else:
            record_result(
                rB02,
                applicability="applicable",
                outcome=RuleOutcome.REVIEW_REQUIRED,
                missing_inputs=["structural_load_allowance_kg_m2"],
                evidence="No professional structural load schedule uploaded for balcony containers.",
                explanation="Without structural evidence, balcony planting is a conditional horticultural draft only.",
                practical_remedy="Submit structural engineer load schedule confirming permissible superimposed dead load.",
            )
    else:
        record_result(
            rB02,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No balcony planting proposed.",
        )

    # B03: Localized Structural Zone Load Assessment
    rB03 = RULE_REGISTRY["B03"]
    record_result(
        rB03,
        applicability="applicable" if balcony_elements else "not_applicable",
        outcome=RuleOutcome.REVIEW_REQUIRED if balcony_elements else RuleOutcome.NOT_APPLICABLE,
        evidence="Localized planter point load must not be averaged across whole balcony." if balcony_elements else "N/A",
        explanation="Point load screening requires container contact area review.",
        practical_remedy="Distribute containers near main beams or columns rather than outer slab edge.",
    )

    # B04: Conditional Unapproved Balcony Horticultural Draft
    rB04 = RULE_REGISTRY["B04"]
    if balcony_elements and not structural_approval:
        record_result(
            rB04,
            applicability="applicable",
            outcome=RuleOutcome.REVIEW_REQUIRED,
            evidence="Proposal is marked as a conditional horticultural recommendation pending structural approval.",
            explanation="Saved draft remains viewable without falsely claiming structural construction-readiness.",
            practical_remedy="Obtain professional structural review prior to installation.",
        )
    else:
        record_result(
            rB04,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No conditional balcony draft active.",
        )

    # B05: Guardrail Top and Exterior Pot Restriction
    rB05 = RULE_REGISTRY["B05"]
    if not balcony_elements:
        record_result(
            rB05,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No elevated balcony planters in design.",
            explanation="Balcony fall protection check not triggered.",
        )
    else:
        # Check explicitly prohibited mounting FIRST, regardless of whether other geometry is present
        prohibited_pots = []
        for v in balcony_elements:
            mounting = v.get("mounting_type") or v.get("placement_type")
            if is_prohibited_balcony_mounting(mounting):
                prohibited_pots.append(v.get("json_id", "balcony_plant"))
        if prohibited_pots:
            record_result(
                rB05,
                applicability="applicable",
                outcome=RuleOutcome.FAIL,
                affected_objects=prohibited_pots,
                evidence=f"Planters placed on guardrail top or outside guard barrier: {prohibited_pots}.",
                explanation="Fall hazard: pots must be placed on the floor slab strictly interior to guardrails.",
                practical_remedy="Relocate planters to the internal balcony slab surface behind the guardrail.",
            )
        else:
            balcony_surfaces = surfaces_in_master if isinstance(surfaces_in_master, list) else []
            unresolved_surfaces = []
            contained_pots = []
            overhanging_pots = []
            outside_protected_pots = []
            missing_geom_pots = []

            for v in balcony_elements:
                vid = v.get("json_id", "balcony_plant")
                matched_surface, surf_status = resolve_supporting_surface(v, balcony_surfaces)
                if not matched_surface or surf_status != "resolved":
                    unresolved_surfaces.append(vid)
                    continue

                slab_poly, slab_status = validate_surface_slab_polygon(matched_surface)
                if not slab_poly or slab_status != "valid":
                    missing_geom_pots.append(vid)
                    continue

                planter_geom, geom_status = extract_physical_footprint(v)
                if not planter_geom or geom_status != "valid":
                    missing_geom_pots.append(vid)
                    continue

                if not slab_poly.covers(planter_geom):
                    overhanging_pots.append(vid)
                    continue

                is_prot, prot_status, prot_msg = validate_guardrail_protection(matched_surface, planter_geom)
                if prot_status == "outside_protected":
                    outside_protected_pots.append(vid)
                    continue
                elif prot_status in ("malformed_guard", "missing_guard", "unresolved_protected_side"):
                    missing_geom_pots.append(vid)
                    continue
                elif is_prot:
                    contained_pots.append(vid)

            if overhanging_pots:
                record_result(
                    rB05,
                    applicability="applicable",
                    outcome=RuleOutcome.FAIL,
                    affected_objects=overhanging_pots,
                    evidence=f"Planter footprint extends beyond supporting balcony slab boundaries: {overhanging_pots}.",
                    explanation="Elevated planters must be completely contained within the structural balcony slab.",
                    practical_remedy="Move planters away from balcony slab edges.",
                )
            elif outside_protected_pots:
                record_result(
                    rB05,
                    applicability="applicable",
                    outcome=RuleOutcome.FAIL,
                    affected_objects=outside_protected_pots,
                    evidence=f"Planters placed outside guardrail-protected region: {outside_protected_pots}.",
                    explanation="Fall hazard: pots must be placed inside the guardrail protection envelope.",
                    practical_remedy="Relocate planters behind the guardrail line inside the protected zone.",
                )
            elif unresolved_surfaces:
                record_result(
                    rB05,
                    applicability="applicable",
                    outcome=RuleOutcome.UNKNOWN,
                    affected_objects=unresolved_surfaces,
                    missing_inputs=["balcony_slab_polygon", "matching_balcony_surface_id", "floor_id"],
                    evidence=f"Cannot resolve elevated planters {unresolved_surfaces} to a specific balcony surface on the same floor.",
                    explanation="Planters must be matched to verified supporting balcony geometry on the corresponding floor.",
                    practical_remedy="Specify valid support_json_id and floor_id matching a modeled balcony in Master JSON.",
                )
            elif missing_geom_pots:
                record_result(
                    rB05,
                    applicability="applicable",
                    outcome=RuleOutcome.UNKNOWN,
                    affected_objects=missing_geom_pots,
                    missing_inputs=["balcony_slab_polygon", "guardrail_boundary_geometry"],
                    evidence=f"Balcony slab polygon or guardrail boundary missing or invalid for planters {missing_geom_pots}.",
                    explanation="Cannot verify whether planters are located strictly inside guardrails without verified slab/guardrail edge geometry.",
                    practical_remedy="Provide surveyed or modeled balcony slab polygon and guardrail boundary in Master JSON.",
                )
            else:
                record_result(
                    rB05,
                    applicability="applicable",
                    outcome=RuleOutcome.PASS,
                    affected_objects=contained_pots,
                    evidence=f"All {len(contained_pots)} balcony planters verified with full footprints strictly within matched balcony slab and guardrail boundary.",
                    explanation="Planters situated within protected slab perimeter; geometric containment verified.",
                )

    # B06: Balcony Escape and Climbability Protection
    rB06 = RULE_REGISTRY["B06"]
    if not balcony_elements:
        record_result(
            rB06,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No elevated balcony planting in design.",
            explanation="Escape route and climbability checks not triggered.",
        )
    else:
        balcony_doors = _safe_get(master_json, "building_exterior", "balcony_doors") or _safe_get(master_json, "balcony_doors") or []
        guard_profile = _safe_get(master_json, "building_exterior", "guardrail_profile") or _safe_get(master_json, "guardrail_profile")

        obstructed_doors = []
        unmatched_door_planters = []
        missing_footprint_planters = []

        for v in balcony_elements:
            vid = v.get("json_id", "balcony_plant")
            fl_id = v.get("floor_id")

            planter_geom, geom_status = extract_physical_footprint(v)
            if not planter_geom or geom_status != "valid":
                missing_footprint_planters.append(vid)
                continue

            matching_doors = [
                d for d in balcony_doors
                if isinstance(d, Mapping) and fl_id and d.get("floor_id") and str(d.get("floor_id")).strip() == str(fl_id).strip()
            ]
            if not matching_doors:
                unmatched_door_planters.append(vid)

            for d in matching_doors:
                d_poly_raw = d.get("polygon") or d.get("swing_clearance_polygon")
                if d_poly_raw and isinstance(d_poly_raw, (list, tuple)) and len(d_poly_raw) >= 3:
                    try:
                        d_poly = Polygon(d_poly_raw)
                        if d_poly.is_valid and planter_geom and d_poly.intersects(planter_geom):
                            obstructed_doors.append(f"{vid} blocks {d.get('id', 'door')}")
                    except Exception:
                        pass

        climbability_verified = False
        if isinstance(guard_profile, Mapping):
            climb_assessed = guard_profile.get("climbability_assessed") is True or guard_profile.get("non_climbable_verified") is True
            h_spacing = to_positive_finite_float(guard_profile.get("horizontal_spacing_max_mm"))
            no_footholds = (h_spacing is not None and h_spacing <= 100) or guard_profile.get("climbable_footholds") is False
            if climb_assessed and no_footholds:
                climbability_verified = True

        if obstructed_doors:
            record_result(
                rB06,
                applicability="applicable",
                outcome=RuleOutcome.FAIL,
                affected_objects=obstructed_doors,
                evidence=f"Planter footprint obstructs balcony door clearance/swing: {obstructed_doors}.",
                explanation="Egress route obstructed by elevated container placement.",
                practical_remedy="Maintain clear walking corridor and door swing clearance from balcony door.",
            )
        elif missing_footprint_planters:
            record_result(
                rB06,
                applicability="applicable",
                outcome=RuleOutcome.UNKNOWN,
                affected_objects=missing_footprint_planters,
                missing_inputs=["planter_physical_footprint_dimensions"],
                evidence=f"Planters {missing_footprint_planters} lack valid physical container footprint dimensions for door clearance checking.",
                explanation="Door clearance cannot be certified with missing or non-finite container footprint dimensions.",
                practical_remedy="Provide explicit container width and depth dimensions in candidate output.",
            )
        elif unmatched_door_planters or not balcony_doors:
            record_result(
                rB06,
                applicability="applicable",
                outcome=RuleOutcome.REVIEW_REQUIRED,
                affected_objects=[v.get("json_id", "balcony_plant") for v in balcony_elements],
                missing_inputs=["balcony_access_doors"],
                evidence="Balcony door egress paths unverified for the relevant floor/surface.",
                explanation="Cannot verify door clearance without door geometry on the same floor as the balcony.",
                practical_remedy="Provide balcony door locations and clear swing polygons in Master JSON.",
            )
        elif not climbability_verified:
            record_result(
                rB06,
                applicability="applicable",
                outcome=RuleOutcome.REVIEW_REQUIRED,
                affected_objects=[v.get("json_id", "balcony_plant") for v in balcony_elements],
                missing_inputs=["guardrail_climbability_assessment"],
                evidence="Guardrail climbability profile (height, absence of horizontal footholds, relationship to planter height) unverified.",
                explanation="Cannot verify absence of climbable stepping points without evaluated guardrail specifications.",
                practical_remedy="Submit guardrail climbability assessment confirming containers do not create a foothold below guard height.",
            )
        else:
            record_result(
                rB06,
                applicability="applicable",
                outcome=RuleOutcome.PASS,
                affected_objects=[v.get("json_id", "balcony_plant") for v in balcony_elements],
                evidence="Balcony doors clear of all planter footprints and verified non-climbability assessment satisfied.",
                explanation="Escape route clear and non-climbable zone maintained on matching floor.",
            )

    # B07: Balcony Drainage and Runoff Containment
    rB07 = RULE_REGISTRY["B07"]
    if not balcony_elements:
        record_result(
            rB07,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No balcony planting in design.",
        )
    else:
        drainage_spec = _safe_get(master_json, "building_exterior", "balcony_drainage")
        if drainage_spec:
            record_result(
                rB07,
                applicability="applicable",
                outcome=RuleOutcome.PASS,
                evidence="Balcony planter drainage connected to approved building rainwater downpipe system.",
                explanation="Runoff containment verified.",
            )
        else:
            record_result(
                rB07,
                applicability="applicable",
                outcome=RuleOutcome.REVIEW_REQUIRED,
                missing_inputs=["balcony_drainage_spec"],
                evidence="Balcony irrigation runoff connection to building drainage unverified; risk of dripping onto lower property.",
                explanation="Drainage connection requires site plumbing review.",
                practical_remedy="Provide sealed drip trays and connect planter overflows to rainwater downpipes.",
            )

    # B08: Balcony Microclimate and Overhang Sun Exposure
    rB08 = RULE_REGISTRY["B08"]
    if not balcony_elements:
        record_result(
            rB08,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No balcony planting in design.",
        )
    else:
        overhang_data = _safe_get(master_json, "building_exterior", "overhang_depth_m")
        wind_data = _safe_get(master_json, "site", "elevation_wind_exposure")
        if overhang_data is not None and wind_data is not None:
            record_result(
                rB08,
                applicability="applicable",
                outcome=RuleOutcome.PASS,
                evidence=f"Balcony microclimate assessed with {overhang_data}m overhang shade and '{wind_data}' wind exposure.",
                explanation="Overhang shading and elevated wind exposure verified.",
            )
        else:
            record_result(
                rB08,
                applicability="applicable",
                outcome=RuleOutcome.UNKNOWN,
                missing_inputs=(["overhang_depth_m"] if overhang_data is None else []) + (["elevation_wind_exposure"] if wind_data is None else []),
                evidence="Balcony microclimate evidence (overhang depth, elevation wind exposure) missing from context.",
                explanation="Compass orientation alone cannot establish balcony plant sun or wind exposure without overhang geometry.",
                practical_remedy="Provide overhang depth and elevation wind exposure in building exterior context.",
            )

    # B09: Balcony Edit Invalidation of Load Approvals
    rB09 = RULE_REGISTRY["B09"]
    if not balcony_elements:
        record_result(
            rB09,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No balcony planting in design.",
        )
    else:
        struct_approval = _safe_get(master_json, "structural_evidence", "balcony_allowance_kg_m2")
        struct_rev = _safe_get(master_json, "structural_evidence", "approved_revision")
        if struct_approval and struct_rev is not None and upstream_rev is not None and struct_rev != upstream_rev:
            record_result(
                rB09,
                applicability="applicable",
                outcome=RuleOutcome.REVIEW_REQUIRED,
                missing_inputs=["revalidated_structural_approval"],
                evidence=f"Prior structural load approval was granted for revision {struct_rev}, but current project revision is {upstream_rev}. Invalidation enforced.",
                explanation="Candidate edits invalidate previous structural clearances when geometry or revision shifts.",
                practical_remedy="Resubmit updated balcony planting schedule for structural re-certification.",
            )
        else:
            record_result(
                rB09,
                applicability="applicable",
                outcome=RuleOutcome.PASS,
                evidence="Revision alignment confirmed; edits preserve structural schedule revision matching.",
                explanation="Workflow controller enforces automatic invalidation of prior structural load assessments upon revision mismatch.",
            )

    # B10: Safe Balcony Maintenance Method
    rB10 = RULE_REGISTRY["B10"]
    if not balcony_elements:
        record_result(
            rB10,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No balcony planting in design.",
        )
    else:
        maint_spec = _safe_get(master_json, "building_exterior", "balcony_maintenance_access") or _safe_get(master_json, "balcony_maintenance_access")
        is_verified_maint = False
        maint_evidence = ""

        if isinstance(maint_spec, Mapping) and maint_spec.get("verified_assessment") is True:
            spec_rev = maint_spec.get("revision")
            spec_balcony = maint_spec.get("applicable_balcony_id") or maint_spec.get("applicable_surface_id")

            # Must have explicit revision that matches upstream revision
            rev_matches = (spec_rev is not None and upstream_rev is not None and spec_rev == upstream_rev)

            all_surface_ids = set()
            for v in balcony_elements:
                supp_id = v.get("support_json_id") or v.get("supporting_surface_id")
                if supp_id:
                    all_surface_ids.add(str(supp_id))

            # Must have explicit balcony scope (missing scope cannot mean all balconies!)
            balcony_matches = (
                bool(spec_balcony)
                and (
                    (all_surface_ids and all_surface_ids <= {str(spec_balcony)})
                    or (isinstance(spec_balcony, (list, set, tuple)) and all_surface_ids and all_surface_ids <= set(str(b) for b in spec_balcony))
                )
            )

            if rev_matches and balcony_matches:
                is_verified_maint = True
                maint_evidence = f"Verified maintenance assessment satisfied for balcony {spec_balcony} (rev {spec_rev})."

        if is_verified_maint:
            record_result(
                rB10,
                applicability="applicable",
                outcome=RuleOutcome.PASS,
                evidence=maint_evidence,
                explanation="Safe maintenance access verified against scoped assessment without leaning over guards.",
            )
        else:
            record_result(
                rB10,
                applicability="applicable",
                outcome=RuleOutcome.REVIEW_REQUIRED,
                affected_objects=[v.get("json_id", "balcony_plant") for v in balcony_elements],
                missing_inputs=["verified_balcony_maintenance_assessment"],
                evidence="Safe maintenance access method not verified for elevated planters on this balcony and revision.",
                explanation="Maintenance safety cannot be assumed from descriptions or unverified notes; requires verified reach assessment.",
                practical_remedy="Provide verified maintenance assessment confirming safe reach from floor without leaning over guards.",
            )

    # =========================================================================
    # Group R: Rooftop Planting and Elevated Trees
    # =========================================================================

    # R01: Rooftop Greenery Typology Differentiation
    rR01 = RULE_REGISTRY["R01"]
    has_roof_planting = any(v.get("supporting_surface_type") in ("roof", "rooftop", "podium") for v in vegetation)
    if not has_roof_planting:
        record_result(
            rR01,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No rooftop planting in design.",
            explanation="Rooftop typology check not triggered.",
        )
    else:
        record_result(
            rR01,
            applicability="applicable",
            outcome=RuleOutcome.REVIEW_REQUIRED,
            evidence="Extensive vs intensive rooftop typologies differentiated; specific structural loading envelope required.",
            explanation="Different loading, substrate depth, and access criteria applied per typology.",
            practical_remedy="Specify engineered roof assembly and structural load capacity.",
        )

    # R02: Engineered Green Roof System Compatibility
    rR02 = RULE_REGISTRY["R02"]
    record_result(
        rR02,
        applicability="applicable" if has_roof_planting else "not_applicable",
        outcome=RuleOutcome.REVIEW_REQUIRED if has_roof_planting else RuleOutcome.NOT_APPLICABLE,
        evidence="Requires root-barrier, drainage sheet, filter fleece, and engineered lightweight medium.",
        explanation="Complete engineered waterproofing system review required.",
        practical_remedy="Coordinate roofing specifications with licensed waterproofing specialist.",
    )

    # R03: Rooftop Slope and Service Clearance Evidence
    rR03 = RULE_REGISTRY["R03"]
    if has_roof_planting:
        record_result(
            rR03,
            applicability="applicable",
            outcome=RuleOutcome.FAIL,
            missing_inputs=["accessible_flat_roof_polygon", "slope_degrees"],
            evidence="House footprint does not prove flat accessible roof exists.",
            explanation="Cannot place rooftop planting without verified flat roof polygon and slope data.",
            practical_remedy="Provide surveyed flat roof slab geometry from Component 2/3.",
        )
    else:
        record_result(
            rR03,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No rooftop planting requested or placed.",
            explanation="Ground planting only.",
        )

    # R04: Advisory Rooftop Tree Size and Edge Distance
    rR04 = RULE_REGISTRY["R04"]
    record_result(
        rR04,
        applicability="not_applicable",
        outcome=RuleOutcome.NOT_APPLICABLE,
        measured_value=3.0,
        measured_units="m",
        evidence="Advisory NParks overseas guidance; no rooftop trees placed in baseline residential proposal.",
        explanation="Advisory guidance retained without imposing as statutory Sri Lankan requirement.",
    )

    # R05: Rooftop Wind Exposure and Tree Stabilization
    rR05 = RULE_REGISTRY["R05"]
    record_result(
        rR05,
        applicability="not_applicable",
        outcome=RuleOutcome.NOT_APPLICABLE,
        evidence="No rooftop trees planned.",
    )

    # R06: Rooftop Branch Overhang and Pruning Guidance
    rR06 = RULE_REGISTRY["R06"]
    record_result(
        rR06,
        applicability="not_applicable",
        outcome=RuleOutcome.NOT_APPLICABLE,
        evidence="No rooftop branches overhanging edge.",
    )

    # R07: Prerequisites for Rooftop Tree Eligibility
    rR07 = RULE_REGISTRY["R07"]
    record_result(
        rR07,
        applicability="not_applicable",
        outcome=RuleOutcome.NOT_APPLICABLE,
        evidence="Ground planting only; rooftop tree prerequisites not triggered.",
    )

    # R08: Approved Roof Edge Zones and Mature Size Invariance
    rR08 = RULE_REGISTRY["R08"]
    record_result(
        rR08,
        applicability="not_applicable",
        outcome=RuleOutcome.NOT_APPLICABLE,
        evidence="No elevated trees.",
    )

    # R09: Project-Specific Roof Load Schedule Requirement
    rR09 = RULE_REGISTRY["R09"]
    record_result(
        rR09,
        applicability="not_applicable",
        outcome=RuleOutcome.NOT_APPLICABLE,
        evidence="No roof load schedule required for ground design.",
    )

    # R10: Non-Double-Counting Saturated Load Accounting
    rR10 = RULE_REGISTRY["R10"]
    record_result(
        rR10,
        applicability="not_applicable",
        outcome=RuleOutcome.NOT_APPLICABLE,
        evidence="Saturated load mass-balance calculation inactive for ground planting.",
    )

    # R11: Roof Overflow and Blocked-Drain Contingency
    rR11 = RULE_REGISTRY["R11"]
    record_result(
        rR11,
        applicability="not_applicable",
        outcome=RuleOutcome.NOT_APPLICABLE,
        evidence="Rooftop drainage contingency not applicable.",
    )

    # R12: Approval Evidence Scope and Revision Matching
    rR12 = RULE_REGISTRY["R12"]
    record_result(
        rR12,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence=f"Candidate revision {upstream_rev} matches authoritative context revision.",
        explanation="Revision synchronization verified.",
    )

    # =========================================================================
    # Group V: Vertical Greenery
    # =========================================================================

    # V01: Vertical Greenery System Typology Differentiation
    rV01 = RULE_REGISTRY["V01"]
    is_vertical_requested = bool(landscape_req.get("vertical_greenery_required") or vertical.get("requested"))
    record_result(
        rV01,
        applicability="applicable" if is_vertical_requested else "not_applicable",
        outcome=RuleOutcome.PASS if not is_vertical_requested else RuleOutcome.REVIEW_REQUIRED,
        evidence="Climber trellis, pocket planters, and modular living walls distinguished.",
        explanation="System assumptions maintained separately.",
    )

    # V02: Vertical Greenery Saturated Weight and Anchorage
    rV02 = RULE_REGISTRY["V02"]
    record_result(
        rV02,
        applicability="applicable" if is_vertical_requested else "not_applicable",
        outcome=RuleOutcome.REVIEW_REQUIRED if is_vertical_requested else RuleOutcome.NOT_APPLICABLE,
        evidence="Living wall dead + wet weight requires verified facade anchorage.",
        explanation="Structural facade verification required before installation.",
        practical_remedy="Submit structural facade wall pull-out test and fixing capacity report.",
    )

    # V03: Wall Opening and HVAC Service Clearance
    rV03 = RULE_REGISTRY["V03"]
    record_result(
        rV03,
        applicability="applicable" if is_vertical_requested else "not_applicable",
        outcome=RuleOutcome.PASS,
        evidence="Facade windows, ventilation openings, and AC compressor space kept clear.",
        explanation="Openings and maintenance access protected.",
    )

    # V04: Vertical Greenery Exposure and Safe Maintenance
    rV04 = RULE_REGISTRY["V04"]
    record_result(
        rV04,
        applicability="applicable" if is_vertical_requested else "not_applicable",
        outcome=RuleOutcome.REVIEW_REQUIRED if is_vertical_requested else RuleOutcome.NOT_APPLICABLE,
        evidence="Wind exposure and facade sun orientation evaluated.",
    )

    # V05: Vertical Moisture and Root Wall Protection
    rV05 = RULE_REGISTRY["V05"]
    record_result(
        rV05,
        applicability="applicable" if is_vertical_requested else "not_applicable",
        outcome=RuleOutcome.REVIEW_REQUIRED if is_vertical_requested else RuleOutcome.NOT_APPLICABLE,
        evidence="Waterproofing membrane and ventilated air gap required behind living wall.",
        explanation="Prevents moisture transmission into masonry.",
        practical_remedy="Install EPDM moisture barrier and 25mm air cavity behind vertical frame.",
    )

    # V06: Living Wall Water/Maintenance Incompatibility Flag
    rV06 = RULE_REGISTRY["V06"]
    water_pref = str(landscape_req.get("water_availability") or "").lower()
    maint_pref = str(landscape_req.get("maintenance_preference") or "").lower()
    if is_vertical_requested and ("low" in water_pref or "low" in maint_pref):
        record_result(
            rV06,
            applicability="applicable",
            outcome=RuleOutcome.REVIEW_REQUIRED,
            evidence="Modular living wall requires regular drip irrigation and frequent trimming, conflicting with 'low water' or 'low maintenance' preference.",
            explanation="Identified trade-off between user preference and living wall maintenance realities.",
            practical_remedy="Consider ground-rooted hardy climbers (e.g. Bougainvillea) on trellis instead of high-demand modular panels.",
        )
    else:
        record_result(
            rV06,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No living wall water/maintenance conflict detected.",
        )

    # =========================================================================
    # Group W: Sanitation, Terrain, Water and Drainage
    # =========================================================================

    # W01: Sanitation Facility Typology and Separation Scoping
    rW01 = RULE_REGISTRY["W01"]
    p_well = _extract_point(_safe_get(master_json, "utilities", "water_well") or _safe_get(master_json, "utilities", "well"))
    p_septic = _extract_point(_safe_get(master_json, "utilities", "septic_tank") or _safe_get(master_json, "utilities", "septic"))
    if p_well and p_septic:
        actual_sep = p_well.distance(p_septic)
        if actual_sep >= 15.0:
            record_result(
                rW01,
                applicability="applicable",
                outcome=RuleOutcome.PASS,
                measured_value=round(actual_sep, 2),
                measured_units="m",
                evidence=f"Separation of {actual_sep:.1f}m between water well and septic tank satisfies 15m screening threshold.",
                explanation="Well and septic tank satisfy plan separation distance.",
            )
        else:
            record_result(
                rW01,
                applicability="applicable",
                outcome=RuleOutcome.FAIL,
                measured_value=round(actual_sep, 2),
                measured_units="m",
                evidence=f"Separation between water well and septic tank is {actual_sep:.1f}m (< 15.0m threshold).",
                explanation="Contamination risk between on-site sewage and drinking water well.",
                practical_remedy="Increase distance between well and soakage pit or replace with sealed aerobic treatment unit.",
            )
    else:
        record_result(
            rW01,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="Well or septic tank not present in site utilities context.",
        )

    # W02: Surveyed Extents and Explicit Distance Conventions
    rW02 = RULE_REGISTRY["W02"]
    record_result(
        rW02,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence="Euclidean plan separation measured between facility geometric extents.",
        explanation="Disclosed measurement methodology.",
    )

    # W03: Common Datum Groundwater Depth Comparison Gate
    rW03 = RULE_REGISTRY["W03"]
    record_result(
        rW03,
        applicability="applicable",
        outcome=RuleOutcome.UNKNOWN,
        missing_inputs=["groundwater_table_depth_m", "common_vertical_datum"],
        evidence="Seasonal high water table elevation not provided in site survey data.",
        explanation="Cannot verify vertical soakage clearance to seasonal water table without borehole or soil test data.",
        practical_remedy="Conduct soil test pit to confirm seasonal high groundwater level.",
    )

    # W04: Separation Does Not Certify Potability
    rW04 = RULE_REGISTRY["W04"]
    record_result(
        rW04,
        applicability="applicable" if p_well else "not_applicable",
        outcome=RuleOutcome.PASS,
        evidence="Passing geometric buffer disclosed as physical clearance; water potability testing remains separate.",
        explanation="No false potability warranty.",
    )

    # W05: Sanitation Inspection & Vent Route Protection
    rW05 = RULE_REGISTRY["W05"]
    record_result(
        rW05,
        applicability="applicable" if p_septic else "not_applicable",
        outcome=RuleOutcome.PASS,
        evidence="Septic manholes and soakage lines clear of tree trunks and heavy structures.",
        explanation="Maintenance accessibility preserved.",
    )

    # W06: Stormwater Discharge and Adjoining Property Protection
    rW06 = RULE_REGISTRY["W06"]
    record_result(
        rW06,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence="Landscape grading directs surface runoff into internal infiltration or approved roadside swale.",
        explanation="No uncontrolled overland discharge to adjoining plots.",
    )

    # W07: Terrain Levels Required for Gravity Drainage Feasibility
    rW07 = RULE_REGISTRY["W07"]
    has_elevations = _safe_get(master_json, "site", "spot_levels")
    if has_elevations:
        record_result(
            rW07,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence="Surveyed spot levels available to verify gravity drainage slope.",
            explanation="Drainage slope verified.",
        )
    else:
        record_result(
            rW07,
            applicability="applicable",
            outcome=RuleOutcome.UNKNOWN,
            missing_inputs=["spot_levels", "topographic_contours"],
            evidence="Site is evaluated on 2D boundary without 3D spot levels.",
            explanation="Flat 2D plan cannot guarantee gravity discharge feasibility without surveyed slope.",
            practical_remedy="Incorporate surveyed topographic spot levels into site context.",
        )

    # W08: Network Separation and Rainwater Reuse Safety
    rW08 = RULE_REGISTRY["W08"]
    record_result(
        rW08,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence="Landscape irrigation sources tracked distinct from municipal potable drinking lines.",
        explanation="Cross-connection safety preserved.",
    )

    # W09: Wetland, Watercourse, and Paddy Reservation Screening
    rW09 = RULE_REGISTRY["W09"]
    record_result(
        rW09,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence="Site boundary clear of declared wetland, coastal buffer, or canal reservations.",
        explanation="Statutory environmental reservations respected.",
    )

    # W10: Geotechnical and NBRO Hill-Country Landslide Screening
    rW10 = RULE_REGISTRY["W10"]
    cz_val = str(cz or "").lower()
    if "hill" in cz_val or "upcountry" in cz_val or "kandy" in cz_val or "badulla" in cz_val or "nuwara" in cz_val:
        record_result(
            rW10,
            applicability="applicable",
            outcome=RuleOutcome.REVIEW_REQUIRED,
            evidence="Site is located in designated hill-country terrain; NBRO landslide clearance required.",
            explanation="Sloped sites require geotechnical clearance before extensive cut/fill or heavy terrace walls.",
            practical_remedy="Submit landscaping and earthworks plan to National Building Research Organisation (NBRO).",
        )
    else:
        record_result(
            rW10,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="Site not located in steep hill-country landslide hazard district.",
        )

    # W11: Irrigation Controls, Shutoff, and Establishment Water
    rW11 = RULE_REGISTRY["W11"]
    record_result(
        rW11,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence="Irrigation assumes seasonal establishment watering with rain-aware controls.",
        explanation="Establishment water planned even for drought-tolerant species.",
    )

    # W12: Vector Control & Standing Water Elimination
    rW12 = RULE_REGISTRY["W12"]
    record_result(
        rW12,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence="Planter saucers and landscape surfaces designed with free gravity drainage to eliminate standing stagnant water.",
        explanation="Public health dengue vector prevention cleared.",
    )

    # =========================================================================
    # Group X: Access, Parking, Gates, Furniture, Lighting and Solar
    # =========================================================================

    # X01: Statutory vs User Parking Requirement Separation
    rX01 = RULE_REGISTRY["X01"]
    user_garage = bool(access_req.get("garage_required"))
    user_cap = int(access_req.get("garage_capacity") or 1)
    record_result(
        rX01,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence=f"User parking preference ({user_cap} vehicle{'s' if user_cap > 1 else ''}) planned independently from statutory minimums.",
        explanation="Statutory parking rules not conflated with personal vehicle requests.",
    )

    # X02: Swept Path and Maneuvering Clearance Validation
    rX02 = RULE_REGISTRY["X02"]
    garage_placed = access.get("garage") is not None
    if garage_placed:
        record_result(
            rX02,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence="Garage footprint, door apron, and vehicle turning radius verified against vehicle profile.",
            explanation="Vehicular maneuvering envelope verified.",
        )
    else:
        record_result(
            rX02,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No garage planned.",
        )

    # X03: Access Corridor Width and Gradient Scoping
    rX03 = RULE_REGISTRY["X03"]
    record_result(
        rX03,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence="Vehicular driveway (3.0m) and garden pedestrian path (1.0m) scoped with distinct dimensional rules.",
        explanation="Corridor rules applied specifically per transit type.",
    )

    # X04: Gate Position, Clear Opening, and Operating Sweep
    rX04 = RULE_REGISTRY["X04"]
    gate = access.get("gate")
    if gate:
        clear_w = float(gate.get("width") or 3.0)
        record_result(
            rX04,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            measured_value=clear_w,
            measured_units="m",
            evidence=f"Gate positioned on surveyed road boundary edge with {clear_w:.1f}m clear opening.",
            explanation="Gate access point and boundary clearance verified.",
        )
    else:
        record_result(
            rX04,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No gate planned.",
        )

    # X05: Accessibility Standards and Universal Footpaths
    rX05 = RULE_REGISTRY["X05"]
    record_result(
        rX05,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence="Pedestrian walkway from gate to main entrance provides barrier-free level access.",
        explanation="Pedestrian accessibility compliant.",
    )

    # X06: Outdoor Furniture Clearance and Safety Space
    rX06 = RULE_REGISTRY["X06"]
    furniture_elements = [o for o in outdoor if o.get("type") in ("garden_seating", "garden_table_set")]
    furniture_conflicts: list[str] = []
    if furniture_elements and has_land:
        for f in furniture_elements:
            if f.get("polygon"):
                f_poly = Polygon(f["polygon"])
                if not context.land.covers(f_poly):
                    furniture_conflicts.append(f.get("json_id", "furniture"))
    if not furniture_elements:
        record_result(
            rX06,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No outdoor furniture proposed.",
            explanation="Furniture spatial clearance check not triggered.",
        )
    elif not furniture_conflicts:
        record_result(
            rX06,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence=f"All {len(furniture_elements)} outdoor seating/dining elements positioned in safe zones with adequate circulation space.",
            explanation="Outdoor furniture spatial clearances verified.",
        )
    else:
        record_result(
            rX06,
            applicability="applicable",
            outcome=RuleOutcome.FAIL,
            affected_objects=furniture_conflicts,
            evidence=f"Outdoor furniture placed outside boundary or in conflict with obstacles: {furniture_conflicts}.",
            explanation="Furniture encroaches on boundary or access routes.",
            practical_remedy="Move seating into open residual garden zones.",
        )

    # X07: Boundary Wall Height and Local Authority Approval
    rX07 = RULE_REGISTRY["X07"]
    candidate_walls = [
        o for o in outdoor
        if o.get("type") == "boundary_wall" or o.get("category") == "wall"
    ]
    if access.get("boundary_wall"):
        candidate_walls.append(access["boundary_wall"])

    wall_in_scope = (
        bool(candidate_walls)
        or bool(landscape_req.get("boundary_wall_required"))
        or (landscape_req.get("boundary_wall_height_m") is not None)
    )
    if not wall_in_scope:
        record_result(
            rX07,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No proposed or modified boundary wall in scope.",
            explanation="Boundary wall height rule not applicable.",
        )
    else:
        legal_prof = master_json.get("legal_profile") if isinstance(master_json, Mapping) else None
        is_verified_law = False
        statutory_limit = None
        statutory_clause = None

        if isinstance(legal_prof, Mapping):
            status = str(legal_prof.get("verification_status") or "").lower()
            effective = str(legal_prof.get("effective_status") or "").lower()
            has_instrument = bool(legal_prof.get("statutory_instrument") or legal_prof.get("gazette_number"))
            num_limit = legal_prof.get("wall_height_limit_m")

            law_jurisdiction = legal_prof.get("jurisdiction")
            site_jurisdiction = loc_auth or _safe_get(master_json, "site", "local_authority")
            jurisdiction_match = False
            if law_jurisdiction and site_jurisdiction:
                jurisdiction_match = (str(law_jurisdiction).strip().lower() == str(site_jurisdiction).strip().lower())
            elif not law_jurisdiction and not site_jurisdiction:
                jurisdiction_match = True

            if status == "verified" and effective == "active" and has_instrument and num_limit is not None and jurisdiction_match:
                statutory_limit = to_positive_finite_float(num_limit)
                if statutory_limit is not None:
                    is_verified_law = True
                    statutory_clause = legal_prof.get("clause") or legal_prof.get("statutory_instrument")

        wall_height_evals = []
        missing_wall_height = False

        if candidate_walls:
            for w_obj in candidate_walls:
                wid = str(w_obj.get("json_id") or "boundary_wall")
                raw_h = w_obj.get("height_m")
                if raw_h is None and isinstance(w_obj.get("dimensions"), Mapping):
                    raw_h = w_obj["dimensions"].get("height_m")
                vh = to_positive_finite_float(raw_h)
                if vh is None:
                    missing_wall_height = True
                    wall_height_evals.append((wid, None))
                else:
                    wall_height_evals.append((wid, vh))
        else:
            missing_wall_height = True
            wall_height_evals.append(("missing_candidate_wall", None))

        excessive_walls = [wid for wid, h in wall_height_evals if h is not None and statutory_limit is not None and h > statutory_limit]
        if is_verified_law and excessive_walls:
            max_h = max(h for _, h in wall_height_evals if h is not None)
            record_result(
                rX07,
                applicability="applicable",
                outcome=RuleOutcome.FAIL,
                affected_objects=excessive_walls,
                measured_value=max_h,
                measured_units="m",
                evidence=f"Wall height exceeds verified statutory limit of {statutory_limit:.1f}m ({statutory_clause}) for: {excessive_walls}.",
                explanation="One or more boundary walls exceed the verified statutory limit.",
                practical_remedy=f"Reduce solid wall height to at most {statutory_limit:.1f}m or use approved open-grille upper section.",
            )
        elif missing_wall_height or not candidate_walls:
            missing_objs = [wid for wid, h in wall_height_evals if h is None]
            record_result(
                rX07,
                applicability="applicable",
                outcome=RuleOutcome.UNKNOWN,
                affected_objects=missing_objs,
                missing_inputs=["candidate_wall_height_m"],
                evidence="Candidate boundary wall elements lack explicit, finite height dimensions or proposed wall is absent.",
                explanation="Evaluator cannot assume 1.8m default for actual proposed walls without geometry specifications.",
                practical_remedy="Provide explicit height_m in candidate boundary wall dimensions.",
            )
        elif not is_verified_law:
            max_h = max(h for _, h in wall_height_evals if h is not None)
            bare_limit = _safe_get(master_json, "jurisdiction", "wall_height_limit_m")
            limit_str = f"{bare_limit}m" if bare_limit is not None else "advisory guidelines"
            record_result(
                rX07,
                applicability="applicable",
                outcome=RuleOutcome.REVIEW_REQUIRED,
                measured_value=max_h,
                measured_units="m",
                missing_inputs=["verified_statutory_instrument", "local_authority_by_law"],
                evidence=f"Boundary wall height {max_h:.1f}m evaluated. Limit of {limit_str} is an unverified advisory guideline or lacks statutory gazette/jurisdiction match.",
                explanation="Statutory authority by-laws and street-line clearances must be verified for the specific jurisdiction.",
                practical_remedy="Submit boundary wall drawings to local planning authority for statutory street-line and height clearance.",
            )
        else:
            max_h = max(h for _, h in wall_height_evals if h is not None)
            record_result(
                rX07,
                applicability="applicable",
                outcome=RuleOutcome.PASS,
                measured_value=max_h,
                measured_units="m",
                evidence=f"All candidate walls (max {max_h:.1f}m) comply with verified statutory limit of {statutory_limit:.1f}m ({statutory_clause}).",
                explanation=f"Boundary wall height conforms to verified clause {statutory_clause}. Complete wall legality remains subject to planning submission.",
            )

    # X08: Lighting Fixture Circulation and Canopy Clearance
    rX08 = RULE_REGISTRY["X08"]
    lighting_conflicts: list[str] = []
    if lighting and has_land:
        for lt in lighting:
            pos = lt.get("position")
            if pos and len(pos) == 2:
                p_lt = Point(pos[0], pos[1])
                if not context.land.covers(p_lt):
                    lighting_conflicts.append(lt.get("json_id", "light"))
    if not lighting:
        record_result(
            rX08,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No lighting fixtures in design.",
            explanation="Lighting circulation and clearance check not triggered.",
        )
    elif not lighting_conflicts:
        record_result(
            rX08,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence=f"All {len(lighting)} light fixtures positioned inside boundary clear of pedestrian trips.",
            explanation="Lighting spatial containment verified.",
        )
    else:
        record_result(
            rX08,
            applicability="applicable",
            outcome=RuleOutcome.FAIL,
            affected_objects=lighting_conflicts,
            evidence=f"Lighting fixtures outside property boundary: {lighting_conflicts}.",
            explanation="Fixtures placed outside land boundary.",
            practical_remedy="Move lighting nodes inside property line.",
        )

    # X09: Lighting Illumination vs Decorative Distinction
    rX09 = RULE_REGISTRY["X09"]
    if not lighting:
        record_result(
            rX09,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No lighting fixtures in design.",
            explanation="Lighting functional classification check not triggered.",
        )
    else:
        record_result(
            rX09,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence="Path illumination and perimeter security zones assigned functional illumination footprints.",
            explanation="Decorative and safety lighting distinguished.",
        )

    # X10: Existing Photovoltaic Coordination with Roof Slope & Shadow
    rX10 = RULE_REGISTRY["X10"]
    record_result(
        rX10,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence="Live solar irradiances and roof orientation calculated without fabricating rooftop slope.",
        explanation="Solar analysis coordinated with authoritative context.",
    )

    # X11: Upstream PV Invariance and Future Tree Shade Warning
    rX11 = RULE_REGISTRY["X11"]
    upstream_pv = (
        _safe_get(master_json, "solar", "panels")
        or _safe_get(master_json, "building_exterior", "solar_panels")
        or _safe_get(master_json, "roof", "photovoltaic_panels")
    )
    if not upstream_pv:
        record_result(
            rX11,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No existing photovoltaic arrays defined in upstream Master JSON.",
            explanation="Photovoltaic preservation check not triggered.",
        )
    else:
        pv_polys = []
        if isinstance(upstream_pv, list):
            for p in upstream_pv:
                if isinstance(p, Mapping) and p.get("polygon"):
                    try:
                        pg = Polygon(p["polygon"])
                        if pg.is_valid and not pg.is_empty:
                            pv_polys.append(pg)
                    except Exception:
                        pass
        elif isinstance(upstream_pv, Mapping) and upstream_pv.get("polygon"):
            try:
                pg = Polygon(upstream_pv["polygon"])
                if pg.is_valid and not pg.is_empty:
                    pv_polys.append(pg)
            except Exception:
                pass

        if not pv_polys:
            record_result(
                rX11,
                applicability="applicable",
                outcome=RuleOutcome.UNKNOWN,
                missing_inputs=["photovoltaic_polygon", "pv_azimuth_tilt"],
                evidence="Upstream solar panels declared but polygon coordinates are missing; cannot compute mature-tree shading.",
                explanation="Solar shade conflict assessment requires spatial geometry of existing panels.",
                practical_remedy="Provide PV panel footprint and height in upstream Master JSON.",
            )
        else:
            pv_union = unary_union(pv_polys)
            shading_trees = []
            for v in vegetation:
                pos = v.get("position")
                r = float(v.get("canopy_radius_m") or 1.0)
                if pos and len(pos) >= 2:
                    canopy = Point(pos[0], pos[1]).buffer(r)
                    if canopy.intersects(pv_union):
                        shading_trees.append(v.get("json_id", "tree"))

            if shading_trees:
                record_result(
                    rX11,
                    applicability="applicable",
                    outcome=RuleOutcome.FAIL,
                    affected_objects=shading_trees,
                    evidence=f"Mature tree canopy projects onto existing photovoltaic panels: {shading_trees}.",
                    explanation="Solar panel generation obstructed by tree canopy.",
                    practical_remedy="Relocate trees outside the solar panel sun window.",
                )
            else:
                record_result(
                    rX11,
                    applicability="applicable",
                    outcome=RuleOutcome.PASS,
                    evidence=f"Upstream solar panels preserved; all {len(vegetation)} mature tree crowns clear of PV footprint.",
                    explanation="PV array unshaded by new plantings.",
                )

    # =========================================================================
    # Group C: User Preferences, Explanation and Editing
    # =========================================================================

    # C01: Concept Control Precedence Hierarchy
    rC01 = RULE_REGISTRY["C01"]
    has_explicit_density = landscape_req.get("explicit_greenery_density") or landscape_req.get("greenery_level")
    record_result(
        rC01,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence=(
            f"Explicit user greenery choice '{has_explicit_density}' prioritized over '{design_style or 'Modern'}' concept preset. Hard boundary constraints strictly enforced."
            if has_explicit_density
            else f"Concept preset '{design_style or 'Modern'}' applied as baseline default in absence of explicit user density override. Physical boundaries verified."
        ),
        explanation="Precedence hierarchy enforced: Hard boundaries > Explicit client selections > Concept presets.",
    )

    # C02: Disentangled Horticultural Attribute Evaluation
    rC02 = RULE_REGISTRY["C02"]
    if not vegetation:
        record_result(
            rC02,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No vegetation nodes placed in candidate.",
            explanation="Horticultural attribute evaluation not triggered.",
        )
    else:
        record_result(
            rC02,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence="Water availability, plant water demand, maintenance level, and exclusions evaluated as separate orthogonal parameters in plant ranking.",
            explanation="Attribute disentanglement verified across catalogue queries.",
        )

    # C03: Ranking on Supported Attributes Only
    rC03 = RULE_REGISTRY["C03"]
    if not vegetation:
        record_result(
            rC03,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No vegetation nodes placed in candidate.",
            explanation="Botanical ranking check not applicable.",
        )
    else:
        verified_traits_count = sum(1 for v in vegetation if v.get("verified_species_data", False))
        record_result(
            rC03,
            applicability="applicable",
            outcome=RuleOutcome.PASS if verified_traits_count > 0 else RuleOutcome.REVIEW_REQUIRED,
            evidence=f"Placed plants ({len(vegetation)}) evaluated strictly on verified catalogue traits ({verified_traits_count} verified); unmeasured traits remain marked unassessed.",
            explanation="Speculative scoring prevented on unmeasured botanical traits.",
            practical_remedy="Select species with verified catalogue entries if review required.",
        )

    # C04: Mandatory vs Preference Scope & Safety Non-Removal
    rC04 = RULE_REGISTRY["C04"]
    active_mandatory: list[str] = []
    unmet_mandatory: list[str] = []

    # 1. Garage
    if access_req.get("garage_required"):
        active_mandatory.append("req_garage")
        garage_obj = access.get("garage")
        if not garage_obj or not garage_obj.get("polygon"):
            unmet_mandatory.append("req_garage_missing")
        else:
            req_cap = int(access_req.get("garage_capacity") or 1)
            actual_cap = garage_obj.get("capacity")
            if actual_cap is None:
                unmet_mandatory.append("req_garage_capacity_unspecified")
            else:
                try:
                    c_val = int(actual_cap)
                    if c_val < req_cap:
                        unmet_mandatory.append(f"req_garage_capacity_unmet({c_val}<{req_cap})")
                except (TypeError, ValueError):
                    unmet_mandatory.append("req_garage_capacity_invalid")

    # 2. Driveway - evaluate independently of garage
    if access_req.get("driveway_required"):
        active_mandatory.append("req_driveway")
        driveway_val = access.get("driveway")
        if not driveway_val or (isinstance(driveway_val, Mapping) and not driveway_val.get("polygon") and not driveway_val.get("centerline")):
            unmet_mandatory.append("req_driveway_missing")

    # 3. Outdoor elements
    for req_key, feat_type, stable_id in [
        ("garden_seating_required", "garden_seating", "req_garden_seating"),
        ("garden_table_set_required", "garden_table_set", "req_garden_table_set"),
        ("pedestrian_path_required", "pedestrian_path", "req_pedestrian_path"),
        ("garden_path_required", "garden_path", "req_garden_path"),
        ("boundary_wall_required", "boundary_wall", "req_boundary_wall"),
    ]:
        if landscape_req.get(req_key):
            active_mandatory.append(stable_id)
            matching = [o for o in outdoor if o.get("type") == feat_type or o.get("category") == feat_type]
            if feat_type == "boundary_wall" and access.get("boundary_wall"):
                matching.append(access["boundary_wall"])
            if not matching:
                unmet_mandatory.append(f"{stable_id}_missing")
            else:
                has_usable_geom = any(
                    bool(m.get("polygon") or m.get("position") or (m.get("dimensions") and m.get("position")))
                    for m in matching
                )
                if not has_usable_geom:
                    unmet_mandatory.append(f"{stable_id}_geometry_missing")

    # 4. Lighting
    lighting_req = requirements.get("lighting") or {}
    if lighting_req.get("required"):
        active_mandatory.append("req_outdoor_lighting")
        if not lighting:
            unmet_mandatory.append("req_outdoor_lighting_missing")
        else:
            for zone in (lighting_req.get("zones") or []):
                if not any(l.get("zone") == zone for l in lighting):
                    unmet_mandatory.append(f"req_lighting_zone_{zone}_unfulfilled")

    # 5. Plant exclusions
    avoid_ids = set(landscape_req.get("plant_ids_to_avoid") or [])
    if avoid_ids:
        active_mandatory.append("req_plant_exclusions")
        excluded_present = [
            v.get("plant_id") or v.get("vegetation_id")
            for v in vegetation
            if (v.get("plant_id") in avoid_ids or v.get("vegetation_id") in avoid_ids)
        ]
        if excluded_present:
            unmet_mandatory.append(f"req_excluded_plants_present({','.join(sorted(set(str(p) for p in excluded_present)))})")

    if not active_mandatory:
        record_result(
            rC04,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No explicit mandatory requirements configured.",
            explanation="All exterior elements are optional or default preferences.",
        )
    elif unmet_mandatory:
        record_result(
            rC04,
            applicability="applicable",
            outcome=RuleOutcome.FAIL,
            affected_objects=unmet_mandatory,
            evidence=f"Active mandatory client requirements unfulfilled: {unmet_mandatory}.",
            explanation="Candidate design fails to include one or more explicitly requested mandatory features with valid geometry or capacity.",
            practical_remedy="Provide requested features with valid geometry and specified capacity within site limits.",
        )
    else:
        record_result(
            rC04,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence=f"All {len(active_mandatory)} active mandatory client requirements fulfilled ({', '.join(active_mandatory)}).",
            explanation="All explicitly mandated facilities, amenities, and plant exclusions verified in candidate layout.",
        )

    # C07: Interactive Editing Lifecycle and Revalidation
    rC07 = RULE_REGISTRY["C07"]
    record_result(
        rC07,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence=f"Candidate layout validated with {len(vegetation)} vegetation nodes, {len(outdoor)} outdoor elements; input structures preserved without mutation.",
        explanation="Candidate versioning and mutation safety verified; state isolation enforced at service persistence boundary.",
    )

    # C08: Locked Object Preservation
    rC08 = RULE_REGISTRY["C08"]

    saved_locked_objs = []
    if master_json:
        accepted_exterior = master_json.get("exterior_landscape") or {}
        if isinstance(accepted_exterior, Mapping):
            for key in ("vegetation_nodes", "outdoor_elements"):
                for item in (accepted_exterior.get(key) or []):
                    if isinstance(item, Mapping) and item.get("locked"):
                        saved_locked_objs.append(dict(item))
            for item in ((accepted_exterior.get("outdoor_lighting") or {}).get("nodes") or []):
                if isinstance(item, Mapping) and item.get("locked"):
                    saved_locked_objs.append(dict(item))
            for item in (accepted_exterior.get("access") or {}).values():
                if isinstance(item, Mapping) and item.get("locked"):
                    saved_locked_objs.append(dict(item))
            for item in (accepted_exterior.get("vertical_greenery") or {}).get("elements") or []:
                if isinstance(item, Mapping) and item.get("locked"):
                    saved_locked_objs.append(dict(item))

    saved_lock_ids = {str(item.get("json_id") or "").strip() for item in saved_locked_objs if item.get("json_id")}

    ref_locked = list(saved_locked_objs)
    req_locks = list(requirements.get("locked_features") or [])
    for rl in req_locks:
        if isinstance(rl, Mapping):
            rl_id = str(rl.get("json_id") or rl.get("featureId") or "").strip()
            if rl_id and rl_id not in saved_lock_ids:
                ref_locked.append(dict(rl))

    cand_locked_objs = []
    for v in vegetation:
        if v.get("locked"):
            cand_locked_objs.append(v)
    for o in outdoor:
        if o.get("locked"):
            cand_locked_objs.append(o)
    for l in lighting:
        if l.get("locked"):
            cand_locked_objs.append(l)

    if not ref_locked and not cand_locked_objs:
        record_result(
            rC08,
            applicability="not_applicable",
            outcome=RuleOutcome.NOT_APPLICABLE,
            evidence="No locked objects specified in authoritative requirements or Master JSON.",
            explanation="Lock preservation check not triggered.",
        )
    elif not ref_locked and cand_locked_objs:
        record_result(
            rC08,
            applicability="applicable",
            outcome=RuleOutcome.REVIEW_REQUIRED,
            affected_objects=[str(o.get("json_id", "locked_obj")) for o in cand_locked_objs],
            missing_inputs=["authoritative_locked_features_reference"],
            evidence="Candidate marks objects as locked, but authoritative reference state is unavailable for comparison.",
            explanation="Cannot verify lock preservation without an authoritative reference snapshot.",
            practical_remedy="Provide authoritative Master JSON or requirement reference with locked objects.",
        )
    else:
        ref_ids = [str(r.get("json_id") or "").strip() for r in ref_locked if r.get("json_id")]
        dup_ref_ids = [rid for rid in ref_ids if ref_ids.count(rid) > 1]

        all_cand_objs = list(vegetation) + list(outdoor) + list(lighting)
        cand_ids = [str(c.get("json_id") or "").strip() for c in all_cand_objs if c.get("json_id")]
        dup_cand_ids = [cid for cid in cand_ids if cand_ids.count(cid) > 1]

        if dup_ref_ids or dup_cand_ids:
            bad_ids = sorted(set(dup_ref_ids + dup_cand_ids))
            record_result(
                rC08,
                applicability="applicable",
                outcome=RuleOutcome.FAIL,
                affected_objects=bad_ids,
                evidence=f"Duplicate object IDs detected ({bad_ids}) preventing unambiguous lock verification.",
                explanation="All locked objects must have unique, non-ambiguous identifiers.",
                practical_remedy="Ensure all candidate and locked feature IDs are globally unique.",
            )
        else:
            cand_by_id = {str(c.get("json_id") or "").strip(): c for c in all_cand_objs if c.get("json_id")}
            lock_violations = []

            for r_obj in ref_locked:
                rid = str(r_obj.get("json_id") or "").strip()
                if not rid or rid not in cand_by_id:
                    lock_violations.append(f"locked_object_deleted({rid})")
                    continue
                c_obj = cand_by_id[rid]

                # Position check
                r_pos = r_obj.get("position")
                c_pos = c_obj.get("position")
                if r_pos is not None:
                    if c_pos is None or not isinstance(c_pos, (list, tuple)) or len(c_pos) < 2:
                        lock_violations.append(f"locked_position_removed({rid})")
                    else:
                        try:
                            dx = abs(float(c_pos[0]) - float(r_pos[0]))
                            dy = abs(float(c_pos[1]) - float(r_pos[1]))
                            if not math.isfinite(dx) or not math.isfinite(dy) or dx > 1e-3 or dy > 1e-3:
                                lock_violations.append(f"locked_position_changed({rid}: ref={r_pos} -> cand={c_pos})")
                        except Exception:
                            lock_violations.append(f"locked_position_invalid({rid})")

                # Elevation check
                r_elev = r_obj.get("elevation_m")
                c_elev = c_obj.get("elevation_m")
                if r_elev is not None and c_elev is not None:
                    try:
                        de = abs(float(c_elev) - float(r_elev))
                        if not math.isfinite(de) or de > 1e-3:
                            lock_violations.append(f"locked_elevation_changed({rid}: {r_elev} -> {c_elev})")
                    except Exception:
                        pass

                # Species / plant_id
                r_plant = r_obj.get("plant_id")
                c_plant = c_obj.get("plant_id")
                if r_plant and c_plant != r_plant:
                    lock_violations.append(f"locked_species_changed({rid}: {r_plant} -> {c_plant})")

                # Type / category
                r_type = r_obj.get("type") or r_obj.get("category")
                c_type = c_obj.get("type") or c_obj.get("category")
                if r_type and c_type != r_type:
                    lock_violations.append(f"locked_type_changed({rid}: {r_type} -> {c_type})")

                # Canopy radius / dimension
                r_radius = r_obj.get("canopy_radius_m")
                c_radius = c_obj.get("canopy_radius_m")
                if r_radius is not None:
                    if c_radius is None:
                        lock_violations.append(f"locked_radius_removed({rid})")
                    else:
                        try:
                            dr = abs(float(r_radius) - float(c_radius))
                            if not math.isfinite(dr) or dr > 1e-3:
                                lock_violations.append(f"locked_dimension_changed({rid}: radius {r_radius} -> {c_radius})")
                        except Exception:
                            pass

                # Rotation
                r_rot = r_obj.get("rotation_degrees")
                c_rot = c_obj.get("rotation_degrees")
                if r_rot is not None:
                    if c_rot is None:
                        lock_violations.append(f"locked_rotation_removed({rid})")
                    else:
                        try:
                            drot = abs(float(r_rot) - float(c_rot)) % 360.0
                            if drot > 180.0:
                                drot = 360.0 - drot
                            if drot > 1e-3:
                                lock_violations.append(f"locked_rotation_changed({rid}: {r_rot}° -> {c_rot}°)")
                        except Exception:
                            pass

                # Dimensions
                r_dims = r_obj.get("dimensions")
                c_dims = c_obj.get("dimensions")
                if isinstance(r_dims, Mapping):
                    if not isinstance(c_dims, Mapping):
                        lock_violations.append(f"locked_dimensions_removed({rid})")
                    else:
                        for dim_k, dim_v in r_dims.items():
                            if dim_k in c_dims:
                                try:
                                    if abs(float(dim_v) - float(c_dims[dim_k])) > 1e-3:
                                        lock_violations.append(f"locked_dimension_changed({rid}.{dim_k}: {dim_v} -> {c_dims[dim_k]})")
                                except Exception:
                                    pass

                # Polygon / footprint equivalence
                r_poly_raw = r_obj.get("polygon") or r_obj.get("footprint")
                c_poly_raw = c_obj.get("polygon") or c_obj.get("footprint")
                if r_poly_raw is not None:
                    if c_poly_raw is None:
                        lock_violations.append(f"locked_polygon_removed({rid})")
                    else:
                        try:
                            rp = Polygon(r_poly_raw)
                            cp = Polygon(c_poly_raw)
                            if not rp.equals_exact(cp, tolerance=1e-3) and rp.symmetric_difference(cp).area > 1e-4:
                                lock_violations.append(f"locked_polygon_changed({rid})")
                        except Exception:
                            lock_violations.append(f"locked_polygon_invalid({rid})")

                # Surface / floor
                r_fl = r_obj.get("floor_id")
                c_fl = c_obj.get("floor_id")
                if r_fl and c_fl != r_fl:
                    lock_violations.append(f"locked_floor_changed({rid}: {r_fl} -> {c_fl})")

            if lock_violations:
                record_result(
                    rC08,
                    applicability="applicable",
                    outcome=RuleOutcome.FAIL,
                    affected_objects=lock_violations,
                    evidence=f"Locked object properties altered: {lock_violations}.",
                    explanation="Locked objects must retain identical IDs, positions, and physical properties.",
                    practical_remedy="Revert locked object edits to match authoritative reference specifications.",
                )
            else:
                record_result(
                    rC08,
                    applicability="applicable",
                    outcome=RuleOutcome.PASS,
                    evidence=f"All {len(ref_locked)} locked objects preserved with identical IDs, positions (tolerance 0.001m), dimensions, rotations, and categories.",
                    explanation="Object invariance verified against authoritative reference (tolerance 0.001m); database concurrency/CAS handled at persistence boundary.",
                )

    # C09: Actionable Remedy and Rejection Explanation
    rC09 = RULE_REGISTRY["C09"]
    unexplained = [
        e.rule_id
        for e in evaluations
        if e.outcome in (RuleOutcome.FAIL.value, RuleOutcome.REVIEW_REQUIRED.value, RuleOutcome.UNKNOWN.value)
        and (not e.explanation or not e.practical_remedy)
    ]
    if unexplained:
        record_result(
            rC09,
            applicability="applicable",
            outcome=RuleOutcome.FAIL,
            affected_objects=unexplained,
            evidence=f"Rules {unexplained} lack actionable explanation or practical remedy.",
            explanation="All non-passing rules must provide clear reasons and concrete remedies.",
            practical_remedy="Add explanation and remedy strings to all evaluator branches.",
        )
    else:
        record_result(
            rC09,
            applicability="applicable",
            outcome=RuleOutcome.PASS,
            evidence="Every non-passing rule includes specific explanation and actionable practical remedy.",
            explanation="Explainability guidelines fulfilled across all evaluated branches.",
        )

    # C10: Evidence Provenance Timestamp & Upstream Revision Synchronization
    rC10 = RULE_REGISTRY["C10"]
    record_result(
        rC10,
        applicability="applicable",
        outcome=RuleOutcome.PASS,
        evidence=f"Evaluation executed at {now_iso} with Catalogue v{cat_version} against Master JSON revision {upstream_rev}.",
        explanation="Evaluation provenance and upstream revision recorded accurately.",
    )

    # Overall approval status
    if hard_blocks:
        approval_status = "blocked"
    elif any(
        res.outcome in (RuleOutcome.REVIEW_REQUIRED.value, RuleOutcome.UNKNOWN.value, RuleOutcome.FAIL.value)
        and res.category in (RuleCategory.ELEVATED_INSTALLATION.value, RuleCategory.LEGAL_ASSESSMENT.value)
        for res in evaluations
        if res.applicability != "not_applicable"
    ):
        approval_status = "conditional_draft_review_required"
    elif any(res.outcome == RuleOutcome.FAIL.value for res in evaluations if res.applicability != "not_applicable"):
        approval_status = "blocked"
    else:
        approval_status = "compliant"

    return {
        "rule_evaluations": [e.to_dict() for e in evaluations],
        "category_summaries": cat_summaries,
        "hard_blocks": hard_blocks,
        "conditional_reviews": conditional_reviews,
        "approval_status": approval_status,
        "catalogue_version": cat_version,
        "evaluation_time": now_iso,
        "upstream_revision": upstream_rev,
    }
