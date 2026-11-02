"""
CloudeCAD — Endüstriyel Tesis & OG Trafo Merkezi Word (.docx) Rapor Üretici
============================================================================
Ortak CorporateDocxBase (core/docx_base.py) sınıfını miras alarak
IEEE Std 80-2013, TS EN 50522 ve ETTY kapsamında resmi kurumsal Word denetim
raporu üretir.
"""

from pathlib import Path
from datetime import datetime
from typing import Optional, Any

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

from core.docx_base import CorporateDocxBase
from core.industrial_analyzer import IndustrialAnalysisResult


class IndustrialDocxReporter(CorporateDocxBase):
    """Endüstriyel tesis ve OG trafo merkezi topraklama Word raporu üreticisi."""

    def generate_report(
        self,
        res: IndustrialAnalysisResult,
        drawing: Any,
        output_path: Path,
        preview_png_path: Optional[Path] = None
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = Document()
        for sec in doc.sections:
            sec.top_margin = Inches(0.75)
            sec.bottom_margin = Inches(0.75)
            sec.left_margin = Inches(0.8)
            sec.right_margin = Inches(0.8)

        doc.styles['Normal'].font.name = 'Calibri'
        doc.styles['Normal'].font.size = Pt(9.5)
        doc.styles['Normal'].font.color.rgb = self.COLOR_TEXT

        # ── 1. KURUMSAL BAŞLIK BANNERI ─────────────────────────────────────
        hdr_tbl = doc.add_table(rows=1, cols=1)
        hdr_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        hcell = hdr_tbl.cell(0, 0)
        self._set_cell_background(hcell, self.HEX_SUBHEADER_BG)
        self._set_cell_margins(hcell, top=160, bottom=160, left=200, right=200)

        hp = hcell.paragraphs[0]
        r1 = hp.add_run("CLOUDECAD — ENDÜSTRİYEL TESİS VE OG TRAFO MERKEZİ TOPRAKLAMA DENETİM RAPORU\n")
        r1.bold = True
        r1.font.size = Pt(12.5)
        r1.font.color.rgb = RGBColor(255, 255, 255)

        r2 = hp.add_run(
            f"Proje: {res.project_name} | Tipoloji: {res.facility_subtype}\n"
            f"Standartlar: IEEE Std 80-2013, TS EN 50522, ETTY (Madde 10 & Ek-P) | Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        r2.font.size = Pt(9)
        r2.font.color.rgb = RGBColor(203, 213, 225)

        doc.add_paragraph().paragraph_format.space_after = Pt(4)

        # ── 2. YÖNETİCİ ÖZETİ VE MÜHENDİSLİK HÜKMÜ ─────────────────────────
        self._add_section_header(doc, "1", "Yönetici Özeti ve Mühendislik Uygunluk Hükmü")
        is_ok = "UYGUNDUR" in res.executive_verdict
        self._add_callout_box(
            doc,
            f"BAŞMÜHENDİSLİK DENETİM KARARI: {res.executive_verdict} (Uyum Skoru: %{res.compliance_score_percent:.1f})",
            res.verdict_summary,
            bg_hex=self.HEX_SUCCESS_BG if is_ok else self.HEX_DANGER_BG,
            border_hex="15803D" if is_ok else "B91C1C"
        )

        # ── 3. ELEKTROT ŞEBEKESİ VE IEEE 80 DİRENÇ / GERİLİM TABLOSU ───────
        self._add_section_header(doc, "2", "Topraklama Ağı Direnci (Rg ≤ 1.0 Ω) ve IEEE Std 80 Adım/Dokunma Gerilimi")
        st = res.step_touch
        kv_rows = [
            ("Tesis Alanı & Boyutları", f"{res.facility_area_m2:.0f} m² ({res.facility_width_m:.1f}m × {res.facility_length_m:.1f}m)",
             "Zemin Özgül Direnci (ρ)", f"{res.rho_ohm_m:.1f} Ω·m (Yüzey Mıcır ρs={st.rho_s_crushed_rock_ohm_m:.0f} Ω·m, Cs={st.cs_derating_factor:.2f})"),
            ("Toplam Gömülü İletken (L)", f"{res.total_strip_length_m:.1f} m",
             "Dikey Topraklama Elektrotu", f"{res.rod_count} Adet Kazık | {res.busbar_count} Adet OG/AG Bara"),
            ("Eşdeğer Direnç — IEEE 80 (Rg)", f"{res.rg_ieee80_sverak_ohm:.3f} Ω (Sınır ≤ 1.00 Ω)",
             "Eşdeğer Direnç — Laurent (Re)", f"{res.re_laurent_ohm:.3f} Ω"),
            ("Müsaade Edilen Dokunma (Etouch70)", f"{st.e_touch70_limit_v:.1f} V (tf = {st.fault_time_tf_s:.2f} s)",
             "Oluşan Maks. Göz Gerilimi (Em)", f"{st.em_actual_mesh_voltage_v:.1f} V — {'✓ GÜVENLİ' if st.is_touch_safe else '✗ AŞIM'}"),
            ("Müsaade Edilen Adım (Estep70)", f"{st.e_step70_limit_v:.1f} V",
             "Oluşan Maks. Adım Gerilimi (Es)", f"{st.es_actual_step_voltage_v:.1f} V — {'✓ GÜVENLİ' if st.is_step_safe else '✗ AŞIM'}"),
            ("Ağ Gözü Sayısı & Sıklığı", f"{res.total_mesh_eyes} Göz (Ort. D ≈ {res.grid_spacing_d_m:.1f} m)",
             "10×10m Sınırını Aşan Göz", f"{res.oversized_eyes_10m} Adet (Maks. Göz: {res.max_eye_dim_m:.1f} m)"),
        ]

        tbl = doc.add_table(rows=len(kv_rows), cols=4)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._set_table_borders(tbl)
        for r_i, rdata in enumerate(kv_rows):
            row = tbl.rows[r_i]
            for c_i in range(4):
                cell = row.cells[c_i]
                self._set_cell_margins(cell, top=60, bottom=60, left=80, right=80)
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                r = p.add_run(rdata[c_i])
                r.font.size = Pt(8.5)
                if c_i % 2 == 0:
                    r.bold = True
                    r.font.color.rgb = self.COLOR_PRIMARY
                    self._set_cell_background(cell, "F1F5F9")
                else:
                    self._set_cell_background(cell, "FFFFFF")

        doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # ── 4. ŞARTNAME UYGUNLUK MATRİSİ ───────────────────────────────────
        self._add_section_header(doc, "3", "IEEE Std 80-2013 & TS EN 50522 Şartname Denetim Matrisi")
        sc_tbl = doc.add_table(rows=len(res.spec_checks) + 1, cols=3)
        sc_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._set_table_borders(sc_tbl)

        heads = ["Denetim Kriteri", "Standart / Şartname Hükmü", "Proje Denetim Bulgusu"]
        for c_i, h in enumerate(heads):
            c = sc_tbl.rows[0].cells[c_i]
            self._set_cell_background(c, self.HEX_HEADER_BG)
            self._set_cell_margins(c, top=70, bottom=70, left=80, right=80)
            r = c.paragraphs[0].add_run(h)
            r.bold = True
            r.font.size = Pt(8.5)
            r.font.color.rgb = RGBColor(255, 255, 255)

        for idx, chk in enumerate(res.spec_checks, start=1):
            row = sc_tbl.rows[idx]
            for c_i, key in enumerate(["kriter", "sartname", "durum"]):
                cell = row.cells[c_i]
                self._set_cell_margins(cell, top=55, bottom=55, left=80, right=80)
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                val = chk[key]
                r = p.add_run(val)
                r.font.size = Pt(8.0)
                if c_i == 0:
                    r.bold = True
                    self._set_cell_background(cell, "F8FAFC")
                elif c_i == 2:
                    r.bold = True
                    if "✗" in val:
                        r.font.color.rgb = self.COLOR_DANGER
                        self._set_cell_background(cell, self.HEX_DANGER_BG)
                    elif "⚠" in val:
                        r.font.color.rgb = self.COLOR_WARNING
                        self._set_cell_background(cell, self.HEX_WARNING_BG)
                    else:
                        r.font.color.rgb = self.COLOR_SUCCESS
                        self._set_cell_background(cell, self.HEX_SUCCESS_BG)
                else:
                    self._set_cell_background(cell, "FFFFFF")

        doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # ── 5. CAD GÖRSEL DENETİM HARİTASI ─────────────────────────────────
        if preview_png_path and Path(preview_png_path).exists():
            self._add_section_header(doc, "4", "CAD Görsel Denetim Planı")
            try:
                ip = doc.add_paragraph()
                ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
                ip.add_run().add_picture(str(preview_png_path), width=Inches(6.0))
            except Exception:
                pass

        doc.save(str(output_path))
        return output_path
