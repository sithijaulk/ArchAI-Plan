from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any, Mapping, Sequence
from uuid import uuid4

from shapely.geometry import Point, Polygon

from .feasibility import CanonicalProjectGeometry
from .rule_repository import vegetation_catalog
from .schemas import (
    FeasibilityStatus,
    PlantSuitabilityAssessment,
    PlantAlternativeProposal,
    AcceptedPlantAlternative,
)

logger = logging.getLogger(__name__)


def get_plant_catalogue() -> dict[str, Any]:
    """Return the authoritative, versioned vegetation catalogue."""
    return vegetation_catalog()


def get_plant_entry(plant_id: str) -> dict[str, Any] | None:
    """Retrieve a single plant record from the catalogue by its stable identifier."""
    catalog = get_plant_catalogue()
    for entry in catalog.get("entries", []):
        if entry.get("vegetation_id") == plant_id:
            return entry
    return None


def filter_plant_catalogue(
    placement_type: str | None = None,
    category: str | None = None,
    sun_requirement: str | None = None,
    maintenance_level: str | None = None,
    climate_zone: str | None = None,
    query: str | None = None,
    verified_only: bool = False,
) -> list[dict[str, Any]]:
    """Filter the catalogue based on user or spatial criteria without mutating source records."""
    catalog = get_plant_catalogue()
    entries = catalog.get("entries", [])
    filtered: list[dict[str, Any]] = []

    for entry in entries:
        if verified_only and not entry.get("verified_species_data"):
            continue

        if category and entry.get("category") != category:
            continue

        if placement_type:
            p = placement_type.lower()
            if p == "ground" and not entry.get("ground_suitability", True):
                continue
            if p == "container" and not (
                entry.get("container_suitability")
                or entry.get("planter_suitability")
                or entry.get("container_cultivation_supported")
            ):
                continue
            if p == "balcony":
                balcony_status = entry.get("balcony_suitability")
                if balcony_status == "excluded" or balcony_status is False:
                    continue
            if p == "rooftop":
                roof_status = entry.get("rooftop_suitability")
                if roof_status == "excluded" or roof_status is False:
                    continue
            if p == "wall" and not (
                entry.get("vertical_suitability") or entry.get("wall_suitability")
            ):
                continue
            if p == "hanging" and not (
                entry.get("hanging_suitability")
                or entry.get("hanging_basket_suitability")
                or entry.get("category") == "cascading_creeper"
            ):
                continue

        if sun_requirement and sun_requirement != "any":
            req = str(entry.get("sun_requirement") or "adaptable").lower()
            if req != "adaptable" and req != sun_requirement.lower():
                continue

        if maintenance_level and maintenance_level != "any":
            m = str(entry.get("maintenance_level") or "unverified").lower()
            if m != "unverified" and m != maintenance_level.lower():
                continue

        if climate_zone and climate_zone != "unknown":
            climates = entry.get("climate_suitability") or []
            if climates and climate_zone not in climates:
                continue

        if query:
            q = query.lower().strip()
            display = str(entry.get("display_name") or "").lower()
            scientific = str(entry.get("scientific_name") or "").lower()
            notes = str(entry.get("notes") or "").lower()
            if q not in display and q not in scientific and q not in notes:
                continue

        filtered.append(entry)

    return filtered


def evaluate_plant_suitability(
    plant: str | Mapping[str, Any],
    geom: CanonicalProjectGeometry,
    placement_type: str = "ground",
    surface_id: str | None = None,
    sunlight_score: float | None = None,
    climate_zone: str | None = None,
) -> PlantSuitabilityAssessment:
    """
    Truthfully assess a plant against canonical project geometry and known evidence.
    Distinguishes plant botanical suitability, spatial fit, and surface eligibility.
    """
    if isinstance(plant, str):
        entry = get_plant_entry(plant)
        plant_id = plant
    else:
        entry = dict(plant)
        plant_id = str(entry.get("vegetation_id") or "unknown")

    if not entry:
        return PlantSuitabilityAssessment(
            plant_id=plant_id,
            display_name=plant_id,
            scientific_name=None,
            placement_type=placement_type,
            surface_id=surface_id,
            overall_status="review_required",
            plant_suitability="review_required",
            spatial_fit="review_required",
            surface_eligibility="not_applicable",
            reason_codes=["PLANT_NOT_IN_CATALOGUE"],
            explanation=f"Plant ID '{plant_id}' was not found in the versioned botanical catalogue.",
            missing_evidence=[f"plant:{plant_id}:catalogue_record"],
            applicable_rule_ids=["G01"],
            source_revision=geom.source_revision,
        )

    display_name = str(entry.get("display_name") or plant_id)
    scientific_name = entry.get("scientific_name")
    category = str(entry.get("category") or "shrub")
    is_verified = bool(entry.get("verified_species_data", False))
    cat_version = str(get_plant_catalogue().get("catalogue_version", "2.1"))

    canopy_radius = entry.get("canopy_radius_m")
    mature_height = entry.get("mature_height_m")
    root_clearance = entry.get("root_clearance_m")

    reasons: list[str] = []
    missing_evidence: list[str] = []
    rule_ids: list[str] = ["G01"]
    suggested_alternatives: list[PlantAlternativeProposal] = []

    # 1. Botanical Suitability Assessment
    plant_suit = "feasible"
    if climate_zone and climate_zone != "unknown":
        supported_climates = entry.get("climate_suitability") or []
        if supported_climates and climate_zone not in supported_climates:
            plant_suit = "infeasible"
            reasons.append("CLIMATE_ZONE_MISMATCH")

    # Sunlight match
    sun_req = str(entry.get("sun_requirement") or "site_analysis_required")
    if sun_req == "site_analysis_required" or (not is_verified and sunlight_score is None):
        if plant_suit == "feasible":
            plant_suit = "review_required"
        missing_evidence.append(f"plant:{plant_id}:sun_exposure_analysis")
        reasons.append("SUNLIGHT_EVIDENCE_UNVERIFIED")
    elif sunlight_score is not None:
        if sun_req == "full_sun" and sunlight_score < 0.4:
            plant_suit = "infeasible"
            reasons.append("INSUFFICIENT_DIRECT_SUNLIGHT")
        elif sun_req == "full_shade" and sunlight_score > 0.6:
            plant_suit = "infeasible"
            reasons.append("EXCESSIVE_DIRECT_SUNLIGHT")

    # 2. Surface Eligibility Assessment
    surface_elig = "feasible"
    p_type = placement_type.lower()

    if p_type == "ground":
        surface_elig = "feasible"
    elif p_type == "container":
        surface_elig = "feasible"
        is_container_ok = bool(
            entry.get("container_suitability")
            or entry.get("planter_suitability")
            or entry.get("container_cultivation_supported")
        )
        if not is_container_ok:
            surface_elig = "infeasible"
            reasons.append("UNSUPPORTED_CONTAINER_SPECIES")
    elif p_type == "balcony":
        rule_ids.extend(["B01", "B02"])
        if not geom.balconies:
            surface_elig = "not_applicable"
            reasons.append("NO_AUTHORITATIVE_BALCONIES")
        else:
            balcony_suit = entry.get("balcony_suitability")
            if balcony_suit == "excluded" or balcony_suit is False:
                surface_elig = "infeasible"
                reasons.append("SPECIES_EXCLUDED_FROM_BALCONIES")
            else:
                # Structural live load proof requirement
                structural_evidence = geom.structural_evidence.get("balconies", {})
                if not structural_evidence.get("load_bearing_certified"):
                    surface_elig = "review_required"
                    reasons.append("BALCONY_STRUCTURAL_LOAD_UNVERIFIED")
                    missing_evidence.append("balcony:structural_load_certificate")
    elif p_type == "rooftop":
        rule_ids.extend(["R01", "R02"])
        flat_roofs = [r for r in geom.roofs if str(r.get("roof_type") or r.get("type")).lower() == "flat"]
        if not flat_roofs:
            surface_elig = "not_applicable"
            reasons.append("NO_AUTHORITATIVE_FLAT_TERRACES")
        else:
            roof_suit = entry.get("rooftop_suitability")
            if roof_suit == "excluded" or roof_suit is False:
                surface_elig = "infeasible"
                reasons.append("SPECIES_EXCLUDED_FROM_ROOFTOPS")
            else:
                structural_evidence = geom.structural_evidence.get("roofs", {})
                if not structural_evidence.get("terrace_live_load_certified"):
                    surface_elig = "review_required"
                    reasons.append("ROOFTOP_STRUCTURAL_LOAD_UNVERIFIED")
                    missing_evidence.append("rooftop:structural_load_certificate")
    elif p_type == "wall":
        rule_ids.append("V01")
        if not geom.walls:
            surface_elig = "not_applicable"
            reasons.append("NO_AUTHORITATIVE_WALL_FACADES")
        else:
            is_wall_ok = bool(entry.get("vertical_suitability") or entry.get("wall_suitability"))
            if not is_wall_ok:
                surface_elig = "infeasible"
                reasons.append("SPECIES_LACKS_CLIMBING_HABIT")
    elif p_type == "hanging":
        is_hanging_ok = bool(
            entry.get("hanging_suitability")
            or entry.get("hanging_basket_suitability")
            or category == "cascading_creeper"
        )
        if not is_hanging_ok:
            surface_elig = "infeasible"
            reasons.append("SPECIES_LACKS_TRAILING_HABIT")
    else:
        surface_elig = "unsupported"
        reasons.append(f"UNSUPPORTED_PLACEMENT_TYPE_{p_type.upper()}")

    # 3. Spatial Fit Assessment
    spatial_fit = "feasible"
    if p_type == "ground":
        rule_ids.append("G03")
        if canopy_radius is None or mature_height is None:
            spatial_fit = "review_required"
            reasons.append("MISSING_MATURE_DIMENSIONS")
            missing_evidence.append(f"plant:{plant_id}:mature_canopy_radius")
        else:
            r = float(canopy_radius)
            # Evaluate whether exterior ground accommodates a circle of radius r
            can_fit = False
            try:
                eroded = geom.unoccupied_ground.buffer(-r)
                if not eroded.is_empty and eroded.area > 0.05:
                    can_fit = True
            except Exception:
                # Fallback to bounded clearance estimate
                can_fit = geom.unoccupied_area_m2 >= (r * 2) ** 2

            if not can_fit:
                spatial_fit = "infeasible"
                reasons.append("INSUFFICIENT_CANOPY_CLEARANCE")

            # Root clearance near foundation check
            if root_clearance is not None and spatial_fit == "feasible":
                rc = float(root_clearance)
                try:
                    root_safe = geom.unoccupied_ground.difference(geom.house.buffer(rc))
                    if root_safe.is_empty or root_safe.area < 0.1:
                        spatial_fit = "infeasible"
                        reasons.append("INSUFFICIENT_FOUNDATION_SETBACK")
                except Exception:
                    pass

    # Overall Status Determination
    if surface_elig == "not_applicable":
        overall_status: FeasibilityStatus = "not_applicable"
    elif plant_suit == "infeasible" or spatial_fit == "infeasible" or surface_elig == "infeasible":
        overall_status = "infeasible"
    elif plant_suit == "review_required" or spatial_fit == "review_required" or surface_elig == "review_required":
        overall_status = "review_required"
    else:
        overall_status = "feasible"

    # Human-readable explanation
    if overall_status == "feasible":
        explanation = (
            f"'{display_name}' ({scientific_name or 'generic'}) is feasible for {p_type} placement: "
            f"exterior spatial dimensions and biological attributes satisfy evaluated constraints."
        )
    elif overall_status == "infeasible":
        failure_parts = []
        if spatial_fit == "infeasible":
            failure_parts.append(
                f"mature canopy radius ({canopy_radius or 'unknown'}m) exceeds available unbuilt exterior clearance"
            )
        if surface_elig == "infeasible":
            failure_parts.append(f"species or surface is incompatible with {p_type} placement")
        if plant_suit == "infeasible":
            failure_parts.append("environmental/climate mismatch")
        explanation = f"'{display_name}' cannot be placed as requested: " + "; ".join(failure_parts) + "."
    elif overall_status == "not_applicable":
        explanation = f"Placement type '{p_type}' does not apply to this project because required exterior surfaces are absent."
    else:
        explanation = (
            f"'{display_name}' requires additional technical evidence ({', '.join(missing_evidence)}) "
            f"before placement can be verified."
        )

    # Generate Alternative Proposals if Infeasible or Review Required
    if overall_status in {"infeasible", "review_required"} and p_type in {"ground", "balcony", "rooftop", "container"}:
        suggested_alternatives = propose_plant_alternatives(
            original_request=f"plant:{plant_id}",
            failed_reason=explanation,
            geom=geom,
            original_plant_id=plant_id,
            placement_type=p_type,
            catalogue_version=cat_version,
        )

    return PlantSuitabilityAssessment(
        plant_id=plant_id,
        display_name=display_name,
        scientific_name=scientific_name,
        placement_type=p_type,
        surface_id=surface_id,
        overall_status=overall_status,
        plant_suitability=plant_suit,
        spatial_fit=spatial_fit,
        surface_eligibility=surface_elig,
        reason_codes=reasons or ["ASSESSMENT_COMPLETE"],
        explanation=explanation,
        missing_evidence=missing_evidence,
        applicable_rule_ids=rule_ids,
        suggested_alternatives=suggested_alternatives,
        source_revision=geom.source_revision,
        catalogue_version=cat_version,
    )


def propose_plant_alternatives(
    original_request: str,
    failed_reason: str,
    geom: CanonicalProjectGeometry,
    original_plant_id: str | None = None,
    placement_type: str = "ground",
    catalogue_version: str = "2.1",
) -> list[PlantAlternativeProposal]:
    """
    Propose truthful, supported botanical alternatives when an initial request cannot be fulfilled.
    Covers:
    - Compact tree varieties / smaller species
    - Container planters / raised garden beds
    - Vertical wall climbers (if walls present)
    - Balcony pots (if balconies present)
    - Hanging / cascading plants
    Does NOT silently substitute or mark original intent fulfilled without user acceptance.
    """
    proposals: list[PlantAlternativeProposal] = []
    catalog = get_plant_catalogue()
    entries = catalog.get("entries", [])
    seen_alts: set[str] = set()

    # Strategy 1: Compact Tree or Shrub Alternative for Ground
    if placement_type == "ground":
        for entry in entries:
            pid = entry.get("vegetation_id")
            if pid == original_plant_id or pid in seen_alts:
                continue
            cat = entry.get("category")
            canopy_r = entry.get("canopy_radius_m")
            if cat in {"small_tree", "shrub"} and canopy_r is not None and float(canopy_r) <= 1.8:
                # Check spatial fit
                try:
                    eroded = geom.unoccupied_ground.buffer(-float(canopy_r))
                    if not eroded.is_empty and eroded.area > 0.05:
                        seen_alts.add(pid)
                        proposals.append(
                            PlantAlternativeProposal(
                                proposal_id=f"prop_{uuid4().hex[:8]}",
                                original_request=original_request,
                                reason=failed_reason,
                                alternative_plant_id=pid,
                                alternative_display_name=entry.get("display_name", pid),
                                alternative_scientific_name=entry.get("scientific_name"),
                                alternative_category=cat,
                                proposed_placement_type="ground",
                                proposed_surface_id=None,
                                quantity=1,
                                remaining_evidence=[],
                                suitability_explanation=(
                                    f"Compact cultivar '{entry.get('display_name')}' has a mature canopy radius of only "
                                    f"{canopy_r}m and fits within the unbuilt exterior ground clearance."
                                ),
                                source_revision=geom.source_revision,
                                catalogue_version=catalogue_version,
                                status="proposed",
                            )
                        )
                except Exception:
                    pass
            if len(proposals) >= 2:
                break

        # Strategy 2: Container Planter Alternative
        for entry in entries:
            pid = entry.get("vegetation_id")
            if pid in seen_alts or pid == original_plant_id:
                continue
            if entry.get("container_suitability") or entry.get("planter_suitability"):
                seen_alts.add(pid)
                proposals.append(
                    PlantAlternativeProposal(
                        proposal_id=f"prop_{uuid4().hex[:8]}",
                        original_request=original_request,
                        reason=failed_reason,
                        alternative_plant_id=pid,
                        alternative_display_name=entry.get("display_name", pid),
                        alternative_scientific_name=entry.get("scientific_name"),
                        alternative_category="container",
                        proposed_placement_type="container",
                        proposed_surface_id=None,
                        quantity=2,
                        remaining_evidence=[],
                        suitability_explanation=(
                            f"Container planting with '{entry.get('display_name')}' restricts root expansion "
                            "and provides lush greenery without requiring wide open ground."
                        ),
                        source_revision=geom.source_revision,
                        catalogue_version=catalogue_version,
                        status="proposed",
                    )
                )
                break

        # Strategy 3: Vertical Facade Greenery (if exterior walls exist)
        if geom.walls:
            for entry in entries:
                pid = entry.get("vegetation_id")
                if pid in seen_alts:
                    continue
                if entry.get("vertical_suitability") or entry.get("category") == "climber":
                    wall_id = geom.walls[0].get("json_id") or geom.walls[0].get("id")
                    seen_alts.add(pid)
                    proposals.append(
                        PlantAlternativeProposal(
                            proposal_id=f"prop_{uuid4().hex[:8]}",
                            original_request=original_request,
                            reason=failed_reason,
                            alternative_plant_id=pid,
                            alternative_display_name=entry.get("display_name", pid),
                            alternative_scientific_name=entry.get("scientific_name"),
                            alternative_category="climber",
                            proposed_placement_type="wall",
                            proposed_surface_id=wall_id,
                            quantity=1,
                            remaining_evidence=["facade_trellis_support"],
                            suitability_explanation=(
                                f"Climbing greenery '{entry.get('display_name')}' on exterior facade wall {wall_id} "
                                "maximizes vertical foliage without consuming ground footprint."
                            ),
                            source_revision=geom.source_revision,
                            catalogue_version=catalogue_version,
                            status="proposed",
                        )
                    )
                    break

        # Strategy 4: Balcony Pot Greenery (if balcony exists)
        if geom.balconies:
            for entry in entries:
                pid = entry.get("vegetation_id")
                if pid in seen_alts:
                    continue
                if entry.get("balcony_suitability") not in {"excluded", False} and (
                    entry.get("container_suitability") or entry.get("category") in {"shrub", "ground_cover"}
                ):
                    balcony_id = geom.balconies[0].get("json_id") or geom.balconies[0].get("id")
                    seen_alts.add(pid)
                    proposals.append(
                        PlantAlternativeProposal(
                            proposal_id=f"prop_{uuid4().hex[:8]}",
                            original_request=original_request,
                            reason=failed_reason,
                            alternative_plant_id=pid,
                            alternative_display_name=entry.get("display_name", pid),
                            alternative_scientific_name=entry.get("scientific_name"),
                            alternative_category="balcony_pot",
                            proposed_placement_type="balcony",
                            proposed_surface_id=balcony_id,
                            quantity=2,
                            remaining_evidence=["balcony_structural_load_certificate"],
                            suitability_explanation=(
                                f"Balcony potted greenery '{entry.get('display_name')}' utilizes elevated balcony "
                                f"{balcony_id} (subject to structural load certification)."
                            ),
                            source_revision=geom.source_revision,
                            catalogue_version=catalogue_version,
                            status="proposed",
                        )
                    )
                    break

    elif placement_type in {"balcony", "rooftop"}:
        # Alternative for balcony or rooftop when requested plant is excluded
        for entry in entries:
            pid = entry.get("vegetation_id")
            if pid == original_plant_id or pid in seen_alts:
                continue
            if placement_type == "balcony" and entry.get("balcony_suitability") not in {"excluded", False}:
                seen_alts.add(pid)
                proposals.append(
                    PlantAlternativeProposal(
                        proposal_id=f"prop_{uuid4().hex[:8]}",
                        original_request=original_request,
                        reason=failed_reason,
                        alternative_plant_id=pid,
                        alternative_display_name=entry.get("display_name", pid),
                        alternative_scientific_name=entry.get("scientific_name"),
                        alternative_category=entry.get("category", "planter"),
                        proposed_placement_type="balcony",
                        proposed_surface_id=None,
                        quantity=1,
                        remaining_evidence=["balcony_structural_load_certificate"],
                        suitability_explanation=(
                            f"Balcony-compatible species '{entry.get('display_name')}' fits within standard "
                            "balcony planters without exceeding railing height or root depth."
                        ),
                        source_revision=geom.source_revision,
                        catalogue_version=catalogue_version,
                        status="proposed",
                    )
                )
                if len(proposals) >= 2:
                    break

    return proposals


def validate_accepted_alternatives(
    raw_alternatives: Sequence[Mapping[str, Any] | AcceptedPlantAlternative],
    geom: CanonicalProjectGeometry,
) -> list[AcceptedPlantAlternative]:
    """
    Server-side validation of accepted alternatives:
    - Plant ID must exist in the versioned catalogue.
    - Placement type must be supported by the plant.
    - Surface ID must belong to authoritative geometry.
    - Quantity must be positive integer.
    - Does not trust client-supplied 'approved' or 'suitable' flags.
    """
    validated: list[AcceptedPlantAlternative] = []
    catalog = get_plant_catalogue()
    cat_entries = {e["vegetation_id"]: e for e in catalog.get("entries", [])}
    cat_version = str(catalog.get("catalogue_version", "2.1"))

    known_balconies = {
        str(b.get("json_id") or b.get("id"))
        for b in geom.balconies
        if b.get("json_id") or b.get("id")
    }
    known_walls = {
        str(w.get("json_id") or w.get("id"))
        for w in geom.walls
        if w.get("json_id") or w.get("id")
    }
    known_roofs = {
        str(r.get("json_id") or r.get("id"))
        for r in geom.roofs
        if r.get("json_id") or r.get("id")
    }

    for item in raw_alternatives:
        data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        pid = str(data.get("alternative_plant_id") or "").strip()
        if not pid or pid not in cat_entries:
            logger.warning("Rejected alternative with unknown plant ID '%s'", pid)
            continue

        entry = cat_entries[pid]
        p_type = str(data.get("placement_type") or "ground").lower().strip()
        surface_id = data.get("surface_id")
        if surface_id:
            surface_id = str(surface_id).strip()

        # Surface presence check
        if p_type == "balcony" and surface_id and surface_id not in known_balconies:
            logger.warning("Rejected alternative with non-existent balcony surface '%s'", surface_id)
            continue
        if p_type == "wall" and surface_id and surface_id not in known_walls:
            logger.warning("Rejected alternative with non-existent wall surface '%s'", surface_id)
            continue
        if p_type == "rooftop" and surface_id and surface_id not in known_roofs:
            logger.warning("Rejected alternative with non-existent rooftop surface '%s'", surface_id)
            continue

        # Biological check against placement type
        if p_type == "container" and not (
            entry.get("container_suitability") or entry.get("planter_suitability")
        ):
            logger.warning("Plant '%s' does not support container cultivation", pid)
            continue
        if p_type == "wall" and not (
            entry.get("vertical_suitability") or entry.get("category") == "climber"
        ):
            logger.warning("Plant '%s' lacks vertical climbing habit", pid)
            continue

        try:
            qty = max(1, int(data.get("quantity") or 1))
        except (ValueError, TypeError):
            qty = 1

        original_req = str(data.get("original_request") or "user_preference")
        validated.append(
            AcceptedPlantAlternative(
                original_request=original_req,
                alternative_plant_id=pid,
                alternative_display_name=str(entry.get("display_name") or pid),
                placement_type=p_type,
                surface_id=surface_id,
                quantity=qty,
                source_revision=geom.source_revision,
                catalogue_version=cat_version,
                acceptance_status="accepted",
            )
        )

    return validated
