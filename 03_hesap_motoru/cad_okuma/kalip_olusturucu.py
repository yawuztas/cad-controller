# -*- coding: utf-8 -*-
"""
Aşama 1 Ana Orkestratör — Evrensel Kalıp Oluşturucu (`kalip_olusturucu.py`)
=============================================================================
Bir `.dwg` veya `.dxf` dosyasını açar, kayıpsız ham çıkarımdan geçirir,
birim kalibrasyonu + pafta ayrımı + tablo/formül + topoloji/topraklama
katmanlarını birleştirerek doğrulanabilir tek bir `CanonicalProjectModel`
kalıbına döker.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from shapely.geometry import Point, box

from .birim_kalibrator import calibrate_unit
from .ham_cikarici import extract_raw_snapshot
from .pafta_ayirici import extract_frames_and_assign, extract_legend_entries, find_legend_table_regions
from .schema import (
    CanonicalProjectModel,
    EmbeddedAlert,
    RawCADSnapshot,
    SheetFrame,
)
from .tablo_ve_formul import extract_all_tables, extract_formula_blocks
from .topoloji_ve_topraklama import extract_grounding_loops, extract_schematic_graphs


def _collect_embedded_alerts(
    snapshot: RawCADSnapshot,
    sheets: List[SheetFrame],
) -> List[EmbeddedAlert]:
    """OLE2FRAME, XREF ve okunamayan diğer gömülü nesneleri paftalara bağlayarak uyarır."""
    alerts: List[EmbeddedAlert] = []
    sheet_polys = [
        (sh.frame_id, sh.space, box(sh.bbox_du.minx, sh.bbox_du.miny, sh.bbox_du.maxx, sh.bbox_du.maxy))
        for sh in sheets
    ]

    def _sheet_for_bbox(space: str, cx: float, cy: float) -> str:
        pt = Point(cx, cy)
        hits = [
            (fid, poly.area)
            for fid, sp, poly in sheet_polys
            if sp == space and poly.covers(pt)
        ]
        if not hits:
            return "OUTSIDE"
        return min(hits, key=lambda x: x[1])[0]

    for ole in snapshot.ole_objects:
        if ole.decode_status == "OK":
            continue
        cx, cy = ole.bbox.center
        sid = _sheet_for_bbox(ole.space, cx, cy)
        alerts.append(EmbeddedAlert(
            alert_type="OLE2FRAME_EMBEDDED",
            sheet_id=sid,
            space=ole.space,
            layer=ole.layer,
            handle=ole.handle,
            bbox_du=ole.bbox,
            message=ole.note,
        ))

    xref_blocks = sorted({ins.effective_name or ins.block_name for ins in snapshot.inserts if ins.is_xref})
    for xb in xref_blocks:
        first = next(ins for ins in snapshot.inserts if (ins.effective_name or ins.block_name) == xb and ins.is_xref)
        alerts.append(EmbeddedAlert(
            alert_type="EXTERNAL_XREF",
            sheet_id=_sheet_for_bbox(first.space, first.x, first.y),
            space=first.space,
            layer=first.layer,
            handle=first.handle,
            bbox_du=first.bbox,
            message=f"Harici XREF referansı ('{xb}') dış dosyaya bağlıdır; içindeki geometriler ayrı kontrol edilmelidir.",
        ))

    return alerts


def build_canonical_model(
    drawing_path: Union[str, Path],
    use_cache: bool = True,
) -> Tuple[RawCADSnapshot, CanonicalProjectModel]:
    """
    Adım 1'in tek kapısı: DWG/DXF'ten kayıpsız ham görüntü ve evrensel
    `CanonicalProjectModel` kalıbını üretir.
    """
    snapshot = extract_raw_snapshot(drawing_path, use_cache=use_cache)
    unit = calibrate_unit(snapshot)
    sheets, texts_by_frame, inserts_by_frame, paths_by_frame = extract_frames_and_assign(snapshot, unit)
    legend = extract_legend_entries(sheets, texts_by_frame, inserts_by_frame)
    legend_regions = find_legend_table_regions(sheets, texts_by_frame, inserts_by_frame)
    tables = extract_all_tables(snapshot.acad_tables, sheets, texts_by_frame, ole_objects=snapshot.ole_objects)
    formulas = extract_formula_blocks(sheets, texts_by_frame, paths_by_frame)
    schematics = extract_schematic_graphs(sheets, paths_by_frame, texts_by_frame, inserts_by_frame, unit)
    grounding = extract_grounding_loops(
        sheets,
        paths_by_frame,
        texts_by_frame,
        unit,
        inserts_by_frame=inserts_by_frame,
        legend=legend,
        legend_regions=legend_regions,
    )
    alerts = _collect_embedded_alerts(snapshot, sheets)

    model = CanonicalProjectModel(
        filename=snapshot.filename,
        filepath=snapshot.filepath,
        unit=unit,
        sheets=sheets,
        legend=legend,
        tables=tables,
        formula_blocks=formulas,
        schematics=schematics,
        grounding_loops=grounding,
        embedded_alerts=alerts,
        extraction_metrics={
            "raw_entity_counts": snapshot.raw_entity_counts,
            "unhandled_entity_counts": snapshot.unhandled_entity_counts,
            "extracted_texts": len(snapshot.texts),
            "extracted_inserts": len(snapshot.inserts),
            "extracted_paths": len(snapshot.paths),
            "extracted_acad_tables": len(snapshot.acad_tables),
            "extracted_dimensions": len(snapshot.dimensions),
            "extracted_leaders": len(snapshot.leaders),
            "extracted_ole_objects": len(snapshot.ole_objects),
            "sheet_count": len(sheets),
            "legend_entries": len(legend),
            "normalized_tables": len(tables),
            "formula_blocks": len(formulas),
            "formula_blocks_ok": sum(1 for f in formulas if f.parse_status == "OK"),
            "schematic_graphs": len(schematics),
            "grounding_loops": len(grounding),
            "embedded_alerts": len(alerts),
            "warnings": snapshot.extraction_warnings,
        },
    )
    return snapshot, model


def save_canonical_json(
    model: CanonicalProjectModel,
    output_path: Union[str, Path],
) -> Path:
    """Evrensel kalıbı incelenebilir JSON dosyasına yazar."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    return out
