"""
CloudeCAD — Anlamsal Snap & Blok Bağlantı Motoru (Semantic Snapping)
===================================================================
Topraklama şeritleri ile köşe kazıkları (1TP), ek klemensleri (1EKK)
ve eşpotansiyel baraları (etb) arasındaki çizim boşluklarını (tolerans dahilinde)
fiziksel bağlantı segmentleri ile kapatır.

Böylece görsel olarak çizilmiş ama ucu tam değdirilmemiş semboller
matematiksel devre grafında kesintisiz tek bir şebekeye dönüşür.
"""

import math
import logging
from typing import List, Tuple
from core.tier1_parser import Segment, InsertPoint

logger = logging.getLogger(__name__)


def connect_blocks_to_network(
    segments: list[Segment],
    inserts: list[InsertPoint],
    max_connection_distance_mm: float = 600.0,  # 60 cm'ye kadar sembol toleransı
) -> list[Segment]:
    """
    Topraklama bloklarını (1TP kazık, 1EKK klemens, etb bara)
    en yakın topraklama şerit segmentine bağlar.
    """
    if not inserts or not segments:
        return segments

    # Sadece topraklama ile ilgili blokları filtrele
    gnd_inserts = [
        ins for ins in inserts
        if any(k in ins.block_name.lower() for k in ['1tp', 'tp', '1ekk', 'ekk', 'etb', 'rod', 'cubuk', 'kazik', 'bara'])
        and not any(k in ins.block_name.lower() for k in ['tablo', 'tek', 'intercom'])
    ]

    if not gnd_inserts:
        return segments

    logger.info(f"Semantik Bağlantı: {len(gnd_inserts)} topraklama bloğu inceleniyor...")

    # Mevcut segment uç noktalarını topla
    end_points = []
    for s in segments:
        end_points.append(s.start)
        end_points.append(s.end)

    new_connector_segments = []
    connected_count = 0

    for ins in gnd_inserts:
        bx, by = ins.position
        
        # 1. En yakın şerit ucunu bul
        min_dist = float("inf")
        nearest_pt = None
        
        for px, py in end_points:
            d = math.hypot(px - bx, py - by)
            if d < min_dist:
                min_dist = d
                nearest_pt = (px, py)

        # Eğer zaten sıfır veya çok yakınsa (ör. < 10 mm) zaten bağlıdır
        if 10.0 <= min_dist <= max_connection_distance_mm and nearest_pt is not None:
            # Blok ile en yakın uç arasına köprü segmenti ekle
            conn_seg = Segment(
                start=nearest_pt,
                end=(bx, by),
                layer=ins.layer or "00-TOPRAK",
                entity_type=f"CONNECTOR({ins.block_name})",
            )
            new_connector_segments.append(conn_seg)
            end_points.append((bx, by))
            connected_count += 1
            logger.debug(f"  ✓ {ins.block_name} @ ({bx:.0f},{by:.0f}) -> şerit ucuna bağlandı (mesafe: {min_dist/10.0:.1f} cm)")

    if connected_count > 0:
        logger.info(f"✓ {connected_count} adet topraklama bloğu şebekeye bağlandı.")

    return segments + new_connector_segments


def split_segments_at_t_junctions(
    segments: list[Segment],
    tolerance_mm: float = 100.0,
) -> list[Segment]:
    """
    T-kavşaklarını (T-junction) Shapely 2.0 STRtree uzamsal indeksiyle O(M log M)
    hızında tespit edip kesişim noktalarından böler.
    """
    if len(segments) <= 1:
        return segments

    from shapely.geometry import Point, LineString
    from shapely.strtree import STRtree

    lines = [LineString([s.start, s.end]) for s in segments]
    # Tekil uç noktaları topla ve STRtree ile indeksle
    unique_ep_coords = list({s.start for s in segments} | {s.end for s in segments})
    endpoints = [Point(c) for c in unique_ep_coords]
    ep_tree = STRtree(endpoints)

    result_segments = []
    splits_count = 0

    for s, line in zip(segments, lines):
        if s.length < tolerance_mm * 2.5:
            result_segments.append(s)
            continue

        # Sadece bu çizginin bounding-box + tolerance_mm çevresindeki uç noktaları sorgula!
        candidate_idxs = ep_tree.query(line.buffer(tolerance_mm))
        if len(candidate_idxs) == 0:
            result_segments.append(s)
            continue

        split_pts = []
        p_start = Point(line.coords[0])
        p_end = Point(line.coords[-1])

        for idx in candidate_idxs:
            pt = endpoints[int(idx)]
            if line.distance(pt) <= tolerance_mm:
                if pt.distance(p_start) > tolerance_mm and pt.distance(p_end) > tolerance_mm:
                    proj_dist = line.project(pt)
                    split_pts.append((proj_dist, (pt.x, pt.y)))

        if not split_pts:
            result_segments.append(s)
        else:
            split_pts.sort(key=lambda x: x[0])
            unique_splits = []
            for sp in split_pts:
                if not unique_splits or abs(sp[0] - unique_splits[-1][0]) > tolerance_mm:
                    unique_splits.append(sp)

            coords = [line.coords[0]] + [sp[1] for sp in unique_splits] + [line.coords[-1]]
            for i in range(len(coords) - 1):
                p1, p2 = coords[i], coords[i+1]
                if math.hypot(p2[0]-p1[0], p2[1]-p1[1]) >= 1.0:
                    result_segments.append(Segment(
                        start=p1,
                        end=p2,
                        layer=s.layer,
                        entity_type=s.entity_type,
                        handle=s.handle,
                    ))
            splits_count += len(unique_splits)

    if splits_count > 0:
        logger.info(f"✓ T-Kavşak Bölme (STRtree): {splits_count} adet T-bağlantı noktası bölündü ({len(segments)} -> {len(result_segments)} segment).")

    return result_segments


def filter_legend_inserts(
    inserts: list[InsertPoint],
    texts: list,
) -> tuple[list[InsertPoint], list[InsertPoint]]:
    """
    Topraklama lejantındaki (sembol açıklama tablosundaki) örnek blokları
    tespit ederek bina temel topraklamasından hariç tutar.
    
    Döner: (bina_blokları, lejant_blokları)
    """
    if not inserts or not texts:
        return inserts, []

    # Lejant belirteç metinlerini ara
    legend_pts = []
    for t in texts:
        txt_low = t.text.lower()
        if any(k in txt_low for k in [
            'topraklama çubuğu', 'toprakalama çubuğu', 'kadvelt kaynak',
            'eşpotansiyel topraklama barası', 'galvaniz şerit ek klemensi',
            'topraklama lejantı', 'topraklama sembolleri'
        ]):
            legend_pts.append(t.position)

    if not legend_pts:
        return inserts, []

    # Lejant kutusu sınırları (metinlerin etrafına 500mm / 50cm pay)
    margin = 500.0
    min_x = min(p[0] for p in legend_pts) - margin
    max_x = max(p[0] for p in legend_pts) + margin
    min_y = min(p[1] for p in legend_pts) - margin
    max_y = max(p[1] for p in legend_pts) + margin

    # Lejant genellikle dar bir dikey/yatay sütundur (ör. 3-8m)
    if (max_x - min_x) > 15000.0 or (max_y - min_y) > 15000.0:
        # Çok geniş alana yayıldıysa hatalı eşleşmedir
        return inserts, []

    real_inserts = []
    legend_inserts = []

    for ins in inserts:
        bx, by = ins.position
        if min_x <= bx <= max_x and min_y <= by <= max_y:
            legend_inserts.append(ins)
        else:
            real_inserts.append(ins)

    if legend_inserts:
        logger.info(
            f"✓ Topraklama Lejantı tespit edildi. "
            f"Lejanttaki {len(legend_inserts)} sembol ({[b.block_name for b in legend_inserts]}) bina kazık/ek sayımından hariç tutuldu."
        )

    return real_inserts, legend_inserts


def isolate_primary_grounding_cluster(
    segments: list[Segment],
    distance_threshold_mm: float = 10000.0,
) -> list[Segment]:
    """
    Ana temel topraklama ağını izole eder.
    
    Üst katlardaki tek tük parazit hatları veya lejanttaki kısa örnek çizgileri
    ayıklayarak EN BÜYÜK TOPLAM İLETKEN METRAJINA ve GEOMETRİK ALANA
    sahip olan ana temel şebekesini seçer.
    """
    if len(segments) <= 2:
        return segments

    # Segmentlerin orta noktaları
    mid_points = [((s.start[0] + s.end[0])/2, (s.start[1] + s.end[1])/2) for s in segments]
    
    # X koordinatındaki büyük sıçramaları (kat veya pafta aralıklarını) bul
    xs = sorted([p[0] for p in mid_points])
    gaps = []
    for i in range(len(xs) - 1):
        gap = xs[i+1] - xs[i]
        if gap > distance_threshold_mm:
            gaps.append((gap, (xs[i] + xs[i+1]) / 2))

    if not gaps:
        return segments

    # Split sınırlarına göre gruplara ayır
    gaps.sort(reverse=True, key=lambda x: x[0])
    split_x = gaps[0][1]

    left = [s for s in segments if s.start[0] < split_x]
    right = [s for s in segments if s.start[0] >= split_x]

    # Karar kriteri: Toplam iletken uzunluğu (metraj) en yüksek olan taraf ANA TEMEL AĞIDIR!
    left_len = sum(s.length for s in left)
    right_len = sum(s.length for s in right)

    primary = left if left_len >= right_len else right
    secondary = right if left_len >= right_len else left

    logger.info(
        f"Mekânsal İzolasyon: {len(segments)} segmentten {len(primary)} tanesi "
        f"ana temel ağı olarak seçildi (Metraj: {sum(s.length for s in primary)/1000.0:.1f} m, "
        f"elenen parazit: {sum(s.length for s in secondary)/1000.0:.1f} m)."
    )
    return primary

