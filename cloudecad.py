# -*- coding: utf-8 -*-
"""
CloudeCAD v2.0 — Evrensel Elektrik & Raylı Sistem Proje Denetim Platformu
========================================================================
Merkezi Giriş Noktası (Unified Entry Point)

Kullanım:
    python cloudecad.py                                  (İnteraktif Terminal Menüsü)
    python cloudecad.py "klasor_veya_dosya_yolu"         (Otomatik tespit: İstasyon veya Tek Pafta)
    python cloudecad.py --watch                          (Sürekli klasör izleme modu)
    python cloudecad.py --scan                           (incelenecek projeler klasörünü tara)
    python cloudecad.py --file "pafta.dwg"               (Tekil DWG/DXF paftası analizi)
    python cloudecad.py --station "klasor" --code S28    (Belirtilen istasyon kodunu zorla)
"""

from __future__ import annotations

import sys
import os
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any

# Windows konsolunda UTF-8 karakter uyumluluğu
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# CloudeCAD paket yolunu ekle
_ROOT = Path(__file__).parent.resolve()
_ENGINE_DIR = _ROOT / "cloudecadprogramı"
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

try:
    from core import (
        UniversalCADReader,
        DrawingSceneGraph,
        UnifiedAuditEngine as StationAuditEngine,
        StationAuditReport,
        export_station_reports,
    )
    from core.engine import KNOWN_METRO_STATIONS
except ImportError:
    try:
        from common.universal_cad_reader import UniversalCADReader, DrawingSceneGraph
        from common.station_audit_engine import (
            StationAuditEngine,
            StationAuditReport,
            export_station_reports,
            KNOWN_METRO_STATIONS,
        )
    except ImportError as e:
        print(f"\n[HATA] CloudeCAD çekirdek motorları yüklenemedi: {e}")
        print("Lütfen sanal ortamın (venv) aktif olduğundan emin olun.")
        sys.exit(1)

DEFAULT_INPUT_DIR = _ROOT / "incelenecek projeler"
DEFAULT_OUTPUT_DIR = _ROOT / "projelerin inceleme sonuçları"


# ==============================================================================
# TERMINAL VE KONSOL YARDIMCILARI
# ==============================================================================

def print_banner():
    banner = """
================================================================================
  ██████╗██╗      ██████╗ ██╗   ██╗██████╗ ███████╗ ██████╗ █████╗ ██████╗ 
 ██╔════╝██║     ██╔═══██╗██║   ██║██╔══██╗██╔════╝██╔════╝██╔══██╗██╔══██╗
 ██║     ██║     ██║   ██║██║   ██║██║  ██║█████╗  ██║     ███████║██║  ██║
 ██║     ██║     ██║   ██║██║   ██║██║  ██║██╔══╝  ██║     ██╔══██║██║  ██║
 ╚██████╗███████╗╚██████╔╝╚██████╔╝██████╔╝███████╗╚██████╗██║  ██║██████╔╝
  ╚═════╝╚══════╝ ╚═════╝  ╚═════╝ ╚═════╝ ╚══════╝ ╚═════╝╚═╝  ╚═╝╚═════╝ 
                      v2.0 — Evrensel Proje Denetim Platformu
================================================================================
  Disiplinler : Kuvvetli Akım | Zayıf Akım (10 Sistem) | Topraklama | Kablo Tavası
  Standartlar : TS HD 60364 | IEC 60364-5-52 | EN 54 | NFPA 130 | IEEE Std 80
================================================================================
"""
    print(banner)


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f} saniye"
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m} dk {s} sn"


# ==============================================================================
# TEKİL DWG / DXF PAFTASI ANALİZİ
# ==============================================================================

def audit_single_file(
    file_path: Path,
    explicit_code: Optional[str] = None,
    output_dir: Optional[Path] = None,
    use_cache: bool = True,
):
    file_path = Path(file_path).resolve()
    if not file_path.exists():
        print(f"\n[HATA] Dosya bulunamadı: {file_path}")
        return

    output_dir = output_dir or DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "-" * 78)
    print(f"  📄 TEKİL PAFTA İNCELEMESİ: {file_path.name}")
    print(f"  📁 Dosya Yolu: {file_path}")
    print("-" * 78)

    t0 = time.time()
    reader = UniversalCADReader(use_cache=use_cache)
    try:
        scene = reader.read(file_path, explicit_station_code=explicit_code)
    except Exception as ex:
        print(f"\n[HATA] Pafta işlenirken hata oluştu: {ex}")
        return

    dt = time.time() - t0

    print(f"\n  ⏱️  İnceleme Tamamlandı ({format_duration(dt)})")
    print(f"  🏢 Kat Bilgisi            : {scene.floor_name or 'Genel'}")
    print(f"  📑 Pafta Başlığı          : {scene.sheet_title or '-'}")
    print(f"  🔍 Alt Plan Bölgeleri     : {len(scene.sub_plans)} bölge")
    print(f"  🧩 Tespit Edilen Semboller: {len(scene.symbols)} adet")
    print(f"  📊 Çıkarılan Tablolar     : {len(scene.tables)} adet")
    print(f"  🏷️  Kablo & Pano Etiketleri: {len(scene.callouts)} adet")
    print(f"  ⚡ Mantıksal Linyeler     : {len(scene.logical_circuits)} adet")
    print(f"  📏 Fiziksel Güzergahlar   : {len(scene.physical_routes)} adet")

    # Sembol sınıf dağılımı
    classes: Dict[str, int] = {}
    for s in scene.symbols:
        classes[s.classification] = classes.get(s.classification, 0) + 1

    if classes:
        print("\n  📦 Sembol Dağılımı:")
        for cls_name, count in sorted(classes.items(), key=lambda x: -x[1]):
            print(f"     • {cls_name:20s}: {count:4d} adet")

    # Alt Plan Bölgeleri özeti (Çoklu pafta tuvali)
    if scene.sub_plans:
        print(f"\n  🔍 ModelSpace İçinde Algılanan Paftalar ({len(scene.sub_plans)} pafta):")
        for idx, sp in enumerate(scene.sub_plans, 1):
            print(f"     [{idx:2d}] {sp.name:<40s} ({sp.zone_type:18s} | {sp.symbol_count:3d} sembol)")

    # Linye özeti
    if scene.logical_circuits:
        print(f"\n  ⚡ Devreler / Linyeler (İlk 8/{len(scene.logical_circuits)} gösteriliyor):")
        for lc in scene.logical_circuits[:8]:
            print(f"     • [{lc.panel_tag}] Linye {lc.circuit_no}: {lc.fixture_count} armatür/priz, {lc.total_power_w:.0f} W, {lc.cable_cross_section or 'Kesit Belirtilmemiş'}")

    # Tablo özeti
    if scene.tables:
        print(f"\n  📊 Tablolar:")
        for tb in scene.tables:
            print(f"     • {tb.table_type} ({len(tb.headers)} sütun, {len(tb.rows)} satır) - Kolonlar: {', '.join(tb.headers[:5])}")

    # JSON Çıktısı Kaydet
    out_json = output_dir / f"{file_path.stem}_sahne_grafigi.json"
    try:
        import json
        from dataclasses import asdict
        def _json_fallback(o):
            if hasattr(o, "bounds"):
                return {"type": "Polygon", "bounds": list(o.bounds)}
            return str(o)
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(asdict(scene), f, ensure_ascii=False, indent=2, default=_json_fallback)
        print(f"\n  💾 Sahne Grafiği Kaydedildi: {out_json}")
    except Exception as e:
        print(f"  [UYARI] JSON kaydedilemedi: {e}")

    # Mühendislik Denetimini Çalıştır ve Rapor Üret
    try:
        engine = StationAuditEngine(use_cache=use_cache)
        report = engine.audit_single_dwg_project(file_path, scene=scene, explicit_station_code=explicit_code)
        saved_rep = export_station_reports(report, output_dir)
        crit = [f for f in report.findings if f.severity == "CRITICAL"]
        warn = [f for f in report.findings if f.severity == "WARNING"]
        passed = [f for f in report.findings if f.severity == "PASS"]

        print("\n" + "=" * 78)
        print(f"  ⚖️  MÜHENDİSLİK DENETİM SONUÇLARI ({len(report.findings)} Bulgu)")
        print(f"  📜 Kural Paketi: {report.rule_pack_used}")
        print("=" * 78)
        print(f"     🔴 KRİTİK HATA : {len(crit):2d} adet")
        print(f"     🟡 UYARI       : {len(warn):2d} adet")
        print(f"     🟢 UYGUN       : {len(passed):2d} adet")
        print(f"     ℹ️  BELİRSİZLİK : {len(report.uncertainties):2d} adet (İnceleme Listesi)")

        if crit or warn:
            print("\n  📌 TESPİT EDİLEN MÜHENDİSLİK HATALARI VE UYARILAR:")
            for f in crit + warn:
                icon = "🔴" if f.severity == "CRITICAL" else "🟡"
                print(f"     {icon} [{f.code}] {f.title}  (Güven: %{f.confidence_score*100:.0f} - {f.confidence_level})")
                print(f"        • Ölçülen : {f.measured_value}")
                print(f"        • Standart: {f.standard_limit}")
                if f.evidence_chain:
                    print(f"        • Kanıt   : {f.evidence_chain[0]}")

        if report.uncertainties:
            print("\n  🔍 İNCELENMESİ GEREKEN BELİRSİZLİKLER LİSTESİ (Review List):")
            for u in report.uncertainties[:5]:
                print(f"     ℹ️  [{u.code}] {u.title}")
                print(f"        • Şüpheli : {u.suspected_element} (Güven: %{u.confidence_score*100:.0f})")
                print(f"        • Belirti : {u.evidence}")
                print(f"        • Öneri   : {u.recommended_verification}")
        print(f"\n  📄 Mühendislik Raporu (MD)  : {saved_rep['markdown']}")
        print(f"  📊 Denetim Verisi (JSON)    : {saved_rep['json']}")
    except Exception as e:
        print(f"  [UYARI] Mühendislik denetimi çalıştırılamadı: {e}")

    print("-" * 78 + "\n")


# ==============================================================================
# İSTASYON / PROJE KLASÖRÜ BİRLEŞİK DENETİMİ
# ==============================================================================

def audit_station_directory(
    station_dir: Path,
    station_code: Optional[str] = None,
    station_name: Optional[str] = None,
    output_dir: Optional[Path] = None,
    use_cache: bool = True,
) -> Optional[StationAuditReport]:
    station_dir = Path(station_dir).resolve()
    if not station_dir.exists():
        print(f"\n[HATA] Dizin bulunamadı: {station_dir}")
        return None

    output_dir = output_dir or (DEFAULT_OUTPUT_DIR / station_dir.name)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 80)
    print(f"  🏢 İSTASYON BİRLEŞİK MÜHENDİSLİK DENETİMİ BAŞLATILIYOR")
    print(f"  📁 İstasyon Klasörü : {station_dir}")
    print(f"  📤 Rapor Çıktı Yolu : {output_dir}")
    print("=" * 80)

    t0 = time.time()
    engine = StationAuditEngine(use_cache=use_cache)

    def on_progress(cur: int, total: int, fname: str):
        pct = (cur / total) * 100
        print(f"  [{cur:2d}/{total:2d}] (%{pct:5.1f}) İnceleniyor: {fname}")

    report = engine.audit_station(
        station_dir=station_dir,
        station_code=station_code,
        station_name=station_name,
        progress_callback=on_progress,
    )

    dt = time.time() - t0

    # Raporları Kaydet
    saved = export_station_reports(report, output_dir)

    # Konsol Özeti
    crit = [f for f in report.findings if f.severity == "CRITICAL"]
    warn = [f for f in report.findings if f.severity == "WARNING"]
    passed = [f for f in report.findings if f.severity == "PASS"]

    print("\n" + "=" * 80)
    print(f"  🏁 DENETİM TAMAMLANDI — {report.station_code} {report.station_name} ({format_duration(dt)})")
    print(f"  📜 Kural Paketi               : {report.rule_pack_used}")
    print("=" * 80)
    print(f"  📑 Denetlenen Pafta Sayısı    : {report.total_sheets_analyzed}")
    print(f"  🎛️  Birleşik Dağıtım Panoları   : {len(report.panel_summaries)} Pano")
    print(f"  ⚡ Hesaplanan Linye Sayısı     : {len(report.circuit_calculations)} Linye")
    print(f"  🔄 Çapraz Mutabakat Maddeleri : {len(report.reconciliation_items)} Kalem")
    print(f"  📡 Zayıf Akım Alt Sistemleri  : {len(report.weak_current_audits)} Sistem (AX-02, TL-02..11)")
    print(f"  ⚡ Topraklama & Tava Kapsamı   : {len(report.grounding_tray_summaries)} Kat")
    print("-" * 80)
    print(f"  📊 Mühendislik Bulguları Dağılımı:")
    print(f"     🔴 KRİTİK UYGUNSUZLUK : {len(crit):2d} adet")
    print(f"     🟡 MÜHENDİSLİK UYARISI : {len(warn):2d} adet")
    print(f"     🟢 STANDARTLARA UYGUN  : {len(passed):2d} adet")
    print(f"     ℹ️  BELİRSİZLİK LİSTESİ : {len(report.uncertainties):2d} adet")
    print("-" * 80)

    if report.uncertainties:
        print("\n  🔍 İNCELENMESİ GEREKEN BELİRSİZLİKLER LİSTESİ (Review List):")
        for u in report.uncertainties[:5]:
            print(f"     ℹ️  [{u.code}] {u.title} (Güven: %{u.confidence_score*100:.0f})")
            print(f"        • Mahal/Şüpheli : {u.floor_or_scope} | {u.suspected_element}")
            print(f"        • Öneri         : {u.recommended_verification}")

    # Önemli Panolar
    if report.panel_summaries:
        print("\n  🎛️  BİRLEŞİK PANO YÜK & FAZ DENGESİ ÖZETİ:")
        print(f"     {'Pano Kodu':<18} {'Kat':<10} {'Linye':<7} {'Güç (kW)':<10} {'Dengesizlik':<14} {'Durum':<10}")
        print(f"     {'-'*18} {'-'*10} {'-'*7} {'-'*10} {'-'*14} {'-'*10}")
        for p in report.panel_summaries:
            s_str = "UYGUN" if p.status in ("UYGUN", "PASS") else ("UYARI" if p.status == "UYARI" else "KRİTİK")
            print(f"     {p.panel_tag:<18} {p.floor_name:<10} {p.circuit_count:<7d} {p.total_power_w/1000:<10.2f} %{p.imbalance_pct:<13.1f} {s_str:<10}")

    # Öncelikli Bulgular
    if crit:
        print("\n  🔴 EN KRİTİK MÜHENDİSLİK BULGULARI:")
        for f in crit[:6]:
            print(f"     • [{f.code}] {f.title}")
            print(f"       Mahal: {f.floor_or_scope} | Ölçülen: {f.measured_value}")
            print(f"       Kriter: {f.standard_limit}")

    if warn:
        print("\n  🟡 DİKKAT ÇEKEN MÜHENDİSLİK UYARILARI:")
        for f in warn[:5]:
            print(f"     • [{f.code}] {f.title} ({f.floor_or_scope})")

    print("\n" + "=" * 80)
    print("  📄 OLUŞTURULAN MÜHENDİSLİK RAPORLARI:")
    print(f"     📝 Markdown Raporu : {saved['markdown']}")
    print(f"     📊 JSON Veri Dosyası: {saved['json']}")
    print("=" * 80 + "\n")

    return report


# ==============================================================================
# TÜM PROJELERİ TARA (BATCH SCAN)
# ==============================================================================

def scan_all_projects(input_dir: Path, output_base_dir: Path, use_cache: bool = True):
    input_dir = Path(input_dir).resolve()
    output_base_dir = Path(output_base_dir).resolve()

    print("\n" + "=" * 80)
    print(f"  🔍 TOPLU PROJE TARAMASI (BATCH SCAN)")
    print(f"  📥 Girdi Klasörü: {input_dir}")
    print("=" * 80)

    # 1. Alt klasörlerde istasyon paketlerini ara (örn: M09-S28_Yenibosna, M09-S19_Masko)
    station_dirs: List[Path] = []
    for item in sorted(input_dir.iterdir()):
        if item.is_dir():
            # Eğer doğrudan bir istasyon klasörüyse veya altında işsonları_duzenlenmis varsa
            if any(k in item.name.upper() for k in ["M09-S", "M09_S", "ISTASYON", "İSTASYON"]) or "S2" in item.name or "S1" in item.name:
                station_dirs.append(item)
            elif item.name in ["işsonları_duzenlenmis", "işsonları"]:
                for sub in sorted(item.iterdir()):
                    if sub.is_dir() and any(f.suffix.lower() == ".dwg" for f in sub.rglob("*.dwg")):
                        station_dirs.append(sub)

    if not station_dirs:
        # Eğer hiç alt istasyon bulunamadıysa, input_dir'in kendisinde DWG var mı bak
        dwgs = list(input_dir.rglob("*.dwg"))
        if dwgs:
            station_dirs = [input_dir]

    if not station_dirs:
        print("  [UYARI] İncelenecek herhangi bir istasyon veya DWG projesi bulunamadı.")
        return

    print(f"  Tespit Edilen İstasyon Paketleri ({len(station_dirs)} adet):")
    for s in station_dirs:
        print(f"    • {s.name}")

    for idx, sdir in enumerate(station_dirs, 1):
        print(f"\n>>> [{idx}/{len(station_dirs)}] Paket İnceleniyor: {sdir.name} <<<")
        out_d = output_base_dir / sdir.name
        audit_station_directory(sdir, output_dir=out_d, use_cache=use_cache)


# ==============================================================================
# SÜREKLİ İZLEME SERVİSİ (WATCH MODE)
# ==============================================================================

def watch_folder_service(input_dir: Path, output_base_dir: Path, poll_interval: float = 4.0):
    input_dir = Path(input_dir).resolve()
    output_base_dir = Path(output_base_dir).resolve()

    print("\n" + "#" * 80)
    print("  🚀 CLOUDECAD OTOMATİK İZLEME SERVİSİ (WATCH MODE)")
    print(f"  📥 Dinlenen Klasör : {input_dir}")
    print(f"  📤 Rapor Klasörü   : {output_base_dir}")
    print(f"  ⏱️  Yoklama Aralığı : {poll_interval} saniye")
    print("  (Durdurmak için Ctrl+C tuşlarına basın)")
    print("#" * 80 + "\n")

    processed_mtimes: Dict[str, float] = {}

    def check_and_run():
        dwg_files = list(input_dir.rglob("*.dwg"))
        if not dwg_files:
            return

        new_or_modified = False
        for f in dwg_files:
            try:
                mtime = f.stat().st_mtime
                if str(f) not in processed_mtimes or processed_mtimes[str(f)] < mtime:
                    processed_mtimes[str(f)] = mtime
                    new_or_modified = True
            except OSError:
                continue

        if new_or_modified:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Yeni veya güncellenen çizim tespit edildi! Denetim başlatılıyor...")
            scan_all_projects(input_dir, output_base_dir)
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] İzleme devam ediyor...")

    check_and_run()
    try:
        while True:
            time.sleep(poll_interval)
            check_and_run()
    except KeyboardInterrupt:
        print("\n\n  🛑 İzleme servisi kullanıcı tarafından durduruldu.\n")


# ==============================================================================
# İNTERAKTİF MENÜ
# ==============================================================================

def interactive_menu():
    print_banner()
    print("  Lütfen gerçekleştirmek istediğiniz işlemi seçin:")
    print("    [1] İstasyon / Proje Klasörü Denetle (Tüm Disiplinler - StationAuditEngine)")
    print("    [2] Tekil DWG / DXF Paftası İncele (Evrensel CAD Okuyucu v2.0)")
    print("    [3] Tüm Projeleri Tara (Batch Scan - 'incelenecek projeler' klasörü)")
    print("    [4] Sürekli İzleme Servisi (Watch Mode - Klasöre dosya atıldıkça denetle)")
    print("    [0] Çıkış")
    print()

    choice = input("  Seçiminiz (0-4) [Varsayılan: 1]: ").strip() or "1"

    if choice == "0":
        print("  Çıkış yapıldı.")
        sys.exit(0)

    elif choice == "1":
        default_dir = r"D:\autocad projesi\incelenecek projeler\işsonları_duzenlenmis\M09-S28_Yenibosna"
        print(f"\n  İstasyon / Proje Klasör Yolu:")
        print(f"  [Varsayılan: {default_dir}]")
        val = input("  Yol: ").strip().strip('"')
        target_dir = Path(val) if val else Path(default_dir)
        audit_station_directory(target_dir)

    elif choice == "2":
        default_dwg = r"D:\autocad projesi\incelenecek projeler\işsonları_duzenlenmis\M09-S28_Yenibosna\01_Kuvvetli_Akim\AG-PRT-M09-S28-CT0-03-PS-16-A-T-1I-001-0.dwg"
        print(f"\n  İncelenecek DWG / DXF Dosya Yolu:")
        print(f"  [Varsayılan: {Path(default_dwg).name}]")
        val = input("  Yol: ").strip().strip('"')
        target_file = Path(val) if val else Path(default_dwg)
        audit_single_file(target_file)

    elif choice == "3":
        scan_all_projects(DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR)

    elif choice == "4":
        watch_folder_service(DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR)

    else:
        print("  Geçersiz seçim. Çıkılıyor.")


# ==============================================================================
# MAIN GİRİŞ FONKSİYONU
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="cloudecad",
        description="CloudeCAD v2.0 — Evrensel Elektrik & Raylı Sistem Proje Denetim Platformu"
    )
    parser.add_argument("target", nargs="?", default=None, help="İncelenecek dosya veya istasyon klasörü")
    parser.add_argument("--watch", "-w", action="store_true", help="Sürekli klasör izleme modu (Watch Mode)")
    parser.add_argument("--scan", "-s", action="store_true", help="incelenecek projeler klasöründeki tüm istasyonları tara")
    parser.add_argument("--file", "-f", default=None, help="Tekil DWG veya DXF dosyası yolu")
    parser.add_argument("--station", default=None, help="İstasyon klasörü yolu")
    parser.add_argument("--code", default=None, help="İstasyon kodu (Örn: S28, S19)")
    parser.add_argument("--name", default=None, help="İstasyon adı (Örn: Yenibosna)")
    parser.add_argument("--out", "-o", default=None, help="Rapor çıktı klasörü")
    parser.add_argument("--no-cache", action="store_true", help="DXF önbelleğini kullanma, baştan dönüştür")

    args = parser.parse_args()

    use_cache = not args.no_cache
    output_dir = Path(args.out).resolve() if args.out else None

    # 1. Watch Mode
    if args.watch:
        in_dir = Path(args.target).resolve() if args.target else DEFAULT_INPUT_DIR
        out_dir = output_dir or DEFAULT_OUTPUT_DIR
        watch_folder_service(in_dir, out_dir)
        return

    # 2. Batch Scan
    if args.scan:
        in_dir = Path(args.target).resolve() if args.target else DEFAULT_INPUT_DIR
        out_dir = output_dir or DEFAULT_OUTPUT_DIR
        scan_all_projects(in_dir, out_dir, use_cache=use_cache)
        return

    # 3. Explicit File
    if args.file:
        audit_single_file(Path(args.file), explicit_code=args.code, output_dir=output_dir, use_cache=use_cache)
        return

    # 4. Explicit Station
    if args.station:
        audit_station_directory(
            Path(args.station),
            station_code=args.code,
            station_name=args.name,
            output_dir=output_dir,
            use_cache=use_cache,
        )
        return

    # 5. Target argument provided
    if args.target:
        p = Path(args.target).resolve()
        if p.is_file():
            audit_single_file(p, explicit_code=args.code, output_dir=output_dir, use_cache=use_cache)
        elif p.is_dir():
            audit_station_directory(
                p,
                station_code=args.code,
                station_name=args.name,
                output_dir=output_dir,
                use_cache=use_cache,
            )
        else:
            print(f"\n[HATA] Belirtilen hedef bulunamadı: {p}")
        return

    # 6. Hiç parametre verilmediyse İnteraktif Menüyü aç
    interactive_menu()


if __name__ == "__main__":
    main()
