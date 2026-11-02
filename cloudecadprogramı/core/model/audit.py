# -*- coding: utf-8 -*-
"""
Ortak Elektrik Bilgi Modeli — Denetim, Güven Puanı ve Raporlama Varlıkları
========================================================================
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Tuple, Any


class ConfidenceLevel(str, Enum):
    DEFINITE = "KESİN"                        # 1.00: Lejant/katman/şemada doğrudan ve çelişkisiz
    HIGH = "YÜKSEK GÜVEN"                     # 0.85: Standart blok adı / attrib / çoklu kanıt
    PROBABLE = "MUHTEMEL"                     # 0.65: Yakınlık, kablo güzergahı veya yük tahmini
    UNCERTAIN = "İNCELEME GEREKLİ (BELİRSİZ)" # < 0.50: Eksik etiket, çelişki veya açıkta kalmış eleman

    @classmethod
    def from_score(cls, score: float) -> "ConfidenceLevel":
        if score >= 0.95:
            return cls.DEFINITE
        elif score >= 0.80:
            return cls.HIGH
        elif score >= 0.50:
            return cls.PROBABLE
        return cls.UNCERTAIN


@dataclass
class AuditFinding:
    severity: str                           # CRITICAL, WARNING, PASS
    module: str                             # KUVVETLİ_AKIM, ZAYIF_AKIM, TOPRAKLAMA_TAVA, ÇAPRAZ_MUTABAKAT
    code: str                               # Benzersiz hata kodu (örn: REC-SEC-A101)
    title: str                              # Hata başlığı
    floor_or_scope: str                     # Mahal / Kat / Pafta kapsamı
    sheet_names: List[str]                  # İlgili pafta isimleri
    element_id: str                         # Cihaz, Pano veya Linye ID
    measured_value: str                     # Çizimden ölçülen değer
    standard_limit: str                     # Standart / Şartname sınırı
    standard_ref: str                       # İlgili yönetmelik maddesi
    engineering_explanation: str            # Mühendislik değerlendirmesi
    recommendation: str                     # Çözüm / Uygulama önerisi
    confidence_level: str = "KESİN"         # KESİN, YÜKSEK GÜVEN, MUHTEMEL, İNCELEME GEREKLİ
    confidence_score: float = 1.0           # 0.0 .. 1.0
    evidence_chain: List[str] = field(default_factory=list) # Neden bu sonuca varıldı? (Kanıt adımları)
    coordinates: Optional[Tuple[float, float]] = None      # Çizim üzerindeki (X, Y) koordinatı
    standard_version: str = ""              # Standart basım/sürüm yılı (örn: TS HD 60364-5-52:2014)
    clause_or_table: str = ""               # İlgili madde ve tablo numarası (örn: Madde 523 / Çizelge B.52.4)
    data_sources: Dict[str, str] = field(default_factory=dict) # Veri kaynakları (EXPLICIT / ESTIMATED / MISSING)
    assumptions_used: List[str] = field(default_factory=list)  # Hesaplamada kullanılan varsayımlar


@dataclass
class UncertaintyItem:
    """
    Doğrudan 'Hata' olarak ilan edilmeyip, mühendisin incelemesine sunulan
    ve çizimdeki belirsizlik veya eksikliklerden kaynaklanan maddeler.
    """
    code: str
    title: str
    floor_or_scope: str
    suspected_element: str
    confidence_score: float
    evidence: str
    impact_description: str
    recommended_verification: str


@dataclass
class ReconciliationItem:
    category: str
    sheet_name: str
    item_id: str
    source_a_label: str
    source_b_label: str
    status: str
    detail: str
    confidence_score: float = 1.0


@dataclass
class PanelLoadSummary:
    panel_tag: str
    floor_name: str
    source_sheets: List[str]
    circuit_count: int
    total_fixtures: int
    l1_power_w: float
    l2_power_w: float
    l3_power_w: float
    total_power_w: float
    imbalance_pct: float
    is_emergency_or_ups: bool
    status: str
    confidence_score: float = 1.0
    power_source: str = "EXPLICIT"
    assumptions_used: List[str] = field(default_factory=list)


@dataclass
class CircuitCalculation:
    panel_tag: str
    circuit_no: str
    phase: str
    floor_name: str
    source_sheet: str
    circuit_type: str
    fixture_count: int
    power_w: float
    voltage_v: int
    current_ib_a: float
    cable_type: str
    cable_cross_section: str
    conductor_mm2: float
    total_length_m: float
    effective_length_m: float
    vd_limit_pct: float
    fe180_required: bool
    fe180_present: bool
    status: str
    notes: str
    voltage_drop_pct: Optional[float] = None
    ampacity_iz_a: Optional[float] = None
    confidence_score: float = 1.0
    evidence: str = ""
    cable_source: str = "MISSING"
    power_source: str = "MISSING"
    length_source: str = "MISSING"
    standard_ref: str = ""
    assumptions_used: List[str] = field(default_factory=list)


@dataclass
class WeakCurrentSubsystemAudit:
    sys_code: str
    sys_name: str
    riser_sheets: List[str]
    plan_sheets: List[str]
    riser_symbol_count: int
    plan_symbol_count: int
    panels_detected: List[str]
    cable_types_detected: List[str]
    has_fiber_backbone: bool
    has_cat6_cables: bool
    fe180_status: str
    engineering_status: str
    notes: List[str]
    max_station_span_m: Optional[float] = None
    confidence_score: float = 1.0


@dataclass
class GroundingAndTraySummary:
    floor_name: str
    sheet_names: List[str]
    ecb_bars: List[str]
    ts28_panel_bonds: List[str]
    conductor_specs: List[str]
    non_lszh_conductors: List[str]
    lv_tray_count: int
    wc_tray_count: int
    tray_schedule_rows: List[Dict[str, str]]
    estimated_lv_fill_pct: Optional[float] = None
    estimated_wc_fill_pct: Optional[float] = None
    confidence_score: float = 1.0


@dataclass
class StationAuditReport:
    station_code: str
    station_name: str
    total_sheets_analyzed: int
    rule_pack_used: str = "TÜRKİYE_BİNA_YÖNETMELİĞİ & İBB_METRO"
    panel_summaries: List[PanelLoadSummary] = field(default_factory=list)
    circuit_calculations: List[CircuitCalculation] = field(default_factory=list)
    reconciliation_items: List[ReconciliationItem] = field(default_factory=list)
    weak_current_audits: List[WeakCurrentSubsystemAudit] = field(default_factory=list)
    grounding_tray_summaries: List[GroundingAndTraySummary] = field(default_factory=list)
    findings: List[AuditFinding] = field(default_factory=list)
    uncertainties: List[UncertaintyItem] = field(default_factory=list)
    symbol_triage_summary: Dict[str, int] = field(default_factory=dict)
