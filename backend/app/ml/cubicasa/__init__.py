"""
CubiCasa5K Room Segmentation package.
"""

from .segmentation_net import CubiCasa5K, ROOM_CLASSES, ICON_CLASSES
from .preprocessor import preprocess_image
from .postprocessor import PostProcessor, SegmentationResult
from .segmentor import get_segmentor, FloorPlanSegmentor

__all__ = [
    "CubiCasa5K",
    "ROOM_CLASSES",
    "ICON_CLASSES",
    "preprocess_image",
    "PostProcessor",
    "SegmentationResult",
    "get_segmentor",
    "FloorPlanSegmentor",
]

