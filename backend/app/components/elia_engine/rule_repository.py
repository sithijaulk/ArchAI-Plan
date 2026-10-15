from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA = Path(__file__).with_name("data")


@lru_cache(maxsize=1)
def _load(name: str) -> dict[str, Any]:
    with (_DATA / name).open(encoding="utf-8") as stream:
        return json.load(stream)


def elia_rules() -> dict[str, Any]:
    return _load("elia_rules.json")


def vehicle_profiles() -> dict[str, Any]:
    return _load("vehicle_profiles.json")


def vegetation_catalog() -> dict[str, Any]:
    return _load("vegetation_catalog.json")


def lighting_rules() -> dict[str, Any]:
    return _load("lighting_rules.json")
