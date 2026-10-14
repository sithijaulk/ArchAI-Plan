"""
Space Allocation Interface and Providers.
Stage 1: RuleBasedSpaceAllocationProvider.
Stage 2 (future): XGBoostSpaceAllocationProvider.
Determines target room sizes, floor assignment, and checks feasibility.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from ..schemas import ClientRequirementsInput, FloorPreference


# Standard Sri Lankan Residential Baseline Sizing Heuristics (in square meters)
DEFAULT_BASELINE_ROOM_SIZES = {
    "living_room": 22.0,
    "family_living_area": 16.0,
    "dining_area": 14.0,
    "kitchen": 12.0,
    "pantry": 8.0,
    "master_bedroom": 16.0,
    "bedroom": 12.0,
    "attached_bathroom": 4.5,
    "common_bathroom": 4.0,
    "bathroom": 4.0,
    "study_office": 10.0,
    "utility_room": 6.0,
    "store_room": 4.0,
    "laundry": 4.0,
    "staircase": 7.0,  # Reserved structural zone for multi-storey
    "garage_parking": 18.0,
    "balcony": 6.0,
    "other": 10.0,
}


class SpaceAllocationProvider(ABC):
    """
    Abstract interface for room spatial allocation.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    @abstractmethod
    def model_version(self) -> Optional[str]:
        pass

    @abstractmethod
    def allocate_space(
        self,
        buildable_area: float,
        requirements: ClientRequirementsInput
    ) -> Dict[str, Any]:
        """
        Calculates per-floor spatial allocations and room targets.
        """
        pass


class RuleBasedSpaceAllocationProvider(SpaceAllocationProvider):
    """
    Stage-1 deterministic baseline spatial allocator.
    Consumes buildable footprint area, storey count, requested room programme,
    and client floor preferences.
    Distributes spaces across storeys while verifying mathematical feasibility.
    """

    @property
    def provider_name(self) -> str:
        return "rule_based_baseline"

    @property
    def model_version(self) -> Optional[str]:
        return None  # Stage 1: No trained model

    def allocate_space(
        self,
        buildable_area: float,
        requirements: ClientRequirementsInput
    ) -> Dict[str, Any]:
        storey_count = max(1, requirements.storey_count)
        
        # Max footprint capacity with circulation allowance (~85% usable floor area)
        usable_floor_area = buildable_area * 0.85
        total_building_capacity = usable_floor_area * storey_count

        allocated_rooms = []
        total_demanded_area = 0.0
        mandatory_demanded_area = 0.0

        for req in requirements.rooms:
            qty = req.quantity
            base_size = DEFAULT_BASELINE_ROOM_SIZES.get(req.type, 10.0)
            target_size = req.preferred_min_area if (req.preferred_min_area and req.preferred_min_area > 0) else base_size

            for i in range(qty):
                room_entry = {
                    "req_id": f"{req.id}_{i+1}" if qty > 1 else req.id,
                    "type": req.type,
                    "name": req.custom_name or f"{req.type.replace('_', ' ').title()}" + (f" {i+1}" if qty > 1 else ""),
                    "target_area": target_size,
                    "required": req.required,
                    "priority": req.priority.value if hasattr(req.priority, "value") else str(req.priority),
                    "floor_preference": req.floor_preference.value if hasattr(req.floor_preference, "value") else str(req.floor_preference),
                    "assigned_floor_index": 0
                }
                allocated_rooms.append(room_entry)
                total_demanded_area += target_size
                if req.required:
                    mandatory_demanded_area += target_size

        # Infeasibility Check
        if mandatory_demanded_area > total_building_capacity:
            return {
                "feasible": False,
                "infeasibility_reason": "insufficient_buildable_area",
                "details": f"Mandatory room area ({mandatory_demanded_area:.1f} m²) exceeds total available building capacity ({total_building_capacity:.1f} m² across {storey_count} floors).",
                "total_demanded_area": round(total_demanded_area, 2),
                "total_capacity": round(total_building_capacity, 2),
                "floors": []
            }

        # Multi-storey Staircase Reservation
        if storey_count > 1:
            stair_target = DEFAULT_BASELINE_ROOM_SIZES["staircase"]
            # Inject staircase for each floor
            for fl in range(storey_count):
                allocated_rooms.append({
                    "req_id": f"STAIR_F{fl}",
                    "type": "staircase",
                    "name": "Staircase",
                    "target_area": stair_target,
                    "required": True,
                    "priority": "high",
                    "floor_preference": str(fl),
                    "assigned_floor_index": fl,
                    "is_stair": True
                })

        # Floor Assignment Strategy:
        # 1. Ground floor priority: living, kitchen, dining, parking, garage, laundry
        # 2. Upper floor priority: bedrooms, study, balcony, family living
        # 3. Honor explicit user floor preferences first
        floor_names = ["Ground Floor", "First Floor", "Second Floor", "Third Floor"]
        floor_allocations: List[Dict[str, Any]] = [
            {
                "floor_index": idx,
                "name": floor_names[idx] if idx < len(floor_names) else f"Floor {idx}",
                "available_area": round(buildable_area, 2),
                "allocated_area": 0.0,
                "rooms": []
            }
            for idx in range(storey_count)
        ]

        ground_preferred_types = {"living_room", "kitchen", "pantry", "dining_area", "garage_parking", "utility_room"}
        upper_preferred_types = {"master_bedroom", "bedroom", "study_office", "balcony", "family_living_area"}

        for room in allocated_rooms:
            if room.get("is_stair"):
                fl_idx = room["assigned_floor_index"]
                floor_allocations[fl_idx]["rooms"].append(room)
                floor_allocations[fl_idx]["allocated_area"] += room["target_area"]
                continue

            pref = room["floor_preference"]
            assigned_fl = 0

            if pref == "ground":
                assigned_fl = 0
            elif pref == "first" and storey_count > 1:
                assigned_fl = 1
            elif pref == "second" and storey_count > 2:
                assigned_fl = 2
            else:
                # Heuristic allocation
                if room["type"] in ground_preferred_types or storey_count == 1:
                    # If ground floor is already over capacity, overflow to floor 1
                    if storey_count > 1 and floor_allocations[0]["allocated_area"] > usable_floor_area:
                        assigned_fl = 1
                    else:
                        assigned_fl = 0
                elif room["type"] in upper_preferred_types and storey_count > 1:
                    # Place on floor 1 first, then floor 2 if 3 storeys
                    if floor_allocations[1]["allocated_area"] + room["target_area"] <= usable_floor_area or storey_count == 2:
                        assigned_fl = 1
                    elif storey_count > 2:
                        assigned_fl = 2
                    else:
                        assigned_fl = 0
                else:
                    # Balance load across lowest allocated floor
                    assigned_fl = min(range(storey_count), key=lambda i: floor_allocations[i]["allocated_area"])

            room["assigned_floor_index"] = assigned_fl
            floor_allocations[assigned_fl]["rooms"].append(room)
            floor_allocations[assigned_fl]["allocated_area"] += room["target_area"]

        # Scale target areas proportionally if allocated area slightly exceeds usable space
        for fl in floor_allocations:
            fl["allocated_area"] = round(fl["allocated_area"], 2)
            if fl["allocated_area"] > usable_floor_area and usable_floor_area > 0:
                scale_factor = usable_floor_area / fl["allocated_area"]
                for r in fl["rooms"]:
                    if not r.get("is_stair"):
                        r["target_area"] = round(r["target_area"] * scale_factor, 2)
                fl["allocated_area"] = round(sum(r["target_area"] for r in fl["rooms"]), 2)

        return {
            "feasible": True,
            "provider": self.provider_name,
            "model_version": self.model_version,
            "total_demanded_area": round(total_demanded_area, 2),
            "total_capacity": round(total_building_capacity, 2),
            "floors": floor_allocations
        }
