"""
EasyOCR Survey Extraction Provider.
Integrates OpenCV preprocessing, EasyOCR recognition, and measurement association.
Supports multi-page PDF page selection, rotation correction, and non-destructive provenance.
"""
from typing import Any, Dict, Optional
from .survey_provider import SurveyExtractionProvider
from .schemas import (
    ManualSurveyExtractionRequest,
    SurveySource,
    SurveyVerificationStatus,
    GeoreferenceStatus
)
from .survey_vision.preprocessing import (
    load_image_from_bytes,
    preprocess_survey_image,
    get_pdf_page_count
)
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
        page_number = int(context.get("page_number", 1))

        if not file_bytes:
            raise ValueError("No file bytes provided for EasyOCR extraction.")

        # 1. Load image (supports multi-page PDF via PyMuPDF with page selection)
        img_bgr, meta = load_image_from_bytes(file_bytes, ext, page_number=page_number)
        if img_bgr is None:
            raise ValueError(f"Failed to decode survey image or render PDF document (page {page_number}).")

        # 2. Preprocess with OpenCV (dual output: ocr_ready, geometry_ready)
        preprocessed = preprocess_survey_image(img_bgr)
        ocr_image = preprocessed.get("ocr_ready")

        # 3. EasyOCR Text Extraction
        ocr_boxes = SurveyOcrExtractor.extract_text_boxes(ocr_image if ocr_image is not None else img_bgr)
        annotations = SurveyOcrExtractor.parse_annotations(ocr_boxes)

        # 4. Measurement Association
        edges = associate_measurements_to_edges(preprocessed.get("lines", []), annotations)

        # 5. Orientation, Road front, and Scale inference
        inferred = infer_orientation_and_road(
            annotations,
            edges,
            north_symbol_candidates=preprocessed.get("north_symbol_candidates")
        )

        # Determine verification lifecycle status
        has_ambiguous = any(e.verification_status == "ambiguous" for e in edges)
        lifecycle_status = (
            SurveyVerificationStatus.REQUIRES_USER_CORRECTION
            if (has_ambiguous or inferred.get("north_origin") == "default_unknown")
            else SurveyVerificationStatus.EXTRACTED_UNVERIFIED
        )

        return ManualSurveyExtractionRequest(
            north_angle=inferred.get("north_angle", 0.0),
            reference_edge=edges[0].edge_id if edges else None,
            source=SurveySource.EASYOCR,
            edges=edges,
            verified_by_user=False,
            verification_status=lifecycle_status,
            north_angle_origin=inferred.get("north_origin", "default_unknown"),
            drawing_scale=inferred.get("drawing_scale"),
            drawing_scale_origin=inferred.get("drawing_scale_origin", "unknown"),
            road_frontage_edge_id=inferred.get("road_edge_id"),
            road_frontage_origin=inferred.get("road_origin", "none"),
            selected_page_number=page_number,
            total_pages=meta.get("total_pages", 1),
            georeference_status=GeoreferenceStatus.LOCAL_P0_ONLY
        )
