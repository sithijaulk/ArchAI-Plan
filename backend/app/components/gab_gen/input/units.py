"""
Land extent units and drawing-scale handling for GAB-Gen.

All internal area computations use square metres. The original value and unit are
always retained alongside the converted value so the UI can display what the user
(or the deed) actually stated.

Conversion constants are exact by definition:
  1 ft      = 0.3048 m              (international foot)
  1 sq ft   = 0.09290304 m²
  1 perch   = 30.25 sq yd = 272.25 sq ft = 25.29285264 m²
  1 rood    = 40 perches
  1 acre    = 160 perches = 43,560 sq ft = 4046.8564224 m²
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

SQFT_TO_SQM = 0.09290304
PERCH_TO_SQM = 25.29285264
ROOD_TO_SQM = PERCH_TO_SQM * 40.0
ACRE_TO_SQM = 4046.8564224
HECTARE_TO_SQM = 10_000.0

AREA_UNIT_TO_SQM: Dict[str, float] = {
    "sqm": 1.0,
    "sqft": SQFT_TO_SQM,
    "perches": PERCH_TO_SQM,
    "acres": ACRE_TO_SQM,
}

AREA_UNIT_LABELS: Dict[str, str] = {
    "sqm": "Square metres",
    "sqft": "Square feet",
    "perches": "Perches",
    "acres": "Acres",
}

# Plausibility envelope for a single residential parcel. Values outside it are not
# rejected (they may be legitimate) but are reported as warnings for verification.
_MIN_PLAUSIBLE_SQM = 20.0
_MAX_PLAUSIBLE_SQM = 10 * ACRE_TO_SQM

# Survey / deed plans in Sri Lanka are typically drawn between 1:100 and 1:10000.
_TYPICAL_SCALE_RANGE = (50, 10_000)
_MAX_SCALE_DENOMINATOR = 100_000


def _unit_key(unit: Any) -> str:
    return unit.value if hasattr(unit, "value") else str(unit)


def convert_area_to_sqm(value: float, unit: Any) -> float:
    """Converts a land extent to square metres. Raises ValueError on invalid input."""
    key = _unit_key(unit)
    if key not in AREA_UNIT_TO_SQM:
        raise ValueError(f"Unsupported land extent unit '{key}'. Supported: {sorted(AREA_UNIT_TO_SQM)}")
    if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Land extent must be a finite number.")
    if value <= 0:
        raise ValueError("Land extent must be greater than zero.")
    return float(value) * AREA_UNIT_TO_SQM[key]


def convert_sqm_to_unit(area_sqm: float, unit: Any) -> float:
    key = _unit_key(unit)
    if key not in AREA_UNIT_TO_SQM:
        raise ValueError(f"Unsupported land extent unit '{key}'.")
    return float(area_sqm) / AREA_UNIT_TO_SQM[key]


def validate_land_extent(value: Optional[float], unit: Any) -> Dict[str, Any]:
    """
    Validates a declared land extent and returns a structured report:
      {valid, value, unit, area_sqm, errors[], warnings[]}
    """
    errors: List[str] = []
    warnings: List[str] = []
    area_sqm: Optional[float] = None
    key = _unit_key(unit) if unit is not None else None

    try:
        area_sqm = convert_area_to_sqm(value, unit)  # type: ignore[arg-type]
    except ValueError as exc:
        errors.append(str(exc))

    if area_sqm is not None:
        if area_sqm < _MIN_PLAUSIBLE_SQM:
            warnings.append(
                f"Declared extent converts to {area_sqm:.2f} m², which is unusually small for a residential "
                f"parcel. Check the value and unit."
            )
        if area_sqm > _MAX_PLAUSIBLE_SQM:
            warnings.append(
                f"Declared extent converts to {area_sqm:,.0f} m² (> 10 acres). Check the value and unit."
            )

    return {
        "valid": not errors,
        "value": value,
        "unit": key,
        "area_sqm": round(area_sqm, 4) if area_sqm is not None else None,
        "errors": errors,
        "warnings": warnings,
    }


_ARP_PATTERN = re.compile(
    r"""
    (?:A\s*[-:.]?\s*(?P<a1>\d+(?:\.\d+)?)|(?P<a2>\d+(?:\.\d+)?)\s*A)\s*[-,;/\s]*
    (?:R\s*[-:.]?\s*(?P<r1>\d+(?:\.\d+)?)|(?P<r2>\d+(?:\.\d+)?)\s*R)\s*[-,;/\s]*
    (?:P\s*[-:.]?\s*(?P<p1>\d+(?:\.\d+)?)|(?P<p2>\d+(?:\.\d+)?)\s*P)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_acres_roods_perches(text: str) -> Optional[Dict[str, float]]:
    """
    Parses the Sri Lankan deed extent notation, e.g. 'A0-R1-P10.5', '0A 1R 10.5P', 'A. 0 R. 1 P. 10.50'.
    Returns {acres, roods, perches, total_perches, area_sqm} or None if not matched.
    """
    if not text:
        return None
    m = _ARP_PATTERN.search(text.replace("–", "-"))
    if not m:
        return None
    acres = float(m.group("a1") or m.group("a2") or 0)
    roods = float(m.group("r1") or m.group("r2") or 0)
    perches = float(m.group("p1") or m.group("p2") or 0)
    if roods >= 4 or perches >= 40:
        # Outside the A-R-P carry convention; probably an OCR misread. Still return, flagged.
        flagged = True
    else:
        flagged = False
    total_perches = acres * 160 + roods * 40 + perches
    return {
        "acres": acres,
        "roods": roods,
        "perches": perches,
        "total_perches": round(total_perches, 4),
        "area_sqm": round(total_perches * PERCH_TO_SQM, 4),
        "non_canonical": flagged,
    }


_SCALE_PATTERN = re.compile(r"^\s*1\s*[:/]\s*([0-9][0-9,]*(?:\.\d+)?)\s*$")


def parse_scale_ratio(raw: Optional[str]) -> Tuple[Optional[float], List[str], List[str]]:
    """
    Parses a drawing scale ratio such as '1:100', '1 : 1000', '1/500'.
    Returns (denominator | None, errors, warnings).
    """
    errors: List[str] = []
    warnings: List[str] = []
    if raw is None or not str(raw).strip():
        errors.append("Drawing scale ratio is required (e.g. 1:1000).")
        return None, errors, warnings
    m = _SCALE_PATTERN.match(str(raw))
    if not m:
        errors.append(f"Drawing scale '{raw}' is not in the form 1:N (e.g. 1:500).")
        return None, errors, warnings
    denom = float(m.group(1).replace(",", ""))
    if denom <= 0:
        errors.append("Scale denominator must be greater than zero.")
        return None, errors, warnings
    if denom > _MAX_SCALE_DENOMINATOR:
        errors.append(f"Scale 1:{denom:g} is outside the supported range (max 1:{_MAX_SCALE_DENOMINATOR}).")
        return None, errors, warnings
    lo, hi = _TYPICAL_SCALE_RANGE
    if denom < lo or denom > hi:
        warnings.append(
            f"Scale 1:{denom:g} is outside the typical survey-plan range (1:{lo}–1:{hi}). Please verify."
        )
    return denom, errors, warnings


def validate_scale_ratio(raw: Optional[str]) -> Dict[str, Any]:
    denom, errors, warnings = parse_scale_ratio(raw)
    return {
        "valid": not errors,
        "raw": raw,
        "denominator": denom,
        "errors": errors,
        "warnings": warnings,
    }
