# -*- coding: utf-8 -*-
"""
Evrensel CAD Okuyucu (UniversalCADReader) — Modüler Çekirdek
============================================================
DXF/DWG çizimlerini matris dönüşümleri, uzamsal metin dikimi,
ölçek-uyarlamalı lejant ve çok kanıtlı sembol sınıflandırmasıyla açar.
"""

from __future__ import annotations
import math
import logging
import re
from pathlib import Path
from typing import Union, List, Dict, Tuple, Optional, Any
import ezdxf
from ezdxf.math import Vec3, Matrix44
from shapely.geometry import box

try:
    from common.dxf_converter import ensure_dxf, is_valid_dxf
except ImportError:
    from ...common.dxf_converter import ensure_dxf, is_valid_dxf
from ..model.entities import (
    TextToken,
    PlacedSymbol,
    CalloutGroup,
    ExtractedTable,
    SubPlanZone,
    DrawingSceneGraph,
)
from .geometry import (
    clean_turkish_text,
    strip_revit_view_suffix,
    TextReconstructionEngine,
    GeometricTableExtractor,
)
from .classifier import MultiEvidenceClassifier
from .frame_detector import SpatialZoneMapper
from .triage import SymbolTriage
from ..topology.circuit_resolver import LogicalCircuitResolver
from ..topology.route_builder import PhysicalRouteBuilder

logger = logging.getLogger("CloudeCAD.CADReader")


ELECTRICAL_LINE_KEYWORDS = (
    "E-", "ELC", "LIGHT", "LITE", "PWR", "GUC", "GÜÇ", "PRZ", "PRIZ",
    "CABLE", "TRAY", "TAVA", "PANEL", "PANO", "FIRE", "YANGIN", "TOPRAK", "EARTH",
    "00-KUVVETLI", "00-KUVVETLİ", "00-AYDINLATMA", "00-PRIZ", "00-PRİZ", "00-ZAYIF", "00-TOPRAKLAMA"
)


class BlockHierarchyFlattener:
    CONTAINER_PATTERNS = [
        re.compile(r"XREF", re.IGNORECASE),
        re.compile(r"KAT_PLANI", re.IGNORECASE),
        re.compile(r"ARCH", re.IGNORECASE),
        re.compile(r"M3-ARC", re.IGNORECASE),
        re.compile(r"M3-ELC", re.IGNORECASE),
        re.compile(r"FloorPlan-", re.IGNORECASE),
        re.compile(r"YBS", re.IGNORECASE),
        re.compile(r"metraj", re.IGNORECASE),
    ]

    IGNORE_BLOCK_PATTERNS = [
        re.compile(r"M3-STR", re.IGNORECASE),
        re.compile(r"M3-MEC", re.IGNORECASE),
        re.compile(r"hv1029", re.IGNORECASE),
        re.compile(r"HV1032", re.IGNORECASE),
        re.compile(r"6x4x12F", re.IGNORECASE),
        re.compile(r"TP325_Closet", re.IGNORECASE),
        re.compile(r"^C2010_", re.IGNORECASE),
        re.compile(r"^C1070_", re.IGNORECASE),
        re.compile(r"^C1010_", re.IGNORECASE),
        re.compile(r"^C1020_", re.IGNORECASE),
        re.compile(r"^C30", re.IGNORECASE),
        re.compile(r"^B20", re.IGNORECASE),
        re.compile(r"^Railing", re.IGNORECASE),
        re.compile(r"Handrail", re.IGNORECASE),
        re.compile(r"Grid Head", re.IGNORECASE),
        re.compile(r"Level Head", re.IGNORECASE),
        re.compile(r"D_TAG_ROOM", re.IGNORECASE),
        re.compile(r"Space Tag", re.IGNORECASE),
        re.compile(r"D_VIEWTITLE", re.IGNORECASE),
        re.compile(r"PROTA LOGO", re.IGNORECASE),
        re.compile(r"EMAY LOGO", re.IGNORECASE),
        re.compile(r"ATI_Antet", re.IGNORECASE),
        re.compile(r"Antet", re.IGNORECASE),
        re.compile(r"North Arrow", re.IGNORECASE),
        re.compile(r"Kuzey Oku", re.IGNORECASE),
        re.compile(r"^(?:aa|oo|yy)$", re.IGNORECASE),
        re.compile(r"^PL_WC", re.IGNORECASE),
        re.compile(r"^hilton", re.IGNORECASE),
        re.compile(r"imza", re.IGNORECASE),                  # İmza blokları (sevgi imza vb.)
        re.compile(r"Cahit", re.IGNORECASE),                 # Müellif imza/antet blokları
        re.compile(r"Sümer", re.IGNORECASE),                 # Müellif imza/antet blokları
        re.compile(r"^BE_KABLO", re.IGNORECASE),             # Kablo etiket blokları
    ]

    ARCHITECTURAL_IGNORE_LAYERS = (
        "DUVAR", "SIVA", "DSIVA", "DSİVA", "DS\xddVA", "TEFRS", "TEFRIS", "TEFRİŞ",
        "MOBILYA", "MOBİLYA", "KAPI", "KAPİ", "PENCERE", "DKAPIPENCERE",
        "00-CERCEVE", "CERCEVE", "ÇERÇEVE", "FRAME", "BORDER", "MERDIVEN", "MERDİVEN",
        "TARAMA", "HATCH", "OLCU", "ÖLÇÜ", "A-WALL", "A-DOOR", "A-GLAZ", "A-FURN",
    )

    CABLE_TYPE_RE = re.compile(
        r"^(?:N2X[A-Z]*|NHXMH|NA2XY|NYY|LIHCH|JE-H\s*\(St\)\s*H|CAT\s*6[A-Z]*|\d+\s*CORE\s*SM\s*F/O)(?:\s*FE\s*180)?(?:-[JO])?$",
        re.IGNORECASE
    )
    CROSS_SEC_RE = re.compile(
        r"^(?:\d+\s*\(\s*1\s*[xX*]\s*\d+\s*\)\s*\+\s*1\s*[xX*]\s*\d+|\d+\s*[xX*]\s*\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)?)$"
    )
    FULL_FEEDER_RE = re.compile(r"^(?:BS|HS|CS|DS|TS|FS)\d{2}[A-Z0-9_.-]+/[A-Z0-9_.-]+(?:/\d+)?$", re.IGNORECASE)

    @classmethod
    def should_ignore_block(cls, block_name: str) -> bool:
        clean_b = strip_revit_view_suffix(block_name)
        for pat in cls.IGNORE_BLOCK_PATTERNS:
            if pat.search(clean_b) or pat.search(block_name):
                return True
        return False

    @classmethod
    def is_container_block(cls, block_name: str, block_def: Any) -> bool:
        if not block_def:
            return False

        if "FloorPlan-" in block_name:
            has_mtext = any(e.dxftype() in ("TEXT", "MTEXT") for e in block_def)
            ent_count = sum(1 for _ in block_def)
            return has_mtext or ent_count > 15

        for pat in cls.CONTAINER_PATTERNS:
            if pat.search(block_name):
                return True

        insert_count = 0
        text_count = 0
        total_ents = 0
        min_x, min_y = float("inf"), float("inf")
        max_x, max_y = float("-inf"), float("-inf")

        for e in block_def:
            total_ents += 1
            dtype = e.dxftype()
            if dtype == "INSERT":
                insert_count += 1
            elif dtype in ("TEXT", "MTEXT"):
                text_count += 1
            try:
                if hasattr(e.dxf, "start"):
                    min_x = min(min_x, e.dxf.start.x)
                    max_x = max(max_x, e.dxf.start.x)
                    min_y = min(min_y, e.dxf.start.y)
                    max_y = max(max_y, e.dxf.start.y)
                elif hasattr(e.dxf, "insert"):
                    min_x = min(min_x, e.dxf.insert.x)
                    max_x = max(max_x, e.dxf.insert.x)
                    min_y = min(min_y, e.dxf.insert.y)
                    max_y = max(max_y, e.dxf.insert.y)
            except Exception:
                pass

        diagonal = math.hypot(max_x - min_x, max_y - min_y) if min_x != float("inf") else 0.0
        return diagonal > 5000.0 or insert_count >= 3 or total_ents > 500 or text_count >= 10

    @classmethod
    def extract_cable_callouts_from_floorplan(
        cls, bname: str, blk_def: Any, combined_mat: Matrix44
    ) -> List[CalloutGroup]:
        groups: List[CalloutGroup] = []
        mtexts = []
        for e in blk_def:
            if e.dxftype() in ("TEXT", "MTEXT"):
                val = clean_turkish_text(e.text if e.dxftype() == "MTEXT" else e.dxf.text)
                if val:
                    w_pos = combined_mat.transform(Vec3(e.dxf.insert.x, e.dxf.insert.y, 0.0))
                    mtexts.append((w_pos.x, w_pos.y, val, e.dxf.layer))

        idx = 0
        n = len(mtexts)
        while idx < n:
            x, y, val, lay = mtexts[idx]
            if cls.CABLE_TYPE_RE.match(val) and idx + 2 < n:
                c_type = val
                c_sec = mtexts[idx + 1][2] if cls.CROSS_SEC_RE.match(mtexts[idx + 1][2]) else ""
                c_short = mtexts[idx + 2][2] if idx + 2 < n else ""
                c_full = ""
                step = 3
                if idx + 3 < n and cls.FULL_FEEDER_RE.match(mtexts[idx + 3][2]):
                    c_full = mtexts[idx + 3][2]
                    step = 4

                feeder_panel = ""
                m_fp = re.match(r"^[A-Z]{1,2}(S\d{2})([A-Zİ_-]+?)(\d{3})/", c_full, re.IGNORECASE)
                if m_fp:
                    st_c, p_type, p_num = m_fp.group(1).upper(), m_fp.group(2).upper(), m_fp.group(3)
                    if p_type in ("İAPN", "IAPN"):
                        p_type = "İAP-N"
                    elif p_type in ("İAPE", "IAPE"):
                        p_type = "İAP-E"
                    elif p_type == "UPSG":
                        p_type = "UPS-G"
                    elif p_type == "UPSH":
                        p_type = "UPS-H"
                    feeder_panel = f"{st_c}/{p_type}/{p_num}"

                groups.append(CalloutGroup(
                    lines=[l for l in (c_type, c_sec, c_short, c_full) if l],
                    pos=(x, y),
                    layer=lay,
                    parent_block=bname,
                    category="CABLE_TAG",
                    metadata={
                        "cable_type": c_type,
                        "cross_section": c_sec.replace(",", "."),
                        "circuit_id": c_short,
                        "full_code": c_full,
                        "feeder_panel": feeder_panel,
                    }
                ))
                idx += step
            else:
                idx += 1

        return groups

    @classmethod
    def flatten_scene(
        cls, doc: Any, sheet_discipline: str = "", max_depth: int = 5
    ) -> Tuple[List[PlacedSymbol], List[TextToken], List[Dict[str, Any]], List[ExtractedTable], List[CalloutGroup], List[SubPlanZone]]:
        msp = doc.modelspace()
        symbols: List[PlacedSymbol] = []
        raw_tokens: List[TextToken] = []
        raw_geoms: List[Dict[str, Any]] = []
        tables: List[ExtractedTable] = []
        floorplan_callouts: List[CalloutGroup] = []
        zone_bounds_map: Dict[str, List[Tuple[float, float]]] = {}

        is_weak_current_sheet = "ZAYIF_AKIM" in sheet_discipline

        def _record_zone_pt(zone_name: str, x: float, y: float):
            if zone_name:
                zone_bounds_map.setdefault(zone_name, []).append((x, y))

        def _extract_zone_name(tag_chain: str) -> str:
            m = re.search(r"rvt-\d+-(.+?)(?:\s*>|$)", tag_chain)
            if m:
                return m.group(1).strip()
            for part in tag_chain.split(">"):
                p_clean = part.strip()
                if any(k in p_clean.upper() for k in ["BİLET", "PERON", "KUYU", "DRENAJ", "DÖŞEME", "YBS", "YERLE"]):
                    return p_clean
            return ""

        def _traverse_entities(entities: Any, current_matrix: Matrix44, parent_tag: str, depth: int, owner_block: str = "MODELSPACE"):
            if depth > max_depth:
                return

            is_inside_arc_xref = "M3-ARC" in parent_tag.upper()
            is_inside_tav_xref = "-TAV " in parent_tag.upper()
            is_inside_floorplan_dwg = "FLOORPLAN-" in parent_tag.upper()
            active_zone = _extract_zone_name(parent_tag)

            for ent in entities:
                dxftype = ent.dxftype()
                ent_handle = getattr(ent.dxf, "handle", "")

                if dxftype in ("TEXT", "MTEXT"):
                    raw_val = ent.dxf.text if dxftype == "TEXT" else ent.text
                    clean_val = clean_turkish_text(raw_val)
                    if not clean_val:
                        continue

                    ins = ent.dxf.insert
                    local_vec = Vec3(ins.x, ins.y, getattr(ins, "z", 0.0))
                    w_pos = current_matrix.transform(local_vec)
                    _record_zone_pt(active_zone, w_pos.x, w_pos.y)

                    h = getattr(ent.dxf, "height", 2.5)
                    rot = getattr(ent.dxf, "rotation", 0.0)
                    layer = ent.dxf.layer
                    color = getattr(ent.dxf, "color", 256)

                    bbox = TextReconstructionEngine.create_text_bbox((w_pos.x, w_pos.y), clean_val, h, rot)
                    raw_tokens.append(TextToken(
                        text=clean_val,
                        pos=(w_pos.x, w_pos.y, w_pos.z),
                        height=h,
                        rotation=rot,
                        layer=layer,
                        color=color,
                        bbox=bbox,
                        parent_block=parent_tag,
                        dxf_handle=ent_handle,
                        source_handles=[ent_handle] if ent_handle else [],
                        owner_block=owner_block,
                    ))

                elif dxftype == "INSERT":
                    bname = clean_turkish_text(ent.dxf.name)
                    if cls.should_ignore_block(bname):
                        continue

                    blk_def = doc.blocks.get(ent.dxf.name)
                    is_xref_blk = bool(
                        (blk_def and (getattr(blk_def, "is_xref", False) or getattr(blk_def, "is_xref_overlay", False)))
                        or "XREF" in bname.upper()
                        or is_inside_arc_xref
                    )

                    ins = ent.dxf.insert
                    sx = getattr(ent.dxf, "xscale", 1.0)
                    sy = getattr(ent.dxf, "yscale", 1.0)
                    sz = getattr(ent.dxf, "zscale", 1.0)
                    rot = getattr(ent.dxf, "rotation", 0.0)

                    ent_mat = Matrix44.chain(
                        Matrix44.scale(sx, sy, sz),
                        Matrix44.z_rotate(math.radians(rot)),
                        Matrix44.translate(ins.x, ins.y, getattr(ins, "z", 0.0)),
                    )
                    combined_mat = ent_mat * current_matrix

                    attribs_dict = {}
                    if hasattr(ent, "attribs"):
                        for att in ent.attribs:
                            at_tag = att.dxf.tag.upper().strip()
                            at_val = clean_turkish_text(att.dxf.text)
                            att_handle = getattr(att.dxf, "handle", "")
                            if at_val:
                                attribs_dict[at_tag] = at_val
                                att_ins = att.dxf.insert
                                att_w = combined_mat.transform(Vec3(att_ins.x, att_ins.y, 0.0))
                                raw_tokens.append(TextToken(
                                    text=at_val,
                                    pos=(att_w.x, att_w.y, att_w.z),
                                    height=getattr(att.dxf, "height", 2.0),
                                    rotation=getattr(att.dxf, "rotation", 0.0),
                                    layer=att.dxf.layer,
                                    color=getattr(att.dxf, "color", 256),
                                    bbox=TextReconstructionEngine.create_text_bbox((att_w.x, att_w.y), at_val, 2.0, 0.0),
                                    parent_block=bname,
                                    is_attribute=True,
                                    attrib_tag=at_tag,
                                    dxf_handle=att_handle,
                                    source_handles=[att_handle] if att_handle else [],
                                    owner_block=ent_handle or owner_block,
                                ))

                    if "METRAJ" in bname.upper() and blk_def:
                        xy_texts = []
                        for be in blk_def:
                            if be.dxftype() in ("TEXT", "MTEXT"):
                                t_str = clean_turkish_text(be.text if be.dxftype() == "MTEXT" else be.dxf.text)
                                if t_str:
                                    xy_texts.append((be.dxf.insert.x, be.dxf.insert.y, t_str))
                        extracted_tbl = GeometricTableExtractor.extract_grid_table(
                            name=bname,
                            xy_texts=xy_texts,
                            header_keywords=("LİNYE", "KABLO", "UZUNLUK", "SİSTEM", "GENİŞLİK"),
                            row_tol=4.5,
                            source_space="MODEL_BLOCK",
                        )
                        if extracted_tbl:
                            tables.append(extracted_tbl)
                        continue

                    if "FloorPlan-" in bname and blk_def:
                        if cls.is_container_block(bname, blk_def):
                            fp_callouts = cls.extract_cable_callouts_from_floorplan(bname, blk_def, combined_mat)
                            floorplan_callouts.extend(fp_callouts)
                            new_parent = f"{parent_tag} > {bname}" if parent_tag else bname
                            _traverse_entities(blk_def, combined_mat, new_parent, depth + 1, owner_block=ent.dxf.name)
                        continue

                    if cls.is_container_block(bname, blk_def):
                        if blk_def:
                            new_parent = f"{parent_tag} > {bname}" if parent_tag else bname
                            _traverse_entities(blk_def, combined_mat, new_parent, depth + 1, owner_block=ent.dxf.name)
                    else:
                        if is_inside_arc_xref or is_inside_floorplan_dwg:
                            continue
                        if is_weak_current_sheet and is_inside_tav_xref:
                            continue

                        ent_lay_up = ent.dxf.layer.upper().strip()
                        if ent_lay_up in cls.ARCHITECTURAL_IGNORE_LAYERS or any(
                            k in ent_lay_up for k in ("DUVAR", "TEFRS", "TEFRIS", "MOBILYA", "CERCEVE", "DKAPIPENCERE")
                        ):
                            continue
                        if any(p_skip in parent_tag.upper() for p_skip in ("BSL50", "ANTET", "A$C")):
                            continue

                        w_pos = combined_mat.transform(Vec3(0, 0, 0))
                        _record_zone_pt(active_zone, w_pos.x, w_pos.y)
                        sym_box = box(w_pos.x - 200, w_pos.y - 200, w_pos.x + 200, w_pos.y + 200)
                        clean_fam = strip_revit_view_suffix(bname)

                        symbols.append(PlacedSymbol(
                            block_name=bname,
                            clean_family_name=clean_fam,
                            pos=(w_pos.x, w_pos.y, w_pos.z),
                            scale=(sx, sy, sz),
                            rotation=rot,
                            layer=ent.dxf.layer,
                            color=getattr(ent.dxf, "color", 256),
                            bbox=sym_box,
                            attribs=attribs_dict,
                            parent_view=parent_tag,
                            sub_zone=active_zone,
                            dxf_handle=ent_handle,
                            owner_block=owner_block,
                            is_xref=is_xref_blk,
                        ))

                elif dxftype in ("LINE", "ARC", "LWPOLYLINE", "POLYLINE"):
                    if is_inside_arc_xref:
                        continue
                    lay = ent.dxf.layer.upper()
                    if (
                        is_inside_floorplan_dwg
                        or any(kw in lay for kw in ELECTRICAL_LINE_KEYWORDS)
                        or lay in ("0", "DEFPOINTS")
                    ):
                        raw_geoms.append({
                            "entity": ent,
                            "matrix": current_matrix,
                            "parent": parent_tag,
                            "layer": ent.dxf.layer,
                            "color": getattr(ent.dxf, "color", 256),
                            "linetype": getattr(ent.dxf, "linetype", "BYLAYER"),
                            "owner_block": owner_block,
                        })

        _traverse_entities(msp, Matrix44(), "", depth=0, owner_block="MODELSPACE")

        sub_plans: List[SubPlanZone] = []
        for z_name, pts in zone_bounds_map.items():
            if len(pts) < 2:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            minx, maxx = min(xs), max(xs)
            miny, maxy = min(ys), max(ys)
            z_up = z_name.upper()
            z_type = "PLAN"
            if "DÖŞEME" in z_up or "ALTI" in z_up:
                z_type = "UNDERFLOOR"
            elif "KUYU" in z_up or "LF_" in z_up or "ŞAFT" in z_up:
                z_type = "SHAFT"
            elif "DRENAJ" in z_up or "ÇUKUR" in z_up:
                z_type = "SUMP_PIT"

            poly = box(minx, miny, maxx, maxy)
            sym_cnt = sum(1 for s in symbols if s.sub_zone == z_name)
            sub_plans.append(SubPlanZone(
                name=z_name,
                bounds=(round(minx, 1), round(miny, 1), round(maxx, 1), round(maxy, 1)),
                polygon=poly,
                zone_type=z_type,
                symbol_count=sym_cnt,
            ))

        return symbols, raw_tokens, raw_geoms, tables, floorplan_callouts, sub_plans


class UniversalCADReader:
    def __init__(self, use_cache: bool = True):
        self.use_cache = use_cache

    def read(self, drawing_path: Union[str, Path], explicit_station_code: Optional[str] = None) -> DrawingSceneGraph:
        p = Path(drawing_path).resolve()
        logger.info(f"Evrensel CAD Okuyucu başlatıldı: {p.name}")

        dxf_path = ensure_dxf(p, use_cache=self.use_cache)
        if not is_valid_dxf(dxf_path):
            raise RuntimeError(f"DXF dosyası geçersiz veya bozuk: {dxf_path}")

        doc = ezdxf.readfile(dxf_path)
        fn_up = p.name.upper()
        prelim_disc = "03_ZAYIF_AKIM" if any(k in fn_up for k in ["AX-02", "TL-", "USK", "ELM"]) else ""

        # 1. ModelSpace sahnesini matris dönüşümleriyle aç
        symbols, raw_tokens, raw_geoms, msp_tables, fp_callouts, sub_plans = BlockHierarchyFlattener.flatten_scene(
            doc, sheet_discipline=prelim_disc
        )

        # 2. ModelSpace metin parçalarını uzamsal olarak birleştir
        stitched_tokens = TextReconstructionEngine.stitch_horizontal_tokens(raw_tokens, is_paperspace=False)

        # 3. PaperSpace Antet, Görünüm Başlıkları ve PaperSpace Tablolarını çıkar (Strict Hierarchy)
        title_info, ps_tables, ps_view_zones = SpatialZoneMapper.parse_title_and_paperspace_tables(
            doc, stitched_tokens, file_path=p, explicit_station_code=explicit_station_code
        )
        all_tables = msp_tables + ps_tables
        all_sub_plans = sub_plans if sub_plans else ps_view_zones
        if not all_sub_plans:
            all_sub_plans = SpatialZoneMapper.detect_modelspace_frames(doc.modelspace(), stitched_tokens, symbols)
            for s in symbols:
                if not s.sub_zone:
                    for sp in all_sub_plans:
                        if sp.bounds[0] <= s.pos[0] <= sp.bounds[2] and sp.bounds[1] <= s.pos[1] <= sp.bounds[3]:
                            s.sub_zone = sp.name
                            break

        # 4. Alt alta dizili mühendislik etiketlerini grupla
        callouts = TextReconstructionEngine.group_vertical_callouts(stitched_tokens, fp_callouts)

        # 5. Sembol sözlüğü (Lejant) çıkar
        sym_dict = SpatialZoneMapper.extract_symbol_dictionary(stitched_tokens, symbols)

        # 6. Sembolleri 4 kanıtla sınıflandır, güven puanı ve kanıt zinciri ata
        for s in symbols:
            MultiEvidenceClassifier.classify_and_enrich_symbol(s, sym_dict)

        # 6.b Sınıflandırılamayanları kanıtlı triyaj et (mimari kanıtlıysa ayır, elektrik izi varsa belirsizlikte tut)
        triage_counts = SymbolTriage.triage(symbols, stitched_tokens)

        # 7. Fiziksel kablo ve tava güzergahlarını birleştir
        routes = PhysicalRouteBuilder.build_physical_routes(raw_geoms)

        # 8. Linye devrelerini bağla ve güven puanı ata
        logical_circuits = LogicalCircuitResolver.resolve_circuits(
            station_code=title_info["station_code"],
            symbols=symbols,
            tokens=stitched_tokens,
            floorplan_callouts=fp_callouts,
            all_callouts=callouts,
            tables=all_tables,
            sub_plans=all_sub_plans,
        )

        scene = DrawingSceneGraph(
            filepath=str(p),
            filename=p.name,
            station_code=title_info["station_code"],
            station_name=title_info.get("station_name", ""),
            sheet_title=title_info["sheet_title"],
            system_discipline=title_info["system_discipline"],
            floor_name=title_info["floor_name"],
            elevation_kot=title_info["elevation_kot"],
            sub_plans=all_sub_plans,
            symbol_dictionary=sym_dict,
            symbols=symbols,
            texts=stitched_tokens,
            callouts=callouts,
            tables=all_tables,
            physical_routes=routes,
            logical_circuits=logical_circuits,
            raw_stats={
                "total_symbols": len(symbols),
                "total_texts": len(stitched_tokens),
                "total_callouts": len(callouts),
                "total_tables": len(all_tables),
                "total_sub_plans": len(all_sub_plans),
                "total_routes": len(routes),
                "total_logical_circuits": len(logical_circuits),
                "legend_entry_count": len(sym_dict),
                "title_mismatch_warning": title_info.get("title_mismatch_warning", ""),
                "symbol_triage": triage_counts,
            }
        )

        logger.info(f"✓ '{p.name}' başarıyla işlendi: {len(symbols)} sembol, {len(logical_circuits)} linye.")
        return scene
