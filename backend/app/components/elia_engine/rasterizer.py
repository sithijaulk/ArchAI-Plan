from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
from shapely.geometry import Point, Polygon, shape


@dataclass(frozen=True)
class RasterMetadata:
    grid_size: int
    scale: float
    origin_x: float
    origin_y: float
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def to_grid(self, x: float, y: float) -> tuple[float, float]:
        """Convert real-world coordinates (meters) to continuous grid indices (u, v)."""
        u = (x - self.origin_x) * self.scale
        v = (y - self.origin_y) * self.scale
        return u, v

    def to_world(self, u: float, v: float) -> tuple[float, float]:
        """Convert continuous grid indices (u, v) back to real-world coordinates (meters)."""
        x = self.origin_x + (u / self.scale)
        y = self.origin_y + (v / self.scale)
        return x, y


def build_raster_metadata(land_polygon: Polygon, grid_size: int = 96, margin_cells: float = 3.0) -> RasterMetadata:
    """Compute aspect-preserving uniform scaling and origin offset for a site polygon."""
    min_x, min_y, max_x, max_y = land_polygon.bounds
    width = max(max_x - min_x, 1e-3)
    height = max(max_y - min_y, 1e-3)

    usable_cells = float(grid_size) - 2.0 * margin_cells
    scale = usable_cells / max(width, height)

    # Center bounding box in the grid
    scaled_w = width * scale
    scaled_h = height * scale
    offset_u = (grid_size - scaled_w) / 2.0
    offset_v = (grid_size - scaled_h) / 2.0

    origin_x = min_x - (offset_u / scale)
    origin_y = min_y - (offset_v / scale)

    return RasterMetadata(
        grid_size=grid_size,
        scale=scale,
        origin_x=origin_x,
        origin_y=origin_y,
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
    )


def rasterize_polygon(poly: Polygon, meta: RasterMetadata) -> np.ndarray:
    """Rasterize a Shapely polygon into a 2D binary grid (H, W)."""
    grid = np.zeros((meta.grid_size, meta.grid_size), dtype=np.float32)
    if poly.is_empty or not poly.is_valid:
        return grid

    # Bounding box in grid coordinates
    min_u, min_v = meta.to_grid(poly.bounds[0], poly.bounds[1])
    max_u, max_v = meta.to_grid(poly.bounds[2], poly.bounds[3])

    u0 = max(0, int(math.floor(min(min_u, max_u))))
    u1 = min(meta.grid_size, int(math.ceil(max(min_u, max_u))) + 1)
    v0 = max(0, int(math.floor(min(min_v, max_v))))
    v1 = min(meta.grid_size, int(math.ceil(max(min_v, max_v))) + 1)

    for v in range(v0, v1):
        for u in range(u0, u1):
            wx, wy = meta.to_world(u + 0.5, v + 0.5)
            if poly.contains(Point(wx, wy)):
                grid[v, u] = 1.0
    return grid


def rasterize_model_input(prepared_input: Mapping[str, Any], grid_size: int = 96) -> tuple[np.ndarray, RasterMetadata]:
    """
    Produce the canonical 9x96x96 input tensor from the normalized ELIA model input.

    Channel definitions:
      0: land_mask
      1: house_mask
      2: road_access_mask
      3: entrance_mask
      4: utility_restriction_mask
      5: shadow_aspect_mask
      6: preference_density_weight
      7: preference_style_greeny
      8: preference_style_minimal
    """
    raw_land = prepared_input.get("land")
    if not raw_land:
        raise ValueError("Cannot rasterize model input: missing land polygon")
    land_poly = shape(raw_land)
    if land_poly.is_empty or not land_poly.is_valid:
        raise ValueError("Cannot rasterize model input: invalid land polygon")

    meta = build_raster_metadata(land_poly, grid_size=grid_size)
    tensor = np.zeros((9, grid_size, grid_size), dtype=np.float32)

    # Channel 0: Land mask
    tensor[0] = rasterize_polygon(land_poly, meta)

    # Channel 1: House mask
    raw_house = prepared_input.get("house_exterior")
    if raw_house:
        house_poly = shape(raw_house)
        if house_poly.is_valid and not house_poly.is_empty:
            tensor[1] = rasterize_polygon(house_poly, meta)

    # Channel 2: Road access mask
    road_access = prepared_input.get("road_access", {})
    road_side = road_access.get("road_side")
    if road_side and land_poly.is_valid:
        min_x, min_y, max_x, max_y = land_poly.bounds
        road_poly = None
        buffer_depth = 2.0  # 2m corridor along road side
        if road_side == "south":
            road_poly = Polygon([(min_x, min_y), (max_x, min_y), (max_x, min_y + buffer_depth), (min_x, min_y + buffer_depth)])
        elif road_side == "north":
            road_poly = Polygon([(min_x, max_y - buffer_depth), (max_x, max_y - buffer_depth), (max_x, max_y), (min_x, max_y)])
        elif road_side == "east":
            road_poly = Polygon([(max_x - buffer_depth, min_y), (max_x, min_y), (max_x, max_y), (max_x - buffer_depth, max_y)])
        elif road_side == "west":
            road_poly = Polygon([(min_x, min_y), (min_x + buffer_depth, min_y), (min_x + buffer_depth, max_y), (min_x, max_y)])

        if road_poly:
            road_clipped = road_poly.intersection(land_poly)
            if isinstance(road_clipped, Polygon) and not road_clipped.is_empty:
                tensor[2] = rasterize_polygon(road_clipped, meta)

    # Channel 3: Entrance Gaussian mask
    entrance = prepared_input.get("main_entrance") or prepared_input.get("computed_access_target")
    if entrance and len(entrance) >= 2:
        ex, ey = float(entrance[0]), float(entrance[1])
        eu, ev = meta.to_grid(ex, ey)
        sigma = 2.0 * meta.scale  # ~2 meters radius in pixels
        for v in range(grid_size):
            for u in range(grid_size):
                dist_sq = (u - eu) ** 2 + (v - ev) ** 2
                tensor[3, v, u] = math.exp(-dist_sq / (2.0 * (sigma ** 2 + 1e-4)))

    # Channel 4: Utility and restricted zones mask
    utils = prepared_input.get("utilities", {})
    restricted_zones = prepared_input.get("exterior_restrictions", [])
    util_mask = np.zeros((grid_size, grid_size), dtype=np.float32)

    if isinstance(utils, Mapping):
        for u_name, u_data in utils.items():
            if isinstance(u_data, Mapping) and "position_m" in u_data:
                ux, uy = u_data["position_m"][:2]
                radius = 15.24 if u_name in {"well", "septic_tank"} else 1.5  # standard 50ft buffer
                buf_poly = Point(ux, uy).buffer(radius)
                util_mask = np.maximum(util_mask, rasterize_polygon(buf_poly, meta))

    for rz in restricted_zones:
        try:
            rz_poly = shape(rz)
            if rz_poly.is_valid and not rz_poly.is_empty:
                util_mask = np.maximum(util_mask, rasterize_polygon(rz_poly, meta))
        except Exception:
            pass
    tensor[4] = util_mask

    # Channel 5: Sun/Shadow aspect mask (North orientation gradient)
    north_deg = float(prepared_input.get("north_angle_degrees", 0.0))
    north_rad = math.radians(north_deg)
    # Direction vector pointing South (sun facing in northern tropics)
    sun_dx = -math.sin(north_rad)
    sun_dy = -math.cos(north_rad)

    # Gradient from house toward residual ground
    house_cx, house_cy = (land_poly.centroid.x, land_poly.centroid.y)
    raw_house = prepared_input.get("house_exterior")
    if raw_house:
        hp = shape(raw_house)
        if hp.is_valid:
            house_cx, house_cy = hp.centroid.x, hp.centroid.y

    for v in range(grid_size):
        for u in range(grid_size):
            if tensor[0, v, u] > 0 and tensor[1, v, u] == 0:
                wx, wy = meta.to_world(u + 0.5, v + 0.5)
                dx = wx - house_cx
                dy = wy - house_cy
                norm = math.hypot(dx, dy) + 1e-5
                dot = (dx * sun_dx + dy * sun_dy) / norm
                # Map dot [-1, 1] to [0, 1]
                tensor[5, v, u] = max(0.0, min(1.0, 0.5 + 0.5 * dot))

    # Channels 6-8: User preference conditioning
    reqs = prepared_input.get("requirements", {})
    landscape_reqs = reqs.get("landscape", {})

    density_val = landscape_reqs.get("greenery_density", "medium")
    density_map = {"low": 0.33, "medium": 0.66, "high": 1.0, "sparse": 0.33, "balanced": 0.66, "dense": 1.0}
    tensor[6, :, :] = density_map.get(density_val, 0.66)

    concept = str(reqs.get("concept_style", "modern")).lower()
    tensor[7, :, :] = 1.0 if "greeny" in concept else 0.0
    tensor[8, :, :] = 1.0 if "minimal" in concept else 0.0

    return tensor, meta
