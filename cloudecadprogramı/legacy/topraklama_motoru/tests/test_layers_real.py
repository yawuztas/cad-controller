"""Layer tespiti dogrulama — gercek 62 katmanli DXF ile test"""
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
from standards.layer_profiles import is_grounding_layer, is_structural_layer, classify_layer

# 5katli 10 daireli.dxf'teki TUM 62 katman
real_layers = [
    "0", "00-04", "00-06", "00-24V", "00-ANHTR", "00-AYD",
    "00-CERCEVE", "00-ELKYAZ", "00-INTERCOM", "00-KOL_NO",
    "00-LINYE_NO", "00-PRZ", "00-TABLO", "00-TEL", "00-TOPRAK",
    "00-TV", "00-YAZI", "COLUMN4", "DENİZLİK", "DOG", "DOGRAMA",
    "DUVAR İÇİ", "HUANG", "K-P", "KADASTRO", "KAPIPENCERE",
    "KOLONLAR_5", "PARSEL_NO", "PENC3", "SIVA", "TEFRIS", "TEFRIS1",
    "TEFRİS", "TEXT", "TF2", "YAZI", "ahsap kaplama", "aks",
    "d u v a r", "dograma-kesit", "duvar", "g ö r ü n ü ş - ince",
    "hidden", "kapen.", "kapı", "kapı-pencere", "kolon",
    "ÖLÇÜ İÇ", "ölcü", "ölçü", "pencere", "sıva", "tarama",
    "tef. 2", "tef. 3", "tefriş", "tefrişş", "yazı",
]

# BEKLENEN topraklama katmanlari: SADECE 00-TOPRAK
expected_grounding = {"00-TOPRAK"}

# BEKLENEN yapisal katmanlar
expected_structural = {"kolon", "KOLONLAR_5", "COLUMN4"}

print("=" * 65)
print("  KATMAN TESPITI DOGRULAMA TESTI")
print("=" * 65)

errors = []

print("\n--- TOPRAKLAMA TESPITI ---")
for layer in real_layers:
    result = is_grounding_layer(layer)
    expected = layer in expected_grounding
    status = "OK" if result == expected else "HATA"
    if status == "HATA":
        errors.append(f"  TOPRAK: {layer!r} -> {result} (beklenen: {expected})")
    if result:
        mark = "DOGRU" if expected else "YANLIS POZITIF!"
        print(f"  [{'OK' if expected else 'XX'}] {layer:25} -> topraklama={result}  {mark}")

print(f"\n  Topraklama tespit edilen: {sum(1 for l in real_layers if is_grounding_layer(l))}")
print(f"  Beklenen: {len(expected_grounding)}")

print("\n--- YAPISAL TESPIT ---")
for layer in real_layers:
    result = is_structural_layer(layer)
    if result:
        expected = layer in expected_structural
        mark = "DOGRU" if expected else "KONTROL"
        print(f"  [{'OK' if expected else '??'}] {layer:25} -> yapisal={result}  {mark}")

print(f"\n  Yapisal tespit edilen: {sum(1 for l in real_layers if is_structural_layer(l))}")

print("\n--- SINIFLANDIRMA OZETI ---")
cats = {}
for layer in real_layers:
    cat = classify_layer(layer)
    cats.setdefault(cat, []).append(layer)

for cat, layers in sorted(cats.items()):
    print(f"  {cat:15}: {len(layers)} katman")
    for l in layers[:8]:
        print(f"    - {l}")
    if len(layers) > 8:
        print(f"    ... ve {len(layers)-8} daha")

print("\n" + "=" * 65)
if errors:
    print(f"  HATALAR ({len(errors)}):")
    for e in errors:
        print(e)
    print("  SONUC: BASARISIZ")
else:
    print("  SONUC: TUM TESTLER GECTI!")
print("=" * 65)
