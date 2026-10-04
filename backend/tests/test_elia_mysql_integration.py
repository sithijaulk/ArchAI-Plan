"""Opt-in persistence test against an explicitly configured disposable MySQL schema."""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.components.elia_engine.schemas import ELIARequest, ELIARequirements
from app.database import Base
from app.models.component_run import ComponentRun
from app.models.project import Project
from app.routers.elia import run_project_elia


def test_mysql_run_persists_same_master_and_component_history():
    database_url = os.getenv("ELIA_TEST_MYSQL_URL")
    if not database_url:
        pytest.skip("Set ELIA_TEST_MYSQL_URL to a disposable MySQL test schema to run persistence integration.")
    if not database_url.startswith("mysql+pymysql://"):
        pytest.fail("ELIA_TEST_MYSQL_URL must use the existing MySQL PyMySQL driver.")

    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    project = Project(project_name="ELIA persistence integration", master_json={
        "project_name": "ELIA persistence integration", "units": "m",
        "location": {"latitude": 6.9, "longitude": 79.8},
        "land_info": {"boundary_points": [[0, 0], [40, 0], [40, 30], [0, 30]],
                   "road_facing": "south", "calculated_north_bearing": 0},
        "house_exterior_polygon": [[10, 8], [22, 8], [22, 22], [10, 22]],
        "utilities": {"well": {"known": True, "position": [2, 27]},
                      "septic_tank": {"known": True, "position": [22, 27]}},
        "interior_layout": {"rooms": [{"id": "R1", "furniture": ["sofa"]}]},
        "processing": {"esai_engine": {"status": "completed"}},
    })
    try:
        session.add(project)
        session.commit()
        project_id = project.id
        request = ELIARequest(generation_mode="baseline", requirements=ELIARequirements(
            access={"road_side": "south", "garage_required": False, "driveway_required": False}))
        response = run_project_elia(project_id, request, session, _admin=None)
        session.expire_all()
        stored = session.query(Project).filter(Project.id == project_id).one()
        run = session.query(ComponentRun).filter(ComponentRun.project_id == project_id,
                                                  ComponentRun.component_name == "elia_engine").one()
        assert stored.master_json["interior_layout"]["rooms"][0]["furniture"] == ["sofa"]
        assert stored.master_json["exterior_landscape"] == response.exterior_landscape
        assert stored.master_json["processing"]["elia_engine"]["run_id"] == run.id
        assert run.status == "completed"
        assert run.output_json == response.exterior_landscape
    finally:
        if project.id:
            session.query(Project).filter(Project.id == project.id).delete(synchronize_session=False)
            session.commit()
        session.close()
        engine.dispose()
