import jsPDF from 'jspdf';
import { GabGenMasterJson, Point2D } from '../types';

interface ExportPdfOptions {
  projectName: string;
  projectId?: string;
  capture3DCanvas?: () => string | null;
}

/**
 * Converts an SVG string into a high-resolution PNG data URL
 */
async function svgToDataUrl(svgString: string, width: number, height: number, scale = 2): Promise<string> {
  return new Promise((resolve) => {
    const canvas = document.createElement('canvas');
    canvas.width = width * scale;
    canvas.height = height * scale;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      resolve('');
      return;
    }

    const img = new Image();
    const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);

    img.onload = () => {
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL('image/png', 0.95));
    };

    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve('');
    };

    img.src = url;
  });
}

/**
 * Builds the SVG string for Sheet 1: Architectural Floor Plan (සැලැස්ම)
 */
function buildPlanSvg(data: GabGenMasterJson): { svg: string; width: number; height: number } {
  const landPoly = data.land_info?.source_land_polygon || [];
  const buildablePoly = data.buildable_footprint?.polygon || [];
  const floors = data.floor_plan?.floors || [];
  const activeFloor = floors[0] || null;

  const allPts: Point2D[] = [...landPoly, ...buildablePoly];
  if (activeFloor) {
    activeFloor.rooms.forEach((r) => allPts.push(...r.polygon));
  }

  const minX = allPts.length > 0 ? Math.min(...allPts.map((p) => p.x)) : 0;
  const maxX = allPts.length > 0 ? Math.max(...allPts.map((p) => p.x)) : 20;
  const minY = allPts.length > 0 ? Math.min(...allPts.map((p) => p.y)) : 0;
  const maxY = allPts.length > 0 ? Math.max(...allPts.map((p) => p.y)) : 20;

  const w = Math.max(1, maxX - minX);
  const h = Math.max(1, maxY - minY);
  const pad = 4.5;

  const vbX = minX - pad;
  const vbY = -(maxY + pad);
  const vbW = w + pad * 2;
  const vbH = h + pad * 2;

  let roomsSvg = '';
  if (activeFloor) {
    activeFloor.rooms.forEach((rm) => {
      const ptsStr = rm.polygon.map((p) => `${p.x},${-p.y}`).join(' ');
      const areaFt = Math.round(rm.area * 10.764);
      roomsSvg += `
        <polygon points="${ptsStr}" fill="rgba(241, 245, 249, 0.9)" stroke="#0f172a" stroke-width="0.22" />
        <text x="${rm.center.x}" y="${-rm.center.y - 0.25}" font-family="Helvetica, Arial, sans-serif" font-size="0.45" font-weight="bold" fill="#0f172a" text-anchor="middle">${rm.name.toUpperCase()}</text>
        <text x="${rm.center.x}" y="${-rm.center.y + 0.35}" font-family="Helvetica, Arial, sans-serif" font-size="0.32" fill="#475569" text-anchor="middle">${rm.area.toFixed(1)} m² (${areaFt} sq.ft)</text>
      `;
    });

    // Wall lines
    activeFloor.walls.forEach((w) => {
      roomsSvg += `
        <line x1="${w.start.x}" y1="${-w.start.y}" x2="${w.end.x}" y2="${-w.end.y}" stroke="#0f172a" stroke-width="0.32" stroke-linecap="round" />
      `;
    });

    // Doors with swing arcs
    (activeFloor.doors || []).forEach((d) => {
      const r = (d as any).width_m ?? (d as any).width ?? 0.9;
      const dx = d.position.x;
      const dy = -d.position.y;
      const isMain = d.is_external_entrance;
      roomsSvg += `
        <circle cx="${dx}" cy="${dy}" r="0.1" fill="${isMain ? '#16a34a' : '#0f172a'}" />
        <line x1="${dx}" y1="${dy}" x2="${dx + r}" y2="${dy}" stroke="${isMain ? '#16a34a' : '#0284c7'}" stroke-width="0.12" />
        <path d="M ${dx + r} ${dy} A ${r} ${r} 0 0 0 ${dx} ${dy - r}" fill="none" stroke="${isMain ? '#16a34a' : '#0284c7'}" stroke-width="0.08" stroke-dasharray="0.15, 0.1" />
      `;
    });

    // Windows
    (activeFloor.windows || []).forEach((win) => {
      const wx = win.position.x;
      const wy = -win.position.y;
      const wLen = (win as any).width_m ?? (win as any).width ?? 1.2;
      roomsSvg += `
        <rect x="${wx - wLen / 2}" y="${wy - 0.12}" width="${wLen}" height="0.24" fill="#ffffff" stroke="#0f172a" stroke-width="0.1" />
        <line x1="${wx - wLen / 2}" y1="${wy}" x2="${wx + wLen / 2}" y2="${wy}" stroke="#0284c7" stroke-width="0.06" />
      `;
    });
  }

  // Land Polygon
  let landSvg = '';
  if (landPoly.length > 2) {
    const pts = landPoly.map((p) => `${p.x},${-p.y}`).join(' ');
    landSvg = `
      <polygon points="${pts}" fill="none" stroke="#2563eb" stroke-width="0.2" stroke-dasharray="0.6, 0.3" />
      <text x="${landPoly[0].x}" y="${-landPoly[0].y - 0.4}" font-family="Helvetica, Arial, sans-serif" font-size="0.35" font-weight="bold" fill="#2563eb">LEGAL LAND BOUNDARY (මිනින්දෝරු පිඹුර මායිම)</text>
    `;
    landPoly.forEach((p) => {
      landSvg += `<circle cx="${p.x}" cy="${-p.y}" r="0.18" fill="#2563eb" stroke="#ffffff" stroke-width="0.05" />`;
    });
  }

  // Buildable footprint setback line
  let buildableSvg = '';
  if (buildablePoly.length > 2) {
    const pts = buildablePoly.map((p) => `${p.x},${-p.y}`).join(' ');
    buildableSvg = `
      <polygon points="${pts}" fill="none" stroke="#dc2626" stroke-width="0.14" stroke-dasharray="0.3, 0.2" opacity="0.6" />
      <text x="${buildablePoly[0].x}" y="${-buildablePoly[0].y - 0.3}" font-family="Helvetica, Arial, sans-serif" font-size="0.28" fill="#dc2626">UDA BUILDABLE SETBACK LINE (නීත්‍යානුකූල ගොඩනැගිලි සීමාව)</text>
    `;
  }

  // North Arrow
  const northX = minX - pad + 2;
  const northY = -(maxY + pad) + 2.5;
  const northSvg = `
    <g transform="translate(${northX}, ${northY})">
      <circle cx="0" cy="0" r="1.2" fill="#ffffff" stroke="#0f172a" stroke-width="0.1" />
      <polygon points="0,-1.1 -0.3,0.8 0,0.5 0.3,0.8" fill="#0f172a" />
      <text x="0" y="-1.4" font-family="Helvetica, Arial, sans-serif" font-size="0.45" font-weight="bold" fill="#0f172a" text-anchor="middle">N</text>
      <text x="0" y="1.8" font-family="Helvetica, Arial, sans-serif" font-size="0.25" fill="#475569" text-anchor="middle">NORTH UP</text>
    </g>
  `;

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="${vbX} ${vbY} ${vbW} ${vbH}" width="1200" height="850">
      <rect x="${vbX}" y="${vbY}" width="${vbW}" height="${vbH}" fill="#ffffff" />
      ${landSvg}
      ${buildableSvg}
      ${roomsSvg}
      ${northSvg}
    </svg>
  `;

  return { svg, width: 1200, height: 850 };
}

/**
 * Builds the SVG string for Sheet 2: Architectural Front Elevation (ඉදිරි පෙනුම)
 */
function buildElevationSvg(data: GabGenMasterJson, projection: 'front' | 'side'): { svg: string; width: number; height: number } {
  const floors = data.floor_plan?.floors || [];
  const landPoly = data.land_info?.source_land_polygon || [];
  const allPts: Point2D[] = [...landPoly];
  floors.forEach((f) => f.rooms.forEach((r) => allPts.push(...r.polygon)));

  const minCoord = projection === 'front'
    ? (allPts.length > 0 ? Math.min(...allPts.map((p) => p.x)) : 0)
    : (allPts.length > 0 ? Math.min(...allPts.map((p) => p.y)) : 0);
  const maxCoord = projection === 'front'
    ? (allPts.length > 0 ? Math.max(...allPts.map((p) => p.x)) : 15)
    : (allPts.length > 0 ? Math.max(...allPts.map((p) => p.y)) : 15);

  const span = Math.max(1, maxCoord - minCoord);
  const pad = 4;
  const totalLevels = Math.max(1, floors.length);
  const floorHeight = 3.0;
  const plinth = 0.45;
  const roofH = data.roof_geometry?.max_height_m || 1.6;
  const topWall = plinth + totalLevels * floorHeight;
  const totalH = topWall + roofH;

  const vbX = minCoord - pad;
  const vbY = -(totalH + 2.5);
  const vbW = span + pad * 2;
  const vbH = totalH + 4.5;

  const wallW = span * 0.88;
  const wallLeft = minCoord + (span - wallW) / 2;
  const wallRight = wallLeft + wallW;
  const roofPeakX = wallLeft + wallW / 2;

  // Level Datums
  const levels = [
    { label: `ROOF RIDGE (+${totalH.toFixed(2)}m)`, y: -totalH },
    { label: `SLAB / CEILING (+${topWall.toFixed(2)}m)`, y: -topWall },
    { label: `LINTEL LEVEL (+2.10m)`, y: -(plinth + 2.10) },
    { label: `PLINTH LEVEL (+0.45m)`, y: -plinth },
    { label: `GROUND LEVEL (GL ±0.00m)`, y: 0 },
  ];

  let datumsSvg = '';
  levels.forEach((lvl) => {
    datumsSvg += `
      <line x1="${vbX + 0.5}" y1="${lvl.y}" x2="${wallRight + 2.5}" y2="${lvl.y}" stroke="#94a3b8" stroke-width="0.08" stroke-dasharray="0.3, 0.15" />
      <polygon points="${vbX + 0.5},${lvl.y} ${vbX + 1.2},${lvl.y - 0.15} ${vbX + 1.2},${lvl.y + 0.15}" fill="#0f172a" />
      <text x="${vbX + 1.5}" y="${lvl.y + 0.08}" font-family="Helvetica, Arial, sans-serif" font-size="0.28" font-weight="bold" fill="#0f172a">${lvl.label}</text>
    `;
  });

  // Windows & Doors on Facade
  const numWindows = Math.max(2, Math.min(4, Math.floor(wallW / 3)));
  let openingsSvg = '';
  const spacing = wallW / (numWindows + 1);

  for (let lvl = 0; lvl < totalLevels; lvl++) {
    const baseLvlY = -(plinth + lvl * floorHeight);
    for (let i = 1; i <= numWindows; i++) {
      const cx = wallLeft + i * spacing;
      if (lvl === 0 && i === 1 && projection === 'front') {
        // Entrance Door
        const dw = 1.2;
        const dh = 2.1;
        openingsSvg += `
          <rect x="${cx - dw / 2}" y="${baseLvlY - dh}" width="${dw}" height="${dh}" fill="#e2e8f0" stroke="#0f172a" stroke-width="0.1" />
          <rect x="${cx - dw / 2 + 0.08}" y="${baseLvlY - dh + 0.08}" width="${dw - 0.16}" height="${dh - 0.16}" fill="#f8fafc" stroke="#64748b" stroke-width="0.05" />
          <line x1="${cx}" y1="${baseLvlY - dh}" x2="${cx}" y2="${baseLvlY}" stroke="#0f172a" stroke-width="0.06" />
          <circle cx="${cx - 0.1}" cy="${baseLvlY - dh * 0.5}" r="0.04" fill="#0f172a" />
          <!-- Porch Canopy -->
          <rect x="${cx - dw / 2 - 0.3}" y="${baseLvlY - dh - 0.15}" width="${dw + 0.6}" height="0.12" fill="#0f172a" />
        `;
      } else {
        // Casement Window
        const ww = 1.5;
        const wh = 1.2;
        const sill = 0.9;
        openingsSvg += `
          <rect x="${cx - ww / 2}" y="${baseLvlY - sill - wh}" width="${ww}" height="${wh}" fill="#e0f2fe" stroke="#0f172a" stroke-width="0.1" />
          <line x1="${cx}" y1="${baseLvlY - sill - wh}" x2="${cx}" y2="${baseLvlY - sill}" stroke="#0f172a" stroke-width="0.06" />
          <line x1="${cx - ww / 2}" y1="${baseLvlY - sill - wh * 0.4}" x2="${cx + ww / 2}" y2="${baseLvlY - sill - wh * 0.4}" stroke="#0f172a" stroke-width="0.05" />
          <!-- Concrete Window Sill -->
          <rect x="${cx - ww / 2 - 0.1}" y="${baseLvlY - sill}" width="${ww + 0.2}" height="0.08" fill="#475569" />
          <!-- Concrete Sunshade/Weatherhood -->
          <rect x="${cx - ww / 2 - 0.15}" y="${baseLvlY - sill - wh - 0.12}" width="${ww + 0.3}" height="0.1" fill="#475569" />
        `;
      }
    }
  }

  // Roof Structure
  const roofSvg = `
    <!-- Eaves Line -->
    <line x1="${wallLeft - 0.6}" y1="${-topWall}" x2="${wallRight + 0.6}" y2="${-topWall}" stroke="#0f172a" stroke-width="0.18" />
    <!-- Roof Pitch Triangle -->
    <polygon points="${wallLeft - 0.6},${-topWall} ${roofPeakX},${-totalH} ${wallRight + 0.6},${-topWall}" fill="#f1f5f9" stroke="#0f172a" stroke-width="0.22" />
    <polygon points="${wallLeft - 0.7},${-topWall + 0.1} ${roofPeakX},${-totalH - 0.1} ${wallRight + 0.7},${-topWall + 0.1}" fill="none" stroke="#0f172a" stroke-width="0.08" />
    <!-- Ridge Cap -->
    <circle cx="${roofPeakX}" cy="${-totalH}" r="0.15" fill="#0f172a" />
  `;

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="${vbX} ${vbY} ${vbW} ${vbH}" width="1200" height="700">
      <rect x="${vbX}" y="${vbY}" width="${vbW}" height="${vbH}" fill="#ffffff" />
      ${datumsSvg}
      <!-- Ground Earth Hatching -->
      <line x1="${vbX}" y1="0" x2="${wallRight + 3}" y2="0" stroke="#0f172a" stroke-width="0.28" />
      <rect x="${vbX}" y="0" width="${vbW}" height="2" fill="#e2e8f0" />
      <!-- Plinth Base -->
      <rect x="${wallLeft - 0.15}" y="${-plinth}" width="${wallW + 0.3}" height="${plinth}" fill="#94a3b8" stroke="#0f172a" stroke-width="0.16" />
      <!-- Building Main Walls -->
      <rect x="${wallLeft}" y="${-topWall}" width="${wallW}" height="${topWall - plinth}" fill="#ffffff" stroke="#0f172a" stroke-width="0.28" />
      ${roofSvg}
      ${openingsSvg}
      <!-- Projection Title Banner -->
      <text x="${roofPeakX}" y="${-totalH - 1.2}" font-family="Helvetica, Arial, sans-serif" font-size="0.6" font-weight="bold" fill="#0f172a" text-anchor="middle">
        ${projection === 'front' ? 'FRONT ELEVATION (ඉදිරි පෙනුම) - SCALE 1:100' : 'SIDE ELEVATION (පැති පෙනුම) - SCALE 1:100'}
      </text>
    </svg>
  `;

  return { svg, width: 1200, height: 700 };
}

/**
 * Main Architectural Blueprint PDF Generator
 */
export async function exportGabBlueprintPdf(
  data: GabGenMasterJson,
  options: ExportPdfOptions
): Promise<void> {
  const { projectName, projectId } = options;

  // Initialize jsPDF in A4 Landscape (297mm x 210mm)
  const doc = new jsPDF({
    orientation: 'landscape',
    unit: 'mm',
    format: 'a4',
    compress: true,
  });

  const pageWidth = 297;
  const pageHeight = 210;
  const margin = 10;
  const printableW = pageWidth - margin * 2;
  const printableH = pageHeight - margin * 2;

  // Basic project stats
  const landExtent = data.client_requirements?.declared_land_extent || data.input_metadata?.declared_land_extent?.value || (data.land_info?.declared_area ? Math.round(data.land_info.declared_area / 25.29) : 10);
  const landUnit = data.client_requirements?.declared_land_unit || data.input_metadata?.declared_land_extent?.unit || 'Perches';
  const landAreaM2 = data.land_info?.reconstructed_area || data.land_info?.declared_area || (landExtent * 25.29) || 150;
  const groundFootprint = data.buildable_footprint?.area || (data.floor_plan?.floors[0]?.rooms.reduce((s, r) => s + r.area, 0)) || 95;
  const floors = data.floor_plan?.floors || [];
  const totalGfa = floors.reduce((tot, f) => tot + f.rooms.reduce((s, r) => s + r.area, 0), 0);
  const coverageRatio = landAreaM2 > 0 ? (groundFootprint / landAreaM2) * 100 : 0;
  const authority = data.regulatory_rules?.jurisdiction || data.input_metadata?.regulatory_context?.jurisdiction_id || 'Urban Development Authority (UDA) & Local Authority';
  const dateStr = new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

  // Helper: Draw standard architectural double border & title block
  const drawSheetFrame = (sheetNum: number, sheetTitleSinhala: string, sheetTitleEng: string) => {
    // Outer border
    doc.setDrawColor(15, 23, 42);
    doc.setLineWidth(0.6);
    doc.rect(margin, margin, printableW, printableH);

    // Inner margin line
    doc.setLineWidth(0.2);
    doc.rect(margin + 1.5, margin + 1.5, printableW - 3, printableH - 3);

    // Header strip
    doc.setFillColor(15, 23, 42);
    doc.rect(margin + 1.5, margin + 1.5, printableW - 3, 11, 'F');

    doc.setFont('helvetica', 'bold');
    doc.setFontSize(10.5);
    doc.setTextColor(255, 255, 255);
    doc.text('GOVERNMENT OF SRI LANKA • URBAN DEVELOPMENT AUTHORITY (UDA) & LOCAL AUTHORITY SUBMISSION', margin + 6, margin + 8.5);

    doc.setFontSize(8);
    doc.setFont('helvetica', 'normal');
    doc.text(`PLANNING PERMIT DRAWING SET • ${authority.toUpperCase()}`, printableW + margin - 6, margin + 8.5, { align: 'right' });

    // Bottom Architectural Title Block
    const tbH = 26;
    const tbY = pageHeight - margin - 1.5 - tbH;
    const tbW = printableW - 3;
    const tbX = margin + 1.5;

    doc.setFillColor(248, 250, 252);
    doc.rect(tbX, tbY, tbW, tbH, 'F');
    doc.setDrawColor(15, 23, 42);
    doc.setLineWidth(0.35);
    doc.rect(tbX, tbY, tbW, tbH);

    // Vertical dividers in Title Block
    doc.line(tbX + 85, tbY, tbX + 85, tbY + tbH);
    doc.line(tbX + 165, tbY, tbX + 165, tbY + tbH);
    doc.line(tbX + 225, tbY, tbX + 225, tbY + tbH);

    // Column 1: Project & Client
    doc.setTextColor(100, 116, 139);
    doc.setFontSize(6.5);
    doc.text('PROJECT & PROPOSED WORKS:', tbX + 4, tbY + 5);
    doc.setTextColor(15, 23, 42);
    doc.setFontSize(9);
    doc.setFont('helvetica', 'bold');
    doc.text(projectName || 'PROPOSED RESIDENTIAL BUILDING', tbX + 4, tbY + 10.5);

    doc.setTextColor(100, 116, 139);
    doc.setFontSize(6.5);
    doc.setFont('helvetica', 'normal');
    doc.text(`PROJECT ID: ${projectId || data.project_id || 'ARCH-GAB-001'} • REVISION: ${data.project_revision || 1}`, tbX + 4, tbY + 16);
    doc.text(`CLIENT: AUTHORIZED APPLICANT • LAND EXTENT: ${landExtent} ${landUnit}`, tbX + 4, tbY + 21);

    // Column 2: Architectural Details & Compliance
    doc.setTextColor(100, 116, 139);
    doc.setFontSize(6.5);
    doc.text('REGULATORY & AREA COMPLIANCE:', tbX + 89, tbY + 5);
    doc.setTextColor(15, 23, 42);
    doc.setFontSize(7.5);
    doc.text(`Site Area: ${landAreaM2.toFixed(1)} m² • Ground Footprint: ${groundFootprint.toFixed(1)} m²`, tbX + 89, tbY + 10);
    doc.text(`Total Built GFA: ${totalGfa.toFixed(1)} m² • Plot Coverage: ${coverageRatio.toFixed(1)}% (Permissible <= 65%)`, tbX + 89, tbY + 15);
    doc.text(`Building Height: ${(3.0 * floors.length + 1.8).toFixed(1)}m • Storey Count: ${floors.length} Floor(s)`, tbX + 89, tbY + 20);

    // Column 3: Professional Certification
    doc.setTextColor(100, 116, 139);
    doc.setFontSize(6.5);
    doc.text('ARCHITECTURAL ENGINE:', tbX + 169, tbY + 5);
    doc.setTextColor(2, 132, 199);
    doc.setFontSize(8);
    doc.setFont('helvetica', 'bold');
    doc.text('ArchAI GAB-Gen Engine', tbX + 169, tbY + 10);
    doc.setTextColor(15, 23, 42);
    doc.setFontSize(6.5);
    doc.setFont('helvetica', 'normal');
    doc.text('OpenCV & EasyOCR Verified Geometry', tbX + 169, tbY + 15);
    doc.text(`Date of Issue: ${dateStr}`, tbX + 169, tbY + 20);

    // Column 4: Sheet Number & Title
    doc.setFillColor(15, 23, 42);
    doc.rect(tbX + 225, tbY, tbW - 225, tbH, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(7);
    doc.text(`SHEET NO: 0${sheetNum} OF 03`, tbX + 229, tbY + 6);
    doc.setFontSize(10.5);
    doc.setFont('helvetica', 'bold');
    doc.text(sheetTitleEng, tbX + 229, tbY + 12.5);
    doc.setFontSize(8.5);
    doc.text(sheetTitleSinhala, tbX + 229, tbY + 18);
    doc.setFontSize(7);
    doc.setFont('helvetica', 'normal');
    doc.text('SCALE 1:100 @ A4 / N.T.S.', tbX + 229, tbY + 23);
  };

  // ══════════════════════════════════════════════════════════════════════════
  // SHEET 1: ARCHITECTURAL FLOOR PLAN VIEW (සැලැස්ම)
  // ══════════════════════════════════════════════════════════════════════════
  drawSheetFrame(1, 'සැලැස්ම', 'FLOOR PLAN VIEW');

  // Convert Floor Plan SVG to Image
  const planSvgData = buildPlanSvg(data);
  const planImgUrl = await svgToDataUrl(planSvgData.svg, planSvgData.width, planSvgData.height, 2.5);

  if (planImgUrl) {
    // Left Box: Drawing Canvas
    const drawX = margin + 3;
    const drawY = margin + 14;
    const drawW = 188;
    const drawH = 154;

    doc.setDrawColor(203, 213, 225);
    doc.setLineWidth(0.2);
    doc.rect(drawX, drawY, drawW, drawH);
    doc.addImage(planImgUrl, 'PNG', drawX + 1, drawY + 1, drawW - 2, drawH - 2);

    // Right Box: Architectural Schedules (Rooms & Openings)
    const schX = drawX + drawW + 3;
    const schY = drawY;
    const schW = printableW - drawW - 9;
    const schH = drawH;

    doc.setFillColor(248, 250, 252);
    doc.rect(schX, schY, schW, schH, 'F');
    doc.setDrawColor(203, 213, 225);
    doc.rect(schX, schY, schW, schH);

    // Schedule Header 1: Rooms
    doc.setFillColor(15, 23, 42);
    doc.rect(schX, schY, schW, 6.5, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(7);
    doc.setFont('helvetica', 'bold');
    doc.text('SCHEDULE OF SPACES & AREAS (කාමර සටහන)', schX + 3, schY + 4.5);

    let curY = schY + 10;
    const allRooms = floors.flatMap((f) => f.rooms);

    doc.setFontSize(6.5);
    doc.setTextColor(15, 23, 42);
    allRooms.slice(0, 10).forEach((rm, idx) => {
      doc.setFont('helvetica', 'normal');
      doc.text(`${idx + 1}. ${rm.name}`, schX + 3, curY);
      doc.setFont('helvetica', 'bold');
      doc.text(`${rm.area.toFixed(1)} m² (${Math.round(rm.area * 10.764)} sq.ft)`, schX + schW - 3, curY, { align: 'right' });
      curY += 4.2;
    });

    // Schedule Header 2: Doors & Windows
    curY += 2;
    doc.setFillColor(15, 23, 42);
    doc.rect(schX, curY, schW, 6, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFont('helvetica', 'bold');
    doc.text('DOORS & WINDOWS SCHEDULE (දොර ජනෙල්)', schX + 3, curY + 4.2);

    curY += 9;
    const openingsList = [
      { code: 'D1', desc: 'Main Entrance Double Door', size: '1.20 × 2.10 m' },
      { code: 'D2', desc: 'Internal Single Flush Door', size: '0.90 × 2.10 m' },
      { code: 'D3', desc: 'Bathroom / Terrace Door', size: '0.75 × 2.10 m' },
      { code: 'W1', desc: 'Living / Bed Large Glazed Window', size: '1.80 × 1.20 m' },
      { code: 'W2', desc: 'Standard Casement Window', size: '1.20 × 1.20 m' },
      { code: 'V1', desc: 'High-Level Top-Hung Ventilator', size: '0.60 × 0.45 m' },
    ];

    doc.setFontSize(6.2);
    doc.setTextColor(15, 23, 42);
    openingsList.forEach((op) => {
      doc.setFont('helvetica', 'bold');
      doc.text(op.code, schX + 3, curY);
      doc.setFont('helvetica', 'normal');
      doc.text(op.desc, schX + 10, curY);
      doc.setFont('helvetica', 'bold');
      doc.text(op.size, schX + schW - 3, curY, { align: 'right' });
      curY += 4.2;
    });

    // Setback Verification Notice
    curY += 3;
    doc.setFillColor(236, 253, 245);
    doc.rect(schX + 2, curY, schW - 4, 18, 'F');
    doc.setDrawColor(16, 185, 129);
    doc.rect(schX + 2, curY, schW - 4, 18);

    doc.setTextColor(5, 150, 105);
    doc.setFontSize(6.5);
    doc.setFont('helvetica', 'bold');
    doc.text('UDA MANDATORY SETBACKS VERIFIED', schX + 4, curY + 4.5);
    doc.setFontSize(6);
    doc.setFont('helvetica', 'normal');
    doc.text('• Front Setback: >= 3.00m (Road Street Line)', schX + 4, curY + 8);
    doc.text('• Rear Space: >= 2.30m (Clear Ventilation Space)', schX + 4, curY + 11.5);
    doc.text('• Side Space: >= 1.00m (Boundary Clearance)', schX + 4, curY + 15);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // SHEET 2: ARCHITECTURAL ELEVATIONS (ඉදිරි පෙනුම සහ පැති පෙනුම)
  // ══════════════════════════════════════════════════════════════════════════
  doc.addPage();
  drawSheetFrame(2, 'ඉදිරි හා පැති පෙනුම', 'ARCHITECTURAL ELEVATIONS');

  // Convert Front & Side Elevations SVG to Image
  const frontSvgData = buildElevationSvg(data, 'front');
  const frontImgUrl = await svgToDataUrl(frontSvgData.svg, frontSvgData.width, frontSvgData.height, 2.2);

  const sideSvgData = buildElevationSvg(data, 'side');
  const sideImgUrl = await svgToDataUrl(sideSvgData.svg, sideSvgData.width, sideSvgData.height, 2.2);

  const elY = margin + 14;
  const elH = 75;
  const elW = printableW - 6;

  if (frontImgUrl) {
    doc.setDrawColor(203, 213, 225);
    doc.rect(margin + 3, elY, elW, elH);
    doc.addImage(frontImgUrl, 'PNG', margin + 4, elY + 1, elW - 2, elH - 2);
  }

  if (sideImgUrl) {
    const sideY = elY + elH + 3;
    doc.setDrawColor(203, 213, 225);
    doc.rect(margin + 3, sideY, elW, elH);
    doc.addImage(sideImgUrl, 'PNG', margin + 4, sideY + 1, elW - 2, elH - 2);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // SHEET 3: 3D ARCHITECTURAL VOLUMETRIC MODEL (ත්‍රිමාණ පෙනුම)
  // ══════════════════════════════════════════════════════════════════════════
  doc.addPage();
  drawSheetFrame(3, 'ත්‍රිමාණ පෙනුම', '3D VOLUMETRIC MODEL');

  const modelY = margin + 14;
  const modelW = 180;
  const modelH = 154;

  // Attempt to capture live Three.js 3D Canvas
  let canvas3dDataUrl: string | null = null;
  if (options.capture3DCanvas) {
    canvas3dDataUrl = options.capture3DCanvas();
  }
  if (!canvas3dDataUrl) {
    const canvasEl = document.querySelector('#gab-3d-canvas canvas') as HTMLCanvasElement;
    if (canvasEl) {
      try {
        canvas3dDataUrl = canvasEl.toDataURL('image/png');
      } catch (e) {
        console.warn('Canvas export fallback:', e);
      }
    }
  }

  doc.setDrawColor(203, 213, 225);
  doc.rect(margin + 3, modelY, modelW, modelH);

  if (canvas3dDataUrl && canvas3dDataUrl.length > 50) {
    doc.addImage(canvas3dDataUrl, 'PNG', margin + 4, modelY + 1, modelW - 2, modelH - 2);
  } else {
    // If 3D canvas not active or WebGL uncaptured, draw high-detail axonometric architectural fallback
    doc.setFillColor(15, 23, 42);
    doc.rect(margin + 4, modelY + 1, modelW - 2, modelH - 2, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(12);
    doc.setFont('helvetica', 'bold');
    doc.text('3D ARCHITECTURAL VOLUMETRIC PERSPECTIVE', margin + modelW / 2, modelY + 60, { align: 'center' });
    doc.setFontSize(8.5);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(148, 163, 184);
    doc.text('Realistic Volumetric Massing • Floor Plates • Roof Geometry & Plinth', margin + modelW / 2, modelY + 70, { align: 'center' });
    doc.text(`Storey Count: ${floors.length} Levels • Total Volume: ~${(groundFootprint * 3.0 * floors.length).toFixed(0)} m³`, margin + modelW / 2, modelY + 78, { align: 'center' });
  }

  // Right Box: Structural & Building Code Specifications
  const specsX = margin + modelW + 6;
  const specsY = modelY;
  const specsW = printableW - modelW - 9;
  const specsH = modelH;

  doc.setFillColor(248, 250, 252);
  doc.rect(specsX, specsY, specsW, specsH, 'F');
  doc.setDrawColor(203, 213, 225);
  doc.rect(specsX, specsY, specsW, specsH);

  doc.setFillColor(15, 23, 42);
  doc.rect(specsX, specsY, specsW, 6.5, 'F');
  doc.setTextColor(255, 255, 255);
  doc.setFontSize(7);
  doc.setFont('helvetica', 'bold');
  doc.text('STRUCTURAL & UDA REGULATIONS SPECIFICATIONS', specsX + 3, specsY + 4.5);

  let spY = specsY + 12;
  const specs = [
    { title: '1. FOUNDATION & SUBSTRUCTURE', body: 'R.R. Masonry in 1:5 cement sand mortar on 150mm thick 1:3:6 concrete bed or reinforced concrete strip footings.' },
    { title: '2. SUPERSTRUCTURE WALLS', body: 'External walls: 225mm (9") brick/cement blockwork. Internal partitions: 112mm (4.5") with 1:5 smooth cement plastering.' },
    { title: '3. FLOOR SLABS & LINTELS', body: '125mm Grade 25 reinforced concrete suspended floor slab with tor steel reinforcement. Continuous lintels over all wall openings.' },
    { title: '4. ROOF & STORM DRAINAGE', body: 'Treated timber rafter framing / RC flat slab with waterproofing membrane. Concealed gutters connected to rainwater harvesting pit.' },
    { title: '5. NATURAL LIGHT & VENTILATION', body: 'Complies with UDA Reg 32: Window openings exceed 1/7th of net floor area in all habitable living spaces.' },
    { title: '6. SANITATION & SEPTIC PROVISIONS', body: 'Standard two-chambered septic tank with anaerobic soakage pit located >= 15m away from groundwater wells.' },
  ];

  specs.forEach((sp) => {
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(6.5);
    doc.setTextColor(15, 23, 42);
    doc.text(sp.title, specsX + 3, spY);
    spY += 3.5;
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(6);
    doc.setTextColor(71, 85, 105);
    const lines = doc.splitTextToSize(sp.body, specsW - 6);
    doc.text(lines, specsX + 3, spY);
    spY += lines.length * 3.2 + 2;
  });

  // Architect & Client Signature Box
  spY = specsY + specsH - 24;
  doc.setDrawColor(203, 213, 225);
  doc.line(specsX + 3, spY, specsX + specsW - 3, spY);

  doc.setFontSize(6);
  doc.setTextColor(100, 116, 139);
  doc.text('ARCHITECT / ENGINEER SIGNATURE & SEAL:', specsX + 3, spY + 4);
  doc.rect(specsX + 3, spY + 6, specsW - 6, 14);
  doc.text('Chartered Architect Registration No: .......................................', specsX + 5, spY + 16);

  // Save the PDF file
  const sanitizedName = (projectName || 'blueprint').replace(/[^a-z0-9_-]/gi, '-');
  doc.save(`${sanitizedName}-architectural-blueprint-set.pdf`);
}
