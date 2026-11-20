# 🏗️ CloudeCAD v4.0 — Universal CAD Audit & Repair Engine for Buildings & Metro

An engineering-grade pipeline that ingests **any** building or metro AutoCAD
project (`.dwg` / `.dxf`), separates architecture from electrical design
without relying on layer names, repairs broken wire topology, cross-checks the
drawn quantities against a rule-driven calculation engine, and delivers clean
2-layer redline drawings plus audit reports.

> **Türkçe özet için aşağı kaydırın** — detaylı Türkçe dokümantasyon için
> [README_TR.md](README_TR.md) dosyasına bakın.

## ✨ What It Does

1. **Universal CAD Reading** — lossless DXF/DWG scanning with automatic
   `ACAD` conversion caching, and dynamic unit calibration (`mm/cm/m`) derived
   from door arcs, symbol radii and text heights — even when `$INSUNITS` is wrong
2. **Shape & Topology First Separation** — a 3-layer hierarchy (pure geometry
   & morphology → AIA/ISO/BIM prefixes → strict word boundaries) splits
   architectural underlay from electrical design regardless of layer naming
   (`KATMAN_1`, `Pen87`, `CIZPEN`, ... all work)
3. **Wire Healing & Redlines** — broken/duplicate electrical cables are
   topologically repaired; audit findings are clouded into a dedicated
   `_DENETIM_BULGULARI` redline layer
4. **Embedded Table Extraction** — `OLE2FRAME` Excel tables, `ACAD_TABLE`
   objects and open-fraction formula blocks are lifted straight from vectors
5. **Quantity Audit vs Calculation Engine** — written/drawn quantities are
   compared against the internal mevzuat (regulation) & formula engine
   ([pandapower](https://www.pandapower.org), morphological analysis, `turkey_bina`
   / `ibb_metro` rule sets)
6. **4-Discipline Metro Scanning** — `TOPRAKLAMA` (earthing), `SINYAL`
   (signalling), `ZAYIF_AKIM` (low current), `KUVVETLI_AKIM` (power)
7. **Clean 2-Layer Delivery** — `1_MIMARI.dxf` (single `MIMARI` layer) and
   `2_ELEKTRIK.dwg/.dxf` (max `ELEKTRIK` + `HESAPLAR_TABLOLAR`), plus
   Excel/Word/Markdown/HTML reports and `_DENETIM_BULGULARI` findings
8. **Stray Island Elimination** — forgotten copy-pasted fragments and dead
   clones are detected (`DBSCAN` + `cKDTree`) and removed from deliverables

## 🚀 Usage

```bash
pip install -r requirements.txt

# process a project folder (01_girdi/ → 04_cikti/)
python calistir.py <girdi-dizin-yolu>

# or double-click calistir.bat (Windows + AutoCAD core console for DWG)
```

**Pipeline stages** (lossless by design):

```
01_girdi/            original DWG/DXF projects
02_mevzuat_ve_formuller/   YAML rule sets (bina + metro: topraklama,
                     kuvvetli_akim, zayif_akim)
03_hesap_motoru/     calculation engine (cad_okuma, core, rules)
04_cikti/            deliverables: separated drawings, redlines, reports
```

## 🛠 Tech Stack

Python 3 · pandapower · Shapely/SciPy (`cKDTree`, `STRtree`, DBSCAN) ·
ezdxf-style DXF parsing · AutoCAD core console (DWG) · YAML rule engine ·
openpyxl / python-docx reporting

## 📚 Documentation

Detailed Turkish documentation (architecture, separation rules, healing
algorithms, output spec): **[README_TR.md](README_TR.md)**

## 📄 License

All rights reserved. Professional engineering tool — see repository settings.

---

## 🇹🇷 Türkçe Özet

**CloudeCAD v4.0**, bina ve metro AutoCAD projelerini katman adlarına
bağlı kalmadan okuyan, **şekil & topoloji öncelikli 3 katmanlı mimari-elektrik
ayrıştırması** yapan, kopuk/mükerrer hatları onaran, yazılı/çizili hesapları
kendi mevzuat motoruyla denetleyen ve **maksimum 2 katmanlı temiz teslimat**
üreten mühendislik sistemidir.

- **Dinamik birim kalibrasyonu:** `$INSUNITS` hatalı olsa bile mm/cm/m tespiti
- **Katman bağımsız ayrıştırma:** geometri + uluslararası önekler + katı kelime
  sınırları (`BAG_HATILI`/`A_HATCH` karışması engellenir)
- **Kablo onarımı:** kopuk hatlar düzeltilir, bulgular redline katmanında bulutlanır
- **Gömülü tablolar:** OLE Excel ve ACAD_TABLE içerikleri vektörlerden çıkarılır
- **Denetim:** metraj ve hesaplar pandapower destekli formül motoruyla karşılaştırılır
- **Ölü kopya eleme:** DBSCAN + cKDTree ile unutulmuş parçalar temizlenir

**Kullanım:** `python calistir.py <girdi-dizini>` — ayrıntılı dokümantasyon:
[README_TR.md](README_TR.md)
