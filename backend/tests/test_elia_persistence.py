import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.components.elia_engine.schemas import ELIARequest
from app.components.elia_engine.exceptions import ELIAError
from app.database import Base
from app.models.component_run import ComponentRun
from app.models.project import Project
from app.routers import elia


def _candidate(run_id, valid):
    return {
        "version": "1.0", "schema_version": "1.0", "run_id": run_id,
        "coordinate_reference": "local Cartesian meters", "access": {},
        "site_analysis": {}, "utility_safety": {}, "environment": {}, "metrics": {},
        "vegetation_nodes": [], "vertical_greenery": {"elements": []},
        "outdoor_lighting": {"nodes": []}, "outdoor_elements": [],
        "validation_summary": {"valid": valid, "violations": [] if valid else ["candidate_invalid"]},
    }


@pytest.fixture
def database():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    project = Project(project_name="isolated ELIA test", revision=1, master_json={
        "exterior_landscape": {"accepted_run": "old"},
        "processing": {"esai_engine": {"status": "completed"}},
    })
    session.add(project)
    session.commit()
    yield session, project.id
    session.close()
    engine.dispose()


def test_infeasible_candidate_is_historic_and_does_not_replace_design(database, monkeypatch):
    session, project_id = database
    candidate = _candidate("infeasible", False)
    monkeypatch.setattr(elia, "generate_exterior", lambda *args: (candidate, "infeasible"))

    result = elia.run_project_elia(project_id, ELIARequest(generation_mode="baseline"), session, _admin=None)

    stored = session.query(Project).filter(Project.id == project_id).one()
    run = session.query(ComponentRun).filter(ComponentRun.project_id == project_id).one()
    assert result.status == "infeasible"
    assert stored.master_json["exterior_landscape"] == {"accepted_run": "old"}
    assert stored.master_json["processing"]["elia_engine"]["outcome"] == "infeasible"
    assert run.output_json == candidate
    assert run.input_json["master_json_snapshot"]["exterior_landscape"]["accepted_run"] == "old"
    assert run.input_json["source_revision"] == 1


def test_concurrent_project_revision_returns_conflict_and_preserves_newer_data(database, monkeypatch):
    session, project_id = database
    candidate = _candidate("stale", True)

    def concurrent_update(master, requirements, run_id, mode):
        project = session.query(Project).filter(Project.id == project_id).one()
        project.master_json = {**project.master_json, "component_update": {"revision": "newer"}}
        project.revision += 1
        session.commit()
        return candidate, "valid"

    monkeypatch.setattr(elia, "generate_exterior", concurrent_update)

    with pytest.raises(HTTPException) as error:
        elia.run_project_elia(project_id, ELIARequest(generation_mode="baseline"), session, _admin=None)

    stored = session.query(Project).filter(Project.id == project_id).one()
    run = session.query(ComponentRun).filter(ComponentRun.project_id == project_id).one()
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "ELIA_STALE_SOURCE_REVISION"
    assert stored.master_json["component_update"] == {"revision": "newer"}
    assert stored.master_json["exterior_landscape"] == {"accepted_run": "old"}
    assert stored.master_json["processing"]["elia_engine"]["status"] == "failed"
    assert run.status == "failed"
    assert run.output_json == candidate
    assert run.input_json["source_revision"] == 1


def test_invalid_model_candidate_is_saved_without_replacing_accepted_design(database, monkeypatch):
    session, project_id = database
    invalid_candidate = {"json_id": "BAD_001", "position": ["nan", 1]}

    def invalid_generation(*args):
        error = ELIAError("ELIA_INVALID_MODEL_OUTPUT", "Model output contains a non-finite position.")
        error.candidate_output = invalid_candidate
        raise error

    monkeypatch.setattr(elia, "generate_exterior", invalid_generation)

    with pytest.raises(HTTPException) as error:
        elia.run_project_elia(project_id, ELIARequest(), session, _admin=None)

    stored = session.query(Project).filter(Project.id == project_id).one()
    run = session.query(ComponentRun).filter(ComponentRun.project_id == project_id).one()
    assert error.value.status_code == 422
    assert stored.master_json["exterior_landscape"] == {"accepted_run": "old"}
    assert run.status == "failed"
    assert run.output_json == invalid_candidate
    assert run.input_json["schema_version"] == "1.0"