"""
CloudeCAD — TS HD 60364-5-54 Standart Sabitleri
=================================================
IEC 60364 / TS HD 60364-5-54 (Topraklama düzenlemeleri ve
koruyucu iletkenler) standartlarından alınan eşik değerleri.

Referanslar:
  - TS HD 60364-5-54:2011 (Alçak gerilim tesisatı)
  - IEC 62305 (Yıldırımdan korunma)
  - IEEE Std 80-2013 (AC alt istasyonu topraklaması)
  - EMO Teknik Şartnamesi
"""


# ═══════════════════════════════════════════════════════════════
#  TOPRAKLAMA DİRENCI EŞİKLERİ
# ═══════════════════════════════════════════════════════════════

# TT sistemi (bağımsız topraklama) — bina tesisatı
RT_MAX_TT_OHM = 5.0

# TN sistemi (ortak toprak) — YG/AG indirici merkezler
RT_MAX_TN_OHM = 1.0

# Yıldırımdan korunma (IEC 62305)
RT_MAX_LIGHTNING_OHM = 10.0

# Özel tıbbi tesisler (IEC 60364-7-710)
RT_MAX_MEDICAL_OHM = 0.2

# Patlayıcı ortamlar (ATEX)
RT_MAX_ATEX_OHM = 0.1


# ═══════════════════════════════════════════════════════════════
#  ŞEBEKEGÖZELERİ (MESH) BOYUT SINIRI
# ═══════════════════════════════════════════════════════════════

# TS HD 60364-5-54 A.531.3 — Eşpotansiyel topraklama şebekesi
# Maksimum göz boyutu: 20 m × 20 m
MESH_MAX_SIZE_M = 20.0          # metre

# Tolerans: %10 aşma kabul edilir (çizim hatası)
MESH_TOLERANCE_RATIO = 0.10


# ═══════════════════════════════════════════════════════════════
#  İLETKEN KESİT SINIRLAMALARI
# ═══════════════════════════════════════════════════════════════

# Topraklama iletkeni minimum kesit — bakır (mm²)
STRIP_MIN_CROSS_SECTION_CU_MM2 = 16

# Topraklama iletkeni minimum kesit — çelik (mm²)
STRIP_MIN_CROSS_SECTION_STEEL_MM2 = 50

# Galvaniz çelik şerit minimum en × kalınlık (mm)
GALV_STRIP_MIN_WIDTH_MM = 25
GALV_STRIP_MIN_THICKNESS_MM = 3

# Bakır şerit minimum en × kalınlık (mm)
CU_STRIP_MIN_WIDTH_MM = 25
CU_STRIP_MIN_THICKNESS_MM = 2

# Topraklama çubuğu minimum çap (mm)
STAKE_MIN_DIAMETER_STEEL_MM = 16
STAKE_MIN_DIAMETER_CU_MM = 15

# ═══════════════════════════════════════════════════════════════
#  KAZIK BOYUTLARI (yaygın kullanım değerleri)
# ═══════════════════════════════════════════════════════════════

# Betonarme temel topraklaması için minimum donatı çapı (mm)
REBAR_MIN_DIAMETER_MM = 10

# Minimum kazık uzunluğu (m)
STAKE_MIN_LENGTH_M = 1.0

# ═══════════════════════════════════════════════════════════════
#  BAĞLANTI VERİMİ FAKTÖRÜ (η — paralel kazıklar için)
# ═══════════════════════════════════════════════════════════════
# Kazıklar birbirine çok yakın yerleştirilirse verimleri düşer.
# IEEE 80 tablosundan basitleştirilmiş yaklaşım:

ETA_TABLE = {
    1:  1.00,
    2:  0.85,
    3:  0.76,
    4:  0.71,
    5:  0.67,
    6:  0.65,
    8:  0.60,
    10: 0.56,
    12: 0.53,
    16: 0.49,
    20: 0.45,
}

def get_eta(n_stakes: int) -> float:
    """n kazık için bağlantı verimi faktörü η'yı döndürür."""
    if n_stakes <= 0:
        return 1.0
    if n_stakes in ETA_TABLE:
        return ETA_TABLE[n_stakes]
    # Tabloda yoksa lineer interpolasyon
    keys = sorted(ETA_TABLE.keys())
    for i in range(len(keys) - 1):
        if keys[i] <= n_stakes <= keys[i + 1]:
            k0, k1 = keys[i], keys[i + 1]
            eta0, eta1 = ETA_TABLE[k0], ETA_TABLE[k1]
            t = (n_stakes - k0) / (k1 - k0)
            return round(eta0 + t * (eta1 - eta0), 4)
    return ETA_TABLE[max(keys)]  # Tablodan büyükse en küçük η


# ═══════════════════════════════════════════════════════════════
#  DENETİM SONUÇ KODLARI
# ═══════════════════════════════════════════════════════════════

class CheckResult:
    PASS    = "UYGUN"
    FAIL    = "AŞILIYOR"
    WARNING = "UYARI"
    UNKNOWN = "BELİRSİZ"
