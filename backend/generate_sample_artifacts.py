"""
Generate sample PDF artifacts for Phase 8 audit evidence.
Produces:
1. multi_floor_building_report.pdf
2. scale_1_50_room_report.pdf
3. draft_watermarked_report.pdf
"""
import os
import sys
from copy import deepcopy

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath("."))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models.project import Project
from app.models.user import User
from app.components.esai_engine.parser import StructuralInputParser
from app.components.esai_engine.geometry import compute_geometry_fingerprint
from app.components.esai_engine.reporting.contracts import (
    PdfReportRequest,
    ReportMode,
    ReportScope,
)
from app.components.esai_engine.service import EsaiEngineService
from app.components.esai_engine.reporting.report_service import EsaiReportService
from tests.esai.fixtures import MULTI_FLOOR_PROJECT_FIXTURE

ARTIFACT_DIR = r"C:\Users\user\.gemini\antigravity-ide\brain\4858d3dc-0ac6-4ef5-a9aa-504db8fbd533"

def build_test_project(db):
    user = User(
        full_name="Lead Architect",
        email="architect@archaiplan.internal",
        password_hash="pw_hash",
        role="architect",
        is_active=True,
    )
    db.add(user)
    db.commit()

    mj = deepcopy(MULTI_FLOOR_PROJECT_FIXTURE)
    mj["project_name"] = "Skyline Executive Residence"
    mj["author"] = "ArchAI-Plan ESAI-Engine"

    # Add a room without design to test missing design disclosures
    mj["floor_plan"]["floors"][1]["rooms"].append({
        "room_id": "RM_STORAGE_01",
        "name": "Unfinished Utility & Storage",
        "room_type": "storage",
        "polygon": [[2.5, 0.0], [5.0, 0.0], [5.0, 2.5], [2.5, 2.5]],
        "doors": [{"id": "D_STOR", "start": [2.5, 0.5], "end": [2.5, 1.3], "leaf_width": 0.8}],
        "windows": [],
    })

    structural_input = StructuralInputParser.parse(mj)
    geo_fp = compute_geometry_fingerprint(structural_input)

    mj["interior_layout"] = {
        "version": "1.0",
        "design_revision": 3,
        "preference_revision": 2,
        "geometry_fingerprint": geo_fp,
        "preferences": {
            "building": {"style": "contemporary_warm_minimalism", "palette": "neutral_stone"},
            "rooms": {
                "RM_BATH_01": {"bathtub": False, "hot_water": True},
            },
        },
        "designs": {
            "rooms": {
                "RM_LIVING_01": {
                    "room_id": "RM_LIVING_01",
                    "floor_id": "fl_0",
                    "room_name": "Formal Living Room",
                    "room_type": "living_room",
                    "design_revision": 3,
                    "polygon": [[0.0, 0.0], [6.0, 0.0], [6.0, 5.0], [0.0, 5.0]],
                    "area_sqm": 30.0,
                    "furniture": [
                        {
                            "instance_id": "inst_sofa_01",
                            "asset_id": "sofa-3seat-01",
                            "asset_name": "Curved 3-Seater Sofa",
                            "category": "furniture",
                            "dimensions": {"width": 2.4, "depth": 0.95, "height": 0.82},
                            "position": {"x": 3.0, "y": 2.5},
                            "rotation_deg": 0.0,
                            "material": "Italian Bouclé Fabric",
                            "is_locked": True,
                        },
                        {
                            "instance_id": "inst_table_01",
                            "asset_id": "coffee-table-01",
                            "asset_name": "Travertine Coffee Table",
                            "category": "furniture",
                            "dimensions": {"width": 1.2, "depth": 0.7, "height": 0.42},
                            "position": {"x": 3.0, "y": 3.6},
                            "rotation_deg": 0.0,
                            "material": "Natural Roman Travertine",
                        },
                    ],
                    "generation_metadata": {
                        "generations": 25,
                        "population_size": 40,
                        "seed": 101,
                        "fitness_score": 0.942,
                        "hard_constraints_passed": True,
                        "overlap_area_sqm": 0.0,
                        "out_of_bounds_area_sqm": 0.0,
                        "door_violations": 0,
                        "window_violations": 0,
                        "ergonomic_score": 0.965,
                        "runtime_seconds": 1.48,
                    },
                    "validation": {
                        "is_valid": True,
                        "hard_constraints_passed": True,
                        "rules_evaluated": [
                            {
                                "rule_id": "CLR_SEAT_TABLE",
                                "rule_description": "Clearance between seating and coffee table",
                                "standard_source": "Neufert Architects' Data",
                                "standard_edition": "4th Edition",
                                "standard_section": "Living Spaces p. 284",
                                "status": "PASS",
                                "severity": "CRITICAL",
                                "required_clearance_m": 0.45,
                                "message": "Clearance 0.52m meets Neufert requirement (>= 0.45m)",
                            }
                        ],
                    },
                },
                "RM_KITCHEN_01": {
                    "room_id": "RM_KITCHEN_01",
                    "floor_id": "fl_0",
                    "room_name": "Modular Kitchen",
                    "room_type": "kitchen",
                    "design_revision": 3,
                    "polygon": [[6.0, 0.0], [10.0, 0.0], [10.0, 4.0], [6.0, 4.0]],
                    "area_sqm": 16.0,
                    "furniture": [
                        {
                            "instance_id": "inst_sink_01",
                            "asset_id": "sink-undermount-01",
                            "asset_name": "Undermount Double Sink",
                            "category": "kitchen",
                            "dimensions": {"width": 0.85, "depth": 0.55, "height": 0.88},
                            "position": {"x": 8.0, "y": 0.6},
                            "rotation_deg": 0.0,
                            "material": "Brushed Stainless Steel",
                        }
                    ],
                    "validation": {"is_valid": True, "hard_constraints_passed": True},
                },
                "RM_BATH_01": {
                    "room_id": "RM_BATH_01",
                    "floor_id": "fl_1",
                    "room_name": "Attached Bathroom",
                    "room_type": "bathroom",
                    "design_revision": 3,
                    "polygon": [[0.0, 0.0], [2.5, 0.0], [2.5, 2.5], [0.0, 2.5]],
                    "area_sqm": 6.25,
                    "furniture": [
                        {
                            "instance_id": "inst_vanity_01",
                            "asset_id": "bath-vanity-01",
                            "asset_name": "Floating Vanity Basin",
                            "category": "bathroom",
                            "dimensions": {"width": 1.0, "depth": 0.5, "height": 0.85},
                            "position": {"x": 1.25, "y": 0.5},
                            "rotation_deg": 0.0,
                            "material": "Corian Surface",
                        }
                    ],
                    "validation": {"is_valid": True, "hard_constraints_passed": True},
                },
            }
        },
    }

    project = Project(
        project_name="Skyline Executive Residence",
        master_json=mj,
        revision=1,
    )
    db.add(project)
    db.commit()
    return project

def main():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    project = build_test_project(db)
    esai_service = EsaiEngineService(db)
    report_service = EsaiReportService(esai_service)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    print("1. Generating Multi-Floor Building Report (Draft)...")
    req_building = PdfReportRequest(
        scope=ReportScope.BUILDING,
        mode=ReportMode.DRAFT,
        author_name="ArchAI-Plan ESAI-Engine Audit Team",
        notes="Official multi-floor audit sample verifying room completeness, schedules, and missing room disclosure.",
    )
    pdf_bldg, _ = report_service.generate_pdf_report(project, req_building)
    bldg_path = os.path.join(ARTIFACT_DIR, "multi_floor_building_report.pdf")
    with open(bldg_path, "wb") as f:
        f.write(pdf_bldg)
    print(f"   -> Saved: {bldg_path} ({len(pdf_bldg)} bytes)")

    print("2. Generating 1:50 Physical Scale Room Report...")
    req_scale = PdfReportRequest(
        scope=ReportScope.ROOM,
        room_ids=["RM_BATH_01"],
        mode=ReportMode.DRAFT,
        drawing_scale_mode="1:50",
        author_name="ArchAI-Plan ESAI-Engine Audit Team",
        notes="Scale audit sample verifying true physical 1:50 vector drawing output.",
    )
    pdf_scale, _ = report_service.generate_pdf_report(project, req_scale)
    scale_path = os.path.join(ARTIFACT_DIR, "scale_1_50_room_report.pdf")
    with open(scale_path, "wb") as f:
        f.write(pdf_scale)
    print(f"   -> Saved: {scale_path} ({len(pdf_scale)} bytes)")

    print("3. Generating Draft Watermarked Living Room Report...")
    req_draft = PdfReportRequest(
        scope=ReportScope.ROOM,
        room_ids=["RM_LIVING_01"],
        mode=ReportMode.DRAFT,
        author_name="ArchAI-Plan ESAI-Engine Audit Team",
        notes="Draft sample verifying diagonal draft watermark, Neufert citations, and GA metrics.",
    )
    pdf_draft, _ = report_service.generate_pdf_report(project, req_draft)
    draft_path = os.path.join(ARTIFACT_DIR, "draft_watermarked_report.pdf")
    with open(draft_path, "wb") as f:
        f.write(pdf_draft)
    print(f"   -> Saved: {draft_path} ({len(pdf_draft)} bytes)")

    print("All sample PDFs successfully generated!")

if __name__ == "__main__":
    main()
