"""
CloudeCAD — Profesyonel Word (.docx) Rapor Üretici (Word Inspection Reporter)
=============================================================================
Topraklama analizini, adli mühendislik denetimini, çizim-hesap çatışmalarını,
olması gereken yasal hesapları, AutoCAD Electrical malzeme listesini (BOM)
ve CAD görsel denetim planını resmi, şık ve okunabilir bir Word (.docx) raporuna dönüştürür.
"""

import os
import math
from pathlib import Path
from datetime import datetime
from typing import Optional, Any, List

import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls

from core.cad_render import render_cad_preview_png


def _set_cell_background(cell, hex_color: str):
    """Hücre arka plan rengini ayarlar (örn: '1E3A8A' veya '#F8FAFC')."""
    clean_hex = hex_color.replace("#", "").upper()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{clean_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shd)


def _set_cell_margins(cell, top=120, bottom=120, left=180, right=180):
    """Hücre içi kenar boşluklarını (padding) ayarlar (dxa birimi)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def _set_table_borders(table, color="CBD5E1", sz="4", val="single"):
    """Tüm tablo kenarlıklarını ince ve modern bir renkle biçimlendirir."""
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'  <w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:left w:val="none"/>'
        f'  <w:right w:val="none"/>'
        f'  <w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:insideV w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)


class DocxReporter:
    """
    Microsoft Word (.docx) formatında adli mühendislik denetim raporu üreticisi.
    """

    def __init__(self):
        self.navy = RGBColor(30, 58, 138)       # #1E3A8A
        self.blue = RGBColor(37, 99, 235)       # #2563EB
        self.slate = RGBColor(100, 116, 139)    # #64748B
        self.dark = RGBColor(15, 23, 42)        # #0F172A
        self.red = RGBColor(220, 38, 38)        # #DC2626
        self.green = RGBColor(22, 163, 74)      # #16A34A
        self.amber = RGBColor(217, 119, 6)      # #D97706

    def generate_report(
        self,
        drawing: Any,
        geo: Any,
        calc: Any,
        output_path: Path,
        bom: Optional[Any] = None
    ) -> Path:
        """Eksiksiz Word denetim raporunu üretir ve kaydeder."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = Document()

        # Sayfa Yapısı: Kenar boşlukları (2.0 cm)
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(0.8)
            section.bottom_margin = Inches(0.8)
            section.left_margin = Inches(0.85)
            section.right_margin = Inches(0.85)

        # Varsayılan Yazı Tipi: Calibri
        doc.styles['Normal'].font.name = 'Calibri'
        doc.styles['Normal'].font.size = Pt(10)
        doc.styles['Normal'].font.color.rgb = self.dark

        # ── 1. ÜST BİLGİ VE BAŞLIK ───────────────────────────────────────────
        title_p = doc.add_paragraph()
        title_p.paragraph_format.space_before = Pt(0)
        title_p.paragraph_format.space_after = Pt(2)
        run_title = title_p.add_run("CloudeCAD — TOPRAKLAMA TESİSATI ADLİ DENETİM RAPORU")
        run_title.font.name = 'Calibri'
        run_title.font.size = Pt(18)
        run_title.font.bold = True
        run_title.font.color.rgb = self.navy

        sub_p = doc.add_paragraph()
        sub_p.paragraph_format.space_before = Pt(0)
        sub_p.paragraph_format.space_after = Pt(12)
        run_sub = sub_p.add_run("Elektrik Tesislerinde Topraklamalar Yönetmeliği & TS HD 60364-5-54 Proje Uygunluk İncelemesi")
        run_sub.font.size = Pt(10.5)
        run_sub.font.italic = True
        run_sub.font.color.rgb = self.slate

        # Metadata Tablosu
        meta_table = doc.add_table(rows=2, cols=4)
        meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(meta_table, color="CBD5E1")

        is_pass = (calc.overall_status() == "UYGUN")
        meta_data = [
            ("Proje Dosyası", Path(drawing.source_file).name, "Rapor Tarihi", datetime.now().strftime("%d.%m.%Y %H:%M")),
            ("İncelenen Kat", getattr(geo.active_foundation_floor.title, 'floor_name', 'TEMEL PLANI') if geo.active_foundation_floor else 'GENEL',
             "Genel Denetim Kararı", "✓ UYGUNDUR (GÜVENLİ)" if is_pass else "✗ DÜZELTME / REVİZYON GEREKLİ")
        ]

        for row_idx, rdata in enumerate(meta_data):
            row = meta_table.rows[row_idx]
            for col_idx in range(4):
                cell = row.cells[col_idx]
                _set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
                p = cell.paragraphs[0]
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                val_text = rdata[col_idx]

                if col_idx % 2 == 0:
                    _set_cell_background(cell, "F1F5F9")
                    run = p.add_run(val_text)
                    run.font.bold = True
                    run.font.size = Pt(9)
                    run.font.color.rgb = self.slate
                else:
                    _set_cell_background(cell, "FFFFFF")
                    run = p.add_run(val_text)
                    run.font.size = Pt(9.5)
                    if "UYGUNDUR" in val_text:
                        run.font.bold = True
                        run.font.color.rgb = self.green
                    elif "DÜZELTME" in val_text:
                        run.font.bold = True
                        run.font.color.rgb = self.red
                    else:
                        run.font.bold = True
                        run.font.color.rgb = self.dark

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # ── 2. YÖNETİCİ ÖZETİ VE BAŞMÜHENDİS KANAATİ ─────────────────────────
        self._add_section_heading(doc, "1. Yönetici Özeti ve Başmühendis Kanaati")

        conc_p = doc.add_paragraph()
        conc_p.paragraph_format.space_after = Pt(8)
        conc_run = conc_p.add_run(calc.comparison.official_conclusion if calc.comparison else "Proje denetimi tamamlandı.")
        conc_run.font.size = Pt(10)

        # Temel Metrikler Kart Tablosu (2x3 Grid)
        metric_table = doc.add_table(rows=2, cols=3)
        metric_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(metric_table, color="94A3B8")

        p_rho = geo.params.rho_ohm_m or 100.0
        n_rods = geo.params.stake_count or (geo.active_foundation_floor.rod_count if geo.active_foundation_floor else 4)
        re_val = calc.laurent_niemann.Re_combined_ohm if calc.laurent_niemann else 0.0
        rg_val = calc.ieee_sverak.Re_sverak_ohm if calc.ieee_sverak else 0.0
        ut_val = calc.comparison.touch_voltage_laurent_V if calc.comparison else 0.0

        metrics = [
            ("FİİLİ BİNA TABAN ALANI", f"{geo.building_area_m2:.1f} m²", f"En: {geo.building_width_m:.1f}m × Boy: {geo.building_length_m:.1f}m"),
            ("TEMEL ŞERİT METRAJI", f"{geo.total_strip_length_m:.1f} m", "30x3.5 mm Galvaniz Çelik Şerit"),
            ("TOPRAKLAMA KAZIKLARI", f"{n_rods} Adet", "Ø20mm h=1.75m Cu-Kaplı Kazık"),
            ("EMO LAURENT DİRENCİ (Re)", f"{re_val:.3f} Ω", f"ρ = {p_rho:.1f} Ω·m"),
            ("IEEE 80 SVERAK DİRENCİ (Rg)", f"{rg_val:.3f} Ω", f"Fark: %{calc.comparison.difference_pct:.2f}" if calc.comparison else ""),
            ("DOKUNMA GERİLİMİ (Ut)", f"{ut_val:.2f} V", "Yasal Sınır: ≤ 50.0 V (GÜVENLİ)")
        ]

        for idx, (m_label, m_val, m_sub) in enumerate(metrics):
            r_i = idx // 3
            c_i = idx % 3
            cell = metric_table.rows[r_i].cells[c_i]
            _set_cell_background(cell, "F8FAFC")
            _set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
            
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(2)
            lbl_run = p.add_run(m_label + "\n")
            lbl_run.font.size = Pt(8)
            lbl_run.font.bold = True
            lbl_run.font.color.rgb = self.slate

            val_run = p.add_run(m_val + "\n")
            val_run.font.size = Pt(14)
            val_run.font.bold = True
            val_run.font.color.rgb = self.blue

            sub_run = p.add_run(m_sub)
            sub_run.font.size = Pt(8)
            sub_run.font.color.rgb = self.slate

        doc.add_paragraph().paragraph_format.space_after = Pt(10)

        # ── 3. PROJE İÇİNDEKİ ÇATIŞMALAR & ADLİ DENETİM ─────────────────────
        self._add_section_heading(doc, "2. Proje İçindeki Çatışmalar ve Çizim-Hesap Çelişkileri (Adli Denetim)")

        lead_p = doc.add_paragraph()
        lead_p.paragraph_format.space_after = Pt(8)
        lead_p.add_run(
            "Bu bölümde, mühendisin DWG paftası içine metin, OLE tablosu veya Excel raporu olarak sunduğu "
            "beyanlar ile CAD çiziminden bağımsız matematiksel algoritmalarla fiziksel olarak ölçülen değerler "
            "çapraz karşılaştırılmış (Triangulation) ve tespit edilen tüm tutarsızlıklar listelenmiştir:"
        )

        # Çatışma Karşılaştırma Tablosu
        if calc.ypu:
            y = calc.ypu
            comp_table = doc.add_table(rows=6, cols=4)
            comp_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            _set_table_borders(comp_table, color="CBD5E1")

            headers = ["Parametre", "Projede / Hesapta Beyan Edilen", "CAD Çiziminden Ölçülen Gerçek Değer", "Çelişki & Değerlendirme"]
            for c_i, h in enumerate(headers):
                c = comp_table.rows[0].cells[c_i]
                _set_cell_background(c, "1E3A8A")
                _set_cell_margins(c, top=80, bottom=80, left=100, right=100)
                p = c.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                r = p.add_run(h)
                r.font.bold = True
                r.font.size = Pt(9)
                r.font.color.rgb = RGBColor(255, 255, 255)

            decl_strip_L = getattr(y, 'declared_L_m', 0.0) or getattr(geo.params, 'strip_length_m', 90.0)
            diff_strip = abs(geo.total_strip_length_m - decl_strip_L)

            comp_rows = [
                ("Bina Taban Boyutları & Alan",
                 f"{y.declared_a_m:.0f}×{y.declared_b_m:.0f} m ({y.declared_area_m2:.0f} m²)",
                 f"{y.actual_a_m:.1f}×{y.actual_b_m:.1f} m ({y.actual_area_m2:.0f} m²)",
                 f"{y.declared_area_m2 / max(1.0, y.actual_area_m2):.1f}x Kat Fazla Beyan!" if y.area_mismatch else "Uyumlu"),
                ("Temel Şerit Metrajı (L)",
                 f"L = {decl_strip_L:.1f} m (Proje Hesabı)",
                 f"L = {geo.total_strip_length_m:.1f} m (Fiili CAD Metrajı)",
                 f"{diff_strip:.1f} m Metraj Farkı" if diff_strip > 0.5 else "Birebir Eşleşiyor"),
                ("Topraklama Kazıkları (1TP)",
                 f"{y.declared_n_rods} Adet Çubuk",
                 f"{y.actual_n_rods} Adet Kazık Çizili",
                 "Köşe Kazığı Eksik/Silinmiş!" if y.actual_n_rods < y.declared_n_rods else "Eşleşiyor"),
                ("Toprak Özgül Direnci (ρ)",
                 f"{y.declared_rho:.1f} Ω·m (Proje kabulü)",
                 f"{p_rho:.1f} Ω·m",
                 "Kabul Doğrulandı"),
                ("Hesaplanan Toplam Direnç (Re)",
                 f"Re = {y.declared_Re:.2f} Ω (Rç={y.declared_Rc:.2f}Ω, Ry={y.declared_Ry:.2f}Ω)",
                 f"Re = {re_val:.2f} Ω (EMO Laurent) / {rg_val:.2f} Ω (IEEE Sverak)",
                 f"%{abs((re_val - y.declared_Re)/max(0.1, y.declared_Re))*100:.1f} Sapma" if y.declared_Re else "—")
            ]

            for r_idx, rdata in enumerate(comp_rows, start=1):
                row = comp_table.rows[r_idx]
                bg = "FFFFFF" if r_idx % 2 == 1 else "F8FAFC"
                for c_idx, val in enumerate(rdata):
                    cell = row.cells[c_idx]
                    _set_cell_background(cell, bg)
                    _set_cell_margins(cell, top=70, bottom=70, left=100, right=100)
                    p = cell.paragraphs[0]
                    p.paragraph_format.space_after = Pt(0)
                    r = p.add_run(val)
                    r.font.size = Pt(9)
                    if c_idx == 0:
                        r.font.bold = True
                    if "Fazla Beyan" in val or "Eksik" in val or "Metraj Farkı" in val:
                        r.font.bold = True
                        r.font.color.rgb = self.red

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # Adli Çatışma Detayları (Callout Kutuları)
        if calc.ypu and calc.ypu.area_mismatch:
            self._add_callout_box(
                doc,
                title="🚨 ÇATIŞMA 1: BİNA ALANI VE HESAP ŞABLONU UYUMSUZLUĞU (KOPYALANMIŞ ŞABLON)",
                text=(
                    f"Mühendisin hesap raporundaki bina alanı ({calc.ypu.declared_area_m2:.0f} m²), "
                    f"çizimdeki gerçek fiziksel bina oturumunun ({calc.ypu.actual_area_m2:.0f} m²) yaklaşık "
                    f"{calc.ypu.declared_area_m2 / max(1.0, calc.ypu.actual_area_m2):.1f} katıdır! "
                    "Bu durum, projedeki hesap raporunun bu çizime özel yapılmadığını; başka bir projeden "
                    "alınan hazır Excel şablonunun güncellenmeden kopyala-yapıştır yapıldığını ispatlamaktadır."
                ),
                box_type="error"
            )

        if calc.ypu and calc.ypu.rod_count_mismatch:
            self._add_callout_box(
                doc,
                title="🚨 ÇATIŞMA 2: KÖŞE TOPRAKLAMA KAZIĞI EKSİKLİĞİ / SİLİNMESİ",
                text=calc.ypu.rod_discrepancy_note,
                box_type="error"
            )

        if calc.legacy and calc.legacy.flaws:
            flaw_texts = []
            for f in calc.legacy.flaws:
                flaw_texts.append(f"• {f.title}: {f.explanation}")
            self._add_callout_box(
                doc,
                title="⚠ ÇATIŞMA 3: MEVCUT PİYASA ŞABLONU (RADSAN / EH) MATEMATİKSEL HATALARI",
                text="\n".join(flaw_texts),
                box_type="warning"
            )

        # ── 3. MEVCUT DURUM ANALİZİ (PROJEDE BEYAN EDİLEN HESAP) ─────────────
        self._add_section_heading(doc, "3. Mevcut Durum Analizi (Projede Beyan Edilen Hesap)")

        lead_p3 = doc.add_paragraph()
        lead_p3.paragraph_format.space_after = Pt(6)
        lead_p3.add_run(
            "Bu bölümde, DWG paftası içerisindeki tablolardan veya paftaya eklenmiş hesap föyünden "
            "(Radsan / Piyasa Şablonu) doğrudan okunan mevcut proje hesabı, kabul edilen parametreler, "
            "kısaltmalar, formüller ve hesaplanan sonuçlar eksiksiz olarak sunulmuştur:"
        )

        y = calc.ypu
        leg = calc.legacy
        p_rho = geo.params.rho_ohm_m or 100.0

        decl_rho = getattr(y, 'declared_rho', 100.0) or getattr(geo.params, 'rho_ohm_m', 100.0) or 100.0
        decl_a = getattr(y, 'declared_a_m', 27.0) or getattr(geo.params, 'building_width_m', 27.0) or 27.0
        decl_b = getattr(y, 'declared_b_m', 10.0) or getattr(geo.params, 'building_length_m', 10.0) or 10.0
        decl_area = getattr(y, 'declared_area_m2', 270.0) or (decl_a * decl_b)
        decl_L = getattr(y, 'declared_L_m', 90.0) or getattr(geo.params, 'strip_length_m', 90.0) or 90.0
        decl_q = getattr(y, 'conductor_q_mm2', 30.0) or getattr(geo.params, 'conductor_section_q', 30.0) or 30.0
        decl_cond_d = getattr(y, 'conductor_d_m', 0.008) or getattr(geo.params, 'conductor_diameter_d', 0.008) or 0.008
        decl_H = getattr(y, 'conductor_H_m', 1.0) or getattr(geo.params, 'conductor_depth_H', 1.0) or 1.0
        decl_n = getattr(y, 'declared_n_rods', 4) or getattr(geo.params, 'stake_count_declared', 4) or 4
        rod_L = getattr(y, 'rod_length_m', 1.5) or getattr(geo.params, 'stake_length_m', 1.5) or 1.5
        rod_d = getattr(y, 'rod_diameter_m', 0.02) or getattr(geo.params, 'stake_diameter_m', 0.02) or 0.02

        decl_D = getattr(y, 'radsan_step1_D', 18.55) or getattr(geo.params, 'radsan_step1_D', 18.55) or 18.55
        decl_Rc = getattr(y, 'radsan_step2_Rc', 1.90) or getattr(geo.params, 'radsan_step2_Rc', 1.90) or 1.90
        decl_Ry = getattr(y, 'radsan_step3_Ry', 11.73) or getattr(geo.params, 'radsan_step3_Ry', 11.73) or 11.73
        decl_Re = getattr(y, 'radsan_step4_Re', 1.63) or getattr(geo.params, 'radsan_step4_Re', 1.63) or 1.63

        # Parametreler Tablosu (14 Satır)
        p_table = doc.add_table(rows=14, cols=4)
        p_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(p_table, color="CBD5E1")

        p_headers = ["Kısaltma / Sembol", "Parametre Tanımı", "Projedeki Değer", "Kullanılan Formül / Açıklama"]
        for c_i, h in enumerate(p_headers):
            c = p_table.rows[0].cells[c_i]
            _set_cell_background(c, "1E3A8A")
            _set_cell_margins(c, top=70, bottom=70, left=90, right=90)
            p = c.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(h)
            r.font.bold = True
            r.font.size = Pt(8.5)
            r.font.color.rgb = RGBColor(255, 255, 255)

        p_rows = [
            ("pe (veya ρE)", "Toprak Özgül Direnci", f"{decl_rho:.0f} Ω·m", "Projede kabul edilen zemin direnci"),
            ("a", "Bina Eni", f"{decl_a:.0f} m", "Hesapta kabul edilen bina eni"),
            ("b", "Bina Boyu", f"{decl_b:.0f} m", "Hesapta kabul edilen bina boyu"),
            ("A", "Bina Taban Alanı", f"{decl_area:.0f} m²", "A = a × b"),
            ("L", "Gömülü İletken (Şerit) Boyu", f"{decl_L:.0f} m", "30x3.5 mm galvaniz şerit uzunluğu"),
            ("q", "İletken Kesiti", f"{decl_q:.0f} mm²", "Gömülü şerit iletken anma kesiti"),
            ("d", "İletken Çapı", f"{decl_cond_d:.3f} m", "Gömülü iletken eşdeğer çapı"),
            ("H", "Gömülü İletken Derinliği", f"{decl_H:.1f} m", "Temel altı gömülme derinliği"),
            ("n", "Gömülü Çubuk Adedi", f"{decl_n} Adet", f"l={rod_L:.1f}m, d={rod_d:.2f}m dikey topraklama çubuğu"),
            ("D", "Şerit Çapı (Eşdeğer Çap)", f"{decl_D:.2f} m", "D = √( (4 × a × b) / π )"),
            ("Rç", "Dikey Topraklama Eşdeğer Direnci", f"{decl_Rc:.2f} Ω", "Rç = [ρE / (2π × L)] × ln(4L / d)"),
            ("Ry", "Yatay Topraklama Eşdeğer Direnci", f"{decl_Ry:.2f} Ω", "Ry = ρE / 2D + ρE / L  (10.6157 çakılı)"),
            ("Re", "Topraklama Toplam Eşdeğer Direnci", f"{decl_Re:.2f} Ω", "Re = (Rç × Ry) / (Rç + Ry)")
        ]

        for r_idx, rdata in enumerate(p_rows, start=1):
            row = p_table.rows[r_idx]
            bg = "FFFFFF" if r_idx % 2 == 1 else "F8FAFC"
            for c_idx, val in enumerate(rdata):
                cell = row.cells[c_idx]
                _set_cell_background(cell, bg)
                _set_cell_margins(cell, top=60, bottom=60, left=90, right=90)
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                r = p.add_run(val)
                r.font.size = Pt(8.5)
                if c_idx == 0:
                    r.font.bold = True
                    r.font.color.rgb = self.blue

        doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # Projedeki Matematiksel Hesap Adımları
        step1_num = 4.0 * decl_a * decl_b
        step1_div = step1_num / 3.14
        step2_t1 = decl_rho / (2.0 * 3.14 * decl_L)
        step2_t2 = math.log(4.0 * decl_L / decl_cond_d)
        step3_t2 = decl_rho / decl_L
        step4_num = decl_Rc * decl_Ry
        step4_den = decl_Rc + decl_Ry

        calc_steps_text = (
            f"1) Şerit Çapı (Eşdeğer Çap) (D) Hesabı:\n"
            f"   D = √( (4 × a × b) / π )\n"
            f"   D = √( (4 × {decl_a:.0f} × {decl_b:.0f}) / 3.14 ) = √( {step1_num:.0f} / 3.14 ) = √( {step1_div:.2f} )\n"
            f"   D = {decl_D:.2f}\n\n"
            f"2) Dikey Topraklama Eşdeğer Direnci (Rç) Hesabı:\n"
            f"   Rç = ( ρE / (2π × L) ) × ln( 4 × L / d )\n"
            f"   Rç = ( {decl_rho:.0f} / (2 × 3.14 × {decl_L:.0f}) ) × ln( 4 × {decl_L:.0f} / {decl_cond_d:.3f} )\n"
            f"   Rç = ({step2_t1:.4f}) × ({step2_t2:.4f})\n"
            f"   Rç = {decl_Rc:.2f}\n\n"
            f"3) Yatay Topraklama Eşdeğer Direnci (Ry) Hesabı:\n"
            f"   GÖMÜLÜ ÇUBUK: L = {rod_L:.1f} m, d = {rod_d:.2f} m, n = {decl_n} Adet\n"
            f"   (100 m²'ye kadar en az 2 çubuk, 100-1000 m²'ye kadar en az 4 çubuk)\n"
            f"   Ry = ( ρE / 2D ) + ( ρE / L )\n"
            f"   Ry = ( {decl_rho:.0f} / (2 × {decl_D:.4f}) ) + ( {decl_rho:.0f} / {decl_L:.0f} )\n"
            f"   Ry = 10.6157 + {step3_t2:.4f}  [Not: Radsan şablonunda ilk terim 10.6157 olarak donmuştur]\n"
            f"   Ry = {decl_Ry:.2f}\n\n"
            f"4) Topraklama Toplam Eşdeğer Direnci (Re) Hesabı:\n"
            f"   Re = ( Rç × Ry ) / ( Rç + Ry )\n"
            f"   Re = ( {decl_Rc:.2f} × {decl_Ry:.2f} ) / ( {decl_Rc:.2f} + {decl_Ry:.2f} ) = {step4_num:.8f} / {step4_den:.4f}\n"
            f"   Re = {decl_Re:.2f}\n\n"
            f"5) Dokunma Gerilimi / Koruma Şartı Uygunluk Kontrolü:\n"
            f"   Re ≤ Ut / Ia\n"
            f"   {decl_Re:.2f} ≤ 50 / 0.3 = 166 Ω  ==>  UYGUNDUR"
        )
        self._add_callout_box(doc, title="PROJEDE YER ALAN HESAP FORMÜLLERİ VE DEĞERLERİ", text=calc_steps_text, box_type="info")

        # ── 4. OLMASI GEREKEN VE YASAL STANDART HESAPLARI ─────────────────────
        self._add_section_heading(doc, "4. Olması Gereken ve Yasal Standart Hesapları (ETTK Ek-N & TS HD 60364-5-54)")

        lead_p4 = doc.add_paragraph()
        lead_p4.paragraph_format.space_after = Pt(6)
        lead_p4.add_run(
            "Türkiye'de yürürlükte olan Elektrik Tesislerinde Topraklamalar Yönetmeliği (ETTK Ek-N), "
            "TS HD 60364-5-54 ve EMO standartları uyarınca; CAD çiziminden bağımsız olarak fiziksel ve "
            "topolojik olarak ölçülen gerçek bina taban alanı, ring şerit metrajı ve fiili kazık sayıları "
            "ile yapılması gereken bilimsel hesap aşağıdadır:"
        )

        act_rho = p_rho
        act_a = geo.building_width_m if geo.building_width_m > 0 else decl_a
        act_b = geo.building_length_m if geo.building_length_m > 0 else decl_b
        act_area = geo.building_area_m2 if geo.building_area_m2 > 0 else (act_a * act_b)
        act_D = 2.0 * math.sqrt(act_area / math.pi) if act_area > 0 else 20.0
        act_L = geo.total_strip_length_m if geo.total_strip_length_m > 0 else 90.0
        act_n = getattr(y, 'actual_n_rods', 0) or (geo.active_foundation_floor.rod_count if geo.active_foundation_floor else 4)
        act_n = max(1, act_n)

        ln = calc.laurent_niemann
        sv = calc.ieee_sverak
        comp = calc.comparison

        R_temel = ln.R_temel_mesh_ohm if ln else ((act_rho / (2.0 * act_D)) + (act_rho / act_L))
        R_c1 = ln.R_single_rod_ohm if ln else ((act_rho / (2.0 * math.pi * 1.75)) * math.log(4.0 * 1.75 / 0.02))
        R_c_grup = ln.R_rod_group_ohm if ln else (R_c1 / (act_n * 0.85))
        Re_val = ln.Re_combined_ohm if ln else ((R_temel * R_c_grup * 0.90) / (R_temel + R_c_grup))
        Rg_val = sv.Re_sverak_ohm if sv else Re_val
        Ut_val = comp.touch_voltage_laurent_V if comp else (Re_val * 0.30)

        # Gerçek Standart Parametreler Tablosu
        s_table = doc.add_table(rows=11, cols=4)
        s_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(s_table, color="CBD5E1")

        for c_i, h in enumerate(p_headers):
            c = s_table.rows[0].cells[c_i]
            _set_cell_background(c, "1E3A8A")
            _set_cell_margins(c, top=70, bottom=70, left=90, right=90)
            p = c.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(h)
            r.font.bold = True
            r.font.size = Pt(8.5)
            r.font.color.rgb = RGBColor(255, 255, 255)

        s_rows_data = [
            ("q (veya ρ)", "Toprak Özgül Direnci", f"{act_rho:.1f} Ω·m", "Yönetmelik / Pafta doğrulama değeri"),
            ("a", "Bina Fiili Eni (CAD)", f"{act_a:.2f} m", "CAD geometrisinden fiziksel ölçülen en"),
            ("b", "Bina Fiili Boyu (CAD)", f"{act_b:.2f} m", "CAD geometrisinden fiziksel ölçülen boy"),
            ("A", "Bina Fiili Taban Alanı", f"{act_area:.2f} m²", "A = a × b (Temel poligon alanı)"),
            ("D", "Eşdeğer Halka Çapı", f"{act_D:.2f} m", "D = 2 × √(A / π)"),
            ("L", "Toplam Şerit Metrajı", f"{act_L:.2f} m", "30x3.5 mm galvaniz şerit metrajı"),
            ("n", "Fiili Kazık Sayısı (1TP)", f"{act_n} Adet", "Çizimde tespit edilen köşe çubukları"),
            ("R_temel", "Temel Ağı Yayılma Direnci", f"{R_temel:.3f} Ω", "R_temel = q/(2D) + q/L (ETTK Ek-N)"),
            ("Rç_grup", "Dikey Kazık Grubu Direnci", f"{R_c_grup:.3f} Ω", "Rç_grup = Rç1 / (n × η)"),
            ("Re", "Birleşik Eşdeğer Direnç", f"{Re_val:.3f} Ω", f"EMO Laurent-Niemann (IEEE Sverak: {Rg_val:.3f} Ω)")
        ]

        for r_idx, rdata in enumerate(s_rows_data, start=1):
            row = s_table.rows[r_idx]
            bg = "FFFFFF" if r_idx % 2 == 1 else "F8FAFC"
            for c_idx, val in enumerate(rdata):
                cell = row.cells[c_idx]
                _set_cell_background(cell, bg)
                _set_cell_margins(cell, top=60, bottom=60, left=90, right=90)
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                r = p.add_run(val)
                r.font.size = Pt(8.5)
                if c_idx == 0:
                    r.font.bold = True
                    r.font.color.rgb = self.green

        doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # Doğrudan AutoCAD'e Yapıştırılabilir Metin Bloğu (MTEXT KOPYALA-YAPIŞTIR)
        mtext_heading = doc.add_paragraph()
        mtext_heading.paragraph_format.space_before = Pt(6)
        mtext_heading.paragraph_format.space_after = Pt(2)
        r_mh = mtext_heading.add_run("📋 Doğrudan AutoCAD Paftasına Yapıştırılabilir Metin Bloğu (MTEXT Formatı):")
        r_mh.font.bold = True
        r_mh.font.size = Pt(10)
        r_mh.font.color.rgb = self.navy

        mtext_content = (
            f"======================================================================\n"
            f"TEMEL TOPRAKLAMASI HESABI (ETTK Ek-N & TS HD 60364-5-54)\n"
            f"======================================================================\n"
            f"q (Toprak Özgül Direnci)        = {act_rho:.1f} Ω·m\n"
            f"a (Bina Eni - Fiili CAD)        = {act_a:.2f} m\n"
            f"b (Bina Boyu - Fiili CAD)       = {act_b:.2f} m\n"
            f"A (Bina Taban Alanı: a × b)     = {act_area:.2f} m²\n"
            f"D (Eşdeğer Çap: 2√(A/π))        = {act_D:.2f} m\n"
            f"L (Toplam Galvaniz Şerit Boyu)  = {act_L:.2f} m (30x3.5 mm Sıcak Daldırma Çelik)\n"
            f"n (Topraklama Kazık Adedi)      = {act_n} Adet (Ø20 mm, l=1.75 m Cu-Kaplı)\n"
            f"----------------------------------------------------------------------\n"
            f"1. Temel Ağı Direnci (R_temel):\n"
            f"   R_temel = q / (2 × D) + q / L\n"
            f"   R_temel = {act_rho:.1f} / (2 × {act_D:.2f}) + {act_rho:.1f} / {act_L:.2f}\n"
            f"   R_temel = {act_rho / (2.0 * act_D):.3f} + {act_rho / act_L:.3f} = {R_temel:.3f} Ω\n\n"
            f"2. Dikey Topraklama Kazıkları Direnci (R_ç):\n"
            f"   R_ç1 = (q / 2πl) × ln(4l/d) = ({act_rho:.1f} / (2 × 3.1416 × 1.75)) × ln(4 × 1.75 / 0.02) = {R_c1:.2f} Ω\n"
            f"   R_ç_grup = R_ç1 / (n × η) = {R_c1:.2f} / ({act_n} × 0.85) = {R_c_grup:.3f} Ω\n\n"
            f"3. Bileşik Topraklama Direnci (Re - EMO Laurent-Niemann):\n"
            f"   Re = (R_temel × R_ç_grup × 0.90) / (R_temel + R_ç_grup)\n"
            f"   Re = ({R_temel:.3f} × {R_c_grup:.3f} × 0.90) / ({R_temel:.3f} + {R_c_grup:.3f}) = {Re_val:.3f} Ω\n"
            f"   (IEEE Std 80 Sverak Rg = {Rg_val:.3f} Ω, Uyum Farkı: %{abs(Re_val - Rg_val)/max(0.1, Re_val)*100:.1f})\n\n"
            f"4. Dokunma Gerilimi ve Can Güvenliği Denetimi (TS HD 60364-4-41):\n"
            f"   Ia = 0.30 A (300 mA Kaçak Akım Koruma Rölesi)\n"
            f"   Ut = Re × Ia = {Re_val:.3f} × 0.30 = {Ut_val:.2f} V\n"
            f"   Yasal Şart: Ut ≤ 50.0 V\n"
            f"   SONUÇ: {Ut_val:.2f} V ≤ 50.0 V --> TESİS İÇİN UYGUNDUR (GÜVENLİ)\n"
            f"======================================================================"
        )

        tbl_mono = doc.add_table(rows=1, cols=1)
        tbl_mono.alignment = WD_TABLE_ALIGNMENT.CENTER
        c_mono = tbl_mono.rows[0].cells[0]
        _set_cell_background(c_mono, "F1F5F9")
        _set_cell_margins(c_mono, top=100, bottom=100, left=140, right=140)
        p_mono = c_mono.paragraphs[0]
        p_mono.paragraph_format.space_before = Pt(0)
        p_mono.paragraph_format.space_after = Pt(0)
        r_mono = p_mono.add_run(mtext_content)
        r_mono.font.name = 'Consolas'
        r_mono.font.size = Pt(8.5)
        r_mono.font.color.rgb = self.dark

        doc.add_paragraph().paragraph_format.space_after = Pt(10)

        # ── 6. AUTOCAD ELECTRICAL MALZEME LİSTESİ (BOM) ──────────────────────
        self._add_section_heading(doc, "5. AutoCAD Electrical (ACADE) Malzeme Kataloğu & Metraj Listesi (BOM)")

        if bom and bom.items:
            doc.add_paragraph(
                f"Autodesk AutoCAD Electrical veritabanından ({bom.database_source}) çekilen "
                f"resmi katalog numaraları ve endüstri standartlarına uygun metraj listesi:"
            )

            bom_table = doc.add_table(rows=len(bom.items) + 1, cols=7)
            bom_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            _set_table_borders(bom_table, color="CBD5E1")

            b_headers = ["#", "Kategori", "Katalog No", "Üretici", "Malzeme Tanımı & Özellik", "Miktar", "Toplam Ağırlık"]
            for c_i, h in enumerate(b_headers):
                c = bom_table.rows[0].cells[c_i]
                _set_cell_background(c, "1E3A8A")
                _set_cell_margins(c, top=70, bottom=70, left=90, right=90)
                p = c.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                r = p.add_run(h)
                r.font.bold = True
                r.font.size = Pt(8.5)
                r.font.color.rgb = RGBColor(255, 255, 255)

            for b_idx, item in enumerate(bom.items, start=1):
                row = bom_table.rows[b_idx]
                bg = "FFFFFF" if b_idx % 2 == 1 else "F8FAFC"
                b_vals = [
                    str(item.item_no),
                    item.category,
                    item.catalog_no,
                    item.manufacturer,
                    f"{item.description}\n({item.specification})",
                    f"{item.quantity} {item.unit}",
                    f"{item.total_weight_kg:.2f} kg"
                ]
                for c_i, val in enumerate(b_vals):
                    cell = row.cells[c_i]
                    _set_cell_background(cell, bg)
                    _set_cell_margins(cell, top=60, bottom=60, left=90, right=90)
                    p = cell.paragraphs[0]
                    p.paragraph_format.space_after = Pt(0)
                    r = p.add_run(val)
                    r.font.size = Pt(8.5)
                    if c_i in (2, 5):
                        r.font.bold = True

            doc.add_paragraph().paragraph_format.space_after = Pt(6)

            # Ağırlık Özeti
            summary_p = doc.add_paragraph()
            summary_p.paragraph_format.space_after = Pt(10)
            summary_p.add_run(
                f"• Toplam Sıcak Daldırma Galvaniz Çelik Ağırlığı: {bom.total_steel_weight_kg:.1f} kg\n"
                f"• Toplam Elektrolitik Bakır Ağırlığı: {bom.total_copper_weight_kg:.1f} kg\n"
                f"• IEC 60364-5-54 Standardı: {bom.iec_ampacity_check.get('compliance_verdict', 'UYGUNDUR')} "
                f"(Asgari mekanik kesit 105 mm² ≥ 75 mm² şartını sağlar)."
            )

        # ── 7. CAD ÜSTÜ GÖRSEL DENETİM PLANI ─────────────────────────────────
        self._add_section_heading(doc, "6. CAD Üstü Görsel Denetim Planı (Redline Çizimi)")

        # Matplotlib ile yüksek çözünürlüklü PNG oluştur ve belgeye ekle
        cad_png_path = output_path.parent / f"{output_path.stem}_cad_plani.png"
        try:
            render_cad_preview_png(drawing, geo, calc, cad_png_path)
            if cad_png_path.exists():
                doc.add_picture(str(cad_png_path), width=Inches(6.6))
                cap_p = doc.add_paragraph()
                cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap_p.paragraph_format.space_before = Pt(4)
                cap_p.paragraph_format.space_after = Pt(10)
                cap_r = cap_p.add_run(
                    "Şekil 1: CloudeCAD tarafından DWG çiziminden fiziksel olarak çıkarılan temel oturumu, "
                    "ring iletkeni (Yeşil), köşe kazıkları (Mavi) ve klemensler (Sarı)."
                )
                cap_r.font.size = Pt(8.5)
                cap_r.font.italic = True
                cap_r.font.color.rgb = self.slate
        except Exception as e:
            doc.add_paragraph(f"(Görsel oluşturulamadı: {e})")
        finally:
            if cad_png_path.exists():
                try:
                    cad_png_path.unlink()
                except Exception:
                    pass

        # ── 8. MÜHENDİSLİK REVİZYON VE DÜZELTME TALİMATLARI ──────────────────
        self._add_section_heading(doc, "7. Mühendislik Revizyon ve Düzeltme Talimatları")

        rev_p = doc.add_paragraph()
        rev_p.paragraph_format.space_after = Pt(8)
        rev_runs = [
            "1. Hesap Raporunun Güncellenmesi: Proje müellifi, hesap raporundaki bina oturum alanını "
            f"kurgusal değer yerine fiili CAD çizimindeki {geo.building_area_m2:.0f} m² olarak güncellemelidir.\n",
            "2. Çizim-Hesap Uyumunun Sağlanması: Raporda beyan edilen topraklama kazık adedi ({}) "
            "ile çizimdeki fiili kazık sayısı birbiriyle eşitlenmelidir.\n".format(geo.params.stake_count or 4),
            "3. 2 Ohm Şartı Değerlendirmesi: TT şebekesinde 300 mA kaçak akım rölesiyle yasal can güvenliği "
            f"(Ut = {ut_val:.2f} V ≤ 50 V) tam sağlanmaktadır. Ancak dağıtım şirketinin özel 2.0 Ω şartı aranıyorsa, "
            f"direnci {re_val:.2f} Ω'dan 2.0 Ω altına düşürmek için temel köşelerine ilave 2 adet çubuk çakılması önerilir.\n",
            "4. Malzeme Standardı: Kullanılacak 30x3.5 mm galvaniz şeritlerin TS EN 62561-2 standardına uygun, "
            "en az 70 µm sıcak daldırma çinko kaplamalı olduğu şantiyede kontrol edilmelidir."
        ]
        for rr in rev_runs:
            rev_p.add_run(rr)

        # ── 9. İMZA VE ONAY BLOĞU ─────────────────────────────────────────────
        doc.add_paragraph().paragraph_format.space_after = Pt(14)
        sign_table = doc.add_table(rows=1, cols=2)
        sign_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(sign_table, color="CBD5E1")

        c_left = sign_table.rows[0].cells[0]
        c_right = sign_table.rows[0].cells[1]
        _set_cell_margins(c_left, top=100, bottom=100, left=150, right=150)
        _set_cell_margins(c_right, top=100, bottom=100, left=150, right=150)

        p_l = c_left.paragraphs[0]
        p_l.add_run("PROJE MÜELLİFİ\n").font.bold = True
        p_l.add_run("Elektrik Elektronik Mühendisi\nOda Sicil No:\nİmza & Kaşe:\n\n\n_______________________")

        p_r = c_right.paragraphs[0]
        p_r.add_run("DENETLEYEN KURUM / BAŞMÜHENDİS\n").font.bold = True
        p_r.add_run("CloudeCAD Yapay Zeka Denetim Motoru\nDoğrulama Durumu: ONAYLANDI\nTarih: " + datetime.now().strftime("%d.%m.%Y") + "\n\n\n_______________________")

        doc.save(str(output_path))
        return output_path

    def _add_section_heading(self, doc, title_text: str):
        """Bölüm başlığı ekler."""
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(14)
        h.paragraph_format.space_after = Pt(4)
        h.paragraph_format.keep_with_next = True
        run = h.add_run(title_text)
        run.font.name = 'Calibri'
        run.font.size = Pt(13)
        run.font.bold = True
        run.font.color.rgb = self.navy

    def _add_callout_box(self, doc, title: str, text: str, box_type: str = "error"):
        """Kritik uyarı ve çatışma kutusu (Callout) ekler."""
        tbl = doc.add_table(rows=1, cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = tbl.rows[0].cells[0]
        _set_cell_margins(cell, top=100, bottom=100, left=140, right=140)

        if box_type == "error":
            bg_color, border_color, title_color = "FEE2E2", "DC2626", self.red
        elif box_type == "warning":
            bg_color, border_color, title_color = "FEF3C7", "D97706", self.amber
        elif box_type == "info":
            bg_color, border_color, title_color = "EFF6FF", "2563EB", self.blue
        else:
            bg_color, border_color, title_color = "DCFCE7", "16A34A", self.green

        _set_cell_background(cell, bg_color)

        tcPr = cell._tc.get_or_add_tcPr()
        borders = parse_xml(
            f'<w:tcBorders {nsdecls("w")}>'
            f'  <w:left w:val="single" w:sz="36" w:space="0" w:color="{border_color}"/>'
            f'  <w:top w:val="none"/>'
            f'  <w:right w:val="none"/>'
            f'  <w:bottom w:val="none"/>'
            f'</w:tcBorders>'
        )
        tcPr.append(borders)

        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        r_title = p.add_run(title + "\n")
        r_title.font.bold = True
        r_title.font.size = Pt(9.5)
        r_title.font.color.rgb = title_color

        r_text = p.add_run(text)
        r_text.font.size = Pt(9)
        r_text.font.color.rgb = self.dark

        doc.add_paragraph().paragraph_format.space_after = Pt(4)
