import json
import unittest
from copy import deepcopy

from app.services.vsai_validator import validate_master_json


def make_valid_master() -> dict:
    return {
        "project_id": "proj-valid-101",
        "project_name": "Lotus Sanctuary",
        "land_info": {
            "boundary_points": [[0.0, 0.0], [40.0, 0.0], [40.0, 40.0], [0.0, 40.0]],
            "area_sqft": 1600.0,
            "orientation": "North-East",
            "road_facing": "North",
        },
        "floor_plan": {
            "rooms": [
                {
                    "id": "room-living",
                    "name": "Living Room",
                    "type": "living",
                    "polygon": [[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0]],
                },
                {
                    "id": "room-kitchen",
                    "name": "Kitchen",
                    "type": "kitchen",
                    "polygon": [[20.0, 0.0], [40.0, 0.0], [40.0, 20.0], [20.0, 20.0]],
                },
            ],
            "structural_elements": [
                {
                    "id": "col-1",
                    "type": "column",
                    "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
                }
            ],
            "doors": [
                {"id": "door-main", "location": [10.0, 0.0], "wall_id": "wall-front"}
            ],
            "windows": [
                {"id": "win-1", "location": [5.0, 0.0], "wall_id": "wall-front"}
            ],
            "walls": [
                {"id": "wall-front", "coordinates": [[0.0, 0.0], [40.0, 0.0]]}
            ]
        },
        "processing": {
            "gab_gen": {"status": "completed"},
            "vsai_rectifier": {"status": "pending"},
        }
    }


class TestVsaiValidator(unittest.TestCase):

    def test_1_valid_json_with_required_spatial_data(self):
        """Case 1: Fully valid Master JSON with spatial data and doors/windows."""
        payload = make_valid_master()
        result = validate_master_json(payload)
        self.assertEqual(result["status"], "VALID")
        self.assertTrue(result["is_valid"])
        self.assertTrue(result["can_rectify"])
        self.assertEqual(len(result["errors"]), 0)
        self.assertEqual(result["element_counts"]["rooms"], 2)
        self.assertEqual(result["vastu_readiness"]["status"], "READY")
        self.assertTrue(result["vastu_readiness"]["padavinyasa_9x9"]["ready"])
        self.assertTrue(result["vastu_readiness"]["brahmasthan"]["ready"])
        self.assertTrue(result["vastu_readiness"]["entrance_32_pada"]["ready"])
        self.assertTrue(result["vastu_readiness"]["directional_room_placement"]["ready"])

    def test_2_malformed_json_syntax(self):
        """Case 2: Malformed JSON syntax must be handled cleanly without crashing."""
        malformed_bytes = b'{"project_id": "proj-1", "project_name": "Broken", "floor_plan": {'
        result = validate_master_json(malformed_bytes)
        self.assertEqual(result["status"], "INVALID")
        self.assertFalse(result["is_valid"])
        self.assertFalse(result["can_rectify"])
        self.assertTrue(any("Malformed JSON syntax" in err for err in result["errors"]))

    def test_3_empty_json_file(self):
        """Case 3: Empty file or string must be detected with user-friendly error."""
        result = validate_master_json(b"   ")
        self.assertEqual(result["status"], "INVALID")
        self.assertFalse(result["is_valid"])
        self.assertTrue(any("empty" in err.lower() for err in result["errors"]))

    def test_4_missing_required_fields(self):
        """Case 4: Missing top-level fields (project_id, project_name, floor_plan)."""
        payload = {"land_info": {"orientation": "North"}}
        result = validate_master_json(payload)
        self.assertEqual(result["status"], "INVALID")
        self.assertFalse(result["is_valid"])
        self.assertIn("project_id", result["missing_fields"])
        self.assertIn("project_name", result["missing_fields"])
        self.assertIn("floor_plan", result["missing_fields"])

    def test_5_invalid_coordinate_values(self):
        """Case 5: Coordinate points containing strings, booleans, or NaN."""
        payload = make_valid_master()
        # Insert string coordinate
        payload["floor_plan"]["rooms"][0]["polygon"] = [
            [0.0, "ten"], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0]
        ]
        result = validate_master_json(payload)
        self.assertEqual(result["status"], "INVALID")
        self.assertFalse(result["is_valid"])
        self.assertTrue(any("numeric" in err for err in result["errors"]))

    def test_6_malformed_room_polygon(self):
        """Case 6: Polygon with < 3 points, self-intersecting polygon, or zero area."""
        payload = make_valid_master()
        # Fewer than 3 points
        payload["floor_plan"]["rooms"][0]["polygon"] = [[0.0, 0.0], [10.0, 10.0]]
        result = validate_master_json(payload)
        self.assertEqual(result["status"], "INVALID")
        self.assertTrue(any("at least 3 points" in err for err in result["errors"]))

        # Self-intersecting bowtie polygon
        payload2 = make_valid_master()
        payload2["floor_plan"]["rooms"][0]["polygon"] = [
            [0.0, 0.0], [10.0, 10.0], [0.0, 10.0], [10.0, 0.0]
        ]
        result2 = validate_master_json(payload2)
        self.assertEqual(result2["status"], "INVALID")
        self.assertTrue(any("self-intersecting" in err for err in result2["errors"]))

    def test_7_missing_orientation_information(self):
        """Case 7: Missing orientation results in warnings and Vastu-readiness explanation."""
        payload = make_valid_master()
        del payload["land_info"]["orientation"]
        result = validate_master_json(payload)
        self.assertEqual(result["status"], "VALID_WITH_WARNINGS")
        self.assertTrue(result["can_rectify"])
        self.assertIn("land_info.orientation", result["missing_fields"])
        self.assertFalse(result["vastu_readiness"]["padavinyasa_9x9"]["ready"])
        self.assertIn("Missing North orientation", result["vastu_readiness"]["padavinyasa_9x9"]["reason"])
        self.assertEqual(result["vastu_readiness"]["status"], "NOT_READY")

    def test_8_missing_walls_doors_or_windows(self):
        """Case 8: Missing doors/walls produces non-fatal warning with entrance rule marked unready."""
        payload = make_valid_master()
        payload["floor_plan"]["doors"] = []
        payload["floor_plan"]["walls"] = []
        result = validate_master_json(payload)
        self.assertEqual(result["status"], "VALID_WITH_WARNINGS")
        self.assertTrue(result["is_valid"])
        self.assertTrue(result["can_rectify"])
        self.assertFalse(result["vastu_readiness"]["entrance_32_pada"]["ready"])
        self.assertIn("No door elements defined", result["vastu_readiness"]["entrance_32_pada"]["reason"])
        self.assertEqual(result["vastu_readiness"]["status"], "PARTIALLY_READY")

    def test_9_duplicate_element_ids(self):
        """Case 9: Duplicate element IDs across rooms or elements."""
        payload = make_valid_master()
        payload["floor_plan"]["rooms"][1]["id"] = payload["floor_plan"]["rooms"][0]["id"]
        result = validate_master_json(payload)
        self.assertEqual(result["status"], "INVALID")
        self.assertFalse(result["is_valid"])
        self.assertTrue(any("Duplicate element ID" in err for err in result["errors"]))

    def test_10_structurally_valid_but_insufficient_geometry(self):
        """Case 10: Structurally valid JSON with 0 rooms results in INSUFFICIENT_DATA."""
        payload = make_valid_master()
        payload["floor_plan"]["rooms"] = []
        result = validate_master_json(payload)
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertFalse(result["is_valid"])
        self.assertFalse(result["can_rectify"])
        self.assertIn("contains 0 rooms", result["summary"])


if __name__ == "__main__":
    unittest.main()
