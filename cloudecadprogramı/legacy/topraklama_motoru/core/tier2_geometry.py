"""
CloudeCAD — Tier 2: Geometri Motoru
=====================================
DXF'ten çıkarılan ham geometriyi analiz eder:

1. Fuzzy snap (5 cm tolerans) ile kopuk uçları yapıştırır
2. Shapely ile bina dış sınır poligonunu üretir
3. NetworkX ile topraklama ağı topolojisini kurar
4. Göz tespiti + boyut kontrolü yapar
5. Zemin direnci (ρ) ve diğer parametreleri pafta metninden okur

Çıktı: GeometryResult dataclass → Tier 3 hesap motoruna iletilir.
"""

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Optional, Any, List, Dict

from shapely.geometry import LineString, MultiPoint, Polygon, Point
from shapely.ops import unary_union

from config import SNAP_TOLERANCE_MM, DEFAULT_RHO_OHM_M, CONCAVE_HULL_RATIO
from core.tier1_parser import ParsedDrawing, Segment
from utils.snap import snap_segments
from utils.graph import (
    build_graph, find_cycles, get_connected_components,
    total_length_m, find_free_ends, cycle_dimensions_m
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  PAFTADAN OKUNAN PARAMETRELER
# ═══════════════════════════════════════════════════════════════

@dataclass
class DrawingParams:
    """
    Pafta metinlerinden çıkarılan hesap parametreleri.
    Boş kalanlar kullanıcıdan sorulacak veya varsayılan değer kullanılacak.
    """
    # Zemin özgül direnci (Ω·m)
    rho_ohm_m: Optional[float] = None
    rho_source: str = ""          # "pafta" | "kullanıcı" | "varsayılan"

    # Kazık parametreleri
    stake_length_m: Optional[float] = None
    stake_diameter_m: Optional[float] = None
    stake_count: Optional[int] = None

    # Şerit / iletken parametreleri
    strip_length_m: Optional[float] = None     # L (iletken uzunluğu)
    strip_diameter_m: Optional[float] = None   # d (eşdeğer çap)
    strip_depth_m: Optional[float] = None      # h (gömülme derinliği)

    # Bina boyutları (paftadan okunan)
    building_width_m: Optional[float] = None
    building_length_m: Optional[float] = None
    building_area_m2: Optional[float] = None

    # Paftadaki mevcut hesap sonuçları (karşılaştırma için)
    stake_count_declared: Optional[int] = None # Beyan edilen çubuk sayısı
    equivalent_diameter_D: Optional[float] = None
    conductor_section_q: Optional[float] = None
    conductor_diameter_d: Optional[float] = None
    conductor_depth_H: Optional[float] = None
    declared_Rc: Optional[float] = None    # Çubuk direnci (Ω)
    declared_Ri: Optional[float] = None    # Çevre iletken direnci (Ω)
    declared_Ry: Optional[float] = None    # Yatay topraklama direnci (Ω)
    declared_Rt: Optional[float] = None    # Temel topraklama direnci (Ω)
    declared_Re: Optional[float] = None    # Eşdeğer toplam direnç (Ω)
    is_radsan: bool = False
    radsan_step1_D: Optional[float] = None
    radsan_step2_Rc: Optional[float] = None
    radsan_step3_Ry: Optional[float] = None
    radsan_step4_Re: Optional[float] = None

    def missing_critical(self) -> list[str]:
        """Hesap için zorunlu ama eksik parametreleri listeler."""
        missing = []
        if self.rho_ohm_m is None:
            missing.append("ρE (toprak özgül direnci, Ω·m)")
        return missing


# ═══════════════════════════════════════════════════════════════
#  GEOMETRİ SONUÇ YAPISI
# ═══════════════════════════════════════════════════════════════

@dataclass
class MeshEye:
    """Bir topraklama ağı gözü."""
    index: int
    width_m: float
    height_m: float
    nodes: list = field(default_factory=list)

    @property
    def max_dim_m(self) -> float:
        return max(self.width_m, self.height_m)

    @property
    def is_oversized(self) -> bool:
        from standards.ts_hd_60364 import MESH_MAX_SIZE_M, MESH_TOLERANCE_RATIO
        limit = MESH_MAX_SIZE_M * (1 + MESH_TOLERANCE_RATIO)
        return self.max_dim_m > limit


@dataclass
class GeometryResult:
    """Tier 2 geometri analizinin tüm çıktısı."""
    # ── Topraklama ağı ────────────────────────────────────────
    total_strip_length_m: float = 0.0      # Toplam şerit metrajı
    network_count: int = 0                 # Bağlı bileşen sayısı (1 olmalı)
    mesh_eyes: list[MeshEye] = field(default_factory=list)
    free_end_count: int = 0                # Serbest uç sayısı

    # ── Bina sınırı ───────────────────────────────────────────
    building_polygon: Optional[Polygon] = None
    building_area_m2: float = 0.0
    building_width_m: float = 0.0
    building_length_m: float = 0.0

    # ── Paftadan okunan parametreler ──────────────────────────
    params: DrawingParams = field(default_factory=DrawingParams)

    # ── Geometri istatistikleri ───────────────────────────────
    segment_count_before_snap: int = 0
    segment_count_after_snap: int = 0

    # ── Çok Katlı Proje Dilimleri (Floor Zones) ───────────────
    floors: list = field(default_factory=list)
    active_foundation_floor: Optional[Any] = None



# ═══════════════════════════════════════════════════════════════
#  PAFTADAN PARAMETRE OKUMA (Regex tabanlı metin tarama)
# ═══════════════════════════════════════════════════════════════

# Gerçek topraklama hesap paftalarında kullanılan ifadeler
# (EH - TOPRAKLAMA HESABI.xls ve diğer örneklerden türetildi)

_PARAM_PATTERNS = {
    "rho": [
        r"ρ[Ee]?\s*[=:]\s*([\d.,]+)",
        r"ρ\s*\(?\s*[Ωohm].*?[=:]\s*([\d.,]+)",
        r"toprak\s+(?:özgül\s+)?dire[nç]c?\s*[=:]\s*([\d.,]+)",
        r"toprak\s+özgül\s+dire[nç]c?\s*\(?[Ωohm].*?\)?\s*[=:]\s*([\d.,]+)",
        r"(?:rho|Q)\s*[=:]\s*([\d.,]+)",
        r"(?:ρ|Q)\s*=\s*([\d.,]+)\s*Ω",
        # "100 Ω/m KABUL EDİLMİŞTİR" formatı
        r"([\d.,]+)\s*[Ωohm][\/\\]?m?\s*(?:kabul|varsay|assumed)",
    ],
    "stake_length": [
        r"[Ll]\s*[=:]\s*([\d.,]+)\s*m",
        r"çubuk\s+(?:boy|uzunluk)\w*\s*[=:]\s*([\d.,]+)",
        r"stake\s+length\s*[=:]\s*([\d.,]+)",
    ],
    "stake_diameter": [
        r"[Dd]\s*[=:]\s*([\d.,]+)\s*(?:m|cm|mm)",
        r"çubuk\s+çap\w*\s*[=:]\s*([\d.,]+)",
    ],
    "stake_count": [
        r"[Nn]\s*[=:]\s*([\d.,]+)\s*(?:ad|adet|pcs)?",
        r"çubuk\s+(?:adet|sayı)\w*\s*[=:]\s*([\d.,]+)",
    ],
    "strip_length": [
        r"[Ll]\s*[=:]\s*([\d.,]+)\s*m",
        r"iletken\s+uzunluk\w*\s*[=:]\s*([\d.,]+)",
        r"gömülü\s+iletken\s+boy\w*\s*[=:]\s*([\d.,]+)",
    ],
    "declared_Re": [
        r"[Rr][Ee]\s*[=:]\s*([\d.,]+)",
        r"eşdeğer\s+topraklama\s+dire[nç]\w*\s*[=:]\s*([\d.,]+)",
    ],
    "declared_Rt": [
        r"[Rr][Tt]\s*[=:]\s*([\d.,]+)",
        r"temel\s+topraklama.*?dire[nç]\w*\s*[=:]\s*([\d.,]+)",
    ],
    "declared_Rc": [
        r"[Rr][çc]\s*[=:]\s*([\d.,]+)",
        r"topraklama\s+çubuğu?\s+dire[nç]\w*\s*[=:]\s*([\d.,]+)",
    ],
    "declared_Ri": [
        r"[Rr][Ii]\s*[=:]\s*([\d.,]+)",
        r"çevre\s+topraklama.*?dire[nç]\w*\s*[=:]\s*([\d.,]+)",
    ],
}


def _parse_float(s: str) -> float:
    """'29,80' veya '29.80' formatlarını float'a çevirir."""
    return float(s.replace(",", "."))


def _first_match(text: str, patterns: list[str]) -> Optional[float]:
    """Metin içinde ilk eşleşen değeri döner."""
    text_lower = text.lower()
    for pat in patterns:
        m = re.search(pat, text_lower, re.IGNORECASE)
        if m:
            try:
                return _parse_float(m.group(1))
            except (ValueError, IndexError):
                continue
    return None


def extract_params_from_texts(
    texts: list,
    inserts: Optional[list] = None,
    require_rho: bool = True
) -> DrawingParams:
    """
    Çizimdeki TEXT/MTEXT entity'lerinden ve bloklardan hesap parametrelerini
    çıkarır.
    
    Türkiye standartlarındaki tipik lejant ve etiket kalıplarını tanır:
    - "%%C20mm h=1,75m Cu Topraklama Çubuğu" -> d=0.02m, L=1.75m, adet
    - "30x3,5mm Galvaniz Çelik Lama" -> kesit ve iletken tipi
    - "1TP" blok referansları -> çubuk adedi
    """
    params = DrawingParams()
    if not texts:
        return params

    all_text = "\n".join(t.text for t in texts)

    # 1. ρ (Zemin özgül direnci)
    rho = _first_match(all_text, _PARAM_PATTERNS["rho"])
    if rho is not None:
        params.rho_ohm_m = rho
        params.rho_source = "pafta"
        logger.info(f"Paftadan ρ okundu: {rho} Ω·m")
    elif require_rho:
        logger.warning("⚠️  Paftada ρ (zemin özgül direnci) bulunamadı.")

    # 2. Tipik Türk Elektrik Projesi Çubuk Etiketleri:
    # "%%C20mm h=1,75m Cu Topraklama Çubuğu" veya "%%C20mm h=1,75m"
    rod_matches = re.findall(
        r"(?:%%[cC]|Ø|O|\b)\s*(\d+)\s*mm.*?h\s*=\s*([\d.,]+)\s*m",
        all_text, re.IGNORECASE
    )
    if rod_matches:
        diam_mm = float(rod_matches[0][0])
        len_m = _parse_float(rod_matches[0][1])
        params.stake_diameter_m = diam_mm / 1000.0
        params.stake_length_m = len_m
        logger.info(f"Etiketten çubuk tipi: Ø{diam_mm:.0f}mm ({params.stake_diameter_m}m), h={len_m}m")
        
        # Etiket adedi (1 tanesi antet açıklaması olabilir, kalanı köşe etiketleri)
        if len(rod_matches) > 1:
            # Örneğin 5 eşleşme varsa: 1 lejant + 4 köşe = 4 çubuk
            counted_rods = len(rod_matches) - 1
            params.stake_count = counted_rods
            logger.info(f"Etiket sayımından çubuk adedi: {counted_rods} adet")

    # Genel regex fallback çubuk parametreleri
    if params.stake_length_m is None:
        params.stake_length_m = _first_match(all_text, _PARAM_PATTERNS["stake_length"])
    if params.stake_diameter_m is None:
        params.stake_diameter_m = _first_match(all_text, _PARAM_PATTERNS["stake_diameter"])
    if params.stake_count is None:
        v = _first_match(all_text, _PARAM_PATTERNS["stake_count"])
        if v is not None:
            params.stake_count = int(round(v))

    # 3. Blok referanslarından (INSERT) çubuk sayımı doğrulama:
    if inserts:
        # 1TP, TP, ROD, CUBUK, KAZIK blokları
        rod_blocks = [
            ins for ins in inserts
            if any(k in ins.block_name.lower() for k in ['1tp', 'tp', 'rod', 'cubuk', 'kazik'])
            and not any(k in ins.block_name.lower() for k in ['tablo', 'tek'])
        ]
        if rod_blocks:
            logger.info(f"Geometride {len(rod_blocks)} adet çubuk/topraklama bloğu tespit edildi ({[b.block_name for b in rod_blocks]})")
            if params.stake_count is None or params.stake_count == 0:
                params.stake_count = len(rod_blocks)

    # 4. İletken tipi ve kesiti:
    # "30x3,5mm Galvaniz Çelik Lama"
    lama_m = re.search(r"(\d+)\s*[xX*]\s*([\d.,]+)\s*mm\s*(?:galvaniz|çelik|lama|şerit)?", all_text, re.IGNORECASE)
    if lama_m:
        w_mm = float(lama_m.group(1))
        t_mm = _parse_float(lama_m.group(2))
        logger.info(f"Etiketten iletken kesiti: {w_mm:.0f}x{t_mm:.1f}mm Galvaniz Şerit")

    # İletken uzunluğu (açıkça yazılmışsa)
    params.strip_length_m = _first_match(all_text, _PARAM_PATTERNS["strip_length"])

    # Paftadaki mevcut hesap sonuçları
    params.declared_Re = _first_match(all_text, _PARAM_PATTERNS["declared_Re"])
    params.declared_Rt = _first_match(all_text, _PARAM_PATTERNS["declared_Rt"])
    params.declared_Rc = _first_match(all_text, _PARAM_PATTERNS["declared_Rc"])
    params.declared_Ri = _first_match(all_text, _PARAM_PATTERNS["declared_Ri"])

    logger.debug(f"Çıkarılan parametreler: {params}")
    return params


# ═══════════════════════════════════════════════════════════════
#  BİNA SINIRI TESPİTİ (Shapely)
# ═══════════════════════════════════════════════════════════════

def _build_building_polygon(
    structural_segments: list[Segment],
    foundation_bbox: Optional[tuple] = None,
    margin_mm: float = 3000.0,
) -> Optional[Polygon]:
    """
    Yapısal katman segmentlerinden bina dış sınır poligonu oluşturur.
    Çok katlı DWG paftalarında (Bodrum, Zemin, Normal Katlar yan yana olduğunda)
    sadece temel topraklamasının bulunduğu bodrum katın taşıyıcılarını izole eder.
    """
    if not structural_segments:
        return None

    # Eğer temel topraklama ağı koordinatları belliyse, sadece o kattaki taşıyıcıları al
    target_segments = structural_segments
    if foundation_bbox is not None:
        min_x, min_y, max_x, max_y = foundation_bbox
        min_x -= margin_mm
        min_y -= margin_mm
        max_x += margin_mm
        max_y += margin_mm

        in_bounds = [
            s for s in structural_segments
            if (min_x <= s.start[0] <= max_x and min_y <= s.start[1] <= max_y) or
               (min_x <= s.end[0] <= max_x and min_y <= s.end[1] <= max_y)
        ]
        if len(in_bounds) >= 4:
            target_segments = in_bounds
            logger.info(f"Bina sınırı izolasyonu: {len(structural_segments)} taşıyıcıdan {len(target_segments)} tanesi temel katında izole edildi.")

    # Tüm uç noktaları topla
    points = []
    for seg in target_segments:
        points.append(seg.start)
        points.append(seg.end)

    if len(points) < 3:
        return None

    try:
        mp = MultiPoint(points)
        # Shapely concave_hull (ratio: 0=convex, 1=tightest)
        hull = mp.concave_hull(ratio=CONCAVE_HULL_RATIO)
        if hull.geom_type == "Polygon" and hull.area > 0:
            return hull
    except Exception as e:
        logger.debug(f"Concave hull hesaplanamadı: {e}")

    # Fallback: convex hull
    try:
        hull = mp.convex_hull
        if hull.geom_type == "Polygon":
            return hull
    except Exception:
        pass

    return None


# ═══════════════════════════════════════════════════════════════
#  ANA GEOMETRİ ANALİZİ
# ═══════════════════════════════════════════════════════════════

class GeometryEngine:
    """
    ParsedDrawing → GeometryResult dönüşümünü gerçekleştirir.

    Kullanım:
        engine = GeometryEngine()
        result = engine.analyze(drawing)
    """

    def __init__(self, snap_tolerance_mm: float = SNAP_TOLERANCE_MM):
        self.snap_tolerance_mm = snap_tolerance_mm

    def analyze(
        self,
        drawing: ParsedDrawing,
        project_type: str = "BİNA",
        drawing_role: str = ""
    ) -> GeometryResult:
        result = GeometryResult()

        is_metro = ("METRO" in str(project_type).upper())
        is_metro_indoor = is_metro and ("KUYU" not in str(drawing_role).upper())

        logger.info("=" * 55)
        logger.info(f"Tier 2 — Geometri Analizi Başladı [{project_type}]")
        logger.info("=" * 55)

        # 1) Çok Katlı Kat Dilimleyici (Floor Slicer) — Sadece Bina / Endüstriyel yan yana paftalarda çalıştır
        if not is_metro:
            logger.info("→ Çok katlı kat planları taranıyor (Floor Slicer)...")
            from core.floor_slicer import FloorSlicerEngine
            slicer = FloorSlicerEngine(unit_factor=getattr(drawing, 'unit_factor', 10.0))
            floors = slicer.slice_drawing(drawing, discipline_filter="GROUNDING")
            result.floors = floors

            foundation_candidates = [f for f in floors if f.has_foundation_mesh and f.title.elevation_rank <= 0]
            if not foundation_candidates:
                foundation_candidates = [f for f in floors if f.has_foundation_mesh]
            if not foundation_candidates and floors:
                foundation_candidates = [max(floors, key=lambda f: f.grounding_length_m)]

            active_floor = foundation_candidates[0] if foundation_candidates else None
            result.active_foundation_floor = active_floor
        else:
            active_floor = None

        if active_floor and active_floor.grounding_segments:
            logger.info(
                f"✓ Ana Temel Topraklama Katı İzole Edildi: {active_floor.title.floor_name} "
                f"(Kot: {active_floor.title.elevation_rank:+d}, Şerit: {active_floor.grounding_length_m:.1f} m, "
                f"Çubuk: {active_floor.rod_count}, Klemens: {active_floor.clamp_count})"
            )
            segs = active_floor.grounding_segments
            candidate_inserts = active_floor.grounding_inserts if active_floor.grounding_inserts else drawing.grounding_inserts
        else:
            segs = drawing.grounding_segments
            candidate_inserts = drawing.grounding_inserts

        # 2) Paftadaki mevcut hesap metnini oku
        logger.info("→ Pafta metinleri taranıyor...")
        target_texts = drawing.all_texts if drawing.all_texts else drawing.grounding_texts

        # Lejant bloklarını bina bloklarından ayıkla (1TP, 1EKK vs.)
        from utils.semantic_snap import (
            filter_legend_inserts, split_segments_at_t_junctions,
            isolate_primary_grounding_cluster, connect_blocks_to_network
        )
        real_inserts, legend_inserts = filter_legend_inserts(candidate_inserts, target_texts)

        result.params = extract_params_from_texts(
            target_texts,
            real_inserts,
            require_rho=(not is_metro_indoor)
        )

        # 3) Mekânsal Kümeleme & İletken Ayrıştırma
        result.segment_count_before_snap = len(segs)

        # 3a. Blok içindeki mikro sembol çizgilerini (klemens kutusu vs.) ayıkla;
        #     Sadece gerçek iletkenleri ve köprüleri şebekeye al (BIM ve büyük patlatılmış iletkenler korunur)
        real_conductor_segs = [
            s for s in segs
            if not (s.entity_type.endswith("(explode)") and s.length < 150.0)
        ]
        if not real_conductor_segs:
            real_conductor_segs = segs

        # 3b. Ana temel topraklama ağını izole et (uzaktaki pano/kat/lejant parazitlerini ele)
        isolated_segs = isolate_primary_grounding_cluster(real_conductor_segs)

        # 3c. T-kavşaklarını böl (iç bölücü iletkenler ve etb hatları dış ringe tam bağlansın)
        split_segs = split_segments_at_t_junctions(isolated_segs, tolerance_mm=self.snap_tolerance_mm * 2.0)

        # 3d. Köşe kazıklarını ve baraları semantik köprülerle şebekeye bağla
        connected_segs = connect_blocks_to_network(split_segs, real_inserts, max_connection_distance_mm=600.0)

        # 3e. Fuzzy snap uygula
        logger.info(f"→ Fuzzy snap uygulanıyor ({len(connected_segs)} segment)...")
        snapped = snap_segments(connected_segs, self.snap_tolerance_mm)
        result.segment_count_after_snap = len(snapped)

        if not snapped:
            logger.warning(
                "⚠️  Topraklama segmenti bulunamadı. "
                "Katman tespiti yapılamadı ya da çizimde topraklama hattı yok."
            )
            return result

        # 3) Topoloji grafiği kur
        logger.info("→ Topoloji grafiği oluşturuluyor...")
        G = build_graph(snapped)

        # 4) Bağlı bileşen analizi (Ana Şebeke İzolasyonu)
        components = get_connected_components(G, warn_disconnected=(not is_metro_indoor))
        
        # En büyük bağlı bileşen ana temel topraklama şebekesidir
        if components:
            primary_comp = max(components, key=len)
            primary_subG = G.subgraph(primary_comp)
            
            # Ana şebeke uzunluğu
            from utils.graph import total_length_m
            result.total_strip_length_m = total_length_m(primary_subG)
            
            # Eğer ana bileşen tüm grafın %80+ uzunluğunu kapsıyorsa ağ süreklidir
            full_len = total_length_m(G)
            if full_len > 0 and (result.total_strip_length_m / full_len) >= 0.85:
                result.network_count = 1  # Ana şebeke tek parça ve sürekli!
                logger.info(f"✓ Ana Temel Topraklama Ağı KESİNTİSİZ ve TEK PARÇA (Uzunluk: {result.total_strip_length_m:.2f} m)")
            else:
                result.network_count = len(components)
                logger.info(f"→ Toplam iletken uzunluğu: {result.total_strip_length_m:.2f} m ({len(components)} parça)")
        else:
            result.total_strip_length_m = total_length_m(G)
            result.network_count = len(components)

        if not is_metro_indoor:
            # 5) Göz tespiti (döngüler) — Temel / Dış Saha / Endüstriyel ızgara ağları için
            logger.info("→ Ağ gözleri tespit ediliyor...")
            cycles = find_cycles(G)
            for i, cycle in enumerate(cycles):
                w, h = cycle_dimensions_m(G, cycle)
                eye = MeshEye(index=i + 1, width_m=w, height_m=h, nodes=cycle)
                result.mesh_eyes.append(eye)

            oversized = [e for e in result.mesh_eyes if e.is_oversized]
            logger.info(
                f"→ {len(result.mesh_eyes)} göz bulundu, "
                f"{len(oversized)} aşan göz (>20m×20m)"
            )

            # 7) Serbest uç kontrolü
            result.free_end_count = len(find_free_ends(G))
            if result.free_end_count:
                logger.warning(
                    f"⚠️  {result.free_end_count} serbest uç bulundu — "
                    "bağlantısız hat veya snap kaçıklığı olabilir."
                )

            # 8) Bina sınır poligonu
            f_xs = [s.start[0] for s in isolated_segs] + [s.end[0] for s in isolated_segs]
            f_ys = [s.start[1] for s in isolated_segs] + [s.end[1] for s in isolated_segs]
            f_bbox = (min(f_xs), min(f_ys), max(f_xs), max(f_ys)) if f_xs else None

            struct_segs = active_floor.structural_segments if (active_floor and active_floor.structural_segments) else drawing.structural_segments
            if struct_segs:
                logger.info("→ Bina sınır poligonu hesaplanıyor...")
                polygon = _build_building_polygon(struct_segs, foundation_bbox=f_bbox)
                if polygon:
                    result.building_polygon = polygon
                    area_mm2 = polygon.area
                    result.building_area_m2 = area_mm2 / 1e6
                    bb = polygon.bounds  # (minx, miny, maxx, maxy)
                    result.building_width_m  = (bb[2] - bb[0]) / 1000.0
                    result.building_length_m = (bb[3] - bb[1]) / 1000.0
                    logger.info(
                        f"→ Bina sınırı: {result.building_width_m:.1f}m × "
                        f"{result.building_length_m:.1f}m = "
                        f"{result.building_area_m2:.0f} m²"
                    )

            if result.building_area_m2 <= 0.0 and isolated_segs:
                # Fallback: Temel topraklama ringinin kendi sınırlarından bina alanı
                ring_pts = []
                for s in isolated_segs:
                    ring_pts.append(s.start)
                    ring_pts.append(s.end)
                if len(ring_pts) >= 4:
                    mp_ring = MultiPoint(ring_pts)
                    ring_hull = mp_ring.convex_hull
                    if ring_hull.geom_type == "Polygon":
                        result.building_polygon = ring_hull
                        result.building_area_m2 = ring_hull.area / 1e6
                        bb = ring_hull.bounds
                        result.building_width_m = (bb[2] - bb[0]) / 1000.0
                        result.building_length_m = (bb[3] - bb[1]) / 1000.0
                        logger.info(
                            f"→ Bina sınırı (Topraklama ringinden türetildi): {result.building_width_m:.1f}m × "
                            f"{result.building_length_m:.1f}m = {result.building_area_m2:.0f} m²"
                        )
            else:
                logger.debug("Yapısal katman segmenti yok, bina sınırı hesaplanamadı.")

        logger.info("Tier 2 — Geometri Analizi Tamamlandı")
        return result
