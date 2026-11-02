"""
CloudeCAD — Ana CLI Giriş Noktası
====================================
Kullanım:
    python main.py <dosya.dxf>
    python main.py <dosya.dxf> --rho 100
    python main.py <dosya.dxf> --katman "TOPRAK,PE" --cikti outputs/proje

Örnekler:
    python main.py "D:/autocad projesi/ornekprojeler/5katlı 10 daireli.dwg"
    python main.py proje.dxf --rho 40 --verbose
"""

import sys
import logging
import argparse
from pathlib import Path

# Windows konsolunda UTF-8 karakter uyumluluğu
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ── Renk desteği (Windows terminali) ─────────────────────────
try:
    import colorlog
    _COLORLOG = True
except ImportError:
    _COLORLOG = False

# ── Proje kökünü Python path'e ekle ─────────────────────────
_ROOT = Path(__file__).parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _setup_logging(verbose: bool):
    """Logging yapılandırması."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    datefmt = "%H:%M:%S"

    if _COLORLOG:
        handler = colorlog.StreamHandler()
        handler.setFormatter(colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)s]%(reset)s %(message)s",
            datefmt=datefmt,
            log_colors={
                "DEBUG":    "cyan",
                "INFO":     "white",
                "WARNING":  "yellow",
                "ERROR":    "red",
                "CRITICAL": "red,bg_white",
            }
        ))
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    logging.basicConfig(level=level, handlers=[handler])

    # dosya log'u
    from config import LOG_FILE
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    logging.getLogger().addHandler(file_handler)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cloudecad",
        description=(
            "CloudeCAD — DXF/DWG Topraklama Denetim Motoru\n"
            "DXF paftasından topraklama direncini hesaplar ve "
            "TS HD 60364-5-54 standartlarına uygunluğunu denetler."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "dosya",
        help="DXF (veya DWG*) dosyası yolu\n"
             "*DWG: ODA File Converter kurulu olmalıdır.",
    )

    parser.add_argument(
        "--rho",
        type=float,
        metavar="DEĞER",
        help=(
            "Zemin özgül direnci (Ω·m). "
            "Verilmezse paftadan otomatik okunur. "
            "Paftada bulunamazsa varsayılan 100 Ω·m kullanılır."
        ),
    )

    parser.add_argument(
        "--katman",
        metavar="'KAT1,KAT2'",
        help=(
            "Manuel topraklama katmanı adları (virgülle ayırın). "
            "Verilmezse otomatik tespit yapılır. "
            "Örn: --katman '00-TOPRAK,PE,EARTH'"
        ),
    )

    parser.add_argument(
        "--cikti",
        metavar="DİZİN",
        help="Çıktı dizini (varsayılan: outputs/<dosya_adı>)",
    )

    parser.add_argument(
        "--snap",
        type=float,
        default=50.0,
        metavar="MM",
        help="Fuzzy snap toleransı mm cinsinden (varsayılan: 50 mm = 5 cm)",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Ayrıntılı debug çıktısı göster",
    )

    parser.add_argument(
        "--no-svg",
        action="store_true",
        help="SVG Redline üretimini atla",
    )

    parser.add_argument(
        "--ask-rho",
        action="store_true",
        help="ρ paftada bulunamazsa terminalden manuel sormasını zorunlu kıl (varsayılan: otomatik 100 Ω·m)",
    )

    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Rapor tamamlandığında HTML raporunu tarayıcıda otomatik açma",
    )

    parser.add_argument(
        "--batch",
        action="store_true",
        help="Toplu / gözetimsiz çalışma modu (kullanıcı etkileşimli istemleri devre dışı bırakır)",
    )

    parser.add_argument(
        "--redline",
        action="store_true",
        help="Tespit edilen hataları revizyon bulutlarıyla (*_REDLINE.dxf) CAD paftasına işle",
    )

    parser.add_argument(
        "--sartname",
        type=str,
        default=None,
        help="Şartname profili (IBB_M9_METRO, AYGM_GENEL_METRO, TS_HD_60364_BINA, IEEE80_ENDUSTRIYEL)",
    )

    return parser


def _ask_rho() -> float:
    """
    Paftada ρ bulunamazsa kullanıcıdan ister.
    Boş bırakılırsa varsayılan 100 Ω·m kullanılır.
    """
    print()
    print("  ┌─────────────────────────────────────────────────────────┐")
    print("  │  Zemin özgül direnci (ρ) paftada bulunamadı.           │")
    print("  │  Lütfen değeri girin veya varsayılan için ENTER'a basın. │")
    print("  │  Referans değerler:                                      │")
    print("  │    • Sulu bataklık  : 5–40 Ω·m                         │")
    print("  │    • Tarla toprağı  : 40–100 Ω·m                       │")
    print("  │    • Killi toprak   : 100–300 Ω·m                      │")
    print("  │    • Kum / çakıl    : 300–1000 Ω·m                     │")
    print("  │    • Kaya           : 1000+ Ω·m                        │")
    print("  └─────────────────────────────────────────────────────────┘")
    print()

    while True:
        val = input("  ρ değeri [varsayılan=100 Ω·m]: ").strip()
        if val == "":
            print("  → Varsayılan 100 Ω·m kullanılıyor.")
            return 100.0
        try:
            rho = float(val.replace(",", "."))
            if rho <= 0:
                print("  Hata: ρ pozitif olmalı. Tekrar deneyin.")
                continue
            return rho
        except ValueError:
            print("  Hata: Geçersiz sayı. Tekrar deneyin.")


def _ask_extra_layers() -> list[str]:
    """
    Topraklama katmanı tespit edilemezse kullanıcıdan katman adı ister.
    """
    print()
    print("  ⚠  Topraklama katmanı tespit edilemedi.")
    print("  Lütfen DXF'deki topraklama katman adını/adlarını girin.")
    print("  (virgülle ayırın, boş bırakırsanız tüm katmanlar taranır)")
    print()
    val = input("  Katman adları: ").strip()
    if not val:
        return []
    return [v.strip() for v in val.split(",") if v.strip()]


def main():
    parser = _build_parser()
    args = parser.parse_args()

    _setup_logging(args.verbose)
    log = logging.getLogger(__name__)

    # ── Dosya kontrolü ────────────────────────────────────────
    input_path = Path(args.dosya)
    if not input_path.exists():
        log.error(f"Dosya bulunamadı: {input_path}")
        sys.exit(1)

    # ── Çıktı dizini ──────────────────────────────────────────
    if args.cikti:
        output_dir = Path(args.cikti)
    else:
        from config import OUTPUT_DIR
        output_dir = OUTPUT_DIR / input_path.stem

    output_dir.mkdir(parents=True, exist_ok=True)

    print()
    print(f"  CloudeCAD — Topraklama Denetim Motoru")
    print(f"  Dosya  : {input_path.name}")
    print(f"  Çıktı  : {output_dir}")
    print()

    # ══════════════════════════════════════════════════════════
    #  TIER 0: DWG → DXF dönüşümü (Akıllı Önbellekli)
    # ══════════════════════════════════════════════════════════
    dxf_path = input_path
    if input_path.suffix.lower() == ".dwg":
        try:
            from core.tier0_converter import ensure_dxf
            print("  [Tier 0] DWG → DXF dönüşümü / önbellek kontrolü...")
            dxf_path = ensure_dxf(input_path, output_dir=output_dir, use_cache=True)
            print(f"  ✓ DXF hazır: {dxf_path.name}")
        except FileNotFoundError as e:
            print()
            print(f"  ⚠  {e}")
            print()
            print("  DWG dönüşümü yapılamadı. Seçenekler:")
            print("  1) ODA File Converter'ı kurun: https://opendesign.com/guestfiles/oda_file_converter")
            print("  2) DWG'yi AutoCAD ile DXF olarak kaydedin")
            print("  3) '--help' için: python main.py --help")
            sys.exit(1)

    # ══════════════════════════════════════════════════════════
    #  TIER 1: DXF Parser
    # ══════════════════════════════════════════════════════════
    print("  [Tier 1] DXF ayrıştırılıyor...")
    from core.tier1_parser import DXFParser
    parser_obj = DXFParser()
    try:
        drawing = parser_obj.parse(dxf_path)
    except (ValueError, FileNotFoundError) as e:
        log.error(f"DXF okunamadı: {e}")
        sys.exit(1)

    # Manuel katman ekleme
    extra_layers = []
    if args.katman:
        extra_layers = [l.strip() for l in args.katman.split(",")]
    elif not drawing.grounding_layers and not drawing.grounding_segments and not getattr(args, 'batch', False):
        extra_layers = _ask_extra_layers()

    if extra_layers:
        from standards.layer_profiles import GROUNDING_PATTERNS
        for lname in extra_layers:
            drawing.all_layers[lname] = "grounding"
            if lname not in drawing.grounding_layers:
                drawing.grounding_layers.append(lname)
        drawing = parser_obj.parse(dxf_path)
        log.info(f"Manuel katmanlar eklendi: {extra_layers}")

    print(f"  ✓ {drawing.total_entities} entity, "
          f"{len(drawing.grounding_layers)} topraklama katmanı, "
          f"{len(drawing.grounding_segments)} segment")

    # ══════════════════════════════════════════════════════════
    #  TIER 1.5: ERKEN PROJE TİPOLOJİSİ SINIFLANDIRMA (BİNA / METRO / ENDÜSTRİ)
    # ══════════════════════════════════════════════════════════
    from standards.project_classifier import (
        classify_project, PROJECT_TYPE_METRO, PROJECT_TYPE_BUILDING, PROJECT_TYPE_INDUSTRIAL
    )
    cls_result = classify_project(drawing)
    print(f"\n  🔍 [Tier 1.5 — Proje Sınıflandırma] Tespit Edilen Tipoloji: {cls_result.typology} (Güven: %{cls_result.confidence*100:.0f})")
    for r in cls_result.reasons[:3]:
        print(f"     • {r}")

    # ══════════════════════════════════════════════════════════
    #  TIER 2: Geometri Motoru (Tipolojiye Duyarlı)
    # ══════════════════════════════════════════════════════════
    print("  [Tier 2] Geometri analizi...")
    from core.tier2_geometry import GeometryEngine
    geo_engine = GeometryEngine(snap_tolerance_mm=args.snap)
    geo = geo_engine.analyze(
        drawing,
        project_type=cls_result.typology,
        drawing_role=cls_result.metro_role
    )

    if geo.floors and len(geo.floors) > 1:
        print(f"  🏢 Çok Katlı Proje Ayrıştırması ({len(geo.floors)} Kat/Pafta Dilimi):")
        for f in geo.floors:
            is_active = (geo.active_foundation_floor and f.zone_id == geo.active_foundation_floor.zone_id)
            flag = "★ [TEMEL TOPRAKLAMA]" if is_active else "  [Eşpotansiyel Ağ]"
            print(f"     {flag} Kot: {f.title.elevation_rank:+2d} | {f.title.floor_name:<22s} | Şerit: {f.grounding_length_m:5.1f}m | Çubuk: {f.rod_count} | Klemens: {f.clamp_count}")
    elif geo.active_foundation_floor:
        print(f"  🏢 Kat: {geo.active_foundation_floor.title.floor_name} (Kot: {geo.active_foundation_floor.title.elevation_rank:+2d})")

    # ── DAL 1: RAYLI SİSTEM & METRO İSTASYONU ─────────────────
    if cls_result.typology == PROJECT_TYPE_METRO:
        print("\n  🚆 [Raylı Sistem] Metro İstasyonu Topraklama Denetimi Yürütülüyor...")
        from core.metro_analyzer import MetroStationAnalyzer
        from core.metro_docx_reporter import MetroDocxReporter
        from core.cad_render import render_metro_cad_preview_png

        spec_id = args.sartname or "IBB_M9_METRO"
        metro_analyzer = MetroStationAnalyzer(spec_profile_id=spec_id)
        metro_res = metro_analyzer.analyze(drawing, cls_result, geo)

        # CAD Önizleme PNG üretimi
        preview_png_path = output_dir / f"{input_path.stem}_cad_plani.png"
        try:
            render_metro_cad_preview_png(drawing, metro_res, preview_png_path)
        except Exception as e:
            log.warning(f"Metro CAD önizleme oluşturulamadı: {e}")
            preview_png_path = None

        # İsteğe Bağlı Redline CAD Paftası (*_REDLINE.dxf)
        if getattr(args, 'redline', False):
            from core.redline_dxf import generate_redline_dxf
            redline_path = output_dir / f"{input_path.stem}_DENETIM_REDLINE.dxf"
            generate_redline_dxf(dxf_path, metro_res, redline_path, unit_factor=getattr(drawing, 'unit_factor', 1000.0))

        # Word Denetim Raporu Üretimi
        docx_path = output_dir / f"{input_path.stem}_Topraklama_Denetim_Raporu.docx"
        metro_reporter = MetroDocxReporter()
        metro_reporter.generate_report(metro_res, drawing, docx_path, preview_png_path=preview_png_path)

        # Batch inspector özet JSON çıktısı
        json_summary_path = output_dir / f"{input_path.stem}_rapor.json"
        import json
        with open(json_summary_path, "w", encoding="utf-8") as jf:
            json.dump({
                "tipoloji": "METRO",
                "istasyon_kati": metro_res.floor_level,
                "rol": metro_res.drawing_role,
                "kaynak_durumu": metro_res.source_status_note,
                "bara_sayisi": len(metro_res.busbars),
                "toplam_iletken_m": metro_res.total_conductor_m,
                "karar": metro_res.executive_verdict,
                "ozet": metro_res.verdict_summary
            }, jf, ensure_ascii=False, indent=2)

        print("\n" + "╔" + "═" * 74 + "╗")
        print("║      CloudeCAD — Raylı Sistem & Metro İstasyonu Topraklama Raporu        ║")
        print("╚" + "═" * 74 + "╝")
        print(f"  İstasyon Katı/Rolü : {metro_res.floor_level} | {metro_res.drawing_role}")
        print(f"  Topraklama Kaynağı : {metro_res.grounding_source_type}")
        print(f"  Master ETB Durumu  : {'MEVCUT (Peron Altı -48.55)' if metro_res.has_sub_platform_master else 'Üst Kat Dağıtımı (Master ETB Referanslı)'}")
        print(f"  Bakır Baralar      : {len(metro_res.busbars)} Adet (40x5 mm Cu)")
        print(f"  İletken Güzergahı  : {metro_res.total_conductor_m:.1f} m (120mm² Ana / 16mm² Branşman)")
        print(f"  Ekipman Denetimi   : {len(metro_res.grounded_elements)} Doğru / {len(metro_res.spatial_defects)} Eksik")
        print(f"  Teknik Oda Denetimi: {len(metro_res.technical_rooms_audit)} Kritik Teknik Mahal İncelendi")
        print(f"  Ray Altı Hasır / DC: {'MEVCUT (Ray ve Tünel Güzergahı)' if metro_res.has_rail_mesh else 'BU PAFTADA KAPSAM DIŞI (RAY YOKTUR)'}")
        print("  " + "─" * 74)
        print(f"  ✓ BAŞMÜHENDİS KARARI: {metro_res.executive_verdict}")
        print("  " + "─" * 74)
        print(f"  📄 WORD DENETİM RAPORU: {docx_path.name}")
        print()
        return

    # ── DAL 2: ENDÜSTRİYEL TESİS & OG TRAFO MERKEZİ (IEEE Std 80 & EN 50522) ──
    if cls_result.typology == PROJECT_TYPE_INDUSTRIAL:
        print("\n  🏭 [Endüstriyel & Trafo Merkezi] IEEE Std 80 & TS EN 50522 Denetimi Yürütülüyor...")
        from core.tier3_calculator import CalculationEngine
        from core.industrial_analyzer import IndustrialGroundingAnalyzer
        from core.industrial_docx_reporter import IndustrialDocxReporter
        from core.cad_render import render_cad_preview_png

        user_rho_ind = args.rho or geo.params.rho_ohm_m or 100.0
        calc_ind = CalculationEngine().calculate(geo, user_rho=user_rho_ind)
        spec_id = args.sartname or "IEEE80_ENDUSTRIYEL"
        ind_analyzer = IndustrialGroundingAnalyzer(spec_profile_id=spec_id)
        ind_res = ind_analyzer.analyze(drawing, geo, calc_ind, user_rho=user_rho_ind)

        preview_png_path = output_dir / f"{input_path.stem}_cad_plani.png"
        try:
            render_cad_preview_png(drawing, geo, calc_ind, preview_png_path)
        except Exception as e:
            log.warning(f"Endüstriyel CAD önizleme oluşturulamadı: {e}")
            preview_png_path = None

        if getattr(args, 'redline', False):
            from core.redline_dxf import generate_redline_dxf
            redline_path = output_dir / f"{input_path.stem}_DENETIM_REDLINE.dxf"
            generate_redline_dxf(dxf_path, ind_res, redline_path, unit_factor=getattr(drawing, 'unit_factor', 1000.0))

        docx_path = output_dir / f"{input_path.stem}_Topraklama_Denetim_Raporu.docx"
        IndustrialDocxReporter().generate_report(ind_res, drawing, docx_path, preview_png_path=preview_png_path)

        json_summary_path = output_dir / f"{input_path.stem}_rapor.json"
        import json
        with open(json_summary_path, "w", encoding="utf-8") as jf:
            json.dump({
                "tipoloji": "ENDÜSTRİYEL",
                "alt_tip": ind_res.facility_subtype,
                "toplam_iletken_m": ind_res.total_strip_length_m,
                "rg_ieee80_ohm": ind_res.rg_ieee80_sverak_ohm,
                "re_laurent_ohm": ind_res.re_laurent_ohm,
                "em_dokunma_v": ind_res.step_touch.em_actual_mesh_voltage_v,
                "etouch70_sinir_v": ind_res.step_touch.e_touch70_limit_v,
                "karar": ind_res.executive_verdict,
                "ozet": ind_res.verdict_summary,
            }, jf, ensure_ascii=False, indent=2)

        print("\n" + "╔" + "═" * 74 + "╗")
        print("║    CloudeCAD — Endüstriyel Tesis & OG Trafo Merkezi Topraklama Raporu    ║")
        print("╚" + "═" * 74 + "╝")
        print(f"  Tesis Tipi         : {ind_res.facility_subtype}")
        print(f"  İletken / Kazık    : {ind_res.total_strip_length_m:.1f} m Şerit | {ind_res.rod_count} Adet Elektrot")
        print(f"  Direnç (Rg ≤ 1.0Ω) : Rg(IEEE 80) = {ind_res.rg_ieee80_sverak_ohm:.3f} Ω | Re(Laurent) = {ind_res.re_laurent_ohm:.3f} Ω")
        print(f"  Dokunma Gerilimi   : Em = {ind_res.step_touch.em_actual_mesh_voltage_v:.0f} V (Sınır Etouch70 = {ind_res.step_touch.e_touch70_limit_v:.0f} V)")
        print(f"  Adım Gerilimi      : Es = {ind_res.step_touch.es_actual_step_voltage_v:.0f} V (Sınır Estep70 = {ind_res.step_touch.e_step70_limit_v:.0f} V)")
        print("  " + "─" * 74)
        print(f"  ✓ BAŞMÜHENDİS KARARI: {ind_res.executive_verdict}")
        print("  " + "─" * 74)
        print(f"  📄 WORD DENETİM RAPORU: {docx_path.name}")
        print()
        return

    # ══════════════════════════════════════════════════════════
    #  TIER 2.5: Görsel Analiz & OCR Motoru (Vision OCR)
    # ══════════════════════════════════════════════════════════
    print("  [Tier 2.5] Görsel analiz & OCR taranıyor...")
    from core.tier3_vision_ocr import VisionOCREngine
    vision_engine = VisionOCREngine(output_dir=output_dir)
    table_data = vision_engine.scan_dxf_for_tables(dxf_path)

    if table_data:
        print("  ✓ Gömülü/Harici hesap tablosu başarıyla okundu!")
        if table_data.rho_ohm_m:
            geo.params.rho_ohm_m = table_data.rho_ohm_m
            geo.params.rho_source = "hesap_tablosu"
        if table_data.strip_length_m:
            geo.params.strip_length_m = table_data.strip_length_m
        if table_data.building_width_m:
            geo.params.building_width_m = table_data.building_width_m
        if table_data.building_length_m:
            geo.params.building_length_m = table_data.building_length_m
        if table_data.rod_count:
            geo.params.stake_count_declared = table_data.rod_count
            if geo.params.stake_count is None:
                geo.params.stake_count = table_data.rod_count
        if table_data.equivalent_diameter_D:
            geo.params.equivalent_diameter_D = table_data.equivalent_diameter_D
        if table_data.declared_Re:
            geo.params.declared_Re = table_data.declared_Re
        if table_data.declared_Rc:
            geo.params.declared_Rc = table_data.declared_Rc
        if table_data.declared_Ry:
            geo.params.declared_Ry = table_data.declared_Ry
        if table_data.building_area_m2 and (geo.building_area_m2 is None or geo.building_area_m2 == 0):
            geo.building_area_m2 = table_data.building_area_m2
        if table_data.conductor_section_q:
            geo.params.conductor_section_q = table_data.conductor_section_q
        if table_data.conductor_diameter_d:
            geo.params.conductor_diameter_d = table_data.conductor_diameter_d
        if table_data.conductor_depth_H:
            geo.params.conductor_depth_H = table_data.conductor_depth_H
        if table_data.rod_length_m:
            geo.params.stake_length_m = table_data.rod_length_m
        if table_data.rod_diameter_m:
            geo.params.stake_diameter_m = table_data.rod_diameter_m
        geo.params.is_radsan = table_data.is_radsan
        geo.params.radsan_step1_D = table_data.radsan_step1_D
        geo.params.radsan_step2_Rc = table_data.radsan_step2_Rc
        geo.params.radsan_step3_Ry = table_data.radsan_step3_Ry
        geo.params.radsan_step4_Re = table_data.radsan_step4_Re

    # ══════════════════════════════════════════════════════════
    #  ρ değeri — otomatik veya kullanıcı sorgulama
    # ══════════════════════════════════════════════════════════
    user_rho = args.rho

    # Paftada ρ bulunamadıysa ve CLI'dan da verilmediyse:
    if geo.params.rho_ohm_m is None and user_rho is None:
        if args.ask_rho:
            user_rho = _ask_rho()
        else:
            print("  ℹ Paftada ρ belirtilmemiş, yönetmelik standardı 100.0 Ω·m otomatik uygulandı.")
            user_rho = 100.0

    # Paftada ρ bulunduysa ekranda göster
    elif geo.params.rho_ohm_m is not None and user_rho is None:
        print(f"  ✓ Paftadan / Tablodan okunan ρ = {geo.params.rho_ohm_m:.1f} Ω·m [{geo.params.rho_source}]")
        user_rho = geo.params.rho_ohm_m

    # ══════════════════════════════════════════════════════════
    #  TIER 3: Deterministik Hesap
    # ══════════════════════════════════════════════════════════
    print("  [Tier 3] Topraklama direnci hesaplanıyor...")
    from core.tier3_calculator import CalculationEngine
    calc_engine = CalculationEngine()
    calc = calc_engine.calculate(geo, user_rho=user_rho)

    # ══════════════════════════════════════════════════════════
    #  TIER 3.5: AutoCAD Electrical Malzeme Kataloğu (BOM)
    # ══════════════════════════════════════════════════════════
    print("  [Tier 3.5] AutoCAD Electrical malzeme kataloğu (BOM) sorgulanıyor...")
    from core.acade_catalog import ACADECatalogEngine
    acade_engine = ACADECatalogEngine()
    
    rod_cnt = geo.params.stake_count if (geo.params.stake_count is not None and geo.params.stake_count > 0) else (geo.active_foundation_floor.rod_count if geo.active_foundation_floor else 4)
    clamp_cnt = geo.active_foundation_floor.clamp_count if geo.active_foundation_floor else 8
    busbar_cnt = geo.active_foundation_floor.busbar_count if (geo.active_foundation_floor and geo.active_foundation_floor.busbar_count > 0) else 1

    bom = acade_engine.generate_grounding_bom(
        conductor_type="30x3.5_galvaniz_lama",
        strip_length_m=geo.total_strip_length_m,
        rod_count=rod_cnt,
        clamp_count=clamp_cnt,
        busbar_count=busbar_cnt,
        project_name=input_path.stem
    )

    # ══════════════════════════════════════════════════════════
    #  TIER 4: Raporlama
    # ══════════════════════════════════════════════════════════
    print("  [Tier 4] Raporlar üretiliyor...")
    from core.tier4_reporter import Reporter
    reporter = Reporter(output_dir=output_dir)
    paths = reporter.write_all(drawing, geo, calc, bom=bom)

    # Terminal özeti
    reporter.print_summary(geo, calc, bom=bom)

    # Dosya listesi
    print("  Çıktı dosyaları:")
    for fmt, p in paths.items():
        print(f"    • {fmt.upper():<5}: {p}")
    print()

    # Otomatik HTML raporu açma (tarayıcıda)
    if "html" in paths and not args.no_open:
        try:
            import webbrowser
            html_uri = paths["html"].resolve().as_uri()
            print(f"  🌐 Rapor tarayıcınızda açılıyor: {html_uri}")
            webbrowser.open(html_uri)
        except Exception:
            pass


if __name__ == "__main__":
    main()
