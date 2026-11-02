"""
CloudeCAD — Proje Tipolojisi ve Pafta Rolü Sınıflandırıcı (Project Classifier)
==============================================================================
Çizimleri ve proje paketlerini 3 temel mühendislik kategorisine ayırır:
  1. BİNA PROJESİ (Konut, Apartman, Ofis, AVM vb.) -> TS HD 60364-5-54 & ETTK Ek-N
  2. METRO / RAYLI SİSTEM PROJESİ (İstasyon, Tünel, Depo) -> EN 50122-1/2 & İBB Şartnamesi
  3. ENDÜSTRİYEL TESİS PROJESİ (Fabrika, Şalt Sahası, Trafo Merkezi) -> IEEE Std 80 & EN 50522

Metro projelerinde ayrıca paftanın işlevsel rolünü tespit eder:
  - ROLE_EXTERNAL_GRID      : Dış Saha / Kuyu Elektrotları / Muayene Rögarları
  - ROLE_MAIN_ROUTE          : Hat Boyu Güzergah / OG Konsol / Ray & Tünel Şebekesi
  - ROLE_SUB_PLATFORM_MASTER : Peron Altı Ana Topraklama Barası (Master ETB)
  - ROLE_FLOOR_DISTRIBUTION  : Kat İçi Eşpotansiyel Kuşaklama & Pano/Bara Dağıtımı
  - ROLE_TYPICAL_DETAILS     : Tipik Montaj Detayları, Semboller & Şartname Notları
"""

import re
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


PROJECT_TYPE_BUILDING = "BINA"
PROJECT_TYPE_METRO = "METRO"
PROJECT_TYPE_INDUSTRIAL = "ENDUSTRI"

# Metro Pafta Rolleri
ROLE_EXTERNAL_GRID = "EXTERNAL_GRID"            # Dış Saha / Kuyu & Menhol Ağı
ROLE_MAIN_ROUTE = "MAIN_ROUTE"                  # Hat Boyu Güzergah & Konsol
ROLE_SUB_PLATFORM_MASTER = "SUB_PLATFORM_MASTER"# Peron Altı Ana Topraklama Barası (Master ETB)
ROLE_FLOOR_DISTRIBUTION = "FLOOR_DISTRIBUTION"  # Kat İçi Eşpotansiyel & Dağıtım
ROLE_TYPICAL_DETAILS = "TYPICAL_DETAILS"        # Tipik Detaylar & Şartname


@dataclass
class ProjectTypeResult:
    typology: str                               # 'BINA' | 'METRO' | 'ENDUSTRI'
    confidence: float = 1.0                     # 0.0 - 1.0
    reasons: List[str] = field(default_factory=list)
    metro_role: Optional[str] = None            # ROLE_... (eğer METRO ise)
    floor_level_name: str = ""                  # Örn: 'PERON ALTI KATI', 'BİLET HOLÜ'
    has_sub_platform_master: bool = False       # Peron Altı Ana Barası var mı?
    has_external_grid: bool = False             # Dış saha ağı veya kuyu elektrotları var mı?


# Anahtar Kelime Kümeleri
METRO_KEYWORDS = [
    "metro", "istasyon", "istasyonu", "peron", "peron altı", "peron alti",
    "bilet holü", "bilet holu", "konkurs", "ray", "ray altı", "ray alti",
    "tünel", "tunel", "katenar", "traksiyon", "cer gücü", "cer gucu",
    "vld", "og konsol", "hat 1", "hat 2", "hat1", "hat2", "stray current",
    "kaçak akım kuşağı", "raylı sistem", "rayli sistem", "ibb rayli",
    "m09", "m9", "m4", "m7", "m1", "m2", "m3", "m5", "m8", "m11", "m12",
    "ps-17", "ps-16", "ps-18", "bt0-", "ct0-", "u-t-2i"
]

INDUSTRIAL_KEYWORDS = [
    "şalt", "salt", "substation", "şalt sahası", "trafo merkezi", "fabrika",
    "rafineri", "endüstri", "endustri", "sanayi", "ex-proof", "tank sahası",
    "statik topraklama", "işletme topraklaması", "isletme topraklamasi",
    "yg/og", "og/ag trafo", "mesh grid", "grid mesh", "ieee 80", "ieee std 80"
]

BUILDING_KEYWORDS = [
    "daire", "apartman", "konut", "bina", "blok", "kat planı", "kat plani",
    "bodrum kat", "zemin kat", "normal kat", "teras kat", "çatı katı",
    "sığınak", "siginak", "kazan dairesi", "otopark", "radsan", "eh şablonu"
]


def classify_project(drawing_or_path: Any, text_samples: Optional[List[str]] = None) -> ProjectTypeResult:
    """
    Verilen DXF/DWG dosyasını, ParsedDrawing nesnesini veya metin listesini
    inceleyerek proje tipolojisini (BINA, METRO, ENDUSTRI) ve metro rolünü belirler.
    """
    file_name = ""
    block_names = []
    layer_names = []
    texts = []

    if isinstance(drawing_or_path, (str, Path)):
        p = Path(drawing_or_path)
        file_name = p.name.lower()
    elif hasattr(drawing_or_path, 'source_file'):
        file_name = Path(drawing_or_path.source_file).name.lower()
        if hasattr(drawing_or_path, 'all_layers'):
            layer_names = [l.lower() for l in drawing_or_path.all_layers.keys()]
        if hasattr(drawing_or_path, 'all_texts'):
            texts = [t.text.lower() for t in drawing_or_path.all_texts]
    
    if text_samples:
        texts.extend([t.lower() for t in text_samples])

    all_content = " ".join([file_name] + layer_names + texts[:1000]).lower()

    metro_score = 0
    ind_score = 0
    bldg_score = 0
    reasons = []

    # 1. Metro Puanlaması
    for kw in METRO_KEYWORDS:
        if kw in all_content:
            metro_score += 2
            if len(reasons) < 5 and kw in file_name or any(kw in t for t in texts[:100]):
                reasons.append(f"Metro anahtar kelimesi: '{kw}'")

    # 2. Endüstri Puanlaması
    for kw in INDUSTRIAL_KEYWORDS:
        if kw in all_content:
            ind_score += 2
            if len(reasons) < 5:
                reasons.append(f"Endüstriyel anahtar kelime: '{kw}'")

    # 3. Bina Puanlaması
    for kw in BUILDING_KEYWORDS:
        if kw in all_content:
            bldg_score += 1
            if len(reasons) < 5 and (kw in file_name or "daire" in all_content):
                reasons.append(f"Bina anahtar kelimesi: '{kw}'")

    # Raylı sistem kodlama yapısı (Örn: PS-17, U-T-2I, M09, S19)
    if re.search(r'm\d{2}-prt', file_name) or "ps-17" in file_name or "u-t-2i" in file_name:
        metro_score += 10
        reasons.append("İBB Raylı Sistemler proje kodlama standardı (PS-17 / U-T-2I)")

    # Nihai Tipoloji Kararı
    if metro_score >= max(ind_score, bldg_score, 4):
        typology = PROJECT_TYPE_METRO
        confidence = min(1.0, 0.6 + metro_score * 0.05)
    elif ind_score > max(metro_score, bldg_score, 4):
        typology = PROJECT_TYPE_INDUSTRIAL
        confidence = min(1.0, 0.6 + ind_score * 0.05)
    else:
        typology = PROJECT_TYPE_BUILDING
        confidence = 0.85
        if not reasons:
            reasons.append("Standart bina temel topraklaması formatı")

    # Metro İse Pafta Rolü Tespiti
    metro_role = None
    floor_name = ""
    has_sub_platform = False
    has_ext_grid = False

    if typology == PROJECT_TYPE_METRO:
        fn_upper = file_name.upper()

        # 1. Pafta koduna ve doğrudan dosya adına göre öncelikli rol tespiti
        if "BT0-00" in fn_upper or "PERON ALTI KOTU" in all_content or "SSL PERON ALTI" in all_content:
            metro_role = ROLE_SUB_PLATFORM_MASTER
            floor_name = "PERON ALTI KATI (-48.55 Kotu)"
            has_sub_platform = True
            reasons.append("Peron Altı Ana Topraklama Barası (Master ETB) tespit edildi")
        elif "000-99-PS-17-U-T-2I-001" in fn_upper or ("000-99" in fn_upper and "001" in fn_upper) or "RÖGAR KAPAĞI" in all_content or "AĞI İLETKENİ KANALI" in all_content:
            metro_role = ROLE_EXTERNAL_GRID
            floor_name = "DIŞ SAHA / ELEKTROT & RÖGAR PLANI"
            has_ext_grid = True
            reasons.append("Dış saha topraklama ağı, elektrot ve menhol detayları tespit edildi")
        elif "000-99-PS-17-U-T-2I-011" in fn_upper or ("000-99" in fn_upper and "011" in fn_upper) or "KONSOL TOPRAKLAMASI" in all_content:
            metro_role = ROLE_MAIN_ROUTE
            floor_name = "HAT BOYU GÜZERGAH & TÜNEL PLANI"
            reasons.append("Hat boyu OG konsol ve tünel güzergahı tespit edildi")
        elif "BT0-01" in fn_upper or "PERON KATI" in all_content:
            metro_role = ROLE_FLOOR_DISTRIBUTION
            floor_name = "PERON KATI"
        elif "CT0-02" in fn_upper or "KONKURS" in all_content or "ARA KAT" in all_content:
            metro_role = ROLE_FLOOR_DISTRIBUTION
            floor_name = "ARA KAT / KONKURS KATI"
        elif "CT0-03" in fn_upper or "BİLET HOLÜ" in all_content or "BILET HOLU" in all_content:
            metro_role = ROLE_FLOOR_DISTRIBUTION
            floor_name = "BİLET HOLÜ / TURNİKE KATI"
        elif "CT0-2A" in fn_upper or "ASMA KAT" in all_content:
            metro_role = ROLE_FLOOR_DISTRIBUTION
            floor_name = "ASMA KAT"
        elif "CT0-2B" in fn_upper or "TEKNİK KAT" in all_content or "TEKNIK KAT" in all_content:
            metro_role = ROLE_FLOOR_DISTRIBUTION
            floor_name = "TEKNİK KAT 1-2 (Trafo & OG Odaları)"
        elif "CT0-2C" in fn_upper or "ÜST TABLİYE" in all_content or "UST TABLIYE" in all_content:
            metro_role = ROLE_FLOOR_DISTRIBUTION
            floor_name = "ÜST TABLİYE (+76.00 Kotu)"
        else:
            metro_role = ROLE_FLOOR_DISTRIBUTION
            floor_name = "İSTASYON KAT PLANI"

    return ProjectTypeResult(
        typology=typology,
        confidence=confidence,
        reasons=reasons,
        metro_role=metro_role,
        floor_level_name=floor_name,
        has_sub_platform_master=has_sub_platform,
        has_external_grid=has_ext_grid,
    )
