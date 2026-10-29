"""
Space Allocation Interface and Providers.
Stage 1: RuleBasedSpaceAllocationProvider.
Loads baseline room target sizes from gab_baseline_room_program.json research configuration.
Preserves client preferred minimum areas as hard constraints.
Never silently shrinks mandatory rooms below required minimum targets.
"""
from abc import ABC, abstractmethod
import json
import os
from typing import Any, Dict, List, Optional
from ..schemas import ClientRequirementsInput, RoomPriority

_BASELINE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "gab_baseline_room_program.json")


def load_baseline_room_sizes() -> Dict[str, float]:
    """Loads research baseline sizing heuristics from JSON configuration."""
    defaults = {
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
        "staircase": 7.5,
        "garage_parking": 18.0,
        "balcony": 6.0,
        "other": 10.0,
    }
    if os.path.exists(_BASELINE_FILE):
        try:
            with open(_BASELINE_FILE, "r", encoding="utf-8") as f:
                items = json.load(f)
                for item in items:
                    defaults[item["room_type"]] = float(item["recommended_area_sqm"])
        except Exception:
            pass
    return defaults


class SpaceAllocationProvider(ABC):
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
        pass


class RuleBasedSpaceAllocationProvider(SpaceAllocationProvider):
    """
    Stage-1 deterministic baseline spatial allocator.
    Consumes buildable footprint area, storey count (1-4), requested room programme,
    amenities requirements, and floor preferences.
    Guarantees:
      - Mandatory room minimum target areas are NEVER scaled down.
      - Staircase / vertical circulation core is reserved upfront in capacity check for multi-storey plans.
      - Floor overflow check accounts for the room being placed.
      - Hard floor conflicts or capacity overloads return infeasible rather than silently violating constraints.
    """

    @property
    def provider_name(self) -> str:
        return "rule_based_baseline"

    @property
    def model_version(self) -> Optional[str]:
        return None

    def allocate_space(
        self,
        buildable_area: float,
        requirements: ClientRequirementsInput
    ) -> Dict[str, Any]:
        storey_count = max(1, min(4, requirements.storey_count))
        baseline_sizes = load_baseline_room_sizes()

        # Usable footprint floor capacity (~85% usable floor area accounting for circulation & walls)
        usable_floor_area = buildable_area * 0.85
        total_building_capacity = usable_floor_area * storey_count

        stair_size = baseline_sizes.get("staircase", 7.5)
        stair_reservation_per_floor = stair_size if storey_count > 1 else 0.0
        net_usable_per_floor = max(0.0, usable_floor_area - stair_reservation_per_floor)

        allocated_rooms: List[Dict[str, Any]] = []
        total_demanded_area = 0.0
        mandatory_demanded_area = 0.0

        # Step A: Translate explicit room programme from client requirements
        req_room_types = set()
        for req in requirements.rooms:
            qty = req.quantity
            base_size = baseline_sizes.get(req.type, 10.0)
            target_size = req.preferred_min_area if (req.preferred_min_area and req.preferred_min_area > 0) else base_size
            req_room_types.add(req.type)

            for i in range(qty):
                room_entry = {
                    "req_id": f"{req.id}_{i+1}" if qty > 1 else req.id,
                    "type": req.type,
                    "name": req.custom_name or f"{req.type.replace('_', ' ').title()}" + (f" {i+1}" if qty > 1 else ""),
                    "target_area": round(target_size, 2),
                    "required": req.required,
                    "priority": req.priority.value if hasattr(req.priority, "value") else str(req.priority),
                    "floor_preference": str(req.floor_preference),
                    "floor_assignment_type": req.floor_assignment_type.value if hasattr(req.floor_assignment_type, "value") else str(req.floor_assignment_type),
                    "minimum_width_m": req.minimum_width_m,
                    "preferred_width_m": req.preferred_width_m,
                    "preferred_length_m": req.preferred_length_m,
                    "window_orientation_preference": req.window_orientation_preference,
                    "assigned_floor_index": 0,
                    "is_stair": False
                }
                allocated_rooms.append(room_entry)
                total_demanded_area += target_size
                if req.required:
                    mandatory_demanded_area += target_size

        # Step B: Connect convenience requirement toggles to room programme if not already explicitly in room list
        # 1. Parking capacity
        if (requirements.parking_capacity or 0) > 0 and "garage_parking" not in req_room_types:
            garage_size = baseline_sizes.get("garage_parking", 18.0) * requirements.parking_capacity
            allocated_rooms.append({
                "req_id": "REQ_GARAGE_AUTO",
                "type": "garage_parking",
                "name": f"Parking Garage ({requirements.parking_capacity} bay)",
                "target_area": round(garage_size, 2),
                "required": True,
                "priority": "high",
                "floor_preference": "0",  # Ground floor mandatory
                "assigned_floor_index": 0,
                "is_stair": False
            })
            total_demanded_area += garage_size
            mandatory_demanded_area += garage_size

        # 2. Attached bathroom requirement
        if (requirements.attached_bathroom_count or 0) > 0 and "attached_bathroom" not in req_room_types:
            for b_idx in range(requirements.attached_bathroom_count):
                b_size = baseline_sizes.get("attached_bathroom", 4.5)
                allocated_rooms.append({
                    "req_id": f"REQ_ATT_BATH_{b_idx+1}",
                    "type": "attached_bathroom",
                    "name": f"Attached Bathroom {b_idx+1}",
                    "target_area": b_size,
                    "required": True,
                    "priority": "high",
                    "floor_preference": "auto",
                    "assigned_floor_index": 0,
                    "is_stair": False
                })
                total_demanded_area += b_size
                mandatory_demanded_area += b_size

        # 3. Study / Home Office convenience requirement
        if requirements.study_office_requirement and "study_office" not in req_room_types:
            s_size = baseline_sizes.get("study_office", 10.0)
            allocated_rooms.append({
                "req_id": "REQ_STUDY_AUTO",
                "type": "study_office",
                "name": "Study / Home Office",
                "target_area": s_size,
                "required": True,
                "priority": "medium",
                "floor_preference": "auto",
                "assigned_floor_index": 0,
                "is_stair": False
            })
            total_demanded_area += s_size
            mandatory_demanded_area += s_size

        # 4. Storage requirement
        if requirements.storage_requirement and "store_room" not in req_room_types:
            st_size = baseline_sizes.get("store_room", 4.0)
            allocated_rooms.append({
                "req_id": "REQ_STORE_AUTO",
                "type": "store_room",
                "name": "Store Room",
                "target_area": st_size,
                "required": False,
                "priority": "low",
                "floor_preference": "auto",
                "assigned_floor_index": 0,
                "is_stair": False
            })
            total_demanded_area += st_size

        # 5. Laundry / utility requirement
        if requirements.laundry_utility_requirement and "laundry" not in req_room_types and "utility_room" not in req_room_types:
            l_size = baseline_sizes.get("laundry", 4.0)
            allocated_rooms.append({
                "req_id": "REQ_LAUNDRY_AUTO",
                "type": "laundry",
                "name": "Laundry / Utility",
                "target_area": l_size,
                "required": False,
                "priority": "low",
                "floor_preference": "auto",
                "assigned_floor_index": 0,
                "is_stair": False
            })
            total_demanded_area += l_size

        # 6. Balcony requirement
        if requirements.balcony_requirement and storey_count > 1 and "balcony" not in req_room_types:
            bal_size = baseline_sizes.get("balcony", 6.0)
            allocated_rooms.append({
                "req_id": "REQ_BALCONY_AUTO",
                "type": "balcony",
                "name": "Balcony",
                "target_area": bal_size,
                "required": False,
                "priority": "low",
                "floor_preference": "1",
                "assigned_floor_index": 1,
                "is_stair": False
            })
            total_demanded_area += bal_size

        # Mandatory Total Capacity Verification
        total_mandatory_with_stairs = mandatory_demanded_area + (stair_reservation_per_floor * storey_count)
        if total_mandatory_with_stairs > total_building_capacity:
            return {
                "feasible": False,
                "infeasibility_reason": "insufficient_buildable_area",
                "details": (
                    f"Mandatory room area ({mandatory_demanded_area:.1f} m² + {stair_reservation_per_floor * storey_count:.1f} m² stairs = "
                    f"{total_mandatory_with_stairs:.1f} m²) exceeds total usable building capacity ({total_building_capacity:.1f} m² across {storey_count} floors)."
                ),
                "total_demanded_area": round(total_demanded_area, 2),
                "total_capacity": round(total_building_capacity, 2),
                "floors": []
            }

        # Client Preferred Ground Coverage / Building Area Check
        if requirements.preferred_total_building_area and requirements.preferred_total_building_area > 0:
            if mandatory_demanded_area > requirements.preferred_total_building_area:
                return {
                    "feasible": False,
                    "infeasibility_reason": "exceeds_client_preferred_area",
                    "details": (
                        f"Mandatory room programme ({mandatory_demanded_area:.1f} m²) exceeds client's specified "
                        f"preferred total building area constraint ({requirements.preferred_total_building_area:.1f} m²)."
                    ),
                    "total_demanded_area": round(total_demanded_area, 2),
                    "total_capacity": round(total_building_capacity, 2),
                    "floors": []
                }

        # Setup Floor Structures
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

        # Multi-storey Staircase Reservation per Floor
        if storey_count > 1:
            for fl in range(storey_count):
                stair_entry = {
                    "req_id": f"STAIR_F{fl}",
                    "type": "staircase",
                    "name": "Staircase Core",
                    "target_area": stair_size,
                    "required": True,
                    "priority": "high",
                    "floor_preference": str(fl),
                    "assigned_floor_index": fl,
                    "is_stair": True
                }
                floor_allocations[fl]["rooms"].append(stair_entry)
                floor_allocations[fl]["allocated_area"] += stair_size

        # Sorting: Mandatory & High Priority first, explicit floor preferences first
        def sort_key(r):
            pref = str(r.get("floor_preference", "auto")).lower()
            is_explicit = pref in ("ground", "first", "second", "third", "0", "1", "2", "3")
            return (0 if is_explicit else 1, 0 if r.get("required") else 1)

        rooms_to_assign = sorted(allocated_rooms, key=sort_key)

        ground_types = {"living_room", "kitchen", "pantry", "dining_area", "garage_parking", "utility_room"}
        upper_types = {"master_bedroom", "bedroom", "study_office", "balcony", "family_living_area"}

        # Assign Rooms to Floors
        for room in rooms_to_assign:
            pref = str(room["floor_preference"]).lower()
            target_fl: Optional[int] = None

            # 1. Parse floor preference
            if pref in ("ground", "0"):
                target_fl = 0
            elif pref in ("first", "1") and storey_count > 1:
                target_fl = 1
            elif pref in ("second", "2") and storey_count > 2:
                target_fl = 2
            elif pref in ("third", "3") and storey_count > 3:
                target_fl = 3
            elif pref not in ("auto", "any"):
                # Invalid explicit floor preference (e.g. asking for floor 3 in a 2-storey house)
                return {
                    "feasible": False,
                    "infeasibility_reason": "invalid_floor_preference",
                    "details": f"Room '{room['name']}' requested floor '{pref}', which exceeds project storey count of {storey_count}.",
                    "total_demanded_area": round(total_demanded_area, 2),
                    "total_capacity": round(total_building_capacity, 2),
                    "floors": []
                }

            # 2. Check explicit target floor capacity including the room being placed
            if target_fl is not None:
                current_fl_area = floor_allocations[target_fl]["allocated_area"]
                if current_fl_area + room["target_area"] > usable_floor_area:
                    if room["required"]:
                        # Cannot silently scale down mandatory room
                        return {
                            "feasible": False,
                            "infeasibility_reason": "floor_capacity_exceeded",
                            "details": (
                                f"Floor {target_fl} ({floor_allocations[target_fl]['name']}) capacity exceeded. "
                                f"Current allocated area is {current_fl_area:.1f} m² and room '{room['name']}' requires {room['target_area']:.1f} m², "
                                f"exceeding usable floor capacity of {usable_floor_area:.1f} m²."
                            ),
                            "total_demanded_area": round(total_demanded_area, 2),
                            "total_capacity": round(total_building_capacity, 2),
                            "floors": []
                        }
                    else:
                        # Optional room cannot fit on requested floor; skip with warning
                        continue
                assigned_fl = target_fl
            else:
                # 3. Dynamic distribution for 'auto' / 'any'
                # Check preferred floor types
                candidate_floors = list(range(storey_count))
                if room["type"] in ground_types:
                    preferred_order = [0] + [f for f in range(1, storey_count)]
                elif room["type"] in upper_types and storey_count > 1:
                    preferred_order = [f for f in range(1, storey_count)] + [0]
                else:
                    preferred_order = sorted(candidate_floors, key=lambda i: floor_allocations[i]["allocated_area"])

                assigned_fl = None
                for fl_idx in preferred_order:
                    if floor_allocations[fl_idx]["allocated_area"] + room["target_area"] <= usable_floor_area:
                        assigned_fl = fl_idx
                        break

                if assigned_fl is None:
                    if room["required"]:
                        return {
                            "feasible": False,
                            "infeasibility_reason": "insufficient_usable_capacity",
                            "details": f"Mandatory room '{room['name']}' ({room['target_area']:.1f} m²) could not fit on any floor without exceeding capacity.",
                            "total_demanded_area": round(total_demanded_area, 2),
                            "total_capacity": round(total_building_capacity, 2),
                            "floors": []
                        }
                    else:
                        continue

            room["assigned_floor_index"] = assigned_fl
            floor_allocations[assigned_fl]["rooms"].append(room)
            floor_allocations[assigned_fl]["allocated_area"] += room["target_area"]

        for fl in floor_allocations:
            fl["allocated_area"] = round(fl["allocated_area"], 2)

        return {
            "feasible": True,
            "provider": self.provider_name,
            "model_version": self.model_version,
            "total_demanded_area": round(total_demanded_area, 2),
            "total_capacity": round(total_building_capacity, 2),
            "floors": floor_allocations
        }
