# -*- coding: utf-8 -*-
"""
Aşama 1B — Evrensel Birim Kalibratörü (`birim_kalibrator.py`)
==============================================================
`RawCADSnapshot` içindeki fiziksel Dünya Koordinatı (WCS) kanıtlarını
(90° kapı yay yarıçapı, elektrik sembol daireleri, metin yüksekliği ve
çerçeve boyutları) analiz ederek çizim birimini (mm / cm / m) belirler.

Sabit `if med_h <= 30 -> cm` gibi tuzaklara düşmez; `$INSUNITS=4` (mm) veya `6` (m)
yalnızca güçlü çoklu fiziksel kanıt çelişiyorsa geçersiz kılınır.
"""

from __future__ import annotations
import statistics
from typing import Any, Dict, List

from .schema import RawCADSnapshot, UnitCalibration

# DXF Header $INSUNITS -> mm karşılığı (AutoCAD standardı)
INSUNITS_TO_MM: Dict[int, float] = {
    0: 0.0,       # Unitless
    1: 25.4,      # Inches
    2: 304.8,     # Feet
    4: 1.0,       # Millimeters
    5: 10.0,      # Centimeters
    6: 1000.0,    # Meters
}


def calibrate_unit(snapshot: RawCADSnapshot) -> UnitCalibration:
    """Ham CAD görüntüsünden çizim birimini ve ölçek katsayılarını üretir."""
    ins = int(snapshot.insunits_header or 0)
    msp_paths = [p for p in snapshot.paths if p.space == "MODEL"]
    msp_texts = [t for t in snapshot.texts if t.space == "MODEL" and t.height > 0]

    # 1. Fiziksel Kanıt Topla (WCS cinsinden)
    door_arcs: List[float] = [
        p.radius_du
        for p in msp_paths
        if p.dxftype == "ARC"
        and p.radius_du is not None
        and p.arc_sweep_deg is not None
        and 72.0 <= abs(p.arc_sweep_deg) <= 108.0
    ]
    m_doors = sum(1 for r in door_arcs if 0.55 <= r <= 1.35)
    cm_doors = sum(1 for r in door_arcs if 55.0 <= r <= 135.0)
    mm_doors = sum(1 for r in door_arcs if 550.0 <= r <= 1350.0)

    circle_radii: List[float] = [
        p.radius_du for p in msp_paths if p.is_circle and p.radius_du is not None and p.radius_du > 0
    ]
    m_circ = sum(1 for r in circle_radii if 0.04 <= r <= 0.45)
    cm_circ = sum(1 for r in circle_radii if 4.0 <= r <= 45.0)
    mm_circ = sum(1 for r in circle_radii if 40.0 <= r <= 450.0)

    text_heights = [t.height for t in msp_texts if 0.01 <= t.height <= 5000.0]
    med_h = statistics.median(text_heights) if text_heights else 0.0

    # Çizim açıklığı (kaba bina/pafta büyüklüğü)
    all_x = [t.x for t in msp_texts] + [p.bbox.minx for p in msp_paths] + [p.bbox.maxx for p in msp_paths]
    all_y = [t.y for t in msp_texts] + [p.bbox.miny for p in msp_paths] + [p.bbox.maxy for p in msp_paths]
    span = max((max(all_x) - min(all_x)) if all_x else 0.0, (max(all_y) - min(all_y)) if all_y else 0.0)

    # Aday birimler için kanıt skoru
    scores: Dict[str, float] = {"m": 0.0, "cm": 0.0, "mm": 0.0}

    if m_doors >= 2:
        scores["m"] += 4.0 + min(m_doors, 20) * 0.2
    if cm_doors >= 2:
        scores["cm"] += 4.0 + min(cm_doors, 20) * 0.2
    if mm_doors >= 2:
        scores["mm"] += 4.0 + min(mm_doors, 20) * 0.2

    if m_circ >= 5 and m_circ > cm_circ and m_circ > mm_circ:
        scores["m"] += 2.0
    elif cm_circ >= 5 and cm_circ > m_circ and cm_circ > mm_circ:
        scores["cm"] += 2.0
    elif mm_circ >= 5 and mm_circ > m_circ and mm_circ > cm_circ:
        scores["mm"] += 2.0

    if 0.05 <= med_h <= 0.55:
        scores["m"] += 1.5
    elif 4.0 <= med_h <= 45.0:
        scores["cm"] += 1.5
    elif 45.0 < med_h <= 600.0:
        scores["mm"] += 1.5

    if 5.0 <= span <= 350.0 and scores["m"] > 0:
        scores["m"] += 1.0
    elif 400.0 <= span <= 80000.0 and scores["cm"] > 0:
        scores["cm"] += 0.5
    elif span > 30000.0 and scores["mm"] > scores["cm"]:
        scores["mm"] += 0.5

    evidence: Dict[str, Any] = {
        "insunits_header": ins,
        "med_text_height_du": round(med_h, 3),
        "door90_counts": {"m": m_doors, "cm": cm_doors, "mm": mm_doors},
        "circle_sym_counts": {"m": m_circ, "cm": cm_circ, "mm": mm_circ},
        "span_du": round(span, 2),
        "unit_scores": {k: round(v, 2) for k, v in scores.items()},
    }

    best_unit = max(scores.items(), key=lambda kv: kv[1])[0]
    best_score = scores[best_unit]
    sorted_scores = sorted(scores.values(), reverse=True)
    second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0.0

    unit_to_mm_map = {"mm": 1.0, "cm": 10.0, "m": 1000.0}

    # Karar Mantığı:
    # 1) Açıkça cm=5 verilmişse (nadir ve kasıtlıdır) doğrudan güven
    if ins == 5 and best_score - scores["cm"] < 4.0:
        return UnitCalibration(
            unit_name="cm",
            du_to_mm=10.0,
            du_to_m=0.01,
            confidence=0.95,
            source="INSUNITS_EXPLICIT_CM",
            evidence=evidence,
        )

    # 2) Belirsiz/Şablon Header (0=unitless, 4=acadiso.dwt default mm, 6=m)
    if ins in (0, 4, 6):
        hdr_name = {0: "unknown", 4: "mm", 6: "m"}.get(ins, "unknown")
        # Fiziksel kanıt header'dan farklı bir birimde AÇIKÇA baskınsa override et
        if best_score >= 3.5 and (best_score - second_score) >= 1.5:
            if hdr_name != best_unit:
                src = f"PHYSICAL_CALIBRATION_OVERRIDE(hdr={hdr_name}->{best_unit})"
                conf = min(0.98, 0.70 + 0.05 * best_score)
            else:
                src = f"PHYSICAL_CONFIRMED_INSUNITS({best_unit})"
                conf = min(0.99, 0.80 + 0.04 * best_score)
            du_mm = unit_to_mm_map[best_unit]
            return UnitCalibration(
                unit_name=best_unit,  # type: ignore[arg-type]
                du_to_mm=du_mm,
                du_to_m=du_mm / 1000.0,
                confidence=round(conf, 3),
                source=src,
                evidence=evidence,
            )

        # Header geçerli mm/m ama güçlü çelişen kapı/fiziksel kanıt yoksa header'a uy!
        if ins in INSUNITS_TO_MM and INSUNITS_TO_MM[ins] > 0:
            du_mm = INSUNITS_TO_MM[ins]
            u_name = "mm" if ins == 4 else "m"
            return UnitCalibration(
                unit_name=u_name,  # type: ignore[arg-type]
                du_to_mm=du_mm,
                du_to_m=du_mm / 1000.0,
                confidence=0.75,
                source=f"INSUNITS_HEADER({ins})",
                evidence=evidence,
            )

    # 3) Unitless (0) ve zayıf kanıt varsa en yüksek fiziksel skoru seç, hiç yoksa dürüstçe unknown
    if best_score > 0.0:
        du_mm = unit_to_mm_map[best_unit]
        return UnitCalibration(
            unit_name=best_unit,  # type: ignore[arg-type]
            du_to_mm=du_mm,
            du_to_m=du_mm / 1000.0,
            confidence=0.55,
            source=f"WEAK_PHYSICAL_ESTIMATE({best_unit})",
            evidence=evidence,
        )

    return UnitCalibration(
        unit_name="unknown",
        du_to_mm=1.0,
        du_to_m=0.001,
        confidence=0.0,
        source="UNIT_UNDETERMINED",
        evidence=evidence,
    )
