"""
Survey Deed OCR Extraction with EasyOCR.
Extracts boundary distances, bearings, area annotations, scale, and north arrows.
Preserves bounding boxes, confidence scores, and raw observations.
Normalizes common OCR digit/letter confusions (O/0, I/1, S/5).
"""
import re
from typing import Any, Dict, List, Optional, Tuple
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
    - Scale notations (e.g. 1:100, 1:200, 1:500, 1:1000)
    - North arrow and road access annotations
    - Lot numbers and plan references
    """

    _reader = None

    @classmethod
    def get_reader(cls):
        if cls._reader is None and HAS_EASYOCR:
            # Bypass SSL certificate validation when downloading EasyOCR models if OS certificates are missing
            try:
                import ssl
                ssl._create_default_https_context = ssl._create_unverified_context
            except Exception:
                pass
            # Initialize English reader on CPU (model reused across invocations)
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
                "center": center,
                "source": "easyocr",
                "verification_status": "unverified"
            })
        return boxes

    @classmethod
    def normalize_numerical_text(cls, txt: str) -> str:
        """
        Fixes common OCR character confusions in numerical context:
        - Uppercase 'O' or lowercase 'o' -> '0'
        - Uppercase 'I', lowercase 'l', or '|' -> '1'
        - Uppercase 'S' or lowercase 's' -> '5' when flanked by digits
        - Uppercase 'B' -> '8' when leading decimals
        """
        cleaned = txt.strip()
        # Replace O/o when preceded by digit: e.g. 1O.5 -> 10.5
        cleaned = re.sub(r'(\d)[Oo]', r'\g<1>0', cleaned)
        # Replace O/o when followed by digit: e.g. O.5 -> 0.5, .O -> .0
        cleaned = re.sub(r'[Oo](\d)', r'0\g<1>', cleaned)
        cleaned = re.sub(r'(\.)[Oo]', r'\g<1>0', cleaned)
        # Replace I/l/| when preceded or followed by digits
        cleaned = re.sub(r'(\d)[Il\|]', r'\g<1>1', cleaned)
        cleaned = re.sub(r'^[Il\|](\d)', r'1\g<1>', cleaned)
        cleaned = re.sub(r'(\s)[Il\|](\d)', r'\g<1>1\g<2>', cleaned)
        cleaned = re.sub(r'(\.)[Il\|]', r'\g<1>1', cleaned)
        # Replace S/s when inside a number sequence
        cleaned = re.sub(r'(\d)[Ss](\d|\.|$)', r'\g<1>5\g<2>', cleaned)
        cleaned = re.sub(r'^[Bb](\.\d)', r'8\g<1>', cleaned)
        return cleaned

    @classmethod
    def parse_annotations(cls, ocr_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Parses OCR text boxes into structured survey categories:
        - bearings
        - distances
        - scales
        - road_hints
        - north_hints
        - land_extent_hints
        """
        bearings = []
        distances = []
        scales = []
        road_hints = []
        north_hints = []
        extent_hints = []

        # Regex patterns
        bearing_pattern = re.compile(
            r"(\b[NS]\s*[\d\.\°\'\"dms\s]+[EW]\b|\b\d{1,3}[\°\s]\d{1,2}[\'\s]?(\d{1,2}[\"\s]?)?|\b\d{1,3}\.\d{1,4}\s*(?:deg|degrees)?)",
            re.IGNORECASE
        )
        distance_pattern = re.compile(
            r"(\b\d{1,3}(?:\.\d{1,3})?\s*(?:m|meters|ft|feet|lks|links)\b|\b\d{1,3}\.\d{2,3}\b)",
            re.IGNORECASE
        )
        scale_pattern = re.compile(r"\b1\s*[:/]\s*(\d{2,5})\b", re.IGNORECASE)
        extent_pattern = re.compile(
            r"(\b\d+(?:\.\d+)?\s*(?:perches|perch|acres|acre|p|sqm|sq\.m|sqft)\b|\b\d+\s*A\s*\d+\s*R\s*\d+(?:\.\d+)?\s*P\b)",
            re.IGNORECASE
        )

        for box in ocr_boxes:
            raw_txt = box["text"]
            conf = box["confidence"]
            norm_txt = cls.normalize_numerical_text(raw_txt)

            # 1. Scale Detection (e.g. 1:100, 1:200, 1:500)
            sm = scale_pattern.search(norm_txt)
            if sm:
                ratio = f"1:{sm.group(1)}"
                scales.append({
                    "raw": sm.group(0),
                    "ratio": ratio,
                    "confidence": conf,
                    "bbox": box["bbox"],
                    "center": box["center"]
                })

            # 2. Road indicator
            if any(term in norm_txt.lower() for term in ["road", "lane", "path", "street", "access", "mawatha", "rd."]):
                road_hints.append({
                    "text": raw_txt,
                    "confidence": conf,
                    "center": box["center"],
                    "bbox": box["bbox"]
                })

            # 3. North indicator
            if re.search(r"\b(NORTH|N|N\.)\b", raw_txt.upper()):
                # Exclude if part of Quadrant bearing like N 45 E
                if not re.search(r"\bN\s*\d+.*[EW]\b", raw_txt.upper()):
                    north_hints.append({
                        "text": raw_txt,
                        "confidence": conf,
                        "center": box["center"],
                        "bbox": box["bbox"]
                    })

            # 4. Land Extent
            em = extent_pattern.search(raw_txt)
            if em:
                extent_hints.append({
                    "raw": em.group(0),
                    "confidence": conf,
                    "center": box["center"],
                    "bbox": box["bbox"]
                })

            # 5. Bearings
            bm = bearing_pattern.search(norm_txt)
            if bm and not any(k in norm_txt.lower() for k in ["sqm", "sqft", "perch", "acre", "scale", "plan"]):
                bearings.append({
                    "raw": bm.group(0),
                    "confidence": conf,
                    "center": box["center"],
                    "bbox": box["bbox"]
                })

            # 6. Distances
            dm = distance_pattern.search(norm_txt)
            if dm and not sm and not em:
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
            "extent_hints": extent_hints,
            "total_boxes": len(ocr_boxes)
        }


def normalize_numerical_text(txt: str) -> str:
    """Module-level wrapper for OCR character confusion normalization."""
    return SurveyOcrExtractor.normalize_numerical_text(txt)


def extract_scale_ratio(text: str) -> Tuple[Optional[float], str]:
    """
    Extracts ratio scale denominator (e.g., 500 for 1:500) and provenance.
    """
    m = re.search(r"\b1\s*[:/]\s*(\d{2,5})\b", text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1)), "detected_ratio_text"
        except ValueError:
            pass
    return None, "unknown"


def parse_land_extent(text: str) -> Optional[Dict[str, Any]]:
    """
    Parses land extent strings in perches, acres, or ARP notation.
    """
    # 1. ARP Notation: e.g. "0A - 2R - 10P" or "1A 0R 25.5P"
    arp_m = re.search(r"(\d+)\s*A(?:cres?)?\s*[-–]?\s*(\d+)\s*R(?:oods?)?\s*[-–]?\s*(\d+(?:\.\d+)?)\s*P(?:erches?)?", text, re.IGNORECASE)
    if arp_m:
        acres = float(arp_m.group(1))
        roods = float(arp_m.group(2))
        perches = float(arp_m.group(3))
        # 1 acre = 4 roods = 160 perches; 1 rood = 40 perches
        total_perches = (acres * 160.0) + (roods * 40.0) + perches
        sqm = total_perches * 25.29285264
        return {
            "unit": "perches",
            "raw_value": total_perches,
            "value_sqm": round(sqm, 2),
            "format": "ARP",
            "components": {"acres": acres, "roods": roods, "perches": perches}
        }

    # 2. Perches: e.g. "15.25 Perches"
    perch_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:perches|perch|p)\b", text, re.IGNORECASE)
    if perch_m:
        val = float(perch_m.group(1))
        return {
            "unit": "perches",
            "raw_value": val,
            "value_sqm": round(val * 25.29285264, 2),
            "format": "decimal_perches"
        }

    # 3. Acres: e.g. "0.25 Acres"
    acre_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:acres|acre)\b", text, re.IGNORECASE)
    if acre_m:
        val = float(acre_m.group(1))
        return {
            "unit": "acres",
            "raw_value": val,
            "value_sqm": round(val * 4046.8564224, 2),
            "format": "decimal_acres"
        }

    return None


def extract_north_label(text: str) -> Optional[Dict[str, Any]]:
    """
    Extracts explicit North indicator string if detected.
    """
    if re.search(r"\b(TRUE\s+NORTH|MAGNETIC\s+NORTH|NORTH|N\.)\b", text, re.IGNORECASE):
        # Avoid quadrant bearings like "N 45 E"
        if not re.search(r"\bN\s*\d+.*[EW]\b", text, re.IGNORECASE):
            return {"north_label": text.strip(), "confidence": 0.9}
    return None
