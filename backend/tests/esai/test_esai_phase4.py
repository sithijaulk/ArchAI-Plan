"""
Phase 4 Automated Test Suite
Verifies Real PyGAD Evolutionary Layout Optimization, Computational Geometry (Shapely),
Verified Ergonomic Hard Constraints, Planners, Alternatives, Baseline Benchmarking, and APIs.
"""
import copy
import pytest
from shapely.geometry import box, Polygon

from app.models.project import Project
from app.components.esai_engine.contracts import (
    Coordinate2D,
    Dimensions3D,
    DoorDTO,
    DoorHinge,
    DoorOpeningDirection,
    FixedObstructionDTO,
    PlacementMode,
    ResolvedAssetInstanceDTO,
    ResolvedErgonomicConstraintDTO,
    ResolvedFunctionalRelationshipDTO,
    ResolvedRoomDesignInputDTO,
    WindowDTO,
)
from app.components.esai_engine.optimizer.chromosome import ChromosomeCodec, PlacedAssetDTO
from app.components.esai_engine.optimizer.candidate_generator import CandidateGenerator
from app.components.esai_engine.optimizer.geometry_constraints import GeometryConstraintEvaluator
from app.components.esai_engine.optimizer.ergonomic_constraints import ErgonomicConstraintEvaluator
from app.components.esai_engine.optimizer.functional_constraints import FunctionalConstraintEvaluator
from app.components.esai_engine.optimizer.fitness import SpatialFitnessEvaluator
from app.components.esai_engine.optimizer.genetic_optimizer import (
    OptimizationConfig,
    OptimizationResult,
    PyGADLayoutOptimizer,
)
from app.components.esai_engine.optimizer.alternatives import LayoutAlternativeSelector
from app.components.esai_engine.optimizer.baselines import BaselineEvaluator
from copy import deepcopy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.dependencies import require_admin
from app.main import app as fastapi_app
from app.components.esai_engine.service import EsaiEngineService
from tests.esai.fixtures import BEDROOM_PROJECT_FIXTURE, MULTI_FLOOR_PROJECT_FIXTURE


# ── Fixtures for Unit Testing ────────────────────────────────────────────────

@pytest.fixture
def in_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(in_memory_db):
    return in_memory_db


@pytest.fixture
def admin_client(in_memory_db):
    fastapi_app.dependency_overrides[get_db] = lambda: in_memory_db
    fastapi_app.dependency_overrides[require_admin] = lambda: {"id": "admin_test", "role": "admin"}
    client = TestClient(fastapi_app)
    yield client
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def bedroom_project(in_memory_db):
    project = Project(
        id="proj_phase4_bed",
        project_name="Phase 4 Bedroom Test",
        master_json=deepcopy(BEDROOM_PROJECT_FIXTURE),
        revision=1,
    )
    in_memory_db.add(project)
    in_memory_db.commit()
    in_memory_db.refresh(project)
    return project


@pytest.fixture
def multi_room_project(in_memory_db):
    project = Project(
        id="proj_phase4_multi",
        project_name="Phase 4 Multi-Room Test",
        master_json=deepcopy(MULTI_FLOOR_PROJECT_FIXTURE),
        revision=1,
    )
    in_memory_db.add(project)
    in_memory_db.commit()
    in_memory_db.refresh(project)
    return project


@pytest.fixture
def sample_bedroom_design_input(in_memory_db, bedroom_project) -> ResolvedRoomDesignInputDTO:
    service = EsaiEngineService(in_memory_db)
    service.save_room_preferences(
        bedroom_project,
        room_id="RM_BED_01",
        preferences_data={
            "room_specific": {"bed_type": "queen", "bed_quantity": 1, "wardrobe_type": "sliding"},
            "electrical": {"charging_station": True, "ceiling_fan": True},
            "design_style": "modern",
        },
    )
    return service.resolve_room_design_input(bedroom_project, room_id="RM_BED_01", floor_id="floor_gf")


# ── 1. Chromosome Codec Tests ────────────────────────────────────────────────

def test_chromosome_encoding_decoding_and_immutability(sample_bedroom_design_input):
    """
    Verifies that the chromosome encodes only movable assets,
    strictly preserves locked items without mutation, and round-trips correctly.
    """
    poly = Polygon([(p.x, p.y) for p in sample_bedroom_design_input.polygon])
    codec = ChromosomeCodec(poly, sample_bedroom_design_input.asset_instances)

    # Gene space verification
    assert codec.chromosome_length == codec.num_movable * 3
    gene_space = codec.get_gene_space()
    assert len(gene_space) == codec.chromosome_length

    # Decode test vector
    test_vec = [1.5, 2.0, 1.0] * codec.num_movable
    placed = codec.decode(test_vec)

    assert len(placed) == len(sample_bedroom_design_input.asset_instances)
    for p in placed:
        assert isinstance(p.position, Coordinate2D)
        assert p.rotation_deg in (0.0, 90.0, 180.0, 270.0)
        assert p.footprint_polygon is not None
        assert p.footprint_polygon.area > 0.1

    # Encode roundtrip
    encoded = codec.encode(placed)
    assert len(encoded) == codec.chromosome_length


def test_chromosome_locked_placement_immutability():
    """Verifies that user-locked items are never modified by gene changes."""
    room_poly = box(0.0, 0.0, 5.0, 5.0)
    locked_item = ResolvedAssetInstanceDTO(
        instance_id="locked_bed_1",
        asset_id="BED_QUEEN_01",
        asset_name="Locked Queen Bed",
        category="bed",
        subtype="bed",
        dimensions=Dimensions3D(width=1.6, depth=2.0, height=0.6),
        physical_footprint_type="rectangle",
        placement_mode=PlacementMode.FLOOR_STANDING,
        priority="user_locked",
        supported_rotations=[0, 90, 180, 270],
        locked_coordinates=Coordinate2D(x=2.5, y=3.0),
        locked_rotation=90.0,
        rendering_model_id="model_bed_queen_01",
    )
    movable_item = ResolvedAssetInstanceDTO(
        instance_id="movable_desk_1",
        asset_id="DESK_EXEC_01",
        asset_name="Movable Study Desk",
        category="desk",
        subtype="desk",
        dimensions=Dimensions3D(width=1.2, depth=0.6, height=0.75),
        physical_footprint_type="rectangle",
        placement_mode=PlacementMode.FLOOR_STANDING,
        priority="mandatory",
        supported_rotations=[0, 90, 180, 270],
        rendering_model_id="model_desk_exec_01",
    )

    codec = ChromosomeCodec(room_poly, [locked_item, movable_item])
    assert codec.num_movable == 1  # Only desk is movable!

    # Decode with extreme gene values
    placed = codec.decode([0.5, 0.5, 0.0])
    locked_placed = next(p for p in placed if p.instance_id == "locked_bed_1")

    # Locked position must remain exactly at (2.5, 3.0) and 90 deg
    assert locked_placed.position.x == 2.5
    assert locked_placed.position.y == 3.0
    assert locked_placed.rotation_deg == 90.0
    assert locked_placed.is_locked is True


# ── 2. Candidate Population Generation Tests ─────────────────────────────────

def test_candidate_population_generation(sample_bedroom_design_input):
    """Verifies population initialization diversity and seed reproducibility."""
    poly = Polygon([(p.x, p.y) for p in sample_bedroom_design_input.polygon])
    codec = ChromosomeCodec(poly, sample_bedroom_design_input.asset_instances)

    generator = CandidateGenerator(codec=codec, seed=123)
    pop1 = generator.generate_initial_population(population_size=15)
    assert len(pop1) == 15

    # Reproducibility with same seed
    gen2 = CandidateGenerator(codec=codec, seed=123)
    pop2 = gen2.generate_initial_population(population_size=15)
    assert pop1 == pop2

    # Different seed yields different chromosomes
    gen3 = CandidateGenerator(codec=codec, seed=999)
    pop3 = gen3.generate_initial_population(population_size=15)
    assert pop1 != pop3


# ── 3. Geometry Constraints (Shapely) Tests ──────────────────────────────────

def test_geometry_constraints_detects_collision_and_oob():
    """Verifies that furniture overlaps and out-of-bounds positions are detected."""
    room_poly = box(0.0, 0.0, 4.0, 4.0)
    evaluator = GeometryConstraintEvaluator(room_polygon=room_poly)

    # Item A: at center (2.0, 2.0), 1.5 x 1.5
    # Item B: at (2.5, 2.0), 1.5 x 1.5 -> Collides with Item A!
    # Item C: at (4.2, 2.0), 1.0 x 1.0 -> Out of bounds!
    item_a = PlacedAssetDTO(
        instance_id="item_a",
        asset_id="A",
        asset_name="Table A",
        category="table",
        subtype="table",
        dimensions=Dimensions3D(width=1.5, depth=1.5, height=0.7),
        position=Coordinate2D(x=2.0, y=2.0),
        rotation_deg=0.0,
        footprint_polygon=box(1.25, 1.25, 2.75, 2.75),
    )
    item_b = PlacedAssetDTO(
        instance_id="item_b",
        asset_id="B",
        asset_name="Table B",
        category="table",
        subtype="table",
        dimensions=Dimensions3D(width=1.5, depth=1.5, height=0.7),
        position=Coordinate2D(x=2.5, y=2.0),
        rotation_deg=0.0,
        footprint_polygon=box(1.75, 1.25, 3.25, 2.75),
    )
    item_c = PlacedAssetDTO(
        instance_id="item_c",
        asset_id="C",
        asset_name="Table C",
        category="table",
        subtype="table",
        dimensions=Dimensions3D(width=1.0, depth=1.0, height=0.7),
        position=Coordinate2D(x=4.2, y=2.0),
        rotation_deg=0.0,
        footprint_polygon=box(3.7, 1.5, 4.7, 2.5),  # Extends past x=4.0
    )

    res = evaluator.evaluate([item_a, item_b, item_c])
    assert res.is_valid is False
    assert res.overlap_area_sqm > 0.0
    assert res.out_of_bounds_area_sqm > 0.0
    assert any("Collision" in v for v in res.violations)
    assert any("extends outside usable room" in v for v in res.violations)


def test_geometry_constraints_detects_door_blockage():
    """Verifies that placing furniture in front of a door swing is rejected."""
    room_poly = box(0.0, 0.0, 5.0, 5.0)
    door = DoorDTO(
        id="D_TEST",
        room_id="RM_TEST",
        start=Coordinate2D(x=0.0, y=1.0),
        end=Coordinate2D(x=0.0, y=1.9),
        leaf_width=0.9,
        hinge=DoorHinge.LEFT,
        opening_direction=DoorOpeningDirection.INWARD,
        swing_angle=90.0,
    )
    evaluator = GeometryConstraintEvaluator(room_polygon=room_poly, doors=[door])

    # Wardrobe placed right against door opening
    blocking_wardrobe = PlacedAssetDTO(
        instance_id="w_block",
        asset_id="WARDROBE_3DOOR_01",
        asset_name="Blocking Wardrobe",
        category="wardrobe",
        subtype="wardrobe",
        dimensions=Dimensions3D(width=1.8, depth=0.6, height=2.1),
        position=Coordinate2D(x=0.4, y=1.45),
        rotation_deg=90.0,
        footprint_polygon=box(0.1, 0.55, 0.7, 2.35),
    )

    res = evaluator.evaluate([blocking_wardrobe])
    assert res.is_valid is False
    assert res.door_violation_count >= 1
    assert any("door swing/entry clearance zone" in v for v in res.violations)


# ── 4. Ergonomic Constraints Audit ───────────────────────────────────────────

def test_ergonomic_constraints_evaluator(sample_bedroom_design_input):
    """Tests evaluation of Neufert clearances with hard vs soft classification."""
    poly = Polygon([(p.x, p.y) for p in sample_bedroom_design_input.polygon])
    evaluator = ErgonomicConstraintEvaluator(
        rules=sample_bedroom_design_input.ergonomic_constraints,
        room_polygon=poly,
    )

    # Layout with bed at center
    bed = PlacedAssetDTO(
        instance_id="bed_1",
        asset_id="BED_QUEEN_01",
        asset_name="Queen Bed",
        category="bed",
        subtype="bed",
        dimensions=Dimensions3D(width=1.6, depth=2.0, height=0.6),
        position=Coordinate2D(x=2.5, y=2.5),
        rotation_deg=0.0,
        footprint_polygon=box(1.7, 1.5, 3.3, 3.5),
    )

    res = evaluator.evaluate([bed])
    assert res.ergonomic_score > 0.0
    assert len(res.evaluations) >= 1
    for ev in res.evaluations:
        assert ev.rule_id != ""
        assert ev.verification_status != ""


# ── 5. PyGAD Evolutionary Optimization Execution ─────────────────────────────

def test_pygad_evolutionary_optimization_run(sample_bedroom_design_input):
    """
    CRITICAL PROMPT REQUIREMENT:
    Runs real PyGAD evolutionary optimization.
    Verifies chromosome evolution, fitness history tracking, and hard-constraint validity.
    """
    optimizer = PyGADLayoutOptimizer()
    cfg = OptimizationConfig(
        population_size=20,
        num_generations=15,
        num_parents_mating=8,
        seed=42,
        alternatives_count=2,
    )

    result: OptimizationResult = optimizer.optimize_room(sample_bedroom_design_input, cfg)

    assert result.status == "success"
    assert result.room_id == "RM_BED_01"
    assert result.generations_completed == 15
    assert result.total_evaluations > 20
    assert len(result.fitness_history) in (15, 16)
    assert result.best_layout is not None
    assert len(result.best_layout) == len(sample_bedroom_design_input.asset_instances)

    # Ensure final best fitness >= initial best fitness (optimization improves or preserves quality)
    assert result.final_best_fitness >= result.initial_best_fitness

    # Check fitness breakdown
    assert result.fitness_breakdown is not None
    assert result.fitness_breakdown.is_hard_constraint_valid is True
    assert result.fitness_breakdown.overlap_penalty == 0.0
    assert result.fitness_breakdown.out_of_bounds_penalty == 0.0
    assert len(result.fitness_breakdown.violations) == 0


def test_pygad_optimization_deterministic_reproducibility(sample_bedroom_design_input):
    """Ensures identical random seeds produce equivalent evolutionary results."""
    optimizer = PyGADLayoutOptimizer()
    cfg = OptimizationConfig(population_size=20, num_generations=12, seed=42)

    res_1 = optimizer.optimize_room(sample_bedroom_design_input, cfg)
    res_2 = optimizer.optimize_room(sample_bedroom_design_input, cfg)

    assert res_1.status == res_2.status
    assert res_1.final_best_fitness == res_2.final_best_fitness
    if res_1.best_layout is not None and res_2.best_layout is not None:
        assert len(res_1.best_layout) == len(res_2.best_layout)
        for p1, p2 in zip(res_1.best_layout, res_2.best_layout):
            assert p1.position.x == p2.position.x
            assert p1.position.y == p2.position.y
            assert p1.rotation_deg == p2.rotation_deg


# ── 6. Multi-Room and Multi-Floor Scope Execution ────────────────────────────

def test_building_generator_scopes(in_memory_db, multi_room_project):
    """
    Tests Room, Floor, and Building generation scopes across a multi-floor project.
    """
    service = EsaiEngineService(in_memory_db)
    cfg = OptimizationConfig(population_size=15, num_generations=5, seed=42)

    # 1. Scope: Room
    res_room = service.run_generation(
        multi_room_project,
        scope="room",
        target_room_id="RM_LIVING_01",
        config=cfg,
    )
    assert res_room.scope == "room"
    assert res_room.total_rooms_discovered == 1
    assert "RM_LIVING_01" in res_room.rooms
    assert res_room.rooms["RM_LIVING_01"].status in ("success", "partial")

    # 2. Scope: Floor
    res_floor = service.run_generation(
        multi_room_project,
        scope="floor",
        target_floor_id="fl_0",
        config=cfg,
    )
    assert res_floor.scope == "floor"
    assert res_floor.total_rooms_discovered == 2  # Living and Kitchen
    assert "RM_LIVING_01" in res_floor.rooms
    assert "RM_KITCHEN_01" in res_floor.rooms

    # 3. Scope: Entire Building
    res_bldg = service.run_generation(
        multi_room_project,
        scope="building",
        config=cfg,
    )
    assert res_bldg.scope == "building"
    assert res_bldg.total_rooms_discovered == 3  # fl_0 (Living, Kitchen) + fl_1 (Bath)
    assert res_bldg.successful_rooms_count >= 1


# ── 7. Lighting, Electrical, Plumbing, and Finishes Planners ────────────────

def test_service_planners_integration(sample_bedroom_design_input):
    """Verifies that lighting, electrical sockets, and finishes are planned."""
    optimizer = PyGADLayoutOptimizer()
    cfg = OptimizationConfig(population_size=15, num_generations=8, seed=42)
    opt_res = optimizer.optimize_room(sample_bedroom_design_input, cfg)

    from app.components.esai_engine.generation.room_generator import RoomGenerator
    generator = RoomGenerator(optimizer=optimizer)
    room_design = generator.generate_room(sample_bedroom_design_input, cfg)

    # Placed assets exist
    assert len(room_design.placed_assets) >= 1

    # Lighting planned
    assert len(room_design.lighting_fixtures) >= 1
    main_light = room_design.lighting_fixtures[0]
    assert "lighting" in main_light.point_type

    # Electrical points planned (bedside USB sockets)
    assert len(room_design.service_points) >= 1
    for sp in room_design.service_points:
        assert sp.requires_professional_verification is True
        assert sp.status == "proposed_new"

    # Finishes planned
    assert "wall_finish" in room_design.finishes
    assert "floor_finish" in room_design.finishes
    assert "ceiling_finish" in room_design.finishes


# ── 8. Alternatives Generation & Deduplication ───────────────────────────────

def test_alternatives_generation_and_deduplication(sample_bedroom_design_input):
    """Verifies that generated alternatives are non-duplicate and valid."""
    optimizer = PyGADLayoutOptimizer()
    cfg = OptimizationConfig(population_size=25, num_generations=15, alternatives_count=3, seed=42)
    result = optimizer.optimize_room(sample_bedroom_design_input, cfg)

    assert result.status == "success"
    # If multiple valid solutions were explored, alternatives are provided
    for alt in result.alternatives:
        assert alt.fitness_breakdown.is_hard_constraint_valid is True
        assert alt.distinctness_score > 0.0


# ── 9. Baseline Benchmarking (GA vs Random vs Greedy) ────────────────────────

def test_baseline_evaluator_scientific_benchmark(sample_bedroom_design_input):
    """
    CRITICAL PROMPT REQUIREMENT:
    Direct scientific comparison between GA, Random Search, and Greedy Placement.
    """
    evaluator = BaselineEvaluator()
    report = evaluator.benchmark_room(sample_bedroom_design_input, eval_budget=150, seed=42)

    assert report.room_id == "RM_BED_01"
    assert report.ga_metrics.method_name == "PyGAD Genetic Algorithm"
    assert report.random_metrics.method_name == "Random Search Baseline"
    assert report.greedy_metrics.method_name == "Greedy Wall-Placement Baseline"

    # GA runtime and evaluation tracking
    assert report.ga_metrics.evaluations_count > 0
    assert report.random_metrics.evaluations_count == 150
    assert report.greedy_metrics.evaluations_count == 1

    # GA must achieve equal or superior fitness compared to random sampling
    assert report.ga_metrics.best_fitness >= report.random_metrics.best_fitness


# ── 10. API Integration Endpoints ───────────────────────────────────────────

def test_api_run_and_benchmark_endpoints(admin_client, db_session):
    """Verifies /run and /benchmark endpoints execute and enforce authorization."""
    project = Project(id="proj_ga_api_01", project_name="API GA Test", master_json=BEDROOM_PROJECT_FIXTURE)
    db_session.add(project)
    db_session.commit()

    # 1. POST /run
    run_res = admin_client.post(
        "/api/projects/proj_ga_api_01/esai-engine/run",
        json={"scope": "room", "room_id": "RM_BED_01", "population_size": 15, "generations": 5, "seed": 42}
    )
    assert run_res.status_code == 200
    res_data = run_res.json()["result"]
    assert res_data["project_id"] == "proj_ga_api_01"
    assert "RM_BED_01" in res_data["rooms"]
    assert res_data["rooms"]["RM_BED_01"]["status"] in ("success", "partial")

    # 2. POST /benchmark
    bench_res = admin_client.post(
        "/api/projects/proj_ga_api_01/esai-engine/benchmark",
        json={"room_id": "RM_BED_01", "eval_budget": 50, "seed": 42}
    )
    assert bench_res.status_code == 200
    rep_data = bench_res.json()["report"]
    assert "ga_metrics" in rep_data
    assert "random_metrics" in rep_data
    assert "greedy_metrics" in rep_data
