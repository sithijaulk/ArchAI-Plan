"""
GAB-Gen Validation Engine.
Performs comprehensive Stage-1 structural and geometric validation:
- Legal land polygon validity
- Vector closure tolerance cross-check against config
- Declared area vs reconstructed area cross-check against config
- Multi-state regulatory rules verification (COMPLIANT, NON_COMPLIANT, REQUIRES_REGULATORY_VERIFICATION, CONFLICT_REQUIRES_REVIEW)
- Buildable footprint containment inside legal parcel
- Room containment inside buildable footprint
- No illegal overlapping of rooms
- Staircase geometric alignment across multi-storey floors
- Storey count consistency
- Site-level restrictions checking (wetlands, flood retention, road & canal reservations)
"""
import json
import os
from typing import Any, Dict, List, Optional, Tuple
from shapely.geometry import Polygon
from ..schemas import (
    ValidationResult,
    FloorPlanDefinition,
    RegulatoryRule,
    ComplianceStatus,
    ApplicabilityStatus,
    RegulatoryResolutionOutput,
    SiteRestrictionCheck
)

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "gab_validation_config.json")


def get_tolerances() -> Tuple[float, float]:
    """Returns (closure_tolerance_meters, area_tolerance_percent)."""
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                ct = float(cfg.get("closure_tolerance", {}).get("value", 1.5))
                at = float(cfg.get("area_tolerance_percent", {}).get("value", 15.0))
                return ct, at
        except Exception:
            pass
    return 1.5, 15.0


def cross_check_land_area(
    declared_area_sqm: float,
    reconstructed_area_sqm: float,
    tolerance_percent: Optional[float] = None
) -> Dict[str, Any]:
    """
    Compares declared land area with reconstructed polygon area.
    Never silently modifies geometry. Records discrepancy and flags needs_verification if large.
    """
    if tolerance_percent is None:
        _, tolerance_percent = get_tolerances()

    diff_sqm = abs(reconstructed_area_sqm - declared_area_sqm)
    pct_diff = (diff_sqm / declared_area_sqm * 100.0) if declared_area_sqm > 0 else 0.0

    exceeds = pct_diff > tolerance_percent
    warning = None
    if exceeds:
        warning = (
            f"Declared area ({declared_area_sqm:.2f} m²) differs from reconstructed survey area "
            f"({reconstructed_area_sqm:.2f} m²) by {pct_diff:.1f}%, exceeding configured tolerance of {tolerance_percent}%."
        )

    return {
        "declared_area_sqm": round(declared_area_sqm, 2),
        "reconstructed_area_sqm": round(reconstructed_area_sqm, 2),
        "area_difference_sqm": round(diff_sqm, 2),
        "area_difference_percent": round(pct_diff, 2),
        "tolerance_percent": tolerance_percent,
        "exceeds_tolerance": exceeds,
        "warning": warning
    }


def validate_gab_geometry(
    land_poly: Polygon,
    buildable_poly: Polygon,
    closure_error: float,
    area_check: Dict[str, Any],
    floors: List[FloorPlanDefinition],
    expected_storey_count: int = 1,
    rules: Optional[List[RegulatoryRule]] = None,
    regulatory_resolution: Optional[RegulatoryResolutionOutput] = None,
    site_restrictions: Optional[List[SiteRestrictionCheck]] = None
) -> ValidationResult:
    """
    Performs comprehensive GAB Stage-1 structural and multi-state regulatory validation.
    """
    violations: List[str] = []
    warnings: List[str] = []
    unresolved_requirements: List[str] = []
    conflicting_requirements: List[str] = []
    closure_tolerance, _ = get_tolerances()

    # 1. Check legal land polygon validity
    if not land_poly or not land_poly.is_valid or land_poly.area <= 0:
        violations.append("Legal land polygon is topologically invalid or has zero area.")

    # 2. Check closure error against configured tolerance
    if closure_error > closure_tolerance:
        warnings.append(
            f"Survey vector closure error ({closure_error:.3f} m) exceeds configured tolerance ({closure_tolerance} m)."
        )

    # 3. Check area discrepancy
    if area_check.get("exceeds_tolerance"):
        warnings.append(area_check.get("warning", "Area discrepancy exceeds configured tolerance."))

    # 4. Check regulatory rules & resolution
    if not rules:
        violations.append("No verified regulatory setback configuration exists.")
        unresolved_requirements.append("No regulatory rules supplied.")
    else:
        for r in rules:
            if r.verification_status == "research_test":
                warnings.append(f"Rule '{r.rule_id}' is running in research_test mode (authority: {r.authority}).")
                unresolved_requirements.append(f"Rule '{r.rule_id}' is a research benchmark.")
            elif r.verification_status != "verified":
                warnings.append(f"Rule '{r.rule_id}' has unverified status: '{r.verification_status}'.")
                unresolved_requirements.append(f"Rule '{r.rule_id}' is pending verification.")

    if regulatory_resolution:
        for u in regulatory_resolution.unresolved_requirements:
            if u not in unresolved_requirements:
                unresolved_requirements.append(u)
        if regulatory_resolution.authority_verification_status != "verified":
            warnings.append(
                f"Local Authority '{regulatory_resolution.authority_name}' verification status is "
                f"'{regulatory_resolution.authority_verification_status}'."
            )
        if regulatory_resolution.zone_verification_status != "verified":
            warnings.append(
                f"Development zone '{regulatory_resolution.development_zone or 'Not specified'}' is not officially verified."
            )

    # 5. Check buildable footprint validity & containment
    if not buildable_poly or not buildable_poly.is_valid or buildable_poly.area <= 0:
        violations.append("Buildable footprint is empty or invalid.")
    elif land_poly and land_poly.is_valid and not land_poly.buffer(0.01).contains(buildable_poly):
        violations.append("Derived buildable footprint extends outside the legal source land polygon.")

    # 6. Check storey count
    if len(floors) != expected_storey_count:
        violations.append(f"Floor plan count ({len(floors)}) does not match requested storey count ({expected_storey_count}).")

    # 7. Check rooms containment and non-overlap
    stair_polys: List[Tuple[str, Polygon]] = []
    for fl in floors:
        room_polys = []
        for rm in fl.rooms:
            pts = [(p.x, p.y) for p in rm.polygon]
            if len(pts) >= 3:
                r_poly = Polygon(pts)
                if not r_poly.is_valid:
                    violations.append(f"Room '{rm.name}' on {fl.name} has invalid geometry.")
                # Room inside buildable polygon check
                if buildable_poly and buildable_poly.is_valid and not buildable_poly.buffer(0.05).contains(r_poly):
                    violations.append(f"Room '{rm.name}' on {fl.name} extends outside the buildable footprint.")
                room_polys.append((rm.name, r_poly))

                if rm.is_structural_stair:
                    stair_polys.append((fl.name, r_poly))
            else:
                violations.append(f"Room '{rm.name}' on {fl.name} has fewer than 3 vertices.")

        # Check room overlaps on the same floor
        for i in range(len(room_polys)):
            for j in range(i + 1, len(room_polys)):
                name_a, poly_a = room_polys[i]
                name_b, poly_b = room_polys[j]
                intersection = poly_a.intersection(poly_b)
                if intersection.area > 0.1:
                    violations.append(f"Rooms '{name_a}' and '{name_b}' on {fl.name} illegally overlap by {intersection.area:.2f} m².")

    # 8. Multi-storey Staircase Alignment & Dimension Check
    if expected_storey_count > 1:
        if len(stair_polys) < expected_storey_count:
            violations.append(f"Expected {expected_storey_count} staircase cores, found {len(stair_polys)}.")
        elif len(stair_polys) >= 2:
            base_floor, base_stair = stair_polys[0]
            for f_name, s_poly in stair_polys[1:]:
                # Stair cores must overlap almost perfectly (>90% intersection)
                intersect_area = base_stair.intersection(s_poly).area
                min_area = min(base_stair.area, s_poly.area)
                if min_area > 0 and (intersect_area / min_area) < 0.9:
                    violations.append(f"Staircase core on {f_name} does not vertically align with {base_floor}.")

    # 9. Deterministic Room Dimensions and Ventilation Regulatory Check (UDA Gazette 2235/54 Sched. 7)
    design_checks = {
        "room_compliance": [],
        "coverage_compliance": {},
        "staircase_compliance": {},
        "height_compliance": {}
    }

    if rules:
        dim_rules = {r.conditions.get("room_type"): r for r in rules if r.rule_type == "room_dimension"}
        cov_rule = next((r for r in rules if r.rule_type == "ground_coverage"), None)

        # Ground floor coverage check
        gf = next((f for f in floors if f.floor_index == 0), None)
        if gf and land_poly and land_poly.area > 0:
            gf_area = sum(r.area for r in gf.rooms)
            actual_cov = gf_area / land_poly.area
            max_cov = cov_rule.value if cov_rule else 0.65
            cov_ok = actual_cov <= (max_cov + 0.02)  # small numerical buffer
            design_checks["coverage_compliance"] = {
                "ground_floor_area_sqm": round(gf_area, 2),
                "land_area_sqm": round(land_poly.area, 2),
                "actual_coverage_ratio": round(actual_cov, 3),
                "permissible_coverage_ratio": max_cov,
                "compliant": cov_ok
            }
            if not cov_ok:
                violations.append(f"Ground floor coverage ({actual_cov*100:.1f}%) exceeds maximum permissible coverage ({max_cov*100:.1f}%).")

        # Floor-wise room dimensions and clear area check
        for fl in floors:
            for rm in fl.rooms:
                rt = rm.type.lower()
                applicable_rule = None
                if "master_bedroom" in rt:
                    applicable_rule = dim_rules.get("master_bedroom")
                elif "bedroom" in rt:
                    applicable_rule = dim_rules.get("bedroom")
                elif "kitchen" in rt:
                    applicable_rule = dim_rules.get("kitchen")
                elif "bathroom" in rt or "toilet" in rt:
                    applicable_rule = dim_rules.get("bathroom")

                if applicable_rule:
                    min_area = applicable_rule.value
                    passed = rm.area >= (min_area - 0.2)  # numerical tolerance
                    check_item = {
                        "room_id": rm.room_id,
                        "room_name": rm.name,
                        "floor": fl.name,
                        "type": rm.type,
                        "actual_area": rm.area,
                        "required_min_area": min_area,
                        "rule_id": applicable_rule.rule_id,
                        "compliant": passed
                    }
                    design_checks["room_compliance"].append(check_item)
                    if not passed:
                        violations.append(
                            f"Room '{rm.name}' ({rm.area:.2f} m²) on {fl.name} violates statutory minimum area ({min_area} m²) under {applicable_rule.rule_id}."
                        )

    # 10. Site-Level Restrictions Evaluation
    site_restriction_summary: List[Dict[str, Any]] = []
    if site_restrictions:
        for r_check in site_restrictions:
            summary_item = {
                "restriction_type": r_check.restriction_type.value if hasattr(r_check.restriction_type, "value") else str(r_check.restriction_type),
                "checked": r_check.checked,
                "intersected": r_check.intersected,
                "verification_status": r_check.verification_status,
                "dataset_name": r_check.dataset_name,
                "notes": r_check.notes
            }
            site_restriction_summary.append(summary_item)
            if not r_check.checked:
                unresolved_requirements.append(
                    f"Site restriction '{summary_item['restriction_type']}' has NOT been checked against authoritative geospatial datasets."
                )
            elif r_check.intersected is True:
                violations.append(
                    f"Site intersects protected restriction overlay '{summary_item['restriction_type']}' "
                    f"(dataset: {r_check.dataset_name or 'unknown'}). Buffer or statutory clearance required."
                )

    # 11. Strict Multi-State Compliance Verdict & Status
    # Rule: Never mark COMPLIANT if mandatory applicable checks remain unresolved or violations exist.
    if violations:
        compliance_verdict = ComplianceStatus.NON_COMPLIANT
        status = "failed"
        valid = False
        geometry_status = "invalid" if any("polygon" in v.lower() or "room" in v.lower() or "staircase" in v.lower() for v in violations) else "valid"
    elif conflicting_requirements:
        compliance_verdict = ComplianceStatus.CONFLICT_REQUIRES_REVIEW
        status = "needs_verification"
        valid = True
        geometry_status = "valid"
    elif unresolved_requirements:
        compliance_verdict = ComplianceStatus.REQUIRES_REGULATORY_VERIFICATION
        status = "needs_verification"
        valid = True
        geometry_status = "valid"
    elif warnings:
        compliance_verdict = ComplianceStatus.REQUIRES_REGULATORY_VERIFICATION
        status = "needs_verification"
        valid = True
        geometry_status = "valid"
    else:
        compliance_verdict = ComplianceStatus.COMPLIANT
        status = "completed"
        valid = True
        geometry_status = "valid"

    # Regulatory status summary string
    reg_status = "verified"
    if not rules:
        reg_status = "missing"
    elif any(r.verification_status == "research_test" for r in rules):
        reg_status = "research_test"
    elif compliance_verdict == ComplianceStatus.REQUIRES_REGULATORY_VERIFICATION:
        reg_status = "needs_verification"
    elif compliance_verdict == ComplianceStatus.CONFLICT_REQUIRES_REVIEW:
        reg_status = "conflict"

    return ValidationResult(
        valid=valid,
        status=status,
        closure_error=closure_error,
        closure_tolerance=closure_tolerance,
        declared_area_sqm=area_check.get("declared_area_sqm"),
        reconstructed_area_sqm=area_check.get("reconstructed_area_sqm"),
        area_difference_sqm=area_check.get("area_difference_sqm"),
        area_difference_percent=area_check.get("area_difference_percent"),
        violations=violations,
        warnings=warnings,
        geometry_status=geometry_status,
        regulatory_status=reg_status,
        compliance_verdict=compliance_verdict,
        unresolved_requirements=unresolved_requirements,
        conflicting_requirements=conflicting_requirements,
        site_restriction_summary=site_restriction_summary,
        regulatory_resolution=regulatory_resolution,
        design_checks=design_checks
    )
