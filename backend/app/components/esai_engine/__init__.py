"""
ESAI-Engine Component Package
Stage 1: Complete Backend Foundation (Geometry, Catalog, Standards, Requirements, Validation, and APIs)
Without AI Genetic Algorithm Optimization.
"""

from .service import EsaiEngineService
from .contracts import (
    StructuralInputDTO,
    FloorDTO,
    RoomDTO,
    DoorDTO,
    WindowDTO,
    WallDTO,
    RoomRequirementsDTO,
    FurnitureRequirementItem,
    ProjectPreferencesDTO,
    ValidationResultDTO,
    ValidationMessage,
    RoomType,
    AssetCategory,
    LengthUnit,
)
from .catalog import FurnitureCatalogRepository, CatalogAsset
from .rules import ErgonomicStandardsRepository, ErgonomicRule
from .parser import StructuralInputParser, normalize_room_type
from .normalizer import SpatialNormalizer
from .validators import EsaiInputValidator
from .repositories import EsaiDatabaseRepository
from .geometry import compute_geometry_fingerprint
from .placeholder import run

def get_engine_version():
    return "1.0.0"

__all__ = [
    "EsaiEngineService",
    "StructuralInputDTO",
    "FloorDTO",
    "RoomDTO",
    "DoorDTO",
    "WindowDTO",
    "WallDTO",
    "RoomRequirementsDTO",
    "FurnitureRequirementItem",
    "ProjectPreferencesDTO",
    "ValidationResultDTO",
    "ValidationMessage",
    "RoomType",
    "AssetCategory",
    "LengthUnit",
    "FurnitureCatalogRepository",
    "CatalogAsset",
    "ErgonomicStandardsRepository",
    "ErgonomicRule",
    "StructuralInputParser",
    "normalize_room_type",
    "SpatialNormalizer",
    "EsaiInputValidator",
    "EsaiDatabaseRepository",
    "compute_geometry_fingerprint",
    "run",
    "get_engine_version",
]

