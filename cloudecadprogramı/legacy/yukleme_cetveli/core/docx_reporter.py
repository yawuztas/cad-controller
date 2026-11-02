"""
CloudeCAD — Kuvvetli Akım & Yükleme Cetveli Kurumsal Word (.docx) Raporlayıcısı
===============================================================================
Bina (TS HD 60364 / EİTY), Metro/Tünel (NFPA 130 / EN 50122) ve Endüstriyel Tesis
(IEC 60364 / IEC 60909) tipolojileri için resmi Microsoft Word (.docx) denetim,
kablo metraj, çapraz doğrulama ve mühendislik hesap raporu üretir.
"""

import importlib.util
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

# Ortak CorporateDocxBase sınıfını isim çakışması olmadan yükle
_DOCX_BASE_PATH = Path(__file__).resolve().parents[2] / "topraklama_motoru" / "core" / "docx_base.py"
_spec = importlib.util.spec_from_file_location("cloudecad_docx_base", str(_DOCX_BASE_PATH))
_docx_base_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_docx_base_mod)
CorporateDocxBase = _docx_base_mod.CorporateDocxBase

from core.models import ExtractedProjectData
from core.tier3_calculator import EngineeringAuditReport


class PowerDocxReporter(CorporateDocxBase):
    """
    Kuvvetli Akım, Priz, Aydınlatma ve Yükleme Cetveli Denetim Motoru için
    Kurumsal Word (.docx) Rapor Üreticisi.
    """

    def __init__(self, data: ExtractedProjectData, report: EngineeringAuditReport, output_dir: Path, custom_filename: Optional[str] = None):
        self.data = data
        self.report = report
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.slug = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in data.project_name)
        self.custom_filename = custom_filename

    def _add_styled_table(self, doc: Document, headers: List[str], rows_data: List[List[str]], status_col_idx: Optional[int] = None):
        tbl = doc.add_table(rows=1, cols=len(headers))
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._set_table_borders(tbl)

        for i, h in enumerate(headers):
            c = tbl.rows[0].cells[i]
            self._set_cell_background(c, self.HEX_HEADER_BG)
            self._set_cell_margins(c, top=75, bottom=75, left=75, right=75)
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(h)
            r.bold = True
            r.font.size = Pt(8.0)
            r.font.color.rgb = RGBColor(255, 255, 255)

        for r_idx, r_vals in enumerate(rows_data):
            row = tbl.add_row().cells
            for c_i, val in enumerate(r_vals):
                self._set_cell_margins(row[c_i], top=55, bottom=55, left=75, right=75)
                if r_idx % 2 == 1:
                    self._set_cell_background(row[c_i], self.HEX_ZEBRA_BG)
                p = row[c_i].paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if c_i == 0 else WD_ALIGN_PARAGRAPH.CENTER
                r = p.add_run(str(val))
                r.font.size = Pt(8.0)
                if c_i == 0:
                    r.bold = True
                if status_col_idx is not None and c_i == status_col_idx:
                    r.bold = True
                    v_up = str(val).upper()
                    if any(k in v_up for k in ["✗", "HATA", "KRİTİK", "İHLAL", "FARK", "YOK", "YETERSİZ", "AŞILDI"]):
                        self._set_cell_background(row[c_i], self.HEX_DANGER_BG)
                        r.font.color.rgb = self.COLOR_DANGER
                    elif any(k in v_up for k in ["⚠", "UYARI", "SINIR", "RİSK"]):
                        self._set_cell_background(row[c_i], self.HEX_WARNING_BG)
                        r.font.color.rgb = self.COLOR_WARNING
                    else:
                        self._set_cell_background(row[c_i], self.HEX_SUCCESS_BG)
                        r.font.color.rgb = self.COLOR_SUCCESS
        return tbl

    def generate(self) -> Path:
        doc = Document()

        for section in doc.sections:
            section.page_width = Cm(21.0)
            section.page_height = Cm(29.7)
            section.top_margin = Cm(1.6)
            section.bottom_margin = Cm(1.6)
            section.left_margin = Cm(1.6)
            section.right_margin = Cm(1.6)

        style_normal = doc.styles["Normal"]
        style_normal.font.name = "Calibri"
        style_normal.font.size = Pt(9.5)
        style_normal.font.color.rgb = self.COLOR_TEXT

        # Üst Başlık Bandı
        p_head = doc.add_paragraph()
        p_head.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_head.paragraph_format.space_after = Pt(4)
        title_str = (
            "CLOUDECAD — RAYLI SİSTEM / METRO KUVVETLİ AKIM, PRİZ VE AYDINLATMA DENETİM RAPORU\n"
            if self.data.is_metro_plan_sheet
            else "CLOUDECAD — KUVVETLİ AKIM VE YÜKLEME CETVELİ MÜHENDİSLİK DENETİM RAPORU\n"
        )
        r_h1 = p_head.add_run(title_str)
        r_h1.bold = True
        r_h1.font.size = Pt(13.0)
        r_h1.font.color.rgb = self.COLOR_NAVY

        sub_info = (
            f"Proje: {self.data.project_name}  |  İstasyon: {self.data.metro_station_code or '-'} ({self.data.metro_sheet_discipline or self.report.typology})  |  "
            f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            if self.data.is_metro_plan_sheet
            else f"Proje: {self.data.project_name}  |  Tipoloji: {self.report.typology}  |  Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        r_h2 = p_head.add_run(sub_info)
        r_h2.font.size = Pt(9.0)
        r_h2.font.color.rgb = self.COLOR_MUTED

        # ── BÖLÜM 1: PROJE KÜNYESİ VE YÖNETİCİ ÖZETİ ────────────────────────
        self._add_section_header(doc, "1", "PROJE KÜNYESİ VE ELEKTRİKSEL YÖNETİCİ ÖZETİ")

        self._add_callout_box(
            doc,
            f"GENEL MÜHENDİSLİK KARARI: {self.report.overall_verdict} (Uyumluluk Skoru: %{self.report.score_pct:.0f})",
            f"Tipoloji Gerekçesi: {self.report.typology_rationale}\n"
            f"Uygulanan Standartlar: TS HD 60364-5-52 (Kablo Akım Taşıma & Gerilim Düşümü), "
            f"TS HD 60364-4-43 (Aşırı Akım & Termik Dayanım), IEC 60909 (Kısa Devre Hesabı), "
            f"NFPA 130 & EN 50122 (Raylı Sistem & Tünel Yangın/Elektrik Güvenliği), EİTY Md. 57.",
            bg_hex=self.HEX_SUCCESS_BG if self.report.score_pct >= 85 else (
                self.HEX_WARNING_BG if self.report.score_pct >= 65 else self.HEX_DANGER_BG
            ),
            border_hex="15803D" if self.report.score_pct >= 85 else (
                "B45309" if self.report.score_pct >= 65 else "B91C1C"
            ),
        )

        at_pb = self.report.phase_balance_results.get(self.data.main_panel.name) or self.report.phase_balance_results.get("AT")
        at_sc = self.report.short_circuit_results.get(self.data.main_panel.name) or self.report.short_circuit_results.get("AT")
        total_circuits = sum(len(sp.circuits) for sp in self.data.sub_panels.values())

        kv_rows = [
            ("Proje / Pafta Adı", self.data.project_name, "Tesis Tipolojisi / Disiplin", self.data.metro_sheet_discipline or str(self.report.typology)),
            ("Toplam Kurulu Güç (Pkur)", f"{self.report.main_installed_power_w:,.0f} W ({self.report.main_installed_power_w/1000:.1f} kW)",
             "Toplam Talep Gücü (Ptal)", f"{self.report.main_demand_power_w:,.0f} W ({self.report.main_demand_power_w/1000:.1f} kW, ks={self.report.main_diversity_factor:.2f})"),
            ("Ana Besleme / Bara", f"{self.data.main_panel.name} — {self.data.main_panel.feeder_cable_spec}",
             "Ana Hat Tasarım Akımı (Ib)", f"{self.report.main_feeder_current_a:.1f} A (Gerilim Düşümü: %{self.report.main_feeder_vdrop_pct:.2f})"),
            ("Dağıtım Panosu & Linye", f"{len(self.data.sub_panels)} Adet Pano / {total_circuits} Adet Linye",
             "3 Faz Yük Dengesi (AT/ADP)", f"Asimetri %{at_pb.unbalance_pct:.1f} (Inötr = {at_pb.current_neutral_a:.1f} A)" if at_pb else "-"),
            ("CAD Kablo Çizim Metrajı", f"{self.data.metro_poly_total_m:,.1f} m (Vektörel Polyline)" if self.data.is_metro_plan_sheet else "-",
             "Metraj Tablosu Toplamı", f"{self.data.metro_table_total_m:,.1f} m ({self.data.metro_table_count} Satır)" if self.data.is_metro_plan_sheet else (f"{at_sc.ik3_max_ka:.2f} kA" if at_sc else "-")),
        ]

        tbl_meta = doc.add_table(rows=len(kv_rows), cols=4)
        tbl_meta.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._set_table_borders(tbl_meta)
        for r_idx, (k1, v1, k2, v2) in enumerate(kv_rows):
            row_cells = tbl_meta.rows[r_idx].cells
            for c_i, txt in enumerate((k1, v1, k2, v2)):
                self._set_cell_margins(row_cells[c_i], top=70, bottom=70, left=100, right=100)
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

        # Metro İşletme Senaryoları Özeti (Varsa)
        if self.report.metro_scenarios:
            ms = self.report.metro_scenarios
            p_ms = doc.add_paragraph()
            p_ms.paragraph_format.space_before = Pt(6)
            p_ms.paragraph_format.space_after = Pt(2)
            r_ms = p_ms.add_run(
                f"▸ NFPA 130 Metro İşletme Senaryoları Güç Analizi: Normal İşletme Modu = {ms.normal_mode_kw:,.1f} kW  |  "
                f"Yangın/Acil Durum Modu = {ms.emergency_fire_mode_kw:,.1f} kW  |  "
                f"Gece Modu = {ms.night_mode_kw:,.1f} kW  |  Boyutlandırma Zirve Gücü = {ms.peak_demand_kw:,.1f} kW ({ms.governing_scenario})"
            )
            r_ms.bold = True
            r_ms.font.size = Pt(8.5)
            r_ms.font.color.rgb = self.COLOR_NAVY

        # ── BÖLÜM 2: PANO HİYERARŞİSİ, KABLO VE KORUMA KOORDİNASYONU ─────────
        sec2_title = (
            "DAĞITIM PANOLARI LİNYE DAĞILIMI VE REFERANS BESLEME / GERİLİM DÜŞÜMÜ ANALİZİ"
            if self.data.is_metro_plan_sheet
            else "DAĞITIM PANOLARI, AKIM TAŞIMA (Iz) VE GERİLİM DÜŞÜMÜ (%e) DENETİMİ"
        )
        self._add_section_header(doc, "2", sec2_title)

        if self.data.is_metro_plan_sheet:
            p_note = doc.add_paragraph()
            p_note.paragraph_format.space_before = Pt(2)
            p_note.paragraph_format.space_after = Pt(4)
            r_note = p_note.add_run(
                "ℹ Mühendislik Notu: İncelenen pafta bir 'Kat Planı ve Kablo Metraj Paftası' olup üzerinde tek hat şeması veya pano yükleme cetveli "
                "bulunmamaktadır. Aşağıdaki tabloda panolar, kat planındaki BS çağrı etiketleri ve Metraj Tablosundaki linyelere göre gruplanmış; "
                "güç ve besleme kesitleri bağlı linyelerin kablo kesitlerinden referans olarak hesaplanmıştır."
            )
            r_note.italic = True
            r_note.font.size = Pt(8.0)
            r_note.font.color.rgb = self.COLOR_MUTED

        headers_p = [
            "Pano Kodu", "Linye Adedi", "Kurulu Güç (W)", "Talep Gücü (W)", "Akım Ib (A)",
            "Şalter In (A)", "Düzeltilmiş Iz (A)", "Kablo Kesiti & En Uzun Hat", "Gerilim D. (%e)", "Durum"
        ]
        rows_p = []
        for pname, pres in self.report.panel_results.items():
            sp = self.data.sub_panels.get(pname)
            c_cnt = len(sp.circuits) if sp else 0
            c_spec = f"{pres.cable_spec} (Lmax={pres.feeder_length_m:.0f}m)"
            coord_ok = (pres.breaker_coordination_status == "UYGUN") and (pres.rcd_status == "UYGUN") and (pres.vdrop_status == "UYGUN")
            has_tri_err = sp and sp.triangulation_status != "✓ UYUMLU"
            if not coord_ok:
                status_str = "✗ SINIR AŞILDI" if pres.vdrop_status != "UYGUN" else "⚠ KOORDİNASYON"
            elif has_tri_err:
                status_str = "⚠ TABLO FARKI"
            else:
                status_str = "✓ UYGUN"

            rows_p.append([
                pname,
                str(c_cnt),
                f"{pres.installed_power_w:,.0f}",
                f"{pres.demand_power_w_proj:,.0f}",
                f"{pres.current_ib_a:.1f}",
                f"{pres.breaker_rating_a:.0f}A",
                f"{pres.cable_corrected_ampacity_iz:.1f}A",
                c_spec,
                f"%{pres.vdrop_exact_pct:.2f}",
                status_str
            ])
        self._add_styled_table(doc, headers_p, rows_p, status_col_idx=9)

        # ── BÖLÜM 3: METRO KATMAN METRAJI, SAHA EKİPMANLARI VE ÇAPRAZ KONTROL ─
        sec_no = 3
        if self.data.is_metro_plan_sheet:
            self._add_section_header(doc, str(sec_no), "KATMAN BAZLI CAD KABLO METRAJI, EKİPMAN SAYIMI VE PLAN/TABLO KARŞILAŞTIRMASI")
            sec_no += 1

            # 3.1 Katman Bazlı Polyline Kablo Metrajı & Ekipman Sayımı
            layer_rows = []
            for l_name, l_len in self.data.metro_layer_lengths.items():
                l_desc = "Normal Priz Linyeleri (Şebeke)" if "PRZ_N" in l_name else (
                    "Acil Durum Priz Linyeleri (Jeneratör/Essential)" if "PRZ_E" in l_name or "PRZ-E" in l_name else (
                        "UPS Kesintisiz Priz Linyeleri" if "PRZ_T" in l_name else (
                            "Peron / Ray Priz Panosu (RPP) Hatları" if "RPP" in l_name else (
                                "Tünel Bakım Priz Panosu (TPP) Hatları" if "TPP" in l_name else (
                                    "Normal Aydınlatma Linyeleri" if "AYD-N" in l_name else (
                                        "Acil Durum Aydınlatma Linyeleri (NFPA 130)" if "AYD-E" in l_name else (
                                            "UPS / Tünel Aydınlatma Linyeleri" if "AYD-T" in l_name else (
                                                "Acil Çıkış / Yönlendirme Armatür Hatları" if "YONLENDIRME" in l_name else (
                                                    "Acil Mekanik / Yangın Fan & Damper Kabloları" if "acil-KABLO" in l_name else (
                                                        "Normal Mekanik Ekipman Kabloları" if "mekanik-kablo" in l_name else (
                                                            "Ana Kuvvet / Dağıtım Kabloları" if "KUVVET" in l_name else "Elektrik Tesisat Katmanı"
                                                        )
                                                    )
                                                )
                                            )
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
                layer_rows.append([l_name, l_desc, f"{l_len:,.1f} m", "CAD Vektörel Ölçüm (Polyline/Line)"])

            if self.data.metro_table_count > 0:
                diff_m = self.data.metro_table_total_m - self.data.metro_poly_total_m
                if "KUVVET" in self.data.metro_sheet_discipline or "GÜÇ" in self.data.metro_sheet_discipline:
                    diff_note = f"✓ Ortak Tava (Trunk) Çoklu Hat + Şaft Payı: +{diff_m:,.1f} m"
                else:
                    diff_note = f"✓ Tablo Düşey/Şaft Payı: +{diff_m:,.1f} m" if diff_m >= 0 else f"ℹ Kat Planı Çizim Farkı: {diff_m:,.1f} m"
                layer_rows.append([
                    "TOPLAM (CAD vs TABLO)",
                    f"Plan BS/HS Etiket: {self.data.metro_bs_count} Adet | Metraj Tablosu: {self.data.metro_table_count} Satır",
                    f"CAD: {self.data.metro_poly_total_m:,.1f} m  |  Tablo: {self.data.metro_table_total_m:,.1f} m",
                    diff_note
                ])
            elif getattr(self.data, "sheet_role", "") == "METRO_TOPLU_PLAN_METRAJ":
                layer_rows.append([
                    "TOPLAM (CAD ÖLÇÜMÜ)",
                    f"Plan BS Etiket: {self.data.metro_bs_count} Adet | Metraj Tablosu: BULUNAMADI",
                    f"CAD: {self.data.metro_poly_total_m:,.1f} m",
                    "✗ METRAJ TABLOSU EKSİK"
                ])
            else:
                layer_rows.append([
                    "TOPLAM (KAT PLANI ÖLÇÜMÜ)",
                    f"Rol: {getattr(self.data, 'sheet_role', '-')} | Kat: {getattr(self.data, 'floor_name', '-')} | Etiket: {self.data.metro_bs_count} Adet",
                    f"CAD: {self.data.metro_poly_total_m:,.1f} m",
                    "✓ KAT PLANI VEKTÖREL ÖLÇÜM"
                ])

            self._add_styled_table(
                doc,
                ["CAD Katmanı (Layer)", "Fonksiyonel Açıklama", "Ölçülen Uzunluk (m)", "Doğrulama & Kaynak"],
                layer_rows,
                status_col_idx=3
            )

            # 3.2 Saha Ekipman / Priz / Armatür Blok Sayımı
            if self.data.metro_device_counts:
                p_dev = doc.add_paragraph()
                p_dev.paragraph_format.space_before = Pt(6)
                p_dev.paragraph_format.space_after = Pt(2)
                dev_str = "  |  ".join(f"{k}: {v} Adet" for k, v in self.data.metro_device_counts.items())
                r_dev = p_dev.add_run(f"▸ CAD Saha Ekipman & Armatür Blok Sayımı (INSERT): {dev_str}")
                r_dev.bold = True
                r_dev.font.size = Pt(8.5)
                r_dev.font.color.rgb = self.COLOR_NAVY

            # 3.2b Armatür Güç Dağılımı (PS-16-001)
            if getattr(self.data, "metro_luminaire_wattages", None):
                p_lum = doc.add_paragraph()
                p_lum.paragraph_format.space_before = Pt(3)
                p_lum.paragraph_format.space_after = Pt(2)
                lum_str = "  |  ".join(f"{k}: {v} Adet" for k, v in self.data.metro_luminaire_wattages.items())
                r_lum = p_lum.add_run(f"▸ Kat Aydınlatma Armatür Güç Dağılımı: {lum_str}")
                r_lum.font.size = Pt(8.5)
                r_lum.font.color.rgb = self.COLOR_TEXT

            # 3.2c Priz Faz (L1 / L2 / L3) Dağılımı (PS-16-051)
            if getattr(self.data, "metro_socket_phases", None):
                p_sk = doc.add_paragraph()
                p_sk.paragraph_format.space_before = Pt(3)
                p_sk.paragraph_format.space_after = Pt(2)
                sk_parts = [f"{pn} -> L1:{d['L1 (R)']}, L2:{d['L2 (S)']}, L3:{d['L3 (T)']} Priz" for pn, d in self.data.metro_socket_phases.items()]
                r_sk = p_sk.add_run(f"▸ Priz Faz Dağılımı (L1/L2/L3 Etiketlerinden): {'  |  '.join(sk_parts)}")
                r_sk.bold = True
                r_sk.font.size = Pt(8.5)
                r_sk.font.color.rgb = self.COLOR_NAVY

            # 3.2d Mekanik / Ekipman Yük Etiketleri (PS-11)
            if getattr(self.data, "metro_eq_loads", None):
                p_eq = doc.add_paragraph()
                p_eq.paragraph_format.space_before = Pt(3)
                p_eq.paragraph_format.space_after = Pt(2)
                tot_eq_kw = sum(x["power_kw"] for x in self.data.metro_eq_loads)
                eq_sample = ", ".join(f"{x['tag']} ({x['power_kw']:.2f}kW)" for x in self.data.metro_eq_loads[:10])
                r_eq = p_eq.add_run(f"▸ Mekanik / Cihaz Güç Etiketleri ({len(self.data.metro_eq_loads)} Cihaz, Toplam {tot_eq_kw:.2f} kW): {eq_sample}")
                r_eq.font.size = Pt(8.5)

            # 3.2e OG / DC Metraj Tablosu (PS-08)
            if getattr(self.data, "metro_mv_dc_cables", None):
                p_mv = doc.add_paragraph()
                p_mv.paragraph_format.space_before = Pt(4)
                p_mv.paragraph_format.space_after = Pt(2)
                r_mv = p_mv.add_run("▸ İstasyon İçi 34.5 kV OG ve 1500V DC Cer Gücü Kablo Metraj Tablosu (PS-08):")
                r_mv.bold = True
                r_mv.font.size = Pt(8.5)
                r_mv.font.color.rgb = self.COLOR_NAVY
                mv_rows = [[r["equipment"], r["cable_sec"], r["cable_type"], f"{r['length_m']:.0f} m", "✓ OG/DC METRAJ"] for r in self.data.metro_mv_dc_cables]
                self._add_styled_table(doc, ["Beslenen Ekipman / Hücre", "Kablo Kesiti", "İzolasyon / Gerilim", "Uzunluk", "Durum"], mv_rows, status_col_idx=4)

            # 3.2f Borulama / HDPE Rezervasyon Özeti (GN-14)
            if getattr(self.data, "metro_conduit_summary", None):
                p_cn = doc.add_paragraph()
                p_cn.paragraph_format.space_before = Pt(4)
                p_cn.paragraph_format.space_after = Pt(2)
                r_cn = p_cn.add_run(f"▸ Döşeme Altı / Duvar İçi HDPE Kablo Borulama Notları (GN-14): {' | '.join(self.data.metro_conduit_summary[:10])}")
                r_cn.font.size = Pt(8.0)

            # 3.3 Plan BS Etiketi vs Metraj Tablosu Kesit Çelişkileri (Varsa)
            if self.data.metro_sec_mismatches:
                p_mm = doc.add_paragraph()
                p_mm.paragraph_format.space_before = Pt(8)
                p_mm.paragraph_format.space_after = Pt(3)
                r_mm = p_mm.add_run(
                    f"⚠ KRİTİK BULGU: Kat Planı (BS Kablo Etiketi) ile Paftadaki Metraj Tablosu Arasında Kesit Çelişkisi Tespit Edilen Linyeler ({len(self.data.metro_sec_mismatches)} Adet):"
                )
                r_mm.bold = True
                r_mm.font.size = Pt(9.0)
                r_mm.font.color.rgb = self.COLOR_DANGER

                mm_rows = [
                    [m["line_no"], m["bs_code"], m["plan_cable"], m["table_cable"], m["length_m"], "✗ KESİT ÇELİŞKİSİ"]
                    for m in self.data.metro_sec_mismatches[:25]
                ]
                self._add_styled_table(
                    doc,
                    ["Linye No", "Plan BS Kodu (Pano/Hedef)", "Planda Yazan Kablo", "Tabloda Yazan Kablo", "Tablo Boyu", "Denetim Kararı"],
                    mm_rows,
                    status_col_idx=5
                )

        # ── BÖLÜM 4: KISA DEVRE (IEC 60909) VE TERMİK DAYANIM (I²t <= k²S²) ──
        self._add_section_header(doc, str(sec_no), "IEC 60909 KISA DEVRE VE TS HD 60364-4-43 TERMİK DAYANIM DENETİMİ")
        sec_no += 1

        headers_sc = [
            "Pano Kodu", "Kablo & Mesafe", "Ztop (Ω)", "Ik3 Max (kA)", "Ik1 Min (kA)",
            "Şalter Icn (kA)", "Kesme Kapasitesi", "Min Termik S (mm²)", "Termik Dayanım"
        ]
        rows_sc = []
        for pname, sc in self.report.short_circuit_results.items():
            rows_sc.append([
                sc.panel_name,
                f"{sc.cable_spec} ({sc.length_m:.0f}m)",
                f"{sc.z_total_ohm:.4f}",
                f"{sc.ik3_max_ka:.2f}",
                f"{sc.ik1_min_ka:.2f}",
                f"{sc.breaker_icn_ka:.0f} kA",
                sc.breaking_capacity_status,
                f"{sc.s_min_thermal_mm2:.2f}",
                sc.thermal_endurance_status,
            ])
        self._add_styled_table(doc, headers_sc, rows_sc, status_col_idx=6)

        # ── BÖLÜM 5: MÜHENDİSLİK DENETİM BULGULARI VE REVİZYON TALİMATLARI ───
        self._add_section_header(doc, str(sec_no), "MÜHENDİSLİK VE CAD DENETİM BULGULARI — KESİN DÜZELTME TALİMATLARI")

        headers_f = ["Durum", "Kategori", "İlgili Pano / Eleman", "Tespit Edilen Mühendislik Bulgusu & Standart", "Önerilen Düzeltme / Revizyon Talimatı"]
        rows_f = []

        # Önce FAIL ve WARNING bulgularını, ardından PASS/INFO bulgularını sırala
        sorted_findings = sorted(
            self.report.findings,
            key=lambda x: 0 if x.status == "FAIL" else (1 if x.status == "WARNING" else 2)
        )
        for f in sorted_findings:
            badge = "✗ HATA" if f.status == "FAIL" else ("⚠ UYARI" if f.status == "WARNING" else "✓ UYGUN")
            rows_f.append([
                badge,
                f.category,
                f.panel_name,
                f"{f.title}\n{f.detail}",
                f.recommendation or "Mevcut tasarım standarda uygundur."
            ])

        # CAD Hijyen ve Çizim Kalitesi bulgularını da ekle
        if self.data.cad_audit and self.data.cad_audit.findings:
            for cf in self.data.cad_audit.findings:
                badge = "✗ KRİTİK" if cf.severity == "KRİTİK" else ("⚠ UYARI" if cf.severity == "UYARI" else "ℹ BİLGİ")
                rows_f.append([
                    badge,
                    f"CAD / {cf.category}",
                    cf.element,
                    f"{cf.issue}\nEtki: {cf.impact}",
                    cf.correction
                ])

        self._add_styled_table(doc, headers_f, rows_f, status_col_idx=0)

        fname = self.custom_filename or f"Kuvvetli_Akim_Muhendislik_Raporu_{self.slug}.docx"
        out_path = self.output_dir / fname
        doc.save(str(out_path))
        return out_path
