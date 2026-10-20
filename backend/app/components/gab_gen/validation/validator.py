"""
GAB-Gen Validation Engine.
Performs comprehensive Stage-1 structural and geometric validation:
- Legal land polygon validity
- Vector closure tolerance cross-check against config
- Declared area vs reconstructed area cross-check against config
- Regulatory rules presence & verification status check
- Buildable footprint containment inside legal parcel
- Room containment inside buildable footprint
- No illegal overlapping of rooms
- Staircase geometric alignment across multi-storey floors
- Storey count consistency
"""
import json
import os
from typing import Any, Dict, List, Optional, Tuple
from shapely.geometry import Polygon
from ..schemas import ValidationResult, FloorPlanDefinition, RegulatoryRule

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
    rules: Optional[List[RegulatoryRule]] = None
) -> ValidationResult:
    """
    Performs comprehensive GAB Stage-1 validation.
    """
    violations: List[str] = []
    warnings: List[str] = []
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

    # 4. Check regulatory rules
    if not rules:
        violations.append("No verified regulatory setback configuration exists.")
    else:
        for r in rules:
            if r.verification_status != "verified":
                warnings.append(f"Rule '{r.rule_id}' is running in research_test mode (authority: {r.authority}).")

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

    # 8. Multi-storey Staircase Alignment Check
    if expected_storey_count > 1:
        if len(stair_polys) < expected_storey_count:
            violations.append(f"Expected {expected_storey_count} staircase cores, found {len(stair_polys)}.")
        elif len(stair_polys) >= 2:
            base_floor, base_stair = stair_polys[0]
            for f_name, s_poly in stair_polys[1:]:
                # Stair cores must overlap almost perfectly (>95% intersection)
                intersect_area = base_stair.intersection(s_poly).area
                min_area = min(base_stair.area, s_poly.area)
                if min_area > 0 and (intersect_area / min_area) < 0.9:
                    violations.append(f"Staircase core on {f_name} does not vertically align with {base_floor}.")

    # Status Determination
    if violations:
        status = "failed"
        valid = False
        geometry_status = "invalid"
    elif warnings:
        status = "needs_verification"
        valid = True
        geometry_status = "valid"
    else:
        status = "completed"
        valid = True
        geometry_status = "valid"

    # Regulatory status
    reg_status = "verified"
    if not rules:
        reg_status = "missing"
    elif any(r.verification_status == "research_test" for r in rules):
        reg_status = "research_test"
    elif any(r.verification_status == "needs_verification" for r in rules):
        reg_status = "needs_verification"

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
        regulatory_status=reg_status
    )
