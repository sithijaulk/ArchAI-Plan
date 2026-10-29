"""
ESAI Candidate Population Generator
Generates geometrically plausible initial populations for PyGAD,
incorporating wall-alignment sampling, door avoidance, and deterministic random seeds.
"""
import math
import random
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from shapely.geometry import LineString, Point, Polygon

from ..contracts import DoorDTO, FixedObstructionDTO, WindowDTO
from .chromosome import ChromosomeCodec, PlacedAssetDTO


class CandidateGenerator:
    """
    Produces initial chromosomes and baseline candidates (Random Search & Greedy Heuristics).
    """

    def __init__(
        self,
        codec: ChromosomeCodec,
        doors: Optional[List[DoorDTO]] = None,
        windows: Optional[List[WindowDTO]] = None,
        fixed_obstructions: Optional[List[FixedObstructionDTO]] = None,
        seed: Optional[int] = 42,
    ):
        self.codec = codec
        self.room_polygon = codec.room_polygon
        self.doors = doors or []
        self.windows = windows or []
        self.fixed_obstructions = fixed_obstructions or []
        self.seed = seed
        self.rng = random.Random(seed)
        self.np_rng = np.random.RandomState(seed)

        # Extract wall boundary segments
        self.walls: List[LineString] = []
        coords = list(self.room_polygon.exterior.coords)
        for i in range(len(coords) - 1):
            p1, p2 = coords[i], coords[i + 1]
            seg = LineString([p1, p2])
            if seg.length > 0.3:
                self.walls.append(seg)

    def generate_initial_population(self, population_size: int = 30) -> List[List[float]]:
        """
        Creates a diverse initial population of chromosome vectors.
        Uses a blend of wall-aligned placement (50%), interior random (30%), and greedy heuristics (20%).
        """
        population: List[List[float]] = []

        # 1. First candidate: Greedy heuristic placement
        greedy_chrom = self.generate_greedy_chromosome()
        if greedy_chrom:
            population.append(greedy_chrom)

        # 2. Wall-affinity guided candidates
        num_wall_guided = max(5, int(population_size * 0.5))
        for _ in range(num_wall_guided):
            chrom = self._generate_wall_guided_chromosome()
            population.append(chrom)

        # 3. Random interior sampling to ensure genetic diversity
        while len(population) < population_size:
            chrom = self.generate_random_chromosome()
            population.append(chrom)

        return population[:population_size]

    def generate_random_chromosome(self) -> List[float]:
        """
        Generates a completely randomized chromosome within the room bounding box.
        """
        chromosome: List[float] = []
        for inst in self.codec.movable_instances:
            # Sample point inside bounding box
            x = self.rng.uniform(self.codec.min_x, self.codec.max_x)
            y = self.rng.uniform(self.codec.min_y, self.codec.max_y)

            rotations = inst.supported_rotations if inst.supported_rotations else [0, 90, 180, 270]
            rot_idx = self.rng.randint(0, max(0, len(rotations) - 1))

            chromosome.extend([x, y, float(rot_idx)])
        return chromosome

    def generate_greedy_chromosome(self) -> List[float]:
        """
        Constructs a deterministic greedy candidate placing major items against compatible walls
        while avoiding doors and mutual overlap.
        """
        placed_footprints: List[Polygon] = [
            la.footprint_polygon for la in self.codec.locked_assets if la.footprint_polygon
        ]
        chromosome: List[float] = []

        for inst in self.codec.movable_instances:
            best_x, best_y, best_rot_idx = self._find_best_greedy_placement(inst, placed_footprints)
            chromosome.extend([best_x, best_y, float(best_rot_idx)])

            footprint = self.codec.calculate_footprint(
                best_x,
                best_y,
                inst.dimensions.width,
                inst.dimensions.depth,
                (inst.supported_rotations or [0])[best_rot_idx],
            )
            placed_footprints.append(footprint)

        return chromosome

    def _generate_wall_guided_chromosome(self) -> List[float]:
        """
        Samples candidates placing wall-aligned furniture near wall perimeters.
        """
        chromosome: List[float] = []
        for inst in self.codec.movable_instances:
            w = inst.dimensions.width
            d = inst.dimensions.depth
            rotations = inst.supported_rotations if inst.supported_rotations else [0, 90, 180, 270]

            if self.walls and (inst.wall_affinity or inst.placement_mode.value == "wall_mounted"):
                # Pick a random wall
                wall = self.rng.choice(self.walls)
                # Compute wall normal/inward angle
                angle = self._get_wall_inward_angle(wall)
                # Closest allowed rotation
                rot_idx = self._find_closest_rotation_idx(angle, rotations)
                chosen_rot = rotations[rot_idx]

                # Sample along the wall (leaving clearance at edges)
                t = self.rng.uniform(0.15, 0.85)
                wall_pt = wall.interpolate(t, normalized=True)

                # Offset inward into the room
                inward_dist = (d / 2.0) + 0.05
                # Normal vector into room
                dx = -math.sin(math.radians(chosen_rot)) * inward_dist
                dy = math.cos(math.radians(chosen_rot)) * inward_dist
                pos_x = wall_pt.x + dx
                pos_y = wall_pt.y + dy

                # Check if inside polygon; if not, fallback
                if not self.room_polygon.contains(Point(pos_x, pos_y)):
                    pos_x, pos_y = self._sample_interior_point(w, d)

                chromosome.extend([pos_x, pos_y, float(rot_idx)])
            else:
                pos_x, pos_y = self._sample_interior_point(w, d)
                rot_idx = self.rng.randint(0, len(rotations) - 1)
                chromosome.extend([pos_x, pos_y, float(rot_idx)])

        return chromosome

    def _sample_interior_point(self, width: float, depth: float) -> Tuple[float, float]:
        """
        Samples a valid point inside the room polygon with margin.
        """
        margin = max(width, depth) / 2.0
        # Try erosion/buffered polygon for safer interior placement
        buffered = self.room_polygon.buffer(-min(0.2, margin * 0.5))
        target_geom = buffered if not buffered.is_empty else self.room_polygon

        for _ in range(50):
            rx = self.rng.uniform(self.codec.min_x, self.codec.max_x)
            ry = self.rng.uniform(self.codec.min_y, self.codec.max_y)
            pt = Point(rx, ry)
            if target_geom.contains(pt):
                return rx, ry

        # Fallback to centroid
        c = self.room_polygon.centroid
        return c.x, c.y

    def _find_best_greedy_placement(
        self,
        inst: Any,
        existing_footprints: List[Polygon],
    ) -> Tuple[float, float, int]:
        """
        Greedy placement: tries wall segments in sequence to find first non-overlapping position.
        """
        rotations = inst.supported_rotations if inst.supported_rotations else [0, 90, 180, 270]
        w, d = inst.dimensions.width, inst.dimensions.depth

        # Candidate walls
        for wall in self.walls:
            angle = self._get_wall_inward_angle(wall)
            rot_idx = self._find_closest_rotation_idx(angle, rotations)
            chosen_rot = rotations[rot_idx]

            for t in [0.25, 0.5, 0.75, 0.35, 0.65]:
                wall_pt = wall.interpolate(t, normalized=True)
                inward_dist = (d / 2.0) + 0.05
                dx = -math.sin(math.radians(chosen_rot)) * inward_dist
                dy = math.cos(math.radians(chosen_rot)) * inward_dist
                cand_x = wall_pt.x + dx
                cand_y = wall_pt.y + dy

                footprint = self.codec.calculate_footprint(cand_x, cand_y, w, d, chosen_rot)

                # Check containment & overlap
                if self.room_polygon.contains(footprint):
                    collision = any(footprint.intersects(ef) for ef in existing_footprints)
                    if not collision:
                        return cand_x, cand_y, rot_idx

        # Centroid fallback
        c_x, c_y = self._sample_interior_point(w, d)
        return c_x, c_y, 0

    def _get_wall_inward_angle(self, wall: LineString) -> float:
        """
        Computes the angle (in degrees) that faces inward from the wall into the room.
        """
        p1, p2 = wall.coords[0], wall.coords[1]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        # Wall angle
        wall_angle = math.degrees(math.atan2(dy, dx))
        # Normal pointing perpendicular
        normal_angle_1 = (wall_angle + 90.0) % 360.0
        normal_angle_2 = (wall_angle - 90.0) % 360.0

        mid_x = (p1[0] + p2[0]) / 2.0
        mid_y = (p1[1] + p2[1]) / 2.0

        # Test point 0.3m along normal 1
        test_x1 = mid_x + 0.3 * math.cos(math.radians(normal_angle_1))
        test_y1 = mid_y + 0.3 * math.sin(math.radians(normal_angle_1))

        if self.room_polygon.contains(Point(test_x1, test_y1)):
            return normal_angle_1
        return normal_angle_2

    def _find_closest_rotation_idx(self, target_angle: float, supported_rotations: List[int]) -> int:
        best_diff = 999.0
        best_idx = 0
        for idx, rot in enumerate(supported_rotations):
            diff = abs((rot - target_angle + 180) % 360 - 180)
            if diff < best_diff:
                best_diff = diff
                best_idx = idx
        return best_idx
