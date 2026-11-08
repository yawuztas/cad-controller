# -*- coding: utf-8 -*-
"""
CloudeCAD v3.0 — Teslimat Bestecisi (Composer)
===============================================
1. Onaylanmış temiz DXF'i AutoCAD Core Console (accoreconsole.exe) üzerinden
   DWG'ye çevirir (DXFIN yerine doğrudan /i girdisi + SAVEAS 2018).
2. Pafta bazlı teslim paketini delivery/ altında toplar:
   DWG + DXF + redline PNG + planlar + pafta mesuliyet defteri + README.
3. Job seviyesinde RAPOR.md + MESULIYET_DEFTERI.json kopyaları ile manifest üretir.
"""
import sys, os, json, shutil, subprocess, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Optional

import ezdxf

sys.stdout.reconfigure(encoding="utf-8")


def find_accoreconsole() -> Path:
    for year in range(2030, 2018, -1):
        p = Path(rf"C:\Program Files\Autodesk\AutoCAD {year}\accoreconsole.exe")
        if p.exists():
            return p
    base = Path(r"C:\Program Files\Autodesk")
    if base.exists():
        for sub in sorted(base.iterdir(), reverse=True):
            cand = sub / "accoreconsole.exe"
            if cand.exists():
                return cand
    import shutil as _sh
    which = _sh.which("accoreconsole.exe")
    return Path(which) if which else None


def strip_block_splines(src_dxf: Path, dst_dxf: Path) -> int:
    """Blok tanımları içindeki SPLINE varlıklarını çıkarır (Revit debris altlık temizliği).
    Elektriksel hatlar LINE/LWPOLYLINE olduğundan mühendislik içerik kaybı oluşmaz."""
    doc = ezdxf.readfile(str(src_dxf))
    removed = 0
    for blk in doc.blocks:
        if blk.name.startswith("*"):
            continue
        for e in list(blk):
            if e.dxftype() == "SPLINE":
                blk.delete_entity(e)
                removed += 1
    doc.saveas(str(dst_dxf))
    return removed


def dxf_to_dwg_via_console(dxf_path: Path, dwg_path: Path, timeout: int = 240) -> Tuple[Path, dict]:
    """Temiz DXF'i accoreconsole ile DWG 2018 formatına çevirir.
    NOT: Script içinde boşluklu yol AutoCAD'de 'Enter' sayılır; bu yüzden DWG
    önce boşluksuz geçici yolda üretilir, sonra hedefe taşınır."""
    console = find_accoreconsole()
    if not console:
        raise FileNotFoundError("accoreconsole.exe bulunamadı; DWG dönüşümü yapılamaz.")
    dwg_path.parent.mkdir(parents=True, exist_ok=True)
    if dwg_path.exists():
        dwg_path.unlink()

    stem = dxf_path.stem[:40]
    tmp_dwg = Path(tempfile.gettempdir()) / f"ccad_out_{os.getpid()}_{stem}.dwg"
    if tmp_dwg.exists():
        tmp_dwg.unlink()

    info = {"fallback": False, "splines_removed": 0, "fallback_dxf": ""}

    scr_path = Path(tempfile.gettempdir()) / f"ccad_saveas_{os.getpid()}_{stem}.scr"
    scr_lines = [
        "FILEDIA 0",
        "_SAVEAS",
        "2018",
        str(tmp_dwg.resolve()),
        "FILEDIA 1",
    ]
    scr_path.write_text("\n".join(scr_lines) + "\n", encoding="ascii", errors="replace")

    def _run(src: Path) -> bool:
        scr_path.write_text("\n".join(scr_lines) + "\n", encoding="ascii", errors="replace")
        cmd = [str(console), "/i", str(src.resolve()), "/s", str(scr_path)]
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        scr_path.unlink(missing_ok=True)
        return tmp_dwg.exists()

    ok = _run(dxf_path)
    if not ok:
        # FALLBACK: ezdxf roundtrip'i AutoCAD'in sindiremediği içerik (tipik sebep:
        # blok içi Revit debris SPLINE'lar) -> SPLINE'ları çıkarıp yeniden dene.
        try:
            fallback_dxf = dxf_path.with_name(dxf_path.stem + "_altilik_splinesiz.dxf")
            removed = strip_block_splines(dxf_path, fallback_dxf)
        except Exception:
            removed = 0
        if removed > 0:
            ok = _run(fallback_dxf)
            if ok:
                info.update({"fallback": True, "splines_removed": removed,
                             "fallback_dxf": str(fallback_dxf)})
                shutil.copy2(fallback_dxf, dxf_path.with_name(fallback_dxf.name))

    if not tmp_dwg.exists():
        raise RuntimeError(f"DWG üretilemedi ({dwg_path.name}); fallback dahil başarısız.")

    shutil.move(str(tmp_dwg), str(dwg_path))
    for err_p in (Path.cwd() / 'ErrorReports', Path(__file__).resolve().parents[2] / 'ErrorReports'):
        if err_p.exists():
            shutil.rmtree(err_p, ignore_errors=True)
    return dwg_path, info


def _find_original_dwg(job_dir: Path, sheet_stem: str) -> Path:
    """Paftanın orijinal kaynak DWG dosyasını intake.yaml veya proje klasöründen bulur."""
    intake_p = job_dir / "intake.yaml"
    if intake_p.exists():
        try:
            intake = json.loads(intake_p.read_text(encoding="utf-8"))
            yollari = intake.get("pafta_yollari", {})
            if sheet_stem in yollari and Path(yollari[sheet_stem]).exists():
                return Path(yollari[sheet_stem])
        except Exception:
            pass
    root = Path(__file__).resolve().parents[1]
    for p in (root / "incelenecek projeler").rglob(f"{sheet_stem}.dwg"):
        return p
    return None


def _dwg_via_com_fallback(job_dir: Path, sheet_stem: str, dst_dwg: Path) -> Tuple[Path, dict]:
    """2. Kademe DWG Üretici: accoreconsole Revit artığı bloklarda çökerse
    orijinal DWG'yi AutoCAD COM otomasyonu ile açıp onaylı planları doğrudan uygular."""
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from common.com_dwgs import ComDwgApplier

    orig_dwg = _find_original_dwg(job_dir, sheet_stem)
    if orig_dwg is None or not orig_dwg.exists():
        raise FileNotFoundError(f"COM fallback için orijinal DWG bulunamadı: {sheet_stem}.dwg")

    cp_path = job_dir / "plans" / f"{sheet_stem}_change_plan.json"
    wp_path = job_dir / "plans" / f"{sheet_stem}_wire_plan.json"

    approve_layer, approve_wire = set(), set()
    if cp_path.exists():
        cp = json.loads(cp_path.read_text(encoding="utf-8"))
        for p in cp.get("proposals", []):
            st = p.get("status", "")
            if st == "APPROVED" or (p.get("auto_approvable") and st != "REJECTED"):
                approve_layer.add(p["proposal_id"])
    if wp_path.exists():
        wp = json.loads(wp_path.read_text(encoding="utf-8"))
        for p in wp.get("proposals", []):
            st = p.get("status", "")
            if st == "APPROVED" or (p.get("auto_approvable") and st != "REJECTED"):
                approve_wire.add(p["proposal_id"])

    dst_dwg.parent.mkdir(parents=True, exist_ok=True)
    if dst_dwg.exists():
        dst_dwg.unlink()

    applier = ComDwgApplier(visible=False)
    doc = None
    try:
        doc = applier.open(orig_dwg)
        rep = applier.apply_plan_json(doc, cp_path, wp_path, approve_layer, approve_wire)
        applier.saveas_dwg(doc, dst_dwg)
    finally:
        if doc is not None:
            applier.close(doc)

    if not dst_dwg.exists():
        raise RuntimeError(f"COM ile DWG kaydedilemedi: {dst_dwg.name}")
    return dst_dwg, {"com_fallback": True, **rep}


def _write_saha_recetesi(sheet_stem: str, op_data: dict, dst_path: Path) -> bool:
    """Varsa паfta için ASBUILT saha reçetesi talimat belgesi üretir."""
    props = op_data.get("proposals", [])
    if not props:
        return False
    lines = [
        f"# SAHA UYGULAMA TALİMATI (AS-BUILT REÇETE) — {sheet_stem}",
        "",
        f"**Tarih:** {datetime.now(timezone.utc).isoformat()}",
        "**Not:** Bu pafta AS-BUILT (sahada kurulu tesisat) statüsünde olduğundan faz/linye etiketleri",
        "çizim üzerinde sessizce değiştirilmemiştir. Aşağıdaki reçetenin saha ekibi tarafından",
        "pano klemens/şalter çıkışlarında fiziksel olarak uygulanması önerilir:",
        "",
    ]
    for i, p in enumerate(props, 1):
        st = p.get("status", "ASBUILT_FIELD_RECOMMENDATION_ONLY")
        durum = "MÜHENDİS ONAYLI SAHA TALİMATI" if st == "APPROVED" else (
            "REDDEDİLDİ" if st == "REJECTED" else "SAHA REÇETESİ ÖNERİSİ"
        )
        lines.extend([
            f"## {i}. {p.get('target_element', '-')} ({p.get('category', '-')}) — [{durum}]",
            f"- **Mevcut Durum:** {p.get('old_text', '-')}",
            f"- **Önerilen Saha Müdahalesi:** {p.get('new_text', '-')}",
            f"- **Mühendislik Kanıtı:** {p.get('verification_proof', '-')}",
            f"- **Teknik Gerekçe:** {p.get('reason', '-')}",
            "",
        ])
    dst_path.write_text("\n".join(lines), encoding="utf-8")
    return True


def compose_sheet(job_dir: Path, sheet_stem: str, engineer: dict) -> dict:
    """Tek paftanın teslim paketini oluşturur. Dönen dict: durum + yollar."""
    job_dir = Path(job_dir)
    out_dxf = job_dir / "output" / f"{sheet_stem}_temiz.dxf"
    if not out_dxf.exists():
        return {"sheet": sheet_stem, "status": "HATA", "message": f"Temiz DXF yok: {out_dxf.name}"}

    delivery_sheet = job_dir / "delivery" / sheet_stem
    delivery_sheet.mkdir(parents=True, exist_ok=True)

    # 1) DXF kopyası
    dxf_copy = delivery_sheet / out_dxf.name
    shutil.copy2(out_dxf, dxf_copy)

    # 2) DWG dönüşümü (Kademe 1: accoreconsole -> Kademe 2: AutoCAD COM Fallback)
    dwg_target = delivery_sheet / f"{sheet_stem}_temiz.dwg"
    dwg_msg = ""
    try:
        dwg, conv_info = dxf_to_dwg_via_console(out_dxf, dwg_target)
        dwg_msg = f"{dwg.stat().st_size // 1024} KB"
        if conv_info.get("fallback"):
            dwg_msg += (f" (ALTIK SADELEŞTİRİLDİ: blok içi {conv_info['splines_removed']} SPLINE çıkarıldı — "
                        f"Revit debris altlığı; temiz DXF kopyası: {Path(conv_info['fallback_dxf']).name})")
    except Exception as console_err:
        try:
            dwg, com_info = _dwg_via_com_fallback(job_dir, sheet_stem, dwg_target)
            dwg_msg = (f"{dwg.stat().st_size // 1024} KB "
                       f"(COM-DWG KADEMESİ: layer={com_info.get('layer_applied', 0)}, "
                       f"wire={com_info.get('wire_applied', 0)})")
        except Exception as com_err:
            dwg_msg = f"DÖNÜŞÜM HATASI: Console({console_err}) | COM({com_err})"

    # 3) Redline + planlar + pafta defteri + saha reçetesi
    red_src = job_dir / "redline" / f"{sheet_stem}.png"
    if red_src.exists():
        shutil.copy2(red_src, delivery_sheet / red_src.name)
    plans_dir = delivery_sheet / "plans"
    plans_dir.mkdir(exist_ok=True)
    for suffix in ("_change_plan.json", "_wire_plan.json", "_optimizer.json"):
        src = job_dir / "plans" / f"{sheet_stem}{suffix}"
        if src.exists():
            shutil.copy2(src, plans_dir / src.name)
    op_src = job_dir / "plans" / f"{sheet_stem}_optimizer.json"
    if op_src.exists():
        try:
            op_data = json.loads(op_src.read_text(encoding="utf-8"))
            _write_saha_recetesi(sheet_stem, op_data, delivery_sheet / "SAHA_RECETESI.md")
        except Exception:
            pass
    applied_src = job_dir / "applied" / f"{sheet_stem}_applied_changes.json"
    if applied_src.exists():
        applied_dir = delivery_sheet / "applied"
        applied_dir.mkdir(exist_ok=True)
        shutil.copy2(applied_src, applied_dir / applied_src.name)

    # 4) Pafta README
    readme = [
        f"CLOUDECAD v3.0 — TESLİM PAKETİ: {sheet_stem}",
        f"Üretim: {datetime.now(timezone.utc).isoformat()}",
        f"Mühendis: {engineer.get('adi')} ({engineer.get('unvan')}) — Yetki Belge No: {engineer.get('yetki_belge_no')}",
        f"DWG: {'üretildi (' + dwg_msg + ')' if not dwg_msg.startswith('DÖNÜŞÜM') else dwg_msg}",
        "",
        "İçerik:",
        "  *_temiz.dwg / *_temiz.dxf  -> Onaylanmış değişikliklerle temizlenmiş pafta",
        "  redline PNG                -> Uygulanan müdahalelerin görsel haritası",
        "  plans/*.json               -> Öneri planları (onaylı + onay bekleyen + reddedilen)",
        "  applied/*.json             -> Pafta mesuliyet defteri (SHA-256 imzalı kayıtlar)",
        "  SAHA_RECETESI.md (varsa)   -> Pano/linye faz dengeleme saha uygulama talimatı",
        "",
        "NOT: plans/ içinde status'u REQUIRES_APPROVAL / NOT_SELECTED olan maddeler",
        "uygulanmamıştır; mühendis onayı beklemektedir.",
    ]
    (delivery_sheet / "README.txt").write_text("\n".join(readme), encoding="utf-8")

    return {
        "sheet": sheet_stem,
        "status": "OK" if not dwg_msg.startswith("DÖNÜŞÜM") else "OK_DXF_ONLY",
        "dxf": str(dxf_copy),
        "dwg": dwg_msg,
        "dir": str(delivery_sheet),
    }


def _classify_counts(proposals: list) -> Tuple[int, int, int]:
    """(onaylanan_veya_otomatik, bekleyen, reddedilen) sayılarını döndürür."""
    app, wait, rej = 0, 0, 0
    for p in proposals:
        st = p.get("status", "")
        if st == "REJECTED":
            rej += 1
        elif st == "APPROVED" or (p.get("auto_approvable") and st == "PROPOSED"):
            app += 1
        else:
            wait += 1
    return app, wait, rej


def regen_rapor(job_dir: Path) -> Path:
    """Plan JSON'larından ve mesuliyet defterinden RAPOR.md'yi güncel durumla yeniden üretir."""
    job_dir = Path(job_dir)
    lines = [
        "# JOB — Birleşik Denetim + Onarım Raporu (güncel)",
        "",
        f"**Yenilendi:** {datetime.now(timezone.utc).isoformat()}",
        "",
        "| Pafta | Layer (UYGULANAN / BEKLEYEN / RED) | Wire (UYGULANAN / BEKLEYEN / RED) | Optimizer Saha Reçetesi |",
        "| :--- | :--- | :--- | :--- |",
    ]
    total_app = 0
    saha_lines = [
        "# SAHA UYGULAMA REÇETELERİ (AS-BUILT FAZ DENGELEME TALİMATLARI)",
        "",
        f"**Üretim:** {datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    has_saha = False
    for f in sorted((job_dir / "plans").glob("*_change_plan.json")):
        stem = f.name[: -len("_change_plan.json")]
        cp = json.loads(f.read_text(encoding="utf-8"))
        wire_f = job_dir / "plans" / f"{stem}_wire_plan.json"
        wp = json.loads(wire_f.read_text(encoding="utf-8")) if wire_f.exists() else {"proposals": []}
        op_f = job_dir / "plans" / f"{stem}_optimizer.json"
        op = json.loads(op_f.read_text(encoding="utf-8")) if op_f.exists() else {"proposals": []}

        c_app, c_wait, c_rej = _classify_counts(cp.get("proposals", []))
        w_app, w_wait, w_rej = _classify_counts(wp.get("proposals", []))
        o_props = op.get("proposals", [])
        o_cnt = sum(1 for p in o_props if p.get("status") != "REJECTED")
        total_app += c_app + w_app
        lines.append(
            f"| {stem[:44]} | {c_app} / {c_wait} / {c_rej} | "
            f"{w_app} / {w_wait} / {w_rej} | {o_cnt} |"
        )
        if o_props:
            has_saha = True
            saha_lines.append(f"## Pafta: `{stem}`")
            for p in o_props:
                st = p.get("status", "ASBUILT_FIELD_RECOMMENDATION_ONLY")
                etiket = "ONAYLI SAHA TALİMATI" if st == "APPROVED" else (
                    "REDDEDİLDİ" if st == "REJECTED" else "ÖNERİLEN SAHA REÇETESİ"
                )
                saha_lines.extend([
                    f"- **Pano / Hedef:** `{p.get('target_element', '-')}` — **[{etiket}]**",
                    f"  - **Mevcut:** {p.get('old_text', '-')}",
                    f"  - **Saha Talimatı:** {p.get('new_text', '-')}",
                    f"  - **Kanıt:** {p.get('verification_proof', '-')}",
                    "",
                ])
    led_f = job_dir / "RESPONSIBILITE_DEFTERI.json"
    if led_f.exists():
        led = json.loads(led_f.read_text(encoding="utf-8"))
        led_cnt = led.get("total_changes", total_app)
        lines.append("")
        lines.append(f"**Toplam uygulanan değişiklik:** {total_app} (Mesuliyet defteri kaydı: {led_cnt}, SHA-256 imzalı)")
    lines.append("")
    lines.append("### Kural Uyarısı")
    lines.append("- `REQUIRES_APPROVAL` / `NOT_SELECTED` maddeler uygulanmamıştır; Onay İstasyonu kararı bekler.")
    lines.append("- ASBUILT işlerde faz etiketi DWG'de değiştirilmez; yalnızca saha reçetesi (`SAHA_RECETELERI.md`) üretilir.")
    out = job_dir / "RAPOR.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    if has_saha:
        saha_out = job_dir / "SAHA_RECETELERI.md"
        saha_out.write_text("\n".join(saha_lines), encoding="utf-8")
        if (job_dir / "delivery").exists():
            shutil.copy2(saha_out, job_dir / "delivery" / "SAHA_RECETELERI.md")
    return out


def compose_job(job_dir: Path, sheets: list, engineer: dict) -> dict:
    """Tüm paftaları + job seviyesi belgeleri delivery/ altında toplar."""
    job_dir = Path(job_dir)
    rapor = regen_rapor(job_dir)  # RAPOR.md'yi en güncel karar durumuyla tazele
    results = [compose_sheet(job_dir, s, engineer) for s in sheets]

    # Job seviyesi kopyalar
    for name in ("RAPOR.md", "SAHA_RECETELERI.md", "RESPONSIBILITE_DEFTERI.json", "intake.yaml"):
        src = job_dir / name
        if src.exists():
            shutil.copy2(src, job_dir / "delivery" / name)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engineer": engineer,
        "sheets": [{k: v for k, v in r.items() if k != "dir"} for r in results],
    }
    (job_dir / "delivery" / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"results": results, "manifest": str(job_dir / "delivery" / "MANIFEST.json")}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="compose_delivery")
    ap.add_argument("--job", default=r"D:\autocad projesi\jobs\JOB-2026-S19-SAHA-01")
    ap.add_argument("--sheets", default="", help="Virgülle ayrılmış pafta stem'leri; boşsa hepsi")
    args = ap.parse_args()

    job_dir = Path(args.job)
    intake = json.loads((job_dir / "intake.yaml").read_text(encoding="utf-8"))
    engineer = intake.get("muhendis", {"adi": "[MÜHENDİS]", "unvan": "Elektrik Müh.", "yetki_belge_no": "-"})
    if args.sheets:
        sheets = [s.strip() for s in args.sheets.split(",")]
    else:
        sheets = [f.stem.replace("_temiz", "") for f in (job_dir / "output").glob("*_temiz.dxf")]

    print(f"Composer başladı: {len(sheets)} pafta")
    res = compose_job(job_dir, sheets, engineer)
    for r in res["results"]:
        print(f"  [{r['status']:>11}] {r['sheet']} | DWG: {r.get('dwg', '-')}")
    print(f"Manifest: {res['manifest']}")
