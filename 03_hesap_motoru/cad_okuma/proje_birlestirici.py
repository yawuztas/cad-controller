# -*- coding: utf-8 -*-
"""
Evrensel Çok-Dosyalı Proje / Metro İstasyon Birleştirici (`proje_birlestirici.py`)
===================================================================================
Tek dosya (`bina`) yerine onlarca paftaya bölünmüş klasör tabanlı projelerde
(Metro istasyonları, büyük endüstriyel/hastane kampüsleri):
  1. Alt klasörlerdeki tüm DWG/DXF paftalarını (kopya/yedekleri eleyerek) okur,
  2. PaperSpace ve ModelSpace antet bilgilerini çıkarıp proje/istasyon adı
     tutarlılığını denetler,
  3. Topraklama ringleri, VLD/MEB/EEB, ray izolasyonu (EN 50122), kablo tavası
     etiketleri, FE180/PH120/LSZH kablolar, N-1 trafo/UPS ve şema graflarını tek
     bir `MultiProjectAuditReport` altında birleştirir,
  4. `RuleEngine` YAML profili + `pandapower` + `momepy` + `plotly` çıktıları üretir.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field
from shapely.geometry import LineString
from shapely.strtree import STRtree

_MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(_MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_MOTOR_ROOT))

from core.rules.rule_engine import RuleEngine  # noqa: E402

from .cizim_onarici import separate_and_simplify_to_two_layers  # noqa: E402
from .denetim_isaretleyici import convert_dxf_to_dwg  # noqa: E402
from .disiplin_ayirici import classify_drawing_discipline  # noqa: E402
from .hesap_denetleyici import AuditFindingItem, build_calculation_audit_report  # noqa: E402
from .kalip_olusturucu import build_canonical_model  # noqa: E402
from .mahal_analizi import extract_architectural_enclosures  # noqa: E402
from .metin_temizleyici import norm_tr  # noqa: E402
from .metraj_cikarici import _RE_CABLE, build_project_inventory  # noqa: E402
from .schema import GroundingLoop, RawCADSnapshot, RawPath  # noqa: E402
from .sebeke_analizi import (  # noqa: E402
    NetworkAnalysisReport,
    NetworkFeederInput,
    TransformerInput,
    TransformerRedundancyResult,
    analyze_radial_network_pandapower,
    build_feeders_from_audit_rows,
    build_interactive_plotly_report,
    check_n1_transformer_redundancy,
)

_RE_STATION_HEADER = re.compile(r"([A-ZÇĞİÖŞÜ0-9\s]{3,45}\bİSTASYONU)", re.IGNORECASE)
_RE_TRAY_TAG = re.compile(r"\b(WC|LV|HV|OG|AG|MV|FA|SC|TR|KT)\s*/\s*(\d{2,4})\s*(?:/\s*(\d{2,4}))?\b", re.IGNORECASE)
_RE_TRAFO_KVA = re.compile(r"(\d{3,4})\s*kVA", re.IGNORECASE)
_RE_UPS_KVA = re.compile(r"UPS[^0-9]{0,20}(\d{2,4})\s*kVA", re.IGNORECASE)
_RE_BACKUP_PREFIX = re.compile(r"^(?:copy\s+of\s+|~\$|__)", re.IGNORECASE)


class SheetTitleMetadata(BaseModel):
    filename: str
    relative_path: str
    discipline_folder: str = ""
    classified_discipline: str = ""
    unit_name: str = "mm"
    station_or_project_name: str = ""
    sheet_title: str = ""
    scale: str = ""
    revision: str = ""
    symbol_count: int = 0
    grounding_loop_count: int = 0
    enclosure_count: int = 0
    schematic_node_count: int = 0
    arch_output_dxf: str = ""
    elec_output_dxf: str = ""
    elec_output_dwg: str = ""


class TraySummaryItem(BaseModel):
    system_code: str
    width_mm: int
    height_mm: Optional[int] = None
    occurrences: int
    sheets: List[str] = Field(default_factory=list)


class MultiProjectAuditReport(BaseModel):
    project_root: str
    rule_pack: str
    files_scanned: int = 0
    files_skipped_duplicates: List[str] = Field(default_factory=list)
    detected_station_names: Dict[str, int] = Field(default_factory=dict)
    sheet_metadata: List[SheetTitleMetadata] = Field(default_factory=list)
    aggregated_symbols: Dict[str, int] = Field(default_factory=dict)
    aggregated_by_discipline: Dict[str, int] = Field(default_factory=dict)
    discipline_breakdown: Dict[str, int] = Field(default_factory=dict)
    grounding_loops: List[GroundingLoop] = Field(default_factory=list)
    tray_inventory: List[TraySummaryItem] = Field(default_factory=list)
    cable_types_detected: Dict[str, int] = Field(default_factory=dict)
    transformer_ratings_kva: List[float] = Field(default_factory=list)
    ups_ratings_kva: List[float] = Field(default_factory=list)
    transformer_redundancy: Optional[TransformerRedundancyResult] = None
    network_analysis: Optional[NetworkAnalysisReport] = None
    findings: List[AuditFindingItem] = Field(default_factory=list)
    summary_counts: Dict[str, int] = Field(default_factory=dict)


def collect_project_drawings(
    root_dir: Union[str, Path],
    *,
    include_subdirs: Optional[Sequence[str]] = None,
    dxf_override_dir: Optional[Union[str, Path]] = None,
    max_files: Optional[int] = None,
) -> Tuple[List[Tuple[Path, Path]], List[str]]:
    """
    Klasördeki tüm CAD dosyalarını toplar; `Copy of ...`, `~`, `YEDEK/BAK` dosyalarını
    atlar ve varsa `dxf_override_dir` içindeki önceden dönüştürülmüş DXF yolunu eşler.
    Dönüş: ([(okunacak_dosya_yolu, orijinal_kaynak_yolu)], atlanan_isimler)
    """
    root = Path(root_dir)
    if not root.exists():
        raise FileNotFoundError(f"Proje klasörü bulunamadı: {root}")

    search_roots = [root / sd for sd in include_subdirs if (root / sd).exists()] if include_subdirs else [root]
    candidates: List[Path] = []
    for sr in search_roots:
        for p in sorted(sr.rglob("*")):
            if p.is_file() and p.suffix.lower() in (".dwg", ".dxf"):
                candidates.append(p)

    selected: List[Tuple[Path, Path]] = []
    skipped: List[str] = []
    seen_stems: Set[str] = set()
    seen_hashes: Set[str] = set()
    dxf_dir = Path(dxf_override_dir) if dxf_override_dir else None

    for p in candidates:
        name_u = norm_tr(p.name).upper()
        if _RE_BACKUP_PREFIX.match(p.name) or any(k in name_u for k in ("YEDEK", ".BAK", "BACKUP")):
            skipped.append(p.name)
            continue
        if p.stem.lower() in seen_stems:
            skipped.append(p.name)
            continue
        h = hashlib.sha256()
        try:
            with p.open("rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
            fhash = h.hexdigest()
        except OSError:
            fhash = ""
        if fhash and fhash in seen_hashes:
            skipped.append(p.name)
            continue
        seen_stems.add(p.stem.lower())
        if fhash:
            seen_hashes.add(fhash)
        read_path = p
        if dxf_dir is not None:
            cand_dxf = dxf_dir / f"{p.stem}.dxf"
            if cand_dxf.exists():
                read_path = cand_dxf
        selected.append((read_path, p))
        if max_files is not None and len(selected) >= max_files:
            break

    return selected, skipped


def _normalize_station_name(raw: str) -> str:
    """
    Antetteki istasyon adını temizler:
    - 'ATAKÖY İSTASYONU - BİLET HOLÜ KATI' / 'ATAKÖY İSTASYONU YOLCU GEÇİŞ KONTROL' -> 'ATAKÖY İSTASYONU'
    - Hat geneli kapak başlıklarını ('... METRO HATTI İNŞAATI') istasyon adı çelişkisi saymaz.
    """
    s = " ".join((raw or "").replace("\\~", " ").split()).strip()
    if not s:
        return ""
    m_st = _RE_STATION_HEADER.search(s)
    if m_st:
        return " ".join(m_st.group(1).strip().split())
    su = norm_tr(s).upper()
    if any(k in su for k in ("METRO HATTI", "INSAATI", "RAYLI SISTEM")):
        return ""
    return s


def _deduplicate_station_ratings(sheet_records: Sequence[Tuple[str, Sequence[float]]]) -> List[float]:
    """
    Aynı istasyon trafosu / UPS ekipmanının 20+ altlık paftada tekrar sayılmasını önler:
    Öncelikli olarak KUVVETLI_AKIM paftalarından (yoksa tüm paftalardan) her kVA değeri için
    tek paftadaki maksimum gerçek adedi alarak istasyonun tekilleştirilmiş kapasitesini döner.
    """
    power_recs = [list(r) for d, r in sheet_records if d == "KUVVETLI_AKIM" and r]
    active = power_recs if power_recs else [list(r) for _, r in sheet_records if r]
    if not active:
        return []
    max_per_kva: Dict[float, int] = {}
    for ratings in active:
        cnt = Counter(float(v) for v in ratings if v and v > 0)
        for kva, n in cnt.items():
            if n > max_per_kva.get(kva, 0):
                max_per_kva[kva] = n
    out: List[float] = []
    for kva in sorted(max_per_kva.keys(), reverse=True):
        out.extend([kva] * max_per_kva[kva])
    return out


def _format_kva_summary(ratings: Sequence[float]) -> str:
    """[2500, 2500, 2000, 2000] -> '2×2500 kVA + 2×2000 kVA' biçiminde kompakt gösterir."""
    if not ratings:
        return "-"
    cnt = Counter(float(v) for v in ratings if v and v > 0)
    parts = [f"{n}×{kva:.0f} kVA" if n > 1 else f"{kva:.0f} kVA" for kva, n in sorted(cnt.items(), key=lambda x: -x[0])]
    return " + ".join(parts)


def _extract_paperspace_title_info(snapshot: RawCADSnapshot) -> Tuple[str, str, str, str]:
    """PaperSpace ATTRIB ve başlık metinlerinden (istasyon_adi, pafta_adi, olcek, revizyon) çıkarır."""
    station_cands: Counter[str] = Counter()
    title_cands: List[str] = []
    scale = ""
    revision = ""

    for t in snapshot.texts:
        if not t.space.startswith("PAPERSPACE:"):
            continue
        raw = " ".join((t.text or "").replace("\\~", " ").split()).strip()
        if not raw:
            continue
        tag_u = norm_tr(t.attrib_tag).upper()
        if tag_u in ("SUNUMADI", "ISTASYON", "PROJEADI") and len(raw) >= 4:
            norm_st = _normalize_station_name(raw)
            if norm_st:
                station_cands[norm_st] += 2
        elif tag_u in ("PAFTAADI", "BASLIK", "TITLE") and len(raw) >= 4:
            title_cands.append(raw)
        elif tag_u in ("OLCEK", "SCALE"):
            scale = raw
        elif tag_u in ("REVIZYON", "REV"):
            revision = raw
        else:
            m_st = _RE_STATION_HEADER.search(raw)
            if m_st:
                norm_st = _normalize_station_name(m_st.group(1).strip())
                if norm_st:
                    station_cands[norm_st] += 1
            if any(k in norm_tr(raw).upper() for k in ("PROJESİ", "PROJESI", "PLANI", "ŞEMASI", "SEMASI")) and len(raw) >= 8:
                title_cands.append(raw[:120])

    station_name = station_cands.most_common(1)[0][0] if station_cands else ""
    sheet_title = title_cands[0] if title_cands else ""
    return station_name, sheet_title, scale, revision


def _line_geoms_from_paths(paths: Sequence[RawPath], du_to_m: float) -> List[LineString]:
    out: List[LineString] = []
    s = max(du_to_m, 1e-6)
    for p in paths:
        if len(p.points) < 2:
            continue
        pts = [(x * s, y * s) for x, y in p.points]
        if p.closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        ls = LineString(pts)
        if ls.length >= 0.05:
            out.append(ls)
    return out


def _process_single_sheet_for_bundle(
    read_path_s: str,
    orig_path_s: str,
    root_s: str,
    rule_pack: str,
    use_cache: bool,
    extract_enclosures: bool,
    export_two_layer_dir_s: Optional[str],
    export_dwg: bool,
) -> Dict[str, Any]:
    """Tek bir paftayı çoklu proje paketi adına bağımsız olarak analiz eder (ProcessPool uyumlu)."""
    read_path = Path(read_path_s)
    orig_path = Path(orig_path_s)
    root = Path(root_s)
    rel = str(orig_path.relative_to(root)) if orig_path.is_relative_to(root) else orig_path.name
    disc_folder = orig_path.parent.name if orig_path.parent != root else ""

    snap, model = build_canonical_model(read_path, use_cache=use_cache)
    inv = build_project_inventory(snap, model)
    calc_rep = build_calculation_audit_report(snap, model, inventory=inv, rule_pack=rule_pack)
    dem_w = calc_rep.power_budget.titleblock_demand_w or calc_rep.power_budget.subpanels_demand_sum_w
    f_list, f_skip = build_feeders_from_audit_rows(
        calc_rep.main_incomer.panel_name or "AGADP",
        calc_rep.panel_rows,
        calc_rep.vd_formulas,
    )
    st_name, sh_title, scale, rev = _extract_paperspace_title_info(snap)

    enc_count = 0
    if extract_enclosures:
        arch_paths = [
            p for p in snap.paths
            if any(k in norm_tr(p.layer).upper() for k in ("WALL", "DUVAR", "A-WALL", "S-STRS", "MIMARI"))
        ]
        if len(arch_paths) >= 4:
            encs, _ = extract_architectural_enclosures(arch_paths, model.unit.du_to_m, texts=snap.texts)
            enc_count = len(encs)

    sym_agg: Dict[str, int] = defaultdict(int)
    disc_agg: Dict[str, int] = defaultdict(int)
    for sb in inv.symbol_bom:
        lbl = f"[{sb.discipline}] {sb.category}: {sb.description[:45]}"
        sym_agg[lbl] += sb.total_count
        disc_agg[sb.discipline] += sb.total_count

    cable_agg: Dict[str, int] = defaultdict(int)
    lszh_count = 0
    non_lszh_power_cables: List[Tuple[str, str]] = []
    _lszh_keys = ("N2XH", "N2XRH", "N2XCH", "NHXMH", "FE180", "PH120", "07Z1", "H07Z", "LSZH", "LS0H", "LSOH", "HFFR", "XLPE")
    for cb in inv.cable_bom:
        cable_agg[cb.spec] += cb.occurrences
        spec_u = norm_tr(cb.spec).upper()
        if any(k in spec_u for k in _lszh_keys):
            lszh_count += cb.occurrences
        elif any(k in spec_u for k in ("NYY", "YVV")):
            non_lszh_power_cables.append((orig_path.name, cb.spec))

    if not inv.cable_bom:
        for t in snap.texts:
            for m_c in _RE_CABLE.finditer(t.text or ""):
                sp_txt = " ".join(m_c.group(0).split())
                cable_agg[sp_txt] += 1
                su = norm_tr(sp_txt).upper()
                if any(k in su for k in _lszh_keys):
                    lszh_count += 1
                elif any(k in su for k in ("NYY", "YVV")):
                    non_lszh_power_cables.append((orig_path.name, sp_txt))

    vld_hits = 0
    meb_hits = 0
    eeb_hits = 0
    sc_jb_hits = 0
    trafo_kvas: List[float] = []
    ups_kvas: List[float] = []
    ground_res_vals: List[float] = []
    tray_occ: Dict[Tuple[str, int, Optional[int]], int] = defaultdict(int)

    for ins in snap.inserts:
        bu = norm_tr(ins.effective_name or ins.block_name).upper()
        if "VLD" in bu:
            vld_hits += 1
        if any(k in bu for k in ("MEB", "EPTB", "ANA ESPOTANSIYEL", "ESPOTANSIYEL BARA", "TOPRAKLAMA BARA", "ETB")):
            meb_hits += 1
        if "EEB" in bu:
            eeb_hits += 1
        if "SC-JB" in bu or "TEST KUTU" in bu:
            sc_jb_hits += 1
        m_ups = _RE_UPS_KVA.search(ins.effective_name or ins.block_name)
        if m_ups:
            ups_kvas.append(float(m_ups.group(1)))
        m_tr = _RE_TRAFO_KVA.search(ins.effective_name or ins.block_name)
        if m_tr and ("TRAFO" in bu or "TRANSF" in bu):
            trafo_kvas.append(float(m_tr.group(1)))

    for t in snap.texts:
        raw = " ".join((t.text or "").split()).strip()
        if not raw:
            continue
        tu = norm_tr(raw).upper()
        for m_tray in _RE_TRAY_TAG.finditer(raw):
            code = m_tray.group(1).upper()
            w_mm = int(m_tray.group(2))
            h_mm = int(m_tray.group(3)) if m_tray.group(3) else None
            tray_occ[(code, w_mm, h_mm)] += 1
        if "VLD" in tu and ("SINIRLAYICI" in tu or "LIMITING" in tu or "RAY" in tu or len(tu) <= 24):
            vld_hits += 1
        if re.search(r"\b(?:MEB|ETB|EBB|EPTB)\b|(?:ANA\s+)?E[SŞ]POTANS[Iİ]YEL(?:\s+TOPRAKLAMA)?\s+BARA|POTANS[Iİ]YEL\s+DENGELEME", raw, re.IGNORECASE):
            meb_hits += 1
        if re.search(r"\bEEB\b", raw):
            eeb_hits += 1
        if "SC-JB" in tu or "TEST KUTU" in tu:
            sc_jb_hits += 1
        m_res = re.search(r"(?:R_?E?|D[İI]REN[ÇC])\s*[:=≤<]+\s*(\d+(?:[.,]\d+)?)\s*(?:OHM|Ω)", raw, re.IGNORECASE)
        if m_res:
            try:
                ground_res_vals.append(float(m_res.group(1).replace(",", ".")))
            except ValueError:
                pass

    rail_ground_intersections: List[Tuple[str, Tuple[float, float]]] = []
    rail_paths = [
        p for p in snap.paths
        if any(rk in norm_tr(p.layer).upper() for rk in ("TRAK-RAIL", "E-RAIL", "RAY-HAT", "RAIL_TRACK"))
    ]
    gnd_paths = [
        p for p in snap.paths
        if any(gk in norm_tr(p.layer).upper() for gk in ("E-EAR", "TOPRAK", "GND", "EARTH", "YP-EL"))
    ]
    if rail_paths and gnd_paths:
        r_geoms = _line_geoms_from_paths(rail_paths, model.unit.du_to_m)
        g_geoms = _line_geoms_from_paths(gnd_paths, model.unit.du_to_m)
        if r_geoms and g_geoms:
            g_tree = STRtree(g_geoms)
            for rg in r_geoms:
                for gi in g_tree.query(rg):
                    gg = g_geoms[int(gi)]
                    if rg.intersects(gg):
                        pt = rg.intersection(gg).centroid
                        rail_ground_intersections.append((orig_path.name, (round(pt.x, 2), round(pt.y, 2))))
                        break

    disc_cls, _ = classify_drawing_discipline(snap, model, source_path=str(orig_path))
    arch_out_s, elec_out_s, elec_dwg_s = "", "", ""
    if export_two_layer_dir_s is not None:
        disc_dir = Path(export_two_layer_dir_s) / disc_cls
        out_a = disc_dir / f"{orig_path.stem}_1_MIMARI.dxf"
        out_e = disc_dir / f"{orig_path.stem}_2_ELEKTRIK.dxf"
        separate_and_simplify_to_two_layers(
            snap.dxf_path,
            snap,
            model,
            out_arch_dxf=out_a,
            out_elec_dxf=out_e,
            heal_wires=True,
        )
        arch_out_s = str(out_a)
        elec_out_s = str(out_e)
        if export_dwg:
            dwg_res = convert_dxf_to_dwg(out_e, out_e.with_suffix(".dwg"))
            if dwg_res.success and dwg_res.dwg_path:
                elec_dwg_s = dwg_res.dwg_path

    meta = SheetTitleMetadata(
        filename=orig_path.name,
        relative_path=rel,
        discipline_folder=disc_folder,
        classified_discipline=disc_cls,
        unit_name=model.unit.unit_name,
        station_or_project_name=st_name,
        sheet_title=sh_title,
        scale=scale,
        revision=rev,
        symbol_count=sum(x.total_count for x in inv.symbol_bom),
        grounding_loop_count=len(model.grounding_loops),
        enclosure_count=enc_count,
        schematic_node_count=sum(len(g.nodes) for g in model.schematics),
        arch_output_dxf=arch_out_s,
        elec_output_dxf=elec_out_s,
        elec_output_dwg=elec_dwg_s,
    )
    return {
        "orig_name": orig_path.name,
        "dem_kw": (dem_w / 1000.0) if (dem_w and dem_w > 0) else None,
        "feeders": f_list,
        "skipped_feeders": f_skip,
        "st_name": st_name,
        "sym_agg": dict(sym_agg),
        "disc_agg": dict(disc_agg),
        "cable_agg": dict(cable_agg),
        "lszh_count": lszh_count,
        "non_lszh": non_lszh_power_cables,
        "grounding_loops": list(model.grounding_loops),
        "vld_hits": vld_hits,
        "meb_hits": meb_hits,
        "eeb_hits": eeb_hits,
        "sc_jb_hits": sc_jb_hits,
        "trafo_kvas": trafo_kvas,
        "ups_kvas": ups_kvas,
        "ground_res_vals": ground_res_vals,
        "tray_occ": dict(tray_occ),
        "rail_ground_intersections": rail_ground_intersections,
        "meta": meta,
    }


def analyze_multi_sheet_project(
    project_root: Union[str, Path],
    *,
    include_subdirs: Optional[Sequence[str]] = None,
    rule_pack: str = "ibb_metro",
    dxf_override_dir: Optional[Union[str, Path]] = None,
    use_cache: bool = True,
    max_files: Optional[int] = None,
    extract_enclosures: bool = False,
    export_two_layer_dir: Optional[Union[str, Path]] = None,
    export_dwg: bool = False,
    max_workers: int = 1,
) -> MultiProjectAuditReport:
    """
    Çoklu DWG/DXF proje klasörünü (örn. metro istasyonu) tek bir evrensel
    okuma, antet tutarlılık, topraklama/kuvvetli akım kural denetimi ve
    `pandapower` şebeke analizinden geçirir.
    """
    root = Path(project_root)
    rules = RuleEngine.load_pack(rule_pack)
    files, skipped = collect_project_drawings(
        root,
        include_subdirs=include_subdirs,
        dxf_override_dir=dxf_override_dir,
        max_files=max_files,
    )

    report = MultiProjectAuditReport(
        project_root=str(root),
        rule_pack=rule_pack,
        files_scanned=len(files),
        files_skipped_duplicates=skipped,
    )

    station_counter: Counter[str] = Counter()
    station_files: Dict[str, List[str]] = defaultdict(list)
    sym_agg: Counter[str] = Counter()
    disc_agg: Counter[str] = Counter()
    tray_agg: Dict[Tuple[str, int, Optional[int]], Set[str]] = defaultdict(set)
    tray_occ: Counter[Tuple[str, int, Optional[int]]] = Counter()
    cable_agg: Counter[str] = Counter()
    trafo_kvas: List[float] = []
    ups_kvas: List[float] = []

    vld_hits = 0
    meb_hits = 0
    eeb_hits = 0
    sc_jb_hits = 0
    ground_res_vals: List[float] = []
    rail_ground_intersections: List[Tuple[str, Tuple[float, float]]] = []
    lszh_count = 0
    non_lszh_power_cables: List[Tuple[str, str]] = []
    feeders_collected: List[NetworkFeederInput] = []
    skipped_feeders_notes: List[str] = []
    demand_power_candidates_kw: List[float] = []

    export_dir_s = str(export_two_layer_dir) if export_two_layer_dir is not None else None
    per_sheet_results: List[Dict[str, Any]] = []
    if max_workers > 1 and len(files) > 1:
        res_by_idx: Dict[int, Dict[str, Any]] = {}
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            futs = {
                pool.submit(
                    _process_single_sheet_for_bundle,
                    str(rp),
                    str(op),
                    str(root),
                    rule_pack,
                    use_cache,
                    extract_enclosures,
                    export_dir_s,
                    export_dwg,
                ): idx
                for idx, (rp, op) in enumerate(files)
            }
            for fut in as_completed(futs):
                res_by_idx[futs[fut]] = fut.result()
        per_sheet_results = [res_by_idx[i] for i in range(len(files))]
    else:
        for rp, op in files:
            per_sheet_results.append(
                _process_single_sheet_for_bundle(
                    str(rp),
                    str(op),
                    str(root),
                    rule_pack,
                    use_cache,
                    extract_enclosures,
                    export_dir_s,
                    export_dwg,
                )
            )

    trafo_sheet_records: List[Tuple[str, List[float]]] = []
    ups_sheet_records: List[Tuple[str, List[float]]] = []
    for sr in per_sheet_results:
        if sr["dem_kw"] is not None:
            demand_power_candidates_kw.append(sr["dem_kw"])
        feeders_collected.extend(sr["feeders"])
        skipped_feeders_notes.extend(sr["skipped_feeders"])
        if sr["st_name"]:
            station_counter[sr["st_name"]] += 1
            station_files[sr["st_name"]].append(sr["orig_name"])
        for k, v in sr["sym_agg"].items():
            sym_agg[k] += v
        for k, v in sr["disc_agg"].items():
            disc_agg[k] += v
        for k, v in sr["cable_agg"].items():
            cable_agg[k] += v
        lszh_count += sr["lszh_count"]
        non_lszh_power_cables.extend(sr["non_lszh"])
        report.grounding_loops.extend(sr["grounding_loops"])
        vld_hits += sr["vld_hits"]
        meb_hits += sr["meb_hits"]
        eeb_hits += sr["eeb_hits"]
        sc_jb_hits += sr["sc_jb_hits"]
        if sr["trafo_kvas"]:
            trafo_sheet_records.append((sr["meta"].classified_discipline, sr["trafo_kvas"]))
        if sr["ups_kvas"]:
            ups_sheet_records.append((sr["meta"].classified_discipline, sr["ups_kvas"]))
        ground_res_vals.extend(sr["ground_res_vals"])
        for k, v in sr["tray_occ"].items():
            tray_occ[k] += v
            tray_agg[k].add(sr["orig_name"])
        rail_ground_intersections.extend(sr["rail_ground_intersections"])
        report.sheet_metadata.append(sr["meta"])

    trafo_kvas = _deduplicate_station_ratings(trafo_sheet_records)
    ups_kvas = _deduplicate_station_ratings(ups_sheet_records)

    report.discipline_breakdown = dict(Counter(sm.classified_discipline for sm in report.sheet_metadata if sm.classified_discipline))
    report.detected_station_names = dict(station_counter.most_common())
    report.aggregated_symbols = dict(sym_agg.most_common())
    report.aggregated_by_discipline = dict(disc_agg.most_common())
    report.cable_types_detected = dict(cable_agg.most_common())
    report.transformer_ratings_kva = sorted(trafo_kvas, reverse=True)
    report.ups_ratings_kva = sorted(ups_kvas, reverse=True)
    report.tray_inventory = [
        TraySummaryItem(
            system_code=k[0],
            width_mm=k[1],
            height_mm=k[2],
            occurrences=tray_occ[k],
            sheets=sorted(tray_agg[k]),
        )
        for k in sorted(tray_occ.keys(), key=lambda x: -tray_occ[x])
    ]

    # Kurallar (RuleEngine YAML değerleriyle)
    findings: List[AuditFindingItem] = []
    fid = 1

    def _add_finding(
        sev: str,
        cat: str,
        loc: str,
        proj_val: str,
        eng_val: str,
        std: str,
        desc: str,
        rec: str = "",
    ) -> None:
        nonlocal fid
        findings.append(
            AuditFindingItem(
                finding_id=f"M-{fid:02d}",
                severity=sev,  # type: ignore[arg-type]
                category=cat,
                location=loc,
                project_value=proj_val,
                engine_value=eng_val,
                standard_ref=std,
                description=desc,
                recommendation=rec,
            )
        )
        fid += 1

    # 1. Antet / İstasyon adı tutarlılık denetimi
    if len(station_counter) > 1:
        summary_txt = ", ".join(f"{k} ({v} pafta)" for k, v in station_counter.most_common())
        _add_finding(
            "UYARI",
            "Pafta Antet Tutarlılığı",
            "İstasyon Genel",
            summary_txt,
            "Tek ve tutarlı istasyon adı",
            "CAD Pafta Standardı",
            "Aynı proje klasöründeki pafta antetlerinde birden fazla farklı istasyon/proje adı tespit edildi.",
            "Eski/kopya paftadan kalan antet başlıklarını güncel istasyon adıyla düzeltin.",
        )

    # 2. Topraklama ve Ray Yalıtımı (EN 50122)
    stray_cfg = rules.get("grounding_architecture", {}).get("stray_current_mitigation", {})
    ear_cfg = rules.get("station_earthing", {})
    max_r_ohm = float(ear_cfg.get("max_ground_resistance_ohm", 1.0))

    if rail_ground_intersections:
        ex = rail_ground_intersections[0]
        _add_finding(
            "KRITIK",
            "Ray-Toprak Doğrudan Teması (Floating Return İhlali)",
            ex[0],
            f"Kesişim @ {ex[1]} m ({len(rail_ground_intersections)} pafta)",
            "Doğrudan temas = 0 (Yalnız VLD üzerinden)",
            "EN 50122-2 / NFPA 130",
            "DC cer rayı hattı ile istasyon topraklama iletkeni geometrik olarak doğrudan kesişiyor.",
            "Ray ile PE topraklamasını fiziksel olarak ayırın ve VLD üzerinden bağlayın.",
        )

    if stray_cfg.get("voltage_limiting_device_vld", ear_cfg.get("voltage_limiting_device_vld", False)):
        if vld_hits > 0:
            _add_finding(
                "UYGUN",
                "VLD (Gerilim Sınırlama Cihazı) Varlığı",
                "Topraklama Paftaları",
                f"{vld_hits} VLD referansı",
                "VLD mevcut",
                "EN 50122-1 Md. 6",
                "Ray-toprak arası aşırı gerilim sınırlama (VLD) referansı çizimlerde tespit edildi.",
            )
        else:
            _add_finding(
                "BILGI",
                "VLD (Gerilim Sınırlama Cihazı) Kontrolü",
                "İncelenen Topraklama Paftaları",
                "Taranan paftalarda VLD etiketi saptanmadı",
                "VLD (VLD-F/O) çizimde/şemada gösterilmeli",
                "EN 50122-1 Md. 6",
                "İncelenen paftalar içinde açık 'VLD' sembol/etiket adı tespit edilemedi (ayrı tünel/cer paftasında olabilir).",
                "Cer trafo ve ray dönüş şemalarında VLD bağlantısını doğrulayın.",
            )

    meb_min = int(ear_cfg.get("meb_min_count", 2))
    if meb_hits >= meb_min:
        _add_finding(
            "UYGUN",
            "Ana Eşpotansiyel Bara (MEB)",
            "Topraklama Sistemi",
            f"{meb_hits} MEB referansı",
            f"MEB >= {meb_min} adet",
            "EN 50122-1 / Metro Şartnamesi",
            "İstasyon genelinde yeterli sayıda Ana Eşpotansiyel Bara (MEB) referansı görüldü.",
        )
    elif report.grounding_loops:
        _add_finding(
            "UYARI",
            "Ana Eşpotansiyel Bara (MEB) Referansı",
            "Topraklama Paftaları",
            f"{meb_hits} MEB etiketi, {len(report.grounding_loops)} topraklama ringi",
            f"En az {meb_min} MEB (çift hat 120 mm² Cu)",
            "Metro Topraklama Şartnamesi",
            "Topraklama ringleri mevcut ancak çizimlerde en az 2 adet açık MEB etiketi doğrulanamadı.",
        )

    for rv in ground_res_vals:
        if rv > max_r_ohm:
            _add_finding(
                "KRITIK",
                "İstasyon Topraklama Direnci Sınırı",
                "Topraklama Paftaları",
                f"R = {rv:.2f} Ohm",
                f"R <= {max_r_ohm:.2f} Ohm",
                "EN 50122-1 / ETTMY",
                f"Çizimde belirtilen topraklama direnci ({rv:.2f} Ω) şartname sınırını ({max_r_ohm:.2f} Ω) aşıyor.",
            )

    # 3. LSZH / FE180 Yangın Güvenliği Kablo Kontrolü
    fire_cfg = rules.get("fire_and_life_safety", {})
    if fire_cfg.get("lszh_mandatory", False) and non_lszh_power_cables:
        _add_finding(
            "KRITIK",
            "Halogen-Free (LSZH / FE180) Kablo Şartı",
            non_lszh_power_cables[0][0],
            f"{non_lszh_power_cables[0][1]} ({len(non_lszh_power_cables)} kalem)",
            "LSZH (N2XH / NHXMH / FE180)",
            "NFPA 130 Md. 8.8 / BYKHY",
            "Yeraltı istasyonunda PVC kılıflı (NYY/YVV) kuvvet kablosu tespit edildi; şartname gereği LSZH/FE180 kullanılmalıdır.",
            "Tüm kapalı istasyon kuvvet/acil kablolarını N2XH/FE180 olarak revize edin.",
        )

    # 4. N-1 Trafo Yedekliliği & pandapower Şebeke Analizi (veri varsa)
    total_demand_kw = max(demand_power_candidates_kw) if demand_power_candidates_kw else (
        round(sum(f.power_kw for f in feeders_collected), 2) if feeders_collected else None
    )
    if trafo_kvas:
        tr_cfg = rules.get("transformer_and_ups", {})
        n1_req = bool(tr_cfg.get("n1_transformer_redundancy", True))
        tr_red = check_n1_transformer_redundancy(trafo_kvas, demand_kw=total_demand_kw)
        report.transformer_redundancy = tr_red
        if n1_req:
            sev_tr = tr_red.status if tr_red.status in ("UYGUN", "KRITIK", "UYARI") else "BILGI"
            _add_finding(
                sev_tr,
                "N-1 Trafo Yedekliliği",
                "Güç Dağıtım / Trafo",
                _format_kva_summary(tr_red.ratings_kva),
                f"N-1 Kalan={tr_red.n1_remaining_kva:.0f} kVA" + (f" (Yük=%{tr_red.n1_utilization_pct:.1f})" if tr_red.n1_utilization_pct is not None else ""),
                "Metro / Tesis Şartnamesi",
                tr_red.note,
            )

    if feeders_collected:
        tr = TransformerInput(sn_kva=max(trafo_kvas), name="TR-01") if trafo_kvas else None
        na_rep = analyze_radial_network_pandapower(feeders_collected, transformer=tr)
        na_rep.skipped_branches = skipped_feeders_notes
        report.network_analysis = na_rep
        if na_rep.converged:
            max_vd_lim = float(rules.get("voltage_drop_limits", {}).get("total_allowed_pct", 5.0))
            _add_finding(
                "UYGUN" if na_rep.max_voltage_drop_pct <= max_vd_lim else "KRITIK",
                "Çok Baralı Yük Akışı & Gerilim Düşümü (pandapower)",
                f"{len(na_rep.buses)} bara / {len(na_rep.lines)} fider",
                f"Maks. %e = %{na_rep.max_voltage_drop_pct:.2f}",
                f"<= %{max_vd_lim:.1f}",
                "TS HD 60364-5-52 / IEC 60909",
                f"pandapower AC yük akışı yakınsadı; en kritik barada bağıl gerilim düşümü %{na_rep.max_voltage_drop_pct:.2f}.",
            )

    counts = Counter(f.severity for f in findings)
    report.findings = findings
    report.summary_counts = {
        "KRITIK": counts.get("KRITIK", 0),
        "UYARI": counts.get("UYARI", 0),
        "BILGI": counts.get("BILGI", 0),
        "UYGUN": counts.get("UYGUN", 0),
        "toplam_bulgu": len(findings),
    }
    return report


def save_multi_sheet_reports(
    report: MultiProjectAuditReport,
    output_dir: Union[str, Path],
    *,
    base_name: str = "istasyon_denetim",
    include_plotlyjs: Union[bool, str] = "cdn",
) -> Dict[str, Path]:
    """Çok-dosyalı proje analizini JSON, Markdown, Excel (.xlsx) ve Plotly HTML olarak kaydeder."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: Dict[str, Path] = {}

    # 1. JSON
    p_json = out / f"{base_name}.json"
    p_json.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    paths["json"] = p_json

    # 2. Markdown (Sade, Yönetici Özeti + 4 Disiplin Kartları; tam pafta/BOM dökümü Excel & HTML ekinde)
    unit_cnt = Counter(sm.unit_name for sm in report.sheet_metadata)
    unit_txt = ", ".join(f"`{u}`: {n}" for u, n in unit_cnt.most_common()) or "-"
    disc_order = ("KUVVETLI_AKIM", "TOPRAKLAMA", "ZAYIF_AKIM", "SINYAL")
    disc_labels = {
        "KUVVETLI_AKIM": "Kuvvetli Akım",
        "TOPRAKLAMA": "Topraklama",
        "ZAYIF_AKIM": "Zayıf Akım",
        "SINYAL": "Sinyal / SCADA",
    }
    disc_txt = " | ".join(
        f"{disc_labels[d]}: **{report.discipline_breakdown.get(d, 0)}**"
        for d in disc_order
    )
    st_summary = ", ".join(f"{k} ({v} pafta)" for k, v in report.detected_station_names.items()) or "BELİRSİZ"
    tr_str = _format_kva_summary(report.transformer_ratings_kva)
    ups_str = _format_kva_summary(report.ups_ratings_kva)
    sc = report.summary_counts

    lines = [
        f"# Metro / İstasyon Mühendislik Özet Raporu — `{Path(report.project_root).name}`",
        "",
        f"> **İstasyon (Antet):** {st_summary} | **Profil:** `{report.rule_pack}` | "
        f"**Taranan Pafta:** `{report.files_scanned}` (Elenen kopya: `{len(report.files_skipped_duplicates)}`) | "
        f"**Bulgular:** Kritik `{sc.get('KRITIK', 0)}`, Uyarı `{sc.get('UYARI', 0)}`, Uygun `{sc.get('UYGUN', 0)}`",
        "",
        f"- **4 Disiplin Dağılımı:** {disc_txt}",
        f"- **Tespit Edilen Birimler:** {unit_txt}",
        f"- **Tekilleştirilmiş Güç Ekipmanları:** Trafo: `{tr_str}` | UPS: `{ups_str}` | Topraklama Ringi: `{len(report.grounding_loops)}` | Tava Tipi: `{len(report.tray_inventory)}`",
        "",
        "## 1. Denetim Bulguları",
        "| ID | Önem | Kategori | Konum | Proje Değeri | Mevzuat / Beklenen | Standart |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for f in report.findings:
        lines.append(
            f"| `{f.finding_id}` | **{f.severity}** | {f.category} | {f.location} | {f.project_value} | {f.engine_value} | {f.standard_ref} |"
        )
    if not report.findings:
        lines.append("| - | - | - | - | Herhangi bir aykırılık tespit edilmedi | - | - |")

    lines.extend([
        "",
        "## 2. 4 Disiplin Bazlı Temiz Veri Özeti",
        "| Disiplin | Pafta Sayısı | Toplam Ekipman | Topraklama Ring | Şema Düğümü | Öne Çıkan Veri Özeti |",
        "| :--- | ---: | ---: | ---: | ---: | :--- |",
    ])
    for d in disc_order:
        d_sheets = [sm for sm in report.sheet_metadata if sm.classified_discipline == d]
        n_sh = len(d_sheets)
        n_sym = sum(sm.symbol_count for sm in d_sheets)
        n_ring = sum(sm.grounding_loop_count for sm in d_sheets)
        n_node = sum(sm.schematic_node_count for sm in d_sheets)
        if d == "KUVVETLI_AKIM":
            tray_by_cw: Counter[Tuple[str, int]] = Counter()
            for t in report.tray_inventory:
                tray_by_cw[(t.system_code, t.width_mm)] += t.occurrences
            top_trays = ", ".join(f"{c}/{w} ({n}x)" for (c, w), n in tray_by_cw.most_common(4)) or "-"
            note = f"Trafo: {tr_str}; UPS: {ups_str}; Başlıca Tavalar: {top_trays}"
        elif d == "TOPRAKLAMA":
            note = f"Ring: {len(report.grounding_loops)} adet; VLD/MEB doğrulaması üst bulgularda"
        elif d == "ZAYIF_AKIM":
            sub_cnt: Counter[str] = Counter()
            for sm in d_sheets:
                m_sub = re.search(r"\b(AX-\d{2}|TL-\d{2})\b", sm.filename.upper())
                if m_sub:
                    sub_cnt[m_sub.group(1)] += 1
            sub_s = ", ".join(f"{k}({v})" for k, v in sub_cnt.most_common(8)) or "-"
            note = f"Alt sistemler: {sub_s}"
        else:
            note = "SCADA / PLC / RTU / Sinyalizasyon paftaları"
        lines.append(f"| **{disc_labels[d]}** | {n_sh} | {n_sym:,} | {n_ring} | {n_node:,} | {note} |")

    top_cables = list(report.cable_types_detected.items())[:10]
    if top_cables:
        lines.extend([
            "",
            "## 3. Tespit Edilen Başlıca Kablo Tipleri (İlk 10)",
            "| Kablo Tipi | Etiket Adedi |",
            "| :--- | ---: |",
        ])
        for c_spec, c_cnt in top_cables:
            lines.append(f"| `{c_spec}` | {c_cnt} |")

    if len(report.sheet_metadata) <= 20:
        lines.extend([
            "",
            "## 4. Pafta & Antet Listesi",
            "| Dosya | Disiplin | Birim | İstasyon (Antet) | Sembol | Ring | Şema Düğümü |",
            "| :--- | :--- | :--- | :--- | ---: | ---: | ---: |",
        ])
        for sm in report.sheet_metadata:
            lines.append(
                f"| {sm.filename} | {sm.classified_discipline or '-'} | {sm.unit_name} | {sm.station_or_project_name or '-'} | "
                f"{sm.symbol_count} | {sm.grounding_loop_count} | {sm.schematic_node_count} |"
            )
    else:
        lines.extend([
            "",
            f"> *Tam {len(report.sheet_metadata)} paftalık liste, tüm ekipman metrajı (`{len(report.aggregated_symbols)}` kalem) ve `{len(report.tray_inventory)}` tava tipi `{base_name}.xlsx` ve interaktif `{base_name}.html` dosyalarında yer almaktadır.*",
        ])

    p_md = out / f"{base_name}.md"
    p_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    paths["md"] = p_md

    # 3. Excel (.xlsx)
    wb = openpyxl.Workbook()
    ws_sum = wb.active
    ws_sum.title = "Pafta ve Antetler"
    headers = ["Dosya", "Klasör", "Tespit Edilen Disiplin", "Birim", "Antet İstasyon", "Pafta Başlığı", "Ölçek", "Sembol Adedi", "Topraklama Ring", "Kapalı Mahal", "Şema Düğümü", "1_MIMARI DXF", "2_ELEKTRIK DXF/DWG"]
    ws_sum.append(headers)
    hdr_fill = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
    hdr_font = Font(bold=True, color="FFFFFF")
    for ci in range(1, len(headers) + 1):
        c = ws_sum.cell(row=1, column=ci)
        c.fill = hdr_fill
        c.font = hdr_font
        c.alignment = Alignment(horizontal="center")
    for sm in report.sheet_metadata:
        ws_sum.append([
            sm.filename, sm.discipline_folder, sm.classified_discipline, sm.unit_name,
            sm.station_or_project_name, sm.sheet_title, sm.scale,
            sm.symbol_count, sm.grounding_loop_count, sm.enclosure_count, sm.schematic_node_count,
            sm.arch_output_dxf, sm.elec_output_dwg or sm.elec_output_dxf,
        ])

    ws_bom = wb.create_sheet("Ekipman Metraji")
    ws_bom.append(["Ekipman / Blok Tanımı", "Toplam Adet"])
    for k, v in report.aggregated_symbols.items():
        ws_bom.append([k, v])

    ws_tray = wb.create_sheet("Kablo Tavalari")
    ws_tray.append(["Sistem Kodu", "Genişlik (mm)", "Kot/Yükseklik (mm)", "Etiket Sayısı", "Paftalar"])
    for tr in report.tray_inventory:
        ws_tray.append([tr.system_code, tr.width_mm, tr.height_mm or "", tr.occurrences, ", ".join(tr.sheets)])

    ws_fnd = wb.create_sheet("Denetim Bulgulari")
    ws_fnd.append(["ID", "Şiddet", "Kategori", "Konum", "Proje Değeri", "Beklenen / Mevzuat", "Standart", "Açıklama", "Öneri"])
    for f in report.findings:
        ws_fnd.append([f.finding_id, f.severity, f.category, f.location, f.project_value, f.engine_value, f.standard_ref, f.description, f.recommendation])

    for ws in wb.worksheets:
        for col in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=10)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(max_len + 3, 12), 55)

    p_xlsx = out / f"{base_name}.xlsx"
    wb.save(str(p_xlsx))
    paths["xlsx"] = p_xlsx

    # 4. Plotly interaktif HTML
    bus_res = report.network_analysis.buses if report.network_analysis else None
    p_html = build_interactive_plotly_report(
        title=f"CloudeCAD Mühendislik Analiz Panosu — {Path(report.project_root).name}",
        out_html=out / f"{base_name}.html",
        discipline_counts=report.aggregated_by_discipline,
        bus_results=bus_res,
        finding_severity_counts={
            k: report.summary_counts.get(k, 0)
            for k in ("KRITIK", "UYARI", "BILGI", "UYGUN")
            if report.summary_counts.get(k, 0) > 0
        },
        include_plotlyjs=include_plotlyjs,
    )
    paths["html"] = p_html
    return paths
