"""
Post-processing for CubiCasa5K model outputs.

The model (hg_furukawa_original) produces a single tensor of shape (B, 51, H, W):
  channels  0–20  : heatmaps (sigmoid-activated)
  channels 21–32  : room segmentation logits  (12 classes)
  channels 33–50  : icon segmentation logits  (18 classes)

This module splits that tensor and converts it into:
  - room segmentation mask  (H×W integer label map)
  - wall mask               (binary H×W)
  - icon segmentation mask  (H×W integer label map)
  - vectorized room polygons (list of shapely Polygons per room class)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from scipy import ndimage
from skimage import measure
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .segmentation_net import ROOM_CLASSES, ICON_CLASSES, OUTPUT_SPLIT

# Index of the "Wall" class in rooms
WALL_CLASS_IDX = ROOM_CLASSES.index("Wall")


# ---------------------------------------------------------------------------
# Output container
# ---------------------------------------------------------------------------

@dataclass
class SegmentationResult:
    """All outputs produced by PostProcessor.process()."""

    # Dense label maps  (H×W numpy int arrays at original image resolution)
    room_mask: np.ndarray           # values in [0, 11]
    icon_mask: np.ndarray           # values in [0, 16]
    wall_mask: np.ndarray           # binary uint8

    # Confidence maps (H×W float32, max softmax score per pixel)
    room_confidence: np.ndarray
    icon_confidence: np.ndarray

    # Vectorized polygons: {room_class_name: [Polygon, ...]}
    room_polygons: Dict[str, List[Polygon]] = field(default_factory=dict)

    # Icon detections: list of (icon_class_name, centroid_y, centroid_x, area)
    icon_detections: List[Tuple[str, float, float, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Post-processor
# ---------------------------------------------------------------------------

class PostProcessor:
    """
    Parameters
    ----------
    min_room_area  : minimum pixel area to keep a connected room component
    polygon_simplify_tolerance : Douglas-Peucker tolerance (in pixels)
    min_icon_area  : minimum pixel area for an icon detection
    """

    def __init__(
        self,
        min_room_area: int = 500,
        polygon_simplify_tolerance: float = 2.0,
        min_icon_area: int = 50,
    ):
        self.min_room_area = min_room_area
        self.polygon_simplify_tolerance = polygon_simplify_tolerance
        self.min_icon_area = min_icon_area

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(
        self,
        output: torch.Tensor,
        orig_size: Tuple[int, int],
    ) -> SegmentationResult:
        """
        Parameters
        ----------
        output    : (1, 51, H, W) or (51, H, W) – raw model output tensor
        orig_size : (orig_H, orig_W) – resize outputs back to this

        Returns
        -------
        SegmentationResult
        """
        output = _ensure_3d(output)   # (51, H, W)

        # Upsample the full tensor to original size, then split
        output = _resize_logits(output, orig_size)           # (51, H, W)
        heatmaps, room_logits, icon_logits = torch.split(
            output, OUTPUT_SPLIT, dim=0
        )
        # heatmaps are already sigmoid-activated by the model; no further processing needed here

        # Softmax → argmax
        room_prob = torch.softmax(room_logits, dim=0).numpy()  # (12, H, W)
        icon_prob = torch.softmax(icon_logits, dim=0).numpy()  # (18, H, W)

        room_mask = room_prob.argmax(axis=0).astype(np.int32)  # (H, W)
        icon_mask = icon_prob.argmax(axis=0).astype(np.int32)  # (H, W)
        room_conf = room_prob.max(axis=0).astype(np.float32)
        icon_conf = icon_prob.max(axis=0).astype(np.float32)

        wall_mask = (room_mask == WALL_CLASS_IDX).astype(np.uint8)

        room_polygons  = self._vectorize_rooms(room_mask)
        icon_detections = self._detect_icons(icon_mask)

        return SegmentationResult(
            room_mask=room_mask,
            icon_mask=icon_mask,
            wall_mask=wall_mask,
            room_confidence=room_conf,
            icon_confidence=icon_conf,
            room_polygons=room_polygons,
            icon_detections=icon_detections,
        )

    # ------------------------------------------------------------------
    # Room polygon vectorization
    # ------------------------------------------------------------------

    def _vectorize_rooms(
        self, room_mask: np.ndarray
    ) -> Dict[str, List[Polygon]]:
        """
        For each non-background, non-wall room class, extract connected
        components and fit simplified Shapely polygons to their contours.
        """
        polygons: Dict[str, List[Polygon]] = {}

        skip_classes = {0, WALL_CLASS_IDX}  # Background + Wall

        for cls_idx, cls_name in enumerate(ROOM_CLASSES):
            if cls_idx in skip_classes:
                continue

            binary = (room_mask == cls_idx).astype(np.uint8)
            if binary.sum() < self.min_room_area:
                continue

            labeled, n_components = ndimage.label(binary)

            class_polys = []
            for comp_id in range(1, n_components + 1):
                comp_mask = (labeled == comp_id).astype(np.uint8)
                if comp_mask.sum() < self.min_room_area:
                    continue

                poly = self._mask_to_polygon(comp_mask)
                if poly is not None:
                    class_polys.append(poly)

            if class_polys:
                polygons[cls_name] = class_polys

        return polygons

    def _mask_to_polygon(self, binary_mask: np.ndarray) -> Polygon | None:
        """Convert a binary mask to a simplified Shapely Polygon."""
        # find_contours returns contours as (row, col) = (y, x)
        contours = measure.find_contours(binary_mask.astype(float), level=0.5)
        if not contours:
            return None

        # Pick the longest contour (outer boundary)
        contour = max(contours, key=len)
        if len(contour) < 4:
            return None

        # skimage returns (row, col) → swap to (x, y) for Shapely
        xy_coords = [(c[1], c[0]) for c in contour]
        try:
            poly = Polygon(xy_coords)
            if not poly.is_valid:
                poly = poly.buffer(0)
            poly = poly.simplify(
                self.polygon_simplify_tolerance,
                preserve_topology=True,
            )
            if poly.is_empty or poly.area < self.min_room_area:
                return None
            return poly
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Icon detection
    # ------------------------------------------------------------------

    def _detect_icons(
        self, icon_mask: np.ndarray
    ) -> List[Tuple[str, float, float, float]]:
        """
        Extract connected components for each icon class and return
        (class_name, centroid_y, centroid_x, area) tuples.
        """
        detections = []
        for cls_idx, cls_name in enumerate(ICON_CLASSES):
            if cls_idx == 0:  # No Icon
                continue

            binary = (icon_mask == cls_idx).astype(np.uint8)
            if binary.sum() < self.min_icon_area:
                continue

            labeled, n = ndimage.label(binary)
            props = measure.regionprops(labeled)
            for prop in props:
                if prop.area >= self.min_icon_area:
                    cy, cx = prop.centroid
                    detections.append((cls_name, cy, cx, float(prop.area)))

        return detections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_3d(t: torch.Tensor) -> torch.Tensor:
    if t.dim() == 4:
        return t.squeeze(0)
    return t


def _resize_logits(
    logits: torch.Tensor, size: Tuple[int, int]
) -> torch.Tensor:
    """Bilinear upsample (C, H, W) → (C, target_H, target_W)."""
    return F.interpolate(
        logits.unsqueeze(0).float(),
        size=size,
        mode="bilinear",
        align_corners=False,
    ).squeeze(0).cpu()
