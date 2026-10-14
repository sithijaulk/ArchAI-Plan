from __future__ import annotations

from .rule_repository import vegetation_catalog as load_vegetation_catalog


def get_catalogue() -> dict:
    return load_vegetation_catalog()
