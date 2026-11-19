# -*- coding: utf-8 -*-
"""
Evrensel Çizim, Katman ve Topoloji Onarıcı (`cizim_onarici.py`)
================================================================
Projedeki mimari ve elektrik çizimlerini `GEMINI.md` sıfır-hardcode
ilkelerine göre onarır:
  1. `consolidate_architecture_to_single_layer`:
     Mimari çizimdeki tüm nesneleri ve blok içi geometrileri tek bir
     `MIMARI` katmanında (Renk 8 Gri, 0.09 mm ince çizgi) toplar; mükerrer
     (`INSERT`, `LINE`) ve sıfır uzunluklu (< 1 mm) çöp nesneleri siler.
  2. `rehabilitate_electrical_dxf`:
     Lejant ve evrensel blok sınıflandırıcısı ile yanlış katmana düşmüş
     elektrik armatürlerini, anahtarları, yangın elemanlarını, panoları,
     yazıları ve OLE tablolarını projenin kendi elektrik katmanlarına
     taşır; ardından `TopologicalWireHealer` ile mükerrer kabloları,
     doğrusal kopuklukları ve sembole değmeyen kablo uçlarını onarır.
  3. `merge_arch_and_elec_dxf`:
     Tek `MIMARI` katmanlı mimari altlık ile onarılmış elektrik çizimini
     blok çakışması olmadan birleşik proje DXF'inde toplar.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import math
from pathlib import Path
import re
import tempfile
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import ezdxf
from ezdxf.addons.importer import Importer
from shapely.geometry import Point, Polygon, box

from core.cad.cad_safety import CADSafetyGuard, UnitScaleResolver
from core.healer.wire_healer import TopologicalWireHealer
from core.model.entities import PlacedSymbol, TextToken

from .disiplin_ayirici import (
    build_container_block_names,
    classify_insert_role,
    classify_paths_arch_vs_elec,
    detect_cloned_architectural_entities,
    is_container_insert,
)
from .metin_temizleyici import norm_tr
from .schema import CanonicalProjectModel, RawCADSnapshot, RawInsert, RawText


def _ensure_layer(
    doc: Any,
    name: str,
    color: int = 7,
    lineweight: int = 25,
    linetype: str = "CONTINUOUS",
    locked: bool = False,
) -> None:
    """Hedef katmanın dokümanda uygun renk/kalınlık ayarlarıyla tanımlı olmasını sağlar."""
    if linetype not in doc.linetypes:
        linetype = "CONTINUOUS"
    if name in doc.layers:
        layer = doc.layers.get(name)
        layer.color = color
        layer.dxf.lineweight = lineweight
        layer.dxf.linetype = linetype
        layer.lock() if locked else layer.unlock()
    else:
        layer = doc.layers.add(
            name=name,
            color=color,
            linetype=linetype,
            lineweight=lineweight,
        )
        if locked:
            layer.lock()


def _set_entity_layer_bylayer(ent: Any, target_layer: str) -> None:
    """Varlığın ve varsa ATTRIB alt öğelerinin katmanını BYLAYER uyumlu günceller."""
    ent.dxf.layer = target_layer
    if hasattr(ent.dxf, "color"):
        ent.dxf.color = 256
    if hasattr(ent.dxf, "lineweight"):
        ent.dxf.lineweight = -1
    if ent.dxftype() == "INSERT":
        for att in getattr(ent, "attribs", ()):
            att.dxf.layer = target_layer
            if hasattr(att.dxf, "color"):
                att.dxf.color = 256
            if hasattr(att.dxf, "lineweight"):
                att.dxf.lineweight = -1


def _collect_used_blocks_recursive(doc: Any, root_block_names: Set[str]) -> Set[str]:
    """Verilen kök blok adlarından erişilen tüm alt blokları özyineli toplar."""
    visited: Set[str] = set()
    stack = [b for b in root_block_names if b]
    while stack:
        bn = stack.pop()
        if bn in visited or bn not in doc.blocks:
            continue
        visited.add(bn)
        blk = doc.blocks.get(bn)
        for sub in blk:
            if sub.dxftype() == "INSERT":
                cbn = getattr(sub.dxf, "name", "")
                if cbn and cbn not in visited:
                    stack.append(cbn)
    return visited


def consolidate_architecture_to_single_layer(
    doc_arch: Any,
    target_layer: str = "MIMARI",
    color: int = 8,
    lineweight: int = 9,
    purge_unused_layers: bool = True,
) -> Dict[str, Any]:
    """
    Mimari dokümandaki tüm MSP nesnelerini ve blok içi geometrileri tek bir
    `MIMARI` katmanında toplar; mükerrer `INSERT`, mükerrer `LINE` ve < 1 mm
    sıfır boyutlu `LINE` nesnelerini temizler.
    """
    unit_mm, unit_src = UnitScaleResolver.resolve_unit_to_mm(doc_arch)
    dup_tol = max(10.0 / max(unit_mm, 1e-6), 0.1)     # ~1 cm
    zero_tol = max(1.0 / max(unit_mm, 1e-6), 0.01)    # ~1 mm

    _ensure_layer(doc_arch, target_layer, color=color, lineweight=lineweight, locked=False)
    msp = doc_arch.modelspace()

    # 1. Mükerrer INSERT, sıfır boy LINE ve mükerrer LINE temizliği
    seen_inserts: Set[Tuple[Any, ...]] = set()
    seen_lines: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()
    deleted_dup_inserts = 0
    deleted_dup_lines = 0
    deleted_zero_lines = 0

    to_delete: List[Any] = []
    for ent in list(msp):
        dt = ent.dxftype()
        if dt == "INSERT":
            p = ent.dxf.insert
            key = (
                (getattr(ent.dxf, "name", "") or "").strip().lower(),
                round(float(p.x) / dup_tol),
                round(float(p.y) / dup_tol),
                round(float(getattr(ent.dxf, "rotation", 0.0) or 0.0) % 360.0, 1),
                round(float(getattr(ent.dxf, "xscale", 1.0) or 1.0), 2),
                round(float(getattr(ent.dxf, "yscale", 1.0) or 1.0), 2),
            )
            if key in seen_inserts:
                to_delete.append(ent)
                deleted_dup_inserts += 1
                continue
            seen_inserts.add(key)
        elif dt == "LINE":
            s, e = ent.dxf.start, ent.dxf.end
            length = math.hypot(float(e.x) - float(s.x), float(e.y) - float(s.y))
            if length < zero_tol:
                to_delete.append(ent)
                deleted_zero_lines += 1
                continue
            p1 = (round(float(s.x) / dup_tol), round(float(s.y) / dup_tol))
            p2 = (round(float(e.x) / dup_tol), round(float(e.y) / dup_tol))
            if p1 == p2:
                to_delete.append(ent)
                deleted_zero_lines += 1
                continue
            lkey = (min(p1, p2), max(p1, p2))
            if lkey in seen_lines:
                to_delete.append(ent)
                deleted_dup_lines += 1
                continue
            seen_lines.add(lkey)

    for ent in to_delete:
        msp.delete_entity(ent)

    # 2. Kalan tüm MSP varlıklarını tek MIMARI katmanına taşı
    moved_msp_entities = 0
    root_blocks: Set[str] = set()
    for ent in msp:
        if getattr(ent.dxf, "layer", "") != target_layer:
            moved_msp_entities += 1
        _set_entity_layer_bylayer(ent, target_layer)
        if ent.dxftype() == "INSERT":
            bn = getattr(ent.dxf, "name", "")
            if bn:
                root_blocks.add(bn)

    # 3. Mimari blokların iç katmanlarını da tek MIMARI katmanına çek (XREF hariç)
    used_blocks = _collect_used_blocks_recursive(doc_arch, root_blocks)
    moved_block_entities = 0
    for bn in used_blocks:
        blk = doc_arch.blocks.get(bn)
        if blk is None or CADSafetyGuard.is_xref_block_record(blk, bn):
            continue
        for sub in blk:
            if sub.dxftype() in ("BLOCK", "ENDBLK"):
                continue
            if getattr(sub.dxf, "layer", "") != target_layer:
                moved_block_entities += 1
            _set_entity_layer_bylayer(sub, target_layer)

    # 4. Kullanılmayan blok tanımlarını ve boş eski katmanları temizle (0 ve Defpoints hariç)
    purged_layers = _purge_unused_layers(doc_arch, {target_layer}) if purge_unused_layers else 0

    return {
        "target_layer": target_layer,
        "unit_mm": unit_mm,
        "unit_source": unit_src,
        "deleted_duplicate_inserts": deleted_dup_inserts,
        "deleted_duplicate_lines": deleted_dup_lines,
        "deleted_zero_length_lines": deleted_zero_lines,
        "moved_msp_entities": moved_msp_entities,
        "moved_block_entities": moved_block_entities,
        "purged_layers": purged_layers,
        "remaining_msp_entities": len(msp),
    }


def discover_project_electrical_layers(doc: Any) -> Dict[str, str]:
    """
    Dokümanda halihazırda kullanılan katman isimlendirme geleneğine (`00-*` veya `E-*`)
    uygun şekilde standart elektrik kategori -> hedef katman eşlemesi üretir.
    """
    existing = [lay.dxf.name for lay in doc.layers]
    existing_up = {norm_tr(n).upper(): n for n in existing}
    uses_00_prefix = sum(1 for n in existing if n.upper().startswith("00-")) >= 3

    def _pick(match_tokens: Tuple[str, ...], default_00: str, default_e: str) -> str:
        # Tam ön-ek eşleşmelerini öncele
        candidates: List[str] = []
        for up, orig in existing_up.items():
            if any(tok in up for tok in match_tokens):
                candidates.append(orig)
        if candidates:
            candidates.sort(key=lambda s: (0 if s.upper().startswith(("00-", "E-")) else 1, len(s), s))
            return candidates[0]
        return default_00 if uses_00_prefix else default_e

    return {
        "AYDINLATMA": _pick(("00-AYD", "E-LITE", "AYDINLATMA", "AYD"), "00-AYD", "E-AYDINLATMA-ARMATUR"),
        "ANAHTAR": _pick(("00-ANHTR", "ANHTR", "ANAHTAR", "E-SWITCH"), "00-ANHTR", "E-ANAHTAR"),
        "PRİZ": _pick(("00-PRZ", "PRIZ", "E-POWR-SOCK"), "00-PRZ", "E-PRIZ-SORTI"),
        "PANO / TABLO": _pick(("00-TABLO", "00-PANO", "E-PANO", "TABLO", "PANO"), "00-TABLO", "E-PANO"),
        "YANGIN ALGILAMA": _pick(("00-YANGIN", "YANGIN", "FIRE"), "00-YANGIN", "E-YANGIN"),
        "TOPRAKLAMA": _pick(("00-TOPRAK", "E-GRND", "TOPRAKLAMA"), "00-TOPRAK", "E-TOPRAKLAMA"),
        "ELKYAZ": _pick(("00-ELKYAZ", "ELKYAZ", "E-ETIKET"), "00-ELKYAZ", "E-ETIKET-TABLO"),
    }


def _layer_palette_for_name(name: str) -> Tuple[int, int]:
    up = norm_tr(name).upper()
    if "ANHTR" in up or "ANAHTAR" in up:
        return 3, 20      # Yeşil, 0.20mm
    if "AYD" in up or "LITE" in up:
        return 2, 25      # Sarı, 0.25mm
    if "PRZ" in up or "PRIZ" in up:
        return 30, 25     # Turuncu, 0.25mm
    if "TABLO" in up or "PANO" in up:
        return 5, 35      # Mavi, 0.35mm
    if "YANGIN" in up or "FIRE" in up:
        return 1, 25      # Kırmızı, 0.25mm
    if "TOPRAK" in up or "GRND" in up:
        return 94, 30     # Koyu yeşil, 0.30mm
    if "ELKYAZ" in up or "ETIKET" in up:
        return 7, 18      # Beyaz/siyah, 0.18mm
    return 7, 25


def _build_wire_healer_inputs_from_doc(
    doc: Any,
    snapshot: RawCADSnapshot,
    model: CanonicalProjectModel,
) -> Tuple[List[PlacedSymbol], List[TextToken]]:
    """Dokümandaki güncel MSP nesnelerinden TopologicalWireHealer için evrensel girdi üretir."""
    snap_ins_by_handle: Dict[str, RawInsert] = {
        ins.handle: ins for ins in snapshot.inserts if not ins.parent_chain and ins.handle
    }
    msp = doc.modelspace()
    symbols: List[PlacedSymbol] = []
    texts: List[TextToken] = []

    du_to_m = max(model.unit.du_to_m, 1e-6)
    default_half = max(0.15 / du_to_m, 0.5)

    for ent in msp:
        dt = ent.dxftype()
        hnd = str(getattr(ent.dxf, "handle", "") or "")
        lay = str(getattr(ent.dxf, "layer", "0") or "0")
        col = int(getattr(ent.dxf, "color", 256) or 256)
        if dt == "INSERT":
            raw_ins = snap_ins_by_handle.get(hnd)
            if raw_ins is not None:
                px, py, pz = raw_ins.x, raw_ins.y, raw_ins.z
                bname = raw_ins.effective_name or raw_ins.block_name
                poly = box(raw_ins.bbox.minx, raw_ins.bbox.miny, raw_ins.bbox.maxx, raw_ins.bbox.maxy)
                role, cat, _, _, _ = classify_insert_role(raw_ins, model.legend)
                if role != "ELECTRICAL":
                    continue
                cls_label = cat or "ELECTRICAL"
                rot = raw_ins.rotation
                sx, sy = raw_ins.xscale, raw_ins.yscale
                attribs = dict(raw_ins.attribs)
            else:
                p = ent.dxf.insert
                px, py, pz = float(p.x), float(p.y), float(getattr(p, "z", 0.0))
                bname = str(getattr(ent.dxf, "name", "") or "")
                poly = box(px - default_half, py - default_half, px + default_half, py + default_half)
                cls_label = "ELECTRICAL"
                rot = float(getattr(ent.dxf, "rotation", 0.0) or 0.0)
                sx = float(getattr(ent.dxf, "xscale", 1.0) or 1.0)
                sy = float(getattr(ent.dxf, "yscale", 1.0) or 1.0)
                attribs = {}
            symbols.append(
                PlacedSymbol(
                    block_name=bname,
                    clean_family_name=bname,
                    pos=(px, py, pz),
                    scale=(sx, sy, 1.0),
                    rotation=rot,
                    layer=lay,
                    color=col,
                    bbox=poly,
                    attribs=attribs,
                    classification=cls_label,
                    dxf_handle=hnd,
                )
            )
        elif dt in ("TEXT", "MTEXT"):
            txt_val = ent.dxf.text if dt == "TEXT" else ent.text
            ins_p = getattr(ent.dxf, "insert", None)
            if ins_p is None:
                continue
            tx, ty = float(ins_p.x), float(ins_p.y)
            th = float(getattr(ent.dxf, "height", getattr(ent.dxf, "char_height", 1.0)) or 1.0)
            texts.append(
                TextToken(
                    text=str(txt_val or ""),
                    pos=(tx, ty, 0.0),
                    height=th,
                    rotation=float(getattr(ent.dxf, "rotation", 0.0) or 0.0),
                    layer=lay,
                    color=col,
                    bbox=box(tx, ty, tx + max(th, 1.0), ty + max(th, 1.0)),
                    dxf_handle=hnd,
                )
            )

    return symbols, texts


def rehabilitate_electrical_dxf(
    doc_elec: Any,
    snapshot: RawCADSnapshot,
    model: CanonicalProjectModel,
    drawing_name: str = "electrical",
) -> Dict[str, Any]:
    """
    Saf elektrik DXF dokümanı üzerinde:
      1) Yanlış katmandaki INSERT (armatür, anahtar, yangın, pano/detay),
         TEXT/MTEXT ve OLE2FRAME nesnelerini projenin doğru elektrik katmanlarına taşır,
      2) `TopologicalWireHealer` ile üst üste binen çift kablo çizgilerini,
         doğrusal kopuklukları ve sembole <= 5 cm kalmış uçları otomatik onarır.
    """
    msp = doc_elec.modelspace()
    layer_before = Counter(str(getattr(e.dxf, "layer", "0") or "0") for e in msp)
    layer_map = discover_project_electrical_layers(doc_elec)
    for target_name in set(layer_map.values()):
        if target_name not in doc_elec.layers:
            c, lw = _layer_palette_for_name(target_name)
            _ensure_layer(doc_elec, target_name, color=c, lineweight=lw, locked=False)

    snap_ins_by_handle: Dict[str, RawInsert] = {
        ins.handle: ins for ins in snapshot.inserts if not ins.parent_chain and ins.handle
    }

    moved_inserts: Counter = Counter()
    moved_texts: Counter = Counter()
    moved_ole: Counter = Counter()

    for ent in msp:
        dt = ent.dxftype()
        hnd = str(getattr(ent.dxf, "handle", "") or "")
        cur_lay = str(getattr(ent.dxf, "layer", "0") or "0")
        cur_lay_u = norm_tr(cur_lay).upper()

        if dt == "INSERT":
            raw_ins = snap_ins_by_handle.get(hnd)
            if raw_ins is None:
                continue
            verdict = CADSafetyGuard.check_entity_mutable(doc_elec, ent)
            if not verdict.allowed:
                continue

            role, cat, disc, _, src = classify_insert_role(raw_ins, model.legend)
            if role != "ELECTRICAL":
                continue
            # Buat ve hat/linye etiketi kendi devresinin katmanında kalır
            if cat in ("BUAT", "HAT / LİNYE ETİKETİ", "DİĞER ELEKTRİK", "BELİRSİZ"):
                continue

            is_generic_or_frame = cur_lay_u in ("0", "DEFPOINTS") or any(
                fk in cur_lay_u for fk in ("CERCEVE", "ANTET", "BORDER", "00-YAZI")
            )
            # Yalnızca lejanttan, blok adından veya şema/çerçeve iç katman analizinden pozitif kanıtlı olanları taşı
            if src not in ("LEJANT", "BLOK_ADI") and not (is_generic_or_frame and cat in ("PANO / TABLO", "SEMA / DETAY")):
                continue

            target_lay: Optional[str] = None
            if cat in ("AYDINLATMA", "ANAHTAR", "PRİZ", "YANGIN ALGILAMA", "PANO / TABLO", "TOPRAKLAMA"):
                target_lay = layer_map.get(cat)
            elif cat == "SEMA / DETAY":
                target_lay = layer_map.get("ELKYAZ")

            if target_lay and target_lay != cur_lay:
                _set_entity_layer_bylayer(ent, target_lay)
                moved_inserts[(cur_lay, target_lay, cat)] += 1

        elif dt in ("TEXT", "MTEXT"):
            if cur_lay_u in ("0", "00-YAZI", "YAZI") or any(fk in cur_lay_u for fk in ("CERCEVE", "ANTET")):
                target_lay = layer_map["ELKYAZ"]
                if target_lay != cur_lay:
                    _set_entity_layer_bylayer(ent, target_lay)
                    moved_texts[(cur_lay, target_lay)] += 1

        elif dt == "OLE2FRAME":
            if cur_lay_u in ("0", "00-LINYE_NO") or any(fk in cur_lay_u for fk in ("CERCEVE", "ANTET", "YAZI")):
                target_lay = layer_map["PANO / TABLO"]
                if target_lay != cur_lay:
                    _set_entity_layer_bylayer(ent, target_lay)
                    moved_ole[(cur_lay, target_lay)] += 1

    # Topolojik kablo ve çizgi onarımı (auto_approvable=True güvenli müdahaleler)
    placed_syms, text_tokens = _build_wire_healer_inputs_from_doc(doc_elec, snapshot, model)
    plan_wh = TopologicalWireHealer.analyze_and_propose(
        doc_elec,
        symbols=placed_syms,
        texts=text_tokens,
        drawing_name=drawing_name,
    )
    auto_wire_ids = {p.proposal_id for p in plan_wh.proposals if p.auto_approvable}
    wire_applied = TopologicalWireHealer.apply_plan(doc_elec, plan_wh, approved_proposal_ids=auto_wire_ids)

    layer_after = Counter(str(getattr(e.dxf, "layer", "0") or "0") for e in msp)

    return {
        "layer_map": layer_map,
        "moved_inserts": {f"{a} -> {b} ({cat})": cnt for (a, b, cat), cnt in sorted(moved_inserts.items())},
        "moved_inserts_total": sum(moved_inserts.values()),
        "moved_texts": {f"{a} -> {b}": cnt for (a, b), cnt in sorted(moved_texts.items())},
        "moved_texts_total": sum(moved_texts.values()),
        "moved_ole": {f"{a} -> {b}": cnt for (a, b), cnt in sorted(moved_ole.items())},
        "moved_ole_total": sum(moved_ole.values()),
        "wire_heal_summary": dict(plan_wh.summary_counts),
        "wire_applied": wire_applied,
        "wire_applied_total": len(wire_applied),
        "layer_before": dict(sorted(layer_before.items())),
        "layer_after": dict(sorted(layer_after.items())),
    }


def merge_arch_and_elec_dxf(
    doc_arch_clean: Any,
    doc_elec_clean: Any,
    out_path: Path,
) -> Path:
    """
    Tek `MIMARI` katmanında toplanmış mimari altlık ile onarılmış elektrik DXF'ini
    birleşik proje olarak kaydeder (`OLE2FRAME` ve blok tanımları korunarak).
    """
    with tempfile.TemporaryDirectory() as td:
        tmp_elec = Path(td) / "elec_base.dxf"
        tmp_arch = Path(td) / "arch_src.dxf"
        doc_elec_clean.saveas(str(tmp_elec))

        # Elektrikteki blok adlarıyla çakışan mimari blok varsa geçici yeniden adlandır
        # (* anonim blokları ve _ ile başlayan standart AutoCAD ok/ölçü blokları hariç)
        elec_blk_names = {b.name for b in doc_elec_clean.blocks if not b.name.startswith(("*", "_"))}
        arch_copy = doc_arch_clean
        rename_map: Dict[str, str] = {}
        for blk in list(arch_copy.blocks):
            bn = blk.name
            if bn.startswith(("*", "_")) or bn not in elec_blk_names:
                continue
            new_bn = f"ARCH__{bn}"
            while new_bn in elec_blk_names or new_bn in arch_copy.blocks:
                new_bn += "_"
            rename_map[bn] = new_bn
        if rename_map:
            for bn, new_bn in rename_map.items():
                arch_copy.blocks.rename_block(bn, new_bn)
            for ds in arch_copy.dimstyles:
                for attr in ("dimblk", "dimblk1", "dimblk2", "dimldrblk"):
                    val = str(getattr(ds.dxf, attr, "") or "")
                    if val in rename_map:
                        setattr(ds.dxf, attr, rename_map[val])
            for ent in arch_copy.modelspace():
                if ent.dxftype() == "INSERT" and ent.dxf.name in rename_map:
                    ent.dxf.name = rename_map[ent.dxf.name]
            for blk in arch_copy.blocks:
                for sub in blk:
                    if sub.dxftype() == "INSERT" and sub.dxf.name in rename_map:
                        sub.dxf.name = rename_map[sub.dxf.name]

        arch_copy.saveas(str(tmp_arch))

        merged_doc = ezdxf.readfile(str(tmp_elec))
        arch_src = ezdxf.readfile(str(tmp_arch))
        importer = Importer(arch_src, merged_doc)
        importer.import_modelspace()
        importer.finalize()

        _ensure_layer(merged_doc, "MIMARI", color=8, lineweight=9, locked=False)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        merged_doc.saveas(str(out_path))
    return out_path


_RE_ELEC_TEXT = re.compile(
    r"(?:\d+\s*[xX*]\s*\d+|N2XH|NYY|NYM|NHXMH|FE180|PH120|LSZH|CAT\s*[567]|"
    r"\b(?:WC|LV|HV)\s*/\s*\d+|\b(?:VLD|MEB|EEB|AGADP|UPS|TRAFO|KAKR|RCD|TMS|TMŞ|AOS|SCADA|PLC|RTU)\b|"
    r"\b\d+(?:[.,]\d+)?\s*(?:kW|kVA|VA|kA|mA|mm2|Ohm|Ω)\b|PANO|TABLO|LİNYE|LINYE|TOPRAKLAMA|AYDINLATMA|"
    r"KUVVETL[Iİ]\s*AKIM|ZAYIF\s*AKIM|KOLON\s*[SŞ]EMA|TEK\s*HAT|LEJANT)",
    re.IGNORECASE,
)
_RE_SHORT_ELEC_TAG = re.compile(
    r"^(?:[APKLBTZ]|DT|AT|OT|IS|TV|ID|EKK|ETB|VLD|MEB)[- ]?\d{1,3}[A-Z]?$",
    re.IGNORECASE,
)

# Yalnızca uluslararası AIA/ISO/BIM (Revit + ArchiCAD) disiplin ön-ekleri ve çekirdek evrensel mimari terimler
# (ofis-bazlı kelime avcılığı yerine şekil + topoloji + mekânsal/tekrar konsensüsü kullanılır!)
_MIXED_ARCH_LAYER_PREFIXES: Tuple[str, ...] = (
    "A-", "A_", "I-", "I_", "S-", "S_", "M-", "M_", "G-PLAN",
    "STRUCTURAL-", "STRUCTURAL_", "SHELL-", "SHELL_",
)
_MIXED_ARCH_LAYER_KEYS: Tuple[str, ...] = (
    "ARKA_PLAN", "CARTIGLIO", "ARREDO", "P-SANR",
    "MIMARI", "MİMARI", "TARAMA", "HATCH",
    "G-ANNO-SYMB", "A-DETL", "A-FLOR", "A-GENM", "A-AREA", "M-AREA", "M-HVAC", "M-EQPM",
)
_ELEC_SUB_LAYER_KEYS: Tuple[str, ...] = (
    "E-", "E_", "EE-", "00-AYD", "00-ANHTR", "00-PRZ", "00-TABLO", "00-PANO", "00-YANGIN",
    "00-TOPRAK", "00-KOL", "00-LINYE", "00-24V", "00-06", "00-ELKYAZ", "00-YAZI",
    "00-TEL", "00-TV", "00-INTERCOM",
    "PRT-EL-", "PRT-EL_", "PRT_", "YP-EL",
    "ELEKTRIK", "KABLO", "TRAY", "TAVA", "TOPRAK", "CABL", "LITE", "POWR",
)


def _purge_unused_layers(doc: Any, keep_layers: Set[str]) -> int:
    """Referanssız ölü blok tanımlarını ve artık kullanılmayan tüm eski katmanları temizler."""
    roots: Set[str] = set()
    for layout in doc.layouts:
        for ent in layout:
            if ent.dxftype() == "INSERT":
                bn = getattr(ent.dxf, "name", "")
                if bn:
                    roots.add(bn)
    used_blocks = _collect_used_blocks_recursive(doc, roots)

    for ds in doc.dimstyles:
        for attr in ("dimblk", "dimblk1", "dimblk2", "dimldrblk"):
            v = str(getattr(ds.dxf, attr, "") or "").strip()
            if v:
                used_blocks.add(v)

    for blk in list(doc.blocks):
        bn = blk.name
        if bn.startswith(("*", "_")) or bn in used_blocks or CADSafetyGuard.is_xref_block_record(blk, bn):
            continue
        try:
            doc.blocks.delete_block(bn, safe=False)
        except Exception:
            pass

    used: Set[str] = {"0", "Defpoints", "DEFPOINTS"} | set(keep_layers)
    for layout in doc.layouts:
        for ent in layout:
            used.add(str(getattr(ent.dxf, "layer", "0") or "0"))
    for bn in used_blocks:
        blk = doc.blocks.get(bn)
        if blk is None:
            continue
        for sub in blk:
            used.add(str(getattr(sub.dxf, "layer", "0") or "0"))

    purged = 0
    for lay in list(doc.layers):
        ln = lay.dxf.name
        if ln in used or ln.lower() in ("0", "defpoints"):
            continue
        try:
            doc.layers.discard(ln)
            purged += 1
        except Exception:
            pass
    return purged


def _is_obvious_arch_layer_name(layer: str) -> bool:
    lu = norm_tr(layer).upper()
    if lu.startswith(_MIXED_ARCH_LAYER_PREFIXES):
        return True
    return any(k in lu for k in _MIXED_ARCH_LAYER_KEYS)


def _is_obvious_elec_layer_name(layer: str) -> bool:
    lu = norm_tr(layer).upper()
    if lu.startswith(("E-", "E_", "PRT-EL-", "YP-EL", "EL-")):
        return True
    return any(k in lu for k in _ELEC_SUB_LAYER_KEYS)


def separate_and_simplify_to_two_layers(
    src_dxf: Union[str, Path],
    snapshot: RawCADSnapshot,
    model: CanonicalProjectModel,
    *,
    out_arch_dxf: Optional[Union[str, Path]] = None,
    out_elec_dxf: Optional[Union[str, Path]] = None,
    out_merged_dxf: Optional[Union[str, Path]] = None,
    arch_layer: str = "MIMARI",
    elec_layer: str = "ELEKTRIK",
    calc_layer: str = "HESAPLAR_TABLOLAR",
    heal_wires: bool = True,
) -> Dict[str, Any]:
    """
    Herhangi bir Bina veya Metro DXF çizimini evrensel olarak ayırır ve sadeleştirir:
      1) `out_arch_dxf`: Yalnızca Mimari/Statik/Mekanik altlık -> **1 Layer (`MIMARI`)**
      2) `out_elec_dxf`: Altlıksız saf Elektrik çizimi + Excel/Hesap tabloları ->
         **Maksimum 2 Layer (`ELEKTRIK` + `HESAPLAR_TABLOLAR`)**
      3) `out_merged_dxf` (opsiyonel): Birleşik temiz çizim (`MIMARI` + `ELEKTRIK` + `HESAPLAR_TABLOLAR`)
    """
    du_to_m = max(model.unit.du_to_m, 1e-6)
    containers = build_container_block_names(snapshot.inserts, du_to_m)

    # 1. Hesap/Tablo/OLE tutamakları (handle) ve sınırlayıcı kutuları
    calc_handles: Set[str] = set()
    calc_boxes: List[Tuple[float, float, float, float]] = []
    for o in snapshot.ole_objects:
        if o.space == "MODEL":
            if o.handle:
                calc_handles.add(o.handle)
            calc_boxes.append((o.bbox.minx, o.bbox.miny, o.bbox.maxx, o.bbox.maxy))
    for tb in snapshot.acad_tables:
        if tb.space == "MODEL" and tb.handle:
            calc_handles.add(tb.handle)
    for nt in model.tables:
        if nt.bbox_du is not None:
            calc_boxes.append((nt.bbox_du.minx, nt.bbox_du.miny, nt.bbox_du.maxx, nt.bbox_du.maxy))
    for fb in model.formula_blocks:
        for h in fb.source_handles:
            calc_handles.add(h)
        calc_boxes.append((fb.bbox_du.minx, fb.bbox_du.miny, fb.bbox_du.maxx, fb.bbox_du.maxy))
    for sh in model.sheets:
        if sh.space == "MODEL" and sh.role in ("YUKLEME_CETVELI", "GERILIM_DUSUMU", "LEJANT"):
            calc_boxes.append((sh.bbox_du.minx, sh.bbox_du.miny, sh.bbox_du.maxx, sh.bbox_du.maxy))

    def _in_calc_box(x: float, y: float) -> bool:
        return any(bx0 <= x <= bx1 and by0 <= y <= by1 for bx0, by0, bx1, by1 in calc_boxes)

    # 2. Kopya çakıştırma (cKDTree) ve yol/blok sınıflandırma ön analizi
    by_sheet_ins: Dict[str, List[RawInsert]] = defaultdict(list)
    by_sheet_pth: Dict[str, List[Any]] = defaultdict(list)
    msp_sheets = [sh for sh in model.sheets if sh.space == "MODEL"]
    for ins in snapshot.inserts:
        if ins.space == "MODEL" and not ins.parent_chain:
            for sh in msp_sheets:
                if sh.bbox_du.contains_xy(ins.x, ins.y):
                    by_sheet_ins[sh.frame_id].append(ins)
                    break
    for p in snapshot.paths:
        if p.space == "MODEL" and not p.parent_chain:
            cx, cy = p.bbox.center
            for sh in msp_sheets:
                if sh.bbox_du.contains_xy(cx, cy):
                    by_sheet_pth[sh.frame_id].append(p)
                    break

    view_bundles = [
        {"view_id": sh.frame_id, "role": sh.role, "paths": by_sheet_pth[sh.frame_id], "inserts": by_sheet_ins[sh.frame_id]}
        for sh in msp_sheets
    ]
    cloned_paths, cloned_inserts = detect_cloned_architectural_entities(view_bundles, du_to_m)

    elec_inserts: List[RawInsert] = []
    ins_role_by_handle: Dict[str, str] = {}
    mixed_container_names: Set[str] = set()
    for ins in snapshot.inserts:
        if ins.space != "MODEL":
            continue
        bname = ins.effective_name or ins.block_name
        role, _, _, _, _ = classify_insert_role(ins, model.legend, cloned_insert_ids=cloned_inserts)
        if not ins.parent_chain and ins.handle:
            ins_role_by_handle[ins.handle] = role
        if role == "ELECTRICAL":
            elec_inserts.append(ins)
            if ins.parent_chain:
                for seg in ins.parent_chain.split(">"):
                    sn = seg.strip()
                    if sn and sn in containers:
                        mixed_container_names.add(sn)
        if is_container_insert(ins, du_to_m, containers):
            bu = norm_tr(bname).upper()
            if "-ELC-" in bu or "ELC" in bu:
                mixed_container_names.add(bname)

    path_split = classify_paths_arch_vs_elec(
        [p for p in snapshot.paths if p.space == "MODEL" and not p.parent_chain],
        elec_inserts,
        du_to_m,
        cloned_path_ids=cloned_paths,
        container_block_names=containers,
    )
    arch_path_handles = {p.handle for p in path_split["ARCHITECTURAL"] if p.handle}
    wire_path_handles = {p.handle for p in path_split["ELECTRICAL_WIRE"] if p.handle}

    # Şema/hesap paftalarının koruma kutuları (tek hat / kolon şeması içi metinler mimari sayılmaz)
    schematic_boxes: List[Tuple[float, float, float, float]] = [
        (sh.bbox_du.minx, sh.bbox_du.miny, sh.bbox_du.maxx, sh.bbox_du.maxy)
        for sh in model.sheets
        if sh.space == "MODEL" and sh.role in ("KOLON_SEMASI", "TEK_HAT", "YUKLEME_CETVELI", "GERILIM_DUSUMU", "LEJANT")
    ]

    def _in_schematic_box(x: float, y: float) -> bool:
        return any(bx0 <= x <= bx1 and by0 <= y <= by1 for bx0, by0, bx1, by1 in schematic_boxes)

    # Çift yönlü Katman-Bazlı Geometrik Çoğunluk Oylaması (kelime listesine bağımlı olmadan!)
    lay_votes: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    for p in path_split["ARCHITECTURAL"]:
        lay_votes[p.layer][0] += 1
    for p in path_split["ELECTRICAL_WIRE"]:
        lay_votes[p.layer][1] += 1
    for ins in snapshot.inserts:
        if ins.space == "MODEL" and not ins.parent_chain and ins.handle:
            r = ins_role_by_handle.get(ins.handle)
            if r == "ARCHITECTURAL":
                lay_votes[ins.layer][0] += 1
            elif r == "ELECTRICAL":
                lay_votes[ins.layer][1] += 1
    geo_arch_layers: Set[str] = {
        ln for ln, (ac, ec) in lay_votes.items()
        if ln.upper() not in ("0", "", "DEFPOINTS")
        and not _is_obvious_elec_layer_name(ln)
        and ac >= 3
        and (ac / max(ac + ec, 1)) >= 0.75
    }
    geo_elec_layers: Set[str] = {
        ln for ln, (ac, ec) in lay_votes.items()
        if ln.upper() not in ("0", "", "DEFPOINTS")
        and not _is_obvious_arch_layer_name(ln)
        and ec >= 3
        and (ec / max(ac + ec, 1)) >= 0.75
    }

    # Doğrulanmış elektrik çapa noktaları (semboller + kablo uçları/orta noktaları) -> cKDTree
    import numpy as np
    from scipy.spatial import cKDTree

    elec_anchor_pts: List[Tuple[float, float]] = [(ins.x, ins.y) for ins in elec_inserts]
    for p in path_split["ELECTRICAL_WIRE"]:
        if p.points:
            elec_anchor_pts.append(p.points[0])
            elec_anchor_pts.append(p.points[-1])
            if len(p.points) > 2:
                elec_anchor_pts.append(p.points[len(p.points) // 2])
    elec_anchor_tree = (
        cKDTree(np.array(elec_anchor_pts, dtype=np.float64)) if elec_anchor_pts else None
    )

    msp_texts = [t for t in snapshot.texts if t.space == "MODEL" and not t.parent_chain and t.handle]
    txt_by_handle: Dict[str, RawText] = {t.handle: t for t in msp_texts}

    # Saf Geometri: Merdiven basamak numarası dizisi tespiti (katman adı ne olursa olsun!)
    # 1..40 arası çıplak tam sayılardan 0.12–0.75 m aralıkla >= 4 komşulu kümeler -> mimari basamak numarası
    stair_num_handles: Set[str] = set()
    bare_ints = [
        t for t in msp_texts
        if not _is_obvious_elec_layer_name(t.layer)
        and not _in_calc_box(t.x, t.y)
        and not _in_schematic_box(t.x, t.y)
        and re.match(r"^\d{1,2}$", (t.text or "").strip())
        and 1 <= int((t.text or "0").strip()) <= 40
    ]
    if len(bare_ints) >= 4:
        bi_pts = np.array([[t.x, t.y] for t in bare_ints], dtype=np.float64)
        bi_tree = cKDTree(bi_pts)
        r_step_du = max(0.85 / du_to_m, 1.0)
        # Bağlı bileşenler: her bileşen >= 4 ardışık/yakın basamak numarası içeriyorsa merdiven numarasıdır
        adj = bi_tree.query_ball_tree(bi_tree, r=r_step_du)
        visited_bi: Set[int] = set()
        for i0 in range(len(bare_ints)):
            if i0 in visited_bi:
                continue
            comp: List[int] = []
            stk = [i0]
            visited_bi.add(i0)
            while stk:
                cur = stk.pop()
                comp.append(cur)
                for nb in adj[cur]:
                    if nb not in visited_bi:
                        visited_bi.add(nb)
                        stk.append(nb)
            if len(comp) >= 4:
                vals = {int(bare_ints[ci].text.strip()) for ci in comp}
                if len(vals) >= 4:
                    for ci in comp:
                        stair_num_handles.add(bare_ints[ci].handle)

    # Salt-Yazı Katman Konsensüsü: geometrisi olmayan bilinmeyen bir yazı katmanında
    # 0 elektrik metni varsa ve yazıların >= %65'i basamak numarası veya elektrikten > 1.2 m uzaksa -> ARCH
    text_only_by_lay: Dict[str, List[RawText]] = defaultdict(list)
    for rt in msp_texts:
        ln = rt.layer
        if (
            ln.upper() in ("0", "", "DEFPOINTS")
            or _is_obvious_elec_layer_name(ln)
            or _is_obvious_arch_layer_name(ln)
            or ln in geo_arch_layers
            or ln in geo_elec_layers
        ):
            continue
        if _in_calc_box(rt.x, rt.y) or _in_schematic_box(rt.x, rt.y):
            continue
        text_only_by_lay[ln].append(rt)

    geo_arch_text_layers: Set[str] = set()
    far_text_thresh_m = 1.25
    for ln, rts in text_only_by_lay.items():
        if len(rts) < 3:
            continue
        elec_txt_hits = sum(
            1 for rt in rts
            if _RE_ELEC_TEXT.search(rt.text or "") or _RE_SHORT_ELEC_TAG.match((rt.text or "").strip())
        )
        if elec_txt_hits > 0:
            continue
        arch_like = 0
        for rt in rts:
            if rt.handle in stair_num_handles:
                arch_like += 1
            elif elec_anchor_tree is not None:
                d_m = float(elec_anchor_tree.query([rt.x, rt.y])[0]) * du_to_m
                if d_m > far_text_thresh_m:
                    arch_like += 1
        # Kat planlarında birebir tekrar eden elektrik dışı mimari oda/şaft etiketleri (örn. 'HAV.B.', 'BANYO', 'TOPRAK DOLGU')
        txt_counts = Counter((rt.text or "").strip().upper() for rt in rts if (rt.text or "").strip())
        repeated_ratio = sum(c for c in txt_counts.values() if c >= 3) / max(len(rts), 1)
        if (arch_like / len(rts)) >= 0.65 or (len(rts) >= 4 and repeated_ratio >= 0.70):
            geo_arch_text_layers.add(ln)

    def _classify_top_entity(ent: Any) -> str:
        """Top-level ModelSpace varlığı için 'ARCH' | 'CALC' | 'ELEC' | 'MIXED_CONT' döner."""
        dt = ent.dxftype()
        hnd = str(getattr(ent.dxf, "handle", "") or "")
        lay = str(getattr(ent.dxf, "layer", "0") or "0")

        if dt in ("OLE2FRAME", "ACAD_TABLE") or (hnd and hnd in calc_handles):
            return "CALC"

        if dt == "INSERT":
            bn = str(getattr(ent.dxf, "name", "") or "")
            p = ent.dxf.insert
            if _in_calc_box(float(p.x), float(p.y)) and ins_role_by_handle.get(hnd) != "ARCHITECTURAL":
                return "CALC"
            if bn in mixed_container_names:
                return "MIXED_CONT"
            bu = norm_tr(bn).upper()
            if any(ak in bu for ak in ("-ARC-", "-STR-", "-MEC-", "ANTET", "CERCEVE")):
                return "ARCH"
            r = ins_role_by_handle.get(hnd)
            if r == "ARCHITECTURAL":
                return "ARCH"
            if r == "ELECTRICAL":
                return "ELEC"
            return "ARCH" if (_is_obvious_arch_layer_name(lay) or lay in geo_arch_layers) else "ELEC"

        if dt in ("TEXT", "MTEXT"):
            rt = txt_by_handle.get(hnd)
            tx = rt.x if rt else float(getattr(getattr(ent.dxf, "insert", None), "x", 0.0) or 0.0)
            ty = rt.y if rt else float(getattr(getattr(ent.dxf, "insert", None), "y", 0.0) or 0.0)
            txt_s = (rt.text if rt else (ent.dxf.text if dt == "TEXT" else ent.plain_text())) or ""
            if _in_calc_box(tx, ty):
                return "CALC"
            if _is_obvious_elec_layer_name(lay) or _RE_ELEC_TEXT.search(txt_s):
                return "ELEC"
            if _in_schematic_box(tx, ty) and not _is_obvious_arch_layer_name(lay):
                return "ELEC"
            if (
                _is_obvious_arch_layer_name(lay)
                or lay in geo_arch_layers
                or lay in geo_arch_text_layers
                or hnd in stair_num_handles
                or "G-ANNO" in norm_tr(lay).upper()
            ):
                return "ARCH"
            if _RE_SHORT_ELEC_TAG.match(txt_s.strip()) or lay in geo_elec_layers:
                return "ELEC"
            if elec_anchor_tree is not None:
                d_m = float(elec_anchor_tree.query([tx, ty])[0]) * du_to_m
                if d_m > 1.50:
                    return "ARCH"
            return "ELEC"

        # Çizgi / poligon / tarama / ölçü vb.
        if (_is_obvious_arch_layer_name(lay) or lay in geo_arch_layers) and not _is_obvious_elec_layer_name(lay):
            return "ARCH"
        if hnd and hnd in wire_path_handles:
            return "ELEC"
        if hnd and hnd in arch_path_handles:
            return "ARCH"
        if dt == "DIMENSION":
            return "ARCH"
        if _is_obvious_elec_layer_name(lay) or lay in geo_elec_layers:
            return "ELEC"
        # Konum calc_box içindeyse ve mimari değilse
        pos_pt = None
        if dt == "LINE":
            pos_pt = ((ent.dxf.start.x + ent.dxf.end.x) * 0.5, (ent.dxf.start.y + ent.dxf.end.y) * 0.5)
        elif dt == "CIRCLE" or dt == "ARC":
            pos_pt = (float(ent.dxf.center.x), float(ent.dxf.center.y))
        if pos_pt and _in_calc_box(pos_pt[0], pos_pt[1]) and not _is_obvious_arch_layer_name(lay):
            return "CALC"
        if _is_obvious_arch_layer_name(lay) or lay in geo_arch_layers:
            return "ARCH"
        return "ARCH" if dt == "HATCH" else "ELEC"

    stats: Dict[str, Any] = {
        "arch_entities": 0,
        "elec_entities": 0,
        "calc_entities": 0,
        "wire_heals": 0,
        "arch_layers_after": [],
        "elec_layers_after": [],
    }

    # --- ÇIKTI 1: SAF MİMARİ (Tek layer: MIMARI) ---
    doc_arch = None
    if out_arch_dxf is not None or out_merged_dxf is not None:
        doc_arch = ezdxf.readfile(str(src_dxf))
        msp_a = doc_arch.modelspace()
        for ent in list(msp_a):
            cls_b = _classify_top_entity(ent)
            if cls_b in ("ELEC", "CALC"):
                msp_a.delete_entity(ent)
        # Karma konteyner blokların içinden saf elektrik alt varlıklarını buda
        for blk in doc_arch.blocks:
            bn = blk.name
            if bn.startswith("*") or CADSafetyGuard.is_xref_block_record(blk, bn):
                continue
            for sub in list(blk):
                if sub.dxftype() in ("BLOCK", "ENDBLK"):
                    continue
                if _is_obvious_elec_layer_name(str(getattr(sub.dxf, "layer", "0") or "0")):
                    try:
                        blk.delete_entity(sub)
                    except Exception:
                        pass
        arch_rep = consolidate_architecture_to_single_layer(
            doc_arch, target_layer=arch_layer, color=8, lineweight=9, purge_unused_layers=True
        )
        stats["arch_entities"] = len(msp_a)
        stats["arch_layers_after"] = sorted(
            lay.dxf.name for lay in doc_arch.layers if lay.dxf.name.lower() not in ("0", "defpoints")
        )
        stats["arch_msp_layers"] = sorted({str(getattr(e.dxf, "layer", "0")) for e in msp_a})
        if out_arch_dxf is not None:
            Path(out_arch_dxf).parent.mkdir(parents=True, exist_ok=True)
            doc_arch.saveas(str(out_arch_dxf))

    # --- ÇIKTI 2: SAF ELEKTRİK + HESAPLAR (Maksimum 2 Layer: ELEKTRIK + HESAPLAR_TABLOLAR) ---
    doc_elec = None
    if out_elec_dxf is not None or out_merged_dxf is not None:
        doc_elec = ezdxf.readfile(str(src_dxf))
        _ensure_layer(doc_elec, elec_layer, color=7, lineweight=25, locked=False)
        _ensure_layer(doc_elec, calc_layer, color=4, lineweight=18, locked=False)
        msp_e = doc_elec.modelspace()
        calc_count = 0
        elec_count = 0
        kept_blocks: Set[str] = set()

        for ent in list(msp_e):
            cls_b = _classify_top_entity(ent)
            if cls_b == "ARCH":
                msp_e.delete_entity(ent)
                continue
            target = calc_layer if cls_b == "CALC" else elec_layer
            _set_entity_layer_bylayer(ent, target)
            if target == calc_layer:
                calc_count += 1
            else:
                elec_count += 1
            if ent.dxftype() == "INSERT":
                bn = getattr(ent.dxf, "name", "")
                if bn:
                    kept_blocks.add(bn)

        # Kalan blokların içindeki alt varlıkları temizle (mimari alt çizgileri sil, elektriği tek katmana al)
        used_blocks_e = _collect_used_blocks_recursive(doc_elec, kept_blocks)
        for bn in used_blocks_e:
            blk = doc_elec.blocks.get(bn)
            if blk is None or CADSafetyGuard.is_xref_block_record(blk, bn):
                continue
            bu_blk = norm_tr(bn).upper()
            for sub in list(blk):
                if sub.dxftype() in ("BLOCK", "ENDBLK"):
                    continue
                slay = str(getattr(sub.dxf, "layer", "0") or "0")
                if sub.dxftype() == "INSERT":
                    sub_bn = str(getattr(sub.dxf, "name", "") or "")
                    sub_bu = norm_tr(sub_bn).upper()
                    if any(ak in sub_bu for ak in ("-ARC-", "-STR-", "-MEC-")) or _is_obvious_arch_layer_name(slay):
                        try:
                            blk.delete_entity(sub)
                        except Exception:
                            pass
                        continue
                    _set_entity_layer_bylayer(sub, elec_layer)
                elif _is_obvious_arch_layer_name(slay) and not _is_obvious_elec_layer_name(slay):
                    try:
                        blk.delete_entity(sub)
                    except Exception:
                        pass
                elif sub.dxftype() in ("TEXT", "MTEXT") and slay == "0" and not _RE_ELEC_TEXT.search(
                    sub.dxf.text if sub.dxftype() == "TEXT" else sub.plain_text()
                ):
                    if "-ELC-" not in bu_blk:
                        try:
                            blk.delete_entity(sub)
                        except Exception:
                            pass
                    else:
                        _set_entity_layer_bylayer(sub, elec_layer)
                else:
                    _set_entity_layer_bylayer(sub, elec_layer)

        if heal_wires:
            placed_syms, text_tokens = _build_wire_healer_inputs_from_doc(doc_elec, snapshot, model)
            plan_wh = TopologicalWireHealer.analyze_and_propose(
                doc_elec, symbols=placed_syms, texts=text_tokens, drawing_name=Path(src_dxf).name
            )
            auto_ids = {p.proposal_id for p in plan_wh.proposals if p.auto_approvable}
            applied_wh = TopologicalWireHealer.apply_plan(doc_elec, plan_wh, approved_proposal_ids=auto_ids)
            stats["wire_heals"] = len(applied_wh)

        keep_e_layers = {elec_layer}
        if calc_count > 0:
            keep_e_layers.add(calc_layer)
        else:
            try:
                doc_elec.layers.remove(calc_layer)
            except Exception:
                pass
        _purge_unused_layers(doc_elec, keep_e_layers)
        stats["elec_entities"] = elec_count
        stats["calc_entities"] = calc_count
        stats["elec_layers_after"] = sorted(
            lay.dxf.name for lay in doc_elec.layers if lay.dxf.name.lower() not in ("0", "defpoints")
        )
        stats["elec_msp_layers"] = sorted({str(getattr(e.dxf, "layer", "0")) for e in msp_e})
        if out_elec_dxf is not None:
            Path(out_elec_dxf).parent.mkdir(parents=True, exist_ok=True)
            doc_elec.saveas(str(out_elec_dxf))

    if out_merged_dxf is not None and doc_arch is not None and doc_elec is not None:
        merge_arch_and_elec_dxf(doc_arch, doc_elec, Path(out_merged_dxf))

    return stats
