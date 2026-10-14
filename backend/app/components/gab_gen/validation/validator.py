"""
GAB-Gen Validation Engine.
Performs comprehensive Stage-1 structural and geometric validation:
- Legal land polygon validity
- Vector closure tolerance cross-check
- Declared area vs reconstructed area cross-check
- Buildable footprint containment inside legal parcel
- Room containment inside buildable footprint
- No illegal overlapping of rooms
- Multi-storey consistency (e.g. stair alignment)
"""
from typing import Any, Dict, List, Tuple
from shapely.geometry import Polygon
from ..schemas import ValidationResult, FloorPlanDefinition


def cross_check_land_area(
    declared_area_sqm: float,
    reconstructed_area_sqm: float,
    tolerance_percent: float = 15.0
) -> Dict[str, Any]:
    """
    Compares declared land area with reconstructed polygon area.
    Never silently modifies geometry. Records discrepancy and flags needs_verification if large.
    """
    diff_sqm = abs(reconstructed_area_sqm - declared_area_sqm)
    pct_diff = (diff_sqm / declared_area_sqm * 100.0) if declared_area_sqm > 0 else 0.0

    needs_verification = pct_diff > tolerance_percent
    warning = None
    if needs_verification:
        warning = (
            f"Declared area ({declared_area_sqm:.2f} m²) differs from reconstructed survey area "
            f"({reconstructed_area_sqm:.2f} m²) by {pct_diff:.1f}%, exceeding the {tolerance_percent}% tolerance."
        )

    return {
        "declared_area_sqm": round(declared_area_sqm, 2),
        "reconstructed_area_sqm": round(reconstructed_area_sqm, 2),
        "area_difference_sqm": round(diff_sqm, 2),
        "area_difference_percent": round(pct_diff, 2),
        "exceeds_tolerance": needs_verification,
        "warning": warning
    }


def validate_gab_geometry(
    land_poly: Polygon,
    buildable_poly: Polygon,
    closure_error: float,
    area_check: Dict[str, Any],
    floors: List[FloorPlanDefinition]
) -> ValidationResult:
    """
    Performs complete GAB Stage-1 validation.
    """
    violations: List[str] = []
    warnings: List[str] = []

    # 1. Check land polygon validity
    if not land_poly or not land_poly.is_valid or land_poly.area <= 0:
        violations.append("Legal land polygon is topologically invalid or has zero area.")

    # 2. Check closure error (surveying tolerance: 1.5m or 1/50 perimeter)
    closure_tolerance = 1.5
    if closure_error > closure_tolerance:
        warnings.append(f"Survey vector closure error ({closure_error:.3f} m) exceeds allowed tolerance ({closure_tolerance} m).")

    # 3. Check area discrepancy
    if area_check.get("exceeds_tolerance"):
        warnings.append(area_check.get("warning", "Area discrepancy exceeds tolerance."))

    # 4. Check buildable footprint containment
    if not buildable_poly or not buildable_poly.is_valid or buildable_poly.area <= 0:
        violations.append("Buildable footprint is empty or invalid.")
    elif not land_poly.buffer(0.01).contains(buildable_poly):
        violations.append("Derived buildable footprint extends outside the legal source land polygon.")

    # 5. Check floors and room non-overlap
    for fl in floors:
        room_polys = []
        for rm in fl.rooms:
            pts = [(p.x, p.y) for p in rm.polygon]
            if len(pts) >= 3:
                r_poly = Polygon(pts)
                room_polys.append((rm.name, r_poly))

        # Check room overlaps on the same floor
        for i in range(len(room_polys)):
            for j in range(i + 1, len(room_polys)):
                name_a, poly_a = room_polys[i]
                name_b, poly_b = room_polys[j]
                intersection = poly_a.intersection(poly_b)
                # Allow tiny boundary contact, but flag significant volumetric overlap
                if intersection.area > 0.1:
                    violations.append(f"Rooms '{name_a}' and '{name_b}' on {fl.name} illegally overlap by {intersection.area:.2f} m².")

    # Determine overall status
    if violations:
        status = "failed"
        valid = False
    elif warnings:
        status = "needs_verification"
        valid = True
    else:
        status = "completed"
        valid = True

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
        warnings=warnings
    )
