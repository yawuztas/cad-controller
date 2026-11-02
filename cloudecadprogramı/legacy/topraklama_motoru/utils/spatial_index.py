"""
CloudeCAD — Yüksek Performanslı Uzamsal İndeksleme Motoru (Shapely 2.0 STRtree)
==============================================================================
O(N x M) ve O(M^2) karmaşıklığındaki iç içe geometri arama döngülerini
C-tabanlı R-Tree (Shapely STRtree) veri yapısıyla O(N log M) seviyesine indirir.
50.000+ segmentli büyük altyapı, metro ve endüstriyel tesis paftalarında
mesafe ve T-ek klemens sorgularını 50-100 kat hızlandırır.
"""

import math
from typing import List, Tuple, Optional, Any
from shapely.geometry import Point, LineString
from shapely.strtree import STRtree


class ConductorSpatialIndex:
    """
    Topraklama iletken segmentlerini (LineString) R-Tree içinde indeksler.
    Herhangi bir (X, Y) noktasından en yakın iletkene olan Öklid mesafesini
    ve en yakın iletkeni milisaniyeler içinde bulur.
    """

    def __init__(self, segments: List[Any]):
        self.lines: List[LineString] = []
        self.layers: List[str] = []
        self.raw_segments: List[Any] = []

        for s in segments:
            if s.start != s.end:
                self.lines.append(LineString([s.start, s.end]))
                self.layers.append(getattr(s, "layer", ""))
                self.raw_segments.append(s)

        self._tree: Optional[STRtree] = STRtree(self.lines) if self.lines else None

    @property
    def is_empty(self) -> bool:
        return len(self.lines) == 0

    def nearest_distance_and_layer(self, x: float, y: float) -> Tuple[float, str]:
        """
        Verilen (x, y) noktasına en yakın topraklama iletkeninin mesafesini
        ve katman adını döner.
        """
        if not self._tree or not self.lines:
            return (999.9, "YOK")

        pt = Point(x, y)
        idx = self._tree.nearest(pt)
        if idx is None:
            return (999.9, "YOK")

        # Shapely 2.0 STRtree.nearest skaler sorguda tam sayı indeks döner
        idx_int = int(idx)
        dist = float(pt.distance(self.lines[idx_int]))
        return (dist, self.layers[idx_int])

    def find_t_junction_missing_clamps(
        self,
        clamp_points: List[Tuple[float, float]],
        junction_tol: float = 0.25,
        endpoint_margin: float = 0.25,
        clamp_search_radius: float = 1.20,
        min_cluster_dist: float = 1.50,
        min_branch_length: float = 0.20,
    ) -> List[Tuple[float, float]]:
        """
        Bir iletkenin uç noktasının başka bir iletkenin gövdesine (T-ek / branşman)
        saplandığı noktaları STRtree ile O(M log M) hızında bulur ve yakınında
        klemens ('kkk') sembolü olmayanları döndürür.
        """
        if not self._tree or not self.lines:
            return []

        clamp_pts_geom = [Point(cx, cy) for cx, cy in clamp_points]
        clamp_tree = STRtree(clamp_pts_geom) if clamp_pts_geom else None

        missing_clamps: List[Tuple[float, float]] = []

        for i, line_a in enumerate(self.lines):
            if line_a.length < min_branch_length:
                continue
            coords = list(line_a.coords)
            for ep in (coords[0], coords[-1]):
                ep_pt = Point(ep[0], ep[1])
                # Sadece ep_pt çevresindeki junction_tol mesafesindeki aday çizgileri sorgula
                candidate_indices = self._tree.query(ep_pt.buffer(junction_tol))
                is_t_junction = False

                for j in candidate_indices:
                    j_int = int(j)
                    if i == j_int:
                        continue
                    line_b = self.lines[j_int]
                    if line_b.distance(ep_pt) <= junction_tol:
                        b_coords = list(line_b.coords)
                        b_start = Point(b_coords[0])
                        b_end = Point(b_coords[-1])
                        # Gövdeye saplanma kontrolü (köşe dönüşü değil, gerçek T-ek)
                        if b_start.distance(ep_pt) > endpoint_margin and b_end.distance(ep_pt) > endpoint_margin:
                            is_t_junction = True
                            break

                if is_t_junction:
                    has_clamp = False
                    if clamp_tree is not None:
                        near_clamps = clamp_tree.query(ep_pt.buffer(clamp_search_radius))
                        for c_idx in near_clamps:
                            if clamp_pts_geom[int(c_idx)].distance(ep_pt) <= clamp_search_radius:
                                has_clamp = True
                                break

                    if not has_clamp:
                        if not any(math.hypot(ep[0] - mx, ep[1] - my) < min_cluster_dist for mx, my in missing_clamps):
                            missing_clamps.append((round(ep[0], 2), round(ep[1], 2)))

        return missing_clamps


class PointSpatialIndex:
    """
    Metinleri, mahalleri veya ekipman noktalarını R-Tree ile indeksler;
    en yakın mahal / etiket sorgularını anında yanıtlar.
    """

    def __init__(self, items: List[Tuple[float, float, Any]]):
        """items: [(x, y, payload), ...]"""
        self.points: List[Point] = []
        self.payloads: List[Any] = []
        for x, y, payload in items:
            self.points.append(Point(x, y))
            self.payloads.append(payload)
        self._tree: Optional[STRtree] = STRtree(self.points) if self.points else None

    def nearest_within(self, x: float, y: float, max_dist: float) -> Optional[Tuple[float, Any]]:
        """(x, y) noktasına max_dist mesafedeki en yakın öğeyi (mesafe, payload) döner."""
        if not self._tree or not self.points:
            return None
        pt = Point(x, y)
        idx = self._tree.nearest(pt)
        if idx is None:
            return None
        idx_int = int(idx)
        dist = float(pt.distance(self.points[idx_int]))
        if dist <= max_dist:
            return (dist, self.payloads[idx_int])
        return None
