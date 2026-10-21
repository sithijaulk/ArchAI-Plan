"""
ESAI Plumbing & Mechanical Planner
Identifies water supply, drainage, and hot-water dependencies for placed sanitary and kitchen fixtures.
"""
from typing import Any, Dict, List, Optional
from ..contracts import PlacedFixturePointDTO, ResolvedRoomDesignInputDTO
from ..optimizer.chromosome import PlacedAssetDTO


class PlumbingPlanner:
    """
    Plans water supply and drainage dependencies based on placed sanitary and kitchen fixtures.
    """

    def plan_plumbing(
        self,
        design_input: ResolvedRoomDesignInputDTO,
        placed_assets: List[PlacedAssetDTO],
    ) -> List[PlacedFixturePointDTO]:
        points: List[PlacedFixturePointDTO] = []

        hot_water_required = any(
            "water_hot" in (req.service_type.value if hasattr(req.service_type, "value") else str(req.service_type))
            for req in design_input.service_requirements
        )

        for asset in placed_assets:
            cat = asset.category.lower().strip()
            # Washbasin / Vanity
            if "vanity" in cat or "basin" in cat:
                points.append(
                    PlacedFixturePointDTO(
                        point_id=f"pl_basin_{asset.instance_id}",
                        point_type="plumbing_water_and_drainage",
                        description=f"Cold {'and Hot ' if hot_water_required else ''}water supply and 32mm waste trap for {asset.asset_name}",
                        associated_instance_id=asset.instance_id,
                        position=asset.position,
                        installation_height_m=0.55,
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"hot_water": hot_water_required, "drain_diameter_mm": 32},
                    )
                )

            # Shower
            elif "shower" in cat:
                points.append(
                    PlacedFixturePointDTO(
                        point_id=f"pl_shower_{asset.instance_id}",
                        point_type="plumbing_shower_mixer_drain",
                        description=f"Concealed shower mixer and 100mm floor drain trap for {asset.asset_name}",
                        associated_instance_id=asset.instance_id,
                        position=asset.position,
                        installation_height_m=1.05,
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"hot_water": hot_water_required, "floor_trap_mm": 100},
                    )
                )

            # Bathtub (if selected)
            elif "bathtub" in cat:
                points.append(
                    PlacedFixturePointDTO(
                        point_id=f"pl_tub_{asset.instance_id}",
                        point_type="plumbing_bathtub_supply_drain",
                        description=f"High-flow hot/cold water supply and 40mm drain for {asset.asset_name}",
                        associated_instance_id=asset.instance_id,
                        position=asset.position,
                        installation_height_m=0.45,
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"hot_water": True, "drain_diameter_mm": 40},
                    )
                )

            # WC / Commode
            elif "commode" in cat or "toilet" in cat or "wc" in cat:
                points.append(
                    PlacedFixturePointDTO(
                        point_id=f"pl_wc_{asset.instance_id}",
                        point_type="plumbing_wc_soil_pipe",
                        description=f"110mm soil pipe connection and cold water cistern inlet for {asset.asset_name}",
                        associated_instance_id=asset.instance_id,
                        position=asset.position,
                        installation_height_m=0.20,
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"soil_pipe_mm": 110, "flush_type": "dual_flush"},
                    )
                )

            # Kitchen Sink
            elif "sink" in cat:
                points.append(
                    PlacedFixturePointDTO(
                        point_id=f"pl_sink_{asset.instance_id}",
                        point_type="plumbing_sink_supply_drain",
                        description=f"Kitchen water supply and 40mm waste outlet for {asset.asset_name}",
                        associated_instance_id=asset.instance_id,
                        position=asset.position,
                        installation_height_m=0.50,
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"hot_water": hot_water_required, "grease_trap_compatible": True},
                    )
                )

        return points
