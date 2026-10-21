"""
Catalog Repository & Manager
Loads and manages typed furniture catalog assets from JSON storage.
Validates item properties, dimensions, and supported room types.
"""
import json
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .contracts import (
    AssetCategory,
    Dimensions3D,
    AssetMobility,
    RoomType,
    PlacementMode,
    FinishCategory,
    ServiceType,
)
from .exceptions import CatalogItemNotFoundError


class CatalogAsset(BaseModel):
    id: str
    category: AssetCategory
    subtype: str = ""
    name: str
    description: Optional[str] = None
    supported_room_types: List[str]
    dimensions: Dimensions3D
    physical_footprint_type: str = "rectangle"
    placement_mode: PlacementMode = PlacementMode.FLOOR_STANDING
    default_clearance_rule_id: str
    supported_rotations: List[int] = Field(default_factory=lambda: [0, 90, 180, 270])
    placement_preferences: dict = Field(default_factory=dict)
    wall_attachment_required: bool = False
    ceiling_attachment_required: bool = False
    floor_attachment_required: bool = False
    style_compatibility: List[str] = Field(default_factory=list)
    material_variants: List[str] = Field(default_factory=list)
    color_variants: List[str] = Field(default_factory=list)
    required_services: List[Dict[str, Any]] = Field(default_factory=list)
    optional_services: List[Dict[str, Any]] = Field(default_factory=list)
    functional_relations: List[str] = Field(default_factory=list)
    safety_considerations: Optional[str] = None
    accessibility_tags: List[str] = Field(default_factory=list)
    provenance: str = "Architectural Graphic Standards & Ergonomic Furniture Specifications"
    mobility: AssetMobility = AssetMobility.MOVABLE
    rendering_model_id: str
    enabled: bool = True


class FinishAsset(BaseModel):
    id: str
    category: FinishCategory
    name: str
    material_type: str
    compatible_surfaces: List[str] = Field(default_factory=list)
    style_tags: List[str] = Field(default_factory=list)
    color_variants: List[str] = Field(default_factory=list)
    texture_mapping: Optional[str] = None
    installation_notes: Optional[str] = None
    provenance: str = "Verified Architectural Specification"
    enabled: bool = True


class FurnitureCatalogRepository:
    """Singleton repository for furniture catalog assets, finishes, and service specs."""

    _instance: Optional["FurnitureCatalogRepository"] = None

    def __init__(self, json_path: Optional[str] = None, finishes_path: Optional[str] = None):
        base_dir = os.path.dirname(__file__)
        if json_path is None:
            json_path = os.path.join(base_dir, "data", "furniture_catalog.json")
        if finishes_path is None:
            finishes_path = os.path.join(base_dir, "data", "finishes_catalog.json")
        self.json_path = json_path
        self.finishes_path = finishes_path
        self._items: Dict[str, CatalogAsset] = {}
        self._finishes: Dict[str, FinishAsset] = {}
        self.load()

    @classmethod
    def get_instance(cls, json_path: Optional[str] = None, finishes_path: Optional[str] = None) -> "FurnitureCatalogRepository":
        if cls._instance is None:
            cls._instance = FurnitureCatalogRepository(json_path, finishes_path)
        return cls._instance

    def load(self) -> None:
        if not os.path.exists(self.json_path):
            raise FileNotFoundError(f"Furniture catalog JSON not found at {self.json_path}")

        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._items.clear()
        for raw in data.get("items", []):
            try:
                cat = AssetCategory(raw["category"])
            except ValueError:
                cat = AssetCategory.OTHER

            placement = PlacementMode.FLOOR_STANDING
            if "placement_mode" in raw:
                try:
                    placement = PlacementMode(raw["placement_mode"])
                except ValueError:
                    placement = PlacementMode.FLOOR_STANDING

            asset = CatalogAsset(
                id=raw["id"],
                category=cat,
                subtype=raw.get("subtype", raw["category"]),
                name=raw["name"],
                description=raw.get("description"),
                supported_room_types=raw.get("supported_room_types", []),
                dimensions=Dimensions3D(**raw["dimensions"]),
                physical_footprint_type=raw.get("physical_footprint_type", "rectangle"),
                placement_mode=placement,
                default_clearance_rule_id=raw.get("default_clearance_rule_id", "GENERAL_CIRCULATION"),
                supported_rotations=raw.get("supported_rotations", [0, 90, 180, 270]),
                placement_preferences=raw.get("placement_preferences", {}),
                wall_attachment_required=raw.get("wall_attachment_required", False),
                ceiling_attachment_required=raw.get("ceiling_attachment_required", False),
                floor_attachment_required=raw.get("floor_attachment_required", False),
                style_compatibility=raw.get("style_compatibility", []),
                material_variants=raw.get("material_variants", []),
                color_variants=raw.get("color_variants", []),
                required_services=raw.get("required_services", []),
                optional_services=raw.get("optional_services", []),
                functional_relations=raw.get("functional_relations", []),
                safety_considerations=raw.get("safety_considerations"),
                accessibility_tags=raw.get("accessibility_tags", []),
                provenance=raw.get("provenance", "Architectural Graphic Standards & Ergonomic Furniture Specifications"),
                mobility=AssetMobility(raw.get("mobility", "movable")),
                rendering_model_id=raw.get("rendering_model_id", f"model_{raw['id']}"),
                enabled=raw.get("enabled", True),
            )
            self._items[asset.id] = asset

        # Load finishes if file exists
        self._finishes.clear()
        if os.path.exists(self.finishes_path):
            with open(self.finishes_path, "r", encoding="utf-8") as f:
                fdata = json.load(f)
            for fraw in fdata.get("finishes", []):
                try:
                    fcat = FinishCategory(fraw["category"])
                except ValueError:
                    fcat = FinishCategory.WALL_FINISH
                finish = FinishAsset(
                    id=fraw["id"],
                    category=fcat,
                    name=fraw["name"],
                    material_type=fraw.get("material_type", "standard"),
                    compatible_surfaces=fraw.get("compatible_surfaces", []),
                    style_tags=fraw.get("style_tags", []),
                    color_variants=fraw.get("color_variants", []),
                    texture_mapping=fraw.get("texture_mapping"),
                    installation_notes=fraw.get("installation_notes"),
                    provenance=fraw.get("provenance", "Verified Architectural Specification"),
                    enabled=fraw.get("enabled", True),
                )
                self._finishes[finish.id] = finish

    def get_all(self, enabled_only: bool = True) -> List[CatalogAsset]:
        items = list(self._items.values())
        if enabled_only:
            return [it for it in items if it.enabled]
        return items

    def find_by_id(self, item_id: str) -> Optional[CatalogAsset]:
        return self._items.get(item_id)

    def get_by_id(self, item_id: str) -> CatalogAsset:
        if item_id not in self._items:
            raise CatalogItemNotFoundError(item_id)
        return self._items[item_id]

    def get_by_category(self, category: Any) -> List[CatalogAsset]:
        cat_val = category.value if isinstance(category, AssetCategory) else str(category).lower().strip()
        return [it for it in self._items.values() if it.category.value == cat_val and it.enabled]

    def get_by_subtype(self, subtype: str) -> List[CatalogAsset]:
        sub_val = subtype.lower().strip()
        return [it for it in self._items.values() if it.subtype.lower() == sub_val and it.enabled]

    def get_by_room_type(self, room_type: str) -> List[CatalogAsset]:
        rt_val = room_type.lower().strip()
        return [
            it for it in self._items.values()
            if (rt_val in [r.lower() for r in it.supported_room_types] or "all" in it.supported_room_types) and it.enabled
        ]

    def get_by_style(self, style: str) -> List[CatalogAsset]:
        return [
            it for it in self._items.values()
            if (style in it.style_compatibility or "all" in it.style_compatibility) and it.enabled
        ]

    def get_all_categories(self) -> List[str]:
        return sorted(list({it.category.value for it in self._items.values() if it.enabled}))

    def get_all_finishes(
        self,
        category: Optional[FinishCategory] = None,
        style: Optional[str] = None,
    ) -> List[FinishAsset]:
        finishes = list(self._finishes.values())
        if category is not None:
            finishes = [f for f in finishes if f.category == category]
        if style:
            finishes = [f for f in finishes if style in f.style_tags or "all" in f.style_tags]
        return [f for f in finishes if f.enabled]

    def get_finish_by_id(self, finish_id: str) -> Optional[FinishAsset]:
        return self._finishes.get(finish_id)

