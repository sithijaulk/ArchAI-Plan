"""
<<<<<<< HEAD
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
from .parser import StructuralInputParser
from .normalizer import SpatialNormalizer
from .validators import EsaiInputValidator
from .repositories import EsaiDatabaseRepository
from .placeholder import run

__all__ = [
    "EsaiEngineService",
    "StructuralInputDTO",
    "FloorDTO",
    "RoomDTO",
    "DoorDTO",
    "WindowDTO",
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
    "SpatialNormalizer",
    "EsaiInputValidator",
    "EsaiDatabaseRepository",
    "run",
]
=======
ESAI-Engine (Ergonomic Spatial Intelligence AI) - Stage 1
"""

def get_engine_version():
    return "1.0.0"
>>>>>>> 9bad7e69e2c866a8ea4d6b80b58f75bdfe121d9d
