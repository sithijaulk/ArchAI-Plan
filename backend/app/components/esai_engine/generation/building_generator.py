"""
ESAI Building Generator
Orchestrates multi-room, multi-floor, and building-level layout generation.
Discovers actual project geometry, resolves effective client preferences,
and compiles aggregate generation outcomes.
"""
from typing import Any, Dict, List, Optional
from app.models.project import Project
from ..contracts import (
    GeneratedBuildingDesignDTO,
    GeneratedRoomDesignDTO,
    ResolvedRoomDesignInputDTO,
)
from ..optimizer.genetic_optimizer import OptimizationConfig
from .room_generator import RoomGenerator


class BuildingGenerator:
    """
    Coordinates layout optimization across entire buildings, floors, or specific rooms.
    """

    def __init__(self, room_generator: Optional[RoomGenerator] = None):
        self.room_generator = room_generator or RoomGenerator()

    def generate(
        self,
        service: Any,
        project: Project,
        scope: str = "building",  # "room" | "floor" | "building"
        target_floor_id: Optional[str] = None,
        target_room_id: Optional[str] = None,
        config: Optional[OptimizationConfig] = None,
    ) -> GeneratedBuildingDesignDTO:
        """
        Executes generation over the requested scope.
        """
        all_rooms = service.get_rooms(project)
        rooms_to_process = []

        if scope == "room" and target_room_id:
            rooms_to_process = [r for r in all_rooms if r.room_id == target_room_id]
        elif scope == "floor" and target_floor_id:
            rooms_to_process = [r for r in all_rooms if r.floor_id == target_floor_id]
        else:
            rooms_to_process = list(all_rooms)

        total_discovered = len(rooms_to_process)
        successful_count = 0
        failed_count = 0
        room_results: Dict[str, GeneratedRoomDesignDTO] = {}

        rev = getattr(project, "revision", 1) or 1

        for room in rooms_to_process:
            try:
                # 1. Resolve effective preferences & GA-ready design input
                design_input: ResolvedRoomDesignInputDTO = service.resolve_room_design_input(
                    project=project,
                    room_id=room.room_id,
                    floor_id=room.floor_id,
                )

                # 2. Run Room Generator
                room_res = self.room_generator.generate_room(design_input, config)
                room_results[room.room_id] = room_res

                if room_res.status == "success":
                    successful_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                failed_count += 1
                from ..contracts import Coordinate2D
                # Structured error fallback for individual room without aborting entire building
                poly_coords = room.polygon if room.polygon else []
                room_results[room.room_id] = GeneratedRoomDesignDTO(
                    room_id=room.room_id,
                    room_name=room.name,
                    room_type=room.room_type.value if hasattr(room.room_type, "value") else str(room.room_type),
                    floor_id=room.floor_id,
                    status="error",
                    polygon=poly_coords,
                    area_sqm=room.area_sqm or 0.0,
                    ceiling_height_m=room.ceiling_height or 2.8,
                    diagnostics=[f"Optimization pipeline exception: {str(e)}"],
                    hard_constraints_passed=False,
                )

        # 3. Determine Overall Building Status
        if successful_count == total_discovered and total_discovered > 0:
            overall_status = "success"
        elif successful_count > 0:
            overall_status = "partial"
        else:
            overall_status = "failed"

        structural_input = service.get_structural_context(project)
        from ..geometry import compute_geometry_fingerprint
        geo_fingerprint = compute_geometry_fingerprint(structural_input)

        return GeneratedBuildingDesignDTO(
            project_id=project.id,
            project_name=project.project_name,
            status=overall_status,
            geometry_revision=rev,
            geometry_fingerprint=geo_fingerprint,
            scope=scope,
            target_floor_id=target_floor_id,
            target_room_id=target_room_id,
            total_rooms_discovered=total_discovered,
            successful_rooms_count=successful_count,
            failed_rooms_count=failed_count,
            rooms=room_results,
            metadata={
                "engine": "ESAI-Engine Phase 4 Evolutionary Optimizer",
                "framework": "PyGAD + Shapely",
                "scope": scope,
            },
        )
