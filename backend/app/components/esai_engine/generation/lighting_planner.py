"""
ESAI Lighting Planner
Determines luminaire fixture placements based on room geometry, ceiling height,
and placed functional furniture (islands, dining tables, desks, beds).
"""
from typing import Any, Dict, List, Optional
from shapely.geometry import Point, Polygon

from ..contracts import Coordinate2D, PlacedFixturePointDTO, ResolvedRoomDesignInputDTO
from ..optimizer.chromosome import PlacedAssetDTO


class LightingPlanner:
    """
    Plans luminaire positions grounded by geometric ceiling centers and functional zones.
    """

    def plan_lighting(
        self,
        design_input: ResolvedRoomDesignInputDTO,
        placed_assets: List[PlacedAssetDTO],
    ) -> List[PlacedFixturePointDTO]:
        fixtures: List[PlacedFixturePointDTO] = []
        poly_pts = [(p.x, p.y) for p in design_input.polygon]
        room_poly = Polygon(poly_pts)
        c = room_poly.centroid
        room_area = design_input.area_sqm
        ceiling_h = design_input.ceiling_height_m

        # 1. Primary Central Ceiling / Pendant Luminaire
        fixtures.append(
            PlacedFixturePointDTO(
                point_id=f"lt_ceil_{design_input.room_id}_main",
                point_type="lighting_ceiling_main",
                description="General ambient ceiling luminaire centered in room",
                position=Coordinate2D(x=round(c.x, 3), y=round(c.y, 3)),
                installation_height_m=ceiling_h,
                status="proposed_new",
                requires_professional_verification=True,
                spec={
                    "fixture_category": "ceiling_ambient",
                    "color_temperature_k": 3000,
                    "target_lux": 150,
                },
            )
        )

        # 2. Functional Task Lighting grounded by furniture
        for asset in placed_assets:
            cat = asset.category.lower().strip()
            # Dining table pendant
            if "dining" in cat and "table" in cat:
                fixtures.append(
                    PlacedFixturePointDTO(
                        point_id=f"lt_pendant_{asset.instance_id}",
                        point_type="lighting_pendant_dining",
                        description=f"Decorative pendant fixture suspended over {asset.asset_name}",
                        associated_instance_id=asset.instance_id,
                        position=asset.position,
                        installation_height_m=round(ceiling_h - 0.75, 2),
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"fixture_category": "pendant", "mounting": "suspended"},
                    )
                )

            # Study / Work Desk task light
            elif "desk" in cat:
                fixtures.append(
                    PlacedFixturePointDTO(
                        point_id=f"lt_task_{asset.instance_id}",
                        point_type="lighting_task_desk",
                        description=f"Focused task lighting over {asset.asset_name}",
                        associated_instance_id=asset.instance_id,
                        position=asset.position,
                        installation_height_m=round(asset.dimensions.height + 0.45, 2),
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"fixture_category": "task_light", "target_lux": 400},
                    )
                )

            # Bed reading lights
            elif cat == "bed":
                fixtures.append(
                    PlacedFixturePointDTO(
                        point_id=f"lt_read_{asset.instance_id}",
                        point_type="lighting_reading_bed",
                        description=f"Directional headboard reading lights for {asset.asset_name}",
                        associated_instance_id=asset.instance_id,
                        position=asset.position,
                        installation_height_m=round(asset.dimensions.height + 0.60, 2),
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"fixture_category": "reading_sconce", "color_temperature_k": 2700},
                    )
                )

        return fixtures
