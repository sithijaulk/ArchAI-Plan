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

    elif r_type == "hip":
        # Hip roof: slopes down on all 4 sides towards eaves
        slice_along_x = width >= height
        if slice_along_x:
            mid_y = (min_y + max_y) / 2.0
            hip_inset = min(width * 0.25, height * 0.4)
            half_span = height / 2.0
            max_h = round(half_span * math.tan(pitch_rad), 3)
            r1 = Point2D(x=round(min_x + hip_inset, 3), y=round(mid_y, 3))
            r2 = Point2D(x=round(max_x - hip_inset, 3), y=round(mid_y, 3))
            ridge_points = [r1, r2]

            # 4 distinct sloped planes: West Hip (triangle), East Hip (triangle), South Pitch (trapezoid), North Pitch (trapezoid)
            # Plane 1: West Hip Triangle
            p_west = [Point2D(x=round(min_x, 3), y=round(min_y, 3)), Point2D(x=round(min_x, 3), y=round(max_y, 3)), r1]
            planes.append(RoofPlane(plane_id="HIP_WEST", polygon=p_west, pitch_deg=roof_pref.pitch_angle_deg, slope_azimuth=270.0, height_offset_m=max_h))

            # Plane 2: East Hip Triangle
            p_east = [Point2D(x=round(max_x, 3), y=round(max_y, 3)), Point2D(x=round(max_x, 3), y=round(min_y, 3)), r2]
            planes.append(RoofPlane(plane_id="HIP_EAST", polygon=p_east, pitch_deg=roof_pref.pitch_angle_deg, slope_azimuth=90.0, height_offset_m=max_h))

            # Plane 3: South Trapezoid
            p_south = [Point2D(x=round(min_x, 3), y=round(min_y, 3)), r1, r2, Point2D(x=round(max_x, 3), y=round(min_y, 3))]
            planes.append(RoofPlane(plane_id="HIP_SOUTH", polygon=p_south, pitch_deg=roof_pref.pitch_angle_deg, slope_azimuth=180.0, height_offset_m=max_h))

            # Plane 4: North Trapezoid
            p_north = [r1, Point2D(x=round(min_x, 3), y=round(max_y, 3)), Point2D(x=round(max_x, 3), y=round(max_y, 3)), r2]
            planes.append(RoofPlane(plane_id="HIP_NORTH", polygon=p_north, pitch_deg=roof_pref.pitch_angle_deg, slope_azimuth=0.0, height_offset_m=max_h))
        else:
            mid_x = (min_x + max_x) / 2.0
            hip_inset = min(height * 0.25, width * 0.4)
            half_span = width / 2.0
            max_h = round(half_span * math.tan(pitch_rad), 3)
            r1 = Point2D(x=round(mid_x, 3), y=round(min_y + hip_inset, 3))
            r2 = Point2D(x=round(mid_x, 3), y=round(max_y - hip_inset, 3))
            ridge_points = [r1, r2]

            # Plane 1: South Hip Triangle
            p_south = [Point2D(x=round(min_x, 3), y=round(min_y, 3)), Point2D(x=round(max_x, 3), y=round(min_y, 3)), r1]
            planes.append(RoofPlane(plane_id="HIP_SOUTH", polygon=p_south, pitch_deg=roof_pref.pitch_angle_deg, slope_azimuth=180.0, height_offset_m=max_h))

            # Plane 2: North Hip Triangle
            p_north = [Point2D(x=round(max_x, 3), y=round(max_y, 3)), Point2D(x=round(min_x, 3), y=round(max_y, 3)), r2]
            planes.append(RoofPlane(plane_id="HIP_NORTH", polygon=p_north, pitch_deg=roof_pref.pitch_angle_deg, slope_azimuth=0.0, height_offset_m=max_h))

            # Plane 3: West Trapezoid
            p_west = [Point2D(x=round(min_x, 3), y=round(min_y, 3)), r1, r2, Point2D(x=round(min_x, 3), y=round(max_y, 3))]
            planes.append(RoofPlane(plane_id="HIP_WEST", polygon=p_west, pitch_deg=roof_pref.pitch_angle_deg, slope_azimuth=270.0, height_offset_m=max_h))

            # Plane 4: East Trapezoid
            p_east = [r1, Point2D(x=round(max_x, 3), y=round(min_y, 3)), Point2D(x=round(max_x, 3), y=round(max_y, 3)), r2]
            planes.append(RoofPlane(plane_id="HIP_EAST", polygon=p_east, pitch_deg=roof_pref.pitch_angle_deg, slope_azimuth=90.0, height_offset_m=max_h))

    return GeneratedRoofGeometry(
        roof_type=r_type,
        ridge_points=ridge_points,
        eave_polygon=eave_coords,
        planes=planes,
        max_height_m=max(0.2, round(max_h, 3)),
        drainage=roof_pref.drainage_preference,
        provenance="calculated_geometry"
    )


def validate_roof_geometry(
    roof_geom: GeneratedRoofGeometry,
    building_footprint_poly: Polygon
) -> Dict[str, Any]:
    """
    Validates physical roof geometric feasibility:
    1. Eave boundary containment (eaves must cover or enclose building footprint)
    2. Finite coordinates and positive height
    3. Non-empty planes
    4. Safe slope bounds for roof type
    """
    violations: List[str] = []
    warnings: List[str] = []

    if not roof_geom.eave_polygon or len(roof_geom.eave_polygon) < 3:
        violations.append("Roof eave boundary is degenerate or missing vertices.")
        return {"valid": False, "violations": violations, "warnings": warnings}

    pts = [(p.x, p.y) for p in roof_geom.eave_polygon]
    eave_poly = Polygon(pts)
    if not eave_poly.is_valid:
        violations.append("Roof eave polygon has self-intersecting or invalid topology.")

    if building_footprint_poly and building_footprint_poly.is_valid:
        # Building footprint must be inside eave boundary with small tolerance
        if not eave_poly.buffer(0.05).contains(building_footprint_poly):
            warnings.append("Roof eave does not fully cover the entire building footprint.")

    if roof_geom.max_height_m <= 0.0:
        violations.append(f"Roof maximum height ({roof_geom.max_height_m}m) must be positive.")

    if not roof_geom.planes:
        violations.append("Roof defines no sloped or slab planes.")

    r_type = roof_geom.roof_type
    if r_type in ("gable", "hip") and roof_geom.max_height_m < 0.5:
        warnings.append(f"Pitched {r_type} roof has very shallow height ({roof_geom.max_height_m:.2f}m).")

    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "warnings": warnings,
        "roof_type": r_type,
        "plane_count": len(roof_geom.planes),
        "max_height_m": roof_geom.max_height_m
    }

