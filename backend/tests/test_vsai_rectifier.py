import os
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from io import BytesIO

os.environ["DATABASE_URL"] = "mysql+pymysql://test:test@localhost/archai_test"

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.component_run import ComponentRun, ProjectOutput
from app.models.project import Project
from app.services.vsai_rectifier import (
    RectificationDefinition,
    VsaiInputError,
    prepare_master_json,
    run_vsai_rectifier,
)
from app.services.vsai_rules import RuleDefinition, evaluate_rules
from app.utils.vsai_geometry import GeometryValidationError, validate_floor_plan


def sample_master(project_id="project-1"):
    return {
        "project_id": project_id,
        "project_name": "Sample House",
        "land_info": {"orientation": "north"},
        "buildable_footprint": {"source": "baseline"},
        "floor_plan": {
            "rooms": [
                {"id": "living", "name": "Living", "polygon": [[0, 0], [4, 0], [4, 4], [0, 4]]},
                {"id": "bedroom", "name": "Bedroom", "polygon": [[4, 0], [8, 0], [8, 4], [4, 4]]},
            ],
            "structural_elements": [
                {"id": "column-1", "polygon": [[1, 1], [1.2, 1], [1.2, 1.2], [1, 1.2]]}
            ],
        },
        "structural_rectification": {},
        "interior_layout": {"furniture": ["sofa"]},
        "exterior_landscape": {"garden": True},
        "processing": {
            "gab_gen": {"status": "completed"},
            "vsai_rectifier": {"status": "pending"},
            "esai_engine": {"status": "pending"},
            "elia_engine": {"status": "pending"},
        },
    }


class VsaiGeometryAndRulesTests(unittest.TestCase):
    def test_valid_room_and_structural_polygons_are_accepted(self):
        geometry = validate_floor_plan(sample_master()["floor_plan"])
        self.assertEqual(len(geometry["rooms"]), 2)
        self.assertEqual(len(geometry["structural_elements"]), 1)

    def test_degenerate_and_self_intersecting_polygons_are_rejected(self):
        for polygon in (
            [[0, 0], [1, 1], [2, 2]],
            [[0, 0], [2, 2], [0, 2], [2, 0]],
        ):
            with self.subTest(polygon=polygon), self.assertRaises(GeometryValidationError):
                validate_floor_plan({"rooms": [{"id": "bad", "polygon": polygon}]})

    def test_malformed_and_nonfinite_coordinates_are_rejected(self):
        for polygon in (
            [[0, 0], [1, 0], [float("nan"), 1]],
            [[0, 0], [1, 0], [1, "x"]],
        ):
            with self.subTest(polygon=polygon), self.assertRaises(GeometryValidationError):
                validate_floor_plan({"rooms": [{"id": "bad", "polygon": polygon}]})

    def test_unconfigured_vastu_rules_are_never_reported_as_passed(self):
        result = run_vsai_rectifier(sample_master())["result"]
        self.assertEqual(result["score_status"], "unavailable")
        self.assertIsNone(result["vastu_compliance_score"])
        self.assertTrue(all(rule["status"] == "unconfigured" for rule in result["rule_results"]))

    def test_rule_results_are_repeatable_and_weights_are_applied_only_to_evaluated_rules(self):
        rules = (
            RuleDefinition("test.pass", "test", "Pass", True, 2.0, lambda _: True),
            RuleDefinition("test.fail", "test", "Fail", True, 1.0, lambda _: False),
            RuleDefinition("test.missing", "test", "Missing", True, 5.0, lambda _: None),
            RuleDefinition("test.unconfigured", "test", "Not available"),
        )
        first = evaluate_rules(sample_master(), rules)
        second = evaluate_rules(sample_master(), rules)
        self.assertEqual(first, second)
        self.assertEqual(first["vastu_compliance_score"], 66.67)
        self.assertEqual(first["rule_coverage"]["evaluated"], 2)
        self.assertEqual(first["rule_coverage"]["unevaluable"], 1)
        self.assertEqual(first["rule_coverage"]["unconfigured"], 1)

    def test_room_overlap_is_reported_without_automatic_geometry_changes(self):
        document = sample_master()
        document["floor_plan"]["rooms"][1]["polygon"] = [[3, 0], [7, 0], [7, 4], [3, 4]]
        result = run_vsai_rectifier(document)["result"]
        self.assertEqual(result["geometry_checks"]["room_overlaps"], [
            {"first_room_id": "living", "second_room_id": "bedroom"}
        ])
        self.assertEqual(result["corrections"], [])

    def test_valid_configured_correction_preserves_original_geometry(self):
        document = sample_master()
        original = deepcopy(document["floor_plan"]["rooms"][0]["polygon"])
        definition = RectificationDefinition(
            "test.translate",
            "rooms",
            lambda polygon: [[x - 0.1, y] for x, y in polygon],
            "Test-only configured translation.",
        )
        result = run_vsai_rectifier(document, rectifications=(definition,))["result"]
        self.assertEqual(result["original_geometry"]["rooms"][0]["polygon"], original)
        self.assertNotEqual(
            result["corrected_geometry"]["rooms"][0]["polygon"],
            result["original_geometry"]["rooms"][0]["polygon"],
        )
        self.assertEqual(result["corrections"][0]["status"], "applied")
        self.assertEqual(document["floor_plan"]["rooms"][0]["polygon"], original)

    def test_invalid_correction_is_not_applied(self):
        document = sample_master()
        original = deepcopy(document["floor_plan"]["rooms"][0]["polygon"])
        definition = RectificationDefinition(
            "test.invalid",
            "rooms",
            lambda _polygon: [[0, 0], [2, 2], [0, 2], [2, 0]],
            "Invalid test correction.",
        )
        result = run_vsai_rectifier(document, rectifications=(definition,))["result"]
        self.assertEqual(result["corrected_geometry"]["rooms"][0]["polygon"], original)
        self.assertEqual(result["corrections"][0]["status"], "rejected")

    def test_correction_introducing_room_overlap_is_rejected(self):
        document = sample_master()
        definition = RectificationDefinition(
            "test.overlap",
            "rooms",
            lambda polygon: [[x + 0.5, y] for x, y in polygon],
            "Test correction that overlaps adjacent room.",
        )
        result = run_vsai_rectifier(document, rectifications=(definition,))["result"]
        self.assertEqual(result["corrections"][0]["status"], "rejected")

    def test_supplied_baseline_preserves_existing_downstream_outputs(self):
        stored = sample_master()
        supplied = sample_master()
        supplied["floor_plan"]["rooms"][0]["name"] = "Updated living"
        supplied["interior_layout"] = {"furniture": ["replacement"]}
        supplied["exterior_landscape"] = {"garden": False}
        supplied["processing"]["esai_engine"]["status"] = "failed"
        candidate = prepare_master_json("project-1", stored, supplied)
        self.assertEqual(candidate["floor_plan"]["rooms"][0]["name"], "Updated living")
        self.assertEqual(candidate["interior_layout"], stored["interior_layout"])
        self.assertEqual(candidate["exterior_landscape"], stored["exterior_landscape"])
        self.assertEqual(candidate["processing"]["esai_engine"], stored["processing"]["esai_engine"])

    def test_supplied_master_for_another_project_is_rejected(self):
        with self.assertRaises(VsaiInputError):
            prepare_master_json("project-1", sample_master(), sample_master("project-2"))

    def test_supplied_master_must_satisfy_root_schema_before_merge(self):
        supplied = sample_master()
        supplied.pop("processing")
        with self.assertRaisesRegex(VsaiInputError, "processing"):
            prepare_master_json("project-1", sample_master(), supplied)


class VsaiApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.Session = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)
        cls.client = TestClient(app)
        cls.upload_dir = tempfile.TemporaryDirectory()
        cls.previous_upload_dir = settings.upload_dir
        settings.upload_dir = cls.upload_dir.name

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        settings.upload_dir = cls.previous_upload_dir
        cls.client.close()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()
        cls.upload_dir.cleanup()

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.project = Project(
            id="project-1",
            project_name="Sample House",
            master_json=sample_master(),
        )
        with self.Session() as db:
            db.add(self.project)
            db.commit()

    def _png_bytes(self):
        stream = BytesIO()
        Image.new("RGB", (8, 8), color="white").save(stream, format="PNG")
        return stream.getvalue()

    def test_run_endpoint_completes_and_persists_master_json(self):
        response = self.client.post("/api/projects/project-1/vsai-rectifier/run")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["score_status"], "unavailable")
        self.assertEqual(body["master_json"]["processing"]["vsai_rectifier"]["status"], "completed")
        self.assertEqual(body["master_json"]["interior_layout"], {"furniture": ["sofa"]})
        self.assertNotEqual(body["master_json"]["structural_rectification"], {})
        with self.Session() as db:
            run = db.query(ComponentRun).one()
            self.assertEqual(run.status, "completed")
            self.assertIsNotNone(run.input_json)
            self.assertIsNotNone(run.output_json)

    def test_nonexistent_project_returns_404(self):
        response = self.client.post("/api/projects/missing/vsai-rectifier/run")
        self.assertEqual(response.status_code, 404)

    def test_invalid_master_json_returns_422_and_records_failure(self):
        original = deepcopy(sample_master())
        payload = sample_master()
        payload["floor_plan"]["rooms"][0]["polygon"] = [[0, 0], [2, 2], [0, 2], [2, 0]]
        response = self.client.post(
            "/api/projects/project-1/vsai-rectifier/run",
            json={"master_json": payload},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("self-intersects", response.json()["detail"])
        with self.Session() as db:
            run = db.query(ComponentRun).one()
            self.assertEqual(run.status, "failed")
            self.assertIn("self-intersects", run.error_message)
            saved = db.query(Project).filter_by(id="project-1").one().master_json
            self.assertEqual(saved["floor_plan"], original["floor_plan"])
            self.assertEqual(saved["processing"]["vsai_rectifier"]["status"], "failed")

    def test_missing_floor_plan_geometry_returns_clear_error(self):
        payload = sample_master()
        payload["floor_plan"] = {}
        response = self.client.post(
            "/api/projects/project-1/vsai-rectifier/run",
            json={"master_json": payload},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("floor_plan.rooms", response.json()["detail"])

    def test_invalid_project_id_in_supplied_payload_does_not_overwrite_project(self):
        response = self.client.post(
            "/api/projects/project-1/vsai-rectifier/run",
            json={"master_json": sample_master("other-project")},
        )
        self.assertEqual(response.status_code, 422)
        with self.Session() as db:
            project = db.query(Project).filter_by(id="project-1").one()
            self.assertEqual(project.master_json["floor_plan"], sample_master()["floor_plan"])
            self.assertEqual(project.master_json["processing"]["vsai_rectifier"]["status"], "failed")

    def test_history_and_existing_master_json_endpoint(self):
        self.client.post("/api/projects/project-1/vsai-rectifier/run")
        history = self.client.get("/api/projects/project-1/vsai-rectifier/history")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["runs"][0]["status"], "completed")
        master = self.client.get("/api/projects/project-1/master-json")
        self.assertEqual(master.status_code, 200)
        self.assertEqual(master.json()["processing"]["vsai_rectifier"]["status"], "completed")
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/projects").status_code, 200)
        self.assertEqual(self.client.get("/api/gallery").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)

    def test_successful_supplied_master_payload_is_accepted(self):
        payload = sample_master()
        payload["floor_plan"]["rooms"][0]["name"] = "Submitted baseline"
        response = self.client.post(
            "/api/projects/project-1/vsai-rectifier/run",
            json={"master_json": payload},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["master_json"]["floor_plan"]["rooms"][0]["name"],
            "Submitted baseline",
        )

    def test_failed_run_history_exposes_failure_and_score_status(self):
        payload = sample_master()
        payload["floor_plan"] = {}
        self.client.post(
            "/api/projects/project-1/vsai-rectifier/run",
            json={"master_json": payload},
        )
        response = self.client.get("/api/projects/project-1/vsai-rectifier/history")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["runs"][0]["status"], "failed")
        self.assertIsNone(response.json()["runs"][0]["score_status"])

    def test_other_component_stubs_remain_unchanged(self):
        response = self.client.post("/api/projects/project-1/esai-engine/run")
        self.assertEqual(response.status_code, 501)

    def test_swagger_openapi_documents_vsai_endpoints(self):
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        self.assertIn("post", paths["/api/projects/{project_id}/vsai-rectifier/run"])
        self.assertIn("post", paths["/api/projects/{project_id}/vsai-rectifier/upload"])
        self.assertIn("get", paths["/api/projects/{project_id}/vsai-rectifier/history"])

    def test_image_with_invalid_content_is_rejected(self):
        response = self.client.post(
            "/api/projects/project-1/vsai-rectifier/upload",
            files={"file": ("plan.png", b"not an image", "image/png")},
        )
        self.assertEqual(response.status_code, 400)

    def test_extension_content_mismatch_is_rejected(self):
        response = self.client.post(
            "/api/projects/project-1/vsai-rectifier/upload",
            files={"file": ("plan.jpg", self._png_bytes(), "image/jpeg")},
        )
        self.assertEqual(response.status_code, 400)

    def test_oversized_image_is_rejected(self):
        previous_limit = settings.max_upload_mb
        settings.max_upload_mb = 1
        try:
            response = self.client.post(
                "/api/projects/project-1/vsai-rectifier/upload",
                files={"file": ("plan.png", b"x" * (1024 * 1024 + 1), "image/png")},
            )
        finally:
            settings.max_upload_mb = previous_limit
        self.assertEqual(response.status_code, 413)

    def test_valid_image_is_saved_with_pending_ai_metadata(self):
        response = self.client.post(
            "/api/projects/project-1/vsai-rectifier/upload",
            files={"file": ("plan.png", self._png_bytes(), "image/png")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()
        self.assertEqual(result["processing_status"], "pending_ai_processing")
        self.assertEqual(result["image_to_vector_status"], "pending_ai_processing")
        self.assertNotIn("C:\\", result["file_path"])
        with self.Session() as db:
            output = db.query(ProjectOutput).one()
            self.assertEqual(output.metadata_json["original_filename"], "plan.png")
            self.assertEqual(output.metadata_json["media_type"], "image/png")
            self.assertTrue(os.path.isfile(os.path.join(settings.upload_dir, output.file_path)))

    def test_run_history_records_start_and_completion_times(self):
        self.client.post("/api/projects/project-1/vsai-rectifier/run")
        with self.Session() as db:
            run = db.query(ComponentRun).one()
            self.assertIsInstance(run.started_at, datetime)
            self.assertIsInstance(run.completed_at, datetime)


if __name__ == "__main__":
    unittest.main()
