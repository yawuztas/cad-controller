# -*- coding: utf-8 -*-
"""
Aşama 1E — Evrensel Topoloji (Şema Grafı) ve Topraklama Geometri Çıkarıcı
===========================================================================
Sabit koordinat kutuları, pano isimleri veya "4 köşeli bina" varsayımları
OLMADAN metre birimine normalize edilmiş geometriden:
1. Kolon / Tek Hat Şemaları için T-kavşak ve uç temaslı NetworkX grafı (`SchematicGraph`)
2. Temel Topraklaması için `edgeminer` + `Shapely` ile kapalı ring poligonları,
   iç şeritler ve temas eden tüm filizler (`GroundingLoop`)
üretir.
"""

from __future__ import annotations
import math
import statistics
from typing import Any, Dict, List, Optional, Set, Tuple

from ezdxf import edgeminer
import networkx as nx
from shapely.geometry import LineString, MultiLineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

from .disiplin_ayirici import extract_grounding_material_specs
from .metin_temizleyici import norm_tr
from .schema import (
    GroundingLoop,
    LegendEntry,
    RawInsert,
    RawPath,
    RawText,
    SchematicEdge,
    SchematicGraph,
    SchematicNode,
    SheetFrame,
    UnitCalibration,
)


def _paths_to_meter_segments(
    paths: List[RawPath],
    du_to_m: float,
    frame: SheetFrame,
) -> List[Tuple[LineString, RawPath]]:
    """Pafta çerçeve kenarı dışındaki çizgisel yolları metre cinsinden LineString segmentlerine çevirir."""
    f_w_m = frame.bbox_m.width
    f_h_m = frame.bbox_m.height
    segs: List[Tuple[LineString, RawPath]] = []

    for p in paths:
        if p.dxftype not in ("LINE", "LWPOLYLINE", "POLYLINE", "SPLINE", "ARC"):
            continue
        if p.handle and p.handle in (frame.border_handle or ""):
            continue
        # Pafta sınırını kaplayan dev dikdörtgenleri atla
        p_w_m = p.bbox.width * du_to_m
        p_h_m = p.bbox.height * du_to_m
        if p.closed and p_w_m > 0.85 * f_w_m and p_h_m > 0.85 * f_h_m:
            continue
        if len(p.points) < 2:
            continue
        pts_m = [(x * du_to_m, y * du_to_m) for x, y in p.points]
        for i in range(len(pts_m) - 1):
            p1, p2 = pts_m[i], pts_m[i + 1]
            ls = LineString([p1, p2])
            if ls.length >= 1e-4:
                segs.append((ls, p))
        if p.closed and pts_m[0] != pts_m[-1]:
            ls = LineString([pts_m[-1], pts_m[0]])
            if ls.length >= 1e-4:
                segs.append((ls, p))
    return segs


def extract_schematic_graphs(
    sheets: List[SheetFrame],
    paths_by_frame: Dict[str, List[RawPath]],
    texts_by_frame: Dict[str, List[RawText]],
    inserts_by_frame: Dict[str, List[RawInsert]],
    unit: UnitCalibration,
) -> List[SchematicGraph]:
    """KOLON_SEMASI / TEK_HAT paftalarından düğüm-kenar topolojik şema grafı çıkarır."""
    graphs: List[SchematicGraph] = []
    du_to_m = unit.du_to_m
    g_idx = 0

    for sh in sheets:
        if sh.role not in ("KOLON_SEMASI", "TEK_HAT"):
            continue
        f_paths = paths_by_frame.get(sh.frame_id, [])
        f_texts = texts_by_frame.get(sh.frame_id, [])
        f_inserts = inserts_by_frame.get(sh.frame_id, [])

        heights_m = [t.height * du_to_m for t in f_texts if t.height > 0]
        h_med_m = statistics.median(heights_m) if heights_m else 0.15
        snap_tol = max(0.40 * h_med_m, 0.04)

        raw_segs = _paths_to_meter_segments(f_paths, du_to_m, sh)
        # Formül/sembol içi minik çizgileri (< 0.15m veya tablo kenarları değil, gerçek hatları koru)
        wire_segs = [(ls, rp) for ls, rp in raw_segs if ls.length >= max(0.5 * h_med_m, 0.08)]
        if not wire_segs:
            continue

        # Uç noktaları tolerans içinde kuantize ederek başlangıç düğümleri oluştur
        def _q(pt: Tuple[float, float]) -> Tuple[float, float]:
            step = snap_tol
            return (round(pt[0] / step) * step, round(pt[1] / step) * step)

        nx_g = nx.Graph()
        seg_geoms: List[LineString] = []
        for ls, rp in wire_segs:
            c0 = _q((ls.coords[0][0], ls.coords[0][1]))
            c1 = _q((ls.coords[-1][0], ls.coords[-1][1]))
            if c0 == c1:
                continue
            seg_geoms.append(ls)
            if nx_g.has_edge(c0, c1):
                nx_g[c0][c1]["handles"].add(rp.handle)
            else:
                nx_g.add_edge(c0, c1, handles={rp.handle} if rp.handle else set(), length_m=ls.length, geom=ls)

        # T-kavşakları (bir segmentin ucunun başka bir segment gövdesine dokunması) bağla
        if seg_geoms:
            edge_items = list(nx_g.edges(data=True))
            edge_geoms = [d["geom"] for _, _, d in edge_items]
            tree = STRtree(edge_geoms)
            for node_xy in list(nx_g.nodes()):
                nx0, ny0 = node_xy
                p_obj = Point(node_xy)
                q_box = box(nx0 - snap_tol, ny0 - snap_tol, nx0 + snap_tol, ny0 + snap_tol)
                for ci in tree.query(q_box):
                    u, v, data = edge_items[int(ci)]
                    if node_xy in (u, v):
                        continue
                    if data["geom"].distance(p_obj) <= snap_tol:
                        # T-kavşak bağı ekle
                        nx_g.add_edge(node_xy, u, handles=set(), length_m=p_obj.distance(Point(u)), geom=LineString([node_xy, u]))

        # Metinleri en yakın kenar veya düğüme bağla (STRtree ile O(N log M))
        edge_list_final = list(nx_g.edges(data=True))
        final_geoms = [d["geom"] for _, _, d in edge_list_final if "geom" in d]
        edge_tree = STRtree(final_geoms) if final_geoms else None
        edge_texts_map: Dict[Tuple[Tuple[float, float], Tuple[float, float]], List[str]] = {}
        node_texts_map: Dict[Tuple[float, float], List[str]] = {n: [] for n in nx_g.nodes()}

        node_list = [n for n in nx_g.nodes() if nx_g.degree(n) != 2]
        node_pts = [Point(n) for n in node_list]
        node_tree = STRtree(node_pts) if node_pts else None

        search_r = max(3.5 * h_med_m, 0.40)
        for t in f_texts:
            tx_m, ty_m = t.x * du_to_m, t.y * du_to_m
            tp = Point(tx_m, ty_m)
            t_box = box(tx_m - search_r, ty_m - search_r, tx_m + search_r, ty_m + search_r)
            best_node = None
            if node_tree is not None:
                n_hits = [int(i) for i in node_tree.query(t_box)]
                if n_hits:
                    best_ni = min(n_hits, key=lambda idx: node_pts[idx].distance(tp))
                    if node_pts[best_ni].distance(tp) < search_r:
                        best_node = node_list[best_ni]
            if best_node is not None:
                node_texts_map[best_node].append(t.text.strip())
            elif edge_tree is not None:
                hits = [int(i) for i in edge_tree.query(t_box)]
                if hits:
                    best_ei = min(hits, key=lambda idx: final_geoms[idx].distance(tp))
                    if final_geoms[best_ei].distance(tp) <= search_r:
                        u, v, _ = edge_list_final[best_ei]
                        edge_texts_map.setdefault((u, v), []).append(t.text.strip())

        # Düğüm ve kenar modellerini üret
        node_ids: Dict[Tuple[float, float], str] = {}
        s_nodes: List[SchematicNode] = []
        for idx, (n_xy, d) in enumerate(nx_g.nodes(data=True), 1):
            nid = f"N_{idx:03d}"
            node_ids[n_xy] = nid
            txts = node_texts_map.get(n_xy, [])
            joined = norm_tr(" ".join(txts))
            ntype = "UNKNOWN"
            if any(k in joined for k in ("TEDAS", "TR-", "TRAFO", "SEBEKE", "OG")):
                ntype = "UTILITY_INCOMER"
            elif any(k in joined for k in ("ASANSOR", "HIDROFOR", "POMPA", "FAN", "CHILLER", "MOTOR")):
                ntype = "LOAD_MOTOR"
            elif any(k in joined for k in ("PANO", "DT", "AT", "O-T", "KURULU GUC", "TALEP")):
                ntype = "PANEL"
            elif any(k in joined for k in ("AOS", "KAK", "TMŞ", "TMS", "KA")):
                ntype = "BREAKER"
            elif nx_g.degree(n_xy) >= 3:
                ntype = "JUNCTION"
            s_nodes.append(SchematicNode(
                node_id=nid,
                node_type=ntype,  # type: ignore[arg-type]
                label=txts[0] if txts else "",
                pos_m=(round(n_xy[0], 3), round(n_xy[1], 3)),
                texts=txts,
            ))

        s_edges: List[SchematicEdge] = []
        for e_idx, (u, v, data) in enumerate(edge_list_final, 1):
            txts = edge_texts_map.get((u, v)) or edge_texts_map.get((v, u)) or []
            s_edges.append(SchematicEdge(
                edge_id=f"E_{e_idx:03d}",
                source_node=node_ids[u],
                target_node=node_ids[v],
                path_handles=sorted(h for h in data.get("handles", set()) if h),
                texts_along_edge=txts,
                length_m=round(float(data.get("length_m", 0.0)), 3),
            ))

        g_idx += 1
        graphs.append(SchematicGraph(
            graph_id=f"SCH_{g_idx:02d}",
            sheet_id=sh.frame_id,
            nodes=s_nodes,
            edges=s_edges,
            connected_components=nx.number_connected_components(nx_g),
        ))

    return graphs


_NON_GROUNDING_LAYER_PREFIXES: Tuple[str, ...] = (
    "A-", "A_", "I-", "I_", "S-", "S_", "M-", "M_", "Q-", "P-", "F-",
    "G-ANNO", "G-IMPT", "G-PLAN", "PRT-MI", "YP_MI", "YP_UY", "_YP_UY",
)
_NON_GROUNDING_LAYER_KEYS: Tuple[str, ...] = (
    "ELKYAZ", "TABLO", "CERCEVE", "ANTET", "DUVAR", "WALL", "DOOR", "KAPI",
    "ARKA_PLAN", "CARTIGLIO",
    "WINDOW", "PENCERE", "FLOR", "DOSEME", "COLS", "FNDN", "BEAM", "STAIR",
    "MERDIVEN", "FURN", "TEFRIS", "SANR", "FACADE", "CLNG", "GLAZ", "DETL",
    "SECT", "HATCH", "TARAMA", "GRID", "HANDRAIL", "PROJECTION",
    "AX", "OLCU", "DIM", "TEXT", "YAZI", "ANNO", "BAG_HATILI",
)


def _is_non_grounding_layer(layer_name: str) -> bool:
    lu = norm_tr(layer_name).upper().strip()
    if lu.startswith(_NON_GROUNDING_LAYER_PREFIXES):
        return True
    return any(k in lu for k in _NON_GROUNDING_LAYER_KEYS)


def _find_grounding_layer_names(f_paths: List[RawPath], f_texts: List[RawText]) -> Set[str]:
    """Topraklama şerit katmanlarını ada veya elektrik iletken sinyaline göre tespit eder (mimari katmanları asla almaz)."""
    by_layer: Dict[str, List[RawPath]] = {}
    for p in f_paths:
        if p.dxftype in ("LINE", "LWPOLYLINE", "POLYLINE"):
            by_layer.setdefault(p.layer, []).append(p)

    # 1. Katman adında doğrudan topraklama/şerit sinyali olanlar (yazı/mimari hariç)
    named = {
        lay for lay in by_layer
        if not _is_non_grounding_layer(lay)
        and any(k in norm_tr(lay).upper() for k in ("TOPRAK", "SERIT", "TEMEL", "LAMA", "GND", "EARTHING"))
    }
    if named:
        return named

    # 2. Yedek: açıkça mimari/ölçü/statik/yazı olmayan, elektrik veya nötr ('0') iletken katmanları
    return {
        lay for lay in by_layer
        if not _is_non_grounding_layer(lay)
    }


def extract_grounding_loops(
    sheets: List[SheetFrame],
    paths_by_frame: Dict[str, List[RawPath]],
    texts_by_frame: Dict[str, List[RawText]],
    unit: UnitCalibration,
    inserts_by_frame: Optional[Dict[str, List[RawInsert]]] = None,
    legend: Optional[Dict[str, LegendEntry]] = None,
    legend_regions: Optional[List[Tuple[str, float, float, float, float]]] = None,
) -> List[GroundingLoop]:
    """
    TOPRAKLAMA paftalarından gerçek dış ring çevresi, alan, iç bağlantılar,
    temas eden tüm filizler ve saha topraklama çubuğu adedini (lokal lejant örnekleri
    hariç tutularak) `edgeminer` + `Shapely polygonize` ile çıkarır.
    """
    loops_out: List[GroundingLoop] = []
    du_to_m = unit.du_to_m
    l_idx = 0
    leg_regs = legend_regions or []

    def _in_legend_reg(fid: str, x: float, y: float) -> bool:
        return any(
            rfid == fid and x_lo <= x <= x_hi and y_bot <= y <= y_top
            for rfid, x_lo, x_hi, y_bot, y_top in leg_regs
        )

    for sh in sheets:
        if sh.role != "TOPRAKLAMA":
            continue
        sh_tu = norm_tr(sh.title).upper()
        if any(sk in sh_tu for sk in ("KOLON SEMASI", "TEK HAT", "ROGARI DETAY", "BARA DETAY", "MONTAJ DETAY")):
            continue
        f_paths = [
            p for p in paths_by_frame.get(sh.frame_id, [])
            if not _in_legend_reg(sh.frame_id, p.bbox.center[0], p.bbox.center[1])
        ]
        f_texts = texts_by_frame.get(sh.frame_id, [])
        gnd_layers = _find_grounding_layer_names(f_paths, f_texts)
        cand_paths = [p for p in f_paths if p.layer in gnd_layers]
        segs_with_meta = _paths_to_meter_segments(cand_paths, du_to_m, sh)
        if not segs_with_meta:
            continue

        def _extract_polys(lines_in: List[LineString]) -> List[Polygon]:
            merged_l = unary_union(lines_in)
            out_p = [p for p in polygonize(merged_l) if p.area >= 4.0]
            if not out_p and len(lines_in) <= 250:
                em_edges = [
                    edgeminer.make_edge(
                        (ls.coords[0][0], ls.coords[0][1]),
                        (ls.coords[-1][0], ls.coords[-1][1]),
                    )
                    for ls in lines_in
                    if ls.length >= 0.05
                ]
                if em_edges:
                    try:
                        deposit = edgeminer.Deposit(em_edges, gap_tol=0.12)
                        found_loops = edgeminer.find_all_loops(deposit, timeout=1.0)
                        for chain in found_loops:
                            pts = [(float(e.start.x), float(e.start.y)) for e in chain]
                            if len(pts) >= 3:
                                poly = Polygon(pts).buffer(0)
                                if poly.area >= 4.0:
                                    out_p.append(poly)
                    except edgeminer.TimeoutError:
                        pass
            return out_p

        all_lines = [ls for ls, _ in segs_with_meta]
        polys = _extract_polys(all_lines)

        # Bazı projelerde filizler TOPRAK katmanında iken ana ring "0" vb. nötr/elektrik katmanda çizilmiş olabilir:
        # Kapalı alan bulunamazsa mimari/statik olmayan nötr ve elektrik iletken katmanlarını da dene
        if not polys and "0" not in gnd_layers:
            extra_layers = {
                p.layer for p in f_paths
                if p.dxftype in ("LINE", "LWPOLYLINE", "POLYLINE")
                and not _is_non_grounding_layer(p.layer)
                and (
                    norm_tr(p.layer).upper().strip() == "0"
                    or any(ek in norm_tr(p.layer).upper() for ek in ("TOPRAK", "GND", "EAR", "SERIT", "LAMA", "E-", "PRT-EL", "YP-EL"))
                )
            }
            cand_paths = [p for p in f_paths if p.layer in (gnd_layers | extra_layers)]
            segs_with_meta = _paths_to_meter_segments(cand_paths, du_to_m, sh)
            if segs_with_meta:
                polys = _extract_polys([ls for ls, _ in segs_with_meta])

        if not polys:
            continue

        # En büyük dış ring poligon(lar)ı birleştir (iç içe bölmeler birleşerek dış sınırı verir)
        ring_union = unary_union(polys)
        outer_poly = (
            max(ring_union.geoms, key=lambda g: g.area)
            if ring_union.geom_type == "MultiPolygon"
            else ring_union
        )
        exterior_ring = LineString(outer_poly.exterior.coords)
        outer_perim_m = float(exterior_ring.length)
        area_m2 = float(outer_poly.area)
        d_eq_m = math.sqrt(4.0 * area_m2 / math.pi) if area_m2 > 0 else 0.0

        # İç bağlantılar vs Dışarı çıkan temas eden filizler
        inner_len_m = 0.0
        spur_count = 0
        spur_len_m = 0.0
        used_handles: Set[str] = set()
        used_layers: Set[str] = set()

        touch_tol_m = 0.12
        ring_tol_buf = exterior_ring.buffer(0.08)
        prep_ring_buf = prep(ring_tol_buf)
        prep_touch_env = prep(outer_poly.buffer(touch_tol_m))

        for rp in cand_paths:
            if len(rp.points) < 2:
                continue
            pts_m = [(x * du_to_m, y * du_to_m) for x, y in rp.points]
            ring_pts = pts_m + ([pts_m[0]] if rp.closed and pts_m[0] != pts_m[-1] else [])
            rp_line = LineString(ring_pts)
            if rp_line.length < 0.05:
                continue
            if not prep_touch_env.intersects(rp_line):
                continue

            if prep_ring_buf.covers(rp_line):
                if rp.handle:
                    used_handles.add(rp.handle)
                used_layers.add(rp.layer)
                continue

            if prep_ring_buf.disjoint(rp_line):
                non_ring_geom = rp_line
            else:
                # Dış halka sınırıyla çakışan (<= 8 cm sapmalı) segmentleri ele;
                # dik uzanan filiz ve iç şeritlerin uzunluğundan tıraşlama yapma.
                non_ring_segs = []
                for idx in range(len(ring_pts) - 1):
                    p0, p1 = ring_pts[idx], ring_pts[idx + 1]
                    if p0 == p1:
                        continue
                    seg = LineString([p0, p1])
                    if seg.length < 0.02 or prep_ring_buf.covers(seg):
                        continue
                    non_ring_segs.append(seg)

                if not non_ring_segs:
                    if rp.handle:
                        used_handles.add(rp.handle)
                    used_layers.add(rp.layer)
                    continue
                non_ring_geom = non_ring_segs[0] if len(non_ring_segs) == 1 else MultiLineString(non_ring_segs)

            # İçeride kalan kısım vs dışarı uzanan filiz kısmı
            inside_part = non_ring_geom.intersection(outer_poly)
            outside_part = non_ring_geom.difference(outer_poly)

            if not inside_part.is_empty and inside_part.length > 0.15:
                inner_len_m += float(inside_part.length)
                if rp.handle:
                    used_handles.add(rp.handle)
                used_layers.add(rp.layer)

            if not outside_part.is_empty and outside_part.length > 0.15:
                if rp_line.distance(exterior_ring) <= touch_tol_m:
                    spur_count += 1
                    spur_len_m += float(outside_part.length)
                    if rp.handle:
                        used_handles.add(rp.handle)
                    used_layers.add(rp.layer)

        l_idx += 1
        ring_plus_inner = round(outer_perim_m + inner_len_m, 2)
        total_m = outer_perim_m + inner_len_m + spur_len_m
        ring_spec, spur_spec = extract_grounding_material_specs(f_texts)

        rod_count: Optional[int] = None
        if inserts_by_frame is not None:
            f_inserts = [
                ins for ins in inserts_by_frame.get(sh.frame_id, [])
                if not ins.is_xref and not _in_legend_reg(sh.frame_id, ins.x, ins.y)
            ]
            rod_hits = 0
            for ins in f_inserts:
                bname = ins.effective_name or ins.block_name
                leg_entry = (legend or {}).get(bname) or (legend or {}).get(bname.strip())
                desc_u = norm_tr(leg_entry.description).upper() if leg_entry else ""
                blk_u = norm_tr(bname).upper()
                if (
                    any(k in desc_u for k in ("TOPRAKLAMA CUB", "TOPRAKALAMA CUB", "BAKIR CUBUK", "ELECTRODE"))
                    or blk_u in ("1TP", "GND_ROD", "TP", "RODS", "T_CUBUK")
                ):
                    rod_hits += 1
            rod_count = rod_hits

        loops_out.append(GroundingLoop(
            loop_id=f"GND_{l_idx:02d}",
            sheet_id=sh.frame_id,
            outer_perimeter_m=round(outer_perim_m, 2),
            area_m2=round(area_m2, 2),
            equivalent_diameter_m=round(d_eq_m, 2),
            inner_conductors_m=round(inner_len_m, 2),
            ring_plus_inner_m=ring_plus_inner,
            ring_conductor_spec=ring_spec,
            spur_count=spur_count,
            spur_total_m=round(spur_len_m, 2),
            spur_conductor_spec=spur_spec,
            rod_block_count=rod_count,
            total_conductor_m=round(total_m, 2),
            layer_names=sorted(used_layers),
            source_handles=sorted(used_handles),
        ))

    return loops_out
