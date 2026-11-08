# -*- coding: utf-8 -*-
"""
CloudeCAD v3.0 — ONAY İSTASYONU (Review Station)
=================================================
Gerçek paftalardan üretilen öneri planlarını mühendis onayına sunar:
  - Milisaniyelik (<20 ms) anlık onay / ret / geri al (JSON durum güncellemesi + arka plan DXF senkronu)
  - Saha reçeteleri (ASBUILT Optimizer) için doğrudan görüntüleme ve onaylama
  - Kural bazlı TOPLU triyaj ve sayfa içi hızlı toplu onay/ret
  - Pafta bazlı ve iş bazlı mesuliyet defterine tekrarsız (idempotent) imzalı kayıt
  - 2 kademeli Composer entegrasyonu (accoreconsole -> AutoCAD COM DWG fallback)

Çalıştırma:
    python tools/review_station.py --job jobs/JOB-2026-S19-SAHA-01 --port 8765
"""
import hashlib
import json
import os
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ezdxf
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from core.cad.cad_safety import LayerStandardSpec
from core.healer.layer_doctor import (
    DoctorChangePlan,
    LayerAndBlockDoctor,
    LayerChangeProposal,
    SkippedEntityRecord,
    STANDARD_LAYER_SPECS,
)
from core.healer.wire_healer import (
    TopologicalWireHealer,
    WireHealPlan,
    WireHealProposal,
)
from core.rules.rule_engine import RuleEngine

# --------------------------------------------------------------------------
# Plan Depoları ve Sınıflandırma
# --------------------------------------------------------------------------
SUFFIX = {"layer": "_change_plan.json", "wire": "_wire_plan.json", "optimizer": "_optimizer.json"}
PENDING_SET = {"REQUIRES_APPROVAL", "PROPOSED", "NOT_SELECTED"}


def bucket_of(row: dict) -> str:
    st = row["status"]
    if row.get("module") == "optimizer":
        if st == "APPROVED":
            return "approved"
        if st == "REJECTED":
            return "rejected"
        return "saha_recetesi"
    if st == "REJECTED":
        return "rejected"
    if st == "APPROVED":
        return "auto_applied" if row["auto"] else "approved"
    if row["auto"] and st == "PROPOSED":
        return "auto_applied"
    return "pending"


def build_rows(data: dict, sheet: str, module: str) -> List[dict]:
    rows = []
    props = data.get("proposals", [])
    if module == "layer":
        for p in props:
            rows.append({
                "id": p["proposal_id"],
                "sheet": sheet,
                "module": module,
                "kind": "LAYER",
                "layer": p["new_layer"],
                "old_layer": p.get("old_layer", ""),
                "detail": f"{p.get('old_layer', '?')} → {p['new_layer']}",
                "label": p.get("entity_label", p.get("dxf_handle", "")),
                "handle": p.get("dxf_handle", ""),
                "gap_mm": None,
                "angle": None,
                "confidence": p.get("confidence_score", 0.5),
                "auto": bool(p.get("auto_approvable", False)),
                "status": p.get("status", "REQUIRES_APPROVAL"),
                "reason": (p.get("reason") or "")[:240],
            })
    elif module == "wire":
        for p in props:
            ctx = f"{p.get('circuit_context_a') or '-'} / {p.get('circuit_context_b') or '-'}"
            rows.append({
                "id": p["proposal_id"],
                "sheet": sheet,
                "module": module,
                "kind": p["action"],
                "layer": p.get("layer", ""),
                "detail": f"{p.get('layer', '')} · {p['action']}",
                "label": f"{p.get('primary_handle', '')}↔{p.get('secondary_handle', '')}",
                "handle": p.get("primary_handle", ""),
                "gap_mm": p.get("gap_mm"),
                "angle": p.get("angle_diff_deg"),
                "confidence": p.get("confidence_score", 0.5),
                "auto": bool(p.get("auto_approvable", False)),
                "status": p.get("status", "REQUIRES_APPROVAL"),
                "reason": (p.get("reason") or "")[:240],
                "ctx": ctx,
            })
    else:
        for p in props:
            rows.append({
                "id": p["proposal_id"],
                "sheet": sheet,
                "module": module,
                "kind": p.get("category", "PHASE_BALANCE"),
                "layer": "-",
                "detail": f"{(p.get('old_text') or '')[:48]} → {(p.get('new_text') or '')[:48]}",
                "label": p.get("target_element", ""),
                "handle": p.get("dxf_handle", ""),
                "gap_mm": None,
                "angle": None,
                "confidence": 1.0 if p.get("verification_passed") else 0.5,
                "auto": False,
                "status": p.get("status", "ASBUILT_FIELD_RECOMMENDATION_ONLY"),
                "reason": f"{p.get('verification_proof', '')} | {p.get('reason', '')}"[:260],
                "can_apply": bool(p.get("can_apply_to_dwg", False)),
            })
    for r in rows:
        r["bucket"] = bucket_of(r)
    return rows


class PlanFile:
    """Bir (pafta, modül) plan dosyasının hafif indeksi."""

    def __init__(self, path: Path, sheet: str, module: str):
        self.path = path
        self.sheet = sheet
        self.module = module
        self.rows: List[dict] = []
        self.loaded_at = 0.0
        self.file_mtime = 0.0
        self.refresh()

    def refresh(self):
        t0 = time.time()
        self.file_mtime = self.path.stat().st_mtime
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.rows = build_rows(data, self.sheet, self.module)
        self.loaded_at = time.time() - t0
        return data

    def load_full(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save_full_atomic(self, data: dict):
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(self.path))
        self.file_mtime = self.path.stat().st_mtime
        self.rows = build_rows(data, self.sheet, self.module)


class JobStore:
    def __init__(self, job_dir: Path):
        self.job_dir = Path(job_dir)
        self.plans: Dict[str, PlanFile] = {}
        self.engineer = {}
        intake = self.job_dir / "intake.yaml"
        if intake.exists():
            self.engineer = json.loads(intake.read_text(encoding="utf-8")).get("muhendis", {})
        self.rule_engine = RuleEngine(default_pack="ibb_metro")

    def discover(self):
        plans_dir = self.job_dir / "plans"
        for module, suffix in SUFFIX.items():
            for f in sorted(plans_dir.glob(f"*{suffix}")):
                stem = f.name[: -len(suffix)]
                key = f"{stem}|{module}"
                mtime = f.stat().st_mtime
                if key not in self.plans:
                    self.plans[key] = PlanFile(f, stem, module)
                elif getattr(self.plans[key], "file_mtime", 0.0) != mtime:
                    self.plans[key].refresh()
        return self.plans

    def sheets(self) -> List[str]:
        return sorted({p.sheet for p in self.plans.values()})

    def ledger_path(self) -> Path:
        return self.job_dir / "RESPONSIBILITE_DEFTERI.json"

    def update_ledger(self, sheet: str, new_records: List[dict], remove_proposal_ids: set = None):
        """İş seviyesi mesuliyet defterini tekrarsız (idempotent) günceller."""
        lp = self.ledger_path()
        if lp.exists():
            payload = json.loads(lp.read_text(encoding="utf-8"))
        else:
            payload = {"job_id": self.job_dir.name, "muhendis": self.engineer, "changes": []}

        remove_ids = set(remove_proposal_ids or ())
        adding_ids = {r.get("proposal_id") for r in new_records if r.get("proposal_id")}
        drop_ids = remove_ids | adding_ids

        kept = [
            c for c in payload.get("changes", [])
            if not (c.get("pafta") == sheet and c.get("proposal_id") in drop_ids)
        ]
        kept.extend(new_records)
        payload["changes"] = kept
        payload["total_changes"] = len(kept)
        payload["last_station_update"] = datetime.now(timezone.utc).isoformat()

        tmp = lp.with_name(lp.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(lp))

    def update_sheet_applied_ledger(self, sheet: str, new_records: List[dict], remove_proposal_ids: set = None):
        """Pafta bazlı applied_changes.json dosyasını mevcut kayıtları ezmeden günceller."""
        ap_path = self.job_dir / "applied" / f"{sheet}_applied_changes.json"
        ap_path.parent.mkdir(parents=True, exist_ok=True)
        if ap_path.exists():
            try:
                payload = json.loads(ap_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {"drawing_name": f"{sheet}.dwg", "applied_changes": []}
        else:
            payload = {"drawing_name": f"{sheet}.dwg", "applied_changes": []}

        remove_ids = set(remove_proposal_ids or ())
        adding_ids = {r.get("proposal_id") for r in new_records if r.get("proposal_id")}
        drop_ids = remove_ids | adding_ids

        existing = payload.get("applied_changes", [])
        kept = [c for c in existing if c.get("proposal_id") not in drop_ids]
        for r in new_records:
            clean_rec = {k: v for k, v in r.items() if k not in ("pafta", "modul")}
            kept.append(clean_rec)

        payload["total_applied"] = len(kept)
        payload["applied_changes"] = kept
        tmp = ap_path.with_name(ap_path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(ap_path))


def rebuild_layer_plan(data: dict) -> DoctorChangePlan:
    return DoctorChangePlan(
        drawing_name=data.get("drawing_name", ""),
        unit_to_mm=data.get("unit_to_mm", 1.0),
        unit_source=data.get("unit_source", ""),
        created_at=data.get("created_at", ""),
        proposals=[LayerChangeProposal(**p) for p in data.get("proposals", [])],
        skipped_entities=[],  # Hızlı bellek içi işlem için 30.000 skip kaydını yeniden yaratma
        safety_skipped_counts=data.get("safety_skipped_counts", {}),
        summary_counts=data.get("summary_counts", {}),
    )


def rebuild_wire_plan(data: dict) -> WireHealPlan:
    return WireHealPlan(
        drawing_name=data.get("drawing_name", ""),
        unit_to_mm=data.get("unit_to_mm", 1.0),
        unit_source=data.get("unit_source", ""),
        max_stitch_gap_mm=data.get("max_stitch_gap_mm", 200.0),
        max_stitch_gap_units=data.get("max_stitch_gap_units", 200.0),
        max_snap_gap_mm=data.get("max_snap_gap_mm", 150.0),
        max_snap_gap_units=data.get("max_snap_gap_units", 150.0),
        created_at=data.get("created_at", ""),
        proposals=[WireHealProposal(**p) for p in data.get("proposals", [])],
        summary_counts=data.get("summary_counts", {}),
    )


JOB = JobStore(Path(r"D:\autocad projesi\jobs\JOB-2026-S19-SAHA-01"))
APPLY_LOCK = threading.Lock()   # Aynı dosyaya eşzamanlı yazma engeli
app = FastAPI(title="CloudeCAD Onay İstasyonu", version="3.0")


# --------------------------------------------------------------------------
# Modeller
# --------------------------------------------------------------------------
class DecideBody(BaseModel):
    sheet: str
    module: str                     # layer | wire | optimizer
    approve_ids: List[str] = []
    reject_ids: List[str] = []
    reset_ids: List[str] = []       # Geri al (bekleyene döndür)
    sync_dxf: bool = True           # False ise DXF yazımı arka plan thread'inde yapılır (UI <20ms)


class BulkBody(BaseModel):
    sheet: Optional[str] = None
    module: str = ""
    decision: str                   # approve | reject
    gap_min: Optional[float] = None
    gap_max: Optional[float] = None
    angle_min: Optional[float] = None
    angle_max: Optional[float] = None
    action: Optional[str] = None    # örn: STITCH_COLLINEAR_GAP
    q: Optional[str] = None
    commit: bool = False            # False: yalnız eşleşen id önizlemesi
    sync_dxf: bool = False


class ComposeBody(BaseModel):
    sheets: List[str]


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.get("/api/job")
def api_job():
    plans = JOB.discover()
    summary = {}
    for pf in plans.values():
        for r in pf.rows:
            key = f"{r['module']}:{r['bucket']}"
            summary[key] = summary.get(key, 0) + 1
    return {
        "job_id": JOB.job_dir.name,
        "muhendis": JOB.engineer,
        "sheets": JOB.sheets(),
        "summary": summary,
        "plans_loaded": len(plans),
    }


@app.get("/api/proposals")
def api_proposals(sheet: str = "", module: str = "", bucket: str = "",
                  gap_min: float = None, gap_max: float = None,
                  angle_max: float = None, action: str = "", q: str = "",
                  page: int = 1, page_size: int = 50):
    JOB.discover()
    rows = []
    for pf in JOB.plans.values():
        if sheet and pf.sheet != sheet:
            continue
        if module and pf.module != module:
            continue
        rows.extend(pf.rows)

    if bucket and bucket != "all":
        if bucket == "applied_all":
            rows = [r for r in rows if r["bucket"] in ("auto_applied", "approved")]
        else:
            rows = [r for r in rows if r["bucket"] == bucket]
    if gap_min is not None:
        rows = [r for r in rows if r["gap_mm"] is not None and r["gap_mm"] >= gap_min]
    if gap_max is not None:
        rows = [r for r in rows if r["gap_mm"] is not None and r["gap_mm"] <= gap_max]
    if angle_max is not None:
        rows = [r for r in rows if r["angle"] is not None and r["angle"] <= angle_max]
    if action:
        rows = [r for r in rows if action.upper() in r["kind"].upper()]
    if q:
        ql = q.lower()
        rows = [
            r for r in rows
            if ql in (r["label"] or "").lower()
            or ql in (r["reason"] or "").lower()
            or ql in (r["layer"] or "").lower()
            or ql in (r["detail"] or "").lower()
        ]

    total = len(rows)
    page = max(1, page)
    page_size = min(200, max(10, page_size))
    chunk = rows[(page - 1) * page_size: page * page_size]
    return {"total": total, "page": page, "page_size": page_size, "rows": chunk}


@app.get("/api/redline/{name}")
def api_redline(name: str):
    p = JOB.job_dir / "redline" / f"{name}.png"
    if not p.exists():
        raise HTTPException(404, "Redline bulunamadı")
    return FileResponse(p, media_type="image/png")


def _sync_approved_to_dxf(sheet: str, module: str, data: dict, approve_set: set):
    """Onaylanan değişiklikleri temiz DXF dosyasına cerrahi olarak yazar."""
    if not approve_set or module not in ("layer", "wire"):
        return
    clean = JOB.job_dir / "output" / f"{sheet}_temiz.dxf"
    if not clean.exists():
        return
    with APPLY_LOCK:
        doc = ezdxf.readfile(str(clean))
        tmp_dxf = clean.with_name(clean.name + ".tmp")
        if module == "layer":
            plan = rebuild_layer_plan(data)
            LayerAndBlockDoctor.apply_plan(
                doc, plan,
                approved_proposal_ids=approve_set,
                output_dxf_path=tmp_dxf,
            )
        elif module == "wire":
            plan = rebuild_wire_plan(data)
            TopologicalWireHealer.apply_plan(
                doc, plan,
                approved_proposal_ids=approve_set,
                output_dxf_path=tmp_dxf,
            )
        if tmp_dxf.exists():
            os.replace(str(tmp_dxf), str(clean))


@app.post("/api/decide")
def api_decide(body: DecideBody):
    return _decide_impl(body)


def _decide_impl(body: DecideBody):
    t0 = time.time()
    key = f"{body.sheet}|{body.module}"
    JOB.discover()
    pf = JOB.plans.get(key)
    if pf is None:
        raise HTTPException(404, f"Plan bulunamadı: {key}")

    approve_set = set(body.approve_ids)
    reject_set = set(body.reject_ids)
    reset_set = set(body.reset_ids)

    with APPLY_LOCK:
        data = pf.load_full()
        now_iso = datetime.now(timezone.utc).isoformat()
        records = []

        for p in data.get("proposals", []):
            pid = p.get("proposal_id", "")
            if pid in approve_set:
                p["status"] = "APPROVED"
                raw_sig = f"{body.sheet}|{pid}|APPROVED|{now_iso}"
                sig_hash = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()[:16]
                if body.module == "layer":
                    spec = STANDARD_LAYER_SPECS.get(
                        p.get("new_layer", ""),
                        LayerStandardSpec(name=p.get("new_layer", "0"), color=7, lineweight=25),
                    )
                    records.append({
                        "pafta": body.sheet,
                        "modul": "LayerDoctor",
                        "proposal_id": pid,
                        "dxf_handle": p.get("dxf_handle", ""),
                        "dxftype": p.get("dxftype", "INSERT"),
                        "entity_label": p.get("entity_label", ""),
                        "old_layer": p.get("old_layer", ""),
                        "new_layer": p.get("new_layer", ""),
                        "old_color": 256,
                        "new_color_bylayer": 256,
                        "layer_aci_color": spec.color,
                        "layer_lineweight": spec.lineweight,
                        "plotstyle_name": spec.plotstyle_name,
                        "layer_locked": spec.locked,
                        "reason": p.get("reason", ""),
                        "applied_at": now_iso,
                        "signature_hash": sig_hash,
                    })
                elif body.module == "wire":
                    records.append({
                        "pafta": body.sheet,
                        "modul": "WireHealer",
                        "proposal_id": pid,
                        "action": p.get("action", ""),
                        "primary_handle": p.get("primary_handle", ""),
                        "secondary_handle": p.get("secondary_handle", ""),
                        "layer": p.get("layer", ""),
                        "applied_at": now_iso,
                        "signature_hash": sig_hash,
                    })
                else:
                    records.append({
                        "pafta": body.sheet,
                        "modul": "ElectricalOptimizer_SahaRecetesi",
                        "proposal_id": pid,
                        "target_element": p.get("target_element", ""),
                        "category": p.get("category", ""),
                        "old_text": p.get("old_text", ""),
                        "new_text": p.get("new_text", ""),
                        "applied_at": now_iso,
                        "signature_hash": sig_hash,
                    })
            elif pid in reject_set:
                p["status"] = "REJECTED"
            elif pid in reset_set:
                if body.module == "optimizer":
                    p["status"] = "ASBUILT_FIELD_RECOMMENDATION_ONLY"
                else:
                    p["status"] = "PROPOSED" if p.get("auto_approvable") else "REQUIRES_APPROVAL"

        # Plan JSON'unu atomik kaydet ve hafızadaki satırları anında tazele
        pf.save_full_atomic(data)

        # Mesuliyet defterlerini güncelle
        remove_from_ledger = reject_set | reset_set
        if records or remove_from_ledger:
            JOB.update_ledger(body.sheet, records, remove_proposal_ids=remove_from_ledger)
            if body.module == "layer":
                JOB.update_sheet_applied_ledger(body.sheet, records, remove_proposal_ids=remove_from_ledger)

    # Temiz DXF senkronizasyonu (yalnızca yeni onay varsa ve layer/wire modülüyse)
    if approve_set and body.module in ("layer", "wire"):
        if body.sync_dxf:
            _sync_approved_to_dxf(body.sheet, body.module, data, approve_set)
        else:
            threading.Thread(
                target=_sync_approved_to_dxf,
                args=(body.sheet, body.module, data, approve_set),
                daemon=True,
            ).start()

    return {
        "status": "OK",
        "sheet": body.sheet,
        "module": body.module,
        "approved": len(approve_set),
        "rejected": len(reject_set),
        "reset": len(reset_set),
        "applied_records": len(records),
        "seconds": round(time.time() - t0, 3),
    }


@app.post("/api/bulk")
def api_bulk(body: BulkBody):
    """Kural bazlı toplu triyaj. commit=False -> yalnızca eşleşen id önizlemesi."""
    JOB.discover()
    matched_by_key: Dict[str, List[str]] = {}
    total_matched = 0
    sample_ids = []

    for pf in JOB.plans.values():
        if body.module and pf.module != body.module:
            continue
        if body.sheet and pf.sheet != body.sheet:
            continue
        for r in pf.rows:
            if r["bucket"] not in ("pending", "saha_recetesi"):
                continue
            if body.gap_min is not None and (r["gap_mm"] is None or r["gap_mm"] < body.gap_min):
                continue
            if body.gap_max is not None and (r["gap_mm"] is None or r["gap_mm"] > body.gap_max):
                continue
            if body.angle_min is not None and (r["angle"] is None or r["angle"] < body.angle_min):
                continue
            if body.angle_max is not None and (r["angle"] is None or r["angle"] > body.angle_max):
                continue
            if body.action and body.action.upper() not in r["kind"].upper():
                continue
            if body.q:
                ql = body.q.lower()
                if (ql not in (r["label"] or "").lower()
                        and ql not in (r["reason"] or "").lower()
                        and ql not in (r["detail"] or "").lower()):
                    continue
            k = f"{pf.sheet}|{pf.module}"
            matched_by_key.setdefault(k, []).append(r["id"])
            total_matched += 1
            if len(sample_ids) < 20:
                sample_ids.append(r["id"])

    preview = {
        "matched": total_matched,
        "ids_sample": sample_ids,
        "commit": body.commit,
        "decision": body.decision,
    }
    if not body.commit or not total_matched:
        return preview

    results = {}
    for k, ids in matched_by_key.items():
        sheet, mod = k.split("|", 1)
        b = DecideBody(
            sheet=sheet,
            module=mod,
            approve_ids=(ids if body.decision == "approve" else []),
            reject_ids=(ids if body.decision == "reject" else []),
            sync_dxf=body.sync_dxf,
        )
        try:
            results[k] = _decide_impl(b)
        except HTTPException as e:
            results[k] = {"status": "HATA", "message": e.detail}
    return {**preview, "results": results}


@app.post("/api/compose")
def api_compose(body: ComposeBody):
    sys.path.insert(0, str(ROOT / "tools"))
    import compose_delivery
    sheets = list(body.sheets)
    if sheets == ["__ALL__"]:
        sheets = [f.stem.replace("_temiz", "") for f in sorted((JOB.job_dir / "output").glob("*_temiz.dxf"))]
    with APPLY_LOCK:
        res = compose_delivery.compose_job(JOB.job_dir, sheets, JOB.engineer)
    return res


@app.get("/api/delivery")
def api_delivery():
    d = JOB.job_dir / "delivery"
    if not d.exists():
        return {"exists": False}
    items = []
    for p in sorted(d.rglob("*")):
        if p.is_file():
            items.append({"rel": str(p.relative_to(d)), "kb": round(p.stat().st_size / 1024, 1)})
    return {"exists": True, "files": items}


# --------------------------------------------------------------------------
# HTML Arayüzü
# --------------------------------------------------------------------------
HTML = """<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<title>CloudeCAD — Onay Ekranı</title>
<style>
 body{font-family:'Segoe UI',Arial,sans-serif;margin:0;background:#F4F6F8;color:#1E1E1E}
 header{background:#0B2545;color:#fff;padding:12px 20px}
 header h1{font-size:17px;margin:0 0 2px}
 header .sub{font-size:12.5px;opacity:.85}
 .wrap{padding:14px 20px;max-width:1140px;margin:0 auto}
 .cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px}
 .card{background:#fff;border:2px solid #E0E4E8;border-radius:8px;padding:10px 16px;flex:1;min-width:180px;cursor:pointer;transition:all .15s}
 .card:hover{border-color:#134074;transform:translateY(-1px);box-shadow:0 3px 8px rgba(0,0,0,.06)}
 .card.active{border-color:#0B2545;background:#EDF3FA}
 .card b{display:block;font-size:26px;color:#0B2545}
 .card.ok b{color:#0B6A2E}.card.wait b{color:#B26A00}.card.saha b{color:#1A73E8}
 .card span{font-size:12px;color:#505A64}
 .top-bar{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin:14px 0 10px}
 .chips{display:flex;gap:6px;flex-wrap:wrap}
 .chip{padding:6px 14px;border-radius:16px;border:1px solid #C9CFD6;background:#fff;font-size:12.5px;cursor:pointer;font-weight:500}
 .chip.on{background:#0B2545;color:#fff;border-color:#0B2545}
 .page-actions{display:flex;gap:6px;align-items:center}
 .item{background:#fff;border:1px solid #E0E4E8;border-radius:8px;padding:10px 14px;margin-bottom:8px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;transition:opacity .15s}
 .item.busy{opacity:.55;pointer-events:none}
 .item .what{flex:2.2;min-width:280px;font-size:13.5px}
 .item .what .title{font-weight:600;color:#0B2545;margin-bottom:4px}
 .item .what .badges{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:4px}
 .badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11.5px;font-family:Consolas,monospace}
 .badge.sym{background:#E8F0FE;color:#174EA6;border:1px solid #D2E3FC}
 .badge.dtl{background:#FEF7E0;color:#B06000;border:1px solid #FEEFC3}
 .item .what .why{font-size:11.5px;color:#5F6368}
 .item .where{font-size:12px;color:#33475B;min-width:145px;font-weight:500}
 .item .where small{display:block;font-size:10.5px;color:#7A8694;font-weight:400}
 .item .conf{font-size:12px;min-width:60px;text-align:center}
 .btns{display:flex;gap:6px;align-items:center;min-width:190px;justify-content:flex-end}
 button{padding:7px 13px;border:0;border-radius:6px;background:#134074;color:#fff;cursor:pointer;font-size:12.5px;font-weight:500}
 button.g{background:#188038}button.r{background:#B3261E}button.gray{background:#5F6368}button.sm{padding:5px 10px;font-size:11.5px}
 button:hover{filter:brightness(1.1)}
 button:disabled{opacity:.5;cursor:not-allowed}
 .st-pill{padding:4px 9px;border-radius:12px;font-size:11.5px;font-weight:600}
 .st-pill.approved{background:#E6F4EA;color:#137333}
 .st-pill.auto_applied{background:#E8F0FE;color:#1967D2}
 .st-pill.rejected{background:#FCE8E6;color:#C5221F}
 details{background:#fff;border:1px solid #E0E4E8;border-radius:8px;padding:8px 14px;margin:8px 0}
 summary{cursor:pointer;font-weight:600;font-size:13px;color:#33475B}
 .adv{display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:8px 0}
 select,input{padding:6px 9px;border:1px solid #C9CFD6;border-radius:5px;font-size:12.5px}
 .pg{margin:10px 0;display:flex;gap:10px;align-items:center;font-size:13px}
 .kv{font-size:11.5px;color:#646E78}
 #msg{position:fixed;right:16px;bottom:16px;background:#0B2545;color:#fff;padding:11px 16px;border-radius:8px;display:none;font-size:12.5px;max-width:440px;box-shadow:0 4px 12px rgba(0,0,0,.2);z-index:99}
 .done-note{font-size:12.5px;color:#646E78;margin-top:6px}
</style></head><body>
<header>
 <h1>CloudeCAD — Değişiklik Onay İstasyonu</h1>
 <div class="sub" id="jobinfo"></div>
 <div class="sub" style="opacity:.75">Önerilen düzeltmeleri inceleyin: onayladıklarınız paftaya ve imzalı mesuliyet defterine işlenir, reddettikleriniz yalnızca raporlanır.</div>
</header>
<div class="wrap">
 <div class="cards" id="cards"></div>

 <div class="top-bar">
  <div class="chips" id="chips"></div>
  <div class="page-actions" id="pageActions"></div>
 </div>

 <div id="list"></div>
 <div class="pg" id="pg"></div>

 <details id="advBox"><summary>⚙️ Gelişmiş araçlar (pafta/durum filtresi, kurallı toplu işlem, tüm geçmiş)</summary>
  <div class="adv">
   <select id="fSheet" onchange="load(1)"><option value="">Tüm paftalar</option></select>
   <select id="fBucket" onchange="load(1)">
    <option value="pending">⏳ Sadece bekleyenler</option>
    <option value="all">🔍 Tüm durumlar (hepsi)</option>
    <option value="applied_all">✅ Tüm uygulananlar (Otomatik + Onaylı)</option>
    <option value="approved">👍 Sadece benim onayladıklarım</option>
    <option value="auto_applied">🤖 Otomatik uygulananlar</option>
    <option value="rejected">✗ Reddettiklerim</option>
    <option value="saha_recetesi">📋 Saha reçeteleri</option>
   </select>
   <input id="fGapMax" type="number" placeholder="boşluk ≤ mm" style="width:110px">
   <input id="fAngleMax" type="number" placeholder="açı ≤ °" style="width:80px">
   <input id="fQ" type="text" placeholder="sembol / katman ara..." style="width:165px" onkeydown="if(event.key==='Enter')load(1)">
   <button onclick="load(1)">FİLTRELE</button>
   <button class="gray" onclick="resetFilters()">SIFIRLA</button>
  </div>
  <div class="adv">
   <b style="font-size:12.5px">Filtreye uyan tüm kayıtlar için toplu işlem:</b>
   <button class="g" id="bulkA" onclick="bulk('approve',this)">FİLTRELENEN BEKLEYENLERİ ONAYLA</button>
   <button class="r" id="bulkR" onclick="bulk('reject',this)">FİLTRELENEN BEKLEYENLERİ REDDET</button>
  </div>
 </details>

 <h2>📦 Teslim Paketi ve DWG Üretimi</h2>
 <div class="adv" style="background:#fff;border:1px solid #E0E4E8;border-radius:8px;padding:10px 14px">
  <select id="cSheet"></select>
  <button onclick="compose(false)" id="btnCompOne">SEÇİLEN PAFTANIN TESLİM PAKETİNİ ÜRET (DWG)</button>
  <button class="g" onclick="compose(true)" id="btnCompAll">TÜM PAFTALARI ÜRET (7/7 DWG + RAPOR)</button>
  <span id="cOut" class="kv"></span>
 </div>
 <details><summary>📂 Teslim klasörü içeriği (delivery/)</summary><div id="delivery" class="kv"></div></details>
 <details><summary>🗺️ Değişiklik haritaları (Redline PNG)</summary><div id="redlinks" class="kv"></div></details>
 <p class="done-note">İpucu: Üstteki 4 özet kartına tıklayarak doğrudan ilgili kayıtları listeleyebilirsiniz. Yanlışlıkla verdiğiniz bir kararı "↩ Geri Al" butonuyla istediğiniz an geri alabilirsiniz.</p>
</div>
<div id="msg"></div>
<script>
let PAGE=1,TOTAL=0,PS=25,MOD='',CURRENT_ROWS=[];
const $=id=>document.getElementById(id);
const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let toastTimer=null;
function toast(m){const x=$('msg');x.textContent=m;x.style.display='block';clearTimeout(toastTimer);toastTimer=setTimeout(()=>x.style.display='none',4500);}
async function j(url,opt){const r=await fetch(url,opt);if(!r.ok){let e=await r.json().catch(()=>({detail:r.statusText}));throw new Error(e.detail||r.statusText);}return r.json();}

function shortSheet(s){
 if(!s)return '';
 const m=s.match(/(S\\d+)-(?:000-99-|CT0-03-|CT0-2A-|BT0-00-)?([A-Z]{2}-\\d+)/);
 if(m) return m[1]+' · '+s.replace(/^AG-[A-Z]+-M09-S\\d+-/,'').replace(/-A-T-2I-001.*$/,'');
 return s.length>26?s.slice(0,12)+'…'+s.slice(-12):s;
}

function kindLabel(x){
 const k=x.kind||'';
 if(k==='LAYER') return (x.layer||'').startsWith('A-MIMARI')
   ? '🏠 Mimari altlık elemanını gri/kilitli arka plana taşı'
   : '⚡ Elektrik elemanını standart katmana taşı ('+esc(x.layer)+')';
 if(k==='DELETE_DUPLICATE') return '🧹 Üst üste binmiş çift çizgiyi temizle';
 if(k.startsWith('STITCH')) return '🔌 Kopuk kablo uçlarını birleştir ('+(x.gap_mm!=null?x.gap_mm.toFixed(0):'?')+' mm boşluk)';
 if(k.startsWith('SNAP')) return '🧲 Açıkta kalan kablo ucunu sembole bağla';
 if(k==='PHASE_BALANCE') return '⚖️ Pano Faz Dengeleme Saha Reçetesi (AS-BUILT)';
 if(k.startsWith('BYKHY')) return '🚒 Yangın pompası kablo/KAK düzeltmesi';
 if(k==='PROTECTION_COORDINATION') return '🛡️ Sigorta-kablo koordinasyon düzeltmesi';
 return esc(k);
}
function bucketTr(b){return {
 pending:'⏳ Onay bekliyor',
 auto_applied:'🤖 Otomatik uygulandı',
 approved:'✅ Mühendis onaylı',
 rejected:'✗ Reddedildi',
 saha_recetesi:'📋 Saha reçetesi'
}[b]||b;}

async function refreshSummary(){
 const jb=await j('/api/job');
 $('jobinfo').textContent=jb.job_id+'  ·  '+(jb.muhendis.adi||'')+' ('+(jb.muhendis.unvan||'')+')';
 const s=jb.summary;
 const wait=(s['layer:pending']||0)+(s['wire:pending']||0);
 const userApp=(s['layer:approved']||0)+(s['wire:approved']||0)+(s['optimizer:approved']||0);
 const autoApp=(s['layer:auto_applied']||0)+(s['wire:auto_applied']||0);
 const done=autoApp+userApp;
 const saha=(s['optimizer:saha_recetesi']||0)+(s['optimizer:approved']||0);
 const curB=$('fBucket').value;
 $('cards').innerHTML=
  `<div class="card ok ${curB==='applied_all'?'active':''}" onclick="filterByCard('', 'applied_all')" title="Uygulanan tüm değişiklikleri görmek için tıklayın">
     <b>${done}</b><span>✅ Uygulanmış değişiklik (${autoApp} otomatik, ${userApp} onaylı)</span>
   </div>
   <div class="card wait ${curB==='pending'&&MOD!==('optimizer')?'active':''}" onclick="filterByCard('', 'pending')" title="Onayınızı bekleyen maddeleri görmek için tıklayın">
     <b>${wait}</b><span>⏳ Onayınızı bekleyen karar</span>
   </div>
   <div class="card saha ${MOD==='optimizer'?'active':''}" onclick="setMod('optimizer')" title="Pano faz dengeleme saha reçetelerini görmek için tıklayın">
     <b>${saha}</b><span>📋 Sahaya iletilecek pano reçetesi (tıkla ve incele)</span>
   </div>
   <div class="card ${curB==='all'&&!MOD?'active':''}" onclick="filterByCard('', 'all')" title="Tüm paftalardaki tüm kayıtları görmek için tıklayın">
     <b>${jb.sheets.length}</b><span>📄 İşlenen pafta (tüm kayıtları göster)</span>
   </div>`;
 if(!$('fSheet').options || $('fSheet').options.length<=1){
  const sh='<option value="">Tüm paftalar ('+jb.sheets.length+')</option>'+jb.sheets.map(s=>`<option value="${esc(s)}">${esc(shortSheet(s))} (${esc(s)})</option>`).join('');
  $('fSheet').innerHTML=sh;
  $('cSheet').innerHTML=jb.sheets.map(s=>`<option value="${esc(s)}">${esc(shortSheet(s))} — ${esc(s)}</option>`).join('');
  $('redlinks').innerHTML=jb.sheets.map(s=>`<a href="/api/redline/${encodeURIComponent(s)}" target="_blank">${esc(shortSheet(s))}</a>`).join(' &nbsp;·&nbsp; ');
 }
 renderChips();
}

function renderChips(){
 $('chips').innerHTML=[
  ['','Hepsi (Bekleyenler)'],
  ['layer','⚡ Katman düzeltmeleri'],
  ['wire','🔌 Kablo onarımları'],
  ['optimizer','📋 Saha reçeteleri (Pano Faz Dengeleme)']
 ].map(([v,t])=>`<div class="chip ${MOD===v?'on':''}" onclick="setMod('${v}')">${t}</div>`).join('');
}

function filterByCard(mod, bucket){
 MOD=mod;
 $('fBucket').value=bucket;
 renderChips();
 load(1);
}

function setMod(m){
 MOD=m;
 if(m==='optimizer'){
  $('fBucket').value='all';
 }else if($('fBucket').value==='saha_recetesi'||$('fBucket').value==='all'){
  $('fBucket').value='pending';
 }
 renderChips();
 load(1);
}

function resetFilters(){
 MOD='';
 $('fSheet').value='';
 $('fBucket').value='pending';
 $('fGapMax').value='';
 $('fAngleMax').value='';
 $('fQ').value='';
 renderChips();
 load(1);
}

function fparams(p){
 const q=new URLSearchParams();
 if($('fSheet').value)q.set('sheet',$('fSheet').value);
 if(MOD)q.set('module',MOD);
 const b=$('fBucket').value;
 if(b && b!=='all') q.set('bucket',b);
 if($('fGapMax').value)q.set('gap_max',$('fGapMax').value);
 if($('fAngleMax').value)q.set('angle_max',$('fAngleMax').value);
 if($('fQ').value)q.set('q',$('fQ').value);
 q.set('page',p);q.set('page_size',PS);
 return q;
}

async function load(p){
 PAGE=p;
 await refreshSummary();
 const r=await j('/api/proposals?'+fparams(p));
 TOTAL=r.total;
 CURRENT_ROWS=r.rows||[];
 const actionable=CURRENT_ROWS.filter(x=>x.bucket==='pending'||x.bucket==='saha_recetesi');
 if(actionable.length>1){
  $('pageActions').innerHTML=
   `<span class="kv">Bu sayfadaki ${actionable.length} bekleyen:</span>
    <button class="g sm" onclick="decidePage(true)">✓ Sayfadakileri Onayla</button>
    <button class="r sm" onclick="decidePage(false)">✗ Sayfadakileri Reddet</button>`;
 }else{
  $('pageActions').innerHTML='';
 }

 let h='';
 for(const x of CURRENT_ROWS){
  const isPending=(x.bucket==='pending'||x.bucket==='saha_recetesi');
  const canUndo=(x.bucket==='approved'||x.bucket==='rejected');
  const approveLbl=(x.module==='optimizer')?'✓ REÇETEYİ ONAYLA':'✓ ONAYLA';
  h+=`<div class="item" id="row-${esc(x.sheet)}-${esc(x.id)}">
   <div class="what">
    <div class="title">${kindLabel(x)}</div>
    <div class="badges">
     ${x.label?`<span class="badge sym" title="Sembol / Varlık Etiketi">🏷️ ${esc(x.label)}</span>`:''}
     ${x.detail?`<span class="badge dtl" title="Eski → Yeni Durum">🔀 ${esc(x.detail)}</span>`:''}
    </div>
    <div class="why" title="${esc(x.reason)}">${esc((x.reason||'').slice(0,145))}${(x.reason||'').length>145?'…':''}</div>
   </div>
   <div class="where" title="${esc(x.sheet)}">📄 ${esc(shortSheet(x.sheet))}<small>${esc(x.sheet.slice(-18))}</small></div>
   <div class="conf">Güven<br><b>%${Math.round((x.confidence||0)*100)}</b></div>
   <div class="btns">${isPending?
     `<button class="g" onclick="decide('${esc(x.id)}','${esc(x.module)}','${esc(x.sheet)}','approve',this)">${approveLbl}</button>
      <button class="r" onclick="decide('${esc(x.id)}','${esc(x.module)}','${esc(x.sheet)}','reject',this)">✗ REDDET</button>`
    : `<span class="st-pill ${esc(x.bucket)}">${bucketTr(x.bucket)}</span>` +
      (canUndo?`<button class="gray sm" onclick="decide('${esc(x.id)}','${esc(x.module)}','${esc(x.sheet)}','reset',this)" title="Kararı geri al ve bekleyenlere döndür">↩ Geri Al</button>`:'')}
   </div>
  </div>`;
 }
 $('list').innerHTML=h||'<p class="kv" style="padding:14px;background:#fff;border-radius:8px;border:1px solid #E0E4E8">Bu filtrede kayıt bulunmuyor. Üstteki kartlara veya sekmelere tıklayarak diğer kategorilere geçebilirsiniz. 🎉</p>';
 const pages=Math.max(1,Math.ceil(TOTAL/PS));
 $('pg').innerHTML=`Toplam <b>${TOTAL}</b> kayıt · Sayfa ${PAGE}/${pages} `+
  (PAGE>1?`<button class="gray sm" onclick="load(${PAGE-1})">‹ Önceki</button>`:'')+
  (PAGE<pages?`<button class="gray sm" onclick="load(${PAGE+1})">Sonraki ›</button>`:'');
}

async function decide(id,mod,sheet,action,btn){
 const rowEl=document.getElementById(`row-${sheet}-${id}`);
 if(rowEl) rowEl.classList.add('busy');
 if(btn){btn.disabled=true;btn.textContent='⏳ İşleniyor…';}
 try{
  const payload={
   sheet:sheet,
   module:mod,
   approve_ids:action==='approve'?[id]:[],
   reject_ids:action==='reject'?[id]:[],
   reset_ids:action==='reset'?[id]:[],
   sync_dxf:false
  };
  const res=await j('/api/decide',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const msgMap={
   approve:'✓ Onaylandı ('+res.seconds+' sn) — mesuliyet defterine ve paftaya işlendi.',
   reject:'✗ Reddedildi ('+res.seconds+' sn) — çizime dokunulmadı.',
   reset:'↩ Karar geri alındı ('+res.seconds+' sn) — tekrar bekleyenlere eklendi.'
  };
  toast(msgMap[action]||'İşlem tamamlandı.');
  await load(PAGE);
 }catch(e){
  if(rowEl) rowEl.classList.remove('busy');
  toast('HATA: '+e.message);
 }
}

async function decidePage(approve){
 const actionable=CURRENT_ROWS.filter(x=>x.bucket==='pending'||x.bucket==='saha_recetesi');
 if(!actionable.length) return;
 const byKey={};
 for(const x of actionable){
  const k=x.sheet+'|'+x.module;
  (byKey[k]=byKey[k]||[]).push(x.id);
 }
 toast('⏳ Sayfadaki '+actionable.length+' kayıt işleniyor…');
 try{
  for(const [k,ids] of Object.entries(byKey)){
   const [sheet,mod]=k.split('|');
   await j('/api/decide',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({sheet:sheet,module:mod,approve_ids:approve?ids:[],reject_ids:approve?[]:ids,sync_dxf:false})});
  }
  toast((approve?'✓ ':'✗ ')+actionable.length+' kayıt topluca işlendi.');
  const nextP = (PAGE>1 && CURRENT_ROWS.length===actionable.length) ? PAGE-1 : PAGE;
  await load(nextP);
 }catch(e){toast('HATA: '+e.message);}
}

let ARMED=null;
async function bulk(decision,btn){
 const q=fparams(1);['page','page_size','bucket'].forEach(k=>q.delete(k));
 const body={};for(const[k,v]of q.entries()){body[k]=isNaN(v)||v===''?v:Number(v);}
 body.module=body.module||'';body.decision=decision;body.commit=false;body.sync_dxf=false;
 const pre=await j('/api/bulk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!pre.matched){toast('Filtreye uyan bekleyen kayıt yok.');return;}
 if(ARMED&&ARMED.decision===decision){
  body.commit=true;
  btn.disabled=true;btn.textContent='⏳ Uygulanıyor…';
  const res=await j('/api/bulk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  btn.disabled=false;ARMED=null;btn.textContent=btn.dataset.label;
  toast('Toplu işlem tamamlandı ('+pre.matched+' kayıt).');
  await load(1);
 }else{
  disarm();ARMED={decision:decision};btn.dataset.label=btn.textContent;
  btn.textContent=pre.matched+' kayıt eşleşti — ONAYLAMAK İÇİN TEKRAR TIKLA';
  setTimeout(disarm,12000);
 }
}
function disarm(){ARMED=null;['bulkA','bulkR'].forEach(id=>{const b=document.getElementById(id);if(b&&b.dataset.label)b.textContent=b.dataset.label;});}

async function compose(all){
 const sheets=all?['__ALL__']:[$('cSheet').value];
 if(!all&&!sheets[0])return toast('Pafta seçin.');
 const btn=all?$('btnCompAll'):$('btnCompOne');
 btn.disabled=true;
 $('cOut').textContent='⏳ DWG ve teslim paketi üretiliyor… (Lütfen bekleyin)';
 try{
  const res=await j('/api/compose',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({sheets:sheets})});
  const res2=res.results||[];
  toast('Teslim paketi hazır: '+res2.length+' pafta işlendi.');
  $('cOut').innerHTML=res2.map(r=>(r.status==='OK'?'✅':'⚠️')+' <b>'+esc(shortSheet(r.sheet))+'</b> ('+esc(r.dwg)+')').join(' &nbsp;·&nbsp; ');
  listDelivery();
 }catch(e){$('cOut').textContent='';toast('HATA: '+e.message);}
 finally{btn.disabled=false;}
}
async function listDelivery(){
 const d=await j('/api/delivery');
 $('delivery').innerHTML=d.exists?
  '<ul style="margin:4px 0">'+d.files.map(f=>`<li>${esc(f.rel)} (${f.kb} KB)</li>`).join('')+'</ul>':'Henüz teslim klasörü üretilmedi.';
}
load(1);listDelivery();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


def main():
    import argparse
    import uvicorn
    ap = argparse.ArgumentParser(prog="review_station")
    ap.add_argument("--job", default=r"D:\autocad projesi\jobs\JOB-2026-S19-SAHA-01")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    JOB.job_dir = Path(args.job)
    JOB.discover()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
