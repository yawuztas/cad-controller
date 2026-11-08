# -*- coding: utf-8 -*-
"""
CAD Geometri ve Metin Yeniden İnşa Motoru (Geometry & Text Reconstruction)
==========================================================================
"""

from __future__ import annotations
import math
import re
from typing import List, Dict, Optional, Tuple, Any
from shapely.geometry import box, Polygon, Point
from shapely.strtree import STRtree

from ..model.entities import TextToken, CalloutGroup, ExtractedTable


def clean_turkish_text(text: str) -> str:
    """Türkçe CAD çizimlerindeki bozuk karakter kodlamalarını temizler."""
    if not text:
        return ""
    t = text.strip()
    replacements = {
        r"\\U\+0130": "İ",
        r"\\U\+0131": "ı",
        r"\\U\+015E": "Ş",
        r"\\U\+015F": "ş",
        r"\\U\+011E": "Ğ",
        r"\\U\+011F": "ğ",
        r"\\U\+00DC": "Ü",
        r"\\U\+00FC": "ü",
        r"\\U\+00D6": "Ö",
        r"\\U\+00F6": "ö",
        r"\\U\+00C7": "Ç",
        r"\\U\+00E7": "ç",
        r"%%C": "Ø",
        r"%%c": "Ø",
        r"%%D": "°",
        r"%%d": "°",
        r"%%P": "±",
        r"%%p": "±",
        "\xdd": "İ",
        "\xfd": "ı",
        "\xde": "Ş",
        "\xfe": "ş",
        "\xd0": "Ğ",
        "\xf0": "ğ",
    }
    for pat, rep in replacements.items():
        t = re.sub(pat, rep, t)

    # MTEXT formatlama kodlarını temizle: \A1; \fArial|b0|i0; { } vb.
    t = re.sub(r"\\A[012];", "", t)
    t = re.sub(r"\\H[0-9.]+x;", "", t)
    t = re.sub(r"\\W[0-9.]+;", "", t)
    t = re.sub(r"\\f[^;]+;", "", t)
    t = re.sub(r"\\F[^;]+;", "", t)
    t = re.sub(r"\\C[0-9]+;", "", t)
    t = re.sub(r"\\p[^;]+;", "", t)
    t = re.sub(r"\\P", "\n", t)
    t = re.sub(r"[{}]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def strip_revit_view_suffix(block_name: str) -> str:
    """
    Revit görünüm soneklerini blok adından temizler.
    Örnek: 'Lineer Led 31W_3ph-AYD 02 FFL BİLET HOLÜ 1_5' -> 'Lineer Led 31W_3ph'
    """
    clean = re.sub(r"-[A-ZİÜÖÇŞĞ0-9_\s]+(?:FFL|SSL|KATI|HOLÜ|PERON|GÖRÜNÜM|BİLET).*$", "", block_name, flags=re.IGNORECASE)
    clean = re.sub(r"-\d+$", "", clean)
    clean = re.sub(r"_\d+$", "", clean)
    return clean.strip() or block_name.strip()


class TextReconstructionEngine:
    @classmethod
    def create_text_bbox(
        cls, pos: Tuple[float, float], text: str, height: float, rotation: float, is_paperspace: bool = False
    ) -> Polygon:
        w_factor = 0.65 if is_paperspace else 0.75
        width = max(len(text) * height * w_factor, height * 0.8)
        x0, y0 = pos[0], pos[1]
        x1, y1 = x0 + width, y0 + height
        rad = math.radians(rotation)
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)
        corners = [
            (x0, y0),
            (x0 + width * cos_r, y0 + width * sin_r),
            (x0 + width * cos_r - height * sin_r, y0 + width * sin_r + height * cos_r),
            (x0 - height * sin_r, y0 + height * cos_r),
        ]
        return Polygon(corners)

    @classmethod
    def stitch_horizontal_tokens(cls, tokens: List[TextToken], is_paperspace: bool = False) -> List[TextToken]:
        """Aynı satırda yan yana duran parçalı metinleri uzamsal olarak birleştirir."""
        if not tokens:
            return []

        tokens_by_layer: Dict[str, List[TextToken]] = {}
        for t in tokens:
            tokens_by_layer.setdefault(t.layer, []).append(t)

        stitched: List[TextToken] = []

        for layer, layer_tokens in tokens_by_layer.items():
            if len(layer_tokens) == 1:
                stitched.append(layer_tokens[0])
                continue

            used = set()
            for i, t1 in enumerate(layer_tokens):
                if i in used:
                    continue

                cluster = [t1]
                used.add(i)
                h = max(t1.height, 2.0)
                y_tol = 0.55 * h if is_paperspace else 0.80 * h
                max_dx = 5.0 * h if is_paperspace else 4.0 * h

                for j, t2 in enumerate(layer_tokens):
                    if j in used:
                        continue
                    if abs(t2.rotation - t1.rotation) < 5.0:
                        dy = abs(t2.pos[1] - t1.pos[1])
                        dx = t2.pos[0] - t1.pos[0]
                        if dy <= y_tol and -0.5 * h <= dx <= max_dx:
                            cluster.append(t2)
                            used.add(j)

                if len(cluster) == 1:
                    if not t1.source_handles and t1.dxf_handle:
                        t1.source_handles = [t1.dxf_handle]
                    stitched.append(t1)
                else:
                    cluster.sort(key=lambda t: t.pos[0])
                    comb_text = " ".join(t.text for t in cluster).strip()
                    comb_text = re.sub(r"\s+", " ", comb_text)
                    min_x = min(t.pos[0] for t in cluster)
                    avg_y = sum(t.pos[1] for t in cluster) / len(cluster)
                    max_h = max(t.height for t in cluster)
                    src_handles = []
                    for t in cluster:
                        if t.source_handles:
                            src_handles.extend(t.source_handles)
                        elif t.dxf_handle:
                            src_handles.append(t.dxf_handle)
                    stitched.append(TextToken(
                        text=comb_text,
                        pos=(min_x, avg_y, cluster[0].pos[2]),
                        height=max_h,
                        rotation=cluster[0].rotation,
                        layer=layer,
                        color=cluster[0].color,
                        bbox=cls.create_text_bbox((min_x, avg_y), comb_text, max_h, cluster[0].rotation, is_paperspace),
                        parent_block=cluster[0].parent_block,
                        is_attribute=any(t.is_attribute for t in cluster),
                        attrib_tag=cluster[0].attrib_tag,
                        dxf_handle=cluster[0].dxf_handle,
                        source_handles=src_handles,
                        owner_block=cluster[0].owner_block,
                    ))

        return stitched

    @classmethod
    def group_vertical_callouts(
        cls, tokens: List[TextToken], floorplan_callouts: Optional[List[CalloutGroup]] = None
    ) -> List[CalloutGroup]:
        """Alt alta dizili mühendislik etiketlerini ve FloorPlan kablo kesitlerini gruplar."""
        callouts: List[CalloutGroup] = []
        if floorplan_callouts:
            callouts.extend(floorplan_callouts)

        if not tokens:
            return callouts

        tokens_by_layer: Dict[str, List[TextToken]] = {}
        for t in tokens:
            tokens_by_layer.setdefault(t.layer, []).append(t)

        tray_kw = re.compile(r"^(?:LV|WC|MV|HV|FA|TEL|SEC|UPS|EM)\d{2}-[A-Z0-9]+", re.IGNORECASE)
        mech_kw = re.compile(r"^(?:TVC|MVS|EXC|CDB|BAP|DAP|WSH|FPP|ACP|MCC)\d{2}", re.IGNORECASE)

        for layer, lay_tokens in tokens_by_layer.items():
            used = set()
            for i, t1 in enumerate(lay_tokens):
                if i in used:
                    continue

                t1_up = t1.text.upper()
                is_tray = bool(tray_kw.search(t1_up)) or "TAVA" in layer.upper()
                is_mech = bool(mech_kw.search(t1_up))

                if is_tray or is_mech:
                    cat = "TRAY_TAG" if is_tray else "MECHANICAL_LOAD"
                    callouts.append(CalloutGroup(
                        lines=[t1.text],
                        pos=(t1.pos[0], t1.pos[1]),
                        layer=layer,
                        parent_block=t1.parent_block,
                        category=cat,
                        metadata={"raw_tag": t1.text, "circuit_id": t1.text.split("/")[0] if "/" in t1.text else t1.text}
                    ))
                    used.add(i)

        return callouts


class GeometricTableExtractor:
    @classmethod
    def extract_grid_table(
        cls,
        name: str,
        xy_texts: List[Tuple[float, float, str]],
        header_keywords: Tuple[str, ...],
        row_tol: float = 4.5,
        source_space: str = "PAPERSPACE",
    ) -> Optional[ExtractedTable]:
        if not xy_texts:
            return None

        hdr_y = None
        hdr_tokens = []
        for x, y, val in sorted(xy_texts, key=lambda item: -item[1]):
            v_up = val.upper()
            if any(k in v_up for k in header_keywords):
                hdr_y = y
                break

        if hdr_y is None:
            return None

        hdr_row = [t for t in xy_texts if abs(t[1] - hdr_y) <= row_tol]
        hdr_row.sort(key=lambda item: item[0])
        headers = [t[2] for t in hdr_row]
        col_x = [t[0] for t in hdr_row]

        if len(col_x) < 2:
            return None

        data_tokens = [t for t in xy_texts if t[1] < (hdr_y - row_tol)]
        data_by_y: Dict[int, List[Tuple[float, float, str]]] = {}
        for x, y, val in data_tokens:
            bin_idx = int(round(y / (row_tol * 2.0)))
            data_by_y.setdefault(bin_idx, []).append((x, y, val))

        rows: List[Dict[str, str]] = []
        for bin_idx, row_toks in sorted(data_by_y.items(), key=lambda item: -item[0]):
            r_dict = {h: "" for h in headers}
            for x, y, val in row_toks:
                best_ci = min(range(len(col_x)), key=lambda ci: abs(col_x[ci] - x))
                if abs(col_x[best_ci] - x) <= 60.0:
                    r_dict[headers[best_ci]] = val
            if any(v for v in r_dict.values()):
                rows.append(r_dict)

        if not rows:
            return None

        all_xs = [t[0] for t in xy_texts]
        all_ys = [t[1] for t in xy_texts]
        tbl_box = box(min(all_xs), min(all_ys), max(all_xs), max(all_ys))

        return ExtractedTable(
            name=name,
            headers=headers,
            rows=rows,
            bbox=tbl_box,
            source_space=source_space,
            table_type="CABLE_OR_LOAD_SCHEDULE",
        )
