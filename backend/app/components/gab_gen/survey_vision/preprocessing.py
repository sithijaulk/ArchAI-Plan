"""
Survey Vision Preprocessing Pipeline.
Implements OpenCV-based configurable image preprocessing for survey and deed plans:
- File loading & format conversion (including PyMuPDF for multi-page PDF rendering)
- EXIF orientation correction
- Grayscale conversion, adaptive thresholding (Otsu / adaptive Gaussian), denoising, CLAHE contrast enhancement
- Deskewing and rotation correction
- Separate OCR-ready and Geometry-ready image output streams
- Hough line, contour extraction, and boundary segment detection
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

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

from PIL import Image, ImageOps


# Configurable default preprocessing constants
MAX_PDF_PAGES = 50
MAX_IMAGE_PIXELS = 40_000_000  # ~40 Megapixels safety limit against decompression bombs
DEFAULT_DPI = 300


def get_pdf_page_count(file_bytes: bytes) -> int:
    """Returns the total number of pages in a PDF document."""
    if HAS_PYMUPDF:
        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            if doc.is_encrypted:
                raise ValueError("The uploaded PDF is encrypted/password-protected. Please provide an unencrypted document.")
            count = len(doc)
            if count == 0:
                raise ValueError("The uploaded PDF contains 0 pages.")
            if count > MAX_PDF_PAGES:
                raise ValueError(f"PDF exceeds maximum allowed page count ({MAX_PDF_PAGES} pages). Uploaded has {count} pages.")
            return count
        except Exception as e:
            if "encrypted" in str(e).lower() or "page count" in str(e).lower():
                raise
            raise ValueError(f"Corrupted or unreadable PDF document: {str(e)}")
    elif HAS_PYPDF:
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            if reader.is_encrypted:
                raise ValueError("The uploaded PDF is encrypted/password-protected. Please provide an unencrypted document.")
            count = len(reader.pages)
            if count == 0:
                raise ValueError("The uploaded PDF contains 0 pages.")
            if count > MAX_PDF_PAGES:
                raise ValueError(f"PDF exceeds maximum allowed page count ({MAX_PDF_PAGES} pages). Uploaded has {count} pages.")
            return count
        except Exception as e:
            if "encrypted" in str(e).lower() or "page count" in str(e).lower():
                raise
            raise ValueError(f"Corrupted or unreadable PDF document: {str(e)}")
    else:
        raise RuntimeError("pymupdf or pypdf is required for PDF page count inspection.")


def load_image_from_bytes(
    file_bytes: bytes,
    ext: str,
    page_number: int = 1,
    target_dpi: int = DEFAULT_DPI
) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
    """
    Loads raw bytes into an OpenCV BGR numpy array with safety validations.
    Supports multi-page PDF via PyMuPDF (page_number is 1-indexed).
    Applies EXIF orientation correction for mobile photo scans.
    Returns: (bgr_image, metadata)
    """
    meta: Dict[str, Any] = {
        "page_number": page_number,
        "total_pages": 1,
        "dpi": target_dpi,
        "format": ext.lower().replace(".", ""),
        "exif_transposed": False
    }

    if ext.lower() == ".pdf":
        if not HAS_PYMUPDF:
            raise RuntimeError("pymupdf is required for PDF conversion.")
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        if doc.is_encrypted:
            raise ValueError("The uploaded PDF is encrypted. Please provide an unencrypted PDF.")
        total_pages = len(doc)
        meta["total_pages"] = total_pages
        if page_number < 1 or page_number > total_pages:
            raise ValueError(f"Requested page {page_number} is out of range. Document has {total_pages} page(s).")

        page = doc[page_number - 1]
        # Render at target_dpi (standard zoom ratio: target_dpi / 72.0)
        zoom = target_dpi / 72.0
        mat = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        pil_img = Image.open(io.BytesIO(img_data)).convert("RGB")
    else:
        # Standard image file (JPG, PNG)
        try:
            pil_img = Image.open(io.BytesIO(file_bytes))
            # EXIF Orientation correction
            transposed = ImageOps.exif_transpose(pil_img)
            if transposed is not None:
                if transposed.size != pil_img.size:
                    meta["exif_transposed"] = True
                pil_img = transposed.convert("RGB")
            else:
                pil_img = pil_img.convert("RGB")
        except Exception as e:
            raise ValueError(f"Corrupted or invalid image file: {str(e)}")

    w, h = pil_img.size
    total_pixels = w * h
    if total_pixels > MAX_IMAGE_PIXELS:
        raise ValueError(
            f"Image dimensions ({w}x{h} = {total_pixels} pixels) exceed safety ceiling of {MAX_IMAGE_PIXELS} pixels."
        )

    meta["dimensions"] = {"width": w, "height": h}
    img_np = np.array(pil_img)
    bgr_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR) if HAS_OPENCV else img_np
    return bgr_img, meta


def preprocess_survey_image(
    img_bgr: np.ndarray,
    clip_limit: float = 2.0,
    bilateral_d: int = 9
) -> Dict[str, Any]:
    """
    Runs OpenCV image preprocessing pipeline tailored for cadastral deeds:
    Produces TWO specialized image variants:
      1. ocr_ready: Enhanced grayscale preserving subtle text numerals and degree symbols.
      2. geometry_ready: Cleaned binary image for line and boundary detection.
    """
    if not HAS_OPENCV or img_bgr is None:
        return {
            "gray": None,
            "binary": None,
            "ocr_ready": None,
            "skew_angle": 0.0,
            "lines": [],
            "dimensions": {"width": 0, "height": 0}
        }

    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # 1. Bilateral filtering: smooths background texture while strictly keeping edges sharp
    denoised = cv2.bilateralFilter(gray, d=bilateral_d, sigmaColor=75, sigmaSpace=75)

    # 2. CLAHE (Contrast Limited Adaptive Histogram Equalization) for text and line enhancement
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    enhanced_gray = clahe.apply(denoised)

    # 3. Otsu & Adaptive Thresholding
    # Otsu thresholding creates high-contrast binary
    _, otsu_inv = cv2.threshold(enhanced_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Adaptive thresholding preserves faint boundary lines in unevenly scanned documents
    adaptive_inv = cv2.adaptiveThreshold(
        enhanced_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 4
    )

    # Combine Otsu and Adaptive to preserve both strong text and faint boundaries
    binary_inv = cv2.bitwise_or(otsu_inv, adaptive_inv)

    # 4. Deskewing / Rotation angle estimation
    skew_angle = detect_skew_angle(binary_inv)

    if abs(skew_angle) > 0.5 and abs(skew_angle) < 45.0:
        center = (w // 2, h // 2)
        rot_mat = cv2.getRotationMatrix2D(center, skew_angle, 1.0)
        rotated_binary = cv2.warpAffine(
            binary_inv, rot_mat, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        rotated_enhanced_gray = cv2.warpAffine(
            enhanced_gray, rot_mat, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        rotated_bgr = cv2.warpAffine(
            img_bgr, rot_mat, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
    else:
        rotated_binary = binary_inv
        rotated_enhanced_gray = enhanced_gray
        rotated_bgr = img_bgr
        skew_angle = 0.0

    # 5. Boundary line segment detection on deskewed geometry image
    lines = detect_lines(rotated_binary)

    # 6. Extract candidate North arrow symbol positions
    north_symbol_candidates = detect_north_arrow_candidates(rotated_binary)

    return {
        "gray": rotated_enhanced_gray,
        "binary": rotated_binary,
        "ocr_ready": rotated_enhanced_gray,
        "geometry_ready": rotated_binary,
        "bgr_aligned": rotated_bgr,
        "skew_angle": round(skew_angle, 2),
        "lines": lines,
        "north_symbol_candidates": north_symbol_candidates,
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
    """
    Detects geometric line segments using Hough Lines P.
    Filters and clusters candidates to extract plausible boundary edges.
    """
    # Morphological kernel to slightly bridge broken scanned lines without thickening text
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    dilated = cv2.dilate(binary_inv, kernel, iterations=1)

    lines = cv2.HoughLinesP(
        dilated,
        rho=1,
        theta=np.pi / 180,
        threshold=60,
        minLineLength=25,
        maxLineGap=12
    )
    if lines is None:
        return []

    results = []
    for line in lines[:150]:  # Cap at top 150 lines
        coords = line[0] if len(line.shape) > 1 and line.shape[0] == 1 else line
        if len(coords) == 4:
            x1, y1, x2, y2 = coords
        else:
            x1, y1, x2, y2 = coords.flatten()[:4]
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 20:
            continue
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0
        results.append({
            "p1": [int(x1), int(y1)],
            "p2": [int(x2), int(y2)],
            "length": round(length, 2),
            "angle": round(angle, 2)
        })

    # Sort descending by length
    results.sort(key=lambda item: item["length"], reverse=True)
    return results


def detect_north_arrow_candidates(binary_inv: np.ndarray) -> List[Dict[str, Any]]:
    """
    Heuristic detection of North arrow symbols:
    Finds isolated vertical or triangular contours with high aspect ratio or pointy vertices.
    """
    contours, _ = cv2.findContours(binary_inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        # North arrows on typical 300DPI scans are usually between 200 and 8000 pixels
        if area < 150 or area > 10000:
            continue

        x, y, w, h = cv2.boundingRect(cnt)
        aspect = h / float(w) if w > 0 else 0

        # Arrows are often elongated vertically (aspect 1.4 to 5.0) or triangular (3-4 approx vertices)
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)

        if (1.3 <= aspect <= 5.0) or (len(approx) in (3, 4, 5)):
            candidates.append({
                "bbox": [x, y, w, h],
                "center": [x + w // 2, y + h // 2],
                "area": area,
                "aspect_ratio": round(aspect, 2),
                "num_vertices": len(approx)
            })

    return candidates
