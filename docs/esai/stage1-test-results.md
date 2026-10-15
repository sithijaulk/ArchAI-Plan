# ESAI Stage 1 Test Execution Results

## Test Suite Summary
- **Test File**: [test_esai_stage1.py](file:///backend/tests/esai/test_esai_stage1.py)
- **Framework**: `pytest 9.1.1` on `Python 3.13.15`
- **Total Test Cases**: 18
- **Passed**: 18
- **Failed**: 0
- **Execution Time**: ~4.4 seconds

## Detailed Test Breakdown

| # | Test Name | Target Module | Result |
| :--- | :--- | :--- | :--- |
| 1 | `test_furniture_catalog_loading` | [catalog.py](file:///backend/app/components/esai_engine/catalog.py) | **PASSED** |
| 2 | `test_catalog_non_existent_item_raises_exception` | [catalog.py](file:///backend/app/components/esai_engine/catalog.py) | **PASSED** |
| 3 | `test_ergonomic_standards_provenance_and_verification` | [rules.py](file:///backend/app/components/esai_engine/rules.py) | **PASSED** |
| 4 | `test_parse_bedroom_structural_geometry` | [parser.py](file:///backend/app/components/esai_engine/parser.py) | **PASSED** |
| 5 | `test_parse_multi_floor_and_room_discovery` | [normalizer.py](file:///backend/app/components/esai_engine/normalizer.py) | **PASSED** |
| 6 | `test_unit_conversion_from_millimeters_to_meters` | [parser.py](file:///backend/app/components/esai_engine/parser.py) | **PASSED** |
| 7 | `test_unit_conversion_helper` | [contracts.py](file:///backend/app/components/esai_engine/contracts.py) | **PASSED** |
| 8 | `test_invalid_self_intersecting_polygon_rejected` | [geometry.py](file:///backend/app/components/esai_engine/geometry.py) | **PASSED** |
| 9 | `test_l_shaped_polygon_area_computation` | [geometry.py](file:///backend/app/components/esai_engine/geometry.py) | **PASSED** |
| 10 | `test_valid_room_requirements_validation` | [validators.py](file:///backend/app/components/esai_engine/validators.py) | **PASSED** |
| 11 | `test_validation_fails_on_unknown_catalog_item` | [validators.py](file:///backend/app/components/esai_engine/validators.py) | **PASSED** |
| 12 | `test_validation_detects_locked_item_blocking_door` | [validators.py](file:///backend/app/components/esai_engine/validators.py) | **PASSED** |
| 13 | `test_esai_database_repository_persistence` | [repositories.py](file:///backend/app/components/esai_engine/repositories.py) | **PASSED** |
| 14 | `test_master_json_immutability_on_requirement_save` | [service.py](file:///backend/app/components/esai_engine/service.py) | **PASSED** |
| 15 | `test_api_run_returns_controlled_501` | [esai.py](file:///backend/app/routers/esai.py) | **PASSED** |
| 16 | `test_api_context_and_floors_discovery` | [esai.py](file:///backend/app/routers/esai.py) | **PASSED** |
| 17 | `test_api_global_catalog_and_standards` | [esai.py](file:///backend/app/routers/esai.py) | **PASSED** |
| 18 | `test_api_saved_configurations_crud` | [esai.py](file:///backend/app/routers/esai.py) | **PASSED** |
