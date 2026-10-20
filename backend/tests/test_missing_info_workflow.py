"""
Tests for Missing-Information Collection Workflow in VSAI Rectifier.

Validates:
1. Missing fields detection (orientation, main entrance, missing room types, missing polygons).
2. Conflicting direction detection (e.g. door declared North but placed on South boundary).
3. Valid JSON with no missing fields (Vastu analysis runs immediately without blocking).
4. Successful user confirmation merge and subsequent 4-group Vastu analysis.
"""

import unittest
from copy import deepcopy

from app.services.missing_info_service import (
    detect_missing_and_ambiguous_info,
    merge_confirmed_inputs,
)
from app.services.vsai_validator import validate_master_json
from app.routers.vsai_rectifier import confirm_missing_info_direct


def get_base_valid_plan() -> dict:
    return {
        "project_id": "test-complete-101",
        "project_name": "Harmonious Sanctuary",
        "land_info": {
            "boundary_points": [[0.0, 0.0], [40.0, 0.0], [40.0, 40.0], [0.0, 40.0]],
            "area_sqft": 1600.0,
            "orientation": "NORTH",
            "road_facing": "North",
        },
        "floor_plan": {
            "rooms": [
                {
                    "id": "room-ne",
                    "name": "Pooja Room",
                    "type": "pooja",
                    "polygon": [[26.6, 26.6], [40.0, 26.6], [40.0, 40.0], [26.6, 40.0]],
                },
                {
                    "id": "room-se",
                    "name": "Kitchen",
                    "type": "kitchen",
                    "polygon": [[26.6, 0.0], [40.0, 0.0], [40.0, 13.3], [26.6, 13.3]],
                },
                {
                    "id": "room-sw",
                    "name": "Master Bedroom",
                    "type": "master_bedroom",
                    "polygon": [[0.0, 0.0], [13.3, 0.0], [13.3, 13.3], [0.0, 13.3]],
                },
                {
                    "id": "room-nw",
                    "name": "Living Room",
                    "type": "living",
                    "polygon": [[0.0, 26.6], [13.3, 26.6], [13.3, 40.0], [0.0, 40.0]],
                },
            ],
            "doors": [
                {
                    "id": "door-main",
                    "name": "Main Entrance",
                    "type": "main_entrance",
                    "direction": "NORTH",
                    "location": [20.0, 40.0],
                },
                {
                    "id": "door-back",
                    "name": "Rear Door",
                    "type": "back_door",
                    "direction": "SOUTH",
                    "location": [20.0, 0.0],
                },
            ],
        },
    }


class TestMissingInfoWorkflow(unittest.TestCase):

    def test_1_detects_missing_fields_and_defers_vastu(self):
        """Scenario 1: Detects missing orientation, entrance, room types, and polygons.
        Verifies that Vastu analysis is deferred when essential info is missing."""
        plan = {
            "project_id": "test-missing-1",
            "floor_plan": {
                "rooms": [
                    {
                        "id": "room-1",
                        "name": "Unknown Room 1",
                        "type": "room",  # Generic type needs clarification
                        "polygon": [[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0]],
                    },
                    {
                        "id": "room-2",
                        "name": "Ghost Room",
                        "type": "bedroom",
                        "polygon": [],  # Missing geometry/polygon
                    },
                ],
                "doors": [
                    {
                        "id": "d1",
                        "location": [10.0, 20.0],
                    },
                    {
                        "id": "d2",
                        "location": [20.0, 0.0],
                    },
                ],
            },
            # Missing land_info / orientation
        }

        report = detect_missing_and_ambiguous_info(plan)
        self.assertTrue(report["has_blocking_missing_info"])
        question_ids = [q["id"] for q in report["questions"]]

        # Orientation question should be present and required
        self.assertIn("orientation", question_ids)
        orient_q = next(q for q in report["questions"] if q["id"] == "orientation")
        self.assertTrue(orient_q["is_required"])

        # Main entrance question should be present
        self.assertIn("main_entrance", question_ids)

        # Generic room type question should be present
        self.assertIn("room_type_room-1", question_ids)

        # Missing polygon question should be present
        self.assertIn("room_poly_missing_room-2", question_ids)

        # When running through validator, vastu_analysis must be deferred (None)
        validation = validate_master_json(plan)
        self.assertIsNone(validation.get("vastu_analysis"))
        self.assertIn(validation.get("vastu_readiness", {}).get("status"), ["NOT_READY", "NEEDS_USER_CONFIRMATION"])
        self.assertIn("missing_info_report", validation)

    def test_2_detects_conflicting_door_directions(self):
        """Scenario 2: Door declared as NORTH but placed on the SOUTH boundary wall.
        Verifies that a conflict is detected and the geometric direction is suggested."""
        plan = get_base_valid_plan()
        # Deliberately place a door at Y = 40 (which is North wall in standard Cartesian, but let's test boundary derivation)
        # Note: in _derive_cardinal_side_from_position:
        # dist_north = abs(py - min_y), dist_south = abs(py - max_y)
        # So min_y (0.0) is North side in SVG coordinates, max_y (40.0) is South side.
        # If py=40.0, it's at South wall. If direction is declared as "NORTH", that's a conflict!
        plan["floor_plan"]["doors"][0]["location"] = [20.0, 40.0]
        plan["floor_plan"]["doors"][0]["direction"] = "NORTH"

        report = detect_missing_and_ambiguous_info(plan)
        conflict_questions = [q for q in report["questions"] if q["has_conflict"]]
        self.assertTrue(len(conflict_questions) >= 1)

        door_q = next((q for q in conflict_questions if "door" in q["id"]), None)
        self.assertIsNotNone(door_q)
        self.assertTrue(door_q["has_conflict"])
        self.assertEqual(door_q["suggested_value"], "SOUTH")

    def test_3_valid_json_with_no_missing_fields(self):
        """Scenario 3: Fully specified and coherent Master JSON.
        Verifies that no blocking questions are generated and Vastu analysis runs immediately."""
        plan = get_base_valid_plan()
        # Ensure door direction matches its location in SVG coords:
        # door-main at [20.0, 0.0] (North wall, min_y) with direction NORTH
        plan["floor_plan"]["doors"][0]["location"] = [20.0, 0.0]
        plan["floor_plan"]["doors"][0]["direction"] = "NORTH"
        plan["floor_plan"]["doors"][0]["is_main_entrance"] = True
        plan["floor_plan"]["doors"][1]["location"] = [20.0, 40.0]
        plan["floor_plan"]["doors"][1]["direction"] = "SOUTH"

        report = detect_missing_and_ambiguous_info(plan)
        self.assertFalse(report["has_blocking_missing_info"])
        blocking_questions = [q for q in report["questions"] if q["is_required"]]
        self.assertEqual(len(blocking_questions), 0)

        validation = validate_master_json(plan)
        self.assertTrue(validation["is_valid"])
        self.assertEqual(validation.get("vastu_readiness", {}).get("status"), "READY")
        self.assertIsNotNone(validation.get("vastu_analysis"))
        
        # Verify 4 finalized rule groups are evaluated
        analysis = validation["vastu_analysis"]
        self.assertIn("score", analysis)
        self.assertIn("grade", analysis)
        self.assertIn("dwara_sthana", analysis)
        self.assertIn("brahmasthan", analysis)
        self.assertIn("defects", analysis)
        self.assertIn("good_aspects", analysis)
        self.assertTrue(analysis["total_rules_evaluated"] > 0)

    def test_4_user_confirmation_merges_and_runs_analysis(self):
        """Scenario 4: Missing fields are supplied via user confirmation.
        Verifies non-destructive merge, preservation of source, and successful 4-group Vastu run."""
        initial_plan = {
            "project_id": "test-confirm-workflow",
            "project_name": "Lotus Incomplete",
            "land_info": {
                "boundary_points": [[0.0, 0.0], [40.0, 0.0], [40.0, 40.0], [0.0, 40.0]],
            },
            "floor_plan": {
                "rooms": [
                    {
                        "id": "r-1",
                        "name": "Room 1",
                        "type": "room",  # ambiguous
                        "polygon": [[26.6, 26.6], [40.0, 26.6], [40.0, 40.0], [26.6, 40.0]],
                    },
                    {
                        "id": "r-2",
                        "name": "Kitchen",
                        "type": "kitchen",
                        "polygon": [[26.6, 0.0], [40.0, 0.0], [40.0, 13.3], [26.6, 13.3]],
                    },
                ],
                "doors": [
                    {
                        "id": "d-entry",
                        "location": [20.0, 0.0],
                    }
                ],
            },
        }

        # Initially, blocking info exists
        initial_report = detect_missing_and_ambiguous_info(initial_plan)
        self.assertTrue(initial_report["has_blocking_missing_info"])

        # Prepare user answers
        answers = {
            "orientation": "NORTH",
            "main_entrance": "d-entry",
            "door_direction_d-entry": "NORTH",
            "room_type_r-1": "pooja",
        }

        # Merge inputs non-destructively
        merged_plan = merge_confirmed_inputs(initial_plan, answers)

        # Check audit trail & non-destructive snapshot
        self.assertIn("original_source_snapshot", merged_plan)
        self.assertIn("user_confirmations", merged_plan)
        self.assertEqual(merged_plan["user_confirmations"]["orientation"], "NORTH")
        self.assertEqual(merged_plan["land_info"]["orientation"], "North")

        # Verify door was updated
        doors = merged_plan["floor_plan"]["doors"]
        entry_door = next(d for d in doors if d["id"] == "d-entry")
        self.assertTrue(entry_door.get("is_main_entrance"))
        self.assertEqual(entry_door.get("direction"), "NORTH")

        # Verify room type was updated
        room_1 = next(r for r in merged_plan["floor_plan"]["rooms"] if r["id"] == "r-1")
        self.assertEqual(room_1["type"], "pooja")

        # Now test the endpoint / router handler
        payload = {
            "master_json": initial_plan,
            "confirmed_answers": answers,
        }
        response = confirm_missing_info_direct(payload)

        self.assertTrue(response["is_complete"])
        self.assertIsNotNone(response["vastu_analysis"])
        self.assertGreater(response["vastu_analysis"]["score"], 0)
        self.assertEqual(response["validation"]["vastu_readiness"]["status"], "READY")


if __name__ == "__main__":
    unittest.main()
