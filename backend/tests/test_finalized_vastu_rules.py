"""
Unit and integration tests for the finalized Vastu Shastra rules:
1. Brahmasthan Exact Center-Point Check (vsai.brahmasthan.exact_center)
2. Dwara Sthana Door Combinations (vsai.dwara_sthana.combination)
3. Main Entrance Direction Analysis (vsai.main_entrance.direction)
4. Room Direction Analysis (vsai.room.direction)
"""

import unittest
from app.services.vastu_engine import (
    evaluate_vastu_shastra,
    load_vastu_rules,
    DWARA_STHANA_COMBINATIONS,
    PadavinyasaGrid,
    BoundingBox,
)


class FinalizedVastuRulesTests(unittest.TestCase):

    def test_rules_loading_and_structure(self):
        """Verifies that the 4 finalized rules are loaded from JSON."""
        rules = load_vastu_rules()
        self.assertEqual(len(rules), 4)
        rule_ids = {r.get("rule_id") for r in rules}
        self.assertEqual(rule_ids, {
            "vsai.brahmasthan.exact_center",
            "vsai.dwara_sthana.combination",
            "vsai.main_entrance.direction",
            "vsai.room.direction",
        })

    def test_brahmasthan_exact_center_unobstructed(self):
        """Pass condition: center point is open and unobstructed."""
        payload = {
            "land_info": {"orientation": "North"},
            "floor_plan": {
                "rooms": [
                    {"id": "r1", "name": "Room 1", "type": "living", "polygon": [[0, 0], [20, 0], [20, 20], [0, 20]]},
                    {"id": "r2", "name": "Room 2", "type": "kitchen", "polygon": [[30, 0], [50, 0], [50, 20], [30, 20]]},
                    {"id": "r3", "name": "Room 3", "type": "bedroom", "polygon": [[0, 30], [20, 30], [20, 50], [0, 50]]},
                    {"id": "r4", "name": "Room 4", "type": "pooja", "polygon": [[30, 30], [50, 30], [50, 50], [30, 50]]},
                ],
                "doors": [],
            },
        }
        res = evaluate_vastu_shastra(payload)
        self.assertEqual(res["brahmasthan"]["status"], "CLEAR")
        self.assertEqual(res["brahmasthan"]["exact_center"], [25.0, 25.0])
        self.assertEqual(len(res["brahmasthan"]["obstructing_objects"]), 0)

        # Confirm good aspect is reported
        brahma_good = [g for g in res["good_aspects"] if g["rule_id"] == "vsai.brahmasthan.exact_center"]
        self.assertEqual(len(brahma_good), 1)

    def test_brahmasthan_exact_center_obstructed_by_room(self):
        """Fail condition: room polygon occupies exact center point (25, 25)."""
        payload = {
            "land_info": {"orientation": "North"},
            "floor_plan": {
                "rooms": [
                    # Room covering (25, 25)
                    {"id": "r1", "name": "Central Hall", "type": "living_room", "polygon": [[10, 10], [40, 10], [40, 40], [10, 40]]},
                    {"id": "r2", "name": "Perimeter Room", "type": "bedroom", "polygon": [[0, 0], [10, 0], [10, 50], [0, 50]]},
                ],
                "doors": [],
            },
        }
        res = evaluate_vastu_shastra(payload)
        self.assertEqual(res["brahmasthan"]["status"], "OBSTRUCTED")
        self.assertIn("Central Hall", res["brahmasthan"]["obstructing_objects"])

        defects = [d for d in res["defects"] if d["rule_id"] == "vsai.brahmasthan.exact_center"]
        self.assertEqual(len(defects), 1)
        self.assertEqual(defects[0]["severity"], "CRITICAL")

    def test_brahmasthan_exact_center_obstructed_by_column(self):
        """Fail condition: structural column occupies exact center point."""
        payload = {
            "land_info": {"orientation": "North"},
            "floor_plan": {
                "rooms": [
                    {"id": "r1", "name": "Room A", "type": "living", "polygon": [[0, 0], [20, 0], [20, 20], [0, 20]]},
                    {"id": "r2", "name": "Room B", "type": "bedroom", "polygon": [[30, 30], [50, 30], [50, 50], [30, 50]]},
                ],
                "structural_elements": [
                    {"id": "c1", "name": "Pillar Core", "type": "column", "polygon": [[24.5, 24.5], [25.5, 24.5], [25.5, 25.5], [24.5, 25.5]]}
                ],
                "doors": [],
            },
        }
        res = evaluate_vastu_shastra(payload)
        self.assertEqual(res["brahmasthan"]["status"], "OBSTRUCTED")
        self.assertIn("Pillar Core", res["brahmasthan"]["obstructing_objects"])

    def test_dwara_sthana_dhruva_empty_doors_condition(self):
        """Dhruva condition: Classify combination as Dhruva ONLY when there are no doors anywhere in the house."""
        payload = {
            "floor_plan": {
                "rooms": [
                    {"id": "r1", "name": "Room 1", "type": "living", "polygon": [[0, 0], [20, 0], [20, 20], [0, 20]]},
                ],
                "doors": [],  # Zero doors
            }
        }
        res = evaluate_vastu_shastra(payload)
        self.assertEqual(res["dwara_sthana"]["house_type"], "Dhruva")
        self.assertEqual(res["dwara_sthana"]["classification"], "VERY_GOOD")
        self.assertEqual(res["dwara_sthana"]["directions"], [])
        self.assertEqual(res["dwara_sthana"]["traditional_result"], "Wealth, grain and prosperity")

    def test_dwara_sthana_all_16_combinations(self):
        """Verifies all 16 cardinal door combinations match specification."""
        self.assertEqual(len(DWARA_STHANA_COMBINATIONS), 16)

        test_cases = [
            ([], "Dhruva", "VERY_GOOD"),
            (["EAST"], "Dhanya", "GOOD"),
            (["SOUTH"], "Jaya", "GOOD"),
            (["EAST", "SOUTH"], "Nanda", "BAD"),
            (["WEST"], "Khara", "BAD"),
            (["EAST", "WEST"], "Kanta", "GOOD"),
            (["SOUTH", "WEST"], "Manorama", "GOOD"),
            (["EAST", "SOUTH", "WEST"], "Sumukha", "GOOD"),
            (["NORTH"], "Durmukha", "BAD"),
            (["EAST", "NORTH"], "Ugra", "BAD"),
            (["NORTH", "SOUTH"], "Ripuda", "BAD"),
            (["EAST", "NORTH", "SOUTH"], "Vittada", "GOOD"),
            (["NORTH", "WEST"], "Kshaya/Nasha", "BAD"),
            (["EAST", "NORTH", "WEST"], "Akranda", "BAD"),
            (["NORTH", "SOUTH", "WEST"], "Vipula", "GOOD"),
            (["EAST", "NORTH", "SOUTH", "WEST"], "Vijaya", "VERY_GOOD"),
        ]

        for dirs, expected_type, expected_class in test_cases:
            doors_payload = [
                {"id": f"d-{d}", "name": f"Door {d}", "cardinal_direction": d}
                for d in dirs
            ]
            payload = {
                "floor_plan": {
                    "rooms": [{"id": "r1", "name": "Room", "type": "living", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}],
                    "doors": doors_payload,
                }
            }
            res = evaluate_vastu_shastra(payload)
            self.assertEqual(res["dwara_sthana"]["house_type"], expected_type)
            self.assertEqual(res["dwara_sthana"]["classification"], expected_class)

    def test_main_entrance_direction_analysis(self):
        """Positive suitable zones (North, North-East, East) vs inauspicious zones."""
        # 1. Auspicious North entrance
        payload_north = {
            "floor_plan": {
                "rooms": [{"id": "r1", "name": "Room", "type": "living", "polygon": [[0, 0], [30, 0], [30, 30], [0, 30]]}],
                "doors": [{"id": "main", "name": "Entrance", "is_main_entrance": True, "position": [15, 30], "cardinal_direction": "NORTH"}],
            }
        }
        res_north = evaluate_vastu_shastra(payload_north)
        self.assertEqual(res_north["main_entrance"]["classification"], "POSITIVE_SUITABLE")

        # 2. Inauspicious South entrance
        payload_south = {
            "floor_plan": {
                "rooms": [{"id": "r1", "name": "Room", "type": "living", "polygon": [[0, 0], [30, 0], [30, 30], [0, 30]]}],
                "doors": [{"id": "main", "name": "Entrance", "is_main_entrance": True, "position": [15, 0], "cardinal_direction": "SOUTH"}],
            }
        }
        res_south = evaluate_vastu_shastra(payload_south)
        self.assertEqual(res_south["main_entrance"]["classification"], "UNSUITABLE")
        entrance_defects = [d for d in res_south["defects"] if d["rule_id"] == "vsai.main_entrance.direction"]
        self.assertEqual(len(entrance_defects), 1)

    def test_room_direction_analysis_primary_vs_alternatives(self):
        """Kitchen primary (SE) vs alternative (NW) vs defect (NE)."""
        site_land = {"boundary_points": [[0, 0], [50, 0], [50, 50], [0, 50]], "orientation": "North"}

        # Primary SE
        res_se = evaluate_vastu_shastra({
            "land_info": site_land,
            "floor_plan": {
                "rooms": [{"id": "k1", "name": "Kitchen", "type": "kitchen", "polygon": [[35, 5], [45, 5], [45, 15], [35, 15]]}],
                "doors": [],
            }
        })
        se_good = [g for g in res_se["good_aspects"] if "Kitchen" in g["title"]]
        self.assertTrue(len(se_good) > 0)

        # Alternative NW
        res_nw = evaluate_vastu_shastra({
            "land_info": site_land,
            "floor_plan": {
                "rooms": [{"id": "k1", "name": "Kitchen", "type": "kitchen", "polygon": [[5, 35], [15, 35], [15, 45], [5, 45]]}],
                "doors": [],
            }
        })
        nw_good = [g for g in res_nw["good_aspects"] if "Kitchen" in g["title"] and "Acceptable Alternative" in g["title"]]
        self.assertTrue(len(nw_good) > 0)

        # Defect NE
        res_ne = evaluate_vastu_shastra({
            "land_info": site_land,
            "floor_plan": {
                "rooms": [{"id": "k1", "name": "Kitchen", "type": "kitchen", "polygon": [[35, 35], [45, 35], [45, 45], [35, 45]]}],
                "doors": [],
            }
        })
        ne_defects = [d for d in res_ne["defects"] if "Kitchen" in d["title"]]
        self.assertTrue(len(ne_defects) > 0)

    def test_toilet_in_prohibited_ishanya_sector(self):
        """Toilet in Ishanya (North-East) generates CRITICAL defect."""
        site_land = {"boundary_points": [[0, 0], [50, 0], [50, 50], [0, 50]], "orientation": "North"}
        res = evaluate_vastu_shastra({
            "land_info": site_land,
            "floor_plan": {
                "rooms": [{"id": "t1", "name": "Attached Toilet", "type": "toilet_washroom", "polygon": [[35, 35], [45, 35], [45, 45], [35, 45]]}],
                "doors": [],
            }
        })
        toilet_defects = [d for d in res["defects"] if "Attached Toilet" in d["title"]]
        self.assertEqual(len(toilet_defects), 1)
        self.assertEqual(toilet_defects[0]["severity"], "CRITICAL")


if __name__ == "__main__":
    unittest.main()
