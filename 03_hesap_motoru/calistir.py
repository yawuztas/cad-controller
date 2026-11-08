# -*- coding: utf-8 -*-
"""
CloudeCAD — Ana Hesap ve Onarım Motoru (03_hesap_motoru/calistir.py)
=====================================================================
Bu betik, kullanıcının istediği 4 aşamalı temiz hattı yürütür:
  1. 01_girdi/ altındaki tüm DWG ve DXF dosyalarını okur.
  2. 02_mevzuat_ve_formuller/ altındaki kurallara (İBB Metro / Türkiye Bina / BYKHY) göre denetler.
  3. 03_hesap_motoru çekirdeği ile katmanları ayıklar, kopuk kabloları diker, faz dengesini çözer.
  4. Sonuçları 04_cikti/ altına eksiksiz teslim eder (Temiz DWG, Raporlar, Reçeteler, Defter).
"""
import sys
import os
import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
MOTOR_DIR = Path(__file__).resolve().parent

if str(MOTOR_DIR) not in sys.path:
    sys.path.insert(0, str(MOTOR_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common.dxf_converter import ensure_dxf
from core.cad.reader import UniversalCADReader
from core.cad.triage import SymbolTriage
from core.healer.layer_doctor import LayerAndBlockDoctor
from core.healer.wire_healer import TopologicalWireHealer
from core.healer.electrical_optimizer import (
    ElectricalAutoOptimizer, ElectricalOptimizationPlan,
)
from core.rules.rule_engine import RuleEngine
from tools.compose_delivery import dxf_to_dwg_via_console, _dwg_via_com_fallback

GIRDI_DIR = ROOT / "01_girdi"
MEVZUAT_DIR = ROOT / "02_mevzuat_ve_formuller"
CIKTI_DIR = ROOT / "04_cikti"

TEMIZ_CIZIM_DIR = CIKTI_DIR / "temiz_cizimler"
RAPOR_DIR = CIKTI_DIR / "raporlar"
SAHA_DIR = CIKTI_DIR / "saha_receteleri"

for d in (TEMIZ_CIZIM_DIR, RAPOR_DIR, SAHA_DIR):
    d.mkdir(parents=True, exist_ok=True)


def sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def count_entities(doc):
    c = {}
    for ent in doc.modelspace():
        t = ent.dxftype()
        c[t] = c.get(t, 0) + 1
    return c


def main():
    print("=" * 72)
    print("  CLOUDECAD — MÜHENDİSLİK HESAP VE OTOMATİK ONARIM MOTORU")
    print("=" * 72)
    print(f"  [1] Girdi Klasörü:    {GIRDI_DIR.relative_to(ROOT)}")
    print(f"  [2] Mevzuat Paketi:   {MEVZUAT_DIR.relative_to(ROOT)} (ibb_metro / turkey_bina)")
    print(f"  [3] Hesap Motoru:     {MOTOR_DIR.relative_to(ROOT)}")
    print(f"  [4] Çıktı Klasörü:    {CIKTI_DIR.relative_to(ROOT)}")
    print("=" * 72)

    candidates = sorted(list(GIRDI_DIR.glob("*.dwg")) + list(GIRDI_DIR.glob("*.dxf")))
    if not candidates:
        print("\n[UYARI] '01_girdi' klasöründe incelenecek DWG veya DXF bulunamadı!")
        print("Lütfen incelenmesini istediğiniz çizimleri '01_girdi' içine kopyalayın.\n")
        return

    print(f"\nİncelenecek Pafta Sayısı: {len(candidates)}")
    for i, c in enumerate(candidates, 1):
        print(f"  {i}. {c.name} ({round(c.stat().st_size / 1024, 1)} KB)")

    rule_engine = RuleEngine.get_instance(default_pack="ibb_metro")
    reader = UniversalCADReader(use_cache=True)
    t_start = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    all_ledger = []
    sheet_summaries = []
    saha_receteleri_all = []

    for idx, filepath in enumerate(candidates, 1):
        stem = filepath.stem
        t0 = time.time()
        print(f"\n{'-' * 72}")
        print(f"[{idx}/{len(candidates)}] İŞLENİYOR: {filepath.name}")

        # 1. DXF Hazırla
        dxf_path = ensure_dxf(filepath, use_cache=True)
        print(f"  ✓ DXF Ayrıştırıldı: {Path(dxf_path).name}")

        # 2. Geometri Okuma ve Triyaj
        sc = reader.read(filepath)
        triage_counts = SymbolTriage.triage(sc.symbols, sc.texts)
        print(f"  ✓ Sahne Analizi: {len(sc.symbols)} sembol, {len(sc.texts)} metin, {len(sc.logical_circuits)} linye devresi")

        doc = ezdxf.readfile(str(dxf_path))
        counts_before = count_entities(doc)

        # 3. Layer Doctor (Mimariyi Ayıkla, Elektriği Standartlaştır)
        plan_ld = LayerAndBlockDoctor.analyze_and_propose(
            doc, symbols=sc.symbols, routes=sc.physical_routes, drawing_name=filepath.name
        )
        auto_layer_ids = {p.proposal_id for p in plan_ld.proposals if p.auto_approvable}
        applied_ld = LayerAndBlockDoctor.apply_plan(doc, plan_ld, approved_proposal_ids=auto_layer_ids)
        print(f"  ✓ Katman Doktoru: {len(applied_ld)} mimari/elektrik elemanı düzenlendi (Korunan: {plan_ld.summary_counts.get('total_safety_skipped', 0)})")

        # 4. Wire Healer (Kopuk Hatları Dik, Çift Çizgileri Temizle, Snap Yap)
        plan_wh = TopologicalWireHealer.analyze_and_propose(
            doc, symbols=sc.symbols, texts=sc.texts, drawing_name=filepath.name
        )
        auto_wire_ids = {p.proposal_id for p in plan_wh.proposals if p.auto_approvable}
        applied_wh = TopologicalWireHealer.apply_plan(doc, plan_wh, approved_proposal_ids=auto_wire_ids)
        print(f"  ✓ Kablo Onarıcı: {len(applied_wh)} müdahale (Çift çizgi silme: {plan_wh.summary_counts.get('duplicates_found', 0)}, Otomatik köprü: {plan_wh.summary_counts.get('collinear_stitches_auto', 0)})")

        # 5. Temiz DXF Kaydet
        out_clean_dxf = TEMIZ_CIZIM_DIR / f"{stem}_temiz.dxf"
        doc.saveas(str(out_clean_dxf))

        # 6. Temiz DWG Üret (Kademe 1: accoreconsole -> Kademe 2: COM fallback)
        out_clean_dwg = TEMIZ_CIZIM_DIR / f"{stem}_temiz.dwg"
        dwg_status = "ÜRETİLDİ"
        try:
            dxf_to_dwg_via_console(out_clean_dxf, out_clean_dwg)
            print(f"  ✓ DWG 2018 Üretildi: {out_clean_dwg.name} ({round(out_clean_dwg.stat().st_size / 1024, 1)} KB)")
        except Exception as e_console:
            try:
                # Orijinal DWG üzerinden COM ile uygula
                if filepath.suffix.lower() == ".dwg":
                    _dwg_via_com_fallback(ROOT / "jobs" / "JOB-2026-S19-SAHA-01", stem, out_clean_dwg)
                    print(f"  ✓ DWG 2018 (COM Kademesi ile) Üretildi: {out_clean_dwg.name}")
                else:
                    dwg_status = f"Console Hatası: {e_console}"
            except Exception as e_com:
                dwg_status = f"Hata: {e_console} | COM: {e_com}"
                print(f"  ⚠ DWG Üretilemedi (DXF hazır): {dwg_status}")

        # 7. As-Built Optimizasyon & Pano Faz Dengesi
        plan_op = ElectricalOptimizationPlan(
            drawing_name=filepath.name, job_type="ASBUILT", rule_pack="ibb_metro", created_at=now_iso
        )
        panels = {}
        for lc in sc.logical_circuits:
            ph_raw = (lc.phase or "").upper()
            is3 = ph_raw in ("3F", "RST", "L1L2L3") or ("L1" in ph_raw and "L2" in ph_raw)
            panels.setdefault(lc.panel_tag, []).append({
                "circuit_id": lc.circuit_no,
                "power_w": float(lc.total_power_w or 0.0),
                "phase": lc.phase,
                "is_3phase": is3,
                "dxf_handle": "",
                "raw_text": "",
            })
        for ptag, circuits in panels.items():
            if len(circuits) >= 3:
                ElectricalAutoOptimizer.propose_phase_balance(plan_op, ptag, circuits, rule_engine=rule_engine)

        if plan_op.proposals:
            print(f"  ✓ Pano Optimizasyonu: {len(plan_op.proposals)} saha faz dengeleme reçetesi üretildi")
            for p in plan_op.proposals:
                saha_receteleri_all.append({"pafta": stem, **p.to_dict()})

        # 8. Redline PNG Haritası Çiz
        fig, ax = plt.subplots(figsize=(10, 7))
        ax.set_title(f"MÜHENDİSLİK REDLİNE — {stem}\n(Gri: Mimariye Taşınan | Mavi: Elektrik Katmanı | Yeşil: Kablo Köprüsü)", fontsize=9)
        for p in plan_ld.proposals:
            if p.status == "APPROVED":
                try:
                    ent = doc.entitydb.get(p.dxf_handle)
                    if ent and ent.dxftype() == "INSERT":
                        c = "#9AA0A6" if p.new_layer == "A-MIMARI-ALTYAPI" else "#1A73E8"
                        ax.scatter(ent.dxf.insert.x, ent.dxf.insert.y, s=6, c=c, alpha=0.6)
                except Exception:
                    pass
        for a in applied_wh:
            if a.get("action") == "STITCH_COLLINEAR_GAP":
                pr = next((p for p in plan_wh.proposals if p.proposal_id == a["proposal_id"]), None)
                if pr:
                    ax.plot([pr.start_pt[0], pr.end_pt[0]], [pr.start_pt[1], pr.end_pt[1]], c="#188038", lw=1.5)
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.2)
        fig.tight_layout()
        redline_png = RAPOR_DIR / f"{stem}_redline.png"
        fig.savefig(str(redline_png), dpi=100)
        plt.close(fig)

        # Mesuliyet Kayıtları
        for r in applied_ld:
            all_ledger.append({"pafta": stem, "modul": "LayerDoctor", "proposal_id": r.proposal_id, "signature": r.signature_hash})
        for a in applied_wh:
            all_ledger.append({"pafta": stem, "modul": "WireHealer", "proposal_id": a.get("proposal_id"), "signature": sha16(f"{stem}|{a.get('proposal_id')}")})

        elapsed = time.time() - t0
        sheet_summaries.append({
            "pafta": stem,
            "layer_applied": len(applied_ld),
            "wire_applied": len(applied_wh),
            "opt_proposals": len(plan_op.proposals),
            "dwg_status": dwg_status,
            "sure_sn": round(elapsed, 1),
        })

    # --- NİHAİ RAPORLARI VE SAHA REÇETELERİNİ YAZ ---
    # 1. RESPONSIBILITE_DEFTERI.json
    ledger_path = RAPOR_DIR / "RESPONSIBILITE_DEFTERI.json"
    ledger_payload = {
        "generated_at": now_iso,
        "total_changes": len(all_ledger),
        "changes": all_ledger,
    }
    ledger_path.write_text(json.dumps(ledger_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. DENETIM_VE_ONARIM_RAPORU.md
    rapor_md = RAPOR_DIR / "DENETIM_VE_ONARIM_RAPORU.md"
    lines = [
        "# CLOUDECAD — Birleşik Mühendislik Denetim ve Onarım Raporu",
        "",
        f"**Tarih:** {now_iso}  ",
        f"**Toplam İşlenen Pafta:** {len(candidates)}  ",
        f"**Toplam Uygulanan Değişiklik:** {len(all_ledger)} (İmzalı Defter: `RESPONSIBILITE_DEFTERI.json`)  ",
        "",
        "## Pafta Bazlı Özet Tablosu",
        "",
        "| Pafta | Katman Düzeltmesi | Kablo Onarımı | Saha Faz Reçetesi | DWG 2018 Durumu | İşlem Süresi |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ]
    for s in sheet_summaries:
        lines.append(f"| {s['pafta']} | {s['layer_applied']} adet | {s['wire_applied']} adet | {s['opt_proposals']} adet | {s['dwg_status']} | {s['sure_sn']} sn |")

    lines.extend([
        "",
        "## Uygulanan Mühendislik Kuralları",
        "- **Mimari Altlık Koruması:** Tespit edilen mimari elemanlar `A-MIMARI-ALTYAPI` katmanına (Color 8, Kilitli) taşınarak elektrik hatları netleştirildi.",
        "- **Kablo Kopukluk Onarımı:** 4 katı koşulu sağlayan ve aralarında başka eleman olmayan kopuk uçlar doğrusal olarak birleştirildi; yan yana paralel hatlara dokunulmadı.",
        "- **Blok & XREF Koruması:** Blok tanımları ve XREF elemanları dokunulmaz kalkanla korundu; sadece INSERT referansları güncellendi.",
        "",
        "Detaylı görsel kırmızı hat incelemeleri için `04_cikti/raporlar/*_redline.png` haritalarına bakınız.",
    ])
    rapor_md.write_text("\n".join(lines), encoding="utf-8")

    # 3. SAHA_RECETELERI.md (Varsa)
    if saha_receteleri_all:
        saha_md = SAHA_DIR / "SAHA_RECETELERI.md"
        slines = [
            "# SAHA UYGULAMA REÇETELERİ (Pano Faz Dengeleme Talimatları)",
            "",
            f"**Tarih:** {now_iso}",
            "",
            "Aşağıdaki panolarda yüksek faz dengesizliği tespit edilmiştir. Çizim as-built (mevcut kurulu tesisat) olduğundan",
            "etiketler çizimde sessizce değiştirilmemiş; pano klemens çıkışlarında fiziksel olarak yapılması gereken",
            "linye faz aktarımları mühendislik hesabı ile reçetelendirilmiştir:",
            "",
        ]
        for p in saha_receteleri_all:
            slines.extend([
                f"### Pafta: `{p['pafta']}` — Hedef: `{p.get('target_element', '-')}`",
                f"- **Mevcut Durum:** {p.get('old_text', '-')}",
                f"- **Önerilen Saha Müdahalesi:** {p.get('new_text', '-')}",
                f"- **Mühendislik Kanıtı:** {p.get('verification_proof', '-')}",
                "",
            ])
        saha_md.write_text("\n".join(slines), encoding="utf-8")

    total_sec = round(time.time() - t_start, 1)
    print("\n" + "=" * 72)
    print(f"  İŞLEM BAŞARIYLA TAMAMLANDI! (Toplam Süre: {total_sec} sn)")
    print(f"  ✓ Temiz DWG/DXF Çıktıları: 04_cikti/temiz_cizimler/")
    print(f"  ✓ Denetim Raporu:          04_cikti/raporlar/DENETIM_VE_ONARIM_RAPORU.md")
    print(f"  ✓ İmzalı Defter:           04_cikti/raporlar/RESPONSIBILITE_DEFTERI.json")
    print(f"  ✓ Redline Görselleri:      04_cikti/raporlar/*_redline.png")
    if saha_receteleri_all:
        print(f"  ✓ Saha Reçeteleri:         04_cikti/saha_receteleri/SAHA_RECETELERI.md")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
