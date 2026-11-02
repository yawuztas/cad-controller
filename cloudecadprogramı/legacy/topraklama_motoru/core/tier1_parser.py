"""
CloudeCAD — Tier 1: DXF Parser
================================
ezdxf kullanarak DXF dosyasını okur, entity'leri kategorize eder
ve geometrik veriyi temiz Python veri yapılarına dönüştürür.

Eski sistemden temel fark:
  Eski: Koordinatlar "1234.56, 789.01" string → Shapely kullanamaz
  Yeni: Koordinatlar (1234.56, 789.01) tuple → Shapely doğrudan kullanır
"""

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import ezdxf
from ezdxf.math import Vec3

from config import MIN_LINE_LENGTH_MM
from standards.layer_profiles import (
    classify_layer, is_grounding_layer,
    is_grounding_block, is_non_grounding_block,
    is_structural_layer
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  VERİ YAPILARI (Dataclass)
# ═══════════════════════════════════════════════════════════════

@dataclass
class Segment:
    """Bir çizgi segmentini temsil eder (LINE, LWPOLYLINE'dan üretilir)."""
    start: tuple[float, float]   # (x, y) — mm veya çizim birimi
    end: tuple[float, float]     # (x, y)
    layer: str = ""
    length: float = 0.0          # Öklid uzunluğu (çizim birimiyle)
    entity_type: str = "LINE"    # Kaynak entity tipi
    handle: str = ""             # DXF handle (takip için)

    def __post_init__(self):
        if self.length == 0.0:
            dx = self.end[0] - self.start[0]
            dy = self.end[1] - self.start[1]
            self.length = math.hypot(dx, dy)


@dataclass
class InsertPoint:
    """Bir blok referansının konumunu temsil eder."""
    position: tuple[float, float]   # (x, y)
    block_name: str = ""
    layer: str = ""
    rotation_deg: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    handle: str = ""
    attributes: dict = field(default_factory=dict)  # {tag: value}


@dataclass
class TextEntity:
    """Metin entity'si (TEXT veya MTEXT)."""
    position: tuple[float, float]
    text: str = ""
    layer: str = ""
    height: float = 0.0
    rotation_deg: float = 0.0


@dataclass
class ParsedDrawing:
    """
    Ayrıştırılmış DXF çiziminin tüm verisi.
    Tier 2 geometri motoruna bu nesne iletilir.
    """
    # ── Kaynak dosya ─────────────────────────────────────────
    source_file: str = ""
    dxf_version: str = ""
    unit_factor: float = 1.0   # Çizim birimi → mm dönüşüm katsayısı

    # ── Katman bilgisi ────────────────────────────────────────
    all_layers: dict = field(default_factory=dict)   # {name: category}
    grounding_layers: list = field(default_factory=list)
    structural_layers: list = field(default_factory=list)

    # ── Topraklama geometrisi ─────────────────────────────────
    grounding_segments: list[Segment] = field(default_factory=list)
    grounding_inserts: list[InsertPoint] = field(default_factory=list)
    grounding_texts: list[TextEntity] = field(default_factory=list)

    # ── Yapısal geometri (bina sınırı tespiti için) ───────────
    structural_segments: list[Segment] = field(default_factory=list)

    all_texts: list = field(default_factory=list)           # TUM katmanlardaki metinler
    # ── Mekânsal Denetim & Uygulama Projesi Varlıkları ────────
    equipment_elements: list = field(default_factory=list)  # Metal kapak, merdiven, ızgara, pompa, pano vb.
    clamp_points: list = field(default_factory=list)        # Vidalı klemens (kkk) koordinatları (mm)
    busbar_points: list = field(default_factory=list)       # Topraklama barası (tb/ECB) sembolleri
    grid_axes: list = field(default_factory=list)           # Mimari aks (S-GRID-IDEN) koordinatları
    # ── İstatistik ────────────────────────────────────────────
    total_entities: int = 0
    skipped_short: int = 0      # Min. uzunluk altında atlanan çizgiler

    def summary(self) -> dict:
        """Özet istatistik sözlüğü."""
        return {
            "kaynak_dosya": self.source_file,
            "dxf_versiyonu": self.dxf_version,
            "toplam_entity": self.total_entities,
            "topraklama_katmanlari": self.grounding_layers,
            "yapisal_katmanlar": self.structural_layers,
            "topraklama_segment": len(self.grounding_segments),
            "topraklama_blok": len(self.grounding_inserts),
            "topraklama_metin": len(self.grounding_texts),
            "yapisal_segment": len(self.structural_segments),
            "atlanan_kisa_cizgi": self.skipped_short,
        }


# ═══════════════════════════════════════════════════════════════
#  UNIT FACTOR — ezdxf'in UNITS değerinden mm dönüşümü
# ═══════════════════════════════════════════════════════════════
# ezdxf header $INSUNITS değerleri:
# 0=Tanımsız, 1=İnç, 2=Feet, 3=Mil, 4=mm, 5=cm, 6=m, ...

_UNIT_TO_MM = {
    0: 1.0,      # Tanımsız → mm varsay
    1: 25.4,     # İnç
    2: 304.8,    # Feet
    3: 0.0254,   # Mil (mil = 1/1000 inç)
    4: 1.0,      # mm
    5: 10.0,     # cm
    6: 1000.0,   # m
    7: 1e6,      # km (nadiren kullanılır)
    8: 1609344.0,# Mil (yer)
}


def _get_unit_factor(doc) -> float:
    """
    DXF dökümanından mm dönüşüm katsayısını hesaplar.
    
    Türkiye elektrik ve mimari projelerinde AutoCAD şablonu (acadiso.dwt)
    çoğunlukla $INSUNITS=4 (mm) veya 0 kalsa dahi:
      - Konut ve ticari binalar genellikle CENTİMETRE (cm) (katsayı=10.0),
      - Altyapı, raylı sistem ve metro istasyonları METRE (m) (katsayı=1000.0),
      - Bazı detay ve makine projeleri MİLİMETRE (mm) (katsayı=1.0)
    olarak çizilir. Bu fonksiyon geometrik varlıkları istatistiksel ve topolojik
    olarak inceleyerek gerçek çizim ölçeğini tespit eder.
    """
    try:
        msp = doc.modelspace()
        
        # 1. Kapı genişliği heuriştiği (~70-90 cm / 65-110 birim)
        kapi_lines = [
            e for e in msp
            if any(k in e.dxf.get("layer", "").lower() for k in ["kapi", "kapı", "door"])
            and "ölçü" not in e.dxf.get("layer", "").lower()
            and "olcu" not in e.dxf.get("layer", "").lower()
            and e.dxftype() == "LINE"
        ]
        if kapi_lines:
            kapi_lens = [
                math.hypot(e.dxf.end[0] - e.dxf.start[0], e.dxf.end[1] - e.dxf.start[1])
                for e in kapi_lines
            ]
            cm_doors = [l for l in kapi_lens if 65.0 <= l <= 110.0]
            mm_doors = [l for l in kapi_lens if 650.0 <= l <= 1100.0]
            m_doors = [l for l in kapi_lens if 0.65 <= l <= 1.10]
            
            if len(cm_doors) >= 3:
                logger.info(f"Birim doğrulandı: {len(cm_doors)} adet kapı genişliği (~70-90cm) tespit edildi → CM birimi (katsayı=10.0)")
                return 10.0
            elif len(mm_doors) >= 3:
                logger.info(f"Birim doğrulandı: {len(mm_doors)} adet kapı genişliği (~700-900mm) tespit edildi → MM birimi (katsayı=1.0)")
                return 1.0
            elif len(m_doors) >= 3:
                logger.info(f"Birim doğrulandı: {len(m_doors)} adet kapı genişliği (~0.7-0.9m) tespit edildi → METRE birimi (katsayı=1000.0)")
                return 1000.0

        # 2. Topraklama hatları ve iletken segment uzunlukları
        gnd_lens = []
        for e in msp:
            lay = e.dxf.get("layer", "")
            if is_grounding_layer(lay):
                if e.dxftype() == "LINE":
                    l = math.hypot(e.dxf.end.x - e.dxf.start.x, e.dxf.end.y - e.dxf.start.y)
                    if l > 0.01:
                        gnd_lens.append(l)
                elif e.dxftype() in ("LWPOLYLINE", "POLYLINE"):
                    try:
                        pts = list(e.get_points("xy")) if e.dxftype() == "LWPOLYLINE" else [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                        for p1, p2 in zip(pts[:-1], pts[1:]):
                            l = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                            if l > 0.01:
                                gnd_lens.append(l)
                    except Exception:
                        pass
        if len(gnd_lens) >= 5:
            gnd_lens.sort()
            med_gnd = gnd_lens[len(gnd_lens) // 2]
            max_gnd = gnd_lens[-1]
            if max_gnd <= 150.0 and med_gnd <= 5.0:
                logger.info(f"Birim doğrulandı: Topraklama hatları medyan={med_gnd:.2f}, maks={max_gnd:.2f} → Fiilen METRE çizilmiş (katsayı=1000.0)")
                return 1000.0
            elif 500.0 <= max_gnd <= 25000.0 and 15.0 <= med_gnd <= 180.0:
                logger.info(f"Birim doğrulandı: Topraklama hatları medyan={med_gnd:.1f}, maks={max_gnd:.1f} → Fiilen CM çizilmiş (katsayı=10.0)")
                return 10.0
            elif med_gnd >= 200.0 or max_gnd > 25000.0:
                logger.info(f"Birim doğrulandı: Topraklama hatları medyan={med_gnd:.1f}, maks={max_gnd:.1f} → Fiilen MM çizilmiş (katsayı=1.0)")
                return 1.0

        # 3. Model alanı genel çizgi istatistiği (Çizgi medyanı ve 90. persentil)
        msp_lens = []
        coords_x = []
        for e in msp:
            if e.dxftype() == "LINE":
                l = math.hypot(e.dxf.end.x - e.dxf.start.x, e.dxf.end.y - e.dxf.start.y)
                if l > 0.05:
                    msp_lens.append(l)
                if len(coords_x) < 50:
                    coords_x.append(abs(e.dxf.start.x))
            if len(msp_lens) >= 300:
                break
        if len(msp_lens) >= 15:
            msp_lens.sort()
            med_l = msp_lens[len(msp_lens) // 2]
            p90_l = msp_lens[int(len(msp_lens) * 0.9)]
            if med_l < 5.0 and p90_l < 50.0:
                logger.info(f"Birim doğrulandı: ModelSpace çizgi medyanı={med_l:.2f}, P90={p90_l:.2f} → Fiilen METRE çizilmiş (katsayı=1000.0)")
                return 1000.0
            elif 12.0 <= med_l <= 150.0:
                logger.info(f"Birim doğrulandı: ModelSpace çizgi medyanı={med_l:.1f} → Fiilen CM çizilmiş (katsayı=10.0)")
                return 10.0
            elif med_l > 200.0:
                logger.info(f"Birim doğrulandı: ModelSpace çizgi medyanı={med_l:.1f} → Fiilen MM çizilmiş (katsayı=1.0)")
                return 1.0

        # 4. Georeferanslı UTM / ITRF koordinat kontrolü (Altyapı/Metro haritaları)
        if coords_x and max(coords_x) > 10000.0:
            max_sampled = max(msp_lens) if msp_lens else 0
            if max_sampled < 500.0:
                logger.info(f"Birim doğrulandı: Georeferanslı koordinatlar (X > 10.000) ve maks boy={max_sampled:.1f} → METRE birimi (katsayı=1000.0)")
                return 1000.0

        # 5. Mimari ve taşıyıcı elemanların boyutlarını incele (Kolon, Duvar, Perde)
        arch_dims = []
        for e in msp:
            lay = e.dxf.get("layer", "").lower()
            if any(k in lay for k in ['kolon', 'column', 'duvar', 'wall', 'structural', 'bearing', 'betonarme']):
                if e.dxftype() == 'LINE':
                    l = math.hypot(e.dxf.end[0] - e.dxf.start[0], e.dxf.end[1] - e.dxf.start[1])
                    if l > 0.05:
                        arch_dims.append(l)
                elif e.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
                    try:
                        pts = list(e.get_points('xy')) if e.dxftype() == 'LWPOLYLINE' else [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                        if len(pts) >= 2:
                            dx = max(p[0] for p in pts) - min(p[0] for p in pts)
                            dy = max(p[1] for p in pts) - min(p[1] for p in pts)
                            if dx > 0.05 and dy > 0.05:
                                arch_dims.append(max(dx, dy))
                    except Exception:
                        pass
            if len(arch_dims) >= 150:
                break

        if len(arch_dims) >= 10:
            arch_dims.sort()
            median_dim = arch_dims[len(arch_dims) // 2]
            if 15.0 <= median_dim <= 180.0:
                logger.info(f"Birim doğrulandı: Mimari eleman medyanı {median_dim:.1f} → Fiilen CM çizilmiş (katsayı=10.0)")
                return 10.0
            elif 200.0 <= median_dim <= 2000.0:
                logger.info(f"Birim doğrulandı: Mimari eleman medyanı {median_dim:.1f} → Fiilen MM çizilmiş (katsayı=1.0)")
                return 1.0
            elif 0.15 <= median_dim <= 2.0:
                logger.info(f"Birim doğrulandı: Mimari eleman medyanı {median_dim:.2f} → Fiilen METRE çizilmiş (katsayı=1000.0)")
                return 1000.0

        # 6. $INSUNITS header kontrolü (fallback)
        insunits = doc.header.get("$INSUNITS", 0)
        insunits = int(insunits) if insunits is not None else 0
        if insunits in (1, 2, 3, 5, 6, 7, 8):
            factor = _UNIT_TO_MM.get(insunits, 1.0)
            return factor

        # Default fallback
        return 1.0
    except Exception as e:
        logger.warning(f"Birim tespiti hatası ({e}), varsayılan katsayı=1.0")
        return 1.0


# ═══════════════════════════════════════════════════════════════
#  PARSER SINIFI
# ═══════════════════════════════════════════════════════════════

class DXFParser:
    """
    ezdxf tabanlı DXF ayrıştırıcı.

    Kullanım:
        parser = DXFParser()
        drawing = parser.parse("proje.dxf")
    """

    def __init__(self, min_length_mm: float = MIN_LINE_LENGTH_MM):
        self.min_length_mm = min_length_mm

    def parse(self, dxf_path: Path) -> ParsedDrawing:
        """
        DXF dosyasını ayrıştırır ve ParsedDrawing döner.
        """
        dxf_path = Path(dxf_path)
        logger.info(f"DXF ayrıştırılıyor: {dxf_path.name}")

        try:
            doc = ezdxf.readfile(str(dxf_path))
        except ezdxf.DXFError as e:
            raise ValueError(f"Geçersiz DXF dosyası: {e}") from e
        except FileNotFoundError:
            raise FileNotFoundError(f"DXF bulunamadı: {dxf_path}")

        msp = doc.modelspace()
        unit_factor = _get_unit_factor(doc)

        drawing = ParsedDrawing(
            source_file=dxf_path.name,
            dxf_version=doc.dxfversion,
            unit_factor=unit_factor,
        )

        # 1) Katman listesini oluştur
        self._parse_layers(doc, drawing)

        # 2) Entity'leri tara
        self._parse_entities(msp, drawing, unit_factor)

        logger.info(
            f"Ayrıştırma tamamlandı — "
            f"{len(drawing.grounding_segments)} topraklama segmenti, "
            f"{len(drawing.grounding_inserts)} blok, "
            f"{drawing.total_entities} toplam entity"
        )
        return drawing

    # ── Katman Ayrıştırma ──────────────────────────────────────────────────

    def _parse_layers(self, doc, drawing: ParsedDrawing):
        """Tüm katmanları listeler ve kategorize eder."""
        grounding = []
        structural = []
        all_layers = {}

        for layer in doc.layers:
            name = layer.dxf.name
            cat = classify_layer(name)
            all_layers[name] = cat
            if cat == "grounding":
                grounding.append(name)
            elif cat == "structural":
                structural.append(name)

        if not grounding:
            has_bim_elc = any(
                any(k in b.name.upper() for k in ["ELC", "FLOORPLAN", "TOPRAK"])
                for b in doc.blocks
                if not b.name.startswith("*")
            )
            if has_bim_elc:
                logger.info("✓ Revit/BIM elektrik ve kat planı blokları tespit edildi — topraklama hatları BIM bloklarından çözümlenecek.")
            else:
                logger.warning(
                    "⚠️  İsim regex'i ile topraklama katmanı bulunamadı. "
                    "Topolojik Halka/Göz Algılayıcı (LayerFingerprinter) devreye giriyor..."
                )
                from core.layer_fingerprint import LayerFingerprinter
                fp = LayerFingerprinter(unit_factor=drawing.unit_factor)
                topological_layers = fp.identify_grounding_layers(doc)
                if topological_layers:
                    logger.info(f"✓ Topolojik parmak izi ile {len(topological_layers)} topraklama katmanı kurtarıldı: {topological_layers}")
                    for tlay in topological_layers:
                        all_layers[tlay] = "grounding"
                        grounding.append(tlay)
                else:
                    logger.warning(
                        "⚠️  Topolojik incelemede de topraklama katmanı tespit EDİLEMEDİ.\n"
                        "    DXF'teki tüm katman isimleri:\n" +
                        "\n".join(f"      • {n}" for n in sorted(all_layers.keys()))
                    )

        drawing.all_layers = all_layers
        drawing.grounding_layers = grounding
        drawing.structural_layers = structural

    # ── Entity Ayrıştırma ──────────────────────────────────────────────────

    def _parse_entities(self, msp, drawing: ParsedDrawing, unit_factor: float):
        """ModelSpace entity'lerini tarar ve kategorize eder.
        
        v2 degisiklikler:
        - INSERT'ler explode edilerek blok icindeki geometri de cikarilir
        - TUM katmanlardaki metinler okunur (parametre cikarmak icin)
        - ARC entity'ler de segment olarak eklenir
        """
        total = 0
        skipped = 0

        # Block tanimlarini onceden al (explode icin)
        doc = msp.doc if hasattr(msp, 'doc') else None

        for entity in msp:
            total += 1
            etype = entity.dxftype()
            layer = entity.dxf.get("layer", "0")
            cat = drawing.all_layers.get(layer, classify_layer(layer))
            is_gnd = (cat == "grounding")
            is_str = (cat == "structural")

            try:
                if etype == "LINE":
                    seg = self._parse_line(entity, layer, unit_factor)
                    if seg:
                        if seg.length < self.min_length_mm:
                            skipped += 1
                        elif is_gnd:
                            drawing.grounding_segments.append(seg)
                        elif is_str:
                            drawing.structural_segments.append(seg)

                elif etype in ("LWPOLYLINE", "POLYLINE"):
                    segs = self._parse_polyline(entity, layer, unit_factor)
                    for seg in segs:
                        if seg.length < self.min_length_mm:
                            skipped += 1
                        elif is_gnd:
                            drawing.grounding_segments.append(seg)
                        elif is_str:
                            drawing.structural_segments.append(seg)

                elif etype == "ARC":
                    if is_gnd or is_str:
                        segs = self._parse_arc(entity, layer, unit_factor)
                        for seg in segs:
                            if seg.length < self.min_length_mm:
                                skipped += 1
                            elif is_gnd:
                                drawing.grounding_segments.append(seg)
                            elif is_str:
                                drawing.structural_segments.append(seg)

                elif etype == "INSERT":
                    bname = getattr(entity.dxf, 'name', '')
                    # Antet, logo, lejant çerçevesi gibi pafta kenarlıklarını atla
                    if any(k in bname.upper() for k in ['LOGO', 'A0-', 'A1-', 'TITLE', 'ANTET', 'TTLB', 'SYMB']):
                        continue

                    if is_gnd:
                        # Katman kirliliği koruması: Tefriş/Aydınlatma blokları topraklama katmanında yer alsa dahi elenir
                        if is_non_grounding_block(bname):
                            logger.info(
                                f"⚠️ Katman Kirliliği (Layer Misuse) Önleme: '{bname}' bloğu "
                                f"'{layer}' katmanında yer alıyor ancak mimari/aydınlatma elemanı. Elendi."
                            )
                            continue

                        ins = self._parse_insert(entity, layer, unit_factor)
                        if ins:
                            drawing.grounding_inserts.append(ins)
                        # INSERT icindeki geometriyi sadece gercek topraklama semboluyse explode et
                        if doc is not None and is_grounding_block(bname):
                            exploded = self._explode_insert(
                                entity, doc, layer, unit_factor
                            )
                            for seg in exploded:
                                if seg.length >= self.min_length_mm:
                                    drawing.grounding_segments.append(seg)
                    else:
                        # Katman '0' veya diğer katmanlardaki BIM / Revit / alt disiplin bloklarını aç
                        if doc is not None and bname in doc.blocks:
                            self._explode_bim_insert(entity, doc, drawing, unit_factor)

                elif etype in ("TEXT", "MTEXT"):
                    # Topraklama katmanindaki metinler
                    if is_gnd:
                        txt = self._parse_text(entity, layer, unit_factor)
                        if txt:
                            drawing.grounding_texts.append(txt)
                    # TUM katmanlardaki metinleri de kaydet
                    # (parametre cikarimi icin — rho, L, d, n vs.)
                    txt = self._parse_text(entity, layer, unit_factor)
                    if txt:
                        drawing.all_texts.append(txt)

                # CIRCLE: Topraklama buat veya kazik sembolu olabilir
                elif etype == "CIRCLE":
                    if is_gnd:
                        ins = self._parse_circle_as_insert(entity, layer, unit_factor)
                        if ins:
                            drawing.grounding_inserts.append(ins)

            except Exception as e:
                logger.debug(f"Entity atlandi ({etype}/{layer}): {e}")
                continue

        drawing.total_entities = total
        drawing.skipped_short = skipped

        logger.info(
            f"Entity tarama: {total} toplam, "
            f"{skipped} kisa cizgi atlandi"
        )

    # ── Tekil Entity Parse Metodları ───────────────────────────────────────

    def _parse_line(
        self, entity, layer: str, uf: float
    ) -> Optional[Segment]:
        """LINE entity'den Segment üretir."""
        try:
            s = entity.dxf.start
            e = entity.dxf.end
            start = (s.x * uf, s.y * uf)
            end   = (e.x * uf, e.y * uf)
            return Segment(
                start=start, end=end,
                layer=layer, entity_type="LINE",
                handle=entity.dxf.get("handle", ""),
            )
        except Exception:
            return None

    def _parse_polyline(
        self, entity, layer: str, uf: float
    ) -> list[Segment]:
        """LWPOLYLINE / POLYLINE'ı ardışık Segment listesine dönüştürür."""
        segs = []
        try:
            if entity.dxftype() == "LWPOLYLINE":
                pts = [(p[0] * uf, p[1] * uf) for p in entity.get_points("xy")]
            else:
                # Eski POLYLINE — vertex'lerden al
                pts = [
                    (v.dxf.location.x * uf, v.dxf.location.y * uf)
                    for v in entity.vertices
                ]

            if len(pts) < 2:
                return segs

            for i in range(len(pts) - 1):
                segs.append(Segment(
                    start=pts[i], end=pts[i + 1],
                    layer=layer, entity_type="POLYLINE",
                    handle=entity.dxf.get("handle", ""),
                ))

            # Kapalı polyline: son → ilk
            if hasattr(entity.dxf, "flags") and entity.is_closed:
                segs.append(Segment(
                    start=pts[-1], end=pts[0],
                    layer=layer, entity_type="POLYLINE",
                    handle=entity.dxf.get("handle", "") + "_close",
                ))
        except Exception as e:
            logger.debug(f"Polyline parse hatası: {e}")
        return segs

    def _parse_insert(
        self, entity, layer: str, uf: float
    ) -> Optional[InsertPoint]:
        """INSERT (blok referansı) entity'den InsertPoint üretir."""
        try:
            pos = entity.dxf.insert
            attrs = {}
            # Blok attribute'larını oku
            if hasattr(entity, "attribs"):
                for attrib in entity.attribs:
                    tag = attrib.dxf.get("tag", "")
                    val = attrib.dxf.get("text", "")
                    if tag and val:
                        attrs[tag] = val

            return InsertPoint(
                position=(pos.x * uf, pos.y * uf),
                block_name=entity.dxf.name,
                layer=layer,
                rotation_deg=math.degrees(entity.dxf.get("rotation", 0.0)),
                scale_x=entity.dxf.get("xscale", 1.0),
                scale_y=entity.dxf.get("yscale", 1.0),
                handle=entity.dxf.get("handle", ""),
                attributes=attrs,
            )
        except Exception as e:
            logger.debug(f"INSERT parse hatası: {e}")
            return None

    def _parse_text(
        self, entity, layer: str, uf: float
    ) -> Optional[TextEntity]:
        """TEXT / MTEXT entity'den TextEntity üretir."""
        try:
            if entity.dxftype() == "TEXT":
                pos = entity.dxf.insert
                txt = entity.dxf.get("text", "").strip()
                height = entity.dxf.get("height", 0.0)
                rot = entity.dxf.get("rotation", 0.0)
            else:  # MTEXT
                pos = entity.dxf.insert
                try:
                    txt = entity.plain_text().strip()
                except Exception:
                    txt = getattr(entity, 'text', '').strip()
                height = entity.dxf.get("char_height", 0.0)
                rot = entity.dxf.get("rotation", 0.0)

            if not txt:
                return None

            return TextEntity(
                position=(pos.x * uf, pos.y * uf),
                text=txt,
                layer=layer,
                height=height * uf,
                rotation_deg=rot,
            )
        except Exception as e:
            logger.debug(f"TEXT parse hatası: {e}")
            return None

    def _parse_circle_as_insert(
        self, entity, layer: str, uf: float
    ) -> Optional[InsertPoint]:
        """CIRCLE'ı topraklama noktası (buat/kazık) olarak işler."""
        try:
            center = entity.dxf.center
            radius = entity.dxf.radius * uf
            return InsertPoint(
                position=(center.x * uf, center.y * uf),
                block_name=f"CIRCLE_r{radius:.0f}",
                layer=layer,
                handle=entity.dxf.get("handle", ""),
            )
        except Exception as e:
            logger.debug(f"CIRCLE parse hatasi: {e}")
            return None

    def _explode_insert(
        self, entity, doc, parent_layer: str, uf: float,
        depth: int = 0
    ) -> list[Segment]:
        """
        INSERT (blok referansi) icindeki geometriyi cozumler.
        
        Blok tanimindaki LINE, LWPOLYLINE, ARC entity'lerini
        INSERT'in konum, olcek ve rotasyonuna gore donusturur.
        
        Maksimum 3 seviye ic ice blok destekler (sonsuz dongu onlemi).
        """
        if depth > 3:
            return []
        
        segments = []
        try:
            block_name = entity.dxf.name
            if block_name not in doc.blocks:
                return []
            
            block = doc.blocks[block_name]
            
            # INSERT transformasyonu
            ins_x = entity.dxf.insert.x * uf
            ins_y = entity.dxf.insert.y * uf
            sx = entity.dxf.get("xscale", 1.0)
            sy = entity.dxf.get("yscale", 1.0)
            rot_rad = math.radians(entity.dxf.get("rotation", 0.0))
            cos_r = math.cos(rot_rad)
            sin_r = math.sin(rot_rad)
            
            def transform(px, py):
                """Blok lokal koordinatini INSERT global koordinatina donustur."""
                # Olcekle
                tx = px * uf * sx
                ty = py * uf * sy
                # Dondur
                rx = tx * cos_r - ty * sin_r
                ry = tx * sin_r + ty * cos_r
                # Ofsette
                return (rx + ins_x, ry + ins_y)
            
            for be in block:
                betype = be.dxftype()
                try:
                    if betype == "LINE":
                        s = transform(be.dxf.start.x, be.dxf.start.y)
                        e = transform(be.dxf.end.x, be.dxf.end.y)
                        segments.append(Segment(
                            start=s, end=e,
                            layer=parent_layer,
                            entity_type="LINE(explode)",
                            handle=be.dxf.get("handle", ""),
                        ))
                    
                    elif betype in ("LWPOLYLINE", "POLYLINE"):
                        if betype == "LWPOLYLINE":
                            pts = [(p[0], p[1]) for p in be.get_points("xy")]
                        else:
                            pts = [(v.dxf.location.x, v.dxf.location.y) for v in be.vertices]
                        
                        tpts = [transform(p[0], p[1]) for p in pts]
                        for i in range(len(tpts) - 1):
                            segments.append(Segment(
                                start=tpts[i], end=tpts[i+1],
                                layer=parent_layer,
                                entity_type="POLYLINE(explode)",
                            ))
                        if hasattr(be, 'is_closed') and be.is_closed and len(tpts) > 2:
                            segments.append(Segment(
                                start=tpts[-1], end=tpts[0],
                                layer=parent_layer,
                                entity_type="POLYLINE(explode)",
                            ))
                    
                    elif betype == "ARC":
                        cx, cy = be.dxf.center.x, be.dxf.center.y
                        r = be.dxf.radius
                        sa = math.radians(be.dxf.start_angle)
                        ea = math.radians(be.dxf.end_angle)
                        # Yayi 8 segmente bol
                        if ea < sa:
                            ea += 2 * math.pi
                        n_seg = max(4, int((ea - sa) / (math.pi / 8)))
                        angles = [sa + (ea - sa) * i / n_seg for i in range(n_seg + 1)]
                        arc_pts = [transform(cx + r * math.cos(a), cy + r * math.sin(a)) for a in angles]
                        for i in range(len(arc_pts) - 1):
                            segments.append(Segment(
                                start=arc_pts[i], end=arc_pts[i+1],
                                layer=parent_layer,
                                entity_type="ARC(explode)",
                            ))
                    
                    elif betype == "INSERT":
                        # Ic ice blok — recursive
                        sub_segs = self._explode_insert(
                            be, doc, parent_layer, uf, depth + 1
                        )
                        segments.extend(sub_segs)
                
                except Exception:
                    continue
        
        except Exception as e:
            logger.debug(f"INSERT explode hatasi ({entity.dxf.name}): {e}")
        
        return segments

    def _parse_arc(
        self, entity, layer: str, uf: float, n_segments: int = 8
    ) -> list[Segment]:
        """ARC entity'yi ardisik duz segmentlere donusturur."""
        segments = []
        try:
            cx = entity.dxf.center.x * uf
            cy = entity.dxf.center.y * uf
            r = entity.dxf.radius * uf
            sa = math.radians(entity.dxf.start_angle)
            ea = math.radians(entity.dxf.end_angle)
            
            if ea < sa:
                ea += 2 * math.pi
            
            n = max(4, int((ea - sa) / (math.pi / 8)))
            angles = [sa + (ea - sa) * i / n for i in range(n + 1)]
            pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in angles]
            
            for i in range(len(pts) - 1):
                segments.append(Segment(
                    start=pts[i], end=pts[i+1],
                    layer=layer,
                    entity_type="ARC",
                    handle=entity.dxf.get("handle", ""),
                ))
        except Exception as e:
            logger.debug(f"ARC parse hatasi: {e}")
        
        return segments

    def _explode_bim_insert(
        self, entity, doc, drawing: ParsedDrawing, uf: float,
        parent_tf=None, depth: int = 0
    ):
        """
        Revit BIM exportları ve blok referansları içindeki geometriyi çözer.
        Taşıyıcı elemanları (S-COLS, A-WALL) yapısal segmentlere,
        elektrik/topraklama hatlarını (LINE, LWPOLYLINE ve ARC dönüşlerini) topraklama segmentlerine,
        kapak/merdiven/ızgara/pompa/pano gibi ekipmanları equipment_elements listesine,
        klemens (kkk) ve baraları (tb) ilgili listelere ekler.
        """
        if depth > 4:
            return

        try:
            bname = entity.dxf.name
            if bname not in doc.blocks:
                return
            bname_upper = bname.upper()
            ent_layer = entity.dxf.get("layer", "0").upper()

            if any(k in bname_upper for k in [
                'LOGO', 'A0-', 'A1-', 'TITLE', 'ANTET', 'TTLB', 'SYMB',
                '_OBLIQUE', 'OKK', 'CONDUIT_SET', 'SECTION', 'GRID HEAD',
                'PEDESTAL', 'CERAMIC', 'DOLGU BETONU', 'DOGU BETONU', 'PRECAST U CANAL'
            ]):
                return

            block = doc.blocks[bname]

            ins_x = entity.dxf.insert.x
            ins_y = entity.dxf.insert.y
            sx = entity.dxf.get("xscale", 1.0)
            sy = entity.dxf.get("yscale", 1.0)
            rot_deg = entity.dxf.get("rotation", 0.0)
            rot_rad = math.radians(rot_deg)
            cos_r = math.cos(rot_rad)
            sin_r = math.sin(rot_rad)

            def tf(px, py):
                tx = px * sx
                ty = py * sy
                rx = tx * cos_r - ty * sin_r
                ry = tx * sin_r + ty * cos_r
                gx = rx + ins_x
                gy = ry + ins_y
                if parent_tf:
                    return parent_tf(gx, gy)
                return (gx, gy)

            ins_global = parent_tf(ins_x, ins_y) if parent_tf else (ins_x, ins_y)
            ins_mm = (ins_global[0] * uf, ins_global[1] * uf)

            # Dinamik lejant kontrolü (Sabit X > 85000 filtresi kaldırıldı, istasyonun tamamı taranır)
            is_in_legend_area = ("LEJANT" in bname_upper or "SEMBOL" in bname_upper)

            # 1) Vidalı Topraklama Klemensi (kkk)
            if "KKK" in bname_upper:
                if not is_in_legend_area:
                    drawing.clamp_points.append(ins_mm)
                    drawing.grounding_inserts.append(InsertPoint(
                        position=ins_mm,
                        block_name="Vidalı Topraklama Klemensi (kkk)",
                        layer="BIM-KLEMENS"
                    ))
                return

            # 2) Topraklama Barası Sembolü (tb / C7CD84BE7)
            if any(k in bname_upper for k in ["_TB-", "C7CD84BE7", "TOPRAKLAMA_BARASI"]):
                if not is_in_legend_area:
                    drawing.busbar_points.append({"position": ins_mm, "block_name": bname})
                    drawing.grounding_inserts.append(InsertPoint(
                        position=ins_mm,
                        block_name="40x5mm Bakır Topraklama Barası",
                        layer="BIM-BARA"
                    ))
                return

            # 3) Denetlenecek Metal Yapı Elemanları ve Mekanik/Elektrik Ekipmanlar
            eq_cat = None
            eq_rule = ""
            if "INSPECTION HATCH" in bname_upper:
                eq_cat = "Metal Muayene / Şaft Kapağı"
                eq_rule = "Proje Notu Md.1 (16mm² Cu / Örgülü Bakır)"
            elif "OPEN COVER" in bname_upper:
                eq_cat = "Metal Döşeme Kapağı (KMM)"
                eq_rule = "Proje Notu Md.1 (16mm² Cu / Örgülü Bakır)"
            elif "STAIR-LADDER" in bname_upper:
                eq_cat = "Metal Şaft / Kedi Merdiveni"
                eq_rule = "Proje Notu Md.1 (16mm² Cu)"
            elif "IZGARA" in bname_upper:
                eq_cat = "Metal Drenaj Izgarası / Mazgal"
                eq_rule = "Proje Notu Md.1 (16mm² Cu)"
            elif "ESC-" in bname_upper or "ESCALATOR" in bname_upper:
                eq_cat = "Yürüyen Merdiven Karkası / Çukuru"
                eq_rule = "İBB Şartnamesi Bölüm 8 & Proje Notu Md.1"
            elif any(k in bname_upper for k in ["YD400", "DAMPER", "PANJUR"]):
                eq_cat = "Duman Atma / Yangın Damperi & Şaft Panjuru"
                eq_rule = "Proje Notu Md.1 & Md.3 (16mm² Cu)"
            elif any(k in bname_upper for k in ["NP 3171", "C4F9D3624", "PUMP", "POMPA"]):
                eq_cat = "Mekanik Drenaj / Karter Pompası"
                eq_rule = "Proje Notu Md.3 & Ortak Teknik Şartname Md.A.1.15"
            elif ent_layer == "M-EQPM" and "RVT" not in bname_upper:
                eq_cat = "Mekanik Havalandırma / Pompa Teçhizatı"
                eq_rule = "Proje Notu Md.3 (Koruma Topraklaması)"
            elif ent_layer == "E-ELEC-EQPM" and "RVT" not in bname_upper:
                eq_cat = "Elektrik Dağıtım / MCC Panosu"
                eq_rule = "Proje Notu Md.2 & Md.13 (PE Barası / Topraklama)"
            elif "_B-V" in bname_upper or "_B-4748" in bname_upper:
                # Bara üzerindeki civata/terminal sembolü — ekipman değildir
                return

            if eq_cat is not None:
                if not is_in_legend_area:
                    pts_mm = []
                    for be in block:
                        bt = be.dxftype()
                        if bt == "LINE":
                            p1 = tf(be.dxf.start.x, be.dxf.start.y)
                            p2 = tf(be.dxf.end.x, be.dxf.end.y)
                            pts_mm.extend([(p1[0] * uf, p1[1] * uf), (p2[0] * uf, p2[1] * uf)])
                        elif bt == "LWPOLYLINE":
                            for p in be.get_points("xy"):
                                tp = tf(p[0], p[1])
                                pts_mm.append((tp[0] * uf, tp[1] * uf))
                        elif bt == "ARC":
                            cp = tf(be.dxf.center.x, be.dxf.center.y)
                            pts_mm.append((cp[0] * uf, cp[1] * uf))
                    if not pts_mm:
                        pts_mm = [ins_mm]
                    cx_mm = sum(p[0] for p in pts_mm) / len(pts_mm)
                    cy_mm = sum(p[1] for p in pts_mm) / len(pts_mm)
                    if not ("LEJANT" in bname_upper or "SEMBOL" in bname_upper):
                        # Kısa okunaklı blok adı
                        short_name = bname.split("-BIT")[0].split("_rvt")[0]
                        if "FloorPlan-" in short_name and "__dwg_" in short_name:
                            short_name = short_name.split("__dwg_")[-1]
                        drawing.equipment_elements.append({
                            "category": eq_cat,
                            "rule": eq_rule,
                            "block_name": short_name[:50],
                            "center": (cx_mm, cy_mm),
                            "points": pts_mm[::max(1, len(pts_mm) // 25)],
                            "layer": ent_layer,
                        })
                return

            is_elc_block = any(k in bname_upper for k in ['ELC', 'TOPRAK', 'GND', 'EARTH', 'FLOORPLAN'])
            is_str_block = any(k in bname_upper for k in ['STR', 'ARC', 'WALL', 'COL'])

            def _resolve_bim_gnd_layer(be_obj, base_layer: str) -> tuple[bool, str]:
                """FloorPlan/ELC bloğu içindeki iletkenleri rengine ve çizgi tipine göre sınıflandırır."""
                col = be_obj.dxf.get("color", 256)
                lt = str(be_obj.dxf.get("linetype", "BYLAYER")).upper()
                # Renk 2 (Sarı) + BYLAYER/CONTINUOUS çizgiler metin oklarıdır (callout leader), kablo değildir!
                if col == 2 and lt in ("BYLAYER", "CONTINUOUS"):
                    return False, base_layer
                if col == 130:
                    return True, "BIM-ANA-TOPRAKLAMA-AGI (120-240mm2 Cu)"
                elif col == 43:
                    return True, "BIM-TALI-TOPRAKLAMA-AGI (Tava Irtibatli Cu)"
                elif col == 63:
                    return True, "BIM-KORUMA-ILETKENI (16mm2 H07Z-R Bransman)"
                elif col == 3:
                    return True, "BIM-RAY-HASIR-DONATI-IRTIBATI (185mm2)"
                elif col == 53:
                    return True, "BIM-ISLETME-ZAYIF-AKIM-IRTIBATI"
                return True, (base_layer if base_layer != "0" else "BIM-TOPRAKLAMA")

            for be in block:
                betype = be.dxftype()
                blay = be.dxf.get("layer", "0")
                bcat = drawing.all_layers.get(blay, classify_layer(blay))
                is_be_gnd = (bcat == "grounding") or is_grounding_layer(blay)
                is_be_str = (bcat == "structural") or is_structural_layer(blay)
                eff_glay = blay

                if blay == "0" and is_elc_block and not is_str_block:
                    is_be_gnd, eff_glay = _resolve_bim_gnd_layer(be, blay)
                elif blay == "0" and is_str_block and not is_elc_block:
                    is_be_str = True

                if betype == "LINE":
                    s_raw = tf(be.dxf.start.x, be.dxf.start.y)
                    e_raw = tf(be.dxf.end.x, be.dxf.end.y)
                    s = (s_raw[0] * uf, s_raw[1] * uf)
                    e = (e_raw[0] * uf, e_raw[1] * uf)
                    l = math.hypot(e[0] - s[0], e[1] - s[1])
                    if l >= self.min_length_mm:
                        seg = Segment(start=s, end=e, layer=eff_glay if is_be_gnd else blay, entity_type="LINE(bim)", handle=be.dxf.get("handle", ""))
                        if is_be_gnd:
                            drawing.grounding_segments.append(seg)
                            if eff_glay not in drawing.grounding_layers:
                                drawing.grounding_layers.append(eff_glay)
                        elif is_be_str:
                            drawing.structural_segments.append(seg)

                elif betype in ("LWPOLYLINE", "POLYLINE"):
                    if betype == "LWPOLYLINE":
                        pts = list(be.get_points("xy"))
                    else:
                        pts = [(v.dxf.location.x, v.dxf.location.y) for v in be.vertices]
                    tpts = [tf(p[0], p[1]) for p in pts]
                    tpts_mm = [(p[0] * uf, p[1] * uf) for p in tpts]
                    is_closed = getattr(be, "is_closed", False)
                    for i in range(len(tpts_mm) - 1):
                        seg = Segment(start=tpts_mm[i], end=tpts_mm[i+1], layer=eff_glay if is_be_gnd else blay, entity_type="POLYLINE(bim)")
                        if seg.length >= self.min_length_mm:
                            if is_be_gnd:
                                drawing.grounding_segments.append(seg)
                                if eff_glay not in drawing.grounding_layers:
                                    drawing.grounding_layers.append(eff_glay)
                            elif is_be_str:
                                drawing.structural_segments.append(seg)
                    if is_closed and len(tpts_mm) > 2:
                        seg = Segment(start=tpts_mm[-1], end=tpts_mm[0], layer=eff_glay if is_be_gnd else blay, entity_type="POLYLINE(bim)")
                        if seg.length >= self.min_length_mm:
                            if is_be_gnd:
                                drawing.grounding_segments.append(seg)
                                if eff_glay not in drawing.grounding_layers:
                                    drawing.grounding_layers.append(eff_glay)
                            elif is_be_str:
                                drawing.structural_segments.append(seg)

                elif betype == "ARC":
                    # Kablo dönüş köşelerindeki (fillet) yayları çözümle — kopukluk hatasını önler!
                    if is_be_gnd or is_be_str:
                        cx, cy = be.dxf.center.x, be.dxf.center.y
                        r = be.dxf.radius
                        sa = math.radians(be.dxf.start_angle)
                        ea = math.radians(be.dxf.end_angle)
                        if ea < sa:
                            ea += 2 * math.pi
                        n_seg = max(4, int((ea - sa) / (math.pi / 8)))
                        angles = [sa + (ea - sa) * i / n_seg for i in range(n_seg + 1)]
                        arc_pts = [tf(cx + r * math.cos(a), cy + r * math.sin(a)) for a in angles]
                        arc_pts_mm = [(p[0] * uf, p[1] * uf) for p in arc_pts]
                        for i in range(len(arc_pts_mm) - 1):
                            seg = Segment(
                                start=arc_pts_mm[i], end=arc_pts_mm[i+1],
                                layer=eff_glay if is_be_gnd else blay,
                                entity_type="ARC(bim)"
                            )
                            if seg.length >= 20.0:  # Köşe dönüş yayları kısa olabilir, 20mm üstünü koru
                                if is_be_gnd:
                                    drawing.grounding_segments.append(seg)
                                    if eff_glay not in drawing.grounding_layers:
                                        drawing.grounding_layers.append(eff_glay)
                                elif is_be_str:
                                    drawing.structural_segments.append(seg)

                elif betype in ("TEXT", "MTEXT"):
                    if betype == "TEXT":
                        txt = be.dxf.text.strip()
                        pos = be.dxf.insert
                    else:
                        txt = be.plain_text().strip() if hasattr(be, "plain_text") else getattr(be, "text", "").strip()
                        pos = be.dxf.insert
                    if txt:
                        tpos = tf(pos.x, pos.y)
                        tpos_mm = (tpos[0] * uf, tpos[1] * uf)
                        te = TextEntity(position=tpos_mm, text=txt, layer=blay)
                        drawing.all_texts.append(te)
                        if blay == "S-GRID-IDEN":
                            clean_lbl = re.sub(r"\\f[^;]+;|\\[A-Za-z0-9]+;|\{|\}", "", txt).strip()
                            if clean_lbl and len(clean_lbl) <= 4:
                                drawing.grid_axes.append({"label": clean_lbl, "position": tpos_mm})
                        if is_be_gnd or any(k in txt.lower() for k in ['toprak', 'bara', 'kazik', 'özgül', 'pe', 'iletken', 'ecb', 'mm²', 'mm2', 'cu']):
                            drawing.grounding_texts.append(te)

                elif betype == "INSERT":
                    self._explode_bim_insert(
                        be, doc, drawing, uf, parent_tf=tf, depth=depth + 1
                    )
        except Exception as e:
            logger.debug(f"BIM explode hatası ({getattr(entity.dxf, 'name', '')}): {e}")

