"""
CubiCasa Segmentor Singleton Manager.
Thread-safe lazy-loading of the CubiCasa5K model.
"""

import logging
import threading
from pathlib import Path
from typing import Optional, Union
import numpy as np
from PIL import Image
import torch

from .segmentation_net import CubiCasa5K
from .preprocessor import preprocess_image
from .postprocessor import PostProcessor, SegmentationResult
from ...config import settings

logger = logging.getLogger(__name__)

_segmentor_lock = threading.Lock()
_segmentor_instance: Optional["FloorPlanSegmentor"] = None


class FloorPlanSegmentor:
    """
    FloorPlanSegmentor wraps the CubiCasa5K neural network for room and icon inference.
    """

    def __init__(
        self,
        checkpoint: Union[str, Path],
        device: Optional[str] = None,
        min_room_area: int = 500,
        polygon_simplify_tolerance: float = 2.0,
        min_icon_area: int = 50,
    ):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        checkpoint_path = Path(checkpoint)
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"CubiCasa weights checkpoint not found at: {checkpoint_path}")

        logger.info("Loading CubiCasa5K model from %s on device %s...", checkpoint_path, self.device)
        self.model = CubiCasa5K.from_pretrained(str(checkpoint_path), device=self.device)
        self.postprocessor = PostProcessor(
            min_room_area=min_room_area,
            polygon_simplify_tolerance=polygon_simplify_tolerance,
            min_icon_area=min_icon_area,
        )
        logger.info("CubiCasa5K model loaded successfully.")

    @torch.no_grad()
    def predict(self, image: Union[str, Path, np.ndarray, Image.Image]) -> SegmentationResult:
        """
        Runs inference on a single floor plan image.
        """
        tensor, orig_size = preprocess_image(image, device=self.device)
        output = self.model(tensor)
        return self.postprocessor.process(output, orig_size)


def get_segmentor(checkpoint_path: Optional[str] = None) -> FloorPlanSegmentor:
    """
    Returns the singleton FloorPlanSegmentor instance, initializing it if necessary.
    Thread-safe lazy loader.
    """
    global _segmentor_instance
    if _segmentor_instance is not None:
        return _segmentor_instance

    with _segmentor_lock:
        if _segmentor_instance is None:
            target_path = checkpoint_path or getattr(settings, "cubicasa_weights_path", None)
            if not target_path:
                target_path = "C:/Users/IMAKA/Desktop/CubicasaRoomSegmentation/weights/cubicasa5k.pkl"
            _segmentor_instance = FloorPlanSegmentor(target_path)
        return _segmentor_instance
