"""
ESAI Ergonomic Constraint Evaluator
Audits spatial arrangements against verified Neufert & ISO 7250 ergonomic rules.
Separates verified mandatory hard constraints from soft advisory design heuristics.
"""
import math
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from shapely.geometry import box, Polygon
from shapely.affinity import rotate, translate

from ..contracts import (
    ClearanceDirection,
    ConstraintPriority,
    ResolvedErgonomicConstraintDTO,
    StandardVerificationStatus,
)
from .chromosome import PlacedAssetDTO


class ErgonomicRuleResultDTO(BaseModel):
    rule_id: str
    source_title: str
    source_edition: str
    source_section: str
    verification_status: str
    clearance_direction: str
    required_threshold_m: float
    measured_clearance_m: float
    is_mandatory: bool
    passed: bool
    notes: str


class ErgonomicEvaluationResult(BaseModel):
    is_valid: bool = True
    violations: List[str] = Field(default_factory=list)
    ergonomic_score: float = 1.0
    evaluations: List[ErgonomicRuleResultDTO] = Field(default_factory=list)


class ErgonomicConstraintEvaluator:
    """
    Evaluates verified Neufert clearances and accessibility buffer zones.
    """

    def __init__(
        self,
        rules: List[ResolvedErgonomicConstraintDTO],
        room_polygon: Polygon,
    ):
        self.rules = rules
        self.room_polygon = room_polygon

    def evaluate(self, placed_assets: List[PlacedAssetDTO]) -> ErgonomicEvaluationResult:
        """
        Tests each placed asset against applicable ergonomic clearance rules.
        """
        violations: List[str] = []
        rule_results: List[ErgonomicRuleResultDTO] = []
        score_accum = 0.0
        score_count = 0

        # Build map of assets by category
        category_map: Dict[str, List[PlacedAssetDTO]] = {}
        for asset in placed_assets:
            category_map.setdefault(asset.category.lower().strip(), []).append(asset)
            category_map.setdefault(asset.subtype.lower().strip(), []).append(asset)

        # Other footprints to check against for clearance obstruction
        all_footprints = [a.footprint_polygon for a in placed_assets if a.footprint_polygon]

        for rule in self.rules:
            # Check which assets this rule applies to
            matching_assets: List[PlacedAssetDTO] = []
            for app_cat in rule.applicable_categories:
                clean_cat = app_cat.lower().strip()
                if clean_cat == "all":
                    matching_assets = list(placed_assets)
                    break
                matching_assets.extend(category_map.get(clean_cat, []))

            # Deduplicate by instance_id
            seen_ids = set()
            unique_matches = []
            for ma in matching_assets:
                if ma.instance_id not in seen_ids:
                    seen_ids.add(ma.instance_id)
                    unique_matches.append(ma)

            for target_asset in unique_matches:
                score_count += 1
                clearance_poly = self._create_clearance_zone(
                    target_asset,
                    rule.clearance_direction,
                    rule.threshold_m,
                )

                # Measure overlap with other furniture footprints (excluding self)
                other_fps = [
                    a.footprint_polygon
                    for a in placed_assets
                    if a.instance_id != target_asset.instance_id and a.footprint_polygon
                ]

                obstructed = False
                max_inter_area = 0.0
                for ofp in other_fps:
                    if clearance_poly.intersects(ofp):
                        inter = clearance_poly.intersection(ofp).area
                        if inter > 0.01:
                            obstructed = True
                            max_inter_area = max(max_inter_area, inter)

                # Check if clearance extends completely outside room
                outside_room = False
                if not self.room_polygon.contains(clearance_poly):
                    outside_area = clearance_poly.difference(self.room_polygon).area
                    rule_dir = rule.clearance_direction.value if hasattr(rule.clearance_direction, "value") else str(rule.clearance_direction)
                    if rule_dir.lower() == "front" and outside_area > 0.05:
                        obstructed = True
                        outside_room = True

                passed = not obstructed
                measured_clearance = rule.threshold_m if passed else max(0.1, rule.threshold_m - math.sqrt(max_inter_area))

                # Scoring
                if passed:
                    score_accum += 1.0
                else:
                    ratio = max(0.0, measured_clearance / rule.threshold_m) if rule.threshold_m > 0 else 0.0
                    score_accum += ratio

                status_val = rule.verification_status.value if hasattr(rule.verification_status, "value") else str(rule.verification_status)
                dir_val = rule.clearance_direction.value if hasattr(rule.clearance_direction, "value") else str(rule.clearance_direction)

                eval_dto = ErgonomicRuleResultDTO(
                    rule_id=rule.rule_id,
                    source_title=rule.source_title,
                    source_edition=rule.source_edition,
                    source_section=rule.source_section,
                    verification_status=status_val,
                    clearance_direction=dir_val,
                    required_threshold_m=rule.threshold_m,
                    measured_clearance_m=round(measured_clearance, 3),
                    is_mandatory=rule.is_mandatory,
                    passed=passed,
                    notes=(
                        f"Compliant ({measured_clearance:.2f}m >= {rule.threshold_m:.2f}m)"
                        if passed else
                        f"Clearance obstructed by other furniture ({measured_clearance:.2f}m < {rule.threshold_m:.2f}m)"
                    ),
                )
                rule_results.append(eval_dto)

                # Hard constraint policy: only fail if rule is mandatory (verified + hard)
                if not passed and rule.is_mandatory:
                    violations.append(
                        f"Hard Ergonomic Violation [{rule.rule_id}]: {target_asset.asset_name} lacks required {dir_val} clearance of {rule.threshold_m}m ({rule.source_title})."
                    )

        ergonomic_score = (score_accum / score_count) if score_count > 0 else 1.0
        is_valid = len(violations) == 0

        return ErgonomicEvaluationResult(
            is_valid=is_valid,
            violations=violations,
            ergonomic_score=round(ergonomic_score, 3),
            evaluations=rule_results,
        )

    def _create_clearance_zone(
        self,
        asset: PlacedAssetDTO,
        direction: ClearanceDirection,
        threshold_m: float,
    ) -> Polygon:
        """
        Creates oriented clearance zone polygon relative to asset orientation.
        """
        w = asset.dimensions.width
        d = asset.dimensions.depth
        hw = w / 2.0
        hd = d / 2.0

        dir_val = direction.value if hasattr(direction, "value") else str(direction).lower().strip()

        # Local clearance box
        if dir_val == "front":
            # Front extends along +Y in local coordinates (depth-wise)
            c_box = box(-hw, hd, hw, hd + threshold_m)
        elif dir_val in ("side", "sides", "both_sides"):
            # Side extends along +X and -X (width-wise)
            c_box = box(-hw - threshold_m, -hd, hw + threshold_m, hd)
        elif dir_val == "left":
            c_box = box(-hw - threshold_m, -hd, -hw, hd)
        elif dir_val == "right":
            c_box = box(hw, -hd, hw + threshold_m, hd)
        elif dir_val in ("rear", "back"):
            # Rear extends along -Y
            c_box = box(-hw, -hd - threshold_m, hw, -hd)
        else:
            # ALL_SIDES / CIRCULATION
            c_box = box(-hw - threshold_m, -hd - threshold_m, hw + threshold_m, hd + threshold_m)

        rotated = rotate(c_box, asset.rotation_deg, origin=(0, 0))
        return translate(rotated, asset.position.x, asset.position.y)
