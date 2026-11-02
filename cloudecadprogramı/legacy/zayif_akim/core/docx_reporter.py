"""
CloudeCAD — Zayıf Akım & Yangın Algılama Kurumsal Word (.docx) Raporlayıcısı
============================================================================
Bina (BYKHY, TS EN 54, BTK, TS EN 50083), Metro/Tünel (NFPA 130, TS EN 54-16/22,
EN 50121-4) ve Endüstriyel Tesis (TS EN 54-12 Beam, ATEX / Ex-Proof, TS EN 54-23 VAD)
tipolojileri için kurumsal Microsoft Word (.docx) denetim raporu üretir.
"""

import importlib.util
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

# Ortak CorporateDocxBase sınıfını isim çakışması olmadan yükle
_DOCX_BASE_PATH = Path(__file__).resolve().parents[2] / "topraklama_motoru" / "core" / "docx_base.py"
_spec = importlib.util.spec_from_file_location("cloudecad_docx_base", str(_DOCX_BASE_PATH))
_docx_base_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_docx_base_mod)
CorporateDocxBase = _docx_base_mod.CorporateDocxBase

from core.models import WeakCurrentAuditReport


class WeakCurrentDocxReporter(CorporateDocxBase):
    """
    Zayıf Akım ve Yangın Algılama Sistemleri için Kurumsal Word (.docx) Rapor Üreticisi.
    """

    def __init__(self, report: WeakCurrentAuditReport, output_dir: Path):
        self.report = report
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.slug = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in report.project_name)

    def generate(self) -> Path:
        doc = Document()

        for section in doc.sections:
            section.page_width = Cm(21.0)
            section.page_height = Cm(29.7)
            section.top_margin = Cm(1.8)
            section.bottom_margin = Cm(1.8)
            section.left_margin = Cm(1.8)
            section.right_margin = Cm(1.8)

        style_normal = doc.styles["Normal"]
        style_normal.font.name = "Calibri"
        style_normal.font.size = Pt(9.5)
        style_normal.font.color.rgb = self.COLOR_TEXT

        p_head = doc.add_paragraph()
        p_head.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_head.paragraph_format.space_after = Pt(2)
        r_h1 = p_head.add_run("CLOUDECAD — ZAYIF AKIM VE YANGIN ALGILAMA SİSTEMLERİ DENETİM RAPORU\n")
        r_h1.bold = True
        r_h1.font.size = Pt(13.5)
        r_h1.font.color.rgb = self.COLOR_NAVY

        r_h2 = p_head.add_run(
            f"Proje: {self.report.project_name}  |  Tipoloji: {self.report.typology}  |  "
            f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        r_h2.font.size = Pt(9.5)
        r_h2.font.color.rgb = self.COLOR_MUTED

        # ── BÖLÜM 1: PROJE KÜNYESİ VE TİPOLOJİ SINIFLANDIRMASI ───────────────
        self._add_section_header(doc, "1", "PROJE KÜNYESİ VE ZAYIF AKIM TİPOLOJİ SINIFLANDIRMASI")

        self._add_callout_box(
            doc,
            f"GENEL MÜHENDİSLİK KARARI: {self.report.overall_verdict} (Uyumluluk Skoru: %{self.report.score_pct:.0f})",
            f"Algılanan Tesis Tipolojisi: {self.report.typology} (Güven: %{self.report.typology_confidence*100:.0f})\n"
            f"Dayanak Standartlar: {self.report.typology_rationale}",
            bg_hex=self.HEX_SUCCESS_BG if self.report.score_pct >= 85 else (
                self.HEX_WARNING_BG if self.report.score_pct >= 65 else self.HEX_DANGER_BG
            ),
            border_hex="15803D" if self.report.score_pct >= 85 else (
                "B45309" if self.report.score_pct >= 65 else "B91C1C"
            ),
        )

        f = self.report.fire_alarm
        t = self.report.telecom
        tv = self.report.smatv
        ic = self.report.intercom

        kv_rows = [
            ("Proje / Dosya Adı", self.report.project_name, "Tesis Tipolojisi", self.report.typology),
            ("Yangın Santral Tipi", f"{f.system_type} ({f.total_devices} Cihaz)",
             "FE180 / PH120 Kablo", "✓ Belirtilmiş" if f.fe180_cable_specified else "⚠ Çizim Notunda Yok"),
            ("Duman / Isı Dedektörü", f"Duman: {f.smoke_detectors} | Isı: {f.heat_detectors}",
             "Beam / Alev / Ex-Proof", f"Beam/Alev: {f.beam_flame_cnt if hasattr(f, 'beam_flame_cnt') else f.beam_flame_detectors} | Ex-Proof: {f.ex_proof_devices}"),
            ("Yangın Buton & Siren", f"Buton (YB): {f.manual_call_points} | Siren (SKM): {f.sirens_flashers}",
             "Fiber LHD / PA-VA Anons", f"LHD: {f.linear_heat_detector_m:.0f}m | PA/VA Hoparlör: {t.pava_speakers}"),
            ("Data / Telekom & CCTV", f"RJ45/Data: {t.sockets} | BTK: {t.main_boxes} | CCTV: {t.cctv_cameras}",
             "SMATV & İnterkom Durumu", f"TV: {tv.status} ({tv.tv_sockets}) | Diafon: {ic.status} ({ic.monitors})"),
        ]

        tbl_meta = doc.add_table(rows=len(kv_rows), cols=4)
        tbl_meta.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._set_table_borders(tbl_meta)
        for r_idx, (k1, v1, k2, v2) in enumerate(kv_rows):
            row_cells = tbl_meta.rows[r_idx].cells
            for c_i, txt in enumerate((k1, v1, k2, v2)):
                self._set_cell_margins(row_cells[c_i], top=75, bottom=75, left=100, right=100)
                p = row_cells[c_i].paragraphs[0]
                run = p.add_run(str(txt))
                run.font.size = Pt(8.5)
                if c_i in (0, 2):
                    self._set_cell_background(row_cells[c_i], "E2E8F0")
                    run.bold = True
                    run.font.color.rgb = self.COLOR_NAVY
                else:
                    if r_idx % 2 == 1:
                        self._set_cell_background(row_cells[c_i], self.HEX_ZEBRA_BG)

        # ── BÖLÜM 2: ALT SİSTEM ENVANTER VE KAPASİTE TABLOSU ─────────────────
        self._add_section_header(doc, "2", "ALT SİSTEM ENVANTERİ VE STANDART UYUMLULUK MATRİSİ")

        headers_sys = ["Alt Sistem", "Tespit Edilen Cihaz & Kapasite Özeti", "İlgili Yönetmelik / Norm", "Durum"]
        tbl_sys = doc.add_table(rows=1, cols=4)
        tbl_sys.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._set_table_borders(tbl_sys)

        for i, h in enumerate(headers_sys):
            c = tbl_sys.rows[0].cells[i]
            self._set_cell_background(c, self.HEX_HEADER_BG)
            self._set_cell_margins(c, top=80, bottom=80, left=90, right=90)
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(h)
            r.bold = True
            r.font.size = Pt(8.5)
            r.font.color.rgb = RGBColor(255, 255, 255)

        sys_rows = [
            ("Yangın Algılama & İhbar", f.notes, "BYKHY / TS EN 54 / NFPA 130", f.status),
            ("Yapısal Kablolama / Fiber / PA-VA", t.notes, "BTK / TIA-EIA-568 / TS EN 54-16", t.status),
            ("SMATV / Merkezi Uydu TV", tv.notes, "TS EN 50083 / RG6-U6", tv.status),
            ("İnterkom & Kapı Kontrol", ic.notes, "TS EN 62820 / Diafon", ic.status),
        ]
        for r_idx, (sname, snotes, snorm, sstat) in enumerate(sys_rows):
            row = tbl_sys.add_row().cells
            for c_i, val in enumerate((sname, snotes, snorm, sstat)):
                self._set_cell_margins(row[c_i], top=65, bottom=65, left=90, right=90)
                if r_idx % 2 == 1:
                    self._set_cell_background(row[c_i], self.HEX_ZEBRA_BG)
                p = row[c_i].paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_i in (2, 3) else WD_ALIGN_PARAGRAPH.LEFT
                r = p.add_run(str(val))
                r.font.size = Pt(8.5)
                if c_i in (0, 3):
                    r.bold = True

        # ── BÖLÜM 3: MÜHENDİSLİK DENETİM BULGULARI VE REVİZYON TALİMATLARI ───
        self._add_section_header(doc, "3", "ZAYIF AKIM & YANGIN GÜVENLİĞİ DENETİM BULGULARI VE TALİMATLAR")

        headers_f = ["Önem", "Sistem", "İncelenen Eleman", "Tespit Edilen Eksiklik & Risk", "Kesin Düzeltme / Revizyon Talimatı"]
        tbl_f = doc.add_table(rows=1, cols=len(headers_f))
        tbl_f.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._set_table_borders(tbl_f)

        for i, h in enumerate(headers_f):
            c = tbl_f.rows[0].cells[i]
            self._set_cell_background(c, self.HEX_HEADER_BG)
            self._set_cell_margins(c, top=80, bottom=80, left=80, right=80)
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(h)
            r.bold = True
            r.font.size = Pt(8.0)
            r.font.color.rgb = RGBColor(255, 255, 255)

        for r_idx, item in enumerate(self.report.findings):
            row = tbl_f.add_row().cells
            vals = [
                item.severity,
                item.system,
                item.element,
                f"{item.issue}\nEtki: {item.impact}",
                item.correction,
            ]
            for c_i, val in enumerate(vals):
                self._set_cell_margins(row[c_i], top=65, bottom=65, left=80, right=80)
                if r_idx % 2 == 1:
                    self._set_cell_background(row[c_i], self.HEX_ZEBRA_BG)
                p = row[c_i].paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_i in (0, 1) else WD_ALIGN_PARAGRAPH.LEFT
                r = p.add_run(str(val))
                r.font.size = Pt(8.0)
                if c_i == 0:
                    r.bold = True
                    if item.severity == "KRİTİK":
                        self._set_cell_background(row[c_i], self.HEX_DANGER_BG)
                        r.font.color.rgb = self.COLOR_DANGER
                    elif item.severity == "UYARI":
                        self._set_cell_background(row[c_i], self.HEX_WARNING_BG)
                        r.font.color.rgb = self.COLOR_WARNING
                    else:
                        self._set_cell_background(row[c_i], self.HEX_SUCCESS_BG)
                        r.font.color.rgb = self.COLOR_SUCCESS

        out_path = self.output_dir / f"Zayif_Akim_Muhendislik_Raporu_{self.slug}.docx"
        doc.save(str(out_path))
        return out_path
