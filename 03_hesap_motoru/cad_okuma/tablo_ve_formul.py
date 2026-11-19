# -*- coding: utf-8 -*-
"""
Aşama 1D — Adaptif Tablo ve Çok-Satırlı Formül Çıkarıcı (`tablo_ve_formul.py`)
===============================================================================
1. Doğrudan `ACAD_TABLE` nesnelerini kalıba aktarır.
2. Sabit `row_tol=4.5` / `dx<=60` varsayımları olmadan, metin yüksekliğine (`H`)
   oranlı adaptif satır/sütun kümelemesi ile çizgili/metin tablolarını okur.
3. Gerilim düşümü kesir çubuklarını (`----` veya yatay LINE) bulup:
   - Aynı satırdaki (`= % 0,217`) VE
   - Bir/iki alt satıra ayrı yazılmış (`%%%e =  0,36  +  0,37`)
   hesap ifadelerini gerçek DXF handle kanıtıyla çıkarır; yoksa `UNREADABLE` der.
"""

from __future__ import annotations
from collections import defaultdict
import re
import statistics
from typing import Dict, List, Optional, Tuple

from .metin_temizleyici import norm_tr, parse_tr_float
from .schema import (
    BBox2D,
    FormulaBlock,
    NormalizedTable,
    RawAcadTable,
    RawOleObject,
    RawPath,
    RawText,
    SheetFrame,
)

TABLE_HEADER_KEYWORDS: Tuple[str, ...] = (
    "LINYE", "PANO", "DEVRE", "GUC", "KURULU", "TALEP", "KABLO",
    "KESIT", "UZUNLUK", "AKIM", "SIGORTA", "FAZ", "SEMBOL",
    "ACIKLAMA", "TANIM", "ADET", "WATTS", "KW", "GERILIM",
)


def _cluster_by_y(tokens: List[RawText], y_tol: float) -> List[List[RawText]]:
    """Metinleri Y koordinatına göre üstten alta adaptif satırlara böler."""
    if not tokens:
        return []
    ordered = sorted(tokens, key=lambda t: (-t.y, t.x))
    rows: List[List[RawText]] = []
    cur_row: List[RawText] = [ordered[0]]
    cur_y = ordered[0].y

    for t in ordered[1:]:
        if abs(t.y - cur_y) <= y_tol:
            cur_row.append(t)
            cur_y = sum(x.y for x in cur_row) / len(cur_row)
        else:
            rows.append(sorted(cur_row, key=lambda x: x.x))
            cur_row = [t]
            cur_y = t.y
    rows.append(sorted(cur_row, key=lambda x: x.x))
    return rows


def extract_all_tables(
    acad_tables: List[RawAcadTable],
    sheets: List[SheetFrame],
    texts_by_frame: Dict[str, List[RawText]],
    ole_objects: Optional[List[RawOleObject]] = None,
) -> List[NormalizedTable]:
    """ACAD_TABLE, çözülmüş OLE2 tabloları ve adaptif metin tablolarını `NormalizedTable` kalıbına döker."""
    out: List[NormalizedTable] = []
    tbl_idx = 0

    def _sheet_for_point(space: str, x: float, y: float) -> str:
        hits = [
            (sh.bbox_du.width * sh.bbox_du.height, sh.frame_id)
            for sh in sheets
            if sh.space == space and sh.bbox_du.minx <= x <= sh.bbox_du.maxx and sh.bbox_du.miny <= y <= sh.bbox_du.maxy
        ]
        return min(hits, key=lambda it: it[0])[1] if hits else space

    # 1. Doğrudan AutoCAD ACAD_TABLE nesneleri
    for at in acad_tables:
        if not at.rows:
            continue
        tbl_idx += 1
        headers = at.rows[0]
        dict_rows: List[Dict[str, str]] = []
        for r in at.rows[1:]:
            if not any(c.strip() for c in r):
                continue
            d = {}
            for ci, h in enumerate(headers):
                key = h or f"SUTUN_{ci + 1}"
                d[key] = r[ci] if ci < len(r) else ""
            dict_rows.append(d)
        out.append(NormalizedTable(
            table_id=f"TBL_{tbl_idx:03d}",
            sheet_id=at.space,
            source_kind="ACAD_TABLE",
            title=headers[0] if headers else "ACAD_TABLE",
            headers=headers,
            rows=dict_rows,
            raw_matrix=at.rows,
            bbox_du=at.bbox,
            confidence=1.0,
            source_handles=[at.handle] if at.handle else [],
        ))

    # 1B. Çözülmüş Gömülü OLE2FRAME Tabloları (Excel / EMF CONTENTS)
    for ole in (ole_objects or []):
        if ole.decode_status != "OK" or not ole.decoded_rows:
            continue
        tbl_idx += 1
        headers = ole.decoded_rows[0]
        cx, cy = ole.bbox.center
        sid = _sheet_for_point(ole.space, cx, cy)
        dict_rows_o: List[Dict[str, str]] = []
        for r in ole.decoded_rows[1:]:
            dict_rows_o.append({f"COL_{ci + 1}": val for ci, val in enumerate(r)})
        out.append(NormalizedTable(
            table_id=f"TBL_{tbl_idx:03d}",
            sheet_id=sid,
            source_kind="OLE2_DECODED",
            title=ole.decoded_title or f"OLE2_{ole.handle}",
            headers=headers,
            rows=dict_rows_o,
            raw_matrix=ole.decoded_rows,
            bbox_du=ole.bbox,
            confidence=0.95,
            source_handles=[ole.handle] if ole.handle else [],
        ))

    # 2. Pafta içi çizgili/metin grid tabloları (metin boyu H ile ölçekli)
    for sh in sheets:
        f_texts = texts_by_frame.get(sh.frame_id, [])
        if len(f_texts) < 6:
            continue
        heights = [t.height for t in f_texts if t.height > 0]
        h_med = statistics.median(heights) if heights else 2.5
        y_tol = max(0.75 * h_med, 1e-3)
        y_rows = _cluster_by_y(f_texts, y_tol=y_tol)

        i = 0
        while i < len(y_rows):
            row = y_rows[i]
            kw_hits = sum(
                1 for t in row if any(k in norm_tr(t.text) for k in TABLE_HEADER_KEYWORDS)
            )
            if len(row) >= 3 and kw_hits >= 2:
                headers = [t.text.strip() for t in row]
                unique_hdrs = {norm_tr(h) for h in headers if h.strip()}
                # Tekrarlayan pano etiketlerini (Kurulu Güç / 10900W / Kurulu Güç / 10900W) veya saf veri satırlarını ele
                if len(unique_hdrs) < 3 or len(unique_hdrs) < len(headers) * 0.6:
                    i += 1
                    continue
                if sum(1 for h in headers if re.match(r"^\d+(?:[.,]\d+)?\s*[WwAaVv]?$", h)) > len(headers) * 0.4:
                    i += 1
                    continue
                col_xs = [t.x for t in row]
                # Sütun genişliği komşu sütun orta noktalarından adaptif hesaplanır
                col_bounds: List[Tuple[float, float]] = []
                for ci, cx in enumerate(col_xs):
                    left_lim = (col_xs[ci - 1] + cx) * 0.5 if ci > 0 else (cx - 12.0 * h_med)
                    right_lim = (cx + col_xs[ci + 1]) * 0.5 if ci + 1 < len(col_xs) else (cx + 25.0 * h_med)
                    col_bounds.append((left_lim, right_lim))

                # Maksimum dikey satır boşluğu (başlık satırından 4.5H'dan fazla koparsa tablo biter)
                raw_matrix: List[List[str]] = [headers]
                dict_rows_g: List[Dict[str, str]] = []
                handles_used: List[str] = [t.handle for t in row if t.handle]
                prev_y = sum(t.y for t in row) / len(row)
                tbl_tokens = list(row)

                j = i + 1
                while j < len(y_rows):
                    cand_row = y_rows[j]
                    cand_y = sum(t.y for t in cand_row) / len(cand_row)
                    if abs(prev_y - cand_y) > 5.0 * h_med:
                        break
                    in_cols = [
                        t for t in cand_row
                        if col_bounds[0][0] <= t.x <= col_bounds[-1][1]
                    ]
                    if not in_cols:
                        break
                    row_cells = [""] * len(headers)
                    for t in in_cols:
                        best_ci = min(range(len(col_xs)), key=lambda ci: abs(t.x - col_xs[ci]))
                        if col_bounds[best_ci][0] <= t.x <= col_bounds[best_ci][1]:
                            row_cells[best_ci] = f"{row_cells[best_ci]} {t.text}".strip()
                            if t.handle:
                                handles_used.append(t.handle)
                            tbl_tokens.append(t)
                    if not any(row_cells):
                        break
                    raw_matrix.append(row_cells)
                    dict_rows_g.append({headers[ci] or f"COL_{ci+1}": row_cells[ci] for ci in range(len(headers))})
                    prev_y = cand_y
                    j += 1

                if len(dict_rows_g) >= 2:
                    tbl_idx += 1
                    xs = [t.x for t in tbl_tokens]
                    ys = [t.y for t in tbl_tokens]
                    out.append(NormalizedTable(
                        table_id=f"TBL_{tbl_idx:03d}",
                        sheet_id=sh.frame_id,
                        source_kind="TEXT_GRID",
                        title=sh.title or sh.role,
                        headers=headers,
                        rows=dict_rows_g,
                        raw_matrix=raw_matrix,
                        bbox_du=BBox2D(minx=min(xs), miny=min(ys), maxx=max(xs), maxy=max(ys)),
                        confidence=0.90,
                        source_handles=handles_used,
                    ))
                    i = j
                    continue
            i += 1

    return out


def extract_formula_blocks(
    sheets: List[SheetFrame],
    texts_by_frame: Dict[str, List[RawText]],
    paths_by_frame: Dict[str, List[RawPath]],
) -> List[FormulaBlock]:
    """
    Gerilim düşümü ve mühendislik kesir formüllerini yakalar.
    Kesir çizgisinin hem sağındaki hem de bir altındaki sonuç satırlarını (`%%%e =  0,36`) okur.
    """
    blocks: List[FormulaBlock] = []
    f_idx = 0

    for sh in sheets:
        f_texts = texts_by_frame.get(sh.frame_id, [])
        f_paths = paths_by_frame.get(sh.frame_id, [])
        if not f_texts:
            continue

        heights = [t.height for t in f_texts if t.height > 0]
        h_med = statistics.median(heights) if heights else 2.5

        # Aday kesir çubukları: en az 4 adet '-' veya '_' içeren metinler ya da yatay kısa çizgiler
        bars: List[Dict[str, object]] = []
        for t in f_texts:
            if re.search(r"[-_—]{4,}", t.text):
                # Örn: "0,0124 x ------------------" veya "------------------"
                m_c = re.match(r"^\s*(.*?)[-—_]{4,}", t.text)
                prefix_coeff = m_c.group(1).strip() if m_c else ""
                x_bar_min = t.bbox.minx + (len(prefix_coeff) * t.height * 0.55 if prefix_coeff else 0.0)
                bars.append({
                    "x_min": x_bar_min,
                    "x_max": max(t.bbox.maxx, x_bar_min + 3.0 * t.height),
                    "y": t.y,
                    "h": max(t.height, h_med),
                    "coeff": prefix_coeff,
                    "handles": [t.handle] if t.handle else [],
                })

        # Çizgisel yatay kesir çizgileri (yüksekliği ~0, uzunluğu 2H..22H arası olan LINE'lar)
        for p in f_paths:
            if p.dxftype == "LINE" and len(p.points) == 2:
                (x1, y1), (x2, y2) = p.points
                if abs(y2 - y1) <= 0.15 * h_med and (2.0 * h_med) <= abs(x2 - x1) <= (24.0 * h_med):
                    bars.append({
                        "x_min": min(x1, x2),
                        "x_max": max(x1, x2),
                        "y": (y1 + y2) * 0.5,
                        "h": h_med,
                        "coeff": "",
                        "handles": [p.handle] if p.handle else [],
                    })

        # Aynı noktadaki kesir çubuğu tekrarlarını temizle
        dedup_bars: List[Dict[str, object]] = []
        for b in bars:
            if not any(
                abs(float(b["y"]) - float(db["y"])) < 0.8 * h_med
                and abs(float(b["x_min"]) - float(db["x_min"])) < 2.0 * h_med
                for db in dedup_bars
            ):
                dedup_bars.append(b)

        for b in dedup_bars:
            bx0 = float(b["x_min"])
            bx1 = float(b["x_max"])
            by = float(b["y"])
            bh = float(b["h"])
            cx = (bx0 + bx1) * 0.5

            num_toks = [
                t for t in f_texts
                if (bx0 - 2.5 * bh) <= t.x <= (bx1 + 2.5 * bh)
                and (by + 0.15 * bh) <= t.y <= (by + 2.8 * bh)
                and re.search(r"\d", t.text)
                and not re.search(r"[-_—]{4,}", t.text)
            ]
            den_toks = [
                t for t in f_texts
                if (bx0 - 2.5 * bh) <= t.x <= (bx1 + 2.5 * bh)
                and (by - 2.8 * bh) <= t.y <= (by - 0.15 * bh)
                and re.search(r"\d", t.text)
                and not re.search(r"[-_—]{4,}", t.text)
            ]
            if not num_toks or not den_toks:
                continue

            # En yakın dikey pay ve payda
            num_t = min(num_toks, key=lambda t: abs(t.y - by) + abs(t.bbox.center[0] - cx) * 0.3)
            den_t = min(den_toks, key=lambda t: abs(t.y - by) + abs(t.bbox.center[0] - cx) * 0.3)

            # Soldaki ek katsayılar (bar metninin solunda)
            coeffs: List[str] = [str(b["coeff"])] if b["coeff"] else []
            coeff_toks = [
                t for t in f_texts
                if (bx0 - 10.0 * bh) <= t.x < bx0
                and abs(t.y - by) <= 1.2 * bh
                and re.search(r"\d+[.,]\d+", t.text)
                and t.handle not in list(b["handles"])  # type: ignore[operator]
            ]
            for ct in sorted(coeff_toks, key=lambda t: t.x):
                coeffs.append(ct.text.strip())

            # Sonuç Arama 1: Aynı satır sağında `= ...`
            res_toks = [
                t for t in f_texts
                if t.x >= bx1 - 1.5 * bh
                and t.x <= bx1 + 14.0 * bh
                and abs(t.y - by) <= 1.4 * bh
                and "=" in t.text
                and re.search(r"\d", t.text)
            ]

            parsed_val: Optional[float] = None
            res_texts: List[str] = []
            res_handles: List[str] = []
            if res_toks:
                res_toks.sort(key=lambda t: t.x)
                rt = res_toks[0]
                m_eq = re.search(r"=\s*%?\s*(\d+(?:[.,]\d+)?)", rt.text)
                if m_eq:
                    parsed_val = parse_tr_float(m_eq.group(1))
                    res_texts.append(rt.text.strip())
                    if rt.handle:
                        res_handles.append(rt.handle)

            # Sonuç Arama 2: Kesir çubuğunun ve paydanın altındaki sonuç satırı!
            # (Örn: üst satırda pay/payda, alt satırda "%%%e =" ve aynı satırda hizalı "0,36")
            if parsed_val is None:
                max_res_y = min(by - 1.8 * bh, den_t.y - 0.6 * bh)
                eq_anchors = [
                    t for t in f_texts
                    if (by - 7.5 * bh) <= t.y <= max_res_y
                    and t.x <= bx1 + 2.0 * bh
                    and t is not den_t
                    and ("=" in t.text or re.search(r"%\s*e", norm_tr(t.text)))
                ]
                below_nums = [
                    t for t in f_texts
                    if (by - 7.5 * bh) <= t.y <= max_res_y
                    and t is not den_t
                    and (bx0 - 2.0 * bh) <= t.bbox.center[0] <= (bx1 + 3.0 * bh)
                    and re.match(r"^[=%\s]*(\d+(?:[.,]\d+)?)\s*%?$", t.text.strip())
                    and ("=" in t.text or any(abs(ea.y - t.y) <= 0.9 * bh for ea in eq_anchors))
                ]
                if below_nums:
                    # Birden fazla alt sonuç satırı varsa (ör. %e1=0,36 ve altında toplam %e=0,74),
                    # paydaya en yakın ilk sonuç satırını al!
                    best_num = min(below_nums, key=lambda t: (abs(den_t.y - t.y), abs(t.bbox.center[0] - cx)))
                    m_bn = re.search(r"(\d+(?:[.,]\d+)?)", best_num.text)
                    if m_bn:
                        parsed_val = parse_tr_float(m_bn.group(1))
                        same_y_eq = [ea for ea in eq_anchors if abs(ea.y - best_num.y) <= 0.9 * bh]
                        for ea in same_y_eq:
                            res_texts.append(ea.text.strip())
                            if ea.handle:
                                res_handles.append(ea.handle)
                        res_texts.append(best_num.text.strip())
                        if best_num.handle:
                            res_handles.append(best_num.handle)

            used_handles = list(b["handles"])  # type: ignore[arg-type]
            for t in (num_t, den_t):
                if t.handle:
                    used_handles.append(t.handle)
            used_handles.extend(res_handles)

            # GD şeması içindeki hat kablo+uzunluk etiketini ("4x6NYY/6mm2" üstte / "30m" altta) ayrı sınıflandır
            is_cable_num = bool(re.search(r"(?:NYY|N2XH|NHXMH|NYM|TTR|XLPE|FE180|MM2|07Z1)", num_t.text, re.IGNORECASE))
            m_len_den = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*m\s*$", den_t.text.strip(), re.IGNORECASE)
            if is_cable_num and m_len_den and parsed_val is None:
                f_idx += 1
                seg_len = parse_tr_float(m_len_den.group(1))
                blocks.append(FormulaBlock(
                    formula_id=f"FRM_{f_idx:03d}",
                    sheet_id=sh.frame_id,
                    formula_kind="FEEDER_SEGMENT",
                    label=sh.title or f"{sh.frame_id}@{int(round(by))}",
                    numerator_texts=[num_t.text.strip()],
                    denominator_texts=[den_t.text.strip()],
                    coefficient_texts=[],
                    result_texts=[den_t.text.strip()],
                    parsed_result_value=seg_len,
                    parse_status="OK" if seg_len is not None else "PARTIAL",
                    bbox_du=BBox2D(
                        minx=min(bx0, num_t.bbox.minx, den_t.bbox.minx),
                        miny=den_t.bbox.miny,
                        maxx=max(bx1, num_t.bbox.maxx, den_t.bbox.maxx),
                        maxy=num_t.bbox.maxy,
                    ),
                    source_handles=used_handles,
                ))
                continue

            den_u = den_t.text.upper()
            has_arch_poz = any(w in den_u or w in num_t.text.upper() for w in ("DOZLU", "GRANIT", "GRANİT", "BETON", "SIVA", "SERAMIK", "SERAMİK", "MERMER", "BOYA", "KAPLAMA"))
            has_vd_math = (
                any(ch in den_t.text for ch in ("*", "x", "X", "·", "^", "²"))
                or bool(re.match(r"^\s*\d+(?:[.,]\d+)?\s*(?:[*xX·]\s*\d+(?:[.,]\d+)?\s*)+\s*$", den_t.text))
            )
            is_vd_signal = (not has_arch_poz) and (
                sh.role == "GERILIM_DUSUMU"
                or any("0,0124" in c or "0.0124" in c or "0,074" in c or "0.074" in c or "0,011" in c or "0,067" in c for c in coeffs)
                or (has_vd_math and bool(re.search(r"\b(?:56|380|400|220|230)\b", den_t.text)))
            )
            # Yalnızca gerçek gerilim düşümü / matematiksel formül bloklarını veya explicit '=' sonucu olanları al
            if not is_vd_signal and parsed_val is None:
                continue

            f_idx += 1
            kind = "VOLTAGE_DROP" if is_vd_signal else "GENERIC"

            blocks.append(FormulaBlock(
                formula_id=f"FRM_{f_idx:03d}",
                sheet_id=sh.frame_id,
                formula_kind=kind,  # type: ignore[arg-type]
                label=sh.title or f"{sh.frame_id}@{int(round(by))}",
                numerator_texts=[num_t.text.strip()],
                denominator_texts=[den_t.text.strip()],
                coefficient_texts=[c for c in coeffs if c],
                result_texts=res_texts,
                parsed_result_value=parsed_val,
                parse_status="OK" if parsed_val is not None else "PARTIAL",
                bbox_du=BBox2D(
                    minx=min(bx0, num_t.bbox.minx, den_t.bbox.minx),
                    miny=den_t.bbox.miny,
                    maxx=max(bx1, num_t.bbox.maxx, den_t.bbox.maxx),
                    maxy=num_t.bbox.maxy,
                ),
                source_handles=used_handles,
            ))

    return blocks
