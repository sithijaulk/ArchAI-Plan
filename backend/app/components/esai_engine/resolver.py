"""
Preference-to-Catalog Resolver
Deterministically converts Phase 2 effective room preferences into a GA-ready design input package.
Enforces asset variants, bed configurations, exclusions, service mappings, ergonomic constraints,
and deterministic aesthetic evaluation without fabricating coordinates.
"""
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from .catalog import CatalogAsset, FinishAsset, FurnitureCatalogRepository
from .contracts import (
    AestheticEvaluationDTO,
    AssetCategory,
    ClearanceDirection,
    ConstraintPriority,
    Coordinate2D,
    Dimensions3D,
    DoorDTO,
    FixedObstructionDTO,
    PlacementMode,
    ResolvedAssetInstanceDTO,
    ResolvedErgonomicConstraintDTO,
    ResolvedFunctionalRelationshipDTO,
    ResolvedRoomDesignInputDTO,
    ResolvedServiceRequirementDTO,
    RoomType,
    ServiceStatus,
    ServiceType,
    StandardVerificationStatus,
    WindowDTO,
)
from .rules import ErgonomicRule, ErgonomicStandardsRepository
from .room_knowledge import RoomKnowledgeRepository


class PreferenceToCatalogResolver:
    """
    Deterministic resolver bridging client preferences and the evolutionary placement engine.
    """

    def __init__(
        self,
        catalog_repo: Optional[FurnitureCatalogRepository] = None,
        rules_repo: Optional[ErgonomicStandardsRepository] = None,
        knowledge_repo: Optional[RoomKnowledgeRepository] = None,
    ):
        self.catalog_repo = catalog_repo or FurnitureCatalogRepository.get_instance()
        self.rules_repo = rules_repo or ErgonomicStandardsRepository.get_instance()
        self.knowledge_repo = knowledge_repo or RoomKnowledgeRepository.get_instance()

    def _find_asset(self, *candidate_ids: str) -> Optional[CatalogAsset]:
        for cid in candidate_ids:
            if not cid:
                continue
            asset = self.catalog_repo.find_by_id(cid)
            if asset:
                return asset
        return None

    def resolve(
        self,
        project_id: str,
        floor_id: str,
        room_id: str,
        room_name: str,
        room_type_str: str,
        polygon: List[Coordinate2D],
        area_sqm: float,
        ceiling_height_m: float,
        doors: List[DoorDTO],
        windows: List[WindowDTO],
        fixed_obstructions: List[FixedObstructionDTO],
        effective_preferences: Dict[str, Any],
        geometry_fingerprint: str = "",
        geometry_revision: int = 1,
        elevation_m: float = 0.0,
    ) -> ResolvedRoomDesignInputDTO:
        """
        Main entry point for resolving a room's design requirements.
        """
        diagnostics: List[str] = []
        missing_assets: List[str] = []

        # 1. Normalize room type and fetch room profile
        clean_room_type = room_type_str.lower().strip()
        room_profile = self.knowledge_repo.get_profile(clean_room_type)

        # 2. Extract preferences sections
        pref_data = effective_preferences
        if isinstance(effective_preferences, dict):
            if "effective_preferences" in effective_preferences and isinstance(effective_preferences["effective_preferences"], dict):
                pref_data = effective_preferences["effective_preferences"]
            elif "effective" in effective_preferences and isinstance(effective_preferences["effective"], dict):
                pref_data = effective_preferences["effective"]
            elif "preferences" in effective_preferences and isinstance(effective_preferences["preferences"], dict):
                pref_data = effective_preferences["preferences"]

        design_style = pref_data.get("design_style", "modern")
        color_palette = pref_data.get("color_palette", ["neutral_warm"])
        materials = pref_data.get("materials", ["wood_oak", "stainless_steel"])
        lighting_prefs = pref_data.get("lighting", {})
        electrical_prefs = pref_data.get("electrical", {})
        plumbing_prefs = pref_data.get("plumbing", {})
        custom_rules = pref_data.get("custom_rules", {})
        room_specific = pref_data.get("room_specific", {})

        # 3. Compile Exclusions
        excluded_categories: Set[str] = set()
        for exc in pref_data.get("excluded_furniture", []):
            if isinstance(exc, str):
                excluded_categories.add(exc.lower().strip())

        # Check explicit plumbing exclusions (e.g. bathtub)
        if plumbing_prefs.get("bathtub_preferred") is False:
            excluded_categories.add("bathtub")

        # 4. Resolve Asset Instances
        resolved_instances: List[ResolvedAssetInstanceDTO] = []
        service_requirements: List[ResolvedServiceRequirementDTO] = []
        instance_counter = 1

        # Track locked items
        locked_placements = pref_data.get("locked_placements", [])
        locked_map: Dict[str, Dict[str, Any]] = {}
        for lp in locked_placements:
            key = lp.get("item_id") or lp.get("asset_id") or lp.get("category")
            if key:
                locked_map[key] = lp

        # Helper to instantiate a catalog asset
        def add_instance(
            asset: CatalogAsset,
            priority: str = "mandatory",
            custom_dims: Optional[Dimensions3D] = None,
            wall_affinity: Optional[str] = None,
            preferred_wall: Optional[str] = None,
            instance_key: Optional[str] = None,
        ) -> Optional[ResolvedAssetInstanceDTO]:
            nonlocal instance_counter

            # Guard against exclusions
            if asset.category.value.lower() in excluded_categories or asset.subtype.lower() in excluded_categories:
                diagnostics.append(f"Excluded item '{asset.name}' was skipped per user exclusion preferences.")
                return None

            inst_id = f"inst_{clean_room_type}_{asset.category.value}_{instance_counter}"
            instance_counter += 1

            # Check locked coordinates
            locked_info = locked_map.get(instance_key or asset.id) or locked_map.get(asset.category.value)
            locked_coords = None
            locked_rot = None
            if locked_info:
                if "x" in locked_info and "y" in locked_info:
                    locked_coords = Coordinate2D(x=float(locked_info["x"]), y=float(locked_info["y"]))
                if "rotation" in locked_info:
                    locked_rot = float(locked_info["rotation"])
                priority = "user_locked"

            # Determine wall affinity
            affinity = wall_affinity or asset.placement_preferences.get("wall_affinity")

            # Determine service connections
            associated_services: List[str] = []
            for svc in asset.required_services:
                svc_id = f"svc_{inst_id}_{svc.get('service_type', 'point')}"
                associated_services.append(svc_id)
                service_requirements.append(
                    ResolvedServiceRequirementDTO(
                        service_id=svc_id,
                        service_type=ServiceType(svc.get("service_type", ServiceType.POWER_GENERAL.value)),
                        associated_instance_id=inst_id,
                        status=ServiceStatus.PROPOSED_NEW,
                        description=f"Proposed connection for {asset.name}: {svc.get('description', '')}",
                        requires_professional_verification=True,
                        connection_spec=svc,
                    )
                )

            instance = ResolvedAssetInstanceDTO(
                instance_id=inst_id,
                asset_id=asset.id,
                asset_name=asset.name,
                category=asset.category.value,
                subtype=asset.subtype,
                dimensions=custom_dims or asset.dimensions,
                physical_footprint_type=asset.physical_footprint_type,
                placement_mode=asset.placement_mode,
                priority=priority,
                supported_rotations=asset.supported_rotations,
                wall_affinity=affinity,
                preferred_wall=preferred_wall,
                locked_coordinates=locked_coords,
                locked_rotation=locked_rot,
                style_tag=design_style,
                material_variant=materials[0] if materials else None,
                clearance_rule_id=asset.default_clearance_rule_id,
                associated_service_ids=associated_services,
                rendering_model_id=asset.rendering_model_id,
                source_attribution="preference_derived" if not locked_coords else "user_locked",
            )
            resolved_instances.append(instance)
            return instance

        # ── 4A. Process Room-Specific Preferences ──
        # Bedroom: Bed type, quantity, wardrobe, bedside tables, desk
        if any(b in clean_room_type for b in ("bed", "master_bed", "guest")):
            bed_type = room_specific.get("bed_type", "single")
            bed_qty = int(room_specific.get("bed_quantity") or room_specific.get("bed_count") or 1)
            if bed_qty <= 0:
                diagnostics.append(f"Invalid bed quantity {bed_qty}; defaulted to 1.")
                bed_qty = 1

            # Match Bed Asset
            matched_bed_asset = self._resolve_bed_asset(bed_type)
            if matched_bed_asset:
                # IMPORTANT: Support multiple distinct bed instances (e.g. 2 single beds remain 2 instances)
                for _ in range(bed_qty):
                    add_instance(matched_bed_asset, priority="mandatory")
            else:
                missing_assets.append(f"Bed asset matching type '{bed_type}'")

            # Bedside Tables (typically 2 for double/queen/king, 1 or 2 for single)
            nightstand_asset = self._find_asset("NIGHTSTAND_01")
            if nightstand_asset and "bedside_table" not in excluded_categories:
                nightstand_qty = 2 if bed_type in ("double", "queen", "king") and bed_qty == 1 else bed_qty
                for _ in range(nightstand_qty):
                    add_instance(nightstand_asset, priority="optional")

            # Wardrobe
            wardrobe_type = room_specific.get("wardrobe_type", "sliding")
            wardrobe_asset = self._resolve_wardrobe_asset(wardrobe_type)
            if wardrobe_asset and "wardrobe" not in excluded_categories:
                add_instance(wardrobe_asset, priority="mandatory")

            # Study Desk if included
            if room_specific.get("desk_included") is True and "desk" not in excluded_categories:
                desk_asset = self._find_asset("DESK_EXEC_01", "DESK_STANDING_01")
                if desk_asset:
                    add_instance(desk_asset, priority="optional")

        # Bathroom: Shower, Basin/Vanity, Commode, Bathtub
        elif any(b in clean_room_type for b in ("bath", "toilet", "powder")):
            commode_asset = self._find_asset("BATH_COMMODE_WALLHUNG_01", "BATH_COMMODE_01")
            if commode_asset and "commode" not in excluded_categories:
                add_instance(commode_asset, priority="mandatory")

            # Vanity / Washbasin
            vanity_type = plumbing_prefs.get("vanity_basin_type", room_specific.get("vanity_type", "single"))
            vanity_id = "BATH_DOUBLE_VANITY_01" if vanity_type == "double" else "BATH_BASIN_VANITY_01"
            vanity_asset = self._find_asset(vanity_id, "BATH_BASIN_VANITY_01")
            if vanity_asset and "vanity" not in excluded_categories and "washbasin" not in excluded_categories:
                add_instance(vanity_asset, priority="mandatory")

            # Shower
            shower_asset = self._find_asset("BATH_WALKIN_SHOWER_01", "BATH_SHOWER_ENCLOSURE_01")
            if shower_asset and "shower" not in excluded_categories:
                add_instance(shower_asset, priority="mandatory")

            # Bathtub: Only if explicitly preferred and not excluded
            if plumbing_prefs.get("bathtub_preferred") is True and "bathtub" not in excluded_categories:
                bathtub_type = plumbing_prefs.get("bathtub_type", "freestanding")
                tub_id = "BATH_BATHTUB_FREESTANDING_01" if bathtub_type == "freestanding" else "BATH_BATHTUB_BUILTIN_01"
                tub_asset = self._find_asset(tub_id, "BATH_BATHTUB_FREESTANDING_01")
                if tub_asset:
                    add_instance(tub_asset, priority="mandatory")

        # Kitchen: Cabinetry, Sink, Cooktop, Refrigerator, Range Hood, Dishwasher
        elif any(k in clean_room_type for k in ("kitchen", "pantry")):
            sink_asset = self._find_asset("KITCHEN_SINK_UNIT_01", "KITCHEN_DOUBLE_SINK_01")
            if sink_asset and "sink" not in excluded_categories:
                add_instance(sink_asset, priority="mandatory")

            cooktop_asset = self._find_asset("COOKTOP_INDUCTION_01")
            if cooktop_asset and "cooktop" not in excluded_categories:
                add_instance(cooktop_asset, priority="mandatory")

            hood_asset = self._find_asset("RANGE_HOOD_CHIMNEY_01")
            if hood_asset and "range_hood" not in excluded_categories:
                add_instance(hood_asset, priority="mandatory")

            fridge_asset = self._find_asset("REFRIGERATOR_FRENCH_DOOR_01")
            if fridge_asset and "refrigerator" not in excluded_categories:
                add_instance(fridge_asset, priority="mandatory")

            # Dishwasher if preferred
            if room_specific.get("dishwasher_included") or electrical_prefs.get("dishwasher_provision"):
                dw_asset = self._find_asset("DISHWASHER_BUILTIN_01")
                if dw_asset and "dishwasher" not in excluded_categories:
                    add_instance(dw_asset, priority="optional")

        # Living Room: Sofa, Coffee Table, TV Unit
        elif any(l in clean_room_type for l in ("living", "lounge", "tv")):
            seating_type = room_specific.get("seating_type", "three_seat")
            sofa_id = "SOFA_SECTIONAL_L_01" if seating_type in ("sectional", "l_shaped") else "SOFA_3SEATER_01"
            sofa_asset = self._find_asset(sofa_id, "SOFA_3SEATER_01", "SOFA_2SEATER_01")
            if sofa_asset and "sofa" not in excluded_categories:
                add_instance(sofa_asset, priority="mandatory")

            coffee_table_asset = self._find_asset("COFFEE_TABLE_01")
            if coffee_table_asset and "coffee_table" not in excluded_categories:
                add_instance(coffee_table_asset, priority="optional")

            # TV Unit
            tv_wall = room_specific.get("tv_wall") or custom_rules.get("tv_wall")
            tv_asset = self._find_asset("TV_CONSOLE_01", "MEDIA_WALL_UNIT_01")
            if tv_asset and "tv_unit" not in excluded_categories and "tv_console" not in excluded_categories:
                add_instance(tv_asset, priority="mandatory", preferred_wall=tv_wall, wall_affinity="back_against_wall")

        # Dining Room: Table & Chairs
        elif "dining" in clean_room_type:
            table_asset = self._find_asset("DINING_TABLE_6S_01", "DINING_TABLE_ROUND_4S_01", "DINING_TABLE_8S_01")
            if table_asset and "dining_table" not in excluded_categories:
                add_instance(table_asset, priority="mandatory")

            chair_asset = self._find_asset("DINING_CHAIR_01")
            if chair_asset and "dining_chair" not in excluded_categories:
                for _ in range(6):
                    add_instance(chair_asset, priority="mandatory")

        # Study / Office: Desk & Ergonomic Chair
        elif any(o in clean_room_type for o in ("study", "office", "work")):
            desk_asset = self._find_asset("DESK_STANDING_01", "DESK_EXEC_01")
            if desk_asset and "desk" not in excluded_categories:
                add_instance(desk_asset, priority="mandatory")

            chair_asset = self._find_asset("OFFICE_CHAIR_01")
            if chair_asset and "office_chair" not in excluded_categories:
                add_instance(chair_asset, priority="mandatory")

        # Laundry / Utility: Washer, Dryer, Sink
        elif any(u in clean_room_type for u in ("laundry", "utility")):
            washer_asset = self._find_asset("WASHING_MACHINE_01")
            if washer_asset and "washing_machine" not in excluded_categories:
                add_instance(washer_asset, priority="mandatory")

        # ── 4B. Process Explicit Mandatory / Optional Items ──
        for item in pref_data.get("mandatory_furniture", []):
            self._process_preference_item(
                item,
                priority="mandatory",
                add_instance_fn=add_instance,
                missing_assets=missing_assets,
            )

        for item in pref_data.get("optional_furniture", []):
            self._process_preference_item(
                item,
                priority="optional",
                add_instance_fn=add_instance,
                missing_assets=missing_assets,
            )

        # ── 5. Resolve Service Requirements (Electrical, Plumbing, Mechanical) ──
        # Bedside Sockets
        if electrical_prefs.get("charging_station") or electrical_prefs.get("bedside_sockets"):
            service_requirements.append(
                ResolvedServiceRequirementDTO(
                    service_id=f"svc_{clean_room_type}_bedside_sockets",
                    service_type=ServiceType.USB_CHARGING,
                    status=ServiceStatus.PROPOSED_NEW,
                    description="Bedside dual USB-C / AC charging points (provisional placement with sleeping zone)",
                    requires_professional_verification=True,
                )
            )

        # Ceiling Fan
        if electrical_prefs.get("ceiling_fan") is True:
            fan_asset = self._find_asset("CEILING_FAN_01")
            if fan_asset and "ceiling_fan" not in excluded_categories:
                add_instance(fan_asset, priority="mandatory")
            service_requirements.append(
                ResolvedServiceRequirementDTO(
                    service_id=f"svc_{clean_room_type}_fan_point",
                    service_type=ServiceType.FAN_POINT,
                    status=ServiceStatus.PROPOSED_NEW,
                    description="Ceiling fan junction point centered in room ceiling zone",
                    requires_professional_verification=True,
                )
            )

        # Hot Water Provision
        if plumbing_prefs.get("hot_water") is True:
            service_requirements.append(
                ResolvedServiceRequirementDTO(
                    service_id=f"svc_{clean_room_type}_hot_water",
                    service_type=ServiceType.WATER_HOT,
                    status=ServiceStatus.PROPOSED_NEW,
                    description=f"Hot water supply line requirement ({plumbing_prefs.get('water_heater_type', 'central_solar')} system)",
                    requires_professional_verification=True,
                    connection_spec={"heater_type": plumbing_prefs.get("water_heater_type", "central_solar")},
                )
            )

        # TV power/data points
        if electrical_prefs.get("tv_points") is True:
            service_requirements.append(
                ResolvedServiceRequirementDTO(
                    service_id=f"svc_{clean_room_type}_tv_media",
                    service_type=ServiceType.TV_POWER,
                    status=ServiceStatus.PROPOSED_NEW,
                    description="Wall media electrical socket and RJ45/coaxial data outlet behind TV display",
                    requires_professional_verification=True,
                )
            )

        # ── 6. Ergonomic Constraints (Neufert & Anthropometric Clearance Rules) ──
        present_categories = {inst.category for inst in resolved_instances}
        ergonomic_constraints: List[ResolvedErgonomicConstraintDTO] = []

        all_rules = self.rules_repo.get_all(enforceable_only=False)
        for rule in all_rules:
            # Check applicability
            if any(cat in rule.applicable_categories for cat in present_categories) or "all" in rule.applicable_categories:
                is_mandatory = rule.is_mandatory_compliance
                ergonomic_constraints.append(
                    ResolvedErgonomicConstraintDTO(
                        rule_id=rule.id,
                        applicable_categories=rule.applicable_categories,
                        clearance_direction=rule.clearance_direction,
                        threshold_m=rule.threshold_m,
                        priority=rule.priority,
                        verification_status=rule.verification_status,
                        source_title=rule.source_title,
                        source_edition=rule.source_edition,
                        source_section=rule.source_section,
                        is_mandatory=is_mandatory,
                        description=f"Neufert clearance constraint ({rule.clearance_direction.value}): {rule.threshold_m}m",
                    )
                )

        # ── 7. Functional Relationships ──
        functional_relationships: List[ResolvedFunctionalRelationshipDTO] = []
        for rel in self.knowledge_repo.get_functional_relations():
            if rel.primary_category in present_categories and rel.related_category in present_categories:
                functional_relationships.append(
                    ResolvedFunctionalRelationshipDTO(
                        relation_id=f"rel_{rel.primary_category}_{rel.related_category}",
                        from_category=rel.primary_category,
                        to_category=rel.related_category,
                        relation_type=rel.relation_type,
                        min_distance_m=rel.min_distance_m,
                        max_distance_m=rel.max_distance_m,
                        optimal_distance_m=rel.optimal_distance_m,
                        is_hard_constraint=rel.is_hard_constraint,
                        notes=rel.notes,
                    )
                )

        # ── 8. Aesthetic Evaluation Profile ──
        aesthetic_eval = self.knowledge_repo.evaluate_aesthetic_compatibility(
            style_name=design_style,
            palette=color_palette,
            materials=materials,
        )

        # ── 9. Surface Finishes ──
        finishes_map: Dict[str, Any] = {
            "wall_finish": pref_data.get("wall_finish", "PAINT_MATTE_WHITE_01"),
            "floor_finish": pref_data.get("floor_finish", "FLOOR_OAK_PARQUET_01"),
            "ceiling_finish": pref_data.get("ceiling_finish", "CEILING_GYPSUM_COVE_01"),
        }

        # ── 10. Diagnostics & Feasibility Validation ──
        feasibility_status = "feasible"
        total_footprint = sum(inst.dimensions.width * inst.dimensions.depth for inst in resolved_instances)
        density_ratio = total_footprint / area_sqm if area_sqm > 0 else 0.0

        if room_profile and area_sqm < room_profile.default_min_area_sqm:
            diagnostics.append(
                f"Room area ({area_sqm:.1f}m²) is below standard recommended minimum ({room_profile.default_min_area_sqm:.1f}m²) for {room_profile.display_name}."
            )
            feasibility_status = "conditional_warning"

        if density_ratio > 0.50:
            diagnostics.append(
                f"Furniture footprint density ({density_ratio * 100:.1f}%) exceeds 50% spatial threshold. GA clearance optimization will operate under strict bounds."
            )
            feasibility_status = "conditional_warning"

        if density_ratio > 0.70:
            diagnostics.append("Critical space congestion: furniture footprint exceeds 70% of floor area.")
            feasibility_status = "infeasible"

        if missing_assets:
            diagnostics.append(f"Unresolved catalog items: {', '.join(missing_assets)}")
            if feasibility_status == "feasible":
                feasibility_status = "conditional_warning"

        # Construct and return GA design package
        return ResolvedRoomDesignInputDTO(
            project_id=project_id,
            floor_id=floor_id,
            room_id=room_id,
            room_name=room_name,
            room_type=clean_room_type,
            polygon=polygon,
            area_sqm=area_sqm,
            ceiling_height_m=ceiling_height_m,
            elevation_m=elevation_m,
            geometry_fingerprint=geometry_fingerprint,
            geometry_revision=geometry_revision,
            doors=doors,
            windows=windows,
            fixed_obstructions=fixed_obstructions,
            asset_instances=resolved_instances,
            service_requirements=service_requirements,
            ergonomic_constraints=ergonomic_constraints,
            functional_relationships=functional_relationships,
            excluded_categories=list(excluded_categories),
            finishes=finishes_map,
            aesthetic_profile=aesthetic_eval,
            diagnostics=diagnostics,
            missing_assets=missing_assets,
            feasibility_status=feasibility_status,
            provenance_metadata={
                "standards_source": "Neufert Architects' Data 4th Ed. / ISO 7250 Anthropometrics",
                "resolver_version": "1.0-phase3",
                "deterministic_scoring": True,
            },
        )

    # ── Internal Resolution Helpers ──

    def _resolve_bed_asset(self, bed_type: str) -> Optional[CatalogAsset]:
        bed_type_clean = bed_type.lower().strip()
        mapping = {
            "single": "BED_SINGLE_01",
            "double": "BED_DOUBLE_01",
            "queen": "BED_QUEEN_01",
            "king": "BED_KING_01",
            "twin": "BED_TWIN_PAIR_01",
            "bunk": "BED_BUNK_01",
            "triple_sleeper": "BED_TRIPLE_SLEEPER_01",
            "storage": "BED_STORAGE_01",
            "platform": "BED_QUEEN_01",
        }
        target_id = mapping.get(bed_type_clean, "BED_SINGLE_01")
        return self._find_asset(target_id, "BED_SINGLE_01")

    def _resolve_wardrobe_asset(self, wardrobe_type: str) -> Optional[CatalogAsset]:
        w_clean = wardrobe_type.lower().strip()
        if "walk" in w_clean:
            return self._find_asset("WARDROBE_WALKIN_UNIT_01", "WARDROBE_4DOOR_01")
        if "hinged" in w_clean or "4door" in w_clean:
            return self._find_asset("WARDROBE_4DOOR_01", "WARDROBE_3DOOR_01")
        return self._find_asset("WARDROBE_SLIDING_01", "WARDROBE_3DOOR_01")

    def _process_preference_item(
        self,
        item: Any,
        priority: str,
        add_instance_fn: Any,
        missing_assets: List[str],
    ) -> None:
        if isinstance(item, str):
            item_id = item
            custom_dims = None
            quantity = 1
        elif isinstance(item, dict):
            item_id = item.get("id") or item.get("asset_id") or item.get("category")
            quantity = int(item.get("quantity", 1))
            dims_dict = item.get("dimensions") or item.get("custom_dimensions")
            custom_dims = Dimensions3D(**dims_dict) if dims_dict else None
        else:
            return

        if not item_id:
            return

        # Attempt lookup by ID
        asset = self.catalog_repo.find_by_id(item_id)
        if not asset:
            # Fallback by category
            assets = self.catalog_repo.get_by_category(item_id)
            if assets:
                asset = assets[0]

        if asset:
            for _ in range(max(1, quantity)):
                add_instance_fn(asset, priority=priority, custom_dims=custom_dims)
        else:
            missing_assets.append(str(item_id))
