"""
CloudeCAD — Katman Isim Profilleri (v2)
==========================================
DXF dosyalarindaki katman isimlerini islevsel kategorilere esler.
Turkce, Ingilizce ve karisik isimlendirme stillerini kapsar.

v2 DEGISIKLIKLER:
- PE/PEN kaliplari tam kelime eslesmesine cevrildi (PENCERE false positive duzeltildi)
- Negatif liste eklendi (KAPI, PENCERE, PENC iceren katmanlar hariç)
- classify_layer oncelik sirasi: once negatif kontrol, sonra pozitif
- Gercek proje verileriyle dogrulanmis (62 katmanli 5katli 10 daireli.dxf)
"""

import re
from typing import Optional


# ═══════════════════════════════════════════════════════════════
#  TOPRAKLAMA KATMANI KALIPLARI
# ═══════════════════════════════════════════════════════════════
# Her kalip (pattern, mode) ikilisi:
#   mode='contains'  → substring eslesmesi (eski davranis)
#   mode='word'      → kelime sinirli esleme (\b...\b)
#   mode='exact'     → tam eslesme
#   mode='regex'     → regex

GROUNDING_RULES: list[tuple[str, str]] = [
    # --- Turkce (guvenli substring) ---
    ("TOPRAK",           "contains"),
    ("TOPRAKLAMA",       "contains"),
    ("TEMEL-TOPRAK",     "contains"),
    ("TEMEL_TOPRAK",     "contains"),
    ("TEMEL TOPRAK",     "contains"),
    # --- Elektrik prefix'li ---
    ("00-TOPRAK",        "contains"),
    ("EL-TOPRAK",        "contains"),
    ("ELK-TOPRAK",       "contains"),
    ("T-TOPRAK",         "contains"),
    ("T.TOPRAK",         "contains"),
    # --- Ingilizce (guvenli substring) ---
    ("EARTHING",         "contains"),
    ("GROUNDING",        "contains"),
    ("GROUND",           "word"),      # "GROUND" kelime olarak (PLAYGROUND hariç)
    ("EARTH",            "word"),      # "EARTH" kelime olarak
    ("GND",              "word"),      # "GND" kelime olarak
    # --- TEHLIKELI kisaltmalar: TAM KELIME eslesmesi ---
    ("PE",               "exact"),     # Sadece katman adi tam "PE" ise
    ("PEN",              "exact"),     # Sadece katman adi tam "PEN" ise
    ("PE-BARA",          "exact"),
    ("PE_BARA",          "exact"),
    # --- Tam kelime eslesmesi gerekenler ---
    ("T-HAT",            "exact"),
    ("T.HAT",            "exact"),
    ("TOPRAKLAMA-HATTI", "contains"),
    ("TOPRAKLAMA_HATTI", "contains"),
    # --- Kazik / cubuk ---
    ("KAZIK",            "contains"),
    ("TOPRAKLAMA-KAZIK", "contains"),
    ("TOPRAK-CUBUK",     "contains"),
    ("TOPRAK-ROD",       "contains"),
    # --- Ek / buat ---
    ("TOPRAKLAMA-BUAT",  "contains"),
    ("TEST-BUAT",        "contains"),
    ("TEST BUAT",        "contains"),
    ("TOPRAK-EK",        "contains"),
    # --- Bara ---
    ("TOPRAKLAMA-BARA",  "contains"),
    ("ESBP",             "exact"),
    # --- Regex ---
    (r"^EL[\-_.].*TOPRAK", "regex"),
    (r"^00[\-_.].*TOPRAK", "regex"),
]


# ═══════════════════════════════════════════════════════════════
#  NEGATIF LISTE (topraklama OLMAYAN ama false positive veren)
# ═══════════════════════════════════════════════════════════════
# Bu kelimelerden herhangi biri katman adinda geciyorsa,
# katman KESINLIKLE topraklama degildir.

GROUNDING_NEGATIVE: list[str] = [
    "PENCERE", "PENC",
    "KAPI", "DOOR", "WINDOW",
    "KAPIPENCERE",
    "DOGRAMA",
    "MOBILYA", "FURNITURE",
    "TEFRIS",
    "TAVAN", "CEILING",
    "MERDIVEN", "STAIR",
]


# ═══════════════════════════════════════════════════════════════
#  MIMARI / YAPI KATMANI KALIPLARI (maskeleme icin)
# ═══════════════════════════════════════════════════════════════

ARCHITECTURAL_PATTERNS: list[str] = [
    # Duvarlar
    "DUVAR", "WALL", "DUV",
    # Doseme
    "DOSEME", "DOSEME", "SLAB", "FLOOR",
    # Tavan
    "TAVAN", "CEILING",
    # Kapi / pencere
    "KAPI", "DOOR", "PENCERE", "WINDOW", "PENC",
    "DOGRAMA",
    # Merdivenler
    "MERDIVEN", "STAIR",
    # Mobilya / tefris
    "MOBILYA", "FURNITURE", "TEFRIS",
    # Tarama / dolgu
    "HATCH", "DOLGU", "TARAMA",
    # Olcu / yazi
    "DIM", "OLCU", "TEXT", "YAZI",
    # Aks
    "AKS", "AXIS", "GRID",
    # Kaldirilan / kullanilmayan
    "DEFPOINTS",
]


# ═══════════════════════════════════════════════════════════════
#  KOLON / PERDE KATMANLARI (bina siniri tespiti icin)
# ═══════════════════════════════════════════════════════════════

STRUCTURAL_COLUMN_PATTERNS: list[str] = [
    "KOLON", "COLUMN", "COL",
    "PERDE", "SHEARWALL", "SHEAR-WALL",
    "TEMEL", "FOUNDATION", "FOOTING",
    "KIRIS", "BEAM",
    "YAPISAL", "STRUCTURAL", "BEARING",
    "BETONARME", "BETON",
    "DUVAR", "WALL",
    "MIM-KOLON", "MIM-PERDE",
    "A-KOLON", "A-PERDE",
    "KOLONLAR",
]

# ═══════════════════════════════════════════════════════════════
#  TOPRAKLAMA VE TEFRİŞ / AYDINLATMA BLOK KALIPLARI
# ═══════════════════════════════════════════════════════════════

GROUNDING_BLOCK_PATTERNS: list[str] = [
    "1TP", "TP", "1EKK", "EKK", "ETB", "1KAD", "KAD",
    "ROD", "CUBUK", "KAZIK", "TOPRAK", "GROUND", "EARTH",
    "BARA", "ESBP", "KLEMENS"
]

NON_GROUNDING_BLOCK_PATTERNS: list[str] = [
    "136", "CE", "BB", "BED", "CHAIR", "MASA", "KOLTUK", "LAVABO", "EVIYE",
    "LAMBA", "AYD", "ARMATUR", "PRIZ", "ANAHTAR", "INTERCOM",
    "TELEFON", "TV", "DATA"
]

def is_grounding_block(block_name: str) -> bool:
    """Blok adı topraklama elemanına (kazık, klemens, bara) mı ait?"""
    name = block_name.upper().strip()
    return any(p in name for p in GROUNDING_BLOCK_PATTERNS)

def is_non_grounding_block(block_name: str) -> bool:
    """Blok adı kesinlikle topraklama OLMAYAN mimari/aydınlatma elemanı mı?"""
    name = block_name.upper().strip()
    return any(name == p or name.startswith(p + "_") or name.startswith(p + "-") or name.endswith("_" + p) for p in NON_GROUNDING_BLOCK_PATTERNS)


# ═══════════════════════════════════════════════════════════════
#  ESLESTIRME FONKSIYONLARI
# ═══════════════════════════════════════════════════════════════

def _matches_simple(layer_name: str, patterns: list[str]) -> bool:
    """Basit substring eslesmesi (negatif liste ve mimari icin)."""
    upper = layer_name.upper().strip()
    for pattern in patterns:
        if pattern.upper() in upper:
            return True
    return False


def _is_negative_match(layer_name: str) -> bool:
    """Bu katman negatif listedeki kelimelerden birini iceriyor mu?"""
    upper = layer_name.upper().strip()
    for neg in GROUNDING_NEGATIVE:
        if neg.upper() in upper:
            return True
    return False


def is_grounding_layer(layer_name: str) -> bool:
    """
    Bu katman bir topraklama katmani mi?

    Mantik:
    1. Once negatif listeyi kontrol et — PENCERE, KAPI vs. iceriyorsa HAYIR
    2. Sonra pozitif kurallara bak — eslesen varsa EVET
    """
    upper = layer_name.upper().strip()

    # Adim 1: Negatif kontrol
    if _is_negative_match(layer_name):
        return False

    # Adim 2: Pozitif kurallar
    for pattern, mode in GROUNDING_RULES:
        pat_upper = pattern.upper()

        if mode == "contains":
            if pat_upper in upper:
                return True

        elif mode == "word":
            # Kelime sinirli esleme: \bPATTERN\b
            if re.search(r'\b' + re.escape(pat_upper) + r'\b', upper):
                return True

        elif mode == "exact":
            # Tam eslesme (ama - _ . prefix/suffix olabilir)
            # "PE" → "PE", "00-PE", "EL_PE" uyar ama "PENCERE" uymaz
            if re.search(r'(?:^|[\-_.\s])' + re.escape(pat_upper) + r'(?:$|[\-_.\s])', upper):
                return True
            # Veya birebir tam eslesme
            if upper == pat_upper:
                return True

        elif mode == "regex":
            if re.search(pattern, upper, re.IGNORECASE):
                return True

    return False


def is_architectural_layer(layer_name: str) -> bool:
    """Bu katman mimari detay (maskelenmesi gereken) mi?"""
    return _matches_simple(layer_name, ARCHITECTURAL_PATTERNS)


def is_structural_layer(layer_name: str) -> bool:
    """Bu katman bina tasiyici sistem (sinir tespitinde kullanilan) mi?"""
    return _matches_simple(layer_name, STRUCTURAL_COLUMN_PATTERNS)


def classify_layer(layer_name: str) -> str:
    """
    Katmani kategorize et.
    Doner: 'grounding' | 'structural' | 'architectural' | 'unknown'
    """
    if is_grounding_layer(layer_name):
        return "grounding"
    if is_structural_layer(layer_name):
        return "structural"
    if is_architectural_layer(layer_name):
        return "architectural"
    return "unknown"


def get_layer_display_name(layer_name: str) -> str:
    """Muhendis icin okunabilir kategori adi."""
    category = classify_layer(layer_name)
    labels = {
        "grounding":     "Topraklama",
        "structural":    "Tasiyici Sistem",
        "architectural": "Mimari Detay",
        "unknown":       "Siniflandirilmamis",
    }
    return labels.get(category, "Bilinmiyor")
