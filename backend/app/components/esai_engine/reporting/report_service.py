"""
Phase 8 Report Service
Coordinates report data extraction, validation, vector layout drawing,
and PDF document generation. Provides portable structured JSON exports.
Strictly excludes budgets, prices, monetary values, and cost calculations.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from app.models.project import Project
from .contracts import (
    PdfReportRequest,
    ReportDataDTO,
    ReportMode,
    ReportOptionsResponse,
    ReportScope,
    ReportSection,
)
from .data_adapter import ReportDataAdapter
from .pdf_builder import PdfReportBuilder


class EsaiReportService:
    """
    Coordinates professional PDF reporting and portable design exports for ESAI-Engine.
    """

    def __init__(self, esai_service: Any):
        self.esai_service = esai_service
        self.data_adapter = ReportDataAdapter(esai_service)
        self.pdf_builder = PdfReportBuilder()

    def get_report_options(self, project: Optional[Project] = None) -> ReportOptionsResponse:
        """
        Returns supported scopes, modes, and available sections for the export UI,
        as well as available floors, rooms, and staleness audit for the selected project.
        """
        floors_info = []
        rooms_info = []
        staleness_info = {}

        if project:
            try:
                floors = self.esai_service.get_floors(project)
                floors_info = [{"id": f.floor_id, "name": f.floor_name or f.floor_id} for f in floors]
            except Exception:
                floors_info = []

            try:
                rooms = self.esai_service.get_rooms(project)
                rooms_info = [{"id": r.room_id, "name": r.name, "floor_id": r.floor_id, "type": r.room_type} for r in rooms]
            except Exception:
                rooms_info = []

            try:
                staleness_info = self.esai_service.persistence_mgr.check_staleness(project).model_dump()
            except Exception:
                staleness_info = {"is_stale": False}

        scopes = [s.value for s in ReportScope]
        sections = [sec.value for sec in ReportSection]

        return ReportOptionsResponse(
            available_scopes=scopes,
            available_modes=[m.value for m in ReportMode],
            available_sections=sections,
            default_sections=[
                ReportSection.COVER.value,
                ReportSection.PROJECT_OVERVIEW.value,
                ReportSection.LAYOUT_DRAWINGS.value,
                ReportSection.FURNITURE_SCHEDULE.value,
                ReportSection.ELECTRICAL_SCHEDULE.value,
                ReportSection.FINISH_SCHEDULE.value,
                ReportSection.ERGONOMIC_VALIDATION.value,
                ReportSection.DISCLAIMERS.value,
            ],
            supported_scopes=scopes,
            supported_sections=sections,
            available_floors=floors_info,
            available_rooms=rooms_info,
            staleness=staleness_info,
        )

    def generate_pdf_report(
        self,
        project: Project,
        request: PdfReportRequest,
    ) -> Tuple[bytes, str]:
        """
        Generates the professional PDF report and returns (pdf_bytes, sanitized_filename).
        """
        # 1. Extract and validate report data
        report_data: ReportDataDTO = self.data_adapter.extract_report_data(project, request)

        # 2. Build PDF Document
        pdf_bytes = self.pdf_builder.build_pdf_bytes(report_data, active_sections=request.sections)

        # 3. Create sanitized filename (ASCII-safe for Content-Disposition HTTP headers)
        import unicodedata
        proj_name = getattr(project, "project_name", getattr(project, "name", "Project"))
        ascii_name = unicodedata.normalize('NFKD', str(proj_name)).encode('ascii', 'ignore').decode('ascii')
        safe_name = re.sub(r"[^\w\-_]", "_", ascii_name).strip("_") or "Project"
        scope_str = request.scope.value
        if request.scope == ReportScope.ROOM and request.target_room_id:
            scope_str = f"Room_{request.target_room_id}"
        elif request.scope == ReportScope.FLOOR and request.target_floor_id:
            scope_str = f"Floor_{request.target_floor_id}"

        filename = f"ESAI_Interior_Report_{safe_name}_{scope_str}_rev{report_data.design_revision}.pdf"
        return pdf_bytes, filename

    def get_export_data(
        self,
        project: Project,
        scope: Any = ReportScope.BUILDING,
        target_floor_id: Optional[str] = None,
        target_room_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Provides a portable structured JSON copy of ESAI-owned design data,
        schedules, and validation results.
        """
        if isinstance(scope, PdfReportRequest):
            req = scope
        else:
            req = PdfReportRequest(
                scope=scope,
                mode=ReportMode.DRAFT,
                target_floor_id=target_floor_id,
                target_room_id=target_room_id,
            )
        report_data: ReportDataDTO = self.data_adapter.extract_report_data(project, req)
        return report_data.model_dump(mode="json")
