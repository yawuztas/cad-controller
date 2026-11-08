# -*- coding: utf-8 -*-
"""
Deterministik Mühendislik Hesap Motoru (ElectricalCalculators)
==============================================================
Elektrik mühendisliği standart formüllerini çalıştırır. Asla AI tahmini içermez.
"""

from __future__ import annotations
import math
import re
from typing import Tuple, Optional, Dict, Any, List


from dataclasses import dataclass


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
            # 5 damarlı: 3 Faz + 1 Nötr + 1 PE
            return CableConductorSpec(cores=5, phase_mm2=sec, neutral_mm2=sec, pe_mm2=sec, is_pe_explicit=True, is_valid=True, raw_str=raw)
        elif cnt == 4:
            # 4 damarlı: 3 Faz + 1 Nötr (veya motor devresinde 3 Faz + 1 PE). PE açıkça doğrulanmamış.
            return CableConductorSpec(cores=4, phase_mm2=sec, neutral_mm2=sec, pe_mm2=None, is_pe_explicit=False, is_valid=True, raw_str=raw)
        elif cnt == 3:
            if sec <= 6.0:
                # Küçük kesit 230V devre: 1 Faz + 1 Nötr + 1 PE
                return CableConductorSpec(cores=3, phase_mm2=sec, neutral_mm2=sec, pe_mm2=sec, is_pe_explicit=True, is_valid=True, raw_str=raw)
            else:
                # Büyük kesit 3 Faz (örn 3x50): Nötr ve PE ayrı çekilmeli
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
    Yüzde Gerilim Düşümünü (%e) hesaplar:
      - 1 Faz: %e = (2 * L * P) / (κ * S * U²) * 100
      - 3 Faz: %e = (1 * L * P) / (κ * S * U²) * 100
    """
    if power_w <= 0.0 or cond_mm2 <= 0.0 or voltage_v <= 0 or conductivity <= 0:
        return 0.0
    factor = 1.0 if is_3phase else 2.0
    vd = (factor * effective_length_m * power_w) / (conductivity * cond_mm2 * (voltage_v ** 2)) * 100.0
    return round(vd, 2)


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


def check_pe_cross_section_iec60364_5_54(phase_mm2: float, pe_mm2: float) -> Tuple[bool, float, str]:
    """
    IEC 60364-5-54 Tablo 54.2 uyarınca koruma iletkeni (PE) kontrolü:
      - S_faz <= 16 mm²     => S_PE >= S_faz
      - 16 < S_faz <= 35 mm² => S_PE >= 16 mm²
      - S_faz > 35 mm²      => S_PE >= S_faz / 2
    """
    if phase_mm2 <= 16.0:
        req_pe = phase_mm2
    elif phase_mm2 <= 35.0:
        req_pe = 16.0
    else:
        req_pe = round(phase_mm2 / 2.0, 1)

    is_compliant = pe_mm2 >= req_pe
    explanation = f"S_faz = {phase_mm2} mm² için IEC 60364-5-54 min S_PE = {req_pe} mm²; Mevcut = {pe_mm2} mm²"
    return is_compliant, req_pe, explanation
