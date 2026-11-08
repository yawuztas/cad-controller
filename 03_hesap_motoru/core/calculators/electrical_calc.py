# -*- coding: utf-8 -*-
"""
Deterministik Mühendislik Hesap Motoru (ElectricalCalculators — FULL SÜRÜM)
===========================================================================
Bina ve Metro projeleri için 3 ana disiplindeki (Topraklama, Kuvvetli Akım,
Zayıf Akım) tüm resmi yönetmelik ve uluslararası standart formüllerini
%100 deterministik (sıfır AI tahmini) olarak çalıştırır.

Kapsanan Standartlar:
  1. TOPRAKLAMA (ETTMY Ek-N/Ek-P, TS HD 60364-5-54, TS HD 60364-4-41, IEEE Std 80-2013, TS EN 62305)
  2. KUVVETLİ AKIM (EİTY Md. 57, TS HD 60364-5-52, TS HD 60364-4-43, TS EN 60909, EPDK, TS EN 12464-1)
  3. ZAYIF AKIM (BYKHY Md. 74-84, TS EN 54-4/14/16, ISO/IEC 11801, TS EN 62676, TS EN 60728)
"""

from __future__ import annotations
import math
import re
from dataclasses import dataclass
from typing import Tuple, Optional, Dict, Any, List


# ==============================================================================
# SABİT TABLOLAR (TS HD 60364, ETTMY, TEDAŞ)
# ==============================================================================

# TS HD 60364-5-52 Bakır Kablo AC Direnç (R, Ω/km) ve Reaktans (X, Ω/km)
CABLE_IMPEDANCE_TABLE: Dict[float, Dict[str, float]] = {
    1.5:   {"r_20c": 12.10, "r_70c": 14.48, "r_90c": 15.43, "x": 0.100},
    2.5:   {"r_20c": 7.41,  "r_70c": 8.87,  "r_90c": 9.45,  "x": 0.090},
    4.0:   {"r_20c": 4.61,  "r_70c": 5.52,  "r_90c": 5.88,  "x": 0.085},
    6.0:   {"r_20c": 3.08,  "r_70c": 3.69,  "r_90c": 3.93,  "x": 0.082},
    10.0:  {"r_20c": 1.83,  "r_70c": 2.19,  "r_90c": 2.33,  "x": 0.082},
    16.0:  {"r_20c": 1.15,  "r_70c": 1.38,  "r_90c": 1.47,  "x": 0.082},
    25.0:  {"r_20c": 0.727, "r_70c": 0.870, "r_90c": 0.927, "x": 0.080},
    35.0:  {"r_20c": 0.524, "r_70c": 0.627, "r_90c": 0.668, "x": 0.079},
    50.0:  {"r_20c": 0.387, "r_70c": 0.463, "r_90c": 0.494, "x": 0.078},
    70.0:  {"r_20c": 0.268, "r_70c": 0.321, "r_90c": 0.342, "x": 0.075},
    95.0:  {"r_20c": 0.193, "r_70c": 0.231, "r_90c": 0.246, "x": 0.075},
    120.0: {"r_20c": 0.153, "r_70c": 0.183, "r_90c": 0.195, "x": 0.073},
    150.0: {"r_20c": 0.124, "r_70c": 0.148, "r_90c": 0.158, "x": 0.073},
    185.0: {"r_20c": 0.099, "r_70c": 0.118, "r_90c": 0.126, "x": 0.072},
    240.0: {"r_20c": 0.075, "r_70c": 0.090, "r_90c": 0.096, "x": 0.072},
    300.0: {"r_20c": 0.060, "r_70c": 0.072, "r_90c": 0.077, "x": 0.071},
}

# TS HD 60364-5-52 Tablo B.52.14 Ortam Sıcaklığı Düzeltme Katsayısı (k1)
TEMP_DERATING_PVC: Dict[int, float] = {
    10: 1.22, 15: 1.17, 20: 1.12, 25: 1.06, 30: 1.00,
    35: 0.94, 40: 0.87, 45: 0.79, 50: 0.71, 55: 0.61, 60: 0.50
}
TEMP_DERATING_XLPE: Dict[int, float] = {
    10: 1.15, 15: 1.12, 20: 1.08, 25: 1.04, 30: 1.00,
    35: 0.96, 40: 0.91, 45: 0.87, 50: 0.82, 55: 0.76, 60: 0.71
}

# TS HD 60364-5-52 Tablo B.52.17 Gruplama / Demetleme Katsayısı (k2)
GROUPING_DERATING_K2: List[Tuple[int, float]] = [
    (1, 1.00), (2, 0.80), (3, 0.70), (4, 0.65), (5, 0.60),
    (6, 0.57), (7, 0.54), (8, 0.52), (9, 0.50), (12, 0.45),
    (16, 0.41), (20, 0.38)
]

# ETTMY / IEEE 80 Paralel Topraklama Çubukları Etkileşim Verim Katsayısı (η)
ROD_COUPLING_ETA_TABLE: List[Tuple[int, float]] = [
    (1, 1.00), (2, 0.90), (3, 0.85), (4, 0.80), (5, 0.78),
    (6, 0.75), (8, 0.72), (10, 0.70), (12, 0.67), (16, 0.64), (20, 0.60)
]

# TEDAŞ / EMO Bina Çoklu Daire Eşzamanlılık (Diversite) Katsayısı Tablosu
BUILDING_COINCIDENCE_TABLE: List[Tuple[int, float]] = [
    (1, 1.00), (2, 0.90), (3, 0.80), (4, 0.70), (5, 0.60),
    (6, 0.55), (7, 0.50), (8, 0.48), (10, 0.45), (12, 0.42),
    (15, 0.40), (20, 0.37), (25, 0.35), (30, 0.33), (40, 0.30),
    (50, 0.27), (100, 0.25)
]


# ==============================================================================
# BÖLÜM 0: KABLO ETİKETİ AYRIŞTIRICI (PARSER)
# ==============================================================================

@dataclass
class CableConductorSpec:
    cores: int
    phase_mm2: float
    neutral_mm2: Optional[float]
    pe_mm2: Optional[float]
    is_pe_explicit: bool
    is_valid: bool
    raw_str: str


def parse_cable_spec(cross_sec_str: str) -> CableConductorSpec:
    """
    Kablo etiketinden iletken sayısını, faz kesitini (mm²), nötr ve PE kesitlerini açıkça çıkarır.
    Bilinmeyen veya tanımsız kesitlerde ASLA varsayım yapmaz (is_valid=False döner).
    """
    raw = str(cross_sec_str).strip()
    s = raw.replace(" ", "").replace(",", ".")
    if not s or s.upper() in ("KESİT BELİRTİLMEMİŞ", "YOK", "-", "UNKNOWN"):
        return CableConductorSpec(cores=0, phase_mm2=0.0, neutral_mm2=None, pe_mm2=None, is_pe_explicit=False, is_valid=False, raw_str=raw)

    # 1. 3x50+25 veya 3x50+35
    m_plus = re.search(r"(\d+)\s*[xX*]\s*(\d+(?:\.\d+)?)\s*\+\s*(\d+(?:\.\d+)?)", s)
    if m_plus:
        cnt = int(m_plus.group(1)) + 1
        ph = float(m_plus.group(2))
        pe_n = float(m_plus.group(3))
        return CableConductorSpec(cores=cnt, phase_mm2=ph, neutral_mm2=pe_n, pe_mm2=pe_n, is_pe_explicit=True, is_valid=True, raw_str=raw)

    # 2. 3(1x185)+1x95 (Açık PE topraklama iletkenli paralel besleme)
    m_par = re.search(r"(\d+)\s*\(\s*1\s*[xX*]\s*(\d+(?:\.\d+)?)\s*\)\s*\+\s*1\s*[xX*]\s*(\d+(?:\.\d+)?)", s)
    if m_par:
        cnt = int(m_par.group(1)) + 1
        ph = float(m_par.group(2))
        pe = float(m_par.group(3))
        return CableConductorSpec(cores=cnt, phase_mm2=ph, neutral_mm2=None, pe_mm2=pe, is_pe_explicit=True, is_valid=True, raw_str=raw)

    # 3. 3x50/25 (Konsantrik nötr/PE iletkenli)
    m_slash = re.search(r"(\d+)\s*[xX*]\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", s)
    if m_slash:
        cnt = int(m_slash.group(1)) + 1
        ph = float(m_slash.group(2))
        pe_n = float(m_slash.group(3))
        return CableConductorSpec(cores=cnt, phase_mm2=ph, neutral_mm2=pe_n, pe_mm2=pe_n, is_pe_explicit=True, is_valid=True, raw_str=raw)

    # 4. Standart çok damarlı kablolar (5x6, 4x4, 3x2.5, 3x50, 1x120 vb.)
    m_std = re.search(r"(\d+)\s*[xX*]\s*(\d+(?:\.\d+)?)", s)
    if m_std:
        cnt = int(m_std.group(1))
        sec = float(m_std.group(2))
        if cnt == 5:
            return CableConductorSpec(cores=5, phase_mm2=sec, neutral_mm2=sec, pe_mm2=sec, is_pe_explicit=True, is_valid=True, raw_str=raw)
        elif cnt == 4:
            return CableConductorSpec(cores=4, phase_mm2=sec, neutral_mm2=sec, pe_mm2=None, is_pe_explicit=False, is_valid=True, raw_str=raw)
        elif cnt == 3:
            if sec <= 6.0:
                return CableConductorSpec(cores=3, phase_mm2=sec, neutral_mm2=sec, pe_mm2=sec, is_pe_explicit=True, is_valid=True, raw_str=raw)
            else:
                return CableConductorSpec(cores=3, phase_mm2=sec, neutral_mm2=None, pe_mm2=None, is_pe_explicit=False, is_valid=True, raw_str=raw)
        elif cnt == 1:
            return CableConductorSpec(cores=1, phase_mm2=sec, neutral_mm2=None, pe_mm2=None, is_pe_explicit=False, is_valid=True, raw_str=raw)

    return CableConductorSpec(cores=0, phase_mm2=0.0, neutral_mm2=None, pe_mm2=None, is_pe_explicit=False, is_valid=False, raw_str=raw)


def parse_cross_section_mm2(cross_sec_str: str) -> Tuple[int, float, Optional[float]]:
    """
    Geriye dönük uyumluluk sarmalayıcısı:
    (cores, phase_mm2, pe_or_n_mm2) döner. Bilinmeyen kesitlerde (0, 0.0, None) döner.
    """
    spec = parse_cable_spec(cross_sec_str)
    if not spec.is_valid:
        return (0, 0.0, None)
    pe_or_n = spec.pe_mm2 if spec.pe_mm2 is not None else spec.neutral_mm2
    return (spec.cores, spec.phase_mm2, pe_or_n)


# ==============================================================================
# BÖLÜM 1: TOPRAKLAMA VE YILDIRIMDAN KORUNMA HESAPLARI
# (ETTMY Ek-N/Ek-P, TS HD 60364-5-54, TS HD 60364-4-41, IEEE Std 80, TS EN 62305)
# ==============================================================================

def get_rod_coupling_eta(n_rods: int) -> float:
    """Paralel çubuk sayısına göre karşılıklı etkileşim verim katsayısını (η) döner."""
    if n_rods <= 1:
        return 1.00
    for count, eta in ROD_COUPLING_ETA_TABLE:
        if n_rods <= count:
            return eta
    return 0.60


def calc_vertical_rod_resistance_dwight(
    rho_ohm_m: float,
    rod_length_m: float,
    rod_diameter_m: float = 0.02,
    n_rods: int = 1,
    use_exact_dwight: bool = False,
) -> float:
    """
    Dikey topraklama kazığı (çubuğu) yayılma direnci — Dwight / ETTMY Ek-P Formülü:
      - Klasik ETTMY: R_c1 = (ρ / (2πL)) * ln(4L / d)
      - Tam Dwight:   R_c1 = (ρ / (2πL)) * (ln(8L / d) - 1)
      - Grup Direnci: R_cn = R_c1 / (n * η)
    """
    if rho_ohm_m <= 0 or rod_length_m <= 0 or rod_diameter_m <= 0 or n_rods <= 0:
        return 0.0
    if use_exact_dwight:
        r_one = (rho_ohm_m / (2.0 * math.pi * rod_length_m)) * (math.log((8.0 * rod_length_m) / rod_diameter_m) - 1.0)
    else:
        r_one = (rho_ohm_m / (2.0 * math.pi * rod_length_m)) * math.log((4.0 * rod_length_m) / rod_diameter_m)
    eta = get_rod_coupling_eta(n_rods)
    return round(max(0.001, r_one / (n_rods * eta)), 4)


def calc_horizontal_strip_resistance_dwight(
    rho_ohm_m: float,
    strip_length_m: float,
    equiv_diameter_m: float = 0.015,
    depth_h_m: float = 1.0,
) -> float:
    """
    Yatay gömülü şerit / çevre iletkeni yayılma direnci — Dwight / ETTMY Ek-P:
      R_şerit = (ρ / (2πL)) * (ln(2L² / (d * h)) - 1)
    """
    if rho_ohm_m <= 0 or strip_length_m <= 0 or equiv_diameter_m <= 0 or depth_h_m <= 0:
        return 0.0
    inner = (2.0 * (strip_length_m ** 2)) / (equiv_diameter_m * depth_h_m)
    if inner <= math.e:
        r_val = (rho_ohm_m / (2.0 * math.pi * strip_length_m)) * math.log((2.0 * strip_length_m) / equiv_diameter_m)
    else:
        r_val = (rho_ohm_m / (2.0 * math.pi * strip_length_m)) * (math.log(inner) - 1.0)
    return round(max(0.001, r_val), 4)


def calc_foundation_earthing_laurent_niemann(
    rho_ohm_m: float,
    building_area_m2: float,
    total_strip_length_m: float,
    n_rods: int = 0,
    rod_length_m: float = 1.5,
    rod_diameter_m: float = 0.02,
) -> Dict[str, float]:
    """
    ETTMY Ek-N & EMO Laurent-Niemann Temel Topraklayıcı + Schwarz Kuplaj Hesabı:
      1. Eşdeğer Daire Çapı: D = 2 * √(A / π)
      2. Temel Izgara Direnci: R_temel = (ρ / (2D)) + (ρ / L)
      3. Kazık Grubu Direnci: R_çubuk = R_c1 / (n * η)
      4. Schwarz Kuplajlı Bileşke: R_e = (R_temel * R_çubuk - R_m²) / (R_temel + R_çubuk - 2*R_m)
    """
    if rho_ohm_m <= 0 or building_area_m2 <= 0 or total_strip_length_m <= 0:
        return {"D_m": 0.0, "R_temel_ohm": 0.0, "R_rods_ohm": 0.0, "R_combined_ohm": 0.0}

    d_eq = 2.0 * math.sqrt(building_area_m2 / math.pi)
    r_temel = (rho_ohm_m / (2.0 * d_eq)) + (rho_ohm_m / total_strip_length_m)

    if n_rods > 0 and rod_length_m > 0:
        r_rods = calc_vertical_rod_resistance_dwight(rho_ohm_m, rod_length_m, rod_diameter_m, n_rods)
        r_m = 0.33 * r_temel
        denom = r_temel + r_rods - (2.0 * r_m)
        if denom > 0:
            r_comb = ((r_temel * r_rods) - (r_m ** 2)) / denom
        else:
            r_comb = (r_temel * r_rods) / (r_temel + r_rods)
    else:
        r_rods = 0.0
        r_comb = r_temel

    return {
        "D_m": round(d_eq, 2),
        "R_temel_ohm": round(r_temel, 4),
        "R_rods_ohm": round(r_rods, 4),
        "R_combined_ohm": round(max(0.01, r_comb), 4),
    }


def calc_foundation_earthing_ieee80_sverak(
    rho_ohm_m: float,
    building_area_m2: float,
    total_strip_length_m: float,
    n_rods: int = 4,
    rod_length_m: float = 1.5,
    depth_h_m: float = 1.0,
) -> float:
    """
    IEEE Std 80-2013 Sverak Formülü (Temel ızgara + köşe çubukları + gömülme derinliği):
      L_T = L_şerit + n * L_çubuk
      R_g = ρ * [ 1/L_T + (1 / √(20*A)) * (1 + 1 / (1 + h * √(20/A))) ]
    """
    if rho_ohm_m <= 0 or building_area_m2 <= 0 or total_strip_length_m <= 0:
        return 0.0
    l_total = total_strip_length_m + max(0, n_rods) * max(0.0, rod_length_m)
    term_len = 1.0 / l_total
    sqrt_20a = math.sqrt(20.0 * building_area_m2)
    depth_factor = 1.0 / (1.0 + depth_h_m * math.sqrt(20.0 / building_area_m2))
    term_area = (1.0 / sqrt_20a) * (1.0 + depth_factor)
    return round(rho_ohm_m * (term_len + term_area), 4)


def check_pe_cross_section_iec60364_5_54(phase_mm2: float, pe_mm2: float) -> Tuple[bool, float, str]:
    """
    TS HD 60364-5-54 Çizelge 54.2 uyarınca koruma iletkeni (PE) geometrik kesit kontrolü:
      - S_faz <= 16 mm²      => S_PE >= S_faz
      - 16 < S_faz <= 35 mm² => S_PE >= 16 mm²
      - S_faz > 35 mm²       => S_PE >= S_faz / 2
    """
    if phase_mm2 <= 16.0:
        req_pe = phase_mm2
    elif phase_mm2 <= 35.0:
        req_pe = 16.0
    else:
        req_pe = round(phase_mm2 / 2.0, 1)

    is_compliant = pe_mm2 >= req_pe
    explanation = f"S_faz = {phase_mm2} mm² için TS HD 60364-5-54 min S_PE = {req_pe} mm²; Mevcut = {pe_mm2} mm²"
    return is_compliant, req_pe, explanation


def calc_adiabatic_pe_min_mm2(
    fault_current_a: float,
    disconnection_time_s: float = 0.4,
    k_material: float = 143.0,
) -> float:
    """
    TS HD 60364-5-54 Madde 543.1.1 Tam Adyabatik Koruma İletkeni Kesit Formülü (t <= 5 s):
      S_PE_min = √(I_k² * t) / k = (I_k * √t) / k
    Varsayılan k = 143.0 (XLPE/HFFR bakır veya ayrı PVC bakır); kablo içi PVC bakır için k = 115.0.
    """
    if fault_current_a <= 0 or disconnection_time_s <= 0 or k_material <= 0:
        return 0.0
    s_min = (fault_current_a * math.sqrt(disconnection_time_s)) / k_material
    return round(s_min, 2)


def check_fault_loop_and_touch_voltage(
    system_type: str,
    loop_or_earth_ohm: float,
    protection_rating_or_ideltan_a: float,
    mcb_curve: str = "C",
    u0_v: float = 230.0,
    max_touch_v: float = 50.0,
) -> Dict[str, Any]:
    """
    TS HD 60364-4-41 Dolaylı Temasa Karşı Koruma (TN Çevrim Empedansı & TT Dokunma Gerilimi):
      - TN Sistemi (Md. 411.4.4): Z_s * I_a <= U_0 (B eğrisi Ia=5*In, C eğrisi Ia=10*In, D eğrisi Ia=20*In)
      - TT Sistemi (Md. 411.5.3): R_A * I_Δn <= 50 V
    """
    sys_u = system_type.strip().upper()
    if sys_u.startswith("TT"):
        touch_v = loop_or_earth_ohm * protection_rating_or_ideltan_a
        max_ra = max_touch_v / protection_rating_or_ideltan_a if protection_rating_or_ideltan_a > 0 else 0.0
        ok = touch_v <= max_touch_v
        return {
            "system": "TT",
            "is_compliant": ok,
            "touch_voltage_v": round(touch_v, 2),
            "max_allowed_ohm": round(max_ra, 2),
            "measured_ohm": round(loop_or_earth_ohm, 4),
            "formula": f"R_A ({loop_or_earth_ohm:.2f} Ω) * I_Δn ({protection_rating_or_ideltan_a} A) = {touch_v:.2f} V <= {max_touch_v} V",
        }
    else:
        mult = {"B": 5.0, "C": 10.0, "D": 20.0}.get(mcb_curve.strip().upper(), 10.0)
        ia = mult * protection_rating_or_ideltan_a
        max_zs = u0_v / ia if ia > 0 else 0.0
        ok = loop_or_earth_ohm <= max_zs
        return {
            "system": "TN",
            "is_compliant": ok,
            "trip_current_ia_a": round(ia, 1),
            "max_allowed_ohm": round(max_zs, 4),
            "measured_ohm": round(loop_or_earth_ohm, 4),
            "formula": f"Z_s ({loop_or_earth_ohm:.4f} Ω) * I_a ({ia:.0f} A) = {loop_or_earth_ohm * ia:.1f} V <= U_0 ({u0_v:.0f} V)",
        }


def calc_lps_separation_distance_m(
    height_length_m: float,
    lps_class: int = 3,
    kc_current_sharing: float = 0.5,
    km_insulation: float = 0.5,
) -> float:
    """
    TS EN 62305-3 Madde 6.3 Yıldırımdan Korunma Ayırma Mesafesi (s) Formülü:
      s = (k_i * k_c / k_m) * l
      k_i: Sınıf I=0.08, Sınıf II=0.06, Sınıf III ve IV=0.04
      k_m: Hava=1.0, Beton/Tuğla=0.5
    """
    if height_length_m <= 0 or km_insulation <= 0:
        return 0.0
    ki_map = {1: 0.08, 2: 0.06, 3: 0.04, 4: 0.04}
    ki = ki_map.get(lps_class, 0.04)
    s_m = (ki * kc_current_sharing / km_insulation) * height_length_m
    return round(s_m, 3)


# ==============================================================================
# BÖLÜM 2: KUVVETLİ AKIM HESAPLARI
# (EİTY Md. 57, TS HD 60364-5-52, TS HD 60364-4-43, TS EN 60909, EPDK, TS EN 12464-1)
# ==============================================================================

def calc_operating_current_ib(
    power_w: float, voltage_v: int = 230, cos_phi: float = 0.95, is_3phase: bool = False
) -> float:
    """
    İşletme akımını (Ib) hesaplar:
      - 1 Faz (230V): Ib = P / (U * cosφ)
      - 3 Faz (400V): Ib = P / (√3 * U * cosφ)
    """
    if power_w <= 0.0 or voltage_v <= 0 or cos_phi <= 0:
        return 0.0
    if is_3phase:
        return round(power_w / (math.sqrt(3.0) * voltage_v * cos_phi), 2)
    return round(power_w / (voltage_v * cos_phi), 2)


def calc_effective_circuit_length(
    total_length_m: float, fixture_count: int, is_mech_or_direct: bool = False, is_building: bool = False
) -> float:
    """
    Dağıtılı yüklerde eşdeğer moment kablo boyunu hesaplar.
    Aydınlatma ve priz linyelerinde ilk noktaya kadar tam akım,
    sonraki armatürler arasında ise ~0.55 yayılı yük moment katsayısı uygulanır.
    """
    if is_mech_or_direct or fixture_count <= 1:
        return round(total_length_m, 2)

    base_drop_m = 8.0 if is_building else 15.0
    span_len = max(total_length_m - base_drop_m, 0.0)
    eff = base_drop_m + (0.55 * span_len)
    return round(eff, 2)


def calc_voltage_drop_pct(
    power_w: float,
    effective_length_m: float,
    cond_mm2: float,
    voltage_v: int = 230,
    conductivity: float = 56.0,
    is_3phase: bool = False,
) -> float:
    """
    Klasik Omik Yüzde Gerilim Düşümünü (%e — EİTY Md. 57) hesaplar:
      - 1 Faz: %e = (200 * L * P) / (κ * S * U²)
      - 3 Faz: %e = (100 * L * P) / (κ * S * U²)
    """
    if power_w <= 0.0 or cond_mm2 <= 0.0 or voltage_v <= 0 or conductivity <= 0:
        return 0.0
    factor = 1.0 if is_3phase else 2.0
    vd = (factor * effective_length_m * power_w) / (conductivity * cond_mm2 * (voltage_v ** 2)) * 100.0
    return round(vd, 2)


def calc_voltage_drop_exact_iec_pct(
    current_ib_a: float,
    length_m: float,
    cond_mm2: float,
    cos_phi: float = 0.90,
    is_3phase: bool = True,
    insulation: str = "XLPE",
    n_parallel: int = 1,
) -> Tuple[float, float]:
    """
    TS HD 60364-5-52 Ek-G Tam Empedanslı (Reaktans Dahil) Gerilim Düşümü Hesabı:
      ΔU = b * I_b * (L / 1000) * (R_km * cosφ + X_km * sinφ) / n_parallel
      %e = (ΔU / U_n) * 100
      b = √3 (3 faz, Un=400V) veya b = 2 (1 faz, Un=230V)
    Döner: (delta_u_volts, vdrop_pct)
    """
    if current_ib_a <= 0 or length_m <= 0 or cond_mm2 <= 0 or n_parallel <= 0:
        return (0.0, 0.0)

    # En yakın kesit empedansını al veya analitik hesapla
    spec = CABLE_IMPEDANCE_TABLE.get(cond_mm2)
    ins_u = insulation.strip().upper()
    if spec:
        r_km = spec["r_90c"] if ins_u in ("XLPE", "EPR", "HFFR", "N2XH") else spec["r_70c"]
        x_km = spec["x"]
    else:
        kappa = 44.0 if ins_u in ("XLPE", "EPR", "HFFR", "N2XH") else 46.8
        r_km = 1000.0 / (kappa * cond_mm2)
        x_km = 0.080

    cos_p = max(0.1, min(1.0, cos_phi))
    sin_p = math.sqrt(max(0.0, 1.0 - (cos_p ** 2)))
    b_factor = math.sqrt(3.0) if is_3phase else 2.0
    u_nom = 400.0 if is_3phase else 230.0

    delta_u = b_factor * current_ib_a * (length_m / 1000.0) * ((r_km * cos_p) + (x_km * sin_p)) / n_parallel
    vdrop_pct = (delta_u / u_nom) * 100.0
    return (round(delta_u, 3), round(vdrop_pct, 2))


def calc_derated_ampacity_iz(
    base_ampacity_iz0: float,
    ambient_temp_c: float = 30.0,
    grouped_circuits: int = 1,
    insulation: str = "XLPE",
) -> Tuple[float, float, float]:
    """
    TS HD 60364-5-52 Düzeltilmiş Akım Taşıma Kapasitesi (Iz):
      I_z = I_z0 * k_1 (sıcaklık) * k_2 (gruplama)
    Döner: (iz_corrected, k1_temp, k2_group)
    """
    if base_ampacity_iz0 <= 0:
        return (0.0, 1.0, 1.0)

    table = TEMP_DERATING_XLPE if insulation.strip().upper() in ("XLPE", "EPR", "HFFR", "N2XH") else TEMP_DERATING_PVC
    temps = sorted(table.keys())
    closest_t = min(temps, key=lambda t: abs(t - ambient_temp_c))
    k1 = table[closest_t]

    k2 = 0.38
    if grouped_circuits <= 1:
        k2 = 1.00
    else:
        for cnt, factor in GROUPING_DERATING_K2:
            if grouped_circuits <= cnt:
                k2 = factor
                break

    iz = round(base_ampacity_iz0 * k1 * k2, 2)
    return (iz, k1, k2)


def calc_dwelling_demand_power_w(installed_power_w: float) -> float:
    """
    EİTY Madde 57 / BEDAŞ Tekil Konut (Daire) Talep Gücü Kuralı:
      - İlk 8.000 W'lık kısmın %60'ı (4.800 W)
      - 8.000 W'ı aşan kısmın %40'ı
    """
    if installed_power_w <= 0:
        return 0.0
    if installed_power_w <= 8000.0:
        return round(installed_power_w * 0.60, 1)
    return round(4800.0 + (installed_power_w - 8000.0) * 0.40, 1)


def get_building_coincidence_factor(apartment_count: int) -> float:
    """TEDAŞ / EMO bina daire sayısına göre eşzamanlılık (diversite) katsayısını döner."""
    if apartment_count <= 1:
        return 1.00
    for cnt, factor in BUILDING_COINCIDENCE_TABLE:
        if apartment_count <= cnt:
            return factor
    return 0.25


def calc_phase_imbalance_pct(l1_w: float, l2_w: float, l3_w: float) -> float:
    """
    Üç faz arasındaki dengesizlik yüzdesini (%Δ) hesaplar:
      %Δ = (Maks Faz Yükü - Min Faz Yükü) / Ortalama Faz Yükü * 100
    """
    phases = [l1_w, l2_w, l3_w]
    tot_w = sum(phases)
    if tot_w <= 0.0:
        return 0.0
    avg_w = tot_w / 3.0
    return round(((max(phases) - min(phases)) / avg_w) * 100.0, 1)


def calc_neutral_current_3phase(ir_a: float, is_a: float, it_a: float) -> float:
    """
    120° faz farkı ile 3 fazlı sistemde vektörel Nötr Akımını (I_N) hesaplar:
      I_N = √(I_R² + I_S² + I_T² - (I_R*I_S + I_S*I_T + I_T*I_R))
    """
    in_sq = (ir_a ** 2) + (is_a ** 2) + (it_a ** 2) - (ir_a * is_a + is_a * it_a + it_a * ir_a)
    return round(math.sqrt(max(0.0, in_sq)), 2)


def calc_short_circuit_iec60909(
    length_m: float,
    cond_mm2: float,
    r_upstream_ohm: float = 0.0025,
    x_upstream_ohm: float = 0.0148,
    disconnection_time_s: float = 0.04,
    k_material: float = 143.0,
) -> Dict[str, float]:
    """
    TS EN 60909-0 & TS HD 60364-4-43 Kısa Devre (I_k3max, I_k1min) ve Termik Dayanım Hesabı:
      - Z_kablo = √(R_kablo² + X_kablo²)
      - I_k3_max = (1.05 * 400) / (√3 * Z_toplam)
      - I_k1_min = (0.95 * 230) / √((2 * R_top)² + (2 * X_top)²)
      - S_min_termik = (I_k3_max * √t) / k
    """
    if length_m <= 0 or cond_mm2 <= 0:
        return {"ik3_max_ka": 0.0, "ik1_min_ka": 0.0, "z_total_ohm": 0.0, "s_min_thermal_mm2": 0.0}

    spec = CABLE_IMPEDANCE_TABLE.get(cond_mm2)
    r_20 = (spec["r_20c"] * length_m / 1000.0) if spec else (0.0178 * length_m / cond_mm2)
    r_hot = r_20 * 1.25  # Kısa devre sıcaklığında omik direnç artışı (IEC 60909)
    x_line = ((spec["x"] if spec else 0.080) * length_m / 1000.0)

    r_tot_max = r_upstream_ohm + r_20
    x_tot = x_upstream_ohm + x_line
    z_tot_max = math.sqrt((r_tot_max ** 2) + (x_tot ** 2))

    r_tot_min = r_upstream_ohm + r_hot
    z_loop_min = math.sqrt(((2.0 * r_tot_min) ** 2) + ((2.0 * x_tot) ** 2))

    ik3_a = (1.05 * 400.0) / (math.sqrt(3.0) * z_tot_max) if z_tot_max > 0 else 0.0
    ik1_a = (0.95 * 230.0) / z_loop_min if z_loop_min > 0 else 0.0
    s_min = (ik3_a * math.sqrt(disconnection_time_s)) / k_material if k_material > 0 else 0.0

    return {
        "ik3_max_ka": round(ik3_a / 1000.0, 2),
        "ik1_min_ka": round(ik1_a / 1000.0, 2),
        "z_total_ohm": round(z_tot_max, 5),
        "s_min_thermal_mm2": round(s_min, 2),
    }


def calc_compensation_capacitor_kvar(
    active_power_kw: float,
    initial_cos_phi: float = 0.80,
    target_cos_phi: float = 0.98,
) -> float:
    """
    EPDK Reaktif Güç Sınırlarına Uygun Kompanzasyon Kondansatör Gücü (Q_c) Hesabı:
      Q_c = P * (tan(arccos(cosφ₁)) - tan(arccos(cosφ₂)))   [kVAr]
    """
    if active_power_kw <= 0 or initial_cos_phi <= 0 or target_cos_phi <= initial_cos_phi:
        return 0.0
    phi_1 = math.acos(min(1.0, max(0.1, initial_cos_phi)))
    phi_2 = math.acos(min(1.0, max(0.1, target_cos_phi)))
    q_kvar = active_power_kw * (math.tan(phi_1) - math.tan(phi_2))
    return round(max(0.0, q_kvar), 2)


def calc_illumination_lumen_method(
    room_width_m: float,
    room_length_m: float,
    mounting_height_hm_m: float,
    target_lux: float = 300.0,
    luminaire_flux_lm: float = 3600.0,
    utilization_factor_u: float = 0.65,
    maintenance_factor_mf: float = 0.80,
) -> Dict[str, Any]:
    """
    TS EN 12464-1 Aydınlatma Lümen Yöntemi Hesabı:
      - Oda İndeksi: K = (a * b) / (h_m * (a + b))
      - Toplam Işık Akısı: Φ_toplam = (E * A) / (η_u * MF)
      - Armatür Sayısı: N = ceil(Φ_toplam / Φ_armatür)
    """
    if room_width_m <= 0 or room_length_m <= 0 or mounting_height_hm_m <= 0 or luminaire_flux_lm <= 0:
        return {"area_m2": 0.0, "room_index_k": 0.0, "total_flux_lm": 0.0, "fixture_count": 0, "achieved_lux": 0.0}

    area = room_width_m * room_length_m
    k_idx = area / (mounting_height_hm_m * (room_width_m + room_length_m))
    tot_flux = (target_lux * area) / (utilization_factor_u * maintenance_factor_mf)
    n_fix = math.ceil(tot_flux / luminaire_flux_lm)
    achieved_e = (n_fix * luminaire_flux_lm * utilization_factor_u * maintenance_factor_mf) / area

    return {
        "area_m2": round(area, 2),
        "room_index_k": round(k_idx, 2),
        "total_flux_lm": round(tot_flux, 1),
        "fixture_count": int(n_fix),
        "achieved_lux": round(achieved_e, 1),
    }


def check_breaker_selectivity(
    upstream_rating_a: float,
    downstream_rating_a: float,
    upstream_curve: str = "C",
    downstream_curve: str = "C",
    upstream_icn_ka: Optional[float] = None,
    downstream_icn_ka: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Kesiciler Arası Aşırı Akım ve Karakteristik Seçicilik (Selektivite) Kontrolü (IEC 60947-2 / TS HD 60364-5-53):
      1. Anma Akımı Hiyerarşisi: I_n,üst > I_n,alt (Ters kademelendirme yasağı)
      2. Amperometrik Seçicilik Oranı: I_n,üst / I_n,alt >= 1.6 (Tam/kısmi aşırı yük seçicilik eşiği)
      3. Açma Eğrisi Koordinasyonu: Üstteki kesici alttakinden daha hızlı bir eğriye sahip olamaz
         (Örn: Üst B, Alt C/D tipi ise alt hattaki ani demeraj üst ana kesiciyi gereksiz açtırır!)
      4. Kesme Kapasitesi Hiyerarşisi: I_cn,üst >= I_cn,alt
    """
    issues: List[str] = []
    ratio = round(upstream_rating_a / downstream_rating_a, 2) if downstream_rating_a > 0 else 0.0

    # 1. Ters Kademelendirme Kontrolü
    if downstream_rating_a >= upstream_rating_a:
        issues.append(
            f"KRİTİK TERS KADEMELENDİRME: Alt kademe kesici ({downstream_rating_a:.0f}A), "
            f"üst kademe kesiciden ({upstream_rating_a:.0f}A) büyük veya eşittir! Alt hattaki yük üst şalteri açtırır."
        )

    # 2. Amperometrik Seçicilik Oranı (En az 1.6 kat kuralı)
    elif ratio < 1.60:
        issues.append(
            f"SEÇİCİLİK RİSKİ: Üst/Alt kesici anma akımı oranı {ratio:.2f} < 1.60'tır. "
            f"Aşırı yük veya orta ölçekli arızalarda üst kesici ({upstream_rating_a:.0f}A) de açarak diğer devreleri karartabilir."
        )

    # 3. Açma Eğrisi Koordinasyonu (B, C, D)
    curve_speed = {"B": 1, "C": 2, "D": 3}
    u_spd = curve_speed.get(upstream_curve.strip().upper(), 2)
    d_spd = curve_speed.get(downstream_curve.strip().upper(), 2)
    if u_spd < d_spd:
        issues.append(
            f"EĞRİ UYUMSUZLUĞU: Üst kesici '{upstream_curve.upper()}' eğrili (daha hızlı), "
            f"alt kesici '{downstream_curve.upper()}' eğrili (daha yavaş)! "
            f"Alt devredeki demeraj akımında üstteki ana kesici erken açacaktır."
        )

    # 4. Kesme Kapasitesi Hiyerarşisi
    if upstream_icn_ka is not None and downstream_icn_ka is not None:
        if upstream_icn_ka < downstream_icn_ka:
            issues.append(
                f"KESME KAPASİTESİ ÇELİŞKİSİ: Üst kesici kapasitesi ({upstream_icn_ka:.0f} kA), "
                f"alt kesiciden ({downstream_icn_ka:.0f} kA) düşüktür."
            )

    is_compliant = len(issues) == 0
    status = "TAM SEÇİCİ" if is_compliant else ("UYARI" if ratio >= 1.25 and downstream_rating_a < upstream_rating_a else "KORUMA SIRALAMA HATASI")

    return {
        "is_compliant": is_compliant,
        "status": status,
        "current_ratio": ratio,
        "upstream_rating_a": upstream_rating_a,
        "downstream_rating_a": downstream_rating_a,
        "upstream_curve": upstream_curve.upper(),
        "downstream_curve": downstream_curve.upper(),
        "issues": issues,
    }


def check_rcd_selectivity(
    upstream_ideltan_ma: float,
    downstream_ideltan_ma: float,
    is_upstream_selective_s_type: bool = True,
) -> Dict[str, Any]:
    """
    Kaçak Akım Koruma Röleleri (KAKR / RCD) Seçicilik Kontrolü (TS HD 60364-5-53):
      1. Akım Kademelendirmesi: I_Δn,üst >= 3 * I_Δn,alt (Örn: 300 mA ana pano, 30 mA linye/tali pano)
      2. Zaman Kademelendirmesi: Üstteki RCD mutlaka S (Selektif / Gecikmeli) tip olmalıdır (Δt >= 40 ms).
         Aksi halde, her iki RCD de ani açma yapar ve alt hattaki gövde kaçağında tüm bina kararır!
    """
    issues: List[str] = []

    # Akım oranı kontrolü
    if downstream_ideltan_ma >= upstream_ideltan_ma:
        issues.append(
            f"KRİTİK KAKR KADEMELENDİRME HATASI: Alt KAKR ({downstream_ideltan_ma:.0f} mA) >= "
            f"Üst KAKR ({upstream_ideltan_ma:.0f} mA)! Alt ve üst röleler ters bağlanmış."
        )
    elif upstream_ideltan_ma < (3.0 * downstream_ideltan_ma):
        issues.append(
            f"KAKR SEÇİCİLİK RİSKİ: Üst KAKR ({upstream_ideltan_ma:.0f} mA), alt KAKR'ın ({downstream_ideltan_ma:.0f} mA) "
            f"en az 3 katı olmalıdır (I_Δn,üst >= 3*I_Δn,alt kuralı ihlali)."
        )

    # Zaman gecikmesi (S-tipi) kontrolü
    if not is_upstream_selective_s_type:
        issues.append(
            "ZAMAN SEÇİCİLİĞİ EKSİK: Üst KAKR 'S' (Selektif/Gecikmeli) tip olarak tanımlanmamış! "
            "Ani kaçakta 30 mA röle ile birlikte 300 mA ana röle de açarak tüm binayı enerjisiz bırakır."
        )

    is_compliant = len(issues) == 0
    return {
        "is_compliant": is_compliant,
        "status": "SEÇİCİ RCD KORUMASI" if is_compliant else "RCD SEÇİCİLİK HATASI",
        "upstream_ideltan_ma": upstream_ideltan_ma,
        "downstream_ideltan_ma": downstream_ideltan_ma,
        "is_upstream_selective_s_type": is_upstream_selective_s_type,
        "issues": issues,
    }


def check_single_line_hierarchy_chain(
    feeders_chain: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Tek hat şemasında kaynaktan en uç linye noktasına kadar kesicilerin baştan sona
    doğru sıralanıp sıralanmadığını (monotonik hiyerarşi ve kademelendirme) denetler.

    Girdi:
      feeders_chain = [
        {"name": "TRAFO/ANA ŞALTER", "rating_a": 400.0, "curve": "D", "icn_ka": 36.0, "rcd_ma": 300.0, "rcd_s": True},
        {"name": "TD-1 TALİ DAĞITIM", "rating_a": 160.0, "curve": "C", "icn_ka": 25.0},
        {"name": "KAT PANOSU GİRİŞ",  "rating_a": 63.0,  "curve": "C", "icn_ka": 10.0},
        {"name": "LİNYE ÇIKIŞ (PRİZ)", "rating_a": 16.0,  "curve": "C", "icn_ka": 6.0,  "rcd_ma": 30.0,  "rcd_s": False},
      ]
    """
    chain_findings: List[Dict[str, Any]] = []
    has_critical_error = False

    for i in range(len(feeders_chain) - 1):
        parent = feeders_chain[i]
        child = feeders_chain[i + 1]

        # Aşırı akım kesici seçiciliği
        mcb_res = check_breaker_selectivity(
            upstream_rating_a=parent.get("rating_a", 0.0),
            downstream_rating_a=child.get("rating_a", 0.0),
            upstream_curve=parent.get("curve", "C"),
            downstream_curve=child.get("curve", "C"),
            upstream_icn_ka=parent.get("icn_ka"),
            downstream_icn_ka=child.get("icn_ka"),
        )

        step_info: Dict[str, Any] = {
            "step": f"{parent.get('name', 'Üst')} -> {child.get('name', 'Alt')}",
            "mcb_selectivity": mcb_res,
            "rcd_selectivity": None,
        }

        if not mcb_res["is_compliant"]:
            if "KRİTİK" in " ".join(mcb_res["issues"]):
                has_critical_error = True

        # RCD seçiciliği (Her ikisinde de RCD tanımlıysa)
        p_rcd = parent.get("rcd_ma")
        c_rcd = child.get("rcd_ma")
        if p_rcd is not None and c_rcd is not None:
            rcd_res = check_rcd_selectivity(
                upstream_ideltan_ma=p_rcd,
                downstream_ideltan_ma=c_rcd,
                is_upstream_selective_s_type=parent.get("rcd_s", True),
            )
            step_info["rcd_selectivity"] = rcd_res
            if not rcd_res["is_compliant"]:
                has_critical_error = True

        chain_findings.append(step_info)

    return {
        "total_levels": len(feeders_chain),
        "chain_valid": not has_critical_error,
        "overall_status": "DOĞRU SIRALANMIŞ (HİYERARŞİK SEÇİCİLİK UYGUN)" if not has_critical_error else "KESİCİ SIRALAMASINDA HATA VAR",
        "steps": chain_findings,
    }


# ==============================================================================
# BÖLÜM 3: ZAYIF AKIM HESAPLARI
# (BYKHY, TS EN 54-4/14/16, ISO/IEC 11801, TS EN 62676, TS EN 60728)
# ==============================================================================

def calc_fire_alarm_battery_capacity_ah(
    quiescent_current_a: float,
    alarm_current_a: float,
    standby_hours: float = 24.0,
    alarm_hours: float = 0.5,
    aging_factor_k: float = 1.25,
) -> float:
    """
    TS EN 54-4 & TS EN 54-14 Madde 6.8 Yangın İhbar Santrali Akü Kapasite Formülü:
      C_Ah = k * ((I_sükunet * T_bekleme) + (I_alarm * T_alarm))
    """
    if quiescent_current_a < 0 or alarm_current_a < 0:
        return 0.0
    cap_ah = aging_factor_k * ((quiescent_current_a * standby_hours) + (alarm_current_a * alarm_hours))
    return round(cap_ah, 2)


def calc_fire_loop_voltage_drop_v(
    loop_length_m: float,
    loop_alarm_current_a: float,
    conductor_mm2: float = 0.50,
) -> Tuple[float, bool]:
    """
    Yangın Algılama Çevrim (Loop) veya Siren Hattı DC Gerilim Düşümü:
      ΔU = 2 * (L / 1000) * R_km * I_alarm
      (0.8 mm çap ≈ 0.50 mm² için R_km = 36.6 Ω/km; 1.5 mm² için R_km = 12.1 Ω/km)
      24V DC sistemde izin verilen azami düşüm: <= 6.0 V (min çalışma 18.0 V DC)
    """
    if loop_length_m <= 0 or loop_alarm_current_a <= 0 or conductor_mm2 <= 0:
        return (0.0, True)
    r_km = 18.3 / conductor_mm2
    dv = 2.0 * (loop_length_m / 1000.0) * r_km * loop_alarm_current_a
    return (round(dv, 2), dv <= 6.0)


def calc_fiber_optic_link_loss_db(
    length_km: float,
    connector_pairs: int = 2,
    fusion_splices: int = 2,
    fiber_mode: str = "SM_1310",
    safety_margin_db: float = 2.0,
) -> float:
    """
    ISO/IEC 11801 Fiber Optik Zayıflama Bütçesi (Link Loss Budget) Formülü:
      Loss_dB = (α * L_km) + (N_conn * 0.50 dB) + (N_splice * 0.10 dB) + Margin_dB
    """
    alpha_map = {
        "MM_850": 3.50,
        "MM_1300": 1.50,
        "SM_1310": 0.40,
        "SM_1550": 0.30,
    }
    alpha = alpha_map.get(fiber_mode.strip().upper(), 0.40)
    loss = (alpha * max(0.0, length_km)) + (max(0, connector_pairs) * 0.50) + (max(0, fusion_splices) * 0.10) + safety_margin_db
    return round(loss, 2)


def calc_cctv_storage_and_poe_budget(
    camera_count: int,
    bitrate_mbps: float = 4.0,
    retention_days: int = 30,
    hours_per_day: float = 24.0,
    watts_per_camera: float = 12.5,
) -> Dict[str, float]:
    """
    TS EN 62676 CCTV Disk Depolama (TB), Bant Genişliği (Mbps) ve IEEE 802.3at PoE Bütçesi:
      - Disk_TB = (Bitrate_Mbps * 86400 * Gün * N_kamera * (Saat/24)) / (8 * 10⁶)
      - Bant_Genişliği_Mbps = N_kamera * Bitrate_Mbps * 1.20
      - PoE_Switch_Gücü_W = 1.25 * N_kamera * P_kamera
    """
    if camera_count <= 0:
        return {"storage_tb": 0.0, "bandwidth_mbps": 0.0, "poe_budget_w": 0.0}
    seconds = 86400.0 * retention_days * (hours_per_day / 24.0)
    storage_tb = (bitrate_mbps * seconds * camera_count) / 8_000_000.0
    bw_mbps = camera_count * bitrate_mbps * 1.20
    poe_w = 1.25 * camera_count * watts_per_camera
    return {
        "storage_tb": round(storage_tb, 2),
        "bandwidth_mbps": round(bw_mbps, 1),
        "poe_budget_w": round(poe_w, 1),
    }


def calc_pava_speaker_spl_and_amp(
    speaker_count: int,
    tap_power_w: float = 6.0,
    spl_1w_1m_db: float = 90.0,
    listener_distance_m: float = 4.0,
) -> Dict[str, float]:
    """
    TS EN 54-16 / TS EN 54-24 Acil Anons 100V Hat Amfi Gücü ve Mesafeye Göre Ses Basınç Seviyesi (SPL):
      - P_amfi_min = 1.25 * (N_hoparlör * P_tap)
      - Z_hat_ohm = 100² / (N_hoparlör * P_tap)
      - SPL(r) = SPL_1W_1m + 10*log10(P_tap) - 20*log10(r)
    """
    if speaker_count <= 0 or tap_power_w <= 0 or listener_distance_m <= 0:
        return {"total_speaker_w": 0.0, "min_amplifier_w": 0.0, "line_impedance_ohm": 0.0, "spl_at_listener_dba": 0.0}
    tot_w = speaker_count * tap_power_w
    amp_w = 1.25 * tot_w
    z_ohm = 10000.0 / tot_w
    spl_r = spl_1w_1m_db + (10.0 * math.log10(tap_power_w)) - (20.0 * math.log10(listener_distance_m))
    return {
        "total_speaker_w": round(tot_w, 1),
        "min_amplifier_w": round(amp_w, 1),
        "line_impedance_ohm": round(z_ohm, 1),
        "spl_at_listener_dba": round(spl_r, 1),
    }
