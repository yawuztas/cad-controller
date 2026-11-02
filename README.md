# CloudeCAD (CAD Controller) — v3.0

> **End-to-End Electrical CAD / BIM Audit, Auto-Healer, Review Station & Delivery Pipeline**

CloudeCAD is an automated CAD auditing and healing engine designed for complex electrical engineering projects (including metro stations, commercial facilities, and residential buildings). It parses mixed CAD/BIM exports, identifies architectural vs. electrical infrastructure, heals broken wire topologies, verifies standards against Turkish BYKHY & IEC/İBB Metro rules, and provides an engineer review station before compiling signed DWG delivery packages.

---

## ⚡ Key Capabilities

1. **CAD Safety Shield (`cad_safety.py`):**
   - Read-only XREF protection and container isolation.
   - `BLOCK` definition vs. `INSERT` reference separation (never mutates block definitions directly).
   - Dynamic `$INSUNITS` and drawing extents scale resolution (mm / cm / m).
   - Surgical `MTEXT` formatting tag preservation.

2. **Layer & Block Doctor (`layer_doctor.py`):**
   - Automatically triages proven architectural entities to locked, background layers (`A-MIMARI-ALTYAPI`, Color 8).
   - Re-organizes electrical routes and symbols into standard `E-*` layer specs with lineweight & plotstyle preservation.

3. **Topological Wire Healer (`wire_healer.py`):**
   - `STRtree`-accelerated spatial query index.
   - 4-condition collinear stitcher with bridge-angle checking (strictly prevents merging parallel side-by-side circuits).
   - Duplicate route cleaner with circuit context protection.
   - Graduated symbol snapper (`<= 5 cm` auto, `> 5 cm` requires approval).

4. **Electrical Auto-Optimizer (`electrical_optimizer.py`):**
   - Pano (Panel) phase balancing via greedy LPT optimization (e.g., reduces imbalance from %141 to <%5).
   - AS-BUILT vs. DESIGN governance mode: generates field instruction recipes (`SAHA_RECETELERI.md`) for as-built projects without mutating physical drawings unexpectedly.
   - BYKHY fire pump safety rules (FE180 cable verification, RCD/KAK exclusion guard).

5. **Review Station & Composer (`review_station.py` & `compose_delivery.py`):**
   - FastAPI-powered web UI (`http://127.0.0.1:8765`) for instant engineer triage (<20 ms response, batch approval, one-click undo).
   - Two-tier delivery compilation: `accoreconsole.exe` native compiler with automatic fallback to AutoCAD COM Automation (`ComDwgApplier`) to survive Revit-exported spline debris crashes.
   - Cryptographically signed audit trail (`RESPONSIBILITE_DEFTERI.json`, SHA-256 signatures).

---

## 🚀 Quick Start

### 1. Installation
```powershell
# Create & activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Run Test Suite
```powershell
pytest tests/test_reference_projects.py -v
```

### 3. Launch Review Station
```powershell
python tools/review_station.py --port 8765
# Or double click onay_istasyonu.bat
```

---

## 📂 Architecture

```
├── cloudecadprogramı/        # Core Engineering Engines
│   ├── core/cad/             # Readers, Triage, Safety Shield
│   ├── core/healer/          # LayerDoctor, WireHealer, ElectricalOptimizer, TableGenerator
│   ├── core/rules/           # RuleEngine (ibb_metro, turkey_bina)
│   └── common/               # DXF converters & COM automation (com_dwgs.py)
├── tools/                    # Operational Pipeline
│   ├── field_run_healer.py   # Full pipeline batch runner
│   ├── review_station.py     # FastAPI engineer review web UI
│   ├── compose_delivery.py   # DXF -> DWG 2018 + package composer
│   └── generate_system_guide.py # Documentation & SSOT builder
├── tests/                    # Reference verification test suite (13/13 passing)
└── lispkodlar/               # Auxiliary AutoCAD LISP utilities
```

---

## 📜 Documentation
- Complete System Guide: [`CLOUDECAD_SISTEM_REHBERI.md`](CLOUDECAD_SISTEM_REHBERI.md) / `CLOUDECAD_SISTEM_REHBERI.docx`
- Status Report & Changelog: [`DURUM_RAPORU_2026-11-02.md`](DURUM_RAPORU_2026-11-02.md)
