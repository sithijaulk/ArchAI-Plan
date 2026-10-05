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
from app.routers import projects
from app.schemas.project import ProjectUpdate


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


@pytest.fixture
def concurrent_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'project-revisions.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    first = sessions()
    second = sessions()
    project = Project(project_name="revision test", revision=1, master_json={
        "land_info": {"upstream": "original"}, "processing": {},
    })
    first.add(project)
    first.commit()
    project_id = project.id
    yield first, second, project_id
    first.close()
    second.close()
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
    assert error.value.detail["current_revision"] == stored.revision
    assert stored.master_json["component_update"] == {"revision": "newer"}
    assert stored.master_json["exterior_landscape"] == {"accepted_run": "old"}
    assert stored.master_json["processing"]["elia_engine"]["status"] == "failed"
    assert run.status == "failed"
    assert run.output_json == candidate
    assert run.input_json["source_revision"] == 1


def test_stale_elia_run_does_not_overwrite_newer_elia_metadata(database, monkeypatch):
    session, project_id = database
    candidate = _candidate("old-run", True)

    def newer_elia_run(master, requirements, run_id, mode):
        project = session.query(Project).filter(Project.id == project_id).one()
        master = {**project.master_json, "processing": {
            **project.master_json.get("processing", {}),
            "elia_engine": {"status": "completed", "run_id": "newer-run", "outcome": "valid"},
        }}
        project.master_json = master
        project.revision += 1
        session.commit()
        return candidate, "valid"

    monkeypatch.setattr(elia, "generate_exterior", newer_elia_run)

    with pytest.raises(HTTPException) as error:
        elia.run_project_elia(project_id, ELIARequest(generation_mode="baseline"), session, _admin=None)

    stored = session.query(Project).filter(Project.id == project_id).one()
    assert error.value.status_code == 409
    assert stored.master_json["processing"]["elia_engine"] == {
        "status": "completed", "run_id": "newer-run", "outcome": "valid"}


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


def test_invalid_baseline_response_is_rejected_before_design_commit(database, monkeypatch):
    session, project_id = database
    invalid_candidate = {"version": "1.0", "schema_version": "1.0", "run_id": "bad-response"}
    monkeypatch.setattr(elia, "generate_exterior", lambda *args: (invalid_candidate, "valid"))

    with pytest.raises(HTTPException) as error:
        elia.run_project_elia(project_id, ELIARequest(generation_mode="baseline"), session, _admin=None)

    stored = session.query(Project).filter(Project.id == project_id).one()
    run = session.query(ComponentRun).filter(ComponentRun.project_id == project_id).one()
    assert error.value.status_code == 500
    assert stored.master_json["exterior_landscape"] == {"accepted_run": "old"}
    assert run.status == "failed"
    assert run.output_json == invalid_candidate


def test_non_finite_baseline_response_is_rejected_before_design_commit(database, monkeypatch):
    session, project_id = database
    invalid_candidate = _candidate("non-finite", True)
    invalid_candidate["metrics"]["unexpected"] = float("nan")
    monkeypatch.setattr(elia, "generate_exterior", lambda *args: (invalid_candidate, "valid"))

    with pytest.raises(HTTPException) as error:
        elia.run_project_elia(project_id, ELIARequest(generation_mode="baseline"), session, _admin=None)

    stored = session.query(Project).filter(Project.id == project_id).one()
    run = session.query(ComponentRun).filter(ComponentRun.project_id == project_id).one()
    assert error.value.status_code == 500
    assert stored.master_json["exterior_landscape"] == {"accepted_run": "old"}
    assert run.status == "failed"
    assert run.output_json["metrics"]["unexpected"] == "<non_finite>"


def test_project_master_update_rejects_stale_revision_across_sessions(concurrent_database):
    first, second, project_id = concurrent_database
    stale = first.query(Project).filter(Project.id == project_id).one()
    latest = second.query(Project).filter(Project.id == project_id).one()
    latest.master_json = {**latest.master_json, "component_2": {"result": "new"}}
    latest.revision = 2
    second.commit()

    with pytest.raises(HTTPException) as error:
        projects.update_project(project_id, ProjectUpdate(expected_revision=1,
            master_json={"component_1": {"stale": True}}), first, _admin=None)

    first.expire_all()
    stored = first.query(Project).filter(Project.id == project_id).one()
    assert error.value.status_code == 409
    assert error.value.detail["current_revision"] == 2
    assert stored.master_json["component_2"] == {"result": "new"}
    assert "component_1" not in stored.master_json


def test_component_skip_returns_conflict_when_other_session_updates_master(concurrent_database):
    first, second, project_id = concurrent_database
    first.query(Project).filter(Project.id == project_id).one()
    latest = second.query(Project).filter(Project.id == project_id).one()
    latest.master_json = {**latest.master_json, "component_2": {"result": "new"}}
    latest.revision = 2
    second.commit()

    with pytest.raises(HTTPException) as error:
        projects.skip_component(project_id, "gab_gen", expected_revision=1,
                                db=first, _admin=None)

    first.expire_all()
    stored = first.query(Project).filter(Project.id == project_id).one()
    assert error.value.status_code == 409
    assert error.value.detail["current_revision"] == 2
    assert stored.master_json["component_2"] == {"result": "new"}
    assert stored.master_json["processing"].get("gab_gen") is None
    assert first.query(ComponentRun).filter(ComponentRun.project_id == project_id).count() == 0


def test_component_skip_returns_incremented_revision(database):
    session, project_id = database

    result = projects.skip_component(project_id, "gab_gen", expected_revision=1,
                                     db=session, _admin=None)

    stored = session.query(Project).filter(Project.id == project_id).one()
    assert result["revision"] == 2
    assert stored.revision == 2
    assert result["master_json"]["processing"]["gab_gen"]["status"] == "skipped"