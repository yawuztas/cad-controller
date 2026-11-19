# -*- coding: utf-8 -*-
"""
Aşama 1C — Evrensel Pafta / Çerçeve Ayırıcı ve Rol Sınıflandırıcı (`pafta_ayirici.py`)
======================================================================================
Çizim birimi (du_to_m) ile normalize edilmiş fiziksel boyutlara göre:
1. Kapalı dikdörtgen LWPOLYLINE/POLYLINE ve eksene paralel (H/V) LINE sınırlarından
   pafta çerçevelerini çıkarır, iç içe çift çerçeve kenarlıklarını tekilleştirir.
2. Tüm dolu PaperSpace paftalarını da ayrı SheetFrame olarak ekler.
3. Her paftanın mühendislik rolünü (KAT_PLANI, KOLON_SEMASI, GERILIM_DUSUMU, vb.)
   kanıt zinciriyle sınıflandırır.
4. Çizimdeki dinamik Lejant (Sembol Sözlüğü) eşleştirmesini ham koordinat tahminleri
   olmadan çıkarır.
"""

from __future__ import annotations
from collections import Counter, defaultdict
import math
import re
from typing import Dict, List, Optional, Tuple

from shapely.geometry import Point, box
from shapely.strtree import STRtree

from .metin_temizleyici import norm_tr
from .schema import (
    BBox2D,
    LegendEntry,
    RawCADSnapshot,
    RawInsert,
    RawPath,
    RawText,
    SheetFrame,
    UnitCalibration,
)


def _is_approx_rectangle(path: RawPath, du_to_m: float) -> bool:
    """Bir kapalı poligonun yaklaşık dikdörtgen çerçeve olup olmadığını kontrol eder."""
    w_m = path.bbox.width * du_to_m
    h_m = path.bbox.height * du_to_m
    if w_m < 4.0 or h_m < 3.0:
        return False
    # En-boy oranı aşırı ince şeritleri ele
    aspect = max(w_m / max(h_m, 1e-6), h_m / max(w_m, 1e-6))
    if aspect > 12.0:
        return False

    pts = path.points
    if len(pts) < 4 or len(pts) > 14:
        return False

    # Köşe noktalarının bbox sınırlarına ne kadar oturduğunu ölç
    bx = path.bbox
    tol_x = max(bx.width * 0.02, 1e-4)
    tol_y = max(bx.height * 0.02, 1e-4)
    near_border = sum(
        1
        for x, y in pts
        if (abs(x - bx.minx) <= tol_x or abs(x - bx.maxx) <= tol_x)
        and (abs(y - bx.miny) <= tol_y or abs(y - bx.maxy) <= tol_y)
    )
    return near_border >= min(len(pts), 4)


def _detect_line_rectangles(paths: List[RawPath], du_to_m: float) -> List[Tuple[BBox2D, str]]:
    """4 ayrı LINE ile çizilmiş dikdörtgen pafta sınırlarını (yatay+düşey kesişimi) tespit eder."""
    horiz: List[Tuple[float, float, float, str]] = []  # (y, x1, x2, handle)
    vert: List[Tuple[float, float, float, str]] = []   # (x, y1, y2, handle)
    min_side_du = 4.0 / max(du_to_m, 1e-6)

    for p in paths:
        if p.space != "MODEL" or p.dxftype != "LINE" or len(p.points) != 2:
            continue
        if p.length_du < min_side_du:
            continue
        (x1, y1), (x2, y2) = p.points
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        if dy <= max(dx * 0.01, 1e-4):
            horiz.append(((y1 + y2) * 0.5, min(x1, x2), max(x1, x2), p.handle))
        elif dx <= max(dy * 0.01, 1e-4):
            vert.append(((x1 + x2) * 0.5, min(y1, y2), max(y1, y2), p.handle))

    if len(horiz) < 2 or len(vert) < 2:
        return []

    # Aynı x1..x2 aralığını paylaşan yatay çiftlerle uyumlu dikey çiftleri eşleştir
    rects: List[Tuple[BBox2D, str]] = []
    horiz.sort(key=lambda h: h[1])
    for i in range(len(horiz)):
        y_a, xa1, xa2, ha = horiz[i]
        len_a = xa2 - xa1
        for j in range(i + 1, len(horiz)):
            y_b, xb1, xb2, hb = horiz[j]
            if xb1 > xa1 + len_a * 0.15:
                break
            if abs(xa1 - xb1) <= len_a * 0.03 and abs(xa2 - xb2) <= len_a * 0.03:
                ymin, ymax = min(y_a, y_b), max(y_a, y_b)
                h_du = ymax - ymin
                if h_du < min_side_du:
                    continue
                aspect = max(len_a / max(h_du, 1e-6), h_du / max(len_a, 1e-6))
                if aspect > 12.0:
                    continue
                # Sol ve sağ kenarda uyumlu dikey LINE var mı?
                tol_x = max(len_a * 0.03, 1e-4)
                tol_y = max(h_du * 0.04, 1e-4)
                has_left = any(
                    abs(vx - xa1) <= tol_x and vy1 <= ymin + tol_y and vy2 >= ymax - tol_y
                    for vx, vy1, vy2, _ in vert
                )
                has_right = any(
                    abs(vx - xa2) <= tol_x and vy1 <= ymin + tol_y and vy2 >= ymax - tol_y
                    for vx, vy1, vy2, _ in vert
                )
                if has_left and has_right:
                    rects.append((BBox2D(minx=xa1, miny=ymin, maxx=xa2, maxy=ymax), f"{ha}+{hb}"))
    return rects


def _deduplicate_frames(
    cands: List[Tuple[BBox2D, str]],
    du_to_m: float,
    msp_texts: List[RawText],
) -> List[Tuple[BBox2D, str]]:
    """
    1. Çift kenarlıklı çerçeveleri (%72+ alan örtüşmesi) tek dış çerçevede birleştirir.
    2. Büyük bir PLAN / ŞEMA dış çerçevesinin içinde kalan ve üzerinde ayrı bir
       pafta başlığı (PLANI/ŞEMASI/HESABI/DETAYI/NOTLAR) taşımayan bina dış kontur
       dikdörtgenlerini (ör. kat planı içindeki yapı oturtum sınırı) ayrı pafta
       sanmaktan korur.
    """
    if not cands:
        return []
    ordered = sorted(cands, key=lambda c: c[0].area, reverse=True)
    kept: List[Tuple[BBox2D, str]] = []
    kept_polys: List[object] = []

    title_kws = ("PLANI", "SEMASI", "HESABI", "CETVELI", "LEJANT", "DETAY", "NOTLAR", "GERILIM")
    for bb, hnd in ordered:
        poly = box(bb.minx, bb.miny, bb.maxx, bb.maxy)
        is_dup = False
        for kp in kept_polys:
            inter = poly.intersection(kp).area
            if inter / max(poly.area, 1e-9) > 0.80:
                if poly.area / max(kp.area, 1e-9) > 0.72:
                    is_dup = True
                    break
                # Dış pafta (>= 350 m²) içindeki küçük çerçevede başlık/tablo yoksa bina konturudur
                kp_area_m2 = kp.area * (du_to_m ** 2)
                if kp_area_m2 >= 350.0:
                    has_sub_title = any(
                        bb.contains_xy(t.x, t.y) and any(k in norm_tr(t.text) for k in title_kws)
                        for t in msp_texts
                    )
                    if not has_sub_title:
                        is_dup = True
                        break
        if not is_dup:
            kept.append((bb, hnd))
            kept_polys.append(poly)
    return kept


def _classify_frame_role(
    texts: List[RawText],
    door_arc_count: int,
    paths: Optional[List[RawPath]] = None,
) -> Tuple[str, float, List[str], str]:
    """Pafta içeriğindeki başlık metinleri ve fiziksel izlere bakarak rolü belirler."""
    joined = norm_tr(" ".join(t.text for t in texts))
    # Pafta başlığı adayı: medyan yazı boyunun >= %105'i (tekil dev harf uç değerlerinden etkilenmez)
    heights = sorted(t.height for t in texts if t.height > 0)
    med_h = heights[len(heights) // 2] if heights else 1.0
    big_joined = norm_tr(" ".join(t.text for t in texts if t.height >= med_h * 1.05 and len(t.text) <= 95))
    ev: List[str] = []
    scores: Dict[str, float] = defaultdict(float)

    # 1. Güçlü başlık sinyalleri (büyük puntolu/başlık ifadeleri)
    is_riser_or_sld = bool(
        any(k in joined for k in ("KOLON DAGITIM SEMASI", "KOLON SEMASI", "DAGITIM SEMASI", "TEK HAT SEMASI", "SINGLE LINE"))
    )
    if any(k in big_joined for k in ("KOLON DAGITIM SEMASI", "KOLON SEMASI", "DAGITIM SEMASI")):
        scores["KOLON_SEMASI"] += 8.0
        ev.append("Kolon dağıtım şeması başlığı")
    elif any(k in joined for k in ("KOLON SEMASI", "DAGITIM SEMASI", "ANA DAGITIM TABLOSU")):
        scores["KOLON_SEMASI"] += 6.5
        ev.append("Kolon şeması terimi")

    if any(k in big_joined for k in ("TEK HAT", "SINGLE LINE")):
        scores["TEK_HAT"] += 8.0
        ev.append("Tek hat şeması başlığı")

    if any(k in big_joined for k in ("GERILIM DUSUMU", "VOLTAGE DROP")):
        scores["GERILIM_DUSUMU"] += 6.5
        ev.append("Gerilim düşümü başlığı")
    elif re.search(r"%\s*E\d*|0[.,]0(?:124|74|112|675)", joined):
        scores["GERILIM_DUSUMU"] += 3.0
        ev.append("Gerilim düşümü formül/katsayı ibaresi")

    # Başlık/not ayrımı: "DETAYI / NOTLAR" içeren bilgi/detay kutularını plan sanma
    has_detail_or_notes_head = bool(
        re.search(r"\b(?:DETAYI|DETAYLARI|NOTLAR|NOTLARI)\b", joined)
    ) and not re.search(
        r"\b(?:KAT\s+PLANI|KABLOLAMA\s+PLANI|KURULUM\s+PLANI|YERLESIM\s+PLANI|KOTU\s+PLANI|SINYALIZASYON\s+PLANI|OTOMASYON\s+PLANI|GUZERGAH\s+PLANI|TOPRAKLAMA\s+(?:VE\s+VAZIYET\s+)?PLANI|KOLON\s+(?:DAGITIM\s+)?SEMASI)\b",
        joined,
    )

    if any(k in big_joined for k in ("TOPRAKLAMA PLANI", "TEMEL TOPRAKLAMA")) and not has_detail_or_notes_head and not is_riser_or_sld:
        scores["TOPRAKLAMA"] += 5.5
        ev.append("Topraklama planı başlığı")
    elif "TOPRAKLAMA" in joined and not has_detail_or_notes_head and not is_riser_or_sld:
        scores["TOPRAKLAMA"] += 2.0
        ev.append("Topraklama ibaresi")

    # Topraklama katmanı geometrisi varsa güçlü fiziksel sinyal ekle (detay veya şema değilse)
    if (not has_detail_or_notes_head) and (not is_riser_or_sld) and paths and any(
        any(gk in norm_tr(p.layer) for gk in ("TOPRAK", "SERIT", "TEMEL", "GND", "EARTHING"))
        for p in paths
    ):
        scores["TOPRAKLAMA"] += 3.0
        ev.append("Topraklama iletken katmanı")

    if any(k in big_joined for k in ("YUKLEME CETVELI", "LINYE TABLOSU")):
        scores["YUKLEME_CETVELI"] += 6.0
        ev.append("Yükleme cetveli başlığı")
    elif "LINYE NO" in joined:
        scores["YUKLEME_CETVELI"] += 2.5

    if any(k in big_joined for k in ("LEJANT", "SEMBOLLER", "SEMBOL")):
        scores["LEJANT"] += 5.0
        ev.append("Lejant başlığı")

    if any(
        k in big_joined
        for k in (
            "KAT PLANI",
            "AYDINLATMA PLANI",
            "KUVVETLI AKIM PLANI",
            "ZAYIF AKIM PLANI",
            "PRIZ PLANI",
            "KABLOLAMA PLANI",
            "KURULUM PLANI",
            "YERLESIM PLANI",
            "KOTU PLANI",
            "SINYALIZASYON PLANI",
            "OTOMASYON PLANI",
            "GUZERGAH PLANI",
            "INSTALLATION AND CABLING PLAN",
        )
    ):
        scores["KAT_PLANI"] += 6.0
        ev.append("Kat planı başlığı")

    if any(k in joined for k in ("FFL", "SSL", "PERON", "BILET HOLU", "TEKNIK KAT", "SAFT", "EKIPMAN ODASI")) and not any(
        k in joined for k in ("KOLON DAGITIM", "YUKLEME CETVELI", "GERILIM DUSUMU")
    ):
        scores["KAT_PLANI"] += 4.5
        ev.append("BIM/Metro kat veya teknik mahal etiketi")

    if paths and scores.get("TOPRAKLAMA", 0.0) == 0.0 and door_arc_count < 2 and not has_detail_or_notes_head:
        arch_wall_door_cnt = sum(
            1
            for p in paths
            if any(
                ak in norm_tr(p.layer).upper()
                for ak in ("A-WALL", "I-WALL", "A-DOOR", "A-GENM", "DUVAR", "KAPI", "KAPIPENCERE")
            )
        )
        if arch_wall_door_cnt >= 15:
            scores["KAT_PLANI"] += 3.5
            ev.append(f"Mimari duvar/kapı geometrisi ({arch_wall_door_cnt} çizgi)")

    if door_arc_count >= 2:
        scores["KAT_PLANI"] += 3.0 + min(door_arc_count * 0.05, 3.0)
        ev.append(f"Fiziksel kapı yayı ({door_arc_count} adet)")

    if (has_detail_or_notes_head or any(k in big_joined for k in ("DETAYI", "DETAYLARI", "NOTLAR"))) and not scores:
        scores["DETAY"] += 4.0
        ev.append("Detay / Notlar başlığı")

    # Başlık tahmini: madde cümlesi olmayan, tam kelimeli PLAN/ŞEMA/HESAP/DETAY/NOTLAR başlıklarını seç
    title_cand = ""
    best_rank = (-1.0, -1e12, -999)
    re_title_kw = re.compile(
        r"\b(?:PLANI|SEMASI|HESABI|CETVELI|LEJANT|TOPRAKLAMA|DETAYI|DETAYLARI|NOTLAR|NOTLARI)\b"
    )
    for t in texts:
        raw_t = t.text.strip()
        if not raw_t or len(raw_t) > 90:
            continue
        tu = norm_tr(raw_t)
        if re.match(r"^\d+\s*[.):\-]", raw_t) and not re.match(
            r"^\d+\s*\.\s*(?:KAT|BODRUM|NORMAL|ZEMIN|ASMA|TERAS|CATI)\b", tu
        ):
            continue
        if not re_title_kw.search(tu):
            continue
        # "VE ..." diye devam eden paragraf satırları yerine kısa/üst başlıkları tercih et
        kw_bonus = 1.0 if not re.match(r"^(?:VE|VEYA|BU|AYNI|HER)\b", tu) else 0.0
        rank = (round(t.height * (1.15 if kw_bonus else 0.75), 3), round(t.y, 1), -len(raw_t))
        if rank > best_rank:
            best_rank = rank
            title_cand = raw_t

    if not scores:
        return ("DETAY" if len(texts) >= 3 else "DIGER"), 0.25, ["Belirgin disiplin başlığı yok"], title_cand

    best_role, best_s = max(scores.items(), key=lambda kv: kv[1])
    conf = round(min(0.99, 0.35 + 0.10 * best_s), 2)
    return best_role, conf, ev, title_cand


def extract_frames_and_assign(
    snapshot: RawCADSnapshot,
    unit: UnitCalibration,
) -> Tuple[List[SheetFrame], Dict[str, List[RawText]], Dict[str, List[RawInsert]], Dict[str, List[RawPath]]]:
    """
    ModelSpace ve PaperSpace paftalarını bulur; metin/sembol/geometrileri paftalara bağlar.
    """
    du_to_m = unit.du_to_m

    msp_texts = [t for t in snapshot.texts if t.space == "MODEL"]
    msp_inserts = [i for i in snapshot.inserts if i.space == "MODEL"]
    msp_paths = [p for p in snapshot.paths if p.space == "MODEL"]
    msp_oles = [o for o in snapshot.ole_objects if o.space == "MODEL"]

    # 1. ModelSpace kapalı ve çizgisel dikdörtgen çerçeveleri topla
    rect_cands: List[Tuple[BBox2D, str]] = []
    for p in msp_paths:
        if p.closed and p.dxftype in ("LWPOLYLINE", "POLYLINE"):
            if _is_approx_rectangle(p, du_to_m):
                rect_cands.append((p.bbox, p.handle))

    rect_cands.extend(_detect_line_rectangles(snapshot.paths, du_to_m))

    # 1B. Çerçevesiz büyük ölçekli birleşik kat planı bloklarını (BIM/Revit altlıkları) görünüm çerçevesi yap
    large_plan_boxes: List[Tuple[BBox2D, str]] = []
    for ins in msp_inserts:
        if ins.parent_chain or ins.is_xref:
            continue
        w_m = ins.bbox.width * du_to_m
        h_m = ins.bbox.height * du_to_m
        if w_m >= 15.0 and h_m >= 12.0:
            aspect = max(w_m / max(h_m, 1e-6), h_m / max(w_m, 1e-6))
            if aspect <= 14.0:
                large_plan_boxes.append((ins.bbox, ins.handle))

    if large_plan_boxes:
        n_lp = len(large_plan_boxes)
        lp_polys = [box(bb.minx, bb.miny, bb.maxx, bb.maxy) for bb, _ in large_plan_boxes]
        lp_parent = list(range(n_lp))

        def _lp_find(x: int) -> int:
            while lp_parent[x] != x:
                lp_parent[x] = lp_parent[lp_parent[x]]
                x = lp_parent[x]
            return x

        for i in range(n_lp):
            for j in range(i + 1, n_lp):
                min_a = min(lp_polys[i].area, lp_polys[j].area)
                if min_a > 1e-9 and (lp_polys[i].intersection(lp_polys[j]).area / min_a) >= 0.20:
                    ri, rj = _lp_find(i), _lp_find(j)
                    if ri != rj:
                        lp_parent[rj] = ri

        lp_groups: Dict[int, List[int]] = defaultdict(list)
        for idx in range(n_lp):
            lp_groups[_lp_find(idx)].append(idx)

        existing_rc_polys = [box(bb.minx, bb.miny, bb.maxx, bb.maxy) for bb, _ in rect_cands]
        for idxs in lp_groups.values():
            u_bb = BBox2D(
                minx=min(large_plan_boxes[k][0].minx for k in idxs),
                miny=min(large_plan_boxes[k][0].miny for k in idxs),
                maxx=max(large_plan_boxes[k][0].maxx for k in idxs),
                maxy=max(large_plan_boxes[k][0].maxy for k in idxs),
            )
            u_poly = box(u_bb.minx, u_bb.miny, u_bb.maxx, u_bb.maxy)
            if u_poly.area <= 1e-9:
                continue
            if not any((u_poly.intersection(ep).area / u_poly.area) > 0.50 for ep in existing_rc_polys):
                rect_cands.append((u_bb, f"BLK:{large_plan_boxes[idxs[0]][1]}"))

    unique_rects = _deduplicate_frames(rect_cands, du_to_m=du_to_m, msp_texts=msp_texts)

    if not unique_rects and (msp_texts or msp_paths or msp_inserts):
        xs = [t.x for t in msp_texts] + [p.bbox.minx for p in msp_paths] + [p.bbox.maxx for p in msp_paths]
        ys = [t.y for t in msp_texts] + [p.bbox.miny for p in msp_paths] + [p.bbox.maxy for p in msp_paths]
        if xs and ys:
            unique_rects = [(BBox2D(minx=min(xs), miny=min(ys), maxx=max(xs), maxy=max(ys)), "VIRTUAL_MSP")]

    # Sol-üstten sağ-alta sırala ki frame_id kararlı olsun
    unique_rects.sort(key=lambda c: (-round(c[0].maxy, 1), round(c[0].minx, 1)))

    frame_polys = [box(bb.minx, bb.miny, bb.maxx, bb.maxy) for bb, _ in unique_rects]
    frame_tree = STRtree(frame_polys) if frame_polys else None

    texts_by_frame: Dict[str, List[RawText]] = defaultdict(list)
    inserts_by_frame: Dict[str, List[RawInsert]] = defaultdict(list)
    paths_by_frame: Dict[str, List[RawPath]] = defaultdict(list)
    oles_count_by_frame: Dict[str, int] = defaultdict(int)
    frame_ids = [f"M_{idx + 1:02d}" for idx in range(len(unique_rects))]

    def _find_frame_id(x: float, y: float) -> str:
        if not frame_tree:
            return "M_OUTSIDE"
        pt = Point(x, y)
        hits = [int(i) for i in frame_tree.query(pt) if frame_polys[int(i)].covers(pt)]
        if not hits:
            return "M_OUTSIDE"
        # İç içe pafta varsa en küçük alanı seç
        best_i = min(hits, key=lambda idx: frame_polys[idx].area)
        return frame_ids[best_i]

    for t in msp_texts:
        texts_by_frame[_find_frame_id(t.x, t.y)].append(t)
    for ins in msp_inserts:
        inserts_by_frame[_find_frame_id(ins.x, ins.y)].append(ins)
    for p in msp_paths:
        cx, cy = p.bbox.center
        paths_by_frame[_find_frame_id(cx, cy)].append(p)
    for o in msp_oles:
        cx, cy = o.bbox.center
        oles_count_by_frame[_find_frame_id(cx, cy)] += 1

    sheets: List[SheetFrame] = []
    for idx, (bb_du, border_h) in enumerate(unique_rects):
        fid = frame_ids[idx]
        f_texts = texts_by_frame[fid]
        f_inserts = inserts_by_frame[fid]
        f_paths = paths_by_frame[fid]
        door_cnt = sum(
            1
            for p in f_paths
            if p.dxftype == "ARC"
            and p.radius_du is not None
            and p.arc_sweep_deg is not None
            and 72.0 <= abs(p.arc_sweep_deg) <= 108.0
            and 0.55 <= (p.radius_du * du_to_m) <= 1.35
        )
        role, conf, ev, title = _classify_frame_role(f_texts, door_cnt, paths=f_paths)
        if not title and f_inserts:
            bim_titles: List[str] = []
            for ins in f_inserts:
                bn = (ins.effective_name or ins.block_name or "").strip()
                bu = norm_tr(bn).upper()
                if any(k in bu for k in ("FFL", "SSL", "PERON", "BILET HOLU", "TEKNIK KAT", "SAFT", "EKIPMAN ODASI")):
                    m_bt = re.search(r"((?:OGDC|PRZ|FFL|SSL|PERON|BILET|TEKNIK|OG|KAT)[^<>]{3,})$", bn, re.IGNORECASE)
                    bim_titles.append((m_bt.group(1) if m_bt else bn).strip()[:90])
            if bim_titles:
                title = Counter(bim_titles).most_common(1)[0][0]
        bb_m = BBox2D(
            minx=round(bb_du.minx * du_to_m, 3),
            miny=round(bb_du.miny * du_to_m, 3),
            maxx=round(bb_du.maxx * du_to_m, 3),
            maxy=round(bb_du.maxy * du_to_m, 3),
        )
        sheets.append(SheetFrame(
            frame_id=fid,
            space="MODEL",
            bbox_du=bb_du,
            bbox_m=bb_m,
            role=role,  # type: ignore[arg-type]
            role_confidence=conf,
            role_evidence=ev,
            title=title,
            border_handle=border_h,
            text_count=len(f_texts),
            insert_count=len(f_inserts),
            path_count=len(f_paths),
            ole_count=oles_count_by_frame[fid],
        ))

    # 2. PaperSpace Paftalarını da ekle
    ps_spaces = sorted({t.space for t in snapshot.texts if t.space.startswith("PAPERSPACE:")} |
                       {i.space for i in snapshot.inserts if i.space.startswith("PAPERSPACE:")})
    for p_idx, sp_name in enumerate(ps_spaces, 1):
        fid = f"PS_{p_idx:02d}"
        f_texts = [t for t in snapshot.texts if t.space == sp_name]
        f_inserts = [i for i in snapshot.inserts if i.space == sp_name]
        f_paths = [p for p in snapshot.paths if p.space == sp_name]
        texts_by_frame[fid] = f_texts
        inserts_by_frame[fid] = f_inserts
        paths_by_frame[fid] = f_paths
        xs = [t.x for t in f_texts] + [i.x for i in f_inserts]
        ys = [t.y for t in f_texts] + [i.y for i in f_inserts]
        bb_du = BBox2D(
            minx=min(xs) if xs else 0.0,
            miny=min(ys) if ys else 0.0,
            maxx=max(xs) if xs else 0.0,
            maxy=max(ys) if ys else 0.0,
        )
        bb_m = BBox2D(
            minx=round(bb_du.minx * du_to_m, 3),
            miny=round(bb_du.miny * du_to_m, 3),
            maxx=round(bb_du.maxx * du_to_m, 3),
            maxy=round(bb_du.maxy * du_to_m, 3),
        )
        role, conf, ev, title = _classify_frame_role(f_texts, 0, paths=f_paths)
        sheets.append(SheetFrame(
            frame_id=fid,
            space=sp_name,
            bbox_du=bb_du,
            bbox_m=bb_m,
            role=role,  # type: ignore[arg-type]
            role_confidence=conf,
            role_evidence=ev,
            title=title or sp_name.replace("PAPERSPACE:", ""),
            border_handle="",
            text_count=len(f_texts),
            insert_count=len(f_inserts),
            path_count=len(f_paths),
            ole_count=sum(1 for o in snapshot.ole_objects if o.space == sp_name),
        ))

    # 3. PaperSpace tek/baskın anteti açıkça KOLON_SEMASI / TEK_HAT ise ve ModelSpace'te
    #    mimari kat planı yoksa (ör. topraklama kolon şeması paftaları), başlığında "PLANI"
    #    geçmeyen ModelSpace şema çerçevelerine şema rolünü evrensel olarak miras ver.
    ps_sheets = [s for s in sheets if s.space.startswith("PAPERSPACE:")]
    msp_sheets = [s for s in sheets if s.space == "MODEL"]
    if ps_sheets and msp_sheets:
        ps_sch_roles = {s.role for s in ps_sheets if s.role in ("KOLON_SEMASI", "TEK_HAT")}
        if len(ps_sch_roles) == 1:
            inherited_role = next(iter(ps_sch_roles))
            for ms in msp_sheets:
                if ms.role in ("TOPRAKLAMA", "DIGER", "DETAY") and not any(
                    ev_k in " ".join(ms.role_evidence)
                    for ev_k in ("Topraklama planı başlığı", "Kat planı başlığı")
                ):
                    ms.role = inherited_role  # type: ignore[assignment]
                    ms.role_evidence.append(f"PaperSpace antet mirası ({inherited_role})")

    return sheets, texts_by_frame, inserts_by_frame, paths_by_frame


def find_legend_table_regions(
    sheets: List[SheetFrame],
    texts_by_frame: Dict[str, List[RawText]],
    inserts_by_frame: Dict[str, List[RawInsert]],
) -> List[Tuple[str, float, float, float, float]]:
    """
    Tüm paftalardaki `SEMBOL | AÇIKLAMASI` lejant tablo kutularının sınırlarını
    `(sheet_id, x_lo, x_hi, y_bot, y_top)` olarak döndürür.
    Böylece M_01/M_04 gibi plan paftalarının içindeki küçük lokal lejant kutuları da
    saha/ekipman metrajından ve topraklama şerit boyundan güvenle ayırt edilebilir.
    """
    regions: List[Tuple[str, float, float, float, float]] = []

    for sh in sheets:
        f_texts = texts_by_frame.get(sh.frame_id, [])
        f_inserts = inserts_by_frame.get(sh.frame_id, [])
        if not f_texts or not f_inserts:
            continue

        sym_hdrs = sorted(
            [t for t in f_texts if re.match(r"^(?:SEMBOL(?:U|LER|LERI)?|SYMBOL)$", norm_tr(t.text))],
            key=lambda t: t.x,
        )
        desc_hdrs = [
            t for t in f_texts
            if re.match(r"^(?:ACIKLAMA(?:SI|LAR|LARI)?|TANIM(?:I|LAR)?|DESCRIPTION)$", norm_tr(t.text))
        ]

        candidate_pairs: List[Tuple[float, float, float, float]] = []
        for shdr in sym_hdrs:
            same_row_descs = [
                dhdr for dhdr in desc_hdrs
                if abs(shdr.y - dhdr.y) <= max(shdr.height, dhdr.height, 1.0) * 2.5 and dhdr.x > shdr.x
            ]
            if not same_row_descs:
                continue
            dhdr = min(same_row_descs, key=lambda d: d.x - shdr.x)
            h_ref = max(shdr.height, dhdr.height, 1.0)
            next_syms = [o for o in sym_hdrs if o is not shdr and o.x > dhdr.x and abs(o.y - shdr.y) <= 5.0 * h_ref]
            max_col_x = (next_syms[0].x - 2.0 * h_ref) if next_syms else (dhdr.x + 35.0 * h_ref)
            x_lo = shdr.x - 4.5 * h_ref
            x_hi = min(dhdr.x + 35.0 * h_ref, max_col_x)
            y_top = max(shdr.y, dhdr.y) + 1.5 * h_ref

            # Açıklama satırlarının bittiği alt sınırı dikey boşluktan dinamik kes (sola dayalı metinler dahil)
            col_texts = sorted(
                [
                    t for t in f_texts
                    if (shdr.x + 1.5 * h_ref) <= t.x <= x_hi
                    and t.y < shdr.y - 0.5 * h_ref
                    and len(t.text.strip()) >= 3
                ],
                key=lambda t: -t.y,
            )
            if col_texts:
                prev_y = shdr.y
                last_y = col_texts[0].y
                gaps = [
                    col_texts[k].y - col_texts[k + 1].y
                    for k in range(len(col_texts) - 1)
                    if 0.8 * h_ref <= (col_texts[k].y - col_texts[k + 1].y) <= 6.0 * h_ref
                ]
                med_gap = sorted(gaps)[len(gaps) // 2] if gaps else (3.0 * h_ref)
                max_allow_gap = max(med_gap * 2.6, 5.5 * h_ref)
                for ct in col_texts:
                    if prev_y - ct.y > max_allow_gap:
                        break
                    last_y = ct.y
                    prev_y = ct.y
                y_bot = last_y - 2.0 * h_ref
            else:
                y_bot = sh.bbox_du.miny
            candidate_pairs.append((x_lo, x_hi, y_bot, y_top))

        if not candidate_pairs and sh.role == "LEJANT":
            candidate_pairs.append((sh.bbox_du.minx, sh.bbox_du.maxx, sh.bbox_du.miny, sh.bbox_du.maxy))

        for x_lo, x_hi, y_bot, y_top in candidate_pairs:
            regions.append((sh.frame_id, x_lo, x_hi, y_bot, y_top))

    return regions


def extract_legend_entries(
    sheets: List[SheetFrame],
    texts_by_frame: Dict[str, List[RawText]],
    inserts_by_frame: Dict[str, List[RawInsert]],
) -> Dict[str, LegendEntry]:
    """
    Sabit koordinat pencereleri olmadan, SEMBOL/AÇIKLAMA başlıkları veya LEJANT
    paftalarındaki blok-metin satır eşleşmesinden sembol sözlüğünü çıkarır.
    Her sembolü yalnızca dikey olarak en yakın tek açıklama satırıyla eşleştirerek
    üst/alt komşu satırların metinlerinin birleşmesini önler.
    """
    legend: Dict[str, LegendEntry] = {}
    regions = find_legend_table_regions(sheets, texts_by_frame, inserts_by_frame)

    for fid, x_lo, x_hi, y_bot, y_top in regions:
        f_texts = texts_by_frame.get(fid, [])
        f_inserts = inserts_by_frame.get(fid, [])
        band_inserts = [
            ins for ins in f_inserts
            if not ins.is_xref and not ins.parent_chain and x_lo <= ins.x <= x_hi and y_bot <= ins.y <= y_top
        ]
        band_texts = [
            t for t in f_texts
            if x_lo <= t.x <= x_hi and y_bot <= t.y <= y_top
            and not re.match(r"^(?:SEMBOL(?:U|LER|LERI)?|SYMBOL|ACIKLAMA(?:SI|LAR|LARI)?|TANIM(?:I|LAR)?|DESCRIPTION)$", norm_tr(t.text))
        ]
        for ins in band_inserts:
            # Sağındaki aday açıklama metinlerinden yalnızca dikeyde EN YAKIN satırı seç
            cands = [
                t for t in band_texts
                if t.x > ins.x
                and (t.x - ins.x) <= max(t.height * 38.0, (x_hi - ins.x))
                and abs(t.y - ins.y) <= max(t.height * 2.1, 4.0)
                and len(t.text.strip()) >= 3
            ]
            if not cands:
                continue
            anchor_t = min(cands, key=lambda t: (abs(t.y - ins.y), t.x - ins.x))
            h_row = max(anchor_t.height, 1.0)
            same_row = sorted(
                [t for t in cands if abs(t.y - anchor_t.y) <= 0.55 * h_row],
                key=lambda t: t.x,
            )
            desc = " ".join(t.text.strip() for t in same_row[:2]).strip()
            if not desc or len(desc) < 2:
                continue
            key = ins.effective_name or ins.block_name
            if key not in legend:
                legend[key] = LegendEntry(
                    symbol_key=key,
                    block_names=[ins.block_name] if ins.block_name != key else [key],
                    description=desc,
                    sheet_id=fid,
                    source_handles=[ins.handle] + [t.handle for t in same_row[:2] if t.handle],
                )
            elif ins.block_name not in legend[key].block_names:
                legend[key].block_names.append(ins.block_name)

    return legend
