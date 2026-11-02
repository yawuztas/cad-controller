"""
CloudeCAD — Elektrik İç Tesisleri Yönetmeliği (EİTY) ve TEDAŞ Kuralları
=======================================================================
Gerilim düşümü limitleri, talep faktörü hesapları, can güvenliği (KAKR)
ve faz dengeleme standartları.
"""

import math

# ── Gerilim Düşümü İzin Verilen Azami Sınırları (EİTY Madde 57) ───────────────
LIMIT_VDROP_LIGHTING = 1.5       # Aydınlatma ve priz devreleri (%1.5)
LIMIT_VDROP_POWER = 3.0          # Motor ve güç devreleri (%3.0)
LIMIT_VDROP_MAIN_FEEDER = 3.5    # Kofre / Trafo - Ana Pano arası (%3.5)
LIMIT_VDROP_TRANSFORMER_TOTAL = 5.0 # Özel trafolu tesislerde toplam sınır (%5.0)

# ── Gerilim Düşümü Sabitleri (Bakır İletken, κ = 56 m/(Ω·mm²)) ─────────────────
K_COPPER_3PHASE = 0.0124  # 380V Trifaze (100 / (κ * U²))
K_COPPER_1PHASE = 0.0740  # 220V Monofaze (200 / (κ * U²))

# ── Konutlar İçin Eşzamanlılık Tablosu (BEDAŞ / TEDAŞ Standart) ───────────────
BUILDING_DIVERSITY_TABLE = [
    (1, 2, 0.80),
    (3, 5, 0.60),
    (6, 10, 0.45),
    (11, 20, 0.38),
    (21, 30, 0.33),
    (31, 40, 0.28),
    (41, 50, 0.26),
    (51, 999, 0.25),
]


def calculate_dwelling_demand_power(installed_w: float) -> float:
    """
    BEDAŞ / EMO Konut Daire Talep Gücü:
    İlk 8000 W için %60, 8000 W üzeri için %40 eşzamanlılık.
    """
    if installed_w <= 8000.0:
        return installed_w * 0.60
    return (8000.0 * 0.60) + ((installed_w - 8000.0) * 0.40)


def get_building_diversity_factor(dwelling_count: int) -> float:
    """Bina daire sayısına göre genel eşzamanlılık (talep) katsayısı."""
    if dwelling_count <= 0:
        return 1.0
    for min_d, max_d, factor in BUILDING_DIVERSITY_TABLE:
        if min_d <= dwelling_count <= max_d:
            return factor
    return 0.25


def calculate_voltage_drop_approx(
    length_m: float,
    power_w: float,
    cross_section_mm2: float,
    is_three_phase: bool = True
) -> float:
    """
    Klasik Türk Proje Formülü (Omik Yaklaşım):
    Trifaze: %e = 0.0124 * (L * P_kW) / S
    Monofaze: %e = 0.074 * (L * P_kW) / S
    """
    if cross_section_mm2 <= 0 or length_m <= 0:
        return 0.0
    p_kw = power_w / 1000.0
    k = K_COPPER_3PHASE if is_three_phase else K_COPPER_1PHASE
    return round(k * (length_m * p_kw) / cross_section_mm2, 3)


def calculate_voltage_drop_exact(
    length_m: float,
    current_a: float,
    cross_section_mm2: float,
    r_ohm_km: float,
    x_ohm_km: float,
    cos_phi: float = 0.8,
    is_three_phase: bool = True,
    voltage_v: float = 380.0
) -> float:
    """
    TS HD 60364 ve IEC Kesin Gerilim Düşümü Formülü (Omik + Endüktif):
    Trifaze:  ΔU = √3 * I * L * (R * cosφ + X * sinφ)
    Monofaze: ΔU = 2 * I * L * (R * cosφ + X * sinφ)
    %e = (ΔU / U) * 100
    """
    sin_phi = math.sqrt(max(0.0, 1.0 - cos_phi**2))
    l_km = length_m / 1000.0
    
    # Hat empedansı
    z_line = (r_ohm_km * cos_phi + x_ohm_km * sin_phi) * l_km
    
    if is_three_phase:
        delta_u = math.sqrt(3.0) * current_a * z_line
    else:
        delta_u = 2.0 * current_a * z_line

    pct_e = (delta_u / voltage_v) * 100.0
    return round(pct_e, 3)
