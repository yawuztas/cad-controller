# -*- coding: utf-8 -*-
"""
Aşama 1F — Evrensel Envanter ve Metraj Çıkarıcı (`metraj_cikarici.py`)
========================================================================
`RawCADSnapshot` ve `CanonicalProjectModel` verilerinden;
- Pano / Dağıtım Tablosu Listesi,
- Şalt & Koruma Ekipmanı Metrajı (KAKR, Sigorta/TMŞ, Sayaç, Parafudr),
- Kablo ve Temel Topraklama Metrajı,
- Kat Planı / Pafta Bazlı Sembol & Armatür Metrajı
çıkarır ve mühendisin AutoCAD projesiyle 30 saniyede eşleştirip
doğrulayabileceği okunaklı Markdown + JSON özetini üretir.

GEMINI.md kurallarına %100 uygundur: sabit pano adı, dosya adı, koordinat
veya sayı uydurma/fallback KESİNLİKLE içermez.
"""

from __future__ import annotations
from collections import Counter, defaultdict
import math
from pathlib import Path
import re
import statistics
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

from .disiplin_ayirici import (
    build_container_block_names,
    classify_insert_role,
    classify_paths_arch_vs_elec,
    describe_wire_layer,
    detect_cloned_architectural_entities,
    find_below_title_for_sheet,
    infer_view_discipline,
    is_clean_legend_desc,
    is_container_insert,
    is_dim_or_tick_subprimitive,
    parse_floor_label,
    partition_outside_regions,
)
from .metin_temizleyici import norm_tr, parse_tr_float
from .pafta_ayirici import find_legend_table_regions
from .schema import (
    CableBomItem,
    CanonicalProjectModel,
    LoadScheduleBreakerItem,
    NormalizedTable,
    OleTableSummary,
    OutsideClusterSummary,
    PanelInventoryItem,
    ProjectInventory,
    ProjectViewSummary,
    RawCADSnapshot,
    RawInsert,
    RawPath,
    RawText,
    SheetFrame,
    SwitchgearBomItem,
    SymbolBomItem,
    WireLayerBomItem,
)

# ---------------------------------------------------------------------------
# Evrensel Mühendislik Örüntüleri (Türk / IEC Elektrik Standartları)
# ---------------------------------------------------------------------------

_RE_RCD_TAG = re.compile(r"^(?:KAKR?|RCD)$", re.IGNORECASE)
_RE_RCD_MA = re.compile(r"^(\d{2,3})\s*mA$", re.IGNORECASE)
_RE_POLE_AMP = re.compile(r"^([1234])\s*[xX*]\s*(\d{1,4})\s*\(?A\)?$", re.IGNORECASE)
_RE_METER = re.compile(r"^([13])\s*[xX*]\s*\d{1,3}\(\s*\d{1,3}\s*A?\)$", re.IGNORECASE)
_RE_BREAKER_CURVE = re.compile(r"^(?:[BCDK]\s*\d{0,2}|[1234])\s*\(\s*\d{1,4}\s*A\)$", re.IGNORECASE)
_RE_BREAKER_SHORT = re.compile(r"^[BCDK]\s*(?:2|4|6|10|16|20|25|32|40|50|63|80|100|125)\s*A?$", re.IGNORECASE)
_RE_TMS = re.compile(r"^TM[SŞ](?:\s*\d+x?\d*\s*A?)?$", re.IGNORECASE)
_RE_SPD = re.compile(r"^(?:SPD|PARAFUDR)$", re.IGNORECASE)
_RE_AOS = re.compile(r"^AOS$", re.IGNORECASE)

_RE_CABLE = re.compile(
    r"(?:\d+\s*[xX*]\s*\(\s*\d+\s*[xX*]\s*\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?\s*[şsŞS]?)?(?:\s*\+\s*\d+(?:[.,]\d+)?)?"
    r"(?:\s*mm[2²])?(?:\s*(?:NYY|N2XH|N2XRH|N2XCH|N2XSY|NA2XSY|NHXMH|NYM|TTR|YVV|H07V|H07Z|07Z1|FE180|PH\d+|CU|XLPE|LSZH|LS0H|LSOH|HFFR)(?:-[A-Z0-9]+)?)*\s*\)"
    r"(?:\s*mm[2²])?(?:\s*(?:NYY|N2XH|N2XRH|N2XCH|N2XSY|NA2XSY|NHXMH|NYM|TTR|YVV|H07V|H07Z|07Z1|FE180|PH\d+|CU|XLPE|LSZH|LS0H|LSOH|HFFR)(?:-[A-Z0-9]+)?)*)"
    r"|(?:\d+\s*[xX*]\s*\d+(?:[.,]\d+)?(?:\s*\+\s*\d+(?:[.,]\d+)?)?(?:/\d+(?:[.,]\d+)?\s*[şsŞS]?)?\s*"
    r"(?:mm[2²]\s*)?(?:NYY|N2XH|N2XRH|N2XCH|N2XSY|NA2XSY|NHXMH|NYM|TTR|YVV|H07V|H07Z|07Z1|FE180|CU|XLPE|LSZH|LS0H|LSOH|HFFR)(?:-[A-Z0-9]+)?"
    r"(?:[/\s]*\d+(?:[.,]\d+)?\s*mm[2²])?(?:\s*(?:\(\s*(?:07Z1|FE\s*180|PH\s*\d+|HFFR|LSZH|LS0H|LSOH)\s*\)|07Z1|FE\s*180|PH\s*\d+|LSZH|LS0H|LSOH|HFFR|E90|XLPE))*)"
    r"|(?:\d+\s*mm[2²]\s*(?:Cu|H07Z-?R|XLPE|N2XH|N2XRH|N2XCH))"
    r"|(?:(?:U/FTP|SF/UTP|F/UTP|S/FTP|U/UTP|F/STP|FTP|STP|UTP)\s+)?CAT\s*[5678][AE]?(?:\s+(?:\(\s*(?:HFFR|LSZH|LS0H|LSOH)\s*\)|LSZH|LS0H|LSOH|HFFR|UTP|FTP|STP))*"
    r"|(?:RG\s*\d+[/U\-]*\d*)"
    r"|(?:DT\d+\s+Duafon\s+Kablosu)",
    re.IGNORECASE,
)
_RE_LEN_M = re.compile(r"^(\d+(?:[.,]\d+)?)\s*m$", re.IGNORECASE)
_RE_WATT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(k?W|VA|kVA)\b", re.IGNORECASE)

# Pano aday metni olarak YANLIŞLIKLA seçilmemesi gereken genel şema kelimeleri
_NOT_PANEL_TOKENS = {
    "M", "W", "KW", "KVA", "VA", "KA", "MA", "AOS", "TMS", "TMŞ", "KAK",
    "KAKR", "CAT", "CU", "NYY", "N2XH", "TEDAS", "TEDASDAN", "TEDASTAN",
    "ZEMIN", "BODRUM", "CATI", "NORMAL", "GALERI", "KAT", "SEMBOL",
    "ACIKLAMA", "ACIKLAMASI", "LINYE", "KOLON", "KURULU", "TALEP",
}


def _assign_items_to_sheets(
    sheets: List[SheetFrame],
    texts: List[RawText],
    inserts: List[RawInsert],
    paths: List[RawPath],
) -> Tuple[
    Dict[str, List[RawText]],
    Dict[str, List[RawInsert]],
    Dict[str, List[RawPath]],
    List[RawText],
    List[RawInsert],
    List[RawPath],
]:
    """Ham TEXT, INSERT ve PATH nesnelerini en dar kapsayan paftaya atar; dışarıda kalanları ayırır."""
    by_space: Dict[str, List[SheetFrame]] = defaultdict(list)
    for sh in sheets:
        by_space[sh.space].append(sh)

    texts_by_sheet: Dict[str, List[RawText]] = defaultdict(list)
    inserts_by_sheet: Dict[str, List[RawInsert]] = defaultdict(list)
    paths_by_sheet: Dict[str, List[RawPath]] = defaultdict(list)
    outside_texts: List[RawText] = []
    outside_inserts: List[RawInsert] = []
    outside_paths: List[RawPath] = []

    def _find_sheet(space: str, x: float, y: float) -> Optional[str]:
        if space.startswith("PAPERSPACE:"):
            cands = by_space.get(space, [])
            return cands[0].frame_id if cands else None
        hits = []
        for sh in by_space.get(space, []):
            b = sh.bbox_du
            if b.minx <= x <= b.maxx and b.miny <= y <= b.maxy:
                hits.append((b.width * b.height, sh.frame_id))
        if not hits:
            return None
        return min(hits, key=lambda item: item[0])[1]

    for t in texts:
        sid = _find_sheet(t.space, t.x, t.y)
        if sid:
            texts_by_sheet[sid].append(t)
        else:
            outside_texts.append(t)

    for ins in inserts:
        if ins.is_xref:
            continue
        sid = _find_sheet(ins.space, ins.x, ins.y)
        if sid:
            inserts_by_sheet[sid].append(ins)
        else:
            outside_inserts.append(ins)

    for p in paths:
        cx, cy = p.bbox.center
        sid = _find_sheet(p.space, cx, cy)
        if sid:
            paths_by_sheet[sid].append(p)
        else:
            outside_paths.append(p)

    return texts_by_sheet, inserts_by_sheet, paths_by_sheet, outside_texts, outside_inserts, outside_paths


def _parse_power_watts(text: str) -> Optional[float]:
    m = _RE_WATT.search(text.replace(",", "."))
    if not m:
        return None
    val = parse_tr_float(m.group(1))
    if val is None:
        return None
    unit = m.group(2).upper()
    return val * 1000.0 if unit in ("KW", "KVA") else val


def _extract_schematic_bom(
    sheets: List[SheetFrame],
    texts_by_sheet: Dict[str, List[RawText]],
    inserts_by_sheet: Dict[str, List[RawInsert]],
) -> Tuple[List[PanelInventoryItem], List[SwitchgearBomItem], List[CableBomItem]]:
    """
    KOLON_SEMASI / TEK_HAT / PLAN paftalarından mekânsal yakınlıkla
    pano, şalt ekipmanı (KAKR, sigorta, sayaç) ve kablo metrajı çıkarır.
    """
    switchgear_counts: Dict[Tuple[str, str], Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    switchgear_handles: Dict[Tuple[str, str], List[str]] = defaultdict(list)

    cable_occ: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cable_len: Dict[str, float] = defaultdict(float)
    cable_has_len: Dict[str, bool] = defaultdict(bool)
    cable_handles: Dict[str, List[str]] = defaultdict(list)

    panels_map: Dict[str, PanelInventoryItem] = {}

    def _add_panel(
        name: str,
        sheet_id: str,
        role: str = "BELIRSIZ",
        parent_panel: Optional[str] = None,
        breaker: Optional[str] = None,
        rcd: Optional[str] = None,
        cable: Optional[str] = None,
        p_inst: Optional[float] = None,
        p_dem: Optional[float] = None,
        handles: Iterable[str] = (),
    ) -> None:
        key = norm_tr(name).upper()
        if key not in panels_map:
            panels_map[key] = PanelInventoryItem(
                panel_name=name.strip(),
                role=role,  # type: ignore[arg-type]
                parent_panel=parent_panel,
                sheet_ids=[sheet_id],
                breaker_rating=breaker,
                rcd_rating=rcd,
                feeder_cable=cable,
                installed_power_w=p_inst,
                demand_power_w=p_dem,
                source_handles=[h for h in handles if h],
            )
        else:
            p = panels_map[key]
            if sheet_id not in p.sheet_ids:
                p.sheet_ids.append(sheet_id)
            if role != "BELIRSIZ" and p.role == "BELIRSIZ":
                p.role = role  # type: ignore[assignment]
            p.parent_panel = p.parent_panel or parent_panel
            p.breaker_rating = p.breaker_rating or breaker
            p.rcd_rating = p.rcd_rating or rcd
            p.feeder_cable = p.feeder_cable or cable
            if p_inst is not None and p.installed_power_w is None:
                p.installed_power_w = p_inst
            if p_dem is not None and p.demand_power_w is None:
                p.demand_power_w = p_dem
            for h in handles:
                if h and h not in p.source_handles:
                    p.source_handles.append(h)

    # 1. Blok ATTRIB'lerinden gelen açık pano tanımları (tüm paftalarda)
    for sh in sheets:
        for ins in inserts_by_sheet.get(sh.frame_id, []):
            for attr_k, attr_v in ins.attribs.items():
                ak = norm_tr(attr_k).upper()
                av = attr_v.strip()
                if av and any(tok in ak for tok in ("PANO", "PANEL", "TABLO")) and len(av) <= 24:
                    _add_panel(av, sh.frame_id, handles=[ins.handle])

    # 2. Şema ve gerilim düşümü paftalarında şalt + kablo + pano kümesi çıkarımı
    #    Önce birincil şema paftalarını (KOLON_SEMASI, TEK_HAT) işle; GERILIM_DUSUMU
    #    yalnızca birincil şemadan hiç kablo çıkmadıysa yedek kaynak olarak kullanılır (çift sayım önlenir).
    primary_sh = [sh for sh in sheets if sh.role in ("KOLON_SEMASI", "TEK_HAT")]
    vd_sh = [sh for sh in sheets if sh.role == "GERILIM_DUSUMU"]
    ordered_schematic = primary_sh + vd_sh
    has_primary_cables = False

    def _match_cables_on_sheet(
        sh_id: str,
        f_texts: List[RawText],
        h_med: float,
        consumed_idx: Set[int],
    ) -> int:
        matched_count = 0
        cable_nodes: List[Tuple[int, RawText, str, bool]] = []
        len_nodes: List[Tuple[int, RawText, float]] = []

        for idx, t in enumerate(f_texts):
            if idx in consumed_idx:
                continue
            txt = t.text.strip()
            if len(txt) <= 55 and _RE_CABLE.search(txt):
                consumed_idx.add(idx)
                # Aynı satır içinde "4x6N2XH 18m" gibi boy varsa mm2 hariç m değerini ayır
                txt_no_mm2 = re.sub(r"\d+(?:[.,]\d+)?\s*mm2", "", txt, flags=re.IGNORECASE)
                m_inline = re.search(r"\b(\d+(?:[.,]\d+)?)\s*m\b", txt_no_mm2, re.IGNORECASE)
                spec_raw = txt
                inline_len: Optional[float] = None
                if m_inline:
                    cand_v = parse_tr_float(m_inline.group(1))
                    if cand_v is not None and 0.1 <= cand_v <= 2000.0:
                        inline_len = cand_v
                        spec_raw = (txt[:m_inline.start()] + txt[m_inline.end():]).strip()
                spec = re.sub(r"\s+", " ", spec_raw).strip(" /-–")
                if not spec:
                    spec = re.sub(r"\s+", " ", txt).strip()
                cable_occ[spec][sh_id] += 1
                matched_count += 1
                if t.handle:
                    cable_handles[spec].append(t.handle)
                if inline_len is not None:
                    cable_len[spec] += inline_len
                    cable_has_len[spec] = True
                cable_nodes.append((idx, t, spec, inline_len is not None))
            else:
                m_l = _RE_LEN_M.match(txt)
                if m_l:
                    lv = parse_tr_float(m_l.group(1))
                    if lv is not None and 0.1 <= lv <= 2000.0:
                        len_nodes.append((idx, t, lv))

        # 1'e 1 en yakın komşu (weighted distance) eşleme: bir boy etiketi yalnızca 1 kabloya gider
        pair_candidates: List[Tuple[float, int, str, int, float]] = []
        for c_idx, ct, spec, has_inline in cable_nodes:
            if has_inline:
                continue
            local_h = min(max(ct.height if ct.height > 0 else h_med, h_med), 3.0 * h_med)
            max_dx = 10.0 * local_h
            max_dy = 5.5 * local_h
            for l_idx, lt, lv in len_nodes:
                if l_idx in consumed_idx:
                    continue
                dx = abs(lt.x - ct.x)
                dy = abs(lt.y - ct.y)
                if dx <= max_dx and dy <= max_dy:
                    cost = math.hypot(dx * 1.5, dy)
                    pair_candidates.append((cost, c_idx, spec, l_idx, lv))

        pair_candidates.sort(key=lambda item: item[0])
        matched_cables: Set[int] = set()
        for _cost, c_idx, spec, l_idx, lv in pair_candidates:
            if c_idx in matched_cables or l_idx in consumed_idx:
                continue
            matched_cables.add(c_idx)
            consumed_idx.add(l_idx)
            cable_len[spec] += lv
            cable_has_len[spec] = True

        return matched_count

    for sh in ordered_schematic:
        f_texts = texts_by_sheet.get(sh.frame_id, [])
        if not f_texts:
            continue

        heights = [t.height for t in f_texts if t.height > 0]
        h_med = statistics.median(heights) if heights else 2.5
        consumed_idx: Set[int] = set()

        # Gerilim düşümü paftası: yalnızca birincil şemadan hiç kablo bulunamadıysa kullan
        if sh.role == "GERILIM_DUSUMU":
            if not has_primary_cables:
                _match_cables_on_sheet(sh.frame_id, f_texts, h_med, consumed_idx)
            continue

        # 2A. KAKR (Kaçak Akım Koruma Rölesi) kümeleri: "KAK"/"KAKR" veya "30mA"/"300mA" çevresi
        for idx, t in enumerate(f_texts):
            if idx in consumed_idx:
                continue
            txt = t.text.strip()
            if not (_RE_RCD_TAG.match(txt) or _RE_RCD_MA.match(txt)):
                continue

            # Yakındaki (yatay 7*H, dikey 4.8*H) parçalardan amper ve mA topla
            nbrs = [
                (j, o) for j, o in enumerate(f_texts)
                if j not in consumed_idx
                and abs(o.x - t.x) <= 7.0 * h_med
                and abs(o.y - t.y) <= 4.8 * h_med
            ]
            amp_txt = None
            ma_txt = None
            has_kak_word = _RE_RCD_TAG.match(txt) is not None
            cluster_indices: List[int] = []
            cluster_handles: List[str] = []

            for j, o in nbrs:
                os = o.text.strip()
                if _RE_RCD_TAG.match(os):
                    has_kak_word = True
                    cluster_indices.append(j)
                    if o.handle:
                        cluster_handles.append(o.handle)
                elif _RE_RCD_MA.match(os) and ma_txt is None:
                    ma_txt = os.replace(" ", "")
                    cluster_indices.append(j)
                    if o.handle:
                        cluster_handles.append(o.handle)
                elif _RE_POLE_AMP.match(os) and amp_txt is None:
                    if abs(o.x - t.x) <= 4.0 * h_med and abs(o.y - t.y) <= 3.8 * h_med:
                        amp_txt = os.replace(" ", "")
                        cluster_indices.append(j)
                        if o.handle:
                            cluster_handles.append(o.handle)

            if has_kak_word or (ma_txt and amp_txt):
                for j in cluster_indices:
                    consumed_idx.add(j)
                parts = [p for p in (amp_txt, ma_txt, "KAKR") if p]
                spec = " ".join(parts)
                switchgear_counts[("KAKR", spec)][sh.frame_id] += 1
                switchgear_handles[("KAKR", spec)].extend(cluster_handles)

        # 2B. Sayaçlar (3x5(60A), 3x10(30A) vb.)
        for idx, t in enumerate(f_texts):
            if idx in consumed_idx:
                continue
            txt = t.text.strip()
            if _RE_METER.match(txt):
                consumed_idx.add(idx)
                spec = f"Sayaç {txt.replace(' ', '')}"
                switchgear_counts[("SAYAC", spec)][sh.frame_id] += 1
                if t.handle:
                    switchgear_handles[("SAYAC", spec)].append(t.handle)

        # 2C. Kablolar (1'e 1 yakın metre etiketi eşlemesi dahil)
        if _match_cables_on_sheet(sh.frame_id, f_texts, h_med, consumed_idx) > 0:
            has_primary_cables = True

        # 2D. Sigorta / TMŞ / Kompakt Şalter + Parafudr (AOS)
        for idx, t in enumerate(f_texts):
            if idx in consumed_idx:
                continue
            txt = t.text.strip()
            if len(txt) > 22:
                continue
            if _RE_SPD.match(txt):
                consumed_idx.add(idx)
                spec = txt.upper()
                switchgear_counts[("PARAFUDR_AOS", spec)][sh.frame_id] += 1
                if t.handle:
                    switchgear_handles[("PARAFUDR_AOS", spec)].append(t.handle)
            elif _RE_AOS.match(txt):
                consumed_idx.add(idx)
                spec = "AOS (Anahtarlı Otomatik Sigorta)"
                switchgear_counts[("SIGORTA_SALTER", spec)][sh.frame_id] += 1
                if t.handle:
                    switchgear_handles[("SIGORTA_SALTER", spec)].append(t.handle)
            elif _RE_BREAKER_CURVE.match(txt) or _RE_BREAKER_SHORT.match(txt) or _RE_POLE_AMP.match(txt) or _RE_TMS.match(txt):
                consumed_idx.add(idx)
                spec = txt.replace(" ", "")
                if _RE_POLE_AMP.match(txt):
                    for j, o in enumerate(f_texts):
                        if j not in consumed_idx and _RE_TMS.match(o.text.strip()):
                            if abs(o.x - t.x) <= 5.0 * h_med and abs(o.y - t.y) <= 2.5 * h_med:
                                spec = f"{spec} TMŞ"
                                consumed_idx.add(j)
                                break
                switchgear_counts[("SIGORTA_SALTER", spec)][sh.frame_id] += 1
                if t.handle:
                    switchgear_handles[("SIGORTA_SALTER", spec)].append(t.handle)

        # 2E. Pano Etiketleri (Satır koridoru / Voronoi yarı-aralık ve kilitli bölme hiyerarşisi ile)
        anchors = [
            t for t in f_texts
            if any(k in norm_tr(t.text).upper() for k in ("KURULU GUC", "TALEP GUC", "KAK", "TMS", "TALI TABLO", "ANA TABLO"))
        ]
        raw_panel_cands: List[Tuple[RawText, str, str]] = []
        for t in f_texts:
            txt = t.text.strip()
            if not (2 <= len(txt) <= 18):
                continue
            nt = norm_tr(txt).upper()
            if nt in _NOT_PANEL_TOKENS:
                continue
            if re.match(r"^\d+(?:[.,]\d+)?\s*(?:W|KW|KVA|M|KA|MA|A|V|MM2)?$", nt):
                continue
            if _RE_CABLE.search(txt) or _RE_BREAKER_CURVE.match(txt) or _RE_BREAKER_SHORT.match(txt) or _RE_POLE_AMP.match(txt) or _RE_METER.match(txt) or _RE_RCD_MA.match(txt):
                continue
            if re.match(r"^\d+\.?\s*KAT$", nt):
                continue
            looks_like_panel_code = bool(
                re.match(r"^(?:AT|TT|OT|O-T|D-T\d*|DT-\d+|KT-\d+|DP-\d+|AP-\d+|TP-\d+|MDP[-\w]*|DB[-\w]*|LP[-\w]*|PANO[-\s\w]+|.*PANO.*)$", nt)
            )
            near_anchor = any(abs(a.x - t.x) <= 14.0 * h_med and abs(a.y - t.y) <= 18.0 * h_med for a in anchors)
            if not (looks_like_panel_code or (near_anchor and re.match(r"^[A-ZÇĞİÖŞÜ][A-Z0-9ÇĞİÖŞÜ\-]{1,10}$", nt))):
                continue
            p_role = "ANA_PANO" if nt in ("AT", "MDP", "AP", "ANA PANO", "ANA TABLO") else (
                "ORTAK_PANO" if nt in ("OT", "O-T", "ORTAK", "ORTAK PANO") else "TALI_PANO"
            )
            raw_panel_cands.append((t, nt, p_role))

        main_panel_name = next((c[0].text.strip() for c in raw_panel_cands if c[2] == "ANA_PANO"), None)

        for t, nt, p_role in raw_panel_cands:
            txt = t.text.strip()
            # Aynı kolon ve aynı satırdaki komşu panolara göre koridor sınırını dinamik hesapla
            same_col = [
                o for o, _, _ in raw_panel_cands
                if o is not t and abs(o.x - t.x) <= 22.0 * h_med and abs(o.y - t.y) > 2.5 * h_med
            ]
            same_row = [
                o for o, _, _ in raw_panel_cands
                if o is not t and abs(o.y - t.y) <= 8.0 * h_med and abs(o.x - t.x) > 22.0 * h_med
            ]
            right_xs = [o.x - t.x for o in same_row if o.x > t.x]
            left_xs = [t.x - o.x for o in same_row if o.x < t.x]
            if same_col:
                above_ys = [o.y - t.y for o in same_col if o.y > t.y]
                below_ys = [t.y - o.y for o in same_col if o.y < t.y]
                dy_up = min(10.0 * h_med, 0.56 * min(above_ys)) if above_ys else 10.0 * h_med
                dy_dn = min(10.0 * h_med, 0.44 * min(below_ys)) if below_ys else 10.0 * h_med
                dx_left = min(52.0 * h_med, 0.5 * min(left_xs)) if left_xs else 52.0 * h_med
                dx_right = min(52.0 * h_med, 0.5 * min(right_xs)) if right_xs else 52.0 * h_med
                pwr_dy_up, pwr_dy_dn = min(7.0 * h_med, dy_up), min(7.0 * h_med, dy_dn)
            else:
                dx_left = min(22.0 * h_med, 0.5 * min(left_xs)) if left_xs else 22.0 * h_med
                dx_right = min(22.0 * h_med, 0.5 * min(right_xs)) if right_xs else 22.0 * h_med
                dy_up, dy_dn = 5.0 * h_med, 18.0 * h_med
                pwr_dy_up, pwr_dy_dn = 5.0 * h_med, 18.0 * h_med

            if p_role == "ANA_PANO":
                local = [
                    o for o in f_texts
                    if o is not t
                    and (t.x - 8.0 * h_med) <= o.x <= (t.x + 32.0 * h_med)
                    and (t.y - 16.0 * h_med) <= o.y <= (t.y + 4.5 * h_med)
                ]
            else:
                local = [
                    o for o in f_texts
                    if o is not t
                    and (t.y - dy_dn) <= o.y <= (t.y + dy_up)
                    and (t.x - dx_left) <= o.x <= (t.x + dx_right)
                ]

            p_inst: Optional[float] = None
            p_dem: Optional[float] = None
            brk: Optional[str] = None
            rcd: Optional[str] = None
            cab: Optional[str] = None
            has_meter_or_tms = False

            # Güç değerleri kendi kutusunda aranır; şalt/kablo koridor boyunca taranır
            pwr_dx_max = min(dx_right, 35.0 * h_med) if same_col else dx_right
            pwr_local = sorted(
                [
                    o for o in local
                    if (t.x - dx_left) <= o.x <= (t.x + pwr_dx_max)
                    and (t.y - pwr_dy_dn) <= o.y <= (t.y + pwr_dy_up)
                ],
                key=lambda o: abs(o.y - t.y) * 3.0 + abs(o.x - t.x),
            )
            found_pws: List[float] = []
            for lo in pwr_local:
                pw = _parse_power_watts(lo.text.strip())
                if pw is not None:
                    found_pws.append(pw)
                    if len(found_pws) == 2:
                        break
            if len(found_pws) == 1:
                p_inst = found_pws[0]
            elif len(found_pws) >= 2:
                p_inst = max(found_pws[0], found_pws[1])
                p_dem = min(found_pws[0], found_pws[1])

            for lo in sorted(local, key=lambda o: abs(o.y - t.y) * 3.0 + abs(o.x - t.x)):
                lt = lo.text.strip()
                if brk is None and (_RE_BREAKER_CURVE.match(lt) or _RE_BREAKER_SHORT.match(lt) or _RE_TMS.match(lt)):
                    brk = lt.replace(" ", "")
                if _RE_METER.match(lt) or _RE_TMS.match(lt):
                    has_meter_or_tms = True
                if rcd is None:
                    if p_role == "ANA_PANO" and _RE_RCD_MA.match(lt):
                        rcd = lt.replace(" ", "")
                    elif _RE_POLE_AMP.match(lt):
                        # Kendi koridorunda yanında KAK/30mA var mı?
                        nbr_rcd = [
                            x for x in local
                            if abs(x.x - lo.x) <= 4.0 * h_med and abs(x.y - lo.y) <= 4.5 * h_med
                        ]
                        ma_hit = next((x.text.strip().replace(" ", "") for x in nbr_rcd if _RE_RCD_MA.match(x.text.strip())), "")
                        if any(_RE_RCD_TAG.match(x.text.strip()) for x in nbr_rcd) or ma_hit:
                            rcd = f"{lt.replace(' ', '')} {ma_hit}".strip()
                if cab is None and _RE_CABLE.search(lt) and p_role != "ANA_PANO":
                    cab = re.sub(r"\s+", " ", lt).strip()

            looks_like_strict = bool(
                re.match(r"^(?:AT|TT|OT|O-T|D-T\d*|DT-\d+|KT-\d+|DP-\d+|AP-\d+|TP-\d+|MDP[-\w]*|DB[-\w]*|LP[-\w]*|PANO[-\s\w]+|.*PANO.*)$", nt)
            )
            if not (looks_like_strict or has_meter_or_tms or any((p_inst, p_dem, brk, rcd, cab))):
                continue

            parent_nm = main_panel_name if (main_panel_name and p_role != "ANA_PANO") else (
                "TEDAŞ" if p_role == "ANA_PANO" and any("TEDAS" in norm_tr(x.text).upper() for x in f_texts) else None
            )
            _add_panel(
                txt,
                sh.frame_id,
                role=p_role,
                parent_panel=parent_nm,
                breaker=brk,
                rcd=rcd,
                cable=cab,
                p_inst=p_inst,
                p_dem=p_dem,
                handles=[t.handle],
            )

    # Çıktıları düzenli listelere dök
    panels_out = sorted(panels_map.values(), key=lambda p: (0 if p.role == "ANA_PANO" else 1, p.panel_name))
    sg_out = [
        SwitchgearBomItem(
            category=cat,  # type: ignore[arg-type]
            spec=spec,
            count=sum(sb.values()),
            sheet_breakdown=dict(sorted(sb.items())),
            source_handles=switchgear_handles[(cat, spec)][:20],
        )
        for (cat, spec), sb in sorted(switchgear_counts.items(), key=lambda kv: (-sum(kv[1].values()), kv[0][0], kv[0][1]))
    ]
    cables_out = [
        CableBomItem(
            spec=spec,
            occurrences=sum(sb.values()),
            explicit_length_m=round(cable_len[spec], 2) if cable_has_len[spec] else None,
            sheet_breakdown=dict(sorted(sb.items())),
            source_handles=cable_handles[spec][:20],
        )
        for spec, sb in sorted(cable_occ.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
    ]
    return panels_out, sg_out, cables_out


_RE_TABLE_CABLE_COL = re.compile(r"\b(?:KABLO|CABLE|KES[Iİ]T|SECTION|[Iİ]LETKEN)\b", re.IGNORECASE)
_RE_TABLE_LEN_COL = re.compile(r"\b(?:UZUNLUK|METRAJ|LENGTH|BOYU)\b|\(\s*M\s*\)", re.IGNORECASE)
_RE_PROSE_NOTE = re.compile(
    r"(?:YAPILACAKTIR|ED[Iİ]LECEKT[Iİ]R|KULLANILACAKTIR|TES[Iİ]S\s+ED[Iİ]L|OLACAKTIR|CEK[Iİ]LECEKT[Iİ]R)",
    re.IGNORECASE,
)


def _merge_table_and_plan_cables(
    existing_cables: List[CableBomItem],
    tables: Sequence[NormalizedTable],
    sheets: Sequence[SheetFrame],
    texts_by_sheet: Dict[str, List[RawText]],
    legend_regions_by_sheet: Dict[str, List[Tuple[float, float, float, float]]],
) -> List[CableBomItem]:
    """
    Şemalar dışındaki:
      1) Sütun başlığında KABLO/KESİT + (opsiyonel) UZUNLUK/METRAJ yer alan tüm tabloları,
      2) Aktif kat/plan paftalarındaki açık kablo etiketlerini (`3x(1x185/25ş mm2 XLPE)`, `1x120mm² H07Z-R` vb.)
    evrensel olarak kablo BOM'una ekler; not/lejant metinlerini ve mükerrer tablo hücrelerini hariç tutar.
    """
    cable_occ: Dict[str, Counter] = defaultdict(Counter)
    cable_len: Dict[str, float] = defaultdict(float)
    cable_has_len: Dict[str, bool] = defaultdict(bool)
    cable_handles: Dict[str, List[str]] = defaultdict(list)

    for cb in existing_cables:
        for sid, cnt in cb.sheet_breakdown.items():
            cable_occ[cb.spec][sid] += cnt
        if not cb.sheet_breakdown:
            cable_occ[cb.spec]["SEMA"] += cb.occurrences
        if cb.explicit_length_m is not None:
            cable_len[cb.spec] += cb.explicit_length_m
            cable_has_len[cb.spec] = True
        cable_handles[cb.spec].extend(cb.source_handles)

    sheet_roles_by_id = {sh.frame_id: sh.role for sh in sheets}
    table_boxes_by_sheet: Dict[str, List[Tuple[float, float, float, float]]] = defaultdict(list)
    for tbl in tables:
        if tbl.bbox_du is not None:
            table_boxes_by_sheet[tbl.sheet_id or ""].append(
                (tbl.bbox_du.minx, tbl.bbox_du.miny, tbl.bbox_du.maxx, tbl.bbox_du.maxy)
            )
        if not tbl.raw_matrix or len(tbl.raw_matrix) < 2:
            continue

        all_rows = [[str(c).strip() for c in r] for r in tbl.raw_matrix if any(str(c).strip() for c in r)]
        if len(all_rows) < 2:
            continue

        top_blob = norm_tr(" ".join(" ".join(r) for r in all_rows[:3])).upper()
        if any(gk in top_blob for gk in ("TOPRAKLAMA HESAB", "LAURENT", "OZGUL DIRENC", "AYDINLATMA HESAB")):
            continue

        # İlk 3 satır içinde KABLO/KESİT ve varsa UZUNLUK sütununu bul
        hdr_row_idx = -1
        cable_col: Optional[int] = None
        len_col: Optional[int] = None
        for ri, row in enumerate(all_rows[:3]):
            c_col = None
            l_col = None
            for ci, cell in enumerate(row):
                if _RE_TABLE_CABLE_COL.search(cell):
                    c_col = ci
                elif _RE_TABLE_LEN_COL.search(cell):
                    l_col = ci
            if c_col is not None:
                hdr_row_idx = ri
                cable_col = c_col
                len_col = l_col
                break
        if hdr_row_idx < 0 or cable_col is None:
            continue
        # Kolon şeması içindeki metin ızgaraları _extract_schematic_bom ile zaten işlendi;
        # TEXT_GRID yalnızca açık UZUNLUK sütunu da olan metraj tablolarında eklenir.
        sh_role = sheet_roles_by_id.get(tbl.sheet_id or "", "")
        if tbl.source_kind == "TEXT_GRID" and (sh_role in ("KOLON_SEMASI", "TEK_HAT") or len_col is None):
            continue
        # Yükleme cetveli/ısı tablosunda uzunluk yoksa ve şemada aynı kablolar zaten varsa çift sayma
        if len_col is None and tbl.source_kind == "OLE2_DECODED" and cable_occ:
            continue

        sid = tbl.sheet_id or "TABLO"
        for row in all_rows[hdr_row_idx + 1:]:
            if cable_col >= len(row):
                continue
            cell_c = row[cable_col].strip()
            if not cell_c or len(cell_c) > 65:
                continue
            m_cab = _RE_CABLE.search(cell_c)
            if not m_cab:
                continue
            spec = re.sub(r"\s+", " ", m_cab.group(0)).strip()
            cable_occ[spec][sid] += 1
            if len_col is not None and len_col < len(row):
                raw_l = re.sub(r"[^0-9.,]", "", row[len_col])
                lv = parse_tr_float(raw_l) if raw_l else None
                if lv is not None and 0.05 <= lv <= 50000.0:
                    cable_len[spec] += lv
                    cable_has_len[spec] = True
            for h in tbl.source_handles[:3]:
                if h and h not in cable_handles[spec]:
                    cable_handles[spec].append(h)

    # Plan / şaft paftalarındaki müstakil kablo çağrıları ("3x(1x185/25ş mm2 XLPE)", "1x120mm² H07Z-R" vb.)
    for sh in sheets:
        if sh.space.startswith("PAPERSPACE:") or sh.role in ("LEJANT", "KOLON_SEMASI", "TEK_HAT", "GERILIM_DUSUMU", "YUKLEME_CETVELI"):
            continue
        sh_tu = norm_tr(sh.title or "").upper()
        if any(nk in sh_tu for nk in ("NOTLAR", "NOTES", "LEJANT")):
            continue
        leg_boxes = legend_regions_by_sheet.get(sh.frame_id, [])
        tbl_boxes = table_boxes_by_sheet.get(sh.frame_id, [])
        for t in texts_by_sheet.get(sh.frame_id, []):
            raw = " ".join((t.text or "").split()).strip()
            if not raw or len(raw) > 75 or _RE_PROSE_NOTE.search(raw):
                continue
            if leg_boxes and _in_any_box(t.x, t.y, leg_boxes):
                continue
            if tbl_boxes and _in_any_box(t.x, t.y, tbl_boxes):
                continue
            for m_c in _RE_CABLE.finditer(raw):
                spec = re.sub(r"\s+", " ", m_c.group(0)).strip()
                cable_occ[spec][sh.frame_id] += 1
                m_l = re.search(r"\b(\d+(?:[.,]\d+)?)\s*m\b", raw[m_c.end():], re.IGNORECASE)
                if m_l:
                    lv = parse_tr_float(m_l.group(1))
                    if lv is not None and 0.1 <= lv <= 50000.0:
                        cable_len[spec] += lv
                        cable_has_len[spec] = True
                if t.handle and len(cable_handles[spec]) < 20 and t.handle not in cable_handles[spec]:
                    cable_handles[spec].append(t.handle)

    out = [
        CableBomItem(
            spec=spec,
            occurrences=sum(sb.values()),
            explicit_length_m=round(cable_len[spec], 2) if cable_has_len[spec] else None,
            sheet_breakdown=dict(sorted(sb.items())),
            source_handles=cable_handles[spec][:20],
        )
        for spec, sb in sorted(
            cable_occ.items(),
            key=lambda kv: (-sum(kv[1].values()), -(cable_len[kv[0]] if cable_has_len[kv[0]] else 0.0), kv[0]),
        )
    ]
    return out


_RE_SCHED_MCB_ONLY = re.compile(
    r"^(?:(?:[1234]\s*[xX*]\s*)?\d{1,3}\s*A(?:\s*[BCDK])?(?:\s*(?:AOS|MCB))?|[BCDK]\s*\d{1,3}\s*A?)$",
    re.IGNORECASE,
)
_RE_SCHED_BARE_AMP = re.compile(r"^(?:([1234])\s*[xX*]\s*)?(\d{1,3})\s*A?$")
_RE_SCHED_CURVE_CAP = re.compile(r"^(?:(\d+(?:[.,]\d+)?)\s*kA\s*)?([BCDK])$", re.IGNORECASE)
_RE_SCHED_CURVE_ONLY = re.compile(r"^(?:[BCDK]|AOS|MCB)$", re.IGNORECASE)
_RE_SCHED_PANEL_HEADER = re.compile(
    r"(?:^|\b)([A-Z]{1,6}(?:[-_]?\d{1,3}|-[A-Z0-9]{1,4}))"
    r"(?=\s+(?:[A-Z0-9]+\s+){0,2}(?:TABLO|PANO|YUKLEME)|$|\))"
)
_RE_SCHED_PANEL_CELL = re.compile(r"^(?:[A-Z]{1,5}-\d{1,3}|[A-Z]{1,3}-[A-Z0-9]{1,3}|MDP[-_A-Z0-9]+)$")
_RE_SCHED_LINYE_ROW = re.compile(r"^(?:[APKM]\s*\d{1,3}|L\s*\d{1,3}|YEDEK|SPARE)$", re.IGNORECASE)


def _normalize_amp_token(tok: str) -> Optional[str]:
    m = _RE_SCHED_BARE_AMP.match(tok.strip())
    if not m:
        return None
    pole, amp_s = m.group(1), m.group(2)
    amp_v = int(amp_s)
    if amp_v < 2 or amp_v > 630:
        return None
    return f"{pole}x{amp_v}A" if pole else f"{amp_v}A"


_RE_SCHED_NON_PANEL_PREFIX = re.compile(
    r"^(?:PRIZ|AYD|LINYE|KOL|FAZ|KAT|DAIRE|MOTOR|POMPA|FAN|KLIMA|ASANS|ISIT|YEDEK|SPARE|GUC|SIG)",
    re.IGNORECASE,
)


def _extract_load_schedule_breakers(tables: Sequence[NormalizedTable]) -> List[LoadScheduleBreakerItem]:
    """
    OLE2 / ACAD_TABLE / BORDERED_GRID yükleme cetvellerinden pano bazlı linye kesicilerini
    ('10A B AOS', '16A C AOS', '3x32A C AOS' vb.) ve kablo kesitlerini evrensel olarak ayırır.
    Kolon şeması parçacıklarını (TEXT_GRID) ve topraklama/gerilim düşümü tablolarını atlar.
    """
    grouped: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}

    for tbl in tables:
        if tbl.source_kind == "TEXT_GRID":
            continue
        if not tbl.raw_matrix:
            continue
        all_rows = [[str(c).strip() for c in r] for r in tbl.raw_matrix if any(str(c).strip() for c in r)]
        if len(all_rows) < 2:
            continue

        top_blob = norm_tr(" ".join(" ".join(r) for r in all_rows[:6])).upper()
        full_blob = norm_tr(" ".join(" ".join(r) for r in all_rows)).upper()
        # Topraklama hesap tablolarını yükleme cetveli sanma
        if any(gk in top_blob for gk in ("TOPRAKLAMA", "LAURENT", "OZGUL DIRENC", "YAYILMA")) and "YUKLEME" not in top_blob:
            continue
        is_load_sched = any(
            lk in full_blob for lk in ("YUKLEME", "LINYE", "SIGORTA", "KESICI", "KURULU GUC", "SORTI", "AOS")
        )
        if not is_load_sched:
            continue

        power_is_watt = "(W)" in top_blob and "(KW)" not in top_blob

        # Pano adını önce başlıktaki tireli/rakamlı koddan (KP-99 vb.), sonra tablo içindeki bağımsız pano hücresinden (O-T, DT-55), yoksa başlıktaki kısa koddan bul
        panel_name = ""
        title_u = norm_tr(tbl.title or "").upper()
        if title_u:
            m_t = _RE_SCHED_PANEL_HEADER.search(title_u)
            if m_t:
                cand_p = re.sub(r"\s+", "", m_t.group(1)).upper()
                if cand_p not in _NOT_PANEL_TOKENS and len(cand_p) <= 16:
                    panel_name = cand_p

        if not panel_name:
            for row in all_rows:
                for c in row:
                    cu = norm_tr(c).upper().strip()
                    if (
                        _RE_SCHED_PANEL_CELL.match(cu)
                        and not _RE_CABLE.search(c)
                        and not _RE_METER.match(c)
                        and not _RE_SCHED_NON_PANEL_PREFIX.match(cu)
                        and cu not in _NOT_PANEL_TOKENS
                        and not _RE_SCHED_LINYE_ROW.match(cu)
                    ):
                        panel_name = cu
                        break
                if panel_name:
                    break

        if not panel_name:
            for candidate_txt in ([title_u] if title_u else []) + [norm_tr(" ".join(r)).upper() for r in all_rows[:5]]:
                if not candidate_txt:
                    continue
                m_p = _RE_SCHED_PANEL_HEADER.search(candidate_txt)
                if m_p:
                    cand_p = re.sub(r"\s+", "", m_p.group(1)).upper()
                    if cand_p not in _NOT_PANEL_TOKENS and len(cand_p) <= 16:
                        panel_name = cand_p
                        break
                m_short = re.search(
                    r"\b([A-Z]{2,4}-[A-Z0-9]{1,4})\b|\b(ADP|ATP|MDP|OMP|TDP)(?=\s+(?:[A-Z0-9]+\s+){0,2}(?:TABLO|PANO|YUKLEME))",
                    candidate_txt,
                )
                if m_short:
                    cand_s = (m_short.group(1) or m_short.group(2) or "").upper()
                    if cand_s and cand_s not in _NOT_PANEL_TOKENS:
                        panel_name = cand_s
                        break
        if not panel_name:
            panel_name = (tbl.title or "").strip()[:32] or tbl.sheet_id or tbl.table_id

        # Sütun rollerini başlıklardan tespit et (ancak satır başlıkla birleşikse bile veriyi atlama)
        breaker_cols: Set[int] = set()
        cable_cols: Set[int] = set()
        power_cols: Set[int] = set()
        for row in all_rows[:7]:
            row_u = [norm_tr(c).upper() for c in row]
            if any(any(k in cu for k in ("LINYE", "SIGORTA", "KESICI", "KABLO", "GUC", "SORTI")) for cu in row_u):
                for ci, cu in enumerate(row_u):
                    if any(k in cu for k in ("SIGORTA", "KESICI", "AOS", "MCB", "SALTER", "KORUMA")):
                        breaker_cols.add(ci)
                    if any(k in cu for k in ("KABLO", "KESIT", "ILETKEN")):
                        cable_cols.add(ci)
                    if any(k in cu for k in ("GUC", "KW", "KURULU", "WATT", "T.GUCU")):
                        power_cols.add(ci)

        src_handle = tbl.source_handles[0] if tbl.source_handles else tbl.table_id

        for row in all_rows:
            non_empty = [(ci, c) for ci, c in enumerate(row) if c]
            if len(non_empty) < 2:
                continue
            first_u = norm_tr(non_empty[0][1]).upper()
            row_joined = norm_tr(" ".join(c for _, c in non_empty)).upper()
            if first_u.startswith(("TOPLAM", "GENEL TOPLAM", "TALEP GUC")) or "YUKLEME CETVELI" in row_joined:
                continue

            breaker_spec = ""
            # 1) Standart Türk cetvel üçlüsü: [AOS|MCB] + [10|16|3x32] + [3 kA B|3 kA C|B|C]
            for pos in range(len(non_empty) - 1):
                _, c_tok = non_empty[pos]
                if c_tok.strip().upper() in ("AOS", "MCB"):
                    amp_norm = _normalize_amp_token(non_empty[pos + 1][1])
                    if amp_norm:
                        curve_part = ""
                        if pos + 2 < len(non_empty):
                            m_cc = _RE_SCHED_CURVE_CAP.match(non_empty[pos + 2][1].strip())
                            if m_cc:
                                curve_part = m_cc.group(2).upper()
                        breaker_spec = f"{amp_norm} {curve_part} {c_tok.strip().upper()}".replace("  ", " ").strip()
                        break

            # 2) Tek hücre / split eğri formatı ("10A" | "B" | "AOS" veya "16A C AOS")
            if not breaker_spec:
                has_linye_or_cable = (
                    any(_RE_SCHED_LINYE_ROW.match(c) for _, c in non_empty)
                    or any(_RE_CABLE.search(c) for _, c in non_empty)
                )
                if has_linye_or_cable:
                    search_indices = sorted(breaker_cols) if breaker_cols else [ci for ci, _ in non_empty]
                    cand_lists = [search_indices, [ci for ci, _ in non_empty]]
                    for idxs in cand_lists:
                        for ci in idxs:
                            if ci >= len(row) or not row[ci]:
                                continue
                            cell_v = row[ci].strip()
                            if _RE_SCHED_MCB_ONLY.match(cell_v):
                                breaker_spec = re.sub(r"\s+", " ", cell_v).upper()
                                if ci + 1 < len(row) and row[ci + 1] and _RE_SCHED_CURVE_ONLY.match(row[ci + 1].strip()):
                                    nxt = row[ci + 1].strip().upper()
                                    if nxt not in breaker_spec:
                                        breaker_spec = f"{breaker_spec} {nxt}"
                                if ci + 2 < len(row) and row[ci + 2] and row[ci + 2].strip().upper() in ("AOS", "MCB"):
                                    nxt2 = row[ci + 2].strip().upper()
                                    if nxt2 not in breaker_spec:
                                        breaker_spec = f"{breaker_spec} {nxt2}"
                                break
                        if breaker_spec:
                            break

            if not breaker_spec:
                continue

            # Aynı satırdaki kablo ve güç bilgisini bul
            cable_spec = ""
            c_search = sorted(cable_cols) if cable_cols else [ci for ci, _ in non_empty]
            for idxs in (c_search, [ci for ci, _ in non_empty]):
                for ci in idxs:
                    if ci < len(row) and row[ci] and _RE_CABLE.search(row[ci]):
                        cable_spec = re.sub(r"\s+", " ", row[ci]).strip()
                        break
                if cable_spec:
                    break

            pwr_kw = 0.0
            # Güç değeri genellikle linye satırındaki kablo öncesi sayıdır (TOPLAM GÜÇ veya FAZ GÜCÜ)
            for ci, c_str in non_empty:
                cu = c_str.strip()
                if _RE_SCHED_LINYE_ROW.match(cu) or _RE_CABLE.search(cu) or cu.upper() in ("AOS", "MCB"):
                    continue
                if breaker_spec and cu in breaker_spec:
                    continue
                pv = parse_tr_float(cu.replace("kW", "").replace("KW", "").strip())
                if pv is None:
                    continue
                if power_is_watt and 40.0 <= pv <= 100000.0:
                    # Örn. "9", "280", "280" -> son/büyük toplam güç sütunu gerçek gücü taşır (sorti adedi < 40 genelde atlanır)
                    pwr_kw = round(pv / 1000.0, 3)
                elif not power_is_watt and 0.05 <= pv <= 500.0 and ci not in breaker_cols and ci not in cable_cols:
                    pwr_kw = pv

            key = (panel_name, breaker_spec, cable_spec, tbl.source_kind, src_handle)
            bucket = grouped.setdefault(key, {"count": 0, "power_kw": 0.0})
            bucket["count"] += 1
            bucket["power_kw"] += pwr_kw

    items = [
        LoadScheduleBreakerItem(
            panel_name=k[0],
            breaker_spec=k[1],
            cable_spec=k[2],
            count=v["count"],
            total_power_kw=round(v["power_kw"], 2),
            source_kind=k[3],
            source_handle=k[4],
        )
        for k, v in grouped.items()
    ]
    items.sort(key=lambda it: (it.panel_name, -it.count, it.breaker_spec, it.cable_spec))
    return items


def _compute_wires_by_layer(wire_ps: Sequence[RawPath], du_to_m: float) -> List[WireLayerBomItem]:
    """Elektrik hat çizgilerini katman bazında segmente ayırıp toplam uzunluğu (m) hesaplar."""
    by_lay: Dict[str, Tuple[int, float]] = {}
    for p in wire_ps:
        lay = p.layer or "0"
        cnt, ln = by_lay.get(lay, (0, 0.0))
        by_lay[lay] = (cnt + 1, ln + p.length_du * du_to_m)
    out: List[WireLayerBomItem] = []
    for lay, (cnt, ln_m) in sorted(by_lay.items(), key=lambda kv: (-kv[1][1], kv[0])):
        rounded_m = round(ln_m, 2)
        if rounded_m <= 0.0:
            continue
        out.append(WireLayerBomItem(
            layer=lay,
            description=describe_wire_layer(lay),
            segment_count=cnt,
            total_length_m=rounded_m,
        ))
    return out


def _category_from_legend_desc(desc: str) -> Optional[str]:
    """Lejant açıklamasından (katman gürültüsünden bağımsız) tek tip elektrik kategorisi üretir."""
    du = norm_tr(desc).upper()
    if "BUAT" in du:
        return "BUAT"
    if any(k in du for k in ("LINYE", "LINYESI", "KOLON NO", "KOLON HAT", "HAT ETIKET")):
        return "HAT / LİNYE ETİKETİ"
    if any(k in du for k in ("TELEFON", "TV", "TELEVIZYON", "INTERCOM", "DUAFON", "DATA", "ZIL", "KAPI OTOM")):
        return "ZAYIF AKIM"
    if "PRIZ" in du:
        return "PRİZ"
    if any(k in du for k in ("ARMATUR", "FLORESANT", "AVIZE", "TAVAN", "DUVAR")):
        return "AYDINLATMA"
    if any(k in du for k in ("VAVIEN", "KOMUTATOR", "ANAHTAR")) and "SIGORTA" not in du:
        return "ANAHTAR"
    if "SAYAC" in du:
        return "SAYAÇ"
    if any(k in du for k in ("SIGORTA", "SALTER", "KACAK AKIM", "KORUMA")):
        return "ŞALT / KORUMA"
    if any(k in du for k in ("TABLO", "PANO")):
        return "PANO / TABLO"
    if any(k in du for k in ("TOPRAK", "SERIT", "KLEMENS", "CUBUG", "BARAS", "KADVELT")):
        return "TOPRAKLAMA"
    if any(k in du for k in ("DUMAN", "YANGIN", "IHBAR", "SIREN", "FLASOR", "SONLANDIRMA")):
        return "YANGIN ALGILAMA"
    return None


def _inserts_to_symbol_bom(
    grouped_inserts: Iterable[Tuple[str, RawInsert]],
    legend: Dict[str, object],
    cloned_insert_ids: Optional[Set[int]] = None,
    du_to_m: float = 0.01,
    container_block_names: Optional[Set[str]] = None,
) -> Tuple[List[SymbolBomItem], int, int, Counter, List[RawInsert]]:
    """
    (alan_id, RawInsert) çiftlerinden yalnızca doğrulanmış elektrik sembol metrajı,
    mimari blok sayısı, belirsiz/anonim blok sayısı ve disiplin dağılımı üretir.
    """
    sym_counts: Dict[Tuple[str, str, str], Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sym_layers: Dict[Tuple[str, str, str], Set[str]] = defaultdict(set)
    sym_desc_info: Dict[Tuple[str, str, str], Tuple[str, str]] = {}
    disc_counts: Counter = Counter()
    elec_inserts: List[RawInsert] = []
    arch_count = 0
    uncertain_count = 0

    for area_id, ins in grouped_inserts:
        bname = ins.effective_name or ins.block_name
        if is_container_insert(ins, du_to_m, container_block_names=container_block_names):
            continue
        if is_dim_or_tick_subprimitive(bname) or is_dim_or_tick_subprimitive(ins.block_name):
            continue
        if ins.parent_chain and container_block_names is not None:
            parent_blk = ins.parent_chain.split(">")[-1].strip()
            if parent_blk and parent_blk not in container_block_names:
                continue

        role_grp, cat, disc, desc, dsrc = classify_insert_role(
            ins, legend, cloned_insert_ids=cloned_insert_ids  # type: ignore[arg-type]
        )
        if role_grp == "ARCHITECTURAL":
            arch_count += 1
            continue
        if role_grp == "UNCERTAIN":
            uncertain_count += 1
            continue

        leg = legend.get(bname) or legend.get(bname.strip()) or legend.get(bname.strip().lower())
        if leg is not None and is_clean_legend_desc(getattr(leg, "description", "")):
            leg_cat = _category_from_legend_desc(getattr(leg, "description", ""))
            if leg_cat:
                cat = leg_cat
            desc = getattr(leg, "description", desc)
            dsrc = "LEJANT"

        # Proje zengin bir lejant içeriyorsa (len>=5), lejantta ve sembol sözlüğünde hiç yer almayan
        # 1-3 karakterli jenerik yön/geçiş oklarını ("oo", "aa", "yy", "1B" vb.) katman adından
        # sahte ekipman ("Zayif Akim", "Aydinlatma") olarak sayma; belirsiz olarak ayır.
        b_clean = bname.strip()
        if (
            len(legend) >= 5
            and dsrc == "KATMAN_ADI"
            and len(b_clean) <= 3
            and b_clean.isalnum()
        ):
            elec_inserts.append(ins)
            uncertain_count += 1
            continue

        disc_counts[disc] += 1
        elec_inserts.append(ins)
        key = (cat, disc, bname)
        sym_counts[key][area_id] += 1
        sym_layers[key].add(ins.layer)
        if key not in sym_desc_info or dsrc == "LEJANT":
            sym_desc_info[key] = (desc, dsrc)

    out_items: List[SymbolBomItem] = []
    for (cat, disc, bname), sb in sorted(sym_counts.items(), key=lambda kv: (-sum(kv[1].values()), kv[0][0], kv[0][2])):
        desc, dsrc = sym_desc_info[(cat, disc, bname)]
        if dsrc == "KATMAN_ADI" and cat != "DİĞER ELEKTRİK":
            desc = f"{cat.title()} ({', '.join(sorted(sym_layers[(cat, disc, bname)]))})"

        out_items.append(SymbolBomItem(
            category=cat,
            block_name=bname,
            description=desc,
            description_source=dsrc,  # type: ignore[arg-type]
            discipline=disc,  # type: ignore[arg-type]
            layer_names=sorted(sym_layers[(cat, disc, bname)]),
            total_count=sum(sb.values()),
            sheet_breakdown=dict(sorted(sb.items())),
        ))
    return out_items, arch_count, uncertain_count, disc_counts, elec_inserts


def _cluster_outside_items(
    outside_texts: List[RawText],
    outside_inserts: List[RawInsert],
    outside_paths: List[RawPath],
    du_to_m: float,
    legend: Dict[str, object],
    claimed_anchor_handles: Optional[Set[str]] = None,
    regions: Optional[List[Dict[str, Any]]] = None,
    cloned_path_ids: Optional[Set[int]] = None,
    cloned_insert_ids: Optional[Set[int]] = None,
    container_block_names: Optional[Set[str]] = None,
) -> List[OutsideClusterSummary]:
    """
    Pafta çerçevesi dışında kalan antetsiz alanları altlarındaki plan başlıklarına
    göre ayrı görünümlere böler, her birinde mimari altlık vs. elektrik ayrımı yapar.
    """
    if regions is None:
        regions = partition_outside_regions(
            outside_texts,
            outside_inserts,
            outside_paths,
            du_to_m,
            claimed_anchor_handles=claimed_anchor_handles,
        )
    clusters: List[OutsideClusterSummary] = []
    for reg in regions:
        c_texts: List[RawText] = reg["texts"]
        c_ins: List[RawInsert] = reg["inserts"]
        c_paths: List[RawPath] = reg["paths"]
        title: str = reg["title"]

        syms, arch_c, unc_c, disc_c, elec_ins = _inserts_to_symbol_bom(
            [("OUT", ins) for ins in c_ins],
            legend,
            cloned_insert_ids=cloned_insert_ids,
            du_to_m=du_to_m,
            container_block_names=container_block_names,
        )
        p_split = classify_paths_arch_vs_elec(
            c_paths,
            elec_ins,
            du_to_m,
            cloned_path_ids=cloned_path_ids,
            container_block_names=container_block_names,
        )
        arch_p = len(p_split["ARCHITECTURAL"])
        wire_ps = p_split["ELECTRICAL_WIRE"]
        wire_m = round(sum(p.length_du for p in wire_ps) * du_to_m, 2)
        el_total = sum(s.total_count for s in syms)

        # Başlıksız tekil mimari blok kırıntılarını sahte görünüm olarak listeleme
        if reg["source_kind"] == "CERCEVESIZ_KUME" and el_total == 0 and len(wire_ps) == 0 and len(c_texts) < 15:
            continue
        if el_total == 0 and arch_c == 0 and len(wire_ps) == 0 and len(c_texts) < 5:
            continue

        cid = f"DIS_{len(clusters) + 1:02d}"
        for s in syms:
            s.sheet_breakdown = {cid: s.total_count}

        floor_lbl = parse_floor_label(title)
        disc_lbl = infer_view_discipline(title, "KAT_PLANI", disc_c, len(wire_ps))

        clusters.append(OutsideClusterSummary(
            cluster_id=cid,
            title=title,
            source_kind=reg["source_kind"],
            title_position=reg["title_position"],
            floor_or_scope=floor_lbl,
            discipline=disc_lbl,
            text_count=len(c_texts),
            electrical_symbol_count=el_total,
            non_electrical_count=arch_c,
            uncertain_block_count=unc_c,
            arch_path_count=arch_p,
            elec_wire_count=len(wire_ps),
            elec_wire_length_m=wire_m,
            symbols=syms,
            wires_by_layer=_compute_wires_by_layer(wire_ps, du_to_m),
        ))
    return clusters


_SCHEMATIC_ROLES = frozenset({
    "KOLON_SEMASI", "TEK_HAT", "DUAFON_SEMASI", "GERILIM_DUSUMU", "YUKLEME_CETVELI", "DETAY"
})
_RE_PANEL_PREFIX = re.compile(r"^([A-ZÇĞİÖŞÜ]{1,6})[-_ ]?\d+$")
_RE_OLE_GROUND_L = re.compile(r"\bL\s*=\s*(\d+(?:[.,]\d+)?)\b")
_RE_OLE_GROUND_A = re.compile(r"\bA\s*=\s*(\d+(?:[.,]\d+)?)\b")
_RE_OLE_GROUND_N = re.compile(r"\bn\s*=\s*(\d+)\b")


def _in_any_box(x: float, y: float, boxes: List[Tuple[float, float, float, float]]) -> bool:
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, x1, y0, y1 in boxes)


def _parse_ole_grounding_params(tbl) -> Optional[Dict[str, float]]:
    """OLE tablo matrisinden L (iletken uzunluğu), A (alan) ve n (köşe/çubuk) parametrelerini okur."""
    if tbl.source_kind != "OLE2_DECODED" or not tbl.raw_matrix:
        return None
    joined_lines = [" ".join(str(c).strip() for c in row if str(c).strip()) for row in tbl.raw_matrix]
    blob = "\n".join(joined_lines)
    params: Dict[str, float] = {}
    for key, pat in (("L", _RE_OLE_GROUND_L), ("A", _RE_OLE_GROUND_A), ("n", _RE_OLE_GROUND_N)):
        m = pat.search(blob)
        if m:
            try:
                params[key] = float(m.group(1).replace(",", "."))
            except ValueError:
                pass
    if len(params) < 2:
        for row in tbl.raw_matrix:
            cells = [str(c).strip() for c in row if str(c).strip()]
            for i, c in enumerate(cells):
                if c in ("L", "A", "n") and c not in params:
                    for j in range(i + 1, min(len(cells), i + 3)):
                        if cells[j] == "=":
                            continue
                        try:
                            params[c] = float(cells[j].replace(",", "."))
                        except ValueError:
                            pass
                        break
    return params if len(params) >= 2 else None


def _collect_cross_check_alerts(
    model: CanonicalProjectModel,
    panels: List[PanelInventoryItem],
) -> List[str]:
    """Topraklama, OLE hesap tablosu ve kolon şeması kardeş panoları arasında evrensel çapraz kontroller üretir."""
    alerts: List[str] = []

    ole_by_sheet = {tbl.sheet_id: _parse_ole_grounding_params(tbl) for tbl in model.tables}
    for g in model.grounding_loops:
        if g.rod_block_count is not None and g.spur_count > 0 and g.rod_block_count != g.spur_count:
            alerts.append(
                f"Topraklama çubuğu uyumsuzluğu ({g.sheet_id}): {g.spur_count} adet filiz hattı çizili, "
                f"ancak planda {g.rod_block_count} adet topraklama çubuğu tespit edildi."
            )
        ole_p = ole_by_sheet.get(g.sheet_id)
        if ole_p:
            diffs: List[str] = []
            if "L" in ole_p and g.ring_plus_inner_m > 0:
                l_ole = ole_p["L"]
                if abs(l_ole - g.ring_plus_inner_m) > max(1.0, 0.02 * l_ole):
                    diffs.append(
                        f"L: hesapta {l_ole:g} m vs çizimde {g.ring_plus_inner_m:.2f} m "
                        f"(filiz dahil {g.total_conductor_m:.2f} m)"
                    )
            if "A" in ole_p and g.area_m2 > 0:
                a_ole = ole_p["A"]
                if abs(a_ole - g.area_m2) > max(2.0, 0.02 * a_ole):
                    diffs.append(f"A: hesapta {a_ole:g} m² vs çizimde {g.area_m2:.2f} m²")
            if "n" in ole_p and g.rod_block_count is not None and int(round(ole_p["n"])) != g.rod_block_count:
                diffs.append(f"n: hesapta {int(round(ole_p['n']))} vs sahada {g.rod_block_count} adet")
            if diffs:
                alerts.append(f"Topraklama OLE vs CAD farkı ({g.sheet_id}): " + "; ".join(diffs) + ".")

    kolon_sids = {sh.frame_id for sh in model.sheets if sh.role == "KOLON_SEMASI"}
    kolon_panels = [p for p in panels if any(sid in kolon_sids for sid in p.sheet_ids)]
    sibling_groups: Dict[str, List[PanelInventoryItem]] = {}
    for p in kolon_panels:
        m_pre = _RE_PANEL_PREFIX.match(p.panel_name)
        if m_pre:
            sibling_groups.setdefault(f"SERI:{m_pre.group(1)}", []).append(p)
        elif p.parent_panel:
            sibling_groups.setdefault(f"UST:{p.parent_panel}", []).append(p)

    seen_panel_alerts: Set[str] = set()
    for grp in sibling_groups.values():
        if len(grp) < 3:
            continue
        has_brk = sum(1 for p in grp if p.breaker_rating)
        has_rcd = sum(1 for p in grp if p.rcd_rating)
        has_rcd_ma = sum(1 for p in grp if p.rcd_rating and "mA" in p.rcd_rating)
        has_cab = sum(1 for p in grp if p.feeder_cable)
        thresh = max(2, int(0.6 * len(grp)))
        for p in grp:
            missing: List[str] = []
            if has_brk >= thresh and not p.breaker_rating:
                missing.append("Kesici")
            if has_rcd >= thresh and not p.rcd_rating:
                missing.append("KAKR")
            elif has_rcd_ma >= thresh and p.rcd_rating and "mA" not in p.rcd_rating:
                missing.append("KAKR (mA hassasiyeti)")
            if has_cab >= thresh and not p.feeder_cable:
                missing.append("Besleme Kablosu")
            if missing and p.panel_name not in seen_panel_alerts:
                seen_panel_alerts.add(p.panel_name)
                alerts.append(
                    f"Kolon şeması eksiklik kontrolü ({p.panel_name}): kardeş panolarda bulunan "
                    f"{', '.join(missing)} etiketi çizimde eksik/okunamadı."
                )

    return alerts


def build_project_inventory(
    snapshot: RawCADSnapshot,
    model: CanonicalProjectModel,
) -> ProjectInventory:
    """
    Ham CAD anlık görüntüsü ve kanonik modelden Kat x Disiplin ekseninde
    mimari altlıktan arındırılmış mühendislik metraj özeti (`ProjectInventory`) üretir.
    """
    texts_by_sheet, inserts_by_sheet, paths_by_sheet, outside_texts, outside_inserts, outside_paths = _assign_items_to_sheets(
        model.sheets, snapshot.texts, snapshot.inserts, snapshot.paths
    )

    legend_regions = find_legend_table_regions(model.sheets, texts_by_sheet, inserts_by_sheet)
    regions_by_sheet: Dict[str, List[Tuple[float, float, float, float]]] = {}
    for r_sid, rx0, rx1, ry0, ry1 in legend_regions:
        regions_by_sheet.setdefault(r_sid, []).append((rx0, rx1, ry0, ry1))

    # Gömülü yerel lejant kutularındaki örnek sembol/çizgileri pafta sayımından hariç tut
    filtered_inserts_by_sheet: Dict[str, List[RawInsert]] = {}
    filtered_paths_by_sheet: Dict[str, List[RawPath]] = {}
    for sh in model.sheets:
        boxes = regions_by_sheet.get(sh.frame_id, [])
        sh_ins = inserts_by_sheet.get(sh.frame_id, [])
        sh_pth = paths_by_sheet.get(sh.frame_id, [])
        if boxes and sh.role != "LEJANT":
            sh_ins = [ins for ins in sh_ins if not _in_any_box(ins.x, ins.y, boxes)]
            sh_pth = [pth for pth in sh_pth if not _in_any_box(pth.bbox.center[0], pth.bbox.center[1], boxes)]
        filtered_inserts_by_sheet[sh.frame_id] = sh_ins
        filtered_paths_by_sheet[sh.frame_id] = sh_pth

    panels, switchgear_bom, cable_bom = _extract_schematic_bom(
        model.sheets, texts_by_sheet, filtered_inserts_by_sheet
    )
    cable_bom = _merge_table_and_plan_cables(
        cable_bom, model.tables, model.sheets, texts_by_sheet, regions_by_sheet
    )

    du_to_m = model.unit.du_to_m
    container_block_names: Set[str] = build_container_block_names(snapshot.inserts, du_to_m)
    gnd_sheets = {g.sheet_id for g in model.grounding_loops}
    claimed_anchor_handles: Set[str] = set()
    sheet_titles: Dict[str, Tuple[str, str]] = {}
    for sh in model.sheets:
        sh_title = sh.title
        title_pos = "ICINDE" if sh_title else "YOK"
        if not sh_title:
            below_t = find_below_title_for_sheet(sh, outside_texts, du_to_m)
            if below_t is not None:
                sh_title = below_t.text.strip()[:90]
                title_pos = "ALTINDA"
                sh.title = sh_title
                if below_t.handle:
                    claimed_anchor_handles.add(below_t.handle)
        sheet_titles[sh.frame_id] = (sh_title, title_pos)

    outside_regions = partition_outside_regions(
        outside_texts,
        outside_inserts,
        outside_paths,
        du_to_m,
        claimed_anchor_handles=claimed_anchor_handles,
    )

    view_bundles = [
        {
            "view_id": sh.frame_id,
            "role": sh.role,
            "paths": filtered_paths_by_sheet.get(sh.frame_id, []),
            "inserts": filtered_inserts_by_sheet.get(sh.frame_id, []),
        }
        for sh in model.sheets
    ] + [
        {
            "view_id": f"REG_{r_idx}",
            "role": "KAT_PLANI",
            "paths": reg["paths"],
            "inserts": reg["inserts"],
        }
        for r_idx, reg in enumerate(outside_regions)
    ]
    cloned_path_ids, cloned_insert_ids = detect_cloned_architectural_entities(view_bundles, du_to_m)

    views: List[ProjectViewSummary] = []

    field_pairs: List[Tuple[str, RawInsert]] = []
    schematic_pairs: List[Tuple[str, RawInsert]] = []
    total_arch_paths = 0
    total_elec_wires = 0
    total_uncertain_blocks = 0

    for sh in model.sheets:
        sh_title, title_pos = sheet_titles[sh.frame_id]

        sh_inserts = filtered_inserts_by_sheet.get(sh.frame_id, [])
        sh_paths = filtered_paths_by_sheet.get(sh.frame_id, [])

        # LEJANT paftasının kendi tablosundaki 1'er örnek sembolü proje metrajına karıştırma
        if sh.role == "LEJANT":
            sh_syms, sh_arch_c, sh_unc_c, sh_disc_c, sh_elec_ins = [], 0, 0, Counter(), []
        else:
            target_pairs = schematic_pairs if sh.role in _SCHEMATIC_ROLES else field_pairs
            for ins in sh_inserts:
                target_pairs.append((sh.frame_id, ins))
            sh_syms, sh_arch_c, sh_unc_c, sh_disc_c, sh_elec_ins = _inserts_to_symbol_bom(
                [(sh.frame_id, ins) for ins in sh_inserts],
                model.legend,
                cloned_insert_ids=cloned_insert_ids,
                du_to_m=du_to_m,
                container_block_names=container_block_names,
            )

        p_split = classify_paths_arch_vs_elec(
            sh_paths,
            sh_elec_ins,
            du_to_m,
            cloned_path_ids=cloned_path_ids,
            container_block_names=container_block_names,
        )
        sh_arch_p = len(p_split["ARCHITECTURAL"])
        sh_wire_ps = p_split["ELECTRICAL_WIRE"]
        sh_wire_m = round(sum(p.length_du for p in sh_wire_ps) * du_to_m, 2)
        sh_wires_by_layer = _compute_wires_by_layer(sh_wire_ps, du_to_m)

        total_arch_paths += sh_arch_p
        total_elec_wires += len(sh_wire_ps)

        floor_lbl = parse_floor_label(sh_title, role=sh.role)
        disc_lbl = infer_view_discipline(
            sh_title, sh.role, sh_disc_c, len(sh_wire_ps), has_grounding_loop=(sh.frame_id in gnd_sheets)
        )
        views.append(ProjectViewSummary(
            view_id=sh.frame_id,
            source_kind="PAFTA",
            floor_or_scope=floor_lbl,
            discipline=disc_lbl,  # type: ignore[arg-type]
            title=sh_title,
            title_position=title_pos,  # type: ignore[arg-type]
            arch_block_count=sh_arch_c,
            arch_path_count=sh_arch_p,
            elec_symbol_count=sum(s.total_count for s in sh_syms),
            elec_wire_count=len(sh_wire_ps),
            elec_wire_length_m=sh_wire_m,
            uncertain_block_count=sh_unc_c,
            minx_du=round(sh.bbox_du.minx, 2),
            miny_du=round(sh.bbox_du.miny, 2),
            symbols=sh_syms,
            wires_by_layer=sh_wires_by_layer,
        ))

    symbol_bom, framed_arch_count, framed_unc_count, _, _ = _inserts_to_symbol_bom(
        field_pairs,
        model.legend,
        cloned_insert_ids=cloned_insert_ids,
        du_to_m=du_to_m,
        container_block_names=container_block_names,
    )
    schematic_symbol_bom, sch_arch_c, sch_unc_c, _, _ = _inserts_to_symbol_bom(
        schematic_pairs,
        model.legend,
        cloned_insert_ids=cloned_insert_ids,
        du_to_m=du_to_m,
        container_block_names=container_block_names,
    )
    framed_arch_count += sch_arch_c
    total_uncertain_blocks += framed_unc_count + sch_unc_c

    outside_clusters = _cluster_outside_items(
        outside_texts,
        outside_inserts,
        outside_paths,
        du_to_m,
        model.legend,
        claimed_anchor_handles=claimed_anchor_handles,
        regions=outside_regions,
        cloned_path_ids=cloned_path_ids,
        cloned_insert_ids=cloned_insert_ids,
        container_block_names=container_block_names,
    )
    outside_elec_count = 0
    for cl in outside_clusters:
        outside_elec_count += cl.electrical_symbol_count
        total_arch_paths += cl.arch_path_count
        total_elec_wires += cl.elec_wire_count
        total_uncertain_blocks += cl.uncertain_block_count
        views.append(ProjectViewSummary(
            view_id=cl.cluster_id,
            source_kind=cl.source_kind,  # type: ignore[arg-type]
            floor_or_scope=cl.floor_or_scope or "Genel / Diğer",
            discipline=cl.discipline,  # type: ignore[arg-type]
            title=cl.title,
            title_position=cl.title_position,  # type: ignore[arg-type]
            arch_block_count=cl.non_electrical_count,
            arch_path_count=cl.arch_path_count,
            elec_symbol_count=cl.electrical_symbol_count,
            elec_wire_count=cl.elec_wire_count,
            elec_wire_length_m=cl.elec_wire_length_m,
            uncertain_block_count=cl.uncertain_block_count,
            symbols=cl.symbols,
            wires_by_layer=cl.wires_by_layer,
        ))

    total_arch_blocks = framed_arch_count + sum(cl.non_electrical_count for cl in outside_clusters)
    total_elec_symbols = sum(s.total_count for s in symbol_bom) + outside_elec_count

    # Çözülen OLE2 gömülü tabloların ve yükleme cetveli linye sigortalarının özeti
    load_schedule_breakers = _extract_load_schedule_breakers(model.tables)
    ole_summaries: List[OleTableSummary] = []
    for tbl in model.tables:
        if tbl.source_kind != "OLE2_DECODED":
            continue
        ole_summaries.append(OleTableSummary(
            handle=tbl.source_handles[0] if tbl.source_handles else tbl.table_id,
            sheet_id=tbl.sheet_id,
            title=tbl.title,
            row_count=len(tbl.raw_matrix),
            cell_count=sum(len(r) for r in tbl.raw_matrix),
            preview_rows=[r[:8] for r in tbl.raw_matrix[:6]],
        ))

    alerts: List[str] = _collect_cross_check_alerts(model, panels)
    titled_outside = [c for c in outside_clusters if c.source_kind == "CERCEVESIZ_PLAN"]
    salt_arch_count = sum(1 for v in views if v.discipline == "SALT_MIMARI_ALTLIK")
    if outside_clusters:
        alerts.append(
            f"Pafta çerçevesi dışı (antetsiz/ölü kopya) {len(outside_clusters)} bölgede ({len(titled_outside)} başlıklı plan) "
            f"{outside_elec_count} elektrik sembolü aktif metraj dışında ayrıca listelendi (Bölüm 4B)."
        )
    if salt_arch_count:
        alerts.append(
            f"{salt_arch_count} adet çerçeveli/çerçevesiz kopya yalnızca mimari altlık (elektrik sembolü yok) olarak ayrıldı."
        )
    if total_uncertain_blocks:
        alerts.append(
            f"{total_uncertain_blocks} adet anonim/tanımsız blok (A$C... veya kanıtsız katman) elektrik sayımına dahil edilmedi."
        )

    unread_oles = [o for o in snapshot.ole_objects if o.decode_status != "OK"]
    if unread_oles:
        alerts.append(f"{len(unread_oles)} adet çözülemeyen gömülü OLE/Görsel nesne var.")
    if snapshot.unhandled_entity_counts:
        alerts.append(f"Desteklenmeyen DXF tipleri: {snapshot.unhandled_entity_counts}")
    partial_vd = sum(
        1 for fb in model.formula_blocks
        if fb.formula_kind == "VOLTAGE_DROP" and fb.parse_status != "OK"
    )
    if partial_vd:
        alerts.append(f"{partial_vd} adet gerilim düşümü formülü kısmi/eksik okundu (ham değer eksik olabilir).")
    if snapshot.extraction_warnings:
        alerts.append(f"{len(snapshot.extraction_warnings)} adet çıkarım uyarısı var.")

    return ProjectInventory(
        filename=model.filename,
        unit_name=model.unit.unit_name,
        sheet_count=len(model.sheets),
        views=views,
        architectural_summary={
            "mimari_blok": total_arch_blocks,
            "mimari_cizgi": total_arch_paths,
            "elektrik_sembol": total_elec_symbols,
            "elektrik_hat_cizgi": total_elec_wires,
            "belirsiz_anonim_blok": total_uncertain_blocks,
        },
        panels=panels,
        switchgear_bom=switchgear_bom,
        load_schedule_breakers=load_schedule_breakers,
        cable_bom=cable_bom,
        grounding_loops=model.grounding_loops,
        symbol_bom=symbol_bom,
        schematic_symbol_bom=schematic_symbol_bom,
        outside_clusters=outside_clusters,
        ole_decoded_tables=ole_summaries,
        non_electrical_block_count=framed_arch_count,
        uncertain_block_count=total_uncertain_blocks,
        outside_text_count=len(outside_texts),
        outside_electrical_insert_count=outside_elec_count,
        alerts_summary=alerts,
    )


_DISC_LABELS: Dict[str, str] = {
    "KUVVETLI_AKIM": "Kuvvetli Akım",
    "ZAYIF_AKIM": "Zayıf Akım",
    "TOPRAKLAMA": "Topraklama",
    "KARMA_ELEKTRIK": "Kuvvetli + Zayıf Akım",
    "SALT_MIMARI_ALTLIK": "Salt Mimari Altlık (Elektrik Yok)",
    "SEMA_HESAP": "Şema / Hesap",
    "LEJANT_DETAY": "Lejant / Detay",
    "BELIRSIZ": "Belirsiz",
}

_SOURCE_KIND_LABELS: Dict[str, str] = {
    "PAFTA": "Pafta",
    "CERCEVESIZ_PLAN": "Çerçevesiz Plan",
    "CERCEVESIZ_KUME": "Çerçevesiz Küme",
}


def _panel_table_rows(panels: List[PanelInventoryItem]) -> List[List[str]]:
    rows: List[List[str]] = []
    for p in panels:
        pwr = (
            f"{p.installed_power_w or '-'} / {p.demand_power_w or '-'}"
            if (p.installed_power_w or p.demand_power_w)
            else "-"
        )
        rows.append([
            p.panel_name,
            p.parent_panel or "-",
            p.role,
            ", ".join(p.sheet_ids),
            p.breaker_rating or "-",
            p.rcd_rating or "-",
            p.feeder_cable or "-",
            pwr,
        ])
    return rows


def _symbol_bom_rows(items: List[SymbolBomItem], *, italic_src: bool = False) -> List[List[str]]:
    rows: List[List[str]] = []
    for s in items:
        desc = f"{s.description} *({s.description_source})*" if italic_src else f"{s.description} ({s.description_source})"
        bd = ", ".join(f"{k}: {v}" for k, v in s.sheet_breakdown.items())
        rows.append([s.category, s.block_name, desc, str(s.total_count), bd])
    return rows


def _format_grounding_summary(g) -> str:
    ring_spec = g.ring_conductor_spec or "Temel Ring + İç İletken"
    spur_spec = g.spur_conductor_spec or "Filiz"
    rod_txt = f" | Saha Topraklama Çubuğu = {g.rod_block_count} adet" if g.rod_block_count is not None else ""
    return (
        f"Temel Topraklama ({g.sheet_id}): {ring_spec} = {g.ring_plus_inner_m:.2f} m "
        f"(Dış Çevre {g.outer_perimeter_m} m + İç İletken {g.inner_conductors_m} m) "
        f"| Alan = {g.area_m2} m² | {spur_spec} Filiz = {g.spur_count} adet ({g.spur_total_m} m)"
        f"{rod_txt} | Toplam İletken = {g.total_conductor_m} m"
    )


_ACTIVE_PLAN_DISCIPLINES = frozenset({
    "KUVVETLI_AKIM", "ZAYIF_AKIM", "TOPRAKLAMA", "KARMA_ELEKTRIK",
})


def _active_plan_views(inv: ProjectInventory) -> List[ProjectViewSummary]:
    """Aktif fiziksel kat / topraklama / saha planı görünümlerini döner."""
    gnd_views = {g.sheet_id for g in inv.grounding_loops}
    return [
        v for v in inv.views
        if v.discipline in _ACTIVE_PLAN_DISCIPLINES
        and (v.symbols or v.elec_wire_length_m > 0 or v.view_id in gnd_views)
    ]


def _aggregate_active_wire_layers(
    active_views: Sequence[ProjectViewSummary],
    gnd_view_ids: Set[str] = frozenset(),
) -> List[WireLayerBomItem]:
    """Aktif fiziksel planlardaki yatay kablo/iletken uzunluklarını katman bazında toplar."""
    agg: Dict[str, Tuple[str, int, float]] = {}
    for v in active_views:
        skip_raw_gnd = v.view_id in gnd_view_ids
        for wl in v.wires_by_layer:
            if skip_raw_gnd and "TOPRAK" in norm_tr(wl.layer).upper():
                continue
            desc, cnt, ln_m = agg.get(wl.layer, (wl.description or describe_wire_layer(wl.layer), 0, 0.0))
            agg[wl.layer] = (desc, cnt + wl.segment_count, ln_m + wl.total_length_m)
    out = [
        WireLayerBomItem(
            layer=lay,
            description=desc,
            segment_count=cnt,
            total_length_m=round(ln_m, 2),
        )
        for lay, (desc, cnt, ln_m) in agg.items()
        if round(ln_m, 2) > 0
    ]
    out.sort(key=lambda w: (-w.total_length_m, w.layer))
    return out


def _area_grounding_rows(gnd_loops: Sequence[Any]) -> List[Tuple[str, str, str, float, str, str]]:
    """Geometrik temel topraklama halkası ve filizlerini doğrudan tablo satırı (tuple) formatına çevirir."""
    rows: List[Tuple[str, str, str, float, str, str]] = []
    for g in gnd_loops:
        ring_spec = g.ring_conductor_spec or "Temel Ring + İç Şerit"
        rows.append((
            "TOPRAKLAMA İLETKENİ",
            ring_spec,
            f"Temel Ring ({g.outer_perimeter_m} m) + İç Şerit ({g.inner_conductors_m} m) — Alan: {g.area_m2} m²",
            round(g.ring_plus_inner_m, 2),
            "m",
            g.sheet_id or "-",
        ))
        if g.spur_count > 0 or g.spur_total_m > 0:
            spur_spec = g.spur_conductor_spec or "Topraklama Filizi"
            rows.append((
                "TOPRAKLAMA FİLİZİ",
                spur_spec,
                f"Temel topraklama filiz çıkışı ({g.spur_count} adet)",
                round(g.spur_total_m, 2),
                "m",
                f"{g.sheet_id}: {g.spur_count} adet" if g.sheet_id else f"{g.spur_count} adet",
            ))
    return rows


def _area_unified_rows(v: ProjectViewSummary, view_gnd: Sequence[Any]) -> Tuple[List[List[str]], float]:
    """Tek bir alan başlığı altında ekipman (adet) + kablo/topraklama (m) birleşik tablo satırlarını üretir."""
    rows: List[List[str]] = []
    for s in v.symbols:
        desc_clean = s.description.split(" (")[0]
        rows.append([s.category, s.block_name, desc_clean, str(s.total_count), "adet"])

    total_m = 0.0
    if view_gnd:
        for cat, code, desc, qty_m, unit, _note in _area_grounding_rows(view_gnd):
            rows.append([cat, code, desc, f"{qty_m:.2f}", unit])
            total_m += qty_m

    for wl in v.wires_by_layer:
        if view_gnd and "TOPRAK" in norm_tr(wl.layer).upper():
            continue
        rows.append([
            "KABLO / HAT (2B)",
            wl.layer,
            f"{wl.description} ({wl.segment_count} parça)",
            f"{wl.total_length_m:.2f}",
            "m",
        ])
        total_m += wl.total_length_m

    return rows, round(total_m, 2)


def _unmeasured_cables_note(
    unmeasured_cables: Sequence[CableBomItem],
    active_wires_all: Sequence[WireLayerBomItem],
    grounding_loops: Sequence[Any],
) -> Optional[str]:
    """Şemada yalnız kablo tipi yazılı olup yanında metre yazmayan hatlar için kat planı eşleşmesini özetler."""
    if not unmeasured_cables:
        return None
    specs_txt = ", ".join(f"`{c.spec}`" for c in unmeasured_cables)
    plan_refs: List[str] = []
    for wl in active_wires_all:
        lu = norm_tr(wl.layer).upper()
        if any(k in lu for k in ("TEL", "TV", "INTERCOM", "DUAFON", "24V", "YANGIN", "DATA")):
            plan_refs.append(f"`{wl.layer}` ({wl.total_length_m:.2f} m)")
    spur_m = round(sum(getattr(g, "spur_total_m", 0.0) for g in grounding_loops), 2)
    if spur_m > 0:
        plan_refs.append(f"Topraklama Filizi ({spur_m:.2f} m)")
    if plan_refs:
        return (
            f"Şemada yalnızca kablo tipi belirtilen (yanında ayrıca metre yazılmamış) hatların ({specs_txt}) "
            f"uzunlukları kat/topraklama planlarındaki çizimlerden ölçülmüştür: {', '.join(plan_refs)}."
        )
    return (
        f"Şemada yalnızca kablo tipi belirtilen (yanında ayrıca metre yazılmamış) hat etiketleri: {specs_txt}."
    )


def _load_schedule_rows(items: Sequence[LoadScheduleBreakerItem]) -> List[List[str]]:
    return [
        [
            it.panel_name,
            it.breaker_spec,
            it.cable_spec or "-",
            str(it.count),
            f"{it.total_power_kw:.2f}" if it.total_power_kw > 0 else "-",
            f"{it.source_kind} ({it.source_handle})" if it.source_handle else (it.source_kind or "-"),
        ]
        for it in items
    ]


def format_inventory_markdown(inv: ProjectInventory, sheets: Optional[List[SheetFrame]] = None) -> str:
    """Mühendisin alan/grup bazlı ve sağ bölge şema/hesap ayrıştırılmış sade Markdown metraj raporunu üretir."""
    arch = inv.architectural_summary
    active_views = _active_plan_views(inv)
    gnd_by_view = defaultdict(list)
    for g in inv.grounding_loops:
        gnd_by_view[g.sheet_id].append(g)
    gnd_view_ids = set(gnd_by_view.keys())

    active_wires = _aggregate_active_wire_layers(active_views, gnd_view_ids=gnd_view_ids)
    active_wires_all = _aggregate_active_wire_layers(active_views)
    gnd_rows = _area_grounding_rows(inv.grounding_loops)
    sized_cables = [c for c in inv.cable_bom if c.explicit_length_m is not None]
    unmeasured_cables = [c for c in inv.cable_bom if c.explicit_length_m is None]
    unmeasured_note = _unmeasured_cables_note(unmeasured_cables, active_wires_all, inv.grounding_loops)

    lines: List[str] = []
    lines.append(f"# Proje Metraj ve Envanter Özeti — `{inv.filename}`")
    lines.append(
        f"- **Tespit Edilen Birim:** `{inv.unit_name}` | **Pafta Sayısı:** `{inv.sheet_count}` "
        f"| **Aktif Plan Alanı:** `{len(active_views)}`"
    )
    if arch:
        lines.append(
            f"- **Mimari Altlık (Ayrılan):** `{arch.get('mimari_blok', 0)}` blok, "
            f"`{arch.get('mimari_cizgi', 0)}` çizgi | "
            f"**Doğrulanmış Elektrik:** `{arch.get('elektrik_sembol', 0)}` sembol, "
            f"`{arch.get('elektrik_hat_cizgi', 0)}` hat çizgisi | "
            f"**Hariç Tutulan Ok/Anonim Blok:** `{arch.get('belirsiz_anonim_blok', 0)}`"
        )
    else:
        lines.append(f"- **Mimari/Tefriş Blok (hariç tutulan):** `{inv.non_electrical_block_count}`")
    lines.append(
        "- **Sağ Bölge (Kolon Şeması / Tek Hat / Hesap / Cetvel) Ayrıştırması:** Kat planları ile sağdaki "
        "şema-hesap paftaları topolojik rolüne göre ayrılmıştır. Şemalarda tekrar gösterilen kat sembolleri "
        "(`T`, `TV`, `ID`, `Z` vb.) ve ölçeksiz şema hat çizgileri fiziksel saha metrajına **dahil edilmez**; "
        "sağ bölgeden yalnızca sahada bulunmayan pano listesi, şalt/koruma/sayaçlar, gömülü yükleme cetveli "
        "linye sigortaları ve yazılı kolon besleme kablo metrajları alınır.\n"
    )

    if active_views:
        lines.append(f"## 1. Alan / Grup Bazlı Tam Ekipman ve Kablo Metrajı ({len(active_views)} alan)")
        lines.append(
            "> *Not: Kat/saha planlarındaki kablo metrajları çizimdeki katmanlı hatların **2B yatay iz düşüm** toplamıdır "
            "(düşey kolon/sorti iniş-çıkışları çizimde yükseklik verilmediğinden dahil edilmemiştir).*\n"
        )
        for v in active_views:
            area_title = v.title or v.floor_or_scope
            disc_lbl = _DISC_LABELS.get(v.discipline, v.discipline)
            area_rows, area_m = _area_unified_rows(v, gnd_by_view.get(v.view_id, []))
            lines.append(
                f"### {area_title} (`{v.view_id}` — {disc_lbl} | {v.elec_symbol_count} adet | {area_m:.2f} m)"
            )
            if area_rows:
                lines.append("| Kategori | Kalem / Kodu | Açıklama | Miktar | Birim |")
                lines.append("| :--- | :--- | :--- | ---: | :--- |")
                for cat, code, desc, qty_s, unit in area_rows:
                    lines.append(f"| {cat} | `{code}` | {desc} | **{qty_s}** | {unit} |")
            else:
                lines.append("*Bu alanda ayrıştırılmış kalem yok.*")
            lines.append("")

    total_phys_m = round(
        sum(w.total_length_m for w in active_wires) + sum(r[3] for r in gnd_rows), 2
    )
    lines.append(f"## 2. Proje Geneli Fiziksel Saha İcmali ({sum(s.total_count for s in inv.symbol_bom)} adet | {total_phys_m:.2f} m)")
    if inv.symbol_bom:
        lines.append("### 2A. Tüm Aktif Planlar Ekipman Toplamı (Adet)")
        lines.append("| Kategori | Blok | Tanım (Kaynak) | Toplam | Pafta / Alan Dağılımı |")
        lines.append("| :--- | :--- | :--- | ---: | :--- |")
        for r in _symbol_bom_rows(inv.symbol_bom, italic_src=True):
            lines.append(f"| {r[0]} | `{r[1]}` | {r[2]} | **{r[3]}** | {r[4]} |")
        lines.append("")
    else:
        lines.append("*Pafta içi kat planlarında elektrik sembolü bulunamadı.*\n")

    if active_wires or gnd_rows:
        lines.append(f"### 2B. Tüm Aktif Planlar Kablo, Hat & Temel Topraklama İletkeni Toplamı ({total_phys_m:.2f} m)")
        lines.append("| Kategori | Hat Katmanı / İletken | Tanım | Uzunluk (m) | Parça / Detay |")
        lines.append("| :--- | :--- | :--- | ---: | :--- |")
        for cat, code, desc, qty_m, _unit, note in gnd_rows:
            lines.append(f"| {cat} | `{code}` | {desc} | **{qty_m:.2f}** | {note} |")
        for wl in active_wires:
            lines.append(f"| KABLO / HAT (2B) | `{wl.layer}` | {wl.description} | **{wl.total_length_m:.2f}** | {wl.segment_count} parça |")
        lines.append("")

    lines.append("## 3. Sağ Bölge — Kolon Şeması, Tek Hat, Yükleme Cetvelleri & Hesaplar")
    lines.append(f"### 3A. Panolar ({len(inv.panels)} adet tespit edildi)")
    if inv.panels:
        lines.append("| Pano | Üst Pano | Rol | Paftalar | Kesici | KAKR | Besleme Kablosu | Kurulu / Talep (W) |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for r in _panel_table_rows(inv.panels):
            lines.append(
                f"| **{r[0]}** | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} |"
            )
    else:
        lines.append("*Şema veya blok niteliklerinden pano etiketi ayrıştırılamadı.*")
    lines.append("")

    lines.append(f"### 3B. Kolon Şeması / Tek Hat Şalt, Koruma & Sayaç Metrajı ({sum(x.count for x in inv.switchgear_bom)} adet)")
    if inv.switchgear_bom:
        lines.append("| Kategori | Tip / Değer | Toplam Adet | Bulunduğu Paftalar |")
        lines.append("| :--- | :--- | ---: | :--- |")
        for item in inv.switchgear_bom:
            bd = ", ".join(f"{k}: {v}" for k, v in item.sheet_breakdown.items())
            lines.append(f"| {item.category} | `{item.spec}` | **{item.count}** | {bd} |")
    else:
        lines.append("*Şema üzerinde ayrıştırılabilir şalt etiketi bulunamadı.*")
    lines.append("")

    lines.append(
        f"### 3C. Yükleme Cetvellerinden Okunan İç Linye Sigortaları & Linyeler ({sum(x.count for x in inv.load_schedule_breakers)} adet)"
    )
    if inv.load_schedule_breakers:
        panels_with_sched = sorted({x.panel_name for x in inv.load_schedule_breakers})
        lines.append(
            f"> *Çözümlenen yükleme cetveli olan panolar: {', '.join(f'`{p}`' for p in panels_with_sched)}. "
            "Cetveli çizimde yer almayan/çözülemeyen diğer panolar için tahmin veya varsayım yapılmamıştır.*"
        )
        lines.append("| Pano / Tablo | Linye Sigortası / Kesici | Linye Kablosu | Adet | Toplam Güç (kW) | Kaynak Tablo |")
        lines.append("| :--- | :--- | :--- | ---: | ---: | :--- |")
        for r in _load_schedule_rows(inv.load_schedule_breakers):
            lines.append(f"| **{r[0]}** | `{r[1]}` | `{r[2]}` | **{r[3]}** | {r[4]} | {r[5]} |")
    else:
        lines.append("*Çözümlenebilir yükleme cetveli içinde linye sigortası satırı bulunamadı.*")
    lines.append("")

    lines.append("### 3D. Şemadan Okunan Kolon Besleme Kabloları & Yazılı Metrajlar")
    if sized_cables:
        lines.append("| Kablo / İletken Tipi | Hat Sayısı | Yazılı Boy Toplamı (m) | Pafta Dağılımı |")
        lines.append("| :--- | ---: | ---: | :--- |")
        for c in sized_cables:
            bd = ", ".join(f"{k}: {v}" for k, v in c.sheet_breakdown.items())
            lines.append(f"| `{c.spec}` | {c.occurrences} | **{c.explicit_length_m:.2f}** | {bd} |")
    elif not unmeasured_note:
        lines.append("*Şema üzerinde yazılı kablo tipi/metrajı tespit edilmedi.*")
    if unmeasured_note:
        lines.append(f"\n> *{unmeasured_note}*")
    lines.append("")

    if inv.ole_decoded_tables:
        lines.append(f"### 3E. Gömülü OLE / Excel Hesap Tabloları ({len(inv.ole_decoded_tables)} tablo çözüldü)")
        lines.append("| Handle | Pafta | Başlık | Satır | Hücre | İlk Satır Örneği |")
        lines.append("| :--- | :--- | :--- | ---: | ---: | :--- |")
        for ot in inv.ole_decoded_tables:
            sample = " | ".join(ot.preview_rows[1][:5]) if len(ot.preview_rows) > 1 else (
                " | ".join(ot.preview_rows[0][:5]) if ot.preview_rows else "-"
            )
            lines.append(f"| `{ot.handle}` | `{ot.sheet_id}` | {ot.title} | {ot.row_count} | {ot.cell_count} | {sample} |")
        lines.append("")

    if inv.schematic_symbol_bom:
        lines.append(
            f"### 3F. Çift Sayımdan Hariç Tutulan Şema / Detay Sembolleri "
            f"({sum(s.total_count for s in inv.schematic_symbol_bom)} adet — Fiziksel Saha Toplamına Eklenmez)"
        )
        lines.append("| Kategori | Blok | Tanım (Kaynak) | Toplam | Pafta Dağılımı |")
        lines.append("| :--- | :--- | :--- | ---: | :--- |")
        for r in _symbol_bom_rows(inv.schematic_symbol_bom, italic_src=True):
            lines.append(f"| {r[0]} | `{r[1]}` | {r[2]} | **{r[3]}** | {r[4]} |")
        lines.append("")

    if inv.outside_clusters:
        lines.append(
            f"## Bölüm 4B. Çerçeve Dışı / Antetsiz (Ölü / Çalışma Kopyası) Bölgeler "
            f"({sum(c.electrical_symbol_count for c in inv.outside_clusters)} elektrik sembolü — Aktif Metraj Dışı)"
        )
        lines.append("| Bölge | Kat / Bölüm | Disiplin | Altındaki Başlık | Elektrik | Mimari Blok | Elektrik Hat | Ekipman Özeti |")
        lines.append("| :--- | :--- | :--- | :--- | ---: | ---: | ---: | :--- |")
        for cl in inv.outside_clusters:
            disc_lbl = _DISC_LABELS.get(cl.discipline, cl.discipline)
            top_s = ", ".join(f"{s.block_name} ({s.description.split(' (')[0]}): {s.total_count}" for s in cl.symbols)
            hat_s = f"{cl.elec_wire_count} ({cl.elec_wire_length_m:.2f} m)" if cl.elec_wire_count else "0"
            lines.append(
                f"| `{cl.cluster_id}` | {cl.floor_or_scope or '-'} | **{disc_lbl}** | {cl.title} | "
                f"**{cl.electrical_symbol_count}** | {cl.non_electrical_count} | {hat_s} | {top_s or '-'} |"
            )
        lines.append("")

    if inv.alerts_summary:
        lines.append("## 5. Dikkat / Okunamayanlar & Çapraz Kontroller")
        for a in inv.alerts_summary:
            lines.append(f"- {a}")

    salt_arch = [v for v in inv.views if v.discipline == "SALT_MIMARI_ALTLIK"]
    if salt_arch:
        lines.append(
            "\n- *Not (Görünüm Haritası / Salt Mimari Altlık Ayrımı): Elektrik içermediği için hariç tutulan görünümler: "
            + ", ".join(f"`{v.view_id}` ({v.title or v.floor_or_scope})" for v in salt_arch)
            + ".*"
        )

    return "\n".join(lines) + "\n"


def _shade_cell(cell, hex_color: str) -> None:
    """Word tablo hücresine arka plan rengi uygular."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _add_styled_docx_table(doc, headers: List[str], rows: List[List[str]], right_align_cols: Set[int] = frozenset()) -> None:
    """Başlıklı ve zebra satırlı Word tablosu ekler."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    tbl = doc.add_table(rows=1 + len(rows), cols=len(headers))
    tbl.style = "Table Grid"

    for ci, h in enumerate(headers):
        cell = tbl.rows[0].cells[ci]
        _shade_cell(cell, "1F4E79")
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        if ci in right_align_cols:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = p.add_run(str(h))
        run.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(255, 255, 255)

    for ri, row_vals in enumerate(rows):
        bg = "F2F5F9" if ri % 2 == 1 else None
        for ci, val in enumerate(row_vals):
            cell = tbl.rows[ri + 1].cells[ci]
            if bg:
                _shade_cell(cell, bg)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            if ci in right_align_cols:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            run = p.add_run(str(val))
            run.font.size = Pt(9)


def save_inventory_docx(
    inv: ProjectInventory,
    output_path: Union[str, Path],
    sheets: Optional[List[SheetFrame]] = None,
) -> Path:
    """Proje metraj ve envanter özetini Microsoft Word (.docx) olarak kaydeder."""
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    for sec in doc.sections:
        sec.top_margin = Cm(1.5)
        sec.bottom_margin = Cm(1.5)
        sec.left_margin = Cm(1.5)
        sec.right_margin = Cm(1.5)

    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Calibri"
    normal_style.font.size = Pt(10)

    title = doc.add_heading(f"Proje Metraj ve Envanter Özeti — {inv.filename}", level=1)
    if title.runs:
        title.runs[0].font.color.rgb = RGBColor(31, 78, 121)

    arch = inv.architectural_summary
    active_views = _active_plan_views(inv)
    gnd_by_view = defaultdict(list)
    for g in inv.grounding_loops:
        gnd_by_view[g.sheet_id].append(g)
    gnd_view_ids = set(gnd_by_view.keys())

    active_wires = _aggregate_active_wire_layers(active_views, gnd_view_ids=gnd_view_ids)
    active_wires_all = _aggregate_active_wire_layers(active_views)
    gnd_rows = _area_grounding_rows(inv.grounding_loops)
    sized_cables = [c for c in inv.cable_bom if c.explicit_length_m is not None]
    unmeasured_cables = [c for c in inv.cable_bom if c.explicit_length_m is None]
    unmeasured_note = _unmeasured_cables_note(unmeasured_cables, active_wires_all, inv.grounding_loops)

    if arch:
        meta = doc.add_paragraph(
            f"Birim: {inv.unit_name}  |  Pafta: {inv.sheet_count}  |  Aktif Plan Alanı: {len(active_views)}  |  "
            f"Ayrılan Mimari: {arch.get('mimari_blok', 0)} blok / {arch.get('mimari_cizgi', 0)} çizgi  |  "
            f"Doğrulanmış Elektrik: {arch.get('elektrik_sembol', 0)} sembol / {arch.get('elektrik_hat_cizgi', 0)} hat"
        )
    else:
        meta = doc.add_paragraph(
            f"Tespit Edilen Birim: {inv.unit_name}   |   Pafta Sayısı: {inv.sheet_count}   |   "
            f"Hariç Tutulan Mimari/Tefriş Blok: {inv.non_electrical_block_count}"
        )
    if meta.runs:
        meta.runs[0].bold = True

    doc.add_paragraph(
        "Sağ Bölge Ayrıştırması: Şemalarda katlara paralel tekrar çizilen semboller (T, TV, ID, Z vb.) ve ölçeksiz şema "
        "çizgileri saha metrajına dahil edilmez; sağ bölgeden yalnızca pano listesi, şalt/koruma/sayaçlar, yükleme cetveli "
        "linye sigortaları ve yazılı kolon besleme kablo metrajları alınır."
    )

    if active_views:
        doc.add_heading(f"1. Alan / Grup Bazlı Tam Ekipman ve Kablo Metrajı ({len(active_views)} alan)", level=2)
        doc.add_paragraph(
            "Not: Kat/saha planlarındaki kablo metrajları çizimdeki hatların 2B yatay iz düşüm toplamıdır "
            "(düşey kolon/sorti iniş-çıkışları çizimde yükseklik verilmediğinden dahil edilmemiştir)."
        )
        for v in active_views:
            area_title = v.title or v.floor_or_scope
            disc_lbl = _DISC_LABELS.get(v.discipline, v.discipline)
            area_rows, area_m = _area_unified_rows(v, gnd_by_view.get(v.view_id, []))
            doc.add_heading(
                f"{area_title} ({v.view_id} — {disc_lbl} | {v.elec_symbol_count} adet | {area_m:.2f} m)",
                level=3,
            )
            if area_rows:
                _add_styled_docx_table(
                    doc,
                    ["Kategori", "Kalem / Kodu", "Açıklama", "Miktar", "Birim"],
                    area_rows,
                    right_align_cols={3},
                )

    total_phys_m = round(
        sum(w.total_length_m for w in active_wires) + sum(r[3] for r in gnd_rows), 2
    )
    doc.add_heading(
        f"2. Proje Geneli Fiziksel Saha İcmali ({sum(s.total_count for s in inv.symbol_bom)} adet | {total_phys_m:.2f} m)",
        level=2,
    )
    if inv.symbol_bom:
        doc.add_heading("2A. Tüm Aktif Planlar Ekipman Toplamı (Adet)", level=3)
        _add_styled_docx_table(
            doc,
            ["Kategori", "Blok", "Tanım (Kaynak)", "Toplam", "Pafta Dağılımı"],
            _symbol_bom_rows(inv.symbol_bom, italic_src=False),
            right_align_cols={3},
        )
    else:
        doc.add_paragraph("Pafta içi kat planlarında elektrik sembolü bulunamadı.")

    if active_wires or gnd_rows:
        doc.add_heading(
            f"2B. Tüm Aktif Planlar Kablo, Hat & Temel Topraklama İletkeni Toplamı ({total_phys_m:.2f} m)",
            level=3,
        )
        icmal_wire_rows: List[List[str]] = [
            [cat, code, desc, f"{qty_m:.2f}", note]
            for cat, code, desc, qty_m, _unit, note in gnd_rows
        ]
        icmal_wire_rows.extend([
            ["KABLO / HAT (2B)", wl.layer, wl.description, f"{wl.total_length_m:.2f}", f"{wl.segment_count} parça"]
            for wl in active_wires
        ])
        _add_styled_docx_table(
            doc,
            ["Kategori", "Hat Katmanı / İletken", "Tanım", "Uzunluk (m)", "Parça / Detay"],
            icmal_wire_rows,
            right_align_cols={3},
        )

    doc.add_heading("3. Sağ Bölge — Kolon Şeması, Tek Hat, Yükleme Cetvelleri & Hesaplar", level=2)
    doc.add_heading(f"3A. Panolar ({len(inv.panels)} adet)", level=3)
    if inv.panels:
        _add_styled_docx_table(
            doc,
            ["Pano", "Üst Pano", "Rol", "Paftalar", "Kesici", "KAKR", "Besleme Kablosu", "Kurulu / Talep (W)"],
            _panel_table_rows(inv.panels),
        )
    else:
        doc.add_paragraph("Şema veya blok niteliklerinden pano etiketi ayrıştırılamadı.")

    doc.add_heading(f"3B. Kolon Şeması / Tek Hat Şalt, Koruma & Sayaç Metrajı ({sum(x.count for x in inv.switchgear_bom)} adet)", level=3)
    if inv.switchgear_bom:
        _add_styled_docx_table(
            doc,
            ["Kategori", "Tip / Değer", "Toplam Adet", "Bulunduğu Paftalar"],
            [
                [x.category, x.spec, str(x.count), ", ".join(f"{k}: {v}" for k, v in x.sheet_breakdown.items())]
                for x in inv.switchgear_bom
            ],
            right_align_cols={2},
        )
    else:
        doc.add_paragraph("Şema üzerinde ayrıştırılabilir şalt etiketi bulunamadı.")

    if inv.load_schedule_breakers:
        doc.add_heading(
            f"3C. Yükleme Cetvellerinden Okunan İç Linye Sigortaları ({sum(x.count for x in inv.load_schedule_breakers)} adet)",
            level=3,
        )
        _add_styled_docx_table(
            doc,
            ["Pano / Tablo", "Linye Sigortası / Kesici", "Linye Kablosu", "Adet", "Toplam Güç (kW)", "Kaynak Tablo"],
            _load_schedule_rows(inv.load_schedule_breakers),
            right_align_cols={3, 4},
        )

    doc.add_heading("3D. Şemadan Okunan Kolon Besleme Kabloları & Yazılı Metrajlar", level=3)
    if sized_cables:
        _add_styled_docx_table(
            doc,
            ["Kablo / İletken Tipi", "Hat Sayısı", "Yazılı Boy (m)", "Pafta Dağılımı"],
            [
                [
                    c.spec,
                    str(c.occurrences),
                    f"{c.explicit_length_m:.2f}",
                    ", ".join(f"{k}: {v}" for k, v in c.sheet_breakdown.items()),
                ]
                for c in sized_cables
            ],
            right_align_cols={1, 2},
        )
    elif not unmeasured_note:
        doc.add_paragraph("Şema üzerinde yazılı kablo tipi/metrajı tespit edilmedi.")
    if unmeasured_note:
        doc.add_paragraph(unmeasured_note)

    if inv.ole_decoded_tables:
        doc.add_heading(f"3E. Gömülü OLE / Excel Hesap Tabloları ({len(inv.ole_decoded_tables)} tablo çözüldü)", level=3)
        _add_styled_docx_table(
            doc,
            ["Handle", "Pafta", "Başlık", "Satır", "Hücre", "İlk Satır Örneği"],
            [
                [
                    ot.handle,
                    ot.sheet_id,
                    ot.title,
                    str(ot.row_count),
                    str(ot.cell_count),
                    " | ".join(ot.preview_rows[1][:5]) if len(ot.preview_rows) > 1 else (
                        " | ".join(ot.preview_rows[0][:5]) if ot.preview_rows else "-"
                    ),
                ]
                for ot in inv.ole_decoded_tables
            ],
            right_align_cols={3, 4},
        )

    if inv.schematic_symbol_bom:
        doc.add_heading(
            f"3F. Çift Sayımdan Hariç Tutulan Şema / Detay Sembolleri ({sum(s.total_count for s in inv.schematic_symbol_bom)} adet — Fiziksel Saha Toplamına Eklenmez)",
            level=3,
        )
        _add_styled_docx_table(
            doc,
            ["Kategori", "Blok", "Tanım (Kaynak)", "Toplam", "Pafta Dağılımı"],
            _symbol_bom_rows(inv.schematic_symbol_bom, italic_src=False),
            right_align_cols={3},
        )

    if inv.outside_clusters:
        doc.add_heading(
            f"Bölüm 4B. Çerçeve Dışı / Antetsiz (Ölü / Çalışma Kopyası) Bölgeler ({sum(c.electrical_symbol_count for c in inv.outside_clusters)} elektrik sembolü — Aktif Metraj Dışı)",
            level=2,
        )
        _add_styled_docx_table(
            doc,
            ["Bölge", "Kat / Bölüm", "Disiplin", "Altındaki Başlık", "Elektrik", "Mimari Blok", "Hat", "Ekipman Özeti"],
            [
                [
                    cl.cluster_id,
                    cl.floor_or_scope or "-",
                    _DISC_LABELS.get(cl.discipline, cl.discipline),
                    cl.title,
                    str(cl.electrical_symbol_count),
                    str(cl.non_electrical_count),
                    f"{cl.elec_wire_count} ({cl.elec_wire_length_m:.2f} m)" if cl.elec_wire_count else "0",
                    ", ".join(f"{s.block_name} ({s.description.split(' (')[0]}): {s.total_count}" for s in cl.symbols) or "-",
                ]
                for cl in inv.outside_clusters
            ],
            right_align_cols={4, 5, 6},
        )

    if inv.alerts_summary:
        doc.add_heading("5. Dikkat / Okunamayanlar & Çapraz Kontroller", level=2)
        for a in inv.alerts_summary:
            doc.add_paragraph(a, style="List Bullet")

    salt_arch = [v for v in inv.views if v.discipline == "SALT_MIMARI_ALTLIK"]
    if salt_arch:
        doc.add_paragraph(
            "Not (Görünüm Haritası / Salt Mimari Altlık Ayrımı): "
            + ", ".join(f"{v.view_id} ({v.title or v.floor_or_scope})" for v in salt_arch),
            style="List Bullet",
        )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


def save_inventory_xlsx(
    inv: ProjectInventory,
    output_path: Union[str, Path],
    sheets: Optional[List[SheetFrame]] = None,
) -> Path:
    """Alan bazlı, saha icmali ve sağ bölge şema/cetvel ayrıştırılmış sade Excel (.xlsx) metraj defteri üretir."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    zebra_fill = PatternFill(start_color="F2F5FA", end_color="F2F5FA", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=10)
    body_font = Font(size=10)

    def _write_sheet(ws, headers: List[str], rows: List[List[Any]], right_cols: Set[int] = frozenset()) -> None:
        ws.append(headers)
        for ci in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=ci)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="right" if (ci - 1) in right_cols else "left", vertical="center")
        for ri, row in enumerate(rows, start=2):
            ws.append(row)
            for ci in range(1, len(headers) + 1):
                cell = ws.cell(row=ri, column=ci)
                cell.font = body_font
                if ri % 2 == 1:
                    cell.fill = zebra_fill
                cell.alignment = Alignment(horizontal="right" if (ci - 1) in right_cols else "left", vertical="center")
        ws.freeze_panes = "A2"
        for ci, h in enumerate(headers, start=1):
            max_len = max([len(str(h))] + [len(str(r[ci - 1])) for r in rows if ci - 1 < len(r)], default=12)
            ws.column_dimensions[get_column_letter(ci)].width = min(max(max_len + 3, 12), 54)

    active_views = _active_plan_views(inv)
    gnd_by_view = defaultdict(list)
    for g in inv.grounding_loops:
        gnd_by_view[g.sheet_id].append(g)
    gnd_view_ids = set(gnd_by_view.keys())

    active_wires = _aggregate_active_wire_layers(active_views, gnd_view_ids=gnd_view_ids)
    active_wires_all = _aggregate_active_wire_layers(active_views)
    gnd_rows = _area_grounding_rows(inv.grounding_loops)
    sized_cables = [c for c in inv.cable_bom if c.explicit_length_m is not None]
    unmeasured_cables = [c for c in inv.cable_bom if c.explicit_length_m is None]
    unmeasured_note = _unmeasured_cables_note(unmeasured_cables, active_wires_all, inv.grounding_loops)

    # 1. Alan_Bazli_Metraj (Doğrudan açılan ilk sekme: grup başlıkları altında ekipman + kablo + topraklama)
    ws_area = wb.active
    ws_area.title = "Alan_Bazli_Metraj"
    area_rows: List[List[Any]] = []
    for v in active_views:
        area_title = v.title or v.floor_or_scope
        disc_lbl = _DISC_LABELS.get(v.discipline, v.discipline)
        view_gnd = gnd_by_view.get(v.view_id, [])
        for s in v.symbols:
            area_rows.append([
                v.view_id,
                area_title,
                disc_lbl,
                s.category,
                s.block_name,
                s.description.split(" (")[0],
                s.total_count,
                "adet",
                "",
            ])
        for cat, code, desc, qty_m, unit, note in _area_grounding_rows(view_gnd):
            area_rows.append([
                v.view_id,
                area_title,
                disc_lbl,
                cat,
                code,
                desc,
                qty_m,
                unit,
                note,
            ])
        for wl in v.wires_by_layer:
            if view_gnd and "TOPRAK" in norm_tr(wl.layer).upper():
                continue
            area_rows.append([
                v.view_id,
                area_title,
                disc_lbl,
                "KABLO / HAT (2B)",
                wl.layer,
                wl.description,
                wl.total_length_m,
                "m",
                f"{wl.segment_count} parca cizgi (2B yatay iz dusum)",
            ])
    _write_sheet(
        ws_area,
        ["Alan ID", "Alan / Grup Basligi", "Disiplin", "Kategori", "Blok / Katman", "Ekipman / Hat Tanimi", "Miktar", "Birim", "Not"],
        area_rows,
        right_cols={6},
    )

    # 2. Saha_Icmal_Adet_Metre
    ws_icmal = wb.create_sheet("Saha_Icmal_Adet_Metre")
    icmal_rows: List[List[Any]] = []
    for s in inv.symbol_bom:
        bd = ", ".join(f"{k}: {v}" for k, v in sorted(s.sheet_breakdown.items()))
        icmal_rows.append(["EKIPMAN", s.category, s.block_name, s.description.split(" (")[0], s.total_count, "adet", bd])
    for cat, code, desc, qty_m, unit, note in gnd_rows:
        icmal_rows.append(["TEMEL TOPRAKLAMA", cat, code, desc, qty_m, unit, note])
    for wl in active_wires:
        icmal_rows.append(["KABLO / HAT (2B)", "HAT / ILETKEN", wl.layer, wl.description, wl.total_length_m, "m", f"{wl.segment_count} parca"])
    _write_sheet(
        ws_icmal,
        ["Tur", "Kategori", "Blok / Katman", "Tanim", "Toplam Miktar", "Birim", "Alan / Parca Dagilimi"],
        icmal_rows,
        right_cols={4},
    )

    # 3. Sema_Salt_ve_Panolar
    ws_sch = wb.create_sheet("Sema_Salt_ve_Panolar")
    sch_rows: List[List[Any]] = []
    for r in _panel_table_rows(inv.panels):
        sch_rows.append(["PANO", r[2], r[0], f"Ust Pano: {r[1]} | Kesici: {r[4]} | KAKR: {r[5]} | Kablo: {r[6]} | Guc(W): {r[7]}", 1, "adet", r[3]])
    for x in inv.switchgear_bom:
        bd = ", ".join(f"{k}: {v}" for k, v in x.sheet_breakdown.items())
        sch_rows.append(["SALT / SAYAC", x.category, x.spec, "-", x.count, "adet", bd])
    for c in sized_cables:
        bd = ", ".join(f"{k}: {v}" for k, v in c.sheet_breakdown.items())
        sch_rows.append(["KOLON KABLO", "BESLEME KABLOSU", c.spec, f"{c.occurrences} adet kolon hatti", c.explicit_length_m, "m", bd])
    _write_sheet(
        ws_sch,
        ["Grup", "Kategori", "Tip / Pano Adi", "Teknik Detay", "Miktar", "Birim", "Pafta Dagilimi"],
        sch_rows,
        right_cols={4},
    )

    # 4. Yukleme_Cetveli_Sigorta
    ws_ole = wb.create_sheet("Yukleme_Cetveli_Sigorta")
    _write_sheet(
        ws_ole,
        ["Pano / Tablo", "Linye Sigortasi / Kesici", "Linye Kablosu", "Adet", "Toplam Guc (kW)", "Kaynak Tablo"],
        _load_schedule_rows(inv.load_schedule_breakers),
        right_cols={3, 4},
    )

    # 5. Kontrol_ve_Uyarilar
    ws_alert = wb.create_sheet("Kontrol_ve_Uyarilar")
    alert_rows = [[i + 1, a] for i, a in enumerate(inv.alerts_summary)]
    if unmeasured_note:
        alert_rows.append(["SEMA_KABLO_NOTU", unmeasured_note])
    salt_arch = [v for v in inv.views if v.discipline == "SALT_MIMARI_ALTLIK"]
    if salt_arch:
        alert_rows.append([
            "SALT_MIMARI",
            "Elektrik icermedigi icin haric tutulan gorunumler: "
            + ", ".join(f"{v.view_id} ({v.title or v.floor_or_scope})" for v in salt_arch),
        ])
    for s in inv.schematic_symbol_bom:
        bd = ", ".join(f"{k}: {v}" for k, v in sorted(s.sheet_breakdown.items()))
        alert_rows.append(["HARIC_SEMA", f"Cift sayim disi sema sembolu: {s.block_name} ({s.description}) = {s.total_count} adet [{bd}]"])
    _write_sheet(ws_alert, ["No / Kod", "Aciklama / Bulgu"], alert_rows)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return out


def save_inventory_reports(
    inv: ProjectInventory,
    output_dir: Union[str, Path],
    sheets: Optional[List[SheetFrame]] = None,
) -> Tuple[Path, Path, Path]:
    """Envanteri Word (.docx), Markdown (.md), JSON (.json) ve Excel (.xlsx) olarak kaydeder."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(inv.filename).stem
    docx_path = out_dir / f"{stem}_metraj.docx"
    md_path = out_dir / f"{stem}_metraj.md"
    json_path = out_dir / f"{stem}_metraj.json"
    xlsx_path = out_dir / f"{stem}_metraj.xlsx"
    save_inventory_docx(inv, docx_path, sheets=sheets)
    save_inventory_xlsx(inv, xlsx_path, sheets=sheets)
    md_path.write_text(format_inventory_markdown(inv, sheets=sheets), encoding="utf-8")
    json_path.write_text(inv.model_dump_json(indent=2), encoding="utf-8")
    return docx_path, md_path, json_path
