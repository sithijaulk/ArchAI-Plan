"""
ESAI Integration & Unit Test Fixtures
Deterministic test fixtures representing varied spatial layouts:
- Single floor rectangular bedroom
- Multi-floor project
- Living room, kitchen, bathroom
- Irregular/L-shaped room
- Invalid geometry cases & unit conversion cases
Explicitly marked as ESAI integration-test fixtures.
"""

# 1. Single Floor Standard Bedroom (Meters)
BEDROOM_PROJECT_FIXTURE = {
    "project_id": "test_proj_bedroom_01",
    "project_name": "Modern Suburban Villa - Master Bed",
    "unit": "m",
    "floor_plan": {
        "floors": [
            {
                "floor_id": "floor_gf",
                "floor_name": "Ground Floor",
                "elevation": 0.0,
                "rooms": [
                    {
                        "room_id": "RM_BED_01",
                        "name": "Master Bedroom",
                        "room_type": "master_bedroom",
                        "ceiling_height": 2.8,
                        "polygon": [
                            [0.0, 0.0],
                            [5.0, 0.0],
                            [5.0, 4.0],
                            [0.0, 4.0]
                        ],
                        "doors": [
                            {
                                "id": "DR_BED_01",
                                "start": [0.0, 0.5],
                                "end": [0.0, 1.4],
                                "leaf_width": 0.9,
                                "hinge": "left",
                                "opening_direction": "inward",
                                "swing_angle": 90.0,
                                "protected_depth": 0.9
                            }
                        ],
                        "windows": [
                            {
                                "id": "WIN_BED_01",
                                "start": [2.0, 4.0],
                                "end": [3.5, 4.0],
                                "length": 1.5,
                                "sill_height": 0.9,
                                "height": 1.2,
                                "opening_type": "sliding"
                            }
                        ],
                        "fixed_obstructions": []
                    }
                ]
            }
        ]
    },
    "processing": {
        "gab_gen": {"status": "completed"},
        "vsai_rectifier": {"status": "completed"},
        "esai_engine": {"status": "pending"},
        "elia_engine": {"status": "pending"}
    }
}

# 2. Multi-Floor Project with Living, Kitchen, Bath
MULTI_FLOOR_PROJECT_FIXTURE = {
    "project_id": "test_proj_multi_02",
    "project_name": "Two-Story Residence",
    "unit": "m",
    "floor_plan": {
        "floors": [
            {
                "floor_id": "fl_0",
                "floor_name": "Ground Floor",
                "elevation": 0.0,
                "rooms": [
                    {
                        "room_id": "RM_LIVING_01",
                        "name": "Formal Living Room",
                        "room_type": "living_room",
                        "polygon": [[0.0, 0.0], [6.0, 0.0], [6.0, 5.0], [0.0, 5.0]],
                        "doors": [{"id": "D_LIV", "start": [0.0, 1.0], "end": [0.0, 2.0], "leaf_width": 1.0}],
                        "windows": [{"id": "W_LIV", "start": [2.0, 5.0], "end": [4.0, 5.0], "length": 2.0}]
                    },
                    {
                        "room_id": "RM_KITCHEN_01",
                        "name": "Modular Kitchen",
                        "room_type": "kitchen",
                        "polygon": [[6.0, 0.0], [10.0, 0.0], [10.0, 4.0], [6.0, 4.0]],
                        "doors": [{"id": "D_KIT", "start": [6.0, 1.0], "end": [6.0, 1.9], "leaf_width": 0.9}],
                        "windows": [{"id": "W_KIT", "start": [8.0, 4.0], "end": [9.5, 4.0], "length": 1.5}]
                    }
                ]
            },
            {
                "floor_id": "fl_1",
                "floor_name": "First Floor",
                "elevation": 3.2,
                "rooms": [
                    {
                        "room_id": "RM_BATH_01",
                        "name": "Attached Bathroom",
                        "room_type": "bathroom",
                        "polygon": [[0.0, 0.0], [2.5, 0.0], [2.5, 2.5], [0.0, 2.5]],
                        "doors": [{"id": "D_BATH", "start": [0.0, 0.5], "end": [0.0, 1.3], "leaf_width": 0.8}],
                        "windows": [{"id": "W_BATH", "start": [1.0, 2.5], "end": [1.6, 2.5], "length": 0.6}]
                    }
                ]
            }
        ]
    },
    "processing": {
        "gab_gen": {"status": "completed"},
        "vsai_rectifier": {"status": "pending"},
        "esai_engine": {"status": "pending"},
        "elia_engine": {"status": "pending"}
    }
}

# 3. L-Shaped Room Fixture
L_SHAPED_ROOM_FIXTURE = {
    "project_id": "test_proj_l_shape",
    "project_name": "L-Shaped Studio",
    "unit": "m",
    "floor_plan": {
        "floors": [
            {
                "floor_id": "fl_0",
                "rooms": [
                    {
                        "room_id": "RM_L_01",
                        "name": "L-Shaped Study / Studio",
                        "room_type": "study",
                        "polygon": [
                            [0.0, 0.0],
                            [6.0, 0.0],
                            [6.0, 3.0],
                            [3.0, 3.0],
                            [3.0, 6.0],
                            [0.0, 6.0]
                        ],
                        "doors": [{"id": "D_L", "start": [0.0, 1.0], "end": [0.0, 1.9], "leaf_width": 0.9}],
                        "windows": [{"id": "W_L", "start": [4.0, 0.0], "end": [5.5, 0.0], "length": 1.5}]
                    }
                ]
            }
        ]
    }
}

# 4. Unit Conversion Test Fixture (Millimeters)
MILLIMETERS_PROJECT_FIXTURE = {
    "project_id": "test_proj_mm",
    "project_name": "Millimeter Scaled Room",
    "unit": "mm",
    "floor_plan": {
        "floors": [
            {
                "floor_id": "fl_0",
                "rooms": [
                    {
                        "room_id": "RM_MM_01",
                        "name": "Room in MM",
                        "room_type": "bedroom",
                        "polygon": [
                            [0.0, 0.0],
                            [4000.0, 0.0],
                            [4000.0, 3000.0],
                            [0.0, 3000.0]
                        ],
                        "doors": [{"id": "D_MM", "start": [0.0, 500.0], "end": [0.0, 1400.0], "leaf_width": 900.0}]
                    }
                ]
            }
        ]
    }
}

# 5. Invalid Polygons Fixtures
INVALID_SELF_INTERSECTING_FIXTURE = {
    "project_id": "test_invalid_self_intersect",
    "project_name": "Self-Intersecting Bow-tie Room",
    "unit": "m",
    "floor_plan": {
        "floors": [
            {
                "floor_id": "fl_0",
                "rooms": [
                    {
                        "room_id": "RM_BOWTIE",
                        "name": "Self Intersecting",
                        "room_type": "bedroom",
                        "polygon": [
                            [0.0, 0.0],
                            [4.0, 4.0],
                            [4.0, 0.0],
                            [0.0, 4.0]
                        ]
                    }
                ]
            }
        ]
    }
}
