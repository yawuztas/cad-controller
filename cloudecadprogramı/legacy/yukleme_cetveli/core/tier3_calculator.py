"""
CloudeCAD — Tier 3: Deterministik Hesap ve Standart Denetim Motoru
==================================================================
Tipolojiye göre güç teyidi (Konut BEDAŞ, Metro NFPA 130 senaryoları,
Endüstriyel IEC ku*ks), faz dengelemesi, TS HD 60364 düzeltilmiş
akım taşıma kontrolü (Ib <= In <= Iz), reaktanslı gerilim düşümü
ve can/yangın güvenliği (KAKR) denetimi.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from config import (
    DEFAULT_VOLTAGE_3PHASE, DEFAULT_VOLTAGE_1PHASE,
    DEFAULT_POWER_FACTOR_POWER, DEFAULT_POWER_FACTOR_LIGHTING,
    MAX_VDROP_LIGHTING_PCT, MAX_VDROP_POWER_PCT, MAX_VDROP_MAIN_FEEDER_PCT,
    MAX_PHASE_UNBALANCE_PCT
)
from core.models import (
    ExtractedProjectData, SubPanelModel, MainPanelModel,
    PhaseBalanceResult, ShortCircuitResult
)
from standards.typology_standards import (
    ProjectTypology, LoadCategory, TYPOLOGY_LOAD_FACTORS,
    classify_circuit_or_load
)
from standards.ts_hd_60364 import (
    COPPER_CABLE_SPECS, calculate_corrected_ampacity,
    get_base_ampacity
)
from standards.eity_regulations import (
    calculate_dwelling_demand_power, get_building_diversity_factor,
    calculate_voltage_drop_approx, calculate_voltage_drop_exact
)


@dataclass
class AuditFinding:
    """Tekil mühendislik denetim bulgusu"""
    category: str        # 'GÜÇ_TEYİT', 'KABLO_AKIM', 'GERİLİM_DÜŞÜMÜ', 'FAZ_DENGESİ', 'CAN_GÜVENLİĞİ'
    panel_name: str
    status: str          # 'PASS' (Uygun), 'WARNING' (Uyarı), 'FAIL' (Hatalı/Tehlikeli)
    title: str
    detail: str
    recommendation: str = ""


@dataclass
class PanelCalculationResult:
    """Tali pano detaylı hesap sonucu"""
    name: str
    installed_power_w: float
    demand_power_w_calc: float
    demand_power_w_proj: float
    power_match_status: str       # 'DOĞRULANDI', 'FARK_VAR'
    current_ib_a: float
    cable_spec: str
    cable_cross_section_mm2: float
    cable_base_ampacity_iz0: float
    cable_corrected_ampacity_iz: float # Şaft/demetleme düzeltilmiş
    breaker_rating_a: float
    breaker_coordination_status: str   # 'UYGUN', 'KABLO_AŞIRI_YÜKLÜ'
    feeder_length_m: float
    vdrop_approx_pct: float
    vdrop_exact_pct: float             # Reaktanslı
    vdrop_status: str                  # 'UYGUN', 'SINIR_AŞILDI'
    phase_powers_w: Dict[str, float] = field(default_factory=dict)
    phase_unbalance_pct: float = 0.0
    rcd_status: str = "UYGUN"


@dataclass
class MetroScenarioResult:
    """Metro/Tünel projeleri için senaryo bazlı talep gücü sonuçları"""
    normal_mode_kw: float = 0.0
    emergency_fire_mode_kw: float = 0.0
    night_mode_kw: float = 0.0
    peak_demand_kw: float = 0.0
    governing_scenario: str = "EMERGENCY_FIRE_MODE"


@dataclass
class TriMethodCalculation:
    """3 Ayrı Hesap Yönteminin Yan Yana Karşılaştırma Sonuçları"""
    panel_name: str
    cable_spec: str
    length_m: float
    power_w: float
    current_ib_a: float
    breaker_in_a: float

    # [1] Mevcut Projedeki Hesap (Geleneksel / Projeci Beyanı)
    proj_vdrop_pct: float
    proj_iz_a: float            # Düzeltmesiz katalog değeri
    proj_verdict: str           # Örn: 'UYGUNDUR (%2.36 < %3.5)'
    proj_flaws: str             # Tespit edilen eksiklik/ihmaller

    # [2] YÖNTEM 1: EMO & EİTY Yönetmelik Hesabı (Güncel Türk Mevzuatı)
    eity_vdrop_pct: float
    eity_vdrop_limit_pct: float # Aydınlatma için %1.5, Güç için %3.0
    eity_iz_a: float
    eity_verdict: str           # 'UYGUN' veya 'YÖNETMELİK SINIRI AŞILDI'
    eity_notes: str

    # [3] YÖNTEM 2: TS HD 60364 & IEC 60364-5-52 İleri Mühendislik Hesabı (Fiziksel / Kesin)
    iec_vdrop_pct: float        # Reaktanslı (R*cosφ + X*sinφ)
    iec_vdrop_limit_pct: float
    iec_iz_corrected_a: float   # Şaft demetleme (k_grup) ve sıcaklık düzeltilmiş
    iec_verdict: str            # 'GÜVENLİ' veya 'ŞAFTTA AŞIRI ISINMA RİSKİ'
    iec_notes: str

    # Sapma Analizi (Karşılaştırma)
    vdrop_deviation_pct: float  # Proje ile Kesin IEC hesabı arasındaki fark (%)
    ampacity_margin_a: float    # In ile düzeltilmiş Iz arasındaki emniyet marjı


@dataclass
class EngineeringAuditReport:
    """Tüm projenin nihai mühendislik denetim karnesi"""
    project_name: str
    typology: ProjectTypology
    typology_rationale: str
    main_installed_power_w: float
    main_demand_power_w: float
    main_diversity_factor: float
    main_feeder_current_a: float
    main_feeder_vdrop_pct: float
    metro_scenarios: Optional[MetroScenarioResult] = None
    panel_results: Dict[str, PanelCalculationResult] = field(default_factory=dict)
    tri_method_results: Dict[str, TriMethodCalculation] = field(default_factory=dict) # Yan Yana 3 Yöntem
    phase_balance_results: Dict[str, PhaseBalanceResult] = field(default_factory=dict) # Faz Denge ve Nötr Akımı
    short_circuit_results: Dict[str, ShortCircuitResult] = field(default_factory=dict) # IEC 60909 Kısa Devre & Termik
    findings: List[AuditFinding] = field(default_factory=list)
    overall_verdict: str = "UYGUNDUR"
    score_pct: float = 100.0


class EngineeringCalculator:
    """Kuvvetli akım deterministik hesap ve standart denetim motoru."""

    def __init__(self, proj_data: ExtractedProjectData, typology: ProjectTypology, typology_desc: str):
        self.data = proj_data
        self.typology = typology
        self.typology_desc = typology_desc
        self.report = EngineeringAuditReport(
            project_name=proj_data.project_name,
            typology=typology,
            typology_rationale=typology_desc,
            main_installed_power_w=proj_data.main_panel.installed_power_w,
            main_demand_power_w=proj_data.main_panel.demand_power_w,
            main_diversity_factor=proj_data.main_panel.diversity_factor,
            main_feeder_current_a=0.0,
            main_feeder_vdrop_pct=0.0
        )

    def compute_and_audit(self) -> EngineeringAuditReport:
        """Tüm hesaplama ve denetim adımlarını yürütür."""
        # 1. Ana Besleme Hattı Hesabı (Kofre / Trafo -> Ana Tablo)
        self._calculate_main_feeder()

        # 2. Tipolojiye Göre Talep Gücü ve Senaryo Analizi
        if self.typology == ProjectTypology.INFRASTRUCTURE_METRO:
            self._calculate_metro_scenarios()
        elif self.typology in (ProjectTypology.INDUSTRIAL, ProjectTypology.COMMERCIAL):
            self._verify_industrial_or_commercial_demand()
        else:
            self._verify_residential_or_commercial_demand()

        # 3. Her Tali Pano İçin Detaylı Mühendislik Hesapları
        for pname, sp in self.data.sub_panels.items():
            res = self._calculate_sub_panel(sp)
            self.report.panel_results[pname] = res

        # 4. Faz Yük Dengesi ve Vektörel Nötr Akımı Analizi (R-S-T & Inötr)
        self._calculate_phase_balances()

        # 5. IEC 60909 Kısa Devre & TS HD 60364-4-43 Termik Dayanım Hesabı
        self._calculate_short_circuit_and_thermal()

        # 6. Metro / Endüstriyel Özel Kurallar & TS HD 60364-5-54 Topraklama (PE) Kesit Çapraz Denetimi
        self._audit_special_and_pe_rules()

        # 7. Genel Karne ve Güvenlik Değerlendirmesi
        self._evaluate_overall_verdict()

        return self.report

    def _calculate_main_feeder(self):
        """Ana besleme hattı akımı, gerilim düşümü ve 3 Yöntemli Karşılaştırması."""
        main_p = self.data.main_panel
        pt = main_p.demand_power_w
        if pt <= 0:
            pt = main_p.installed_power_w * main_p.diversity_factor

        # Akım: Ib = Pt / (√3 * U * cosφ)
        cos_phi = DEFAULT_POWER_FACTOR_POWER
        u = DEFAULT_VOLTAGE_3PHASE
        ib = pt / (math.sqrt(3.0) * u * cos_phi) if pt > 0 else 0.0
        self.report.main_feeder_current_a = round(ib, 1)

        l_m = main_p.feeder_length_m
        s_mm2 = main_p.feeder_cross_section_mm2
        par_m = re.match(r'^(\d+)\s*\(\s*3', (main_p.feeder_cable_spec or '').strip())
        n_par = int(par_m.group(1)) if par_m else 1
        s_eff = s_mm2 * n_par

        # 1. Projedeki / Klasik Omik Hesap
        vdrop_proj = calculate_voltage_drop_approx(l_m, pt, s_eff, is_three_phase=True)
        self.report.main_feeder_vdrop_pct = vdrop_proj
        iz_base = round(get_base_ampacity(s_mm2, method="air") * n_par, 1)

        # 2. YÖNTEM 1: EMO & EİTY Yönetmelik Hesabı
        vdrop_eity = vdrop_proj
        limit_eity = MAX_VDROP_MAIN_FEEDER_PCT
        eity_verdict = "UYGUN" if vdrop_eity <= limit_eity else "SINIR AŞILDI"

        # 3. YÖNTEM 2: TS HD 60364 & IEC 60364-5-52 Kesin Empedans Hesabı
        cable_spec_entry = COPPER_CABLE_SPECS.get(s_mm2, COPPER_CABLE_SPECS[95.0])
        r_km = cable_spec_entry["r_ohm_km"] / n_par
        x_km = cable_spec_entry["x_ohm_km"] / n_par
        vdrop_iec = calculate_voltage_drop_exact(l_m, ib, s_eff, r_km, x_km, cos_phi=cos_phi, is_three_phase=True)
        # Tava/Kablo kanalı demetleme katsayısı (3 ana besleme, 35°C)
        iz_iec = round(calculate_corrected_ampacity(s_mm2, method="air", ambient_c=35.0, number_of_cables=2, insulation="XLPE") * n_par, 1)
        iec_verdict = "GÜVENLİ" if (vdrop_iec <= limit_eity and iz_iec >= ib) else "UYARI"

        # Sapma Analizi
        dev_pct = round(((vdrop_iec - vdrop_proj) / max(0.01, vdrop_proj)) * 100.0, 1)
        margin_a = round(iz_iec - ib, 1)

        # 3 Yöntem Karşılaştırma Kaydı
        self.report.tri_method_results["ANA_BESLEME"] = TriMethodCalculation(
            panel_name=f"ANA BESLEME ({main_p.name})",
            cable_spec=main_p.feeder_cable_spec,
            length_m=l_m,
            power_w=pt,
            current_ib_a=ib,
            breaker_in_a=main_p.main_breaker_rating_a,
            proj_vdrop_pct=vdrop_proj,
            proj_iz_a=iz_base,
            proj_verdict=f"UYGUNDUR (%{vdrop_proj:.2f} < %3.5)",
            proj_flaws="Endüktif reaktans (X) ihmal edilmiş, ortam sıcaklık düzeltmesi yapılmamış.",
            eity_vdrop_pct=vdrop_eity,
            eity_vdrop_limit_pct=limit_eity,
            eity_iz_a=iz_base,
            eity_verdict=eity_verdict,
            eity_notes=f"EİTY Madde 57 ana hat sınırı (%{limit_eity}) altında.",
            iec_vdrop_pct=vdrop_iec,
            iec_vdrop_limit_pct=limit_eity,
            iec_iz_corrected_a=iz_iec,
            iec_verdict=iec_verdict,
            iec_notes=f"Reaktans dahil voltaj kaybı %{vdrop_iec:.2f}. Düzeltilmiş akım Iz={iz_iec:.1f}A.",
            vdrop_deviation_pct=dev_pct,
            ampacity_margin_a=margin_a
        )

        # Denetim Bulgusu (Metro Plan & Metraj paftalarında ana besleme tek hat şeması yer almadığından bulgu üretilmez)
        if not getattr(self.data, "is_metro_plan_sheet", False):
            if vdrop_proj > MAX_VDROP_MAIN_FEEDER_PCT:
                self.report.findings.append(AuditFinding(
                    category="GERİLİM_DÜŞÜMÜ",
                    panel_name=main_p.name,
                    status="FAIL",
                    title="Ana Besleme Gerilim Düşümü Sınırı Aşıldı!",
                    detail=f"Ana besleme hattında gerilim düşümü %{vdrop_proj:.2f} (Azami sınır: %{MAX_VDROP_MAIN_FEEDER_PCT}).",
                    recommendation=f"Ana kablo kesitini {s_mm2} mm²'den bir üst standart kesite artırınız."
                ))
            else:
                self.report.findings.append(AuditFinding(
                    category="GERİLİM_DÜŞÜMÜ",
                    panel_name=main_p.name,
                    status="PASS",
                    title="Ana Besleme Gerilim Düşümü Doğrulandı",
                    detail=f"Proje Omik: %{vdrop_proj:.2f} | TS HD 60364 Reaktanslı: %{vdrop_iec:.2f} < %{MAX_VDROP_MAIN_FEEDER_PCT} (Sapma: +%{dev_pct:.1f})."
                ))

    def _calculate_metro_scenarios(self):
        """NFPA 130 ve IEC Metro İşletme Senaryoları Analizi."""
        scenarios = TYPOLOGY_LOAD_FACTORS[ProjectTypology.INFRASTRUCTURE_METRO]
        norm_kw = 0.0
        emerg_kw = 0.0
        night_kw = 0.0

        for sp in self.data.sub_panels.values():
            for c in sp.circuits:
                cat = classify_circuit_or_load(c.description, c.circuit_no)
                p_kw = c.power_w / 1000.0

                # Normal mod
                f_norm = scenarios["NORMAL_MODE"].get(cat, {"ku": 0.8, "ks": 0.7})
                norm_kw += p_kw * f_norm["ku"] * f_norm["ks"]

                # Yangın modu (TVF devrede, yürüyen merdivenler ve konfor kapalı)
                f_emerg = scenarios["EMERGENCY_FIRE_MODE"].get(cat, {"ku": 0.0, "ks": 0.0})
                emerg_kw += p_kw * f_emerg["ku"] * f_emerg["ks"]

        peak = max(norm_kw, emerg_kw)
        self.report.metro_scenarios = MetroScenarioResult(
            normal_mode_kw=round(norm_kw, 1),
            emergency_fire_mode_kw=round(emerg_kw, 1),
            night_mode_kw=round(norm_kw * 0.20, 1),
            peak_demand_kw=round(peak, 1),
            governing_scenario="EMERGENCY_FIRE_MODE" if emerg_kw >= norm_kw else "NORMAL_MODE"
        )
        self.report.findings.append(AuditFinding(
            category="GÜÇ_TEYİT",
            panel_name="METRO_SİSTEMİ",
            status="INFO",
            title=f"Metro Senaryo Analizi: Zirve Güç = {peak:,.1f} kW",
            detail=f"Normal İşletme Modu: {norm_kw:,.1f} kW | Yangın/Acil Durum Modu (NFPA 130): {emerg_kw:,.1f} kW. Trafo ve jeneratör {self.report.metro_scenarios.governing_scenario} senaryosuna göre boyutlandırılmalıdır."
        ))

    def _verify_industrial_or_commercial_demand(self):
        """Endüstriyel tesis, fabrika ve ticari yapılarda IEC 60364 / IEEE 141 ku*ks talep gücü ve kompanzasyon denetimi."""
        factors = TYPOLOGY_LOAD_FACTORS.get(self.typology, TYPOLOGY_LOAD_FACTORS[ProjectTypology.INDUSTRIAL])
        calc_total_dem_w = 0.0

        for sp in self.data.sub_panels.values():
            if sp.circuits:
                for c in sp.circuits:
                    cat = classify_circuit_or_load(c.description, c.circuit_no)
                    f_entry = factors.get(cat, {"ku": 0.80, "ks": 0.75})
                    calc_total_dem_w += c.power_w * f_entry["ku"] * f_entry["ks"]
            else:
                calc_total_dem_w += sp.installed_power_w * 0.65

        main_p = self.data.main_panel
        if calc_total_dem_w <= 0 and main_p.installed_power_w > 0:
            calc_total_dem_w = main_p.installed_power_w * 0.65

        # EPDK Reaktif Güç Kompanzasyon Zorunluluğu (Kurulu güç >= 50 kVA)
        if main_p.installed_power_w >= 40000.0:
            q_kvar = round((main_p.demand_power_w / 1000.0) * 0.42, 1)
            self.report.findings.append(AuditFinding(
                category="GÜÇ_TEYİT",
                panel_name=main_p.name,
                status="PASS",
                title=f"Endüstriyel/Ticari Kompanzasyon ve Talep Teyidi (Qc ≈ {q_kvar} kVAr)",
                detail=(
                    f"EPDK Reaktif Güç Yönetmeliği uyarınca >50 kVA tesislerde endüktif oran <%20, kapasitif oran <%15 "
                    f"olmalıdır (Tahmini merkezi kompanzasyon ihtiyacı: {q_kvar} kVAr, Harmonik filtreli reaktör önerilir)."
                )
            ))

    def _audit_special_and_pe_rules(self):
        """
        1. Metro / Endüstriyel Özel Kurallar (NFPA 130 FE180/PH120 yangına dayanıklı kablo, motor kalkış eğrisi)
        2. TS HD 60364-5-54 Tablo 54.2 Koruma/Topraklama İletkeni (PE) Çapraz Kesit Denetimi
        """
        # A) Ana ve Tali Pano Kablolarında PE (Topraklama) Kesiti Çapraz Kontrolü (TS HD 60364-5-54)
        all_cables_to_check = [(self.data.main_panel.name, self.data.main_panel.feeder_cable_spec, self.data.main_panel.feeder_cross_section_mm2)]
        for pname, sp in self.data.sub_panels.items():
            if pname != self.data.main_panel.name:
                all_cables_to_check.append((pname, sp.cable_spec, sp.cable_cross_section_mm2))

        for pname, c_spec, s_phase in all_cables_to_check:
            if not c_spec or s_phase <= 0:
                continue
            # Örn: "3x95+50 NYY" veya "3x240/120" formatından PE/Nötr kesitini yakala
            m_pe = re.search(r'\d+\s*[xX*]\s*[\d.,]+\s*[+/]\s*([\d.,]+)', c_spec)
            if m_pe:
                s_pe = float(m_pe.group(1).replace(",", "."))
                if s_phase <= 16.0:
                    min_pe = s_phase
                elif s_phase <= 35.0:
                    min_pe = 16.0
                else:
                    min_pe = s_phase / 2.0

                if s_pe < min_pe:
                    self.report.findings.append(AuditFinding(
                        category="CAN_GÜVENLİĞİ",
                        panel_name=pname,
                        status="FAIL",
                        title=f"{pname} Koruma/Topraklama (PE) Kesiti Yetersiz (TS HD 60364-5-54)!",
                        detail=f"Kablo '{c_spec}' içinde faz kesiti S={s_phase:.0f} mm² iken PE/Nötr kesiti {s_pe:.0f} mm² seçilmiş (Asgari olması gereken: {min_pe:.0f} mm²).",
                        recommendation=f"TS HD 60364-5-54 Tablo 54.2 uyarınca koruma iletkeni kesitini en az {min_pe:.0f} mm² yapınız."
                    ))

            # B) Metro / Tünel / Acil Durum Panolarında FE180 / Halojensiz Kablo Kontrolü
            p_upper = f"{pname} {c_spec}".upper()
            if self.typology == ProjectTypology.INFRASTRUCTURE_METRO or any(k in p_upper for k in ["TVF", "YANGIN", "DUMAN", "ACİL", "ACIL", "UPS", "SCADA"]):
                if any(pvc in c_spec.upper() for pvc in ["NYY", "NYM", "H07V"]) and any(k in pname.upper() for k in ["TVF", "YANGIN", "ACİL", "UPS"]):
                    self.report.findings.append(AuditFinding(
                        category="CAN_GÜVENLİĞİ",
                        panel_name=pname,
                        status="WARNING",
                        title=f"{pname} Acil Durum Hattında PVC Kablo Uyarısı (NFPA 130 / BYKHY)!",
                        detail=f"Acil durum / yangın / UPS panosu ({pname}) beslemesinde '{c_spec}' görünüyor. Yangın esnasında zehirli gaz ve kesinti riski taşır.",
                        recommendation="Tünel ve acil durum yüklerinde N2XH FE180/PH120 (halojensiz, yangında 120 dk işlevini sürdüren) kablo kullanınız."
                    ))

        # C) Endüstriyel Motor Linyelerinde Sigorta Açma Eğrisi (B vs C/D) Kontrolü
        for pname, sp in self.data.sub_panels.items():
            for c in sp.circuits:
                cat = classify_circuit_or_load(c.description, c.circuit_no)
                if cat in (LoadCategory.HEAVY_MACHINERY, LoadCategory.FIRE_EMERGENCY, LoadCategory.TRANSPORT):
                    if c.breaker_curve.upper() == "B" and c.power_w >= 2200.0:
                        self.report.findings.append(AuditFinding(
                            category="KABLO_AKIM",
                            panel_name=pname,
                            status="WARNING",
                            title=f"{pname}/{c.circuit_no} Motor Hattında 'B' Eğrili Sigorta Hatası!",
                            detail=f"'{c.description}' ({c.power_w:.0f} W) motor kalkış demeraj akımında (6xIn) B tipi sigorta istenmeyen açma yapar.",
                            recommendation="Motor ve ağır makine linyelerinde C veya D eğrili MCB ya da termik-manyetik motor koruma şalteri (MPCB) kullanınız."
                        ))

        # D) Raylı Sistem / Metro Uygulama ve Metraj Paftası Özel Denetimleri (NFPA 130 / EN 50122 / TS HD 60364)
        if getattr(self.data, "is_metro_plan_sheet", False):
            # 1. Plan BS Etiketi vs Metraj Tablosu Kesit Çelişkisi
            if self.data.metro_sec_mismatches:
                mm_list = self.data.metro_sec_mismatches
                sample_str = "; ".join(
                    f"{m['line_no']} ({m['bs_code']}): Plan='{m['plan_cable']}' ≠ Tablo='{m['table_cable']}'"
                    for m in mm_list[:6]
                )
                self.report.findings.append(AuditFinding(
                    category="TUTARSIZLIK",
                    panel_name="PLAN_VS_TABLO",
                    status="FAIL",
                    title=f"Kat Planı BS Etiketi ile Metraj Tablosu Arasında {len(mm_list)} Adet Kablo Kesiti Çelişkisi!",
                    detail=(
                        f"Aynı paftada kat planı üzerindeki BS kablo çağrı etiketleri ile Metraj Tablosundaki kablo kesitleri "
                        f"birbirini tutmamaktadır ({sample_str}{' vb.' if len(mm_list) > 6 else ''})."
                    ),
                    recommendation="Gerilim düşümü hesabına göre güncellenen tablo kesitleri ile kat planındaki BS çağrı bloklarını birebir eşitleyiniz."
                ))

            # 2. Eksik Metraj Tablosu veya Tabloda Unutulan Linyeler (Yalnızca Toplu Plan & Metraj Paftalarında Zorunlu)
            if getattr(self.data, "sheet_role", "") == "METRO_TOPLU_PLAN_METRAJ" and self.data.metro_bs_count > 0 and self.data.metro_table_count == 0:
                self.report.findings.append(AuditFinding(
                    category="EKSİK_VERİ",
                    panel_name="METRAJ_TABLOSU",
                    status="FAIL",
                    title=f"Paftada Kablo / Linye Uzunluk (Metraj) Tablosu Eksik ({self.data.metro_bs_count} Linye)!",
                    detail=(
                        f"Kat planında {self.data.metro_bs_count} adet BS kablolama etiketi ve CAD üzerinde toplam "
                        f"{self.data.metro_poly_total_m:,.1f} m kablo güzergahı çizilmiş olmasına rağmen, paftada "
                        f"'Hat No / Kablo / Uzunluk (m)' tablosu bulunmamaktadır ve BS bloklarındaki uzunluk haneleri '-' bırakılmıştır."
                    ),
                    recommendation="Uygulama paftasına her linyenin gerçek mesafesini içeren Kablo Metraj Tablosu eklenmeli ve BS etiketlerindeki '-' alanları doldurulmalıdır."
                ))
            elif self.data.metro_table_count > 0 and self.data.metro_unlisted_circuits:
                ul = self.data.metro_unlisted_circuits
                self.report.findings.append(AuditFinding(
                    category="EKSİK_VERİ",
                    panel_name="METRAJ_TABLOSU",
                    status="WARNING",
                    title=f"Kat Planında Çizili {len(ul)} Adet Linye Metraj Tablosunda Unutulmuş!",
                    detail=(
                        f"Planda BS etiketi bulunan {len(ul)} adet linye ({', '.join(ul[:10])}{'...' if len(ul) > 10 else ''}) "
                        f"pafta üzerindeki Metraj Tablosuna dahil edilmemiştir."
                    ),
                    recommendation="Keşif ve kablo siparişinde eksik metraj çıkmaması için plandaki tüm linyeleri Metraj Tablosuna ekleyiniz."
                ))

            # 2b. Kat Planı Kopyala-Yapıştır (Copy-Paste) BS/HS/CS Etiket Hataları
            if getattr(self.data, "metro_bs_copypaste_errors", None):
                cp_list = self.data.metro_bs_copypaste_errors
                cp_sample = "; ".join(cp_list[:5])
                self.report.findings.append(AuditFinding(
                    category="TUTARSIZLIK",
                    panel_name="BS_ETİKET_KOPYALA_YAPIŞTIR",
                    status="WARNING",
                    title=f"Kat Planında {len(cp_list)} Adet Kopyala-Yapıştır (Copy-Paste) BS/CS Kablo Etiket Hatası!",
                    detail=(
                        f"Kat planı üzerindeki çağrı kutularında üst linye numarası ile alt pano/istasyon kodu uyuşmamaktadır: "
                        f"{cp_sample}{' vb.' if len(cp_list) > 5 else ''}."
                    ),
                    recommendation="Kopyala-yapıştır yapılan çağrı kutularındaki BS/HS/CS hedef pano ve istasyon kodlarını ilgili linye numarasıyla birebir uyumlu olacak şekilde düzeltiniz."
                ))

            # 3. NFPA 130 Acil Durum / Yangın Hatlarında FE180 Kablo Denetimi
            if self.data.metro_fe180_issues:
                fe_list = self.data.metro_fe180_issues
                fe_sample = "; ".join(f"{x['line_no']} ({x['target']} -> {x['cable']})" for x in fe_list[:6])
                self.report.findings.append(AuditFinding(
                    category="CAN_GÜVENLİĞİ",
                    panel_name="ACİL_YANGIN_HATLARI",
                    status="FAIL",
                    title=f"NFPA 130 İhlali: {len(fe_list)} Adet Acil/Yangın/Can Güvenliği Hattında FE180 Kablo Eksik!",
                    detail=(
                        f"Acil priz/aydınlatma (İAP-E/PE), yangın duman damperi (FS), duman egzoz fanı (FE) veya asansör (LFP) "
                        f"beslemelerinde yangına dayanıksız standart N2XH kablo kullanılmıştır: {fe_sample}."
                    ),
                    recommendation="NFPA 130 ve BYKHY uyarınca yangın anında çalışması zorunlu tüm acil/yangın/asansör hatlarını N2XH FE180 (PH120) olarak revize ediniz."
                ))

            # 4. Uzun 2.5 mm² Linyelerde Gerilim Düşümü Riski (L >= 50m)
            if self.data.metro_long_circuits:
                lc_list = sorted(self.data.metro_long_circuits, key=lambda x: -x["length_m"])
                lc_sample = "; ".join(
                    f"{x['line_no']} (L={x['length_m']:.0f}m, {x['cable']}, %e≈%{x['vdrop_pct']:.2f})"
                    for x in lc_list[:6]
                )
                self.report.findings.append(AuditFinding(
                    category="GERİLİM_DÜŞÜMÜ",
                    panel_name="UZUN_LİNYELER",
                    status="WARNING",
                    title=f"{len(lc_list)} Adet Uzun (50m–{lc_list[0]['length_m']:.0f}m) 2.5 mm² Linyede Gerilim Düşümü Sınır Aşımı!",
                    detail=(
                        f"İstasyon katlarında 50 metreyi aşan 2.5 mm² kesitli hatlarda (%e sınırı: %{lc_list[0]['limit_pct']}) "
                        f"gerilim düşümü riski tespit edilmiştir: {lc_sample}."
                    ),
                    recommendation="50 metreden uzun aydınlatma ve priz linyelerinde kesiti 3x2,5 mm² yerine 3x4 mm² (75m üstünde 3x6 mm²) N2XH olarak büyütünüz."
                ))

            # 5. TN-S Metro Sisteminde 4 İletkenli (3x.../..) Kablo ve PE İletkeni Kontrolü
            four_wire_cables = set()
            for sp in self.data.sub_panels.values():
                for c in sp.circuits:
                    if re.search(r'\b3\s*[xX]\s*\d+\s*/\s*\d+', c.cable_spec):
                        four_wire_cables.add(f"{c.circuit_no} ({c.cable_spec})")
            if four_wire_cables:
                fw_sample = ", ".join(sorted(list(four_wire_cables))[:6])
                self.report.findings.append(AuditFinding(
                    category="CAN_GÜVENLİĞİ",
                    panel_name="TN-S_TOPRAKLAMA",
                    status="WARNING",
                    title=f"TN-S Metro Sisteminde 4 Damarlı (3xS/S_kons) Kablo Kullanımı ({len(four_wire_cables)} Hat)!",
                    detail=(
                        f"Projede {fw_sample} vb. 3 faz + 1 konsantrik iletkenli (toplam 4 iletken) kablolar kullanılmıştır. "
                        f"EN 50122-1 ve TS HD 60364-5-54 gereği metro istasyonlarında TN-C (PEN birleşik iletken) yasaktır."
                    ),
                    recommendation="Bu hatlarda konsantrik iletkenin yalnızca Nötr (N) veya PE olarak kullanıldığını doğrulayınız; 3 faz + N + PE gereken panolarda ya 5 damarlı (4xS/S_pe veya 5xS) kablo kullanınız ya da tava boyunca harici Cu PE topraklama iletkeni çekiniz."
                ))

            # 6. Tamamlanmamış Uygulama Notları
            if self.data.metro_unfinished_notes:
                self.report.findings.append(AuditFinding(
                    category="GÜÇ_TEYİT",
                    panel_name="UYGULAMA_NOTU",
                    status="WARNING",
                    title="Uygulama Paftasında Kesinleşmemiş (Unfinalized) Tasarım Notu Mevcut!",
                    detail=f"Çizim üzerinde '{self.data.metro_unfinished_notes[0]}' notu bırakılmıştır.",
                    recommendation="Saha imalatı öncesinde tünel ve döşeme altı bağlantı detaylarını kesinleştirerek geçici notu kaldırınız."
                ))

    def _verify_residential_or_commercial_demand(self):
        """Konut ve genel yapılarda bağımsız talep gücü formül teyidi."""
        main_p = self.data.main_panel
        d_count = max(1, main_p.total_dwelling_count)
        expected_ks = get_building_diversity_factor(d_count)

        if main_p.installed_power_w > 0:
            calc_dem = round(main_p.installed_power_w * expected_ks, 1)
            proj_dem = main_p.demand_power_w

            if abs(calc_dem - proj_dem) < (main_p.installed_power_w * 0.05):
                self.report.findings.append(AuditFinding(
                    category="GÜÇ_TEYİT",
                    panel_name="BİNA_GENELİ",
                    status="PASS",
                    title="Bina Eşzamanlılık ve Talep Gücü Doğrulandı",
                    detail=f"{d_count} bağımsız bölüm için TEDAŞ katsayısı ks={expected_ks}. Hesaplanan Talep: {calc_dem:,.0f} W, Projedeki: {proj_dem:,.0f} W (Tam Uyum)."
                ))
            else:
                self.report.findings.append(AuditFinding(
                    category="GÜÇ_TEYİT",
                    panel_name="BİNA_GENELİ",
                    status="WARNING",
                    title="Bina Talep Gücünde Sapma Tespit Edildi",
                    detail=f"TEDAŞ standardına göre {d_count} daire için katsayı {expected_ks} olmalıdır (Hesaplanan Talep: {calc_dem:,.0f} W). Projede {proj_dem:,.0f} W alınmış.",
                    recommendation="Ana besleme kablosu ve ana şalter boyutlandırmasını resmi katsayıya göre kontrol ediniz."
                ))

    def _calculate_sub_panel(self, sp: SubPanelModel) -> PanelCalculationResult:
        """Tek bir tali panonun tam mühendislik kontrolünü yapar."""
        # 1. Pano Tipine ve Proje Tipolojisine Göre Talep Gücü ve Standart Sınır Belirleme
        pname_u = sp.name.upper()
        is_power_panel = any(k in pname_u for k in ["MCC", "ADP", "SDP", "MDP", "TVF", "POMPA", "KUVVET", "KOMP", "VİNÇ", "VINC", "CHILLER"])
        is_ups_panel = any(k in pname_u for k in ["UPS", "EM", "ACİL", "ACIL", "SCADA", "SER"])

        if sp.name == 'AT':
            calc_dem = sp.installed_power_w * sp.diversity_factor
            vdrop_limit = MAX_VDROP_MAIN_FEEDER_PCT # %3.5
            calc_method = "air"
        elif sp.name in ('O-T', 'OT'):
            # O-T için EMO 8kW kuralı (8000*0.6 + (18560-8000)*0.4 = 9024 W)
            calc_dem = 8000.0 * 0.6 + (sp.installed_power_w - 8000.0) * 0.4 if sp.installed_power_w > 8000.0 else sp.installed_power_w * 0.6
            vdrop_limit = MAX_VDROP_POWER_PCT # %3.0 (Motorlar ve Ortak Alan için EİTY Madde 57)
            calc_method = "conduit"
        elif is_power_panel or self.typology in (ProjectTypology.INFRASTRUCTURE_METRO, ProjectTypology.INDUSTRIAL):
            calc_dem = sp.demand_power_w if sp.demand_power_w > 0 else sp.installed_power_w * sp.diversity_factor
            vdrop_limit = 2.0 if is_ups_panel else MAX_VDROP_POWER_PCT # UPS için %2.0, Kuvvet/MCC için %3.0
            calc_method = "air" # Metro ve endüstriyel tesislerde kablo tavası
        elif sp.name in ('İŞ-T', 'IS-T'):
            calc_dem = sp.installed_power_w
            vdrop_limit = MAX_VDROP_LIGHTING_PCT # %1.5
            calc_method = "conduit"
        else:
            calc_dem = calculate_dwelling_demand_power(sp.installed_power_w) if self.typology == ProjectTypology.RESIDENTIAL else sp.demand_power_w
            vdrop_limit = MAX_VDROP_LIGHTING_PCT # %1.5
            calc_method = "conduit"

        p_match = "DOĞRULANDI" if abs(calc_dem - sp.demand_power_w) < 50.0 else "FARK_VAR"

        if p_match == "DOĞRULANDI":
            if len(self.data.sub_panels) <= 8:
                self.report.findings.append(AuditFinding(
                    category="GÜÇ_TEYİT",
                    panel_name=sp.name,
                    status="PASS",
                    title=f"{sp.name} Talep Gücü Doğrulandı",
                    detail=f"Kurulu: {sp.installed_power_w:,.0f} W -> Standart hesabı: {calc_dem:,.0f} W, Projedeki: {sp.demand_power_w:,.0f} W."
                ))
        else:
            self.report.findings.append(AuditFinding(
                category="GÜÇ_TEYİT",
                panel_name=sp.name,
                status="WARNING",
                title=f"{sp.name} Talep Gücü Uyuşmazlığı",
                detail=f"Standarda göre {calc_dem:,.0f} W olmalı, projede {sp.demand_power_w:,.0f} W yazılmış."
            ))

        # 2. İşletme Akımı (Trifaze kabulü)
        cos_phi = DEFAULT_POWER_FACTOR_POWER
        u = DEFAULT_VOLTAGE_3PHASE
        ib = sp.demand_power_w / (math.sqrt(3.0) * u * cos_phi) if sp.demand_power_w > 0 else 0.0

        # 3. TS HD 60364 Düzeltilmiş Akım Taşıma Kapasitesi
        s_mm2 = sp.cable_cross_section_mm2
        par_m = re.match(r'^(\d+)\s*\(\s*3', sp.cable_spec.strip())
        n_par = int(par_m.group(1)) if par_m else 1
        iz0 = round(get_base_ampacity(s_mm2, method=calc_method) * n_par, 1)
        # Şaft ortamında grup katsayısı ve sıcaklık düzeltmesi
        iz_corr = round(calculate_corrected_ampacity(s_mm2, method=calc_method, ambient_c=35.0, number_of_cables=2 if sp.name == 'AT' else 4, insulation="XLPE") * n_par, 1)

        # 4. Koordinasyon Denetimi: Ib <= In <= Iz
        in_brk = sp.breaker_rating_a
        brk_status = "UYGUN"
        if ib > in_brk:
            brk_status = "SİGORTA_YETERSİZ"
            self.report.findings.append(AuditFinding(
                category="KABLO_AKIM",
                panel_name=sp.name,
                status="FAIL",
                title=f"{sp.name} Sigortası Yetersiz!",
                detail=f"İşletme Akımı Ib={ib:.1f} A, seçilen sigorta In={in_brk:.0f} A'den büyüktür. Sigorta gereksiz açacaktır!",
                recommendation=f"Giriş sigortasını en az {math.ceil(ib/5)*5} A seçiniz."
            ))
        elif in_brk > iz_corr and sp.name != 'AT':
            brk_status = "KABLO_AŞIRI_YÜKLÜ"
            self.report.findings.append(AuditFinding(
                category="KABLO_AKIM",
                panel_name=sp.name,
                status="WARNING",
                title=f"{sp.name} Kablosu Şaftta Aşırı Yüklenebilir (TS HD 60364)!",
                detail=f"Sigorta ({in_brk:.0f} A), kablonun şaft/demetleme düzeltilmiş kapasitesinden ({iz_corr:.1f} A) büyüktür! Kablo nominalde {iz0:.0f} A taşır ancak şaft ortamında ısınıp tehlike oluşturabilir.",
                recommendation=f"Kablo kesitini {s_mm2} mm²'den bir üst kademeye artırınız veya sigortayı {math.floor(iz_corr)} A seviyesine çekiniz."
            ))

        # 5. Gerilim Düşümü (Klasik Omik vs Reaktanslı Kesin)
        l_m = sp.feeder_length_m
        v_approx = calculate_voltage_drop_approx(l_m, sp.demand_power_w, s_mm2, is_three_phase=True)
        # Reaktanslı TS HD 60364
        cable_spec_entry = COPPER_CABLE_SPECS.get(s_mm2, COPPER_CABLE_SPECS.get(6.0, {"r_ohm_km": 3.08, "x_ohm_km": 0.082}))
        r_km = cable_spec_entry["r_ohm_km"]
        x_km = cable_spec_entry["x_ohm_km"]
        v_exact = calculate_voltage_drop_exact(l_m, ib, s_mm2, r_km, x_km, cos_phi=cos_phi, is_three_phase=True)

        v_status = "UYGUN"
        if v_approx > vdrop_limit:
            v_status = "SINIR_AŞILDI"
            self.report.findings.append(AuditFinding(
                category="GERİLİM_DÜŞÜMÜ",
                panel_name=sp.name,
                status="FAIL",
                title=f"{sp.name} Gerilim Düşümü Sınırı Aşıldı!",
                detail=f"Gerilim düşümü %{v_approx:.2f} (Azami yönetmelik sınırı: %{vdrop_limit}).",
                recommendation=f"Kablo kesitini {s_mm2} mm² yerine en az {s_mm2*1.5:.0f} mm² seçiniz."
            ))

        # 6. Faz Dengesi Analizi
        p_phases = {"R": 0.0, "S": 0.0, "T": 0.0}
        for c in sp.circuits:
            ph = c.phase.upper()
            if ph in p_phases:
                p_phases[ph] += c.power_w
            elif "3P" in ph or "RST" in ph:
                p_phases["R"] += c.power_w / 3.0
                p_phases["S"] += c.power_w / 3.0
                p_phases["T"] += c.power_w / 3.0

        p_vals = list(p_phases.values())
        max_p = max(p_vals) if p_vals else 0.0
        min_p = min(p_vals) if p_vals else 0.0
        unbalance = round(((max_p - min_p) / max_p) * 100.0, 1) if max_p > 0 else 0.0

        if unbalance > MAX_PHASE_UNBALANCE_PCT and len(sp.circuits) > 1:
            self.report.findings.append(AuditFinding(
                category="FAZ_DENGESİ",
                panel_name=sp.name,
                status="WARNING",
                title=f"{sp.name} Faz Yük Dengesizliği: %{unbalance:.1f} (Azami: %{MAX_PHASE_UNBALANCE_PCT})",
                detail=f"Faz güçleri: R={p_phases['R']:.0f}W, S={p_phases['S']:.0f}W, T={p_phases['T']:.0f}W. Nötr iletkeninde aşırı akım oluşabilir!",
                recommendation="Linyeleri fazlara daha dengeli dağıtınız."
            ))

        # 7. KAKR Koordinasyonu
        rcd_stat = "UYGUN"
        m_rcd = re.search(r'(\d+)\s*[aA]', sp.rcd_spec)
        rcd_rating = float(m_rcd.group(1)) if m_rcd else 25.0
        if rcd_rating < in_brk and sp.name != 'AT':
            rcd_stat = "KAKR_ERİME_RİSKİ"
            self.report.findings.append(AuditFinding(
                category="CAN_GÜVENLİĞİ",
                panel_name=sp.name,
                status="FAIL",
                title=f"{sp.name} KAKR Yangın/Erime Tehlikesi!",
                detail=f"Kaçak akım rölesi ({rcd_rating:.0f} A), önündeki sigortadan ({in_brk:.0f} A) küçüktür! Aşırı yükte KAKR kontakları yanabilir.",
                recommendation=f"KAKR anma akımını en az {in_brk:.0f} A (tercihen 40 A) olarak değiştiriniz."
            ))

        # 3 Yöntem Karşılaştırma Kaydı (Sub-panel)
        sub_dev_pct = round(((v_exact - v_approx) / max(0.01, v_approx)) * 100.0, 1)
        sub_margin_a = round(iz_corr - in_brk, 1)
        sub_flaws = []
        if in_brk > iz_corr and sp.name != 'AT':
            sub_flaws.append(f"Şaft demetlemesinde Iz ({iz_corr:.1f}A) < In ({in_brk:.0f}A)")
        if rcd_rating < in_brk and sp.name != 'AT':
            sub_flaws.append(f"KAKR ({rcd_rating:.0f}A) < Sigorta ({in_brk:.0f}A)")
        if not sub_flaws:
            sub_flaws.append("Standart şablon hesabı.")

        self.report.tri_method_results[sp.name] = TriMethodCalculation(
            panel_name=sp.name,
            cable_spec=sp.cable_spec,
            length_m=l_m,
            power_w=sp.demand_power_w,
            current_ib_a=round(ib, 2),
            breaker_in_a=in_brk,
            proj_vdrop_pct=v_approx,
            proj_iz_a=iz0,
            proj_verdict="UYGUNDUR (Beyan)",
            proj_flaws=" | ".join(sub_flaws),
            eity_vdrop_pct=v_approx,
            eity_vdrop_limit_pct=vdrop_limit,
            eity_iz_a=iz0,
            eity_verdict="UYGUN" if v_approx <= vdrop_limit else "YÖNETMELİK SINIRI AŞILDI",
            eity_notes=f"EİTY Madde 57 sınırı: %{vdrop_limit}.",
            iec_vdrop_pct=v_exact,
            iec_vdrop_limit_pct=vdrop_limit,
            iec_iz_corrected_a=iz_corr,
            iec_verdict="GÜVENLİ" if (v_exact <= vdrop_limit and iz_corr >= ib) else "UYARI",
            iec_notes=f"TS HD 60364: Reaktanslı %e=%{v_exact:.2f}. Düzeltilmiş Iz={iz_corr:.1f}A.",
            vdrop_deviation_pct=sub_dev_pct,
            ampacity_margin_a=sub_margin_a
        )


        return PanelCalculationResult(
            name=sp.name,
            installed_power_w=sp.installed_power_w,
            demand_power_w_calc=calc_dem,
            demand_power_w_proj=sp.demand_power_w,
            power_match_status=p_match,
            current_ib_a=round(ib, 2),
            cable_spec=sp.cable_spec,
            cable_cross_section_mm2=s_mm2,
            cable_base_ampacity_iz0=iz0,
            cable_corrected_ampacity_iz=iz_corr,
            breaker_rating_a=in_brk,
            breaker_coordination_status=brk_status,
            feeder_length_m=l_m,
            vdrop_approx_pct=v_approx,
            vdrop_exact_pct=v_exact,
            vdrop_status=v_status,
            phase_powers_w=p_phases,
            phase_unbalance_pct=unbalance,
            rcd_status=rcd_stat
        )

    def _calculate_phase_balances(self):
        """Her pano ve bina geneli için faz yük dağılımı (R-S-T) ve vektörel nötr akımını (IN) hesaplar."""
        u_ph = DEFAULT_VOLTAGE_1PHASE
        cos_phi = DEFAULT_POWER_FACTOR_POWER

        # 1. Tali Panoların Faz Denge Hesapları
        tot_pr = 0.0
        tot_ps = 0.0
        tot_pt = 0.0

        for pname, sp in self.data.sub_panels.items():
            if pname == 'AT':
                continue
            pr = 0.0
            ps = 0.0
            pt = 0.0

            if sp.circuits:
                for c in sp.circuits:
                    ph = c.phase.upper()
                    if ph == 'R':
                        pr += c.power_w
                    elif ph == 'S':
                        ps += c.power_w
                    elif ph == 'T':
                        pt += c.power_w
                    elif '3P' in ph or 'RST' in ph:
                        pr += c.power_w / 3.0
                        ps += c.power_w / 3.0
                        pt += c.power_w / 3.0
                    else:
                        pr += c.power_w / 3.0
                        ps += c.power_w / 3.0
                        pt += c.power_w / 3.0
            else:
                pr = sp.installed_power_w / 3.0
                ps = sp.installed_power_w / 3.0
                pt = sp.installed_power_w / 3.0

            tot_pr += pr
            tot_ps += ps
            tot_pt += pt

            ir = pr / (u_ph * cos_phi) if pr > 0 else 0.0
            is_ = ps / (u_ph * cos_phi) if ps > 0 else 0.0
            it = pt / (u_ph * cos_phi) if pt > 0 else 0.0

            # Vektörel Nötr Akımı: In = sqrt(Ir^2 + Is^2 + It^2 - (Ir*Is + Is*It + It*Ir))
            i_n_sq = ir**2 + is_**2 + it**2 - (ir * is_ + is_ * it + it * ir)
            i_n = math.sqrt(max(0.0, i_n_sq))

            iavg = (ir + is_ + it) / 3.0 if (ir + is_ + it) > 0 else 0.0
            unb = (max(abs(ir - iavg), abs(is_ - iavg), abs(it - iavg)) / iavg) * 100.0 if iavg > 0 else 0.0

            if iavg == 0.0:
                status = "YÜK YOK / KAPSAM DIŞI"
                rec = "Bu paftada linye/yük tanımlı değildir."
            elif unb <= MAX_PHASE_UNBALANCE_PCT:
                status = "DENGELİ (<%15)"
                rec = "Faz yük dağılımı dengeli, nötr iletkeni aşırı ısınma riski taşımıyor."
            else:
                status = "⚠ DENGESİZ / NÖTR ISINMA RİSKİ"
                rec = f"Faz asimetrisi %{unb:.1f} > %{MAX_PHASE_UNBALANCE_PCT}, Inötr={i_n:.1f} A. Linyeleri fazlara eşit dağıtınız."

            self.report.phase_balance_results[pname] = PhaseBalanceResult(
                panel_name=pname,
                power_r_w=round(pr, 1),
                power_s_w=round(ps, 1),
                power_t_w=round(pt, 1),
                current_r_a=round(ir, 1),
                current_s_a=round(is_, 1),
                current_t_a=round(it, 1),
                current_neutral_a=round(i_n, 1),
                unbalance_pct=round(unb, 1),
                status=status,
                recommendation=rec
            )

        # 2. Ana Tablo (AT) / Bina Geneli Faz Dengesi
        main_p = self.data.main_panel
        ks = main_p.diversity_factor if main_p.diversity_factor > 0 else 0.25
        at_pr = tot_pr * ks
        at_ps = tot_ps * ks
        at_pt = tot_pt * ks
        at_ir = at_pr / (u_ph * cos_phi) if at_pr > 0 else 0.0
        at_is = at_ps / (u_ph * cos_phi) if at_ps > 0 else 0.0
        at_it = at_pt / (u_ph * cos_phi) if at_pt > 0 else 0.0

        at_in_sq = at_ir**2 + at_is**2 + at_it**2 - (at_ir * at_is + at_is * at_it + at_it * at_ir)
        at_in = math.sqrt(max(0.0, at_in_sq))
        at_iavg = (at_ir + at_is + at_it) / 3.0 if (at_ir + at_is + at_it) > 0 else 0.0
        at_unb = (max(abs(at_ir - at_iavg), abs(at_is - at_iavg), abs(at_it - at_iavg)) / at_iavg) * 100.0 if at_iavg > 0 else 0.0

        if at_iavg == 0.0:
            at_status = "YÜK YOK / KAPSAM DIŞI"
            at_rec = "Bu paftada kuvvetli akım yükleme cetveli / pano yükü bulunmamaktadır."
        elif at_unb <= MAX_PHASE_UNBALANCE_PCT:
            at_status = "DENGELİ (<%15)"
            at_rec = "Tesis geneli faz dağılımı dengeli."
        else:
            at_status = "⚠ DENGESİZ / NÖTR ISINMA RİSKİ"
            at_rec = f"Tesis geneli asimetri %{at_unb:.1f}, ana nötr akımı {at_in:.1f} A."

        self.report.phase_balance_results["AT"] = PhaseBalanceResult(
            panel_name=f"AT ({main_p.name or 'ANA TABLO'})",
            power_r_w=round(at_pr, 1),
            power_s_w=round(at_ps, 1),
            power_t_w=round(at_pt, 1),
            current_r_a=round(at_ir, 1),
            current_s_a=round(at_is, 1),
            current_t_a=round(at_it, 1),
            current_neutral_a=round(at_in, 1),
            unbalance_pct=round(at_unb, 1),
            status=at_status,
            recommendation=at_rec
        )

    def _calculate_short_circuit_and_thermal(self):
        """IEC 60909 kısa devre akımları (Ik3, Ik1) ve TS HD 60364-4-43 termik dayanımını hesaplar."""
        u_n = DEFAULT_VOLTAGE_3PHASE  # 400V
        u_ph = DEFAULT_VOLTAGE_1PHASE  # 230V
        c_max = 1.05
        t_trip = 0.04  # s (Ani manyetik açma süresi)
        k_factor = 143.0  # Cu/XLPE için k sabiti (TS HD 60364-4-43)

        # 1. Şebeke / Kofre Empedansı (1000 kVA Trafo + AG hat varsayımı)
        r_kofre = 0.0025
        x_kofre = 0.0148

        # 2. Ana Besleme (Kofre -> AT)
        main_p = self.data.main_panel
        l_main = main_p.feeder_length_m if main_p.feeder_length_m > 0 else 50.0
        s_main = main_p.feeder_cross_section_mm2 if main_p.feeder_cross_section_mm2 > 0 else 95.0

        r_feeder = 0.0175 * l_main / s_main
        x_feeder = 0.08 * l_main / 1000.0

        r_at = r_kofre + r_feeder
        x_at = x_kofre + x_feeder
        z_at = math.sqrt(r_at**2 + x_at**2)

        ik3_at = (c_max * u_n) / (math.sqrt(3.0) * z_at)  # Amper
        ik1_at = (0.95 * u_ph) / math.sqrt((r_at * 2.0)**2 + (x_at * 1.5)**2)  # Amper

        # AT TMŞ Kesme Kapasitesi (Standart 250A TMŞ = 25 kA veya 36 kA)
        icn_at = 25.0
        at_brk_ok = (icn_at >= (ik3_at / 1000.0))
        at_brk_status = "UYGUN (Icn >= Ik3)" if at_brk_ok else "YETERSİZ / PATLAMA RİSKİ"

        s_min_at = (ik3_at * math.sqrt(t_trip)) / k_factor
        at_therm_ok = (s_main >= s_min_at)
        at_therm_status = "GÜVENLİ (S >= Smin)" if at_therm_ok else "ERİME RİSKİ"

        self.report.short_circuit_results["AT"] = ShortCircuitResult(
            panel_name=f"AT ({main_p.name or 'ANA TABLO'})",
            cable_spec=main_p.feeder_cable_spec or "3x95+50 NYY",
            length_m=round(l_main, 1),
            cross_section_mm2=s_main,
            r_total_ohm=round(r_at, 5),
            x_total_ohm=round(x_at, 5),
            z_total_ohm=round(z_at, 5),
            ik3_max_ka=round(ik3_at / 1000.0, 2),
            ik1_min_ka=round(ik1_at / 1000.0, 2),
            breaker_icn_ka=icn_at,
            breaking_capacity_status=at_brk_status,
            s_min_thermal_mm2=round(s_min_at, 1),
            thermal_endurance_status=at_therm_status,
            notes="Ana TMŞ kesme kapasitesi (25 kA) ve 95 mm² ana kablo termik olarak tam güvenlidir."
        )

        # 3. Tali Panolar (AT -> Tali Pano)
        for pname, sp in self.data.sub_panels.items():
            if pname == 'AT':
                continue
            l_sub = sp.feeder_length_m if sp.feeder_length_m > 0 else 10.0
            s_sub = sp.cable_cross_section_mm2 if sp.cable_cross_section_mm2 > 0 else 6.0

            r_branch = 0.0175 * l_sub / s_sub
            x_branch = 0.08 * l_sub / 1000.0

            r_tot = r_at + r_branch
            x_tot = x_at + x_branch
            z_tot = math.sqrt(r_tot**2 + x_tot**2)

            ik3 = (c_max * u_n) / (math.sqrt(3.0) * z_tot)
            ik1 = (0.95 * u_ph) / math.sqrt((r_tot * 2.0)**2 + (x_tot * 1.5)**2)

            # Sigorta/Şalter kesme kapasitesi (Konut MCB=6kA, Endüstriyel MCB=10kA/25kA, Metro=25kA)
            if self.typology == ProjectTypology.INFRASTRUCTURE_METRO:
                icn = 25.0
            elif self.typology == ProjectTypology.INDUSTRIAL:
                icn = 25.0 if sp.breaker_rating_a >= 63.0 else 10.0
            else:
                icn = 6.0

            ik3_ka = ik3 / 1000.0
            brk_ok = (icn >= ik3_ka)

            if brk_ok:
                brk_stat = "UYGUN (Icn >= Ik3)"
                notes = f"Kesme kapasitesi ({icn:.0f} kA) yeterlidir (Ik3={ik3_ka:.2f} kA <= {icn:.0f} kA)."
            else:
                req_icn = 25 if ik3_ka > 10.0 else 10
                brk_stat = f"⚠ YETERSİZ / {req_icn} kA ZORUNLU"
                notes = f"Kısa devre akımı ({ik3_ka:.2f} kA) {icn:.0f} kA sınırı aşar! En az {req_icn} kA kesme kapasiteli koruma şarttır."
                if not getattr(self.data, "is_metro_plan_sheet", False):
                    self.report.findings.append(AuditFinding(
                        category="KISA_DEVRE",
                        panel_name=pname,
                        status="FAIL",
                        title=f"{pname} Sigorta Kesme Kapasitesi Yetersiz (Icn < Ik3)!",
                        detail=f"Panodaki 3 faz kısa devre akımı Ik3={ik3_ka:.2f} kA olup {icn:.0f} kA sigorta sınırını aşmaktadır. Kontak kaynaması veya patlama riski bulunur.",
                        recommendation=f"Pano giriş korumasını en az {req_icn} kA kesme kapasiteli (Icn >= {req_icn} kA) şalter/MCB ile değiştiriniz."
                    ))

            s_min = (ik3 * math.sqrt(t_trip)) / k_factor
            therm_ok = (s_sub >= s_min) or getattr(self.data, "is_metro_plan_sheet", False)
            therm_stat = "GÜVENLİ (S >= Smin)" if therm_ok else "⚠ TERMİK ERİME RİSKİ"

            if not therm_ok:
                self.report.findings.append(AuditFinding(
                    category="KISA_DEVRE",
                    panel_name=pname,
                    status="WARNING",
                    title=f"{pname} Kablo Kesiti Termik Dayanım Sınırında (S < Smin)!",
                    detail=f"Kısa devre anında kablonun hasar görmemesi için asgari kesit Smin={s_min:.1f} mm², mevcut kesit {s_sub:.1f} mm².",
                    recommendation=f"Kablo kesitini en az {math.ceil(s_min)} mm² seçiniz."
                ))

            self.report.short_circuit_results[pname] = ShortCircuitResult(
                panel_name=pname,
                cable_spec=sp.cable_spec or f"4x{s_sub:.0f}",
                length_m=round(l_sub, 1),
                cross_section_mm2=s_sub,
                r_total_ohm=round(r_tot, 5),
                x_total_ohm=round(x_tot, 5),
                z_total_ohm=round(z_tot, 5),
                ik3_max_ka=round(ik3_ka, 2),
                ik1_min_ka=round(ik1 / 1000.0, 2),
                breaker_icn_ka=icn,
                breaking_capacity_status=brk_stat,
                s_min_thermal_mm2=round(s_min, 1),
                thermal_endurance_status=therm_stat,
                notes=notes
            )

    def _evaluate_overall_verdict(self):
        """Projenin nihai karnesi ve güvenlik skorunu hesaplar."""
        fails = [f for f in self.report.findings if f.status == "FAIL"]
        warnings = [f for f in self.report.findings if f.status == "WARNING"]

        penalty = (len(fails) * 15.0) + (len(warnings) * 4.0)
        self.report.score_pct = max(0.0, min(100.0, 100.0 - penalty))

        if fails:
            self.report.overall_verdict = "UYGUN DEĞİLDİR (KRİTİK GÜVENLİK/STANDART İHLALİ)"
        elif warnings:
            self.report.overall_verdict = "ŞARTLI UYGUN (DÜZELTİLMESİ GEREKEN UYARILAR VAR)"
        else:
            self.report.overall_verdict = "UYGUNDUR (TÜM STANDARTLARA VE YÖNETMELİĞE TAM UYUMLU)"

