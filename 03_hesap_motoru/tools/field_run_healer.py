# -*- coding: utf-8 -*-
"""
CloudeCAD v3.0 — SAHA İNDİRİM TESTİ (JOB-2026-S19-SAHA-01)
===========================================================
Gerçek M09-S19_Masko paftaları üzerinde Healer zincirini koşar:
  Okuma(cache) -> Triyaj -> LayerDoctor -> WireHealer -> ASBUILT Optimizasyon
Çıktı: jobs/JOB-2026-S19-SAHA-01/ (temiz DXF, planlar, mesuliyet defteri, redline, RAPOR.md)
"""
import sys, os, json, time, hashlib
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"D:\autocad projesi")
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

NOW = datetime.now(timezone.utc)
JOB_DIR = ROOT / "jobs" / "JOB-2026-S19-SAHA-01"
for sub in ("output", "plans", "redline", "applied"):
    (JOB_DIR / sub).mkdir(parents=True, exist_ok=True)

MUEHENDIS = {
    "adi": "[MÜHENDİS ADI SOYADI]",
    "unvan": "Elektrik Mühendisi",
    "yetki_belge_no": "[YETKİ BELGESİ NO]",
    "job_type": "ASBUILT",
    "paket": "ibb_metro",
}

CANDIDATES = [
    ROOT / "incelenecek projeler/işsonları_duzenlenmis/M09-S19_Masko/03_Zayif_Akim/AG-USK-M09-S19-000-99-AX-02-A-T-2I-001.dwg",
    ROOT / "incelenecek projeler/işsonları_duzenlenmis/M09-S19_Masko/03_Zayif_Akim/AG-USK-M09-S19-000-99-TL-02-A-T-2I-001.dwg",
    ROOT / "incelenecek projeler/işsonları_duzenlenmis/M09-S19_Masko/03_Zayif_Akim/AG-USK-M09-S19-CT0-03-TL-03-A-T-2I-001.dwg",
    ROOT / "incelenecek projeler/işsonları_duzenlenmis/M09-S19_Masko/03_Zayif_Akim/AG-PRT-M09-S19-CT0-03-TL-11-A-T-2I-001-A.dwg",
    # Kuvvetli akım (linye/pano etiketleri burada -> faz dengeleme saha reçetesi bu paftalardan üretilir)
    ROOT / "incelenecek projeler/işsonları_duzenlenmis/M09-S19_Masko/01_Kuvvetli_Akim/AG-PRT-M09-S19-BT0-00-PS-08-A-T-2I-001-A.dwg",
    ROOT / "incelenecek projeler/işsonları_duzenlenmis/M09-S19_Masko/01_Kuvvetli_Akim/AG-PRT-M09-S19-CT0-03-PS-11-A-T-2I-001-A.dwg",
    ROOT / "incelenecek projeler/işsonları_duzenlenmis/M09-S19_Masko/01_Kuvvetli_Akim/AG-PRT-M09-S19-CT0-2A-PS-16-A-T-2I-001-0.dwg",
]
sheets = [p for p in CANDIDATES if p.exists()]
print(f"Seçilen pafta: {len(sheets)} / {len(CANDIDATES)}")
for p in CANDIDATES:
    if not p.exists():
        print(f"  [ATLANDI - yok] {p.name}")

intake = {
    "job_id": "JOB-2026-S19-SAHA-01",
    "musteri": "[İÇ TEST - MÜŞTERİ ADI]",
    "proje_tipi": "METRO ASBUILT DENETIM+ONARIM",
    "istasyon": "S19 Masko",
    "kural_paketi": "ibb_metro",
    "job_type": "ASBUILT",
    "paftalar": [p.name for p in sheets],
    "pafta_yollari": {p.stem: str(p.resolve()) for p in sheets},
    "created_at": NOW.isoformat(),
    "muhendis": MUEHENDIS,
}
(JOB_DIR / "intake.yaml").write_text(json.dumps(intake, ensure_ascii=False, indent=2), encoding="utf-8")

rule_engine = RuleEngine(default_pack="ibb_metro")
reader = UniversalCADReader(use_cache=True)

def sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

def count_entities(doc):
    c = {}
    for ent in doc.modelspace():
        t = ent.dxftype()
        c[t] = c.get(t, 0) + 1
    return c

job_ledger = []
sheet_reports = []
t_total = time.time()

for dwg in sheets:
    t0 = time.time()
    stem = dwg.stem
    print(f"\n{'=' * 66}\nPAFTA: {stem}")
    try:
        # 1) Tier-0: DWG -> önbellekteki DXF (cache hit bekleniyor)
        dxf_path = ensure_dxf(dwg, use_cache=True)
        print(f"  [1] DXF hazır: {Path(dxf_path).name} ({Path(dxf_path).stat().st_size // 1024} KB)")

        # 2) Sahne okuma + triyaj
        sc = reader.read(dwg)
        triage_counts = SymbolTriage.triage(sc.symbols, sc.texts)
        print(f"  [2] Sahne: {len(sc.symbols)} sembol, {len(sc.texts)} metin, "
              f"{len(sc.logical_circuits)} linye, {len(sc.physical_routes)} güzergah")
        print(f"      Triyaj: {triage_counts}")

        # 3) Mutasyon için belgeyi aç
        doc = ezdxf.readfile(str(dxf_path))
        counts_before = count_entities(doc)

        # 4) LayerDoctor
        plan_ld = LayerAndBlockDoctor.analyze_and_propose(
            doc, symbols=sc.symbols, routes=sc.physical_routes,
            drawing_name=dwg.name,
        )
        auto_ids = {p.proposal_id for p in plan_ld.proposals if p.auto_approvable}
        applied_ld = LayerAndBlockDoctor.apply_plan(
            doc, plan_ld, approved_proposal_ids=auto_ids,
            applied_ledger_path=JOB_DIR / "applied" / f"{stem}_applied_changes.json",
        )
        plan_ld.save_json(JOB_DIR / "plans" / f"{stem}_change_plan.json")
        print(f"  [4] LayerDoctor: {plan_ld.summary_counts.get('total_proposals', 0)} öneri "
              f"(auto={plan_ld.summary_counts.get('auto_approvable', 0)}, "
              f"onaylı={len(applied_ld)}, güvenlik-atlanan={plan_ld.summary_counts.get('total_safety_skipped', 0)})")

        # 5) WireHealer (katman taşımalarından SONRAKI belge üzerinde)
        plan_wh = TopologicalWireHealer.analyze_and_propose(
            doc, symbols=sc.symbols, texts=sc.texts, drawing_name=dwg.name,
        )
        wauto_ids = {p.proposal_id for p in plan_wh.proposals if p.auto_approvable}
        applied_wh = TopologicalWireHealer.apply_plan(
            doc, plan_wh, approved_proposal_ids=wauto_ids,
        )
        plan_wh.save_json(JOB_DIR / "plans" / f"{stem}_wire_plan.json")
        print(f"  [5] WireHealer: dup={plan_wh.summary_counts.get('duplicates_found', 0)}, "
              f"stitch-auto={plan_wh.summary_counts.get('collinear_stitches_auto', 0)}, "
              f"stitch-blok={plan_wh.summary_counts.get('collinear_stitches_blocked', 0)}, "
              f"snap={plan_wh.summary_counts.get('symbol_snaps', 0)}, uygulanan={len(applied_wh)}")

        # Temiz DXF çıktısı
        out_dxf = JOB_DIR / "output" / f"{stem}_temiz.dxf"
        doc.saveas(str(out_dxf))
        counts_after = count_entities(doc)

        # 6) ASBUILT Optimizasyon (faz dengesi saha reçetesi)
        plan_op = ElectricalOptimizationPlan(
            drawing_name=dwg.name, job_type="ASBUILT",
            rule_pack="ibb_metro", created_at=NOW.isoformat(),
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
                ElectricalAutoOptimizer.propose_phase_balance(
                    plan_op, ptag, circuits, rule_engine=rule_engine,
                )
        plan_op.save_json(JOB_DIR / "plans" / f"{stem}_optimizer.json")
        print(f"  [6] Optimizer(ASBUILT): {len(panels)} pano, "
              f"{plan_op.summary_counts.get('total_proposals', 0)} saha önerisi")

        # 7) Redline PNG
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.set_title(f"REDLINE — {stem}\n(Gri: mimariye taşınan | Mavi: E-* katmanına taşınan | "
                     f"Yeşil: köprü/stitch | Turuncu: snap)", fontsize=9)
        for p in plan_ld.proposals:
            if p.status != "APPROVED":
                continue
            try:
                ent = doc.entitydb.get(p.dxf_handle)
                if ent is None:
                    continue
                if ent.dxftype() == "INSERT":
                    pt = ent.dxf.insert
                elif ent.dxftype() == "LINE":
                    pt = ent.dxf.start
                else:
                    continue
                color = "#9AA0A6" if p.new_layer == "A-MIMARI-ALTYAPI" else "#1A73E8"
                ax.scatter(pt.x, pt.y, s=6, c=color, alpha=0.55)
            except Exception:
                continue
        for a in applied_wh:
            if a.get("action") == "STITCH_COLLINEAR_GAP":
                pr = next((p for p in plan_wh.proposals if p.proposal_id == a["proposal_id"]), None)
                if pr:
                    ax.plot([pr.start_pt[0], pr.end_pt[0]], [pr.start_pt[1], pr.end_pt[1]],
                            c="#188038", lw=1.4, alpha=0.9)
            elif a.get("action", "").startswith("SNAP_TO_SYMBOL"):
                pr = next((p for p in plan_wh.proposals if p.proposal_id == a["proposal_id"]), None)
                if pr:
                    ax.annotate("", xy=pr.end_pt[:2], xytext=pr.start_pt[:2],
                                arrowprops=dict(arrowstyle="->", color="#E8710A", lw=1.0))
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        red_path = JOB_DIR / "redline" / f"{stem}.png"
        fig.savefig(str(red_path), dpi=110)
        plt.close(fig)

        # 8) Mesuliyet defteri kayıtları
        from dataclasses import asdict as _asdict
        for r in applied_ld:
            job_ledger.append({
                "pafta": stem, "modul": "LayerDoctor", **_asdict(r),
            })
        for a in applied_wh:
            job_ledger.append({
                "pafta": stem, "modul": "WireHealer",
                "signature_hash": sha16(f"{stem}|{a.get('proposal_id', '')}|{NOW.isoformat()}"),
                "applied_at": NOW.isoformat(),
                **a,
            })

        # 8b) STITCH ÖRNEKLEMESİ: uygulanan köprüler gerçekten 4 koşullu mu? (kanıt)
        st_applied = [a for a in applied_wh if a.get("action") == "STITCH_COLLINEAR_GAP"]
        spot_ok = 0
        for a in st_applied[:3]:
            pr = next((p for p in plan_wh.proposals if p.proposal_id == a["proposal_id"]), None)
            br = doc.entitydb.get(a.get("new_bridge_handle", ""))
            if pr is None or br is None:
                continue
            conds = pr.conditions_met
            same_layer = br.dxf.layer == pr.layer
            import math as _m
            g = _m.hypot(pr.end_pt[0] - pr.start_pt[0], pr.end_pt[1] - pr.start_pt[1])
            gap_ok = abs(g - pr.gap_drawing_units) < 0.01
            if all(conds.values()) and same_layer and gap_ok and pr.angle_diff_deg <= 5.0:
                spot_ok += 1
        print(f"  [5b] Köprü örnekleme: {min(3, len(st_applied))} örnekten {spot_ok} tanesi 4 koşul + geometri doğrulandı")

        # Bütünlük özeti
        delta = {}
        for k in set(counts_before) | set(counts_after):
            d_ = counts_after.get(k, 0) - counts_before.get(k, 0)
            if d_:
                delta[k] = d_
        elapsed = time.time() - t0
        print(f"  [7] Redline: {red_path.name} | Varlık değişimi: {delta or 'yok'} | Süre: {elapsed:.1f}s")

        sheet_reports.append({
            "pafta": stem,
            "sembol": len(sc.symbols), "metin": len(sc.texts),
            "linye": len(sc.logical_circuits),
            "triyaj": triage_counts,
            "layer_oneri": plan_ld.summary_counts,
            "layer_uygulanan": len(applied_ld),
            "wire": plan_wh.summary_counts,
            "wire_uygulanan": len(applied_wh),
            "stitch_ornekleme": f"{spot_ok}/{min(3, len(st_applied))}",
            "optimizer_oneri": plan_op.summary_counts,
            "varlik_delta": delta,
            "sure_sn": round(elapsed, 1),
            "temiz_dxf": str(out_dxf),
        })

    except Exception as e:
        import traceback
        print(f"  [HATA] {e}")
        traceback.print_exc()
        sheet_reports.append({"pafta": stem, "hata": str(e)})

# Job mesuliyet defteri
ledger_payload = {
    "job_id": "JOB-2026-S19-SAHA-01",
    "muhendis": MUEHENDIS,
    "created_at": NOW.isoformat(),
    "total_changes": len(job_ledger),
    "changes": job_ledger,
    "note": "Her kayıt mühendis onayına tabidir; bu koşumda yalnızca auto_approvable işlemler uygulandı.",
}
led_path = JOB_DIR / "RESPONSIBILITE_DEFTERI.json"
led_path.write_text(json.dumps(ledger_payload, ensure_ascii=False, indent=2), encoding="utf-8")

# RAPOR.md
ok_sheets = [r for r in sheet_reports if "hata" not in r]
lines = [
    "# JOB-2026-S19-SAHA-01 — Saha İndirim Testi Raporu",
    "",
    f"**Tarih:** {NOW.isoformat()}  ",
    f"**Mühendis:** {MUEHENDIS['adi']} ({MUEHENDIS['unvan']}) — Yetki Belge No: {MUEHENDIS['yetki_belge_no']}  ",
    f"**Kural Paketi:** ibb_metro | **Mod:** ASBUILT",
    "",
    "| Pafta | Sembol | Metin | Linye | Layer Öneri | Uygulanan | Wire (dup/stitchA/stitchB/snap) | Uygulanan | Köprü Örnek | Varlık Δ | Süre |",
    "| :--- | ---: | ---: | ---: | ---: | ---: | :--- | ---: | :---: | :--- | ---: |",
]
for r in ok_sheets:
    w = r["wire"]
    lines.append(
        f"| {r['pafta'][:42]} | {r['sembol']} | {r['metin']} | {r['linye']} | "
        f"{r['layer_oneri'].get('total_proposals', 0)} | {r['layer_uygulanan']} | "
        f"{w.get('duplicates_found', 0)}/{w.get('collinear_stitches_auto', 0)}/{w.get('collinear_stitches_blocked', 0)}/{w.get('symbol_snaps', 0)} | "
        f"{r['wire_uygulanan']} | {r['stitch_ornekleme']} | {json.dumps(r['varlik_delta'], ensure_ascii=False)} | {r['sure_sn']} |"
    )
for r in sheet_reports:
    if "hata" in r:
        lines.append(f"| {r['pafta']} | HATA: {r['hata'][:60]} | | | | | | | | |")
lines += [
    "",
    f"**Toplam uygulanan değişiklik:** {len(job_ledger)} (mesuliyet defteri: RESPONSIBILITE_DEFTERI.json)",
    "",
    "## Kural Uyarısı",
    "- Yalnızca `auto_approvable` işlemler uygulandı; tüm `REQUIRES_APPROVAL` maddeler plan dosyalarında Onay İstasyonu için bekliyor.",
    "- ASBUILT modunda faz etiketi DWG'de değiştirilmedi; panolar için saha reçetesi önerileri optimizer planlarındadır.",
]
(JOB_DIR / "RAPOR.md").write_text("\n".join(lines), encoding="utf-8")

print(f"\n{'=' * 66}")
print(f"TOPLAM: {len(ok_sheets)}/{len(sheets)} pafta işlendi | "
      f"{len(job_ledger)} uygulanan değişiklik | {time.time() - t_total:.1f}s")
print(f"Çıktı klasörü: {JOB_DIR}")
sys.exit(0 if ok_sheets else 1)
