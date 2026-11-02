"""
CloudeCAD — Yükleme Cetveli ve Kuvvetli Akım Modülü Yapılandırması
==================================================================
Tüm yollar, toleranslar, varsayılan katsayılar ve ayarlar.
"""

from pathlib import Path

# ── Dizin Yapısı ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# Proje Kök Dizini (D:\autocad projesi)
PROJECT_ROOT = BASE_DIR.parent.parent.resolve()
REPORTS_DIR = PROJECT_ROOT / "raporlar"

# ── AutoCAD Core Console / ODA Yolları ────────────────────────────────────────
ACCORECONSOLE_PATHS = [
    Path(r"C:\Program Files\Autodesk\AutoCAD 2027\accoreconsole.exe"),
    Path(r"C:\Program Files\Autodesk\AutoCAD 2026\accoreconsole.exe"),
    Path(r"C:\Program Files\Autodesk\AutoCAD 2025\accoreconsole.exe"),
    Path(r"C:\Program Files\Autodesk\AutoCAD 2024\accoreconsole.exe"),
    Path(r"C:\Program Files\Autodesk\AutoCAD 2023\accoreconsole.exe"),
    Path(r"C:\Program Files\Autodesk\AutoCAD 2022\accoreconsole.exe"),
    Path(r"C:\Program Files\Autodesk\AutoCAD 2021\accoreconsole.exe"),
]

ODA_CONVERTER_PATHS = [
    Path(r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"),
    Path(r"C:\Program Files (x86)\ODA\ODAFileConverter\ODAFileConverter.exe"),
    Path(r"C:\ODAFileConverter\ODAFileConverter.exe"),
]

# ── CAD Parse & Kümeleme Ayarları ─────────────────────────────────────────────
# Pano metinlerini gruplama yarıçapı (DXF biriminde)
PANEL_CLUSTER_DX = 350.0   # Yatayda arama toleransı
PANEL_CLUSTER_DY = 80.0    # Düşeyde arama toleransı

# ── Elektriksel Varsayılanlar (Yönetmelik / TEDAŞ) ─────────────────────────────
DEFAULT_VOLTAGE_3PHASE = 380.0  # V (veya TS EN 50160: 400V)
DEFAULT_VOLTAGE_1PHASE = 220.0  # V (veya TS EN 50160: 230V)
DEFAULT_POWER_FACTOR_POWER = 0.80      # Güç / Motor / Genel yük için cosφ
DEFAULT_POWER_FACTOR_LIGHTING = 0.90   # Modern LED aydınlatma için cosφ

# Gerilim düşümü sınırları (%)
MAX_VDROP_LIGHTING_PCT = 1.5
MAX_VDROP_POWER_PCT = 3.0
MAX_VDROP_MAIN_FEEDER_PCT = 3.5

# Faz dengesizliği azami kabul edilebilir oran (%)
MAX_PHASE_UNBALANCE_PCT = 20.0

# ── Loglama ───────────────────────────────────────────────────────────────────
LOG_FILE = OUTPUT_DIR / "yukleme_cetveli.log"
