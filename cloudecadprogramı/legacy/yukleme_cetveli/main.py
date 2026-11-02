"""
CloudeCAD — Yükleme Cetveli ve Kuvvetli Akım Denetim Motoru
===========================================================
Bağımsız Giriş Noktası (Standalone Entry Point)

Kullanım:
    python main.py "proje.dwg"
    python main.py "proje.dxf" --no-open
"""

import sys
import os
import webbrowser
from pathlib import Path

# Modül yollarını sys.path'e ekle
_THIS_DIR = Path(__file__).parent.resolve()
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# Windows konsolunda UTF-8 karakter uyumluluğu
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from config import OUTPUT_DIR
from core.tier0_converter import ensure_dxf
from core.tier1_triangulator import PowerDataTriangulator
from core.tier2_typology_detector import TypologyDetector
from core.tier3_calculator import EngineeringCalculator
from core.tier4_reporter import PowerReporter


def run_power_audit(file_path: str, open_browser: bool = True):
    """Kuvvetli akım ve yükleme cetveli analiz ardışık düzeni."""
    raw_path = Path(file_path).resolve()
    if not raw_path.exists():
        print(f"[HATA] Dosya bulunamadı: {raw_path}")
        sys.exit(1)

    print("=" * 72)
    print("  CloudeCAD — Kuvvetli Akım & Yükleme Cetveli Denetim Motoru")
    print(f"  Hedef Dosya: {raw_path.name}")
    print("=" * 72)

    # 1. Aşama: DXF Dönüştürme (Gerekirse)
    print("\n[Tier 0] DWG/DXF Kontrolü...")
    dxf_path = ensure_dxf(str(raw_path))
    print(f"  ✓ DXF Hazır: {Path(dxf_path).name}")

    # 2. Aşama: 3 Kanallı Veri Çekme ve Çapraz Doğrulama (Triangulation)
    print("\n[Tier 1] 3 Kanallı Veri Çekme ve Çapraz Doğrulama (CAD, OLE, Excel)...")
    triangulator = PowerDataTriangulator(dxf_path)
    proj_data = triangulator.extract_and_verify()

    matches = len([d for d in proj_data.discrepancies if d.status == "MATCH"])
    mismatches = len([d for d in proj_data.discrepancies if d.status == "MISMATCH"])
    print(f"  ✓ {len(proj_data.sub_panels)} adet pano tespit edildi.")
    print(f"  ✓ {proj_data.ole_count} adet gömülü OLE tablosu tarandı.")
    print(f"  ✓ Çapraz Doğrulama: {matches} parametre tam uyumlu, {mismatches} uyarı/fark.")

    # 3. Aşama: Tipoloji Tespiti
    print("\n[Tier 2] Proje Tipolojisi Algılanıyor...")
    typology, conf, reason = TypologyDetector.detect(proj_data)
    print(f"  ✓ Tipoloji: {typology.value} (Güven: %{conf*100:.0f})")
    print(f"  ✓ Gerekçe : {reason}")

    # 4. Aşama: Deterministik Hesap ve Mühendislik Denetimi
    print("\n[Tier 3] Deterministik Hesap ve Standart Denetimi...")
    calculator = EngineeringCalculator(proj_data, typology, reason)
    audit_report = calculator.compute_and_audit()

    print(f"  ✓ Toplam Kurulu Güç : {audit_report.main_installed_power_w:,.0f} W")
    print(f"  ✓ Toplam Talep Gücü  : {audit_report.main_demand_power_w:,.0f} W (ks={audit_report.main_diversity_factor:.2f})")
    print(f"  ✓ Ana Dağıtım Akımı : {audit_report.main_feeder_current_a:.1f} A")
    print(f"  ✓ Ana Hat Gerilim D.: %{audit_report.main_feeder_vdrop_pct:.2f} (Sınır: %3.5)")
    at_pb = audit_report.phase_balance_results.get("AT")
    at_sc = audit_report.short_circuit_results.get("AT")
    ot_sc = audit_report.short_circuit_results.get("O-T")
    if at_pb:
        print(f"  ✓ Faz Yük Dengesi   : Asimetri %{at_pb.unbalance_pct:.1f}, Inötr={at_pb.current_neutral_a:.1f} A ({at_pb.status})")
    if at_sc:
        print(f"  ✓ AT Kısa Devre(Ik3): {at_sc.ik3_max_ka:.2f} kA | TMŞ Icn={at_sc.breaker_icn_ka:.0f} kA ({at_sc.breaking_capacity_status})")
    if ot_sc and ot_sc.ik3_max_ka > 6.0:
        print(f"  ⚠ O-T Kısa Devre    : Ik3={ot_sc.ik3_max_ka:.2f} kA > 6 kA (10 kA MCB Zorunlu)")
    print(f"  ✓ Genel Karar       : {audit_report.overall_verdict} (Skor: %{audit_report.score_pct:.0f})")

    # 5. Aşama: Raporlama ve Excel Yükleme Cetveli Üretimi
    print("\n[Tier 4] Raporlar ve Excel Yükleme Cetveli Üretiliyor...")
    reporter = PowerReporter(proj_data, audit_report, OUTPUT_DIR / proj_data.project_name)
    out_files = reporter.generate_all()

    print(f"  ✓ Excel Yükleme Cetveli : {out_files['excel']}")
    if "docx" in out_files:
        print(f"  ✓ Word Mühendislik Rap. : {out_files['docx']}")
    print(f"  ✓ HTML Denetim Raporu  : {out_files['html']}")
    print(f"  ✓ JSON Özeti           : {out_files['json']}")
    if hasattr(reporter, 'bom') and reporter.bom:
        b = reporter.bom
        src_label = "AutoCAD Electrical default_cat.mdb" if b.db_connected else "Katalog Normu"
        print(f"  ✓ ACADE Keşif Özeti    : {len(b.summary_items)} kalem malzeme eşleşti ({b.total_mcb_count} MCB, {b.total_mccb_count} TMŞ, {b.total_rcd_count} KAKR) [{src_label}]")



    print("\n" + "=" * 72)
    print("  İŞLEM BAŞARIYLA TAMAMLANDI!")
    print("=" * 72)

    if open_browser and out_files["html"].exists():
        try:
            webbrowser.open(out_files["html"].as_uri())
        except Exception:
            pass

    return out_files


def main():
    if len(sys.argv) < 2:
        print("Kullanım: python main.py <dosya_yolu.dwg veya dosya_yolu.dxf> [--no-open]")
        sys.exit(1)

    file_arg = sys.argv[1]
    no_open = "--no-open" in sys.argv
    run_power_audit(file_arg, open_browser=not no_open)


if __name__ == "__main__":
    main()
