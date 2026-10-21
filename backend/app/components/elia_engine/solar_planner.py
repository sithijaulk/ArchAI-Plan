from __future__ import annotations

import math
from typing import Any, Mapping
from shapely.geometry import Polygon, MultiPolygon, Point, box

from .exceptions import ELIAError


def evaluate_solar_structural_evidence(
    supporting_surface_id: str | None,
    master_json: Mapping[str, Any],
    requirements: Mapping[str, Any] | None = None,
    element: Mapping[str, Any] | None = None,
    surface_item: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Authoritative ELIA structural evidence evaluator for solar PV installations.
    
    Zero-Shortcut Contract:
    - Resolves actual supporting roof/terrace surface from Master JSON.
    - Matches evidence scope against project, surface, and installation type.
    - Distinguishes missing evidence (evidence_missing) from invalid evidence (invalid_evidence).
    - Validates numeric capacity and proposed load values; rejects non-finite, negative, and boolean types.
    - Missing proposed load remains review_required (does not silently default to 25.0 kg/m2).
    - Rejects bare boolean flags (certified: true) without verified engineer credentials or capacity.
    - Removes generic total-allowance-minus-150 shortcut; requires explicit scoped capacity or recorded signoff.
    - Distinguishes recorded external signoff from independently verified capacity.
    - Returns structured status, reasons, missing evidence, and provenance.
    """
    s_id = str(supporting_surface_id).strip() if supporting_surface_id is not None else None

    # 1. Resolve actual supporting surface if not directly provided
    if surface_item is None and s_id:
        candidates = []
        raw_surfaces = master_json.get("surfaces")
        if isinstance(raw_surfaces, Mapping):
            s_roofs = raw_surfaces.get("roofs") or raw_surfaces.get("roof_surfaces")
            if isinstance(s_roofs, list):
                candidates.extend(s_roofs)
            s_terr = raw_surfaces.get("terraces") or raw_surfaces.get("flat_roofs")
            if isinstance(s_terr, list):
                candidates.extend(s_terr)
        raw_roofs = master_json.get("roofs") or master_json.get("roof_surfaces")
        if isinstance(raw_roofs, list):
            candidates.extend(raw_roofs)
        raw_terr = master_json.get("terraces") or master_json.get("flat_roofs")
        if isinstance(raw_terr, list):
            candidates.extend(raw_terr)
        exterior = master_json.get("building_exterior")
        if isinstance(exterior, Mapping):
            b_roofs = exterior.get("roofs") or exterior.get("roof_surfaces")
            if isinstance(b_roofs, list):
                candidates.extend(b_roofs)
            b_terr = exterior.get("terraces") or exterior.get("flat_roofs")
            if isinstance(b_terr, list):
                candidates.extend(b_terr)
        house = master_json.get("house")
        if isinstance(house, Mapping):
            h_roof = house.get("roof") or house.get("roofs")
            if isinstance(h_roof, list):
                candidates.extend(h_roof)
            elif isinstance(h_roof, Mapping):
                h_surfaces = h_roof.get("surfaces") or h_roof.get("faces")
                if isinstance(h_surfaces, list):
                    candidates.extend(h_surfaces)

        for c in candidates:
            if isinstance(c, Mapping):
                cid = str(c.get("id") or c.get("json_id") or "").strip()
                if cid.lower() == s_id.lower():
                    surface_item = c
                    break

        if surface_item is None and s_id:
            return {
                "status": "invalid_evidence",
                "is_approved": False,
                "is_preview_provisional": True,
                "reason": f"Supporting roof surface '{s_id}' not found in Master JSON.",
                "missing_evidence": ["authoritative_roof_surfaces"],
                "approval_provenance": "unverified",
                "capacity_provenance": "unverified",
                "engineer_reference": None,
                "supporting_surface_id": s_id,
                "remaining_capacity_kg_m2": None,
                "proposed_load_kg_m2": None,
                "installation_type": None,
            }

    # 2. Extract structural evidence payload
    surf_struct_ev = surface_item.get("structural_evidence") if isinstance(surface_item, Mapping) else None
    master_struct_ev = master_json.get("structural_evidence")
    effective_struct_ev = surf_struct_ev if isinstance(surf_struct_ev, Mapping) else (
        master_struct_ev if isinstance(master_struct_ev, Mapping) else None
    )

    if effective_struct_ev is None:
        return {
            "status": "evidence_missing",
            "is_approved": False,
            "is_preview_provisional": True,
            "reason": "NO_STRUCTURAL_EVIDENCE_PROVIDED",
            "missing_evidence": ["structural_load_certification", "structural_evidence"],
            "approval_provenance": "unverified",
            "capacity_provenance": "unverified",
            "engineer_reference": None,
            "supporting_surface_id": s_id,
            "remaining_capacity_kg_m2": None,
            "proposed_load_kg_m2": None,
            "installation_type": None,
        }

    if not isinstance(effective_struct_ev, Mapping):
        return {
            "status": "invalid_evidence",
            "is_approved": False,
            "is_preview_provisional": True,
            "reason": "MALFORMED_STRUCTURAL_EVIDENCE_PAYLOAD",
            "missing_evidence": ["valid_structural_evidence_record"],
            "approval_provenance": "unverified",
            "capacity_provenance": "unverified",
            "engineer_reference": None,
            "supporting_surface_id": s_id,
            "remaining_capacity_kg_m2": None,
            "proposed_load_kg_m2": None,
            "installation_type": None,
        }

    # 3. Scope matching: surface ID and installation type
    ev_inst_type = effective_struct_ev.get("installation_type")
    req_inst_type = (
        ((requirements or {}).get("solar") or {}).get("installation_type")
        or ((element or {}).get("installation_type"))
    )

    scope_matched = True
    app_surfaces = effective_struct_ev.get("applicable_surface_ids") or effective_struct_ev.get("applicable_surfaces")
    if isinstance(app_surfaces, (list, tuple)):
        if s_id and s_id not in [str(x) for x in app_surfaces]:
            scope_matched = False
    target_surf = effective_struct_ev.get("target_surface_id") or effective_struct_ev.get("surface_id")
    if target_surf is not None and s_id:
        if str(target_surf).lower() != s_id.lower():
            scope_matched = False

    if ev_inst_type and req_inst_type:
        if str(ev_inst_type).strip().lower() != str(req_inst_type).strip().lower():
            scope_matched = False

    if not scope_matched:
        return {
            "status": "review_required",
            "is_approved": False,
            "is_preview_provisional": True,
            "reason": "STRUCTURAL_EVIDENCE_SCOPE_MISMATCH",
            "missing_evidence": ["applicable_surface_or_installation_scope"],
            "approval_provenance": "unverified",
            "capacity_provenance": "unverified",
            "engineer_reference": None,
            "supporting_surface_id": s_id,
            "remaining_capacity_kg_m2": None,
            "proposed_load_kg_m2": None,
            "installation_type": str(ev_inst_type) if ev_inst_type else None,
        }

    # 4. Engineer credentials verification
    cred = (
        effective_struct_ev.get("engineer_license")
        or effective_struct_ev.get("report_id")
        or effective_struct_ev.get("certification_document_id")
    )
    has_engineer_cred = False
    engineer_ref = None
    if cred and isinstance(cred, str) and len(cred.strip()) >= 3:
        cred_str = cred.strip()
        if not any(cred_str.lower().endswith(ext) for ext in [".pdf", ".png", ".jpg", ".txt", ".docx"]):
            has_engineer_cred = True
            engineer_ref = cred_str
        elif effective_struct_ev.get("engineer_license"):
            has_engineer_cred = True
            engineer_ref = str(effective_struct_ev.get("engineer_license")).strip()

    if not has_engineer_cred:
        return {
            "status": "review_required",
            "is_approved": False,
            "is_preview_provisional": True,
            "reason": "MISSING_OR_INVALID_ENGINEER_CREDENTIALS",
            "missing_evidence": ["engineer_license_or_report_id"],
            "approval_provenance": "unverified",
            "capacity_provenance": "unverified",
            "engineer_reference": None,
            "supporting_surface_id": s_id,
            "remaining_capacity_kg_m2": None,
            "proposed_load_kg_m2": None,
            "installation_type": str(ev_inst_type) if ev_inst_type else None,
        }

    # 5. Proposed load validation
    req_load_val = (
        ((requirements or {}).get("solar") or {}).get("proposed_load_kg_m2")
        or ((requirements or {}).get("solar") or {}).get("pv_array_dead_load_kg_m2")
        or ((element or {}).get("proposed_load_kg_m2"))
        or effective_struct_ev.get("proposed_load_kg_m2")
    )

    if req_load_val is not None:
        if isinstance(req_load_val, bool):
            raise ELIAError("ELIA_INVALID_REQUIREMENT", f"Proposed solar PV load must be a finite positive number, got boolean '{req_load_val}'.")
        try:
            proposed_load_kg_m2 = float(req_load_val)
            if not (math.isfinite(proposed_load_kg_m2) and proposed_load_kg_m2 > 0):
                raise ELIAError("ELIA_INVALID_REQUIREMENT", f"Proposed solar PV load must be a finite positive number, got '{req_load_val}'.")
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ELIAError):
                raise
            raise ELIAError("ELIA_INVALID_REQUIREMENT", f"Proposed solar PV load must be a finite positive number, got '{req_load_val}'.") from exc
    else:
        proposed_load_kg_m2 = None

    if proposed_load_kg_m2 is None:
        return {
            "status": "review_required",
            "is_approved": False,
            "is_preview_provisional": True,
            "reason": "MISSING_PROPOSED_PV_LOAD",
            "missing_evidence": ["proposed_pv_load_kg_m2"],
            "approval_provenance": "unverified",
            "capacity_provenance": "missing_proposed_load",
            "engineer_reference": engineer_ref,
            "supporting_surface_id": s_id,
            "remaining_capacity_kg_m2": None,
            "proposed_load_kg_m2": None,
            "installation_type": str(ev_inst_type) if ev_inst_type else None,
        }

    # 6. Capacity and Approval Verification
    rem_cap_raw = effective_struct_ev.get("remaining_capacity_kg_m2") or effective_struct_ev.get("available_solar_capacity_kg_m2")
    allowance_raw = effective_struct_ev.get("roof_allowance_kg_m2") or effective_struct_ev.get("live_load_capacity_kg_m2")

    if isinstance(rem_cap_raw, bool) or isinstance(allowance_raw, bool):
        return {
            "status": "invalid_evidence",
            "is_approved": False,
            "is_preview_provisional": True,
            "reason": "MALFORMED_BOOLEAN_CAPACITY_VALUE",
            "missing_evidence": ["valid_numeric_capacity_value"],
            "approval_provenance": "unverified",
            "capacity_provenance": "invalid_boolean_capacity",
            "engineer_reference": engineer_ref,
            "supporting_surface_id": s_id,
            "remaining_capacity_kg_m2": None,
            "proposed_load_kg_m2": proposed_load_kg_m2,
            "installation_type": str(ev_inst_type) if ev_inst_type else None,
        }

    if rem_cap_raw is not None:
        try:
            rem_val = float(rem_cap_raw)
            if not (math.isfinite(rem_val) and rem_val > 0):
                return {
                    "status": "invalid_evidence",
                    "is_approved": False,
                    "is_preview_provisional": True,
                    "reason": f"Non-finite or non-positive capacity value '{rem_cap_raw}'.",
                    "missing_evidence": ["valid_numeric_capacity_value"],
                    "approval_provenance": "unverified",
                    "capacity_provenance": "invalid_capacity",
                    "engineer_reference": engineer_ref,
                    "supporting_surface_id": s_id,
                    "remaining_capacity_kg_m2": None,
                    "proposed_load_kg_m2": proposed_load_kg_m2,
                    "installation_type": str(ev_inst_type) if ev_inst_type else None,
                }
            if rem_val >= proposed_load_kg_m2:
                return {
                    "status": "approved",
                    "is_approved": True,
                    "is_preview_provisional": False,
                    "reason": "VERIFIED_RESIDUAL_CAPACITY",
                    "missing_evidence": [],
                    "approval_provenance": "independently_verified",
                    "capacity_provenance": f"verified_residual_capacity_{rem_val:.1f}_kg_m2_exceeds_load_{proposed_load_kg_m2:.1f}_kg_m2",
                    "engineer_reference": engineer_ref,
                    "supporting_surface_id": s_id,
                    "remaining_capacity_kg_m2": rem_val,
                    "proposed_load_kg_m2": proposed_load_kg_m2,
                    "installation_type": str(ev_inst_type) if ev_inst_type else None,
                }
            else:
                return {
                    "status": "review_required",
                    "is_approved": False,
                    "is_preview_provisional": True,
                    "reason": "INSUFFICIENT_RESIDUAL_LOAD_CAPACITY",
                    "missing_evidence": ["adequate_residual_load_capacity"],
                    "approval_provenance": "unverified",
                    "capacity_provenance": f"insufficient_residual_capacity_{rem_val:.1f}_kg_m2_for_load_{proposed_load_kg_m2:.1f}_kg_m2",
                    "engineer_reference": engineer_ref,
                    "supporting_surface_id": s_id,
                    "remaining_capacity_kg_m2": rem_val,
                    "proposed_load_kg_m2": proposed_load_kg_m2,
                    "installation_type": str(ev_inst_type) if ev_inst_type else None,
                }
        except (TypeError, ValueError):
            return {
                "status": "invalid_evidence",
                "is_approved": False,
                "is_preview_provisional": True,
                "reason": f"Non-numeric capacity value '{rem_cap_raw}'.",
                "missing_evidence": ["valid_numeric_capacity_value"],
                "approval_provenance": "unverified",
                "capacity_provenance": "invalid_capacity",
                "engineer_reference": engineer_ref,
                "supporting_surface_id": s_id,
                "remaining_capacity_kg_m2": None,
                "proposed_load_kg_m2": proposed_load_kg_m2,
                "installation_type": str(ev_inst_type) if ev_inst_type else None,
            }

    if effective_struct_ev.get("solar_load_certified") is True or bool(effective_struct_ev.get("approved_configuration")):
        return {
            "status": "approved",
            "is_approved": True,
            "is_preview_provisional": False,
            "reason": "RECORDED_EXTERNAL_SIGNOFF",
            "missing_evidence": [],
            "approval_provenance": "recorded_external_signoff",
            "capacity_provenance": "recorded_configuration_signoff",
            "engineer_reference": engineer_ref,
            "supporting_surface_id": s_id,
            "remaining_capacity_kg_m2": None,
            "proposed_load_kg_m2": proposed_load_kg_m2,
            "installation_type": str(ev_inst_type) if ev_inst_type else None,
        }

    if allowance_raw is not None:
        return {
            "status": "review_required",
            "is_approved": False,
            "is_preview_provisional": True,
            "reason": "TOTAL_ALLOWANCE_REQUIRES_PV_SPECIFIC_CALCULATION",
            "missing_evidence": ["remaining_capacity_kg_m2"],
            "approval_provenance": "unverified",
            "capacity_provenance": "total_code_allowance_without_pv_specific_surplus_evidence",
            "engineer_reference": engineer_ref,
            "supporting_surface_id": s_id,
            "remaining_capacity_kg_m2": None,
            "proposed_load_kg_m2": proposed_load_kg_m2,
            "installation_type": str(ev_inst_type) if ev_inst_type else None,
        }

    return {
        "status": "review_required",
        "is_approved": False,
        "is_preview_provisional": True,
        "reason": "MISSING_RESIDUAL_CAPACITY_EVIDENCE",
        "missing_evidence": ["remaining_capacity_kg_m2"],
        "approval_provenance": "unverified",
        "capacity_provenance": "unverified",
        "engineer_reference": engineer_ref,
        "supporting_surface_id": s_id,
        "remaining_capacity_kg_m2": None,
        "proposed_load_kg_m2": proposed_load_kg_m2,
        "installation_type": str(ev_inst_type) if ev_inst_type else None,
    }


def _extract_roof_surfaces(
    master_json: Mapping[str, Any],
    unit_scale: float = 1.0,
    requirements: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Extract and validate authoritative roof and terrace surfaces from Master JSON.
    
    Zero-Fabrication Contract:
    - Never synthesizes a roof from the ground house footprint.
    - Preserves interior cutouts/holes (skylights, HVAC chases).
    - Distinguishes authoritative measurements from missing evidence.
    - Does not invent defaults for missing elevation, pitch, or azimuth.
    - Flatness is established only from explicit metadata or measured pitch < 5 deg.
    """
    if requirements is None:
        requirements = master_json.get("exterior_requirements") or master_json.get("requirements") or {}
    candidates = []
    
    # 1. Direct roofs/terraces lists and surfaces dictionary
    raw_surfaces = master_json.get("surfaces")
    if isinstance(raw_surfaces, Mapping):
        s_roofs = raw_surfaces.get("roofs") or raw_surfaces.get("roof_surfaces")
        if isinstance(s_roofs, list):
            candidates.extend(s_roofs)
        s_terr = raw_surfaces.get("terraces") or raw_surfaces.get("flat_roofs")
        if isinstance(s_terr, list):
            candidates.extend(s_terr)
            
    raw_roofs = master_json.get("roofs") or master_json.get("roof_surfaces")
    if isinstance(raw_roofs, list):
        candidates.extend(raw_roofs)
        
    raw_terraces = master_json.get("terraces") or master_json.get("flat_roofs")
    if isinstance(raw_terraces, list):
        candidates.extend(raw_terraces)
        
    # 2. Check building_exterior nested structure
    exterior = master_json.get("building_exterior")
    if isinstance(exterior, Mapping):
        b_roofs = exterior.get("roofs") or exterior.get("roof_surfaces")
        if isinstance(b_roofs, list):
            candidates.extend(b_roofs)
        b_terr = exterior.get("terraces") or exterior.get("flat_roofs")
        if isinstance(b_terr, list):
            candidates.extend(b_terr)

    # 3. Check house.roof nested structure
    house = master_json.get("house")
    if isinstance(house, Mapping):
        h_roof = house.get("roof") or house.get("roofs")
        if isinstance(h_roof, list):
            candidates.extend(h_roof)
        elif isinstance(h_roof, Mapping):
            h_surfaces = h_roof.get("surfaces") or h_roof.get("faces")
            if isinstance(h_surfaces, list):
                candidates.extend(h_surfaces)

    surfaces = []
    structural_evidence = master_json.get("structural_evidence") or {}

    # Process each surface candidate
    for i, item in enumerate(candidates):
        if not isinstance(item, Mapping):
            continue
        s_id = str(item.get("json_id") or item.get("id") or f"ROOF_{i+1:03d}")
        r_type = str(item.get("roof_type") or item.get("type") or "roof").lower()
        
        # Coordinates extraction preserving outer boundary and interior cutouts/holes
        raw_coords = item.get("polygon") or item.get("coordinates")
        if isinstance(raw_coords, Mapping):
            raw_coords = raw_coords.get("coordinates", [])

        exterior_pts = []
        interior_rings = []
        if isinstance(raw_coords, (list, tuple)) and raw_coords:
            if isinstance(raw_coords[0], (list, tuple)) and raw_coords[0] and isinstance(raw_coords[0][0], (list, tuple)):
                # Ring-of-rings GeoJSON polygon: [ [ [x,y], ... ], [ [x_hole, y_hole], ... ] ]
                ext = raw_coords[0]
                for pt in ext:
                    try:
                        x_f, y_f = float(pt[0]), float(pt[1])
                        if not (math.isfinite(x_f) and math.isfinite(y_f)):
                            raise ELIAError("ELIA_INVALID_ROOF_MEASUREMENT", "Non-finite coordinate in roof polygon.")
                        exterior_pts.append((x_f * unit_scale, y_f * unit_scale))
                    except (TypeError, ValueError, IndexError) as exc:
                        if isinstance(exc, ELIAError):
                            raise
                        continue
                for hole in raw_coords[1:]:
                    if isinstance(hole, (list, tuple)) and len(hole) >= 3:
                        h_pts = []
                        for pt in hole:
                            try:
                                x_f, y_f = float(pt[0]), float(pt[1])
                                if not (math.isfinite(x_f) and math.isfinite(y_f)):
                                    raise ELIAError("ELIA_INVALID_ROOF_MEASUREMENT", "Non-finite coordinate in roof cutout hole.")
                                h_pts.append((x_f * unit_scale, y_f * unit_scale))
                            except (TypeError, ValueError, IndexError) as exc:
                                if isinstance(exc, ELIAError):
                                    raise
                                pass
                        if len(h_pts) >= 3:
                            interior_rings.append(h_pts)
            else:
                for pt in raw_coords:
                    try:
                        x_f, y_f = float(pt[0]), float(pt[1])
                        if not (math.isfinite(x_f) and math.isfinite(y_f)):
                            raise ELIAError("ELIA_INVALID_ROOF_MEASUREMENT", "Non-finite coordinate in roof polygon.")
                        exterior_pts.append((x_f * unit_scale, y_f * unit_scale))
                    except (TypeError, ValueError, IndexError) as exc:
                        if isinstance(exc, ELIAError):
                            raise
                        continue

        if len(exterior_pts) < 3:
            continue
            
        try:
            poly = Polygon(exterior_pts, interior_rings)
        except (TypeError, ValueError, IndexError):
            continue

        if not poly.is_valid or poly.area <= 0:
            continue

        # 1. Elevation: Distinguish authoritative measurements from missing evidence
        elev = item.get("elevation_m") if "elevation_m" in item else item.get("z_m") if "z_m" in item else item.get("elevation") if "elevation" in item else item.get("height_m")
        elevation_m = None
        has_measured_elevation = False
        missing_elevation = False
        if elev is not None:
            try:
                val = float(elev)
                if not math.isfinite(val):
                    raise ELIAError("ELIA_INVALID_ROOF_MEASUREMENT", f"Non-finite elevation value '{elev}' in roof geometry.")
                if 0.0 < val <= 150.0:
                    elevation_m = val
                    has_measured_elevation = True
                else:
                    missing_elevation = True
            except (TypeError, ValueError) as exc:
                if isinstance(exc, ELIAError):
                    raise
                missing_elevation = True
        else:
            missing_elevation = True
        
        display_elevation_m = elevation_m if elevation_m is not None else float(master_json.get("house_height_m") or 6.0)

        # 2. Pitch / Slope: Distinguish explicit flatness, measured pitch, and missing evidence
        explicitly_flat = (
            "flat" in r_type
            or "terrace" in r_type
            or bool(item.get("is_flat"))
            or str(item.get("surface_type") or "").lower() == "flat"
            or str(item.get("surface_type") or "").lower() == "flat_roof"
        )
        pitch = item.get("pitch_degrees") if "pitch_degrees" in item else item.get("pitch_deg") if "pitch_deg" in item else item.get("slope_degrees") if "slope_degrees" in item else item.get("tilt_degrees") if "tilt_degrees" in item else item.get("pitch")
        pitch_deg = None
        has_measured_pitch = False
        missing_pitch = False

        if pitch is not None:
            try:
                val = float(pitch)
                if not math.isfinite(val):
                    raise ELIAError("ELIA_INVALID_ROOF_MEASUREMENT", f"Non-finite pitch value '{pitch}' in roof geometry.")
                if 0.0 <= val < 90.0:
                    pitch_deg = val
                    has_measured_pitch = True
                    is_flat = pitch_deg < 5.0
                    flatness_provenance = "explicit_metadata" if explicitly_flat else "measured_pitch"
                else:
                    missing_pitch = True
                    is_flat = explicitly_flat
                    flatness_provenance = "invalid_measurement"
            except (TypeError, ValueError) as exc:
                if isinstance(exc, ELIAError):
                    raise
                missing_pitch = True
                is_flat = explicitly_flat
                flatness_provenance = "invalid_measurement"
        elif explicitly_flat:
            pitch_deg = 0.0
            has_measured_pitch = False
            missing_pitch = False
            is_flat = True
            flatness_provenance = "explicit_metadata"
        else:
            missing_pitch = True
            is_flat = False
            flatness_provenance = "unknown"

        # 3. Orientation Azimuth: Measured vs Not Applicable (Horizontal) vs Missing
        azimuth = item.get("azimuth_degrees") if "azimuth_degrees" in item else item.get("azimuth_deg") if "azimuth_deg" in item else item.get("orientation_deg") if "orientation_deg" in item else item.get("azimuth") if "azimuth" in item else item.get("rotation_degrees")
        azimuth_deg = None
        has_measured_azimuth = False
        missing_azimuth = False

        if azimuth is not None:
            try:
                val = float(azimuth)
                if not math.isfinite(val):
                    raise ELIAError("ELIA_INVALID_ROOF_MEASUREMENT", f"Non-finite azimuth value '{azimuth}' in roof geometry.")
                if 0.0 <= val <= 360.0:
                    azimuth_deg = val % 360.0
                    has_measured_azimuth = True
            except (TypeError, ValueError) as exc:
                if isinstance(exc, ELIAError):
                    raise
                missing_azimuth = True
        elif is_flat:
            # For a horizontal flat roof, surface azimuth is geometrically not applicable
            azimuth_deg = None
            has_measured_azimuth = False
            missing_azimuth = False
        else:
            # Pitched roof requires orientation azimuth
            missing_azimuth = True

        # 4. Authoritative Structural Live-Load & Net Residual Capacity Evidence Verification
        ev_eval = evaluate_solar_structural_evidence(
            supporting_surface_id=s_id,
            master_json=master_json,
            requirements=requirements,
            surface_item=item,
        )
        is_certified = ev_eval["is_approved"]
        approval_provenance = ev_eval["approval_provenance"]
        capacity_provenance = ev_eval["capacity_provenance"]
        engineer_ref = ev_eval["engineer_reference"]

        surfaces.append({
            "json_id": s_id,
            "type": r_type,
            "is_flat": is_flat,
            "flatness_provenance": flatness_provenance,
            "polygon": poly,
            "raw_coordinates": list(poly.exterior.coords),
            "elevation_m": elevation_m,
            "display_elevation_m": display_elevation_m,
            "has_measured_elevation": has_measured_elevation,
            "missing_elevation": missing_elevation,
            "pitch_deg": pitch_deg,
            "has_measured_pitch": has_measured_pitch,
            "missing_pitch": missing_pitch,
            "azimuth_deg": azimuth_deg,
            "has_measured_azimuth": has_measured_azimuth,
            "missing_azimuth": missing_azimuth,
            "area_m2": poly.area,
            "live_load_certified": is_certified,
            "structural_certification_status": "certified" if is_certified else "unverified",
            "approval_provenance": approval_provenance,
            "capacity_provenance": capacity_provenance,
            "engineer_reference": engineer_ref,
            "access_door": item.get("access_door") or item.get("door_position"),
        })

    return surfaces


def plan_solar_pv(
    master_json: Mapping[str, Any],
    requirements: Mapping[str, Any],
    unit_scale: float = 1.0,
    reserved_roof_zones: list[Polygon] | None = None,
    solar_samples: list[dict[str, Any]] | None = None,
    live_solar: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Plan photovoltaic panel candidate layouts on verified roof or terrace surfaces.
    
    Adheres strictly to the authoritative architecture:
    - Verifies authoritative project location (latitude, longitude).
    - Uses actual roof surface geometry from Master JSON (never synthesizes from house footprint).
    - Preserves interior roof holes (skylights, access shafts, vents).
    - Honors roof tilt and orientation; rejects missing measurements with evidence_missing.
    - Distinguishes provisional geometric preview from structural approval.
    - Explicit surface preferences receive explanations, never silently substituting another roof.
    - Preserves individual module footprints, dimensions, and MultiPolygon geometry.
    - Separates live weather estimates from annual suitability.
    """
    solar_req = requirements.get("solar") or {}
    if not solar_req.get("panels_required", False):
        return None

    # 1. Authoritative Location Verification
    loc = master_json.get("site_location") or master_json.get("location") or master_json.get("geolocation") or {}
    lat = loc.get("latitude") if isinstance(loc, Mapping) else None
    lon = loc.get("longitude") if isinstance(loc, Mapping) else None
    if lat is None or lon is None:
        req_loc = requirements.get("location") or {}
        lat = req_loc.get("latitude")
        lon = req_loc.get("longitude")

    if lat is None or lon is None:
        raise ELIAError("ELIA_INVALID_LOCATION", "Solar panel planning requires validated project latitude and longitude.")

    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError) as exc:
        raise ELIAError("ELIA_INVALID_LOCATION", "Project latitude and longitude must be numeric.") from exc

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ELIAError("ELIA_INVALID_LOCATION", "Latitude or longitude is outside valid terrestrial bounds.")

    # 2. Extract Candidate Roof Surfaces (Strictly without fabricating roof from house footprint)
    surfaces = _extract_roof_surfaces(master_json, unit_scale, requirements=requirements)
    if not surfaces:
        return {
            "status": "evidence_missing",
            "feasibility_status": "evidence_missing",
            "reason": "MISSING_ROOF_GEOMETRY",
            "explanation": "Authoritative Master JSON contains no roof or terrace surfaces. ELIA does not synthesize roof geometry from the house footprint.",
            "missing_evidence": ["authoritative_roof_surfaces", "roof_surface_polygons", "roof_slope_and_orientation", "structural_load_certification"],
            "module_count": 0,
            "system_capacity_kw": 0.0,
        }

    # 3. Surface Selection & Explicit Preference Handling
    pref_surf = str(solar_req.get("preferred_roof_surface") or solar_req.get("preferred_roof_surface_id") or "auto").strip()
    selected_surface = None
    
    if pref_surf.lower() != "auto":
        for s in surfaces:
            if s["json_id"].lower() == pref_surf.lower():
                selected_surface = s
                break
        if selected_surface is None:
            # Must NOT silently switch to another roof surface
            return {
                "status": "infeasible",
                "feasibility_status": "infeasible",
                "reason": "REQUESTED_ROOF_SURFACE_NOT_FOUND",
                "explanation": f"Explicitly requested roof surface '{pref_surf}' was not found in the project Master JSON.",
                "supported_alternatives": [s["json_id"] for s in surfaces],
                "module_count": 0,
                "system_capacity_kw": 0.0,
            }

    if selected_surface is None:
        # Selection evaluating usable roof area and integrated solar insolation from solar evidence
        def _surface_score(s: dict[str, Any]) -> float:
            score = float(s["area_m2"])
            if s["is_flat"]:
                pitch_rad = math.radians(12.0)  # Standard 12-deg racking tilt on flat terrace
                az_rad = math.radians(180.0)    # South racking orientation
            else:
                pitch_rad = math.radians(s["pitch_deg"] if s["pitch_deg"] is not None else 0.0)
                az_rad = math.radians(s["azimuth_deg"] if s["azimuth_deg"] is not None else 180.0)

            if solar_samples:
                # Direct beam insolation integration across sun-up hours
                # cos(theta) = sin(alpha)*cos(beta) + cos(alpha)*sin(beta)*cos(gamma_s - gamma)
                sample_sum = 0.0
                total_weight = 0.0
                for sample in solar_samples:
                    elev = sample.get("solar_elevation_degrees") if "solar_elevation_degrees" in sample else sample.get("elevation")
                    az = sample.get("solar_azimuth_degrees") if "solar_azimuth_degrees" in sample else sample.get("azimuth")
                    if elev is None or az is None or float(elev) <= 0.0:
                        continue
                    alpha = math.radians(float(elev))
                    gamma_s = math.radians(float(az))
                    cos_theta = math.sin(alpha) * math.cos(pitch_rad) + math.cos(alpha) * math.sin(pitch_rad) * math.cos(gamma_s - az_rad)
                    incident = max(0.0, cos_theta)
                    # Weight by direct normal irradiance or beam weight if available
                    w = float(sample.get("direct_normal_irradiance") or sample.get("direct_radiation") or sample.get("dni") or 1.0)
                    if math.isfinite(w) and w > 0:
                        sample_sum += incident * math.sin(alpha) * w
                        total_weight += math.sin(alpha) * w
                if total_weight > 0:
                    insolation_factor = 0.5 + 1.5 * (sample_sum / total_weight)
                    score *= insolation_factor
                elif s["is_flat"]:
                    score *= 1.25
            elif not s["is_flat"] and s["azimuth_deg"] is not None:
                # Equator-facing orientation heuristic (facing south in northern tropics)
                az = s["azimuth_deg"] % 360.0
                orientation_factor = max(0.2, math.cos(math.radians(az - 180.0)))
                score *= (1.0 + orientation_factor)
            elif s["is_flat"]:
                score *= 1.25 # Flat terrace offers flexible racking alignment
            return score

        selected_surface = max(surfaces, key=_surface_score)

    # 4. Check for Missing Crucial Surface Measurements
    if selected_surface.get("missing_elevation"):
        return {
            "status": "evidence_missing",
            "feasibility_status": "evidence_missing",
            "reason": "MISSING_ROOF_ELEVATION",
            "explanation": f"Roof surface '{selected_surface['json_id']}' lacks measured elevation height in Master JSON. ELIA does not invent default roof heights.",
            "missing_evidence": ["elevation_m"],
            "surface_id": selected_surface["json_id"],
            "module_count": 0,
            "system_capacity_kw": 0.0,
        }

    if selected_surface.get("missing_pitch"):
        return {
            "status": "evidence_missing",
            "feasibility_status": "evidence_missing",
            "reason": "MISSING_ROOF_PITCH",
            "explanation": f"Roof surface '{selected_surface['json_id']}' is not declared flat and lacks measured pitch/slope in Master JSON.",
            "missing_evidence": ["roof_pitch_degrees"],
            "surface_id": selected_surface["json_id"],
            "module_count": 0,
            "system_capacity_kw": 0.0,
        }

    if not selected_surface["is_flat"] and selected_surface.get("missing_azimuth"):
        return {
            "status": "evidence_missing",
            "feasibility_status": "evidence_missing",
            "reason": "MISSING_ROOF_AZIMUTH",
            "explanation": f"Pitched roof surface '{selected_surface['json_id']}' lacks measured orientation azimuth in Master JSON.",
            "missing_evidence": ["roof_orientation_azimuth"],
            "surface_id": selected_surface["json_id"],
            "module_count": 0,
            "system_capacity_kw": 0.0,
        }

    # 5. Usable Area Calculation (Edge Setbacks, Doorway Clearances, and Reserved Terrace Zones)
    roof_poly = selected_surface["polygon"]
    edge_setback = 0.5 # 0.5m setback from roof edge for wind safety & perimeter access
    usable_area = roof_poly.buffer(-edge_setback)

    door_pos = selected_surface.get("access_door")
    if door_pos and isinstance(door_pos, (list, tuple)) and len(door_pos) >= 2:
        try:
            door_pt = Point(float(door_pos[0]), float(door_pos[1]))
            usable_area = usable_area.difference(door_pt.buffer(1.2)) # 1.2m clear doorway egress
        except Exception:
            pass

    if reserved_roof_zones:
        for r_zone in reserved_roof_zones:
            if r_zone and not r_zone.is_empty:
                usable_area = usable_area.difference(r_zone.buffer(0.3))

    if usable_area.is_empty or usable_area.area < 4.0:
        return {
            "status": "infeasible",
            "feasibility_status": "infeasible",
            "reason": "INSUFFICIENT_UNSHADED_ROOF_SPACE",
            "explanation": "Insufficient roof surface area remains after mandatory 0.5m safety setbacks and access corridors.",
            "module_count": 0,
            "system_capacity_kw": 0.0,
            "surface_id": selected_surface["json_id"],
        }

    # 6. Panel Array Layout Geometry & Stable Module Identification
    # Standard 400W commercial PV module: 1.75m length x 1.05m width
    panel_w = 1.05
    panel_l = 1.75
    module_rating_kw = 0.400

    # Distinguish adjustable panel racking tilt (design variable) from measured roof pitch
    if selected_surface["is_flat"]:
        racking_tilt = float(solar_req.get("racking_tilt_degrees") or 12.0)
        tilt_deg = racking_tilt
        azimuth_deg = 180.0 # Facing South
        row_pitch_m = panel_l * math.cos(math.radians(tilt_deg)) + 0.45 # Inter-row shading corridor
    else:
        tilt_deg = float(selected_surface["pitch_deg"])
        azimuth_deg = float(selected_surface["azimuth_deg"])
        row_pitch_m = panel_l + 0.10 # Coplanar roof mount gap

    req_count = solar_req.get("target_panel_count") or solar_req.get("panel_count")
    max_panels = int(req_count) if req_count else 40

    min_x, min_y, max_x, max_y = usable_area.bounds
    placed_panels: list[Polygon] = []
    placed_modules: list[dict[str, Any]] = []

    y = min_y
    while y + panel_l <= max_y and len(placed_panels) < max_panels:
        x = min_x
        while x + panel_w <= max_x and len(placed_panels) < max_panels:
            candidate = box(x, y, x + panel_w, y + panel_l)
            if usable_area.covers(candidate):
                placed_panels.append(candidate)
                mod_elev = round(selected_surface["display_elevation_m"] + (0.20 if selected_surface["is_flat"] else 0.08), 3)
                mod_id = f"{selected_surface['json_id']}_PV_{len(placed_panels):03d}"
                placed_modules.append({
                    "id": mod_id,
                    "module_id": mod_id,
                    "surface_id": selected_surface["json_id"],
                    "position": [round(candidate.centroid.x, 3), round(candidate.centroid.y, 3)],
                    "center": [round(candidate.centroid.x, 3), round(candidate.centroid.y, 3)],
                    "elevation_m": mod_elev,
                    "coordinates": [list(candidate.exterior.coords)],
                    "polygon": list(candidate.exterior.coords),
                    "dimensions": {
                        "width_m": panel_w,
                        "length_m": panel_l,
                        "depth_m": panel_l,
                        "thickness_m": 0.04,
                    },
                    "tilt_degrees": tilt_deg,
                    "azimuth_degrees": azimuth_deg,
                })
            x += (panel_w + 0.10) # 10cm inter-module gap
        y += row_pitch_m

    module_count = len(placed_panels)
    if module_count == 0:
        return {
            "status": "infeasible",
            "feasibility_status": "infeasible",
            "reason": "INSUFFICIENT_ROOF_AREA_FOR_MODULES",
            "explanation": "No complete 1.75m x 1.05m solar module could fit inside the usable roof boundary.",
            "module_count": 0,
            "system_capacity_kw": 0.0,
            "surface_id": selected_surface["json_id"],
        }

    total_capacity_kw = round(module_count * module_rating_kw, 2)
    array_envelope = placed_panels[0]
    for p in placed_panels[1:]:
        array_envelope = array_envelope.union(p)

    all_mod_x = [pt[0] for m in placed_modules for pt in m["polygon"]]
    all_mod_y = [pt[1] for m in placed_modules for pt in m["polygon"]]
    array_actual_w = round(max(all_mod_x) - min(all_mod_x), 2)
    array_actual_l = round(max(all_mod_y) - min(all_mod_y), 2)

    # 7. Truthful Solar Radiation & Energy Yield Modeling
    # Empirical baseline: ~4.5 PSH for tropical latitude; clearly marked as preliminary heuristic
    assumed_psh = 4.5
    system_pr = 0.78
    rough_daily_kwh = round(total_capacity_kw * assumed_psh * system_pr, 1)
    rough_annual_kwh = round(total_capacity_kw * assumed_psh * 365.0 * system_pr, 0)

    # 8. Structural Certification & Approval Separation
    is_certified = bool(selected_surface.get("live_load_certified", False))
    structural_status = "certified" if is_certified else "unverified"
    approval_provenance = selected_surface.get("approval_provenance", "unverified")
    capacity_provenance = selected_surface.get("capacity_provenance", "unverified")
    
    if is_certified:
        plan_status = "fulfilled"
        approval_status = "approved"
        validation_valid = True
        is_provisional = False
        structural_disclaimer = (
            "Authoritative structural live-load certification is recorded in Master JSON (recorded_external_signoff). "
            "Professional electrical schematic and utility grid-interconnection approval required before commissioning."
        )
    else:
        plan_status = "review_required"
        approval_status = "provisional_review_required"
        validation_valid = False
        is_provisional = True
        structural_disclaimer = (
            "PROVISIONAL GEOMETRIC PREVIEW ONLY. Supporting roof surface lacks verified structural live-load "
            "certification in Master JSON. Physical installation cannot be accepted without certified structural engineer sign-off."
        )

    center = array_envelope.centroid
    elevation_val = selected_surface["display_elevation_m"]
    mount_offset = 0.20 if selected_surface["is_flat"] else 0.08

    outdoor_element = {
        "json_id": "SOLAR_ARRAY_001",
        "type": "solar_panel_array",
        "supporting_surface_id": selected_surface["json_id"],
        "position": [round(center.x, 3), round(center.y, 3)],
        "elevation_m": round(elevation_val + mount_offset, 3),
        "elevation_provenance": "authoritative" if selected_surface["has_measured_elevation"] else "estimated_display_only",
        "dimensions": {
            "width_m": array_actual_w,
            "length_m": array_actual_l,
            "depth_m": array_actual_l,
            "module_width_m": panel_w,
            "module_length_m": panel_l,
        },
        "polygon": list(array_envelope.exterior.coords) if array_envelope.geom_type == "Polygon" else list(placed_panels[0].exterior.coords),
        "multi_polygon": [list(poly.exterior.coords) for poly in array_envelope.geoms] if array_envelope.geom_type == "MultiPolygon" else None,
        "modules": placed_modules,
        "panels": [m["polygon"] for m in placed_modules],
        "panel_count": module_count,
        "installed_capacity_kw": total_capacity_kw,
        "tilt_degrees": tilt_deg,
        "azimuth_degrees": azimuth_deg,
        "validation": {
            "valid": validation_valid,
            "provisional_geometric_preview": is_provisional,
            "supporting_surface": selected_surface["json_id"],
            "edge_setback_verified": True,
            "structural_certification_status": structural_status,
            "approval_provenance": approval_provenance,
            "capacity_provenance": capacity_provenance,
            "technical_disclaimer": structural_disclaimer,
        },
        "render": {
            "asset_id": "solar_panel_array_generic",
            "visible": True,
        }
    }

    result = {
        "status": plan_status,
        "approval_status": approval_status,
        "valid": validation_valid,
        "provisional_geometric_preview": is_provisional,
        "surface_id": selected_surface["json_id"],
        "target_surface_id": selected_surface["json_id"],
        "surface_type": selected_surface["type"],
        "module_count": module_count,
        "module_wattage_w": int(module_rating_kw * 1000),
        "system_capacity_kw": total_capacity_kw,
        "tilt_degrees": tilt_deg,
        "azimuth_degrees": azimuth_deg,
        "structural_certification_status": structural_status,
        "approval_provenance": approval_provenance,
        "capacity_provenance": capacity_provenance,
        "estimated_annual_yield_kwh": rough_annual_kwh,
        "estimated_daily_yield_kwh": rough_daily_kwh,
        "outdoor_element": outdoor_element,
        "modules": placed_modules,
        "panels": [m["polygon"] for m in placed_modules],
        "energy_estimation": {
            "annual_yield_status": "unavailable_no_tmy_simulation",
            "annual_yield_unavailable_reason": (
                "Authoritative annual PV yield requires localized typical meteorological year (TMY/PVGIS) time-series data. "
                "ELIA does not synthesize unmeasured annual insolation."
            ),
            "is_rough_preliminary_estimate": True,
            "assumed_daily_psh": assumed_psh,
            "performance_ratio": system_pr,
            "estimated_daily_yield_kwh": rough_daily_kwh,
            "estimated_annual_yield_kwh": rough_annual_kwh,
            "rough_benchmark_annual_yield_kwh": rough_annual_kwh,
            "assumptions": [
                "Empirical tropical baseline (~4.5 PSH); preliminary benchmark only, not on-site pyranometer measurement.",
                "Actual energy generation requires localized meteorological year (TMY) or PVGIS simulation.",
                "Current sun position alone does not determine annual-optimal placement.",
            ],
        },
        "solar_evidence_consumed": {
            "live_solar_available": live_solar is not None and live_solar.get("status") == "available",
            "solar_samples_count": len(solar_samples) if solar_samples else 0,
            "live_solar_note": "Current live condition irradiance is a real-time weather model estimate; not annual cumulative irradiation.",
        },
        "assessment_limitations": [
            "Solar layout is geometric packing based on authoritative roof polygon.",
            "Surrounding external terrain and off-site vegetation shading are unmodeled in 2D Master JSON; full 3D horizon survey required.",
            "Does not replace certified electrical single-line diagram or structural wind-uplift calculation.",
        ]
    }
    
    if not is_certified:
        result["missing_evidence"] = [
            "structural_load_certification",
            "structural_evidence.roof_allowance_kg_m2",
            "structural_evidence.engineer_license"
        ]

    return result
