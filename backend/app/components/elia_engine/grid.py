from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from .exceptions import ELIAError


@dataclass(frozen=True)
class NavigationGrid:
    origin_x: float
    origin_y: float
    resolution: float
    width: int
    height: int
    traversable: frozenset[tuple[int, int]]

    def center(self, cell: tuple[int, int]) -> tuple[float, float]:
        return (self.origin_x + (cell[0] + 0.5) * self.resolution,
                self.origin_y + (cell[1] + 0.5) * self.resolution)

    def cell_for(self, coordinate: tuple[float, float]) -> tuple[int, int]:
        return (int((coordinate[0] - self.origin_x) // self.resolution),
                int((coordinate[1] - self.origin_y) // self.resolution))

    def nearest_traversable(self, coordinate: tuple[float, float]) -> tuple[int, int] | None:
        if not self.traversable:
            return None
        return min(self.traversable, key=lambda cell: (
            (self.center(cell)[0] - coordinate[0]) ** 2 + (self.center(cell)[1] - coordinate[1]) ** 2,
            cell[1], cell[0],
        ))


def build_navigation_grid(navigable: BaseGeometry, resolution: float, max_cells: int) -> NavigationGrid:
    if resolution <= 0:
        raise ELIAError("ELIA_INVALID_GRID_RESOLUTION", "A positive A* grid resolution is required.")
    if navigable is None or navigable.is_empty:
        return NavigationGrid(0.0, 0.0, resolution, 0, 0, frozenset())
    min_x, min_y, max_x, max_y = navigable.bounds
    width = max(1, ceil((max_x - min_x) / resolution))
    height = max(1, ceil((max_y - min_y) / resolution))
    if width * height > max_cells:
        raise ELIAError("ELIA_GRID_LIMIT_EXCEEDED", "Site exceeds the configured A* grid cell limit.", status_code=422)
    traversable = set()
    for row in range(height):
        for column in range(width):
            x = min_x + (column + 0.5) * resolution
            y = min_y + (row + 0.5) * resolution
            if navigable.covers(Point(x, y)):
                traversable.add((column, row))
    return NavigationGrid(min_x, min_y, resolution, width, height, frozenset(traversable))
