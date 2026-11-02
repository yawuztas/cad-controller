"""
İnterkom / Görüntülü Diafon ve Kapı Otomatiği Standartları
=========================================================
Daire içi şube/monitör eşleşmesi, bina giriş paneli, kapı otomatiği
ve zayıf akım besleme trafosu kontrol kriterleri.
"""

from typing import Dict, Any


def evaluate_intercom_system(dwelling_count: int, entrance_count: int = 1) -> Dict[str, Any]:
    """
    İnterkom ve kapı kontrol altyapı gereksinimlerini hesaplar.
    """
    panel_type = "DİJİTAL REHBERLİ VE KAMERALI KAPI PANELİ" if dwelling_count > 12 else "BUTONLU VE KAMERALI KAPI PANELİ"

    return {
        "dwelling_count": dwelling_count,
        "required_monitors": dwelling_count,
        "entrance_count": entrance_count,
        "recommended_entrance_panel": panel_type,
        "door_release_required": True,
        "power_supply_recommended": "24V DC 2.5A Regüleli Güç Kaynağı + Akü Grubu",
        "cabling_type": "Cat6 veya 4x2x0.8 DT-8 Bükümlü Kablo"
    }
