# -*- coding: utf-8 -*-
"""
Modül 2 — TopologicalWireHealer (Topolojik Kablo Birleştirme ve Snap Motoru)
============================================================================
1. Duplicate Cleaner (OVERKILL + Devre Bağlamı Koruması):
   Aynı katmanda üst üste binmiş çift çizgileri yakalar. Eğer iki çizginin devre
   bağlamları (circuit_ctx) birbiriyle çelişiyorsa (örn: W1 vs W2), sessizce silmez;
   auto_approvable=False, status='REQUIRES_APPROVAL' olarak Onay İstasyonu'na düşürür.
2. Collinear Stitcher (4 Şartlı Kopuk Kablo Birleştirici):
   İki paralel yan yana hattı yanlışlıkla kısa devre yapmamak için Otomatik Birleştirme
   (auto_approvable=True) SADECE şu 4 şartın TAMAMI sağlandığında yapılır:
     a) Aynı katman (layer_a == layer_b)
     b) Doğrusal hizalı (Her iki çizgi vektörü ve aradaki köprü vektörü açısı <= 5°;
        yan yana paralel hatlarda köprü vektörü dik (~90°) olduğu için kesin elenir!)
     c) Aradaki boşlukta (gap) başka hiçbir sembol veya dik kesişen hat yok
     d) Uçlardaki devre/pano bağlamı çelişmiyor (örn: ikisi de A1 veya aynı devre;
        biri A1 diğeri A2 ise otomatik birleştirme kesinlikle engellenir).
   Koşullardan biri eksikse öneri Onay İstasyonu'na (REQUIRES_APPROVAL) düşer.
3. Symbol Snapper (Kademeli Onay + Çift Müdahale Koruması):
   - STITCH adayı olmuş bir kablo ucuna ikinci kez SNAP önerisi üretilmez.
   - Küçük mikro boşluklar (<= auto_snap_max_cm, varsayılan 5 cm) auto_approvable=True,
     daha büyük boşluklar (5 cm .. max_snap_gap_cm) REQUIRES_APPROVAL olarak üretilir.
4. STRtree Uzamsal İndeksleme & INSUNITS Dinamik Ölçekleme:
   50.000+ LINE içeren metro paftalarında O(n log n) performans için shapely.STRtree kullanılır.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import math
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from ..cad.cad_safety import CADSafetyGuard, UnitScaleResolver
from ..model.entities import PlacedSymbol, TextToken

# Patlatılmış (exploded) mimari, inşaat, mekanik, antet ve ölçülendirme katmanları:
# WireHealer bu katmanlardaki LINE varlıklarını kablo olarak birleştirmeye ÇALIŞMAZ!
NON_WIRE_LAYER_PREFIXES: Tuple[str, ...] = (
    "A-", "A_", "S-", "S_", "M-", "M_", "G-", "G_", "F-", "F_", "C-", "C_", "P-", "P_",
)

NON_WIRE_LAYER_SUBSTRINGS: Tuple[str, ...] = (
    "A-MIMARI-ALTYAPI", "E-ETIKET-TABLO", "E-LEGN", "LEJANT", "LEGEND",
    "DUVAR", "WALL", "SIVA", "DSIVA", "DSİVA", "KAPI", "KAPİ", "DOOR",
    "PENCERE", "WINDOW", "GLAZ", "MERDIVEN", "MERDİVEN", "STAIR",
    "MOBILYA", "MOBİLYA", "TEFRS", "TEFRIS", "TEFRİŞ", "FURN",
    "KOLON", "KIRIS", "KİRİŞ", "BETON", "ELEVATION", "SECT", "KESIT", "KESİT",
    "FLOR", "CEIL", "TAVAN", "ROOF", "CATI", "ÇATI",
    "GRID", "AKS", "AXIS", "OLCU", "ÖLÇÜ", "DIM", "ANNO", "TEXT", "YAZI",
    "HATCH", "TARAMA", "BORDER", "ANTET", "TITLE", "FRAME", "CERCEVE", "ÇERÇEVE",
    "VIEWPORT", "VPORT", "DEFPOINTS", "XREF", "M3-ARC", "M3-STR", "M3-MEC",
    "AFFFEQM", "PLANOTM",
)

# Yukarıdaki mimari/genel kelimeler geçse dahi açıkça kablo/tava/elektrik hattı olan katmanları koru:
EXPLICIT_WIRE_KEYWORDS: Tuple[str, ...] = (
    "KABLO", "CABL", "WIRE", "LINYE", "LİNYE", "SORTI", "SORTİ",
    "TAVA", "TRAY", "BUSBAR", "FIBER", "FİBER", "OPTIK", "OPTİK",
    "CAT6", "CCTV", "ANONS", "PAVA", "TELEFON", "DATA", "SCADA",
    "TOPRAKLAMA", "GROUND",
)


def is_eligible_wire_layer(layer_name: str) -> bool:
    """
    Bir LINE katmanının kablo/tava onarımına (TopologicalWireHealer) uygun olup olmadığını denetler.
    - '0' katmanını ve açık kablo/elektrik katmanlarını kabul eder.
    - Patlatılmış mimari ('A_*', 'A-*'), statik ('S_*'), genel çerçeve ('G-*'),
      sabit tefriş ('F-AFFFEQM'), kesit, merdiven, kapı, yazı ve lejant katmanlarını reddeder.
    """
    lay = (layer_name or "").strip()
    if not lay or lay == "0":
        return True
    lay_up = lay.replace("i", "İ").replace("ı", "I").upper()

    if lay_up in ("A-MIMARI-ALTYAPI", "E-ETIKET-TABLO", "DEFPOINTS"):
        return False

    # Açıkça kablo / tava / zayıf akım hattı kelimesi varsa (örn. 'KABLOLAMA ANONS', 'E-CABL-TRAY') kabul et
    if any(kw in lay_up for kw in EXPLICIT_WIRE_KEYWORDS):
        return True

    # Standart AIA / ISO disiplin önekleri (Mimari A-, Statik S-, Genel G-, Tefriş F-, Mekanik M-)
    if lay_up.startswith(NON_WIRE_LAYER_PREFIXES):
        return False

    # Mimari / Antet / Ölçü / Lejant alt dizgeleri
    if any(sub in lay_up for sub in NON_WIRE_LAYER_SUBSTRINGS):
        return False

    return True


@dataclass
class WireHealProposal:
    """Tek bir topolojik kablo onarım önerisi (Stitch, Snap veya Duplicate Silme)."""
    proposal_id: str
    action: str                         # STITCH_COLLINEAR_GAP, SNAP_TO_SYMBOL, DELETE_DUPLICATE
    primary_handle: str
    secondary_handle: str
    layer: str
    start_pt: Tuple[float, float]
    end_pt: Tuple[float, float]
    gap_drawing_units: float
    gap_mm: float
    angle_diff_deg: float
    circuit_context_a: str
    circuit_context_b: str
    conditions_met: Dict[str, bool]
    confidence_score: float
    reason: str
    auto_approvable: bool
    status: str = "PROPOSED"            # PROPOSED, REQUIRES_APPROVAL, APPROVED, NOT_SELECTED, REJECTED


@dataclass
class WireHealPlan:
    """TopologicalWireHealer tarafından üretilen topolojik onarım planı."""
    drawing_name: str
    unit_to_mm: float
    unit_source: str
    max_stitch_gap_mm: float
    max_stitch_gap_units: float
    max_snap_gap_mm: float
    max_snap_gap_units: float
    created_at: str
    proposals: List[WireHealProposal] = field(default_factory=list)
    summary_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save_json(self, path: Union[str, Path]) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p


class TopologicalWireHealer:
    """
    Modül 2: STRtree uzamsal indeksli, INSUNITS ölçek duyarlı, 4 şartlı doğrusal kablo
    birleştirme, sembol mıknatıslama ve çift çizgi temizleme motoru.
    """

    @staticmethod
    def _angle_between_vectors_deg(v1: Tuple[float, float], v2: Tuple[float, float]) -> float:
        n1 = math.hypot(v1[0], v1[1])
        n2 = math.hypot(v2[0], v2[1])
        if n1 < 1e-9 or n2 < 1e-9:
            return 0.0
        cos_a = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
        return math.degrees(math.acos(cos_a))

    @staticmethod
    def _infer_circuit_context_indexed(
        seg_line: LineString,
        valid_texts: List[Tuple[str, Point]],
        text_tree: Optional[STRtree],
        search_radius_units: float,
    ) -> str:
        """STRtree kullanarak çizgi parçasına en yakın devre/linye etiketini O(log N) sürede bulur."""
        if text_tree is None or not valid_texts:
            return ""
        cand_indices = text_tree.query(seg_line.buffer(search_radius_units))
        best_txt = ""
        best_dist = search_radius_units
        for idx in cand_indices:
            val, pt = valid_texts[int(idx)]
            d = seg_line.distance(pt)
            if d < best_dist or (abs(d - best_dist) <= 1e-9 and best_txt and val != best_txt):
                best_dist = d
                best_txt = val
        return best_txt

    @staticmethod
    def _infer_all_circuit_contexts_indexed(
        seg_line: LineString,
        valid_texts: List[Tuple[str, Point]],
        text_tree: Optional[STRtree],
        search_radius_units: float,
    ) -> List[str]:
        """Bir çizginin çok yakınındaki tüm benzersiz devre etiketlerini döner (Duplicate çelişki kontrolü için)."""
        if text_tree is None or not valid_texts:
            return []
        cand_indices = text_tree.query(seg_line.buffer(search_radius_units))
        hits: List[Tuple[float, str]] = []
        for idx in cand_indices:
            val, pt = valid_texts[int(idx)]
            d = seg_line.distance(pt)
            if d <= search_radius_units:
                hits.append((d, val))
        hits.sort(key=lambda x: x[0])
        unique_vals: List[str] = []
        for _, v in hits:
            if v not in unique_vals:
                unique_vals.append(v)
        return unique_vals

    @classmethod
    def analyze_and_propose(
        cls,
        doc: Any,
        symbols: Optional[List[PlacedSymbol]] = None,
        texts: Optional[List[TextToken]] = None,
        drawing_name: str = "drawing.dxf",
        max_stitch_gap_cm: float = 20.0,
        max_snap_gap_cm: float = 15.0,
        auto_snap_max_cm: float = 5.0,
        collinear_angle_tol_deg: float = 5.0,
    ) -> WireHealPlan:
        """
        ModelSpace içindeki kablo çizgilerini (LINE) STRtree uzamsal indeksleme ile inceler;
        INSUNITS'ten ölçeklenmiş toleranslarla Duplicate, Stitch ve Snap önerileri üretir.
        """
        symbols = symbols or []
        texts = texts or []

        unit_mm, unit_src = UnitScaleResolver.resolve_unit_to_mm(doc)
        max_stitch_mm = max_stitch_gap_cm * 10.0
        max_snap_mm = max_snap_gap_cm * 10.0
        auto_snap_max_mm = auto_snap_max_cm * 10.0

        max_stitch_units = UnitScaleResolver.mm_to_drawing_units(max_stitch_mm, doc)
        max_snap_units = UnitScaleResolver.mm_to_drawing_units(max_snap_mm, doc)
        auto_snap_max_units = UnitScaleResolver.mm_to_drawing_units(auto_snap_max_mm, doc)
        dup_tol_units = UnitScaleResolver.mm_to_drawing_units(1.0, doc)
        min_gap_units = UnitScaleResolver.mm_to_drawing_units(0.5, doc)
        ctx_radius_units = UnitScaleResolver.mm_to_drawing_units(500.0, doc)
        obstacle_buf_units = UnitScaleResolver.mm_to_drawing_units(5.0, doc)

        plan = WireHealPlan(
            drawing_name=drawing_name,
            unit_to_mm=unit_mm,
            unit_source=unit_src,
            max_stitch_gap_mm=max_stitch_mm,
            max_stitch_gap_units=max_stitch_units,
            max_snap_gap_mm=max_snap_mm,
            max_snap_gap_units=max_snap_units,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Metinler için STRtree oluştur
        valid_texts: List[Tuple[str, Point]] = []
        for t in texts:
            val = (t.text or "").strip().upper()
            if val and len(val) <= 35:
                valid_texts.append((val, Point(t.pos[0], t.pos[1])))
        text_tree = STRtree([pt for _, pt in valid_texts]) if valid_texts else None

        # Sadece değiştirilebilir ve kablo/elektrik katmanında olan ModelSpace LINE varlıklarını topla
        line_items: List[Dict[str, Any]] = []
        skipped_non_wire_layers = 0
        for ent in doc.modelspace():
            if ent.dxftype() != "LINE":
                continue
            verdict = CADSafetyGuard.check_entity_mutable(doc, ent)
            if not verdict.allowed:
                continue
            layer = getattr(ent.dxf, "layer", "0")
            if not is_eligible_wire_layer(layer):
                skipped_non_wire_layers += 1
                continue
            s_pt = (float(ent.dxf.start.x), float(ent.dxf.start.y))
            e_pt = (float(ent.dxf.end.x), float(ent.dxf.end.y))
            length = math.hypot(e_pt[0] - s_pt[0], e_pt[1] - s_pt[1])
            if length <= dup_tol_units:
                continue
            geom = LineString([s_pt, e_pt])
            ctx = cls._infer_circuit_context_indexed(geom, valid_texts, text_tree, ctx_radius_units)
            all_ctx = cls._infer_all_circuit_contexts_indexed(geom, valid_texts, text_tree, ctx_radius_units)
            line_items.append({
                "handle": ent.dxf.handle,
                "entity": ent,
                "layer": layer,
                "start": s_pt,
                "end": e_pt,
                "length": length,
                "geom": geom,
                "circuit_ctx": ctx,
                "all_ctx": all_ctx,
            })

        prop_seq = 1
        duplicate_handles: Set[str] = set()

        # ----------------------------------------------------------------------
        # A. DUPLICATE CLEANER (OVERKILL + STRtree + Devre Bağlamı Koruması)
        # ----------------------------------------------------------------------
        n = len(line_items)
        if n > 1:
            line_tree_all = STRtree([it["geom"] for it in line_items])
            for i in range(n):
                li = line_items[i]
                if li["handle"] in duplicate_handles:
                    continue
                cand_indices = line_tree_all.query(li["geom"].buffer(dup_tol_units * 2.0))
                for idx in cand_indices:
                    j = int(idx)
                    if j <= i:
                        continue
                    lj = line_items[j]
                    if lj["handle"] in duplicate_handles or li["layer"] != lj["layer"]:
                        continue
                    same_dir = (
                        math.hypot(li["start"][0] - lj["start"][0], li["start"][1] - lj["start"][1]) <= dup_tol_units
                        and math.hypot(li["end"][0] - lj["end"][0], li["end"][1] - lj["end"][1]) <= dup_tol_units
                    )
                    rev_dir = (
                        math.hypot(li["start"][0] - lj["end"][0], li["start"][1] - lj["end"][1]) <= dup_tol_units
                        and math.hypot(li["end"][0] - lj["start"][0], li["end"][1] - lj["start"][1]) <= dup_tol_units
                    )
                    if same_dir or rev_dir:
                        ctx_a = li["circuit_ctx"]
                        ctx_b = lj["circuit_ctx"]
                        # Eğer üst üste binmiş çizgilerin yakınında birden fazla farklı devre etiketi
                        # (örn. W1 ve W2) varsa veya kendi bağlamları farklıysa sessiz silme YASAKTIR!
                        combined_ctx = list(dict.fromkeys(li["all_ctx"] + lj["all_ctx"]))
                        if ctx_a and ctx_b and ctx_a != ctx_b:
                            ctx_conflict = True
                        elif len(combined_ctx) >= 2:
                            ctx_conflict = True
                            ctx_a = combined_ctx[0]
                            ctx_b = combined_ctx[1]
                        else:
                            ctx_conflict = False

                        duplicate_handles.add(lj["handle"])
                        plan.proposals.append(
                            WireHealProposal(
                                proposal_id=f"WHP-{prop_seq:04d}",
                                action="DELETE_DUPLICATE",
                                primary_handle=li["handle"],
                                secondary_handle=lj["handle"],
                                layer=li["layer"],
                                start_pt=lj["start"],
                                end_pt=lj["end"],
                                gap_drawing_units=0.0,
                                gap_mm=0.0,
                                angle_diff_deg=0.0,
                                circuit_context_a=ctx_a,
                                circuit_context_b=ctx_b,
                                conditions_met={
                                    "same_layer": True,
                                    "coincident_endpoints": True,
                                    "same_circuit_context": not ctx_conflict,
                                },
                                confidence_score=0.40 if ctx_conflict else 1.0,
                                reason=(
                                    f"Üst üste binmiş çizgilerde farklı devre etiketleri ({ctx_a!r} vs {ctx_b!r}) tespit edildi; "
                                    f"iki ayrı devre olabileceği için otomatik silme durduruldu (Onay İstasyonu)."
                                    if ctx_conflict
                                    else f"'{li['layer']}' katmanında üst üste binmiş mükerrer çizgi (OVERKILL)."
                                ),
                                auto_approvable=not ctx_conflict,
                                status="REQUIRES_APPROVAL" if ctx_conflict else "PROPOSED",
                            )
                        )
                        prop_seq += 1

        active_lines = [it for it in line_items if it["handle"] not in duplicate_handles]
        m = len(active_lines)
        active_line_tree = STRtree([it["geom"] for it in active_lines]) if m > 0 else None

        non_arch_symbols = [s for s in symbols if s.classification != "IGNORED_ARCHITECTURAL"]
        sym_bbox_tree = STRtree([s.bbox for s in non_arch_symbols]) if non_arch_symbols else None

        # Stitch adayına giren kablo uçlarını takip et (aynı uca hem STITCH hem SNAP üretilmesini önler!)
        stitched_endpoints: Set[Tuple[str, str]] = set()

        # ----------------------------------------------------------------------
        # B. COLLINEAR STITCHER (4 Şartlı Kopuk Kablo Birleştirici - STRtree ile)
        # ----------------------------------------------------------------------
        stitched_pairs: Set[Tuple[str, str]] = set()
        if m > 1 and active_line_tree is not None:
            for i in range(m):
                li = active_lines[i]
                cand_indices = active_line_tree.query(li["geom"].buffer(max_stitch_units))
                for idx in cand_indices:
                    j = int(idx)
                    if j <= i:
                        continue
                    lj = active_lines[j]

                    # En yakın uç çiftini bul: (end_name_i, pt_a, dir_away_from_a, end_name_j, pt_b, dir_into_b)
                    endpoints_i = [
                        ("end", li["end"], (li["end"][0] - li["start"][0], li["end"][1] - li["start"][1])),
                        ("start", li["start"], (li["start"][0] - li["end"][0], li["start"][1] - li["end"][1])),
                    ]
                    endpoints_j = [
                        ("start", lj["start"], (lj["end"][0] - lj["start"][0], lj["end"][1] - lj["start"][1])),
                        ("end", lj["end"], (lj["start"][0] - lj["end"][0], lj["start"][1] - lj["end"][1])),
                    ]

                    best_pair = None
                    best_gap = float("inf")
                    for end_i, pt_a, vec_a in endpoints_i:
                        for end_j, pt_b, vec_b in endpoints_j:
                            d = math.hypot(pt_b[0] - pt_a[0], pt_b[1] - pt_a[1])
                            if d < best_gap:
                                best_gap = d
                                best_pair = (end_i, pt_a, vec_a, end_j, pt_b, vec_b)

                    if best_pair is None or not (min_gap_units <= best_gap <= max_stitch_units):
                        continue

                    pair_key = tuple(sorted((li["handle"], lj["handle"])))
                    if pair_key in stitched_pairs:
                        continue
                    stitched_pairs.add(pair_key)

                    end_i, pt_a, vec_a, end_j, pt_b, vec_b = best_pair
                    stitched_endpoints.add((li["handle"], end_i))
                    stitched_endpoints.add((lj["handle"], end_j))

                    bridge_vec = (pt_b[0] - pt_a[0], pt_b[1] - pt_a[1])

                    # ŞART 1: Aynı Katman
                    cond_same_layer = li["layer"] == lj["layer"]

                    # ŞART 2: Doğrusal Hizalanma (Hem iki çizgi birbirine paralel olmalı,
                    # HEM DE aradaki köprü vektörü her iki çizgiyle aynı doğrultuda olmalı!)
                    ang_lines = cls._angle_between_vectors_deg(vec_a, vec_b)
                    ang_bridge_a = cls._angle_between_vectors_deg(vec_a, bridge_vec)
                    ang_bridge_b = cls._angle_between_vectors_deg(bridge_vec, vec_b)
                    max_ang = max(ang_lines, ang_bridge_a, ang_bridge_b)
                    cond_collinear = max_ang <= collinear_angle_tol_deg

                    # ŞART 3: Aradaki Boşlukta Başka Sembol veya Kesişen Kablo Yok (STRtree ile)
                    bridge_geom = LineString([pt_a, pt_b])
                    bridge_zone = bridge_geom.buffer(obstacle_buf_units)

                    has_symbol_obstacle = False
                    if sym_bbox_tree is not None:
                        for s_idx in sym_bbox_tree.query(bridge_zone):
                            if non_arch_symbols[int(s_idx)].bbox.intersects(bridge_zone):
                                has_symbol_obstacle = True
                                break

                    has_crossing_wire = False
                    for l_idx in active_line_tree.query(bridge_geom):
                        other = active_lines[int(l_idx)]
                        if other["handle"] not in (li["handle"], lj["handle"]) and other["geom"].intersects(bridge_geom):
                            has_crossing_wire = True
                            break

                    cond_no_obstacle = (not has_symbol_obstacle) and (not has_crossing_wire)

                    # ŞART 4: Uçlarda Aynı Pano / Devre Bağlamı (Çelişki Yok)
                    ctx_a = li["circuit_ctx"]
                    ctx_b = lj["circuit_ctx"]
                    if ctx_a and ctx_b:
                        cond_same_context = ctx_a == ctx_b
                    else:
                        cond_same_context = True

                    all_four_met = (
                        cond_same_layer and cond_collinear and cond_no_obstacle and cond_same_context
                    )

                    gap_mm = best_gap * unit_mm
                    conditions_dict = {
                        "1_same_layer": cond_same_layer,
                        "2_collinear_aligned": cond_collinear,
                        "3_no_intermediate_symbol_or_crossing": cond_no_obstacle,
                        "4_same_circuit_context": cond_same_context,
                    }

                    if all_four_met:
                        reason = (
                            f"4/4 koşul sağlandı: Aynı katman ({li['layer']}), doğrusal açı farkı {max_ang:.1f}°, "
                            f"arada engel yok, devre bağlamı uyumlu ({ctx_a or 'genel'}). Boşluk: {gap_mm:.1f} mm."
                        )
                        plan.proposals.append(
                            WireHealProposal(
                                proposal_id=f"WHP-{prop_seq:04d}",
                                action="STITCH_COLLINEAR_GAP",
                                primary_handle=li["handle"],
                                secondary_handle=lj["handle"],
                                layer=li["layer"],
                                start_pt=pt_a,
                                end_pt=pt_b,
                                gap_drawing_units=round(best_gap, 4),
                                gap_mm=round(gap_mm, 1),
                                angle_diff_deg=round(max_ang, 2),
                                circuit_context_a=ctx_a,
                                circuit_context_b=ctx_b,
                                conditions_met=conditions_dict,
                                confidence_score=0.95,
                                reason=reason,
                                auto_approvable=True,
                                status="PROPOSED",
                            )
                        )
                        prop_seq += 1
                    else:
                        failed_keys = [k for k, v in conditions_dict.items() if not v]
                        reason = (
                            f"Otomatik birleştirme reddedildi (Onay İstasyonu): Eksik koşullar={failed_keys}, "
                            f"açı={max_ang:.1f}°, devreler=({ctx_a!r} vs {ctx_b!r})."
                        )
                        plan.proposals.append(
                            WireHealProposal(
                                proposal_id=f"WHP-{prop_seq:04d}",
                                action="STITCH_COLLINEAR_GAP",
                                primary_handle=li["handle"],
                                secondary_handle=lj["handle"],
                                layer=li["layer"],
                                start_pt=pt_a,
                                end_pt=pt_b,
                                gap_drawing_units=round(best_gap, 4),
                                gap_mm=round(gap_mm, 1),
                                angle_diff_deg=round(max_ang, 2),
                                circuit_context_a=ctx_a,
                                circuit_context_b=ctx_b,
                                conditions_met=conditions_dict,
                                confidence_score=0.35,
                                reason=reason,
                                auto_approvable=False,
                                status="REQUIRES_APPROVAL",
                            )
                        )
                        prop_seq += 1

        # ----------------------------------------------------------------------
        # C. SYMBOL SNAPPER (STRtree + Çift Müdahale Koruması + Kademeli Onay)
        # ----------------------------------------------------------------------
        elec_symbols = [
            s for s in symbols if s.classification not in ("IGNORED_ARCHITECTURAL", "UNKNOWN")
        ]
        elec_sym_pts = [Point(s.pos[0], s.pos[1]) for s in elec_symbols]
        elec_sym_tree = STRtree(elec_sym_pts) if elec_sym_pts else None

        if elec_sym_tree is not None:
            for li in active_lines:
                for end_name, pt in (("start", li["start"]), ("end", li["end"])):
                    # Eğer bu uç zaten STITCH adayına girdiyse aynı uca ikinci kez SNAP üretme!
                    if (li["handle"], end_name) in stitched_endpoints:
                        continue

                    pt_geom = Point(pt[0], pt[1])
                    cand_sym_indices = elec_sym_tree.query(pt_geom.buffer(max_snap_units))
                    best_sym = None
                    best_dist = float("inf")
                    for s_idx in cand_sym_indices:
                        sym = elec_symbols[int(s_idx)]
                        sp = (sym.pos[0], sym.pos[1])
                        d = math.hypot(sp[0] - pt[0], sp[1] - pt[1])
                        if min_gap_units <= d <= max_snap_units and d < best_dist:
                            best_dist = d
                            best_sym = sym

                    if best_sym is not None:
                        sp = (best_sym.pos[0], best_sym.pos[1])
                        gap_mm = best_dist * unit_mm
                        # Küçük mikro boşluklar (<= auto_snap_max_cm, varsayılan 5 cm = 50 mm) otomatik onaylanabilir;
                        # daha büyük mesafeler (> 5 cm) sessiz geometri değişimini önlemek için Onay İstasyonu'na düşer!
                        is_auto_snap = best_dist <= (auto_snap_max_units + 1e-9)
                        plan.proposals.append(
                            WireHealProposal(
                                proposal_id=f"WHP-{prop_seq:04d}",
                                action=f"SNAP_TO_SYMBOL_{end_name.upper()}",
                                primary_handle=li["handle"],
                                secondary_handle=best_sym.dxf_handle or best_sym.block_name,
                                layer=li["layer"],
                                start_pt=pt,
                                end_pt=sp,
                                gap_drawing_units=round(best_dist, 4),
                                gap_mm=round(gap_mm, 1),
                                angle_diff_deg=0.0,
                                circuit_context_a=li["circuit_ctx"],
                                circuit_context_b=best_sym.circuit_tag or best_sym.block_name,
                                conditions_met={
                                    "within_snap_tolerance": True,
                                    "within_auto_micro_snap_limit": is_auto_snap,
                                    "electrical_symbol_verified": True,
                                    "not_already_stitched": True,
                                },
                                confidence_score=0.95 if is_auto_snap else 0.75,
                                reason=(
                                    f"Açık kablo ucu mikro boşluk ({gap_mm:.1f} mm <= {auto_snap_max_mm:.0f} mm) içinde "
                                    f"'{best_sym.block_name}' sembolüne mıknatıslandı."
                                    if is_auto_snap
                                    else f"Açık kablo ucu {gap_mm:.1f} mm (> {auto_snap_max_mm:.0f} mm) mesafedeki "
                                    f"'{best_sym.block_name}' sembolüne aday; Onay İstasyonu onayı gerekir."
                                ),
                                auto_approvable=is_auto_snap,
                                status="PROPOSED" if is_auto_snap else "REQUIRES_APPROVAL",
                            )
                        )
                        prop_seq += 1

        plan.summary_counts = {
            "total_proposals": len(plan.proposals),
            "auto_approvable": sum(1 for p in plan.proposals if p.auto_approvable),
            "requires_approval": sum(1 for p in plan.proposals if not p.auto_approvable),
            "duplicates_found": sum(1 for p in plan.proposals if p.action == "DELETE_DUPLICATE"),
            "duplicates_auto": sum(1 for p in plan.proposals if p.action == "DELETE_DUPLICATE" and p.auto_approvable),
            "duplicates_blocked": sum(1 for p in plan.proposals if p.action == "DELETE_DUPLICATE" and not p.auto_approvable),
            "collinear_stitches_auto": sum(
                1 for p in plan.proposals if p.action == "STITCH_COLLINEAR_GAP" and p.auto_approvable
            ),
            "collinear_stitches_blocked": sum(
                1 for p in plan.proposals if p.action == "STITCH_COLLINEAR_GAP" and not p.auto_approvable
            ),
            "symbol_snaps": sum(1 for p in plan.proposals if p.action.startswith("SNAP_TO_SYMBOL")),
            "symbol_snaps_auto": sum(
                1 for p in plan.proposals if p.action.startswith("SNAP_TO_SYMBOL") and p.auto_approvable
            ),
            "symbol_snaps_requires_approval": sum(
                1 for p in plan.proposals if p.action.startswith("SNAP_TO_SYMBOL") and not p.auto_approvable
            ),
            "skipped_non_wire_layer_lines": skipped_non_wire_layers,
        }
        return plan

    @classmethod
    def apply_plan(
        cls,
        doc: Any,
        plan: WireHealPlan,
        approved_proposal_ids: Optional[Set[str]] = None,
        rejected_proposal_ids: Optional[Set[str]] = None,
        output_dxf_path: Optional[Union[str, Path]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Onaylanan kablo onarım önerilerini (Duplicate silme, Collinear köprüleme, Sembol snap)
        ModelSpace üzerinde uygular ve uygulanan işlemlerin kaydını döner.
        Seçilmeyen önerileri 'REJECTED' yerine 'NOT_SELECTED' olarak işaretler.
        """
        applied: List[Dict[str, Any]] = []
        msp = doc.modelspace()

        for prop in plan.proposals:
            if rejected_proposal_ids is not None and prop.proposal_id in rejected_proposal_ids:
                prop.status = "REJECTED"
                continue

            if approved_proposal_ids is not None:
                if prop.proposal_id not in approved_proposal_ids:
                    if prop.status not in ("REQUIRES_APPROVAL", "REJECTED"):
                        prop.status = "NOT_SELECTED"
                    continue
            else:
                if not prop.auto_approvable:
                    continue

            if prop.action == "DELETE_DUPLICATE":
                verdict = CADSafetyGuard.check_entity_mutable(doc, prop.secondary_handle)
                if not verdict.allowed:
                    continue
                dup_ent = doc.entitydb.get(prop.secondary_handle)
                if dup_ent is not None and getattr(dup_ent, "is_alive", True):
                    msp.delete_entity(dup_ent)
                    prop.status = "APPROVED"
                    applied.append({"proposal_id": prop.proposal_id, "action": prop.action, "deleted": prop.secondary_handle})

            elif prop.action == "STITCH_COLLINEAR_GAP":
                verdict = CADSafetyGuard.check_entity_mutable(doc, prop.primary_handle)
                if not verdict.allowed:
                    continue
                bridge_line = msp.add_line(
                    prop.start_pt,
                    prop.end_pt,
                    dxfattribs={"layer": prop.layer, "color": 256},
                )
                prop.status = "APPROVED"
                applied.append({
                    "proposal_id": prop.proposal_id,
                    "action": prop.action,
                    "new_bridge_handle": bridge_line.dxf.handle,
                    "layer": prop.layer,
                })

            elif prop.action.startswith("SNAP_TO_SYMBOL_"):
                verdict = CADSafetyGuard.check_entity_mutable(doc, prop.primary_handle)
                if not verdict.allowed:
                    continue
                line_ent = doc.entitydb.get(prop.primary_handle)
                if line_ent is None:
                    continue
                if prop.action.endswith("_START"):
                    line_ent.dxf.start = (prop.end_pt[0], prop.end_pt[1], 0.0)
                else:
                    line_ent.dxf.end = (prop.end_pt[0], prop.end_pt[1], 0.0)
                prop.status = "APPROVED"
                applied.append({
                    "proposal_id": prop.proposal_id,
                    "action": prop.action,
                    "snapped_handle": prop.primary_handle,
                })

        if output_dxf_path is not None:
            out_p = Path(output_dxf_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            doc.saveas(out_p)

        return applied
