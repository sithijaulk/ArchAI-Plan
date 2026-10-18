from __future__ import annotations

from typing import Any, Mapping, Sequence

from .rule_repository import vegetation_catalog


def build_factors_assessment(
    residual_area_m2: float,
    land_area_m2: float,
    house_area_m2: float,
    vegetation: Sequence[Mapping[str, Any]],
    shadow_samples: Sequence[Mapping[str, Any]],
    requirements: Mapping[str, Any],
    concept_rules_applied: Sequence[str] | None = None,
    budget_assessment: Mapping[str, Any] | None = None,
    validation_summary: Mapping[str, Any] | None = None,
    rule_evaluations: Sequence[Mapping[str, Any]] | None = None,
    category_summaries: Mapping[str, Any] | None = None,
    approval_status: str | None = None,
) -> dict[str, Any]:
    """Generates the comprehensive 7-factor environmental and customer-specific evaluation.

    Factors covered:
    1. Available space
    2. Sunlight
    3. Climate
    4. Water needs
    5. Plant suitability
    6. Maintenance
    7. Design concept

    Derives assessments from actual placed objects, geometric outcomes, and available evidence.
    Excludes all financial/budget estimation.
    """
    landscape_req = dict(requirements.get("landscape") or {})
    factors: list[dict[str, Any]] = []
    applied_rules = list(concept_rules_applied or [])

    garden_requested = bool(
        landscape_req.get("garden_required")
        or landscape_req.get("preferred_vegetation_categories")
        or landscape_req.get("shade_tree_preference")
        or requirements.get("locked_features")
    )
    total_nodes = len(vegetation)

    catalog = vegetation_catalog()
    cat_version = catalog.get("catalogue_version", "2.0")
    cat_entries = {e["vegetation_id"]: e for e in catalog.get("entries", [])}

    # 1. Available Space
    ground_ratio = (residual_area_m2 / land_area_m2) if land_area_m2 > 0 else 0.0
    violations = list((validation_summary or {}).get("violations") or [])
    boundary_conflicts = [v for v in violations if "boundary" in str(v).lower() or "collision" in str(v).lower() or "clearance" in str(v).lower()]

    if residual_area_m2 <= 0:
        space_status = "unmet"
        space_reason = "No unbuilt residual land available outside the building footprint."
    elif boundary_conflicts:
        space_status = "unmet"
        space_reason = f"Geometric spatial constraints violated: {len(boundary_conflicts)} conflict(s) detected with boundaries or setbacks."
    elif garden_requested and total_nodes == 0 and not landscape_req.get("plant_ids_to_avoid"):
        space_status = "unmet"
        space_reason = f"Residual area of {residual_area_m2:.1f} m² could not accommodate the requested vegetation layout."
    else:
        space_status = "satisfied"
        space_reason = (
            f"Residual open area of {residual_area_m2:.1f} m² ({ground_ratio * 100:.1f}% open land) "
            f"accommodates planned layout with required setbacks and circulation."
        )

    factors.append({
        "factor": "available_space",
        "factor_label": "Available Space",
        "input_value": f"Residual land: {residual_area_m2:.1f} m² (Total: {land_area_m2:.1f} m², House: {house_area_m2:.1f} m²)",
        "data_source": "Upstream Survey & Building Footprint Geometry",
        "status": space_status,
        "reason_and_limitations": space_reason
    })

    # 2. Sunlight
    usable_shadows = [s for s in shadow_samples if s.get("status") == "estimated" and s.get("geometry")]
    if total_nodes == 0:
        if garden_requested:
            sun_status = "unmet"
            sun_input = "No vegetation placed to evaluate sunlight"
            sun_reason = "Vegetation was requested but could not be placed; solar exposure cannot be satisfied."
        else:
            sun_status = "not_applicable"
            sun_input = "No vegetation requested"
            sun_reason = "No vegetation requested or planned."
    elif not usable_shadows:
        sun_input = "No estimated shadow samples (missing solar irradiance or orientation)"
        sun_status = "unknown"
        sun_reason = "Sunlight exposure unassessed: no estimated shadow samples available to determine site solar exposure."
    else:
        # Check actual exposure of placed nodes
        sun_input = f"Polygon shadow analysis with {len(usable_shadows)} afternoon solar sample(s)"
        evaluated = 0
        matches = 0
        for n in vegetation:
            sun = n.get("solar_suitability")
            if sun is None:
                continue
            evaluated += 1
            pid = n.get("plant_id")
            entry = cat_entries.get(pid, {})
            sun_req = entry.get("sun_requirement") or "adaptable"
            if sun_req == "full_sun" and sun >= 0.5:
                matches += 1
            elif sun_req == "full_shade" and sun <= 0.4:
                matches += 1
            elif sun_req == "partial_shade" and (0.25 <= sun <= 0.75):
                matches += 1
            elif sun_req in {"adaptable", "site_analysis_required"}:
                matches += 1

        if evaluated == 0:
            sun_status = "unknown"
            sun_reason = "Placed vegetation nodes lack individual sunlight exposure measurements."
        elif matches == evaluated:
            sun_status = "satisfied"
            sun_reason = f"All {evaluated} placed vegetation node(s) with solar data match their species sunlight exposure requirements."
        elif matches > 0:
            sun_status = "unmet"
            sun_reason = f"{matches} of {evaluated} placed plant(s) match species sunlight requirements; remaining node(s) receive suboptimal exposure."
        else:
            sun_status = "unmet"
            sun_reason = f"None of the {evaluated} evaluated vegetation node(s) receive adequate sunlight exposure for their species."

    factors.append({
        "factor": "sunlight",
        "factor_label": "Sunlight Exposure",
        "input_value": sun_input,
        "data_source": "ELIA Analytical Polygon Shadow Projection",
        "status": sun_status,
        "reason_and_limitations": sun_reason
    })

    # 3. Climate
    climate_zone = requirements.get("climate_zone") or landscape_req.get("climate_zone")
    site_location = requirements.get("location", {})
    city_name = site_location.get("city") if isinstance(site_location, dict) else None

    if total_nodes == 0:
        if garden_requested:
            climate_status = "unmet"
            climate_input = "No vegetation placed to evaluate climate"
            climate_reason = "Vegetation was requested but could not be placed; climate compatibility cannot be satisfied."
        else:
            climate_status = "not_applicable"
            climate_input = "No vegetation requested"
            climate_reason = "No vegetation requested or planned."
    elif not climate_zone or climate_zone == "unknown":
        climate_input = f"Locality: {city_name} (Zone unconfirmed)" if city_name else "Unknown / unstated"
        climate_status = "unknown"
        climate_reason = "Climate zone not declared; cannot verify species climate compatibility without site climate context."
    else:
        climate_input = f"Declared zone: {climate_zone.replace('_', ' ').title()}"
        compatible_count = 0
        unverified_count = 0
        incompatible_count = 0
        for n in vegetation:
            pid = n.get("plant_id")
            entry = cat_entries.get(pid, {})
            climates = entry.get("climate_suitability", [])
            if not climates:
                unverified_count += 1
            elif climate_zone in climates:
                compatible_count += 1
            else:
                incompatible_count += 1

        if incompatible_count > 0:
            climate_status = "unmet"
            climate_reason = f"{compatible_count} compatible, {incompatible_count} incompatible with declared {climate_zone.replace('_', ' ')} climate."
        elif unverified_count == total_nodes:
            climate_status = "unknown"
            climate_reason = f"Climate compatibility unverified for generic species in {climate_zone.replace('_', ' ')}."
        elif compatible_count == total_nodes:
            climate_status = "satisfied"
            climate_reason = f"All {compatible_count} placed vegetation node(s) verified compatible with declared {climate_zone.replace('_', ' ')} climate."
        else:
            climate_status = "satisfied" if compatible_count > 0 and incompatible_count == 0 else "unmet"
            climate_reason = f"{compatible_count} of {total_nodes} plant(s) verified compatible with {climate_zone.replace('_', ' ')}; {unverified_count} unverified."

    factors.append({
        "factor": "climate",
        "factor_label": "Climate Suitability",
        "input_value": climate_input,
        "data_source": "Customer Declaration / Location Context",
        "status": climate_status,
        "reason_and_limitations": climate_reason
    })

    # 4. Water Requirements
    water_avail = requirements.get("water_availability") or landscape_req.get("water_availability")
    if total_nodes == 0:
        if garden_requested:
            water_status = "unmet"
            water_input = "No vegetation placed to evaluate water demand"
            water_reason = "Vegetation was requested but could not be placed; water demand cannot be satisfied."
        else:
            water_status = "not_applicable"
            water_input = "No vegetation requested"
            water_reason = "No vegetation requested or planned."
    elif not water_avail or water_avail == "unknown":
        water_input = "Unknown / unstated"
        water_status = "unknown"
        water_reason = "Water supply availability unstated; cannot verify water demand alignment."
    else:
        water_input = f"Availability: {water_avail.replace('_', ' ').title()}"
        matching = 0
        mismatched = 0
        unknown_water = 0
        for n in vegetation:
            pid = n.get("plant_id")
            entry = cat_entries.get(pid, {})
            demand = n.get("water_demand") or entry.get("water_demand")
            if not demand or demand in {"unknown", "unverified"}:
                unknown_water += 1
            elif water_avail == "limited" and demand != "low":
                mismatched += 1
            elif water_avail == "regular" and demand == "high":
                mismatched += 1
            else:
                matching += 1

        if mismatched > 0:
            water_status = "unmet"
            water_reason = f"{mismatched} plant(s) exceed available water regime ({water_avail.replace('_', ' ')}); {matching} matching."
        elif unknown_water == total_nodes:
            water_status = "unknown"
            water_reason = f"Water demand unknown for placed species under {water_avail.replace('_', ' ')} regime."
        elif matching == total_nodes:
            water_status = "satisfied"
            water_reason = f"All {matching} placed plant(s) match the declared water regime ({water_avail.replace('_', ' ')})."
        else:
            water_status = "satisfied" if matching > 0 and mismatched == 0 else "unmet"
            water_reason = f"{matching} plant(s) match {water_avail.replace('_', ' ')}; {unknown_water} have unverified water demand."

    factors.append({
        "factor": "water_needs",
        "factor_label": "Water Requirements",
        "input_value": water_input,
        "data_source": "Client Water Preference Input",
        "status": water_status,
        "reason_and_limitations": water_reason
    })

    # 5. Plant Suitability
    if total_nodes == 0:
        if garden_requested:
            plant_status = "unmet"
            plant_input = "Vegetation requested but not placed"
            plant_reason = "Vegetation was requested but could not be placed due to site constraints, clearances, or plant exclusions."
        else:
            plant_status = "not_applicable"
            plant_input = "No vegetation requested"
            plant_reason = "No vegetation was requested in client requirements."
    else:
        verified_nodes = [n for n in vegetation if n.get("verified_species_data")]
        if len(verified_nodes) == total_nodes:
            plant_status = "satisfied"
            plant_input = f"{len(verified_nodes)} of {total_nodes} node(s) verified"
            plant_reason = "All placed vegetation nodes have verified botanical species data."
        elif len(verified_nodes) > 0:
            plant_status = "unmet"
            plant_input = f"{len(verified_nodes)} of {total_nodes} node(s) verified"
            plant_reason = f"{len(verified_nodes)} node(s) have verified botanical species; {total_nodes - len(verified_nodes)} node(s) use unverified generic envelopes."
        else:
            plant_status = "unknown"
            plant_input = f"0 of {total_nodes} node(s) verified"
            plant_reason = "All placed vegetation nodes use procedural planning envelopes; botanical species suitability not verified."

    factors.append({
        "factor": "plant_suitability",
        "factor_label": "Plant Suitability",
        "input_value": plant_input,
        "data_source": f"ELIA Botanical Catalogue v{cat_version}",
        "status": plant_status,
        "reason_and_limitations": plant_reason
    })

    # 6. Maintenance Preferences
    maint_pref = requirements.get("maintenance_preference") or landscape_req.get("maintenance_preference")
    if not maint_pref and landscape_req.get("low_maintenance_preference") is True:
        maint_pref = "low"

    if total_nodes == 0:
        if garden_requested:
            maint_status = "unmet"
            maint_input = "No vegetation placed to evaluate maintenance"
            maint_reason = "Vegetation was requested but could not be placed; maintenance alignment cannot be satisfied."
        else:
            maint_status = "not_applicable"
            maint_input = "No vegetation requested"
            maint_reason = "No vegetation requested or planned."
    elif not maint_pref or maint_pref in {"no_preference", "unknown"}:
        maint_input = "No specific preference" if maint_pref == "no_preference" else "Unspecified"
        maint_status = "not_applicable" if maint_pref == "no_preference" else "unknown"
        maint_reason = "Standard maintenance schedule accepted." if maint_pref == "no_preference" else "Maintenance expectation unstated."
    else:
        maint_input = f"Preferred level: {maint_pref.title()} Maintenance"
        matching_maint = 0
        mismatched_maint = 0
        unverified_maint = 0
        for n in vegetation:
            pid = n.get("plant_id")
            entry = cat_entries.get(pid, {})
            level = n.get("maintenance_level") or entry.get("maintenance_level")
            if not level or level in {"unverified", "unknown"}:
                unverified_maint += 1
            elif maint_pref == "low" and level != "low":
                mismatched_maint += 1
            elif maint_pref == "medium" and level == "high":
                mismatched_maint += 1
            else:
                matching_maint += 1

        if mismatched_maint > 0:
            maint_status = "unmet"
            maint_reason = f"{mismatched_maint} plant(s) exceed preferred maintenance level '{maint_pref}'; {matching_maint} matching."
        elif unverified_maint == total_nodes:
            maint_status = "unknown"
            maint_reason = f"Maintenance levels unverified for placed species under '{maint_pref}' preference."
        elif matching_maint == total_nodes:
            maint_status = "satisfied"
            maint_reason = f"All {matching_maint} placed plant(s) match the preferred '{maint_pref}' maintenance level."
        else:
            maint_status = "satisfied" if matching_maint > 0 and mismatched_maint == 0 else "unmet"
            maint_reason = f"{matching_maint} plant(s) match '{maint_pref}' maintenance; {unverified_maint} have unverified maintenance levels."

    factors.append({
        "factor": "maintenance",
        "factor_label": "Maintenance Preferences",
        "input_value": maint_input,
        "data_source": "Client Maintenance Input",
        "status": maint_status,
        "reason_and_limitations": maint_reason
    })

    # 7. Design Concept
    concept = requirements.get("design_style") or "contemporary"
    factors.append({
        "factor": "design_concept",
        "factor_label": "Design Concept",
        "input_value": f"Concept: {concept.title()}",
        "data_source": "Client Requirements Selection",
        "status": "satisfied",
        "reason_and_limitations": (
            f"Configured concept '{concept}' applied via procedural planner heuristics: "
            + (", ".join(applied_rules) if applied_rules else "Default balanced arrangement")
            + ". (Note: Procedural rule influence only; not learned weights)."
        )
    })

    res = {
        "assessment_version": "2.1",
        "summary": {
            "total_factors": len(factors),
            "satisfied": sum(1 for f in factors if f["status"] == "satisfied"),
            "unmet": sum(1 for f in factors if f["status"] == "unmet"),
            "unknown": sum(1 for f in factors if f["status"] == "unknown"),
            "not_applicable": sum(1 for f in factors if f["status"] == "not_applicable"),
        },
        "factors": factors
    }
    if rule_evaluations is not None:
        res["rule_evaluations"] = list(rule_evaluations)
    if category_summaries is not None:
        res["category_summaries"] = dict(category_summaries)
    if approval_status is not None:
        res["approval_status"] = approval_status
    return res

