"""
Repeatable PostgreSQL Integration Tests for ESAI-Engine Stage 1
Validates real PostgreSQL persistence against an explicitly configured disposable schema:
- Schema migration / table structure with psycopg2
- Strict enforcement of PostgreSQL driver (fails if non-PostgreSQL)
- Unique constraint enforcement on (project_id, room_id) in PostgreSQL
- Transactional persistence of room requirements and Centralized Master JSON
- Non-destructive preservation of Master JSON fields in PostgreSQL JSON column
"""
import os
from copy import deepcopy
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from app.database import Base
from app.models.project import Project
from app.models.esai import EsaiRoomRequirement
from app.components.esai_engine.contracts import (
    RoomRequirementsDTO,
    FurnitureRequirementItem,
    AssetCategory,
    RoomType,
)
from app.components.esai_engine.service import EsaiEngineService
from tests.esai.fixtures import BEDROOM_PROJECT_FIXTURE


def _get_postgres_test_session():
    database_url = os.getenv("ESAI_TEST_DB_URL") or os.getenv("ESAI_TEST_MYSQL_URL")
    if not database_url:
        pytest.skip("Set ESAI_TEST_DB_URL to a disposable PostgreSQL test schema to run persistence integration.")
    if not (database_url.startswith("postgresql://") or database_url.startswith("postgresql+psycopg2://")):
        pytest.fail("ESAI_TEST_DB_URL must use the PostgreSQL driver.")

    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    session = Session()
    return engine, session


def test_esai_postgres_transactional_persistence():
    engine, session = _get_postgres_test_session()
    project = Project(
        project_name="ESAI MySQL Integration Project",
        master_json=deepcopy(BEDROOM_PROJECT_FIXTURE)
    )
    session.add(project)
    session.commit()
    project_id = project.id

    try:
        service = EsaiEngineService(session)
        reqs = RoomRequirementsDTO(
            room_id="RM_BED_01",
            floor_id="floor_gf",
            room_type=RoomType.MASTER_BEDROOM,
            items=[
                FurnitureRequirementItem(
                    instance_id="mysql_bed_1",
                    catalog_id="BED_KING_01",
                    category=AssetCategory.BED,
                    quantity=1
                )
            ]
        )

        res = service.save_room_requirements(project, reqs, status="ready")
        assert res["status"] == "ready"

        session.expire_all()
        stored_project = session.query(Project).filter(Project.id == project_id).one()
        stored_req = session.query(EsaiRoomRequirement).filter(
            EsaiRoomRequirement.project_id == project_id,
            EsaiRoomRequirement.room_id == "RM_BED_01"
        ).one()

        assert stored_req.status == "ready"
        assert stored_req.floor_id == "floor_gf"
        assert stored_project.master_json["interior_layout"]["room_requirements"]["RM_BED_01"]["room_id"] == "RM_BED_01"
        assert stored_project.master_json["processing"]["esai_engine"]["status"] == "pending"
        # Structural geometry preserved in MySQL
        assert stored_project.master_json["floor_plan"]["floors"][0]["rooms"][0]["polygon"] == BEDROOM_PROJECT_FIXTURE["floor_plan"]["floors"][0]["rooms"][0]["polygon"]

    finally:
        if project_id:
            session.query(EsaiRoomRequirement).filter(EsaiRoomRequirement.project_id == project_id).delete()
            session.query(Project).filter(Project.id == project_id).delete()
            session.commit()
        session.close()
        engine.dispose()


def test_esai_postgres_unique_constraint():
    engine, session = _get_postgres_test_session()
    project = Project(
        project_name="ESAI MySQL Unique Constraint Test",
        master_json=deepcopy(BEDROOM_PROJECT_FIXTURE)
    )
    session.add(project)
    session.commit()
    project_id = project.id

    try:
        rec1 = EsaiRoomRequirement(
            project_id=project_id,
            floor_id="floor_gf",
            room_id="RM_BED_01",
            requirements_json={"data": "first"}
        )
        session.add(rec1)
        session.commit()

        rec2 = EsaiRoomRequirement(
            project_id=project_id,
            floor_id="floor_gf",
            room_id="RM_BED_01",
            requirements_json={"data": "second"}
        )
        session.add(rec2)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    finally:
        if project_id:
            session.query(EsaiRoomRequirement).filter(EsaiRoomRequirement.project_id == project_id).delete()
            session.query(Project).filter(Project.id == project_id).delete()
            session.commit()
        session.close()
        engine.dispose()
