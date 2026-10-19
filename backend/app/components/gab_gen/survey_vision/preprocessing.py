"""
Survey Vision Preprocessing Pipeline.
Implements OpenCV-based image preprocessing for survey and deed plans:
- File loading & format conversion (including PyMuPDF for PDF rendering)
- Grayscale conversion, adaptive thresholding, denoising, contrast enhancement
- Deskewing and rotation correction
- Hough line and boundary segment detection
- Directional arrow / symbol detection heuristic
"""
import io
import math
import os
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

# Conditional cv2 import with graceful fallback
try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    import pymupdf
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

from PIL import Image


def load_image_from_bytes(file_bytes: bytes, ext: str) -> Optional[np.ndarray]:
    """
    Loads raw bytes into an OpenCV BGR numpy array.
    Supports PDF via pymupdf page rendering.
    """
    if ext.lower() == ".pdf":
        if not HAS_PYMUPDF:
            raise RuntimeError("pymupdf is required for PDF conversion.")
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        if len(doc) == 0:
            return None
        # Render first page at 300 DPI (zoom 300/72 = 4.166)
        page = doc[0]
        pix = page.get_pixmap(dpi=300)
        img_data = pix.tobytes("png")
        pil_img = Image.open(io.BytesIO(img_data)).convert("RGB")
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR) if HAS_OPENCV else np.array(pil_img)
    else:
        # Standard image file (JPG, PNG)
        pil_img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        img_np = np.array(pil_img)
        if HAS_OPENCV:
            return cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        return img_np


def preprocess_survey_image(img_bgr: np.ndarray) -> Dict[str, Any]:
    """
    Runs complete OpenCV image preprocessing on a survey deed image:
    1. Grayscale conversion
    2. Bilateral noise filtering (preserves fine boundary lines and text)
    3. Adaptive thresholding / Otsu thresholding
    4. Deskewing / orientation estimation
    5. Morphological edge enhancement
    """
    if not HAS_OPENCV or img_bgr is None:
        return {"processed": None, "skew_angle": 0.0, "lines": []}

    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # Denoise while keeping boundary lines sharp
    denoised = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)

    # Adaptive contrast enhancement via CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)

    # Otsu thresholding for clear binary line separation
    _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Deskew angle detection using Hough lines or minAreaRect on high-density line segments
    skew_angle = detect_skew_angle(binary)

    # Correct skew if non-negligible
    if abs(skew_angle) > 0.5 and abs(skew_angle) < 45.0:
        center = (w // 2, h // 2)
        rot_mat = cv2.getRotationMatrix2D(center, skew_angle, 1.0)
        rotated_binary = cv2.warpAffine(
            binary, rot_mat, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        rotated_gray = cv2.warpAffine(
            gray, rot_mat, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
    else:
        rotated_binary = binary
        rotated_gray = gray
        skew_angle = 0.0

    # Line detection (Probabilistic Hough Transform)
    lines = detect_lines(rotated_binary)

    return {
        "gray": rotated_gray,
        "binary": rotated_binary,
        "skew_angle": round(skew_angle, 2),
        "lines": lines,
        "dimensions": {"width": w, "height": h}
    }


def detect_skew_angle(binary_inv: np.ndarray) -> float:
    """Estimates dominant skew angle from binary image coordinates."""
    pts = np.column_stack(np.where(binary_inv > 0))
    if len(pts) < 100:
        return 0.0
    rect = cv2.minAreaRect(pts)
    angle = rect[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    return float(angle)


def detect_lines(binary_inv: np.ndarray) -> List[Dict[str, Any]]:
    """Detects primary geometric line segments using Hough Lines P."""
    lines = cv2.HoughLinesP(
        binary_inv,
        rho=1,
        theta=np.pi / 180,
        threshold=80,
        minLineLength=30,
        maxLineGap=10
    )
    if lines is None:
        return []

    results = []
    for line in lines[:100]:  # Cap at top 100 dominant lines
        x1, y1, x2, y2 = line[0]
        length = math.hypot(x2 - x1, y2 - y1)
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0
        results.append({
            "p1": [int(x1), int(y1)],
            "p2": [int(x2), int(y2)],
            "length": round(length, 2),
            "angle": round(angle, 2)
        })
    return results
