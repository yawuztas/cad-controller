"""
CloudeCAD — Yükleme Cetveli Veri Modelleri
==========================================
CAD, OLE ve Excel kaynaklarından toplanan verilerin
tip güvenli sınıfları.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class CircuitModel:
    """Tekil linye bilgisi (Aydınlatma, Priz vb.)"""
    panel_name: str
    circuit_no: str                 # örn: 'A1', 'P1'
    description: str                # örn: 'Aydınlatma', 'Fırın'
    light_points: int = 0           # Sorti
    socket_points: int = 0
    motor_points: int = 0
    power_w: float = 0.0            # Linye gücü (W)
    phase: str = "R"                # 'R', 'S', 'T' veya 'RST'
    cable_spec: str = "3x2.5 NHXMH"
    conduit_dia_mm: float = 18.0
    breaker_rating_a: float = 16.0
    breaker_curve: str = "C"        # 'B' veya 'C'
    rcd_spec: str = ""
    # Yan yana karşılaştırma alanları
    cad_power_w: Optional[float] = None
    cad_cable_spec: str = ""
    excel_power_w: Optional[float] = None
    excel_cable_spec: str = ""
    triangulation_status: str = "TAM UYUMLU"


@dataclass
class SubPanelModel:
    """Tali Dağıtım Panosu (Daire Tablosu DT, Ortak Alan OT vb.)"""
    name: str                                 # örn: 'DT-1', 'O-T'
    installed_power_w: float = 0.0            # Kurulu Güç (W)
    demand_power_w: float = 0.0               # Talep Gücü (W)
    diversity_factor: float = 1.0             # Eşzamanlılık
    cable_spec: str = "4x6"                   # Besleme kablosu
    cable_cross_section_mm2: float = 6.0
    feeder_length_m: float = 10.0             # Kolon mesafesi (m)
    breaker_spec: str = "3(20A) AOS"          # Giriş sigortası
    breaker_rating_a: float = 20.0
    rcd_spec: str = "4x25A 30mA"              # KAKR
    circuits: List[CircuitModel] = field(default_factory=list)
    sources: List[str] = field(default_factory=list) # ['CAD', 'EXCEL', 'OLE']
    confidence: float = 1.0                   # 0.0 - 1.0
    project_vdrop_kolon_pct: float = 0.0      # Projedeki kolon gerilim düşümü (%e)
    project_vdrop_linye_pct: float = 0.0      # Projedeki en uzun linye gerilim düşümü (%e)
    project_vdrop_total_pct: float = 0.0      # Projedeki toplam gerilim düşümü (%e)

    # ── Yan Yana (Side-by-Side) Çizim vs Rapor Kıyaslama Alanları ──────────────
    cad_installed_power_w: Optional[float] = None
    cad_demand_power_w: Optional[float] = None
    cad_cable_spec: str = ""
    cad_feeder_length_m: Optional[float] = None
    cad_breaker_spec: str = ""
    cad_rcd_spec: str = ""
    excel_installed_power_w: Optional[float] = None
    excel_demand_power_w: Optional[float] = None
    excel_cable_spec: str = ""
    excel_feeder_length_m: Optional[float] = None
    excel_breaker_spec: str = ""
    excel_rcd_spec: str = ""
    excel_vdrop_pct: Optional[float] = None
    triangulation_status: str = "TAM UYUMLU"
    triangulation_notes: str = ""


@dataclass
class MainPanelModel:
    """Ana Dağıtım Panosu (AT / ADP) ve Proje Özeti"""
    name: str = "AT"
    installed_power_w: float = 0.0
    demand_power_w: float = 0.0
    diversity_factor: float = 1.0
    feeder_cable_spec: str = "3x95+50NYY"
    feeder_cross_section_mm2: float = 95.0
    feeder_length_m: float = 50.0
    main_breaker_spec: str = "3x250A TMŞ"
    main_breaker_rating_a: float = 250.0
    main_rcd_spec: str = "300mA"
    total_dwelling_count: int = 0
    sources: List[str] = field(default_factory=list)

    # Yan yana kıyaslama alanları
    cad_installed_power_w: Optional[float] = None
    cad_demand_power_w: Optional[float] = None
    cad_cable_spec: str = ""
    cad_feeder_length_m: Optional[float] = None
    cad_breaker_spec: str = ""
    cad_rcd_spec: str = ""
    excel_installed_power_w: Optional[float] = None
    excel_demand_power_w: Optional[float] = None
    excel_cable_spec: str = ""
    excel_feeder_length_m: Optional[float] = None
    excel_breaker_spec: str = ""
    excel_rcd_spec: str = ""
    excel_vdrop_pct: Optional[float] = None
    triangulation_status: str = "TAM UYUMLU"
    triangulation_notes: str = ""


@dataclass
class DiscrepancyItem:
    """Çapraz kontrol uyuşmazlık veya doğrulama maddesi"""
    panel_name: str
    parameter: str                 # 'installed_power', 'cable_spec', 'length_m', 'breaker'
    cad_val: Any
    excel_val: Any
    ole_val: Any = None
    status: str = "MATCH"          # 'MATCH', 'MISMATCH', 'CAD_ONLY', 'EXCEL_ONLY'
    severity: str = "INFO"         # 'INFO', 'WARNING', 'ERROR'
    message: str = ""


@dataclass
class PhaseBalanceResult:
    """Faz Yük Dengesi ve Nötr Akımı Sonuç Modeli"""
    panel_name: str
    power_r_w: float
    power_s_w: float
    power_t_w: float
    current_r_a: float
    current_s_a: float
    current_t_a: float
    current_neutral_a: float       # Nötr akımı (Vektörel toplam)
    unbalance_pct: float           # Asimetri yüzdesi (%)
    status: str                    # 'DENGELİ (<%15)' veya 'DENGESİZ / NÖTR ISINMA RİSKİ'
    recommendation: str = ""


@dataclass
class ShortCircuitResult:
    """IEC 60909 Kısa Devre ve Termik Dayanım Modeli"""
    panel_name: str
    cable_spec: str
    length_m: float
    cross_section_mm2: float
    r_total_ohm: float             # Kaynaktan panoya toplam R
    x_total_ohm: float             # Kaynaktan panoya toplam X
    z_total_ohm: float             # Toplam empedans
    ik3_max_ka: float              # 3 Faz Kısa Devre Akımı (Maksimum)
    ik1_min_ka: float              # 1 Faz-Nötr Kısa Devre Akımı (Minimum)
    breaker_icn_ka: float          # Sigorta kesme kapasitesi (örn: 6.0 kA veya 10.0 kA veya 25.0 kA)
    breaking_capacity_status: str  # 'UYGUN (Icn >= Ik3)' veya 'YETERSİZ / PATLAMA RİSKİ'
    s_min_thermal_mm2: float       # Termik dayanım için gereken min kesit
    thermal_endurance_status: str  # 'GÜVENLİ (S >= Smin)' veya 'ERİME RİSKİ'
    notes: str = ""


@dataclass
class CadAuditFinding:
    """CAD Çizim Kalitesi, Katman ve Eksiklik Maddesi"""
    id: int
    category: str                  # 'EKSİK ELEMAN', 'LAYER HATASI', 'TUTARSIZLIK', 'DRAFTING HATASI'
    element: str                   # İlgili pano / katman / mahal
    issue: str                     # Çizimde atlanan / yapılan hata
    impact: str                    # Projeye, onay merciine veya sahaya etkisi
    correction: str                # Revizyon için kesin düzeltme talimatı
    severity: str = "UYARI"        # 'KRİTİK', 'UYARI', 'BİLGİ'


@dataclass
class CadAuditReport:
    """CAD Çizim Hijyeni ve Katman Denetim Raporu"""
    total_layers: int = 0
    total_entities: int = 0
    total_text_entities: int = 0
    electrical_layers: List[str] = field(default_factory=list)
    architectural_layers: List[str] = field(default_factory=list)
    layer_stats: Dict[str, int] = field(default_factory=dict)
    findings: List[CadAuditFinding] = field(default_factory=list)
    hygiene_score: int = 70        # 0 - 100


@dataclass
class ExtractedProjectData:
    """Tüm 3 kaynaktan çekilmiş ve çapraz kontrol edilmiş proje verileri"""
    project_name: str
    dxf_path: str
    excel_path: Optional[str] = None
    ole_count: int = 0
    main_panel: MainPanelModel = field(default_factory=MainPanelModel)
    sub_panels: Dict[str, SubPanelModel] = field(default_factory=dict)
    cad_voltage_drop_text: Optional[str] = None
    cad_voltage_drop_val: float = 0.0
    discrepancies: List[DiscrepancyItem] = field(default_factory=list)
    cad_audit: Optional[CadAuditReport] = None
    extraction_logs: List[str] = field(default_factory=list)
    # Metro / Uygulama Paftası Katman & Tablo Metraj Denetim Alanları
    is_metro_plan_sheet: bool = False
    sheet_role: str = ""
    floor_code: str = ""
    floor_name: str = ""
    metro_station_code: str = ""
    metro_sheet_discipline: str = ""
    metro_layer_lengths: Dict[str, float] = field(default_factory=dict)
    metro_bs_count: int = 0
    metro_table_count: int = 0
    metro_table_total_m: float = 0.0
    metro_poly_total_m: float = 0.0
    metro_unlisted_circuits: List[str] = field(default_factory=list)
    metro_sec_mismatches: List[Dict[str, str]] = field(default_factory=list)
    metro_fe180_issues: List[Dict[str, str]] = field(default_factory=list)
    metro_long_circuits: List[Dict[str, Any]] = field(default_factory=list)
    metro_unfinished_notes: List[str] = field(default_factory=list)
    metro_bs_copypaste_errors: List[str] = field(default_factory=list)
    metro_device_counts: Dict[str, int] = field(default_factory=dict)
    metro_eq_loads: List[Dict[str, Any]] = field(default_factory=list)
    metro_socket_phases: Dict[str, Dict[str, int]] = field(default_factory=dict)
    metro_luminaire_wattages: Dict[str, int] = field(default_factory=dict)
    metro_mv_dc_cables: List[Dict[str, Any]] = field(default_factory=list)
    metro_tray_length_m: float = 0.0
    metro_conduit_summary: List[str] = field(default_factory=list)
    metro_foreign_block_warnings: List[str] = field(default_factory=list)


