"""
ESAI Finish Planner
Resolves wall, floor, ceiling, and decorative surface specifications
aligned with room functionality and client aesthetic preferences.
"""
from typing import Any, Dict, List, Optional
from ..catalog import FinishCategory, FurnitureCatalogRepository
from ..contracts import ResolvedRoomDesignInputDTO


class FinishPlanner:
    """
    Plans architectural surface treatments grounded by room requirements and style.
    """

    def __init__(self, catalog_repo: Optional[FurnitureCatalogRepository] = None):
        self.catalog_repo = catalog_repo or FurnitureCatalogRepository.get_instance()

    def plan_finishes(self, design_input: ResolvedRoomDesignInputDTO) -> Dict[str, Any]:
        """
        Determines applicable wall, floor, and ceiling finishes.
        """
        room_type = design_input.room_type.lower()
        prefs = design_input.finishes or {}
        style = (
            design_input.aesthetic_profile.dominant_style.lower()
            if design_input.aesthetic_profile else "modern"
        )

        # Defaults based on room type
        if any(b in room_type for b in ("bath", "toilet", "powder")):
            default_wall = "WALL_TILE_PORCELAIN_01"
            default_floor = "FLOOR_TILE_CERAMIC_01"
            default_ceiling = "CEILING_GYPSUM_COVE_01"
        elif any(k in room_type for k in ("kitchen", "pantry")):
            default_wall = "WALL_TILE_PORCELAIN_01"
            default_floor = "FLOOR_TERRAZZO_01"
            default_ceiling = "CEILING_GYPSUM_COVE_01"
        else:
            default_wall = "PAINT_MATTE_WHITE_01"
            default_floor = "FLOOR_OAK_PARQUET_01"
            default_ceiling = "CEILING_GYPSUM_COVE_01"

        wall_id = prefs.get("wall_finish") or default_wall
        floor_id = prefs.get("floor_finish") or default_floor
        ceiling_id = prefs.get("ceiling_finish") or default_ceiling

        wall_finish = self.catalog_repo.get_finish_by_id(wall_id)
        floor_finish = self.catalog_repo.get_finish_by_id(floor_id)
        ceiling_finish = self.catalog_repo.get_finish_by_id(ceiling_id)

        return {
            "wall_finish": {
                "finish_id": wall_id,
                "name": wall_finish.name if wall_finish else "Interior Matte Paint",
                "category": "wall_finish",
                "material_type": wall_finish.material_type if wall_finish else "matte_emulsion",
            },
            "floor_finish": {
                "finish_id": floor_id,
                "name": floor_finish.name if floor_finish else "Engineered Parquet Flooring",
                "category": "floor_finish",
                "material_type": floor_finish.material_type if floor_finish else "timber",
            },
            "ceiling_finish": {
                "finish_id": ceiling_id,
                "name": ceiling_finish.name if ceiling_finish else "Gypsum False Ceiling",
                "category": "ceiling_finish",
                "material_type": ceiling_finish.material_type if ceiling_finish else "gypsum_board",
            },
        }
