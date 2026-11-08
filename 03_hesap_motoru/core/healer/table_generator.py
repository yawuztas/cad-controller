from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from ezdxf.document import Drawing
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..cad.cad_safety import CADSafetyGuard, LayerStandardSpec, UnitScaleResolver


@dataclass
class ScheduleRowInput:
    """
    Yükleme cetveli (Panel Load Schedule) tekil linye / çıkış satırı.
    """
    circuit_id: str
    description: str
    load_watts: float
    phase: str  # "L1", "L2", "L3" veya "L1-L2-L3" (3 Faz)
    cable_spec: str
    breaker_spec: str
    rcd_spec: str = "-"
    length_m: float = 0.0
    voltage_drop_pct: float = 0.0
    # Mevcut DWG tablosundaki hücre metin handle'ları (varsa yerinde güncelleme için)
    cell_handles: Dict[str, str] = field(default_factory=dict)


@dataclass
class GeneratedTableReport:
    """
    Modül 4 (CADTableGenerator) çıktı ve denetim özeti.
    """
    panel_name: str
    total_installed_power_kw: float
    demand_factor: float
    demand_power_kw: float
    l1_kw: float
    l2_kw: float
    l3_kw: float
    phase_imbalance_pct: float
    row_count: int
    dwg_entities_created: int = 0
    dwg_cells_updated: int = 0
    xlsx_path: str = ""
    dwg_table_bbox: Optional[Tuple[float, float, float, float]] = None
    unknown_phase_count: int = 0
    assumptions: List[Dict[str, object]] = field(default_factory=list)
    audit_log: List[Dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class CADTableGenerator:
    """
    Modül 4 — CADTableGenerator (DWG Yükleme Cetveli Çizici + Mevcut Tablo Güncelleyici + .xlsx Üretici)
    --------------------------------------------------------------------------------------------------
    - DWG içine sıfırdan temiz LINE + TEXT ızgarası olarak Yükleme Cetveli çizer.
    - Mevcut DWG tablosunda hücre handle'ları verilmişse CADSafetyGuard üzerinden cerrahi olarak günceller.
    - Birebir aynı doğrulanmış veriyi openpyxl ile imzaya hazır kurumsal Excel (.xlsx) dosyasına aktarır.
    - Kolon şeması (Riser) çizimi v3.1 kapsamındadır; v3.0'da cetvel üretimi ve güncellemesi yapılır.
    """

    def __init__(self, target_layer: str = "E-ETIKET-TABLO") -> None:
        self.target_layer = target_layer

    @staticmethod
    def _compute_phase_summary(
        rows: List[ScheduleRowInput],
        demand_factor: float = 0.80,
    ) -> Tuple[float, float, float, float, float, float, int]:
        """
        (total_kw, demand_kw, l1_kw, l2_kw, l3_kw, imbalance_pct, unknown_phase_count) hesaplar.
        Fazı belirsiz satırlar mühendislik tablosu için üç faza eşit paylaştırılır; bu
        SIFIR VARSAYIM ilkesinin belgelenmiş istisnasıdır ve unknown_phase_count ile
        açıkça TAHMİNİ (ESTIMATED_DEFAULT) olarak raporlanır.
        """
        l1_w = 0.0
        l2_w = 0.0
        l3_w = 0.0
        unknown = 0

        for r in rows:
            ph = (r.phase or "").upper().strip()
            w = max(0.0, float(r.load_watts))
            if ph in ("L1-L2-L3", "3F", "3P", "RST", "L1/L2/L3"):
                l1_w += w / 3.0
                l2_w += w / 3.0
                l3_w += w / 3.0
            elif ph in ("L1", "R"):
                l1_w += w
            elif ph in ("L2", "S"):
                l2_w += w
            elif ph in ("L3", "T"):
                l3_w += w
            else:
                # Belirsiz faz: tablo üretimi için eşit dağıtım (belgelenmiş TAHMİNİ varsayım)
                unknown += 1
                l1_w += w / 3.0
                l2_w += w / 3.0
                l3_w += w / 3.0

        total_kw = (l1_w + l2_w + l3_w) / 1000.0
        demand_kw = total_kw * demand_factor
        l1_kw = l1_w / 1000.0
        l2_kw = l2_w / 1000.0
        l3_kw = l3_w / 1000.0

        phases = [l1_kw, l2_kw, l3_kw]
        max_p = max(phases)
        min_p = min(phases)
        imbalance_pct = round(((max_p - min_p) / max_p) * 100.0, 2) if max_p > 1e-6 else 0.0

        return (
            round(total_kw, 3),
            round(demand_kw, 3),
            round(l1_kw, 3),
            round(l2_kw, 3),
            round(l3_kw, 3),
            imbalance_pct,
            unknown,
        )

    def update_existing_table_cells_in_dwg(
        self,
        doc: Drawing,
        rows: List[ScheduleRowInput],
        approved_cell_handles: Optional[Set[str]] = None,
    ) -> Tuple[int, List[Dict[str, object]]]:
        """
        Mevcut DWG tablosundaki hücre metinlerini (`cell_handles`) Onay İstasyonu kapısından
        (`approved_cell_handles`) geçirerek CADSafetyGuard ile günceller.
        - `approved_cell_handles` None veya boş ise hiçbir mevcut DWG hücresini sessizce değiştirmez
          (`REQUIRES_APPROVAL` olarak kaydeder).
        """
        updated_count = 0
        audit_entries: List[Dict[str, object]] = []

        for r in rows:
            if not r.cell_handles:
                continue
            field_values = {
                "circuit_id": r.circuit_id,
                "description": r.description,
                "load_watts": f"{r.load_watts:.0f}",
                "phase": r.phase,
                "cable_spec": r.cable_spec,
                "breaker_spec": r.breaker_spec,
                "rcd_spec": r.rcd_spec,
                "voltage_drop_pct": f"{r.voltage_drop_pct:.2f}",
            }
            for col_key, handle in r.cell_handles.items():
                if col_key not in field_values or not handle:
                    continue
                new_val = str(field_values[col_key])
                if approved_cell_handles is None or handle not in approved_cell_handles:
                    audit_entries.append({
                        "action": "UPDATE_TABLE_CELL",
                        "circuit_id": r.circuit_id,
                        "column": col_key,
                        "handle": handle,
                        "proposed_text": new_val,
                        "status": "REQUIRES_APPROVAL" if approved_cell_handles is None else "NOT_SELECTED",
                    })
                    continue

                ok, reason_msg, old_val = CADSafetyGuard.safe_update_text_entity(doc, handle, new_val)
                if ok:
                    updated_count += 1
                    audit_entries.append({
                        "action": "UPDATE_TABLE_CELL",
                        "circuit_id": r.circuit_id,
                        "column": col_key,
                        "handle": handle,
                        "old_text": old_val,
                        "new_text": new_val,
                        "status": "APPLIED",
                    })
                else:
                    audit_entries.append({
                        "action": "UPDATE_TABLE_CELL",
                        "circuit_id": r.circuit_id,
                        "column": col_key,
                        "handle": handle,
                        "status": "SKIPPED",
                        "reason": reason_msg,
                    })

        return updated_count, audit_entries

    def draw_panel_schedule_in_dwg(
        self,
        doc: Drawing,
        panel_name: str,
        rows: List[ScheduleRowInput],
        insert_pos: Tuple[float, float] = (0.0, 0.0),
        demand_factor: float = 0.80,
        main_breaker_spec: str = "4x63A Otomatik Şalter",
        supply_cable_spec: str = "4x16+16 mm² N2XH FE180",
        approved_cell_handles: Optional[Set[str]] = None,
    ) -> GeneratedTableReport:
        """
        ModelSpace içerisine `$INSUNITS` ölçeğine duyarlı, standart `E-ETIKET-TABLO` katmanında
        LINE + TEXT ızgarası olarak tam teşekküllü Yükleme Cetveli çizer.
        """
        CADSafetyGuard.ensure_standard_layer(
            doc,
            LayerStandardSpec(
                name=self.target_layer,
                color=7,
                lineweight=25,
                description="Elektrik Yükleme Cetveli ve Etiket Tabloları",
            ),
        )
        msp = doc.modelspace()

        # Ölçekli boyutlar (mm bazlı tanımlanıp çizim birimine çevrilir)
        row_h = UnitScaleResolver.mm_to_drawing_units(80.0, doc)
        header_h = UnitScaleResolver.mm_to_drawing_units(110.0, doc)
        title_h = UnitScaleResolver.mm_to_drawing_units(130.0, doc)
        footer_h = UnitScaleResolver.mm_to_drawing_units(100.0, doc)
        text_h = UnitScaleResolver.mm_to_drawing_units(32.0, doc)
        title_text_h = UnitScaleResolver.mm_to_drawing_units(45.0, doc)
        pad_x = UnitScaleResolver.mm_to_drawing_units(20.0, doc)

        # Sütun genişlikleri (mm bazlı)
        col_defs = [
            ("LINYE NO", UnitScaleResolver.mm_to_drawing_units(240.0, doc)),
            ("LINYE ADI / MAHAL", UnitScaleResolver.mm_to_drawing_units(580.0, doc)),
            ("GUC (W)", UnitScaleResolver.mm_to_drawing_units(240.0, doc)),
            ("L1 (W)", UnitScaleResolver.mm_to_drawing_units(220.0, doc)),
            ("L2 (W)", UnitScaleResolver.mm_to_drawing_units(220.0, doc)),
            ("L3 (W)", UnitScaleResolver.mm_to_drawing_units(220.0, doc)),
            ("KABLO KESITI", UnitScaleResolver.mm_to_drawing_units(420.0, doc)),
            ("SIGORTA", UnitScaleResolver.mm_to_drawing_units(260.0, doc)),
            ("KAK (RCD)", UnitScaleResolver.mm_to_drawing_units(260.0, doc)),
            ("e (%)", UnitScaleResolver.mm_to_drawing_units(200.0, doc)),
        ]
        total_w = sum(w for _, w in col_defs)

        x0, y0 = float(insert_pos[0]), float(insert_pos[1])
        entities_created = 0

        def _add_line(p1: Tuple[float, float], p2: Tuple[float, float]) -> None:
            nonlocal entities_created
            msp.add_line(
                p1,
                p2,
                dxfattribs={"layer": self.target_layer, "color": 256, "lineweight": -1},
            )
            entities_created += 1

        def _add_text(txt: str, pos: Tuple[float, float], height: float) -> None:
            nonlocal entities_created
            msp.add_text(
                txt,
                dxfattribs={
                    "layer": self.target_layer,
                    "insert": pos,
                    "height": height,
                    "color": 256,
                    "lineweight": -1,
                },
            )
            entities_created += 1

        total_kw, demand_kw, l1_kw, l2_kw, l3_kw, imbalance_pct, unknown_cnt = self._compute_phase_summary(
            rows, demand_factor=demand_factor
        )

        # 1. Üst Başlık Kutusu
        y_curr = y0
        _add_line((x0, y_curr), (x0 + total_w, y_curr))
        y_next = y_curr - title_h
        _add_line((x0, y_next), (x0 + total_w, y_next))
        _add_text(
            f"{panel_name} YUKLEME CETVELI | ANA SALTER: {main_breaker_spec} | BESLEME: {supply_cable_spec}",
            (x0 + pad_x, y_next + (title_h - title_text_h) * 0.5),
            title_text_h,
        )
        y_curr = y_next

        # 2. Sütun Başlıkları
        y_header_bottom = y_curr - header_h
        _add_line((x0, y_header_bottom), (x0 + total_w, y_header_bottom))
        cx = x0
        for col_title, col_w in col_defs:
            _add_text(
                col_title,
                (cx + pad_x, y_header_bottom + (header_h - text_h) * 0.5),
                text_h,
            )
            cx += col_w
        y_curr = y_header_bottom

        # 3. Veri Satırları
        for r in rows:
            y_row_bottom = y_curr - row_h
            _add_line((x0, y_row_bottom), (x0 + total_w, y_row_bottom))

            ph = (r.phase or "").upper().strip()
            w = max(0.0, float(r.load_watts))
            if ph in ("L1-L2-L3", "3F", "3P", "RST", "L1/L2/L3"):
                l1_cell, l2_cell, l3_cell = f"{w/3.0:.0f}", f"{w/3.0:.0f}", f"{w/3.0:.0f}"
            elif ph in ("L1", "R"):
                l1_cell, l2_cell, l3_cell = f"{w:.0f}", "-", "-"
            elif ph in ("L2", "S"):
                l1_cell, l2_cell, l3_cell = "-", f"{w:.0f}", "-"
            elif ph in ("L3", "T"):
                l1_cell, l2_cell, l3_cell = "-", "-", f"{w:.0f}"
            else:
                l1_cell, l2_cell, l3_cell = f"{w/3.0:.0f}*", f"{w/3.0:.0f}*", f"{w/3.0:.0f}*"

            row_vals = [
                r.circuit_id,
                r.description,
                f"{w:.0f}",
                l1_cell,
                l2_cell,
                l3_cell,
                r.cable_spec,
                r.breaker_spec,
                r.rcd_spec,
                f"{r.voltage_drop_pct:.2f}",
            ]

            cx = x0
            for val, (_, col_w) in zip(row_vals, col_defs):
                _add_text(
                    str(val),
                    (cx + pad_x, y_row_bottom + (row_h - text_h) * 0.5),
                    text_h,
                )
                cx += col_w

            y_curr = y_row_bottom

        # Dikey Sütun Çizgileri (Sütun başlığı üstünden son veri satırı altına kadar)
        y_grid_top = y0 - title_h
        y_grid_bottom = y_curr
        cx = x0
        for _, col_w in col_defs:
            _add_line((cx, y_grid_top), (cx, y_grid_bottom))
            cx += col_w
        _add_line((x0 + total_w, y_grid_top), (x0 + total_w, y_grid_bottom))

        # 4. Alt Özet Kutusu (Toplam Kurulu Güç, Eşzamanlılık, Talep Gücü, Faz Dengesizliği)
        y_footer_bottom = y_curr - footer_h
        _add_line((x0, y_footer_bottom), (x0 + total_w, y_footer_bottom))
        footer_summary = (
            f"KURULU GUC (Pi): {total_kw:.2f} kW | ESZAMANLILIK (k): {demand_factor:.2f} | "
            f"TALEP GUCU (Pe): {demand_kw:.2f} kW | "
            f"L1: {l1_kw:.2f} kW / L2: {l2_kw:.2f} kW / L3: {l3_kw:.2f} kW | "
            f"FAZ DENGESIZLIGI: %{imbalance_pct:.2f}"
        )
        if unknown_cnt:
            footer_summary += f" | * {unknown_cnt} LINYE FAZI BELIRSIZ: ESHIT DAGITIM (TAHMINI - ESTIMATED_DEFAULT)"
        _add_text(
            footer_summary,
            (x0 + pad_x, y_footer_bottom + (footer_h - text_h) * 0.5),
            text_h,
        )

        # Dış çerçeve sol ve sağ kenar çizgileri
        _add_line((x0, y0), (x0, y_footer_bottom))
        _add_line((x0 + total_w, y0), (x0 + total_w, y_footer_bottom))

        # Varsa ve onaylanmışsa mevcut tablo hücrelerini de güncelle
        updated_cells, cell_audit = self.update_existing_table_cells_in_dwg(
            doc, rows, approved_cell_handles=approved_cell_handles
        )

        return GeneratedTableReport(
            panel_name=panel_name,
            total_installed_power_kw=total_kw,
            demand_factor=demand_factor,
            demand_power_kw=demand_kw,
            l1_kw=l1_kw,
            l2_kw=l2_kw,
            l3_kw=l3_kw,
            phase_imbalance_pct=imbalance_pct,
            row_count=len(rows),
            dwg_entities_created=entities_created,
            dwg_cells_updated=updated_cells,
            dwg_table_bbox=(x0, y_footer_bottom, x0 + total_w, y0),
            unknown_phase_count=unknown_cnt,
            assumptions=(
                [{"tur": "ESTIMATED_DEFAULT", "mesaj": f"{unknown_cnt} linyenin fazı belirsiz; üç faza eşit paylaştırıldı (TAHMINI)"}]
                if unknown_cnt else []
            ),
            audit_log=cell_audit,
        )

    def export_panel_schedule_xlsx(
        self,
        panel_name: str,
        rows: List[ScheduleRowInput],
        output_xlsx_path: str,
        demand_factor: float = 0.80,
        main_breaker_spec: str = "4x63A Otomatik Şalter",
        supply_cable_spec: str = "4x16+16 mm² N2XH FE180",
    ) -> GeneratedTableReport:
        """
        Doğrulanmış Yükleme Cetvelini openpyxl ile kurumsal mühendislik formatında `.xlsx` olarak üretir.
        """
        total_kw, demand_kw, l1_kw, l2_kw, l3_kw, imbalance_pct, unknown_cnt = self._compute_phase_summary(
            rows, demand_factor=demand_factor
        )

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = (panel_name[:28] or "YUKLEME_CETVELI").replace("/", "_")

        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        sub_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        footer_fill = PatternFill(start_color="EDEDED", end_color="EDEDED", fill_type="solid")

        title_font = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
        header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        bold_font = Font(name="Calibri", size=10, bold=True)
        normal_font = Font(name="Calibri", size=10)

        thin_side = Side(border_style="thin", color="808080")
        grid_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        # Üst Başlık
        ws.merge_cells("A1:J1")
        ws["A1"] = f"{panel_name} - PANO YÜKLEME CETVELİ (CLOUDECAD v3.0 DOĞRULANMIŞ ÇIKTI)"
        ws["A1"].fill = header_fill
        ws["A1"].font = title_font
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")

        ws.merge_cells("A2:E2")
        ws["A2"] = f"Ana Şalter: {main_breaker_spec}"
        ws["A2"].fill = sub_fill
        ws["A2"].font = bold_font

        ws.merge_cells("F2:J2")
        ws["F2"] = f"Besleme Kablosu: {supply_cable_spec}"
        ws["F2"].fill = sub_fill
        ws["F2"].font = bold_font

        headers = [
            "Linye No",
            "Linye Adı / Mahal",
            "Güç (W)",
            "L1 (W)",
            "L2 (W)",
            "L3 (W)",
            "Kablo Kesiti",
            "Sigorta / Koruma",
            "KAK (RCD)",
            "Gerilim Düşümü (%)",
        ]
        ws.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=3, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = grid_border

        row_cursor = 4
        for r in rows:
            ph = (r.phase or "").upper().strip()
            w = max(0.0, float(r.load_watts))
            if ph in ("L1-L2-L3", "3F", "3P", "RST", "L1/L2/L3"):
                l1_v, l2_v, l3_v = round(w / 3.0, 1), round(w / 3.0, 1), round(w / 3.0, 1)
            elif ph in ("L1", "R"):
                l1_v, l2_v, l3_v = round(w, 1), 0.0, 0.0
            elif ph in ("L2", "S"):
                l1_v, l2_v, l3_v = 0.0, round(w, 1), 0.0
            elif ph in ("L3", "T"):
                l1_v, l2_v, l3_v = 0.0, 0.0, round(w, 1)
            else:
                l1_v, l2_v, l3_v = f"{round(w / 3.0, 1)}*", f"{round(w / 3.0, 1)}*", f"{round(w / 3.0, 1)}*"

            row_data = [
                r.circuit_id,
                r.description,
                round(w, 1),
                l1_v,
                l2_v,
                l3_v,
                r.cable_spec,
                r.breaker_spec,
                r.rcd_spec,
                round(r.voltage_drop_pct, 2),
            ]
            ws.append(row_data)
            for col_idx in range(1, len(row_data) + 1):
                c = ws.cell(row=row_cursor, column=col_idx)
                c.font = normal_font
                c.border = grid_border
                if col_idx in (1, 3, 4, 5, 6, 8, 9, 10):
                    c.alignment = Alignment(horizontal="center")
            row_cursor += 1

        # Alt Toplam Satırı
        summary_row = [
            "TOPLAM",
            f"Kurulu Güç: {total_kw:.2f} kW | Talep Gücü (k={demand_factor:.2f}): {demand_kw:.2f} kW",
            round(total_kw * 1000.0, 1),
            round(l1_kw * 1000.0, 1),
            round(l2_kw * 1000.0, 1),
            round(l3_kw * 1000.0, 1),
            f"Faz Dengesizliği: %{imbalance_pct:.2f}",
            main_breaker_spec,
            "300mA Seçici",
            "-",
        ]
        ws.append(summary_row)
        for col_idx in range(1, len(summary_row) + 1):
            c = ws.cell(row=row_cursor, column=col_idx)
            c.fill = footer_fill
            c.font = bold_font
            c.border = grid_border

        col_widths = [12, 30, 12, 12, 12, 12, 24, 18, 16, 18]
        for idx, width in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(idx)].width = width

        os.makedirs(os.path.dirname(os.path.abspath(output_xlsx_path)), exist_ok=True)
        wb.save(output_xlsx_path)

        return GeneratedTableReport(
            panel_name=panel_name,
            total_installed_power_kw=total_kw,
            demand_factor=demand_factor,
            demand_power_kw=demand_kw,
            l1_kw=l1_kw,
            l2_kw=l2_kw,
            l3_kw=l3_kw,
            phase_imbalance_pct=imbalance_pct,
            row_count=len(rows),
            xlsx_path=output_xlsx_path,
            unknown_phase_count=unknown_cnt,
            assumptions=(
                [{"tur": "ESTIMATED_DEFAULT", "mesaj": f"{unknown_cnt} linyenin fazı belirsiz; üç faza eşit paylaştırıldı (TAHMINI)"}]
                if unknown_cnt else []
            ),
        )

    @staticmethod
    def save_table_audit_json(report: GeneratedTableReport, output_json_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
        payload = {
            "module": "CADTableGenerator",
            "version": "3.0.0",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "report": report.to_dict(),
        }
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
