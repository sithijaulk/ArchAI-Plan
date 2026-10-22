"""
ESAI Room Generator
Coordinates evolutionary layout optimization and service/finish planning for a single room.
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from ..contracts import (
    GeneratedRoomDesignDTO,
    ResolvedRoomDesignInputDTO,
)
from ..optimizer.genetic_optimizer import PyGADLayoutOptimizer, OptimizationConfig, OptimizationResult
from .lighting_planner import LightingPlanner
from .electrical_planner import ElectricalPlanner
from .plumbing_planner import PlumbingPlanner
from .finish_planner import FinishPlanner


class RoomGenerator:
    """
    Executes evolutionary optimization and integrates lighting, electrical, plumbing, and finishes.
    """

    def __init__(
        self,
        optimizer: Optional[PyGADLayoutOptimizer] = None,
        lighting_planner: Optional[LightingPlanner] = None,
        electrical_planner: Optional[ElectricalPlanner] = None,
        plumbing_planner: Optional[PlumbingPlanner] = None,
        finish_planner: Optional[FinishPlanner] = None,
    ):
        self.optimizer = optimizer or PyGADLayoutOptimizer()
        self.lighting_planner = lighting_planner or LightingPlanner()
        self.electrical_planner = electrical_planner or ElectricalPlanner()
        self.plumbing_planner = plumbing_planner or PlumbingPlanner()
        self.finish_planner = finish_planner or FinishPlanner()

    def generate_room(
        self,
        design_input: ResolvedRoomDesignInputDTO,
        config: Optional[OptimizationConfig] = None,
    ) -> GeneratedRoomDesignDTO:
        """
        Runs optimization and attaches grounded service provisions and finishes.
        """
        opt_res: OptimizationResult = self.optimizer.optimize_room(design_input, config)

        placed_assets_dtos = opt_res.best_layout or []

        # Convert PlacedAssetDTO to dict for serialization
        placed_assets_data: List[Dict[str, Any]] = []
        for pa in placed_assets_dtos:
            placed_assets_data.append({
                "instance_id": pa.instance_id,
                "asset_id": pa.asset_id,
                "asset_name": pa.asset_name,
                "category": pa.category,
                "subtype": pa.subtype,
                "dimensions": pa.dimensions.model_dump() if hasattr(pa.dimensions, "model_dump") else pa.dimensions.dict(),
                "position": {"x": pa.position.x, "y": pa.position.y},
                "rotation_deg": pa.rotation_deg,
                "placement_mode": pa.placement_mode.value if hasattr(pa.placement_mode, "value") else str(pa.placement_mode),
                "priority": pa.priority,
                "wall_affinity": pa.wall_affinity,
                "preferred_wall": pa.preferred_wall,
                "associated_service_ids": pa.associated_service_ids,
                "rendering_model_id": pa.rendering_model_id,
                "is_locked": pa.is_locked,
            })

        # Plan physical lighting fixtures
        lighting_fixtures = self.lighting_planner.plan_lighting(design_input, placed_assets_dtos)

        # Plan electrical sockets grounded to placed assets
        electrical_points = self.electrical_planner.plan_electrical(design_input, placed_assets_dtos)

        # Plan plumbing connections for sanitary fixtures
        plumbing_points = self.plumbing_planner.plan_plumbing(design_input, placed_assets_dtos)

        # Combine electrical and plumbing into service points
        all_service_points = electrical_points + plumbing_points

        # Plan surface finishes
        finishes_data = self.finish_planner.plan_finishes(design_input)

        # Alternatives serialization
        alternatives_data: List[Dict[str, Any]] = []
        for alt in opt_res.alternatives:
            alt_placed_list = []
            for pa in alt.placed_assets:
                alt_placed_list.append({
                    "instance_id": pa.instance_id,
                    "asset_id": pa.asset_id,
                    "asset_name": pa.asset_name,
                    "category": pa.category,
                    "position": {"x": pa.position.x, "y": pa.position.y},
                    "rotation_deg": pa.rotation_deg,
                })
            alternatives_data.append({
                "alternative_index": alt.alternative_index,
                "fitness_score": alt.fitness_score,
                "distinctness_score": alt.distinctness_score,
                "placed_assets": alt_placed_list,
                "fitness_breakdown": alt.fitness_breakdown.model_dump() if hasattr(alt.fitness_breakdown, "model_dump") else alt.fitness_breakdown.dict(),
            })

        # Ergonomic audit results
        ergo_evals = []
        if opt_res.fitness_breakdown:
            pass  # Could include detailed ergo evaluations

        fb_dict = (
            opt_res.fitness_breakdown.model_dump()
            if opt_res.fitness_breakdown and hasattr(opt_res.fitness_breakdown, "model_dump")
            else (opt_res.fitness_breakdown.dict() if opt_res.fitness_breakdown else None)
        )

        return GeneratedRoomDesignDTO(
            room_id=design_input.room_id,
            room_name=design_input.room_name,
            room_type=design_input.room_type,
            floor_id=design_input.floor_id,
            status=opt_res.status,
            polygon=design_input.polygon,
            area_sqm=design_input.area_sqm,
            ceiling_height_m=design_input.ceiling_height_m,
            geometry_revision=getattr(design_input, "geometry_revision", 1),
            preference_revision=getattr(getattr(design_input, "effective_preferences", None), "preference_revision", 1),
            geometry_fingerprint=getattr(design_input, "geometry_fingerprint", None),
            generation_timestamp=datetime.now(timezone.utc).isoformat(),
            active_alternative_id="primary",
            placed_assets=placed_assets_data,
            service_points=all_service_points,
            lighting_fixtures=lighting_fixtures,
            finishes=finishes_data,
            fitness_score=opt_res.final_best_fitness,
            fitness_breakdown=fb_dict,
            alternatives=alternatives_data,
            hard_constraints_passed=(opt_res.status == "success"),
            ergonomic_evaluations=ergo_evals,
            diagnostics=opt_res.diagnostics,
            optimization_metadata={
                "algorithm": "PyGAD Genetic Algorithm",
                "generations": opt_res.generations_completed,
                "evaluations": opt_res.total_evaluations,
                "execution_time_sec": opt_res.execution_time_sec,
                "initial_fitness": opt_res.initial_best_fitness,
                "final_fitness": opt_res.final_best_fitness,
            },
        )
