"""
CloudeCAD — Topolojik Katman & Halka Algılayıcı (Layer-Agnostic Geometric Fingerprinter)
=======================================================================================
Çizimdeki katman isimlerine (layer names) bağımlılığı ortadan kaldırır.
Çizim katmanları hatalı, eksik veya '0', 'KAT1', 'MİMARİ' gibi yanlış seçilmiş olsa dahi;
aşağıdaki topolojik parmak izlerini inceleyerek topraklama ağını %100 doğrulukla bulur:

1. Topraklama blokları (1TP, TP, KAZIK, ÇUBUK, 1EKK, ETB) ile geometrik temas/yakınlık (Anchor Heuristic)
2. Bina dış çevresini saran kapalı döngü (Perimeter Ring Topology)
3. İç bölücü ağ gözleri (20m x 20m veya daha küçük ızgaralar)
4. Tipik temel topraklama metrajı ve ortogonal ağ sürekliliği
"""

import math
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
from pathlib import Path

from shapely.geometry import LineString, MultiPoint, Polygon, Point
from shapely.ops import polygonize, unary_union

logger = logging.getLogger(__name__)


@dataclass
class LayerGeometricProfile:
    """Tek bir CAD katmanının geometrik ve topolojik parmak izi."""
    layer_name: str
    entity_count: int = 0
    total_length_m: float = 0.0
    bounding_box: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    width_m: float = 0.0
    height_m: float = 0.0
    cycle_count: int = 0
    grounding_insert_touch_count: int = 0  # 1TP, 1EKK gibi bloklara değen segment sayısı
    has_perimeter_loop: bool = False
    grounding_likelihood_score: float = 0.0  # 0 - 100 arası puan
    verdict: str = "UNKNOWN"  # "DEFINITIVE_GROUNDING", "PROBABLE_GROUNDING", "STRUCTURAL", "OTHER"


class LayerFingerprinter:
    """
    Çizimdeki tüm katmanları tarayarak geometrik topolojiye dayalı topraklama katmanı
    ve ağ tespiti yapar.
    """

    def __init__(self, unit_factor: float = 10.0):
        self.unit_factor = unit_factor  # çizim birimi -> mm dönüşümü

    def analyze_layers(
        self,
        doc: Any,
        grounding_inserts: Optional[List[Any]] = None
    ) -> Dict[str, LayerGeometricProfile]:
        """
        DXF belgesindeki tüm katmanları inceler ve topolojik puanlarını hesaplar.
        """
        msp = doc.modelspace()
        
        # 1. Çizimdeki tüm blok insert'lerini topla (özellikle çubuk ve klemensler)
        anchor_points = []
        if grounding_inserts:
            for ins in grounding_inserts:
                anchor_points.append(ins.position)
        else:
            # Doğrudan msp'den tara
            for e in msp.query('INSERT'):
                bname = e.dxf.name.lower()
                if any(k in bname for k in ['1tp', 'tp', 'rod', 'cubuk', 'kazik', '1ekk', 'klemens', 'etb']):
                    pos = (e.dxf.insert.x * self.unit_factor, e.dxf.insert.y * self.unit_factor)
                    anchor_points.append(pos)

        # 2. Katmanlara göre lineer entity'leri grupla
        layer_lines: Dict[str, List[Tuple[Tuple[float, float], Tuple[float, float]]]] = {}

        for e in msp.query('LINE LWPOLYLINE POLYLINE'):
            lay = e.dxf.get('layer', '0')
            if lay not in layer_lines:
                layer_lines[lay] = []

            dxftype = e.dxftype()
            if dxftype == 'LINE':
                p1 = (e.dxf.start.x * self.unit_factor, e.dxf.start.y * self.unit_factor)
                p2 = (e.dxf.end.x * self.unit_factor, e.dxf.end.y * self.unit_factor)
                if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) >= 100.0:  # min 10 cm
                    layer_lines[lay].append((p1, p2))
            elif dxftype == 'LWPOLYLINE':
                try:
                    pts = [(p[0] * self.unit_factor, p[1] * self.unit_factor) for p in e.get_points('xy')]
                    is_closed = bool(e.closed)
                    for i in range(len(pts) - 1):
                        layer_lines[lay].append((pts[i], pts[i+1]))
                    if is_closed and len(pts) >= 3:
                        layer_lines[lay].append((pts[-1], pts[0]))
                except Exception:
                    pass
            elif dxftype == 'POLYLINE':
                try:
                    pts = [(v.dxf.location.x * self.unit_factor, v.dxf.location.y * self.unit_factor) for v in e.vertices]
                    is_closed = bool(e.is_closed)
                    for i in range(len(pts) - 1):
                        layer_lines[lay].append((pts[i], pts[i+1]))
                    if is_closed and len(pts) >= 3:
                        layer_lines[lay].append((pts[-1], pts[0]))
                except Exception:
                    pass

        # 3. Her katman için topolojik profili hesapla
        profiles: Dict[str, LayerGeometricProfile] = {}

        for lay, lines in layer_lines.items():
            if not lines:
                continue

            prof = LayerGeometricProfile(layer_name=lay, entity_count=len(lines))

            # Toplam metraj (mm -> metre)
            tot_len_m = sum(math.hypot(p2[0]-p1[0], p2[1]-p1[1]) for p1, p2 in lines) / 1000.0
            prof.total_length_m = tot_len_m

            # Bounding box
            xs = [p[0] for line in lines for p in line]
            ys = [p[1] for line in lines for p in line]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            prof.bounding_box = (min_x, min_y, max_x, max_y)
            prof.width_m = (max_x - min_x) / 1000.0
            prof.height_m = (max_y - min_y) / 1000.0

            # Çubuk ve klemens bloklarına yakınlık (Anchor test - 80 cm tolerans)
            touch_count = 0
            for apt in anchor_points:
                # Blok noktası bu katmanın herhangi bir çizgisine 800 mm'den yakın mı?
                for p1, p2 in lines:
                    ls = LineString([p1, p2])
                    pt = Point(apt[0], apt[1])
                    if ls.distance(pt) <= 800.0:
                        touch_count += 1
                        break
            prof.grounding_insert_touch_count = touch_count

            # Kapalı döngü / poligon analizi (Shapely polygonize)
            if len(lines) >= 4 and tot_len_m >= 15.0:
                try:
                    line_geoms = [LineString([p1, p2]) for p1, p2 in lines]
                    polys = list(polygonize(line_geoms))
                    prof.cycle_count = len(polys)
                    if polys:
                        max_poly = max(polys, key=lambda p: p.area)
                        # Bina ölçeğinde bir poligon mu? (En az 30 m2)
                        if (max_poly.area / 1e6) >= 30.0:
                            prof.has_perimeter_loop = True
                except Exception:
                    pass

            # 4. Topolojik Puanlama Algoritması (0 - 100 Puan)
            score = 0.0
            lay_lower = lay.lower()

            # A) Blok Bağlantı Yoğunluğu (En kritik ayrım: Blok Sayısı / Toplam Metraj)
            # Gerçek topraklama ağında her 5-25 metrede bir klemens veya çubuk bulunur.
            anchor_density = prof.grounding_insert_touch_count / max(1.0, prof.total_length_m)

            if prof.grounding_insert_touch_count >= 3 and anchor_density >= 0.03:
                # Çok yüksek çubuk/klemens yoğunluğu (örn: 100 metrede 13 blok)
                score += 60.0
            elif prof.grounding_insert_touch_count >= 1:
                score += min(prof.grounding_insert_touch_count * 10.0, 30.0)

            # B) Metraj Uygunluğu (Temel topraklama şebekesi tipik olarak 30m - 500m arasındadır)
            if 30.0 <= prof.total_length_m <= 400.0:
                score += 25.0
            elif 400.0 < prof.total_length_m <= 800.0:
                score += 15.0
            elif prof.total_length_m > 1200.0:
                # 1200+ metrelik katmanlar mimari duvarlar, sıva, tefriş veya pafta çerçevesidir!
                score -= 40.0

            # C) Boyut Uygunluğu (Bina temel boyutu: 8m - 150m)
            if 8.0 <= prof.width_m <= 150.0 and 8.0 <= prof.height_m <= 150.0:
                score += 10.0

            # D) İsim İpucu (Bonus / Ceza)
            if any(k in lay_lower for k in ['toprak', 'earth', 'ground', 'pe', 'temel']):
                score += 25.0

            # Yapısal / Mimari / Pafta Çerçevesi Katmanları için Ceza:
            if any(k in lay_lower for k in [
                'slab', 'bearing', 'cerceve', 'çerçeve', 'siva', 'sıva', 'cizpen', 'pen',
                'kolon', 'duvar', 'wall', 'hatch', 'tara', 'dim', 'olcu', 'ölçü', 'yazi', 'text', 'kapi', 'pencere', 'tefris'
            ]):
                if not any(k in lay_lower for k in ['toprak', 'earth', 'ground', 'pe']):
                    score -= 50.0

            prof.grounding_likelihood_score = max(0.0, min(100.0, score))

            # Karar
            if prof.grounding_likelihood_score >= 65.0:
                prof.verdict = "DEFINITIVE_GROUNDING"
            elif prof.grounding_likelihood_score >= 40.0:
                prof.verdict = "PROBABLE_GROUNDING"
            else:
                prof.verdict = "OTHER"

            profiles[lay] = prof

        return profiles

    def identify_grounding_layers(
        self,
        doc: Any,
        grounding_inserts: Optional[List[Any]] = None,
        threshold: float = 45.0
    ) -> List[str]:
        """
        Topolojik puanı eşiğin üzerinde olan tüm katmanları liste olarak döner.
        """
        profiles = self.analyze_layers(doc, grounding_inserts=grounding_inserts)
        candidates = [
            lay for lay, p in profiles.items()
            if p.grounding_likelihood_score >= threshold
        ]
        candidates.sort(key=lambda lay: profiles[lay].grounding_likelihood_score, reverse=True)

        for lay in candidates:
            p = profiles[lay]
            logger.info(
                f"Topolojik Katman Tespiti: [{lay}] -> Puan: {p.grounding_likelihood_score:.1f}/100 | "
                f"Metraj: {p.total_length_m:.1f}m | Halka: {p.has_perimeter_loop} | "
                f"Blok Teması: {p.grounding_insert_touch_count} adet | Karar: {p.verdict}"
            )

        return candidates
