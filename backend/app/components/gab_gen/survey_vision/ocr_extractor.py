"""
Survey Deed OCR Extraction with EasyOCR.
Extracts boundary distances, bearings, area annotations, scale, and north arrows.
Preserves bounding boxes, confidence scores, and raw observations.
"""
import re
from typing import Any, Dict, List, Optional
import numpy as np

try:
    import easyocr
    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False


class SurveyOcrExtractor:
    """
    Runs EasyOCR text extraction and parses typical survey deed annotations:
    - Distance values (meters, feet, links)
    - Angular bearings (degrees, minutes, seconds, quadrant format)
    - Scale notations (e.g. 1:500, 1:1000)
    - North arrow and road access annotations
    """

    _reader = None

    @classmethod
    def get_reader(cls):
        if cls._reader is None and HAS_EASYOCR:
            # Initialize English reader on CPU
            cls._reader = easyocr.Reader(['en'], gpu=False)
        return cls._reader

    @classmethod
    def extract_text_boxes(cls, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Runs EasyOCR on processed image array and extracts normalized text items.
        Returns list of dicts: {text, confidence, bbox: [[x,y],...], center: [x,y]}
        """
        reader = cls.get_reader()
        if reader is None or image is None:
            return []

        raw_results = reader.readtext(image)
        boxes = []
        for bbox, text, conf in raw_results:
            pts = [[int(pt[0]), int(pt[1])] for pt in bbox]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            center = [int(sum(xs) / len(xs)), int(sum(ys) / len(ys))]
            boxes.append({
                "text": text.strip(),
                "confidence": round(float(conf), 3),
                "bbox": pts,
                "center": center
            })
        return boxes

    @classmethod
    def parse_annotations(cls, ocr_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Parses OCR text boxes into structured survey categories:
        - bearings
        - distances
        - scales
        - road_hints
        - north_hints
        """
        bearings = []
        distances = []
        scales = []
        road_hints = []
        north_hints = []

        # Regex patterns
        bearing_pattern = re.compile(
            r"(\b[NS]\s*[\d\.\°\'\"dms\s]+[EW]\b|\b\d{1,3}[\°\s]\d{1,2}[\'\s]?(\d{1,2}[\"\s]?)?|\b\d{1,3}\.\d{1,4}\s*(?:deg|degrees)?)",
            re.IGNORECASE
        )
        distance_pattern = re.compile(
            r"(\b\d{1,3}(?:\.\d{1,3})?\s*(?:m|meters|ft|feet|lks|links)\b|\b\d{1,2}\.\d{2,3}\b)",
            re.IGNORECASE
        )
        scale_pattern = re.compile(r"\b1\s*[:/]\s*\d{2,5}\b", re.IGNORECASE)

        for box in ocr_boxes:
            txt = box["text"]
            conf = box["confidence"]

            # 1. Scale
            sm = scale_pattern.search(txt)
            if sm:
                scales.append({
                    "raw": sm.group(0),
                    "confidence": conf,
                    "bbox": box["bbox"]
                })

            # 2. Road indicator
            if any(term in txt.lower() for term in ["road", "lane", "path", "street", "access", "rd."]):
                road_hints.append({
                    "text": txt,
                    "confidence": conf,
                    "center": box["center"],
                    "bbox": box["bbox"]
                })

            # 3. North indicator
            if any(term in txt.upper() for term in ["NORTH", " N ", "▲ N", "↑ N"]):
                north_hints.append({
                    "text": txt,
                    "confidence": conf,
                    "center": box["center"],
                    "bbox": box["bbox"]
                })

            # 4. Bearings
            bm = bearing_pattern.search(txt)
            if bm and not any(k in txt.lower() for k in ["sqm", "sqft", "perch", "acre"]):
                bearings.append({
                    "raw": bm.group(0),
                    "confidence": conf,
                    "center": box["center"],
                    "bbox": box["bbox"]
                })

            # 5. Distances
            dm = distance_pattern.search(txt)
            if dm and not sm:
                distances.append({
                    "raw": dm.group(0),
                    "confidence": conf,
                    "center": box["center"],
                    "bbox": box["bbox"]
                })

        return {
            "bearings": bearings,
            "distances": distances,
            "scales": scales,
            "road_hints": road_hints,
            "north_hints": north_hints,
            "total_boxes": len(ocr_boxes)
        }
