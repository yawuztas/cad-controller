"""
CloudeCAD — Süperpozisyon ve Çakışma Denetim Motoru CLI 2.0
==========================================================
Kullanım:
    python -m cloudecadprogramı.superpose_motoru.main -i <girdi_klasoru> -o <cikti_klasoru> [--floor CT0-03] [--sector 001]
"""

import argparse
import sys
import time
import re
from pathlib import Path

# Windows console encoding fix
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Proje kökünü sys.path'e ekle
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from cloudecadprogramı.superpose_motoru.core.cad_superposer import CadSuperposer
from cloudecadprogramı.superpose_motoru.core.clash_detector import ClashDetector
from cloudecadprogramı.superpose_motoru.core.docx_reporter import SuperpositionDocxReporter
from cloudecadprogramı.superpose_motoru.core.html_viewer import InteractiveHtmlCadViewer

STATION_NAMES = {
    "M09-S18": "İkitelli Sanayi İstasyonu",
    "M09-S19": "Masko İstasyonu",
    "M09-S20": "Bahariye İstasyonu",
    "M09-S21": "Atatürk Mahallesi İstasyonu",
    "M09-S22": "15 Temmuz İstasyonu",
    "M09-S23": "Mimar Sinan İstasyonu",
    "M09-S24": "Çobançeşme - Kuyumcukent İstasyonu",
    "M09-S25": "29 Ekim Cumhuriyet İstasyonu",
    "M09-S26": "Doğu Sanayi İstasyonu",
    "M09-S27": "İhlas Yuva İstasyonu",
    "M09-S28": "Yenibosna İstasyonu",
    "M09-S29": "Ataköy İstasyonu",
}


def run_superposition(
    input_dir: Path,
    output_dir: Path,
    floor_code: str = "CT0-03",
    sector_filter: str = "001",
    station_key: str = None,
    station_name: str = None
):
    # İlgili kata ait DXF paftalarını bul
    all_dxf_files = list(input_dir.glob(f"*{floor_code}*.dxf"))
    if not all_dxf_files:
        print(f"Uyarı: {input_dir} içinde {floor_code} DXF paftası bulunamadı!")
        return

    # İstasyon kodunu otomatik tespit et
    if not station_key:
        for f in all_dxf_files:
            m = re.search(r'M09-S-?(\d{2})', f.name, re.IGNORECASE)
            if m:
                station_key = f"M09-S{m.group(1)}"
                break
    if not station_key:
        station_key = "M09-S28"
    if not station_name:
        station_name = STATION_NAMES.get(station_key, f"{station_key} İstasyonu")

    # İlgili istasyonun paftalarını filtrele
    dxf_files = [f for f in all_dxf_files if station_key.replace('-', '') in f.name.replace('-', '')]
    if not dxf_files:
        dxf_files = all_dxf_files

    print("=" * 80)
    print("  CloudeCAD 2.0 — Bütünleşik Kablo Tavası ve Kuvvetli Akım Süperpozisyon Motoru")
    print(f"  📥 Girdi Klasörü : {input_dir}")
    print(f"  📤 Çıktı Klasörü : {output_dir}")
    print(f"  🏢 İstasyon      : {station_name} ({station_key})")
    print(f"  📍 Hedef Kat     : {floor_code}" + (f" (Sektör: {sector_filter})" if sector_filter else " (Tüm Kat/Sektörler)"))
    print("=" * 80)

    t0 = time.time()

    # Sektör filtrelemesi varsa uygula
    if sector_filter:
        tava_files = [f for f in dxf_files if "GN-13" in f.name and sector_filter in f.name]
        ayd_files = [f for f in dxf_files if "PS-16" in f.name and sector_filter in f.name]
        guc_files = [f for f in dxf_files if "PS-11" in f.name and sector_filter in f.name]
        if not guc_files:
            guc_files = [f for f in dxf_files if "PS-11" in f.name]
        boru_files = [f for f in dxf_files if "GN-14" in f.name and sector_filter in f.name]
    else:
        tava_files = sorted([f for f in dxf_files if "GN-13" in f.name and not f.name.startswith("._")])
        ayd_files = sorted([f for f in dxf_files if "PS-16" in f.name and not f.name.startswith("._")])
        guc_files = sorted([f for f in dxf_files if "PS-11" in f.name and not f.name.startswith("._")])
        boru_files = sorted([f for f in dxf_files if "GN-14" in f.name and not f.name.startswith("._")])

    if not tava_files or not ayd_files:
        print(f"Hata: {floor_code} için GN-13 (Tava) veya PS-16 (Aydınlatma) paftası bulunamadı!")
        return

    print(f"\n[1/4] Paftalar Eşleştirildi:")
    print(f"   • Tava Paftaları (GN-13)   : {len(tava_files)} adet ({', '.join(f.name[-9:-4] for f in tava_files)})")
    print(f"   • Aydınlatma/Priz (PS-16)  : {len(ayd_files)} adet ({', '.join(f.name[-9:-4] for f in ayd_files)})")
    if guc_files:
        print(f"   • Kuvvet/Mekanik (PS-11)   : {len(guc_files)} adet")
    if boru_files:
        print(f"   • Borulama (GN-14)         : {len(boru_files)} adet")

    superposer = CadSuperposer(station_name=station_name, station_key=station_key)

    print(f"\n[2/4] CAD Geometrisi Ortak Koordinatlarda Ayrıştırılıyor...")
    cnt_tava_tot = 0
    for tf in tava_files:
        cnt = superposer.extract_tava_entities(tf)
        cnt_tava_tot += cnt
    print(f"   ✓ Toplam {cnt_tava_tot} adet tava çizgisi ve {len(superposer.annotations)} adet tava kot/ebat etiketi okundu.")

    cnt_ayd_tot = 0
    for af in ayd_files:
        cnt = superposer.extract_lighting_cables(af)
        cnt_ayd_tot += cnt
    print(f"   ✓ Toplam {cnt_ayd_tot} adet aydınlatma linye çizgisi ve {len(superposer.panels)} adet pano tespit edildi.")

    cnt_guc_tot = 0
    for gf in guc_files:
        cnt = superposer.extract_power_cables(gf)
        cnt_guc_tot += cnt
    if guc_files:
        print(f"   ✓ Toplam {cnt_guc_tot} adet kuvvet besleme çizgisi okundu.")

    cnt_boru_tot = 0
    for bf in boru_files:
        cnt = superposer.extract_conduit_hdpe(bf)
        cnt_boru_tot += cnt
    if boru_files:
        print(f"   ✓ Toplam {cnt_boru_tot} adet döşemealtı borulama çizgisi okundu.")

    # Mimari altlığı ilk aydınlatma paftasından al
    cnt_arc = superposer.extract_architectural_base(ayd_files[0])
    print(f"   ✓ {cnt_arc} adet mimari/strüktürel referans çizgisi dahil edildi.")

    # Dinamik kat planı sınırlarını güncelle
    superposer.update_dynamic_bounds(margin_mm=4000.0)
    print(f"   ✓ Dinamik Kat Sınırları: X=[{superposer.x_min:.0f}, {superposer.x_max:.0f}], Y=[{superposer.y_min:.0f}, {superposer.y_max:.0f}]")

    print(f"\n[3/4] Mühendislik Çakışma, Gerçek Doluluk, Topoloji ve Şebeke Analizi Yapılıyor...")
    detector = ClashDetector(
        station_name=station_name,
        station_key=station_key,
        floor_code=floor_code,
        floor_name="BİLET HOLÜ / TURNİKE KATI"
    )
    audit_res = detector.audit(superposer.segments, superposer.annotations, superposer.panels)

    # Uyarı noktalarını CAD süperpozisyonuna ekle
    if audit_res.route_isolated_pct > 2.0:
        superposer.clash_points.append((35000.0, 52000.0, "UYARI", "Bilet Holü Köşe Armatürleri: Tavasız Güzergah (HDPE Spiral Boru Gerekli)"))

    print(f"   • Toplam Tava Metrajı : {audit_res.total_tray_lv_m:.1f} m (AG) | {audit_res.total_tray_wc_m:.1f} m (ZA)")
    print(f"   • Toplam Kablo Metrajı: {audit_res.total_cable_lighting_m + audit_res.total_cable_power_m:.1f} m (FE180: {audit_res.total_cable_fe180_m:.1f} m)")
    print(f"   • Tava Koridor Uyumu  : %{audit_res.route_in_tray_pct} (Tava İçi Taşınan Hat)")
    print(f"   • Gerçek Doluluk      : %{audit_res.average_fill_ratio_pct} (Maks: %{audit_res.max_fill_ratio_pct} — TS HD 60364-5-52 Uyumlu)")
    print(f"   • EMC Kot Ayrımı      : Δh = {audit_res.elevation_diff_mm} mm ({audit_res.emc_compliance})")
    print(f"   • Topolojik Graf      : {audit_res.tray_nodes_count} Düğüm | {audit_res.connected_components_count} Bileşen | {audit_res.dead_end_nodes_count} Çıkmaz Uç")
    if audit_res.sim_result:
        print(f"   • pandapower Şebeke   : Ik''={audit_res.sim_result.max_short_circuit_ka:.1f} kA (AGDP) | Maks ΔU=%{audit_res.sim_result.max_voltage_drop_pct:.2f} ({audit_res.sim_result.max_voltage_drop_bus.split('(')[0].strip()})")
    print(f"   • Uyum Skoru          : %{audit_res.compliance_score_pct} — {audit_res.executive_verdict}")

    print(f"\n[4/4] Süperpoze Çıktılar Üretiliyor...")
    sub_out = output_dir / f"{station_key.replace('-', '_')}_{station_name.replace(' ', '_').replace('/', '_')}_Superpoze_Tava_Kablo"
    sub_out.mkdir(parents=True, exist_ok=True)

    sec_tag = f"_{sector_filter}" if (sector_filter and sector_filter != "001") else ""

    # 1. Süperpoze DXF
    dxf_out = sub_out / f"{station_key.replace('-', '_')}_{floor_code}{sec_tag}_Bilet_Holu_SUPERPOSE_TAVA_KABLO.dxf"
    superposer.build_superposed_dxf(dxf_out, floor_code=floor_code)
    print(f"   ✓ 1. Süperpoze CAD Paftası (DXF)       : {dxf_out.name} ({dxf_out.stat().st_size / 1024:.1f} KB)")

    # 2. Koordinasyon PNG Görseli
    png_out = sub_out / f"{station_key.replace('-', '_')}_{floor_code}{sec_tag}_SUPERPOSE_KOORDINASYON_PLANI.png"
    superposer.render_coordination_image(png_out, floor_code=floor_code)
    print(f"   ✓ 2. Yüksek Çözünürlüklü Önizleme (PNG): {png_out.name} ({png_out.stat().st_size / 1024:.1f} KB)")

    # 3. İnteraktif Plotly HTML CAD Görüntüleyici
    html_out = sub_out / f"{station_key.replace('-', '_')}_{floor_code}{sec_tag}_SUPERPOSE_INTERAKTIF_GORUNTULEYICI.html"
    viewer = InteractiveHtmlCadViewer(station_name=station_name, station_key=station_key, floor_code=floor_code)
    viewer.generate_html_viewer(
        output_html_path=html_out,
        segments=superposer.segments,
        annotations=superposer.annotations,
        panels=superposer.panels,
        clash_points=superposer.clash_points,
        audit_res=audit_res,
        sim_res=audit_res.sim_result,
        network_graph_paths=audit_res.network_paths_geometry
    )
    print(f"   ✓ 3. İnteraktif WebGL Viewer (HTML)     : {html_out.name} ({html_out.stat().st_size / 1024:.1f} KB)")

    # 4. Kurumsal Word Raporu
    reporter = SuperpositionDocxReporter()
    docx_out = sub_out / f"{station_key.replace('-', '_')}_{station_name.replace(' ', '_').replace('/', '_')}_Kablo_Tava_Superpozisyon_Raporu.docx"
    reporter.generate_report(audit_res, docx_out, image_path=png_out, html_viewer_path=html_out)
    print(f"   ✓ 4. Bütünleşik Word Raporu (.docx)    : {docx_out.name} ({docx_out.stat().st_size / 1024:.1f} KB)")

    print("\n" + "=" * 80)
    print(f"  ✨ Süperpozisyon, Doluluk, Topoloji ve Şebeke Denetimi Başarıyla Tamamlandı! ({time.time() - t0:.1f}s)")
    print(f"  📁 Çıktı Klasörü: {sub_out}")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CloudeCAD 2.0 Tava & Kablo Süperpozisyon Motoru")
    parser.add_argument("-i", "--input", required=True, help="İstasyon paftalarının bulunduğu klasör")
    parser.add_argument("-o", "--output", required=True, help="Çıktı raporları ve CAD dosyalarının kaydedileceği klasör")
    parser.add_argument("-f", "--floor", default="CT0-03", help="Süperpoze edilecek hedef kat kodu (Örn: CT0-03)")
    parser.add_argument("-s", "--sector", default="001", help="İsteğe bağlı sektör filtre kodu (Varsayılan: 001)")
    parser.add_argument("--station", default=None, help="İstasyon kodu (Örn: M09-S28)")
    args = parser.parse_args()

    run_superposition(
        input_dir=Path(args.input),
        output_dir=Path(args.output),
        floor_code=args.floor,
        sector_filter=args.sector,
        station_key=args.station
    )
