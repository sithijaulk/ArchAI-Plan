"""
ESAI Chromosome Codec
Deterministic encoding and decoding between PyGAD 1D gene vectors and 2D spatial layouts.
Preserves user-locked placements, explicit dimensions, and placement modes.
"""
import math
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field
from shapely.geometry import Polygon, box
from shapely.affinity import rotate, translate

from ..contracts import (
    Coordinate2D,
    Dimensions3D,
    PlacementMode,
    ResolvedAssetInstanceDTO,
)


class PlacedAssetDTO(BaseModel):
    """
    Representation of an asset placed with exact 2D coordinates and rotation in the room.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    instance_id: str
    asset_id: str
    asset_name: str
    category: str
    subtype: str
    dimensions: Dimensions3D
    position: Coordinate2D
    rotation_deg: float
    placement_mode: PlacementMode = PlacementMode.FLOOR_STANDING
    priority: str = "mandatory"
    wall_affinity: Optional[str] = None
    preferred_wall: Optional[str] = None
    style_tag: Optional[str] = None
    material_variant: Optional[str] = None
    clearance_rule_id: Optional[str] = None
    associated_service_ids: List[str] = Field(default_factory=list)
    rendering_model_id: Optional[str] = None
    source_attribution: str = "genetic_algorithm"
    is_locked: bool = False
    footprint_polygon: Optional[Any] = None


class ChromosomeCodec:
    """
    Converts between PyGAD gene vectors and typed PlacedAssetDTO lists.
    Guarantees user-locked items are never mutated, and selected asset variants/quantities
    are strictly preserved without substitution.
    """

    GENES_PER_ASSET = 3  # [x, y, rotation_index]

    def __init__(
        self,
        room_polygon: Polygon,
        asset_instances: List[ResolvedAssetInstanceDTO],
    ):
        self.room_polygon = room_polygon
        self.min_x, self.min_y, self.max_x, self.max_y = room_polygon.bounds
        self.width_span = max(0.1, self.max_x - self.min_x)
        self.depth_span = max(0.1, self.max_y - self.min_y)

        # Separate locked vs movable instances
        self.locked_assets: List[PlacedAssetDTO] = []
        self.movable_instances: List[ResolvedAssetInstanceDTO] = []

        for inst in asset_instances:
            if inst.priority == "user_locked" and inst.locked_coordinates is not None:
                rot = inst.locked_rotation if inst.locked_rotation is not None else 0.0
                poly = self.calculate_footprint(
                    inst.locked_coordinates.x,
                    inst.locked_coordinates.y,
                    inst.dimensions.width,
                    inst.dimensions.depth,
                    rot,
                )
                self.locked_assets.append(
                    PlacedAssetDTO(
                        instance_id=inst.instance_id,
                        asset_id=inst.asset_id,
                        asset_name=inst.asset_name,
                        category=inst.category,
                        subtype=inst.subtype,
                        dimensions=inst.dimensions,
                        position=inst.locked_coordinates,
                        rotation_deg=rot,
                        placement_mode=inst.placement_mode,
                        priority="user_locked",
                        wall_affinity=inst.wall_affinity,
                        preferred_wall=inst.preferred_wall,
                        style_tag=inst.style_tag,
                        material_variant=inst.material_variant,
                        clearance_rule_id=inst.clearance_rule_id,
                        associated_service_ids=inst.associated_service_ids,
                        rendering_model_id=inst.rendering_model_id,
                        source_attribution="user_locked",
                        is_locked=True,
                        footprint_polygon=poly,
                    )
                )
            else:
                self.movable_instances.append(inst)

        self.num_movable = len(self.movable_instances)
        self.chromosome_length = self.num_movable * self.GENES_PER_ASSET

    def get_gene_space(self) -> List[Dict[str, float]]:
        """
        Builds the bounds for each gene in the chromosome.
        For each movable asset:
          gene 0 (x): [min_x, max_x]
          gene 1 (y): [min_y, max_y]
          gene 2 (rot_idx): [0, num_allowed_rotations - 1]
        """
        gene_space = []
        for inst in self.movable_instances:
            # X coordinate
            gene_space.append({"low": float(self.min_x), "high": float(self.max_x)})
            # Y coordinate
            gene_space.append({"low": float(self.min_y), "high": float(self.max_y)})
            # Rotation index
            rotations = inst.supported_rotations if inst.supported_rotations else [0, 90, 180, 270]
            max_idx = max(0, len(rotations) - 1)
            gene_space.append({"low": 0.0, "high": float(max_idx)})
        return gene_space

    def decode(self, solution: List[float]) -> List[PlacedAssetDTO]:
        """
        Decodes a 1D PyGAD chromosome vector into full PlacedAssetDTO objects,
        merging movable instances with fixed user-locked assets.
        """
        placed_assets: List[PlacedAssetDTO] = list(self.locked_assets)

        for i, inst in enumerate(self.movable_instances):
            base_idx = i * self.GENES_PER_ASSET
            if base_idx + 2 >= len(solution):
                break

            x_val = float(solution[base_idx])
            y_val = float(solution[base_idx + 1])
            rot_idx_val = float(solution[base_idx + 2])

            # Resolve rotation
            rotations = inst.supported_rotations if inst.supported_rotations else [0, 90, 180, 270]
            safe_rot_idx = int(round(rot_idx_val)) % len(rotations)
            chosen_rot = float(rotations[safe_rot_idx])

            # Clamp coordinates safely to bounding box
            clamped_x = max(self.min_x, min(self.max_x, x_val))
            clamped_y = max(self.min_y, min(self.max_y, y_val))

            footprint = self.calculate_footprint(
                clamped_x,
                clamped_y,
                inst.dimensions.width,
                inst.dimensions.depth,
                chosen_rot,
            )

            placed = PlacedAssetDTO(
                instance_id=inst.instance_id,
                asset_id=inst.asset_id,
                asset_name=inst.asset_name,
                category=inst.category,
                subtype=inst.subtype,
                dimensions=inst.dimensions,
                position=Coordinate2D(x=round(clamped_x, 3), y=round(clamped_y, 3)),
                rotation_deg=chosen_rot,
                placement_mode=inst.placement_mode,
                priority=inst.priority,
                wall_affinity=inst.wall_affinity,
                preferred_wall=inst.preferred_wall,
                style_tag=inst.style_tag,
                material_variant=inst.material_variant,
                clearance_rule_id=inst.clearance_rule_id,
                associated_service_ids=inst.associated_service_ids,
                rendering_model_id=inst.rendering_model_id,
                source_attribution="genetic_algorithm",
                is_locked=False,
                footprint_polygon=footprint,
            )
            placed_assets.append(placed)

        return placed_assets

    def encode(self, placed_assets: List[PlacedAssetDTO]) -> List[float]:
        """
        Encodes a list of PlacedAssetDTO objects into a 1D gene vector.
        """
        placed_map = {pa.instance_id: pa for pa in placed_assets}
        chromosome: List[float] = []

        for inst in self.movable_instances:
            pa = placed_map.get(inst.instance_id)
            if pa:
                rotations = inst.supported_rotations if inst.supported_rotations else [0, 90, 180, 270]
                try:
                    rot_idx = rotations.index(int(pa.rotation_deg))
                except ValueError:
                    rot_idx = 0
                chromosome.extend([pa.position.x, pa.position.y, float(rot_idx)])
            else:
                # Default centroid
                centroid = self.room_polygon.centroid
                chromosome.extend([centroid.x, centroid.y, 0.0])

        return chromosome

    @staticmethod
    def calculate_footprint(
        pos_x: float,
        pos_y: float,
        width: float,
        depth: float,
        rotation_deg: float,
    ) -> Polygon:
        """
        Constructs an oriented bounding box (OBB) Polygon centered at (pos_x, pos_y).
        """
        hw = width / 2.0
        hd = depth / 2.0
        local_box = box(-hw, -hd, hw, hd)
        rotated_box = rotate(local_box, rotation_deg, origin=(0, 0))
        return translate(rotated_box, pos_x, pos_y)
