"""
CloudeCAD — Merkezi Yapılandırma
=================================
Tüm yollar, sabitler ve genel ayarlar buradan okunur.
"""

from pathlib import Path

# ── Proje Kök Dizini ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── ODA File Converter ────────────────────────────────────────────────────────
# ODA File Converter varsayılan kurulum yolu (Windows 64-bit)
ODA_CONVERTER_PATHS = [
    Path(r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"),
    Path(r"C:\Program Files (x86)\ODA\ODAFileConverter\ODAFileConverter.exe"),
    Path(r"C:\ODAFileConverter\ODAFileConverter.exe"),
]

# ── DXF Parse Ayarları ────────────────────────────────────────────────────────
# Minimum anlamlı çizgi uzunluğu (mm cinsinden, çizimdeki birim)
MIN_LINE_LENGTH_MM = 10.0

# ── Geometri Ayarları ─────────────────────────────────────────────────────────
# Fuzzy snap toleransı: Bu mesafeden yakın hat uçları birleştirilir
SNAP_TOLERANCE_MM = 50.0        # 5 cm = 50 mm (DXF mm biriminde)

# Concave hull ayarları (bina sınır poligonu)
CONCAVE_HULL_RATIO = 0.3        # 0=convex hull, 1=mümkün en iç

# ── Topraklama Hesap Sabitleri ────────────────────────────────────────────────
# Varsayılan zemin özgül direnci (kullanıcı giremezse)
DEFAULT_RHO_OHM_M = 100.0       # Ω·m (tipik kuru toprak)

# Kazık boyutları (kullanıcı override edebilir)
DEFAULT_STAKE_LENGTH_M = 1.5    # metre
DEFAULT_STAKE_DIAMETER_MM = 16  # mm (galvaniz çelik çubuk)

# Şerit boyutları (yaygın kullanım)
DEFAULT_STRIP_WIDTH_MM = 30     # mm
DEFAULT_STRIP_THICKNESS_MM = 3  # mm

# ── Loglama ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"              # DEBUG | INFO | WARNING | ERROR
LOG_FILE = OUTPUT_DIR / "cloudecad.log"
