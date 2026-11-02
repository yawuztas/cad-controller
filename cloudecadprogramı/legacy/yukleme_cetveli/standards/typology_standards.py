"""
CloudeCAD — Üniversal Proje Tipolojileri ve Yük Standartları
============================================================
Konut (BEDAŞ/TEDAŞ), Altyapı/Metro (NFPA 130 & IEC), Endüstriyel
ve Ticari binalar için yük kategorileri, kullanım (ku) ve eşzamanlılık (ks)
katsayıları ile işletme senaryoları.
"""

from enum import Enum
from typing import Dict, List, Tuple


class ProjectTypology(str, Enum):
    RESIDENTIAL = "RESIDENTIAL"                     # Konut / Apartman / Site
    INFRASTRUCTURE_METRO = "INFRASTRUCTURE_METRO"   # Metro / Raylı Sistem / Tünel
    INDUSTRIAL = "INDUSTRIAL"                       # Fabrika / Atölye / Depo
    COMMERCIAL = "COMMERCIAL"                       # AVM / Ofis Kulesi / Otel
    GENERAL = "GENERAL"                             # Genel / Belirsiz


class LoadCategory(str, Enum):
    LIGHTING = "LIGHTING"               # Aydınlatma (sürekli yük)
    SOCKET = "SOCKET"                   # Genel prizler (kesikli yük)
    HVAC_MOTOR = "HVAC_MOTOR"           # Klima, havalandırma, fan, pompa
    TRANSPORT = "TRANSPORT"             # Yürüyen merdiven, asansör
    FIRE_EMERGENCY = "FIRE_EMERGENCY"   # Tünel duman tahliye fanları (TVF), yangın pompaları
    CRITICAL_UPS = "CRITICAL_UPS"       # Sinyalizasyon, SCADA, telekom, veri
    HEAVY_MACHINERY = "HEAVY_MACHINERY" # Kompresör, vinç, kaynak


# ── Yük Kategorisi Anahtar Kelime Haritası ─────────────────────────────────────
LOAD_CATEGORY_KEYWORDS = {
    LoadCategory.LIGHTING: [
        'ayd', 'aydınlatma', 'light', 'lighting', 'lamba', 'armatür', 'floran', 'led', 'downlight'
    ],
    LoadCategory.SOCKET: [
        'prz', 'priz', 'socket', 'shuko', 'ups priz', 'şebeke priz'
    ],
    LoadCategory.HVAC_MOTOR: [
        'motor', 'mot', 'chiller', 'klima', 'fancoil', 'fcu', 'klima santrali', 'ahu',
        'vav', 'egzoz fan', 'taze hava', 'pompa', 'sirkülasyon', 'hidrofor', 'kazan'
    ],
    LoadCategory.TRANSPORT: [
        'asansör', 'asansor', 'elevator', 'lift', 'yürüyen merdiven', 'escalator', 'yürüyen bant'
    ],
    LoadCategory.FIRE_EMERGENCY: [
        'tvf', 'duman tahliye', 'smoke', 'yangın', 'yangin', 'sprinkler', 'basınçlandırma',
        'itfaiye', 'jetfan', 'yangın pompası'
    ],
    LoadCategory.CRITICAL_UPS: [
        'ups', 'scada', 'sinyal', 'sinyalizasyon', 'signaling', 'telsiz', 'tetra', 'cctv',
        'anons', 'pa/va', 'sunucu', 'server', 'rack', 'yangın algılama'
    ],
    LoadCategory.HEAVY_MACHINERY: [
        'kompresör', 'vinç', 'crane', 'kaynak', 'torna', 'pres', 'fırın', 'traksiyon', 'catenary'
    ]
}


# ── Tipolojiye Göre Kullanım (ku) ve Eşzamanlılık (ks) Standartları ───────────
# IEC 60364-1 & IEEE 141 Red Book Normları
TYPOLOGY_LOAD_FACTORS = {
    ProjectTypology.RESIDENTIAL: {
        LoadCategory.LIGHTING:       {"ku": 1.00, "ks": 0.60, "cos_phi": 0.90},
        LoadCategory.SOCKET:         {"ku": 1.00, "ks": 0.40, "cos_phi": 0.85},
        LoadCategory.HVAC_MOTOR:     {"ku": 0.80, "ks": 0.70, "cos_phi": 0.80},
        LoadCategory.TRANSPORT:      {"ku": 0.75, "ks": 0.80, "cos_phi": 0.80},
        LoadCategory.FIRE_EMERGENCY: {"ku": 1.00, "ks": 1.00, "cos_phi": 0.85},
        LoadCategory.CRITICAL_UPS:   {"ku": 1.00, "ks": 1.00, "cos_phi": 0.95},
    },
    ProjectTypology.INFRASTRUCTURE_METRO: {
        # Normal İşletme Modu
        "NORMAL_MODE": {
            LoadCategory.LIGHTING:       {"ku": 1.00, "ks": 1.00, "cos_phi": 0.92},
            LoadCategory.SOCKET:         {"ku": 0.50, "ks": 0.20, "cos_phi": 0.85},
            LoadCategory.HVAC_MOTOR:     {"ku": 0.85, "ks": 0.80, "cos_phi": 0.82}, # İstasyon konfor iklimlendirme
            LoadCategory.TRANSPORT:      {"ku": 0.85, "ks": 0.90, "cos_phi": 0.80}, # Merdivenler sürekli çalışır
            LoadCategory.FIRE_EMERGENCY: {"ku": 0.00, "ks": 0.00, "cos_phi": 0.85}, # TVF normalde 0 kW beklemede
            LoadCategory.CRITICAL_UPS:   {"ku": 0.80, "ks": 1.00, "cos_phi": 0.95}, # Sinyalizasyon tam devrede
        },
        # Yangın / Acil Durum Modu (NFPA 130)
        "EMERGENCY_FIRE_MODE": {
            LoadCategory.LIGHTING:       {"ku": 1.00, "ks": 0.80, "cos_phi": 0.92}, # Kaçış aydınlatması
            LoadCategory.SOCKET:         {"ku": 0.00, "ks": 0.00, "cos_phi": 0.85}, # Prizler kesilir
            LoadCategory.HVAC_MOTOR:     {"ku": 0.00, "ks": 0.00, "cos_phi": 0.82}, # Konfor iklimlendirme KESİLİR
            LoadCategory.TRANSPORT:      {"ku": 0.00, "ks": 0.00, "cos_phi": 0.80}, # Merdivenler durdurulur
            LoadCategory.FIRE_EMERGENCY: {"ku": 1.00, "ks": 1.00, "cos_phi": 0.85}, # TVF Tünel Fanları %100 TAM GÜÇ
            LoadCategory.CRITICAL_UPS:   {"ku": 0.90, "ks": 1.00, "cos_phi": 0.95}, # Acil anons & yangın SCADA
        }
    },
    ProjectTypology.INDUSTRIAL: {
        LoadCategory.LIGHTING:       {"ku": 1.00, "ks": 0.90, "cos_phi": 0.90},
        LoadCategory.SOCKET:         {"ku": 0.60, "ks": 0.30, "cos_phi": 0.85},
        LoadCategory.HVAC_MOTOR:     {"ku": 0.85, "ks": 0.75, "cos_phi": 0.82},
        LoadCategory.HEAVY_MACHINERY:{"ku": 0.75, "ks": 0.65, "cos_phi": 0.78},
        LoadCategory.FIRE_EMERGENCY: {"ku": 1.00, "ks": 1.00, "cos_phi": 0.85},
        LoadCategory.CRITICAL_UPS:   {"ku": 0.85, "ks": 1.00, "cos_phi": 0.95},
    },
    ProjectTypology.COMMERCIAL: {
        LoadCategory.LIGHTING:       {"ku": 1.00, "ks": 0.90, "cos_phi": 0.90},
        LoadCategory.SOCKET:         {"ku": 0.70, "ks": 0.40, "cos_phi": 0.85},
        LoadCategory.HVAC_MOTOR:     {"ku": 0.85, "ks": 0.80, "cos_phi": 0.82},
        LoadCategory.TRANSPORT:      {"ku": 0.80, "ks": 0.85, "cos_phi": 0.80},
        LoadCategory.FIRE_EMERGENCY: {"ku": 1.00, "ks": 1.00, "cos_phi": 0.85},
        LoadCategory.CRITICAL_UPS:   {"ku": 0.80, "ks": 1.00, "cos_phi": 0.95},
    }
}


def classify_circuit_or_load(description: str, circuit_no: str = "") -> LoadCategory:
    """Verilen açıklama veya linye numarasına göre yük kategorisini sınıflandırır."""
    text = f"{description} {circuit_no}".lower()
    
    # TVF veya yangın önceliklidir
    for kw in LOAD_CATEGORY_KEYWORDS[LoadCategory.FIRE_EMERGENCY]:
        if kw in text:
            return LoadCategory.FIRE_EMERGENCY
            
    # Kritik UPS / SCADA
    for kw in LOAD_CATEGORY_KEYWORDS[LoadCategory.CRITICAL_UPS]:
        if kw in text:
            return LoadCategory.CRITICAL_UPS

    # Ulaşım / Merdiven / Asansör
    for kw in LOAD_CATEGORY_KEYWORDS[LoadCategory.TRANSPORT]:
        if kw in text:
            return LoadCategory.TRANSPORT

    # Ağır Makine / Kompresör
    for kw in LOAD_CATEGORY_KEYWORDS[LoadCategory.HEAVY_MACHINERY]:
        if kw in text:
            return LoadCategory.HEAVY_MACHINERY

    # HVAC / Motor
    for kw in LOAD_CATEGORY_KEYWORDS[LoadCategory.HVAC_MOTOR]:
        if kw in text:
            return LoadCategory.HVAC_MOTOR

    # Aydınlatma
    for kw in LOAD_CATEGORY_KEYWORDS[LoadCategory.LIGHTING]:
        if kw in text or circuit_no.upper().startswith('A') or circuit_no.upper().startswith('L'):
            return LoadCategory.LIGHTING

    # Priz (Varsayılan genel yük)
    return LoadCategory.SOCKET
