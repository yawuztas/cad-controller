# -*- coding: utf-8 -*-
"""
CloudeCAD — Sıfır Kayıplı Evrensel Okuma, Raporlama & 2-Katmanlı DWG Teslimat Motoru
======================================================================================
İşlem Sırası (Kayıpsız Boru Hattı):
  1. Orijinal çizimden tam okuma (`build_canonical_model`), birim kalibrasyonu ve 4 disiplin
     sınıflandırması (`TOPRAKLAMA`, `SINYAL`, `ZAYIF_AKIM`, `KUVVETLI_AKIM`).
  2. Orijinal katman bilgileriyle %100 kayıpsız Metraj & Hesap Kontrolü (`pandapower`,
     `momepy`, `turkey_bina` / `ibb_metro`) ve Excel/Word/Markdown/HTML rapor üretimi.
  3. Teslimat için görsel sadeleştirme:
     - `1_MIMARI`: Yalnızca mimari/statik/mekanik altlık -> tek katman (`MIMARI`)
     - `2_ELEKTRIK`: Altlıksız saf çizim (`ELEKTRIK`) + gömülü Excel/Tablolar
       (`HESAPLAR_TABLOLAR`) -> **Maksimum 2 katman** (+ `.dwg` & `_DENETIM_BULGULARI`)
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
from typing import Optional

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
MOTOR_DIR = Path(__file__).resolve().parent

if str(MOTOR_DIR) not in sys.path:
    sys.path.insert(0, str(MOTOR_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cad_okuma import (
    analyze_multi_sheet_project,
    build_calculation_audit_report,
    build_canonical_model,
    build_project_inventory,
    classify_drawing_discipline,
    convert_dxf_to_dwg,
    deliver_annotated_dxf_and_dwg,
    save_calculation_audit_reports,
    save_inventory_reports,
    save_multi_sheet_reports,
    separate_and_simplify_to_two_layers,
)

GIRDI_DIR = ROOT / "01_girdi"
CIKTI_DIR = ROOT / "04_cikti"
MIMARI_DIR = CIKTI_DIR / "1_mimari_ve_cevre"
DUZENLENMIS_DIR = CIKTI_DIR / "3_duzenlenmis_elektrik"
METRAJ_DIR = CIKTI_DIR / "4_metraj"
DENETIM_DIR = CIKTI_DIR / "5_hesap_kontrol"


def run_single_file_project(filepath: Path, *, profil: str = "auto", export_dwg: bool = True) -> None:
    """
    Tek `.dwg`/`.dxf` projesi için:
      1-3) Orijinalden kayıpsız okuma, Metraj ve Hesap Kontrolü (+ pandapower)
      4)   Saf 1-layer Mimari + maks 2-layer Elektrik/Hesap DXF/DWG + `_DENETIM_BULGULARI`
    """
    stem = filepath.stem
    t0 = time.time()
    print(f"\n{'-' * 76}")
    print(f"[TEK DOSYA] İŞLENİYOR: {filepath.name}")

    # 1. Orijinal katmanlarla kayıpsız CAD okuma + disiplin sınıflandırma
    snapshot, model = build_canonical_model(filepath, use_cache=True)
    disc, _ = classify_drawing_discipline(snapshot, model, source_path=str(filepath))
    unit_info = model.unit
    sch_nodes = sum(len(g.nodes) for g in model.schematics)
    print(
        f"  ✓ [Adım 1] Disiplin={disc} | Birim={unit_info.unit_name} ({unit_info.du_to_m:.4f} m/DU) | "
        f"Pafta={len(model.sheets)}, Tablo={len(model.tables)}, Şema Düğümü={sch_nodes}"
    )

    # 2. Orijinal katmanlarla %100 kayıpsız Metraj (.docx, .xlsx, .md, .json)
    METRAJ_DIR.mkdir(parents=True, exist_ok=True)
    inv = build_project_inventory(snapshot, model)
    save_inventory_reports(inv, METRAJ_DIR, sheets=model.sheets)
    print(
        f"  ✓ [Adım 2] Metraj: {len(inv.symbol_bom)} sembol tipi ({sum(x.total_count for x in inv.symbol_bom)} adet), "
        f"{len(inv.cable_bom)} kablo satırı -> {METRAJ_DIR.relative_to(ROOT)}"
    )

    # 3. Orijinal katmanlarla %100 kayıpsız Hesap Denetimi (+ pandapower)
    DENETIM_DIR.mkdir(parents=True, exist_ok=True)
    req_pack = "ibb_metro" if profil == "metro" else ("turkey_bina" if profil == "bina" else "auto")
    report = build_calculation_audit_report(snapshot, model, inventory=inv, rule_pack=req_pack)
    save_calculation_audit_reports(report, DENETIM_DIR, base_name=f"{stem}_hesap_kontrol")
    sc = report.summary_counts
    pp_note = (
        f" | pandapower max %e={report.network_analysis.max_voltage_drop_pct:.2f}"
        if (report.network_analysis and report.network_analysis.converged)
        else ""
    )
    print(
        f"  ✓ [Adım 3] Hesap Denetimi: KRITIK={sc.get('KRITIK', 0)}, UYARI={sc.get('UYARI', 0)}, "
        f"UYGUN={sc.get('UYGUN', 0)}{pp_note}"
    )

    # 4. 2-Katman Sadeleştirme (1_MIMARI tek katman + 2_ELEKTRIK maks 2 katman) + DWG & Redline
    MIMARI_DIR.mkdir(parents=True, exist_ok=True)
    DUZENLENMIS_DIR.mkdir(parents=True, exist_ok=True)
    arch_dxf = MIMARI_DIR / f"{stem}_1_MIMARI.dxf"
    elec_dxf = DUZENLENMIS_DIR / f"{stem}_2_ELEKTRIK.dxf"
    merged_dxf = DUZENLENMIS_DIR / f"{stem}_birlesik_sade.dxf"
    stats = separate_and_simplify_to_two_layers(
        snapshot.dxf_path,
        snapshot,
        model,
        out_arch_dxf=arch_dxf,
        out_elec_dxf=elec_dxf,
        out_merged_dxf=merged_dxf,
        heal_wires=True,
    )
    dwg_note = "DXF"
    if export_dwg:
        d_elec = convert_dxf_to_dwg(elec_dxf, elec_dxf.with_suffix(".dwg"))
        ann_res, dwg_res = deliver_annotated_dxf_and_dwg(
            merged_dxf,
            report,
            DENETIM_DIR,
            base_name=f"{stem}_denetim_bulgulu",
            convert_clean_dwg_path=merged_dxf.with_suffix(".dwg"),
        )
        dwg_ok = (d_elec.success and d_elec.dwg_path) and (dwg_res and dwg_res.success)
        dwg_note = f"DWG+Redline({ann_res.clouds_drawn} bulut)" if dwg_ok else "DXF (DWG kısmi)"
    print(
        f"  ✓ [Adım 4] Sade Çizim: Mimari={stats['arch_msp_layers']} | "
        f"Elektrik={stats['elec_msp_layers']} (onarım={stats['wire_heals']}) | {dwg_note}"
    )
    print(f"  Tamamlandı ({time.time() - t0:.1f} sn)")


def _detect_rule_pack_for_dir(folder: Path, forced_profil: str) -> str:
    if forced_profil == "metro":
        return "ibb_metro"
    if forced_profil == "bina":
        return "turkey_bina"
    name_u = folder.name.upper()
    if any(sub.is_dir() and any(k in sub.name.upper() for k in ("KUVVETLI", "TOPRAK", "ZAYIF")) for sub in folder.iterdir()):
        return "ibb_metro"
    if any(k in name_u for k in ("METRO", "ISTASYON", "M09", "RAYLI")):
        return "ibb_metro"
    return "turkey_bina"


def run_multi_sheet_folder(
    folder: Path,
    *,
    profil: str = "auto",
    dxf_override_dir: Optional[Path] = None,
    extract_enclosures: bool = True,
    export_two_layer: bool = True,
    export_dwg: bool = True,
) -> None:
    """
    Çoklu pafta klasörünü (Metro / Büyük Tesis) kayıpsız tarar; metraj, kural denetimi,
    plotly HTML ve 4-disipline göre ayrılmış 1_MIMARI + 2_ELEKTRIK çizimlerini üretir.
    """
    t0 = time.time()
    rule_pack = _detect_rule_pack_for_dir(folder, profil)
    print(f"\n{'-' * 76}")
    print(f"[ÇOKLU PAFTA] İŞLENİYOR: {folder.name} (Profil: {rule_pack})")

    out_dir = CIKTI_DIR / f"coklu_{folder.name}"
    two_layer_dir = (out_dir / "disiplin_ve_2layer_cizimler") if export_two_layer else None

    rep = analyze_multi_sheet_project(
        folder,
        rule_pack=rule_pack,
        dxf_override_dir=dxf_override_dir,
        use_cache=True,
        extract_enclosures=extract_enclosures,
        export_two_layer_dir=two_layer_dir,
        export_dwg=export_dwg,
    )
    paths = save_multi_sheet_reports(rep, out_dir, base_name=f"{folder.name}_denetim")
    print(
        f"  ✓ Taranan: {rep.files_scanned} pafta (Atlanan kopya: {len(rep.files_skipped_duplicates)}) | "
        f"Disiplinler: {rep.discipline_breakdown}"
    )
    print(
        f"  ✓ Ring: {len(rep.grounding_loops)}, Tava tipi: {len(rep.tray_inventory)}, "
        f"Trafo(kVA): {rep.transformer_ratings_kva}"
    )
    print(f"  ✓ Bulgular: {rep.summary_counts} -> {paths['html']}")
    if two_layer_dir is not None:
        print(f"  ✓ Disiplin & 2-Layer Çizimler: {two_layer_dir}")
    print(f"  Tamamlandı ({time.time() - t0:.1f} sn)")


def main() -> None:
    parser = argparse.ArgumentParser(description="CloudeCAD Evrensel Bina & Metro Denetim Motoru")
    parser.add_argument("--girdi", type=str, default="", help="Özel DWG/DXF dosyası veya çoklu pafta proje klasörü")
    parser.add_argument("--profil", choices=("auto", "bina", "metro"), default="auto", help="Mevzuat/şartname profili")
    parser.add_argument("--dxf-onbellek", type=str, default="", help="Hazır DXF klasörü (varsa DWG yerine doğrudan okur)")
    parser.add_argument("--dwg-yok", action="store_true", help="Yalnızca DXF ve raporları üret, .dwg dönüşümünü atla")
    parser.add_argument("--iki-katman-yok", action="store_true", help="Çoklu pafta klasöründe 2-katman DXF dışa aktarımını atla")
    args = parser.parse_args()

    print("=" * 76)
    print("  CLOUDECAD — KAYIPSIZ RAPORLAMA & 2-KATMANLI (MIMARI / ELEKTRIK+HESAP) MOTOR")
    print("=" * 76)

    dxf_ovr = Path(args.dxf_onbellek) if args.dxf_onbellek else None
    export_dwg = not args.dwg_yok
    export_two_layer = not args.iki_katman_yok

    if args.girdi:
        target = Path(args.girdi)
        if not target.exists():
            print(f"[HATA] Girdi yolu bulunamadı: {target}")
            return
        if target.is_file():
            run_single_file_project(target, profil=args.profil, export_dwg=export_dwg)
        else:
            run_multi_sheet_folder(
                target,
                profil=args.profil,
                dxf_override_dir=dxf_ovr,
                export_two_layer=export_two_layer,
                export_dwg=export_dwg,
            )
        return

    raw_candidates = sorted(list(GIRDI_DIR.glob("*.dwg")) + list(GIRDI_DIR.glob("*.dxf")))
    file_candidates = [
        c for c in raw_candidates
        if not any(k in c.name.upper() for k in ("YEDEK", "BAK", "BACKUP", "~"))
    ]
    dir_candidates = sorted(
        d for d in GIRDI_DIR.iterdir()
        if d.is_dir() and any(p.suffix.lower() in (".dwg", ".dxf") for p in d.rglob("*"))
    )

    if not file_candidates and not dir_candidates:
        print(f"\n[UYARI] '{GIRDI_DIR}' klasöründe incelenecek DWG/DXF dosyası veya proje alt klasörü bulunamadı.")
        return

    print(f"Tekil dosya sayısı: {len(file_candidates)} | Çoklu pafta klasör sayısı: {len(dir_candidates)}")
    for filepath in file_candidates:
        run_single_file_project(filepath, profil=args.profil, export_dwg=export_dwg)
    for folder in dir_candidates:
        run_multi_sheet_folder(
            folder,
            profil=args.profil,
            dxf_override_dir=dxf_ovr,
            export_two_layer=export_two_layer,
            export_dwg=export_dwg,
        )


if __name__ == "__main__":
    main()
