from __future__ import annotations

from math import cos, radians, sin, tan
from typing import Any, Mapping, Sequence

from shapely import affinity
from shapely.geometry import Polygon

from .rule_repository import elia_rules


def analyze_shadows(footprint: Polygon, height_m: float | None, solar_samples: Sequence[Mapping[str, Any]],
                    north_angle_degrees: float | None = None) -> list[dict[str, Any]]:
    """Project approximate ground shadows analytically; this is not ray tracing."""
    results = []
    minimum_elevation = float(elia_rules()["solar"]["minimum_elevation_degrees"])
    for sample in solar_samples:
        azimuth = float(sample["solar_azimuth_degrees"])
        elevation = float(sample["solar_elevation_degrees"])
        item: dict[str, Any] = {
            "timestamp": sample["timestamp"],
            "solar_azimuth_degrees": azimuth,
            "solar_elevation_degrees": elevation,
            "method": "analytical_directional_prism_approximation",
        }
        if elevation <= minimum_elevation:
            item.update({"status": "sun_too_low", "shadow_length_m": None, "shadow_vector_m": None, "geometry": None})
        elif height_m is None or height_m <= 0:
            item.update({"status": "building_height_unavailable", "shadow_length_m": None, "shadow_vector_m": None, "geometry": None})
        else:
            length = float(height_m) / tan(radians(elevation))
            local_azimuth = azimuth - float(north_angle_degrees or 0.0)
            dx = -sin(radians(local_azimuth)) * length
            dy = -cos(radians(local_azimuth)) * length
            translated = affinity.translate(footprint, xoff=dx, yoff=dy)
            shadow = footprint.union(translated).convex_hull
            item.update({"status": "estimated", "shadow_length_m": length, "shadow_vector_m": [dx, dy],
                         "geometry": {"type": "Polygon", "coordinates": [list(shadow.exterior.coords)]}})
        results.append(item)
    return results
