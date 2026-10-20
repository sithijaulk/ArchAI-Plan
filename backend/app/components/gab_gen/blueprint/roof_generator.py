"""
Roof geometry generator for GAB-Gen.
Generates deterministic 3D/2D roof representations matching user roof preferences:
- flat_slab
- accessible_rooftop
- gable
- hip
- mono_pitch
Calculates ridge vectors, eave polygons with overhang, and sloped roof planes.
"""
import math
from typing import Any, Dict, List, Optional, Tuple
from shapely.geometry import Polygon, box
from ..schemas import Point2D, RoofPreference, GeneratedRoofGeometry, RoofPlane, RoofType


def generate_roof_geometry(
    building_footprint_poly: Polygon,
    roof_pref: Optional[RoofPreference] = None
) -> GeneratedRoofGeometry:
    """
    Constructs vectorized roof geometry with overhang, slope, and ridge definitions.
    Strictly metric coordinates in canonical P0 reference frame.
    """
    if roof_pref is None:
        roof_pref = RoofPreference()

    if not building_footprint_poly or not building_footprint_poly.is_valid or building_footprint_poly.area <= 0:
        return GeneratedRoofGeometry(
            roof_type=roof_pref.roof_type.value if hasattr(roof_pref.roof_type, "value") else str(roof_pref.roof_type),
            ridge_points=[],
            eave_polygon=[],
            planes=[],
            max_height_m=0.0,
            drainage=roof_pref.drainage_preference,
            provenance="default_flat"
        )

    overhang = max(0.0, min(1.5, roof_pref.overhang_m))
    eave_poly = building_footprint_poly.buffer(overhang) if overhang > 0 else building_footprint_poly
    if hasattr(eave_poly, "geoms"):
        eave_poly = max(eave_poly.geoms, key=lambda p: p.area)

    eave_coords = [Point2D(x=round(c[0], 3), y=round(c[1], 3)) for c in list(eave_poly.exterior.coords)[:-1]]

    min_x, min_y, max_x, max_y = eave_poly.bounds
    width = max_x - min_x
    height = max_y - min_y
    pitch_rad = math.radians(roof_pref.pitch_angle_deg)

    r_type = roof_pref.roof_type.value if hasattr(roof_pref.roof_type, "value") else str(roof_pref.roof_type)
    ridge_points: List[Point2D] = []
    planes: List[RoofPlane] = []

    if r_type in ("flat_slab", "accessible_rooftop"):
        # Flat slab or accessible roof terrace
        parapet = roof_pref.parapet_height_m if r_type == "accessible_rooftop" else 0.3
        plane = RoofPlane(
            plane_id="ROOF_SLAB_01",
            polygon=eave_coords,
            pitch_deg=0.0,
            slope_azimuth=0.0,
            height_offset_m=parapet
        )
        planes.append(plane)
        max_h = parapet

    elif r_type == "mono_pitch":
        # Mono-pitch / shed roof sloping down along the shorter axis
        slice_along_x = width >= height
        if slice_along_x:
            max_h = round(height * math.tan(pitch_rad), 3)
            ridge_points = [
                Point2D(x=round(min_x, 3), y=round(max_y, 3)),
                Point2D(x=round(max_x, 3), y=round(max_y, 3))
            ]
        else:
            max_h = round(width * math.tan(pitch_rad), 3)
            ridge_points = [
                Point2D(x=round(max_x, 3), y=round(min_y, 3)),
                Point2D(x=round(max_x, 3), y=round(max_y, 3))
            ]
        plane = RoofPlane(
            plane_id="SHED_PLANE_01",
            polygon=eave_coords,
            pitch_deg=roof_pref.pitch_angle_deg,
            slope_azimuth=180.0 if slice_along_x else 270.0,
            height_offset_m=max_h
        )
        planes.append(plane)

    elif r_type == "gable":
        # Dual pitch gable roof with central ridge
        slice_along_x = width >= height
        if slice_along_x:
            # Ridge runs east-west along X axis at mid-Y
            mid_y = (min_y + max_y) / 2.0
            half_span = height / 2.0
            max_h = round(half_span * math.tan(pitch_rad), 3)
            r1 = Point2D(x=round(min_x, 3), y=round(mid_y, 3))
            r2 = Point2D(x=round(max_x, 3), y=round(mid_y, 3))
            ridge_points = [r1, r2]

            # South Pitch
            box_south = box(min_x - 1, min_y - 1, max_x + 1, mid_y)
            south_geom = eave_poly.intersection(box_south)
            if not south_geom.is_empty:
                s_coords = [Point2D(x=round(c[0], 3), y=round(c[1], 3)) for c in list(south_geom.exterior.coords)[:-1]]
                planes.append(RoofPlane(plane_id="GABLE_SOUTH", polygon=s_coords, pitch_deg=roof_pref.pitch_angle_deg, slope_azimuth=180.0, height_offset_m=max_h))

            # North Pitch
            box_north = box(min_x - 1, mid_y, max_x + 1, max_y + 1)
            north_geom = eave_poly.intersection(box_north)
            if not north_geom.is_empty:
                n_coords = [Point2D(x=round(c[0], 3), y=round(c[1], 3)) for c in list(north_geom.exterior.coords)[:-1]]
                planes.append(RoofPlane(plane_id="GABLE_NORTH", polygon=n_coords, pitch_deg=roof_pref.pitch_angle_deg, slope_azimuth=0.0, height_offset_m=max_h))

        else:
            # Ridge runs north-south along Y axis at mid-X
            mid_x = (min_x + max_x) / 2.0
            half_span = width / 2.0
            max_h = round(half_span * math.tan(pitch_rad), 3)
            r1 = Point2D(x=round(mid_x, 3), y=round(min_y, 3))
            r2 = Point2D(x=round(mid_x, 3), y=round(max_y, 3))
            ridge_points = [r1, r2]

            box_west = box(min_x - 1, min_y - 1, mid_x, max_y + 1)
            w_geom = eave_poly.intersection(box_west)
            if not w_geom.is_empty:
                w_coords = [Point2D(x=round(c[0], 3), y=round(c[1], 3)) for c in list(w_geom.exterior.coords)[:-1]]
                planes.append(RoofPlane(plane_id="GABLE_WEST", polygon=w_coords, pitch_deg=roof_pref.pitch_angle_deg, slope_azimuth=270.0, height_offset_m=max_h))

            box_east = box(mid_x, min_y - 1, max_x + 1, max_y + 1)
            e_geom = eave_poly.intersection(box_east)
            if not e_geom.is_empty:
                e_coords = [Point2D(x=round(c[0], 3), y=round(c[1], 3)) for c in list(e_geom.exterior.coords)[:-1]]
                planes.append(RoofPlane(plane_id="GABLE_EAST", polygon=e_coords, pitch_deg=roof_pref.pitch_angle_deg, slope_azimuth=90.0, height_offset_m=max_h))

    else:
        # Hip roof: slopes down on all 4 sides towards eaves
        slice_along_x = width >= height
        if slice_along_x:
            mid_y = (min_y + max_y) / 2.0
            hip_inset = min(width * 0.2, height * 0.4)
            half_span = height / 2.0
            max_h = round(half_span * math.tan(pitch_rad), 3)
            r1 = Point2D(x=round(min_x + hip_inset, 3), y=round(mid_y, 3))
            r2 = Point2D(x=round(max_x - hip_inset, 3), y=round(mid_y, 3))
            ridge_points = [r1, r2]
        else:
            mid_x = (min_x + max_x) / 2.0
            hip_inset = min(height * 0.2, width * 0.4)
            half_span = width / 2.0
            max_h = round(half_span * math.tan(pitch_rad), 3)
            r1 = Point2D(x=round(mid_x, 3), y=round(min_y + hip_inset, 3))
            r2 = Point2D(x=round(mid_x, 3), y=round(max_y - hip_inset, 3))
            ridge_points = [r1, r2]

        plane = RoofPlane(
            plane_id="HIP_COMPLEX",
            polygon=eave_coords,
            pitch_deg=roof_pref.pitch_angle_deg,
            slope_azimuth=0.0,
            height_offset_m=max_h
        )
        planes.append(plane)

    return GeneratedRoofGeometry(
        roof_type=r_type,
        ridge_points=ridge_points,
        eave_polygon=eave_coords,
        planes=planes,
        max_height_m=max(0.2, round(max_h, 3)),
        drainage=roof_pref.drainage_preference,
        provenance="calculated_geometry"
    )
