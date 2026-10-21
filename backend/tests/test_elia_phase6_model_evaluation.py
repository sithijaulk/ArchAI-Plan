from __future__ import annotations

import copy
import json
import math
import numpy as np
import pytest
from pathlib import Path

from app.components.elia_engine.exceptions import ELIAError
from app.components.elia_engine.model_adapter import (
    ModelAdapter,
    TrainedModelAdapter,
    UnavailableModelAdapter,
    prepare_model_input,
    run_model_generation,
)
from app.components.elia_engine.rasterizer import (
    build_raster_metadata,
    rasterize_model_input,
)
from app.components.elia_engine.neural_layout_engine import (
    NeuralGardenLayoutModel,
    generate_canonical_weights,
)
from app.components.elia_engine.service import run_elia
from shapely.geometry import Polygon


def _make_test_master() -> dict:
    return {
        "units": "m",
        "calculated_north_bearing": 0.0,
        "location": {"latitude": 6.9271, "longitude": 79.8612},
        "land_boundary_polygon": [[0, 0], [30, 0], [30, 25], [0, 25]],
        "house_exterior_polygon": [[10, 8], [22, 8], [22, 17], [10, 17]],
        "road_access": {"road_side": "south"},
        "main_entrance": [16, 8],
        "utilities": {
            "well": {"position_m": [4, 21]},
            "septic_tank": {"position_m": [26, 21]},
        },
    }


def _make_test_reqs() -> dict:
    return {
        "landscape": {
            "greenery_density": "medium",
            "tree_count": 3,
            "garden_seating_required": True,
            "pedestrian_path_required": True,
        },
        "concept_style": "Greeny",
        "access": {"driveway_required": True},
        "units": "m",
    }


# 1. Valid artifact loads in a fresh process
def test_valid_artifact_package_loads_in_fresh_process():
    artifact_dir = Path(__file__).resolve().parent.parent / "app" / "components" / "elia_engine" / "model_artifacts" / "garden_layout_v1"
    assert artifact_dir.exists(), "Model artifact directory must exist"

    model = NeuralGardenLayoutModel.load_from_directory(artifact_dir)
    assert model.version == "elia-garden-layout-v1.0"
    assert "conv1.weight" in model.weights

    adapter = TrainedModelAdapter(artifact_dir)
    assert adapter.model_version == "elia-garden-layout-v1.0"


# 2. Missing/incompatible artifact produces controlled error
def test_missing_or_corrupt_artifact_produces_controlled_error(tmp_path):
    # Missing weights.npz
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"model_version": "corrupt-v1"}), encoding="utf-8")

    with pytest.raises(ELIAError) as exc:
        TrainedModelAdapter(tmp_path)
    assert exc.value.code == "ELIA_INVALID_MODEL_ARTIFACT"

    # Checksum mismatch
    weights_path = tmp_path / "weights.npz"
    np.savez_compressed(weights_path, foo=np.zeros(2))
    manifest.write_text(json.dumps({"model_version": "bad-hash", "weights_sha256": "bad_hex"}), encoding="utf-8")

    with pytest.raises(ELIAError) as exc2:
        TrainedModelAdapter(tmp_path)
    assert exc2.value.code == "ELIA_INVALID_MODEL_ARTIFACT"


# 3. Preprocessing channel order and coordinate transforms
def test_preprocessing_channel_order_and_tensor_dimensions():
    master = _make_test_master()
    reqs = _make_test_reqs()

    prepared = prepare_model_input(master, reqs)
    tensor, meta = rasterize_model_input(prepared, grid_size=96)

    assert tensor.shape == (9, 96, 96)
    assert tensor.dtype == np.float32
    assert np.all(np.isfinite(tensor))
    assert 0.0 <= np.min(tensor) and np.max(tensor) <= 1.0

    # Channel 0 has land mask
    assert np.max(tensor[0]) == 1.0
    # Channel 1 has house mask
    assert np.max(tensor[1]) == 1.0
    # Channel 7 has Greeny style active
    assert np.max(tensor[7]) == 1.0
    # Channel 8 has Minimal style inactive
    assert np.max(tensor[8]) == 0.0


# 4. Forward and inverse coordinate consistency
def test_forward_and_inverse_coordinate_consistency():
    poly = Polygon([[0, 0], [40, 0], [40, 30], [0, 30]])
    meta = build_raster_metadata(poly, grid_size=96)

    test_points = [(0.0, 0.0), (20.0, 15.0), (40.0, 30.0), (12.34, 27.89)]
    for wx, wy in test_points:
        u, v = meta.to_grid(wx, wy)
        rx, ry = meta.to_world(u, v)
        assert math.isclose(wx, rx, abs_tol=1e-5), f"X mismatch: {wx} vs {rx}"
        assert math.isclose(wy, ry, abs_tol=1e-5), f"Y mismatch: {wy} vs {ry}"


# 5. Required missing geometry is not fabricated
def test_missing_required_geometry_is_not_fabricated():
    incomplete_master = _make_test_master()
    del incomplete_master["land_boundary_polygon"]

    with pytest.raises(ELIAError) as exc:
        prepare_model_input(incomplete_master, _make_test_reqs())
    assert exc.value.code == "ELIA_MISSING_LAND_BOUNDARY"


# 6. Malformed/non-finite model output is rejected
def test_malformed_or_non_finite_model_output_rejected():
    master = _make_test_master()
    reqs = _make_test_reqs()

    class CorruptHeatmapAdapter:
        model_version = "corrupt-output-v1"

        def infer(self, prepared_input):
            # Return NaN in outdoor element coordinates
            return {
                "schema_version": "1.0",
                "version": "1.0",
                "coordinate_reference": "meters",
                "access": {},
                "site_analysis": {},
                "utility_safety": {},
                "environment": {},
                "metrics": {},
                "outdoor_elements": [{"json_id": "BAD_01", "type": "garden_seating", "position": [float("nan"), 10.0], "units": "m"}],
            }

    with pytest.raises(ELIAError) as exc:
        run_model_generation(master, reqs, "test_corrupt", CorruptHeatmapAdapter())
    assert exc.value.code == "ELIA_INVALID_MODEL_OUTPUT"


# 7. Model unavailable without silent fallback
def test_trained_model_unavailable_without_silent_fallback():
    master = _make_test_master()
    reqs = _make_test_reqs()

    # UnavailableModelAdapter must raise 503 ELIA_MODEL_UNAVAILABLE
    with pytest.raises(ELIAError) as exc:
        run_model_generation(master, reqs, "test_unavail", UnavailableModelAdapter())
    assert exc.value.code == "ELIA_MODEL_UNAVAILABLE"
    assert exc.value.status_code == 503


# 8. Real artifact inference produces valid exterior landscape
def test_real_artifact_inference_pipeline_execution():
    master = _make_test_master()
    reqs = _make_test_reqs()

    adapter = TrainedModelAdapter()
    result, outcome = run_model_generation(master, reqs, "real_model_run", adapter)

    assert result["generation_mode"] == "trained_model"
    assert result["model_version"] == "elia-garden-layout-v1.0"
    assert "metrics" in result
    assert result["metrics"]["trees_placed"] > 0
    assert len(result["vegetation_nodes"]) > 0

    # Verify all placed trees have provenance marked as trained_model
    for node in result["vegetation_nodes"]:
        assert node.get("source") == "trained_model"
        assert "model_placement_score" in node

    # Verify validation was executed independently
    assert "validation_summary" in result
    assert "rule_evaluations" in result


# 9. Raw and repaired outputs remain distinguishable
def test_model_placed_vs_planner_routed_distinction():
    master = _make_test_master()
    reqs = _make_test_reqs()

    adapter = TrainedModelAdapter()
    result, _ = run_model_generation(master, reqs, "distinguish_run", adapter)

    # Trees come from model
    for v in result.get("vegetation_nodes", []):
        assert v["source"] == "trained_model"

    # Pedestrian paths and driveways come from deterministic planner
    for elem in result.get("outdoor_elements", []):
        if elem["type"] == "pedestrian_path":
            assert elem["source"] == "deterministic_planner"


# 10. Upstream Master JSON remains completely immutable
def test_upstream_master_json_is_not_mutated():
    original_master = _make_test_master()
    master_copy = copy.deepcopy(original_master)
    reqs = _make_test_reqs()

    adapter = TrainedModelAdapter()
    run_model_generation(master_copy, reqs, "immutability_test", adapter)

    assert master_copy == original_master, "Master JSON must not be mutated by inference or decoding"
