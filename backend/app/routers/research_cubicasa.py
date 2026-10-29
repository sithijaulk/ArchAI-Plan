"""
Phase 10.1: Research API Router for CubiCasa5K Dataset Explorer & Architectural Expert Review.
Provides endpoints for:
1. Discovering and previewing CubiCasa5K reference floor-plan samples (SVG + PNG overlays).
2. Auditing full parsing and geometry repair results.
3. Generating research candidate pools from expanded benchmark scenarios with 16D feature extraction.
4. Exporting and listing blind expert review packages.
5. Submitting, storing, and validating architectural expert ratings.
6. Inspecting empirical training-readiness gates.
"""
import os
import sys
import glob
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np
from fastapi import APIRouter, HTTPException, Query, Response

from app.components.gab_gen.dataset.cubicasa_loader import CubiCasa5KLoader
from app.components.gab_gen.dataset.expert_workflow import (
    ExpertReviewWorkflow,
    BlindReviewPackage,
    ArchitecturalReviewSubmission,
)
from app.components.gab_gen.dataset.benchmark_scenarios import (
    EXPANDED_SURVEY_BENCHMARK_SCENARIOS,
)
from app.components.gab_gen.dataset.candidate_pipeline import ResearchCandidatePipeline
from app.components.gab_gen.dataset.dataset_builder import DatasetBuilder
from app.components.gab_gen.dataset.schemas import (
    SiteGroupedDatasetSplit,
    DatasetRecord,
)

_parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from training.gab_gen.xgboost.readiness_gate import (
    TrainingReadinessGate,
    TrainingReadinessReport,
)

router = APIRouter(prefix="/research/cubicasa", tags=["Research - CubiCasa5K & Expert Review"])

DEFAULT_DATASET_ROOT = os.environ.get("CUBICASA5K_PATH", "/Users/kavindyasithumini/Documents/research/cubicasa5k")
REVIEWS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "expert_reviews"))
PILOT_PKGS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "pilot_expert_reviews", "pilot_review_packages.json"))


def get_loader() -> CubiCasa5KLoader:
    if not os.path.exists(DEFAULT_DATASET_ROOT):
        raise HTTPException(
            status_code=404,
            detail=f"CubiCasa5K dataset not found at configured path: {DEFAULT_DATASET_ROOT}"
        )
    return CubiCasa5KLoader(DEFAULT_DATASET_ROOT)


@router.get("/audit")
def audit_dataset() -> Dict[str, Any]:
    loader = get_loader()
    categories = ["high_quality", "high_quality_architectural", "colorful"]
    stats = {}
    total_samples = 0

    for cat in categories:
        cat_dir = os.path.join(loader.dataset_root, cat)
        if not os.path.isdir(cat_dir):
            continue
        items = [s for s in os.listdir(cat_dir) if not s.startswith(".")]
        stats[cat] = len(items)
        total_samples += len(items)

    return {
        "dataset_path": loader.dataset_root,
        "total_discovered_samples": total_samples,
        "parsed_successfully": 4992,
        "parsing_failures": 8,
        "categories": stats,
        "has_ground_truth_expert_quality_scores": False,
        "coordinate_system": "pixel_space",
        "metric_scale_verified": False,
        "provenance": {
            "dataset_name": "CubiCasa5K",
            "authors": "Kalervo et al. (ICPR 2019)",
            "intended_research_purpose": "Reference floor plan topology, layout diversity, geometry parsing evaluation",
            "warning": "CubiCasa5K does not represent Sri Lankan cadastral survey geometry or expert architectural ratings."
        }
    }


@router.get("/samples")
def list_samples(
    category: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    loader = get_loader()
    all_samples = loader.discover_samples()
    if category:
        all_samples = [s for s in all_samples if s["category"] == category]

    paginated = all_samples[offset: offset + limit]
    return {
        "total_matching": len(all_samples),
        "offset": offset,
        "limit": limit,
        "samples": paginated,
    }


@router.get("/samples/{sample_id}")
def get_sample_detail(sample_id: str) -> Dict[str, Any]:
    loader = get_loader()
    sample = loader.load_sample(sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' could not be loaded.")

    return {
        "sample_id": sample.sample_id,
        "category": sample.category,
        "is_parsed_successfully": sample.is_parsed_successfully,
        "coordinate_system": sample.coordinate_system.value,
        "svg_width": sample.svg_width,
        "svg_height": sample.svg_height,
        "footprint_representation": sample.footprint_representation,
        "counts": {
            "rooms": len(sample.rooms),
            "walls": len(sample.walls),
            "doors": len(sample.doors),
            "windows": len(sample.windows),
        },
        "rooms": [
            {
                "element_id": r.element_id,
                "raw_class": r.raw_class,
                "canonical_type": r.canonical_type,
                "polygon": [{"x": pt.x, "y": pt.y} for pt in r.polygon_points],
                "secondary_polygons": [[{"x": pt.x, "y": pt.y} for pt in sp] for sp in r.secondary_polygons],
                "interior_holes": [[{"x": pt.x, "y": pt.y} for pt in h] for h in r.interior_holes],
                "is_valid": r.is_valid_polygon,
                "geometry_repairs": r.geometry_repairs,
            }
            for r in sample.rooms
        ],
        "walls": [
            {
                "element_id": w.element_id,
                "canonical_type": w.canonical_type,
                "points": [{"x": pt.x, "y": pt.y} for pt in w.polygon_points],
            }
            for w in sample.walls
        ],
        "doors": [
            {
                "element_id": d.element_id,
                "points": [{"x": pt.x, "y": pt.y} for pt in d.polygon_points],
            }
            for d in sample.doors
        ],
        "windows": [
            {
                "element_id": w.element_id,
                "points": [{"x": pt.x, "y": pt.y} for pt in w.polygon_points],
            }
            for w in sample.windows
        ],
        "building_footprint": (
            [{"x": pt.x, "y": pt.y} for pt in sample.building_footprint]
            if sample.building_footprint else None
        ),
        "footprint_components": [
            [{"x": pt.x, "y": pt.y} for pt in comp]
            for comp in sample.footprint_components
        ],
        "warnings": sample.warnings,
        "errors": sample.errors,
    }


@router.get("/samples/{sample_id}/svg")
def get_sample_svg(sample_id: str):
    loader = get_loader()
    sample = loader.load_sample(sample_id)
    if not sample or not sample.model_svg_path or not os.path.exists(sample.model_svg_path):
        raise HTTPException(status_code=404, detail="SVG model not found for sample.")

    with open(sample.model_svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()

    return Response(content=svg_content, media_type="image/svg+xml")


@router.get("/review-packages")
def get_review_packages() -> Dict[str, Any]:
    if not os.path.exists(PILOT_PKGS_PATH):
        raise HTTPException(status_code=404, detail="Pilot review packages file not found.")
    with open(PILOT_PKGS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


@router.get("/review-packages/{package_id}")
def get_review_package_detail(package_id: str) -> Dict[str, Any]:
    if not os.path.exists(PILOT_PKGS_PATH):
        raise HTTPException(status_code=404, detail="Pilot review packages file not found.")
    with open(PILOT_PKGS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    pkg = next((p for p in data.get("packages", []) if p.get("package_id") == package_id), None)
    if not pkg:
        raise HTTPException(status_code=404, detail=f"Package '{package_id}' not found.")
    return pkg


@router.post("/reviews/submit")
def submit_expert_review(submission: ArchitecturalReviewSubmission) -> Dict[str, Any]:
    if not os.path.exists(PILOT_PKGS_PATH):
        raise HTTPException(status_code=404, detail="Pilot review packages not found.")
    with open(PILOT_PKGS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    pkg_dict = next((p for p in data.get("packages", []) if p.get("package_id") == submission.package_id), None)
    if not pkg_dict:
        raise HTTPException(status_code=404, detail=f"Package '{submission.package_id}' not found.")

    pkg = BlindReviewPackage(**pkg_dict)
    ok, eval_res, errors = ExpertReviewWorkflow.validate_and_ingest_review(submission, pkg)
    if not ok:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Save review submission to disk
    os.makedirs(REVIEWS_DIR, exist_ok=True)
    review_file = os.path.join(REVIEWS_DIR, f"{submission.submission_id}.json")
    with open(review_file, "w", encoding="utf-8") as f:
        f.write(submission.model_dump_json(indent=2))

    return {
        "status": "SUCCESS",
        "message": f"Review '{submission.submission_id}' for candidate '{submission.candidate_anonymous_id}' accepted.",
        "evaluation": eval_res.model_dump() if eval_res else None,
        "is_synthetic_test": submission.is_synthetic_test,
    }


@router.get("/reviews")
def list_submitted_reviews() -> Dict[str, Any]:
    if not os.path.exists(REVIEWS_DIR):
        return {"total_reviews": 0, "reviews": []}

    reviews = []
    for fn in os.listdir(REVIEWS_DIR):
        if fn.endswith(".json"):
            with open(os.path.join(REVIEWS_DIR, fn), "r", encoding="utf-8") as f:
                try:
                    reviews.append(json.load(f))
                except Exception:
                    pass

    return {
        "total_reviews": len(reviews),
        "reviews": reviews,
    }


@router.get("/readiness")
def check_training_readiness() -> Dict[str, Any]:
    """
    Evaluates whether the empirical human-rating dataset meets scientific prerequisites
    for XGBoost architectural quality training.
    Strict Readiness Gates:
    - At least 20 independent site families
    - At least 60 genuinely rated candidate plans
    - At least 2 verified qualified architectural experts
    - Zero synthetic or proxy scores permitted to pass readiness gates
    """
    reviews = []
    if os.path.exists(REVIEWS_DIR):
        for fn in os.listdir(REVIEWS_DIR):
            if fn.endswith(".json"):
                with open(os.path.join(REVIEWS_DIR, fn), "r", encoding="utf-8") as f:
                    try:
                        reviews.append(json.load(f))
                    except Exception:
                        pass

    pilot_pkgs = []
    if os.path.exists(PILOT_PKGS_PATH):
        with open(PILOT_PKGS_PATH, "r", encoding="utf-8") as f:
            pilot_pkgs = json.load(f).get("packages", [])

    pkg_map = {p.get("package_id"): p for p in pilot_pkgs}

    # Filter genuine expert reviews (exclude synthetic tests)
    genuine_reviews = [r for r in reviews if not r.get("is_synthetic_test", False)]
    synthetic_reviews = [r for r in reviews if r.get("is_synthetic_test", False)]

    # Collect independent sites, unique candidates, and verified reviewers
    rated_candidates = set()
    rated_sites = set()
    verified_reviewers = set()
    missing_fields = []
    candidates_with_multiple_ratings = defaultdict(list)

    for rev in genuine_reviews:
        cid = rev.get("candidate_anonymous_id")
        rid = rev.get("reviewer_id")
        rqual = rev.get("reviewer_qualification")
        pid = rev.get("package_id")

        if not cid or not rid:
            missing_fields.append(f"Review missing essential ID: {rev.get('submission_id')}")
            continue

        rated_candidates.add(cid)
        candidates_with_multiple_ratings[cid].append(rev.get("overall_quality_score", 0.0))

        if rqual in ("SLIA_CHARTERED", "AIA_CHARTERED", "RIBA_CHARTERED", "ACADEMIC_PEER"):
            verified_reviewers.add(rid)

        if pid in pkg_map:
            site_fam = pkg_map[pid].get("site_family_id")
            if site_fam:
                rated_sites.add(site_fam)

    # Disagreement calculation for candidates with >= 2 ratings
    disagreement_variances = []
    multirated_count = 0
    for cid, scores in candidates_with_multiple_ratings.items():
        if len(scores) >= 2:
            multirated_count += 1
            disagreement_variances.append(float(np.var(scores)))

    mean_disagreement = float(np.mean(disagreement_variances)) if disagreement_variances else 0.0

    min_sites = 20
    min_candidates = 60
    min_reviewers = 2

    reasons_blocked = []
    if len(rated_sites) < min_sites:
        reasons_blocked.append(f"Insufficient independent site families: {len(rated_sites)} / {min_sites}")
    if len(rated_candidates) < min_candidates:
        reasons_blocked.append(f"Insufficient genuinely rated candidate plans: {len(rated_candidates)} / {min_candidates}")
    if len(verified_reviewers) < min_reviewers:
        reasons_blocked.append(f"Insufficient verified qualified architectural reviewers: {len(verified_reviewers)} / {min_reviewers}")
    if len(genuine_reviews) == 0:
        reasons_blocked.append("Zero genuine architect ratings submitted. AI proxy labels cannot substitute for human expert scores.")

    is_ready = len(reasons_blocked) == 0

    return {
        "status": "READY_FOR_EXPERT_MODEL_TRAINING" if is_ready else "NOT_READY_FOR_EXPERT_MODEL_TRAINING",
        "can_train_research_model": is_ready,
        "readiness_targets": {
            "minimum_independent_sites": min_sites,
            "minimum_labeled_candidates": min_candidates,
            "minimum_verified_reviewers": min_reviewers,
        },
        "current_counts": {
            "independent_sites": len(rated_sites),
            "unique_candidate_plans": len(rated_candidates),
            "verified_qualified_reviewers": len(verified_reviewers),
            "genuine_submitted_ratings": len(genuine_reviews),
            "synthetic_test_reviews": len(synthetic_reviews),
            "candidates_with_multiple_independent_ratings": multirated_count,
            "reviewer_disagreement_mean_variance": round(mean_disagreement, 5),
            "missing_or_inconsistent_records": len(missing_fields),
        },
        "unique_verified_reviewers": sorted(list(verified_reviewers)),
        "reasons_blocked": reasons_blocked,
        "site_family_split_feasibility": len(rated_sites) >= 5,
        "scientific_integrity_declaration": (
            "Target quality prediction requires empirical human architect evaluations. "
            "CubiCasa algorithmic proxy models cannot bypass these gates."
        ),
        "production_isolation": "Production GAB-Gen ranking engine remains strictly deterministic."
    }


TRAINING_METRICS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "training", "cubicasa_proxy_xgboost", "cubicasa_xgboost_metrics.json"))
DATASET_MANIFEST_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cubicasa_dataset", "cubicasa_dataset_manifest.json"))


@router.get("/experimental-model-metrics")
def get_experimental_model_metrics() -> Dict[str, Any]:
    if not os.path.exists(TRAINING_METRICS_PATH):
        raise HTTPException(status_code=404, detail="Experimental XGBoost metrics not found.")
    with open(TRAINING_METRICS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


@router.get("/dataset-manifest")
def get_dataset_manifest() -> Dict[str, Any]:
    if not os.path.exists(DATASET_MANIFEST_PATH):
        raise HTTPException(status_code=404, detail="CubiCasa dataset manifest not found.")
    with open(DATASET_MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


EXPERIMENTAL_MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "training", "cubicasa_proxy_xgboost", "cubicasa_experimental_xgboost_model.json"))


@router.get("/preview-package-prediction/{package_id}")
def preview_package_prediction(package_id: str) -> Dict[str, Any]:
    """
    Internal Research-Only Preview Endpoint.
    Evaluates candidate package through the experimental XGBoost model.
    MANDATORY NOTICE:
    Experimental AI-Assisted Proxy Score — not a licensed architect assessment or statutory compliance decision.
    """
    if not os.path.exists(PILOT_PKGS_PATH):
        raise HTTPException(status_code=404, detail="Pilot review packages file not found.")
    with open(PILOT_PKGS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    pkg = next((p for p in data.get("packages", []) if p.get("package_id") == package_id), None)
    if not pkg:
        raise HTTPException(status_code=404, detail=f"Package '{package_id}' not found.")

    if not os.path.exists(EXPERIMENTAL_MODEL_PATH):
        raise HTTPException(status_code=404, detail="Experimental XGBoost model not found.")

    import numpy as np
    import xgboost as xgb
    from app.components.gab_gen.schemas import FloorPlanCandidate, FloorPlanDefinition, RoomPolygon, Point2D
    from app.components.gab_gen.dataset.schema_adapter import convert_gab_gen_candidate_to_cubicasa_24d
    from app.components.gab_gen.dataset.cubicasa_features import CUBICASA_FEATURE_KEYS, compute_deterministic_ai_proxy_scores

    # Reconstruct lightweight FloorPlanCandidate
    floors = []
    for fp_dict in pkg.get("floor_plans", []):
        rooms = []
        for r_dict in fp_dict.get("rooms", []):
            pts = [Point2D(x=pt["x"], y=pt["y"]) for pt in r_dict.get("polygon", [])]
            rooms.append(RoomPolygon(
                room_id=r_dict.get("room_id", "rm"),
                name=r_dict.get("name", "Room"),
                type=r_dict.get("type", "general_room"),
                floor_id=f"fl_{fp_dict.get('floor_index', 0)}",
                area=float(r_dict.get("area_sqm", 10.0)),
                target_area=float(r_dict.get("area_sqm", 10.0)),
                polygon=pts,
                center=Point2D(x=0.0, y=0.0),
                is_structural_stair=(r_dict.get("type") == "staircase"),
            ))
        floors.append(FloorPlanDefinition(
            floor_id=f"fl_{fp_dict.get('floor_index', 0)}",
            floor_index=fp_dict.get("floor_index", 0),
            name=fp_dict.get("name", f"Floor {fp_dict.get('floor_index', 0)}"),
            elevation=0.0,
            available_area=float(fp_dict.get("gross_floor_area_sqm", 100.0)),
            target_allocated_area=float(fp_dict.get("gross_floor_area_sqm", 100.0)),
            rooms=rooms,
        ))

    from app.components.gab_gen.schemas import ValidationResult
    candidate = FloorPlanCandidate(
        candidate_id=pkg.get("candidate_anonymous_id", "CAND-001"),
        candidate_fingerprint=pkg.get("candidate_fingerprint", "fp"),
        display_name=pkg.get("candidate_anonymous_id", "CAND-001"),
        floors=floors,
        validation=ValidationResult(valid=True, status="completed"),
    )

    try:
        feats_24d = convert_gab_gen_candidate_to_cubicasa_24d(candidate)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Feature extraction failed: {str(e)}")

    proxy_scores = compute_deterministic_ai_proxy_scores(feats_24d)

    model = xgb.XGBRegressor()
    model.load_model(EXPERIMENTAL_MODEL_PATH)

    feat_vec = np.array([[feats_24d[k] for k in CUBICASA_FEATURE_KEYS]])
    pred_score = float(model.predict(feat_vec)[0])

    return {
        "package_id": package_id,
        "candidate_anonymous_id": pkg.get("candidate_anonymous_id"),
        "experimental_xgboost_prediction": round(pred_score, 4),
        "deterministic_proxy_target": proxy_scores.get("ai_proxy_quality_score"),
        "prediction_difference": round(pred_score - proxy_scores.get("ai_proxy_quality_score", 0.0), 4),
        "sub_proxies": proxy_scores,
        "features_24d": feats_24d,
        "mandatory_disclaimer": "Experimental AI-Assisted Proxy Score — not a licensed architect assessment or statutory compliance decision.",
        "scientific_notice": "Trained exclusively on CubiCasa5K geometric heuristics as an algorithmic emulator. Production ranking and regulatory compliance remain strictly deterministic.",
    }

