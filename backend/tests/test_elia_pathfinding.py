from shapely.geometry import Polygon, box

from app.components.elia_engine.grid import build_navigation_grid
from app.components.elia_engine.pathfinding import astar_path
from app.components.elia_engine.vehicle_access import validate_vehicle_route


def test_astar_finds_path_around_building_obstacle():
    navigable = box(0, 0, 20, 12).difference(box(8, 2, 12, 10))
    grid = build_navigation_grid(navigable, 1, 1000)
    result = astar_path(grid, (2, 6), (18, 6))
    assert result["found"]
    assert result["explored_nodes"] > 0
    assert all(navigable.covers(__import__("shapely").geometry.Point(point)) for point in result["coordinates"])


def test_astar_reports_disconnected_grid():
    navigable = box(0, 0, 4, 4).union(box(8, 0, 12, 4))
    grid = build_navigation_grid(navigable, 1, 1000)
    result = astar_path(grid, (1, 1), (11, 1))
    assert not result["found"]


def test_turning_check_passes_straight_route_and_rejects_tight_curve():
    vehicle = {"minimum_turning_radius_m": 5.0, "width_m": 1.8}
    assert validate_vehicle_route([(0, 0), (4, 0), (8, 0)], vehicle, 3.0, 0.25)["valid"]
    assert not validate_vehicle_route([(0, 0), (1, 0), (1, 1)], vehicle, 3.0, 0.25)["turning_valid"]


def test_turning_check_rejects_collinear_reversal():
    vehicle = {"minimum_turning_radius_m": 1.0, "width_m": 1.8}

    result = validate_vehicle_route([(0, 0), (4, 0), (1, 0)], vehicle, 3.0, 0.25)

    assert not result["turning_valid"]
    assert result["observed_minimum_radius_m"] == 0.0


def test_empty_navigation_geometry_returns_no_route_without_exception():
    grid = build_navigation_grid(Polygon(), 1, 1000)

    result = astar_path(grid, (0, 0), (1, 1))

    assert not result["found"]
