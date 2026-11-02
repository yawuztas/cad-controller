"""
Binaların Yangından Korunması Hakkında Yönetmelik (BYKHY) & TS EN 54-14
=====================================================================
Yangın algılama ve ihbar sistemlerinin projelendirme kriterleri,
dedektör koruma alanları, buton aralıkları ve yangın senaryosu entegrasyon kuralları.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class FireMandatoryCheck:
    """Yangın algılama sistemi zorunluluk durumu"""
    is_mandatory: bool
    reasons: List[str]
    system_type_recommended: str  # 'ADRESLİ' veya 'KONVANSİYONEL'


def evaluate_fire_alarm_mandate(
    building_height_m: float,
    dwelling_count: int,
    total_area_m2: float,
    has_basement_carpark: bool = True
) -> FireMandatoryCheck:
    """
    BYKHY Madde 74 ve 75 uyarınca yangın algılama sisteminin yasal zorunluluğunu değerlendirir.
    """
    reasons = []
    is_mand = False

    if building_height_m > 21.5:
        is_mand = True
        reasons.append(f"Yapı yüksekliği ({building_height_m:.1f} m) > 21.5 m (BYKHY Md 75).")

    if dwelling_count > 20:
        is_mand = True
        reasons.append(f"Toplam bağımsız bölüm ({dwelling_count}) > 20 adet konut/işyeri.")

    if total_area_m2 > 1000.0:
        is_mand = True
        reasons.append(f"Toplam kapalı alan ({total_area_m2:,.0f} m²) > 1,000 m².")

    if has_basement_carpark:
        is_mand = True
        reasons.append("Bodrum kat otopark/kazan dairesi/teknik hacim mevcuttur.")

    sys_type = "ADRESLİ YANGIN ALGILAMA" if (dwelling_count > 30 or building_height_m > 30.5) else "KONVANSİYONEL VEYA ADRESLİ"

    return FireMandatoryCheck(
        is_mandatory=is_mand,
        reasons=reasons,
        system_type_recommended=sys_type
    )


def check_detector_spacing(area_m2: float, ceiling_height_m: float = 2.8, detector_type: str = "SMOKE") -> Dict[str, float]:
    """
    TS EN 54-14 Çizelge A.1'e göre dedektör azami koruma alanı ve yarıçapını döner.
    """
    if detector_type.upper() in ("HEAT", "ISI", "SICAKLIK"):
        # Isı dedektörü
        max_area = 30.0 if ceiling_height_m <= 7.5 else 20.0
        radius = 5.3
    else:
        # Optik duman dedektörü
        max_area = 50.0 if ceiling_height_m <= 6.0 else 40.0
        radius = 7.5

    required_detectors = max(1, int(area_m2 / max_area) + (1 if area_m2 % max_area > 5.0 else 0))

    return {
        "max_coverage_area_m2": max_area,
        "max_radius_m": radius,
        "calculated_min_detectors": required_detectors
    }
