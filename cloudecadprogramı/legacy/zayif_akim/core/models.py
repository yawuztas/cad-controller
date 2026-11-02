"""
CloudeCAD — Zayıf Akım Sistemleri Veri Modelleri
================================================
Yangın İhbar, Telefon/Data, TV/Uydu, İnterkom ve Denetim Bulgusu modelleri.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class WeakCurrentBlockItem:
    """Tekil zayıf akım bloğu veya sembolü"""
    system: str              # 'FIRE_ALARM', 'TELECOM', 'SMATV', 'INTERCOM', 'POWER_24V'
    block_name: str          # 'DS', 'YB', 'YIS', 'T', '1tk', 'BTK', 'TV', 'TAP', 'ID', 'Z', 'KO'
    count: int = 0
    layer: str = ""
    description: str = ""


@dataclass
class FireAlarmSystemModel:
    """Yangın Algılama ve İhbar Sistemi Modeli (TS EN 54, BYKHY, NFPA 130)"""
    smoke_detectors: int = 0
    heat_detectors: int = 0
    beam_flame_detectors: int = 0        # Endüstriyel / yüksek tavan Beam, Alev veya Gaz dedektörü
    ex_proof_devices: int = 0            # ATEX / Ex-Proof yangın elemanı
    linear_heat_detector_m: float = 0.0  # Tünel / Galeri Fiber-Optik Doğrusal Isı Algılama (LHD)
    manual_call_points: int = 0
    sirens_flashers: int = 0
    control_panels: int = 0
    total_devices: int = 0
    is_drawn: bool = False
    system_type: str = "KONVANSİYONEL"   # 'ADRESLİ' veya 'KONVANSİYONEL'
    fe180_cable_specified: bool = False  # FE180 / PH120 halojensiz ekranlı yangın kablosu
    elevator_interface_relay: bool = False
    fire_pump_interface_relay: bool = False
    scada_hvac_interface: bool = False   # Metro TVS / PSD / Yangın SCADA entegrasyonu
    unmonitored_rooms: List[str] = field(default_factory=list) # Uzamsal STRtree denetiminde dedektörsüz kalan mahaller
    over_spaced_detectors: int = 0       # TS EN 54-14 kapsama yarıçapı (r=6.2m) dışına taşan dedektör sayısı
    status: str = "UYGUN"
    notes: str = ""


@dataclass
class TelecomSystemModel:
    """Telefon ve Yapısal Kablolama (Data / Fiber Omurga) Modeli (BTK & TIA/EIA)"""
    sockets: int = 0                     # Daire/Saha prizleri (T / RJ45 / Data)
    floor_boxes: int = 0                 # Kat dağıtım kutuları (1TK / Rack Kabin)
    main_boxes: int = 0                  # Bina ana telefon kutusu (BTK / Sistem Odası MDF)
    fiber_backbone_rings: int = 0        # Metro / Endüstriyel yedekli Fiber Optik Ring
    cctv_cameras: int = 0                # IP Kamera / CCTV noktaları
    pava_speakers: int = 0               # Acil Anons ve Sesli Tahliye (PA/VA) hoparlörleri
    estimated_pairs: int = 0
    btk_capacity_adequate: bool = True
    is_drawn: bool = False
    status: str = "UYGUN"
    notes: str = ""


@dataclass
class SmatvSystemModel:
    """TV / Uydu Dağıtım Sistemi Modeli (SMATV & TS EN 50083)"""
    tv_sockets: int = 0                  # TV prizleri
    tap_offs: int = 0                    # Kat dağıtıcılar (TAP)
    floor_boxes: int = 0                 # Kat TV kutuları (1tvk)
    multiswitches: int = 0               # TV santrali / Multiswitch (TVS)
    is_drawn: bool = False
    status: str = "UYGUN"
    notes: str = ""


@dataclass
class IntercomSystemModel:
    """Görüntülü / Sesli Diafon ve Kapı Kontrol Modeli"""
    monitors: int = 0                    # Daire içi şubeler / monitörler (ID)
    door_bell_buttons: int = 0           # Daire kapı zilleri (Z)
    door_releases: int = 0               # Kapı otomatiği (KO)
    entrance_panels: int = 0             # Dış kapı panelleri (KZ)
    power_supplies: int = 0              # Besleme trafoları (24V / KF)
    is_drawn: bool = False
    status: str = "UYGUN"
    notes: str = ""


@dataclass
class WeakCurrentAuditFinding:
    """Zayıf akım denetim bulgusu ve eksiklik maddesi"""
    id: int
    system: str                          # 'YANGIN', 'TELEFON_DATA', 'PA_VA_ACIL_ANONS', 'TV_UYDU', 'INTERCOM', 'GENEL_CAD'
    element: str                         # 'Duman Dedektörü', 'Yangın Butonu', 'BTK Kutusu', 'LHD Fiber' vb.
    issue: str                           # Tespit edilen hata / eksiklik
    impact: str                          # Yönetmelik, can güvenliği veya işletme etkisi
    correction: str                      # Kesin düzeltme ve revizyon talimatı
    severity: str = "UYARI"              # 'KRİTİK', 'UYARI', 'BİLGİ'


@dataclass
class WeakCurrentAuditReport:
    """Tüm projenin nihai Zayıf Akım Sistemleri Denetim Raporu"""
    project_name: str
    dxf_path: str
    typology: str = "BUILDING"           # 'BUILDING', 'METRO_RAIL', 'INDUSTRIAL'
    typology_confidence: float = 0.85
    typology_rationale: str = "Standart Konut / Ticari Bina Zayıf Akım Tesisatı (BYKHY & BTK)"
    dwelling_count: int = 0
    floor_count: int = 0
    building_height_m: float = 15.0

    # Raylı Sistem / Metro Alt Rol ve Kat Bilgileri
    sheet_role: str = "BINA_ZAYIF_AKIM"
    station_code: str = ""
    discipline_code: str = ""
    discipline_name: str = ""
    floor_code: str = ""
    floor_name: str = ""
    metro_device_counts: Dict[str, int] = field(default_factory=dict)
    metro_cable_lengths_m: Dict[str, float] = field(default_factory=dict)
    metro_cable_total_m: float = 0.0
    metro_fe180_cable_m: float = 0.0
    metro_copypaste_errors: List[str] = field(default_factory=list)
    metro_foreign_block_warnings: List[str] = field(default_factory=list)
    metro_subsystem_data: Dict[str, Any] = field(default_factory=dict)

    # Standart Bina / Tesis Sistem Modelleri
    fire_alarm: FireAlarmSystemModel = field(default_factory=FireAlarmSystemModel)
    telecom: TelecomSystemModel = field(default_factory=TelecomSystemModel)
    smatv: SmatvSystemModel = field(default_factory=SmatvSystemModel)
    intercom: IntercomSystemModel = field(default_factory=IntercomSystemModel)

    findings: List[WeakCurrentAuditFinding] = field(default_factory=list)
    cad_layers_found: List[str] = field(default_factory=list)
    overall_verdict: str = "UYGUNDUR"
    score_pct: float = 100.0
    extraction_logs: List[str] = field(default_factory=list)


@dataclass
class WeakCurrentStationItem:
    """İstasyon paketi içindeki tekil bir Zayıf Akım paftasının analiz çıktısı."""
    file_path: Any
    report: WeakCurrentAuditReport


@dataclass
class ConsolidatedWeakCurrentStationData:
    """Bir metro istasyonunun tüm Zayıf Akım & Telekom disiplinlerinin (AX-02, TL-02..TL-11) birleştirilmiş modeli."""
    station_code: str
    station_name: str
    line_name: str
    items: List[WeakCurrentStationItem] = field(default_factory=list)
    missing_discipline_warnings: List[str] = field(default_factory=list)
    missing_floor_warnings: List[str] = field(default_factory=list)
    discipline_summaries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    total_devices_by_system: Dict[str, int] = field(default_factory=dict)
    total_cable_poly_m: float = 0.0
    total_fe180_cable_m: float = 0.0
    total_copypaste_errors: int = 0
    total_foreign_blocks: int = 0
    total_critical_findings: int = 0
    total_warning_findings: int = 0
    average_score_pct: float = 100.0

