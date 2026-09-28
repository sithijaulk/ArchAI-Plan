from copy import deepcopy
from typing import Any, Mapping


VALID_COMPONENTS = ("gab_gen", "vsai_rectifier", "esai_engine", "elia_engine")

DEFAULT_MASTER_JSON: dict[str, Any] = {
    "project_id": "",
    "project_name": "",
    "land_info": {},
    "buildable_footprint": {},
    "floor_plan": {},
    "structural_rectification": {},
    "interior_layout": {},
    "exterior_landscape": {},
    "processing": {
        component: {"status": "pending"} for component in VALID_COMPONENTS
    },
}


def new_master_json(project_id: str, project_name: str) -> dict[str, Any]:
    document = deepcopy(DEFAULT_MASTER_JSON)
    document["project_id"] = project_id
    document["project_name"] = project_name
    return document


def _merge_dicts(current: dict[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(current.get(key), dict):
            _merge_dicts(current[key], value)
        else:
            current[key] = deepcopy(value)
    return current


def merge_master_json(current: Mapping[str, Any] | None, updates: Mapping[str, Any]) -> dict[str, Any]:
    document = deepcopy(DEFAULT_MASTER_JSON)
    if current:
        _merge_dicts(document, current)
    _merge_dicts(document, updates)
    return document