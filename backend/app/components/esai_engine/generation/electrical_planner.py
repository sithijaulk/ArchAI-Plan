"""
ESAI Electrical Planner
Associates proposed electrical power, data, and charging provisions
directly with placed furniture coordinates (e.g. TV units, bedsides, workstations).
"""
import math
from typing import Any, Dict, List, Optional
from shapely.geometry import Point, Polygon

from ..contracts import Coordinate2D, PlacedFixturePointDTO, ResolvedRoomDesignInputDTO
from ..optimizer.chromosome import PlacedAssetDTO


class ElectricalPlanner:
    """
    Grounds electrical service provisions to placed furniture while requiring professional verification.
    """

    def plan_electrical(
        self,
        design_input: ResolvedRoomDesignInputDTO,
        placed_assets: List[PlacedAssetDTO],
    ) -> List[PlacedFixturePointDTO]:
        service_points: List[PlacedFixturePointDTO] = []
        poly_pts = [(p.x, p.y) for p in design_input.polygon]
        room_poly = Polygon(poly_pts)
        centroid = room_poly.centroid

        for asset in placed_assets:
            cat = asset.category.lower().strip()
            w = asset.dimensions.width
            d = asset.dimensions.depth
            rot_rad = math.radians(asset.rotation_deg)

            # 1. TV Unit: Power & Media/Data Wall Point
            if cat in ("tv_console", "media_wall", "tv_unit"):
                service_points.append(
                    PlacedFixturePointDTO(
                        point_id=f"el_tv_media_{asset.instance_id}",
                        point_type="power_tv_media",
                        description=f"Quad electrical socket + RJ45 data outlet for {asset.asset_name}",
                        associated_instance_id=asset.instance_id,
                        position=asset.position,
                        installation_height_m=0.45,
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"circuits": ["general_power", "cat6_data"], "gangs": 4},
                    )
                )

            # 2. Bed: Bedside dual USB-C / AC charging sockets
            elif cat == "bed":
                # Offset to left and right sides of headboard
                half_w = (w / 2.0) + 0.30
                dx = math.cos(rot_rad) * half_w
                dy = math.sin(rot_rad) * half_w

                # Left socket
                service_points.append(
                    PlacedFixturePointDTO(
                        point_id=f"el_bedside_L_{asset.instance_id}",
                        point_type="power_usb_charging",
                        description=f"Left bedside dual USB-C / 13A socket for {asset.asset_name}",
                        associated_instance_id=asset.instance_id,
                        position=Coordinate2D(
                            x=round(asset.position.x - dx, 3),
                            y=round(asset.position.y - dy, 3),
                        ),
                        installation_height_m=0.60,
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"fast_charge_pd": True, "usb_ports": 2},
                    )
                )
                # Right socket
                service_points.append(
                    PlacedFixturePointDTO(
                        point_id=f"el_bedside_R_{asset.instance_id}",
                        point_type="power_usb_charging",
                        description=f"Right bedside dual USB-C / 13A socket for {asset.asset_name}",
                        associated_instance_id=asset.instance_id,
                        position=Coordinate2D(
                            x=round(asset.position.x + dx, 3),
                            y=round(asset.position.y + dy, 3),
                        ),
                        installation_height_m=0.60,
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"fast_charge_pd": True, "usb_ports": 2},
                    )
                )

            # 3. Workstation / Desk: Power & Data Outlets
            elif "desk" in cat:
                service_points.append(
                    PlacedFixturePointDTO(
                        point_id=f"el_desk_{asset.instance_id}",
                        point_type="power_workstation",
                        description=f"Workstation clean power and ethernet RJ45 point for {asset.asset_name}",
                        associated_instance_id=asset.instance_id,
                        position=asset.position,
                        installation_height_m=0.75,
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"gangs": 4, "surge_protection": True},
                    )
                )

            # 4. Kitchen Major Appliances
            elif "refrigerator" in cat:
                service_points.append(
                    PlacedFixturePointDTO(
                        point_id=f"el_fridge_{asset.instance_id}",
                        point_type="power_refrigerator",
                        description="Dedicated unswitched refrigerator power socket",
                        associated_instance_id=asset.instance_id,
                        position=asset.position,
                        installation_height_m=0.30,
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"dedicated_circuit": True, "ampere": 16},
                    )
                )
            elif "cooktop" in cat or "range" in cat:
                service_points.append(
                    PlacedFixturePointDTO(
                        point_id=f"el_cooktop_{asset.instance_id}",
                        point_type="power_cooktop_high_load",
                        description="High-amperage induction cooktop junction point",
                        associated_instance_id=asset.instance_id,
                        position=asset.position,
                        installation_height_m=0.75,
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"dedicated_circuit": True, "ampere": 32, "phase": "single_or_three"},
                    )
                )

        # 5. Room-Level Services (Ceiling fan point, AC provision)
        for req in design_input.service_requirements:
            st = req.service_type.value if hasattr(req.service_type, "value") else str(req.service_type)
            if "fan" in st:
                service_points.append(
                    PlacedFixturePointDTO(
                        point_id=f"el_fan_{design_input.room_id}",
                        point_type="power_ceiling_fan",
                        description="Ceiling fan junction point centered in room ceiling zone",
                        position=Coordinate2D(x=round(centroid.x, 3), y=round(centroid.y, 3)),
                        installation_height_m=design_input.ceiling_height_m,
                        status="proposed_new",
                        requires_professional_verification=True,
                        spec={"control": "speed_regulator"},
                    )
                )

        return service_points
