"""
CloudeCAD — Zayıf Akım Sistemleri Denetim Motoru Yapılandırması
==============================================================
Yangın Algılama (TS EN 54 & BYKHY), Telefon/Data (BTK),
TV/Uydu (TS EN 50083) ve İnterkom standart eşikleri ve katman tanımları.
"""

from pathlib import Path

# Dizin Yolları
BASE_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Standart CAD Katman Eşleşmeleri ──────────────────────────────────────────
# ── Standart CAD Katman Eşleşmeleri ──────────────────────────────────────────
WEAK_CURRENT_LAYERS = {
    "FIRE_ALARM": [
        "00-YANGIN", "YANGIN", "FIRE", "FIRE_ALARM", "YANGIN_IHBAR",
        "PRT-EL-FIRE", "PRT_EL-FIRE", "Yangın kablo metraj", "BE_YANGIN"
    ],
    "TELECOM_DATA": [
        "00-TEL", "TEL", "TELEFON", "DATA", "NETWORK", "ZAYIF_TEL",
        "PRT_TEL", "PRT-TEL", "PRT-EL-DATA", "BE_DATA"
    ],
    "SMATV_TV": [
        "00-TV", "TV", "UYDU", "SMATV", "ANTEN", "CATV"
    ],
    "INTERCOM": [
        "00-INTERCOM", "INTERCOM", "DIAFON", "DİAFON", "ZIL", "KAPI_ZILI"
    ],
    "POWER_24V": [
        "00-24V", "24V", "GUC_KAYNAGI", "ZAYIF_BESLEME"
    ],
    "CCTV": [
        "00-CCTV", "CCTV", "KAMERA", "CAMERA", "BE_CCTV", "PRT_EL _E-CCTV-EQPM", "CCTV Kablo"
    ],
    "PA_VA_ANONS": [
        "00-ANONS", "ANONS", "PAVA", "PA-VA", "SESLENDIRME", "SPEAKER", "HOPARLOR"
    ],
    "ACCESS_CONTROL": [
        "00-KARTLI", "KARTLI_GECIS", "ACCESS", "ACS", "KAPI_KONTROL"
    ],
    "CLOCK_SYSTEM": [
        "00-SAAT", "SAAT", "CLOCK", "PRT-EL-CLOCK", "PRT_EL _CLOCK_HAT"
    ],
    "TETRA_RADIO": [
        "00-TELSİZ", "TELSİZ", "TELSİZ_HAT", "TETRA", "KABLOLAMA TELSİZ SİSTEMİ"
    ],
    "SCADA_AUTOMATION": [
        "00-SCADA", "SCADA", "PLC", "OTOMASYON", "BMS", "SMS"
    ],
    "PIS_DISPLAY": [
        "00-PIS", "PIS", "YBS", "EKRAN", "MONITOR", "YOLCU_BILGI"
    ]
}

# ── Standart CAD Blok / Sembol İsimleri ──────────────────────────────────────
WEAK_CURRENT_BLOCKS = {
    # Yangın Algılama & İhbar (TS EN 54 & NFPA 130)
    "SMOKE_DETECTOR": [
        "DS", "OD", "DUMAN", "SMOKE", "DUMAN_DEDEKTORU",
        "OPTİK DUMAN DEDEKTÖRÜ", "OPTIK DUMAN DEDEKTORU"
    ],
    "HEAT_DETECTOR": [
        "SD", "SICAKLIK", "ISI", "HEAT", "SICAKLIK_DEDEKTORU",
        "ISI DEDEKTÖRÜ", "ISI DEDEKTORU"
    ],
    "COMBINED_DETECTOR": [
        "KOMBİNE (DUMAN-ISI) DEDEKTÖRÜ", "KOMBINE DEDEKTOR", "MULTI_DETECTOR"
    ],
    "FIRE_CALL_POINT": [
        "YB", "BUTON", "MANUAL_CALL", "YANGIN_BUTONU",
        "YANGIN İHBAR BUTONU", "YANGIN IHBAR BUTONU"
    ],
    "FIRE_SIREN": [
        "SKM", "SIREN", "FLASOR", "KORNA", "SIREN_FLASOR",
        "KONVANSİYONEL FLAŞÖR", "KONVANSIYONEL FLASOR", "ADRESLI SIREN"
    ],
    "FIRE_MODULE": [
        "GİRİŞ-ÇIKIŞ MODÜLÜ", "GIRIS-CIKIS MODULU", "KONTROL MODÜLÜ",
        "İZLEME MODÜLÜ", "ROLE MODULU", "MODUL"
    ],
    "FIRE_PANEL": [
        "YIS", "FACP", "SANTRAL", "YANGIN_SANTRALI",
        "YANGIN ALGILAMA SANTRALI", "YANGIN KONTROL PANELI"
    ],

    # Telefon & Dahili Haberleşme
    "TELECOM_SOCKET": [
        "T", "TEL", "DATA", "RJ45", "RJ11", "PRIZ_TEL",
        "TELEFON PRİZİ (Ts - SERVİS)", "TELEFON SORTİSİ (ATM)"
    ],
    "SERVICE_PHONE": [
        "ANALOG (SERVİS) TELEFONU", "ANALOG TELEFON", "IP TELEFON",
        "ANALOG (NEME DAYANIKLI) TELEFON"
    ],
    "EMERGENCY_PHONE": [
        "ACİL DURUM TELEFONU", "ACIL DURUM TELEFONU", "SOS TELEFONU", "TÜNEL TELEFONU"
    ],
    "TELECOM_MDF": [
        "TELEFON ANA DAĞITIM ÇATISI", "BTK", "Bina Telefon Kutusu", "ANA_TELEFON", "MDF"
    ],
    "BUILDING_TELECOM_BOX": [
        "TELEFON ANA DAĞITIM ÇATISI", "BTK", "Bina Telefon Kutusu", "ANA_TELEFON", "MDF"
    ],
    "FLOOR_TELECOM_BOX": ["1TK", "1tk", "TK", "KDTK", "KAT_TELEFON"],

    # Veri İletişim, LAN & Fiber Optik
    "LAN_SWITCH": [
        "YÖNETİLEBİLİR SWITCH", "YONETILEBILIR SWITCH", "INDUSTRIAL SWITCH", "SWITCH"
    ],
    "MPLS_ROUTER": [
        "MPLS İSTASYON ÜNİTESİ", "MPLS ISTASYON UNITESI", "ROUTER"
    ],
    "FIBER_PATCH_PANEL": [
        "FİBER OPTİK BAĞLANTI PANELİ", "FIBER OPTIK BAGLANTI PANELI", "ODF", "PATCH_PANEL"
    ],
    "DATA_OUTLET": ["DATA PRİZİ", "DATA PRIZI", "RJ45_DATA"],

    # Telsiz & TETRA Sistemi
    "TETRA_ANTENNA": [
        "OMNİ YÖNLENDİRİLEBİLİR ANTEN", "OMNI YONLENDIRILEBILIR ANTEN", "ANTEN", "YAGI"
    ],
    "TETRA_COUPLER": ["KUPLÖR", "KUPLOR", "COUPLER"],
    "TETRA_SPLITTER": ["SPLITTER", "BÖLÜCÜ", "BOLUCU"],
    "TETRA_REPEATER": ["rrs", "RRS", "REPEATER", "TEKRARLAYICI"],

    # Acil Anons & Seslendirme (PA/VA)
    "PAVA_SPEAKER": [
        "HOPARLÖR", "HOPARLOR", "SPEAKER", "TAVAN_HOPARLOR", "HORN_HOPARLOR", "SES_PROJEKTORU"
    ],
    "AMBIENT_NOISE_MIC": [
        "GÜRÜLTÜ_MIKROFONU", "GURULTU_MIKROFONU", "ANS_SENSOR", "ANS_MIC"
    ],

    # CCTV Kamera Sistemi
    "CCTV_DOME_CAMERA": [
        "DOME KAMERA (TAVAN VE DUVAR TİPİ CAM)_IC", "DOME KAMERA (HARİCİ TİP) _IC",
        "DOME_CAM", "SABIT_KAMERA"
    ],
    "CCTV_PTZ_CAMERA": [
        "PTZ DOME KAMERA_IC", "PTZ_CAM", "HAREKETLI_KAMERA"
    ],
    "CCTV_MONITOR": [
        "PERON BASI MONITÖRÜ", "TÖM", "TOM", "CCTV_MONITOR"
    ],

    # Saat Sistemi (Master & Slave Clock)
    "ANALOG_CLOCK": [
        "BE_ÇİFT TARAFLI ANALOG SAAT_İ", "BE_CIFT TARAFLI ANALOG SAAT", "ANALOG SAAT"
    ],
    "DIGITAL_CLOCK": [
        "TEK YÜZLÜ TALİ DİJİTAL SAAT", "TEK YUZLU TALI DIJITAL SAAT", "DIJITAL SAAT"
    ],
    "MASTER_CLOCK": ["ANA SAAT", "MASTER CLOCK", "NTP_SERVER"],

    # Kartlı Geçiş ve Kapı Güvenlik (ACS)
    "ACS_CARD_READER": ["KART OKUYUCU", "CARD_READER", "PROXIMITY"],
    "ACS_MAGNETIC_CONTACT": ["Manyetik Kontak", "MANYETIK KONTAK", "DOOR_CONTACT"],
    "ACS_MAGNETIC_LOCK": ["MANYETİK KİLİT", "MANYETIK KILIT", "MAG_LOCK"],
    "ACS_EXIT_BUTTON": ["KAPI AÇMA BUTONU", "KAPI ACMA BUTONU", "RTE_BUTTON"],

    # Yolcu Bilgilendirme Sistemi (PIS)
    "PIS_DISPLAY_DOUBLE": ["çift yüzlü pc", "cift yuzlu pc", "CIFT_TARAFLI_PIS"],
    "PIS_DISPLAY_SINGLE": ["tek yüzlü pc..", "tek yuzlu pc", "TEK_TARAFLI_PIS"],

    # TV / Uydu (Konut / Bina)
    "TV_SOCKET": ["TV", "RADYO_TV", "UYDU_PRIZI"],
    "TV_TAP_OFF": ["TAP", "BOLUCU", "SPLITTER", "TAP_OFF"],
    "FLOOR_TV_BOX": ["1tvk", "1TVK", "TVK", "KAT_TV"],
    "TV_MULTISWITCH": ["TVS", "MULTISWITCH", "SANTRAL_TV", "UYDU_SANTRAL"],

    # İnterkom / Diafon (Bina)
    "INTERCOM_MONITOR": ["ID", "DIAFON", "INTERCOM", "SUBE", "MONITOR"],
    "DOOR_BELL_BUTTON": ["Z", "ZIL", "KAPI_ZILI", "ZIL_BUTONU"],
    "DOOR_RELEASE": ["KO", "KAPI_OTO", "KAPI_OTOMATIGI", "KAPI_KILIT"],
    "DOOR_PANEL": ["KZ", "KAPI_PANELI", "ZIL_PANELI"],
    "INTERCOM_PANEL": ["IS", "INTERCOM_SANTRALI", "DIAFON_SANTRALI"],

    # 24V / UPS Besleme & Panolar
    "POWER_SUPPLY": ["KF", "GUC", "TRAFO", "24V_BESLEME", "ADAPTOR", "24V DC GÜÇ KAYNAĞI", "24V DC GUC KAYNAGI"],
    "TELECOM_PANEL": ["ENERJİ DAĞITIM PANOSU", "ENERJI DAGITIM PANOSU", "ZAYIF AKIM PANOSU", "kabin"]
}

# ── Metro Raylı Sistem Zayıf Akım & Telekomünikasyon Alt Rolleri ─────────────
METRO_WEAK_CURRENT_ROLES = {
    "AX-02": ("METRO_YANGIN_ALGILAMA", "Yangın Algılama ve İhbar Tesisatı Planı"),
    "TL-02": ("METRO_VERI_ILETISIM_LAN", "Veri İletişim, LAN & Fiber Optik Altyapı Planı"),
    "TL-03": ("METRO_TELEFON_INTERKOM", "Telefon, Acil SOS & Dahili Haberleşme Planı"),
    "TL-04": ("METRO_TETRA_TELSIZ", "Telsiz / TETRA Haberleşme & Anten Planı"),
    "TL-05": ("METRO_ACIL_ANONS_PAVA", "Acil Anons ve Sesli Tahliye (PA/VA) Planı"),
    "TL-06": ("METRO_CCTV_KAMERA", "Kapalı Devre Televizyon / CCTV Kamera Sistemi Planı"),
    "TL-07": ("METRO_SAAT_SISTEMI", "Saat Sistemi (Master Clock & Tali Saatler) Planı"),
    "TL-08": ("METRO_KARTLI_GECIS_ACS", "Kartlı Geçiş, Kapı Güvenlik (ACS) Planı"),
    "TL-09": ("METRO_SCADA_OTOMASYON", "SCADA, PLC, Otomasyon & Yangın Senaryo Planı"),
    "TL-10": ("METRO_YOLCU_BILGILENDIRME_PIS", "Yolcu Bilgilendirme Sistemi (PIS) Planı"),
    "TL-11": ("METRO_SISTEM_ODASI_RACK", "Sistem Odası (SER/CER) Rack Kabinet Yerleşim Planı")
}

# ── Standart Yönetmelik Sınırları ───────────────────────────────────────────
# Binaların Yangından Korunması Hakkında Yönetmelik (BYKHY) & TS EN 54-14
MAX_DETECTOR_COVERAGE_AREA_M2 = 50.0       # Standart optik duman dedektörü azami koruma alanı (m²)
MAX_DETECTOR_RADIUS_M = 7.5                # Duman dedektörü koruma yarıçapı (m)
MAX_CALL_POINT_DISTANCE_M = 30.0           # Kaçış yollarında butonlar arası azami mesafe (m)
MIN_ALARM_SOUND_LEVEL_DBA = 65.0           # Genel mahallerde azami arka plan + 5 dBA veya min 65 dBA
MIN_ALARM_SLEEPING_SOUND_DBA = 75.0        # Yatak başlarında minimum ses seviyesi (dBA)
MAX_ZONE_DETECTOR_COUNT = 32               # Konvansiyonel bir zonda azami dedektör sayısı

# BTK Bina İçi Elektronik Haberleşme Tesisatı Standartları
MIN_PAIRS_PER_DWELLING = 2                 # Her bağımsız bölüm için asgari hat çifti sayısı
MIN_RESERVE_CAPACITY_PCT = 20.0            # Kat ve bina dağıtım kutularında asgari yedek kapasite (%)

# TS EN 50083 SMATV Dağıtım Standartları
MIN_TV_SOCKET_LEVEL_DBUV = 60.0            # TV prizi ucu minimum sinyal seviyesi (dBµV)
MAX_TV_SOCKET_LEVEL_DBUV = 80.0            # TV prizi ucu maksimum sinyal seviyesi (dBµV)
