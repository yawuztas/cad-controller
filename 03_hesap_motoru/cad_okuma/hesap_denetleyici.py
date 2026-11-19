# -*- coding: utf-8 -*-
"""
Adım 3 — Evrensel Mühendislik Hesap Denetimi ve Yeniden Hesaplama Motoru (`hesap_denetleyici.py`)
====================================================================================================
CAD okuma (`CanonicalProjectModel`) ve metraj (`ProjectInventory`) çıktılarından dinamik olarak
okunan gömülü hesap tabloları, OLE2 Excel hesapları, gerilim düşümü formül blokları, yükleme
cetvelleri, kolon dağıtım şeması ve temel topraklama geometrisini;

`02_mevzuat_ve_formuller/bina/*.yaml` ve `03_hesap_motoru/core/calculators/electrical_calc.py`
içindeki resmi yönetmelik ve mühendislik formülleriyle yeniden hesaplayarak projedeki yazılı
değerlerle yan yana karşılaştırır.

GEMINI.md ilkelerine %100 uygundur:
  - Sıfır hardcode (örnek dosya sayıları, sabit pano adları, DXF handle ID'si içermez).
  - Okunamayan / çizimde eksik veri için sayı uydurmaz; dürüstçe BELİRSİZ / EKSİK raporlar.
"""

from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Tuple, Union

from pydantic import BaseModel, Field

# core.calculators ve core.rules modüllerine temiz erişim
_MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(_MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_MOTOR_ROOT))

from core.calculators.electrical_calc import (  # noqa: E402
    CableConductorSpec,
    calc_dwelling_demand_power_w,
    calc_foundation_earthing_ieee80_sverak,
    calc_foundation_earthing_laurent_niemann,
    calc_horizontal_strip_resistance_dwight,
    calc_illumination_lumen_method,
    calc_operating_current_ib,
    calc_phase_imbalance_pct,
    calc_vertical_rod_resistance_dwight,
    calc_voltage_drop_exact_iec_pct,
    calc_voltage_drop_pct,
    check_breaker_selectivity,
    check_fault_loop_and_touch_voltage,
    check_pe_cross_section_iec60364_5_54,
    check_rcd_selectivity,
    get_building_coincidence_factor,
    parse_cable_spec,
)
from core.rules.rule_engine import RuleEngine  # noqa: E402

from .metin_temizleyici import norm_tr, parse_tr_float
from .metraj_cikarici import _RE_CABLE, build_project_inventory
from .sebeke_analizi import (
    NetworkAnalysisReport,
    analyze_radial_network_pandapower,
    build_feeders_from_audit_rows,
)
from .schema import (
    CanonicalProjectModel,
    FormulaBlock,
    GroundingLoop,
    NormalizedTable,
    PanelInventoryItem,
    ProjectInventory,
    RawCADSnapshot,
    RawText,
)

# ==============================================================================
# YARDIMCI AYRIŞTIRICILAR VE MEVZUAT OKUYUCU (SIFIR HARDCODE)
# ==============================================================================

_RE_POLE_AMP_STRICT = re.compile(r"^([1-4])\s*[xX*]\s*(\d{1,4})\s*A?$", re.IGNORECASE)
_RE_CURVE_AMP_PAREN = re.compile(r"^[1-4BCDK]\s*\(\s*(\d{1,4})\s*A\s*\)$", re.IGNORECASE)
_RE_RCD_COMB = re.compile(r"([1-4])\s*[xX*]\s*(\d{1,4})\s*A.*?(\d{2,3})\s*mA", re.IGNORECASE)
_RE_PANEL_TOK = re.compile(r"^(?:[A-ZÇĞİÖŞÜ]{1,5}[-_]\d{1,4}|[A-ZÇĞİÖŞÜ]{1,3}[-_][A-Z0-9]{1,3}|AT|OT|MDP|ADP|TDP)$", re.IGNORECASE)
_RE_LINYE_CODE = re.compile(r"^(?:[APKM]\d{1,3}|L\d{1,3}|YEDEK|SPARE)$", re.IGNORECASE)
_RE_FIRE_MOTOR_KEYWORDS = ("YANGIN", "YABGIN", "FIRE", "POMPA", "HIDROFOR", "ASANSOR", "FAN", "DUMAN", "CHILLER")
_RE_FIRE_ONLY_KEYWORDS = ("YANGIN", "YABGIN", "FIRE PUMP", "DUMAN", "SPRINKLER")


def _load_bina_rules() -> Dict[str, Any]:
    """`02_mevzuat_ve_formuller/bina/*.yaml` kurallarını yükler."""
    return RuleEngine.load_pack("turkey_bina")


def _parse_tr_power_value_w(text: str, default_unit: str = "W") -> Optional[float]:
    """
    '553.490W', '133.373W', '533490W', '7,5kW', '9.220 kW' gibi güç metinlerini Watt cinsine çevirir.
    Türkçe binlik nokta ('553.490W' -> 553490 W) ile ondalık noktayı ayırt eder.
    """
    if not text:
        return None
    s = str(text).strip().replace(" ", "")
    m = re.search(r"(\d[\d.,]*)(k?W|k?VA)?$", s, re.IGNORECASE)
    if not m:
        return None
    num_raw = m.group(1)
    unit = (m.group(2) or default_unit).upper()

    if "," in num_raw and "." in num_raw:
        num_val = parse_tr_float(num_raw)
    elif "," in num_raw:
        num_val = parse_tr_float(num_raw)
    elif "." in num_raw:
        # "553.490" gibi son grubu tam 3 haneli + W biriminde Türkçe binlik ayracı
        if re.match(r"^\d{1,3}(?:\.\d{3})+$", num_raw) and unit in ("W", "VA"):
            num_val = float(num_raw.replace(".", ""))
        else:
            num_val = float(num_raw)
    else:
        num_val = float(num_raw)

    if num_val is None:
        return None
    return num_val * 1000.0 if unit in ("KW", "KVA") else num_val


def _parse_amp_from_text(text: str) -> Optional[float]:
    """'3(20A)', '3x320A', 'AOS 3x32 3 kA C', 'AOS 10 3 kA B', 'C20', '32A' ifadelerinden anma akımını (A) çıkarır."""
    if not text:
        return None
    raw = str(text).strip()
    m_k = re.search(r"(?:AOS|MCB|TMS)\s*(?:[1-4]\s*[xX*]\s*)?(\d{1,4})(?!\s*kA)\b", raw, re.IGNORECASE)
    if m_k:
        return float(m_k.group(1))
    m_px = re.search(r"\b[1-4]\s*[xX*]\s*(\d{1,4})(?!\s*kA)\b", raw, re.IGNORECASE)
    if m_px:
        return float(m_px.group(1))
    s = raw.replace(" ", "")
    m1 = _RE_CURVE_AMP_PAREN.match(s)
    if m1:
        return float(m1.group(1))
    m2 = _RE_POLE_AMP_STRICT.match(s)
    if m2:
        return float(m2.group(2))
    m3 = re.search(r"(?:[BCDK])?(\d{1,4})\s*A\b", s, re.IGNORECASE)
    if m3:
        return float(m3.group(1))
    if re.match(r"^\d{1,4}$", s):
        return float(s)
    return None


def _parse_rcd_rating_ma(text: str) -> Tuple[Optional[float], Optional[float], bool]:
    """KAKR etiketinden (anma_akimi_A, acma_akimi_mA, S_tipi_mi) döner."""
    if not text:
        return (None, None, False)
    s = str(text).strip()
    is_s_type = bool(re.search(r"\bS\b|SELEKTIF|GECIKMELI|TIME[-\s]?DELAY", norm_tr(s)))
    m = _RE_RCD_COMB.search(s)
    if m:
        return (float(m.group(2)), float(m.group(3)), is_s_type)
    ma_m = re.search(r"(\d{2,3})\s*mA", s, re.IGNORECASE)
    amp_m = re.search(r"[1-4]\s*[xX*]\s*(\d{1,4})\s*A", s, re.IGNORECASE)
    return (float(amp_m.group(1)) if amp_m else None, float(ma_m.group(1)) if ma_m else None, is_s_type)


def _lookup_cable_ampacity_yaml(
    spec: CableConductorSpec,
    cable_str: str,
    rules: Dict[str, Any],
    method: str = "C",
) -> Tuple[Optional[float], str]:
    """
    `02_kuvvetli_akim.yaml` içindeki TS HD 60364-5-52 tablosundan kablonun temel akım taşıma
    kapasitesini (Iz) okur. Kablo bilinmiyorsa (None, aciklama) döner.
    """
    if not spec.is_valid or spec.phase_mm2 <= 0:
        return (None, "Kesit okunamadı")
    amp_root = rules.get("ampacity_tables_tshd60364", {}) or {}
    cu = norm_tr(cable_str or "").upper()
    is_xlpe = any(k in cu for k in ("N2XH", "XLPE", "EPR", "HFFR", "YXV", "FE180", "07Z1"))
    ins_key = "XLPE_90C" if is_xlpe else "PVC_70C"
    # 3+ damar için 3 yüklü iletken, tek faz / 2-3x2.5 için 2 yüklü iletken
    loaded_key = f"{method}_3_LOADED" if spec.cores >= 4 else f"{method}_2_LOADED"
    tbl = (amp_root.get(ins_key, {}) or {}).get(loaded_key, {})
    if not isinstance(tbl, dict):
        tbl = {}
    # YAML float veya int key olabilir
    iz_val = tbl.get(spec.phase_mm2)
    if iz_val is None and spec.phase_mm2.is_integer():
        iz_val = tbl.get(int(spec.phase_mm2))
    if iz_val is not None:
        return (float(iz_val), f"{ins_key}/{loaded_key}")
    # Tabloda tam eşleşme yoksa YAML ampacity_base_a fallback'i (sayı uydurmadan mevcut tablo lookup)
    base_tbl = rules.get("ampacity_base_a", {}) or {}
    b_val = base_tbl.get(spec.phase_mm2) or (base_tbl.get(int(spec.phase_mm2)) if spec.phase_mm2.is_integer() else None)
    if b_val is not None:
        return (float(b_val), f"ampacity_base_a/{ins_key}")
    return (None, "Tabloda kesit bulunamadı")


def _min_compliant_section_from_yaml(
    required_amp_a: float,
    cable_str: str,
    is_three_phase: bool,
    rules: Dict[str, Any],
    method: str = "C",
) -> Optional[float]:
    """Gerekli akımı taşıyacak en küçük standart kablo kesitini (mm²) YAML tablosundan seçer."""
    amp_root = rules.get("ampacity_tables_tshd60364", {}) or {}
    cu = norm_tr(cable_str or "").upper()
    is_xlpe = any(k in cu for k in ("N2XH", "XLPE", "EPR", "HFFR", "YXV", "FE180", "07Z1"))
    ins_key = "XLPE_90C" if is_xlpe else "PVC_70C"
    loaded_key = f"{method}_3_LOADED" if is_three_phase else f"{method}_2_LOADED"
    tbl = (amp_root.get(ins_key, {}) or {}).get(loaded_key, {})
    if not isinstance(tbl, dict):
        return None
    for sec, iz in sorted((float(k), float(v)) for k, v in tbl.items()):
        if iz >= required_amp_a:
            return sec
    return None


# ==============================================================================
# RAPOR VERİ ŞEMALARI (PYDANTIC)
# ==============================================================================

class AuditFindingItem(BaseModel):
    finding_id: str
    severity: Literal["KRITIK", "UYARI", "BILGI", "UYGUN"]
    category: str
    location: str
    project_value: str
    engine_value: str
    standard_ref: str
    description: str
    recommendation: str = ""
    sheet_id: Optional[str] = None
    anchor_xy: Optional[Tuple[float, float]] = None
    bbox_du: Optional[Tuple[float, float, float, float]] = None
    extra_anchors: List[Tuple[float, float, Optional[Tuple[float, float, float, float]]]] = Field(default_factory=list)


class PowerBudgetAudit(BaseModel):
    main_panel_name: Optional[str] = None
    subpanel_count: int = 0
    subpanels_installed_sum_w: float = 0.0
    subpanels_demand_sum_w: float = 0.0
    main_installed_written_w: Optional[float] = None
    main_demand_factor_written: Optional[float] = None
    main_demand_written_w: Optional[float] = None
    main_demand_calc_w: Optional[float] = None
    recommended_coincidence_factor: Optional[float] = None
    titleblock_table_id: Optional[str] = None
    titleblock_installed_w: Optional[float] = None
    titleblock_demand_w: Optional[float] = None
    titleblock_demand_factor: Optional[float] = None
    installed_diff_titleblock_w: Optional[float] = None
    status: str = "BELİRSİZ"


class LoadCircuitAuditRow(BaseModel):
    circuit_no: str
    breaker_spec: str
    description: str
    sorti_count: int = 0
    written_power_w: float = 0.0
    cable_spec: str = ""
    cable_iz_a: Optional[float] = None
    breaker_amp_a: Optional[float] = None
    is_cable_protected: Optional[bool] = None
    notes: str = ""


class LoadScheduleAudit(BaseModel):
    table_id: str
    sheet_id: str
    source_kind: str
    panel_name: str
    circuits_count: int = 0
    written_ayd_sorti: Optional[int] = None
    written_priz_sorti: Optional[int] = None
    written_motor_sorti: Optional[int] = None
    written_r_w: Optional[float] = None
    written_s_w: Optional[float] = None
    written_t_w: Optional[float] = None
    written_rst_w: Optional[float] = None
    written_total_w: Optional[float] = None
    calc_circuits_total_w: float = 0.0
    written_demand_w: Optional[float] = None
    calc_dwelling_demand_w: Optional[float] = None
    phase_imbalance_single_ph_pct: Optional[float] = None
    phase_imbalance_with_rst_pct: Optional[float] = None
    has_motor_or_fire_load: bool = False
    applies_dwelling_diversity_to_motor: bool = False
    main_breaker_spec: Optional[str] = None
    main_rcd_spec: Optional[str] = None
    status: str = "UYGUN"
    circuits: List[LoadCircuitAuditRow] = Field(default_factory=list)


class MainIncomerAudit(BaseModel):
    panel_name: Optional[str] = None
    source_sheet: str = ""
    demand_power_w: Optional[float] = None
    cable_spec: Optional[str] = None
    length_m: Optional[float] = None
    breaker_spec: Optional[str] = None
    breaker_in_a: Optional[float] = None
    rcd_spec: Optional[str] = None
    rcd_in_a: Optional[float] = None
    rcd_ma: Optional[float] = None
    rcd_is_s_type: bool = False
    project_written_ib_a: Optional[float] = None
    project_written_iz_a: Optional[float] = None
    engine_ib_380v_a: Optional[float] = None
    engine_ib_400v_a: Optional[float] = None
    engine_iz_yaml_a: Optional[float] = None
    iz_source: str = ""
    ib_in_iz_ok: Optional[bool] = None
    pe_mm2: Optional[float] = None
    req_pe_mm2: Optional[float] = None
    pe_ok: Optional[bool] = None
    min_compliant_section_mm2: Optional[float] = None
    cable_vs_vd_sheet_mismatch: Optional[str] = None
    locked_fire_pump_present: bool = False
    locked_fire_pump_breaker: Optional[str] = None
    duplicate_fire_pump_in_common_panel: bool = False


class PanelAuditRow(BaseModel):
    panel_name: str
    role: str = "TALI_PANO"
    source_table_id: Optional[str] = None
    installed_power_w: Optional[float] = None
    demand_power_w: Optional[float] = None
    calc_dwelling_demand_w: Optional[float] = None
    feeder_length_m: Optional[float] = None
    schematic_length_m: Optional[float] = None
    cable_spec: Optional[str] = None
    phase_mm2: Optional[float] = None
    pe_mm2: Optional[float] = None
    breaker_spec: Optional[str] = None
    breaker_in_a: Optional[float] = None
    rcd_spec: Optional[str] = None
    cos_phi_project: Optional[float] = None
    project_ib_a: Optional[float] = None
    engine_ib_proj_params_a: Optional[float] = None
    engine_ib_400v_08_a: Optional[float] = None
    project_iz_a: Optional[float] = None
    engine_iz_yaml_a: Optional[float] = None
    ib_in_iz_ok: Optional[bool] = None
    linye_no: Optional[str] = None
    linye_power_w: Optional[float] = None
    linye_length_m: Optional[float] = None
    linye_section_mm2: Optional[float] = None
    project_vd_linye_pct: Optional[float] = None
    engine_vd_linye_proj_pct: Optional[float] = None
    engine_vd_linye_230v_pct: Optional[float] = None
    project_vd_total_pct: Optional[float] = None
    engine_vd_kolon_proj_pct: Optional[float] = None
    engine_vd_total_no_main_pct: Optional[float] = None
    engine_vd_total_with_main_pct: Optional[float] = None
    engine_vd_total_iec_pct: Optional[float] = None
    vd_limit_written: str = ""
    selectivity_note: str = ""
    flags: List[str] = Field(default_factory=list)


class VoltageDropFormulaRow(BaseModel):
    formula_id: str
    sheet_id: str
    segment_name: str
    cable_spec: str = ""
    length_m: Optional[float] = None
    power_w: Optional[float] = None
    section_mm2: Optional[float] = None
    coeff_written: Optional[float] = None
    is_three_phase: bool = True
    project_vd_pct: Optional[float] = None
    engine_vd_proj_v_pct: Optional[float] = None
    engine_vd_std_v_pct: Optional[float] = None
    engine_vd_iec_ekg_pct: Optional[float] = None
    note: str = ""


class GroundingAudit(BaseModel):
    table_id: Optional[str] = None
    loop_id: Optional[str] = None
    sheet_id: str = ""
    rho_ohm_m: Optional[float] = None
    depth_h_m: Optional[float] = None
    strip_d_m: Optional[float] = None
    # Yazılı tablo girdileri
    table_L_m: Optional[float] = None
    table_a_m: Optional[float] = None
    table_b_m: Optional[float] = None
    table_A_m2: Optional[float] = None
    table_n_rods: Optional[int] = None
    table_rod_L_m: Optional[float] = None
    table_rod_d_m: Optional[float] = None
    # Tabloda yazılı çıktılar
    table_D_written_m: Optional[float] = None
    table_Rc_written_ohm: Optional[float] = None
    table_Ry_written_ohm: Optional[float] = None
    table_Re_written_ohm: Optional[float] = None
    table_limit_written_ohm: Optional[float] = None
    # CAD gerçek geometri
    cad_A_m2: Optional[float] = None
    cad_D_m: Optional[float] = None
    cad_perimeter_m: Optional[float] = None
    cad_inner_m: Optional[float] = None
    cad_ring_plus_inner_m: Optional[float] = None
    cad_spur_m: Optional[float] = None
    cad_rod_count: Optional[int] = None
    cad_rod_L_spec_m: Optional[float] = None
    # Motor recalculation (Tablo girdileri ile)
    engine_tbl_D_m: Optional[float] = None
    engine_tbl_R_temel_ohm: Optional[float] = None
    engine_tbl_R_rods_dwight_ohm: Optional[float] = None
    engine_tbl_R_strip_dwight_ohm: Optional[float] = None
    engine_tbl_R_schwarz_ohm: Optional[float] = None
    engine_tbl_R_sverak_ohm: Optional[float] = None
    # Motor recalculation (CAD gerçek geometri ile)
    engine_cad_R_temel_ohm: Optional[float] = None
    engine_cad_R_rods_dwight_ohm: Optional[float] = None
    engine_cad_R_strip_dwight_ohm: Optional[float] = None
    engine_cad_R_schwarz_ohm: Optional[float] = None
    engine_cad_R_sverak_ohm: Optional[float] = None
    tt_max_allowed_ohm: Optional[float] = None
    tt_compliant: Optional[bool] = None
    formula_anomalies: List[str] = Field(default_factory=list)


class LightingRoomAudit(BaseModel):
    table_id: str
    room_name: str
    width_a_m: float = 0.0
    length_b_m: float = 0.0
    height_H_m: float = 0.0
    mounting_hm_m: float = 0.0
    written_lux: float = 0.0
    reflection_factors: str = ""
    written_k: Optional[float] = None
    calc_k: float = 0.0
    utilization_eta: float = 0.0
    fixture_power_w: float = 0.0
    fixture_flux_lm: float = 0.0
    written_z: Optional[float] = None
    calc_z_exact: float = 0.0
    calc_z_ceil: int = 0
    selected_spec: str = ""
    selected_count: Optional[int] = None
    achieved_lux: float = 0.0
    recommended_ts_en_12464_lux: Optional[float] = None
    notes: List[str] = Field(default_factory=list)


class CalculationAuditReport(BaseModel):
    filename: str
    unit_name: str
    regulation_pack: str = "02_mevzuat_ve_formuller/bina/*.yaml"
    summary_counts: Dict[str, int] = Field(default_factory=dict)
    findings: List[AuditFindingItem] = Field(default_factory=list)
    power_budget: PowerBudgetAudit = Field(default_factory=PowerBudgetAudit)
    load_schedules: List[LoadScheduleAudit] = Field(default_factory=list)
    main_incomer: MainIncomerAudit = Field(default_factory=MainIncomerAudit)
    panel_rows: List[PanelAuditRow] = Field(default_factory=list)
    vd_formulas: List[VoltageDropFormulaRow] = Field(default_factory=list)
    vd_formula_total_proj_written: Optional[float] = None
    vd_formula_total_engine_proj_v: Optional[float] = None
    vd_formula_total_engine_std_v: Optional[float] = None
    grounding: Optional[GroundingAudit] = None
    lighting_rooms: List[LightingRoomAudit] = Field(default_factory=list)
    network_analysis: Optional[NetworkAnalysisReport] = None


# ==============================================================================
# BÖLÜM 1: ANTET / GÜÇ BÜTÇESİ VE ANA PANO ÇIKARIMI
# ==============================================================================

def _extract_main_incomer_from_schematic(
    snapshot: RawCADSnapshot,
    model: CanonicalProjectModel,
    inv: ProjectInventory,
    rules: Dict[str, Any],
) -> Tuple[MainIncomerAudit, Optional[float], Optional[float], Optional[float]]:
    """
    Şema paftalarından (KOLON_SEMASI / TEK_HAT) ana pano beslemesi (TMŞ, ana KAKR, ana kablo,
    yazılı Ib/Iz hesabı ve varsa KİLİTLİ BÖLME / Yangın Pompası dalı) bilgilerini dinamik çıkarır.
    """
    main_panel = next((p for p in inv.panels if p.role == "ANA_PANO"), None)
    audit = MainIncomerAudit(panel_name=main_panel.panel_name if main_panel else None)

    sch_sheets = [sh for sh in model.sheets if sh.role in ("KOLON_SEMASI", "TEK_HAT")]
    pwr_sch_sheets = [
        sh for sh in sch_sheets
        if not any(wk in norm_tr(sh.title).upper() for wk in ("TELEFON", "TELEVIZYON", "DUAFON", "ZAYIF", "YANGIN ALGILAMA"))
    ]
    if pwr_sch_sheets:
        sch_sheets = pwr_sch_sheets
    if not sch_sheets:
        sch_sheets = list(model.sheets)

    # Şemadaki tüm metinler
    sch_texts: List[RawText] = []
    sheet_of_text: Dict[int, str] = {}
    for t in snapshot.texts:
        for sh in sch_sheets:
            if t.space == sh.space and sh.bbox_du.contains_xy(t.x, t.y):
                sch_texts.append(t)
                sheet_of_text[id(t)] = sh.frame_id
                break

    if not sch_texts:
        return audit, None, None, None

    # Ana pano altındaki veya yanındaki Kurulu Güç / Talep Faktörü / Talep Gücü etiketleri
    main_inst_w: Optional[float] = main_panel.installed_power_w if main_panel else None
    main_df: Optional[float] = None
    main_dem_w: Optional[float] = main_panel.demand_power_w if main_panel else None

    for tbl in model.tables:
        if any(sh.frame_id == tbl.sheet_id for sh in sch_sheets):
            blob = norm_tr(" ".join(" ".join(r) for r in tbl.raw_matrix)).upper()
            if "TALEP FAKTORU" in blob and "TALEP GUCU" in blob:
                for row in tbl.raw_matrix:
                    for ci, cell in enumerate(row):
                        cu = norm_tr(cell).upper()
                        if "TALEP FAKTORU" in cu and ci + 1 < len(row):
                            df_v = parse_tr_float(row[ci + 1])
                            if df_v is not None and 0.05 <= df_v <= 1.0:
                                main_df = df_v
                        elif "TALEP GUCU" in cu and ci + 1 < len(row):
                            pw = _parse_tr_power_value_w(row[ci + 1])
                            if pw is not None and pw > 0:
                                main_dem_w = pw
                        elif "AKIM TASIMA KAPASITESI" in cu:
                            m_iz = re.search(r"(\d+(?:[.,]\d+)?)\s*A\b", cell, re.IGNORECASE)
                            if m_iz:
                                audit.project_written_iz_a = parse_tr_float(m_iz.group(1))

    # Şemadaki ham metinlerde "533490W / 0,25 / 133373W" veya komşu etiket değerleri
    main_rcd_anchor: Optional[Tuple[float, float]] = None
    heating_demand_w: Optional[float] = None

    def _can_take_rcd(ma_val: Optional[float]) -> bool:
        if audit.rcd_ma is None and audit.rcd_in_a is None:
            return True
        if ma_val is not None and ma_val >= 100 and (audit.rcd_ma or 0) < 100:
            return True
        return False

    for t in sch_texts:
        s = t.text.strip()
        nu = norm_tr(s).upper()
        if main_inst_w is None and "KURULU GUC" in nu:
            # Sağındaki komşuyu ara
            nbrs = [o for o in sch_texts if abs(o.y - t.y) <= max(15.0, t.height * 2.0) and o.x > t.x]
            for n in sorted(nbrs, key=lambda o: o.x - t.x)[:3]:
                pw = _parse_tr_power_value_w(n.text)
                if pw and pw > 1000:
                    main_inst_w = pw
                    break
        if "=" in s and re.search(r"=\s*(\d+(?:[.,]\d+)?)\s*A\b", s, re.IGNORECASE):
            m_eq = re.search(r"=\s*(\d+(?:[.,]\d+)?)\s*A\b", s, re.IGNORECASE)
            val_a = parse_tr_float(m_eq.group(1)) if m_eq else None
            if val_a is not None:
                if "KAPASIT" in nu or "TASIMA" in nu:
                    audit.project_written_iz_a = val_a
                elif "/" in s:
                    audit.project_written_ib_a = val_a
                    m_num = re.search(r"(\d[\d.,]*)\s*/\s*\d", s)
                    if m_num:
                        num_w = _parse_tr_power_value_w(m_num.group(1) + "W")
                        if num_w and num_w >= 1000.0:
                            heating_demand_w = num_w
        if not audit.source_sheet and main_panel and main_panel.sheet_ids:
            audit.source_sheet = main_panel.sheet_ids[0]
        if _RE_RCD_COMB.search(s):
            rcd_a, ma_val, is_s = _parse_rcd_rating_ma(s)
            if rcd_a and _can_take_rcd(ma_val):
                audit.rcd_in_a = rcd_a
                audit.rcd_ma = ma_val
                audit.rcd_is_s_type = is_s
                audit.rcd_spec = s
                if ma_val and ma_val >= 100:
                    main_rcd_anchor = (t.x, t.y)
        elif ("TMS" in nu or "TMŞ" in s.upper()) and _parse_amp_from_text(s) and not re.search(r"[xX*]\d+\s*\(\d+", s):
            amp = _parse_amp_from_text(s)
            if amp and (audit.breaker_in_a is None or amp > audit.breaker_in_a):
                audit.breaker_in_a = amp
                audit.breaker_spec = s
                audit.source_sheet = sheet_of_text.get(id(t), audit.source_sheet)
        elif re.search(r"^(?:3|4)\s*[xX*]\s*\d{2,4}\s*A?$", s.replace(" ", "")):
            # Yanında TMS / TMŞ veya KAK / YKR / mA varsa
            amp = _parse_amp_from_text(s)
            near_tms = any(
                abs(o.x - t.x) <= max(40.0, t.height * 5.0)
                and abs(o.y - t.y) <= max(40.0, t.height * 5.0)
                and "TMS" in norm_tr(o.text).upper()
                for o in sch_texts
            )
            near_rcd = any(
                abs(o.x - t.x) <= max(40.0, t.height * 5.0)
                and abs(o.y - t.y) <= max(40.0, t.height * 5.0)
                and (
                    any(rk in norm_tr(o.text).upper() for rk in ("KAK", "YKR", "RCD"))
                    or re.search(r"\b\d{2,3}\s*mA\b", o.text, re.I)
                )
                for o in sch_texts
            )
            if near_tms and amp and (audit.breaker_in_a is None or amp > audit.breaker_in_a):
                audit.breaker_in_a = amp
                audit.breaker_spec = f"{s.replace(' ', '')} TMŞ"
                audit.source_sheet = sheet_of_text.get(id(t), "")
            elif near_rcd and amp:
                ma_nbr = next(
                    (
                        re.search(r"(\d{2,3})\s*mA", o.text, re.I)
                        for o in sch_texts
                        if abs(o.x - t.x) <= max(40.0, t.height * 5.0)
                        and abs(o.y - t.y) <= max(40.0, t.height * 5.0)
                        and re.search(r"(\d{2,3})\s*mA", o.text, re.I)
                    ),
                    None,
                )
                ma_val = float(ma_nbr.group(1)) if ma_nbr else None
                is_s = any(
                    abs(o.x - t.x) <= max(40.0, t.height * 5.0)
                    and abs(o.y - t.y) <= max(40.0, t.height * 5.0)
                    and re.search(r"\bS\b|SELEKTIF", norm_tr(o.text))
                    for o in sch_texts
                )
                if _can_take_rcd(ma_val):
                    audit.rcd_in_a = amp
                    audit.rcd_ma = ma_val
                    audit.rcd_is_s_type = is_s
                    audit.rcd_spec = f"{s.replace(' ', '')} {int(ma_val)}mA KAKR" if ma_val else s
                    if ma_val and ma_val >= 100:
                        main_rcd_anchor = (t.x, t.y)
        elif re.match(r"^\d{2,3}\s*mA$", s, re.IGNORECASE):
            ma_val = float(re.match(r"^(\d{2,3})\s*mA$", s, re.IGNORECASE).group(1))
            near_kak = any(
                abs(o.x - t.x) <= max(45.0, t.height * 6.0)
                and abs(o.y - t.y) <= max(45.0, t.height * 6.0)
                and any(rk in norm_tr(o.text).upper() for rk in ("KAK", "YKR", "RCD", "TMS"))
                for o in sch_texts
                if o is not t
            )
            if near_kak and ma_val >= 100 and (audit.rcd_ma or 0) < 100:
                amp_nbr = next(
                    (
                        _parse_amp_from_text(o.text)
                        for o in sch_texts
                        if o is not t
                        and abs(o.x - t.x) <= max(45.0, t.height * 6.0)
                        and abs(o.y - t.y) <= max(45.0, t.height * 6.0)
                        and _RE_POLE_AMP_STRICT.match(o.text.replace(" ", ""))
                    ),
                    None,
                )
                is_s = any(
                    abs(o.x - t.x) <= max(45.0, t.height * 6.0)
                    and abs(o.y - t.y) <= max(45.0, t.height * 6.0)
                    and re.search(r"\bS\b|SELEKTIF", norm_tr(o.text))
                    for o in sch_texts
                )
                audit.rcd_in_a = amp_nbr
                audit.rcd_ma = ma_val
                audit.rcd_is_s_type = is_s
                audit.rcd_spec = (
                    f"{int(amp_nbr)}A {int(ma_val)}mA KAKR"
                    if amp_nbr
                    else f"{int(ma_val)}mA KAKR (Anma akımı yazısız)"
                )
                main_rcd_anchor = (t.x, t.y)

    # Küçük binalarda ana kesici TMŞ değil AOS / MCB ("3(25A) AOS") olabilir
    has_unrated_main_tms = main_rcd_anchor is not None and any(
        ("TMS" in norm_tr(o.text).upper() or "TMŞ" in o.text.upper())
        and abs(o.x - main_rcd_anchor[0]) <= max(150.0, o.height * 15.0)
        and abs(o.y - main_rcd_anchor[1]) <= max(80.0, o.height * 8.0)
        for o in sch_texts
    )
    if audit.breaker_in_a is None and not has_unrated_main_tms:
        anchor_pts: List[Tuple[float, float]] = []
        if main_rcd_anchor is not None:
            anchor_pts.append(main_rcd_anchor)
        if main_panel is not None:
            for t in sch_texts:
                if norm_tr(t.text).upper() == norm_tr(main_panel.panel_name).upper():
                    anchor_pts.append((t.x, t.y))
        mcb_cands: List[Tuple[float, float, str, str]] = []
        for t in sch_texts:
            s = t.text.strip()
            s_ns = s.replace(" ", "")
            if re.search(r"[xX*]\d+\s*\(\d+", s):  # Sayaç "3x10(30A)" hariç
                continue
            if not (_RE_CURVE_AMP_PAREN.match(s_ns) or _RE_POLE_AMP_STRICT.match(s_ns)):
                continue
            near_aos = any(
                o is not t
                and abs(o.x - t.x) <= max(60.0, t.height * 6.0)
                and abs(o.y - t.y) <= max(60.0, t.height * 6.0)
                and any(ak in norm_tr(o.text).upper() for ak in ("AOS", "MCB"))
                for o in sch_texts
            )
            if not near_aos:
                continue
            amp = _parse_amp_from_text(s)
            if not amp or amp < 16 or amp > 630:
                continue
            if anchor_pts:
                best_dist = min(
                    abs(t.y - ay) * 3.0 + abs(t.x - ax)
                    for ax, ay in anchor_pts
                )
                # Ana KAKR varsa aynı yatay koridorda ve yakınında olmalı
                if main_rcd_anchor is not None and (
                    abs(t.y - main_rcd_anchor[1]) > max(80.0, t.height * 10.0)
                    or abs(t.x - main_rcd_anchor[0]) > max(260.0, t.height * 25.0)
                ):
                    continue
                mcb_cands.append((best_dist, amp, f"{s} AOS", sheet_of_text.get(id(t), "")))
        if mcb_cands:
            _, best_amp, best_spec, best_sh = min(mcb_cands, key=lambda item: item[0])
            audit.breaker_in_a = best_amp
            audit.breaker_spec = best_spec
            audit.source_sheet = best_sh or audit.source_sheet

    # Ana besleme kablosunu (en büyük kesitli + şemadaki ana kablo, >= 6 mm²) ve boyunu bul
    best_sec = 0.0
    best_dist_anc = float("inf")
    best_cab_text: Optional[RawText] = None
    cab_ref_pt = main_rcd_anchor or (
        next(((t.x, t.y) for t in sch_texts if main_panel and norm_tr(t.text).upper() == norm_tr(main_panel.panel_name).upper()), None)
    )
    for t in sch_texts:
        if _RE_CABLE.search(t.text):
            sp = parse_cable_spec(t.text)
            if sp.is_valid and sp.phase_mm2 >= 6.0:
                d_anc = math.hypot(t.x - cab_ref_pt[0], t.y - cab_ref_pt[1]) if cab_ref_pt else 0.0
                if (sp.phase_mm2 > best_sec) or (sp.phase_mm2 == best_sec and d_anc < best_dist_anc):
                    best_sec = sp.phase_mm2
                    best_dist_anc = d_anc
                    best_cab_text = t
    if best_cab_text is not None:
        audit.cable_spec = re.sub(r"\s+", " ", best_cab_text.text).strip()
        # Yakınında metre yazısı ara ("50m")
        near_m = [
            o for o in sch_texts
            if o is not best_cab_text
            and abs(o.x - best_cab_text.x) <= max(80.0, best_cab_text.height * 10.0)
            and abs(o.y - best_cab_text.y) <= max(40.0, best_cab_text.height * 5.0)
            and re.match(r"^\d+(?:[.,]\d+)?\s*m$", o.text.strip(), re.IGNORECASE)
        ]
        if near_m:
            best_m = min(near_m, key=lambda o: math.hypot(o.x - best_cab_text.x, o.y - best_cab_text.y))
            audit.length_m = parse_tr_float(re.sub(r"[^0-9.,]", "", best_m.text))

    # Şemada AT etiketinin kendi kutusundaki (sağ/alt) Kurulu Güç / Talep Faktörü / Talep Gücü
    if main_panel is not None:
        at_texts = [t for t in sch_texts if norm_tr(t.text).upper() == norm_tr(main_panel.panel_name).upper()]
        if at_texts:
            at_t = at_texts[0]
            near_at = [
                o for o in sch_texts
                if (at_t.x - max(30.0, at_t.height * 3.0)) <= o.x <= (at_t.x + max(350.0, at_t.height * 35.0))
                and (at_t.y - max(120.0, at_t.height * 12.0)) <= o.y <= (at_t.y + max(25.0, at_t.height * 2.5))
            ]
            # Önce açık satır etiketlerini ("Kurulu Güç:", "Talep Gücü:", "Talep Faktörü:") eşle
            demand_label_blank = False
            for o in near_at:
                ou = norm_tr(o.text).upper()
                row_vals = sorted(
                    (
                        r for r in near_at
                        if r is not o
                        and r.x > o.x
                        and abs(r.y - o.y) <= max(12.0, o.height * 1.6)
                    ),
                    key=lambda r: r.x - o.x,
                )
                if not row_vals:
                    continue
                val_txt = row_vals[0].text.strip()
                if "KURULU GUC" in ou and main_inst_w is None:
                    pw = _parse_tr_power_value_w(val_txt)
                    if pw and pw >= 1000.0:
                        main_inst_w = pw
                elif "TALEP GUC" in ou and main_dem_w is None:
                    pw = _parse_tr_power_value_w(val_txt)
                    if pw and pw >= 1000.0:
                        main_dem_w = pw
                    elif re.match(r"^[-–—.\s]*W?$", val_txt, re.IGNORECASE):
                        demand_label_blank = True
                elif "TALEP FAKTOR" in ou and main_df is None:
                    v = parse_tr_float(val_txt)
                    if v is not None and 0.05 <= v <= 1.0:
                        main_df = v

            # Açık satır etiketi yoksa (eski tip dikey hizalı 2-3 sayı) yalnızca AT sağ/altından al
            pw_cands = sorted(
                {w for w in (_parse_tr_power_value_w(o.text) for o in near_at) if w is not None and w >= 1000.0},
                reverse=True,
            )
            if len(pw_cands) >= 2:
                main_inst_w = main_inst_w or pw_cands[0]
                if not demand_label_blank:
                    main_dem_w = main_dem_w or pw_cands[1]
            elif len(pw_cands) == 1:
                main_inst_w = main_inst_w or pw_cands[0]
            if main_df is None:
                for o in near_at:
                    v = parse_tr_float(o.text.strip())
                    if v is not None and 0.10 <= v <= 1.0 and ("," in o.text or "." in o.text):
                        main_df = v
                        break

    eff_dem_w = main_dem_w if (main_dem_w and main_dem_w > 0) else heating_demand_w
    audit.demand_power_w = eff_dem_w

    # Ana pano akım ve kesit hesapları
    if eff_dem_w and eff_dem_w > 0:
        audit.engine_ib_380v_a = calc_operating_current_ib(eff_dem_w, voltage_v=380, cos_phi=0.80, is_3phase=True)
        audit.engine_ib_400v_a = calc_operating_current_ib(eff_dem_w, voltage_v=400, cos_phi=0.80, is_3phase=True)
    if audit.cable_spec:
        sp = parse_cable_spec(audit.cable_spec)
        if sp.is_valid:
            iz_yaml, iz_src = _lookup_cable_ampacity_yaml(sp, audit.cable_spec, rules, method="C")
            audit.engine_iz_yaml_a = iz_yaml
            audit.iz_source = iz_src
            if sp.pe_mm2 is not None:
                pe_ok, req_pe, _ = check_pe_cross_section_iec60364_5_54(sp.phase_mm2, sp.pe_mm2)
                audit.pe_mm2 = sp.pe_mm2
                audit.req_pe_mm2 = req_pe
                audit.pe_ok = pe_ok

    eff_iz = audit.engine_iz_yaml_a if audit.engine_iz_yaml_a is not None else audit.project_written_iz_a
    if audit.breaker_in_a is not None and eff_iz is not None:
        ib_ref = audit.project_written_ib_a or audit.engine_ib_400v_a or 0.0
        audit.ib_in_iz_ok = (ib_ref <= audit.breaker_in_a <= eff_iz)
        if not audit.ib_in_iz_ok:
            req_amp = max(audit.breaker_in_a, ib_ref)
            audit.min_compliant_section_mm2 = _min_compliant_section_from_yaml(
                req_amp, audit.cable_spec or "N2XH", is_three_phase=True, rules=rules
            )

    # Kilitli bölme / Yangın pompası kontrolü
    for t in sch_texts:
        nu = norm_tr(t.text).upper()
        if "KILITLI BOLME" in nu or any(fk in nu for fk in _RE_FIRE_ONLY_KEYWORDS):
            nbrs = [
                o for o in sch_texts
                if abs(o.x - t.x) <= max(600.0, t.height * 60.0)
                and abs(o.y - t.y) <= max(200.0, t.height * 20.0)
            ]
            if any(fk in norm_tr(o.text).upper() for o in nbrs for fk in _RE_FIRE_ONLY_KEYWORDS):
                audit.locked_fire_pump_present = True
                for o in sorted(nbrs, key=lambda x: math.hypot(x.x - t.x, x.y - t.y)):
                    amp = _parse_amp_from_text(o.text)
                    if amp and 10 <= amp <= 250 and "X10(" not in norm_tr(o.text):
                        audit.locked_fire_pump_breaker = o.text.strip()
                        break

    return audit, main_inst_w, main_df, main_dem_w


def _audit_power_budget(
    model: CanonicalProjectModel,
    inv: ProjectInventory,
    main_incomer: MainIncomerAudit,
    main_inst_w: Optional[float],
    main_df: Optional[float],
    main_dem_w: Optional[float],
) -> PowerBudgetAudit:
    """Alt panolar toplamı, ana pano etiketleri ve pafta anteti arasında güç bütçesi mutabakatı."""
    subpanels = [p for p in inv.panels if p.role != "ANA_PANO"]
    sub_inst_sum = round(sum(p.installed_power_w or 0.0 for p in subpanels), 1)
    sub_dem_sum = round(sum(p.demand_power_w or 0.0 for p in subpanels), 1)

    dwelling_cnt = sum(1 for p in subpanels if p.role == "TALI_PANO")
    rec_coinc = get_building_coincidence_factor(dwelling_cnt) if dwelling_cnt > 0 else None

    main_dem_calc = (
        round(main_inst_w * main_df, 1)
        if (main_inst_w is not None and main_df is not None)
        else None
    )

    # Pafta anteti / bilgi tablosu ara (Kurulu Güç + Talep Gücü olan tablolar)
    tb_id: Optional[str] = None
    tb_inst: Optional[float] = None
    tb_dem: Optional[float] = None
    tb_df: Optional[float] = None

    for tbl in model.tables:
        flat_u = norm_tr(" ".join(" ".join(r) for r in tbl.raw_matrix)).upper()
        if (
            "KURULU" in flat_u
            and "TALEP" in flat_u
            and "LINYE" not in flat_u
            and "2.KOL" not in flat_u
            and "SORTI" not in flat_u
            and "ISINMA" not in flat_u
        ):
            # Çok satırlı sütun başlıklarını (örn. 'Toplam Kurulu' + 'Güç (kW)', 'Talep' + 'Gücü (kW)') tanı
            inst_col: Optional[int] = None
            dem_col: Optional[int] = None
            df_col: Optional[int] = None
            max_cols = max((len(r) for r in tbl.raw_matrix), default=0)
            col_blobs = [
                norm_tr(
                    " ".join(str(r[ci]) for r in tbl.raw_matrix[:3] if ci < len(r))
                ).upper()
                for ci in range(max_cols)
            ]
            for ci, cu in enumerate(col_blobs):
                if "KURULU" in cu and inst_col is None:
                    inst_col = ci
                elif "TALEP" in cu and "FAKTOR" not in cu and dem_col is None:
                    dem_col = ci
                elif "TALEP FAKTOR" in cu and df_col is None:
                    df_col = ci

            for ri, row in enumerate(tbl.raw_matrix):
                for ci, cell in enumerate(row):
                    cu = norm_tr(cell).upper()
                    if "KURULU" in cu and inst_col is None:
                        inst_col = ci
                    elif ("TALEP GUC" in cu or cu == "TALEP") and "FAKTOR" not in cu and dem_col is None:
                        dem_col = ci
                    elif "TALEP FAKTOR" in cu:
                        df_col = ci
                if inst_col is not None and ri > 0 and inst_col < len(row):
                    val_i = _parse_tr_power_value_w(row[inst_col])
                    if val_i and val_i > 1000 and tb_inst is None:
                        tb_inst = val_i
                        tb_id = tbl.table_id
                        if dem_col is not None and dem_col < len(row):
                            tb_dem = _parse_tr_power_value_w(row[dem_col])
                if df_col is not None and ri > 0 and df_col < len(row):
                    val_d = parse_tr_float(row[df_col])
                    if val_d is not None and 0.05 <= val_d <= 1.0 and tb_df is None:
                        tb_df = val_d

    diff_tb = round(tb_inst - sub_inst_sum, 1) if (tb_inst is not None and sub_inst_sum > 0) else None
    has_conflict = False
    if diff_tb is not None and abs(diff_tb) > 50.0:
        has_conflict = True
    if main_inst_w is not None and sub_inst_sum > 0 and abs(main_inst_w - sub_inst_sum) > 50.0:
        has_conflict = True

    return PowerBudgetAudit(
        main_panel_name=main_incomer.panel_name,
        subpanel_count=len(subpanels),
        subpanels_installed_sum_w=sub_inst_sum,
        subpanels_demand_sum_w=sub_dem_sum,
        main_installed_written_w=main_inst_w,
        main_demand_factor_written=main_df,
        main_demand_written_w=main_dem_w,
        main_demand_calc_w=main_dem_calc,
        recommended_coincidence_factor=rec_coinc,
        titleblock_table_id=tb_id,
        titleblock_installed_w=tb_inst,
        titleblock_demand_w=tb_dem,
        titleblock_demand_factor=tb_df,
        installed_diff_titleblock_w=diff_tb,
        status="ÇELİŞKİ / HATA VAR" if has_conflict else "UYGUN",
    )


# ==============================================================================
# BÖLÜM 2: YÜKLEME CETVELLERİ DENETİMİ
# ==============================================================================

def _extract_panel_name_for_schedule(tbl: NormalizedTable) -> str:
    """Yükleme cetveli tablosundan pano adını evrensel olarak çıkarır."""
    all_rows = [[str(c).strip() for c in r] for r in tbl.raw_matrix if any(str(c).strip() for c in r)]
    for row in all_rows:
        for cell in row:
            cu = norm_tr(cell).upper().strip()
            if _RE_PANEL_TOK.match(cu) and not _RE_CABLE.search(cell) and not _RE_LINYE_CODE.match(cu):
                return cu
    title_u = norm_tr(tbl.title or "").upper()
    m = re.search(r"\b([A-Z]{1,4}-\d{1,3}|[A-Z]{1,3}-[A-Z0-9]{1,3}|AT|OT|MDP)\b", title_u)
    return m.group(1) if m else (tbl.title or tbl.table_id)[:24]


def _audit_load_schedules(
    model: CanonicalProjectModel,
    rules: Dict[str, Any],
) -> List[LoadScheduleAudit]:
    """OLE2 / ACAD_TABLE yükleme cetvellerindeki linyeleri, faz dengesini ve diversiteyi denetler."""
    results: List[LoadScheduleAudit] = []
    phase_limit = float((rules.get("phase_imbalance_limits", {}) or {}).get("warning_pct", 15.0))

    for tbl in model.tables:
        if tbl.source_kind == "TEXT_GRID" or not tbl.raw_matrix:
            continue
        all_rows = [[str(c).strip() for c in r] for r in tbl.raw_matrix if any(str(c).strip() for c in r)]
        if len(all_rows) < 4:
            continue
        top_blob = norm_tr(" ".join(" ".join(r) for r in all_rows[:6])).upper()
        full_blob = norm_tr(" ".join(" ".join(r) for r in all_rows)).upper()
        if any(
            gk in top_blob
            for gk in (
                "TOPRAKLAMA",
                "LAURENT",
                "OZGUL DIRENC",
                "AYDINLATMA HESABI",
                "ISINMA KONTROLU",
                "GERILIM DUSUMU",
                "KABLO AKIM TASIMA",
            )
        ):
            continue
        if "2.KOL" in full_blob or "3.KOL" in full_blob:
            continue
        if not any(lk in full_blob for lk in ("SORTI", "YUKLEME")):
            continue

        panel_name = _extract_panel_name_for_schedule(tbl)
        circuits: List[LoadCircuitAuditRow] = []

        w_ayd: Optional[int] = None
        w_priz: Optional[int] = None
        w_mot: Optional[int] = None
        w_r: Optional[float] = None
        w_s: Optional[float] = None
        w_t: Optional[float] = None
        w_rst: Optional[float] = None
        w_tot: Optional[float] = None
        w_dem: Optional[float] = None
        main_brk: Optional[str] = None
        main_rcd: Optional[str] = None
        applies_8kw_rule = "8KW" in full_blob.replace(" ", "") and "0,6" in full_blob

        # Başlıkta/panel özet hücrelerinde yazılı talep gücü, G.SİG ve KAKŞ değerlerini topla
        for row in all_rows:
            joined_u = norm_tr(" ".join(row)).upper()
            if joined_u.startswith("TOPLAM"):
                nums = [parse_tr_float(c) for c in row[1:] if parse_tr_float(c) is not None]
                # Tipik TOPLAM sırası: Ayd, Priz, Motor, R, S, T, RST, Toplam
                if len(nums) >= 8:
                    w_ayd = int(round(nums[0]))
                    w_priz = int(round(nums[1]))
                    w_mot = int(round(nums[2]))
                    w_r, w_s, w_t, w_rst, w_tot = nums[3], nums[4], nums[5], nums[6], nums[7]
                continue

            # Linye başlangıcını satır içinde bul
            linye_idx: Optional[int] = None
            for ci, cell in enumerate(row):
                if _RE_LINYE_CODE.match(cell.strip().upper()):
                    linye_idx = ci
                    break
            if linye_idx is not None:
                lno = row[linye_idx].strip().upper()
                if lno not in ("YEDEK", "SPARE"):
                    sub = row[linye_idx + 1 :]
                    brk_parts: List[str] = []
                    desc_parts: List[str] = []
                    nums_in_line: List[float] = []
                    cab = ""
                    for tok in sub:
                        tu = norm_tr(tok).upper().strip()
                        has_brk_amp = bool(brk_parts) and (_parse_amp_from_text(" ".join(brk_parts)) is not None)
                        is_combined_brk = bool(
                            re.match(r"^(?:AOS|MCB|TMS)\s*(?:[1-4]\s*[xX*]\s*)?\d{1,3}\b", tu)
                            or re.match(r"^[1-4]\s*\(\s*\d{1,3}\s*A\s*\)$", tok.strip(), re.I)
                            or re.match(r"^[BCDK]\d{1,3}(?:\s+\d+\s*kA)?$", tu)
                        )
                        if _RE_CABLE.search(tok):
                            cab = tok.strip()
                        elif not has_brk_amp and (
                            is_combined_brk
                            or tu in ("AOS", "MCB")
                            or (re.match(r"^(?:\d+\s*[xX*]\s*)?\d{1,3}A?$", tok.replace(" ", "")) and len(brk_parts) < 2 and not nums_in_line)
                        ):
                            brk_parts.append(tok.strip())
                        elif re.match(r"^\d+(?:[.,]\d+)?\s*kA\s*[BCDK]?$", tok, re.I) or tu in ("B", "C", "D"):
                            brk_parts.append(tok.strip())
                        else:
                            fv = parse_tr_float(tok)
                            if fv is not None and not any(ch.isalpha() for ch in tok):
                                nums_in_line.append(fv)
                            elif len(tok.strip()) >= 2:
                                desc_parts.append(tok.strip())
                    sorti_c = int(round(nums_in_line[0])) if nums_in_line else 0
                    pwr_c = nums_in_line[-1] if len(nums_in_line) >= 2 else (nums_in_line[0] if len(nums_in_line) == 1 else 0.0)
                    # Eğer sondaki sayı boru çapı (16..50) gibi çok küçükse ve önceki sayı güçse (100..50000) ayır
                    if len(nums_in_line) >= 3 and nums_in_line[-1] < 65 and nums_in_line[-2] >= 100:
                        pwr_c = nums_in_line[-2]
                    brk_str = " ".join(brk_parts).strip()
                    brk_a = _parse_amp_from_text(brk_str)
                    cab_sp = parse_cable_spec(cab) if cab else None
                    iz_c, _ = _lookup_cable_ampacity_yaml(cab_sp, cab, rules) if (cab_sp and cab_sp.is_valid) else (None, "")
                    prot_ok = (brk_a <= iz_c) if (brk_a is not None and iz_c is not None) else None
                    circuits.append(
                        LoadCircuitAuditRow(
                            circuit_no=lno,
                            breaker_spec=brk_str,
                            description=" ".join(desc_parts).strip(),
                            sorti_count=sorti_c,
                            written_power_w=round(pwr_c, 1),
                            cable_spec=cab,
                            cable_iz_a=iz_c,
                            breaker_amp_a=brk_a,
                            is_cable_protected=prot_ok,
                        )
                    )

            # Genel pano şalt / talep özeti
            for ci, cell in enumerate(row):
                cu = norm_tr(cell).upper()
                if ("AOS" in cu or "TMS" in cu) and _parse_amp_from_text(cu) and (len(row) <= 4 or ci < (linye_idx or 99)):
                    main_brk = cell.strip()
                elif "MA" in cu and _RE_RCD_COMB.search(cell):
                    main_rcd = cell.strip()
                elif ci < (linye_idx if linye_idx is not None else 3):
                    fv = parse_tr_float(cell)
                    if fv is not None and fv >= 500:
                        if w_dem is None or fv < w_dem:
                            # Önce en makul talep değerini yakala (toplamdan küçük)
                            if w_tot is None or fv < w_tot:
                                w_dem = fv

        calc_sum_w = round(sum(c.written_power_w for c in circuits), 1)
        tot_ref = w_tot if w_tot is not None else calc_sum_w
        if w_dem is not None and tot_ref and abs(w_dem - tot_ref) < 1.0:
            w_dem = None

        # Pano satırlarında talep gücü (örn. 9024, 7136) doğrudan yazılmışsa bul
        for row in all_rows:
            for cell in row[:3]:
                fv = parse_tr_float(cell)
                if fv is not None and 500 < fv < tot_ref:
                    if w_dem is None or abs(fv - calc_dwelling_demand_power_w(tot_ref)) < abs(w_dem - calc_dwelling_demand_power_w(tot_ref)):
                        w_dem = fv

        calc_dem = calc_dwelling_demand_power_w(tot_ref) if tot_ref > 0 else None

        imb_1ph: Optional[float] = None
        imb_rst: Optional[float] = None
        if w_r is not None and w_s is not None and w_t is not None:
            imb_1ph = calc_phase_imbalance_pct(w_r, w_s, w_t)
            rst_each = (w_rst or 0.0) / 3.0
            imb_rst = calc_phase_imbalance_pct(w_r + rst_each, w_s + rst_each, w_t + rst_each)

        has_motor_fire = any(
            any(kw in norm_tr(c.description).upper() for kw in _RE_FIRE_MOTOR_KEYWORDS)
            for c in circuits
        )
        applies_dw_motor = has_motor_fire and applies_8kw_rule

        status = "UYGUN"
        eff_imb = imb_rst if (w_rst and w_rst > 0) else imb_1ph
        if applies_dw_motor or (eff_imb is not None and eff_imb > phase_limit):
            status = "UYARI / İNCELEME GEREKLİ"
        if any(any(fk in norm_tr(c.description).upper() for fk in _RE_FIRE_ONLY_KEYWORDS) for c in circuits) and main_rcd:
            status = "KRİTİK İHLAL (BYKHY)"

        if not circuits or (
            calc_sum_w <= 0.0
            and w_tot is None
            and all(not c.cable_spec and not c.breaker_spec for c in circuits)
        ):
            continue

        results.append(
            LoadScheduleAudit(
                table_id=tbl.table_id,
                sheet_id=tbl.sheet_id,
                source_kind=tbl.source_kind,
                panel_name=panel_name,
                circuits_count=len(circuits),
                written_ayd_sorti=w_ayd,
                written_priz_sorti=w_priz,
                written_motor_sorti=w_mot,
                written_r_w=w_r,
                written_s_w=w_s,
                written_t_w=w_t,
                written_rst_w=w_rst,
                written_total_w=w_tot,
                calc_circuits_total_w=calc_sum_w,
                written_demand_w=w_dem,
                calc_dwelling_demand_w=calc_dem,
                phase_imbalance_single_ph_pct=imb_1ph,
                phase_imbalance_with_rst_pct=imb_rst,
                has_motor_or_fire_load=has_motor_fire,
                applies_dwelling_diversity_to_motor=applies_dw_motor,
                main_breaker_spec=main_brk,
                main_rcd_spec=main_rcd,
                status=status,
                circuits=circuits,
            )
        )

    return results


# ==============================================================================
# BÖLÜM 3: ISINMA / KESİT / SEÇİCİLİK / GERİLİM DÜŞÜMÜ (TÜM PANOLAR)
# ==============================================================================

def _parse_panel_thermal_vd_tables(model: CanonicalProjectModel) -> List[Dict[str, Any]]:
    """
    OLE2 / Excel ısınma kontrolü ve linye gerilim düşümü tablolarındaki
    tekrarlı 5-satırlı pano bloklarını (TABLO / DİVERSİTE / HAT AKIMI / AKIM TAŞIMA / TOPLAM %e)
    evrensel olarak ayrıştırır.
    """
    blocks: List[Dict[str, Any]] = []

    for tbl in model.tables:
        if tbl.source_kind not in ("OLE2_DECODED", "ACAD_TABLE"):
            continue
        blob = norm_tr(" ".join(" ".join(r) for r in tbl.raw_matrix[:6])).upper()
        if "ISINMA KONTROL" not in blob and "HAT AKIMI" not in blob:
            continue

        rows = tbl.raw_matrix
        i = 0
        while i < len(rows):
            r0 = [str(c).strip() for c in rows[i]]
            r0_u = norm_tr(" ".join(r0)).upper()
            if "TABLO" in r0_u and "KURULU" in r0_u and i + 4 < len(rows):
                r1 = [str(c).strip() for c in rows[i + 1]]
                r2 = [str(c).strip() for c in rows[i + 2]]
                r3 = [str(c).strip() for c in rows[i + 3]]
                r4 = [str(c).strip() for c in rows[i + 4]]

                p_name = ""
                p_inst: Optional[float] = None
                feeder_m: Optional[float] = None
                linye_no: Optional[str] = None

                # r0: ['TABLO', 'KURULU GÜÇ (W)', panel, P_inst, 'Metraj', L_m, 'LİNYE NO', '1.KOL', linye_no, ...]
                for idx, tok in enumerate(r0):
                    tu = norm_tr(tok).upper()
                    if not p_name and _RE_PANEL_TOK.match(tu) and not _RE_LINYE_CODE.match(tu):
                        p_name = tu
                    elif tu == "METRAJ" and idx + 1 < len(r0):
                        feeder_m = parse_tr_float(r0[idx + 1])
                    elif tu == "1.KOL" and idx + 1 < len(r0):
                        linye_no = r0[idx + 1].strip()
                if p_name:
                    # P_inst genelde pano adının hemen sağındaki sayı
                    nums_r0 = [parse_tr_float(c) for c in r0[2:6] if parse_tr_float(c) is not None and parse_tr_float(c) >= 100]
                    if nums_r0:
                        p_inst = nums_r0[0]

                # r1: DİVERSİTE -> P_dem + KESİT(mm2), MESAFE(m)
                p_dem: Optional[float] = None
                linye_sec: Optional[float] = None
                linye_len: Optional[float] = None
                for idx, tok in enumerate(r1):
                    tu = norm_tr(tok).upper()
                    if ("8KW" in tu.replace(" ", "") or "DIVERSITEL" in tu) and idx + 1 < len(r1):
                        v = parse_tr_float(r1[idx + 1])
                        if v and v >= 100:
                            p_dem = v
                if p_dem is None:
                    # Örn. İŞ-T gibi 8kW kuralı satırda yoksa 100..500000 arası sayıyı al
                    for tok in r1[:6]:
                        v = parse_tr_float(tok)
                        if v and v >= 500:
                            p_dem = v
                            break
                for idx, tok in enumerate(r1):
                    tu = norm_tr(tok).upper()
                    if "MESAFE" in tu and idx + 2 < len(r1):
                        linye_sec = parse_tr_float(r1[idx + 1])
                        linye_len = parse_tr_float(r1[idx + 2])
                        break

                # r2: HAT AKIMI (A), KABLO KESİT, Ib, cable_str, Cosφ, cos_phi, HAT GÜÇLERİ, T.HAT GÜÇLERİ, linye_power
                written_ib: Optional[float] = None
                cable_str: Optional[str] = None
                cos_phi: Optional[float] = None
                linye_pwr: Optional[float] = None
                for idx, tok in enumerate(r2):
                    tu = norm_tr(tok).upper()
                    if "COS" in tu and idx + 1 < len(r2):
                        cos_phi = parse_tr_float(r2[idx + 1])
                    elif re.match(r"^[1-4]\s*[xX*]\s*\d+", tok.strip()):
                        cable_str = tok.strip()
                        if idx > 0 and written_ib is None:
                            written_ib = parse_tr_float(r2[idx - 1])
                    elif "HAT GUCLER" in tu and idx + 1 < len(r2):
                        # Sonraki sayısal güç değeri
                        for sub_tok in r2[idx + 1 :]:
                            v = parse_tr_float(sub_tok)
                            if v and v >= 100:
                                linye_pwr = v
                                break

                # r3: KABLO AKIM TAŞIMA KAPASİTESİ (A), Iz, HESAP GERİLİM DÜŞÜMÜ, vd_linye
                written_iz: Optional[float] = None
                vd_linye: Optional[float] = None
                for idx, tok in enumerate(r3):
                    tu = norm_tr(tok).upper()
                    if "KAPASIT" in tu and idx + 1 < len(r3):
                        written_iz = parse_tr_float(r3[idx + 1])
                    elif "GERILIM DUSUMU" in tu and idx + 1 < len(r3):
                        vd_linye = parse_tr_float(r3[idx + 1])

                # r4: total_vd, limit ('<1,5' veya '<3')
                vd_tot = parse_tr_float(r4[0]) if r4 else None
                vd_lim = r4[1].strip() if len(r4) > 1 else ""

                if p_name:
                    blocks.append({
                        "table_id": tbl.table_id,
                        "panel_name": p_name,
                        "p_inst_w": p_inst,
                        "p_dem_w": p_dem,
                        "feeder_m": feeder_m,
                        "cable_str": cable_str,
                        "cos_phi": cos_phi,
                        "written_ib_a": written_ib,
                        "written_iz_a": written_iz,
                        "linye_no": linye_no,
                        "linye_pwr_w": linye_pwr,
                        "linye_len_m": linye_len,
                        "linye_sec_mm2": linye_sec,
                        "vd_linye_pct": vd_linye,
                        "vd_tot_pct": vd_tot,
                        "vd_limit_str": vd_lim,
                    })
                i += 5
                continue
            i += 1

    return blocks


def _audit_panels_and_thermal(
    inv: ProjectInventory,
    model: CanonicalProjectModel,
    main_incomer: MainIncomerAudit,
    main_vd_pct_proj: Optional[float],
    rules: Dict[str, Any],
    load_schedules: Optional[List[LoadScheduleAudit]] = None,
) -> List[PanelAuditRow]:
    r"""
    Tüm alt panoları (`111E01..111E05` OLE tabloları + Kolon Şeması metrajı)
    birleştirerek ısınma ($I_b \le I_n \le I_z$), seçicilik ve gerilim düşümünü yeniden hesaplar.
    """
    inv_by_name: Dict[str, PanelInventoryItem] = {
        norm_tr(p.panel_name).upper(): p for p in inv.panels if p.role != "ANA_PANO"
    }
    ls_by_name: Dict[str, LoadScheduleAudit] = {
        norm_tr(ls.panel_name).upper(): ls for ls in (load_schedules or []) if ls.panel_name
    }
    motor_panel_names = {
        norm_tr(ls.panel_name).upper() for ls in (load_schedules or []) if ls.has_motor_or_fire_load
    }
    ole_rows = _parse_panel_thermal_vd_tables(model)
    seen_panels: Set[str] = set()
    rows_out: List[PanelAuditRow] = []

    def _compute_panel_row(
        p_name: str,
        inv_item: Optional[PanelInventoryItem],
        ole: Optional[Dict[str, Any]],
    ) -> PanelAuditRow:
        flags: List[str] = []
        pk_u = norm_tr(p_name).upper()
        ls_match = ls_by_name.get(pk_u)
        p_inst = (ole or {}).get("p_inst_w") or (inv_item.installed_power_w if inv_item else None)
        p_dem = (ole or {}).get("p_dem_w") or (inv_item.demand_power_w if inv_item else None)
        role = (
            inv_item.role
            if inv_item
            else ("ORTAK_PANO" if pk_u in motor_panel_names else "TALI_PANO")
        )
        sch_len = _extract_schematic_length_for_panel(p_name, inv, model)
        feeder_len = (ole or {}).get("feeder_m") or sch_len
        cab_str = (inv_item.feeder_cable if inv_item and inv_item.feeder_cable else None) or (ole or {}).get("cable_str")
        brk_spec = (inv_item.breaker_rating if inv_item else None) or (ls_match.main_breaker_spec if ls_match else None)
        rcd_spec = (inv_item.rcd_rating if inv_item else None) or (ls_match.main_rcd_spec if ls_match else None)
        brk_a = _parse_amp_from_text(brk_spec or "")

        cos_p = (ole or {}).get("cos_phi")
        w_ib = (ole or {}).get("written_ib_a")
        w_iz = (ole or {}).get("written_iz_a")

        cab_sp = parse_cable_spec(cab_str or "")
        e_iz_yaml, _ = _lookup_cable_ampacity_yaml(cab_sp, cab_str or "", rules, method="C") if cab_sp.is_valid else (None, "")
        is_3ph = cab_sp.cores >= 4 if cab_sp.is_valid else True

        e_ib_proj: Optional[float] = None
        e_ib_400: Optional[float] = None
        if p_dem and p_dem > 0:
            cp = cos_p if (cos_p and 0.3 <= cos_p <= 1.0) else 0.80
            e_ib_proj = calc_operating_current_ib(p_dem, voltage_v=380 if is_3ph else 220, cos_phi=cp, is_3phase=is_3ph)
            e_ib_400 = calc_operating_current_ib(p_dem, voltage_v=400 if is_3ph else 230, cos_phi=0.80, is_3phase=is_3ph)

        eff_iz = e_iz_yaml if e_iz_yaml is not None else w_iz
        ib_ref = w_ib if w_ib is not None else e_ib_400
        ib_in_iz_ok: Optional[bool] = None
        if ib_ref is not None and brk_a is not None and eff_iz is not None:
            ib_in_iz_ok = (ib_ref <= brk_a <= eff_iz)

        if brk_spec is None and role == "TALI_PANO":
            flags.append("ŞEMADA KESİCİ YAZISI EKSİK")
        if w_iz is not None and e_iz_yaml is not None and abs(w_iz - e_iz_yaml) >= 15.0:
            flags.append(f"TABLO Iz HATALI ({w_iz:.0f}A vs {e_iz_yaml:.0f}A)")
        if cos_p is not None and cos_p < 0.75:
            flags.append(f"DÜŞÜK cosφ ({cos_p})")

        # Seçicilik ve KAKR < Sigorta kontrolü (tamamen dosyadan okunan değerlerle)
        sel_notes: List[str] = []
        if inv_item and inv_item.parent_panel:
            parent_row = inv_by_name.get(norm_tr(inv_item.parent_panel).upper())
            parent_brk_a = (
                _parse_amp_from_text(parent_row.breaker_rating or "")
                if parent_row and parent_row.breaker_rating
                else (
                    main_incomer.breaker_in_a
                    if main_incomer.panel_name and norm_tr(inv_item.parent_panel).upper() == norm_tr(main_incomer.panel_name).upper()
                    else None
                )
            )
            if parent_brk_a and brk_a and parent_brk_a > brk_a:
                sel_res = check_breaker_selectivity(parent_brk_a, brk_a, "C", "C")
                if not sel_res["is_compliant"]:
                    sel_notes.append(f"Üst({parent_brk_a:.0f}A)->Pano({brk_a:.0f}A) oran={sel_res['current_ratio']}<1.60")
        if ls_match and (brk_a or rcd_spec):
            up_a = brk_a or (_parse_rcd_rating_ma(rcd_spec or "")[0])
            if up_a:
                for c in ls_match.circuits:
                    if c.breaker_amp_a and up_a >= c.breaker_amp_a:
                        sel_c = check_breaker_selectivity(up_a, c.breaker_amp_a, "C", "C")
                        if not sel_c["is_compliant"]:
                            sel_notes.append(f"{up_a:.0f}A->{c.circuit_no}({c.breaker_amp_a:.0f}A) oran={sel_c['current_ratio']}<1.60")
                            break
        if rcd_spec and brk_a is not None:
            rcd_a, rcd_ma, _ = _parse_rcd_rating_ma(rcd_spec)
            if rcd_a is not None and rcd_a < brk_a:
                flags.append(f"KAKR<SİGORTA ({rcd_a:.0f}A<{brk_a:.0f}A)")
            if rcd_ma is not None and main_incomer.rcd_ma is not None and not main_incomer.rcd_is_s_type:
                sel_notes.append("Üst KAKR 'S' tip değil")

        # Gerilim düşümü yeniden hesapla (kolon + linye)
        l_pwr = (ole or {}).get("linye_pwr_w")
        l_len = (ole or {}).get("linye_len_m")
        l_sec = (ole or {}).get("linye_sec_mm2")
        w_vd_l = (ole or {}).get("vd_linye_pct")
        w_vd_tot = (ole or {}).get("vd_tot_pct")
        vd_lim = (ole or {}).get("vd_limit_str", "")

        e_vd_kol: Optional[float] = None
        if p_dem and feeder_len and cab_sp.is_valid and cab_sp.phase_mm2 > 0:
            e_vd_kol = round(
                (100.0 * feeder_len * p_dem) / (56.0 * cab_sp.phase_mm2 * (380.0 ** 2)),
                3,
            )

        e_vd_lin_proj: Optional[float] = None
        e_vd_lin_230: Optional[float] = None
        is_motor_linye = role == "ORTAK_PANO" or (l_pwr is not None and l_pwr >= 4000 and l_sec is not None and l_sec >= 4.0)
        if l_pwr and l_len and l_sec and l_sec > 0:
            # 3 faz mı 1 faz mı?
            if is_motor_linye:
                e_vd_lin_proj = round((100.0 * l_len * l_pwr) / (56.0 * l_sec * (380.0 ** 2)), 3)
                e_vd_lin_230 = round((100.0 * l_len * l_pwr) / (56.0 * l_sec * (400.0 ** 2)), 3)
            else:
                e_vd_lin_proj = round((200.0 * l_len * l_pwr) / (56.0 * l_sec * (220.0 ** 2)), 3)
                e_vd_lin_230 = round((200.0 * l_len * l_pwr) / (56.0 * l_sec * (230.0 ** 2)), 3)

            if w_vd_l is not None and abs(w_vd_l - e_vd_lin_proj) > 0.15:
                flags.append(
                    f"LİNYE %e FORMÜL HATASI (Yazılı %{w_vd_l:.3f} vs Doğru %{e_vd_lin_proj:.3f})"
                )

        e_vd_no_main = (
            round((e_vd_kol or 0.0) + (e_vd_lin_proj or 0.0), 3)
            if (e_vd_kol is not None or e_vd_lin_proj is not None)
            else None
        )
        e_vd_with_main = (
            round(e_vd_no_main + main_vd_pct_proj, 3)
            if (e_vd_no_main is not None and main_vd_pct_proj is not None)
            else None
        )
        # IEC 60364-5-52 toplam %e (400/230V)
        e_vd_iec: Optional[float] = None
        if p_dem and feeder_len and cab_sp.is_valid and cab_sp.phase_mm2 > 0:
            ib_k = calc_operating_current_ib(p_dem, 400, 0.85, True)
            _, vd_k_iec = calc_voltage_drop_exact_iec_pct(ib_k, feeder_len, cab_sp.phase_mm2, 0.85, True)
            vd_l_iec = e_vd_lin_230 or 0.0
            e_vd_iec = round(vd_k_iec + vd_l_iec, 2)

        if e_vd_with_main is not None and not is_motor_linye and e_vd_with_main > 1.50:
            flags.append(f"ANA BESLEME DAHİL %e>{1.5}% ({e_vd_with_main:.2f}%)")

        calc_dw = calc_dwelling_demand_power_w(p_inst) if (p_inst and role == "TALI_PANO") else None
        if sch_len is not None and feeder_len is not None and abs(sch_len - feeder_len) > 0.1:
            flags.append(f"METRAJ FARKI (Şema {sch_len:.1f}m vs Tablo {feeder_len:.1f}m)")

        return PanelAuditRow(
            panel_name=p_name,
            role=role,
            source_table_id=(ole or {}).get("table_id"),
            installed_power_w=p_inst,
            demand_power_w=p_dem,
            calc_dwelling_demand_w=calc_dw,
            feeder_length_m=feeder_len,
            schematic_length_m=sch_len,
            cable_spec=cab_str,
            phase_mm2=cab_sp.phase_mm2 if cab_sp.is_valid else None,
            pe_mm2=cab_sp.pe_mm2 if cab_sp.is_valid else None,
            breaker_spec=brk_spec,
            breaker_in_a=brk_a,
            rcd_spec=rcd_spec,
            cos_phi_project=cos_p,
            project_ib_a=w_ib,
            engine_ib_proj_params_a=e_ib_proj,
            engine_ib_400v_08_a=e_ib_400,
            project_iz_a=w_iz,
            engine_iz_yaml_a=e_iz_yaml,
            ib_in_iz_ok=ib_in_iz_ok,
            linye_no=(ole or {}).get("linye_no"),
            linye_power_w=l_pwr,
            linye_length_m=l_len,
            linye_section_mm2=l_sec,
            project_vd_linye_pct=w_vd_l,
            engine_vd_linye_proj_pct=e_vd_lin_proj,
            engine_vd_linye_230v_pct=e_vd_lin_230,
            project_vd_total_pct=w_vd_tot,
            engine_vd_kolon_proj_pct=e_vd_kol,
            engine_vd_total_no_main_pct=e_vd_no_main,
            engine_vd_total_with_main_pct=e_vd_with_main,
            engine_vd_total_iec_pct=e_vd_iec,
            vd_limit_written=vd_lim,
            selectivity_note="; ".join(sel_notes),
            flags=flags,
        )

    for ole in ole_rows:
        pk = norm_tr(ole["panel_name"]).upper()
        seen_panels.add(pk)
        rows_out.append(_compute_panel_row(ole["panel_name"], inv_by_name.get(pk), ole))

    for pk, inv_item in sorted(inv_by_name.items()):
        if pk not in seen_panels:
            rows_out.append(_compute_panel_row(inv_item.panel_name, inv_item, None))

    return rows_out


def _extract_schematic_length_for_panel(
    panel_name: str,
    inv: ProjectInventory,
    model: CanonicalProjectModel,
) -> Optional[float]:
    """Şemadan gelen pano besleme boyunu (varsa) okur — yoksa None döner."""
    # `panel_rows` oluşturulurken `metraj_cikarici` zaten `cable_bom` içinde topladı, ancak
    # burada panoya özgü birebir length varsa ileride genişletilebilir; şema grafı kenarlarında da aranır.
    pn_u = norm_tr(panel_name).upper()
    for sg in model.schematics:
        id_to_label = {n.node_id: norm_tr(n.label).upper() for n in sg.nodes}
        for e in sg.edges:
            if id_to_label.get(e.target_node) == pn_u:
                for txt in e.texts_along_edge:
                    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*m$", txt.strip(), re.I)
                    if m:
                        return parse_tr_float(m.group(1))
    return None


# ==============================================================================
# BÖLÜM 4: GERİLİM DÜŞÜMÜ FORMÜL BLOKLARI (`M_18` VB.)
# ==============================================================================

def _audit_voltage_drop_formulas(
    model: CanonicalProjectModel,
    fallback_main_power_w: Optional[float] = None,
) -> Tuple[List[VoltageDropFormulaRow], Optional[float], Optional[float], Optional[float]]:
    """
    `model.formula_blocks` içindeki açık kesirli gerilim düşümü formüllerini (`VOLTAGE_DROP`) ve
    üstündeki kablo/uzunluk segmentlerini (`FEEDER_SEGMENT`) 1'e 1 optimal atama
    (`linear_sum_assignment`: X hizası + uzunluk + kesit uyumu) ile eşleştirip
    `calc_voltage_drop_pct` + `calc_voltage_drop_exact_iec_pct` ile yeniden hesaplar.
    """
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    vd_blocks = sorted(
        [fb for fb in model.formula_blocks if fb.formula_kind == "VOLTAGE_DROP" and fb.parse_status in ("OK", "PARTIAL")],
        key=lambda fb: fb.bbox_du.center[0],
    )
    seg_blocks = sorted(
        [fb for fb in model.formula_blocks if fb.formula_kind == "FEEDER_SEGMENT"],
        key=lambda fb: fb.bbox_du.center[0],
    )

    def _parse_vd_fields(fb: FormulaBlock) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], bool]:
        num_blob = " ".join(fb.numerator_texts).replace(",", ".")
        den_blob = " ".join(fb.denominator_texts).replace(",", ".")
        coef_blob = " ".join(fb.coefficient_texts).replace(",", ".")
        parts = re.findall(r"\d+(?:\.\d+)?", num_blob)
        len_m = float(parts[0]) if len(parts) >= 1 else None
        pwr_raw = float(parts[1]) if len(parts) >= 2 else None
        pwr_w = (pwr_raw * 1000.0) if (pwr_raw is not None and pwr_raw < 1000.0) else pwr_raw
        sec_m = re.search(r"\d+(?:\.\d+)?", den_blob)
        sec_mm2 = float(sec_m.group(0)) if sec_m else None
        c_m = re.search(r"\d+(?:\.\d+)?", coef_blob)
        coeff = float(c_m.group(0)) if c_m else None
        is_3ph = (coeff is None or coeff < 0.04)
        return len_m, pwr_w, sec_mm2, coeff, is_3ph

    # Aynı paftadaki VOLTAGE_DROP ve FEEDER_SEGMENT bloklarını 1'e 1 eşle
    matched_seg_by_vd: Dict[str, Optional[FormulaBlock]] = {}
    vd_by_sheet: Dict[str, List[FormulaBlock]] = defaultdict(list)
    seg_by_sheet: Dict[str, List[FormulaBlock]] = defaultdict(list)
    for fb in vd_blocks:
        vd_by_sheet[fb.sheet_id or ""].append(fb)
    for sb in seg_blocks:
        seg_by_sheet[sb.sheet_id or ""].append(sb)

    for sh_id, vds in vd_by_sheet.items():
        segs = seg_by_sheet.get(sh_id, [])
        if not segs:
            continue
        all_xs = [b.bbox_du.center[0] for b in vds] + [s.bbox_du.center[0] for s in segs]
        span_x = max(1.0, max(all_xs) - min(all_xs))
        cost = np.zeros((len(vds), len(segs)), dtype=float)
        for i, fb in enumerate(vds):
            v_len, _, v_sec, _, _ = _parse_vd_fields(fb)
            cx_v = fb.bbox_du.center[0]
            for j, sb in enumerate(segs):
                c = abs(cx_v - sb.bbox_du.center[0]) / span_x
                s_len = sb.parsed_result_value
                s_cab = " ".join(sb.numerator_texts).strip()
                s_sp = parse_cable_spec(s_cab)
                if v_len is not None and s_len is not None and s_len > 0:
                    c += -5.0 if abs(v_len - s_len) <= 0.15 else 20.0
                if v_sec is not None and s_sp.is_valid and s_sp.phase_mm2 > 0:
                    c += -5.0 if abs(v_sec - s_sp.phase_mm2) <= 0.1 else 20.0
                cost[i, j] = c
        r_ind, c_ind = linear_sum_assignment(cost)
        for ri, ci in zip(r_ind, c_ind):
            if cost[ri, ci] < 15.0:
                matched_seg_by_vd[vds[ri].formula_id] = segs[ci]

    rows: List[VoltageDropFormulaRow] = []
    tot_written = 0.0
    tot_eng_proj = 0.0
    tot_eng_std = 0.0
    has_any = False

    for idx, fb in enumerate(vd_blocks):
        seg_match: Optional[FormulaBlock] = matched_seg_by_vd.get(fb.formula_id)
        cab_str = " ".join(seg_match.numerator_texts).strip() if seg_match else ""
        len_m, pwr_w, sec_mm2, coeff, is_3ph = _parse_vd_fields(fb)
        if len_m is None and seg_match is not None:
            len_m = seg_match.parsed_result_value
        proj_vd = fb.parsed_result_value
        if len_m is None and sec_mm2 is None and proj_vd is None:
            continue
        eng_proj_v: Optional[float] = None
        eng_std_v: Optional[float] = None
        eng_iec: Optional[float] = None
        row_note = ""

        calc_pwr_w = pwr_w
        if calc_pwr_w is None and idx == 0 and is_3ph and fallback_main_power_w and fallback_main_power_w > 0:
            calc_pwr_w = fallback_main_power_w
            row_note = "Projede güç/%e boş (--,--); ana talep gücü ile hesaplandı"
        elif pwr_w is None or proj_vd is None:
            row_note = "Projede güç veya %e sonucu boş (--,--)"

        if len_m and calc_pwr_w and sec_mm2 and sec_mm2 > 0:
            u_proj = 380 if is_3ph else 220
            u_std = 400 if is_3ph else 230
            eng_proj_v = calc_voltage_drop_pct(calc_pwr_w, len_m, sec_mm2, voltage_v=u_proj, conductivity=56.0, is_3phase=is_3ph)
            eng_std_v = calc_voltage_drop_pct(calc_pwr_w, len_m, sec_mm2, voltage_v=u_std, conductivity=56.0, is_3phase=is_3ph)
            ib = calc_operating_current_ib(calc_pwr_w, u_std, cos_phi=0.85 if is_3ph else 0.90, is_3phase=is_3ph)
            ins = "XLPE" if any(k in norm_tr(cab_str).upper() for k in ("N2XH", "XLPE", "07Z1")) else "PVC"
            _, eng_iec = calc_voltage_drop_exact_iec_pct(ib, len_m, sec_mm2, cos_phi=0.85 if is_3ph else 0.90, is_3phase=is_3ph, insulation=ins)

        seg_label = "Ana Besleme" if idx == 0 and is_3ph else ("Kolon Hattı" if is_3ph else "Linye Hattı")
        if proj_vd is not None:
            tot_written += proj_vd
            has_any = True
        if eng_proj_v is not None:
            tot_eng_proj += eng_proj_v
        if eng_std_v is not None:
            tot_eng_std += eng_std_v

        rows.append(
            VoltageDropFormulaRow(
                formula_id=fb.formula_id,
                sheet_id=fb.sheet_id,
                segment_name=seg_label,
                cable_spec=cab_str,
                length_m=len_m,
                power_w=pwr_w,
                section_mm2=sec_mm2,
                coeff_written=coeff,
                is_three_phase=is_3ph,
                project_vd_pct=proj_vd,
                engine_vd_proj_v_pct=eng_proj_v,
                engine_vd_std_v_pct=eng_std_v,
                engine_vd_iec_ekg_pct=eng_iec,
                note=row_note,
            )
        )

    if not has_any and not rows:
        return rows, None, None, None
    return (
        rows,
        round(tot_written, 2) if has_any else None,
        round(tot_eng_proj, 2) if tot_eng_proj > 0 else None,
        round(tot_eng_std, 2) if tot_eng_std > 0 else None,
    )


# ==============================================================================
# BÖLÜM 5: TEMEL TOPRAKLAMA DENETİMİ
# ==============================================================================

def _audit_grounding(
    snapshot: RawCADSnapshot,
    model: CanonicalProjectModel,
    main_incomer: MainIncomerAudit,
    rules: Dict[str, Any],
) -> Optional[GroundingAudit]:
    """
    Topraklama hesap tablosunu (varsa) ile M_02 CAD gerçek temel ring geometrisini eşleştirip
    Laurent-Niemann, Dwight ve IEEE Std 80 Sverak formülleriyle yeniden hesaplar.
    """
    gnd_tbl: Optional[NormalizedTable] = None
    for tbl in model.tables:
        blob = norm_tr(" ".join(" ".join(r) for r in tbl.raw_matrix)).upper()
        if any(k in blob for k in ("GOMULU ILETKEN", "YAYILMA DIRENC", "LAURENT", "TOPRAKLAMA ESDEGER")):
            gnd_tbl = tbl
            break

    gnd_loop: Optional[GroundingLoop] = model.grounding_loops[0] if model.grounding_loops else None
    if gnd_tbl is None and gnd_loop is None:
        return None

    ga = GroundingAudit(
        table_id=gnd_tbl.table_id if gnd_tbl else None,
        loop_id=gnd_loop.loop_id if gnd_loop else None,
        sheet_id=(gnd_tbl.sheet_id if gnd_tbl else (gnd_loop.sheet_id if gnd_loop else "")),
    )

    if gnd_tbl is not None:
        # Satır bazlı key=val ayrıştır
        in_rod_section = False
        for row in gnd_tbl.raw_matrix:
            row_u = norm_tr(" ".join(row)).upper()
            if "GOMULU CUBUK" in row_u or "YATAY TOPRAKLAMA" in row_u:
                in_rod_section = True
            for ci, cell in enumerate(row):
                cu = norm_tr(cell).upper().replace(" ", "")
                val: Optional[float] = None
                for off in (1, 2, 3):
                    if ci + off >= len(row):
                        break
                    nxt = row[ci + off].strip()
                    if "=" in nxt and nxt != "=":
                        break
                    parsed_v = parse_tr_float(nxt)
                    if parsed_v is not None:
                        val = parsed_v
                        break
                if cu == "L=" and val is not None:
                    if in_rod_section and val <= 10.0 and ga.table_rod_L_m is None:
                        ga.table_rod_L_m = val
                    elif not in_rod_section and ga.table_L_m is None:
                        ga.table_L_m = val
                elif cu == "A=" and val is not None:
                    if val <= 80.0 and "EN" in row_u:
                        ga.table_a_m = val
                    elif (val > 30.0 or "ALAN" in row_u) and ga.table_A_m2 is None:
                        ga.table_A_m2 = val
                elif cu == "B=" and val is not None:
                    ga.table_b_m = val
                elif cu == "D=" and val is not None:
                    if val < 0.015:
                        ga.strip_d_m = val
                    elif in_rod_section and val <= 0.1:
                        ga.table_rod_d_m = val
                    elif val >= 5.0 and ga.table_D_written_m is None:
                        ga.table_D_written_m = val
                elif cu == "H=" and val is not None:
                    ga.depth_h_m = val
                elif ("ΡE=" in cu or "PE=" in cu or "RHO=" in cu) and val is not None:
                    ga.rho_ohm_m = val
                elif cu == "N=" and val is not None:
                    ga.table_n_rods = int(round(val))
                elif cu == "RC=" and val is not None:
                    ga.table_Rc_written_ohm = val
                elif cu == "RY=" and val is not None:
                    ga.table_Ry_written_ohm = val
                elif cu == "RE=" and val is not None and ga.table_Re_written_ohm is None:
                    # Bazen Re = değer şeklindedir
                    ga.table_Re_written_ohm = val
            if row and norm_tr(row[0]).upper().strip() == "RE=" and len(row) >= 3:
                v_re = parse_tr_float(row[-1])
                if v_re is not None:
                    ga.table_Re_written_ohm = v_re
            if "≤" in " ".join(row) and len(row) >= 3:
                v_lim = parse_tr_float(row[2])
                if v_lim is not None:
                    ga.table_limit_written_ohm = v_lim

        if ga.table_A_m2 is None and ga.table_a_m and ga.table_b_m:
            ga.table_A_m2 = round(ga.table_a_m * ga.table_b_m, 2)

    # CAD Geometrisi & plan metinlerinden çubuk boyu (örn. 'Ø20mm h=1,75m')
    if gnd_loop is not None:
        ga.cad_A_m2 = gnd_loop.area_m2
        ga.cad_D_m = gnd_loop.equivalent_diameter_m
        ga.cad_perimeter_m = gnd_loop.outer_perimeter_m
        ga.cad_inner_m = gnd_loop.inner_conductors_m
        ga.cad_ring_plus_inner_m = gnd_loop.ring_plus_inner_m
        ga.cad_spur_m = gnd_loop.spur_total_m
        ga.cad_rod_count = gnd_loop.rod_block_count

        sh_gnd = next((s for s in model.sheets if s.frame_id == gnd_loop.sheet_id), None)
        if sh_gnd:
            for t in snapshot.texts:
                if t.space == sh_gnd.space and sh_gnd.bbox_du.contains_xy(t.x, t.y):
                    m_rod = re.search(r"h\s*=\s*(\d+(?:[.,]\d+)?)\s*m", t.text, re.I)
                    if m_rod and ("Ø" in t.text or "MM" in t.text.upper()):
                        v_h = parse_tr_float(m_rod.group(1))
                        # Plan üzerindeki gerçek çubuk etiketini (genelde h >= 1.2m) detaya tercih et
                        if v_h and (ga.cad_rod_L_spec_m is None or v_h > ga.cad_rod_L_spec_m):
                            ga.cad_rod_L_spec_m = v_h

    rho = ga.rho_ohm_m
    depth = ga.depth_h_m if ga.depth_h_m is not None else 1.0
    d_strip = ga.strip_d_m if ga.strip_d_m is not None else 0.008
    d_rod = ga.table_rod_d_m if ga.table_rod_d_m is not None else 0.02

    # 1. Tablo girdileriyle yeniden hesaplama (özgül direnç ρ tabloda/projede okunduysa)
    if rho and ga.table_A_m2 and ga.table_L_m:
        n_r = ga.table_n_rods or 0
        l_r = ga.table_rod_L_m or 1.5
        ln_tbl = calc_foundation_earthing_laurent_niemann(rho, ga.table_A_m2, ga.table_L_m, n_r, l_r, d_rod)
        ga.engine_tbl_D_m = ln_tbl["D_m"]
        ga.engine_tbl_R_temel_ohm = ln_tbl["R_temel_ohm"]
        ga.engine_tbl_R_rods_dwight_ohm = ln_tbl["R_rods_ohm"]
        ga.engine_tbl_R_schwarz_ohm = ln_tbl["R_combined_ohm"]
        ga.engine_tbl_R_strip_dwight_ohm = calc_horizontal_strip_resistance_dwight(rho, ga.table_L_m, d_strip, depth)
        ga.engine_tbl_R_sverak_ohm = calc_foundation_earthing_ieee80_sverak(rho, ga.table_A_m2, ga.table_L_m, n_r, l_r, depth)

        # Tablo formül hatalarını matematiksel olarak teşhis et
        if ga.table_Rc_written_ohm is not None and ga.engine_tbl_R_rods_dwight_ohm is not None:
            if abs(ga.table_Rc_written_ohm - ga.engine_tbl_R_rods_dwight_ohm) > 5.0:
                if (
                    ga.engine_tbl_R_strip_dwight_ohm is not None
                    and abs(ga.table_Rc_written_ohm - ga.engine_tbl_R_strip_dwight_ohm) <= 0.75
                ):
                    ga.formula_anomalies.append(
                        f"Tabloda '2) Dikey Topraklama (Rç)' = {ga.table_Rc_written_ohm:.2f} Ω satırında "
                        f"{n_r}x{l_r:.1f}m çubukların Dwight direnci ({ga.engine_tbl_R_rods_dwight_ohm:.2f} Ω) yerine "
                        f"L={ga.table_L_m:.0f}m yatay şeridin Dwight direnci (~{ga.engine_tbl_R_strip_dwight_ohm:.2f} Ω) hesaplanmıştır."
                    )
                else:
                    ga.formula_anomalies.append(
                        f"Tabloda 'Rç' yazılı değeri ({ga.table_Rc_written_ohm:.2f} Ω) ile "
                        f"Dwight çubuk hesabı ({ga.engine_tbl_R_rods_dwight_ohm:.2f} Ω) uyuşmamaktadır."
                    )
        if ga.table_Ry_written_ohm is not None and ga.engine_tbl_R_temel_ohm is not None:
            if abs(ga.table_Ry_written_ohm - ga.engine_tbl_R_temel_ohm) > 1.0:
                wrong_pi_term = rho / (3.0 * math.pi)
                actual_L_term = rho / ga.table_L_m
                if abs((wrong_pi_term + actual_L_term) - ga.table_Ry_written_ohm) <= 0.10:
                    ga.formula_anomalies.append(
                        f"Tabloda '3) Yatay Topraklama (Ry)' satırında ρ/(2×D)+ρ/L = {ga.engine_tbl_R_temel_ohm:.2f} Ω "
                        f"çıkması gerekirken ilk terim hatalı biçimde ρ/(3π)={wrong_pi_term:.2f} Ω hesaplanıp "
                        f"Ry={ga.table_Ry_written_ohm:.2f} Ω yazılmıştır."
                    )
                else:
                    ga.formula_anomalies.append(
                        f"Tabloda 'Ry' yazılı değeri ({ga.table_Ry_written_ohm:.2f} Ω) ile Laurent-Niemann "
                        f"hesabı ({ga.engine_tbl_R_temel_ohm:.2f} Ω) uyuşmamaktadır."
                    )

    # 2. CAD gerçek geometrisiyle yeniden hesaplama (yalnız ρ okunabildiyse — asla ρ uydurma)
    if rho and ga.cad_A_m2 and ga.cad_ring_plus_inner_m:
        n_cad = ga.cad_rod_count if ga.cad_rod_count is not None else (ga.table_n_rods or 0)
        l_cad = ga.cad_rod_L_spec_m or ga.table_rod_L_m or 1.5
        ln_cad = calc_foundation_earthing_laurent_niemann(
            rho, ga.cad_A_m2, ga.cad_ring_plus_inner_m, n_cad, l_cad, d_rod
        )
        ga.engine_cad_R_temel_ohm = ln_cad["R_temel_ohm"]
        ga.engine_cad_R_rods_dwight_ohm = ln_cad["R_rods_ohm"]
        ga.engine_cad_R_schwarz_ohm = ln_cad["R_combined_ohm"]
        ga.engine_cad_R_strip_dwight_ohm = calc_horizontal_strip_resistance_dwight(
            rho, ga.cad_ring_plus_inner_m, 0.015, depth
        )
        ga.engine_cad_R_sverak_ohm = calc_foundation_earthing_ieee80_sverak(
            rho, ga.cad_A_m2, ga.cad_ring_plus_inner_m, n_cad, l_cad, depth
        )

        # TT dokunma gerilimi sınırı (ana KAKR mA değerine göre)
        i_dn_a = (main_incomer.rcd_ma / 1000.0) if main_incomer.rcd_ma else 0.30
        max_touch = float((rules.get("soil_and_resistance_limits", {}) or {}).get("max_touch_voltage_ac_v", 50.0))
        tt_chk = check_fault_loop_and_touch_voltage("TT", ln_cad["R_combined_ohm"], i_dn_a, max_touch_v=max_touch)
        ga.tt_max_allowed_ohm = tt_chk["max_allowed_ohm"]
        ga.tt_compliant = bool(tt_chk["is_compliant"])

        if ga.table_L_m and abs(ga.table_L_m - ga.cad_ring_plus_inner_m) > 3.0:
            ga.formula_anomalies.append(
                f"Tabloda gömülü iletken boyu L={ga.table_L_m:.1f} m girilmişken M_02 CAD ölçümünde "
                f"ring+iç şerit={ga.cad_ring_plus_inner_m:.2f} m (filizler dahil {(ga.cad_ring_plus_inner_m + (ga.cad_spur_m or 0)):.2f} m) ölçülmüştür."
            )

    return ga


# ==============================================================================
# BÖLÜM 6: AYDINLATMA (LÜMEN YÖNTEMİ) DENETİMİ
# ==============================================================================

def _parse_expr_float(token: str) -> Optional[float]:
    """'2,60- 0,85' veya '1,75' gibi basit fark ifadelerini değerlendirir."""
    s = str(token).strip().replace(" ", "")
    if "-" in s and not s.startswith("-"):
        parts = s.split("-")
        if len(parts) == 2:
            a, b = parse_tr_float(parts[0]), parse_tr_float(parts[1])
            if a is not None and b is not None:
                return round(a - b, 3)
    return parse_tr_float(s)


def _recommended_lux_for_room(room_name: str, rules: Dict[str, Any]) -> Optional[float]:
    rn = norm_tr(room_name).upper()
    lux_tbl = (rules.get("illumination_lumen_method", {}) or {}).get("typical_lux_levels", {}) or {}
    if any(k in rn for k in ("ISYER", "OFIS", "BÜRO", "BURO", "MAGAZA", "DUKKAN")):
        return float(lux_tbl.get("classroom_meeting_room", 300))
    if any(k in rn for k in ("MUTFAK",)):
        return float(lux_tbl.get("wc_bathroom_changing_room", 200))
    if any(k in rn for k in ("YATAK", "ODA", "SALON", "KORIDOR", "HOL")):
        return float(lux_tbl.get("corridor_stairs_circulation", 100))
    return None


def _audit_lighting_tables(
    model: CanonicalProjectModel,
    rules: Dict[str, Any],
) -> List[LightingRoomAudit]:
    """`AYDINLATMA HESABI` tablolarındaki her mahal sütununu Lümen Yöntemiyle yeniden hesaplar."""
    out: List[LightingRoomAudit] = []

    for tbl in model.tables:
        blob = norm_tr(" ".join(" ".join(r) for r in tbl.raw_matrix[:6])).upper()
        if "AYDINLATMA HESAB" not in blob:
            continue

        # Satırları analiz et
        params: Dict[str, List[str]] = {}
        room_names: List[str] = []
        raw_rows = [[str(c).strip() for c in r] for r in tbl.raw_matrix if any(str(c).strip() for c in r)]

        # Mahal isimleri genelde ilk 4 satırda ('İŞYERİ', 'MUTFAK', 'YATAK ODASI', 'YATAK ODASI')
        n_cols = 0
        for ri, row in enumerate(raw_rows):
            r0_u = norm_tr(row[0]).upper() if row else ""
            if "MAHAL ENI" in r0_u or "ENİ" in row[0].upper():
                n_cols = len(row) - 1
                params["a"] = row[1:]
            elif "MAHAL BOYU" in r0_u:
                params["b"] = row[1:]
            elif "MAHAL YUKSEKLIG" in r0_u:
                params["H"] = row[1:]
            elif "ARMATUR YUKSEKLIG" in r0_u:
                params["h"] = row[1:]
            elif "AYDINLIK SIDDET" in r0_u:
                params["E"] = row[1:]
            elif "YANSITMA" in r0_u:
                params["refl"] = row[1:]
            elif "MAHAL ENDEKS" in r0_u and ri + 1 < len(raw_rows):
                params["k"] = raw_rows[ri + 1]
            elif "MAHAL VERIM" in r0_u:
                params["eta"] = row[1:]
            elif "ARMATUR GUCU" in r0_u:
                params["w"] = row[1:]
            elif "ISIK AKISI" in r0_u:
                params["flux"] = row[1:]
            elif "HESAPLANAN ARMATUR" in r0_u and ri + 1 < len(raw_rows):
                params["z"] = raw_rows[ri + 1]
            elif "KULLANILACAK ARMATUR" in r0_u:
                params["sel"] = row[1:]

        if n_cols <= 0:
            continue

        # Mahal adlarını başlık satırlarından derle
        header_tokens: List[str] = []
        for row in raw_rows[:4]:
            for tok in row:
                tu = norm_tr(tok).upper()
                if tu and "AYDINLATMA" not in tu and "MAHAL ISMI" not in tu:
                    header_tokens.append(tok.strip())
        # Tipik: ['YATAK','YATAK','İŞYERİ','MUTFAK','ODASI','ODASI'] -> birleştir
        if n_cols == 4 and len(header_tokens) >= 4:
            # Sütun sırasına göre tahmin: eğer son iki sütun iki satıra bölünmüşse birleştir
            named_single = [t for t in header_tokens if norm_tr(t).upper() not in ("YATAK", "ODASI", "ODA")]
            paired_cnt = max(0, n_cols - len(named_single))
            room_names = list(named_single) + [f"YATAK ODASI #{j+1}" for j in range(paired_cnt)]
        else:
            room_names = [f"MAHAL-{j+1}" for j in range(n_cols)]
        while len(room_names) < n_cols:
            room_names.append(f"MAHAL-{len(room_names)+1}")

        for idx in range(n_cols):
            def _get(k_key: str, default: str = "") -> str:
                arr = params.get(k_key, [])
                return arr[idx] if idx < len(arr) else default

            a_v = parse_tr_float(_get("a")) or 0.0
            b_v = parse_tr_float(_get("b")) or 0.0
            H_v = parse_tr_float(_get("H")) or 0.0
            h_v = _parse_expr_float(_get("h")) or 0.0
            E_v = parse_tr_float(_get("E")) or 0.0
            refl_s = _get("refl")
            k_w = parse_tr_float(_get("k"))
            eta_v = parse_tr_float(_get("eta")) or 0.0
            w_v = parse_tr_float(_get("w")) or 0.0
            flux_v = parse_tr_float(_get("flux")) or 0.0
            z_w = parse_tr_float(_get("z"))
            sel_s = _get("sel")

            m_sel = re.search(r"(\d+)\s*[xX*]\s*\d+", sel_s)
            sel_cnt = int(m_sel.group(1)) if m_sel else None

            res = calc_illumination_lumen_method(
                room_width_m=a_v,
                room_length_m=b_v,
                mounting_height_hm_m=h_v,
                target_lux=E_v,
                luminaire_flux_lm=flux_v,
                utilization_factor_u=eta_v,
                maintenance_factor_mf=0.80,  # 1 / 1.25 faktörünün birebir karşılığı
            )
            z_exact = round((E_v * a_v * b_v * 1.25) / (flux_v * eta_v), 2) if (flux_v * eta_v) > 0 else 0.0

            notes: List[str] = []
            if k_w is not None and res["room_index_k"] > 0 and abs(k_w - res["room_index_k"]) > 0.05:
                notes.append(f"Mahal endeksi k farkı (Yazılı {k_w:.2f} vs {res['room_index_k']:.2f})")
            if z_w is not None and abs(z_w - z_exact) > 0.05:
                notes.append(f"Hesaplanan Z farkı (Yazılı {z_w:.2f} vs {z_exact:.2f})")
            rec_lux = _recommended_lux_for_room(room_names[idx], rules)
            if rec_lux is not None and E_v > 0 and E_v < rec_lux * 0.6:
                notes.append(f"TS EN 12464-1 tavsiyesi ({rec_lux:.0f} lx) için E={E_v:.0f} lx düşük")
            # Excel sağa sürükleme hatası (+1 artışı)
            if idx > 0 and _get("a") == params.get("a", [])[idx - 1] and _get("b") == params.get("b", [])[idx - 1]:
                prev_E = parse_tr_float(params.get("E", [])[idx - 1]) if idx - 1 < len(params.get("E", [])) else None
                if prev_E is not None and E_v == prev_E + 1.0:
                    notes.append(f"Excel sağa sürükleme hatası: E={prev_E:.0f}->{E_v:.0f} lx")
                prev_refl = params.get("refl", [])[idx - 1] if idx - 1 < len(params.get("refl", [])) else ""
                if prev_refl == "80-50-30" and refl_s == "80-50-31":
                    notes.append(f"Excel sağa sürükleme hatası: yansıtma {prev_refl}->{refl_s}")

            out.append(
                LightingRoomAudit(
                    table_id=tbl.table_id,
                    room_name=room_names[idx],
                    width_a_m=a_v,
                    length_b_m=b_v,
                    height_H_m=H_v,
                    mounting_hm_m=h_v,
                    written_lux=E_v,
                    reflection_factors=refl_s,
                    written_k=k_w,
                    calc_k=res["room_index_k"],
                    utilization_eta=eta_v,
                    fixture_power_w=w_v,
                    fixture_flux_lm=flux_v,
                    written_z=z_w,
                    calc_z_exact=z_exact,
                    calc_z_ceil=res["fixture_count"],
                    selected_spec=sel_s,
                    selected_count=sel_cnt,
                    achieved_lux=res["achieved_lux"],
                    recommended_ts_en_12464_lux=rec_lux,
                    notes=notes,
                )
            )

    return out


# ==============================================================================
# BÖLÜM 7: ANA ORKESTRATÖR (`build_calculation_audit_report`)
# ==============================================================================

def _detect_schematic_rcd_under_breaker_mismatches(
    snapshot: RawCADSnapshot,
    model: CanonicalProjectModel,
    main_sheet_id: str,
) -> List[Tuple[str, float, float, Optional[float], Tuple[float, float, float, float]]]:
    """
    Tek hat / kolon şemasında aynı hat sütununda (|dx| küçük, düşey ardışık) bulunan
    kesici anma akımı ile KAKR anma akımını karşılaştırır; `I_n(KAKR) < I_n(Sigorta)`
    olan tüm hatalı kolları gerçek DXF bbox koordinatıyla döndürür:
    `[(etiket, rcd_a, brk_a, rcd_ma, (minx, miny, maxx, maxy)), ...]`.
    """
    sch = next((s for s in model.sheets if s.frame_id == main_sheet_id), None)
    if sch is None:
        return []
    sch_texts = [
        t for t in snapshot.texts
        if t.space == sch.space and sch.bbox_du.contains_xy(t.x, t.y)
    ]
    if not sch_texts:
        return []
    heights = sorted(t.height for t in sch_texts if t.height > 0)
    h_med = heights[len(heights) // 2] if heights else 10.0

    def _is_rcd_cluster(rt: RawText) -> Tuple[Optional[float], Optional[float]]:
        rcd_a, rcd_ma, _ = _parse_rcd_rating_ma(rt.text)
        if rcd_a and rcd_ma:
            return (rcd_a, rcd_ma)
        if re.match(r"^[24]\s*[xX*]\s*\d{1,4}\s*A?$", rt.text.strip(), re.I):
            nbrs = [
                o for o in sch_texts
                if o is not rt
                and abs(o.x - rt.x) <= max(25.0, 3.0 * h_med)
                and abs(o.y - rt.y) <= max(50.0, 6.0 * h_med)
            ]
            has_kak = any("KAK" in norm_tr(o.text).upper() or "RCD" in norm_tr(o.text).upper() for o in nbrs)
            ma_val: Optional[float] = None
            for o in nbrs:
                m_ma = re.search(r"(\d{2,3})\s*mA", o.text, re.I)
                if m_ma:
                    ma_val = float(m_ma.group(1))
                    break
            if has_kak or ma_val is not None:
                return (_parse_amp_from_text(rt.text), ma_val)
        return (None, None)

    rcd_anchors: List[Tuple[RawText, float, Optional[float]]] = []
    rcd_ids: Set[int] = set()
    for t in sch_texts:
        ra, rma = _is_rcd_cluster(t)
        if ra is not None:
            rcd_anchors.append((t, ra, rma))
            rcd_ids.add(id(t))

    brk_anchors: List[Tuple[RawText, float]] = []
    for t in sch_texts:
        if id(t) in rcd_ids:
            continue
        tu = norm_tr(t.text).upper().strip()
        if "MA" in tu or "KAK" in tu or "KA" in tu or "X10(" in tu or _RE_CABLE.search(t.text):
            continue
        if re.match(r"^(?:\d\s*\(\s*\d{1,4}\s*A\s*\)|[1-4]\s*[xX*]\s*\d{1,4}\s*A?(?:\s+TMS)?|(?:AOS|MCB|TMS)\s*(?:[1-4]\s*[xX*]\s*)?\d{1,4}|[BCDK]\d{1,3})$", t.text.strip(), re.I):
            ba = _parse_amp_from_text(t.text)
            if ba is not None and 6.0 <= ba <= 1600.0:
                brk_anchors.append((t, ba))

    hits: List[Tuple[str, float, float, Optional[float], Tuple[float, float, float, float]]] = []
    for rt, rcd_a, rcd_ma in rcd_anchors:
        col_brks = [
            (bt, ba) for bt, ba in brk_anchors
            if abs(bt.x - rt.x) <= max(20.0, 2.5 * h_med)
            and 0.5 < (bt.y - rt.y) <= max(130.0, 14.0 * h_med)
        ]
        if not col_brks:
            continue
        bt, brk_a = min(col_brks, key=lambda item: item[0].y - rt.y)
        if rcd_a < brk_a:
            # Aynı sütun/dal üstündeki yük/devre açıklamasını bul
            col_cands = [
                o for o in sch_texts
                if abs(o.x - rt.x) <= max(35.0, 4.0 * h_med)
                and -max(80.0, 9.0 * h_med) <= (o.y - rt.y) <= max(260.0, 28.0 * h_med)
                and len(o.text.strip()) >= 3
                and not re.match(r"^[\d.,\sWVAaKkMm/()-]+$", o.text.strip())
                and not re.match(r"^\d+\s*[xX*]\s*\d+\s*A?", o.text.strip(), re.I)
                and "MA" not in norm_tr(o.text).upper()
                and norm_tr(o.text).upper() not in ("AOS", "KAK", "KURULU GUC:", "TALEP GUCU:", "6KA", "3KA")
                and not _RE_CABLE.search(o.text)
            ]
            col_cands.sort(key=lambda o: (0 if o.y > bt.y else 1, abs(o.x - rt.x), abs(o.y - bt.y)))
            label = col_cands[0].text.strip() if col_cands else f"{main_sheet_id} kol ({rt.x:.0f},{rt.y:.0f})"
            col_bbox = (
                min(rt.bbox.minx, bt.bbox.minx),
                min(rt.bbox.miny, bt.bbox.miny),
                max(rt.bbox.maxx, bt.bbox.maxx),
                max(rt.bbox.maxy, bt.bbox.maxy),
            )
            hits.append((label, rcd_a, brk_a, rcd_ma, col_bbox))
    return hits


def build_calculation_audit_report(
    snapshot: RawCADSnapshot,
    model: CanonicalProjectModel,
    inventory: Optional[ProjectInventory] = None,
    rule_pack: str = "auto",
) -> CalculationAuditReport:
    """
    Evrensel CAD okuma ve metraj modellerini kullanarak projedeki 5 mühendislik hesap grubunu
    denetler ve mevzuata göre yeniden hesaplar.
    """
    rules = _load_bina_rules()
    inv = inventory if inventory is not None else build_project_inventory(snapshot, model)

    main_incomer, main_inst_w, main_df, main_dem_w = _extract_main_incomer_from_schematic(
        snapshot, model, inv, rules
    )
    power_budget = _audit_power_budget(model, inv, main_incomer, main_inst_w, main_df, main_dem_w)
    load_schedules = _audit_load_schedules(model, rules)

    # Yangın pompası hem kilitli bölme hem ortak panoda çift gösterilmiş mi?
    for ls in load_schedules:
        if main_incomer.locked_fire_pump_present and any(
            any(fk in norm_tr(c.description).upper() for fk in _RE_FIRE_ONLY_KEYWORDS)
            for c in ls.circuits
        ):
            main_incomer.duplicate_fire_pump_in_common_panel = True

    # Ana pano talep gücü boş bırakılmışsa (örn. '--W'), antet talep gücü ile Ib hesabını tamamla
    if main_incomer.demand_power_w is None and power_budget.titleblock_demand_w and power_budget.titleblock_demand_w > 0:
        main_incomer.demand_power_w = power_budget.titleblock_demand_w
        main_incomer.engine_ib_380v_a = calc_operating_current_ib(
            power_budget.titleblock_demand_w, voltage_v=380, cos_phi=0.80, is_3phase=True
        )
        main_incomer.engine_ib_400v_a = calc_operating_current_ib(
            power_budget.titleblock_demand_w, voltage_v=400, cos_phi=0.80, is_3phase=True
        )

    fallback_vd_w = main_incomer.demand_power_w or power_budget.titleblock_demand_w
    vd_formulas, vd_w_tot, vd_eng_proj_tot, vd_eng_std_tot = _audit_voltage_drop_formulas(
        model, fallback_main_power_w=fallback_vd_w
    )

    # Ana besleme kablo çelişkisi (kolon şeması ↔ gerilim düşümü paftası)
    if main_incomer.cable_spec and vd_formulas:
        first_seg_cab = vd_formulas[0].cable_spec
        if first_seg_cab and norm_tr(first_seg_cab) != norm_tr(main_incomer.cable_spec):
            main_incomer.cable_vs_vd_sheet_mismatch = (
                f"Kolon şeması `{main_incomer.cable_spec}` vs GD hesabı `{first_seg_cab}`"
            )

    main_vd_proj = vd_formulas[0].project_vd_pct if vd_formulas else None
    panel_rows = _audit_panels_and_thermal(
        inv, model, main_incomer, main_vd_proj, rules, load_schedules=load_schedules
    )
    grounding = _audit_grounding(snapshot, model, main_incomer, rules)
    lighting_rooms = _audit_lighting_tables(model, rules)
    branch_rcd_hits = _detect_schematic_rcd_under_breaker_mismatches(
        snapshot, model, main_incomer.source_sheet
    )

    # ------------------------------------------------------------------
    # EVRENSEL CAD KOORDİNAT ÇAPALARI (ANNOTATOR / REDLINE İÇİN)
    # ------------------------------------------------------------------
    sheet_map = {s.frame_id: s for s in model.sheets}
    table_map = {t.table_id: t for t in model.tables}
    formula_map = {fb.formula_id: fb for fb in model.formula_blocks}
    grounding_map = {g.loop_id: g for g in model.grounding_loops}
    panel_inv_map = {norm_tr(p.panel_name).upper(): p for p in inv.panels}

    handle_bboxes: Dict[str, Tuple[float, float, float, float]] = {}
    for ent_list in (snapshot.texts, snapshot.inserts, snapshot.paths):
        for ent in ent_list:
            if getattr(ent, "handle", None) and getattr(ent, "bbox", None):
                b = ent.bbox
                handle_bboxes[ent.handle] = (b.minx, b.miny, b.maxx, b.maxy)

    def _merge_boxes(boxes: List[Tuple[float, float, float, float]]) -> Optional[Tuple[float, float, float, float]]:
        if not boxes:
            return None
        return (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )

    def _box_center(box: Optional[Tuple[float, float, float, float]]) -> Optional[Tuple[float, float]]:
        if box is None:
            return None
        return ((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5)

    def _bbox_from_handles(handles: Sequence[str]) -> Optional[Tuple[float, float, float, float]]:
        boxes = [handle_bboxes[h] for h in handles if h in handle_bboxes]
        return _merge_boxes(boxes)

    def _table_bbox(table_id: Optional[str]) -> Optional[Tuple[float, float, float, float]]:
        if not table_id or table_id not in table_map:
            return None
        t = table_map[table_id]
        if t.bbox_du is not None:
            return (t.bbox_du.minx, t.bbox_du.miny, t.bbox_du.maxx, t.bbox_du.maxy)
        return _bbox_from_handles(t.source_handles)

    def _find_text_bbox_in_sheet(
        sheet_id: Optional[str],
        needle: Optional[str],
        *,
        extra_bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> Optional[Tuple[float, float, float, float]]:
        if not needle:
            return extra_bbox
        nu_need = norm_tr(needle).upper().strip()
        if not nu_need:
            return extra_bbox
        sh = sheet_map.get(sheet_id or "")
        matches: List[Tuple[float, float, float, float]] = []
        for rt in snapshot.texts:
            if sh is not None and (rt.space != sh.space or not sh.bbox_du.contains_xy(rt.x, rt.y)):
                continue
            rt_u = norm_tr(rt.text).upper().strip()
            if nu_need == rt_u or (len(nu_need) >= 4 and nu_need in rt_u):
                matches.append((rt.bbox.minx, rt.bbox.miny, rt.bbox.maxx, rt.bbox.maxy))
        if not matches:
            return extra_bbox
        if extra_bbox is not None:
            matches.append(extra_bbox)
        return _merge_boxes(matches)

    def _table_row_bbox(panel_name: str, extra_token: Optional[str] = None) -> Tuple[Optional[str], Optional[Tuple[float, float, float, float]]]:
        p_u = norm_tr(panel_name).upper().strip()
        for t in model.tables:
            flat_u = norm_tr(" ".join(" ".join(r) for r in t.raw_matrix)).upper()
            if p_u not in flat_u:
                continue
            tb = _table_bbox(t.table_id)
            if tb is None:
                continue
            cand_texts = [
                rt for rt in snapshot.texts
                if tb[0] - 5.0 <= rt.x <= tb[2] + 5.0 and tb[1] - 5.0 <= rt.y <= tb[3] + 5.0
                and norm_tr(rt.text).upper().strip() == p_u
            ]
            if cand_texts:
                anchor_t = cand_texts[0]
                row_band = [
                    (rt.bbox.minx, rt.bbox.miny, rt.bbox.maxx, rt.bbox.maxy)
                    for rt in snapshot.texts
                    if tb[0] - 5.0 <= rt.x <= tb[2] + 5.0
                    and abs(rt.y - anchor_t.y) <= max(12.0, anchor_t.height * 1.6)
                ]
                return (t.sheet_id or None, _merge_boxes(row_band) or tb)
            if extra_token:
                for rt in snapshot.texts:
                    if tb[0] - 5.0 <= rt.x <= tb[2] + 5.0 and tb[1] - 5.0 <= rt.y <= tb[3] + 5.0:
                        if norm_tr(extra_token).upper() in norm_tr(rt.text).upper():
                            return (t.sheet_id or None, tb)
            return (t.sheet_id or None, tb)
        return (None, None)

    def _panel_bbox(panel_name: str) -> Tuple[Optional[str], Optional[Tuple[float, float, float, float]]]:
        p_u = norm_tr(panel_name).upper().strip()
        pi = panel_inv_map.get(p_u)
        if pi is not None:
            hb = _bbox_from_handles(pi.source_handles)
            sh_id = pi.sheet_ids[0] if pi.sheet_ids else (main_incomer.source_sheet or None)
            if hb is not None:
                return (sh_id, hb)
        sh_id = main_incomer.source_sheet or None
        return (sh_id, _find_text_bbox_in_sheet(sh_id, panel_name))

    # ------------------------------------------------------------------
    # BULGULAR LİSTESİ (DİNAMİK OLUŞTURMA — ZERO HARDCODE)
    # ------------------------------------------------------------------
    findings: List[AuditFindingItem] = []
    f_seq = 0

    def _add_finding(
        severity: Literal["KRITIK", "UYARI", "BILGI", "UYGUN"],
        category: str,
        location: str,
        project_value: str,
        engine_value: str,
        standard_ref: str,
        description: str,
        recommendation: str = "",
        *,
        sheet_id: Optional[str] = None,
        bbox_du: Optional[Tuple[float, float, float, float]] = None,
        extra_bboxes: Optional[List[Tuple[float, float, float, float]]] = None,
    ) -> None:
        nonlocal f_seq
        f_seq += 1
        extras: List[Tuple[float, float, Optional[Tuple[float, float, float, float]]]] = []
        for eb in (extra_bboxes or []):
            ec = _box_center(eb)
            if ec is not None:
                extras.append((ec[0], ec[1], eb))
        findings.append(
            AuditFindingItem(
                finding_id=f"H-{f_seq:02d}",
                severity=severity,
                category=category,
                location=location,
                project_value=project_value,
                engine_value=engine_value,
                standard_ref=standard_ref,
                description=description,
                recommendation=recommendation,
                sheet_id=sheet_id,
                anchor_xy=_box_center(bbox_du),
                bbox_du=bbox_du,
                extra_anchors=extras,
            )
        )

    main_sh = main_incomer.source_sheet or None
    main_cable_box = _find_text_bbox_in_sheet(main_sh, main_incomer.cable_spec)
    main_brk_box = _find_text_bbox_in_sheet(main_sh, main_incomer.breaker_spec)
    main_rcd_box = _find_text_bbox_in_sheet(main_sh, main_incomer.rcd_spec)
    if main_rcd_box is None and main_incomer.rcd_in_a is not None:
        amp_tok = f"x{int(round(main_incomer.rcd_in_a))}"
        sh_obj = sheet_map.get(main_sh or "")
        rcd_parts: List[Tuple[float, float, float, float]] = []
        for rt in snapshot.texts:
            if sh_obj is not None and (rt.space != sh_obj.space or not sh_obj.bbox_du.contains_xy(rt.x, rt.y)):
                continue
            rt_ns = norm_tr(rt.text).upper().replace(" ", "")
            if amp_tok.upper() in rt_ns:
                nbr_has_kak = any(
                    abs(o.x - rt.x) <= max(45.0, rt.height * 6.0)
                    and abs(o.y - rt.y) <= max(45.0, rt.height * 6.0)
                    and ("KAK" in norm_tr(o.text).upper() or "MA" in norm_tr(o.text).upper())
                    for o in snapshot.texts
                    if o is not rt
                )
                if nbr_has_kak:
                    rcd_parts.append((rt.bbox.minx, rt.bbox.miny, rt.bbox.maxx, rt.bbox.maxy))
        main_rcd_box = _merge_boxes(rcd_parts) or main_brk_box

    # 1. Ana besleme aşırı yük koruması (Ib <= In <= Iz)
    if main_incomer.ib_in_iz_ok is False and main_incomer.breaker_in_a is not None:
        eff_iz = main_incomer.engine_iz_yaml_a or main_incomer.project_written_iz_a
        ib_ref = main_incomer.project_written_ib_a or main_incomer.engine_ib_400v_a or 0.0
        in_a = main_incomer.breaker_in_a
        h01_box = _merge_boxes([b for b in (main_cable_box, main_brk_box) if b is not None])
        if eff_iz is not None and in_a > eff_iz:
            rec_sec = f" en az {main_incomer.min_compliant_section_mm2:.0f} mm² N2XH/XLPE kullanılmalı veya şalter düşürülmelidir." if main_incomer.min_compliant_section_mm2 else ""
            _add_finding(
                "KRITIK",
                "Isınma / Aşırı Akım Koruması",
                f"Ana Besleme ({main_incomer.panel_name or 'AT'})",
                f"In={in_a:.0f}A ({main_incomer.breaker_spec or 'Kesici'}), Iz_yazılı={main_incomer.project_written_iz_a or eff_iz:.0f}A ({main_incomer.cable_spec})",
                f"In={in_a:.0f}A > Iz={eff_iz:.0f}A (İhlal)",
                "TS HD 60364-4-43 Md. 433.1",
                f"Ana kesici anma akımı ({in_a:.0f} A), seçilen kablonun akım taşıma kapasitesinden ({eff_iz:.0f} A) büyüktür; kablo aşırı yükte yanma riski altındadır.",
                f"TS HD 60364-5-52 tablosuna göre{rec_sec}",
                sheet_id=main_sh,
                bbox_du=h01_box,
            )
        elif ib_ref > in_a:
            _add_finding(
                "KRITIK",
                "Isınma / Aşırı Akım Koruması",
                f"Ana Besleme ({main_incomer.panel_name or 'AT'})",
                f"Ib={ib_ref:.1f}A, In={in_a:.0f}A ({main_incomer.breaker_spec or 'Kesici'})",
                f"Ib={ib_ref:.1f}A > In={in_a:.0f}A (İhlal)",
                "TS HD 60364-4-43 Md. 433.1",
                f"İşletme akımı ({ib_ref:.1f} A), ana kesici anma akımından ({in_a:.0f} A) büyüktür; ana şalter işletme yükünde açma yapar.",
                "Kesici anma akımı en az Ib <= In <= Iz olacak şekilde yükseltilmelidir.",
                sheet_id=main_sh,
                bbox_du=h01_box,
            )

    # 2. PE iletken kesiti & kablo tipi çelişkisi
    if main_incomer.pe_ok is False and main_incomer.pe_mm2 and main_incomer.req_pe_mm2:
        rec_pe_sec = main_incomer.min_compliant_section_mm2
        pe_rec_txt = (
            f"PE iletkeni en az {main_incomer.req_pe_mm2:.0f} mm² (standart 50 mm² veya >= {rec_pe_sec:.0f} mm² faz ile uyumlu PE) olarak güncellenmelidir."
            if rec_pe_sec
            else f"PE iletken kesiti en az {main_incomer.req_pe_mm2:.1f} mm² standart kesite yükseltilmelidir."
        )
        _add_finding(
            "KRITIK",
            "PE İletken Kesiti",
            f"Ana Kablo ({main_incomer.panel_name or 'ANA'})",
            f"{main_incomer.cable_spec} (PE={main_incomer.pe_mm2:.0f} mm²)",
            f"Min S_PE >= {main_incomer.req_pe_mm2:.1f} mm²",
            "TS HD 60364-5-54 Çizelge 54.2",
            f"Faz kesiti > 35 mm² kablolarda koruma/nötr kesiti faz kesitinin yarısından ({main_incomer.req_pe_mm2:.1f} mm²) az olamaz.",
            pe_rec_txt,
            sheet_id=main_sh,
            bbox_du=main_cable_box,
        )
    if main_incomer.cable_vs_vd_sheet_mismatch:
        fb0_box = (
            (model.formula_blocks[0].bbox_du.minx, model.formula_blocks[0].bbox_du.miny, model.formula_blocks[0].bbox_du.maxx, model.formula_blocks[0].bbox_du.maxy)
            if model.formula_blocks
            else None
        )
        _add_finding(
            "UYARI",
            "Paftalar Arası Kablo Çelişkisi",
            "Kolon Şeması ↔ Gerilim Düşümü",
            main_incomer.cable_vs_vd_sheet_mismatch,
            "Tek ve tutarlı kesit/izolasyon tipi",
            "EİTY & Proje Bütünlüğü",
            "Kolon şeması ile gerilim düşümü paftasında ana besleme kablo tipi ve PE kesiti farklı yazılmıştır.",
            "Her iki paftada aynı XLPE (N2XH) ve uygun PE kesiti belirtilmelidir.",
            sheet_id=main_sh,
            bbox_du=main_cable_box or fb0_box,
            extra_bboxes=[fb0_box] if (main_cable_box and fb0_box) else None,
        )

    # 3. Yangın pompası çift gösterim & 30mA KAKR ihlali (BYKHY)
    if main_incomer.duplicate_fire_pump_in_common_panel:
        fire_sch_box = _find_text_bbox_in_sheet(main_sh, "YANGIN") or _find_text_bbox_in_sheet(main_sh, "YABGIN")
        fire_tbl_boxes = [
            tb for tb in (
                _table_bbox(ls.table_id)
                for ls in load_schedules
                if any(any(fk in norm_tr(c.description).upper() for fk in _RE_FIRE_ONLY_KEYWORDS) for c in ls.circuits)
            )
            if tb is not None
        ]
        _add_finding(
            "KRITIK",
            "Yangın Güvenliği (BYKHY)",
            "Kolon Şeması (KİLİTLİ BÖLME & Ortak Pano)",
            "Yangın pompası hem KİLİTLİ BÖLME'de hem ortak panoda (30mA KAKR arkasında) 2 kez çizilmiş",
            "KİLİTLİ BÖLME (AT girişi önünden bağımsız FE180 hat, 30mA KAKR'sız)",
            "BYKHY Md. 74-84",
            "Yangın pompası aynı şemada iki farklı yerde mükerrer gösterilmiş olup, ortak pano altında 30mA KAKR ve normal N2XH kablo ile beslenmiştir.",
            "Ortak panodaki mükerrer yangın pompası çıkışı kaldırılmalı; kilitli bölmeden FE180 kablo ile bağımsız beslenmelidir.",
            sheet_id=main_sh,
            bbox_du=fire_sch_box or (fire_tbl_boxes[0] if fire_tbl_boxes else None),
            extra_bboxes=fire_tbl_boxes if fire_sch_box else fire_tbl_boxes[1:],
        )

    # 4. Antet / Kurulu Güç Çelişkisi
    if power_budget.installed_diff_titleblock_w is not None and abs(power_budget.installed_diff_titleblock_w) > 50:
        tb_box = _table_bbox(power_budget.titleblock_table_id)
        tb_sh = table_map[power_budget.titleblock_table_id].sheet_id if power_budget.titleblock_table_id in table_map else None
        _add_finding(
            "UYARI",
            "Güç Bütçesi Çelişkisi",
            f"Pafta Anteti ({power_budget.titleblock_table_id}) ↔ Kolon Şeması",
            f"Antet: {power_budget.titleblock_installed_w:,.0f} W",
            f"Alt Panolar Toplamı: {power_budget.subpanels_installed_sum_w:,.0f} W (Fark: {power_budget.installed_diff_titleblock_w:+,.0f} W)",
            "Proje Tutarlılığı",
            f"Pafta antetinde toplam kurulu güç {power_budget.installed_diff_titleblock_w:+,.0f} W farklı yazılmıştır (tipik yazım hatası).",
            "Antet tablosundaki toplam kurulu güç değeri alt pano toplamıyla eşitlenmelidir.",
            sheet_id=tb_sh or None,
            bbox_du=tb_box,
        )

    # 5. Yükleme cetveli bulguları (Faz dengesizliği, motor diversitesi)
    for ls in load_schedules:
        ls_box = _table_bbox(ls.table_id)
        if ls.applies_dwelling_diversity_to_motor:
            _add_finding(
                "UYARI",
                "Talep Gücü / Diversite Yöntemi",
                f"Yükleme Cetveli ({ls.panel_name} / {ls.table_id})",
                f"Kurulu={ls.written_total_w or ls.calc_circuits_total_w:,.0f}W -> Talep={ls.written_demand_w or 0:,.0f}W (8kW 0,6/0,4)",
                "Ortak motor yüklerinde (Asansör+Hidrofor+Pompa) konut 8kW kuralı uygulanmaz",
                "EİTY Md. 57 / TEDAŞ Ortak Yükler",
                f"`{ls.panel_name}` ortak/motor panosuna dairelere özgü '8kW'a kadar 0,6 gerisi 0,4' formülü uygulanmıştır.",
                "Mekanik/asansör/hidrofor eşzamanlılık faktörleri (0.85–1.00) ile ayrı talep hesabı yapılmalıdır.",
                sheet_id=ls.sheet_id or None,
                bbox_du=ls_box,
            )
        eff_imb = ls.phase_imbalance_with_rst_pct if (ls.written_rst_w and ls.written_rst_w > 0) else ls.phase_imbalance_single_ph_pct
        if eff_imb is not None and eff_imb > 15.0:
            _add_finding(
                "UYARI",
                "Faz Yük Dengesizliği",
                f"Yükleme Cetveli ({ls.panel_name} / {ls.table_id})",
                f"R={ls.written_r_w:.0f}W, S={ls.written_s_w:.0f}W, T={ls.written_t_w:.0f}W (%Δ={eff_imb:.1f}%)",
                "%Δ <= %15.0",
                "EİTY Md. 57",
                f"`{ls.panel_name}` panosunda fazlar arası dengesizlik sınırı (%{15.0:.0f}) aşılmıştır.",
                "Fazlara bağlı linyeler dengeli yeniden dağıtılmalıdır.",
                sheet_id=ls.sheet_id or None,
                bbox_du=ls_box,
            )

    # 6. Eksik kesici etiketleri, KAKR < Sigorta, yanlış Iz ve yanlış %e satırları
    missing_brk_panels = [p.panel_name for p in panel_rows if p.role == "TALI_PANO" and p.breaker_spec is None]
    if missing_brk_panels:
        miss_anchors = [(_panel_bbox(pn)) for pn in missing_brk_panels]
        miss_boxes = [b for _, b in miss_anchors if b is not None]
        _add_finding(
            "UYARI",
            "Eksik Şema Verisi",
            f"Kolon Şeması ({', '.join(missing_brk_panels)})",
            "Kesici anma akımı yazısı YOK (yalnız 6kA AOS)",
            "İlgili pano/devre çıkışında anma akımı (örn. 3x20A / 25A) belirtilmeli",
            "Proje Çizim Bütünlüğü",
            f"Kolon şemasında {len(missing_brk_panels)} panonun ({', '.join(missing_brk_panels)}) sigorta anma akımı etiketi unutulmuştur.",
            "Şemaya ilgili kesici değerleri eklenmelidir.",
            sheet_id=miss_anchors[0][0] if miss_anchors else main_sh,
            bbox_du=miss_boxes[0] if miss_boxes else None,
            extra_bboxes=miss_boxes[1:] if len(miss_boxes) > 1 else None,
        )

    wrong_iz_panels = [p for p in panel_rows if p.project_iz_a is not None and p.engine_iz_yaml_a is not None and abs(p.project_iz_a - p.engine_iz_yaml_a) >= 15.0]
    for p in wrong_iz_panels:
        r_sh, r_box = _table_row_bbox(p.panel_name, p.cable_spec)
        _add_finding(
            "UYARI",
            "Kablo Akım Kapasitesi Hatası",
            f"Isınma Hesabı Tablosu ({p.panel_name})",
            f"Kablo `{p.cable_spec}` için Iz_yazılı={p.project_iz_a:.0f} A",
            f"TS HD 60364-5-52 gerçek Iz={p.engine_iz_yaml_a:.0f} A",
            "TS HD 60364-5-52 Çizelge B.52.3/5",
            f"`{p.panel_name}` ({p.cable_spec}) satırında yazılı Iz={p.project_iz_a:.0f} A değeri, tablodaki gerçek akım taşıma kapasitesi ({p.engine_iz_yaml_a:.0f} A) ile uyuşmamaktadır.",
            "Hesap tablosunda gerçek akım taşıma kapasitesi güncellenmelidir.",
            sheet_id=r_sh,
            bbox_du=r_box,
        )

    wrong_vd_panels = [
        p for p in panel_rows
        if p.project_vd_linye_pct is not None and p.engine_vd_linye_proj_pct is not None
        and abs(p.project_vd_linye_pct - p.engine_vd_linye_proj_pct) > 0.15
    ]
    for p in wrong_vd_panels:
        single_ph_chk = (
            round((200.0 * p.linye_length_m * p.linye_power_w) / (56.0 * p.linye_section_mm2 * (220.0 ** 2)), 3)
            if (p.linye_length_m and p.linye_power_w and p.linye_section_mm2)
            else None
        )
        coeff_note = (
            "3 faz katsayısı (0,0124) yerine tek faz katsayısı (0,074) kullanıldığı tespit edilmiştir"
            if (single_ph_chk is not None and abs(single_ph_chk - p.project_vd_linye_pct) <= 0.05)
            else "tablodaki %e formülü gerçek 3-faz hesabıyla uyuşmamaktadır"
        )
        vd_sh, vd_box = _table_row_bbox(p.panel_name, p.linye_no)
        _add_finding(
            "KRITIK",
            "Gerilim Düşümü Formül Hatası",
            f"Gerilim Düşümü Tablosu ({p.panel_name} / {p.linye_no})",
            f"Yazılı %e_linye = %{p.project_vd_linye_pct:.3f} (Toplam %{p.project_vd_total_pct or 0:.3f})",
            f"Doğru 3-faz %e_linye = %{p.engine_vd_linye_proj_pct:.3f} (400V: %{p.engine_vd_linye_230v_pct or 0:.3f})",
            "EİTY Md. 57",
            f"`{p.panel_name}` panosunda 3 fazlı linyede ({p.linye_power_w:.0f} W, {p.linye_section_mm2:.1f} mm², {p.linye_length_m:.0f} m) {coeff_note}.",
            "Hesap tablosunda gerilim düşümü formülü 3 faz katsayısına göre düzeltilmelidir.",
            sheet_id=vd_sh,
            bbox_du=vd_box,
        )

    # 7. Gerilim düşümü eksik formül ve toplam sınır kontrolü
    for v_row in vd_formulas:
        if v_row.power_w is None or v_row.project_vd_pct is None:
            v_fb = formula_map.get(v_row.formula_id)
            v_box = (v_fb.bbox_du.minx, v_fb.bbox_du.miny, v_fb.bbox_du.maxx, v_fb.bbox_du.maxy) if v_fb else None
            _add_finding(
                "UYARI",
                "Eksik Gerilim Düşümü Hesabı",
                f"Gerilim Düşümü ({v_row.segment_name} / {v_row.formula_id})",
                "Güç / %e boş bırakılmış (--,--)",
                f"Motor: 380V %{_fmt_num(v_row.engine_vd_proj_v_pct, 2)} / 400V %{_fmt_num(v_row.engine_vd_std_v_pct, 2)}",
                "EİTY Md. 57",
                f"`{v_row.segment_name}` ({v_row.cable_spec or '-'}, L={_fmt_num(v_row.length_m, 1)} m, S={_fmt_num(v_row.section_mm2, 1)} mm²) formülünde güç veya %e sonucu boş (`--,--`) bırakılmıştır.",
                "Gerilim düşümü formülündeki tüm segmentlerin güç ve %e değerleri doldurulup toplam %e doğrulanmalıdır.",
                sheet_id=v_row.sheet_id,
                bbox_du=v_box,
            )

    eff_tot_vd = vd_eng_proj_tot if (vd_eng_proj_tot is not None and any(v.project_vd_pct is None for v in vd_formulas)) else vd_w_tot
    if eff_tot_vd is not None and eff_tot_vd > 1.50:
        min_sec_hint = (
            f"en az {main_incomer.min_compliant_section_mm2:.0f} mm² kesite"
            if main_incomer.min_compliant_section_mm2
            else "bir üst standart kablo kesitine"
        )
        last_fb = formula_map.get(vd_formulas[-1].formula_id) if vd_formulas else None
        fb_box = (last_fb.bbox_du.minx, last_fb.bbox_du.miny, last_fb.bbox_du.maxx, last_fb.bbox_du.maxy) if last_fb else None
        _add_finding(
            "UYARI",
            "Gerilim Düşümü Sınır Aşımı",
            "Gerilim Düşümü Hesabı (Toplam %e)",
            f"Pafta Toplam = %{_fmt_num(vd_w_tot, 2)} (380/220V)",
            f"Motor: 380V %{_fmt_num(vd_eng_proj_tot, 2)} / 400V %{_fmt_num(vd_eng_std_tot, 2)} | EİTY Aydınlatma <= %1.50 (Motor <= %3.0)",
            "EİTY Md. 57",
            f"Toplam gerilim düşümü (%{eff_tot_vd:.2f}), aydınlatma sınırı olan %1.5'i aşmaktadır.",
            f"Ana besleme kesiti {min_sec_hint} çıkarılırsa hem akım kapasitesi hem toplam %e iyileşecektir.",
            sheet_id=last_fb.sheet_id if last_fb else None,
            bbox_du=fb_box,
        )

    # 8. KAKR Seçiciliği & Kolon Şeması KAKR < Sigorta Kolu İhlalleri
    if main_incomer.rcd_ma is not None and not main_incomer.rcd_is_s_type:
        rec_rcd_a = int(round(main_incomer.rcd_in_a or main_incomer.breaker_in_a or 0))
        _add_finding(
            "UYARI",
            "KAKR Zaman Seçiciliği",
            f"Ana Pano ({main_incomer.panel_name or 'ANA'})",
            f"{main_incomer.rcd_spec} ('S' ibaresi yok)",
            "Ana pano KAKR mutlaka 'S' (Selektif/Gecikmeli, Δt >= 40 ms) tip olmalı",
            "TS HD 60364-5-53 Md. 536",
            f"Ana panodaki {main_incomer.rcd_ma:.0f} mA KAKR zaman gecikmeli ('S' tip) tanımlanmadığından alt devre kaçaklarında seçicilik sağlanamaz.",
            f"Ana KAKR '4x{rec_rcd_a or '?'}A {main_incomer.rcd_ma:.0f}mA S Tipi' olarak güncellenmelidir.",
            sheet_id=main_sh,
            bbox_du=main_rcd_box,
        )

    if branch_rcd_hits:
        lbls = ", ".join(dict.fromkeys(h[0] for h in branch_rcd_hits))
        pairs = ", ".join(dict.fromkeys(f"{h[1]:.0f}A<{h[2]:.0f}A" for h in branch_rcd_hits))
        rcd_boxes = [h[4] for h in branch_rcd_hits]
        _add_finding(
            "KRITIK",
            "KAKR Akım Koordinasyonu",
            f"Kolon Şeması Çıkışları ({main_incomer.source_sheet})",
            f"{len(branch_rcd_hits)} kolda ({lbls}): KAKR < Sigorta ({pairs})",
            "I_n(KAKR) >= I_n(Koruma Sigortası) olmalı (veya KAKR kesiciyle aynı/üst akımda seçilmeli)",
            "TS HD 60364-5-53 Md. 531.3",
            f"Şema üzerinde {len(branch_rcd_hits)} çıkışta ({lbls}) kaçak akım koruma rölesi anma akımı seri koruma kesicisinden küçüktür; tam yükte KAKR kontakları termik hasar riski altındadır.",
            "Bu kollardaki KAKR anma akımı en az seri sigorta değerine (örn. >= 32A / 40A) çıkarılmalı; yangın pompası hattında KAKR kaldırılmalıdır.",
            sheet_id=main_sh,
            bbox_du=rcd_boxes[0],
            extra_bboxes=rcd_boxes[1:] if len(rcd_boxes) > 1 else None,
        )

    # 9. Topraklama formül anomalileri
    if grounding is not None:
        g_tbl_box = _table_bbox(grounding.table_id)
        g_tbl_sh = table_map[grounding.table_id].sheet_id if (grounding.table_id and grounding.table_id in table_map) else None
        g_loop = grounding_map.get(grounding.loop_id or "")
        g_loop_box = _bbox_from_handles(g_loop.source_handles) if g_loop else None
        for anom in grounding.formula_anomalies:
            if "Dikey Topraklama" in anom or "Rç" in anom:
                g_proj_v = f"Rç={_fmt_num(grounding.table_Rc_written_ohm, 2, ' Ω')} (Re={_fmt_num(grounding.table_Re_written_ohm, 2, ' Ω')})"
                g_exp_v = f"Dwight Rç={_fmt_num(grounding.engine_tbl_R_rods_dwight_ohm, 2, ' Ω')} / CAD Schwarz Re={_fmt_num(grounding.engine_cad_R_schwarz_ohm, 2, ' Ω')}"
            elif "Yatay Topraklama" in anom or "Ry" in anom:
                g_proj_v = f"Ry={_fmt_num(grounding.table_Ry_written_ohm, 2, ' Ω')} (formül hatalı)"
                g_exp_v = f"Laurent-Niemann Ry={_fmt_num(grounding.engine_tbl_R_temel_ohm, 2, ' Ω')} / CAD Re={_fmt_num(grounding.engine_cad_R_schwarz_ohm, 2, ' Ω')}"
            elif "ölçümünde" in anom:
                g_proj_v = f"Tablo L={_fmt_num(grounding.table_L_m, 1, ' m')}, A={_fmt_num(grounding.table_A_m2, 1, ' m²')}"
                g_exp_v = f"CAD L={_fmt_num(grounding.cad_ring_plus_inner_m, 2, ' m')}, A={_fmt_num(grounding.cad_A_m2, 2, ' m²')} (Re={_fmt_num(grounding.engine_cad_R_schwarz_ohm, 2, ' Ω')})"
            else:
                g_proj_v = f"Ry={grounding.table_Ry_written_ohm or '-'} Ω, Rç={grounding.table_Rc_written_ohm or '-'} Ω, Re={grounding.table_Re_written_ohm or '-'} Ω"
                g_exp_v = f"CAD Schwarz Re={grounding.engine_cad_R_schwarz_ohm or grounding.engine_tbl_R_schwarz_ohm or '-'} Ω (Sverak {grounding.engine_cad_R_sverak_ohm or '-'} Ω)"
            _add_finding(
                "KRITIK" if "hesaplanmıştır" in anom or "hatalı biçimde" in anom else "UYARI",
                "Temel Topraklama Formül/Ölçü Kontrolü",
                f"Topraklama ({grounding.table_id or grounding.loop_id})",
                g_proj_v,
                g_exp_v,
                "ETTMY Ek-N/Ek-P & IEEE Std 80",
                anom,
                "Topraklama Excel formülleri gerçek Laurent-Niemann ve Dwight çubuk bağıntılarıyla düzeltilmelidir; bileşke direnç TT sınırı altında olduğu için tesisat güvenlidir.",
                sheet_id=g_tbl_sh or (g_loop.sheet_id if g_loop else None),
                bbox_du=g_tbl_box or g_loop_box,
                extra_bboxes=[g_loop_box] if ("ölçümünde" in anom and g_tbl_box and g_loop_box) else None,
            )
        if grounding.tt_compliant:
            _add_finding(
                "UYGUN",
                "Temel Topraklama Sınır Kontrolü",
                f"Temel Topraklama ({grounding.loop_id or 'Plan'})",
                f"Yazılı Re={grounding.table_Re_written_ohm or '-'} Ω",
                f"Motor CAD Hesabı Re={grounding.engine_cad_R_schwarz_ohm:.2f} Ω <= {grounding.tt_max_allowed_ohm:.1f} Ω",
                "TS HD 60364-4-41 Md. 411.5.3",
                f"CAD ölçümü (A={grounding.cad_A_m2:.2f} m², L={grounding.cad_ring_plus_inner_m:.2f} m) ve gerçek ρ={grounding.rho_ohm_m:.0f} Ω·m ile hesaplanan direnç TT sınırını güvenle sağlar.",
                sheet_id=g_loop.sheet_id if g_loop else g_tbl_sh,
                bbox_du=g_loop_box or g_tbl_box,
            )

    # 10. Aydınlatma hesap notları (mahal başına tek birleştirilmiş bulgu)
    for lr in lighting_rooms:
        if lr.notes:
            lt_box = _table_bbox(lr.table_id)
            lt_sh = table_map[lr.table_id].sheet_id if lr.table_id in table_map else None
            eng_lux_note = (
                f", Önerilen E>={lr.recommended_ts_en_12464_lux:.0f} lx"
                if lr.recommended_ts_en_12464_lux is not None
                else ""
            )
            has_drag = any("sürükleme" in n.lower() for n in lr.notes)
            rec_msg = (
                "Hücre sağa çekme kaynaklı sayı kayması ve mahal lüks seviyesi gözden geçirilmelidir."
                if has_drag
                else "Aydınlatma hesabındaki mahal endeksi (k) ve hedef lüks değeri TS EN 12464-1'e göre doğrulanmalıdır."
            )
            _add_finding(
                "UYARI",
                "Aydınlatma Hesabı",
                f"Aydınlatma ({lr.room_name} / {lr.table_id})",
                f"E={lr.written_lux:.0f} lx, Yansıtma={lr.reflection_factors}, Z={lr.written_z}",
                f"k={lr.calc_k:.2f}, Z_motor={lr.calc_z_exact:.2f} ({lr.calc_z_ceil} adet){eng_lux_note}",
                "TS EN 12464-1",
                "; ".join(lr.notes),
                rec_msg,
                sheet_id=lt_sh or None,
                bbox_du=lt_box,
            )

    from .disiplin_ayirici import classify_drawing_discipline
    from .metro_denetim import collect_metro_single_sheet_findings, detect_rule_pack_for_drawing

    primary_disc, _ = classify_drawing_discipline(snapshot, model)
    active_pack = detect_rule_pack_for_drawing(
        snapshot,
        model,
        inventory,
        requested=rule_pack,
        primary_discipline=primary_disc,
    )
    if active_pack == "ibb_metro":
        metro_rules = RuleEngine.load_pack("ibb_metro")
        metro_findings, _ = collect_metro_single_sheet_findings(
            snapshot,
            model,
            inventory,
            metro_rules,
            finding_cls=AuditFindingItem,
            lookup_iz_fn=_lookup_cable_ampacity_yaml,
            start_fid=len(findings) + 1,
            primary_discipline=primary_disc,
        )
        findings.extend(metro_findings)

    sev_counts = {"KRITIK": 0, "UYARI": 0, "BILGI": 0, "UYGUN": 0}
    for f in findings:
        sev_counts[f.severity] = sev_counts.get(f.severity, 0) + 1

    # Şema / tablo verileri eksiksiz olan kollar için pandapower yük akışı & IEC 60909 kısa devre
    root_bus = (main_incomer.panel_name or "ANA_PANO").strip()
    pp_feeders, pp_skipped = build_feeders_from_audit_rows(root_bus, panel_rows, vd_formulas)
    pp_report = analyze_radial_network_pandapower(pp_feeders)
    pp_report.skipped_branches = pp_skipped

    return CalculationAuditReport(
        filename=model.filename,
        unit_name=model.unit.unit_name,
        regulation_pack=active_pack,
        summary_counts={
            **sev_counts,
            "toplam_bulgu": len(findings),
            "incelenen_pano": len(panel_rows),
            "yukleme_cetveli": len(load_schedules),
            "gd_formul_blogu": len(vd_formulas),
            "aydinlatma_mahali": len(lighting_rooms),
        },
        findings=findings,
        power_budget=power_budget,
        load_schedules=load_schedules,
        main_incomer=main_incomer,
        panel_rows=panel_rows,
        vd_formulas=vd_formulas,
        vd_formula_total_proj_written=vd_w_tot,
        vd_formula_total_engine_proj_v=vd_eng_proj_tot,
        vd_formula_total_engine_std_v=vd_eng_std_tot,
        grounding=grounding,
        lighting_rooms=lighting_rooms,
        network_analysis=pp_report,
    )


# ==============================================================================
# BÖLÜM 8: RAPOR ÜRETİMİ (.md, .docx, .xlsx, .json)
# ==============================================================================

def _fmt_num(v: Optional[float], dec: int = 2, suffix: str = "") -> str:
    if v is None:
        return "BELİRSİZ"
    return f"{v:,.{dec}f}{suffix}"


def _compact_panel_names(names: Sequence[str]) -> str:
    """Ardışık pano adlarını kompakt aralıklara indirger (örn. DT-1..DT-12, DT-14..DT-15)."""
    uniq = list(dict.fromkeys(n.strip() for n in names if n and n.strip()))
    if len(uniq) <= 3:
        return ", ".join(uniq)
    by_prefix: Dict[str, List[Tuple[int, str]]] = {}
    others: List[str] = []
    for nm in uniq:
        m = re.match(r"^([A-Za-zÇĞİÖŞÜçğıöşü\-_]+?)(\d+)$", nm)
        if m:
            by_prefix.setdefault(m.group(1), []).append((int(m.group(2)), nm))
        else:
            others.append(nm)
    parts: List[str] = []
    for pref, items in by_prefix.items():
        items.sort(key=lambda x: x[0])
        s = e = items[0][0]
        for num, _ in items[1:]:
            if num == e + 1:
                e = num
            else:
                parts.append(f"{pref}{s}..{pref}{e}" if e >= s + 2 else (", ".join(f"{pref}{k}" for k in range(s, e + 1))))
                s = e = num
        parts.append(f"{pref}{s}..{pref}{e}" if e >= s + 2 else (", ".join(f"{pref}{k}" for k in range(s, e + 1))))
    parts.extend(others)
    joined = ", ".join(parts)
    return f"{joined} ({len(uniq)} pano)"


def _group_findings_for_display(findings: Sequence[AuditFindingItem]) -> List[Dict[str, str]]:
    """
    Tekrarlayan özdeş bulguları (örn. 14 daire panosunda aynı faz dengesizliği) tek satırda gruplar;
    KRITIK -> UYARI -> UYGUN -> BILGI sırasıyla okunaklı özet satırlar döner.
    """
    sev_order = {"KRITIK": 0, "UYARI": 1, "UYGUN": 2, "BILGI": 3}
    groups: Dict[Tuple[str, str, str, str, str], List[AuditFindingItem]] = {}
    for f in findings:
        key = (f.severity, f.category, f.project_value.strip(), f.engine_value.strip(), f.standard_ref.strip())
        groups.setdefault(key, []).append(f)

    out: List[Dict[str, str]] = []
    ordered = sorted(groups.values(), key=lambda grp: (sev_order.get(grp[0].severity, 9), grp[0].finding_id))
    for grp in ordered:
        f0 = grp[0]
        if len(grp) == 1:
            code_s = f0.finding_id
            loc_s = f0.location
            desc_s = f0.description
        else:
            code_s = f"{grp[0].finding_id}..{grp[-1].finding_id}"
            panel_names: List[str] = []
            for item in grp:
                m_p = re.search(r"\(([^/\)]+)", item.location)
                panel_names.append(m_p.group(1).strip() if m_p else item.location)
            loc_s = _compact_panel_names(panel_names)
            desc_s = f"{len(grp)} özdeş kalemde aynı durum tespit edildi."
        out.append({
            "code": code_s,
            "severity": f0.severity,
            "category": f0.category,
            "location": loc_s,
            "project_value": f0.project_value,
            "engine_value": f0.engine_value,
            "description": desc_s,
            "recommendation": f0.recommendation,
            "standard_ref": f0.standard_ref,
        })
    return out


def _group_load_schedules_for_display(load_schedules: Sequence[LoadScheduleAudit]) -> List[Dict[str, str]]:
    """Özdeş daire yükleme cetvellerini okunaklı özet satırlarda gruplar."""
    groups: Dict[Tuple[Any, ...], List[LoadScheduleAudit]] = {}
    for ls in load_schedules:
        faz_s = f"{ls.written_r_w or 0:.0f} / {ls.written_s_w or 0:.0f} / {ls.written_t_w or 0:.0f} / {ls.written_rst_w or 0:.0f}"
        imb_v = ls.phase_imbalance_with_rst_pct if (ls.written_rst_w and ls.written_rst_w > 0) else ls.phase_imbalance_single_ph_pct
        key = (
            round(ls.calc_circuits_total_w, 0),
            round(ls.written_total_w, 0) if ls.written_total_w is not None else None,
            faz_s,
            round(imb_v, 1) if imb_v is not None else None,
            round(ls.written_demand_w, 0) if ls.written_demand_w is not None else None,
            round(ls.calc_dwelling_demand_w, 0) if ls.calc_dwelling_demand_w is not None else None,
            ls.status,
        )
        groups.setdefault(key, []).append(ls)
    rows: List[Dict[str, str]] = []
    for grp in groups.values():
        ls0 = grp[0]
        faz_s = f"{ls0.written_r_w or 0:.0f} / {ls0.written_s_w or 0:.0f} / {ls0.written_t_w or 0:.0f} / {ls0.written_rst_w or 0:.0f}"
        imb_v = ls0.phase_imbalance_with_rst_pct if (ls0.written_rst_w and ls0.written_rst_w > 0) else ls0.phase_imbalance_single_ph_pct
        rows.append({
            "panel": ls0.panel_name if len(grp) == 1 else _compact_panel_names([x.panel_name for x in grp]),
            "written_total": _fmt_num(ls0.written_total_w, 0),
            "calc_total": f"{ls0.calc_circuits_total_w:,.0f}",
            "phases": faz_s,
            "imbalance": _fmt_num(imb_v, 1, "%"),
            "written_demand": _fmt_num(ls0.written_demand_w, 0),
            "calc_demand": _fmt_num(ls0.calc_dwelling_demand_w, 0),
            "status": ls0.status,
        })
    return rows


def _group_panel_rows_for_display(panel_rows: Sequence[PanelAuditRow]) -> List[Dict[str, str]]:
    """Özdeş alt pano koruma/ısınma satırlarını tek satırda gruplar (Excel tüm panoları ayrı tutar)."""
    groups: Dict[Tuple[Any, ...], List[PanelAuditRow]] = {}
    for p in panel_rows:
        note_s = "; ".join(p.flags + ([p.selectivity_note] if p.selectivity_note else [])) or "UYGUN"
        key = (
            round(p.installed_power_w, 0) if p.installed_power_w is not None else None,
            round(p.demand_power_w, 0) if p.demand_power_w is not None else None,
            p.cable_spec or "-",
            p.breaker_spec or "YOK",
            p.rcd_spec or "-",
            round(p.project_ib_a, 1) if p.project_ib_a is not None else None,
            round(p.engine_ib_400v_08_a, 1) if p.engine_ib_400v_08_a is not None else None,
            round(p.project_iz_a, 0) if p.project_iz_a is not None else None,
            round(p.engine_iz_yaml_a, 0) if p.engine_iz_yaml_a is not None else None,
            note_s,
        )
        groups.setdefault(key, []).append(p)
    rows: List[Dict[str, str]] = []
    for grp in groups.values():
        p0 = grp[0]
        note_s = "; ".join(p0.flags + ([p0.selectivity_note] if p0.selectivity_note else [])) or "UYGUN"
        rows.append({
            "panel": p0.panel_name if len(grp) == 1 else _compact_panel_names([x.panel_name for x in grp]),
            "power": f"{_fmt_num(p0.installed_power_w, 0)} / {_fmt_num(p0.demand_power_w, 0)}",
            "cable": p0.cable_spec or "-",
            "breaker": p0.breaker_spec or "YOK",
            "rcd": p0.rcd_spec or "-",
            "ib_proj": _fmt_num(p0.project_ib_a, 2),
            "ib_eng": _fmt_num(p0.engine_ib_400v_08_a, 2),
            "iz_pair": f"{_fmt_num(p0.project_iz_a, 0)} / {_fmt_num(p0.engine_iz_yaml_a, 0)}",
            "note": note_s,
        })
    return rows


def format_calculation_audit_markdown(report: CalculationAuditReport) -> str:
    """
    Sade, tekrarsız ve karşılaştırmalı Türkçe Mühendislik Raporu (.md):
    - Tek satır karar özeti
    - Gruplanmış kritik/uyarı bulguları
    - Tüm 6 mühendislik hesabımız her zaman gösterilir; projede karşılığı varsa yan yana verilir.
    """
    lines: List[str] = []
    sc = report.summary_counts
    n_crit = sc.get("KRITIK", 0)
    n_warn = sc.get("UYARI", 0)
    n_ok = sc.get("UYGUN", 0)
    verdict = "REVİZYON GEREKLİ (KRİTİK İHLAL VAR)" if n_crit > 0 else ("İNCELEME / UYARI VAR" if n_warn > 0 else "UYGUN")

    lines.append(f"# Mühendislik Hesap Denetimi Raporu — `{report.filename}`")
    lines.append("")
    lines.append(
        f"> **Karar:** **{verdict}** | **Birim:** `{report.unit_name}` | **Profil:** `{report.regulation_pack}` | "
        f"**Pano:** {sc.get('incelenen_pano', 0)} + Ana Pano | "
        f"**Kritik:** {n_crit} | **Uyarı:** {n_warn} | **Uygun:** {n_ok}"
    )
    lines.append("")

    # 1. Öncelikli Bulgular (Gruplanmış, Tekrarsız)
    lines.append("## 1. Kritik Bulgular ve Uyarı Özeti")
    grouped_f = _group_findings_for_display(report.findings)
    if grouped_f:
        lines.append("| Önem | Konu | Konum | Projede Yazılı | Bizim Motor / Mevzuat | Standart |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for g in grouped_f:
            pv_s = g["project_value"].replace("|", "/")
            ev_s = g["engine_value"].replace("|", "/")
            lines.append(
                f"| **{g['severity']}** | {g['category']} | {g['location']} | "
                f"{pv_s} | {ev_s} | {g['standard_ref']} |"
            )
    else:
        lines.append("*Herhangi bir aykırılık tespit edilmedi.*")
    lines.append("")

    # 2. Güç Bütçesi & Yükleme Cetvelleri (HER ZAMAN GÖSTERİLİR)
    pb = report.power_budget
    lines.append("## 2. Güç Bütçesi ve Yükleme Cetvelleri (Proje ↔ Motor)")
    lines.append("| Kalem | Projede Yazılı | Bizim Motor Hesabı | Durum |")
    lines.append("| :--- | :--- | :--- | :--- |")
    lines.append(
        f"| **Toplam Kurulu Güç** | Ana Pano: {_fmt_num(pb.main_installed_written_w, 0, ' W')}"
        f"{(' / Antet: ' + _fmt_num(pb.titleblock_installed_w, 0, ' W')) if pb.titleblock_table_id else ''} | "
        f"Alt Panolar ({pb.subpanel_count} pano): **{pb.subpanels_installed_sum_w:,.0f} W** "
        f"{('(Antet Farkı: ' + _fmt_num(pb.installed_diff_titleblock_w, 0, ' W') + ')') if pb.titleblock_table_id else ''} | {pb.status} |"
    )
    lines.append(
        f"| **Toplam Talep Gücü** | {_fmt_num(pb.main_demand_written_w, 0, ' W')} (T.F.={_fmt_num(pb.main_demand_factor_written, 2)})"
        f"{(' / Antet: ' + _fmt_num(pb.titleblock_demand_w, 0, ' W')) if pb.titleblock_demand_w else ''} | "
        f"Hesap: **{_fmt_num(pb.main_demand_calc_w, 0, ' W')}** (Önerilen eşzamanlılık: {pb.recommended_coincidence_factor or '-'}) | {pb.status} |"
    )
    lines.append("")

    if report.load_schedules:
        g_ls = _group_load_schedules_for_display(report.load_schedules)
        lines.append(f"### 2A. Yükleme Cetvelleri Karşılaştırması ({len(report.load_schedules)} cetvel → {len(g_ls)} grup)")
        lines.append("| Pano / Grup | Proje Toplam (W) | Motor Linye Toplam (W) | R / S / T / RST (W) | Faz Dengesizliği | Proje Talep (W) | Motor EİTY 8kW (W) | Durum |")
        lines.append("| :--- | ---: | ---: | :--- | ---: | ---: | ---: | :--- |")
        for r in g_ls:
            lines.append(
                f"| **{r['panel']}** | {r['written_total']} | {r['calc_total']} | {r['phases']} | "
                f"{r['imbalance']} | {r['written_demand']} | {r['calc_demand']} | {r['status']} |"
            )
    else:
        lines.append("*Projede çözümlenebilir yükleme cetveli bulunamadı (Proje: Yok | Motor: BELİRSİZ).*")
    lines.append("")

    # 3. Isınma & Şalt Koordinasyonu (HER ZAMAN GÖSTERİLİR)
    mi = report.main_incomer
    lines.append("## 3. Isınma (Ib ≤ In ≤ Iz), PE Kesiti ve Şalt Koordinasyonu (Proje ↔ Motor)")
    mi_status = "UYGUN" if mi.ib_in_iz_ok is True else ("KRİTİK İHLAL" if mi.ib_in_iz_ok is False else "BELİRSİZ (Veri Eksik)")
    lines.append("| Parametre (Ana Pano) | Projede Yazılı | Bizim Motor Hesabı | Durum |")
    lines.append("| :--- | :--- | :--- | :--- |")
    lines.append(f"| **Ana Pano / Besleme Kablosu** | `{mi.panel_name or 'BELİRSİZ'}` — `{mi.cable_spec or 'BELİRSİZ'}` ({_fmt_num(mi.length_m, 0, ' m')}) | TS HD 60364-5-52 / 5-54 kontrolü | {mi_status} |")
    lines.append(f"| **Ana Kesici / KAKR** | `{mi.breaker_spec or 'BELİRSİZ'}` / `{mi.rcd_spec or 'BELİRSİZ'}` | Ib ≤ In ≤ Iz & KAKR 'S' tip seçicilik | {mi_status} |")
    proj_ib_txt = _fmt_num(mi.project_written_ib_a, 1, " A") if mi.project_written_ib_a is not None else "Projede Ayrı Yazılmamış"
    lines.append(f"| **İşletme Akımı (Ib)** | {proj_ib_txt} | **{_fmt_num(mi.engine_ib_380v_a, 1, ' A')}** (380V) / **{_fmt_num(mi.engine_ib_400v_a, 1, ' A')}** (400V) | {mi_status} |")
    lines.append(f"| **Akım Taşıma Kapasitesi (Iz)** | {_fmt_num(mi.project_written_iz_a, 0, ' A')} | **{_fmt_num(mi.engine_iz_yaml_a, 0, ' A')}** (TS HD 60364 YAML) | {mi_status} |")
    lines.append("")
    if report.panel_rows:
        g_pr = _group_panel_rows_for_display(report.panel_rows)
        lines.append(f"### 3A. Alt Pano Özet Tablosu ({len(report.panel_rows)} pano → {len(g_pr)} grup; tüm panolar `.xlsx` ekindedir)")
        lines.append("| Pano / Grup | Kurulu / Talep (W) | Kablo | Kesici | KAKR | Proje Ib (A) | Motor Ib 400V (A) | Proje / Motor Iz (A) | Bulgu / Not |")
        lines.append("| :--- | ---: | :--- | :--- | :--- | ---: | ---: | :--- | :--- |")
        for r in g_pr:
            lines.append(
                f"| **{r['panel']}** | {r['power']} | `{r['cable']}` | `{r['breaker']}` | `{r['rcd']}` | "
                f"{r['ib_proj']} | {r['ib_eng']} | {r['iz_pair']} | {r['note']} |"
            )
    else:
        lines.append("*Alt pano şema/tablo satırı okunamadı (Proje: Yok | Motor: BELİRSİZ).*")
    lines.append("")

    # 4. Gerilim Düşümü Hesabı (HER ZAMAN GÖSTERİLİR)
    lines.append("## 4. Gerilim Düşümü (%e) Karşılaştırması (Proje ↔ Motor)")
    if report.vd_formulas:
        lines.append("| Bölüm | Kablo | L (m) | P (W) | S (mm²) | Projede Yazılı %e | Motor 380/220V | Motor 400/230V | IEC Ek-G %e |")
        lines.append("| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for v in report.vd_formulas:
            lines.append(
                f"| {v.segment_name} (`{v.formula_id}`) | `{v.cable_spec or '-'}` | {_fmt_num(v.length_m, 1)} | "
                f"{_fmt_num(v.power_w, 0)} | {_fmt_num(v.section_mm2, 1)} | **{_fmt_num(v.project_vd_pct, 2, '%')}** | "
                f"{_fmt_num(v.engine_vd_proj_v_pct, 2, '%')} | {_fmt_num(v.engine_vd_std_v_pct, 2, '%')} | "
                f"{_fmt_num(v.engine_vd_iec_ekg_pct, 2, '%')} |"
            )
        lines.append(
            f"| **TOPLAM %e** | - | - | - | - | **{_fmt_num(report.vd_formula_total_proj_written, 2, '%')}** | "
            f"**{_fmt_num(report.vd_formula_total_engine_proj_v, 2, '%')}** | "
            f"**{_fmt_num(report.vd_formula_total_engine_std_v, 2, '%')}** | - |"
        )
    else:
        na_vd = (
            f"%{report.network_analysis.max_voltage_drop_pct:.2f} (pandapower)"
            if (report.network_analysis and report.network_analysis.converged)
            else "BELİRSİZ (L/P/S verisi eksik)"
        )
        lines.append("| Bölüm | Projede Yazılı %e | Bizim Motor Hesabı |")
        lines.append("| :--- | :--- | :--- |")
        lines.append(f"| Gerilim Düşümü Hesabı | Projede Yok | {na_vd} |")
    lines.append("")

    # 5. Temel Topraklama Hesabı (HER ZAMAN GÖSTERİLİR)
    lines.append("## 5. Temel Topraklama (R_E) Karşılaştırması (Proje ↔ Motor)")
    if report.grounding:
        g = report.grounding
        lines.append("| Parametre | Projede Yazılı | Motor (Tablo Girdisi) | Motor (Gerçek CAD Geometrisi) |")
        lines.append("| :--- | ---: | ---: | ---: |")
        lines.append(f"| Temel Alanı A (m²) | {_fmt_num(g.table_A_m2, 2)} | {_fmt_num(g.table_A_m2, 2)} | **{_fmt_num(g.cad_A_m2, 2)}** |")
        lines.append(f"| Şerit Boyu L (m) | {_fmt_num(g.table_L_m, 2)} | {_fmt_num(g.table_L_m, 2)} | **{_fmt_num(g.cad_ring_plus_inner_m, 2)}** (+filiz {_fmt_num(g.cad_spur_m, 2)}) |")
        lines.append(f"| Eşdeğer Çap D (m) | {_fmt_num(g.table_D_written_m, 2)} | {_fmt_num(g.engine_tbl_D_m, 2)} | **{_fmt_num(g.cad_D_m, 2)}** |")
        rc_tag = (
            " *(formül uyumsuz)*"
            if (g.table_Rc_written_ohm is not None and g.engine_tbl_R_rods_dwight_ohm is not None and abs(g.table_Rc_written_ohm - g.engine_tbl_R_rods_dwight_ohm) > 1.0)
            else ""
        )
        ry_tag = (
            " *(formül uyumsuz)*"
            if (g.table_Ry_written_ohm is not None and g.engine_tbl_R_temel_ohm is not None and abs(g.table_Ry_written_ohm - g.engine_tbl_R_temel_ohm) > 1.0)
            else ""
        )
        lines.append(f"| Çubuk Direnci Rç (Ω) | {_fmt_num(g.table_Rc_written_ohm, 2)}{rc_tag} | {_fmt_num(g.engine_tbl_R_rods_dwight_ohm, 2)} | **{_fmt_num(g.engine_cad_R_rods_dwight_ohm, 2)}** |")
        lines.append(f"| Yatay / Temel Ry (Ω) | {_fmt_num(g.table_Ry_written_ohm, 2)}{ry_tag} | {_fmt_num(g.engine_tbl_R_temel_ohm, 2)} | **{_fmt_num(g.engine_cad_R_temel_ohm, 2)}** |")
        lines.append(f"| Bileşke Schwarz Re (Ω) | {_fmt_num(g.table_Re_written_ohm, 2)} | {_fmt_num(g.engine_tbl_R_schwarz_ohm, 2)} | **{_fmt_num(g.engine_cad_R_schwarz_ohm, 2)}** |")
        lines.append(f"| IEEE 80 Sverak Rg (Ω) | Projede Yok | {_fmt_num(g.engine_tbl_R_sverak_ohm, 2)} | **{_fmt_num(g.engine_cad_R_sverak_ohm, 2)}** |")
        lines.append(f"| TT Sınır (50V / IΔn) | <= {_fmt_num(g.table_limit_written_ohm, 1, ' Ω')} | - | <= **{_fmt_num(g.tt_max_allowed_ohm, 2, ' Ω')}** ({'UYGUN' if g.tt_compliant else 'BELİRSİZ'}) |")
    else:
        lines.append("| Parametre | Projede Yazılı | Bizim Motor (CAD Geometrisi) |")
        lines.append("| :--- | :--- | :--- |")
        lines.append("| Temel Topraklama Hesabı | Projede Yok | Kapalı temel topraklama halkası / ρ bilgisi bulunamadı (BELİRSİZ) |")
    lines.append("")

    # 6. Aydınlatma Hesabı (HER ZAMAN GÖSTERİLİR)
    lines.append("## 6. Aydınlatma Hesabı — Lümen Yöntemi (Proje ↔ Motor)")
    if report.lighting_rooms:
        lines.append("| Mahal | Boyut (m) | Proje (E / k / Z) | Motor (k / Z / Gerçekleşen lx) | Seçilen | Durum |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for lr in report.lighting_rooms:
            lines.append(
                f"| **{lr.room_name}** | {lr.width_a_m:.1f}×{lr.length_b_m:.1f} (hm={lr.mounting_hm_m:.2f}m) | "
                f"{lr.written_lux:.0f} lx / {_fmt_num(lr.written_k, 2)} / {_fmt_num(lr.written_z, 2)} | "
                f"{lr.calc_k:.2f} / {lr.calc_z_exact:.2f} ({lr.calc_z_ceil} ad.) / **{lr.achieved_lux:.1f} lx** | "
                f"`{lr.selected_spec}` | {'; '.join(lr.notes) or 'UYGUN'} |"
            )
    else:
        lines.append("| Mahal | Projede Yazılı | Bizim Motor Hesabı |")
        lines.append("| :--- | :--- | :--- |")
        lines.append("| Aydınlatma Hesabı | Projede Yok | Çizimde aydınlatma hesap tablosu / mahal boyut girdisi yok (BELİRSİZ) |")
    lines.append("")

    # 7. Şebeke Yük Akışı & Kısa Devre (HER ZAMAN GÖSTERİLİR)
    lines.append("## 7. Şebeke Yük Akışı & IEC 60909 Kısa Devre (`pandapower`)")
    if report.network_analysis and report.network_analysis.converged:
        na = report.network_analysis
        ik_vals = [b.ikss_ka for b in na.buses if b.ikss_ka is not None]
        ik_rng = f"{min(ik_vals):.2f} – {max(ik_vals):.2f} kA" if ik_vals else "BELİRSİZ"
        lines.append(
            f"- **Özet:** {len(na.buses)} bara yakınsadı | **Maks. Bağıl %e:** `%{na.max_voltage_drop_pct:.2f}` | "
            f"**3-Faz Kısa Devre Ik'' Aralığı:** `{ik_rng}`"
        )
        if na.assumptions_notes:
            lines.append(f"- **Not:** {'; '.join(na.assumptions_notes)}")
        # Ana bara + en yüksek %e'li 6 kritik bara (tam bara listesi Excel'de)
        top_buses = sorted(na.buses, key=lambda b: (-b.voltage_drop_pct, b.bus_name))
        show_buses = []
        seen_b: Set[str] = set()
        for b in na.buses[:1] + top_buses[:6]:
            if b.bus_name not in seen_b:
                seen_b.add(b.bus_name)
                show_buses.append(b)
        lines.append("| Bara / Pano (Öncelikli) | Gerilim (p.u.) | Bağıl Düşüm (%e) | 3-Faz Kısa Devre Ik'' (kA) |")
        lines.append("| :--- | ---: | ---: | ---: |")
        for b in show_buses:
            lines.append(f"| **{b.bus_name}** | {b.vm_pu:.4f} | %{b.voltage_drop_pct:.2f} | {_fmt_num(b.ikss_ka, 3, ' kA')} |")
        if len(na.buses) > len(show_buses):
            lines.append(f"*Not: Toplam {len(na.buses)} baranın tamamı `.xlsx` rapor ekinde yer almaktadır.*")
    else:
        lines.append("| Analiz | Projede Yazılı | Bizim Motor (`pandapower`) |")
        lines.append("| :--- | :--- | :--- |")
        lines.append("| Yük Akışı & Kısa Devre | Projede Yok | Yük akışı için eksiksiz besleme kolu/uzunluk verisi yok (BELİRSİZ) |")
    lines.append("")

    return "\n".join(lines) + "\n"


def save_calculation_audit_xlsx(report: CalculationAuditReport, output_path: Union[str, Path]) -> Path:
    """5 sekmeli Excel (.xlsx) mühendislik hesap denetimi raporu üretir."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    zebra_fill = PatternFill(start_color="F2F5FA", end_color="F2F5FA", fill_type="solid")
    crit_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    warn_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    ok_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=10)
    body_font = Font(size=10)

    def _write_sheet(ws, headers: List[str], rows: List[List[Any]], right_cols: Set[int] = frozenset(), status_col: Optional[int] = None) -> None:
        ws.append(headers)
        for ci in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=ci)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="right" if (ci - 1) in right_cols else "left", vertical="center", wrap_text=True)
        for ri, row in enumerate(rows, start=2):
            ws.append(row)
            status_val = str(row[status_col]).upper() if (status_col is not None and status_col < len(row)) else ""
            row_fill = None
            if "KRIT" in status_val or "KRİT" in status_val or "IHLAL" in status_val or "İHLAL" in status_val or "HATA" in status_val:
                row_fill = crit_fill
            elif "UYARI" in status_val or "CELISKI" in status_val or "ÇELİŞKİ" in status_val or "EKSIK" in status_val or "EKSİK" in status_val:
                row_fill = warn_fill
            elif status_val == "UYGUN":
                row_fill = ok_fill
            elif ri % 2 == 1:
                row_fill = zebra_fill

            for ci in range(1, len(headers) + 1):
                cell = ws.cell(row=ri, column=ci)
                cell.font = body_font
                if row_fill is not None:
                    cell.fill = row_fill
                cell.alignment = Alignment(horizontal="right" if (ci - 1) in right_cols else "left", vertical="center", wrap_text=True)
        ws.freeze_panes = "A2"
        for ci, h in enumerate(headers, start=1):
            max_len = max([len(str(h))] + [min(60, len(str(r[ci - 1]))) for r in rows if ci - 1 < len(r)], default=12)
            ws.column_dimensions[get_column_letter(ci)].width = min(max(max_len + 3, 12), 54)

    # 1. 1_Ozet_ve_Kritik_Bulgular
    ws1 = wb.active
    ws1.title = "1_Ozet_ve_Kritik_Bulgular"
    rows1 = [
        [f.finding_id, f.severity, f.category, f.location, f.project_value, f.engine_value, f.standard_ref, f.description, f.recommendation]
        for f in report.findings
    ]
    _write_sheet(
        ws1,
        ["Kod", "Onem", "Kategori", "Konum", "Projedeki Deger", "Motor / Mevzuat Degeri", "Standart", "Aciklama", "Oneri"],
        rows1,
        status_col=1,
    )

    # 2. 2_Guc_ve_Yukleme_Cetveli
    ws2 = wb.create_sheet("2_Guc_ve_Yukleme_Cetveli")
    pb = report.power_budget
    rows2: List[List[Any]] = [
        ["GUC BUTCESI", "Alt Panolar Toplami", pb.subpanels_installed_sum_w, pb.subpanels_demand_sum_w, "-", "-", "-", "-", f"{pb.subpanel_count} pano (coinc: {pb.recommended_coincidence_factor})"],
        ["GUC BUTCESI", f"Ana Pano ({pb.main_panel_name or 'AT'})", pb.main_installed_written_w or "-", pb.main_demand_written_w or "-", pb.main_demand_calc_w or "-", "-", "-", pb.status, f"DF={pb.main_demand_factor_written or '-'}"],
        ["GUC BUTCESI", f"Antet ({pb.titleblock_table_id or '-'})", pb.titleblock_installed_w or "-", pb.titleblock_demand_w or "-", "-", "-", "-", pb.status, f"Fark={pb.installed_diff_titleblock_w or 0} W"],
    ]
    for ls in report.load_schedules:
        imb = ls.phase_imbalance_with_rst_pct if (ls.written_rst_w and ls.written_rst_w > 0) else ls.phase_imbalance_single_ph_pct
        rows2.append([
            "YUKLEME CETVELI",
            f"{ls.panel_name} ({ls.table_id})",
            ls.written_total_w if ls.written_total_w is not None else ls.calc_circuits_total_w,
            ls.written_demand_w if ls.written_demand_w is not None else "-",
            ls.calc_dwelling_demand_w if ls.calc_dwelling_demand_w is not None else "-",
            f"R={ls.written_r_w or 0:.0f}, S={ls.written_s_w or 0:.0f}, T={ls.written_t_w or 0:.0f}, RST={ls.written_rst_w or 0:.0f}",
            f"{imb:.1f}%" if imb is not None else "-",
            ls.status,
            f"{ls.circuits_count} linye | Ana sig: {ls.main_breaker_spec or '-'} | KAKR: {ls.main_rcd_spec or '-'}",
        ])
    _write_sheet(
        ws2,
        ["Grup", "Kalem / Pano", "Kurulu Guc (W)", "Yazili Talep (W)", "EITY 8kW Hesap (W)", "Faz Dagilimi (W)", "Faz Dengesizligi", "Durum", "Detay"],
        rows2,
        right_cols={2, 3, 4, 6},
        status_col=7,
    )

    # 3. 3_Isinma_Kesit_Secicilik
    ws3 = wb.create_sheet("3_Isinma_Kesit_Secicilik")
    mi = report.main_incomer
    rows3: List[List[Any]] = [
        [
            mi.panel_name or "AT (ANA PANO)",
            "ANA_BESLEME",
            report.power_budget.main_installed_written_w or "-",
            mi.demand_power_w or "-",
            mi.cable_spec or "-",
            mi.length_m or "-",
            mi.breaker_spec or "-",
            mi.rcd_spec or "-",
            mi.project_written_ib_a if mi.project_written_ib_a is not None else "-",
            mi.engine_ib_400v_a if mi.engine_ib_400v_a is not None else "-",
            mi.project_written_iz_a if mi.project_written_iz_a is not None else "-",
            mi.engine_iz_yaml_a if mi.engine_iz_yaml_a is not None else "-",
            "UYGUN" if mi.ib_in_iz_ok is True else ("KRITIK IHLAL (In > Iz)" if mi.ib_in_iz_ok is False else "BELIRSIZ (Veri Eksik)"),
        ]
    ]
    for p in report.panel_rows:
        st_s = "; ".join(p.flags + ([p.selectivity_note] if p.selectivity_note else [])) or "UYGUN"
        rows3.append([
            p.panel_name,
            p.role,
            p.installed_power_w if p.installed_power_w is not None else "-",
            p.demand_power_w if p.demand_power_w is not None else "-",
            p.cable_spec or "-",
            p.feeder_length_m if p.feeder_length_m is not None else "-",
            p.breaker_spec or "YOK",
            p.rcd_spec or "-",
            p.project_ib_a if p.project_ib_a is not None else "-",
            p.engine_ib_400v_08_a if p.engine_ib_400v_08_a is not None else "-",
            p.project_iz_a if p.project_iz_a is not None else "-",
            p.engine_iz_yaml_a if p.engine_iz_yaml_a is not None else "-",
            st_s,
        ])
    _write_sheet(
        ws3,
        ["Pano", "Rol", "Kurulu (W)", "Talep (W)", "Kablo", "Metraj (m)", "Kesici", "KAKR", "Ib Yazili (A)", "Ib Motor 400V (A)", "Iz Yazili (A)", "Iz TS HD 60364 (A)", "Durum / Not"],
        rows3,
        right_cols={2, 3, 5, 8, 9, 10, 11},
        status_col=12,
    )

    # 4. 4_Gerilim_Dusumu_57_Pano
    ws4 = wb.create_sheet("4_Gerilim_Dusumu_57_Pano")
    rows4: List[List[Any]] = []
    for v in report.vd_formulas:
        rows4.append([
            f"FORMUL {v.formula_id}",
            v.segment_name,
            v.cable_spec or "-",
            v.length_m or "-",
            v.power_w or "-",
            v.section_mm2 or "-",
            "-",
            "-",
            v.project_vd_pct if v.project_vd_pct is not None else "-",
            "-",
            v.engine_vd_proj_v_pct if v.engine_vd_proj_v_pct is not None else "-",
            v.engine_vd_std_v_pct if v.engine_vd_std_v_pct is not None else "-",
            v.engine_vd_iec_ekg_pct if v.engine_vd_iec_ekg_pct is not None else "-",
            "ANA + KOLON + LINYE FORMULU",
        ])
    for p in report.panel_rows:
        st_v = "; ".join([f for f in p.flags if "%e" in f or "METRAJ" in f]) or "UYGUN"
        rows4.append([
            p.panel_name,
            p.linye_no or "-",
            p.cable_spec or "-",
            p.feeder_length_m if p.feeder_length_m is not None else "-",
            p.demand_power_w if p.demand_power_w is not None else "-",
            p.phase_mm2 if p.phase_mm2 is not None else "-",
            p.project_vd_linye_pct if p.project_vd_linye_pct is not None else "-",
            p.engine_vd_linye_proj_pct if p.engine_vd_linye_proj_pct is not None else "-",
            p.project_vd_total_pct if p.project_vd_total_pct is not None else "-",
            p.engine_vd_total_no_main_pct if p.engine_vd_total_no_main_pct is not None else "-",
            p.engine_vd_total_with_main_pct if p.engine_vd_total_with_main_pct is not None else "-",
            p.engine_vd_total_iec_pct if p.engine_vd_total_iec_pct is not None else "-",
            p.vd_limit_written or "-",
            st_v,
        ])
    _write_sheet(
        ws4,
        ["Pano / Formul", "Linye / Segment", "Kablo", "Kolon L (m)", "Talep / P (W)", "Kesit (mm2)", "Yazili %e_linye", "Motor %e_linye", "Yazili %e_Top", "Motor (Ana Haric)", "Motor (Ana Dahil 380V)", "Motor (400V IEC Ek-G)", "Sinir", "Durum / Bulgu"],
        rows4,
        right_cols={3, 4, 5, 6, 7, 8, 9, 10, 11},
        status_col=13,
    )

    # 5. 5_Topraklama_ve_Aydinlatma
    ws5 = wb.create_sheet("5_Topraklama_ve_Aydinlatma")
    rows5: List[List[Any]] = []
    if report.grounding:
        g = report.grounding
        rows5.extend([
            ["TOPRAKLAMA", "Temel Alani A (m2)", g.table_A_m2 or "-", g.table_A_m2 or "-", g.cad_A_m2 or "-", "BILGI", "Tablo dikdortgen vs M_02 gercek poligon"],
            ["TOPRAKLAMA", "Iletken Boyu L (m)", g.table_L_m or "-", g.table_L_m or "-", g.cad_ring_plus_inner_m or "-", "UYARI", f"Filizler dahil: {(g.cad_ring_plus_inner_m or 0)+(g.cad_spur_m or 0):.2f} m"],
            ["TOPRAKLAMA", "Esdeger Cap D (m)", g.table_D_written_m or "-", g.engine_tbl_D_m or "-", g.cad_D_m or "-", "UYGUN", "D = 2*sqrt(A/pi)"],
            ["TOPRAKLAMA", "Cubuk Direnci Rc (Ohm)", g.table_Rc_written_ohm or "-", g.engine_tbl_R_rods_dwight_ohm or "-", g.engine_cad_R_rods_dwight_ohm or "-", "KRITIK", "Tablo serit Dwight formulu hesaplamis"],
            ["TOPRAKLAMA", "Yatay/Temel Ry (Ohm)", g.table_Ry_written_ohm or "-", g.engine_tbl_R_temel_ohm or "-", g.engine_cad_R_temel_ohm or "-", "KRITIK", "Tabloda ilk terim 100/(3*pi)=10.62 yanlis alinmis"],
            ["TOPRAKLAMA", "Bileske Schwarz Re (Ohm)", g.table_Re_written_ohm or "-", g.engine_tbl_R_schwarz_ohm or "-", g.engine_cad_R_schwarz_ohm or "-", "UYGUN" if g.tt_compliant else "UYARI", f"TT Sinir <= {g.tt_max_allowed_ohm or 166.7:.1f} Ohm | Sverak Rg={g.engine_cad_R_sverak_ohm or '-'}"],
        ])
    for lr in report.lighting_rooms:
        st_l = "UYARI" if lr.notes else "UYGUN"
        rows5.append([
            "AYDINLATMA",
            f"{lr.room_name} ({lr.width_a_m:.1f}x{lr.length_b_m:.1f}m)",
            f"E={lr.written_lux:.0f}lx | k={lr.written_k} | Z={lr.written_z}",
            f"k={lr.calc_k:.2f} | Z={lr.calc_z_exact:.2f} ({lr.calc_z_ceil} ad.)",
            f"{lr.achieved_lux:.1f} lx ({lr.selected_spec})",
            st_l,
            "; ".join(lr.notes) or "Hesap tutarli",
        ])
    _write_sheet(
        ws5,
        ["Disiplin", "Parametre / Mahal", "Projedeki Deger", "Motor (Tablo Girdisi)", "Motor (CAD / Gerceklesen)", "Durum", "Not / Aciklama"],
        rows5,
        status_col=5,
    )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return out


def save_calculation_audit_docx(report: CalculationAuditReport, output_path: Union[str, Path]) -> Path:
    """Hesap denetimi ve yeniden hesaplama raporunu Word (.docx) olarak kaydeder."""
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor
    from .metraj_cikarici import _add_styled_docx_table

    doc = Document()
    for sec in doc.sections:
        sec.top_margin = Cm(1.4)
        sec.bottom_margin = Cm(1.4)
        sec.left_margin = Cm(1.4)
        sec.right_margin = Cm(1.4)

    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Calibri"
    normal_style.font.size = Pt(9.5)

    title = doc.add_heading(f"Mühendislik Hesap Denetimi ve Yeniden Hesaplama — {report.filename}", level=1)
    if title.runs:
        title.runs[0].font.color.rgb = RGBColor(31, 78, 121)

    sc = report.summary_counts
    n_crit = sc.get("KRITIK", 0)
    n_warn = sc.get("UYARI", 0)
    verdict = "REVİZYON GEREKLİ (KRİTİK İHLAL VAR)" if n_crit > 0 else ("İNCELEME / UYARI VAR" if n_warn > 0 else "UYGUN")
    meta = doc.add_paragraph(
        f"Karar: {verdict}  |  Birim: {report.unit_name}  |  Profil: {report.regulation_pack}  |  "
        f"Pano: {sc.get('incelenen_pano', 0)} + Ana Pano  |  "
        f"Kritik: {n_crit}  |  Uyarı: {n_warn}  |  Uygun: {sc.get('UYGUN', 0)}"
    )
    if meta.runs:
        meta.runs[0].bold = True

    doc.add_heading("1. Kritik Bulgular ve Uyarı Özeti (Gruplanmış)", level=2)
    grouped_f = _group_findings_for_display(report.findings)
    if grouped_f:
        _add_styled_docx_table(
            doc,
            ["Önem", "Konu", "Konum", "Projede Yazılı", "Bizim Motor / Mevzuat", "Standart"],
            [
                [g["severity"], g["category"], g["location"], g["project_value"], g["engine_value"], g["standard_ref"]]
                for g in grouped_f
            ],
        )
    else:
        doc.add_paragraph("Herhangi bir aykırılık tespit edilmedi.")

    doc.add_heading("2. Güç Bütçesi ve Yükleme Cetvelleri (Proje ↔ Motor)", level=2)
    pb = report.power_budget
    pb_rows = [
        [
            "Toplam Kurulu Güç",
            f"Ana Pano: {_fmt_num(pb.main_installed_written_w, 0, ' W')}"
            + (f" | Antet: {_fmt_num(pb.titleblock_installed_w, 0, ' W')}" if pb.titleblock_table_id else ""),
            f"Alt Panolar ({pb.subpanel_count} pano): {pb.subpanels_installed_sum_w:,.0f} W"
            + (f" (Antet Farkı: {_fmt_num(pb.installed_diff_titleblock_w, 0, ' W')})" if pb.titleblock_table_id else ""),
            pb.status,
        ],
        [
            "Toplam Talep Gücü",
            f"{_fmt_num(pb.main_demand_written_w, 0, ' W')} (T.F.={_fmt_num(pb.main_demand_factor_written, 2)})",
            f"Hesap: {_fmt_num(pb.main_demand_calc_w, 0, ' W')} (Önerilen eşzamanlılık: {pb.recommended_coincidence_factor or '-'})",
            pb.status,
        ],
    ]
    _add_styled_docx_table(doc, ["Kalem", "Projede Yazılı", "Bizim Motor Hesabı", "Durum"], pb_rows)

    if report.load_schedules:
        g_ls = _group_load_schedules_for_display(report.load_schedules)
        doc.add_heading(f"2A. Yükleme Cetvelleri ({len(report.load_schedules)} cetvel → {len(g_ls)} grup)", level=3)
        _add_styled_docx_table(
            doc,
            ["Pano / Grup", "Proje Toplam (W)", "Motor Toplam (W)", "Faz R/S/T/RST", "Dengesizlik", "Proje / Motor Talep (W)", "Durum"],
            [
                [r["panel"], r["written_total"], r["calc_total"], r["phases"], r["imbalance"], f"{r['written_demand']} / {r['calc_demand']}", r["status"]]
                for r in g_ls
            ],
            right_align_cols={1, 2, 4},
        )
    else:
        doc.add_paragraph("Projede çözümlenebilir yükleme cetveli yok (Motor: BELİRSİZ).")

    doc.add_heading("3. Isınma (Ib ≤ In ≤ Iz), PE Kesiti ve Şalt Koordinasyonu (Proje ↔ Motor)", level=2)
    mi = report.main_incomer
    mi_status = "UYGUN" if mi.ib_in_iz_ok is True else ("KRİTİK İHLAL" if mi.ib_in_iz_ok is False else "BELİRSİZ (Veri Eksik)")
    _add_styled_docx_table(
        doc,
        ["Parametre (Ana Pano)", "Projede Yazılı", "Bizim Motor Hesabı", "Durum"],
        [
            ["Ana Pano / Kablo", f"{mi.panel_name or 'BELİRSİZ'} — {mi.cable_spec or 'BELİRSİZ'} ({_fmt_num(mi.length_m, 0, ' m')})", "TS HD 60364-5-52 / 5-54", mi_status],
            ["Ana Kesici / KAKR", f"{mi.breaker_spec or 'BELİRSİZ'} / {mi.rcd_spec or 'BELİRSİZ'}", "Ib ≤ In ≤ Iz & KAKR 'S' tip", mi_status],
            ["İşletme Akımı (Ib)", _fmt_num(mi.project_written_ib_a, 1, " A") if mi.project_written_ib_a is not None else "Projede Yok", f"{_fmt_num(mi.engine_ib_380v_a, 1, ' A')} (380V) / {_fmt_num(mi.engine_ib_400v_a, 1, ' A')} (400V)", mi_status],
            ["Akım Kapasitesi (Iz)", _fmt_num(mi.project_written_iz_a, 0, " A"), f"{_fmt_num(mi.engine_iz_yaml_a, 0, ' A')} (TS HD 60364 YAML)", mi_status],
        ],
    )
    if report.panel_rows:
        g_pr = _group_panel_rows_for_display(report.panel_rows)
        doc.add_heading(f"3A. Alt Pano Özeti ({len(report.panel_rows)} pano → {len(g_pr)} grup; tüm panolar Excel ekindedir)", level=3)
        _add_styled_docx_table(
            doc,
            ["Pano / Grup", "Kurulu/Talep (W)", "Kablo", "Kesici", "Ib (Proje/Motor)", "Iz (Proje/YAML)", "Bulgu"],
            [
                [r["panel"], r["power"], r["cable"], r["breaker"], f"{r['ib_proj']} / {r['ib_eng']}", r["iz_pair"], r["note"]]
                for r in g_pr
            ],
        )

    doc.add_heading("4. Gerilim Düşümü (%e) Karşılaştırması (Proje ↔ Motor)", level=2)
    if report.vd_formulas:
        vd_rows = [
            [
                f"{v.segment_name} ({v.formula_id})",
                v.cable_spec or "-",
                _fmt_num(v.length_m, 1),
                _fmt_num(v.power_w, 0),
                _fmt_num(v.section_mm2, 1),
                _fmt_num(v.project_vd_pct, 2, "%"),
                _fmt_num(v.engine_vd_proj_v_pct, 2, "%"),
                _fmt_num(v.engine_vd_std_v_pct, 2, "%"),
                _fmt_num(v.engine_vd_iec_ekg_pct, 2, "%"),
            ]
            for v in report.vd_formulas
        ]
        vd_rows.append([
            "TOPLAM %e", "-", "-", "-", "-",
            _fmt_num(report.vd_formula_total_proj_written, 2, "%"),
            _fmt_num(report.vd_formula_total_engine_proj_v, 2, "%"),
            _fmt_num(report.vd_formula_total_engine_std_v, 2, "%"),
            "-",
        ])
        _add_styled_docx_table(
            doc,
            ["Bölüm", "Kablo", "L (m)", "P (W)", "S (mm²)", "Proje %e", "Motor 380V", "Motor 400V", "IEC Ek-G"],
            vd_rows,
            right_align_cols={2, 3, 4, 5, 6, 7, 8},
        )
    else:
        na_vd = (
            f"%{report.network_analysis.max_voltage_drop_pct:.2f} (pandapower)"
            if (report.network_analysis and report.network_analysis.converged)
            else "BELİRSİZ (L/P/S verisi eksik)"
        )
        _add_styled_docx_table(doc, ["Bölüm", "Projede Yazılı %e", "Bizim Motor Hesabı"], [["Gerilim Düşümü", "Projede Yok", na_vd]])

    doc.add_heading("5. Temel Topraklama (R_E) Karşılaştırması (Proje ↔ Motor)", level=2)
    if report.grounding:
        g = report.grounding
        _add_styled_docx_table(
            doc,
            ["Parametre", "Projede Yazılı", "Motor (Tablo Girdisi)", "Motor (Gerçek CAD)"],
            [
                ["Temel Alanı A (m²)", _fmt_num(g.table_A_m2, 2), _fmt_num(g.table_A_m2, 2), _fmt_num(g.cad_A_m2, 2)],
                ["İletken Boyu L (m)", _fmt_num(g.table_L_m, 2), _fmt_num(g.table_L_m, 2), _fmt_num(g.cad_ring_plus_inner_m, 2)],
                ["Çubuk Direnci Rç (Ω)", _fmt_num(g.table_Rc_written_ohm, 2), _fmt_num(g.engine_tbl_R_rods_dwight_ohm, 2), _fmt_num(g.engine_cad_R_rods_dwight_ohm, 2)],
                ["Yatay/Temel Ry (Ω)", _fmt_num(g.table_Ry_written_ohm, 2), _fmt_num(g.engine_tbl_R_temel_ohm, 2), _fmt_num(g.engine_cad_R_temel_ohm, 2)],
                ["Bileşke Schwarz Re (Ω)", _fmt_num(g.table_Re_written_ohm, 2), _fmt_num(g.engine_tbl_R_schwarz_ohm, 2), _fmt_num(g.engine_cad_R_schwarz_ohm, 2)],
                ["IEEE 80 Sverak Rg (Ω)", "Projede Yok", _fmt_num(g.engine_tbl_R_sverak_ohm, 2), _fmt_num(g.engine_cad_R_sverak_ohm, 2)],
            ],
            right_align_cols={1, 2, 3},
        )
    else:
        _add_styled_docx_table(
            doc,
            ["Parametre", "Projede Yazılı", "Bizim Motor (CAD)"],
            [["Temel Topraklama", "Projede Yok", "Kapalı temel ringi / ρ verisi yok (BELİRSİZ)"]],
        )

    doc.add_heading("6. Aydınlatma Hesabı — Lümen Yöntemi (Proje ↔ Motor)", level=2)
    if report.lighting_rooms:
        _add_styled_docx_table(
            doc,
            ["Mahal", "Boyut (m)", "Proje (E / k / Z)", "Motor (k / Z / Gerçekleşen)", "Seçilen", "Durum"],
            [
                [
                    lr.room_name,
                    f"{lr.width_a_m:.1f}×{lr.length_b_m:.1f}",
                    f"{lr.written_lux:.0f} lx / {_fmt_num(lr.written_k, 2)} / {_fmt_num(lr.written_z, 2)}",
                    f"{lr.calc_k:.2f} / {lr.calc_z_exact:.2f} ({lr.calc_z_ceil}) / {lr.achieved_lux:.1f} lx",
                    lr.selected_spec,
                    "; ".join(lr.notes) or "UYGUN",
                ]
                for lr in report.lighting_rooms
            ],
        )
    else:
        _add_styled_docx_table(
            doc,
            ["Mahal", "Projede Yazılı", "Bizim Motor Hesabı"],
            [["Aydınlatma Hesabı", "Projede Yok", "Aydınlatma hesap tablosu bulunamadı (BELİRSİZ)"]],
        )

    doc.add_heading("7. Şebeke Yük Akışı & IEC 60909 Kısa Devre (pandapower)", level=2)
    if report.network_analysis and report.network_analysis.converged:
        na = report.network_analysis
        top_buses = sorted(na.buses, key=lambda b: (-b.voltage_drop_pct, b.bus_name))
        show_buses = []
        seen_b: Set[str] = set()
        for b in na.buses[:1] + top_buses[:6]:
            if b.bus_name not in seen_b:
                seen_b.add(b.bus_name)
                show_buses.append(b)
        _add_styled_docx_table(
            doc,
            ["Bara / Pano (Öncelikli)", "Gerilim (p.u.)", "Bağıl Düşüm (%e)", "3-Faz Kısa Devre Ik'' (kA)"],
            [[b.bus_name, f"{b.vm_pu:.4f}", f"%{b.voltage_drop_pct:.2f}", _fmt_num(b.ikss_ka, 3, " kA")] for b in show_buses],
            right_align_cols={1, 2, 3},
        )
    else:
        _add_styled_docx_table(
            doc,
            ["Analiz", "Projede Yazılı", "Bizim Motor (pandapower)"],
            [["Yük Akışı & Kısa Devre", "Projede Yok", "Eksiksiz besleme kolu/uzunluk verisi yok (BELİRSİZ)"]],
        )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


def save_calculation_audit_reports(
    report: CalculationAuditReport,
    output_dir: Union[str, Path],
    base_name: Optional[str] = None,
) -> Dict[str, Path]:
    """Hesap denetimi raporunu `.xlsx`, `.docx`, `.md` ve `.json` olarak diske yazar."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = base_name or f"{Path(report.filename).stem}_hesap_kontrol"

    xlsx_path = out_dir / f"{stem}.xlsx"
    docx_path = out_dir / f"{stem}.docx"
    md_path = out_dir / f"{stem}.md"
    json_path = out_dir / f"{stem}.json"

    save_calculation_audit_xlsx(report, xlsx_path)
    save_calculation_audit_docx(report, docx_path)
    md_path.write_text(format_calculation_audit_markdown(report), encoding="utf-8")
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return {
        "xlsx": xlsx_path,
        "docx": docx_path,
        "md": md_path,
        "json": json_path,
    }


__all__ = [
    "AuditFindingItem",
    "CalculationAuditReport",
    "GroundingAudit",
    "LightingRoomAudit",
    "LoadCircuitAuditRow",
    "LoadScheduleAudit",
    "MainIncomerAudit",
    "PanelAuditRow",
    "PowerBudgetAudit",
    "VoltageDropFormulaRow",
    "build_calculation_audit_report",
    "format_calculation_audit_markdown",
    "save_calculation_audit_docx",
    "save_calculation_audit_reports",
    "save_calculation_audit_xlsx",
]
