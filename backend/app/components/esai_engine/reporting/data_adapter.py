"""
Phase 8 Report Data Adapter
Extracts authoritative geometry, saved interior layouts, schedules, finishes,
service provisions, and ergonomic validation from project.master_json.
Strictly excludes budgets, prices, monetary values, and cost calculations.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status

from app.models.project import Project
from app.components.esai_engine.geometry import compute_geometry_fingerprint
from .contracts import (
    PdfReportRequest,
    ReportDataDTO,
    ReportScope,
    ReportMode,
    RoomReportDataDTO,
    FloorReportDataDTO,
    RoomScheduleItemDTO,
    LightingScheduleItemDTO,
    ServiceScheduleItemDTO,
    PlumbingScheduleItemDTO,
    FinishScheduleItemDTO,
    ValidationReportItemDTO,
    OptimizationSummaryDTO,
)


class ReportDataAdapter:
    """
    Extracts and normalizes authoritative project data for professional PDF reporting.
    """

    def __init__(self, service: Any):
        self.service = service

    def extract_report_data(self, project: Project, req: PdfReportRequest) -> ReportDataDTO:
        master_json = project.master_json or {}
        floor_plan = master_json.get("floor_plan", {})
        floors = floor_plan.get("floors", [])
        interior_layout = master_json.get("interior_layout", {})
        saved_designs = (
            interior_layout.get("designs", {}).get("rooms")
            or interior_layout.get("rooms")
            or interior_layout.get("saved_designs", {}).get("rooms")
            or {}
        )

        # 1. Structural and Revision Metadata
        current_geo_fp = self.service._get_geo_fingerprint(project)
        saved_geo_fp = interior_layout.get("geometry_fingerprint", "")
        design_revision = int(interior_layout.get("design_revision", 1))
        geometry_revision = int(getattr(project, "revision", 1) or 1)
        preference_revision = int(interior_layout.get("preference_revision", 1))

        # Check staleness
        is_stale = False
        staleness_reasons: List[str] = []
        if saved_geo_fp and saved_geo_fp != current_geo_fp:
            is_stale = True
            staleness_reasons.append("Structural floor plan geometry was modified after interior generation.")

        # In final mode, reject stale designs
        if req.mode == ReportMode.FINAL and is_stale:
            raise HTTPException(
                status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
                detail={
                    "code": "STALE_DESIGN_EXPORT_BLOCKED",
                    "message": "Final validated PDF export is blocked because the design is stale. Regenerate or update the design, or export in Draft mode.",
                    "reasons": staleness_reasons,
                },
            )

        # 2. Filter target rooms based on scope
        target_floors = floors
        target_floor_id = req.target_floor_id or req.floor_id or (req.floor_ids[0] if req.floor_ids else None)
        if req.scope == ReportScope.FLOOR and target_floor_id:
            target_floors = [f for f in floors if (f.get("floor_id") == target_floor_id or f.get("id") == target_floor_id)]
            if not target_floors:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Floor '{target_floor_id}' not found in project '{project.id}'.",
                )

        target_room_ids = set()
        if req.target_room_id:
            target_room_ids.add(req.target_room_id)
        if req.room_id:
            target_room_ids.add(req.room_id)
        if req.room_ids:
            target_room_ids.update(req.room_ids)

        target_rooms_info = []
        for fl in target_floors:
            for rm in fl.get("rooms", []):
                r_id = rm.get("room_id") or rm.get("id")
                if req.scope == ReportScope.ROOM:
                    if target_room_ids and r_id in target_room_ids:
                        target_rooms_info.append((fl, rm))
                else:
                    target_rooms_info.append((fl, rm))

        if req.scope == ReportScope.ROOM:
            found_ids = {r[1].get("room_id") or r[1].get("id") for r in target_rooms_info}
            missing_ids = target_room_ids - found_ids
            if missing_ids or not target_rooms_info:
                req_name = sorted(list(missing_ids))[0] if missing_ids else (list(target_room_ids)[0] if target_room_ids else (req.target_room_id or "unknown"))
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Room '{req_name}' not found in project '{project.id}'.",
                )

        # In final mode, verify all target rooms have valid, complete designs
        if req.mode == ReportMode.FINAL:
            invalid_or_missing = []
            for fl in target_floors:
                for rm in fl.get("rooms", []):
                    r_id = rm.get("room_id") or rm.get("id")
                    if req.scope == ReportScope.ROOM and target_room_ids and r_id not in target_room_ids:
                        continue
                    sd = saved_designs.get(r_id)
                    if not sd:
                        invalid_or_missing.append(f"Room '{r_id}' ({rm.get('name', 'Room')}) has no saved interior design.")
                    else:
                        v = sd.get("validation", {})
                        if v.get("is_valid") is False or v.get("hard_constraints_passed") is False:
                            invalid_or_missing.append(f"Room '{r_id}' has unresolved hard-constraint or validation failures.")
            if invalid_or_missing:
                raise HTTPException(
                    status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
                    detail={
                        "code": "INCOMPLETE_OR_INVALID_DESIGN_EXPORT_BLOCKED",
                        "message": "Final validated PDF export is blocked because one or more target rooms have missing or invalid designs.",
                        "reasons": invalid_or_missing,
                    },
                )

        # 3. Build Room Data Models
        ergo_rules = self.service.standards_repo.get_all(enforceable_only=True)
        rule_map = {r.id: r for r in ergo_rules}

        room_dtos: List[RoomReportDataDTO] = []
        for floor_dict, room_dict in target_rooms_info:
            room_id = room_dict.get("room_id") or room_dict.get("id")
            saved = saved_designs.get(room_id)
            has_design = saved is not None

            # Base room geometry and exact surface calculations
            poly_coords = room_dict.get("polygon", [])
            doors = room_dict.get("doors", [])
            windows = room_dict.get("windows", [])
            area_sqm = float(room_dict.get("area_sqm") or room_dict.get("area", 0.0))
            ceiling_h = float(room_dict.get("ceiling_height_m") or room_dict.get("ceiling_height") or 2.8)

            # Perimeter calculation from boundary polygon
            perimeter_m = 0.0
            if poly_coords and len(poly_coords) >= 3:
                for i in range(len(poly_coords)):
                    p1 = poly_coords[i]
                    p2 = poly_coords[(i + 1) % len(poly_coords)]
                    dx = float(p2[0]) - float(p1[0])
                    dy = float(p2[1]) - float(p1[1])
                    perimeter_m += (dx * dx + dy * dy) ** 0.5
                if area_sqm <= 0.0:
                    try:
                        from shapely.geometry import Polygon as ShapelyPoly
                        area_sqm = float(ShapelyPoly(poly_coords).area)
                    except Exception:
                        pass
            elif area_sqm > 0:
                perimeter_m = 4.0 * (area_sqm ** 0.5)
            else:
                room_warnings.append(f"Room '{room_id}' boundary geometry is missing or incomplete.")

            # Openings deduction (doors & windows)
            openings_area_sqm = 0.0
            for dr in doors:
                dw = float(dr.get("width") or dr.get("width_m", 0.9))
                dh = float(dr.get("height") or dr.get("height_m", 2.1))
                openings_area_sqm += dw * dh

            for wn in windows:
                ww = float(wn.get("width") or wn.get("width_m", 1.2))
                wh = float(wn.get("height") or wn.get("height_m", 1.2))
                openings_area_sqm += ww * wh

            gross_wall_area_sqm = perimeter_m * ceiling_h
            net_wall_area_sqm = max(0.0, gross_wall_area_sqm - openings_area_sqm)

            furniture_sched: List[RoomScheduleItemDTO] = []
            lighting_sched: List[LightingScheduleItemDTO] = []
            service_sched: List[ServiceScheduleItemDTO] = []
            plumbing_sched: List[PlumbingScheduleItemDTO] = []
            finish_sched: List[FinishScheduleItemDTO] = []
            val_items: List[ValidationReportItemDTO] = []
            opt_summary: Optional[OptimizationSummaryDTO] = None
            room_warnings: List[str] = []

            if has_design:
                # Placed Assets Schedule
                all_assets = (
                    saved.get("furniture", []) +
                    saved.get("cabinetry", []) +
                    saved.get("appliances", []) +
                    saved.get("sanitary_fixtures", []) +
                    saved.get("decorations", [])
                )

                for a in all_assets:
                    dims = a.get("dimensions", {})
                    w = float(dims.get("width", 1.0) if isinstance(dims, dict) else getattr(dims, "width", 1.0))
                    d = float(dims.get("depth", dims.get("length", 1.0)) if isinstance(dims, dict) else getattr(dims, "depth", getattr(dims, "length", 1.0)))
                    h = float(dims.get("height", 1.0) if isinstance(dims, dict) else getattr(dims, "height", 1.0))
                    is_locked = bool(a.get("is_locked", False) or a.get("is_user_locked", False) or a.get("locked", False))

                    pos = a.get("position", {})
                    px = float(pos.get("x", 0.0) if isinstance(pos, dict) else getattr(pos, "x", 0.0))
                    py = float(pos.get("y", 0.0) if isinstance(pos, dict) else getattr(pos, "y", 0.0))
                    rot = float(a.get("rotation_deg", a.get("rotation", 0.0)))

                    furniture_sched.append(
                        RoomScheduleItemDTO(
                            instance_id=a.get("instance_id", "inst_unknown"),
                            asset_name=a.get("asset_name") or a.get("name") or "Unknown Asset",
                            catalog_id=a.get("asset_id") or a.get("catalog_id") or "N/A",
                            category=a.get("category", "furniture"),
                            variant=a.get("variant") or a.get("variant_id"),
                            quantity=1,
                            width_m=round(w, 2),
                            depth_m=round(d, 2),
                            height_m=round(h, 2),
                            material=a.get("material", "Default Catalog Finish"),
                            color=a.get("color", "#94a3b8"),
                            placement_mode=a.get("placement_mode", "floor_standing"),
                            is_mandatory=bool(a.get("is_mandatory", True) or a.get("mandatory", True)),
                            is_locked=is_locked,
                            position_x=round(px, 2),
                            position_y=round(py, 2),
                            rotation_deg=round(rot, 1),
                            associated_wall_id=a.get("associated_wall_id") or a.get("attached_wall_id"),
                        )
                    )

                bath_sched = [f for f in furniture_sched if f.category in ("bathroom", "sanitary") or any(k in f.asset_name.lower() for k in ("bath", "wc", "basin", "shower", "vanity", "toilet"))]
                kit_sched = [f for f in furniture_sched if f.category in ("kitchen", "cabinetry", "appliances") or any(k in f.asset_name.lower() for k in ("cabinet", "sink", "hob", "hood", "refrigerator", "oven", "fridge"))]

                # Check client preferences for room-level exclusions (e.g. bathtub, hot water)
                room_reqs = master_json.get("client_preferences", {}).get("room_requirements", {}).get(room_id, {})
                if not room_reqs:
                    room_reqs = master_json.get("interior_layout", {}).get("room_requirements", {}).get(room_id, {})
                bath_opts = room_reqs.get("bathroom", {})
                if bath_opts.get("bathtub_selected") is False:
                    furniture_sched = [f for f in furniture_sched if "bathtub" not in f.asset_name.lower()]
                    bath_sched = [f for f in bath_sched if "bathtub" not in f.asset_name.lower()]
                if bath_opts.get("hot_water_required") is False:
                    plumbing_sched = [p for p in plumbing_sched if "hot_water" not in p.service_type.lower()]

                # Lighting Schedule
                for lgt in saved.get("lighting", []):
                    pos = lgt.get("position", {})
                    lighting_sched.append(
                        LightingScheduleItemDTO(
                            fixture_id=lgt.get("fixture_id", "lgt_unknown"),
                            fixture_type=lgt.get("fixture_type", "ambient_recessed"),
                            purpose=lgt.get("purpose", "General illumination"),
                            installation_mode=lgt.get("installation_mode", "ceiling_recessed"),
                            position_x=round(float(pos.get("x", 0.0) if isinstance(pos, dict) else getattr(pos, "x", 0.0)), 2),
                            position_y=round(float(pos.get("y", 0.0) if isinstance(pos, dict) else getattr(pos, "y", 0.0)), 2),
                            height_m=round(float(lgt.get("height_from_floor_m", ceiling_h)), 2),
                            control_zone=lgt.get("control_zone"),
                            is_proposed=bool(lgt.get("is_proposed", True)),
                        )
                    )

                # Electrical Points Schedule
                for ep in saved.get("electrical_points", []):
                    pos = ep.get("position", {})
                    service_sched.append(
                        ServiceScheduleItemDTO(
                            point_id=ep.get("point_id", "elec_unknown"),
                            service_type=ep.get("service_type", "general_power_outlet"),
                            purpose=ep.get("purpose", "Convenience power"),
                            associated_asset_name=ep.get("associated_asset_id"),
                            position_x=round(float(pos.get("x", 0.0) if isinstance(pos, dict) else getattr(pos, "x", 0.0)), 2),
                            position_y=round(float(pos.get("y", 0.0) if isinstance(pos, dict) else getattr(pos, "y", 0.0)), 2),
                            height_m=round(float(ep.get("height_from_floor_m", 0.3)), 2),
                            status=ep.get("status", "proposed"),
                            requires_professional_review=True,
                        )
                    )

                # Plumbing Provisions Schedule
                for pl in saved.get("plumbing_requirements", []):
                    plumbing_sched.append(
                        PlumbingScheduleItemDTO(
                            item_id=pl.get("point_id", "plumb_unknown"),
                            fixture_type=pl.get("fixture_type", "sanitary_fixture"),
                            hot_water_required=bool(pl.get("hot_water_required", False)),
                            drainage_type=pl.get("drainage_type", "gravity"),
                            supply_type=pl.get("supply_type", "potable_cold"),
                            status=pl.get("status", "proposed"),
                            requires_professional_review=True,
                        )
                    )

                # Finishes Schedule
                wall_f = saved.get("wall_finish") or "Smooth Emulsion Paint"
                floor_f = saved.get("floor_finish") or "Ceramic Tile"
                ceiling_f = saved.get("ceiling_finish") or "Smooth Plaster Board"

                finish_sched.append(
                    FinishScheduleItemDTO(
                        surface_type="Wall",
                        finish_id="FIN_WALL",
                        finish_name=wall_f,
                        material_category="Paint / Wall Covering",
                        color_or_pattern=saved.get("wall_color", "Neutral"),
                        coverage_area_sqm=round(net_wall_area_sqm, 2),
                    )
                )
                finish_sched.append(
                    FinishScheduleItemDTO(
                        surface_type="Floor",
                        finish_id="FIN_FLOOR",
                        finish_name=floor_f,
                        material_category="Flooring",
                        color_or_pattern="Standard Finish",
                        coverage_area_sqm=round(area_sqm, 1),
                    )
                )
                finish_sched.append(
                    FinishScheduleItemDTO(
                        surface_type="Ceiling",
                        finish_id="FIN_CEIL",
                        finish_name=ceiling_f,
                        material_category="Ceiling Finish",
                        color_or_pattern="White Matte",
                        coverage_area_sqm=round(area_sqm, 1),
                    )
                )

                # Ergonomic Validation Provenance (authentic repository citations)
                val_data = saved.get("validation", {})
                for ev in val_data.get("ergonomic_evaluations", []):
                    r_id = ev.get("rule_id", "RULE_GEN")
                    r_ref = rule_map.get(r_id)
                    val_status = "NOT_EVALUATED" if ev.get("status") == "NOT_EVALUATED" else ("PASS" if ev.get("passed", True) else "VIOLATION")

                    # Distinguish verified published standards from internal heuristics
                    if r_ref and getattr(r_ref, "rule_class", "") == "internal_heuristic":
                        std_source = "Internal Architectural Heuristic (Advisory)"
                        std_edition = None
                        std_section = None
                    elif r_ref and getattr(r_ref, "verification_status", None) and str(r_ref.verification_status).lower() != "verified":
                        std_source = r_ref.source_title or "Architectural Design Recommendation"
                        std_edition = r_ref.source_edition
                        std_section = r_ref.source_section
                    else:
                        std_source = r_ref.source_title if (r_ref and r_ref.source_title) else "General Architectural Standard"
                        std_edition = r_ref.source_edition if r_ref else None
                        std_section = r_ref.source_section if r_ref else None

                    val_items.append(
                        ValidationReportItemDTO(
                            rule_id=r_id,
                            rule_description=r_ref.description if (r_ref and r_ref.description) else ev.get("description", "Ergonomic clearance constraint"),
                            standard_source=std_source,
                            standard_edition=std_edition,
                            standard_section=std_section,
                            status=val_status,
                            severity="error" if (r_ref and r_ref.is_mandatory_compliance) else "warning",
                            required_clearance_m=r_ref.threshold_m if r_ref else None,
                            message=ev.get("message", "Compliant with standard clearance criteria."),
                        )
                    )

                # GA Optimization Summary: only include if generation metadata was actually recorded
                meta = saved.get("generation_metadata", {})
                if meta and ("num_generations" in meta or "fitness_score" in val_data):
                    opt_summary = OptimizationSummaryDTO(
                        algorithm_name="PyGAD Genetic Spatial Optimizer",
                        generations=int(meta["num_generations"]) if "num_generations" in meta else None,
                        population_size=int(meta["population_size"]) if "population_size" in meta else None,
                        seed=int(meta["seed"]) if "seed" in meta else None,
                        fitness_score=round(float(val_data.get("fitness_score", 0.0)), 3),
                        hard_constraints_passed=bool(val_data.get("hard_constraints_passed", True)),
                        overlap_area_sqm=round(float(meta.get("overlap_area_sqm", 0.0)), 4),
                        out_of_bounds_area_sqm=round(float(meta.get("out_of_bounds_area_sqm", 0.0)), 4),
                        door_violations=int(meta.get("door_violations", 0)),
                        window_violations=int(meta.get("window_violations", 0)),
                        ergonomic_score=round(float(meta.get("ergonomic_score", 1.0)), 2),
                        runtime_seconds=float(meta.get("runtime_seconds", 0.0)) if meta.get("runtime_seconds") else None,
                    )
                else:
                    opt_summary = None
            else:
                room_warnings.append(f"No saved interior design layout exists for room '{room_id}'.")

            # Extract 3D viewport capture with strict room and revision validation
            capture_b64 = None
            captures = req.view_captures or req.viewer_3d_captures or {}
            if captures and room_id in captures:
                raw_cap = captures[room_id]
                if isinstance(raw_cap, dict):
                    cap_room = raw_cap.get("room_id")
                    cap_rev = raw_cap.get("design_revision")
                    img_str = raw_cap.get("image_base64") or raw_cap.get("image") or raw_cap.get("data_url")

                    # Verify correct room identity
                    if cap_room and str(cap_room) != str(room_id):
                        img_str = None
                    # Verify correct design revision
                    saved_rev = int(saved.get("design_revision", 0)) if saved else 0
                    if cap_rev is not None and int(cap_rev) != saved_rev:
                        img_str = None
                elif isinstance(raw_cap, str):
                    img_str = raw_cap
                else:
                    img_str = None

                # Verify image is nonblank and decodable
                if img_str and len(img_str.strip()) > 100:
                    capture_b64 = img_str.strip()

            room_dtos.append(
                RoomReportDataDTO(
                    room_id=room_id,
                    room_name=room_dict.get("name", "Unnamed Room"),
                    room_type=str(room_dict.get("room_type", "general")),
                    floor_id=floor_dict.get("floor_id", "floor_0"),
                    floor_name=floor_dict.get("floor_name", "Level 0"),
                    area_sqm=round(area_sqm, 2),
                    ceiling_height_m=round(ceiling_h, 2),
                    perimeter_m=round(perimeter_m, 2),
                    net_wall_area_sqm=round(net_wall_area_sqm, 2),
                    openings_area_sqm=round(openings_area_sqm, 2),
                    polygon=poly_coords,
                    doors=doors,
                    windows=windows,
                    design_revision=int(saved.get("design_revision", 0)) if saved else 0,
                    has_design=has_design,
                    furniture_schedule=furniture_sched,
                    bathroom_schedule=bath_sched,
                    kitchen_schedule=kit_sched,
                    lighting_schedule=lighting_sched,
                    service_schedule=service_sched,
                    plumbing_schedule=plumbing_sched,
                    finish_schedule=finish_sched,
                    validation_items=val_items,
                    optimization_summary=opt_summary,
                    image_capture_base64=capture_b64,
                    warnings=room_warnings,
                )
            )

        # Build Floor DTOs
        floors_dict: Dict[str, FloorReportDataDTO] = {}
        for r in room_dtos:
            if r.floor_id not in floors_dict:
                floors_dict[r.floor_id] = FloorReportDataDTO(floor_id=r.floor_id, floor_name=r.floor_name, rooms=[])
            floors_dict[r.floor_id].rooms.append(r)
        floor_dtos = list(floors_dict.values())

        # General Disclaimers and Limitations
        disclaimers = [
            "This interior layout report is conceptually synthesized based on algorithmic ergonomic principles (Neufert standards) and client preferences.",
            "All electrical socket locations, lighting fixtures, and plumbing provisions are conceptual requirements and DO NOT constitute certified MEP construction installation drawings.",
            "All physical MEP provisions must be independently reviewed, coordinated, and approved by licensed electrical and plumbing contractors prior to rough-in.",
            "Room boundary geometry and window/door openings represent the authoritative structural model from projects.master_json.",
            "Absolute exclusion: This report contains no commercial valuations, monetary assessments, or financial provisions.",
        ]

        # Effective preferences overview with full cascade fallback
        effective_prefs = (
            interior_layout.get("preferences", {})
            or master_json.get("client_preferences", {})
            or master_json.get("interior_preferences", {})
            or {}
        )

        return ReportDataDTO(
            project_id=project.id,
            project_name=getattr(project, "project_name", getattr(project, "name", "Project")),
            scope=req.scope,
            mode=req.mode,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            design_revision=design_revision,
            geometry_revision=geometry_revision,
            preference_revision=preference_revision,
            geometry_fingerprint=current_geo_fp,
            is_stale=is_stale,
            staleness_reasons=staleness_reasons,
            rooms=room_dtos,
            floors=floor_dtos,
            client_preferences=effective_prefs,
            author_name=req.author_name or "ArchAI-Plan ESAI-Engine",
            custom_notes=req.notes,
            general_disclaimers=disclaimers,
            drawing_scale_mode=req.drawing_scale_mode or "auto",
            include_2d_drawings=req.include_2d_drawings,
            include_3d_views=req.include_3d_views,
        )
