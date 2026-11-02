"""
CloudeCAD — Çok Katlı Kat Dilimleyici ve Mekânsal Bölümleme Motoru (Floor Slicer)
================================================================================
Çok katlı binalarda, karmaşık endüstriyel tesislerde ve 4-5 katlı Metro
istasyonlarında (Peron, Konkurs, Teknik Kat, Zemin) model alanında yan yana
veya üst üste dizilmiş kat planlarını otomatik tespit eder, sınır kutularını (bbox)
dilimler, kat kotu sırasına dizer ve her katın topraklama ağını bağımsız ayrıştırır.
"""

import re
import math
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any

from shapely.geometry import box, Polygon, MultiPolygon
from shapely.ops import unary_union

logger = logging.getLogger(__name__)


def normalize_cad_text(text: str) -> str:
    """AutoCAD formatlama kodlarını temizler ve Türkçe küçük harfe çevirir."""
    if not text:
        return ""
    # AutoCAD MText formatlama etiketlerini temizle
    clean = re.sub(r'{\\[^}]+}', '', text)
    clean = re.sub(r'\\[A-Za-z0-9]+;', '', clean)
    clean = clean.replace('\\P', ' ').replace('\\p', ' ').replace('\\X', ' ').replace('\\x', ' ')
    clean = clean.replace('%%c', 'Ø').replace('%%C', 'Ø').replace('%%u', '').replace('%%U', '')
    
    # Türkçe küçük harf dönüşümü
    tr_map = str.maketrans('İIĞÜŞÖÇ', 'iıgüsoç')
    return clean.translate(tr_map).lower().strip()


@dataclass
class PlanTitleEntity:
    """Tespit edilen kat paftası başlık metni."""
    raw_text: str
    clean_text: str
    normalized_text: str
    discipline: str      # 'GROUNDING', 'POWER', 'WEAK_CURRENT', 'ARCHITECTURAL', 'LIGHTING', 'OTHER'
    floor_name: str      # 'TEMEL / BODRUM', 'ZEMIN', 'NORMAL', 'PERON', 'KONKURS', 'TEKNIK', etc.
    floor_category: str  # 'FOUNDATION', 'SUB_GRADE_3', 'SUB_GRADE_2', 'SUB_GRADE_1', 'GROUND', 'ABOVE_GROUND', 'ROOF'
    elevation_rank: int  # -4 (B4), -3 (Peron), -2 (Konkurs), -1 (Bodrum/Teknik), 0 (Zemin), 1..N, 99 (Çatı)
    point: Tuple[float, float]
    scale: str = ""      # örn: '1/50'


@dataclass
class FloorZone:
    """
    Dilimlenmiş tekil kat alanı ve bu kata ait topraklama/yapısal veriler.
    """
    zone_id: str
    title: PlanTitleEntity
    bbox: Tuple[float, float, float, float]  # (min_x, min_y, max_x, max_y)
    
    # Kat verileri
    grounding_segments: List[Any] = field(default_factory=list)
    grounding_inserts: List[Any] = field(default_factory=list)
    structural_segments: List[Any] = field(default_factory=list)
    
    # Geometrik ve elektriksel metrikler
    building_area_m2: float = 0.0
    building_width_m: float = 0.0
    building_length_m: float = 0.0
    grounding_length_m: float = 0.0
    rod_count: int = 0
    clamp_count: int = 0
    busbar_count: int = 0
    has_foundation_mesh: bool = False
    notes: List[str] = field(default_factory=list)


def parse_plan_title_entity(text: str, pt: Tuple[float, float], layer: str = "") -> Optional[PlanTitleEntity]:
    """
    Verilen CAD metnini inceler; bir kat veya tesisat planı başlığı olup olmadığını belirler.
    """
    if not text or len(text.strip()) == 0:
        return None
        
    norm = normalize_cad_text(text)
    clean = re.sub(r'{\\[^}]+}', '', text).replace('\\P', ' ').replace('\\X', ' ').strip()
    
    # 1. Başlık Olma Kriteri:
    # Gerçek bir pafta başlığı; 'plan', 'şema' veya açık kat adı ('bodrum kat', 'zemin kat', 'peron', 'konkurs', 'tabliye') içermelidir.
    has_plan_word = any(k in norm for k in ['plan', 'şema', 'sema', 'katı', 'kati', 'kotu', 'tabliye', 'döşeme', 'doseme'])
    has_floor_prefix = any(k in norm for k in [
        'bodrum kat', 'zemin kat', 'normal kat', 'peron', 'konkurs', 'teras kat', 'çatı kat', 'cati kat',
        'peron altı', 'peron alti', 'bilet holü', 'bilet holu', 'teknik kat', 'asma kat', 'üst tabliye', 'ust tabliye'
    ]) or bool(re.search(r'\d+\.\s*kat', norm))
    
    if not (has_plan_word or has_floor_prefix):
        return None
    if len(clean) > 90:
        return None

    # 2. Disiplin Tespiti:
    discipline = 'OTHER'
    if any(k in norm for k in ['toprak', 'ground', 'earth', 'temel topraklama']):
        discipline = 'GROUNDING'
    elif any(k in norm for k in ['kuvvetli', 'kolon şema', 'kolon sema', 'güç', 'guc']):
        discipline = 'POWER'
    elif any(k in norm for k in ['zayıf', 'zayif', 'yangın', 'yangin', 'diafon', 'interkom', 'telefon', 'data']):
        discipline = 'WEAK_CURRENT'
    elif any(k in norm for k in ['aydınlatma', 'aydinlatma']):
        discipline = 'LIGHTING'
    elif any(k in norm for k in ['mimari', 'kalıp', 'kalip', 'donatı', 'donati', 'statik']):
        discipline = 'ARCHITECTURAL'
    elif 'kat plan' in norm:
        discipline = 'ARCHITECTURAL'

    # 3. Kat Adı, Kategori ve Kot Sıralaması (Elevation Rank)
    floor_name = 'GENEL KAT'
    cat = 'GROUND'
    rank = 0

    # Metro ve Derin Bodrum Katları
    if any(k in norm for k in ['peron altı', 'peron alti', 'peronaltı', 'peronalti']):
        floor_name = 'PERON ALTI KATI'
        cat = 'SUB_GRADE_4'
        rank = -4
    elif any(k in norm for k in ['peron', 'ray', 'platform', '-4. kat', '-3. kat', 'b3 kat', 'b4 kat']):
        floor_name = 'PERON KATI'
        cat = 'SUB_GRADE_3'
        rank = -3
    elif any(k in norm for k in ['konkurs', 'bilet', '-2. kat', 'b2 kat', 'bilet holü', 'bilet holu']):
        floor_name = 'BİLET HOLÜ / KONKURS KATI'
        cat = 'SUB_GRADE_2'
        rank = -2
    elif any(k in norm for k in ['teknik', 'trafo merkezi', 'mekanik kat', 'şalt', 'salt']):
        floor_name = 'TEKNİK KAT'
        cat = 'SUB_GRADE_1'
        rank = -1
    elif any(k in norm for k in ['üst tabliye', 'ust tabliye', 'tabliye']):
        floor_name = 'ÜST TABLİYE'
        cat = 'GROUND'
        rank = 0
    elif any(k in norm for k in ['temel', 'radye']):
        floor_name = 'TEMEL / RADYE'
        cat = 'FOUNDATION'
        rank = -2
    elif any(k in norm for k in ['bodrum', '-1. kat', 'b1 kat']):
        floor_name = 'BODRUM KAT'
        cat = 'SUB_GRADE_1'
        rank = -1
    elif any(k in norm for k in ['zemin', 'giriş', 'giris', 'meydan']):
        floor_name = 'ZEMİN KAT'
        cat = 'GROUND'
        rank = 0
    elif any(k in norm for k in ['asma kat', 'galeri']):
        floor_name = 'ASMA KAT'
        cat = 'ABOVE_GROUND'
        rank = 1
    elif any(k in norm for k in ['teras', 'çatı', 'cati', 'paratoner']):
        floor_name = 'TERAS / ÇATI'
        cat = 'ROOF'
        rank = 99
    elif 'normal' in norm:
        floor_name = 'NORMAL KAT'
        cat = 'ABOVE_GROUND'
        rank = 1
    else:
        # N. Kat araması (örn: 1. Kat, 2. Kat, 4. Kat)
        m = re.search(r'(\d+)\.\s*kat', norm)
        if m:
            n = int(m.group(1))
            floor_name = f'{n}. KAT'
            cat = 'ABOVE_GROUND'
            rank = n

    # Ölçek tespiti (Ö : 1/50, 1/100 vb.)
    scale_m = re.search(r'ö\s*:\s*(1/\d+)', norm) or re.search(r'ölçek\s*:\s*(1/\d+)', norm)
    scale = scale_m.group(1) if scale_m else ""

    return PlanTitleEntity(
        raw_text=text,
        clean_text=clean,
        normalized_text=norm,
        discipline=discipline,
        floor_name=floor_name,
        floor_category=cat,
        elevation_rank=rank,
        point=pt,
        scale=scale
    )


class FloorSlicerEngine:
    """
    Çok katlı CAD paftalarını mekânsal olarak katlara dilimleyen motor.
    """

    def __init__(self, unit_factor: float = 10.0):
        self.unit_factor = unit_factor  # çizim birimi -> mm dönüşüm katsayısı (cm=10.0)

    def detect_floor_titles(self, drawing: Any) -> List[PlanTitleEntity]:
        """ParsedDrawing veya entity listesindeki tüm potansiyel pafta ve kat başlıklarını tespit eder."""
        titles: List[PlanTitleEntity] = []
        texts_to_scan: List[Tuple[str, Tuple[float, float], str]] = []
        
        if hasattr(drawing, 'all_texts') and drawing.all_texts:
            for t in drawing.all_texts:
                texts_to_scan.append((t.text, t.position, getattr(t, 'layer', '')))
        elif hasattr(drawing, 'msp_entities'):
            for e in drawing.msp_entities:
                if hasattr(e, 'dxftype') and e.dxftype() in ('TEXT', 'MTEXT'):
                    txt = e.dxf.text if e.dxftype() == 'TEXT' else e.text
                    pt = (e.dxf.insert.x, e.dxf.insert.y) if hasattr(e.dxf, 'insert') else (0.0, 0.0)
                    texts_to_scan.append((txt, pt, e.dxf.get('layer', '')))
        elif isinstance(drawing, list):
            for e in drawing:
                if hasattr(e, 'dxftype') and e.dxftype() in ('TEXT', 'MTEXT'):
                    txt = e.dxf.text if e.dxftype() == 'TEXT' else e.text
                    pt = (e.dxf.insert.x, e.dxf.insert.y) if hasattr(e.dxf, 'insert') else (0.0, 0.0)
                    texts_to_scan.append((txt, pt, e.dxf.get('layer', '')))

        for txt, pt, lay in texts_to_scan:
            t = parse_plan_title_entity(txt, pt, layer=lay)
            if t:
                titles.append(t)
        return titles

    def slice_drawing(
        self,
        drawing: Any,  # ParsedDrawing
        discipline_filter: Optional[str] = "GROUNDING"
    ) -> List[FloorZone]:
        """
        ParsedDrawing nesnesini inceler ve belirtilen disipline göre kat dilimlerini (FloorZone) çıkarır.
        Eğer disiplin 'GROUNDING' ise; topraklama planı başlıklarını ve etraflarındaki ağları izole eder.
        """
        all_titles = self.detect_floor_titles(drawing)
        
        # Filtreleme: İlgili disipline ait başlıkları seç
        disc_titles = [t for t in all_titles if t.discipline == discipline_filter]
        
        # Eğer özel topraklama başlığı yoksa ama genel kat başlıkları varsa onları kullan
        if not disc_titles:
            disc_titles = [t for t in all_titles if t.discipline in ('GROUNDING', 'ARCHITECTURAL', 'OTHER') and t.elevation_rank != 0 or 'kat' in t.normalized_text]

        # Hiç başlık bulunamadıysa: Tüm çizimi tek bir 'ZEMİN / GENEL' katı olarak ele al
        if not disc_titles:
            logger.info("Çizimde kat başlığı tespit edilemedi; tüm çizim tek kat kabul ediliyor.")
            default_title = PlanTitleEntity(
                raw_text="TEMEL / ZEMİN KAT PLANI",
                clean_text="TEMEL / ZEMİN KAT PLANI",
                normalized_text="temel / zemin kat planı",
                discipline=discipline_filter or "GROUNDING",
                floor_name="TEMEL / ZEMİN KAT",
                floor_category="FOUNDATION",
                elevation_rank=-1,
                point=(0.0, 0.0)
            )
            # Tüm çizim sınırını hesapla
            all_pts = []
            for s in drawing.grounding_segments:
                all_pts.extend([s.start, s.end])
            for s in drawing.structural_segments:
                all_pts.extend([s.start, s.end])
            if all_pts:
                min_x = min(p[0] for p in all_pts) - 1000.0
                max_x = max(p[0] for p in all_pts) + 1000.0
                min_y = min(p[1] for p in all_pts) - 1000.0
                max_y = max(p[1] for p in all_pts) + 1000.0
            else:
                min_x, min_y, max_x, max_y = 0.0, 0.0, 100000.0, 100000.0

            zone = FloorZone(
                zone_id="FLOOR_DEFAULT",
                title=default_title,
                bbox=(min_x, min_y, max_x, max_y),
                grounding_segments=drawing.grounding_segments,
                grounding_inserts=drawing.grounding_inserts,
                structural_segments=drawing.structural_segments
            )
            return [zone]

        # Birden fazla başlık varsa: Benzer koordinattaki mükerrerleri filtrele
        unique_titles: List[PlanTitleEntity] = []
        for t in disc_titles:
            # Yakın mesafede (örn < 5 metre) aynı başlık varsa birleştir
            too_close = False
            for ut in unique_titles:
                dist = math.hypot(t.point[0] - ut.point[0], t.point[1] - ut.point[1])
                # Çizim birimi cm için 500 = 5 metre
                if dist < 500.0:
                    too_close = True
                    break
            if not too_close:
                unique_titles.append(t)

        logger.info(f"Kat Ayrıştırma: {len(unique_titles)} adet bağımsız kat/pafta başlığı tespit edildi.")

        # Paftaların model alanındaki yerleşim eksenini belirle (Çoğunlukla yatay dizilirler: X artar)
        unique_titles.sort(key=lambda t: t.point[0])
        
        # Bounding Box dilimleme (X ve Y sınır aralıkları)
        floor_zones: List[FloorZone] = []
        
        for i, t in enumerate(unique_titles):
            # Yatay sınırları komşu başlıkların orta noktalarına göre dilimle
            if len(unique_titles) == 1:
                min_x = t.point[0] - 25000.0  # 250 m sol
                max_x = t.point[0] + 25000.0  # 250 m sağ
            else:
                if i == 0:
                    delta_right = (unique_titles[i+1].point[0] - t.point[0]) / 2.0
                    min_x = t.point[0] - delta_right
                    max_x = t.point[0] + delta_right
                elif i == len(unique_titles) - 1:
                    delta_left = (t.point[0] - unique_titles[i-1].point[0]) / 2.0
                    min_x = t.point[0] - delta_left
                    max_x = t.point[0] + delta_left
                else:
                    min_x = (unique_titles[i-1].point[0] + t.point[0]) / 2.0
                    max_x = (t.point[0] + unique_titles[i+1].point[0]) / 2.0

            # Y sınırları: Başlığın üstünde kalan kat planını kapsayacak şekilde
            min_y = t.point[1] - 3000.0   # Başlığın biraz altı
            max_y = t.point[1] + 35000.0  # Başlığın üstündeki plan (350 metre)

            # Bu dilime düşen topraklama ve yapısal elemanları topla
            zone_gnd_segs = [
                s for s in drawing.grounding_segments
                if min_x <= (s.start[0] + s.end[0]) / 2.0 <= max_x
                and min_y <= (s.start[1] + s.end[1]) / 2.0 <= max_y
            ]
            zone_gnd_inserts = [
                ins for ins in drawing.grounding_inserts
                if min_x <= ins.position[0] <= max_x
                and min_y <= ins.position[1] <= max_y
            ]
            zone_struct_segs = [
                s for s in drawing.structural_segments
                if min_x <= (s.start[0] + s.end[0]) / 2.0 <= max_x
                and min_y <= (s.start[1] + s.end[1]) / 2.0 <= max_y
            ]

            # Metraj ve blok sayımı (mm -> metre)
            total_gnd_len = sum(s.length for s in zone_gnd_segs) / 1000.0
            rods = [ins for ins in zone_gnd_inserts if '1tp' in ins.block_name.lower() or 'cubuk' in ins.block_name.lower() or 'kazik' in ins.block_name.lower()]
            clamps = [ins for ins in zone_gnd_inserts if '1ekk' in ins.block_name.lower() or 'klemens' in ins.block_name.lower()]
            busbars = [ins for ins in zone_gnd_inserts if 'etb' in ins.block_name.lower() or 'bara' in ins.block_name.lower()]

            has_mesh = len(zone_gnd_segs) >= 4 and total_gnd_len >= 20.0

            zone = FloorZone(
                zone_id=f"FLOOR_{i+1}_{t.floor_name.replace(' ', '_')}",
                title=t,
                bbox=(min_x, min_y, max_x, max_y),
                grounding_segments=zone_gnd_segs,
                grounding_inserts=zone_gnd_inserts,
                structural_segments=zone_struct_segs,
                grounding_length_m=total_gnd_len,
                rod_count=len(rods),
                clamp_count=len(clamps),
                busbar_count=len(busbars),
                has_foundation_mesh=has_mesh
            )
            floor_zones.append(zone)

        # Katları fiziksel kot sırasına (en alttan en üste: Peron -> Bodrum -> Zemin -> Normal -> Çatı) göre diz
        floor_zones.sort(key=lambda z: z.title.elevation_rank)

        for z in floor_zones:
            logger.info(
                f"  Dilim: {z.title.elevation_rank:+2d} | {z.title.floor_name:15s} | "
                f"Şerit: {z.grounding_length_m:6.1f}m | Çubuk: {z.rod_count} | Klemens: {z.clamp_count} | "
                f"Ağ Durumu: {'TEMEL AĞI MEVCUT' if z.has_foundation_mesh else 'Boş / İletkensiz'}"
            )

        return floor_zones
