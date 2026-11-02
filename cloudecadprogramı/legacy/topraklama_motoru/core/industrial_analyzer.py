"""
CloudeCAD — Endüstriyel Tesis, Fabrika ve OG Trafo Merkezi Topraklama Denetim Motoru
====================================================================================
Standartlar:
  - IEEE Std 80-2013 (Guide for Safety in AC Substation Grounding)
  - TS EN 50522 (1 kV'u Aşan AC Güç Tesislerinin Topraklanması)
  - Elektrik Tesislerinde Topraklamalar Yönetmeliği (ETTY — Madde 10 & Ek-P)
  - TS HD 60364-5-54 (Koruma İletkenleri ve Eşpotansiyel kuşaklama)

Mühendislik Denetim Yetenekleri:
  1. Eşdeğer Ağ Direnci (Rg ≤ 1.0 Ω Endüstriyel/Trafo Kriteri — Sverak & Laurent-Niemann)
  2. IEEE Std 80-2013 Adım ve Dokunma Gerilimi Güvenlik Analizi (Etouch70, Estep70 vs. Em, Es + Mıcır Tabakası Cs)
  3. Yüksek Gerilim Ağ Gözü Sıklığı Denetimi (Maks. 10x10 m göz boyutu)
  4. STRtree Uzamsal İndeksli Endüstriyel Ekipman Denetimi (Trafo, OG Hücre, Jeneratör, Proses Tankı,
     Çelik Kolon, Çevre Çiti, Kapak, Izgara, Pano)
  5. Cadweld (Ekzotermik Kaynak) ve Vidalı Klemens Noktası Denetimi
"""

import math
import logging
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any

from standards.spec_profiles import get_spec_profile, SpecProfile
from core.metro_analyzer import MetroSpatialDefect

logger = logging.getLogger(__name__)


@dataclass
class StepTouchVoltageAudit:
    """IEEE Std 80-2013 Adım ve Dokunma Gerilimi hesap sonuçları."""
    rho_ohm_m: float = 100.0
    rho_s_crushed_rock_ohm_m: float = 2500.0
    hs_crushed_rock_m: float = 0.15
    fault_time_tf_s: float = 0.50
    assumed_fault_current_ig_a: float = 1000.0
    cs_derating_factor: float = 0.74
    e_touch70_limit_v: float = 840.0
    e_step70_limit_v: float = 2850.0
    gpr_earth_potential_rise_v: float = 850.0
    em_actual_mesh_voltage_v: float = 310.0
    es_actual_step_voltage_v: float = 240.0
    is_touch_safe: bool = True
    is_step_safe: bool = True


@dataclass
class IndustrialAnalysisResult:
    """Endüstriyel tesis veya OG trafo merkezi topraklama denetim çıktısı."""
    project_name: str
    facility_subtype: str = "Endüstriyel Tesis & OG Trafo Merkezi"
    spec_profile_id: str = "IEEE80_ENDUSTRIYEL"

    # 1. Geometri ve Metraj
    total_strip_length_m: float = 0.0
    facility_area_m2: float = 0.0
    facility_width_m: float = 0.0
    facility_length_m: float = 0.0
    rod_count: int = 0
    clamp_count: int = 0
    busbar_count: int = 0
    missing_clamp_junctions: int = 0
    missing_clamp_points: List[Tuple[float, float]] = field(default_factory=list)

    # 2. Ağ Gözü (10x10m Endüstriyel Sınır) Denetimi
    total_mesh_eyes: int = 0
    oversized_eyes_10m: int = 0
    max_eye_dim_m: float = 0.0
    grid_spacing_d_m: float = 6.0

    # 3. Topraklama Direnci (Rg ≤ 1.0 Ω Kriteri)
    rho_ohm_m: float = 100.0
    re_laurent_ohm: float = 0.0
    rg_ieee80_sverak_ohm: float = 0.0
    target_limit_ohm: float = 1.0
    is_resistance_suitable: bool = True

    # 4. IEEE Std 80 Adım ve Dokunma Gerilimi Analizi
    step_touch: StepTouchVoltageAudit = field(default_factory=StepTouchVoltageAudit)

    # 5. Uzamsal Ekipman / Gövde / Çit Denetimi
    spatial_defects: List[MetroSpatialDefect] = field(default_factory=list)
    grounded_elements: List[MetroSpatialDefect] = field(default_factory=list)
    equipment_summary_by_cat: List[Dict[str, Any]] = field(default_factory=list)
    technical_rooms_audit: List[Dict[str, Any]] = field(default_factory=list)

    # 6. Şartname Uygunluk Maddeleri
    spec_checks: List[Dict[str, str]] = field(default_factory=list)
    compliance_score_percent: float = 100.0
    executive_verdict: str = "UYGUNDUR"
    verdict_summary: str = ""


class IndustrialGroundingAnalyzer:
    """
    Endüstriyel tesis, fabrika, GES/RES santrali ve OG trafo merkezi projelerini
    IEEE Std 80-2013 ve TS EN 50522 kapsamında analiz eder.
    """

    def __init__(self, spec_profile_id: str = "IEEE80_ENDUSTRIYEL"):
        self.spec: SpecProfile = get_spec_profile(spec_profile_id)

    def analyze(
        self,
        drawing: Any,
        geo_result: Any,
        calc_result: Any,
        user_rho: Optional[float] = None
    ) -> IndustrialAnalysisResult:
        pname = Path(drawing.source_file).stem if hasattr(drawing, 'source_file') else "Endustriyel_Tesis"
        rho = user_rho or getattr(geo_result.params, 'rho_ohm_m', None) or 100.0

        # Alt tip belirleme (Trafo Merkezi / Fabrika / Santral)
        all_txt = " ".join(t.text.lower() for t in getattr(drawing, 'all_texts', []))
        if "trafo merkez" in all_txt or "indirici" in all_txt or "şalt" in all_txt:
            subtype = "OG / YG Trafo ve Şalt Merkezi"
        elif "ges" in all_txt or "güneş" in all_txt or "res" in all_txt or "santral" in all_txt:
            subtype = "Enerji Üretim Santrali (GES / RES / Kojenerasyon)"
        else:
            subtype = "Endüstriyel Üretim Tesisi & Fabrika OG/AG Şebekesi"

        # 1. Metraj ve Geometri Verileri
        L_strip = max(geo_result.total_strip_length_m, 20.0)
        area_m2 = max(geo_result.building_area_m2, 100.0)
        w_m = max(geo_result.building_width_m, 10.0)
        l_m = max(geo_result.building_length_m, 10.0)

        rod_cnt = (
            geo_result.params.stake_count
            if (geo_result.params.stake_count is not None and geo_result.params.stake_count > 0)
            else (geo_result.active_foundation_floor.rod_count if geo_result.active_foundation_floor else 8)
        )
        busbar_cnt = (
            geo_result.active_foundation_floor.busbar_count
            if (geo_result.active_foundation_floor and geo_result.active_foundation_floor.busbar_count > 0)
            else 2
        )

        # 2. Ağ Gözü (10x10m Endüstriyel Sınır) Kontrolü
        eyes = getattr(geo_result, 'mesh_eyes', [])
        limit_10m = self.spec.max_mesh_eye_m * (1.0 + self.spec.mesh_tolerance_ratio)
        oversized_10m = [e for e in eyes if e.max_dim_m > limit_10m]
        max_eye = max((e.max_dim_m for e in eyes), default=6.0)
        avg_spacing_d = max(3.0, min(12.0, math.sqrt(area_m2) / max(2.0, math.sqrt(max(len(eyes), 4)))))

        # 3. Direnç Hesabı (Rg ≤ 1.0 Ω Endüstriyel Hedef)
        re_laurent = calc_result.laurent_niemann.Re_combined_ohm
        rg_sverak = calc_result.ieee_sverak.Re_sverak_ohm
        best_r = min(re_laurent, rg_sverak) if (re_laurent > 0 and rg_sverak > 0) else max(re_laurent, rg_sverak)
        is_r_ok = (best_r <= self.spec.max_resistance_ohm)

        # 4. IEEE Std 80-2013 Adım ve Dokunma Gerilimi Hesabı
        st_audit = self._calculate_ieee80_step_touch(
            rho=rho,
            rg_ohm=best_r,
            L_strip_m=L_strip,
            rod_count=rod_cnt,
            area_m2=area_m2,
            spacing_d_m=avg_spacing_d,
        )

        # 5. STRtree Uzamsal Ekipman & Klemens Denetimi
        from core.metro_analyzer import MetroStationAnalyzer
        proxy_auditor = MetroStationAnalyzer(spec_profile_id=self.spec.profile_id)
        defects, grounded_list, cat_summary, real_clamps, missing_clamps, missing_clamp_pts = (
            proxy_auditor._audit_spatial_equipment_and_clamps(drawing, "ENDUSTRIYEL_SAHA", subtype)
        )
        tech_rooms = proxy_auditor._audit_technical_rooms(drawing, [], "ENDUSTRIYEL_SAHA")

        if real_clamps == 0 and geo_result.active_foundation_floor:
            real_clamps = geo_result.active_foundation_floor.clamp_count

        # 6. Şartname Kontrol Tablosu
        spec_checks = [
            {
                "kriter": "1. Eşdeğer Topraklama Direnci (Rg ≤ 1.0 Ω)",
                "sartname": "IEEE Std 80-2013 & ETTY Madde 10 uyarınca endüstriyel tesis ve OG trafo merkezi eşdeğer direnci Rg ≤ 1.0 Ω olmalıdır.",
                "durum": (
                    f"✓ UYGUN (Rg = {rg_sverak:.3f} Ω / Re = {re_laurent:.3f} Ω ≤ 1.0 Ω)"
                    if is_r_ok else f"✗ SINIR AŞILDI (Rg = {rg_sverak:.3f} Ω > 1.0 Ω — İlave elektrot/şerit gerekli)"
                )
            },
            {
                "kriter": "2. Dokunma Gerilimi Güvenliği (Em ≤ Etouch70)",
                "sartname": f"IEEE Std 80 (70 kg, tf={st_audit.fault_time_tf_s}s, hs={st_audit.hs_crushed_rock_m}m mıcır) müsaade edilen sınır Etouch70 = {st_audit.e_touch70_limit_v:.0f} V.",
                "durum": (
                    f"✓ GÜVENLİ (Oluşan Göz Gerilimi Em = {st_audit.em_actual_mesh_voltage_v:.0f} V ≤ {st_audit.e_touch70_limit_v:.0f} V)"
                    if st_audit.is_touch_safe else f"✗ TEHLİKELİ (Em = {st_audit.em_actual_mesh_voltage_v:.0f} V > {st_audit.e_touch70_limit_v:.0f} V)"
                )
            },
            {
                "kriter": "3. Adım Gerilimi Güvenliği (Es ≤ Estep70)",
                "sartname": f"IEEE Std 80 müsaade edilen maksimum adım gerilimi sınırı Estep70 = {st_audit.e_step70_limit_v:.0f} V.",
                "durum": (
                    f"✓ GÜVENLİ (Oluşan Adım Gerilimi Es = {st_audit.es_actual_step_voltage_v:.0f} V ≤ {st_audit.e_step70_limit_v:.0f} V)"
                    if st_audit.is_step_safe else f"✗ TEHLİKELİ (Es = {st_audit.es_actual_step_voltage_v:.0f} V > {st_audit.e_step70_limit_v:.0f} V)"
                )
            },
            {
                "kriter": "4. Yüksek Gerilim Ağ Gözü Sıklığı (≤ 10m × 10m)",
                "sartname": "TS EN 50522 & TEİAŞ kriterlerine göre potansiyel gradyanını sınırlamak için ızgara gözleri ≤ 10x10 m olmalıdır.",
                "durum": (
                    f"✓ UYGUN ({len(eyes)} ağ gözü incelendi, tamamı sınır dahilinde)"
                    if len(oversized_10m) == 0 else f"⚠ DİKKAT ({len(oversized_10m)} adet ağ gözü > 10m; maks. {max_eye:.1f} m)"
                )
            },
            {
                "kriter": "5. Ekipman, Gövde, Tank ve Kapak Eşpotansiyel İrtibatı",
                "sartname": "Tüm trafo, OG hücre, jeneratör, proses tankı, çelik kolon ve kapaklar ana ağa bağlanmalıdır.",
                "durum": (
                    f"✓ UYGUN ({len(grounded_list)} ekipman doğrulandı)"
                    if len(defects) == 0 else f"✗ EKSİK VAR ({len(defects)} adet ekipman/kapak topraklanmamış)"
                )
            },
            {
                "kriter": "6. Cadweld (Ekzotermik Kaynak) ve Klemens Noktaları",
                "sartname": "Toprak altı kesişimler Cadweld (ekzotermik kaynak) veya korozyona dayanıklı ağır hizmet klemensi ile yapılmalıdır.",
                "durum": f"✓ {real_clamps} Adet Klemens/Ek Noktası Doğrulandı" if missing_clamps == 0 else f"⚠ {missing_clamps} T-Ek Noktasında Sembol Eksik"
            },
        ]

        # Genel Uyum Skoru ve Hüküm
        penalties = 0.0
        if not is_r_ok:
            penalties += 25.0
        if not st_audit.is_touch_safe:
            penalties += 25.0
        if len(defects) > 0:
            penalties += min(30.0, len(defects) * 5.0)
        if len(oversized_10m) > 0:
            penalties += 10.0

        score = max(10.0, round(100.0 - penalties, 1))
        if is_r_ok and st_audit.is_touch_safe and len(defects) == 0:
            verdict = "UYGUNDUR (IEEE STD 80 & TS EN 50522 KRİTERLERİNE UYGUN)"
        else:
            verdict = "REVİZYON GEREKLİ (DİRENÇ / DOKUNMA GERİLİMİ VEYA EKİPMAN EKSİĞİ)"

        summary = (
            f"{subtype} | Şerit: {L_strip:.1f} m | Kazık: {rod_cnt} Adet | "
            f"Rg(IEEE 80): {rg_sverak:.3f} Ω | Em: {st_audit.em_actual_mesh_voltage_v:.0f}V / {st_audit.e_touch70_limit_v:.0f}V | "
            f"Karar: {verdict}"
        )

        return IndustrialAnalysisResult(
            project_name=pname,
            facility_subtype=subtype,
            spec_profile_id=self.spec.profile_id,
            total_strip_length_m=L_strip,
            facility_area_m2=area_m2,
            facility_width_m=w_m,
            facility_length_m=l_m,
            rod_count=rod_cnt,
            clamp_count=real_clamps,
            busbar_count=busbar_cnt,
            missing_clamp_junctions=missing_clamps,
            missing_clamp_points=missing_clamp_pts,
            total_mesh_eyes=len(eyes),
            oversized_eyes_10m=len(oversized_10m),
            max_eye_dim_m=max_eye,
            grid_spacing_d_m=avg_spacing_d,
            rho_ohm_m=rho,
            re_laurent_ohm=re_laurent,
            rg_ieee80_sverak_ohm=rg_sverak,
            target_limit_ohm=self.spec.max_resistance_ohm,
            is_resistance_suitable=is_r_ok,
            step_touch=st_audit,
            spatial_defects=defects,
            grounded_elements=grounded_list,
            equipment_summary_by_cat=cat_summary,
            technical_rooms_audit=tech_rooms,
            spec_checks=spec_checks,
            compliance_score_percent=score,
            executive_verdict=verdict,
            verdict_summary=summary,
        )

    def _calculate_ieee80_step_touch(
        self,
        rho: float,
        rg_ohm: float,
        L_strip_m: float,
        rod_count: int,
        area_m2: float,
        spacing_d_m: float,
    ) -> StepTouchVoltageAudit:
        """
        IEEE Std 80-2013 Denklem (27), (32), (33), (80), (89) uyarınca
        yüzey mıcır indirgeme faktörü Cs, müsaade edilen Etouch70 / Estep70
        ve oluşan gerçek Em / Es gerilimlerini hesaplar.
        """
        rho_s = self.spec.crushed_rock_rho_s_ohm_m
        hs = self.spec.crushed_rock_thickness_hs_m
        tf = self.spec.fault_clearing_time_s
        ig_a = 1000.0  # Tipik OG tek faz toprak teması şebeke dağılım akımı (1 kA)

        # IEEE 80 Eq. 27: Yüzey mıcır indirgeme faktörü Cs
        cs = 1.0 - (0.09 * (1.0 - (rho / max(rho_s, 1.0)))) / (2.0 * hs + 0.09)
        cs = max(0.30, min(1.0, cs))

        # IEEE 80 Eq. 32 & 33 (70 kg insan ağırlığı için müsaade edilen sınırlar)
        e_touch70 = (1000.0 + 1.5 * cs * rho_s) * (0.157 / math.sqrt(tf))
        e_step70 = (1000.0 + 6.0 * cs * rho_s) * (0.157 / math.sqrt(tf))

        # Etkin gömülü iletken boyu (LM = L_strip + 1.55 * L_rods)
        L_rods_total = max(0, rod_count) * 2.0
        L_M = max(L_strip_m + 1.55 * L_rods_total, 30.0)
        L_S = max(0.75 * L_strip_m + 0.85 * L_rods_total, 25.0)

        # Geometri faktörleri Km, Ks ve düzeltme faktörü Ki
        h = 0.60  # Gömülme derinliği (m)
        d = 0.014 # Eşdeğer iletken çapı (m)
        D = max(3.0, min(15.0, spacing_d_m))
        n = max(3.0, math.sqrt(area_m2) / D + 1.0)
        ki = 0.644 + 0.148 * n

        try:
            km = (1.0 / (2.0 * math.pi)) * (
                math.log((D * D) / (16.0 * h * d)) + (1.0 / math.pi) * math.log(max(1.2, 2.0 * n - 3.0))
            )
            km = max(0.35, min(1.25, km))
        except Exception:
            km = 0.65

        ks = (1.0 / math.pi) * (1.0 / (2.0 * h) + 1.0 / (D + h) + (1.0 / D) * (1.0 - math.pow(0.5, max(1.0, n - 2.0))))
        ks = max(0.25, min(1.10, ks))

        em = (rho * km * ki * ig_a) / L_M
        es = (rho * ks * ki * ig_a) / L_S
        gpr = ig_a * rg_ohm

        return StepTouchVoltageAudit(
            rho_ohm_m=rho,
            rho_s_crushed_rock_ohm_m=rho_s,
            hs_crushed_rock_m=hs,
            fault_time_tf_s=tf,
            assumed_fault_current_ig_a=ig_a,
            cs_derating_factor=round(cs, 3),
            e_touch70_limit_v=round(e_touch70, 1),
            e_step70_limit_v=round(e_step70, 1),
            gpr_earth_potential_rise_v=round(gpr, 1),
            em_actual_mesh_voltage_v=round(em, 1),
            es_actual_step_voltage_v=round(es, 1),
            is_touch_safe=(em <= e_touch70),
            is_step_safe=(es <= e_step70),
        )
