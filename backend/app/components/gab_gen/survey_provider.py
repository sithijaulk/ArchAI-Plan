"""
Survey extraction interface and providers.
Stage 1: ManualSurveyExtractionProvider and FixtureSurveyExtractionProvider.
Stage 2 (future): EasyOCRSurveyExtractionProvider.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from .schemas import ManualSurveyExtractionRequest, SurveyEdgeInput, SurveySource, DistanceUnit, DistanceValue, BearingValue, EdgeType


class SurveyExtractionProvider(ABC):
    """
    Abstract interface for survey extraction.
    Downstream components interact exclusively through this interface.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the identifier of the provider ('manual', 'fixture', 'easyocr')."""
        pass

    @abstractmethod
    def extract_survey(self, context: Dict[str, Any]) -> ManualSurveyExtractionRequest:
        """Extracts or adapts normalized survey measurements."""
        pass


class ManualSurveyExtractionProvider(SurveyExtractionProvider):
    """
    Deterministic Stage-1 manual entry provider.
    Accepts authorized user/test entered boundary parameters following the exact normalized schema.
    """

    @property
    def provider_name(self) -> str:
        return "manual"

    def extract_survey(self, context: Dict[str, Any]) -> ManualSurveyExtractionRequest:
        data = context.get("survey_data")
        if not data:
            raise ValueError("No manual survey data provided in context.")
        if isinstance(data, ManualSurveyExtractionRequest):
            return data
        return ManualSurveyExtractionRequest(**data)


class FixtureSurveyExtractionProvider(SurveyExtractionProvider):
    """
    Deterministic Stage-1 fixture provider for testing, reproducibility, and reference parcels.
    Provides standard test parcels (e.g., standard 10-perch suburban Colombo plot).
    """

    @property
    def provider_name(self) -> str:
        return "fixture"

    def extract_survey(self, context: Dict[str, Any]) -> ManualSurveyExtractionRequest:
        fixture_name = context.get("fixture_name", "standard_10_perch")

        if fixture_name == "rectangular_15x17":
            # 15m x 17m = 255 sqm (~10.08 perches)
            return ManualSurveyExtractionRequest(
                north_angle=0.0,
                reference_edge="E01",
                source=SurveySource.FIXTURE,
                edges=[
                    SurveyEdgeInput(
                        edge_id="E01",
                        distance=DistanceValue(value=15.0, unit=DistanceUnit.METERS),
                        bearing=BearingValue(raw="090°00'00\"", normalized_degrees=90.0),
                        edge_type=EdgeType.ROAD_FRONT,
                        source=SurveySource.FIXTURE
                    ),
                    SurveyEdgeInput(
                        edge_id="E02",
                        distance=DistanceValue(value=17.0, unit=DistanceUnit.METERS),
                        bearing=BearingValue(raw="180°00'00\"", normalized_degrees=180.0),
                        edge_type=EdgeType.SIDE_RIGHT,
                        source=SurveySource.FIXTURE
                    ),
                    SurveyEdgeInput(
                        edge_id="E03",
                        distance=DistanceValue(value=15.0, unit=DistanceUnit.METERS),
                        bearing=BearingValue(raw="270°00'00\"", normalized_degrees=270.0),
                        edge_type=EdgeType.REAR,
                        source=SurveySource.FIXTURE
                    ),
                    SurveyEdgeInput(
                        edge_id="E04",
                        distance=DistanceValue(value=17.0, unit=DistanceUnit.METERS),
                        bearing=BearingValue(raw="000°00'00\"", normalized_degrees=0.0),
                        edge_type=EdgeType.SIDE_LEFT,
                        source=SurveySource.FIXTURE
                    ),
                ]
            )

        # Default: 10-perch suburban residential plot (approx 252.9 sqm)
        # Dimensions: 14.5m road frontage, 17.5m depths, closed loop
        return ManualSurveyExtractionRequest(
            north_angle=0.0,
            reference_edge="E01",
            source=SurveySource.FIXTURE,
            edges=[
                SurveyEdgeInput(
                    edge_id="E01",
                    distance=DistanceValue(value=14.5, unit=DistanceUnit.METERS),
                    bearing=BearingValue(raw="090°00'00\"", normalized_degrees=90.0),
                    edge_type=EdgeType.ROAD_FRONT,
                    source=SurveySource.FIXTURE
                ),
                SurveyEdgeInput(
                    edge_id="E02",
                    distance=DistanceValue(value=17.44, unit=DistanceUnit.METERS),
                    bearing=BearingValue(raw="180°00'00\"", normalized_degrees=180.0),
                    edge_type=EdgeType.SIDE_RIGHT,
                    source=SurveySource.FIXTURE
                ),
                SurveyEdgeInput(
                    edge_id="E03",
                    distance=DistanceValue(value=14.5, unit=DistanceUnit.METERS),
                    bearing=BearingValue(raw="270°00'00\"", normalized_degrees=270.0),
                    edge_type=EdgeType.REAR,
                    source=SurveySource.FIXTURE
                ),
                SurveyEdgeInput(
                    edge_id="E04",
                    distance=DistanceValue(value=17.44, unit=DistanceUnit.METERS),
                    bearing=BearingValue(raw="000°00'00\"", normalized_degrees=0.0),
                    edge_type=EdgeType.SIDE_LEFT,
                    source=SurveySource.FIXTURE
                ),
            ]
        )
