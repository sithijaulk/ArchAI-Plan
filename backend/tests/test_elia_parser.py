import pytest

from app.components.elia_engine.exceptions import ELIAError
from app.components.elia_engine.parser import parse_exterior_context


BASE_MASTER = {
    "project_id": "p1",
    "units": "m",
    "land_info": {"boundary_points": [[0, 0], [30, 0], [30, 20], [0, 20]]},
    "house_exterior_polygon": [[10, 5], [20, 5], [20, 15], [10, 15]],
    "interior_layout": {"rooms": [{"id": "R1", "furniture": ["desk"]}]},
}


def test_parses_and_closes_valid_master_polygons():
    context = parse_exterior_context(BASE_MASTER)

    assert context.land.area == 600
    assert context.house.area == 100
    assert context.normalized_rings == ("land_boundary_polygon", "house_exterior_polygon")


def test_converts_feet_to_meters():
    context = parse_exterior_context({**BASE_MASTER, "units": "ft"})

    assert context.land.area == pytest.approx(600 * 0.3048**2)
    assert context.source_units == "ft"


@pytest.mark.parametrize(
    ("document", "code"),
    [
        ({"house_exterior_polygon": BASE_MASTER["house_exterior_polygon"]}, "ELIA_MISSING_LAND_BOUNDARY"),
        ({"land_info": BASE_MASTER["land_info"]}, "ELIA_MISSING_HOUSE_EXTERIOR"),
        ({**BASE_MASTER, "house_exterior_polygon": [[0, 0], [4, 4], [0, 4], [4, 0]]}, "ELIA_INVALID_POLYGON"),
    ],
)
def test_rejects_missing_or_invalid_geometry(document, code):
    with pytest.raises(ELIAError) as error:
        parse_exterior_context(document)

    assert error.value.code == code


def test_rejects_unknown_units_and_house_outside_land():
    with pytest.raises(ELIAError, match="Unsupported"):
        parse_exterior_context({**BASE_MASTER, "units": "pixels"})
    with pytest.raises(ELIAError) as error:
        parse_exterior_context({**BASE_MASTER, "house_exterior_polygon": [[40, 40], [42, 40], [42, 42], [40, 42]]})
    assert error.value.code == "ELIA_HOUSE_OUTSIDE_LAND"
