"""
CloudeCAD — Deklaratif Şartname Kural Paketleri (Specification Rule Packs)
==========================================================================
Koda gömülü (hardcoded) kesit, mesafe, direnç ve ekipman kurallarını
yapılandırılabilir, JSON olarak dışa/içe aktarılabilir şartname profillerine
ayırır.

Desteklenen Standart Profiller:
1. IBB_M9_METRO        : İBB M9 İkitelli - Ataköy Metro Hattı Teknik Şartnamesi
2. AYGM_GENEL_METRO    : Ulaştırma Bakanlığı (AYGM) Raylı Sistemler Genel Şartnamesi
3. TS_HD_60364_BINA    : TS HD 60364-5-54 & EMO Bina Temel Topraklama Şartnamesi
4. IEEE80_ENDUSTRIYEL  : IEEE Std 80-2013 & TS EN 50522 Endüstriyel / OG Trafo Merkezi
"""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

PROFILES_DIR = Path(__file__).parent / "profiles"


@dataclass
class SpecProfile:
    """Bir kurumun veya standardın tüm denetim parametrelerini barındıran veri profili."""
    profile_id: str
    title: str
    institution: str
    standards_ref: List[str]
    typology: str  # "METRO" | "BUILDING" | "INDUSTRIAL"

    # İletken ve Bara Kesit Kuralları
    main_ring_min_mm2: float = 120.0
    branch_min_mm2: float = 16.0
    tunnel_bond_min_mm2: float = 240.0
    busbar_spec: str = "40x5 mm (200 mm²) Elektrolitik Bakır"
    strip_spec: str = "30x3.5 mm (105 mm²) Sıcak Daldırma Galvaniz Çelik / 50 mm² Cu"

    # Hedef Topraklama Direnci ve Ağ Gözü Boyutları
    max_resistance_ohm: float = 1.0
    max_mesh_eye_m: float = 20.0
    mesh_tolerance_ratio: float = 0.05

    # Uzamsal Yakınlık (Spatial Proximity) Denetim Toleransları (metre)
    equipment_max_dist_m: float = 1.50
    hatch_cover_max_dist_m: float = 2.50
    technical_room_max_dist_m: float = 12.0
    require_t_junction_clamp: bool = True
    t_junction_clamp_search_radius_m: float = 1.20

    # Adım ve Dokunma Gerilimi Parametreleri (Endüstriyel / Trafo Merkezi - IEEE Std 80)
    fault_clearing_time_s: float = 0.50
    crushed_rock_rho_s_ohm_m: float = 2500.0
    crushed_rock_thickness_hs_m: float = 0.15

    # Özel Sözleşme / Şartname Notu
    contract_clause_summary: str = ""


# ═══════════════════════════════════════════════════════════════
#  YERLEŞİK (BUILT-IN) KURUMSAL ŞARTNAME PROFİLLERİ
# ═══════════════════════════════════════════════════════════════

BUILTIN_PROFILES: Dict[str, SpecProfile] = {
    "IBB_M9_METRO": SpecProfile(
        profile_id="IBB_M9_METRO",
        title="M9 İkitelli - Ataköy Metro Hattı Teknik Şartnamesi ve Sözleşme Hükümleri",
        institution="İstanbul Büyükşehir Belediyesi (İBB) Raylı Sistem Dairesi Başkanlığı",
        standards_ref=[
            "İBB M9 Teknik Şartnamesi Bölüm 1.07.01 (Topraklama ve Eşpotansiyel Bağlama)",
            "İBB M9 Teknik Şartnamesi Bölüm 1.07.04 (Yıldırımdan Korunma)",
            "İBB M9 Teknik Şartnamesi Bölüm 5.1 & 5.2 (Kapak, Merdiven, Pano ve Klemens İrtibatları)",
            "TS EN 50122-1 (Raylı Sistemler - Sabit Tesisler - Elektriksel Güvenlik ve Topraklama)",
            "TS EN 50122-2 (DC Cer Sistemlerinin Yol Açtığı Kaçak Akımlara Karşı Koruma)",
            "TS HD 60364-5-54 (Topraklama Düzenlemeleri ve Koruma İletkenleri)"
        ],
        typology="METRO",
        main_ring_min_mm2=120.0,
        branch_min_mm2=16.0,
        tunnel_bond_min_mm2=240.0,
        busbar_spec="40x5 mm (200 mm²) Elektrolitik Bakır (ECB/ETB)",
        max_resistance_ohm=1.0,
        max_mesh_eye_m=20.0,
        equipment_max_dist_m=1.50,
        hatch_cover_max_dist_m=2.50,
        technical_room_max_dist_m=12.0,
        require_t_junction_clamp=True,
        t_junction_clamp_search_radius_m=1.20,
        contract_clause_summary=(
            "Sözleşme Bölüm 1.07.01 & 5.1-5.2 uyarınca istasyon içi ana eşpotansiyel ring 120 mm² "
            "örgülü bakır, ekipman/kapak/merdiven/tava branşmanları en az 16 mm² NYAF (Sarı/Yeşil) "
            "veya 50 mm² bakır, tünel-kuyu geçişleri 240 mm² NYY olmalı; tüm T-ek noktalarında "
            "bakır/bimetal klemens (kkk) veya cadweld kaynak bulunmalıdır."
        )
    ),
    "AYGM_GENEL_METRO": SpecProfile(
        profile_id="AYGM_GENEL_METRO",
        title="Ulaştırma ve Altyapı Bakanlığı (AYGM) Raylı Sistemler Elektrik Teknik Şartnamesi",
        institution="T.C. Ulaştırma ve Altyapı Bakanlığı Altyapı Yatırımları Genel Müdürlüğü (AYGM)",
        standards_ref=[
            "AYGM Raylı Sistemler Elektromekanik Teknik Şartnamesi",
            "TS EN 50122-1 & TS EN 50122-2",
            "TS HD 60364-5-54"
        ],
        typology="METRO",
        main_ring_min_mm2=120.0,
        branch_min_mm2=16.0,
        tunnel_bond_min_mm2=240.0,
        busbar_spec="50x5 mm veya 40x5 mm Elektrolitik Bakır",
        max_resistance_ohm=1.0,
        max_mesh_eye_m=20.0,
        equipment_max_dist_m=1.50,
        hatch_cover_max_dist_m=2.50,
        technical_room_max_dist_m=12.0,
        require_t_junction_clamp=True,
        t_junction_clamp_search_radius_m=1.20,
        contract_clause_summary=(
            "AYGM Raylı Sistemler Şartnamesi uyarınca istasyon ana topraklama barasından (METB) "
            "tüm teknik odalara yedekli ring hattı çekilmeli, tüm metal aksamlar eşpotansiyel "
            "baralara irtibatlandırılmalıdır."
        )
    ),
    "TS_HD_60364_BINA": SpecProfile(
        profile_id="TS_HD_60364_BINA",
        title="TS HD 60364-5-54 & EMO Bina Temel Topraklama ve Eşpotansiyel Şartnamesi",
        institution="TMMOB Elektrik Mühendisleri Odası (EMO) / TSE",
        standards_ref=[
            "Elektrik Tesislerinde Topraklamalar Yönetmeliği (ETTY - 21.08.2001 / 24500)",
            "TS HD 60364-5-54 (Alçak Gerilim Elektrik Tesisleri - Topraklama Düzenlemeleri)",
            "TS EN 62305-3 (Yıldırımdan Korunma - Yapılarda Fiziksel Hasar ve Hayati Tehlike)"
        ],
        typology="BUILDING",
        main_ring_min_mm2=50.0,
        branch_min_mm2=16.0,
        tunnel_bond_min_mm2=95.0,
        busbar_spec="40x5 mm Bakır Ana Topraklama Barası (ATB/ETB)",
        strip_spec="30x3.5 mm (105 mm²) Sıcak Daldırma Galvaniz Çelik Şerit",
        max_resistance_ohm=2.0,
        max_mesh_eye_m=20.0,
        mesh_tolerance_ratio=0.05,
        equipment_max_dist_m=2.00,
        hatch_cover_max_dist_m=2.50,
        require_t_junction_clamp=True,
        contract_clause_summary=(
            "Bina temel topraklaması radye temel altında kapalı ring oluşturacak şekilde "
            "en az 30x3.5 mm galvaniz şerit veya 50 mm² bakır iletken ile maks. 20x20 m ağ "
            "gözleriyle tesis edilmeli; eşdeğer direnç Re ≤ 2.0 Ω olmalıdır."
        )
    ),
    "IEEE80_ENDUSTRIYEL": SpecProfile(
        profile_id="IEEE80_ENDUSTRIYEL",
        title="IEEE Std 80-2013 & TS EN 50522 Endüstriyel Tesis ve OG Trafo Merkezi Şartnamesi",
        institution="TEİAŞ / TEDAŞ / IEEE Power and Energy Society",
        standards_ref=[
            "IEEE Std 80-2013 (Guide for Safety in AC Substation Grounding)",
            "TS EN 50522 (1 kV'u Aşan AC Güç Tesislerinin Topraklanması)",
            "Elektrik Tesislerinde Topraklamalar Yönetmeliği (ETTY - Madde 10 & Ek-P)",
            "TEİAŞ Trafo Merkezleri Topraklama Teknik Şartnamesi"
        ],
        typology="INDUSTRIAL",
        main_ring_min_mm2=95.0,
        branch_min_mm2=50.0,
        tunnel_bond_min_mm2=120.0,
        busbar_spec="50x5 mm veya 40x10 mm Elektrolitik Bakır (OG/AG Topraklama Barası)",
        strip_spec="70–120 mm² Örgülü Bakır veya 40x4 mm Sıcak Daldırma Galvaniz Şerit",
        max_resistance_ohm=1.0,
        max_mesh_eye_m=10.0,
        mesh_tolerance_ratio=0.10,
        equipment_max_dist_m=2.00,
        hatch_cover_max_dist_m=2.50,
        technical_room_max_dist_m=10.0,
        require_t_junction_clamp=True,
        fault_clearing_time_s=0.50,
        crushed_rock_rho_s_ohm_m=2500.0,
        crushed_rock_thickness_hs_m=0.15,
        contract_clause_summary=(
            "Endüstriyel tesis ve OG trafo merkezlerinde eşdeğer ağ direnci Rg ≤ 1.0 Ω olmalı, "
            "ağ gözleri maks. 10x10 m olarak tasarlanmalı, oluşan göz (Em) ve adım (Es) "
            "gerilimleri IEEE Std 80 müsaade edilen dokunma (Etouch70) ve adım (Estep70) "
            "sınırlarının altında kalmalı; trafo, hücre, jeneratör, proses tankı, çelik kolon "
            "ve çevre çiti çift irtibatla topraklama ağına bağlanmalıdır."
        )
    ),
}


def ensure_default_profile_files() -> None:
    """Varsayılan profilleri standards/profiles/*.json olarak diske yazar (kullanıcı düzenleyebilsin diye)."""
    try:
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        for pid, prof in BUILTIN_PROFILES.items():
            json_path = PROFILES_DIR / f"{pid.lower()}.json"
            if not json_path.exists():
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(asdict(prof), f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_spec_profile(profile_id: str = "IBB_M9_METRO") -> SpecProfile:
    """
    İstenen şartname profilini önce standards/profiles/*.json klasöründen okur
    (böylece kullanıcı JSON dosyasını düzenlediyse koda dokunmadan yeni kural geçerli olur),
    bulunamazsa yerleşik (built-in) profili döner.
    """
    ensure_default_profile_files()
    pid = profile_id.upper()
    json_path = PROFILES_DIR / f"{pid.lower()}.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SpecProfile(**data)
        except Exception:
            pass
    return BUILTIN_PROFILES.get(pid, BUILTIN_PROFILES["IBB_M9_METRO"])
