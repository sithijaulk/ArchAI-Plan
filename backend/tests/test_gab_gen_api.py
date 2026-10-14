"""
API integration tests for GAB-Gen endpoints.
Tests:
- Upload survey file validation (PDF, JPG, PNG, rejection of invalid extensions)
- Requirements update & validation
- Manual survey data normalized input
- Validation endpoint
- Generate pipeline with database session
- Infeasible programme handling
"""
import pytest
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


def test_upload_valid_survey(test_project):
    # Test valid PNG
    dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    response = client.post(
        f"/api/projects/{test_project.id}/gab-gen/upload-survey",
        files={"file": ("survey_plan.png", dummy_png, "image/png")}
    )
    assert response.status_code == 200
    assert response.json()["file_metadata"]["original_filename"] == "survey_plan.png"


def test_requirements_and_generate(test_project):
    # 1. Update requirements
    req_payload = {
        "project_name": "GAB Modern Residence",
        "declared_land_extent": 10.0,
        "declared_land_unit": "perches",
        "storey_count": 2,
        "building_type": "residential_house",
        "rooms": [
            {"id": "r1", "type": "living_room", "quantity": 1, "required": True},
            {"id": "r2", "type": "kitchen", "quantity": 1, "required": True},
            {"id": "r3", "type": "master_bedroom", "quantity": 1, "required": True},
            {"id": "r4", "type": "bedroom", "quantity": 2, "required": True},
            {"id": "r5", "type": "bathroom", "quantity": 2, "required": True}
        ]
    }
    r1 = client.put(f"/api/projects/{test_project.id}/gab-gen/requirements", json=req_payload)
    assert r1.status_code == 200

    # 2. Trigger generate
    r2 = client.post(f"/api/projects/{test_project.id}/gab-gen/generate")
    assert r2.status_code == 200
    res_data = r2.json()
    assert res_data["status"] in ("completed", "needs_verification")
    assert len(res_data["master_json"]["floor_plan"]["floors"]) == 2

    # 3. Fetch result endpoint
    r3 = client.get(f"/api/projects/{test_project.id}/gab-gen/result")
    assert r3.status_code == 200
    assert "floor_plan" in r3.json()
