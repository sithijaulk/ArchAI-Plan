"""
Phase 8 Professional PDF Document Builder
Assembles multi-page interior design PDF reports using ReportLab Platypus.
Features cover page, executive summary, floor summaries, room sections,
vector 2D layout drawings, optional 3D perspective captures, tabular schedules,
ergonomic provenance, and strict cost-exclusion disclaimers.
"""
import base64
import io
import os
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image as PlatypusImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .contracts import (
    ReportDataDTO,
    ReportMode,
    ReportScope,
    ReportSection,
    RoomReportDataDTO,
)
from .drawing_renderer import ArchitecturalDrawingRenderer


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that computes total page count and adds running headers,
    footers, and page numbers ("Page X of Y"), plus draft watermarks when applicable.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.is_draft = False
        self.project_name = ""

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()

        # Omit headers and footers on Cover Page (Page 1)
        if self._pageNumber > 1:
            # Running Header
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#0F172A"))
            self.drawString(36, 815, "ARCHAI-PLAN | ESAI-ENGINE")

            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawRightString(559, 815, f"{self.project_name} • Interior Design Specification")

            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.5)
            self.line(36, 808, 559, 808)

            # Running Footer
            self.line(36, 36, 559, 36)
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#94A3B8"))
            self.drawString(36, 24, "Confidential Architectural Specification • Component 3 ESAI-Engine • Zero Cost Estimates")
            self.drawRightString(559, 24, f"Page {self._pageNumber} of {page_count}")

        # Watermark on Draft or Stale Reports
        if self.is_draft:
            self.setFont("Helvetica-Bold", 54)
            self.setFillColor(colors.HexColor("#FEE2E2"), alpha=0.35)
            self.translate(297, 420)
            self.rotate(45)
            self.drawCentredString(0, 0, "DRAFT / UNVALIDATED")

        self.restoreState()


class PdfReportBuilder:
    """
    Builds the professional ReportLab Platypus PDF document from ReportDataDTO.
    """

    def __init__(self):
        self.drawing_renderer = ArchitecturalDrawingRenderer(canvas_width=500, canvas_height=220)
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        self.styles.add(
            ParagraphStyle(
                name="ReportCoverTitle",
                fontName="Helvetica-Bold",
                fontSize=24,
                leading=28,
                textColor=colors.HexColor("#0F172A"),
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="ReportCoverSubtitle",
                fontName="Helvetica",
                fontSize=12,
                leading=16,
                textColor=colors.HexColor("#0284C7"),
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="SectionHeading",
                fontName="Helvetica-Bold",
                fontSize=14,
                leading=18,
                textColor=colors.HexColor("#0F172A"),
                spaceBefore=14,
                spaceAfter=6,
                keepWithNext=True,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="SubSectionHeading",
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=15,
                textColor=colors.HexColor("#1E293B"),
                spaceBefore=10,
                spaceAfter=4,
                keepWithNext=True,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="BodyDark",
                fontName="Helvetica",
                fontSize=8.5,
                leading=12,
                textColor=colors.HexColor("#334155"),
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="TableBody",
                fontName="Helvetica",
                fontSize=7.5,
                leading=10,
                textColor=colors.HexColor("#1E293B"),
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="TableHeader",
                fontName="Helvetica-Bold",
                fontSize=7.5,
                leading=10,
                textColor=colors.HexColor("#FFFFFF"),
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="DisclaimerText",
                fontName="Helvetica",
                fontSize=7.5,
                leading=11,
                textColor=colors.HexColor("#475569"),
            )
        )

    def build_pdf(self, report_data: ReportDataDTO, active_sections: Optional[List[ReportSection]] = None) -> bytes:
        """Alias for build_pdf_bytes."""
        return self.build_pdf_bytes(report_data, active_sections=active_sections)

    def build_pdf_bytes(self, report_data: ReportDataDTO, active_sections: Optional[List[ReportSection]] = None) -> bytes:
        """
        Generates and returns the complete PDF document as binary bytes.
        """
        buffer = io.BytesIO()

        # Canvas with 36pt (0.5 in) margins
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=46,
            bottomMargin=46,
        )

        elements: List[Any] = []
        is_draft = report_data.mode == ReportMode.DRAFT or report_data.is_stale

        # 1. Cover Page
        elements.extend(self._build_cover_page(report_data))
        elements.append(PageBreak())

        # 2. Table of Contents & Spatial Index
        elements.extend(self._build_table_of_contents(report_data, active_sections))
        elements.append(PageBreak())

        # 3. Executive Summary & Overview
        elements.extend(self._build_project_overview(report_data))
        elements.append(Spacer(1, 14))

        # 4. Client Preferences Summary
        if not active_sections or ReportSection.CLIENT_PREFERENCES in active_sections:
            elements.extend(self._build_client_preferences(report_data))
            elements.append(Spacer(1, 14))

        # 5. Room-by-Room Sections
        for room in report_data.rooms:
            elements.append(PageBreak())
            elements.extend(self._build_room_section(room, report_data, active_sections))

        # 6. General Disclaimers & Professional Notes
        elements.append(PageBreak())
        elements.extend(self._build_disclaimers(report_data))

        # Canvas Maker with closure for NumberedCanvas metadata
        def canvas_maker(*args, **kwargs):
            c = NumberedCanvas(*args, **kwargs)
            c.is_draft = is_draft
            c.project_name = report_data.project_name
            return c

        doc.build(elements, canvasmaker=canvas_maker)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    def _build_cover_page(self, data: ReportDataDTO) -> List[Any]:
        story = []
        story.append(Spacer(1, 40))

        # Top Tag / Branding
        story.append(Paragraph("ARCHAI-PLAN | COMPONENT 3 — ESAI-ENGINE", self.styles["ReportCoverSubtitle"]))
        story.append(Spacer(1, 12))

        # Main Title
        story.append(Paragraph("INTERIOR DESIGN & MEP SPECIFICATION REPORT", self.styles["ReportCoverTitle"]))
        story.append(Spacer(1, 16))

        # Subtitle
        scope_label = (
            "Entire Building Architecture & Layout"
            if data.scope == ReportScope.BUILDING
            else f"Floor Scope ({len(data.rooms)} rooms)"
            if data.scope == ReportScope.FLOOR
            else f"Single Room Scope ({data.rooms[0].room_name if data.rooms else 'Room'})"
        )
        story.append(
            Paragraph(
                f"Authoritative Spatial Optimization & Technical Schedule • {scope_label}",
                self.styles["BodyDark"],
            )
        )
        story.append(Spacer(1, 24))

        # Decorative Divider
        story.append(HRFlowable(width="100%", thickness=3, color=colors.HexColor("#0284C7"), spaceAfter=24))

        # Project Metadata Table
        status_text = "FINAL VALIDATED" if data.mode == ReportMode.FINAL and not data.is_stale else "DRAFT / UNVALIDATED"
        meta_data = [
            [
                Paragraph("<b>Project Name:</b>", self.styles["TableBody"]),
                Paragraph(data.project_name, self.styles["TableBody"]),
                Paragraph("<b>Design Revision:</b>", self.styles["TableBody"]),
                Paragraph(f"Rev {data.design_revision}", self.styles["TableBody"]),
            ],
            [
                Paragraph("<b>Project ID:</b>", self.styles["TableBody"]),
                Paragraph(data.project_id, self.styles["TableBody"]),
                Paragraph("<b>Geometry Revision:</b>", self.styles["TableBody"]),
                Paragraph(f"Rev {data.geometry_revision}", self.styles["TableBody"]),
            ],
            [
                Paragraph("<b>Report Scope:</b>", self.styles["TableBody"]),
                Paragraph(data.scope.value.capitalize(), self.styles["TableBody"]),
                Paragraph("<b>Preference Revision:</b>", self.styles["TableBody"]),
                Paragraph(f"Rev {data.preference_revision}", self.styles["TableBody"]),
            ],
            [
                Paragraph("<b>Generation Date:</b>", self.styles["TableBody"]),
                Paragraph(data.generated_at, self.styles["TableBody"]),
                Paragraph("<b>Document Status:</b>", self.styles["TableBody"]),
                Paragraph(f"<b>{status_text}</b>", self.styles["TableBody"]),
            ],
            [
                Paragraph("<b>Author / System:</b>", self.styles["TableBody"]),
                Paragraph(data.author_name or "ArchAI-Plan ESAI-Engine", self.styles["TableBody"]),
                Paragraph("<b>Rooms Included:</b>", self.styles["TableBody"]),
                Paragraph(f"{len(data.rooms)} Rooms", self.styles["TableBody"]),
            ],
        ]

        meta_table = Table(meta_data, colWidths=[90, 170, 100, 140])
        meta_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#E2E8F0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        story.append(meta_table)
        story.append(Spacer(1, 30))

        # Staleness Warning Banner if applicable
        if data.is_stale:
            warn_p = Paragraph(
                "<b>⚠️ STALE GEOMETRY NOTICE:</b> The floor plan geometry in projects.master_json was modified "
                "after this interior layout was synthesized. Layout positions may require selective re-optimization.",
                self.styles["DisclaimerText"],
            )
            warn_box = Table([[warn_p]], colWidths=[500])
            warn_box.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#EF4444")),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ])
            )
            story.append(warn_box)
            story.append(Spacer(1, 20))

        # Bottom Disclaimer Callout
        callout_text = (
            "<b>Notice:</b> This document contains verified ergonomic spatial layouts, room furniture schedules, "
            "finishes, and conceptual MEP provisions synthesized through the ESAI Genetic Algorithm. "
            "All electrical socket locations and plumbing provisions are conceptual requirements and require licensed "
            "contractor sign-off. <b>Absolute Exclusion:</b> This report contains no commercial valuations, monetary assessments, or financial provisions."
        )
        callout_box = Table([[Paragraph(callout_text, self.styles["DisclaimerText"])]], colWidths=[500])
        callout_box.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("PADDING", (0, 0), (-1, -1), 10),
            ])
        )
        story.append(callout_box)

        return story

    def _build_table_of_contents(
        self,
        data: ReportDataDTO,
        active_sections: Optional[List[ReportSection]],
    ) -> List[Any]:
        story = []
        story.append(Paragraph("1. Table of Contents & Spatial Directory", self.styles["SectionHeading"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=10))

        # 1. Section Index
        sec_rows = [
            [
                Paragraph("Section", self.styles["TableHeader"]),
                Paragraph("Description", self.styles["TableHeader"]),
                Paragraph("Status", self.styles["TableHeader"]),
            ],
            [
                Paragraph("1. Executive Spatial Overview", self.styles["TableBody"]),
                Paragraph("Master JSON geometry metadata, revision tracking, and project statistics", self.styles["TableBody"]),
                Paragraph("Included", self.styles["TableBody"]),
            ],
            [
                Paragraph("2. Client Preferences", self.styles["TableBody"]),
                Paragraph("Interior aesthetic style, palette, and mandatory room provisions", self.styles["TableBody"]),
                Paragraph("Included" if (not active_sections or ReportSection.CLIENT_PREFERENCES in active_sections) else "Excluded", self.styles["TableBody"]),
            ],
            [
                Paragraph("3. Room Design Specifications", self.styles["TableBody"]),
                Paragraph("Vector 2D drawings, 3D views, furniture, MEP, finishes & ergonomics", self.styles["TableBody"]),
                Paragraph(f"{len(data.rooms)} Room(s)", self.styles["TableBody"]),
            ],
            [
                Paragraph("4. Technical Disclaimers", self.styles["TableBody"]),
                Paragraph("Professional MEP coordination notices and zero-cost exclusion declaration", self.styles["TableBody"]),
                Paragraph("Mandatory", self.styles["TableBody"]),
            ],
        ]
        sec_table = Table(sec_rows, colWidths=[150, 260, 90], repeatRows=1)
        sec_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("PADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(sec_table)
        story.append(Spacer(1, 14))

        # 2. Floor & Room Directory Matrix
        story.append(Paragraph("Floor & Room Directory", self.styles["SubSectionHeading"]))
        dir_rows = [
            [
                Paragraph("Floor", self.styles["TableHeader"]),
                Paragraph("Room Name", self.styles["TableHeader"]),
                Paragraph("Type", self.styles["TableHeader"]),
                Paragraph("Floor Area", self.styles["TableHeader"]),
                Paragraph("Net Wall", self.styles["TableHeader"]),
                Paragraph("Design Status", self.styles["TableHeader"]),
            ]
        ]
        for rm in data.rooms:
            status_str = f"Rev {rm.design_revision} (Saved)" if rm.has_design else "No Design"
            dir_rows.append([
                Paragraph(rm.floor_name, self.styles["TableBody"]),
                Paragraph(rm.room_name, self.styles["TableBody"]),
                Paragraph(rm.room_type.replace("_", " ").title(), self.styles["TableBody"]),
                Paragraph(f"{rm.area_sqm:.2f} m²", self.styles["TableBody"]),
                Paragraph(f"{rm.net_wall_area_sqm:.2f} m²", self.styles["TableBody"]),
                Paragraph(status_str, self.styles["TableBody"]),
            ])

        dir_table = Table(dir_rows, colWidths=[80, 130, 90, 70, 70, 70], repeatRows=1)
        dir_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("PADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(dir_table)
        return story

    def _build_project_overview(self, data: ReportDataDTO) -> List[Any]:
        story = []
        story.append(Paragraph("2. Project & Spatial Overview", self.styles["SectionHeading"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=8))

        p_desc = (
            f"This interior report documents the authoritative design generated for project <b>{data.project_name}</b> "
            f"(ID: <font name='Courier'>{data.project_id}</font>). It encompasses <b>{len(data.rooms)}</b> analyzed room(s) "
            f"derived directly from the central vectorized Master JSON model."
        )
        story.append(Paragraph(p_desc, self.styles["BodyDark"]))
        story.append(Spacer(1, 8))

        # Summary Table
        table_rows = [
            [
                Paragraph("Floor", self.styles["TableHeader"]),
                Paragraph("Room ID", self.styles["TableHeader"]),
                Paragraph("Room Name", self.styles["TableHeader"]),
                Paragraph("Type", self.styles["TableHeader"]),
                Paragraph("Area (m²)", self.styles["TableHeader"]),
                Paragraph("Items", self.styles["TableHeader"]),
                Paragraph("Status", self.styles["TableHeader"]),
            ]
        ]

        total_area = 0.0
        total_items = 0
        for r in data.rooms:
            total_area += r.area_sqm
            items_cnt = len(r.furniture_schedule)
            total_items += items_cnt
            status_badge = "Configured" if r.has_design else "No Design"

            table_rows.append([
                Paragraph(r.floor_name, self.styles["TableBody"]),
                Paragraph(r.room_id, self.styles["TableBody"]),
                Paragraph(r.room_name, self.styles["TableBody"]),
                Paragraph(r.room_type.replace("_", " ").title(), self.styles["TableBody"]),
                Paragraph(f"{r.area_sqm:.1f}", self.styles["TableBody"]),
                Paragraph(str(items_cnt), self.styles["TableBody"]),
                Paragraph(status_badge, self.styles["TableBody"]),
            ])

        # Summary footer row
        table_rows.append([
            Paragraph("<b>Total</b>", self.styles["TableBody"]),
            Paragraph("-", self.styles["TableBody"]),
            Paragraph(f"<b>{len(data.rooms)} Rooms</b>", self.styles["TableBody"]),
            Paragraph("-", self.styles["TableBody"]),
            Paragraph(f"<b>{total_area:.1f} m²</b>", self.styles["TableBody"]),
            Paragraph(f"<b>{total_items}</b>", self.styles["TableBody"]),
            Paragraph("-", self.styles["TableBody"]),
        ])

        summary_table = Table(table_rows, colWidths=[70, 75, 110, 85, 55, 45, 60])
        summary_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F1F5F9")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(summary_table)

        return story

    def _build_client_preferences(self, data: ReportDataDTO) -> List[Any]:
        story = []
        story.append(Paragraph("3. Client Design Preferences", self.styles["SectionHeading"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=8))

        prefs = data.client_preferences
        if not prefs:
            story.append(Paragraph("No explicit custom client preferences recorded. Using standard regional ergonomic defaults.", self.styles["BodyDark"]))
            return story

        story.append(Paragraph("The spatial layout was generated following the registered client preferences:", self.styles["BodyDark"]))
        story.append(Spacer(1, 6))

        pref_rows = [
            [
                Paragraph("Preference Category", self.styles["TableHeader"]),
                Paragraph("Configured Setting", self.styles["TableHeader"]),
                Paragraph("Applied Scope", self.styles["TableHeader"]),
            ]
        ]

        if "style_profile" in prefs:
            pref_rows.append([
                Paragraph("Architectural Style", self.styles["TableBody"]),
                Paragraph(str(prefs["style_profile"]).replace("_", " ").title(), self.styles["TableBody"]),
                Paragraph("Building", self.styles["TableBody"]),
            ])

        if "lighting" in prefs:
            lgt = prefs["lighting"]
            pref_rows.append([
                Paragraph("Lighting Preference", self.styles["TableBody"]),
                Paragraph(f"Ambience: {lgt.get('ambience', 'Neutral')} • Temp: {lgt.get('color_temperature', 'Warm')}", self.styles["TableBody"]),
                Paragraph("All Rooms", self.styles["TableBody"]),
            ])

        if "floors" in prefs or "rooms" in prefs:
            pref_rows.append([
                Paragraph("Room Overrides", self.styles["TableBody"]),
                Paragraph("Individual room furniture quantities and exclusions registered", self.styles["TableBody"]),
                Paragraph("Room Specific", self.styles["TableBody"]),
            ])

        pref_table = Table(pref_rows, colWidths=[140, 240, 120])
        pref_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("PADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(pref_table)

        return story

    def _build_room_section(
        self,
        room: RoomReportDataDTO,
        report_data: ReportDataDTO,
        active_sections: Optional[List[ReportSection]],
    ) -> List[Any]:
        story = []

        # Room Title & Header Bar
        story.append(Paragraph(f"Room Specification: {room.room_name}", self.styles["SectionHeading"]))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284C7"), spaceAfter=6))

        info_text = (
            f"<b>Room ID:</b> {room.room_id} &nbsp;|&nbsp; "
            f"<b>Type:</b> {room.room_type.replace('_', ' ').title()} &nbsp;|&nbsp; "
            f"<b>Floor:</b> {room.floor_name} &nbsp;|&nbsp; "
            f"<b>Floor Area:</b> {room.area_sqm:.2f} m² &nbsp;|&nbsp; "
            f"<b>Perimeter:</b> {room.perimeter_m:.2f} m &nbsp;|&nbsp; "
            f"<b>Net Wall:</b> {room.net_wall_area_sqm:.2f} m² &nbsp;|&nbsp; "
            f"<b>Ceiling:</b> {room.ceiling_height_m:.2f} m &nbsp;|&nbsp; "
            f"<b>Revision:</b> Rev {room.design_revision}"
        )
        story.append(Paragraph(info_text, self.styles["BodyDark"]))
        story.append(Spacer(1, 10))

        if not room.has_design:
            story.append(
                Paragraph(
                    "<i>No saved interior design layout exists for this room. Use the ESAI Genetic Algorithm optimizer "
                    "to generate and save an optimized layout.</i>",
                    self.styles["BodyDark"],
                )
            )
            return story

        # ── 1. 2D Layout Drawing ──────────────────────────────────────────
        if report_data.include_2d_drawings and (not active_sections or ReportSection.LAYOUT_DRAWINGS in active_sections):
            story.append(Paragraph("2D Architectural Layout Drawing (Vector)", self.styles["SubSectionHeading"]))
            # Extract raw asset dicts with actual coordinates and rotations
            placed_raw = [
                {
                    "instance_id": itm.instance_id,
                    "asset_name": itm.asset_name,
                    "dimensions": {"width": itm.width_m, "depth": itm.depth_m},
                    "position": {"x": itm.position_x, "y": itm.position_y},
                    "rotation_deg": itm.rotation_deg,
                    "is_locked": itm.is_locked,
                }
                for itm in room.furniture_schedule
            ]
            scale_mode = getattr(report_data, "drawing_scale_mode", "auto") or "auto"
            drawing = self.drawing_renderer.render_room_drawing(room, placed_raw, scale_mode=scale_mode)
            story.append(drawing)
            story.append(Spacer(1, 10))

        # ── 2. 3D Perspective View (if enabled, with honest disclosure if missing) ────
        if report_data.include_3d_views:
            if room.image_capture_base64:
                try:
                    img_data = room.image_capture_base64
                    if "base64," in img_data:
                        img_data = img_data.split("base64,")[1]
                    decoded_bytes = base64.b64decode(img_data)
                    img_buf = io.BytesIO(decoded_bytes)
                    p_img = PlatypusImage(img_buf, width=460, height=220)
                    story.append(Paragraph("3D Perspective View (Interactive Session Capture)", self.styles["SubSectionHeading"]))
                    story.append(p_img)
                    story.append(Spacer(1, 10))
                except Exception as e:
                    story.append(Paragraph(f"<i>Could not render 3D view: {str(e)}</i>", self.styles["DisclaimerText"]))
            else:
                story.append(Paragraph("3D Perspective View (Interactive Session Capture)", self.styles["SubSectionHeading"]))
                story.append(
                    Paragraph(
                        "<i>No interactive 3D viewport capture was provided for this room during export. Open the room in the 3D Interior Viewer to capture realistic perspective renderings.</i>",
                        self.styles["DisclaimerText"],
                    )
                )
                story.append(Spacer(1, 6))

        # ── 3. Furniture & Fixtures Schedule ──────────────────────────────
        if not active_sections or ReportSection.FURNITURE_SCHEDULE in active_sections:
            story.append(Paragraph("Furniture & Fixture Schedule", self.styles["SubSectionHeading"]))
            furn_rows = [
                [
                    Paragraph("Item Name", self.styles["TableHeader"]),
                    Paragraph("Catalog ID", self.styles["TableHeader"]),
                    Paragraph("W×D×H (m)", self.styles["TableHeader"]),
                    Paragraph("Pos (X,Y) / Rot", self.styles["TableHeader"]),
                    Paragraph("Material / Finish", self.styles["TableHeader"]),
                    Paragraph("Status", self.styles["TableHeader"]),
                ]
            ]
            for f in room.furniture_schedule:
                lock_label = "Locked" if f.is_locked else "Normal"
                furn_rows.append([
                    Paragraph(f.asset_name, self.styles["TableBody"]),
                    Paragraph(f.catalog_id, self.styles["TableBody"]),
                    Paragraph(f"{f.width_m:.2f}×{f.depth_m:.2f}×{f.height_m:.2f}", self.styles["TableBody"]),
                    Paragraph(f"({f.position_x:.2f}, {f.position_y:.2f}) / {f.rotation_deg:.0f}°", self.styles["TableBody"]),
                    Paragraph(f"{f.material}", self.styles["TableBody"]),
                    Paragraph(lock_label, self.styles["TableBody"]),
                ])

            furn_table = Table(furn_rows, colWidths=[110, 80, 75, 95, 95, 45], repeatRows=1)
            furn_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("PADDING", (0, 0), (-1, -1), 3),
                ])
            )
            story.append(furn_table)
            story.append(Spacer(1, 8))

        # ── 4. Lighting & Electrical Schedule ──────────────────────────────
        if not active_sections or ReportSection.ELECTRICAL_SCHEDULE in active_sections:
            if room.service_schedule or room.lighting_schedule:
                story.append(Paragraph("Lighting & Electrical Service Provisions", self.styles["SubSectionHeading"]))
                elec_rows = [
                    [
                        Paragraph("Service ID", self.styles["TableHeader"]),
                        Paragraph("Type", self.styles["TableHeader"]),
                        Paragraph("Purpose / Zone", self.styles["TableHeader"]),
                        Paragraph("Coord (X, Y)", self.styles["TableHeader"]),
                        Paragraph("Height", self.styles["TableHeader"]),
                        Paragraph("Status", self.styles["TableHeader"]),
                    ]
                ]
                for l in room.lighting_schedule:
                    elec_rows.append([
                        Paragraph(l.fixture_id, self.styles["TableBody"]),
                        Paragraph(f"Lighting: {l.fixture_type}", self.styles["TableBody"]),
                        Paragraph(l.purpose, self.styles["TableBody"]),
                        Paragraph(f"({l.position_x:.2f}, {l.position_y:.2f})", self.styles["TableBody"]),
                        Paragraph(f"{l.height_m:.2f}m", self.styles["TableBody"]),
                        Paragraph("Proposed", self.styles["TableBody"]),
                    ])
                for s in room.service_schedule:
                    elec_rows.append([
                        Paragraph(s.point_id, self.styles["TableBody"]),
                        Paragraph(s.service_type.replace("_", " ").title(), self.styles["TableBody"]),
                        Paragraph(s.purpose, self.styles["TableBody"]),
                        Paragraph(f"({s.position_x:.2f}, {s.position_y:.2f})", self.styles["TableBody"]),
                        Paragraph(f"{s.height_m:.2f}m", self.styles["TableBody"]),
                        Paragraph("Proposed MEP", self.styles["TableBody"]),
                    ])

                elec_table = Table(elec_rows, colWidths=[80, 110, 150, 70, 45, 45], repeatRows=1)
                elec_table.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                        ("PADDING", (0, 0), (-1, -1), 3),
                    ])
                )
                story.append(elec_table)
                story.append(Spacer(1, 8))

        # ── 5. Finishes Schedule ──────────────────────────────────────────
        if not active_sections or ReportSection.FINISH_SCHEDULE in active_sections:
            if room.finish_schedule:
                story.append(Paragraph("Surface & Material Finishes", self.styles["SubSectionHeading"]))
                fin_rows = [
                    [
                        Paragraph("Surface", self.styles["TableHeader"]),
                        Paragraph("Finish Name", self.styles["TableHeader"]),
                        Paragraph("Category", self.styles["TableHeader"]),
                        Paragraph("Color / Tone", self.styles["TableHeader"]),
                        Paragraph("Est. Area", self.styles["TableHeader"]),
                    ]
                ]
                for fn in room.finish_schedule:
                    fin_rows.append([
                        Paragraph(fn.surface_type, self.styles["TableBody"]),
                        Paragraph(fn.finish_name, self.styles["TableBody"]),
                        Paragraph(fn.material_category, self.styles["TableBody"]),
                        Paragraph(fn.color_or_pattern, self.styles["TableBody"]),
                        Paragraph(f"{fn.coverage_area_sqm:.1f} m²" if fn.coverage_area_sqm else "-", self.styles["TableBody"]),
                    ])
                fin_table = Table(fin_rows, colWidths=[70, 150, 120, 100, 60], repeatRows=1)
                fin_table.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                        ("PADDING", (0, 0), (-1, -1), 3),
                    ])
                )
                story.append(fin_table)
                story.append(Spacer(1, 8))

        # ── 6. Ergonomic Validation Provenance ────────────────────────────
        if not active_sections or ReportSection.ERGONOMIC_VALIDATION in active_sections:
            if room.validation_items:
                story.append(Paragraph("Ergonomic Compliance & Rule Provenance", self.styles["SubSectionHeading"]))
                ergo_rows = [
                    [
                        Paragraph("Rule ID", self.styles["TableHeader"]),
                        Paragraph("Standard Reference", self.styles["TableHeader"]),
                        Paragraph("Edition / Section", self.styles["TableHeader"]),
                        Paragraph("Required Clearance", self.styles["TableHeader"]),
                        Paragraph("Status", self.styles["TableHeader"]),
                    ]
                ]
                for v in room.validation_items:
                    cite_text = f"{v.standard_edition} • {v.standard_section}" if (v.standard_edition and v.standard_section) else (v.standard_edition or v.standard_section or "-")
                    ergo_rows.append([
                        Paragraph(v.rule_id, self.styles["TableBody"]),
                        Paragraph(v.standard_source, self.styles["TableBody"]),
                        Paragraph(cite_text, self.styles["TableBody"]),
                        Paragraph(f"{v.required_clearance_m:.2f} m" if v.required_clearance_m else "-", self.styles["TableBody"]),
                        Paragraph(v.status, self.styles["TableBody"]),
                    ])
                ergo_table = Table(ergo_rows, colWidths=[80, 160, 130, 80, 50], repeatRows=1)
                ergo_table.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                        ("PADDING", (0, 0), (-1, -1), 3),
                    ])
                )
                story.append(ergo_table)
                story.append(Spacer(1, 8))

        # ── 7. GA Optimization & Spatial Metrics Summary ──────────────────
        if not active_sections or ReportSection.OPTIMIZATION_SUMMARY in active_sections:
            if room.optimization_summary:
                opt = room.optimization_summary
                story.append(Paragraph("Genetic Layout Optimization Statistics", self.styles["SubSectionHeading"]))
                opt_rows = [
                    [
                        Paragraph("Metric", self.styles["TableHeader"]),
                        Paragraph("Recorded Value", self.styles["TableHeader"]),
                        Paragraph("Evaluation Standard / Gate Criteria", self.styles["TableHeader"]),
                    ],
                    [
                        Paragraph("Algorithm Engine", self.styles["TableBody"]),
                        Paragraph(opt.algorithm_name, self.styles["TableBody"]),
                        Paragraph("PyGAD Real-Valued Continuous Optimizer", self.styles["TableBody"]),
                    ],
                    [
                        Paragraph("Optimization Generations", self.styles["TableBody"]),
                        Paragraph(str(opt.generations) if opt.generations is not None else "Direct / Baseline", self.styles["TableBody"]),
                        Paragraph("Convergence criteria met", self.styles["TableBody"]),
                    ],
                    [
                        Paragraph("Fitness Score", self.styles["TableBody"]),
                        Paragraph(f"{opt.fitness_score:.3f}", self.styles["TableBody"]),
                        Paragraph("Weighted multi-objective ergonomic function", self.styles["TableBody"]),
                    ],
                    [
                        Paragraph("Hard Constraints", self.styles["TableBody"]),
                        Paragraph("PASSED" if opt.hard_constraints_passed else "VIOLATION", self.styles["TableBody"]),
                        Paragraph("Boundary containment & clearance non-overlap", self.styles["TableBody"]),
                    ],
                    [
                        Paragraph("Out-of-Bounds Overlap", self.styles["TableBody"]),
                        Paragraph(f"{opt.out_of_bounds_area_sqm:.4f} m²", self.styles["TableBody"]),
                        Paragraph("Must equal 0.0000 m²", self.styles["TableBody"]),
                    ],
                ]
                opt_table = Table(opt_rows, colWidths=[140, 130, 230], repeatRows=1)
                opt_table.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                        ("PADDING", (0, 0), (-1, -1), 3),
                    ])
                )
                story.append(opt_table)
                story.append(Spacer(1, 8))

        return story

    def _build_disclaimers(self, data: ReportDataDTO) -> List[Any]:
        story = []
        story.append(Paragraph("Appendix: Technical Assumptions & Disclaimers", self.styles["SectionHeading"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=8))

        for disc in data.general_disclaimers:
            bullet_text = f"• {disc}"
            story.append(Paragraph(bullet_text, self.styles["DisclaimerText"]))
            story.append(Spacer(1, 4))

        if data.custom_notes:
            story.append(Spacer(1, 8))
            story.append(Paragraph("<b>Project Notes:</b>", self.styles["SubSectionHeading"]))
            story.append(Paragraph(data.custom_notes, self.styles["BodyDark"]))

        return story
