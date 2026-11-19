# -*- coding: utf-8 -*-
"""
Evrensel Kapalı Mahal & Komşuluk Analizi (`mahal_analizi.py`)
===============================================================
`momepy.enclosures` + `geopandas` + `libpysal.weights.Queen` kullanarak
mimari/yapısal çizgilerden isim/katman ezberi olmadan kapalı mahalleri (oda,
peron, teknik hacim), alan/çevre metrajlarını, oda komşuluk grafını ve
sensör/armatür/kamera kapsama oranlarını çıkarır.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import geopandas as gpd
from libpysal.weights import Queen
import momepy
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .disiplin_ayirici import _is_door_arc
from .schema import RawPath, RawText


def extract_architectural_enclosures(
    arch_paths: Sequence[RawPath],
    du_to_m: float,
    texts: Optional[Sequence[RawText]] = None,
    *,
    min_area_m2: float = 1.5,
    max_area_m2: float = 25000.0,
) -> Tuple[List[Dict[str, Any]], gpd.GeoDataFrame]:
    """
    Mimari duvar/sınır çizgilerinden `momepy.enclosures` ile kapalı mahalleri
    ve `libpysal` Queen ile oda komşuluk ağını çıkarır.
    """
    scale = max(du_to_m, 1e-6)
    lines_m: List[LineString] = []
    for p in arch_paths:
        if p.dxftype not in ("LINE", "LWPOLYLINE", "POLYLINE"):
            continue
        if _is_door_arc(p, scale) or len(p.points) < 2:
            continue
        pts = [(x * scale, y * scale) for x, y in p.points]
        for i in range(len(pts) - 1):
            ls = LineString([pts[i], pts[i + 1]])
            if ls.length >= 0.15:
                lines_m.append(ls)
        if p.closed and pts[0] != pts[-1]:
            ls = LineString([pts[-1], pts[0]])
            if ls.length >= 0.15:
                lines_m.append(ls)

    empty_gdf = gpd.GeoDataFrame({"geometry": gpd.GeoSeries([], dtype="geometry")})
    if len(lines_m) < 3:
        return [], empty_gdf

    barriers_gdf = gpd.GeoDataFrame(geometry=lines_m)
    encl_gdf = momepy.enclosures(barriers_gdf)
    if encl_gdf is None or len(encl_gdf) == 0:
        return [], empty_gdf

    areas = encl_gdf.geometry.area
    valid = encl_gdf[(areas >= min_area_m2) & (areas <= max_area_m2)].copy()
    valid = valid[valid.geometry.is_valid & (~valid.geometry.is_empty)].reset_index(drop=True)
    if len(valid) == 0:
        return [], empty_gdf

    # Tüm küçük mahalleri içine alan tekil dış zarfı ele (en büyük çevre poligon tüm alt odaların birleşimi ise)
    if len(valid) > 1:
        max_idx = int(valid.geometry.area.idxmax())
        max_geom = valid.geometry.iloc[max_idx]
        other_sum = float(valid.geometry.drop(index=max_idx).area.sum())
        if max_geom.area > other_sum * 0.98 and other_sum > 0:
            contained = sum(
                1
                for j, g in enumerate(valid.geometry)
                if j != max_idx and max_geom.buffer(0.05).contains(g.representative_point())
            )
            if contained >= 2:
                valid = valid.drop(index=max_idx).reset_index(drop=True)

    valid["eID"] = list(range(len(valid)))

    neighbors_map: Dict[int, List[int]] = {i: [] for i in range(len(valid))}
    if len(valid) >= 2:
        try:
            w = Queen.from_dataframe(valid, use_index=False, silence_warnings=True)
            for eid, nbs in w.neighbors.items():
                neighbors_map[int(eid)] = [int(n) for n in nbs]
        except Exception:
            pass

    labels_by_eid: Dict[int, List[str]] = {i: [] for i in range(len(valid))}
    if texts:
        geoms = list(valid.geometry)
        tree = STRtree(geoms)
        for t in texts:
            txt = " ".join((t.text or "").split()).strip()
            if len(txt) < 2 or len(txt) > 55:
                continue
            pt = Point(t.x * scale, t.y * scale)
            for hit in tree.query(pt):
                idx = int(hit)
                if geoms[idx].contains(pt):
                    labels_by_eid[idx].append(txt)

    records: List[Dict[str, Any]] = []
    for idx, row in valid.iterrows():
        poly: Polygon = row.geometry
        c = poly.centroid
        lbl = " / ".join(labels_by_eid.get(idx, [])[:2])
        records.append({
            "enclosure_id": int(idx),
            "label": lbl,
            "area_m2": round(float(poly.area), 2),
            "perimeter_m": round(float(poly.length), 2),
            "centroid_m": (round(float(c.x), 3), round(float(c.y), 3)),
            "neighbor_ids": neighbors_map.get(idx, []),
            "geometry": poly,
        })

    return records, valid


def check_coverage_in_enclosures(
    enclosures: Sequence[Dict[str, Any]],
    sensor_points_m: Sequence[Tuple[float, float]],
    radius_m: float,
) -> List[Dict[str, Any]]:
    """
    Çıkarılan her kapalı mahal poligonu içinde verilen kapsama yarıçapıyla
    (`radius_m`, örn. duman detektörü 7.5 m) kapsanan ve açıkta kalan (m²) alanları hesaplar.
    """
    if not enclosures or radius_m <= 0:
        return []
    disks = [Point(x, y).buffer(radius_m) for x, y in sensor_points_m]
    covered_union = unary_union(disks) if disks else None

    out: List[Dict[str, Any]] = []
    for enc in enclosures:
        poly: Polygon = enc["geometry"]
        area = float(poly.area)
        if area <= 0:
            continue
        if covered_union is None or covered_union.is_empty:
            cov_area = 0.0
        else:
            cov_area = float(poly.intersection(covered_union).area)
        uncovered = max(0.0, area - cov_area)
        out.append({
            "enclosure_id": enc["enclosure_id"],
            "label": enc.get("label", ""),
            "area_m2": round(area, 2),
            "covered_m2": round(cov_area, 2),
            "uncovered_m2": round(uncovered, 2),
            "coverage_pct": round((cov_area / area) * 100.0, 2),
        })
    return out
