"""
Test DXF Oluşturucu
====================
Gerçekçi bir topraklama sistemi örnek DXF dosyası oluşturur.
Bu dosya CloudeCAD'in uçtan uca testi için kullanılır.
"""
import sys, ezdxf
from pathlib import Path

out = Path(r"D:\autocad projesi\cloudecadprogramı\outputs\test_topraklama.dxf")

doc = ezdxf.new("R2010")
doc.header["$INSUNITS"] = 4   # 4 = mm (milimetre)
msp = doc.modelspace()

# ── Katman tanımları ──────────────────────────────────────────
doc.layers.add("00-TOPRAK",       color=3)   # Yeşil: Topraklama şerit
doc.layers.add("00-TOPRAK-KAZIK", color=5)   # Mavi:  Topraklama kazık
doc.layers.add("KOLON",           color=2)   # Sarı:  Yapısal kolon

# ── Boyutlar ─────────────────────────────────────────────────
# Birim: mm  |  Bina: 20m x 30m = 20000mm x 30000mm
# Topraklama şeridi: bina dış çevresinde + iç ızgara

offset = 500  # 50cm içeri çekilmiş

# ── Çevre topraklama şeridi (kapalı döngü) ───────────────────
cevre = [
    (offset, offset), (19500, offset),
    (19500, 29500), (offset, 29500)
]
for i in range(len(cevre)):
    msp.add_line(cevre[i], cevre[(i+1) % len(cevre)],
                 dxfattribs={"layer": "00-TOPRAK"})

# ── İç bağlantılar (göz oluşturmak için) ─────────────────────
# Yatay: y = 8000, 16000, 24000 → Göz boyutu ≈ 8m × 9.7m (UYGUN < 20m)
for y in [8000, 16000, 24000]:
    msp.add_line((offset, y), (19500, y), dxfattribs={"layer": "00-TOPRAK"})

# Dikey: x = 6500, 13000 → Göz boyutu ≈ 6.5m × 8m (UYGUN)
for x in [6500, 13000]:
    msp.add_line((x, offset), (x, 29500), dxfattribs={"layer": "00-TOPRAK"})

# ── Topraklama kazıkları (CIRCLE) ─────────────────────────────
kazik_pts = [
    (offset, offset), (19500, offset),
    (offset, 29500),  (19500, 29500),
    (6500, 8000),     (13000, 8000),
]
for pt in kazik_pts:
    msp.add_circle(pt, radius=200, dxfattribs={"layer": "00-TOPRAK-KAZIK"})

# ── Topraklama hesap metinleri ────────────────────────────────
# (Tier 2 bu metinleri okuyacak)
texts = [
    "TOPRAKLAMA HESABI",
    "rho = 100 Ohm/m KABUL EDILMISTIR",
    "L : CEVRE ILETKEN UZUNLUGU = 90 m",
    "d : ILETKEN CAPI = 0.008 m",
    "h : GOMULME DERINLIGI = 2.0 m",
    "n : KAZIK ADEDI = 6",
    "L : KAZIK UZUNLUGU = 1.5 m",
    "d : KAZIK CAPI = 0.02 m",
    "Ri : CEVRE TOPRAKLAMASI = 2.324 Ohm",
    "Re : ESDE GER TOPRAKLAMA DIRENCI = 0.846 Ohm",
]
for i, txt in enumerate(texts):
    msp.add_text(
        txt,
        height=250,
        dxfattribs={"layer": "00-TOPRAK", "insert": (500, -1500 - i * 800)}
    )

# ── Yapısal sistem (bina sınırı için) ────────────────────────
bina = [(0, 0), (20000, 0), (20000, 30000), (0, 30000)]
for i in range(len(bina)):
    msp.add_line(bina[i], bina[(i+1) % len(bina)],
                 dxfattribs={"layer": "KOLON"})
for pt in bina:
    msp.add_circle(pt, radius=500, dxfattribs={"layer": "KOLON"})

doc.saveas(str(out))
print(f"Test DXF oluşturuldu: {out}")
print(f"Şimdi test etmek için:")
print(f'  python main.py "{out}"')
