"""
CloudeCAD — Otomatik Redline / Revizyon Bulutlu CAD Paftası Üretici (Redline DXF Generator)
===========================================================================================
Denetim sonucunda tespit edilen unutulmuş kapakları, topraklanmamış ekipmanları ve
T-ek noktalarında unutulmuş klemens ('kkk') sembollerini doğrudan orijinal AutoCAD (DXF)
paftasının kopyası üzerine yeni denetim katmanları olarak çizer:

  • !!_CLOUDECAD_HATA_BULUTU    (Kırmızı - ACI 1) : Unutulan ekipman/kapak etrafına
                                                    gerçek yaylı AutoCAD Revizyon Bulutu
                                                    (REVCLOUD) ve açıklama etiketi çizer.
  • !!_CLOUDECAD_EKSIK_KLEMENS  (Turuncu - ACI 30): Klemens sembolü unutulan T-ek
                                                    noktalarına uyarı çemberi çizer.
  • !!_CLOUDECAD_ONAYLI_EKIPMAN (Yeşil - ACI 3)   : Doğru topraklanmış elemanlara onay
                                                    halkası koyar.
"""

import math
import logging
from pathlib import Path
from typing import Optional, Any
import ezdxf

logger = logging.getLogger(__name__)


def _add_revcloud_polygon(msp, center_x: float, center_y: float, radius: float, layer: str) -> None:
    """
    Verilen merkez ve yarıçapta gerçek AutoCAD Revizyon Bulutu (yaylı LWPOLYLINE, bulge=0.55) çizer.
    """
    num_lobes = 12
    points_with_bulge = []
    for i in range(num_lobes):
        angle = (2.0 * math.pi * i) / num_lobes
        px = center_x + radius * math.cos(angle)
        py = center_y + radius * math.sin(angle)
        # (x, y, start_width, end_width, bulge) -> pozitif/negatif bulge dışbükey bulut yayı üretir
        points_with_bulge.append((px, py, 0.0, 0.0, -0.55))

    poly = msp.add_lwpolyline(
        points_with_bulge,
        format="xyseb",
        close=True,
        dxfattribs={"layer": layer, "color": 1, "lineweight": 50}
    )
    return poly


def generate_redline_dxf(
    source_dxf_path: Path,
    analysis_res: Any,
    output_dxf_path: Path,
    unit_factor: float = 1000.0
) -> Optional[Path]:
    """
    Kaynak DXF dosyasını okuyarak üzerine denetim bulgularını (Revizyon Bulutları,
    Eksik Klemens İşaretleri ve Hata Notları) çizer ve yeni bir *_REDLINE.dxf olarak kaydeder.
    """
    source_dxf_path = Path(source_dxf_path)
    output_dxf_path = Path(output_dxf_path)
    if not source_dxf_path.exists():
        logger.warning(f"Redline için kaynak DXF bulunamadı: {source_dxf_path}")
        return None

    try:
        doc = ezdxf.readfile(str(source_dxf_path))
        msp = doc.modelspace()

        # Denetim katmanlarını oluştur
        layer_defs = [
            ("!!_CLOUDECAD_HATA_BULUTU", 1, 50),      # Kırmızı (ACI 1), 0.50mm
            ("!!_CLOUDECAD_EKSIK_KLEMENS", 30, 35),   # Turuncu (ACI 30), 0.35mm
            ("!!_CLOUDECAD_ONAYLI_EKIPMAN", 3, 25),   # Yeşil (ACI 3), 0.25mm
        ]
        for lname, aci_color, lw in layer_defs:
            if lname not in doc.layers:
                doc.layers.add(name=lname, color=aci_color, lineweight=lw)

        # CAD çizim birimi ölçeği:
        # tier1_parser tüm koordinatları mm'ye normalize etmiştir (coord * unit_factor).
        # Orijinal DXF koordinatına geri dönmek için mm koordinatını unit_factor'a böleriz.
        uf = unit_factor if unit_factor > 0 else 1000.0
        # 1.8 metrelik revizyon bulutu yarıçapı (orijinal CAD biriminde)
        cloud_radius = (1800.0 / uf)
        text_height = (350.0 / uf)
        clamp_radius = (450.0 / uf)

        # 1. Unutulmuş / Topraklanmamış Ekipmanlara Kırmızı Revizyon Bulutu Çiz
        defects = getattr(analysis_res, "spatial_defects", [])
        for idx, df in enumerate(defects, start=1):
            pos_mm = getattr(df, "position", (0.0, 0.0))
            if not pos_mm or (pos_mm[0] == 0 and pos_mm[1] == 0):
                continue
            cx = pos_mm[0] / uf
            cy = pos_mm[1] / uf

            _add_revcloud_polygon(msp, cx, cy, cloud_radius, "!!_CLOUDECAD_HATA_BULUTU")

            # Ok çizgisi ve Hata Etiketi
            tx = cx + cloud_radius * 1.15
            ty = cy + cloud_radius * 0.85
            msp.add_line(
                (cx + cloud_radius * 0.7, cy + cloud_radius * 0.7),
                (tx, ty),
                dxfattribs={"layer": "!!_CLOUDECAD_HATA_BULUTU", "color": 1, "lineweight": 35}
            )
            label_text = (
                f"HATA #{idx}: {df.category} TOPRAKLANMAMIS "
                f"(En Yakin Hat: {df.nearest_grounding_m:.2f}m)"
            )
            msp.add_text(
                label_text,
                dxfattribs={
                    "layer": "!!_CLOUDECAD_HATA_BULUTU",
                    "color": 1,
                    "height": text_height,
                    "insert": (tx + (150.0 / uf), ty)
                }
            )

        # 2. Eksik Klemens (kkk) T-Ek Noktalarına Turuncu Uyarı Çemberi Çiz
        missing_clamps = getattr(analysis_res, "missing_clamp_points", [])
        for pt_mm in missing_clamps:
            kx = pt_mm[0] / uf
            ky = pt_mm[1] / uf
            msp.add_circle(
                (kx, ky),
                radius=clamp_radius,
                dxfattribs={"layer": "!!_CLOUDECAD_EKSIK_KLEMENS", "color": 30, "lineweight": 35}
            )

        # 3. Doğru Topraklanmış Ekipmanlara Yeşil Onay Halkası Çiz
        grounded = getattr(analysis_res, "grounded_elements", [])
        for ge in grounded:
            pos_mm = getattr(ge, "position", (0.0, 0.0))
            if not pos_mm or (pos_mm[0] == 0 and pos_mm[1] == 0):
                continue
            gx = pos_mm[0] / uf
            gy = pos_mm[1] / uf
            msp.add_circle(
                (gx, gy),
                radius=clamp_radius * 1.1,
                dxfattribs={"layer": "!!_CLOUDECAD_ONAYLI_EKIPMAN", "color": 3, "lineweight": 25}
            )

        output_dxf_path.parent.mkdir(parents=True, exist_ok=True)
        doc.saveas(str(output_dxf_path))
        logger.info(
            f"✓ Redline CAD paftası üretildi: {output_dxf_path.name} "
            f"({len(defects)} hata bulutu, {len(missing_clamps)} eksik klemens işareti)"
        )
        return output_dxf_path
    except Exception as e:
        logger.warning(f"Redline DXF üretilemedi: {e}")
        return None
