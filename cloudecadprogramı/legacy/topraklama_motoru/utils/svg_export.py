"""
CloudeCAD — SVG Redline Üretici
=================================
Topraklama analizini orijinal çizim üzerine görsel katman olarak ekler.

Renkler:
  Yeşil  (#00AA44) — topraklama şeritleri
  Mavi   (#0055FF) — topraklama kazıkları / buat noktaları
  Kırmızı (#FF2200) — boyutu aşan gözler (>20m×20m)
  Turuncu (#FF8800) — serbest uçlar (snap kaçıklığı)
  Gri    (#888888) — bina sınır poligonu

SVG çıktısı doğrudan tarayıcıda açılabilir, PDF'e dönüştürülebilir.
"""

import logging
import math
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Renk paleti
COLORS = {
    "strip":       "#00AA44",   # Topraklama şeridi
    "stake":       "#0055FF",   # Kazık / buat
    "mesh_ok":     "#00AA44",   # Uygun göz
    "mesh_fail":   "#FF2200",   # Boyutu aşan göz
    "free_end":    "#FF8800",   # Serbest uç
    "building":    "#888888",   # Bina sınırı
    "background":  "#F8F8F8",
    "text":        "#222222",
    "annotation":  "#CC0000",
}

_LINE_WIDTH = {
    "strip":    1.5,
    "building": 0.8,
    "mesh":     1.0,
}


def _svg_header(width: float, height: float, vb: str) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="{vb}">\n'
        f'<rect width="100%" height="100%" fill="{COLORS["background"]}"/>\n'
    )


def _svg_footer() -> str:
    return "</svg>\n"


class SVGExporter:
    """
    Topraklama analizi + geometri sonuçlarını SVG'ye dönüştürür.

    Kullanım:
        exporter = SVGExporter()
        exporter.export(drawing, geo_result, calc_result, "output.svg")
    """

    def __init__(self, margin_mm: float = 2000.0):
        self.margin = margin_mm   # SVG kenar boşluğu (çizim biriminde)

    def export(
        self,
        drawing,        # ParsedDrawing
        geo_result,     # GeometryResult
        calc_result,    # CalculationResult
        output_path: Path,
    ) -> Path:
        """SVG dosyasını oluşturur ve kaydeder."""
        output_path = Path(output_path)

        # Sınır kutusu hesapla
        bb = self._calc_bounds(drawing, geo_result)
        if bb is None:
            logger.warning("SVG: Sınır kutusu hesaplanamadı, çizim boş.")
            bb = (0, 0, 100000, 100000)

        min_x, min_y, max_x, max_y = bb
        pad = self.margin
        vb_x = min_x - pad
        vb_y = min_y - pad
        vb_w = (max_x - min_x) + 2 * pad
        vb_h = (max_y - min_y) + 2 * pad

        # SVG viewport: sayfaya sığdır (A4 oran)
        scale = min(1200 / vb_w, 900 / vb_h) if vb_w > 0 and vb_h > 0 else 1.0
        svg_w = vb_w * scale
        svg_h = vb_h * scale
        vb_str = f"{vb_x:.2f} {vb_y:.2f} {vb_w:.2f} {vb_h:.2f}"

        lines = [_svg_header(svg_w, svg_h, vb_str)]

        # Koordinat dönüşümü: DXF Y ekseni ters (yukarı +), SVG Y aşağı +
        def tx(x):  return x - vb_x
        def ty(y):  return vb_y + vb_h - y   # Y eksenini çevir

        target_segs = geo_result.active_foundation_floor.grounding_segments if (geo_result.active_foundation_floor and geo_result.active_foundation_floor.grounding_segments) else drawing.grounding_segments
        target_inserts = geo_result.active_foundation_floor.grounding_inserts if (geo_result.active_foundation_floor and geo_result.active_foundation_floor.grounding_inserts) else drawing.grounding_inserts

        # ── Katmanlar (arka → ön) ─────────────────────────────

        # 1) Bina sınırı (en altta)
        if geo_result.building_polygon:
            lines.append(self._render_polygon(
                geo_result.building_polygon, tx, ty,
                stroke=COLORS["building"], fill="#f1f5f9", stroke_width=1.5,
                dash="6,6", label="Bina Temel Oturumu"
            ))

        # 2) Topraklama şeritleri
        lines.append(f'<g id="strips" opacity="0.9">')
        for seg in target_segs:
            x1, y1 = tx(seg.start[0]), ty(seg.start[1])
            x2, y2 = tx(seg.end[0]),   ty(seg.end[1])
            lines.append(
                f'  <line x1="{x1:.2f}" y1="{y1:.2f}" '
                f'x2="{x2:.2f}" y2="{y2:.2f}" '
                f'stroke="{COLORS["strip"]}" stroke-width="3.0" '
                f'stroke-linecap="round"/>'
            )
        lines.append("</g>")

        # 3) Topraklama noktaları (kazık/buat/klemens)
        lines.append(f'<g id="stakes" opacity="0.95">')
        for ins in target_inserts:
            # Sadece görüntü alanına düşenleri çiz
            if not (vb_x <= ins.position[0] <= vb_x + vb_w and vb_y <= ins.position[1] <= vb_y + vb_h):
                continue
            cx, cy = tx(ins.position[0]), ty(ins.position[1])
            bname = ins.block_name.lower()
            if '1tp' in bname or 'cubuk' in bname or 'kazik' in bname or 'rod' in bname:
                # Topraklama Çubuğu: Mavi içi dolu daire (R=450mm) + dış halka
                lines.append(
                    f'  <circle cx="{cx:.2f}" cy="{cy:.2f}" r="450" '
                    f'fill="{COLORS["stake"]}" stroke="#001188" stroke-width="1.5"><title>Topraklama Çubuğu ({ins.block_name})</title></circle>'
                )
            elif '1ekk' in bname or 'klemens' in bname:
                # Klemens: Sarı kare / elmas
                lines.append(
                    f'  <rect x="{cx-250:.2f}" y="{cy-250:.2f}" width="500" height="500" '
                    f'fill="#F59E0B" stroke="#B45309" stroke-width="1.5"><title>Bağlantı Klemensi ({ins.block_name})</title></rect>'
                )
            elif 'etb' in bname or 'bara' in bname:
                # Eşpotansiyel Bara: Kırmızı/Mor dikdörtgen
                lines.append(
                    f'  <rect x="{cx-400:.2f}" y="{cy-200:.2f}" width="800" height="400" '
                    f'fill="#8B5CF6" stroke="#5B21B6" stroke-width="2.0"><title>Eşpotansiyel Bara ({ins.block_name})</title></rect>'
                )
        lines.append("</g>")

        # 4) Boyutu aşan gözler (kırmızı kutu)
        for eye in geo_result.mesh_eyes:
            if eye.is_oversized:
                lines.append(self._render_mesh_eye(eye, drawing, tx, ty, fail=True))

        # 5) Başlık ve açıklama kutusu
        lines.append(self._render_legend(calc_result, svg_w, svg_h))

        lines.append(_svg_footer())

        svg_content = "\n".join(lines)
        output_path.write_text(svg_content, encoding="utf-8")
        logger.info(f"SVG Redline kaydedildi: {output_path}")
        return output_path

    # ── Yardımcı metodlar ──────────────────────────────────────

    def _calc_bounds(self, drawing, geo_result) -> Optional[tuple]:
        """Tüm geometrinin veya temel katının bounding box'ını hesaplar."""
        # 1. Öncelik: Bina sınır poligonu etrafı (3.5 metre pay ile)
        if geo_result.building_polygon:
            minx, miny, maxx, maxy = geo_result.building_polygon.bounds
            margin = 3500.0
            return (minx - margin, miny - margin, maxx + margin, maxy + margin)

        # 2. Öncelik: Aktif temel katı topraklama iletkenleri
        target_segs = geo_result.active_foundation_floor.grounding_segments if (geo_result.active_foundation_floor and geo_result.active_foundation_floor.grounding_segments) else drawing.grounding_segments
        xs, ys = [], []
        for seg in target_segs:
            xs.extend([seg.start[0], seg.end[0]])
            ys.extend([seg.start[1], seg.end[1]])
        if xs:
            margin = 3500.0
            return (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)

        return None

    def _render_polygon(
        self, polygon, tx, ty,
        stroke="#888", fill="none",
        stroke_width=0.8, dash="", label=""
    ) -> str:
        try:
            coords = list(polygon.exterior.coords)
            pts = " ".join(f"{tx(x):.2f},{ty(y):.2f}" for x, y in coords)
            dash_attr = f'stroke-dasharray="{dash}"' if dash else ""
            title = f"<title>{label}</title>" if label else ""
            return (
                f'<polygon points="{pts}" '
                f'stroke="{stroke}" fill="{fill}" '
                f'stroke-width="{stroke_width}" {dash_attr}>{title}</polygon>'
            )
        except Exception as e:
            logger.debug(f"Poligon render hatası: {e}")
            return ""

    def _render_mesh_eye(self, eye, drawing, tx, ty, fail: bool) -> str:
        """Göz bounding box'ını SVG rect olarak çizer."""
        from utils.graph import build_graph, cycle_bounding_box
        G = build_graph(drawing.grounding_segments)
        bb = cycle_bounding_box(G, eye.nodes)
        if not bb:
            return ""
        min_x, min_y, max_x, max_y = bb
        x = tx(min_x)
        y = ty(max_y)   # SVG'de y ters
        w = (max_x - min_x)
        h = (max_y - min_y)
        color = COLORS["mesh_fail"] if fail else COLORS["mesh_ok"]
        return (
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'fill="{color}" fill-opacity="0.12" '
            f'stroke="{color}" stroke-width="1.5" stroke-dasharray="3,3">'
            f'<title>Göz {eye.index}: {eye.width_m:.1f}m × {eye.height_m:.1f}m — AŞILIYOR</title>'
            f'</rect>'
        )

    def _render_legend(self, calc_result, svg_w: float, svg_h: float) -> str:
        """Sağ üst köşeye bilgi kutusu ekler."""
        Re_str = "—"
        status_color = "#888"
        if calc_result.Re:
            Re_str = f"{calc_result.Re.calculated:.3f} Ω"
            status = calc_result.overall_status()
            status_color = (
                "#00AA44" if status == "UYGUN" else
                "#FF8800" if status == "UYARI" else
                "#FF2200"
            )

        # Göz özeti
        mesh_str = (
            f"{len(calc_result.mesh_checks)} göz, "
            f"{calc_result.oversized_mesh_count} aşıyor"
            if calc_result.mesh_checks else "Göz tespit edilemedi"
        )

        # Basit text box (viewBox koordinatlarına bağımsız, position: fixed gibi)
        return (
            f'<g id="legend" transform="translate(10,10)">'
            f'<rect width="220" height="110" rx="6" ry="6" '
            f'fill="white" stroke="#ccc" stroke-width="1" opacity="0.92"/>'
            f'<text x="10" y="24" font-family="monospace" font-size="11" '
            f'font-weight="bold" fill="#333">CloudeCAD — Topraklama</text>'
            f'<text x="10" y="44" font-family="monospace" font-size="10" fill="#555">'
            f'Re = <tspan fill="{status_color}" font-weight="bold">{Re_str}</tspan></text>'
            f'<text x="10" y="60" font-family="monospace" font-size="10" fill="#555">'
            f'TT ≤ 5Ω: <tspan fill="{status_color}">'
            f'{"UYGUN ✓" if calc_result.Re_vs_TT == "UYGUN" else "AŞILIYOR ✗"}'
            f'</tspan></text>'
            f'<text x="10" y="76" font-family="monospace" font-size="10" fill="#555">'
            f'{mesh_str}</text>'
            f'<text x="10" y="92" font-family="monospace" font-size="9" fill="#999">'
            f'● Yeşil=Şerit  ● Mavi=Kazık  ● Kırmızı=Hata</text>'
            f'<text x="10" y="106" font-family="monospace" font-size="9" fill="#999">'
            f'--- Gri=Bina Sınırı</text>'
            f'</g>'
        )
