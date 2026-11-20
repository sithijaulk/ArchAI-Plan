"""
Phase 8 2D Architectural Vector Drawing Renderer
Generates precise, scale-accurate vector layout drawings using ReportLab Graphics
for inclusion in the PDF interior design reports.
Renders room polygons, walls, doors, windows, and transformed furniture footprints.
"""
import math
from typing import Any, Dict, List, Optional
from reportlab.graphics.shapes import (
    Drawing,
    Group,
    Polygon as DrawPolygon,
    Rect,
    Line,
    String,
    Circle,
)
from reportlab.lib import colors

from .contracts import RoomReportDataDTO, RoomScheduleItemDTO


def _extract_xy(pt: Any) -> tuple[float, float]:
    if isinstance(pt, dict):
        return float(pt.get("x", 0.0)), float(pt.get("y", 0.0))
    elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
        return float(pt[0]), float(pt[1])
    return 0.0, 0.0


class ArchitecturalDrawingRenderer:
    """
    Renders vector architectural layout drawings for room designs on ReportLab Drawings.
    """

    def __init__(
        self,
        canvas_width: float = 460.0,
        canvas_height: float = 230.0,
        margin: float = 25.0,
    ):
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.margin = margin

    def render_room_drawing(
        self,
        room: RoomReportDataDTO,
        placed_assets: List[Dict[str, Any]],
        scale_mode: str = "auto",
    ) -> Drawing:
        """
        Creates a self-contained vector Drawing flowable representing the room layout.
        Supports true physical 1:50 scale, auto-fit with explicit NOT TO SCALE label, and graphic scale bar.
        """
        drawing = Drawing(self.canvas_width, self.canvas_height)

        poly_coords = room.polygon
        if not poly_coords or len(poly_coords) < 3:
            # Fallback placeholder if room polygon is missing
            drawing.add(
                Rect(
                    0, 0, self.canvas_width, self.canvas_height,
                    fillColor=colors.HexColor("#F1F5F9"),
                    strokeColor=colors.HexColor("#CBD5E1"),
                    strokeWidth=1,
                )
            )
            drawing.add(
                String(
                    self.canvas_width / 2, self.canvas_height / 2,
                    "Room boundary geometry unavailable",
                    fontName="Helvetica-Oblique",
                    fontSize=10,
                    fillColor=colors.HexColor("#64748B"),
                    textAnchor="middle",
                )
            )
            return drawing

        # 1. Calculate Bounding Box in meters
        xs = [_extract_xy(pt)[0] for pt in poly_coords]
        ys = [_extract_xy(pt)[1] for pt in poly_coords]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        w_m = max(0.1, max_x - min_x)
        h_m = max(0.1, max_y - min_y)

        # 2. Compute Viewport Scaling (points per meter)
        # At 1:50 scale: 1m = 20mm = 20 * (72 / 25.4) = 56.6929 pt
        SCALE_1_50 = 56.692913
        avail_w = self.canvas_width - self.margin * 2
        avail_h = self.canvas_height - self.margin * 2 - 22.0  # Reserve space for legend & scale bar

        fits_at_1_50 = (w_m * SCALE_1_50 <= avail_w) and (h_m * SCALE_1_50 <= avail_h)

        if scale_mode == "1:50":
            if fits_at_1_50:
                scale = SCALE_1_50
                is_true_scale = True
                scale_label = "Scale: 1:50 @ A4 | Unit: Meters"
            else:
                scale = min(avail_w / w_m, avail_h / h_m)
                is_true_scale = False
                approx_ratio = max(1, round((SCALE_1_50 / scale) * 50))
                scale_label = f"Scale: Exceeds 1:50 (Fit to Page Approx 1:{approx_ratio}) — NOT TO SCALE"
        elif scale_mode == "not_to_scale":
            scale = min(avail_w / w_m, avail_h / h_m)
            is_true_scale = False
            approx_ratio = max(1, round((SCALE_1_50 / scale) * 50))
            scale_label = f"Scale: Fit to Page (Approx 1:{approx_ratio}) — NOT TO SCALE"
        else:  # auto
            if fits_at_1_50:
                scale = SCALE_1_50
                is_true_scale = True
                scale_label = "Scale: 1:50 @ A4 | Unit: Meters"
            else:
                scale = min(avail_w / w_m, avail_h / h_m)
                is_true_scale = False
                approx_ratio = max(1, round((SCALE_1_50 / scale) * 50))
                scale_label = f"Scale: Fit to Page (Approx 1:{approx_ratio}) — NOT TO SCALE"

        # Centering offsets
        rendered_w = w_m * scale
        rendered_h = h_m * scale
        offset_x = self.margin + (avail_w - rendered_w) / 2.0
        offset_y = self.margin + 22.0 + (avail_h - rendered_h) / 2.0

        def to_canvas(x_m: float, y_m: float) -> (float, float):
            cx = offset_x + (x_m - min_x) * scale
            cy = offset_y + (y_m - min_y) * scale
            return cx, cy

        # 3. Background boundary box with grid hint
        drawing.add(
            Rect(
                0, 0, self.canvas_width, self.canvas_height,
                fillColor=colors.HexColor("#FAFAFA"),
                strokeColor=colors.HexColor("#E2E8F0"),
                strokeWidth=0.75,
                rx=4,
                ry=4,
            )
        )

        # 4. Room Floor Polygon
        flat_poly_points: List[float] = []
        for pt in poly_coords:
            px, py = _extract_xy(pt)
            cx, cy = to_canvas(px, py)
            flat_poly_points.extend([cx, cy])

        drawing.add(
            DrawPolygon(
                flat_poly_points,
                fillColor=colors.HexColor("#FFFFFF"),
                strokeColor=colors.HexColor("#1E293B"),
                strokeWidth=2.0,
            )
        )

        # 5. Render Windows (Double blue-grey line along wall segment)
        for win in room.windows:
            start = win.get("start", [0, 0])
            end = win.get("end", [0, 0])
            sx_m, sy_m = _extract_xy(start)
            ex_m, ey_m = _extract_xy(end)
            sx, sy = to_canvas(sx_m, sy_m)
            ex, ey = to_canvas(ex_m, ey_m)

            # Draw aperture opening
            drawing.add(
                Line(
                    sx, sy, ex, ey,
                    strokeColor=colors.HexColor("#0284C7"),
                    strokeWidth=3.5,
                    strokeLineCap=1,
                )
            )
            drawing.add(
                Line(
                    sx, sy, ex, ey,
                    strokeColor=colors.HexColor("#FFFFFF"),
                    strokeWidth=1.5,
                    strokeLineCap=1,
                )
            )

        # 6. Render Doors (Hinged door leaf and protected swing line)
        for dr in room.doors:
            start = dr.get("start", [0, 0])
            end = dr.get("end", [0, 0])
            sx_m, sy_m = _extract_xy(start)
            ex_m, ey_m = _extract_xy(end)
            sx, sy = to_canvas(sx_m, sy_m)
            ex, ey = to_canvas(ex_m, ey_m)

            # Door leaf line
            drawing.add(
                Line(
                    sx, sy, ex, ey,
                    strokeColor=colors.HexColor("#D97706"),
                    strokeWidth=2.5,
                    strokeLineCap=1,
                )
            )

        # 7. Render Placed Furniture Footprints
        for asset in placed_assets:
            dims = asset.get("dimensions", {})
            w = float(dims.get("width", 1.0) if isinstance(dims, dict) else getattr(dims, "width", 1.0))
            d = float(dims.get("depth", 1.0) if isinstance(dims, dict) else getattr(dims, "depth", 1.0))
            pos = asset.get("position", {})
            px = float(pos.get("x", 0.0) if isinstance(pos, dict) else getattr(pos, "x", 0.0))
            py = float(pos.get("y", 0.0) if isinstance(pos, dict) else getattr(pos, "y", 0.0))
            rot_deg = float(asset.get("rotation_deg", 0.0))
            is_locked = bool(asset.get("is_locked", False) or asset.get("is_user_locked", False))
            name = str(asset.get("asset_name", "Item")).split(" ")[0]

            cx, cy = to_canvas(px, py)
            box_w = w * scale
            box_d = d * scale

            # Group for rotation around center (cx, cy)
            asset_grp = Group()
            asset_grp.translate(cx, cy)
            asset_grp.rotate(rot_deg)

            # Footprint rectangle (centered at 0, 0 inside group)
            fill_c = colors.HexColor("#E0F2FE") if not is_locked else colors.HexColor("#FEF3C7")
            stroke_c = colors.HexColor("#0284C7") if not is_locked else colors.HexColor("#D97706")

            asset_grp.add(
                Rect(
                    -box_w / 2.0, -box_d / 2.0,
                    box_w, box_d,
                    fillColor=fill_c,
                    strokeColor=stroke_c,
                    strokeWidth=1.0,
                    rx=1.5, ry=1.5,
                )
            )

            # Front orientation notch
            notch_len = min(6.0, box_d * 0.3)
            asset_grp.add(
                Line(
                    0, -box_d / 2.0,
                    0, -box_d / 2.0 + notch_len,
                    strokeColor=stroke_c,
                    strokeWidth=1.5,
                )
            )

            # Label text
            font_sz = max(6.0, min(8.5, box_w * 0.2))
            asset_grp.add(
                String(
                    0, -font_sz * 0.35,
                    name,
                    fontName="Helvetica-Bold",
                    fontSize=font_sz,
                    fillColor=colors.HexColor("#0F172A"),
                    textAnchor="middle",
                )
            )

            if is_locked:
                asset_grp.add(
                    String(
                        box_w / 2.0 - 5.0, box_d / 2.0 - 6.0,
                        "*",
                        fontName="Helvetica-Bold",
                        fontSize=7.0,
                        fillColor=colors.HexColor("#D97706"),
                        textAnchor="middle",
                    )
                )

            drawing.add(asset_grp)

        # 8. Drawing Title & Dimensions Header
        title_text = f"{room.room_name} ({room.area_sqm:.1f} m² • {w_m:.2f}m × {h_m:.2f}m)"
        drawing.add(
            String(
                12, self.canvas_height - 16,
                title_text,
                fontName="Helvetica-Bold",
                fontSize=9,
                fillColor=colors.HexColor("#0F172A"),
            )
        )

        # 9. Technical Legend at bottom
        legend_y = 6.0
        # Walls
        drawing.add(Line(12, legend_y + 3, 24, legend_y + 3, strokeColor=colors.HexColor("#1E293B"), strokeWidth=2.0))
        drawing.add(String(27, legend_y, "Wall", fontName="Helvetica", fontSize=7, fillColor=colors.HexColor("#475569")))

        # Windows
        drawing.add(Line(48, legend_y + 3, 60, legend_y + 3, strokeColor=colors.HexColor("#0284C7"), strokeWidth=2.5))
        drawing.add(String(63, legend_y, "Window", fontName="Helvetica", fontSize=7, fillColor=colors.HexColor("#475569")))

        # Doors
        drawing.add(Line(96, legend_y + 3, 108, legend_y + 3, strokeColor=colors.HexColor("#D97706"), strokeWidth=2.0))
        drawing.add(String(111, legend_y, "Door", fontName="Helvetica", fontSize=7, fillColor=colors.HexColor("#475569")))

        # Furniture
        drawing.add(Rect(132, legend_y, 7, 5, fillColor=colors.HexColor("#E0F2FE"), strokeColor=colors.HexColor("#0284C7"), strokeWidth=0.8))
        drawing.add(String(142, legend_y, "Furniture", fontName="Helvetica", fontSize=7, fillColor=colors.HexColor("#475569")))

        # Locked
        drawing.add(Rect(178, legend_y, 7, 5, fillColor=colors.HexColor("#FEF3C7"), strokeColor=colors.HexColor("#D97706"), strokeWidth=0.8))
        drawing.add(String(188, legend_y, "Locked (*)", fontName="Helvetica", fontSize=7, fillColor=colors.HexColor("#475569")))

        # 10. Graphic Scale Bar (1 Meter Physical Representation)
        bar_x = 240.0
        bar_len = min(60.0, max(20.0, 1.0 * scale))
        drawing.add(Rect(bar_x, legend_y + 1, bar_len / 2.0, 3, fillColor=colors.HexColor("#0F172A"), strokeColor=colors.HexColor("#0F172A"), strokeWidth=0.5))
        drawing.add(Rect(bar_x + bar_len / 2.0, legend_y + 1, bar_len / 2.0, 3, fillColor=colors.HexColor("#FFFFFF"), strokeColor=colors.HexColor("#0F172A"), strokeWidth=0.5))
        drawing.add(String(bar_x, legend_y - 2, "0", fontName="Helvetica", fontSize=5.5, fillColor=colors.HexColor("#475569"), textAnchor="middle"))
        drawing.add(String(bar_x + bar_len, legend_y - 2, "1m", fontName="Helvetica", fontSize=5.5, fillColor=colors.HexColor("#475569"), textAnchor="middle"))

        # Scale label
        drawing.add(
            String(
                self.canvas_width - 12, legend_y,
                scale_label,
                fontName="Helvetica-Bold" if is_true_scale else "Helvetica-Oblique",
                fontSize=6.8,
                fillColor=colors.HexColor("#0284C7") if is_true_scale else colors.HexColor("#D97706"),
                textAnchor="end",
            )
        )

        return drawing
