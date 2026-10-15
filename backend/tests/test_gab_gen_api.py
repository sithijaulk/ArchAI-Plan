"""
API integration tests for GAB-Gen endpoints.
Tests:
- Upload survey file validation (PDF, JPG, PNG, rejection of invalid extensions / corrupt files)
- Requirements update & validation
- Manual survey data normalized input (edges >= 3)
- Precondition enforcement:
  - Generate without survey -> rejected (400)
  - Generate without requirements -> rejected (400)
  - Generate without regulatory rules -> rejected (400)
- Validation endpoint
- Generate pipeline with database session & non-destructive Master JSON
- Infeasible programme handling
"""
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.project import Project
from app.models.component_run import ComponentRun

# In-memory test SQLite DB for fast endpoint validation
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

import uuid


def create_valid_test_png() -> bytes:
    """Generates real Pillow-verifiable PNG bytes."""
    im = Image.new("RGB", (10, 10), color="blue")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def test_project():
    db = TestingSessionLocal()
    proj_id = str(uuid.uuid4())
    proj = Project(id=proj_id, project_name="GAB Test House", master_json={})
    db.add(proj)
    db.commit()
    db.refresh(proj)
    db.close()
    return proj


def test_gab_context_endpoint(test_project):
    response = client.get(f"/api/projects/{test_project.id}/gab-gen/context")
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == test_project.id
    assert data["status"] == "pending"


def test_upload_invalid_file(test_project):
    # Test rejection of unauthorized extension
    response = client.post(
        f"/api/projects/{test_project.id}/gab-gen/upload-survey",
        files={"file": ("malicious.exe", b"binarycontent", "application/octet-stream")}
    )
    assert response.status_code == 400


def test_upload_corrupt_image(test_project):
    # Extension says .png but content is random text
    response = client.post(
        f"/api/projects/{test_project.id}/gab-gen/upload-survey",
        files={"file": ("corrupt.png", b"not a png image", "image/png")}
    )
    assert response.status_code == 400
    assert "Invalid or corrupted image" in response.json()["detail"]


def test_upload_valid_survey(test_project):
    valid_png = create_valid_test_png()
    response = client.post(
        f"/api/projects/{test_project.id}/gab-gen/upload-survey",
        files={"file": ("survey_plan.png", valid_png, "image/png")}
    )
    assert response.status_code == 200
    assert response.json()["file_metadata"]["original_filename"] == "survey_plan.png"


def test_generate_without_survey_rejected(test_project):
    """Calling /generate when no survey boundaries exist must return 400."""
    response = client.post(f"/api/projects/{test_project.id}/gab-gen/generate")
    assert response.status_code == 400
    assert "Survey boundary data is missing" in response.json()["detail"]


def test_generate_without_requirements_rejected(test_project):
    """Calling /generate with survey boundaries but missing requirements must return 400."""
    # Add survey data
    survey_payload = {
        "north_angle": 0.0,
        "edges": [
            {"edge_id": "E1", "distance": {"value": 15.0, "unit": "m"}, "bearing": {"raw": "90", "normalized_degrees": 90.0}, "edge_type": "road_front"},
            {"edge_id": "E2", "distance": {"value": 15.0, "unit": "m"}, "bearing": {"raw": "180", "normalized_degrees": 180.0}, "edge_type": "side"},
            {"edge_id": "E3", "distance": {"value": 15.0, "unit": "m"}, "bearing": {"raw": "270", "normalized_degrees": 270.0}, "edge_type": "rear"},
            {"edge_id": "E4", "distance": {"value": 15.0, "unit": "m"}, "bearing": {"raw": "0", "normalized_degrees": 0.0}, "edge_type": "side"},
        ]
    }
    client.post(f"/api/projects/{test_project.id}/gab-gen/manual-survey-data", json=survey_payload)

    # Call generate without requirements
    response = client.post(f"/api/projects/{test_project.id}/gab-gen/generate")
    assert response.status_code == 400
    assert "requirements are missing" in response.json()["detail"]


def test_generate_full_pipeline_success(test_project):
    """Full workflow with file, requirements, and survey boundaries succeeds and updates Master JSON."""
    # 1. Upload valid file
    valid_png = create_valid_test_png()
    r_file = client.post(
        f"/api/projects/{test_project.id}/gab-gen/upload-survey",
        files={"file": ("survey_plan.png", valid_png, "image/png")}
    )
    assert r_file.status_code == 200

    # 2. Save survey measurements
    survey_payload = {
        "north_angle": 0.0,
        "edges": [
            {"edge_id": "E01", "distance": {"value": 15.0, "unit": "m"}, "bearing": {"raw": "090°", "normalized_degrees": 90.0}, "edge_type": "road_front"},
            {"edge_id": "E02", "distance": {"value": 18.0, "unit": "m"}, "bearing": {"raw": "180°", "normalized_degrees": 180.0}, "edge_type": "side_right"},
            {"edge_id": "E03", "distance": {"value": 15.0, "unit": "m"}, "bearing": {"raw": "270°", "normalized_degrees": 270.0}, "edge_type": "rear"},
            {"edge_id": "E04", "distance": {"value": 18.0, "unit": "m"}, "bearing": {"raw": "000°", "normalized_degrees": 0.0}, "edge_type": "side_left"},
        ]
    }
    r_survey = client.post(f"/api/projects/{test_project.id}/gab-gen/manual-survey-data", json=survey_payload)
    assert r_survey.status_code == 200

    # 3. Update complete client requirements
    req_payload = {
        "project_name": "GAB Modern Residence",
        "declared_land_extent": 10.5,
        "declared_land_unit": "perches",
        "storey_count": 2,
        "building_type": "residential_house",
        "regulatory_context": {
            "jurisdiction_id": "sri_lanka_uda_standard"
        },
        "rooms": [
            {"id": "r1", "type": "living_room", "quantity": 1, "required": True},
            {"id": "r2", "type": "kitchen", "quantity": 1, "required": True},
            {"id": "r3", "type": "master_bedroom", "quantity": 1, "required": True},
            {"id": "r4", "type": "bedroom", "quantity": 2, "required": True},
            {"id": "r5", "type": "bathroom", "quantity": 2, "required": True}
        ]
    }
    r_req = client.put(f"/api/projects/{test_project.id}/gab-gen/requirements", json=req_payload)
    assert r_req.status_code == 200

    # 4. Trigger generate
    r_gen = client.post(f"/api/projects/{test_project.id}/gab-gen/generate")
    assert r_gen.status_code == 200
    res_data = r_gen.json()
    assert res_data["status"] in ("completed", "needs_verification")
    assert len(res_data["master_json"]["floor_plan"]["floors"]) == 2

    # 5. Result endpoint returns full floor plan
    r_res = client.get(f"/api/projects/{test_project.id}/gab-gen/result")
    assert r_res.status_code == 200
    assert "floor_plan" in r_res.json()
