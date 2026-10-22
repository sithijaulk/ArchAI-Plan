"""
Repeatable Cadastral Survey Extraction Benchmark Framework for GAB-Gen.
Evaluates OCR text accuracy, line detection, measurement association,
traverse closure error, and area discrepancy across synthetic and real survey plan samples.
"""
import json
import math
import os
import time
from typing import Any, Dict, List, Optional
import numpy as np

from ..schemas import (
    ManualSurveyExtractionRequest,
    SurveyEdgeInput,
    DistanceValue,
    BearingValue,
    DistanceUnit,
    EdgeType,
    SurveySource
)
from ..survey_vision.preprocessing import preprocess_survey_image
from ..survey_vision.ocr_extractor import SurveyOcrExtractor
from ..measurement_association.associator import (
    associate_measurements_to_edges,
    infer_orientation_and_road
)
from ..vector_reconstruction.reconstruct import reconstruct_polygon


class SurveyExtractionBenchmark:
    """
    Evaluator for cadastral deed image processing.
    Computes precision, recall, closure error, and boundary alignment metrics.
    """

    @classmethod
    def evaluate_sample(
        cls,
        image_bgr: np.ndarray,
        ground_truth: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Runs the full extraction pipeline on image_bgr and benchmarks against ground_truth.
        ground_truth schema:
        {
            "sample_id": "SURVEY-SYNTH-01",
            "category": "clear_digital | scanned | rotated | noisy",
            "true_edges": [
                {"distance_m": 15.0, "bearing_deg": 90.0, "edge_type": "road_front"},
                ...
            ],
            "true_area_sqm": 255.0,
            "true_north_angle": 0.0,
            "true_scale": "1:100"
        }
        """
        start_time = time.perf_counter()

        # 1. Preprocess
        preprocessed = preprocess_survey_image(image_bgr)
        ocr_ready = preprocessed.get("ocr_ready")

        # 2. OCR Extraction
        ocr_boxes = SurveyOcrExtractor.extract_text_boxes(ocr_ready if ocr_ready is not None else image_bgr)
        annotations = SurveyOcrExtractor.parse_annotations(ocr_boxes)

        # 3. Association
        candidate_edges = associate_measurements_to_edges(preprocessed.get("lines", []), annotations)

        # 4. Inferred Orientation and Scale
        inferred = infer_orientation_and_road(annotations, candidate_edges, preprocessed.get("north_symbol_candidates"))

        proc_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # 5. Vector Reconstruction of candidate
        req = ManualSurveyExtractionRequest(
            north_angle=inferred.get("north_angle", 0.0),
            source=SurveySource.EASYOCR,
            edges=candidate_edges
        )
        recon = reconstruct_polygon(req)

        # 6. Evaluation metrics against ground truth
        true_edges = ground_truth.get("true_edges", [])
        num_true = len(true_edges)
        num_extracted = len(candidate_edges)

        # Matched edges evaluation (within 10% distance and 5 deg bearing)
        matched_count = 0
        dist_errors = []
        bearing_errors = []

        for i in range(min(num_true, num_extracted)):
            te = true_edges[i]
            ee = candidate_edges[i]
            dist_err = abs(ee.distance.value - te["distance_m"])
            b_err = min(
                abs(ee.bearing.normalized_degrees - te["bearing_deg"]),
                360.0 - abs(ee.bearing.normalized_degrees - te["bearing_deg"])
            )
            dist_errors.append(dist_err)
            bearing_errors.append(b_err)
            if dist_err <= (te["distance_m"] * 0.1) and b_err <= 5.0:
                matched_count += 1

        precision = matched_count / num_extracted if num_extracted > 0 else 0.0
        recall = matched_count / num_true if num_true > 0 else 0.0

        true_area = ground_truth.get("true_area_sqm", 0.0)
        calc_area = recon.get("reconstructed_area", 0.0)
        area_err_pct = (abs(calc_area - true_area) / true_area * 100.0) if true_area > 0 else 0.0

        needs_correction = any(
            e.verification_status == "ambiguous" or "needs_user_verification" in e.flags
            for e in candidate_edges
        ) or inferred.get("north_origin") == "default_unknown"

        return {
            "sample_id": ground_truth.get("sample_id", "UNKNOWN"),
            "category": ground_truth.get("category", "unclassified"),
            "processing_time_ms": proc_time_ms,
            "detected_lines_count": len(preprocessed.get("lines", [])),
            "ocr_boxes_count": len(ocr_boxes),
            "extracted_edges_count": num_extracted,
            "true_edges_count": num_true,
            "matched_edges_count": matched_count,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "mean_dist_error_m": round(float(np.mean(dist_errors)), 3) if dist_errors else 0.0,
            "mean_bearing_error_deg": round(float(np.mean(bearing_errors)), 3) if bearing_errors else 0.0,
            "closure_error_m": recon.get("closure_error", 0.0),
            "reconstructed_area_sqm": calc_area,
            "true_area_sqm": true_area,
            "area_error_percent": round(area_err_pct, 2),
            "detected_north_angle": inferred.get("north_angle"),
            "north_origin": inferred.get("north_origin"),
            "detected_scale": inferred.get("drawing_scale"),
            "requires_manual_correction": needs_correction
        }
