"""
CloudeCAD — Süperpozisyon CAD Çekirdeği (CAD Superposer Engine 2.0)
==================================================================
Kablo Tavası (GN-13), Kuvvet Dağıtım (PS-11), Aydınlatma & Priz (PS-16),
Döşemealtı Borulama (GN-14) ve Mimari Referans (ARC) paftalarını ortak
BIM koordinat sisteminde açar.

Yenilikler (v2.0):
• Yalnızca aktif kat planı ana görünümünü ('M3-ELC' & 'rvt-1') hedefleyerek
  harici kesit, lejant, anahtar pafta (rvt-2/3/4) ve yabancı disiplin bloklarını filtreler.
• S-GRID (aks çizgileri), M-AREA-IDEN (mahal çaprazları) ve A-WALL-HDLN gibi
  elektrik dışı katmanları temizler.
• Shapely 2.0+ STRtree ile en yakın tava etiketi (LV vs WC) uzamsal eşleştirmesi
  yaparak Zayıf Akım (WC) ve Alçak Gerilim (LV) tavalarını gerçek koordinatlarında ayırır.
• Uzamsal tekilleştirme (spatial deduplication) ile mükerrer çizgileri temizler.
• Dinamik kat planı sınır tespiti (Quantile-based dynamic bounds).
"""

import math
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass

import ezdxf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
from shapely import Point, LineString, STRtree

# Elektrik tesisatı olmayan yardımcı/mimari/aks katmanları filtresi
NON_ELECTRICAL_LAYERS = {
    "S-GRID",
    "S-GRID-IDEN",
    "M-AREA-IDEN",
    "A-ANNO-NOTE",
    "A-ANNO-IDEN",
    "E-CABL-TRAY-ANNO",
    "G-ANNO-TEXT",
    "A-WALL-HDLN",
}


@dataclass
class SuperposeSegment:
    """Süperpozisyon çizgisi (hat parçası)."""
    x1: float
    y1: float
    x2: float
    y2: float
    category: str       # TAVA_LV, TAVA_WC, KABLO_NORM, KABLO_FE180, KUVVET, BORU, MIMARI
    source_layer: str
    length_m: float = 0.0
    width_mm: int = 300
    elevation_mm: int = 3750

    def __post_init__(self):
        self.length_m = math.hypot(self.x2 - self.x1, self.y2 - self.y1) / 1000.0


@dataclass
class SuperposeAnnotation:
    """Tava kot/ebat veya pano etiketi."""
    x: float
    y: float
    text: str
    category: str       # TAVA_LV_TAG, TAVA_WC_TAG, PANO_TAG
    width_mm: int = 300
    height_mm: int = 60
    elevation_mm: int = 3750


class CadSuperposer:
    """
    Kablo ve Tava projelerini üst üste bindiren (süperpoze eden) CAD motoru.
    """

    def __init__(self, station_name: str = "Çobançeşme - Kuyumcukent İstasyonu", station_key: str = "M09-S24"):
        self.station_name = station_name
        self.station_key = station_key
        self.segments: List[SuperposeSegment] = []
        self.annotations: List[SuperposeAnnotation] = []
        self.panels: List[Tuple[float, float, str]] = []
        self.clash_points: List[Tuple[float, float, str, str]] = []

        # Dinamik Kat Planı Sınırları (Her istasyonun kendi koordinat sistemine otomatik adapte olur)
        self.x_min = -1e9
        self.x_max = 1e9
        self.y_min = -1e9
        self.y_max = 1e9
        self._bounds_locked = False

        # Uzamsal Tekilleştirme Kümesi (Spatial Deduplication Grid)
        self._seen_segment_keys: Set[Tuple[int, int, int, int, str]] = set()

    def _find_primary_inserts(self, msp, discipline_keyword: str) -> List[Any]:
        """Ana kat planı modelspace viewport referanslarını ('rvt-') dinamik olarak bulur."""
        cand = [
            e for e in msp if e.dxftype() == 'INSERT'
            and discipline_keyword in e.dxf.name
            and not any(n in e.dxf.name.upper() for n in ['KESİT', 'KESIT', 'SECT', 'KUYU', 'DETAY', 'DETAIL', 'LEJAND', 'LEGEND'])
        ]
        rvt1 = [e for e in cand if 'rvt-1' in e.dxf.name]
        if rvt1:
            return rvt1
        rvt2 = [e for e in cand if 'rvt-2' in e.dxf.name]
        if rvt2:
            return rvt2
        return cand[:1]

    def _get_primitives(self, ins_entity) -> List[Any]:
        """İç içe geçmiş (nested) tüm blokları özyinelemeli olarak primitif entity'lere açar."""
        results = []
        stack = [ins_entity]
        while stack:
            cur = stack.pop()
            try:
                for ve in cur.virtual_entities():
                    if ve.dxftype() == 'INSERT':
                        stack.append(ve)
                    else:
                        results.append(ve)
            except Exception:
                pass
        return results

    def _is_in_bounds(self, x: float, y: float) -> bool:
        if not self._bounds_locked:
            return True
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max

    def _is_duplicate_segment(self, x1: float, y1: float, x2: float, y2: float, cat: str, snap_grid_mm: float = 15.0) -> bool:
        """15 mm toleransla aynı koordinattaki mükerrer çizgileri tekilleştirir."""
        gx1, gy1 = round(x1 / snap_grid_mm), round(y1 / snap_grid_mm)
        gx2, gy2 = round(x2 / snap_grid_mm), round(y2 / snap_grid_mm)
        p1, p2 = (gx1, gy1), (gx2, gy2)
        if p1 > p2:
            p1, p2 = p2, p1
        key = (p1[0], p1[1], p2[0], p2[1], cat)
        if key in self._seen_segment_keys:
            return True
        self._seen_segment_keys.add(key)
        return False

    def update_dynamic_bounds(self, margin_mm: float = 4000.0):
        """Elektrik ve tava çizgilerinin yoğunluğuna göre dinamik sınırları hassaslaştırır."""
        elc_segs = [s for s in self.segments if s.category in ("TAVA_LV", "TAVA_WC", "KABLO_NORM", "KABLO_FE180", "KUVVET")]
        if not elc_segs:
            return
        xs = [s.x1 for s in elc_segs] + [s.x2 for s in elc_segs]
        ys = [s.y1 for s in elc_segs] + [s.y2 for s in elc_segs]
        self.x_min = float(np.percentile(xs, 0.1)) - margin_mm
        self.x_max = float(np.percentile(xs, 99.9)) + margin_mm
        self.y_min = float(np.percentile(ys, 0.1)) - margin_mm
        self.y_max = float(np.percentile(ys, 99.9)) + margin_mm
        self._bounds_locked = True

    def extract_architectural_base(self, dxf_path: Path) -> int:
        """Mimari / Strüktürel duvar referanslarını (yalnızca rvt-1 ana görünümünden) çıkarır."""
        count = 0
        try:
            doc = ezdxf.readfile(str(dxf_path))
            msp = doc.modelspace()
            arc_inserts = (
                self._find_primary_inserts(msp, 'M3-ARC') or
                self._find_primary_inserts(msp, 'GN-32') or
                self._find_primary_inserts(msp, 'M3-STR')
            )

            for ins in arc_inserts[:1]:
                prims = self._get_primitives(ins)
                for ve in prims:
                    lay_u = ve.dxf.layer.upper()
                    if lay_u in ("S-GRID", "S-GRID-IDEN", "M-AREA-IDEN"):
                        continue
                    if ve.dxftype() == 'LINE':
                        x1, y1 = ve.dxf.start.x, ve.dxf.start.y
                        x2, y2 = ve.dxf.end.x, ve.dxf.end.y
                        if self._is_in_bounds(x1, y1) and self._is_in_bounds(x2, y2):
                            if not self._is_duplicate_segment(x1, y1, x2, y2, "MIMARI", snap_grid_mm=50.0):
                                self.segments.append(SuperposeSegment(x1, y1, x2, y2, "MIMARI", ve.dxf.layer))
                                count += 1
                    elif ve.dxftype() == 'LWPOLYLINE':
                        pts = [(p[0], p[1]) for p in ve.get_points('xy')]
                        for i in range(len(pts) - 1):
                            x1, y1 = pts[i]
                            x2, y2 = pts[i + 1]
                            if self._is_in_bounds(x1, y1) and self._is_in_bounds(x2, y2):
                                if not self._is_duplicate_segment(x1, y1, x2, y2, "MIMARI", snap_grid_mm=50.0):
                                    self.segments.append(SuperposeSegment(x1, y1, x2, y2, "MIMARI", ve.dxf.layer))
                                    count += 1
        except Exception as e:
            print(f"Uyarı: Mimari altlık çıkarılırken hata ({dxf_path.name}): {e}")
        return count

    def extract_tava_entities(self, dxf_path: Path) -> int:
        """
        GN-13 Kablo Tavası paftasından (yalnızca M3-ELC rvt-1 ana görünümünden) tava geometrisini çıkarır.
        Shapely 2.0 STRtree ile her tava çizgisine en yakın LV/ veya WC/ etiketini
        eşleştirerek gerçek Zayıf Akım ve Alçak Gerilim ayrımını yapar.
        """
        count = 0
        try:
            doc = ezdxf.readfile(str(dxf_path))
            msp = doc.modelspace()

            # 1. Modelspace'teki tava etiketlerini topla (Örn: LV/ 300/ 3750, WC/ 100/ 4080)
            local_annos: List[SuperposeAnnotation] = []
            for e in msp:
                if e.dxftype() in ('TEXT', 'MTEXT'):
                    txt = (e.dxf.text if hasattr(e.dxf, 'text') else e.text).strip()
                    if any(k in txt for k in ['LV/', 'WC/', 'MV/']):
                        parts = [p.strip() for p in txt.replace('\\P', ' ').split('/')]
                        w_mm = 300
                        el_mm = 3750
                        cat = "TAVA_LV_TAG" if "LV" in txt else "TAVA_WC_TAG"
                        if len(parts) >= 3:
                            try:
                                w_mm = int(parts[1])
                                el_mm = int(parts[2].split()[0])
                            except (ValueError, IndexError):
                                pass
                        ins_pt = getattr(e.dxf, 'insert', None)
                        if ins_pt and self._is_in_bounds(ins_pt.x, ins_pt.y):
                            anno = SuperposeAnnotation(
                                x=ins_pt.x, y=ins_pt.y, text=txt, category=cat,
                                width_mm=w_mm, elevation_mm=el_mm
                            )
                            local_annos.append(anno)
                            self.annotations.append(anno)

            # 2. Etiketleri Shapely STRtree içine indeksle
            anno_tree = None
            anno_points = []
            if local_annos:
                anno_points = [Point(a.x, a.y) for a in local_annos]
                anno_tree = STRtree(anno_points)

            # 3. Ana Kat Planı Elektrik Modeli ('rvt-') bloğunu aç
            elc_inserts = self._find_primary_inserts(msp, 'M3-ELC')

            raw_tray_lines = []
            for ins in elc_inserts[:1]:
                prims = self._get_primitives(ins)
                for ve in prims:
                    lay_u = ve.dxf.layer.upper()
                    if lay_u in NON_ELECTRICAL_LAYERS:
                        continue
                    if ve.dxftype() == 'LINE':
                        x1, y1 = ve.dxf.start.x, ve.dxf.start.y
                        x2, y2 = ve.dxf.end.x, ve.dxf.end.y
                        if self._is_in_bounds(x1, y1) and self._is_in_bounds(x2, y2):
                            raw_tray_lines.append((x1, y1, x2, y2, ve.dxf.layer))
                    elif ve.dxftype() == 'LWPOLYLINE':
                        pts = [(p[0], p[1]) for p in ve.get_points('xy')]
                        for i in range(len(pts) - 1):
                            x1, y1 = pts[i]
                            x2, y2 = pts[i + 1]
                            if self._is_in_bounds(x1, y1) and self._is_in_bounds(x2, y2):
                                raw_tray_lines.append((x1, y1, x2, y2, ve.dxf.layer))

            # 4. STRtree ile her tava çizgisine en yakın etiketi ata
            for x1, y1, x2, y2, lay in raw_tray_lines:
                lay_u = lay.upper()
                cat = "TAVA_LV"
                w_mm = 300
                el_mm = 3750

                if any(k in lay_u for k in ['WC', 'ZAYIF', 'DATA', 'TEL']):
                    cat = "TAVA_WC"
                    el_mm = 4080

                if anno_tree is not None:
                    geom = LineString([(x1, y1), (x2, y2)])
                    near_idx = anno_tree.nearest(geom)
                    dist_to_tag = geom.distance(anno_points[near_idx])

                    if dist_to_tag <= 8000.0:  # 8.0 m koridor komşuluğu
                        target_anno = local_annos[near_idx]
                        cat = "TAVA_WC" if target_anno.category == "TAVA_WC_TAG" else "TAVA_LV"
                        w_mm = target_anno.width_mm
                        el_mm = target_anno.elevation_mm

                if not self._is_duplicate_segment(x1, y1, x2, y2, cat, snap_grid_mm=15.0):
                    self.segments.append(SuperposeSegment(
                        x1, y1, x2, y2, cat, lay, width_mm=w_mm, elevation_mm=el_mm
                    ))
                    count += 1

        except Exception as e:
            print(f"Hata: {dxf_path.name} tava verisi çıkarılamadı: {e}")
        return count

    def extract_lighting_cables(self, dxf_path: Path) -> int:
        """PS-16 Aydınlatma ve Priz paftasından (yalnızca M3-ELC rvt-1) linye kablolarını ve panoları çıkarır."""
        count = 0
        try:
            doc = ezdxf.readfile(str(dxf_path))
            msp = doc.modelspace()

            # Pano etiketleri (LF, İAP, MCC, UPS, DB-, TMK vb.)
            for e in msp:
                if e.dxftype() in ('TEXT', 'MTEXT'):
                    txt = (e.dxf.text if hasattr(e.dxf, 'text') else e.text).strip()
                    txt_u = txt.upper()
                    if any(k in txt_u for k in ['LF', 'İAP', 'IAP', 'MCC', 'UPS', 'DB-', 'AGDP', 'TMK', 'TSK', 'PANO']) or 'S28/' in txt or 'S24/' in txt:
                        ins_pt = getattr(e.dxf, 'insert', None)
                        if ins_pt and self._is_in_bounds(ins_pt.x, ins_pt.y):
                            self.panels.append((ins_pt.x, ins_pt.y, txt))

            # Ana Kat Planı Elektrik Modeli ('rvt-') bloğunu aç
            elc_inserts = self._find_primary_inserts(msp, 'M3-ELC')
            for ins in elc_inserts[:1]:
                prims = self._get_primitives(ins)
                for ve in prims:
                    lay_u = ve.dxf.layer.upper()
                    if lay_u in NON_ELECTRICAL_LAYERS:
                        continue
                    if ve.dxftype() == 'LINE':
                        x1, y1 = ve.dxf.start.x, ve.dxf.start.y
                        x2, y2 = ve.dxf.end.x, ve.dxf.end.y
                        if self._is_in_bounds(x1, y1) and self._is_in_bounds(x2, y2):
                            cat = "KABLO_FE180" if any(k in lay_u for k in ['EMG', 'ACIL', 'FE180', 'E501', 'E651']) else "KABLO_NORM"
                            if not self._is_duplicate_segment(x1, y1, x2, y2, cat, snap_grid_mm=15.0):
                                self.segments.append(SuperposeSegment(x1, y1, x2, y2, cat, lay_u))
                                count += 1
                    elif ve.dxftype() == 'LWPOLYLINE':
                        pts = [(p[0], p[1]) for p in ve.get_points('xy')]
                        for i in range(len(pts) - 1):
                            x1, y1 = pts[i]
                            x2, y2 = pts[i + 1]
                            if self._is_in_bounds(x1, y1) and self._is_in_bounds(x2, y2):
                                cat = "KABLO_FE180" if any(k in lay_u for k in ['EMG', 'ACIL', 'FE180']) else "KABLO_NORM"
                                if not self._is_duplicate_segment(x1, y1, x2, y2, cat, snap_grid_mm=15.0):
                                    self.segments.append(SuperposeSegment(x1, y1, x2, y2, cat, lay_u))
                                    count += 1

        except Exception as e:
            print(f"Hata: {dxf_path.name} aydınlatma verisi çıkarılamadı: {e}")
        return count

    def extract_power_cables(self, dxf_path: Path) -> int:
        """PS-11 Kuvvet / Mekanik Besleme paftasından (yalnızca M3-ELC rvt-1) güç hatlarını çıkarır."""
        count = 0
        try:
            doc = ezdxf.readfile(str(dxf_path))
            msp = doc.modelspace()

            elc_inserts = self._find_primary_inserts(msp, 'M3-ELC')
            for ins in elc_inserts[:1]:
                prims = self._get_primitives(ins)
                for ve in prims:
                    lay_u = ve.dxf.layer.upper()
                    if lay_u in NON_ELECTRICAL_LAYERS:
                        continue
                    if ve.dxftype() == 'LINE':
                        x1, y1 = ve.dxf.start.x, ve.dxf.start.y
                        x2, y2 = ve.dxf.end.x, ve.dxf.end.y
                        if self._is_in_bounds(x1, y1) and self._is_in_bounds(x2, y2):
                            if not self._is_duplicate_segment(x1, y1, x2, y2, "KUVVET", snap_grid_mm=15.0):
                                self.segments.append(SuperposeSegment(x1, y1, x2, y2, "KUVVET", ve.dxf.layer))
                                count += 1
                    elif ve.dxftype() == 'LWPOLYLINE':
                        pts = [(p[0], p[1]) for p in ve.get_points('xy')]
                        for i in range(len(pts) - 1):
                            x1, y1 = pts[i]
                            x2, y2 = pts[i + 1]
                            if self._is_in_bounds(x1, y1) and self._is_in_bounds(x2, y2):
                                if not self._is_duplicate_segment(x1, y1, x2, y2, "KUVVET", snap_grid_mm=15.0):
                                    self.segments.append(SuperposeSegment(x1, y1, x2, y2, "KUVVET", ve.dxf.layer))
                                    count += 1

        except Exception as e:
            print(f"Hata: {dxf_path.name} kuvvet verisi çıkarılamadı: {e}")
        return count

    def extract_conduit_hdpe(self, dxf_path: Path) -> int:
        """GN-14 Döşemealtı Borulama paftasından (yalnızca M3-ELC rvt-1) spiral HDPE boruları çıkarır."""
        count = 0
        try:
            doc = ezdxf.readfile(str(dxf_path))
            msp = doc.modelspace()
            elc_inserts = self._find_primary_inserts(msp, 'M3-ELC')
            for ins in elc_inserts[:1]:
                prims = self._get_primitives(ins)
                for ve in prims:
                    lay_u = ve.dxf.layer.upper()
                    if lay_u in NON_ELECTRICAL_LAYERS:
                        continue
                    if ve.dxftype() == 'LINE':
                        x1, y1 = ve.dxf.start.x, ve.dxf.start.y
                        x2, y2 = ve.dxf.end.x, ve.dxf.end.y
                        if self._is_in_bounds(x1, y1) and self._is_in_bounds(x2, y2):
                            if not self._is_duplicate_segment(x1, y1, x2, y2, "BORU", snap_grid_mm=15.0):
                                self.segments.append(SuperposeSegment(x1, y1, x2, y2, "BORU", ve.dxf.layer))
                                count += 1
        except Exception as e:
            print(f"Uyarı: {dxf_path.name} borulama verisi çıkarılamadı: {e}")
        return count

    def build_superposed_dxf(self, output_dxf_path: Path, floor_code: str = "CT0-03") -> Path:
        """Tüm katmanları standart AutoCAD katmanlarıyla birleştirip tekil Süperpoze DXF oluşturur."""
        output_dxf_path.parent.mkdir(parents=True, exist_ok=True)
        doc = ezdxf.new('R2010')
        msp = doc.modelspace()

        layer_defs = [
            ("00_REFERANS_MIMARI_VE_AKSLAR", 8, "Mimari ve Strüktürel Referans Çizgileri"),
            ("01_TAVA_ALCAK_GERILIM_LV", 4, "Alçak Gerilim / Kuvvetli Akım Kablo Tavaları (Cyan)"),
            ("02_TAVA_ZAYIF_AKIM_WC", 6, "Zayıf Akım ve Telekomünikasyon Tavaları (Magenta)"),
            ("03_TAVA_ETIKET_VE_KOTLARI", 2, "Tava Ebat ve Kot Yazıları (Sarı)"),
            ("04_KABLO_AYDINLATMA_NORMAL", 7, "Normal Aydınlatma ve Priz Linyeleri (Beyaz)"),
            ("05_KABLO_YANGIN_FE180", 1, "NFPA 130 Yangına Dayanıklı FE180 Linyeleri (Kırmızı)"),
            ("06_KUVVET_MEKANIK_BESLEME", 30, "Mekanik Ekipman / Motor / Pompa Güç Kabloları (Turuncu)"),
            ("07_DAGITIM_PANOLARI", 3, "Dağıtım Panoları ve Besleme Noktaları (Yeşil)"),
            ("08_DOSEME_ALTI_BORU_HDPE", 5, "Döşemealtı Spiral HDPE Koruyucu Borular (Mavi)"),
            ("09_CAKISMA_VE_UYARI_NOKTALARI", 1, "Süperpozisyon Çakışma ve İhlal Belirteçleri (Kırmızı Kalın)"),
        ]

        for lay_name, color, desc in layer_defs:
            doc.layers.add(lay_name, color=color)

        cat_to_layer = {
            "MIMARI": "00_REFERANS_MIMARI_VE_AKSLAR",
            "TAVA_LV": "01_TAVA_ALCAK_GERILIM_LV",
            "TAVA_WC": "02_TAVA_ZAYIF_AKIM_WC",
            "KABLO_NORM": "04_KABLO_AYDINLATMA_NORMAL",
            "KABLO_FE180": "05_KABLO_YANGIN_FE180",
            "KUVVET": "06_KUVVET_MEKANIK_BESLEME",
            "BORU": "08_DOSEME_ALTI_BORU_HDPE",
        }

        for seg in self.segments:
            t_layer = cat_to_layer.get(seg.category, "00_REFERANS_MIMARI_VE_AKSLAR")
            msp.add_line((seg.x1, seg.y1), (seg.x2, seg.y2), dxfattribs={'layer': t_layer})

        for anno in self.annotations:
            msp.add_text(
                anno.text,
                dxfattribs={
                    'layer': '03_TAVA_ETIKET_VE_KOTLARI',
                    'insert': (anno.x, anno.y),
                    'height': 180.0
                }
            )

        # Panoları tekilleştirerek ekle
        seen_panels = set()
        for px, py, ptxt in self.panels:
            clean_p = ptxt.replace('\n', ' ').strip()
            if clean_p not in seen_panels:
                seen_panels.add(clean_p)
                msp.add_circle((px, py), radius=450.0, dxfattribs={'layer': '07_DAGITIM_PANOLARI'})
                msp.add_text(
                    clean_p,
                    dxfattribs={
                        'layer': '07_DAGITIM_PANOLARI',
                        'insert': (px + 600.0, py + 250.0),
                        'height': 240.0
                    }
                )

        # Çakışma ve uyarı noktalarını ekle
        for cx, cy, c_type, c_desc in self.clash_points:
            msp.add_circle((cx, cy), radius=750.0, dxfattribs={'layer': '09_CAKISMA_VE_UYARI_NOKTALARI'})
            msp.add_text(f"[{c_type}] {c_desc}", dxfattribs={'layer': '09_CAKISMA_VE_UYARI_NOKTALARI', 'insert': (cx + 900.0, cy), 'height': 220.0})

        title_text = f"CLOUDECAD 2.0 — {self.station_name.upper()} ({self.station_key}) BÜTÜNLEŞİK SÜPERPOZİSYON PAFTASI [{floor_code}]"
        msp.add_text(title_text, dxfattribs={'layer': '01_TAVA_ALCAK_GERILIM_LV', 'insert': (self.x_min + 2000.0, self.y_max - 1000.0), 'height': 500.0})

        doc.saveas(str(output_dxf_path))
        return output_dxf_path

    def render_coordination_image(self, output_png_path: Path, floor_code: str = "CT0-03") -> Path:
        """Yüksek çözünürlüklü 2D koordinasyon ve süperpozisyon önizleme görseli (PNG) oluşturur."""
        output_png_path.parent.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(24, 12), facecolor='#0B1120')
        ax.set_facecolor('#0B1120')

        lines_by_cat: Dict[str, List[Tuple[Tuple[float, float], Tuple[float, float]]]] = {
            "MIMARI": [],
            "TAVA_LV": [],
            "TAVA_WC": [],
            "KABLO_NORM": [],
            "KABLO_FE180": [],
            "KUVVET": [],
            "BORU": []
        }

        for s in self.segments:
            if s.category in lines_by_cat:
                lines_by_cat[s.category].append(((s.x1, s.y1), (s.x2, s.y2)))

        # 1. Mimari Altyapı
        if lines_by_cat["MIMARI"]:
            ax.add_collection(LineCollection(lines_by_cat["MIMARI"], colors='#334155', linewidths=0.6, alpha=0.55, label='Mimari Duvar & Strüktür'))

        # 2. Alçak Gerilim Tavaları (Cyan)
        if lines_by_cat["TAVA_LV"]:
            ax.add_collection(LineCollection(lines_by_cat["TAVA_LV"], colors='#06B6D4', linewidths=2.2, alpha=0.95, label='AG Kablo Tavaları (LV / GN-13)'))

        # 3. Zayıf Akım Tavaları (Magenta)
        if lines_by_cat["TAVA_WC"]:
            ax.add_collection(LineCollection(lines_by_cat["TAVA_WC"], colors='#E879F9', linewidths=2.0, alpha=0.95, label='Zayıf Akım Tavası (WC / GN-13)'))

        # 4. Kuvvet & Mekanik Besleme
        if lines_by_cat["KUVVET"]:
            ax.add_collection(LineCollection(lines_by_cat["KUVVET"], colors='#FB923C', linewidths=1.5, alpha=0.9, label='Kuvvet & Mekanik Besleme (PS-11)'))

        # 5. Normal Aydınlatma & Priz Linyeleri
        if lines_by_cat["KABLO_NORM"]:
            ax.add_collection(LineCollection(lines_by_cat["KABLO_NORM"], colors='#F8FAFC', linewidths=1.0, alpha=0.85, label='Aydınlatma & Priz (PS-16)'))

        # 6. Yangına Dayanıklı FE180 Kablolar
        if lines_by_cat["KABLO_FE180"]:
            ax.add_collection(LineCollection(lines_by_cat["KABLO_FE180"], colors='#EF4444', linewidths=2.4, alpha=1.0, label='NFPA 130 FE180 Yangın Kabloları'))

        # 7. Döşemealtı Boru
        if lines_by_cat["BORU"]:
            ax.add_collection(LineCollection(lines_by_cat["BORU"], colors='#38BDF8', linewidths=1.2, alpha=0.8, label='Döşemealtı HDPE Spiral Borulama (GN-14)'))

        # Panolar
        seen_panels = set()
        for px, py, ptxt in self.panels:
            clean_p = ptxt.replace('\n', ' ').strip()
            if clean_p not in seen_panels:
                seen_panels.add(clean_p)
                ax.scatter(px, py, s=130, c='#22C55E', marker='s', edgecolors='#FFFFFF', linewidths=1.5, zorder=6)
                ax.text(px + 600, py + 300, clean_p, color='#86EFAC', fontsize=9.5, fontweight='bold', zorder=7)

        # Çakışma Noktaları
        for cx, cy, c_type, c_desc in self.clash_points:
            ax.scatter(cx, cy, s=160, c='#EF4444', marker='D', edgecolors='#FEF08A', linewidths=2.0, zorder=8)

        # Lejanta Panolar ve Çakışma ekle
        ax.scatter([], [], s=100, c='#22C55E', marker='s', edgecolors='#FFFFFF', label='Dağıtım Panoları (DB/LF/MCC)')
        if self.clash_points:
            ax.scatter([], [], s=120, c='#EF4444', marker='D', edgecolors='#FEF08A', label='Çakışma / Uyarı Noktaları')

        # Görüntüleme penceresi sınırları
        ax.set_xlim(self.x_min, self.x_max)
        ax.set_ylim(self.y_min, self.y_max)

        ax.set_title(
            f"CloudeCAD 2.0 — {self.station_name.upper()} ({self.station_key})\n"
            f"KABLO TAVASI (GN-13) & KUVVETLİ AKIM (PS-11 / PS-16) SÜPERPOZİSYON KOORDİNASYON PLANI [{floor_code}]",
            color='#FFFFFF', fontsize=13, fontweight='bold', pad=15
        )

        ax.set_xlabel("İstasyon Boyuna Koordinatı (X / mm)", color='#94A3B8', fontsize=9)
        ax.set_ylabel("İstasyon Enine Koordinatı (Y / mm)", color='#94A3B8', fontsize=9)
        ax.tick_params(colors='#64748B', labelsize=8)
        ax.grid(True, linestyle='--', color='#1E293B', alpha=0.5)

        legend = ax.legend(loc='upper right', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=9.5)
        legend.get_frame().set_alpha(0.9)

        plt.tight_layout()
        plt.savefig(str(output_png_path), dpi=200, facecolor='#0B1120')
        plt.close()
        return output_png_path
