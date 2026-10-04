from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class ResidualSpace:
    geometry: BaseGeometry
    land_area: float
    house_area: float
    restricted_area: float
    available_area: float
    available_ratio: float


def calculate_residual_space(land: Polygon, house: Polygon, restrictions: Iterable[BaseGeometry] = ()) -> ResidualSpace:
    """Subtract the fixed building and protected areas from the legal site polygon."""
    residual = land.difference(house)
    restricted_union = None
    for restriction in restrictions:
        clipped = restriction.intersection(land).difference(house)
        if not clipped.is_empty:
            restricted_union = clipped if restricted_union is None else restricted_union.union(clipped)
    if restricted_union is not None:
        residual = residual.difference(restricted_union)
    available_area = max(0.0, residual.area)
    return ResidualSpace(
        geometry=residual,
        land_area=land.area,
        house_area=house.area,
        restricted_area=0.0 if restricted_union is None else restricted_union.area,
        available_area=available_area,
        available_ratio=available_area / land.area if land.area else 0.0,
    )
