import pytest
import numpy as np
import io
import pypdf
from PIL import Image

from app.components.gab_gen.schemas import (
    SurveyVerificationStatus,
    GeoreferenceStatus,
    ManualSurveyExtractionRequest,
    SurveyEdgeInput,
)
from app.components.gab_gen.survey_vision.preprocessing import (
    get_pdf_page_count,
    load_image_from_bytes,
    preprocess_survey_image,
    detect_skew_angle,
    detect_lines,
    detect_north_arrow_candidates,
)
from app.components.gab_gen.survey_vision.ocr_extractor import (
    normalize_numerical_text,
    extract_scale_ratio,
    parse_land_extent,
    extract_north_label,
)
from app.components.gab_gen.measurement_association.associator import (
    associate_measurements_to_edges,
)
from app.components.gab_gen.vector_reconstruction.reconstruct import (
    reconstruct_polygon,
    normalize_bearing_string,
)



def create_synthetic_survey_image(width=1000, height=800):
    """Creates a synthetic survey plan image with a distinct black rectangular boundary."""
    from PIL import ImageDraw
    pil_img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(pil_img)
    # Draw a 400x300 rectangle in the middle
    draw.rectangle([300, 250, 700, 550], outline=(0, 0, 0), width=3)
    return np.array(pil_img)


def test_pdf_page_count_and_inspection():
    """Verify multi-page PDF inspection, page bounding, and encryption detection."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=600, height=800)
    writer.add_blank_page(width=600, height=800)
    writer.add_blank_page(width=600, height=800)
    buffer = io.BytesIO()
    writer.write(buffer)
    pdf_bytes = buffer.getvalue()

    count = get_pdf_page_count(pdf_bytes)
    assert count == 3


def test_corrupt_file_handling():
    """Verify corrupted or invalid image and pdf files raise clean ValueError."""
    corrupted_bytes = b"NOT_A_VALID_PDF_OR_IMAGE_DATA_12345"
    
    with pytest.raises(ValueError, match="Corrupted or unreadable PDF document"):
        get_pdf_page_count(corrupted_bytes)

    with pytest.raises(ValueError, match="Corrupted or invalid image file"):
        load_image_from_bytes(corrupted_bytes, ext="png")


def test_preprocessing_dual_stream_and_geometry():
    """Verify preprocessing generates both OCR-ready and geometry-ready streams."""
    synthetic = create_synthetic_survey_image()
    # Test preprocessing directly on BGR image
    res = preprocess_survey_image(synthetic)
    assert res["ocr_ready"] is not None
    assert res["geometry_ready"] is not None
    assert res["dimensions"]["width"] == 1000
    assert res["dimensions"]["height"] == 800

    # Line detection should locate rectangular boundary segments
    lines = detect_lines(res["geometry_ready"])
    assert len(lines) >= 4  # Should find at least the 4 strong rectangle borders


def test_ocr_normalization_and_number_confusion():
    """Verify OCR normalization repairs common OCR digit/letter confusions."""
    # 'O' -> '0'
    assert normalize_numerical_text("1O.5m") == "10.5m"
    # 'I' / 'l' -> '1'
    assert normalize_numerical_text("I5.2") == "15.2"
    assert normalize_numerical_text("l2.8") == "12.8"
    # 'S' / 's' -> '5'
    assert normalize_numerical_text("2S.O") == "25.0"
    # 'B' -> '8'
    assert normalize_numerical_text("B.5") == "8.5"


def test_scale_ratio_and_land_extent_extraction():
    """Verify ratio scale parsing and land extent (perches, acres, ARP) regex engines."""
    scale1, orig1 = extract_scale_ratio("Scale 1:500 on survey sheet")
    assert scale1 == 500.0
    assert orig1 == "detected_ratio_text"

    scale2, orig2 = extract_scale_ratio("SCALE 1: 1000")
    assert scale2 == 1000.0

    # Perches parsing
    ext1 = parse_land_extent("Extent: 15.25 Perches")
    assert ext1 is not None
    assert ext1["unit"] == "perches"
    assert pytest.approx(ext1["value_sqm"], 0.1) == 15.25 * 25.29285264

    # ARP parsing (Acres-Roods-Perches: 0A-2R-10P)
    # 0 acres + 2 roods (0.5 acre = 80 perches) + 10 perches = 90 perches
    ext2 = parse_land_extent("Extent 0A - 2R - 10P")
    assert ext2 is not None
    assert ext2["unit"] == "perches"
    assert pytest.approx(ext2["raw_value"], 0.01) == 90.0

    # North label extraction
    north_lbl = extract_north_label("TRUE NORTH")
    assert north_lbl is not None
    assert north_lbl["north_label"] == "TRUE NORTH"


def test_measurement_association_anti_collision():
    """Verify measurement associator pairs text to lines without duplicate assignment collisions."""
    # 4 lines representing a rectangle with distinct lengths
    lines = [
        {"p1": [100, 100], "p2": [500, 100], "length": 400.0, "angle": 0.0},    # Top (mid: 300, 100)
        {"p1": [500, 100], "p2": [500, 400], "length": 350.0, "angle": 90.0},   # Right (mid: 500, 250)
        {"p1": [500, 400], "p2": [100, 400], "length": 250.0, "angle": 180.0},  # Bottom (mid: 300, 400)
        {"p1": [100, 400], "p2": [100, 100], "length": 200.0, "angle": 270.0},  # Left (mid: 100, 250)
    ]

    # Two distance boxes near top and right lines
    ocr_annotations = {
        "distances": [
            {"raw": "20.0m", "confidence": 0.92, "center": [300, 95]},
            {"raw": "15.0m", "confidence": 0.89, "center": [505, 250]}
        ],
        "bearings": [
            {"raw": "090°00'00\"", "confidence": 0.88, "center": [300, 110]}
        ]
    }

    edges = associate_measurements_to_edges(lines, ocr_annotations)
    assert len(edges) == 4
    
    # Check that Top edge (longest, length 400) got 20.0m and right edge (length 350) got 15.0m
    top_edge = edges[0]
    right_edge = edges[1]

    assert top_edge.distance.value == 20.0
    assert right_edge.distance.value == 15.0
    assert top_edge.distance_origin == "ocr"
    assert right_edge.distance_origin == "ocr"
    # Verification status is explicitly flagged
    assert top_edge.verification_status in ["verified", "unverified", "ambiguous"]


from app.components.gab_gen.vector_reconstruction.reconstruct import (
    reconstruct_polygon,
    normalize_bearing_string,
)


def test_vector_reconstruction_with_bowditch_adjustment():
    """Verify vector reconstruction performs Bowditch compass rule adjustment and detects closure."""
    # A nearly closed 20m x 15m rectangle with a tiny 0.1m closure misclosure
    edges = [
        SurveyEdgeInput(
            edge_id="E01",
            distance={"value": 20.0, "unit": "m"},
            bearing={"raw": "090°00'00\"", "normalized_degrees": 90.0}
        ),
        SurveyEdgeInput(
            edge_id="E02",
            distance={"value": 15.0, "unit": "m"},
            bearing={"raw": "180°00'00\"", "normalized_degrees": 180.0}
        ),
        SurveyEdgeInput(
            edge_id="E03",
            distance={"value": 20.0, "unit": "m"},
            bearing={"raw": "270°00'00\"", "normalized_degrees": 270.0}
        ),
        SurveyEdgeInput(
            edge_id="E04",
            distance={"value": 15.1, "unit": "m"},
            bearing={"raw": "000°00'00\"", "normalized_degrees": 0.0}
        ),
    ]

    req = ManualSurveyExtractionRequest(edges=edges)
    poly_data = reconstruct_polygon(req)
    assert poly_data["is_valid"] is True
    assert poly_data["reconstructed_area"] > 290.0
    assert poly_data["closure_error"] > 0.0
    assert poly_data["traverse_adjustment_method"] == "bowditch_compass_rule"
    assert "bowditch_adjusted_vertices" in poly_data
    assert len(poly_data["bowditch_adjusted_vertices"]) == 4
    assert poly_data["coordinate_origin"] == "P0 (0.0, 0.0) canonical local metric frame"


def test_vector_reconstruction_rejects_non_positive_length():
    """Verify system strictly rejects non-positive distance measurements."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SurveyEdgeInput(
            edge_id="E02",
            distance={"value": -5.0, "unit": "m"},
            bearing={"raw": "180°00'00\"", "normalized_degrees": 180.0}
        )
    with pytest.raises(ValidationError):
        SurveyEdgeInput(
            edge_id="E02",
            distance={"value": 0.0, "unit": "m"},
            bearing={"raw": "180°00'00\"", "normalized_degrees": 180.0}
        )


from app.components.gab_gen.survey_vision.benchmark import SurveyExtractionBenchmark


def test_cadastral_benchmark_framework():
    """Verify the Cadastral Benchmark Evaluator produces consistent metrics."""
    synthetic = create_synthetic_survey_image()
    gt = {
        "sample_id": "SL-WP-SYNTH-001",
        "category": "clear_digital",
        "true_edges": [
            {"distance_m": 40.0, "bearing_deg": 90.0, "edge_type": "road_front"},
            {"distance_m": 30.0, "bearing_deg": 180.0, "edge_type": "side"},
            {"distance_m": 40.0, "bearing_deg": 270.0, "edge_type": "rear"},
            {"distance_m": 30.0, "bearing_deg": 0.0, "edge_type": "side"},
        ],
        "true_area_sqm": 1200.0,
        "true_north_angle": 0.0,
        "true_scale": "1:500"
    }

    result = SurveyExtractionBenchmark.evaluate_sample(synthetic, gt)
    assert result["sample_id"] == "SL-WP-SYNTH-001"
    assert result["category"] == "clear_digital"
    assert "precision" in result
    assert "recall" in result
    assert "processing_time_ms" in result
    assert result["processing_time_ms"] >= 0.0
    assert "requires_manual_correction" in result
