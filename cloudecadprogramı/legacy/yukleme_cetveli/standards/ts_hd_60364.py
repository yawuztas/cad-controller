"""
CloudeCAD — TS HD 60364-5-52 ve TS 212 Standartları
===================================================
Bakır iletkenler için akım taşıma kapasiteleri (Iz),
sıcaklık düzeltme faktörleri, demetleme faktörleri,
empedans (R, X) ve standart koruma elemanı anma akımları.
"""

# ── Standart Bakır Kablo Kesitleri ve Temel Akım Taşıma Kapasiteleri (30°C) ───
# TS HD 60364-5-52 Tablo B.52.2 & B.52.4
# "conduit": B1/B2 (Boru içinde sıva altı/üstü)
# "air": E/F (Havada/kablo tavasında delikli)
COPPER_CABLE_SPECS = {
    1.5:  {"conduit": 15.5, "air": 19.5, "r_ohm_km": 12.1,  "x_ohm_km": 0.100, "conduit_dia_mm": 16.0},
    2.5:  {"conduit": 21.0, "air": 27.0, "r_ohm_km": 7.41,  "x_ohm_km": 0.090, "conduit_dia_mm": 18.0},
    4.0:  {"conduit": 28.0, "air": 36.0, "r_ohm_km": 4.61,  "x_ohm_km": 0.082, "conduit_dia_mm": 20.0},
    6.0:  {"conduit": 36.0, "air": 47.0, "r_ohm_km": 3.08,  "x_ohm_km": 0.082, "conduit_dia_mm": 25.0},
    10.0: {"conduit": 50.0, "air": 65.0, "r_ohm_km": 1.83,  "x_ohm_km": 0.082, "conduit_dia_mm": 32.0},
    16.0: {"conduit": 68.0, "air": 87.0, "r_ohm_km": 1.15,  "x_ohm_km": 0.082, "conduit_dia_mm": 32.0},
    25.0: {"conduit": 89.0, "air": 114.0, "r_ohm_km": 0.727, "x_ohm_km": 0.082, "conduit_dia_mm": 40.0},
    35.0: {"conduit": 110.0, "air": 141.0, "r_ohm_km": 0.524, "x_ohm_km": 0.079, "conduit_dia_mm": 50.0},
    50.0: {"conduit": 134.0, "air": 182.0, "r_ohm_km": 0.387, "x_ohm_km": 0.078, "conduit_dia_mm": 50.0},
    70.0: {"conduit": 171.0, "air": 234.0, "r_ohm_km": 0.268, "x_ohm_km": 0.075, "conduit_dia_mm": 63.0},
    95.0: {"conduit": 207.0, "air": 284.0, "r_ohm_km": 0.193, "x_ohm_km": 0.075, "conduit_dia_mm": 75.0},
    120.0: {"conduit": 239.0, "air": 330.0, "r_ohm_km": 0.153, "x_ohm_km": 0.073, "conduit_dia_mm": 90.0},
    150.0: {"conduit": 272.0, "air": 381.0, "r_ohm_km": 0.124, "x_ohm_km": 0.073, "conduit_dia_mm": 90.0},
    185.0: {"conduit": 310.0, "air": 436.0, "r_ohm_km": 0.099, "x_ohm_km": 0.072, "conduit_dia_mm": 110.0},
    240.0: {"conduit": 364.0, "air": 515.0, "r_ohm_km": 0.075, "x_ohm_km": 0.072, "conduit_dia_mm": 125.0},
}

# ── Sıcaklık Düzeltme Katsayısı (k_temp) — TS HD 60364-5-52 Tablo B.52.14 ─────
# Ortam sıcaklığı (°C) -> XLPE / HFFR (90°C azami işletme)
TEMPERATURE_DERATING_XLPE = {
    10: 1.15, 15: 1.12, 20: 1.08, 25: 1.04, 30: 1.00,
    35: 0.96, 40: 0.91, 45: 0.87, 50: 0.82, 55: 0.76, 60: 0.71
}

# PVC yalıtkan (70°C azami işletme)
TEMPERATURE_DERATING_PVC = {
    10: 1.22, 15: 1.17, 20: 1.12, 25: 1.06, 30: 1.00,
    35: 0.94, 40: 0.87, 45: 0.79, 50: 0.71, 55: 0.61, 60: 0.50
}

# ── Demetleme / Gruplama Katsayısı (k_group) — TS HD 60364-5-52 Tablo B.52.17 ──
# Şaftta veya tavada yan yana giden çok damarlı kablo adedi
GROUP_DERATING_TABLE = [
    (1, 1.00),
    (2, 0.80),
    (3, 0.70),
    (4, 0.65),
    (5, 0.60),
    (6, 0.57),
    (7, 0.54),
    (8, 0.52),
    (9, 0.50),
    (12, 0.45),
    (16, 0.41),
    (20, 0.38),
]

# Standart Sigorta ve Kesici Anma Akımları (Amper)
STANDARD_BREAKERS = [
    6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000
]


def get_base_ampacity(cross_section_mm2: float, method: str = "conduit") -> float:
    """Verilen kesit için nominal akım taşıma kapasitesini döner."""
    spec = COPPER_CABLE_SPECS.get(cross_section_mm2)
    if not spec:
        # En yakın küçük kesiti bul
        available = sorted(COPPER_CABLE_SPECS.keys())
        for s in reversed(available):
            if s <= cross_section_mm2:
                spec = COPPER_CABLE_SPECS[s]
                break
        if not spec:
            spec = COPPER_CABLE_SPECS[available[0]]
    return spec.get(method, spec["conduit"])


def get_temperature_factor(ambient_c: float = 30.0, insulation: str = "XLPE") -> float:
    """Ortam sıcaklığına göre düzeltme katsayısını döner."""
    table = TEMPERATURE_DERATING_XLPE if insulation.upper() in ("XLPE", "HFFR", "N2XH") else TEMPERATURE_DERATING_PVC
    temps = sorted(table.keys())
    if ambient_c <= temps[0]:
        return table[temps[0]]
    if ambient_c >= temps[-1]:
        return table[temps[-1]]
    # En yakın sıcaklığı eşle
    closest = min(temps, key=lambda t: abs(t - ambient_c))
    return table[closest]


def get_group_factor(number_of_cables: int = 1) -> float:
    """Yan yana giden kablo sayısına göre demetleme katsayısını döner."""
    if number_of_cables <= 1:
        return 1.0
    for count, factor in GROUP_DERATING_TABLE:
        if number_of_cables <= count:
            return factor
    return 0.38


def calculate_corrected_ampacity(
    cross_section_mm2: float,
    method: str = "conduit",
    ambient_c: float = 30.0,
    number_of_cables: int = 1,
    insulation: str = "XLPE"
) -> float:
    """
    TS HD 60364-5-52 tam düzeltilmiş akım taşıma kapasitesi:
    Iz = Iz0 * k_temp * k_group
    """
    iz0 = get_base_ampacity(cross_section_mm2, method)
    k_temp = get_temperature_factor(ambient_c, insulation)
    k_group = get_group_factor(number_of_cables)
    return round(iz0 * k_temp * k_group, 2)
