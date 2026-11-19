# -*- coding: utf-8 -*-
"""
Adım 4 — Görsel Denetim İşaretleyici (`_DENETIM_BULGULARI`) ve DWG Dönüştürücü (`denetim_isaretleyici.py`)
========================================================================================================
Hesap denetimi (`CalculationAuditReport`) bulgularını mevcut DXF çiziminin **hiçbir orijinal
nesnesine, sayısına veya katmanına dokunmadan** tek bir aç/kapat (veya sil) yapılabilen
`_DENETIM_BULGULARI` katmanı üzerine revizyon bulutu + açıklayıcı not + özet indeks paneli
olarak işler ve AutoCAD Core Console (`accoreconsole.exe`) ile AutoCAD 2018 `.dwg` çıktısı üretir.

GEMINI.md kurallarına %100 uygundur:
  - Sıfır hardcode: tüm koordinatlar, ölçek ve bulgu metinleri dinamiktir.
  - Orijinal çizim verisini bozmaz (salt ek katman redline bindirmesi).
"""

from __future__ import annotations

from collections import defaultdict
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import ezdxf
from pydantic import BaseModel, Field

_MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(_MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_MOTOR_ROOT))

from common.dxf_converter import find_acad_core_console  # noqa: E402

from .hesap_denetleyici import AuditFindingItem, CalculationAuditReport

DEFAULT_AUDIT_LAYER = "_DENETIM_BULGULARI"

_SEVERITY_RANK = {"KRITIK": 4, "UYARI": 3, "BILGI": 2, "UYGUN": 1}
_SEVERITY_ACI = {"KRITIK": 1, "UYARI": 30, "BILGI": 5, "UYGUN": 3}  # 1=Kırmızı, 30=Turuncu, 5=Mavi, 3=Yeşil
_UNIT_DU_PER_M = {"mm": 1000.0, "cm": 100.0, "dm": 10.0, "m": 1.0}


class DwgConversionResult(BaseModel):
    success: bool
    source_dxf: str
    dwg_path: Optional[str] = None
    method: str = ""
    console_path: Optional[str] = None
    splines_removed: int = 0
    ole_frames_stripped: int = 0
    size_bytes: int = 0
    error: str = ""


class AnnotationResult(BaseModel):
    source_dxf: str
    annotated_dxf: str
    annotated_dwg: Optional[str] = None
    layer_name: str = DEFAULT_AUDIT_LAYER
    findings_considered: int = 0
    clouds_drawn: int = 0
    markers_anchored: int = 0
    unanchored_finding_ids: List[str] = Field(default_factory=list)
    summary_box_placed: bool = False
    dwg_conversion: Optional[DwgConversionResult] = None


# ==============================================================================
# ÖLÇEK VE GEOMETRİ YARDIMCILARI
# ==============================================================================

def _estimate_du_per_m(unit_name: str) -> float:
    return _UNIT_DU_PER_M.get((unit_name or "cm").lower().strip(), 100.0)


def _estimate_reference_text_height(doc: Any, du_per_m: float) -> float:
    """Çizimdeki mevcut TEXT/MTEXT yüksekliklerinin medyanını döndürür."""
    msp = doc.modelspace()
    heights: List[float] = []
    for e in msp:
        etype = e.dxftype()
        if etype in ("TEXT", "MTEXT"):
            h = float(getattr(e.dxf, "height", 0.0) or getattr(e.dxf, "char_height", 0.0) or 0.0)
            if 0.005 * du_per_m <= h <= 5.0 * du_per_m:
                heights.append(h)
        if len(heights) >= 600:
            break
    if not heights:
        return 0.14 * du_per_m
    heights.sort()
    h_med = heights[len(heights) // 2]
    return max(0.08 * du_per_m, min(h_med, 0.60 * du_per_m))


def _collect_entity_xy(doc: Any) -> Tuple[List[float], List[float]]:
    """Çizimdeki modelspace varlıklarından örneklem (X, Y) koordinatları toplar."""
    msp = doc.modelspace()
    xs: List[float] = []
    ys: List[float] = []

    def _push(x: float, y: float) -> None:
        if math.isfinite(x) and math.isfinite(y) and abs(x) <= 1e9 and abs(y) <= 1e9:
            xs.append(x)
            ys.append(y)

    for e in msp:
        et = e.dxftype()
        try:
            if et == "LINE":
                _push(float(e.dxf.start.x), float(e.dxf.start.y))
                _push(float(e.dxf.end.x), float(e.dxf.end.y))
            elif et == "LWPOLYLINE":
                pts = list(e.get_points("xy"))
                for pt in (pts[0], pts[len(pts) // 2]) if len(pts) > 1 else pts:
                    _push(float(pt[0]), float(pt[1]))
            elif et in ("CIRCLE", "ARC"):
                cx, cy = float(e.dxf.center.x), float(e.dxf.center.y)
                r = float(e.dxf.radius)
                _push(cx - r, cy - r)
                _push(cx + r, cy + r)
            elif et in ("TEXT", "MTEXT", "INSERT"):
                ins = e.dxf.insert
                _push(float(ins.x), float(ins.y))
        except Exception:
            continue
    return xs, ys


def _compute_modelspace_bounds(
    doc: Any,
    fallback_boxes: Sequence[Tuple[float, float, float, float]] = (),
) -> Optional[Tuple[float, float, float, float]]:
    """Aykırı/kaçak CAD noktalarını (IQR ile) eleyerek ana çizimin sağlam sınır kutusunu hesaplar."""
    xs, ys = _collect_entity_xy(doc)
    if not xs or not ys:
        return _merge_boxes(fallback_boxes) if fallback_boxes else None

    def _robust_range(vals: List[float], anchor_vals: List[float]) -> Tuple[float, float]:
        sv = sorted(vals)
        n = len(sv)
        if n < 8:
            return (sv[0], sv[-1])
        q25 = sv[max(0, int(0.25 * n))]
        q75 = sv[min(n - 1, int(0.75 * n))]
        anchor_span = (max(anchor_vals) - min(anchor_vals)) if anchor_vals else 0.0
        span = max(q75 - q25, anchor_span, 20.0)
        lo_lim = q25 - 3.0 * span
        hi_lim = q75 + 3.0 * span
        kept = [v for v in sv if lo_lim <= v <= hi_lim]
        if anchor_vals:
            kept.extend(anchor_vals)
        return (min(kept), max(kept)) if kept else (sv[0], sv[-1])

    ax = [v for b in fallback_boxes for v in (b[0], b[2])]
    ay = [v for b in fallback_boxes for v in (b[1], b[3])]
    xmin, xmax = _robust_range(xs, ax)
    ymin, ymax = _robust_range(ys, ay)
    return (xmin, ymin, xmax, ymax)


def _boxes_close(
    a: Tuple[float, float, float, float],
    b: Tuple[float, float, float, float],
    tol: float,
) -> bool:
    return not (
        a[2] + tol < b[0]
        or b[2] + tol < a[0]
        or a[3] + tol < b[1]
        or b[3] + tol < a[1]
    )


def _merge_boxes(boxes: Sequence[Tuple[float, float, float, float]]) -> Tuple[float, float, float, float]:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _normalize_box(
    raw_box: Optional[Tuple[float, float, float, float]],
    anchor_xy: Optional[Tuple[float, float]],
    min_dim: float,
) -> Optional[Tuple[float, float, float, float]]:
    if raw_box is not None:
        x0, y0, x1, y1 = raw_box
        if (x1 - x0) < min_dim:
            cx = 0.5 * (x0 + x1)
            x0, x1 = cx - 0.5 * min_dim, cx + 0.5 * min_dim
        if (y1 - y0) < min_dim:
            cy = 0.5 * (y0 + y1)
            y0, y1 = cy - 0.5 * min_dim, cy + 0.5 * min_dim
        return (x0, y0, x1, y1)
    if anchor_xy is not None:
        x, y = anchor_xy
        return (x - min_dim, y - 0.5 * min_dim, x + min_dim, y + 0.5 * min_dim)
    return None


def _draw_revcloud_rect(
    msp: Any,
    box: Tuple[float, float, float, float],
    *,
    layer: str,
    color: int,
    arc_step: float,
    line_width: float,
) -> None:
    """Verilen kutu etrafına AutoCAD REVCLOUD tarzı dışa bombeli kapalı LWPOLYLINE çizer."""
    x0, y0, x1, y1 = box
    # CCW sıra (saat yönünün tersi) + pozitif bulge => yaylar dışarı doğru kabarır
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    verts: List[Tuple[float, float, float, float, float]] = []
    bulge = 0.42
    for idx in range(4):
        sx, sy = corners[idx]
        ex, ey = corners[(idx + 1) % 4]
        side_len = math.hypot(ex - sx, ey - sy)
        n_seg = max(3, min(14, int(round(side_len / max(arc_step, 1e-3)))))
        for s in range(n_seg):
            t = s / n_seg
            verts.append((sx + (ex - sx) * t, sy + (ey - sy) * t, line_width, line_width, bulge))

    msp.add_lwpolyline(
        verts,
        format="xyseb",
        close=True,
        dxfattribs={
            "layer": layer,
            "color": color,
            "lineweight": 35,
        },
    )


def _escape_mtext(text: str) -> str:
    """DXF MTEXT içinde özel ters eğik çizgi/süslü parantez kaçışı ve satır sonu normalizasyonu."""
    s = (text or "").replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    return s.replace("\n", "\\P")


def _wrap_line(text: str, max_chars: int = 62) -> List[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: List[str] = []
    cur = words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= max_chars:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _format_cluster_callout(findings: Sequence[AuditFindingItem]) -> str:
    """Aynı bölgedeki bulgular için tek, okunaklı ve kompakt Türkçe MTEXT metni oluşturur."""
    lines: List[str] = []
    for f in findings:
        head = f"[{f.finding_id}] {f.severity} | {f.category}"
        lines.extend(_wrap_line(head, 56))
        detail = f"Proje: {f.project_value}  |  Doğru: {f.engine_value}"
        lines.extend("  " + ln for ln in _wrap_line(detail, 54))
        if f.recommendation:
            lines.extend("  -> " + ln if i == 0 else "     " + ln for i, ln in enumerate(_wrap_line(f.recommendation, 52)))
    return "\n".join(lines)


# ==============================================================================
# ANA İŞARETLEME MOTORU (`annotate_dxf_with_audit_findings`)
# ==============================================================================

def annotate_dxf_with_audit_findings(
    src_dxf: Union[str, Path],
    dst_dxf: Union[str, Path],
    report: CalculationAuditReport,
    *,
    include_ok: bool = False,
    layer_name: str = DEFAULT_AUDIT_LAYER,
    add_summary_legend: bool = True,
) -> AnnotationResult:
    """
    Mevcut DXF çizimini kopyalar ve **hiçbir orijinal varlığa dokunmadan** yalnızca
    `layer_name` (varsayılan `_DENETIM_BULGULARI`) katmanına revizyon bulutları, lider çizgileri,
    açıklama notları ve özet bulgu indeksi paneli ekler.
    """
    src_path = Path(src_dxf)
    dst_path = Path(dst_dxf)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    doc = ezdxf.readfile(str(src_path))
    if layer_name not in doc.layers:
        doc.layers.add(layer_name, color=1, linetype="CONTINUOUS")

    msp = doc.modelspace()
    du_per_m = _estimate_du_per_m(report.unit_name)
    h_med = _estimate_reference_text_height(doc, du_per_m)
    h_note = max(h_med * 1.15, 0.12 * du_per_m)
    min_box_dim = 2.5 * h_note
    arc_step = 3.2 * h_note
    cloud_lw = 0.22 * h_note

    active_findings = [
        f for f in report.findings
        if include_ok or f.severity != "UYGUN"
    ]

    # Her bulgu için hedef kutuları topla
    target_items: List[Tuple[AuditFindingItem, Tuple[float, float, float, float]]] = []
    unanchored_ids: List[str] = []

    for f in active_findings:
        boxes_for_f: List[Tuple[float, float, float, float]] = []
        primary = _normalize_box(f.bbox_du, f.anchor_xy, min_box_dim)
        if primary is not None:
            boxes_for_f.append(primary)
        for ex, ey, eb in f.extra_anchors:
            nb = _normalize_box(eb, (ex, ey), min_box_dim)
            if nb is not None:
                boxes_for_f.append(nb)

        if not boxes_for_f:
            unanchored_ids.append(f.finding_id)
            continue
        for b in boxes_for_f:
            target_items.append((f, b))

    # Yakın/çakışan hedefleri tek temiz bulutta birleştir (aynı tablo/kolon üst üste binmesin)
    merge_tol = 2.0 * h_note
    clusters: List[Dict[str, Any]] = []
    for f, box in target_items:
        placed = False
        for cl in clusters:
            if _boxes_close(cl["box"], box, merge_tol):
                cl["box"] = _merge_boxes([cl["box"], box])
                if f.finding_id not in cl["fids"]:
                    cl["findings"].append(f)
                    cl["fids"].add(f.finding_id)
                placed = True
                break
        if not placed:
            clusters.append({
                "box": box,
                "findings": [f],
                "fids": {f.finding_id},
            })

    # Aykırı noktaları eleyen sağlam çizim sınırı (çağırma kartları & özet kutusu bu bandın üstüne konacak)
    all_target_boxes = [box for _, box in target_items]
    orig_bounds = _compute_modelspace_bounds(doc, fallback_boxes=all_target_boxes)
    sheet_top_y = (
        orig_bounds[3]
        if orig_bounds is not None
        else (max(b[3] for b in all_target_boxes) if all_target_boxes else 0.0)
    )

    # Soldan sağa sırala ki üstteki açıklama kartları da soldan sağa düzgün dizilsin
    clusters.sort(key=lambda c: c["box"][0])

    # Tüm açıklama kartları pafta üst sınırının kesinlikle ÜSTÜNDE başlasın (çizim içine hiç kart düşmesin)
    rail_floor_y = max(
        sheet_top_y,
        max((b[3] for b in all_target_boxes), default=sheet_top_y),
    ) + 10.0 * h_note

    placed_label_boxes: List[Tuple[float, float, float, float]] = []
    highest_rail_y = rail_floor_y
    clouds_drawn = 0

    for cl in clusters:
        bx0, by0, bx1, by1 = cl["box"]
        pad_x = min(3.0 * h_note, max(1.2 * h_note, 0.04 * (bx1 - bx0)))
        pad_y = min(3.0 * h_note, max(1.2 * h_note, 0.04 * (by1 - by0)))
        cloud_box = (bx0 - pad_x, by0 - pad_y, bx1 + pad_x, by1 + pad_y)

        top_sev = max(cl["findings"], key=lambda it: _SEVERITY_RANK.get(it.severity, 0)).severity
        aci = _SEVERITY_ACI.get(top_sev, 1)

        _draw_revcloud_rect(
            msp,
            cloud_box,
            layer=layer_name,
            color=aci,
            arc_step=arc_step,
            line_width=cloud_lw,
        )
        clouds_drawn += 1

        # Çizim içinde yalnızca kompakt bulgu kodu rozeti ("[H-01, H-02]") — diğer yazıları ezmez
        badge_ids = ", ".join(f.finding_id for f in cl["findings"])
        badge_h = max(h_med * 0.95, 0.10 * du_per_m)
        msp.add_text(
            f"[{badge_ids}]",
            dxfattribs={
                "layer": layer_name,
                "color": aci,
                "height": badge_h,
                "insert": (cloud_box[0], cloud_box[3] + 0.5 * badge_h),
            },
        )

        # Detaylı Türkçe açıklama kartını pafta üstündeki temiz banda yerleştir
        callout_txt = _format_cluster_callout(cl["findings"])
        n_lines = max(2, callout_txt.count("\n") + 1)
        box_w = 48.0 * h_note
        box_h = (n_lines + 3) * 1.65 * h_note

        lx = 0.5 * (cloud_box[0] + cloud_box[2]) - 0.5 * box_w
        ly = rail_floor_y + box_h

        # Komşu açıklama kartlarıyla çakışmayı tam kart genişliği + yükseklik basamaklarıyla önle
        for attempt in range(36):
            cand_lbox = (lx, ly - box_h, lx + box_w, ly)
            if not any(_boxes_close(cand_lbox, ob, 3.0 * h_note) for ob in placed_label_boxes):
                break
            if attempt % 2 == 0:
                ly += box_h + 4.0 * h_note
            else:
                lx += 1.15 * box_w
        placed_label_boxes.append((lx, ly - box_h, lx + box_w, ly))
        highest_rail_y = max(highest_rail_y, ly)

        # Lider çizgisi: bulutun üst ortasından üst boşluktaki kartın alt kenarına
        sx, sy = 0.5 * (cloud_box[0] + cloud_box[2]), cloud_box[3]
        tx, ty = lx + 0.25 * box_w, ly - box_h - 0.5 * h_note
        msp.add_line(
            (sx, sy),
            (tx, ty),
            dxfattribs={"layer": layer_name, "color": aci, "lineweight": 25},
        )
        # Açıklama kartı çerçevesi + Türkçe MTEXT
        msp.add_lwpolyline(
            [
                (lx - 0.8 * h_note, ly - box_h - 0.5 * h_note),
                (lx + box_w + 0.8 * h_note, ly - box_h - 0.5 * h_note),
                (lx + box_w + 0.8 * h_note, ly + 0.7 * h_note),
                (lx - 0.8 * h_note, ly + 0.7 * h_note),
            ],
            close=True,
            dxfattribs={"layer": layer_name, "color": aci, "lineweight": 25},
        )
        msp.add_mtext(
            _escape_mtext(callout_txt),
            dxfattribs={
                "layer": layer_name,
                "color": aci,
                "char_height": h_note * 0.90,
                "width": box_w,
                "insert": (lx, ly),
                "attachment_point": 1,  # Top-Left
            },
        )

    # İlk pafta/bulutların hemen üst-soluna Özet Denetim İndeks Paneli ekle
    summary_placed = False
    if add_summary_legend and orig_bounds is not None and report.findings:
        ox0, _oy0, ox1, _oy1 = orig_bounds
        sh_idx = h_note * 1.15
        sc = report.summary_counts
        panel_lines = [
            f"CLOUDECAD DENETİM BULGULARI ÖZETİ — {report.filename}",
            (
                f"Birim: {report.unit_name} | Layer: {layer_name} "
                f"| Kritik İhlal: {sc.get('KRITIK', 0)} | Uyarı: {sc.get('UYARI', 0)} | Uygun: {sc.get('UYGUN', 0)}"
            ),
            "Not: Bu katman orijinal sayılara dokunmaz; düzenleme sonrası tek tıkla kapatabilir veya silebilirsiniz.",
            "-" * 96,
        ]
        for f in report.findings:
            mark = "OK" if f.severity == "UYGUN" else ("!" if f.severity == "KRITIK" else "*")
            anch_tag = "(KONUM İŞARETLİ)" if (f.bbox_du or f.anchor_xy or f.extra_anchors) else "(GENEL)"
            panel_lines.append(
                f"[{f.finding_id}] [{f.severity}] {mark} {f.location} {anch_tag} -> {f.project_value} | Doğru: {f.engine_value}"
            )

        panel_text = "\n".join(panel_lines)
        panel_w = max(95.0 * sh_idx, min(180.0 * sh_idx, max(ox1 - ox0, 40.0 * sh_idx) * 0.35))
        panel_h = (len(panel_lines) + 4) * 1.65 * sh_idx
        px = min((b[0] for b in all_target_boxes), default=ox0)
        py = highest_rail_y + panel_h + 10.0 * sh_idx

        # Üst-sol köşeye temiz özet kutusu
        msp.add_lwpolyline(
            [
                (px - 1.5 * sh_idx, py - panel_h - 1.0 * sh_idx),
                (px + panel_w + 1.5 * sh_idx, py - panel_h - 1.0 * sh_idx),
                (px + panel_w + 1.5 * sh_idx, py + 1.5 * sh_idx),
                (px - 1.5 * sh_idx, py + 1.5 * sh_idx),
            ],
            close=True,
            dxfattribs={"layer": layer_name, "color": 1, "lineweight": 35},
        )
        msp.add_mtext(
            _escape_mtext(panel_text),
            dxfattribs={
                "layer": layer_name,
                "color": 1,
                "char_height": sh_idx,
                "width": panel_w,
                "insert": (px, py),
                "attachment_point": 1,
            },
        )
        summary_placed = True

    doc.saveas(str(dst_path))
    return AnnotationResult(
        source_dxf=str(src_path),
        annotated_dxf=str(dst_path),
        layer_name=layer_name,
        findings_considered=len(active_findings),
        clouds_drawn=clouds_drawn,
        markers_anchored=len(target_items),
        unanchored_finding_ids=unanchored_ids,
        summary_box_placed=summary_placed,
    )


# ==============================================================================
# AUTOCAD CORE CONSOLE İLE DWG DÖNÜŞÜMÜ (`convert_dxf_to_dwg`)
# ==============================================================================

def strip_block_splines(src_dxf: Path, dst_dxf: Path) -> int:
    """Blok tanımları içindeki SPLINE varlıklarını çıkarır (AutoCAD kaydetme koruması)."""
    doc = ezdxf.readfile(str(src_dxf))
    removed = 0
    for blk in doc.blocks:
        if blk.name.startswith("*"):
            continue
        for e in list(blk):
            if e.dxftype() == "SPLINE":
                blk.delete_entity(e)
                removed += 1
    doc.saveas(str(dst_dxf))
    return removed


def convert_dxf_to_dwg(
    dxf_path: Union[str, Path],
    dwg_path: Union[str, Path],
    *,
    timeout: int = 240,
    run_audit: bool = True,
) -> DwgConversionResult:
    """
    DXF dosyasını AutoCAD Core Console (`accoreconsole.exe`) üzerinden AutoCAD 2018 `.dwg`
    formatına çevirir. Boşluk/Türkçe yol kaynaklı script kesilmelerini önlemek için hem
    girdi hem çıktı boşluksuz geçici klasörde işlenir.
    """
    src = Path(dxf_path).resolve()
    dst = Path(dwg_path).resolve()
    if not src.exists():
        return DwgConversionResult(
            success=False,
            source_dxf=str(src),
            error=f"Kaynak DXF bulunamadı: {src}",
        )

    console = find_acad_core_console()
    if console is None or not console.exists():
        return DwgConversionResult(
            success=False,
            source_dxf=str(src),
            error="accoreconsole.exe bulunamadı (AutoCAD kurulumu gerekli).",
        )

    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="ccad_dwg_"))
    splines_removed = 0
    ole_stripped = 0
    method = "accoreconsole_saveas_2018"

    try:
        tmp_in = tmp_dir / "input.dxf"
        tmp_out = tmp_dir / "output.dwg"
        scr_path = tmp_dir / "save_dwg.scr"
        shutil.copy2(src, tmp_in)

        def _invoke(in_file: Path) -> subprocess.CompletedProcess[str]:
            if tmp_out.exists():
                tmp_out.unlink()
            out_posix = tmp_out.resolve().as_posix()
            scr_lines = ["FILEDIA 0"]
            if run_audit:
                scr_lines.extend(["_AUDIT", "_Y"])
            scr_lines.extend([
                "_SAVEAS",
                "2018",
                out_posix,
                "FILEDIA 1",
                "_QUIT",
                "_Y",
                "",
            ])
            scr_path.write_text("\n".join(scr_lines), encoding="ascii", errors="replace")
            cmd = [str(console), "/i", str(in_file.resolve()), "/s", str(scr_path.resolve())]
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

        res = _invoke(tmp_in)
        cur_in = tmp_in
        if not tmp_out.exists():
            # Kademe 2: Revit/mimari bloklarda SPLINE kaynaklı save hatası olursa SPLINE temizle
            tmp_nospline = tmp_dir / "input_nospline.dxf"
            try:
                splines_removed = strip_block_splines(cur_in, tmp_nospline)
            except Exception:
                splines_removed = 0
            if splines_removed > 0:
                method = "accoreconsole_saveas_2018_spline_stripped"
                cur_in = tmp_nospline
                res = _invoke(cur_in)

        if not tmp_out.exists():
            # Kademe 3: AutoCAD Core Console headless OLE2FRAME render çökmesini atlamak için
            # yalnızca geçici DWG dönüştürme kopyasından OLE2FRAME çıkar (kaynak DXF dokunulmaz!)
            tmp_no_ole = tmp_dir / "input_no_ole.dxf"
            try:
                d_ole = ezdxf.readfile(str(cur_in))
                ole_ents = [e for e in d_ole.modelspace() if e.dxftype() == "OLE2FRAME"]
                if ole_ents:
                    for oe in ole_ents:
                        d_ole.modelspace().delete_entity(oe)
                    ole_stripped = len(ole_ents)
                    d_ole.saveas(str(tmp_no_ole))
                    method = "accoreconsole_saveas_2018_ole_stripped"
                    cur_in = tmp_no_ole
                    res = _invoke(cur_in)
            except Exception:
                pass

        if not tmp_out.exists():
            # Kademe 4: Bozuk DXF dictionary/OBJECTS ağacı varsa Importer ile temiz R2018 kabuğa aktar
            tmp_imp = tmp_dir / "input_rebuilt.dxf"
            try:
                from ezdxf.addons import Importer
                d_src = ezdxf.readfile(str(cur_in))
                d_fresh = ezdxf.new("R2018")
                imp = Importer(d_src, d_fresh)
                imp.import_modelspace()
                imp.finalize()
                d_fresh.saveas(str(tmp_imp))
                method = "accoreconsole_saveas_2018_importer_rebuild"
                res = _invoke(tmp_imp)
            except Exception:
                pass

        if not tmp_out.exists():
            tail = (res.stdout or "").replace("\x00", "")[-400:] + " | " + (res.stderr or "")[-200:]
            return DwgConversionResult(
                success=False,
                source_dxf=str(src),
                method=method,
                console_path=str(console),
                splines_removed=splines_removed,
                ole_frames_stripped=ole_stripped,
                error=f"DWG çıktısı oluşturulamadı: {tail.strip()}",
            )

        if dst.exists():
            dst.unlink()
        shutil.move(str(tmp_out), str(dst))
        return DwgConversionResult(
            success=True,
            source_dxf=str(src),
            dwg_path=str(dst),
            method=method,
            console_path=str(console),
            splines_removed=splines_removed,
            ole_frames_stripped=ole_stripped,
            size_bytes=dst.stat().st_size,
        )
    except Exception as exc:
        return DwgConversionResult(
            success=False,
            source_dxf=str(src),
            method=method,
            console_path=str(console),
            splines_removed=splines_removed,
            ole_frames_stripped=ole_stripped,
            error=str(exc),
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        for err_p in (Path.cwd() / "ErrorReports", Path(__file__).resolve().parents[2] / "ErrorReports"):
            if err_p.exists():
                shutil.rmtree(err_p, ignore_errors=True)


def deliver_annotated_dxf_and_dwg(
    clean_dxf: Union[str, Path],
    report: CalculationAuditReport,
    output_dir: Union[str, Path],
    *,
    base_name: Optional[str] = None,
    include_ok: bool = False,
    layer_name: str = DEFAULT_AUDIT_LAYER,
    convert_clean_dwg_path: Optional[Union[str, Path]] = None,
) -> Tuple[AnnotationResult, Optional[DwgConversionResult]]:
    """
    Tek çağrıda:
      1. İsteğe bağlı olarak temiz (bulutsuz) `clean_dxf` dosyasını `.dwg`ye çevirir (`convert_clean_dwg_path`).
      2. `_DENETIM_BULGULARI` katmanlı `<base_name>.dxf` üretir.
      3. Aynı dosyayı `.dwg` formatına (`<base_name>.dwg`) çevirir.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = base_name or f"{Path(report.filename).stem}_denetim_bulgulu"

    clean_dwg_res: Optional[DwgConversionResult] = None
    if convert_clean_dwg_path is not None:
        clean_dwg_res = convert_dxf_to_dwg(clean_dxf, convert_clean_dwg_path)

    ann_dxf = out_dir / f"{stem}.dxf"
    ann_dwg = out_dir / f"{stem}.dwg"
    ann_res = annotate_dxf_with_audit_findings(
        clean_dxf,
        ann_dxf,
        report,
        include_ok=include_ok,
        layer_name=layer_name,
    )
    dwg_res = convert_dxf_to_dwg(ann_dxf, ann_dwg)
    ann_res.dwg_conversion = dwg_res
    if dwg_res.success:
        ann_res.annotated_dwg = dwg_res.dwg_path
    return ann_res, clean_dwg_res


__all__ = [
    "AnnotationResult",
    "DEFAULT_AUDIT_LAYER",
    "DwgConversionResult",
    "annotate_dxf_with_audit_findings",
    "convert_dxf_to_dwg",
    "deliver_annotated_dxf_and_dwg",
]
