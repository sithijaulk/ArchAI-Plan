import json
import unittest
from pathlib import Path

from app.services.master_json import MasterJsonAdapter, load_master_json_config
from app.services.vsai_validator import validate_master_json


class TestMasterJsonAdapter(unittest.TestCase):
    def setUp(self):
        self.config = load_master_json_config()

    def test_canonical_room_type_resolution(self):
        """Tests that various synonyms (English, French, abbreviations) map to canonical room types."""
        self.assertEqual(MasterJsonAdapter.resolve_room_type("cuisine"), "kitchen")
        self.assertEqual(MasterJsonAdapter.resolve_room_type("sejour"), "living_room")
        self.assertEqual(MasterJsonAdapter.resolve_room_type("living"), "living_room")
        self.assertEqual(MasterJsonAdapter.resolve_room_type("wc"), "toilet")
        self.assertEqual(MasterJsonAdapter.resolve_room_type("bathroom"), "toilet")
        self.assertEqual(MasterJsonAdapter.resolve_room_type("chambre"), "bedroom")
        self.assertEqual(MasterJsonAdapter.resolve_room_type("cellier"), "store_room")
        self.assertEqual(MasterJsonAdapter.resolve_room_type("garage"), "garage")
        self.assertEqual(MasterJsonAdapter.resolve_room_type("mandir"), "pooja_room")
        self.assertEqual(MasterJsonAdapter.resolve_room_type("prayer"), "pooja_room")

    def test_direction_resolution(self):
        """Tests direction synonyms map to standard cardinal directions."""
        self.assertEqual(MasterJsonAdapter.resolve_direction("N"), "NORTH")
        self.assertEqual(MasterJsonAdapter.resolve_direction("top"), "NORTH")
        self.assertEqual(MasterJsonAdapter.resolve_direction("North"), "NORTH")
        self.assertEqual(MasterJsonAdapter.resolve_direction("S"), "SOUTH")
        self.assertEqual(MasterJsonAdapter.resolve_direction("bottom"), "SOUTH")
        self.assertEqual(MasterJsonAdapter.resolve_direction("E"), "EAST")
        self.assertEqual(MasterJsonAdapter.resolve_direction("W"), "WEST")

    def test_normalize_alternative_gab_gen_payload(self):
        """Tests that a payload with non-standard field names (e.g., spaces, site.facing, meter units)
        is automatically normalized into a valid Master JSON."""
        raw_gab_gen_data = {
            "id": "GAB-SAMPLE-99",
            "name": "Alternative GAB-Gen Blueprint",
            "site": {
                "facing": "top",
                "area_sqft": 1500
            },
            "units": "m",
            "spaces": [
                {
                    "id": "space-01",
                    "name": "Séjour / Repas",
                    "type": "sejour",
                    "polygon": [[0, 0], [6.0, 0], [6.0, 4.0], [0, 4.0]]
                },
                {
                    "id": "space-02",
                    "name": "Cuisine",
                    "type": "cuisine",
                    "polygon": [[6.0, 0], [10.0, 0], [10.0, 4.0], [6.0, 4.0]]
                }
            ],
            "openings": {
                "doors": [
                    {
                        "id": "door-entry",
                        "direction": "N",
                        "is_main_entrance": True,
                        "position": [3.0, 0]
                    }
                ]
            }
        }

        normalized = MasterJsonAdapter.normalize(raw_gab_gen_data)

        # 1. Project ID & Name
        self.assertEqual(normalized["project_id"], "GAB-SAMPLE-99")
        self.assertEqual(normalized["project_name"], "Alternative GAB-Gen Blueprint")

        # 2. Land info & Orientation
        self.assertEqual(normalized["land_info"]["orientation"], "North")

        # 3. Units & Scaled coordinates (m -> mm: 6.0m -> 6000mm)
        self.assertEqual(normalized["floor_plan"]["units"], "mm")
        rooms = normalized["floor_plan"]["rooms"]
        self.assertEqual(len(rooms), 2)

        # Living room check
        self.assertEqual(rooms[0]["type"], "living_room")
        self.assertEqual(rooms[0]["polygon"][1], [6000.0, 0.0])

        # Kitchen check
        self.assertEqual(rooms[1]["type"], "kitchen")
        self.assertEqual(rooms[1]["polygon"][0], [6000.0, 0.0])

        # Door check
        doors = normalized["floor_plan"]["doors"]
        self.assertEqual(len(doors), 1)
        self.assertEqual(doors[0]["direction"], "NORTH")
        self.assertEqual(doors[0]["position"], [3000.0, 0.0])

        # 4. Feed directly into validate_master_json
        val_result = validate_master_json(raw_gab_gen_data)
        self.assertTrue(val_result["is_valid"])
        self.assertIn(val_result["status"], ("VALID", "VALID_WITH_WARNINGS"))
        self.assertIn("vastu_analysis", val_result)


if __name__ == "__main__":
    unittest.main()
