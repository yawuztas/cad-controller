# -*- coding: utf-8 -*-
"""
Fiziksel Güzergah ve Tava Topoloji Motoru (PhysicalRouteBuilder)
===============================================================
Grid Hash (O(1)) snapping ile LINE ve ARC parçalarını kesintisiz güzergahlara birleştirir.
"""

from __future__ import annotations
import math
import networkx as nx
from typing import List, Dict, Tuple, Any
from shapely.geometry import LineString, MultiLineString
from ezdxf.math import Vec3, Matrix44

from ..model.entities import LinearRoute


class PhysicalRouteBuilder:
    @classmethod
    def build_physical_routes(cls, raw_geoms: List[Dict[str, Any]], tolerance_mm: float = 60.0) -> List[LinearRoute]:
        lines_by_layer: Dict[str, List[Tuple[LineString, str, str]]] = {}

        for item in raw_geoms:
            ent = item["entity"]
            mat: Matrix44 = item["matrix"]
            dtype = ent.dxftype()
            layer = item["layer"]
            ent_handle = getattr(ent.dxf, "handle", "")
            owner_blk = item.get("owner_block", "MODELSPACE")

            try:
                if dtype == "LINE":
                    p1 = mat.transform(ent.dxf.start)
                    p2 = mat.transform(ent.dxf.end)
                    if math.hypot(p2.x - p1.x, p2.y - p1.y) > 5.0:
                        lines_by_layer.setdefault(layer, []).append(
                            (LineString([(p1.x, p1.y), (p2.x, p2.y)]), ent_handle, owner_blk)
                        )
                elif dtype == "ARC":
                    center = mat.transform(ent.dxf.center)
                    r = ent.dxf.radius * getattr(mat, "a11", 1.0)
                    sa = math.radians(ent.dxf.start_angle)
                    ea = math.radians(ent.dxf.end_angle)
                    if ea < sa:
                        ea += 2 * math.pi
                    steps = max(int(math.degrees(ea - sa) / 15), 4)
                    pts = []
                    for s in range(steps + 1):
                        ang = sa + (ea - sa) * (s / steps)
                        pts.append((center.x + r * math.cos(ang), center.y + r * math.sin(ang)))
                    lines_by_layer.setdefault(layer, []).append((LineString(pts), ent_handle, owner_blk))
                elif dtype in ("LWPOLYLINE", "POLYLINE"):
                    pts = [mat.transform(Vec3(p[0], p[1], 0.0)) for p in ent.get_points()]
                    if len(pts) >= 2:
                        lines_by_layer.setdefault(layer, []).append(
                            (LineString([(p.x, p.y) for p in pts]), ent_handle, owner_blk)
                        )
            except Exception:
                pass

        routes: List[LinearRoute] = []

        for layer, l_geoms in lines_by_layer.items():
            if not l_geoms:
                continue

            G = nx.Graph()
            node_coords: Dict[int, Tuple[float, float]] = {}
            grid_bins: Dict[Tuple[int, int], List[int]] = {}
            node_id = 0

            def _get_node(pt: Tuple[float, float]) -> int:
                nonlocal node_id
                gx = int(round(pt[0] / tolerance_mm))
                gy = int(round(pt[1] / tolerance_mm))

                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        bin_key = (gx + dx, gy + dy)
                        if bin_key in grid_bins:
                            for cand_id in grid_bins[bin_key]:
                                c = node_coords[cand_id]
                                if math.hypot(c[0] - pt[0], c[1] - pt[1]) <= tolerance_mm:
                                    return cand_id

                nid = node_id
                node_coords[nid] = pt
                grid_bins.setdefault((gx, gy), []).append(nid)
                node_id += 1
                return nid

            for line, hnd, oblk in l_geoms:
                coords = list(line.coords)
                u = _get_node(coords[0])
                v = _get_node(coords[-1])
                length = line.length
                G.add_edge(u, v, weight=length, geom=line, handle=hnd, owner_block=oblk)

            for comp in nx.connected_components(G):
                subG = G.subgraph(comp)
                total_len = sum(d["weight"] for _, _, d in subG.edges(data=True)) / 1000.0
                if total_len > 0.5:
                    sub_geoms = [d["geom"] for _, _, d in subG.edges(data=True)]
                    sub_handles = [d["handle"] for _, _, d in subG.edges(data=True) if d.get("handle")]
                    sub_owners = [d.get("owner_block", "MODELSPACE") for _, _, d in subG.edges(data=True)]
                    comb = sub_geoms[0] if len(sub_geoms) == 1 else MultiLineString(sub_geoms)
                    subsystem = "TRAY" if "TRAY" in layer.upper() or "TAVA" in layer.upper() else "CABLE"
                    routes.append(LinearRoute(
                        layer=layer,
                        color=256,
                        linetype="CONTINUOUS",
                        total_length_m=round(total_len, 2),
                        geometry=comb,
                        subsystem=subsystem,
                        entity_handles=sub_handles,
                        owner_block=sub_owners[0] if sub_owners else "MODELSPACE",
                    ))

        return routes
