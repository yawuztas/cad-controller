"""
BTK Bina İçi Elektronik Haberleşme Tesisatı Teknik Şartnamesi & TIA/EIA 568
===========================================================================
Bina ana telefon/data kutusu (BTK), kat dağıtım kutuları (1TK),
daire prizleri (T/RJ45) kapasite ve yedekleme denetim kuralları.
"""

from typing import Dict, Any


def calculate_telecom_capacities(dwelling_count: int, floor_count: int) -> Dict[str, Any]:
    """
    BTK şartnamesine göre gereken asgari telefon/data altyapı kapasitelerini hesaplar.
    """
    dwellings_per_floor = max(1, dwelling_count // max(1, floor_count))

    # Daire başına asgari 2 hat (telefon + internet/data)
    min_pairs_per_dwelling = 2
    total_active_pairs = dwelling_count * min_pairs_per_dwelling

    # BTK (Bina Ana Kutusu) Kapasitesi: En az %20 yedek ile standart reglet kademesi (10, 20, 30, 50, 100, 200 çift)
    standard_btk_sizes = [10, 20, 30, 50, 100, 200, 300, 500]
    required_btk_pairs = total_active_pairs * 1.20
    recommended_btk = standard_btk_sizes[-1]
    for s in standard_btk_sizes:
        if s >= required_btk_pairs:
            recommended_btk = s
            break

    # Kat Kutusu (1TK) Kapasitesi: Katta bulunan daireler için çift sayısı + %20 yedek
    floor_pairs = dwellings_per_floor * min_pairs_per_dwelling * 1.20
    standard_tk_sizes = [10, 20, 30, 50]
    recommended_tk = standard_tk_sizes[-1]
    for s in standard_tk_sizes:
        if s >= floor_pairs:
            recommended_tk = s
            break

    return {
        "dwelling_count": dwelling_count,
        "floor_count": floor_count,
        "min_active_pairs": total_active_pairs,
        "btk_capacity_required": round(required_btk_pairs, 0),
        "btk_recommended_spec": f"{recommended_btk} Çiftlik BTK Kutusu",
        "floor_tk_recommended_spec": f"{recommended_tk} Çiftlik Kat Dağıtım Kutusu (1TK)",
        "backbone_cable_recommended": f"Cat6 UTP / {recommended_btk} Perlik Telefon Kablosu"
    }
