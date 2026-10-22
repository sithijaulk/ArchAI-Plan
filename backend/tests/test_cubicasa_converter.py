import numpy as np
from shapely.geometry import Polygon


from app.ml.cubicasa.postprocessor import SegmentationResult
from app.services.cubicasa_to_master_json import (
    snap_polygon_to_orthogonal,
    format_dimension_text,
    convert_cubicasa_to_master_json,
)


def test_format_dimension_text():
    assert format_dimension_text(14.0, 12.0) == "14'0\" \u00d7 12'0\""
    assert format_dimension_text(5.5, 8.25) == "5'6\" \u00d7 8'3\""


def test_snap_polygon_to_orthogonal():
    # Slightly slanted rectangle
    poly = Polygon([[0, 0], [100, 1], [101, 100], [1, 99], [0, 0]])
    snapped = snap_polygon_to_orthogonal(poly)
    assert snapped.is_valid
    assert snapped.area > 0


def test_convert_cubicasa_to_master_json():
    # Synthetic SegmentationResult
    room_poly1 = Polygon([[10, 10], [200, 10], [200, 150], [10, 150], [10, 10]])
    room_poly2 = Polygon([[200, 10], [400, 10], [400, 150], [200, 150], [200, 10]])

    result = SegmentationResult(
        room_mask=np.zeros((300, 500), dtype=np.int32),
        icon_mask=np.zeros((300, 500), dtype=np.int32),
        wall_mask=np.zeros((300, 500), dtype=np.uint8),
        room_confidence=np.ones((300, 500), dtype=np.float32) * 0.9,
        icon_confidence=np.ones((300, 500), dtype=np.float32) * 0.9,
        room_polygons={
            "Living Room": [room_poly1],
            "Bedroom": [room_poly2],
        },
        icon_detections=[
            ("Door", 150.0, 100.0, 120.0),
            ("Window", 10.0, 100.0, 150.0),
        ],
    )

    master = convert_cubicasa_to_master_json(
        result=result,
        image_width_px=500,
        image_height_px=300,
        target_width_ft=42.0,
        project_id="test-proj-01",
    )

    assert master["project_id"] == "test-proj-01"
    assert master["units"] == "ft"
    rooms = master["floor_plan"]["rooms"]
    assert len(rooms) == 2
    types = [r["type"] for r in rooms]
    assert "living" in types
    assert "bedroom" in types
    assert len(master["floor_plan"]["doors"]) == 1
    assert len(master["floor_plan"]["windows"]) == 1
    assert master["floor_plan"]["doors"][0]["is_main_entrance"] is True
