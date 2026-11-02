"""
CloudeCAD — Zayıf Akım Sistemleri Denetim Motoru
================================================
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
from core.cad_parser import WeakCurrentCadParser
from core.systems_auditor import WeakCurrentAuditor
from core.reporter import WeakCurrentReporter


def run_weak_current_audit(file_path: str, open_browser: bool = True):
    """Zayıf akım analiz ardışık düzenini çalıştırır."""
    raw_path = Path(file_path).resolve()
    if not raw_path.exists():
        print(f"[HATA] Dosya bulunamadı: {raw_path}")
        sys.exit(1)

    print("=" * 72)
    print("  CloudeCAD — Zayıf Akım Sistemleri Denetim Motoru")
    print(f"  Hedef Dosya: {raw_path.name}")
    print("=" * 72)

    # 1. Aşama: DXF Kontrolü ve Dönüştürme
    print("\n[Aşama 1] DWG/DXF Kontrolü...")
    dxf_path = ensure_dxf(str(raw_path))
    print(f"  ✓ DXF Hazır: {Path(dxf_path).name}")

    # 2. Aşama: CAD Zayıf Akım Katman ve Blok Taraması
    print("\n[Aşama 2] Zayıf Akım Katmanları ve Blokları Taranıyor...")
    parser = WeakCurrentCadParser(dxf_path)
    report = parser.parse()

    print(f"  ✓ Algılanan Tipoloji      : {report.typology} (Güven: %{report.typology_confidence*100:.0f})")
    print(f"  ✓ Tespit Edilen Katmanlar : {len(report.cad_layers_found)} adet ({', '.join(report.cad_layers_found)})")
    print(f"  ✓ Yangın Algılama Elemanı : {report.fire_alarm.total_devices} adet (Duman: {report.fire_alarm.smoke_detectors}, Buton: {report.fire_alarm.manual_call_points}, Siren: {report.fire_alarm.sirens_flashers})")
    print(f"  ✓ Telefon / Data Prizleri : {report.telecom.sockets} adet (Kat Kutusu: {report.telecom.floor_boxes}, Bina Kutusu: {report.telecom.main_boxes})")
    print(f"  ✓ TV / Uydu Prizleri      : {report.smatv.tv_sockets} adet (TAP: {report.smatv.tap_offs}, TV Santrali: {report.smatv.multiswitches})")
    print(f"  ✓ İnterkom Monitörleri    : {report.intercom.monitors} adet (Kapı Zili: {report.intercom.door_bell_buttons}, Kapı Otomatiği: {report.intercom.door_releases})")

    # 3. Aşama: Yönetmelik ve Standart Denetimi (BYKHY, TS EN 54, BTK, TS EN 50083)
    print("\n[Aşama 3] Standart ve Yönetmelik Denetimi Yürütülüyor...")
    auditor = WeakCurrentAuditor(report)
    audited_report = auditor.audit_all()

    crit_cnt = len([f for f in audited_report.findings if f.severity == "KRİTİK"])
    warn_cnt = len([f for f in audited_report.findings if f.severity == "UYARI"])

    print(f"  ✓ Denetim Kararı          : {audited_report.overall_verdict}")
    print(f"  ✓ Güvenlik Skoru          : %{audited_report.score_pct:.0f} / 100")
    print(f"  ✓ Tespit Edilen Maddeler  : {len(audited_report.findings)} adet (Kritik: {crit_cnt}, Uyarı: {warn_cnt})")

    # 4. Aşama: Raporlama ve Çıktı Üretimi
    print("\n[Aşama 4] Raporlar ve Belgeler Üretiliyor...")
    proj_out_dir = OUTPUT_DIR / audited_report.project_name
    reporter = WeakCurrentReporter(audited_report, proj_out_dir)
    out_files = reporter.generate_all()

    print(f"  ✓ Excel Zayıf Akım Cetveli: {out_files['excel']}")
    if "docx" in out_files:
        print(f"  ✓ Word Mühendislik Raporu : {out_files['docx']}")
    print(f"  ✓ HTML Denetim Raporu     : {out_files['html']}")
    print(f"  ✓ JSON Özeti              : {out_files['json']}")

    print("\n" + "=" * 72)
    print("  ZAYIF AKIM ANALİZİ BAŞARIYLA TAMAMLANDI!")
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
    run_weak_current_audit(file_arg, open_browser=not no_open)


if __name__ == "__main__":
    main()
