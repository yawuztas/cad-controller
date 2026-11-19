# -*- coding: utf-8 -*-
"""
Aşama 1A — Kayıpsız Ham CAD Çıkarıcı (`ham_cikarici.py`)
==========================================================
Bir .dwg veya .dxf dosyasını TEK SEFERDE ve SIFIR katman/blok filtresiyle okur.
ModelSpace ve tüm dolu PaperSpace paftalarını; dinamik blok kök adlarını (*U),
ACAD_TABLE, LEADER/MLEADER, DIMENSION, CIRCLE/ARC/ELLIPSE/SPLINE/HATCH ve
OLE2FRAME/IMAGE envanterini Dünya Koordinat Sisteminde (WCS) `RawCADSnapshot`
modeline döker.
"""

from __future__ import annotations
from collections import Counter
import io
import logging
import math
from pathlib import Path
import struct
import sys
import zipfile
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import ezdxf
from ezdxf import path as ezpath
from ezdxf.entities.acad_table import read_acad_table_content
from ezdxf.math import Matrix44, Vec3

from .metin_temizleyici import clean_cad_text_lines, clean_turkish_text
from .schema import (
    BBox2D,
    LayerInfo,
    RawAcadTable,
    RawCADSnapshot,
    RawDimension,
    RawInsert,
    RawLeader,
    RawOleObject,
    RawPath,
    RawText,
)

# common.dxf_converter modülünün güvenli import'u
_MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(_MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_MOTOR_ROOT))

from common.dxf_converter import ensure_dxf, is_valid_dxf

logger = logging.getLogger("CloudeCAD.HamCikarici")


def _bbox_from_points(pts: Iterable[Tuple[float, float]]) -> BBox2D:
    xs: List[float] = []
    ys: List[float] = []
    for x, y in pts:
        xs.append(float(x))
        ys.append(float(y))
    if not xs:
        return BBox2D(minx=0.0, miny=0.0, maxx=0.0, maxy=0.0)
    return BBox2D(minx=min(xs), miny=min(ys), maxx=max(xs), maxy=max(ys))


def _text_bbox(x: float, y: float, text: str, height: float, rot_deg: float) -> BBox2D:
    h = max(abs(float(height or 0.0)), 1e-4)
    w = max(len(text) * h * 0.68, h * 0.8)
    rad = math.radians(rot_deg)
    c, s = math.cos(rad), math.sin(rad)
    corners = [
        (x, y),
        (x + w * c, y + w * s),
        (x + w * c - h * s, y + w * s + h * c),
        (x - h * s, y + h * c),
    ]
    return _bbox_from_points(corners)


def _matrix_xy_scale(mat: Matrix44) -> float:
    vx = mat.transform_direction(Vec3(1.0, 0.0, 0.0))
    vy = mat.transform_direction(Vec3(0.0, 1.0, 0.0))
    return max(1e-6, (vx.magnitude + vy.magnitude) * 0.5)


def _matrix_rot_deg(mat: Matrix44, local_rot_deg: float = 0.0) -> float:
    ang = math.radians(local_rot_deg)
    d = mat.transform_direction(Vec3(math.cos(ang), math.sin(ang), 0.0))
    return math.degrees(math.atan2(d.y, d.x))


def resolve_dynamic_block_name(doc: ezdxf.document.Drawing, block_name: str) -> Tuple[str, bool]:
    """
    AutoCAD dinamik blokları (*U12, *U145 vb.) için AcDbBlockRepBTag XData'sı
    üzerinden gerçek kök blok adını çözer.
    """
    clean_raw = clean_turkish_text(block_name)
    if not block_name.startswith("*"):
        return clean_raw, False

    blk = doc.blocks.get(block_name)
    if blk is None:
        return clean_raw, block_name.upper().startswith("*U")

    try:
        blk_rec = getattr(blk, "block_record", None)
        if blk_rec is not None and blk_rec.has_xdata("AcDbBlockRepBTag"):
            xdata = blk_rec.get_xdata("AcDbBlockRepBTag")
            for code, value in xdata:
                if code == 1005 and value in doc.entitydb:
                    root_ent = doc.entitydb[value]
                    root_name = getattr(root_ent.dxf, "name", "")
                    if root_name:
                        return clean_turkish_text(root_name), True
    except Exception as exc:
        logger.debug(f"Dinamik blok adı çözülemedi ({block_name}): {exc}")

    return clean_raw, block_name.upper().startswith("*U")


def _group_emf_cells_to_rows(cells: List[Tuple[int, int, str]]) -> List[List[str]]:
    """Koordinatlı EMF metin kayıtlarını (y, x, metin) adaptif satır toleransı ile tabloya çevirir."""
    if not cells:
        return []
    ys = sorted({c[0] for c in cells})
    y_span = (ys[-1] - ys[0]) if len(ys) > 1 else 0
    row_tol = max(3.0, 0.012 * y_span)

    cells_sorted = sorted(cells, key=lambda c: (c[0], c[1]))
    grouped_rows: List[List[Tuple[int, str]]] = []
    cur_y = cells_sorted[0][0]
    cur_row: List[Tuple[int, str]] = []

    for py, px, txt in cells_sorted:
        if abs(py - cur_y) <= row_tol:
            cur_row.append((px, txt))
        else:
            if cur_row:
                grouped_rows.append(sorted(cur_row, key=lambda it: it[0]))
            cur_y = py
            cur_row = [(px, txt)]
    if cur_row:
        grouped_rows.append(sorted(cur_row, key=lambda it: it[0]))

    rows_out: List[List[str]] = []
    for r in grouped_rows:
        vals = [t for _, t in r if t]
        if vals:
            rows_out.append(vals)
    return rows_out


def _decode_ole2_payload(ent: Any) -> Tuple[str, str, List[List[str]], int]:
    """
    OLE2FRAME ikili akışından gömülü Excel (.xls/.xlsx) veya EMF (`CONTENTS`)
    tablosunu harici araç olmadan çözer.
    Dönüş: (decode_status, decoded_title, decoded_rows, cell_count)
    """
    raw_fn = getattr(ent, "binary_data", None)
    if not callable(raw_fn):
        return "UNREADABLE", "", [], 0
    raw: bytes = raw_fn()
    if not raw:
        return "UNREADABLE", "", [], 0

    cf_idx = raw.find(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if cf_idx < 0:
        pk_idx = raw.find(b"PK\x03\x04")
        if pk_idx >= 0:
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(raw[pk_idx:]), data_only=True, read_only=True)
                sh = wb.active
                rows = [
                    [str(c).strip() for c in row if c is not None and str(c).strip()]
                    for row in sh.iter_rows(values_only=True)
                ]
                rows = [r for r in rows if r]
                if rows:
                    return "OK", " ".join(rows[0])[:120], rows, sum(len(r) for r in rows)
            except Exception:
                pass
        return "UNREADABLE", "", [], 0

    cf = raw[cf_idx:]

    # Yol 1: Doğrudan .xls Workbook (xlrd)
    try:
        import xlrd
        wb = xlrd.open_workbook(file_contents=cf)
        sh = wb.sheet_by_index(0)
        xls_rows: List[List[str]] = []
        for r in range(sh.nrows):
            vals = [str(v).strip() for v in sh.row_values(r) if str(v).strip()]
            if vals:
                xls_rows.append(vals)
        if xls_rows:
            return "OK", " ".join(xls_rows[0])[:120], xls_rows, sum(len(r) for r in xls_rows)
    except Exception:
        pass

    # Yol 2: CFBF içi `Package` (.xlsx) veya `CONTENTS` (EMF metafile)
    try:
        from xlrd import compdoc
        cd = compdoc.CompDoc(cf)

        pkg = cd.get_named_stream("Package")
        if pkg:
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(pkg), data_only=True, read_only=True)
                sh = wb.active
                pkg_rows = [
                    [str(c).strip() for c in row if c is not None and str(c).strip()]
                    for row in sh.iter_rows(values_only=True)
                ]
                pkg_rows = [r for r in pkg_rows if r]
                if pkg_rows:
                    return "OK", " ".join(pkg_rows[0])[:120], pkg_rows, sum(len(r) for r in pkg_rows)
            except Exception:
                pass

        contents = cd.get_named_stream("CONTENTS")
        if contents:
            emf_sig = contents.find(b" EMF")
            if emf_sig >= 40:
                pos = emf_sig - 40
                cells: List[Tuple[int, int, str]] = []
                while pos + 8 <= len(contents):
                    rt, rs = struct.unpack_from("<II", contents, pos)
                    if rs < 8 or pos + rs > len(contents):
                        break
                    if rt == 84 and rs >= 76:  # EMR_EXTTEXTOUTW
                        px, py, n_chars, off_str = struct.unpack_from("<iiII", contents, pos + 36)
                        if n_chars > 0 and off_str >= 76 and off_str + n_chars * 2 <= rs:
                            txt = contents[pos + off_str : pos + off_str + n_chars * 2].decode("utf-16le", "ignore").strip()
                            if txt:
                                cells.append((py, px, txt))
                    elif rt == 83 and rs >= 76:  # EMR_EXTTEXTOUTA
                        px, py, n_chars, off_str = struct.unpack_from("<iiII", contents, pos + 36)
                        if n_chars > 0 and off_str >= 76 and off_str + n_chars <= rs:
                            txt = contents[pos + off_str : pos + off_str + n_chars].decode("cp1254", "ignore").strip()
                            if txt:
                                cells.append((py, px, txt))
                    pos += rs

                if cells:
                    emf_rows = _group_emf_cells_to_rows(cells)
                    title = " ".join(emf_rows[0])[:120] if emf_rows else ""
                    return "OK", title, emf_rows, len(cells)
    except Exception:
        pass

    return "UNREADABLE", "", [], 0


def _extract_layers(doc: ezdxf.document.Drawing) -> List[LayerInfo]:
    out: List[LayerInfo] = []
    for lay in doc.layers:
        out.append(LayerInfo(
            name=clean_turkish_text(lay.dxf.name) or lay.dxf.name,
            color=int(getattr(lay.dxf, "color", 7)),
            linetype=str(getattr(lay.dxf, "linetype", "CONTINUOUS")),
            lineweight=int(getattr(lay.dxf, "lineweight", -3)),
            is_locked=bool(lay.is_locked()),
            is_on=bool(lay.is_on()),
            is_frozen=bool(lay.is_frozen()),
            plot=bool(getattr(lay.dxf, "plot", 1)),
        ))
    return out


def _extract_text_like(
    ent: Any,
    mat: Matrix44,
    space: str,
    owner_block: str,
    parent_chain: str,
) -> Optional[RawText]:
    dxftype = ent.dxftype()
    if dxftype == "TEXT":
        raw_str = getattr(ent.dxf, "text", "") or ""
    elif dxftype == "MTEXT":
        raw_str = getattr(ent, "text", "") or ""
    elif dxftype == "ATTRIB":
        raw_str = getattr(ent.dxf, "text", "") or ""
    else:
        return None

    single, lines = clean_cad_text_lines(raw_str)
    if not single:
        return None

    ins = getattr(ent.dxf, "insert", Vec3(0.0, 0.0, 0.0))
    from_align = False
    if dxftype in ("TEXT", "ATTRIB"):
        halign = int(getattr(ent.dxf, "halign", 0) or 0)
        valign = int(getattr(ent.dxf, "valign", 0) or 0)
        al = getattr(ent.dxf, "align_point", None)
        if (halign != 0 or valign != 0) and al is not None:
            # AutoCAD'de hizalı TEXT/ATTRIB nesnelerinde gerçek nokta align_point'tir
            # (FIT / ALIGNED hariç tüm tiplerde insert çoğu zaman 0,0 kalır).
            if not (halign in (3, 5) and (abs(ins.x) > 1e-6 or abs(ins.y) > 1e-6)):
                ins = al
                from_align = True

    w_pos = mat.transform(Vec3(float(ins.x), float(ins.y), float(getattr(ins, "z", 0.0))))
    local_h = float(getattr(ent.dxf, "height", getattr(ent.dxf, "char_height", 2.5)) or 2.5)
    world_h = local_h * _matrix_xy_scale(mat)
    world_rot = _matrix_rot_deg(mat, float(getattr(ent.dxf, "rotation", 0.0) or 0.0))

    return RawText(
        handle=str(getattr(ent.dxf, "handle", "") or ""),
        dxftype=dxftype,
        text=single,
        lines=lines,
        raw_text=raw_str,
        x=round(w_pos.x, 4),
        y=round(w_pos.y, 4),
        z=round(w_pos.z, 4),
        height=round(world_h, 4),
        rotation=round(world_rot, 3),
        layer=str(getattr(ent.dxf, "layer", "0") or "0"),
        color=int(getattr(ent.dxf, "color", 256) or 256),
        space=space,
        owner_block=owner_block,
        parent_chain=parent_chain,
        is_attribute=(dxftype == "ATTRIB"),
        attrib_tag=str(getattr(ent.dxf, "tag", "") or "").upper().strip() if dxftype == "ATTRIB" else "",
        from_align_point=from_align,
        bbox=_text_bbox(w_pos.x, w_pos.y, single, world_h, world_rot),
    )


def _polyline_len(pts: List[Tuple[float, float]], closed: bool) -> float:
    if len(pts) < 2:
        return 0.0
    total = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))
    if closed and pts[0] != pts[-1]:
        total += math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
    return total


def _adaptive_flatten(p: ezpath.Path) -> List[Tuple[float, float]]:
    """Birimden bağımsız (ölçek invariant) eğri örnekleme toleransı ile path düzleştirir."""
    bb = ezpath.bbox([p], fast=True)
    diag = math.hypot(bb.size.x, bb.size.y) if bb.has_data else 1.0
    tol = max(diag * 0.008, 1e-6)
    pts = [(float(v.x), float(v.y)) for v in p.flattening(distance=tol)]
    return pts


def _extract_path_entities(
    ent: Any,
    mat: Matrix44,
    space: str,
    owner_block: str,
    parent_chain: str,
    warnings: List[str],
) -> List[RawPath]:
    dxftype = ent.dxftype()
    handle = str(getattr(ent.dxf, "handle", "") or "")
    layer = str(getattr(ent.dxf, "layer", "0") or "0")
    color = int(getattr(ent.dxf, "color", 256) or 256)
    linetype = str(getattr(ent.dxf, "linetype", "BYLAYER") or "BYLAYER")
    scale = _matrix_xy_scale(mat)

    def _make_raw(
        pts_w: List[Tuple[float, float]],
        kind: str,
        closed: bool = False,
        is_circle: bool = False,
        radius_du: Optional[float] = None,
        sweep_deg: Optional[float] = None,
    ) -> Optional[RawPath]:
        min_pts = 1 if kind == "POINT" else 2
        if len(pts_w) < min_pts:
            return None
        rounded = [(round(x, 4), round(y, 4)) for x, y in pts_w]
        length = (
            2.0 * math.pi * radius_du
            if is_circle and radius_du is not None
            else (
                math.radians(abs(sweep_deg)) * radius_du
                if kind == "ARC" and radius_du is not None and sweep_deg is not None
                else _polyline_len(rounded, closed)
            )
        )
        return RawPath(
            handle=handle,
            dxftype=kind,
            points=rounded,
            closed=closed,
            is_circle=is_circle,
            radius_du=round(radius_du, 4) if radius_du is not None else None,
            arc_sweep_deg=round(sweep_deg, 3) if sweep_deg is not None else None,
            length_du=round(length, 4),
            layer=layer,
            color=color,
            linetype=linetype,
            space=space,
            owner_block=owner_block,
            parent_chain=parent_chain,
            bbox=_bbox_from_points(rounded),
        )

    try:
        if dxftype == "LINE":
            p1 = mat.transform(ent.dxf.start)
            p2 = mat.transform(ent.dxf.end)
            rp = _make_raw([(p1.x, p1.y), (p2.x, p2.y)], "LINE", closed=False)
            return [rp] if rp else []

        if dxftype == "LWPOLYLINE":
            closed = bool(getattr(ent, "closed", False) or getattr(ent, "is_closed", False))
            raw_pts = list(ent.get_points("xyb"))
            has_bulge = any(abs(p[2]) > 1e-6 for p in raw_pts)
            if has_bulge:
                p_obj = ezpath.make_path(ent).transform(mat)
                pts_w = _adaptive_flatten(p_obj)
            else:
                pts_w = [(v.x, v.y) for v in (mat.transform(Vec3(p[0], p[1], 0.0)) for p in raw_pts)]
                if closed and len(pts_w) >= 3 and pts_w[0] != pts_w[-1]:
                    pts_w.append(pts_w[0])
            rp = _make_raw(pts_w, "LWPOLYLINE", closed=closed)
            return [rp] if rp else []

        if dxftype == "POLYLINE":
            if ent.is_3d_polyline or ent.is_2d_polyline:
                closed = bool(getattr(ent, "is_closed", False))
                p_obj = ezpath.make_path(ent).transform(mat)
                pts_w = _adaptive_flatten(p_obj)
                rp = _make_raw(pts_w, "POLYLINE", closed=closed)
                return [rp] if rp else []
            return []

        if dxftype == "ARC":
            r_w = float(ent.dxf.radius) * scale
            sa = float(ent.dxf.start_angle)
            ea = float(ent.dxf.end_angle)
            sweep = (ea - sa) % 360.0
            if sweep == 0.0:
                sweep = 360.0
            p_obj = ezpath.make_path(ent).transform(mat)
            pts_w = _adaptive_flatten(p_obj)
            rp = _make_raw(pts_w, "ARC", closed=False, radius_du=r_w, sweep_deg=sweep)
            return [rp] if rp else []

        if dxftype == "CIRCLE":
            r_w = float(ent.dxf.radius) * scale
            p_obj = ezpath.make_path(ent).transform(mat)
            pts_w = _adaptive_flatten(p_obj)
            rp = _make_raw(pts_w, "CIRCLE", closed=True, is_circle=True, radius_du=r_w, sweep_deg=360.0)
            return [rp] if rp else []

        if dxftype in ("ELLIPSE", "SPLINE"):
            p_obj = ezpath.make_path(ent).transform(mat)
            pts_w = _adaptive_flatten(p_obj)
            closed = bool(getattr(ent, "closed", False))
            rp = _make_raw(pts_w, dxftype, closed=closed)
            return [rp] if rp else []

        if dxftype == "HATCH":
            out_paths: List[RawPath] = []
            for p_obj in ezpath.from_hatch(ent):
                pts_w = _adaptive_flatten(p_obj.transform(mat))
                rp = _make_raw(pts_w, "HATCH_BOUNDARY", closed=True)
                if rp:
                    out_paths.append(rp)
            return out_paths

        if dxftype == "POINT":
            loc = getattr(ent.dxf, "location", Vec3(0.0, 0.0, 0.0))
            p_w = mat.transform(Vec3(float(loc.x), float(loc.y), 0.0))
            rp = _make_raw([(p_w.x, p_w.y)], "POINT", closed=False)
            return [rp] if rp else []

        if dxftype in ("SOLID", "TRACE", "3DFACE"):
            pts_local = ent.wcs_vertices(close=True) if hasattr(ent, "wcs_vertices") else []
            pts_w = [(v.x, v.y) for v in (mat.transform(Vec3(p.x, p.y, 0.0)) for p in pts_local)]
            rp = _make_raw(pts_w, dxftype, closed=True)
            return [rp] if rp else []

    except Exception as exc:
        warnings.append(f"{dxftype} ({handle}): geometri çıkarılamadı ({exc})")
    return []


def extract_raw_snapshot(drawing_path: Union[str, Path], use_cache: bool = True) -> RawCADSnapshot:
    """
    Bir .dwg veya .dxf dosyasını kayıpsız okuyarak `RawCADSnapshot` döner.
    HİÇBİR katman/blok/renk elemesi yapılmaz; her şey WCS koordinatına alınır.
    """
    src_path = Path(drawing_path).resolve()
    dxf_path = ensure_dxf(src_path, use_cache=use_cache)
    if not is_valid_dxf(dxf_path):
        raise RuntimeError(f"DXF dosyası geçersiz veya yarım kalmış: {dxf_path}")

    doc = ezdxf.readfile(dxf_path)
    layers = _extract_layers(doc)

    texts: List[RawText] = []
    inserts: List[RawInsert] = []
    paths: List[RawPath] = []
    acad_tables: List[RawAcadTable] = []
    dimensions: List[RawDimension] = []
    leaders: List[RawLeader] = []
    ole_objects: List[RawOleObject] = []
    raw_counts: Counter = Counter()
    unhandled_counts: Counter = Counter()
    warnings: List[str] = []

    dyn_cache: Dict[str, Tuple[str, bool]] = {}

    def _get_dyn(bname: str) -> Tuple[str, bool]:
        if bname not in dyn_cache:
            dyn_cache[bname] = resolve_dynamic_block_name(doc, bname)
        return dyn_cache[bname]

    def _traverse(
        entities: Any,
        cur_mat: Matrix44,
        space: str,
        owner_block: str,
        parent_chain: str,
        depth: int,
        seen_blocks: Tuple[str, ...],
    ) -> None:
        if depth > 12:
            warnings.append(f"Maksimum blok derinliği (12) aşıldı: {parent_chain}")
            return

        for ent in entities:
            dxftype = ent.dxftype()
            raw_counts[dxftype] += 1
            handle = str(getattr(ent.dxf, "handle", "") or "")
            layer = str(getattr(ent.dxf, "layer", "0") or "0")

            if dxftype in ("TEXT", "MTEXT"):
                rt = _extract_text_like(ent, cur_mat, space, owner_block, parent_chain)
                if rt:
                    texts.append(rt)

            elif dxftype == "INSERT":
                bname = str(getattr(ent.dxf, "name", "") or "")
                eff_name, is_dyn = _get_dyn(bname)
                blk_def = doc.blocks.get(bname)
                blk_rec = getattr(blk_def, "block_record", None) if blk_def else None
                blk_hdr = getattr(blk_def, "block", None) if blk_def else None
                is_xref = bool(
                    (blk_hdr and (getattr(blk_hdr, "is_xref", False) or getattr(blk_hdr, "is_xref_overlay", False)))
                    or (blk_rec and getattr(blk_rec, "is_xref", False))
                )

                ins = ent.dxf.insert
                sx = float(getattr(ent.dxf, "xscale", 1.0) or 1.0)
                sy = float(getattr(ent.dxf, "yscale", 1.0) or 1.0)
                sz = float(getattr(ent.dxf, "zscale", 1.0) or 1.0)
                rot = float(getattr(ent.dxf, "rotation", 0.0) or 0.0)

                ent_mat = Matrix44.chain(
                    Matrix44.scale(sx, sy, sz),
                    Matrix44.z_rotate(math.radians(rot)),
                    Matrix44.translate(float(ins.x), float(ins.y), float(getattr(ins, "z", 0.0))),
                )
                combined_mat = ent_mat * cur_mat
                w_pos = combined_mat.transform(Vec3(0.0, 0.0, 0.0))

                attribs_map: Dict[str, str] = {}
                if hasattr(ent, "attribs"):
                    for att in ent.attribs:
                        rt_att = _extract_text_like(att, cur_mat, space, owner_block, f"{parent_chain} > {eff_name}".strip(" >"))
                        if rt_att:
                            texts.append(rt_att)
                            if rt_att.attrib_tag:
                                attribs_map[rt_att.attrib_tag] = rt_att.text

                # Insert bbox'ı alt blok taranınca gerçek WCS geometrisinden hesaplanır
                est_r = max(abs(sx), abs(sy), 1.0)
                ins_bbox = BBox2D(
                    minx=round(w_pos.x - est_r, 4),
                    miny=round(w_pos.y - est_r, 4),
                    maxx=round(w_pos.x + est_r, 4),
                    maxy=round(w_pos.y + est_r, 4),
                )

                raw_ins = RawInsert(
                    handle=handle,
                    block_name=clean_turkish_text(bname) or bname,
                    effective_name=eff_name or bname,
                    is_dynamic=is_dyn,
                    is_xref=is_xref,
                    x=round(w_pos.x, 4),
                    y=round(w_pos.y, 4),
                    z=round(w_pos.z, 4),
                    xscale=round(sx, 4),
                    yscale=round(sy, 4),
                    rotation=round(_matrix_rot_deg(combined_mat, 0.0), 3),
                    layer=layer,
                    color=int(getattr(ent.dxf, "color", 256) or 256),
                    space=space,
                    owner_block=owner_block,
                    parent_chain=parent_chain,
                    attribs=attribs_map,
                    bbox=ins_bbox,
                )
                inserts.append(raw_ins)

                p_start = len(paths)
                t_start = len(texts)
                if blk_def is not None and not is_xref and bname not in seen_blocks:
                    next_chain = f"{parent_chain} > {eff_name}" if parent_chain else eff_name
                    _traverse(
                        blk_def,
                        combined_mat,
                        space=space,
                        owner_block=eff_name or bname,
                        parent_chain=next_chain,
                        depth=depth + 1,
                        seen_blocks=seen_blocks + (bname,),
                    )

                child_paths = paths[p_start:]
                child_texts = texts[t_start:]
                raw_ins.internal_layers = sorted(
                    {
                        str(obj.layer).strip()
                        for obj in (*child_paths, *child_texts)
                        if getattr(obj, "layer", None)
                        and str(obj.layer).strip() not in ("", "0", "DEFPOINTS")
                    }
                )
                true_bb: Optional[BBox2D] = None
                if child_paths:
                    true_bb = BBox2D(
                        minx=round(min(p.bbox.minx for p in child_paths), 4),
                        miny=round(min(p.bbox.miny for p in child_paths), 4),
                        maxx=round(max(p.bbox.maxx for p in child_paths), 4),
                        maxy=round(max(p.bbox.maxy for p in child_paths), 4),
                    )
                elif child_texts:
                    true_bb = BBox2D(
                        minx=round(min(t.bbox.minx for t in child_texts), 4),
                        miny=round(min(t.bbox.miny for t in child_texts), 4),
                        maxx=round(max(t.bbox.maxx for t in child_texts), 4),
                        maxy=round(max(t.bbox.maxy for t in child_texts), 4),
                    )
                if true_bb is not None:
                    raw_ins.bbox = true_bb
                    pad_x = max(true_bb.width * 0.25, 1e-4)
                    pad_y = max(true_bb.height * 0.25, 1e-4)
                    if (
                        w_pos.x < true_bb.minx - pad_x
                        or w_pos.x > true_bb.maxx + pad_x
                        or w_pos.y < true_bb.miny - pad_y
                        or w_pos.y > true_bb.maxy + pad_y
                    ):
                        cx, cy = true_bb.center
                        raw_ins.x = round(cx, 4)
                        raw_ins.y = round(cy, 4)

            elif dxftype in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE", "HATCH", "SOLID", "TRACE", "3DFACE", "POINT"):
                extracted_p = _extract_path_entities(ent, cur_mat, space, owner_block, parent_chain, warnings)
                paths.extend(extracted_p)

            elif dxftype == "ACAD_TABLE":
                try:
                    rows = read_acad_table_content(ent)
                    cleaned_rows = [[clean_turkish_text(str(cell or "")) for cell in row] for row in rows]
                    ins_p = getattr(ent.dxf, "insert", Vec3(0.0, 0.0, 0.0))
                    w_p = cur_mat.transform(Vec3(float(ins_p.x), float(ins_p.y), 0.0))
                    acad_tables.append(RawAcadTable(
                        handle=handle,
                        layer=layer,
                        space=space,
                        x=round(w_p.x, 4),
                        y=round(w_p.y, 4),
                        rows=cleaned_rows,
                    ))
                except Exception as exc:
                    warnings.append(f"ACAD_TABLE ({handle}) okunamadı: {exc}")

            elif dxftype == "DIMENSION":
                try:
                    txt_ov = clean_turkish_text(getattr(ent.dxf, "text", "") or "")
                    meas = getattr(ent, "measurement", None)
                    if callable(meas):
                        meas = meas()
                    tp = getattr(ent.dxf, "text_midpoint", None) or getattr(ent.dxf, "defpoint", Vec3(0.0, 0.0, 0.0))
                    w_p = cur_mat.transform(Vec3(float(tp.x), float(tp.y), 0.0))
                    dimensions.append(RawDimension(
                        handle=handle,
                        dimtype=int(getattr(ent.dxf, "dimtype", 0) or 0),
                        text_override=txt_ov,
                        measurement_du=round(float(meas), 4) if isinstance(meas, (int, float)) else None,
                        x=round(w_p.x, 4),
                        y=round(w_p.y, 4),
                        layer=layer,
                        space=space,
                    ))
                except Exception as exc:
                    warnings.append(f"DIMENSION ({handle}) okunamadı: {exc}")

            elif dxftype in ("LEADER", "MLEADER"):
                try:
                    verts: List[Tuple[float, float]] = []
                    ltxt = ""
                    if dxftype == "LEADER":
                        for v in getattr(ent, "vertices", []):
                            wv = cur_mat.transform(Vec3(v))
                            verts.append((round(wv.x, 4), round(wv.y, 4)))
                    else:
                        if hasattr(ent, "has_mtext_content") and ent.has_mtext_content():
                            ltxt = clean_turkish_text(ent.get_mtext_content() or "")
                        ctx = getattr(ent, "context", None)
                        for ld in getattr(ctx, "leaders", []) if ctx else []:
                            for ll in getattr(ld, "lines", []):
                                for v in getattr(ll, "vertices", []):
                                    wv = cur_mat.transform(Vec3(float(v.x), float(v.y), 0.0))
                                    verts.append((round(wv.x, 4), round(wv.y, 4)))
                    leaders.append(RawLeader(
                        handle=handle,
                        dxftype=dxftype,
                        vertices=verts,
                        text=ltxt,
                        layer=layer,
                        space=space,
                    ))
                except Exception as exc:
                    warnings.append(f"{dxftype} ({handle}) okunamadı: {exc}")

            elif dxftype in ("OLE2FRAME", "IMAGE", "WIPEOUT"):
                try:
                    bb_raw = ent.bbox() if hasattr(ent, "bbox") else None
                    if bb_raw is not None and getattr(bb_raw, "has_data", False):
                        p1 = cur_mat.transform(Vec3(float(bb_raw.extmin[0]), float(bb_raw.extmin[1]), 0.0))
                        p2 = cur_mat.transform(Vec3(float(bb_raw.extmax[0]), float(bb_raw.extmax[1]), 0.0))
                        bb = _bbox_from_points([(p1.x, p1.y), (p2.x, p2.y)])
                    elif bb_raw is not None and hasattr(bb_raw, "__len__") and len(bb_raw) == 2:
                        p1 = cur_mat.transform(Vec3(float(bb_raw[0][0]), float(bb_raw[0][1]), 0.0))
                        p2 = cur_mat.transform(Vec3(float(bb_raw[1][0]), float(bb_raw[1][1]), 0.0))
                        bb = _bbox_from_points([(p1.x, p1.y), (p2.x, p2.y)])
                    else:
                        ins_p = getattr(ent.dxf, "insert", Vec3(0.0, 0.0, 0.0))
                        p1 = cur_mat.transform(Vec3(float(ins_p.x), float(ins_p.y), 0.0))
                        bb = BBox2D(minx=p1.x, miny=p1.y, maxx=p1.x, maxy=p1.y)

                    d_status, d_title, d_rows, d_cells = (
                        _decode_ole2_payload(ent) if dxftype == "OLE2FRAME" else ("UNREADABLE", "", [], 0)
                    )
                    note_txt = (
                        f"OLE2 tablosu çözüldü ({len(d_rows)} satır, {d_cells} hücre): {d_title}"
                        if d_status == "OK"
                        else f"Gömülü {dxftype} nesnesi (katman: {layer}) DXF metni olarak ayrıştırılamaz."
                    )
                    ole_objects.append(RawOleObject(
                        handle=handle,
                        dxftype=dxftype,
                        layer=layer,
                        space=space,
                        bbox=bb,
                        note=note_txt,
                        decode_status=d_status,  # type: ignore[arg-type]
                        decoded_title=d_title,
                        decoded_rows=d_rows,
                        decoded_text_count=d_cells,
                    ))
                except Exception as exc:
                    warnings.append(f"{dxftype} ({handle}) okunamadı: {exc}")

            elif dxftype not in ("ATTDEF", "SEQEND", "VERTEX", "VIEWPORT"):
                unhandled_counts[dxftype] += 1

    layout_names: List[str] = []
    for lay in doc.layouts:
        layout_names.append(lay.name)
        space_tag = "MODEL" if lay.name == "Model" else f"PAPERSPACE:{lay.name}"
        if len(lay) > 0:
            _traverse(
                lay,
                Matrix44(),
                space=space_tag,
                owner_block=lay.name.upper(),
                parent_chain="",
                depth=0,
                seen_blocks=(),
            )

    extmin_hdr = doc.header.get("$EXTMIN")
    extmax_hdr = doc.header.get("$EXTMAX")

    return RawCADSnapshot(
        filepath=str(src_path),
        filename=src_path.name,
        dxf_path=str(dxf_path),
        dxf_version=str(getattr(doc, "dxfversion", "")),
        insunits_header=int(doc.header.get("$INSUNITS", 0) or 0),
        extmin=(float(extmin_hdr[0]), float(extmin_hdr[1])) if extmin_hdr else None,
        extmax=(float(extmax_hdr[0]), float(extmax_hdr[1])) if extmax_hdr else None,
        layouts=layout_names,
        layers=layers,
        texts=texts,
        inserts=inserts,
        paths=paths,
        acad_tables=acad_tables,
        dimensions=dimensions,
        leaders=leaders,
        ole_objects=ole_objects,
        raw_entity_counts=dict(raw_counts),
        unhandled_entity_counts=dict(unhandled_counts),
        extraction_warnings=warnings,
    )
