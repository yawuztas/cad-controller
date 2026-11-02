"""
CloudeCAD — Fuzzy Snap Algoritması
=====================================
Birbirine yakın hat uçlarını birleştirir.

Problem:
  Sahada çizilen DWG dosyalarında hatlar tam olarak birbirine
  değmez. Mühendis paftayı elle çizdiğinde veya snap ayarı
  kapalıyken 2–50 mm aralığında boşluklar kalır.

Çözüm:
  Tüm hat uçlarını uzamsal bir ızgaraya (grid) yerleştir.
  Tolerans aralığındaki uçları en yakın komşuya "yapıştır".

Karmaşıklık:
  Naif O(N²) yerine grid-based O(N) yaklaşımı kullanılır.
  50.000 segment için dahi milisaniyeler içinde tamamlanır.
"""

import math
import logging
from typing import NamedTuple
from collections import defaultdict

logger = logging.getLogger(__name__)


# Koordinat hassasiyeti — float karşılaştırma için yuvarlama basamağı
_COORD_DECIMALS = 3


def _round_coord(x: float, y: float, decimals: int = _COORD_DECIMALS) -> tuple:
    return (round(x, decimals), round(y, decimals))


class GridSnap:
    """
    Grid tabanlı fuzzy snap.

    Koordinat uzayını tolerance_mm boyutlu hücrelere böler.
    Her uç nokta hücresine ve komşu hücrelere yerleştirilir.
    Snap işlemi: Her uca en yakın komşu aranan ve tolerans
    içindeyse yerine geçirilir.
    """

    def __init__(self, tolerance_mm: float):
        self.tolerance = tolerance_mm
        self._grid: dict[tuple, list[tuple[float, float]]] = defaultdict(list)

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        """Koordinatı grid hücresine dönüştür."""
        return (int(x // self.tolerance), int(y // self.tolerance))

    def add(self, x: float, y: float):
        """Bir noktayı grid'e ekle."""
        cell = self._cell(x, y)
        self._grid[cell].append((x, y))

    def nearest(self, x: float, y: float) -> tuple[float, float]:
        """
        Verilen noktaya tolerans içinde en yakın kayıtlı noktayı bul.
        Yoksa (x, y) kendisini döner.
        """
        cx, cy = self._cell(x, y)
        best = (x, y)
        best_dist = math.inf

        # 3x3 komşu hücreleri tara
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for px, py in self._grid.get((cx + dx, cy + dy), []):
                    d = math.hypot(px - x, py - y)
                    if d < best_dist and d <= self.tolerance:
                        best_dist = d
                        best = (px, py)
        return best


def snap_segments(
    segments: list,
    tolerance_mm: float,
) -> list:
    """
    Segment listesini alır, yakın uç noktaları birleştirir.

    Algoritma:
    1. Tüm uç noktaları topla
    2. Her noktayı grid hücresine göre grupla
    3. Her grup için bir "temsilci" koordinat seç (ilk eklenen)
    4. Her segmentin uçlarını temsilci koordinata eşle

    Parametreler:
        segments    : Segment nesnelerinin listesi (start, end tuple içerir)
        tolerance_mm: Birleştirme eşiği (mm)

    Döner:
        Uç noktaları normalize edilmiş yeni Segment listesi
    """
    if not segments:
        return segments

    from dataclasses import replace as dc_replace

    # ── Geçiş 1: Gerçek O(1) Grid Kovaları ile Temsilci Harita ───────────
    grid_buckets: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)

    def _find_or_create_rep(x: float, y: float) -> tuple[float, float]:
        cx, cy = int(x // tolerance_mm), int(y // tolerance_mm)
        best_rep = None
        best_dist = tolerance_mm + 1.0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for rep in grid_buckets.get((cx + dx, cy + dy), ()):
                    d = math.hypot(rep[0] - x, rep[1] - y)
                    if d <= tolerance_mm and d < best_dist:
                        best_dist = d
                        best_rep = rep
        if best_rep is not None:
            return best_rep
        rep = _round_coord(x, y)
        grid_buckets[(cx, cy)].append(rep)
        return rep

    # Tüm uç noktaları indeksle ve her segment ucunu O(1) komşu aramasıyla eşle
    snapped = []
    snap_count = 0

    for seg in segments:
        orig_start = seg.start
        orig_end   = seg.end

        new_start = _find_or_create_rep(orig_start[0], orig_start[1])
        new_end   = _find_or_create_rep(orig_end[0], orig_end[1])

        if new_start != orig_start or new_end != orig_end:
            snap_count += 1

        # Dejenere segment (start == end) atla
        if math.isclose(new_start[0], new_end[0], abs_tol=1e-6) and \
           math.isclose(new_start[1], new_end[1], abs_tol=1e-6):
            continue

        new_length = math.hypot(
            new_end[0] - new_start[0],
            new_end[1] - new_start[1],
        )
        snapped.append(dc_replace(seg, start=new_start, end=new_end, length=new_length))

    logger.info(
        f"Fuzzy snap: {len(segments)} segment -> {len(snapped)} segment, "
        f"{snap_count} uc duzeltildi (tolerans={tolerance_mm:.0f} mm)"
    )
    return snapped

