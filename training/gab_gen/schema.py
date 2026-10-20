"""
GAB-Gen Training & Machine Learning Architecture Specification.
Defines:
- Feature schema (versioned)
- Target definition (multivariate spatial allocation targets)
- Data dictionary
- Dataset generation constraints
- Validation rules for synthetic & empirical datasets
- Split strategy & seed reproducibility
"""
from typing import Any, Dict, List

DATASET_SCHEMA_VERSION = "1.0.0"

DATA_DICTIONARY: Dict[str, Dict[str, Any]] = {
    "features": {
        "land_extent_sqm": {
            "type": "float",
            "unit": "square_meters",
            "description": "Calculated or declared total legal land area in square meters.",
            "range": [20.0, 5000.0]
        },
        "road_frontage_width_m": {
            "type": "float",
            "unit": "meters",
            "description": "Length of the boundary edge directly abutting the access road.",
            "range": [3.0, 100.0]
        },
        "plot_aspect_ratio": {
            "type": "float",
            "unit": "ratio",
            "description": "Ratio of plot depth to frontage width (depth / frontage).",
            "range": [0.2, 5.0]
        },
        "plot_convexity": {
            "type": "float",
            "unit": "ratio",
            "description": "Ratio of parcel area to convex hull area (measures plot irregularity).",
            "range": [0.5, 1.0]
        },
        "buildable_area_sqm": {
            "type": "float",
            "unit": "square_meters",
            "description": "Area remaining inside legal setbacks.",
            "range": [15.0, 4000.0]
        },
        "buildable_coverage_ratio": {
            "type": "float",
            "unit": "ratio",
            "description": "Buildable area divided by total land area.",
            "range": [0.2, 0.9]
        },
        "storey_count": {
            "type": "int",
            "unit": "count",
            "description": "Requested number of floors (1-4).",
            "range": [1, 4]
        },
        "demanded_bedrooms": {
            "type": "int",
            "unit": "count",
            "description": "Total requested bedroom count.",
            "range": [1, 8]
        },
        "demanded_bathrooms": {
            "type": "int",
            "unit": "count",
            "description": "Total requested bathroom count.",
            "range": [1, 6]
        },
        "parking_bays": {
            "type": "int",
            "unit": "count",
            "description": "Requested vehicle parking bays.",
            "range": [0, 4]
        },
        "total_programme_min_area": {
            "type": "float",
            "unit": "square_meters",
            "description": "Sum of mandatory room preferred minimum areas.",
            "range": [20.0, 1500.0]
        }
    },
    "targets": {
        "ground_floor_allocated_sqm": {
            "type": "float",
            "unit": "square_meters",
            "description": "Total enclosed footprint allocated to ground floor spaces."
        },
        "first_floor_allocated_sqm": {
            "type": "float",
            "unit": "square_meters",
            "description": "Total footprint allocated to first floor (0 if single storey)."
        },
        "upper_floors_allocated_sqm": {
            "type": "float",
            "unit": "square_meters",
            "description": "Total footprint allocated across 2nd & 3rd storeys."
        },
        "living_zone_area_ratio": {
            "type": "float",
            "unit": "ratio",
            "description": "Fraction of usable area assigned to public living & dining."
        },
        "private_zone_area_ratio": {
            "type": "float",
            "unit": "ratio",
            "description": "Fraction of usable area assigned to bedrooms and private spaces."
        },
        "service_zone_area_ratio": {
            "type": "float",
            "unit": "ratio",
            "description": "Fraction of usable area assigned to kitchen, utility, and storage."
        }
    }
}

VALIDATION_RULES = [
    "No row may have buildable_area_sqm > land_extent_sqm.",
    "No row may have total_programme_min_area > (buildable_area_sqm * storey_count * 0.95).",
    "Sum of zone ratios (living + private + service + circulation) must equal 1.0 within 0.02.",
    "Dataset splits must be stratified by storey_count and parcel size quantiles (small, medium, large).",
    "Synthetic datasets must document noise distributions and generator heuristics."
]

SPLIT_STRATEGY = {
    "train_ratio": 0.70,
    "validation_ratio": 0.15,
    "test_ratio": 0.15,
    "random_seed": 42,
    "stratify_keys": ["storey_count"]
}
