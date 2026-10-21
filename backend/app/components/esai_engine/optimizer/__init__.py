"""
ESAI Optimizer Package
Real Evolutionary Spatial Placement Engine using PyGAD and Shapely.
"""
from .chromosome import ChromosomeCodec, PlacedAssetDTO
from .geometry_constraints import GeometryConstraintEvaluator
from .ergonomic_constraints import ErgonomicConstraintEvaluator
from .functional_constraints import FunctionalConstraintEvaluator
from .fitness import SpatialFitnessEvaluator
from .genetic_optimizer import PyGADLayoutOptimizer, OptimizationConfig, OptimizationResult
from .alternatives import LayoutAlternativeSelector
from .baselines import BaselineEvaluator, BaselineComparisonReport

__all__ = [
    "ChromosomeCodec",
    "PlacedAssetDTO",
    "GeometryConstraintEvaluator",
    "ErgonomicConstraintEvaluator",
    "FunctionalConstraintEvaluator",
    "SpatialFitnessEvaluator",
    "PyGADLayoutOptimizer",
    "OptimizationConfig",
    "OptimizationResult",
    "LayoutAlternativeSelector",
    "BaselineEvaluator",
    "BaselineComparisonReport",
]
