"""
Catalog Repository & Manager
Loads and manages typed furniture catalog assets from JSON storage.
Validates item properties, dimensions, and supported room types.
"""
import json
import os
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from .contracts import (
    AssetCategory,
    Dimensions3D,
    AssetMobility,
    RoomType
)
from .exceptions import CatalogItemNotFoundError


class CatalogAsset(BaseModel):
    id: str
    category: AssetCategory
    name: str
    supported_room_types: List[str]
    dimensions: Dimensions3D
    physical_footprint_type: str = "rectangle"
    default_clearance_rule_id: str
    supported_rotations: List[int] = Field(default_factory=lambda: [0, 90, 180, 270])
    placement_preferences: dict = Field(default_factory=dict)
    functional_relations: List[str] = Field(default_factory=list)
    mobility: AssetMobility = AssetMobility.MOVABLE
    rendering_model_id: str
    material_variants: List[str] = Field(default_factory=list)
    enabled: bool = True


class FurnitureCatalogRepository:
    """Singleton repository for furniture catalog assets."""

    _instance: Optional["FurnitureCatalogRepository"] = None

    def __init__(self, json_path: Optional[str] = None):
        if json_path is None:
            base_dir = os.path.dirname(__file__)
            json_path = os.path.join(base_dir, "data", "furniture_catalog.json")
        self.json_path = json_path
        self._items: Dict[str, CatalogAsset] = {}
        self.load()

    @classmethod
    def get_instance(cls, json_path: Optional[str] = None) -> "FurnitureCatalogRepository":
        if cls._instance is None:
            cls._instance = FurnitureCatalogRepository(json_path)
        return cls._instance

    def load(self) -> None:
        if not os.path.exists(self.json_path):
            raise FileNotFoundError(f"Furniture catalog JSON not found at {self.json_path}")

        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._items.clear()
        for raw in data.get("items", []):
            asset = CatalogAsset(
                id=raw["id"],
                category=AssetCategory(raw["category"]),
                name=raw["name"],
                supported_room_types=raw.get("supported_room_types", []),
                dimensions=Dimensions3D(**raw["dimensions"]),
                physical_footprint_type=raw.get("physical_footprint_type", "rectangle"),
                default_clearance_rule_id=raw.get("default_clearance_rule_id", "GENERAL_CIRCULATION"),
                supported_rotations=raw.get("supported_rotations", [0, 90, 180, 270]),
                placement_preferences=raw.get("placement_preferences", {}),
                functional_relations=raw.get("functional_relations", []),
                mobility=AssetMobility(raw.get("mobility", "movable")),
                rendering_model_id=raw.get("rendering_model_id", f"model_{raw['id']}"),
                material_variants=raw.get("material_variants", []),
                enabled=raw.get("enabled", True),
            )
            self._items[asset.id] = asset

    def get_all(self, enabled_only: bool = True) -> List[CatalogAsset]:
        items = list(self._items.values())
        if enabled_only:
            return [it for it in items if it.enabled]
        return items

    def get_by_id(self, item_id: str) -> CatalogAsset:
        if item_id not in self._items:
            raise CatalogItemNotFoundError(item_id)
        return self._items[item_id]

    def get_by_category(self, category: AssetCategory) -> List[CatalogAsset]:
        return [it for it in self._items.values() if it.category == category and it.enabled]

    def get_by_room_type(self, room_type: str) -> List[CatalogAsset]:
        return [
            it for it in self._items.values()
            if (room_type in it.supported_room_types or "all" in it.supported_room_types) and it.enabled
        ]
