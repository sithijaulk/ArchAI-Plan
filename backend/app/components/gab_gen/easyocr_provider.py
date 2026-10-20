"""
EasyOCR Survey Extraction Provider.
Integrates OpenCV preprocessing, EasyOCR recognition, and measurement association.
"""
from typing import Any, Dict
from .survey_provider import SurveyExtractionProvider
from .schemas import ManualSurveyExtractionRequest, SurveySource
from .survey_vision.preprocessing import load_image_from_bytes, preprocess_survey_image
from .survey_vision.ocr_extractor import SurveyOcrExtractor
from .measurement_association.associator import (
    associate_measurements_to_edges,
    infer_orientation_and_road
)


class EasyOCRSurveyExtractionProvider(SurveyExtractionProvider):
    """
    Automated survey extraction using OpenCV and EasyOCR.
    Produces candidate survey boundary measurements with confidence scores and provenance.
    """

    @property
    def provider_name(self) -> str:
        return "easyocr"

    def extract_survey(self, context: Dict[str, Any]) -> ManualSurveyExtractionRequest:
        file_bytes = context.get("file_bytes")
        filename = context.get("filename", "plan.png")
        ext = context.get("ext", ".png")

        if not file_bytes:
            raise ValueError("No file bytes provided for EasyOCR extraction.")

        # 1. Load image (supports PDF via PyMuPDF)
        img_bgr = load_image_from_bytes(file_bytes, ext)
        if img_bgr is None:
            raise ValueError("Failed to decode survey image or render PDF document.")

        # 2. Preprocess with OpenCV
        preprocessed = preprocess_survey_image(img_bgr)
        gray = preprocessed.get("gray")

        # 3. EasyOCR Text Extraction
        ocr_boxes = SurveyOcrExtractor.extract_text_boxes(gray if gray is not None else img_bgr)
        annotations = SurveyOcrExtractor.parse_annotations(ocr_boxes)

        # 4. Measurement Association
        edges = associate_measurements_to_edges(preprocessed.get("lines", []), annotations)

        # 5. Orientation and Road front
        inferred = infer_orientation_and_road(annotations, edges)

        return ManualSurveyExtractionRequest(
            north_angle=inferred.get("north_angle", 0.0),
            reference_edge=edges[0].edge_id if edges else None,
            source=SurveySource.EASYOCR,
            edges=edges,
            verified_by_user=False,
            north_angle_origin="ocr_arrow" if inferred.get("north_confidence", 0) > 0.6 else "default_unknown",
            road_frontage_edge_id=inferred.get("road_edge_id"),
            road_frontage_origin="ocr_annotation" if inferred.get("road_confidence", 0) > 0.6 else "none"
        )
