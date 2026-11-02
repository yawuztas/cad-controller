# -*- coding: utf-8 -*-
"""
Mantıksal Devre ve Linye Çözümleme Motoru (LogicalCircuitResolver)
=================================================================
Mühendislik etiketlerini, armatür ve priz sembollerini Öklid ağacı (STRtree)
ve Minimum Spanning Tree (MST) ile bağlar; güven puanlarını atar.
"""

from __future__ import annotations
import re
import networkx as nx
from typing import List, Dict, Tuple, Optional, Any
from shapely.geometry import Point
from shapely.strtree import STRtree

from ..model.entities import PlacedSymbol, TextToken, CalloutGroup, ExtractedTable, LogicalCircuit, SubPlanZone


class LogicalCircuitResolver:
    @classmethod
    def resolve_circuits(
        cls,
        station_code: str,
        symbols: List[PlacedSymbol],
        tokens: List[TextToken],
        floorplan_callouts: List[CalloutGroup],
        all_callouts: Optional[List[CalloutGroup]] = None,
        tables: Optional[List[ExtractedTable]] = None,
        sub_plans: Optional[List[SubPlanZone]] = None,
    ) -> List[LogicalCircuit]:
        cable_by_circuit: Dict[str, Dict[str, Any]] = {}
        combined_callouts = list(floorplan_callouts or []) + list(all_callouts or [])
        for cc in combined_callouts:
            if cc.category == "CABLE_TAG":
                cid_norm = re.sub(r"[^A-Z0-9]", "", cc.metadata.get("circuit_id", "").upper())
                if cid_norm and cid_norm not in cable_by_circuit:
                    cable_by_circuit[cid_norm] = cc.metadata

        tag_regex = re.compile(r"\b(CDB|PE|[AEKP])(\d{3})(\d{2})/(\d{2})/(L[123])\b", re.IGNORECASE)

        table_len_by_circuit: Dict[str, float] = {}
        table_cable_by_circuit: Dict[str, Dict[str, str]] = {}
        table_power_by_circuit: Dict[str, float] = {}
        if tables:
            for tb in tables:
                for row in tb.rows:
                    l_no = row.get("LİNYE NO", "") or row.get("LİNYE", "") or row.get("DEVRE NO", "")
                    if not l_no:
                        continue
                    l_norm = re.sub(r"[^A-Z0-9]", "", l_no.upper())
                    if not l_norm:
                        continue
                    candidate_keys = [l_norm]
                    m_tr = tag_regex.search(l_no)
                    if m_tr:
                        candidate_keys.append(f"{m_tr.group(1).upper()}{m_tr.group(2)}{m_tr.group(3)}")

                    u_str = row.get("UZUNLUK (m)", "") or row.get("UZUNLUK", "") or row.get("BOY (m)", "")
                    if u_str:
                        m_len = re.search(r"(\d+(?:\.\d+)?)", u_str.replace(",", "."))
                        if m_len:
                            for ck in candidate_keys:
                                table_len_by_circuit[ck] = float(m_len.group(1))
                    k_sec = row.get("KABLO KESİTİ", "") or row.get("KESİT", "") or row.get("KABLO", "")
                    k_typ = row.get("KABLO TİPİ", "") or row.get("YALITIM", "")
                    if k_sec:
                        for ck in candidate_keys:
                            table_cable_by_circuit[ck] = {"cross_section": k_sec.strip(), "cable_type": k_typ.strip()}
                    p_str = row.get("GÜÇ (W)", "") or row.get("TOPLAM GÜÇ (W)", "") or row.get("TOPLAM GÜÇ", "") or row.get("GÜÇ", "")
                    if p_str:
                        m_pw = re.search(r"(\d+(?:\.\d+)?)", p_str.replace(",", "."))
                        if m_pw:
                            for ck in candidate_keys:
                                table_power_by_circuit[ck] = float(m_pw.group(1))

        target_syms = [s for s in symbols if s.classification in ("LUMINAIRE", "SOCKET")]
        logical_list: List[LogicalCircuit] = []

        if target_syms:
            circuit_tokens = []
            for t in tokens:
                m = tag_regex.search(t.text)
                if m:
                    circuit_tokens.append((
                        t,
                        m.group(1).upper(),
                        m.group(2),
                        m.group(3),
                        m.group(5).upper(),
                    ))

            is_building_style = False
            if not circuit_tokens:
                bldg_regex = re.compile(r"^(P|A|L)(\d+)$", re.IGNORECASE)
                for t in tokens:
                    txt = t.text.strip().upper()
                    m = bldg_regex.match(txt)
                    if m or txt in ("FIRIN", "FİRİN", "KOMBİ", "KOMBI", "BULAŞIK", "ÇAMAŞIR"):
                        p_pref = m.group(1).upper() if m else "P"
                        c_num = m.group(2) if m else txt
                        fl_zone_name = "GENEL_KAT"
                        if sub_plans:
                            for sp in sub_plans:
                                if sp.bounds[0] <= t.pos[0] <= sp.bounds[2] and sp.bounds[1] <= t.pos[1] <= sp.bounds[3]:
                                    fl_zone_name = sp.name
                                    break
                        circuit_tokens.append((
                            t,
                            p_pref,
                            fl_zone_name,
                            c_num,
                            "L1",
                        ))
                if circuit_tokens:
                    is_building_style = True

            if circuit_tokens:
                lum_syms = [s for s in target_syms if s.classification == "LUMINAIRE"]
                sock_syms = [s for s in target_syms if s.classification == "SOCKET"]
                sym_points = [Point(s.pos[0], s.pos[1]) for s in target_syms]
                tree = STRtree(sym_points)
                lum_points = [Point(s.pos[0], s.pos[1]) for s in lum_syms]
                lum_tree = STRtree(lum_points) if lum_points else None
                sock_points = [Point(s.pos[0], s.pos[1]) for s in sock_syms]
                sock_tree = STRtree(sock_points) if sock_points else None

                circuits_dict: Dict[Tuple[str, str, str], List[Tuple[PlacedSymbol, float, str]]] = {}

                for tok, p_prefix, zone, c_no, phase in circuit_tokens:
                    tok_pt = Point(tok.pos[0], tok.pos[1])
                    c_conf = 1.0
                    c_ev = ""

                    if is_building_style:
                        if p_prefix in ("A", "L") and lum_tree is not None:
                            n_idx = lum_tree.nearest(tok_pt)
                            if n_idx is None:
                                continue
                            best_sym = lum_syms[int(n_idx)]
                            dist_mm = tok_pt.distance(lum_points[int(n_idx)])
                            c_ev = "Aydınlatma linyesi en yakın armatüre bağlandı"
                        elif sock_tree is not None:
                            n_idx = sock_tree.nearest(tok_pt)
                            if n_idx is None:
                                continue
                            best_sym = sock_syms[int(n_idx)]
                            dist_mm = tok_pt.distance(sock_points[int(n_idx)])
                            c_ev = "Priz linyesi en yakın prize bağlandı"
                        else:
                            continue

                        if dist_mm > 350.0:
                            continue

                        c_conf = 1.0 if dist_mm <= 120.0 else (0.85 if dist_mm <= 250.0 else 0.70)
                        short_fl = zone.replace("KUVVETLİ AKIM VE AYDINLATMA TESİSAT PLANI", "").strip() or zone
                        panel_key = f"TABLO ({short_fl})"
                        short_circuit_code = f"{p_prefix}{c_no}" if p_prefix != c_no else c_no
                    else:
                        nearest_idx = tree.nearest(tok_pt)
                        if nearest_idx is None:
                            continue
                        best_sym = target_syms[int(nearest_idx)]
                        dist_mm = tok_pt.distance(sym_points[int(nearest_idx)])
                        if dist_mm > 3500.0:
                            continue

                        c_conf = 1.0 if dist_mm <= 1200.0 else 0.85
                        c_ev = f"Revit hiyerarşik linye kodu {dist_mm:.0f}mm mesafedeki armatür/prize bağlandı"

                        if p_prefix in ("A", "P"):
                            panel_key = f"{station_code}/İAP-N/{zone}"
                        elif p_prefix in ("E", "PE"):
                            panel_key = f"{station_code}/İAP-E/{zone}"
                        elif p_prefix == "CDB":
                            panel_key = f"{station_code}/CDB/{zone}"
                        else:
                            panel_key = f"{station_code}/İAP-{p_prefix}/{zone}"
                        short_circuit_code = f"{p_prefix}{zone}-{c_no}"

                    best_sym.circuit_tag = f"{panel_key} | {short_circuit_code} ({phase})"
                    key = (panel_key, short_circuit_code, phase)
                    circuits_dict.setdefault(key, []).append((best_sym, c_conf, c_ev))

                # Çizim üzerindeki açık kablo kesit yazıları için uzamsal arama hazırlığı
                cable_text_re = re.compile(
                    r"\b(\d+\s*[xX*]\s*\d+(?:[.,]\d+)?(?:\s*[+/]\s*\d+(?:[.,]\d+)?)?)\s*(N2XH(?:-J|-O)?|NHXMH|NYY|NYM|LIHCH|FE\s*180)?\b",
                    re.IGNORECASE,
                )
                explicit_cable_tokens: List[Tuple[Point, str, str]] = []
                for t in tokens:
                    m_ct = cable_text_re.search(t.text)
                    if m_ct:
                        sec_s = m_ct.group(1).replace(" ", "").replace(",", ".")
                        typ_s = (m_ct.group(2) or "").strip().upper()
                        # Ölçek (1/50, 2x36W vb.) ile karışmaması için kontrol
                        if "W" not in t.text.upper() and not sec_s.endswith(("36", "18", "72")):
                            explicit_cable_tokens.append((Point(t.pos[0], t.pos[1]), sec_s, typ_s))

                for (pan, c_code, phase), syms_data in sorted(circuits_dict.items()):
                    dedup_tol = 15.0 if is_building_style else 150.0
                    unique_syms_map: Dict[Tuple[int, int], PlacedSymbol] = {}
                    scores = []
                    evs = []
                    assumptions = []
                    for s, score, ev in syms_data:
                        k_pt = (int(round(s.pos[0] / dedup_tol)), int(round(s.pos[1] / dedup_tol)))
                        unique_syms_map[k_pt] = s
                        scores.append(score)
                        if ev and ev not in evs:
                            evs.append(ev)

                    syms = list(unique_syms_map.values())
                    pts = [(s.pos[0], s.pos[1]) for s in syms]
                    c_norm = re.sub(r"[^A-Z0-9]", "", c_code.upper())

                    # 1. KABLO KESİTİ VE TİPİ ÇIKARIMI (Sıfır Varsayım!)
                    c_meta = cable_by_circuit.get(c_norm, {})
                    t_cable = table_cable_by_circuit.get(c_norm, {})
                    cable_sec = ""
                    cable_typ = ""
                    cable_full = ""
                    cable_source = "MISSING"

                    if c_meta.get("cross_section"):
                        cable_sec = c_meta["cross_section"].strip()
                        cable_typ = c_meta.get("cable_type", "").strip()
                        cable_full = c_meta.get("full_code", "")
                        cable_source = "EXPLICIT_CALLOUT"
                        evs.append(f"Kablo kesiti çizim etiketinden (Callout) okundu: {cable_sec} {cable_typ}".strip())
                    elif t_cable.get("cross_section"):
                        cable_sec = t_cable["cross_section"].strip()
                        cable_typ = t_cable.get("cable_type", "").strip()
                        cable_source = "EXPLICIT_TABLE"
                        evs.append(f"Kablo kesiti metraj/yükleme tablosundan okundu: {cable_sec} {cable_typ}".strip())
                    elif explicit_cable_tokens and pts:
                        prox_limit = 300.0 if is_building_style else 2500.0
                        best_d = prox_limit
                        for c_pt, sec_s, typ_s in explicit_cable_tokens:
                            for sx, sy in pts:
                                d = c_pt.distance(Point(sx, sy))
                                if d < best_d:
                                    best_d = d
                                    cable_sec = sec_s
                                    cable_typ = typ_s
                        if cable_sec:
                            cable_source = "EXPLICIT_TEXT"
                            evs.append(f"Kablo kesiti yakın metinden ({best_d:.0f} birim) okundu: {cable_sec} {cable_typ}".strip())

                    if not cable_sec:
                        assumptions.append("Çizimde veya tabloda bu linye için kablo kesit etiketi bulunamadı (otomatik kesit atanmadı)")

                    # 2. GÜÇ ÇIKARIMI (Sıfır Gizli Varsayım!)
                    if c_norm in table_power_by_circuit:
                        total_w = table_power_by_circuit[c_norm]
                        power_source = "EXPLICIT_TABLE"
                        evs.append(f"Linye toplam gücü tablodan kesin okundu: {total_w:.0f}W")
                    else:
                        exp_syms = [s for s in syms if s.power_w > 0 and s.power_source.startswith("EXPLICIT")]
                        if len(exp_syms) == len(syms) and len(syms) > 0:
                            total_w = sum(s.power_w for s in syms)
                            power_source = "EXPLICIT"
                            evs.append(f"Cihaz güçleri çizimden/lejanttan kesin okundu: Toplam {total_w:.0f}W")
                        elif len(exp_syms) > 0:
                            total_w = sum(s.power_w for s in syms)
                            power_source = "PARTIAL_EXPLICIT"
                            assumptions.append(f"{len(syms) - len(exp_syms)}/{len(syms)} adet cihazın gücü çizimde yazılı değil")
                        else:
                            total_w = 0.0
                            power_source = "MISSING"
                            assumptions.append("Cihaz güçleri çizimde veya lejantta yazılı değil")

                    # 3. GÜZERGAH UZUNLUĞU ÇIKARIMI (Sıfır Gizli İniş Payı!)
                    route_len = 0.0
                    length_source = "MISSING"
                    if c_norm in table_len_by_circuit:
                        route_len = table_len_by_circuit[c_norm]
                        length_source = "EXPLICIT_TABLE"
                        evs.append(f"Linye uzunluğu metraj tablosundan kesin okundu: {route_len:.1f}m")
                    elif len(pts) >= 2:
                        scale_div = 100.0 if is_building_style else 1000.0
                        mst_g = nx.Graph()
                        for i_p in range(len(pts)):
                            for j_p in range(i_p + 1, len(pts)):
                                d_man = (abs(pts[i_p][0] - pts[j_p][0]) + abs(pts[i_p][1] - pts[j_p][1])) / scale_div
                                if d_man <= 45.0:
                                    mst_g.add_edge(i_p, j_p, weight=d_man)
                        if mst_g.number_of_edges() > 0:
                            mst_tree = nx.minimum_spanning_tree(mst_g)
                            est_len = sum(d["weight"] for _, _, d in mst_tree.edges(data=True))
                            route_len = round(est_len, 2)
                            length_source = "ESTIMATED_MST"
                            assumptions.append(
                                f"Tabloda uzunluk olmadığından cihazlar arası MST mesafesi ({route_len:.1f}m) ölçüldü (pano besleme/iniş boyu çizimde yok)"
                            )
                        else:
                            assumptions.append("Cihazlar arası geçerli kablo güzergahı veya metraj tablosu bulunamadı")
                    else:
                        assumptions.append("Tek noktalı devrede kablo güzergahı veya metraj tablosu bulunamadı")

                    avg_score = round(sum(scores) / len(scores), 2) if scores else 0.85
                    if cable_source == "MISSING" or power_source == "MISSING" or length_source == "MISSING":
                        avg_score = min(avg_score, 0.45)
                        c_level = "İNCELEME GEREKLİ (BELİRSİZ)"
                    elif "ESTIMATED" in length_source or "PARTIAL" in power_source:
                        avg_score = min(avg_score, 0.70)
                        c_level = "MUHTEMEL"
                    else:
                        c_level = "KESİN" if avg_score >= 0.95 else ("YÜKSEK GÜVEN" if avg_score >= 0.80 else "MUHTEMEL")

                    logical_list.append(LogicalCircuit(
                        panel_tag=pan,
                        circuit_no=c_code,
                        phase=phase,
                        fixtures=syms,
                        fixture_count=len(syms),
                        total_power_w=round(total_w, 1),
                        cable_cross_section=cable_sec,
                        cable_type=cable_typ,
                        cable_full_code=cable_full,
                        estimated_route_length_m=route_len,
                        sub_zone=syms[0].sub_zone if syms else "",
                        confidence_level=c_level,
                        confidence_score=avg_score,
                        evidence_chain=evs,
                        cable_source=cable_source,
                        power_source=power_source,
                        length_source=length_source,
                        assumptions_used=assumptions,
                    ))

        return logical_list
