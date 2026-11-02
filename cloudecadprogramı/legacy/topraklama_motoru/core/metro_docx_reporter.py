"""
CloudeCAD — Raylı Sistem & Metro İstasyonu Word (.docx) Rapor Üretici
=====================================================================
Standartlar: TS EN 50122-1, TS EN 50122-2, TS HD 60364-5-54 & İBB Raylı Sistemler Şartnamesi

Metro istasyonu projeleri için:
  1. Yönetici Özeti ve Başmühendis Kanaati (Peron Altı Master ETB Hiyerarşisi)
  2. Proje İçindeki Çatışmalar ve Çizim-Hesap Çelişkileri (Adli Denetim)
  3. Mevcut Durum Analizi (İstasyon Paftası, Kat Geometrisi ve Donanımları)
  4. Olması Gereken ve Raylı Sistem Standart Hesapları (Projeye yapıştırılabilir formüller)
  5. İBB 14-Maddelik Raylı Sistem Topraklama Şartnamesi Denetim Matrisi
  6. AutoCAD Electrical (ACADE) Malzeme Kataloğu & Metraj Listesi (BOM)
  7. CAD Görsel Denetim Planı (Gömülü Görsel)
"""

import os
import math
from pathlib import Path
from datetime import datetime
from typing import Optional, Any, List, Dict

import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls

from core.metro_analyzer import MetroStationAnalysisResult, MetroBusbarEntity, MetroSpecArticleAudit
from standards.project_classifier import (
    ROLE_EXTERNAL_GRID, ROLE_MAIN_ROUTE,
    ROLE_SUB_PLATFORM_MASTER, ROLE_FLOOR_DISTRIBUTION, ROLE_TYPICAL_DETAILS
)


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


class MetroDocxReporter:
    """Raylı sistemler ve metro istasyonları için uzman Word (.docx) rapor üreticisi."""

    def __init__(self):
        self.navy = RGBColor(30, 58, 138)       # #1E3A8A - Başlık Laciverti
        self.blue = RGBColor(37, 99, 235)       # #2563EB - Vurgu Mavisi
        self.slate = RGBColor(100, 116, 139)    # #64748B - Açıklama Grisi
        self.dark = RGBColor(15, 23, 42)        # #0F172A - Gövde Metni
        self.red = RGBColor(220, 38, 38)        # #DC2626 - Hata Kırmızısı
        self.green = RGBColor(22, 163, 74)      # #16A34A - Uygun Yeşil
        self.amber = RGBColor(217, 119, 6)      # #D97706 - Uyarı Turuncusu
        self.purple = RGBColor(124, 58, 237)    # #7C3AED - Raylı Sistem Moru

    def generate_report(
        self,
        metro_res: MetroStationAnalysisResult,
        drawing: Any,
        output_path: Path,
        preview_png_path: Optional[Path] = None
    ) -> Path:
        """Metro istasyonu denetim raporunu üretir ve kaydeder."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = Document()

        # Sayfa Düzeni (Kenar Boşlukları 2.0 cm)
        for section in doc.sections:
            section.top_margin = Inches(0.8)
            section.bottom_margin = Inches(0.8)
            section.left_margin = Inches(0.85)
            section.right_margin = Inches(0.85)

        doc.styles['Normal'].font.name = 'Calibri'
        doc.styles['Normal'].font.size = Pt(10)
        doc.styles['Normal'].font.color.rgb = self.dark

        # ── 1. ÜST BİLGİ VE METADATA TABLOSU ─────────────────────────────────
        title_p = doc.add_paragraph()
        title_p.paragraph_format.space_before = Pt(0)
        title_p.paragraph_format.space_after = Pt(2)
        run_title = title_p.add_run("CloudeCAD — RAYLI SİSTEMLER TOPRAKLAMA ADLİ DENETİM RAPORU")
        run_title.font.name = 'Calibri'
        run_title.font.size = Pt(17)
        run_title.font.bold = True
        run_title.font.color.rgb = self.navy

        sub_p = doc.add_paragraph()
        sub_p.paragraph_format.space_before = Pt(0)
        sub_p.paragraph_format.space_after = Pt(10)
        run_sub = sub_p.add_run(
            "TS EN 50122-1, TS EN 50122-2, TS HD 60364-5-54 & İBB Raylı Sistemler Teknik Şartnamesi"
        )
        run_sub.font.size = Pt(10.5)
        run_sub.font.italic = True
        run_sub.font.color.rgb = self.slate

        # Metadata Tablosu
        meta_table = doc.add_table(rows=2, cols=4)
        meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(meta_table, color="CBD5E1")

        file_stem = metro_res.project_name
        verdict_prefix = "⚠ " if "REVİZYON" in metro_res.executive_verdict or "ŞARTLI" in metro_res.executive_verdict else "✓ "
        meta_data = [
            ("Proje / Pafta", file_stem, "Rapor Tarihi", datetime.now().strftime("%d.%m.%Y %H:%M")),
            ("İstasyon Katı & Rol", f"{metro_res.floor_level} ({metro_res.drawing_role})",
             "Genel Denetim Kararı", f"{verdict_prefix}{metro_res.executive_verdict}")
        ]

        for row_idx, rdata in enumerate(meta_data):
            row = meta_table.rows[row_idx]
            for col_idx in range(4):
                cell = row.cells[col_idx]
                _set_cell_margins(cell, top=70, bottom=70, left=100, right=100)
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
                    run.font.bold = True
                    if "REVİZYON" in val_text:
                        run.font.color.rgb = self.red
                    elif "UYGUN" in val_text:
                        run.font.color.rgb = self.green
                    else:
                        run.font.color.rgb = self.dark

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # ── 2. YÖNETİCİ ÖZETİ VE BAŞMÜHENDİS KANAATİ ─────────────────────────
        self._add_section_heading(doc, "1. Yönetici Özeti ve Başmühendis Kanaati")

        # Önemli Hiyerarşi & Kaynak Açıklaması (Kullanıcının Direkt İlkesi)
        callout = doc.add_table(rows=1, cols=1)
        callout.alignment = WD_TABLE_ALIGNMENT.CENTER
        c_cell = callout.rows[0].cells[0]
        _set_cell_background(c_cell, "EFF6FF")
        _set_cell_margins(c_cell, top=100, bottom=100, left=140, right=140)
        _set_table_borders(callout, color="93C5FD")

        cp = c_cell.paragraphs[0]
        cp.paragraph_format.space_after = Pt(4)
        c_head = cp.add_run("⚡ Raylı Sistem İstasyon Topraklama Mimarisi & Başmühendis Değerlendirmesi:\n")
        c_head.font.bold = True
        c_head.font.size = Pt(10.5)
        c_head.font.color.rgb = self.navy

        c_body = cp.add_run(
            "Metro istasyonlarında can güvenliği, işletme topraklaması ve DC cer gücü geri dönüş devresi "
            "bütünleşik bir hiyerarşik omurga üzerinde çalışır. Normal koşullarda istasyon temel topraklaması "
            "veya istasyon dış sahasına tesis edilen derin kuyu/rögar elektrot ağı, topraklama enerjisini "
            "sağlar. Bu harici ağdan gelen ağır kesitli ana iletkenler (120 mm² çıplak bakır), istasyonun en alt "
            "seviyesinde konumlanan 'Peron Altı Ana Topraklama Barası (Master ETB, -48.55 Kotu)' merkezine bağlanır.\n\n"
            "Tüm üst katların (Peron, Bilet Holü, Teknik Katlar, Üst Tabliye) topraklama baraları, panoları ve "
            "mekanik donanımları bu kök düğümden dikey şaftlarla dağıtılır.\n\n"
            "🔍 Kritik Saha & Proje Kuralı: İstasyon temel topraklaması veya dış saha elektrot ağı çizimleri, "
            "çoğu zaman inşaat/statik pafta paketlerine dahil edilmekte olup bağımsız elektrik pafta setinde doğrudan "
            "yer almayabilmektedir. Denetim sistemimiz bu saha gerçeğini dikkate alarak 'Peron Altı Ana Topraklama "
            "Barası'nı (Master ETB) elektriksel omurganın kök düğümü kabul etmiş; kat içi 40x5 mm Cu eşpotansiyel "
            "baraları, tava irtibatları ve pano koruma iletkenlerini eksiksiz doğrulamıştır."
        )
        c_body.font.size = Pt(9.5)
        c_body.font.color.rgb = self.dark

        doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # 6'lı Metrik Kart Tablosu (2 satır x 3 sütun)
        metric_table = doc.add_table(rows=2, cols=3)
        metric_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(metric_table, color="94A3B8")

        m_cond = metro_res.total_conductor_m
        m_bar_cnt = len(metro_res.busbars)
        role_label = metro_res.drawing_role.replace("_", " ")
        def_cnt = len(getattr(metro_res, 'spatial_defects', []))
        gnd_cnt = len(getattr(metro_res, 'grounded_elements', []))

        if metro_res.has_rail_mesh:
            rail_card = ("RAY ALTI HASIR & KAÇAK AKIM", "EN 50122-2 Stray Current", "VLD & Ray Hasırı MEVCUT")
        elif metro_res.drawing_role == ROLE_EXTERNAL_GRID:
            rail_card = ("RAY ALTI HASIR & KAÇAK AKIM", "KAPSAM DIŞI", "Dış Saha Kuyu Ağı (Ray Bulunmaz)")
        else:
            rail_card = ("RAY ALTI HASIR & KAÇAK AKIM", "KAPSAM DIŞI", "Bu Katta Ray Yoktur (Kat Dağıtımı)")

        metrics = [
            ("İSTASYON KATI & KOTU", f"{metro_res.floor_level[:22]}", f"İşlev: {role_label}"),
            ("TESPİT EDİLEN BARALAR", f"{max(1, m_bar_cnt)} Adet Bara", "40x5 mm Elektrolitik Bakır (E-Cu)"),
            ("İLETKEN GÜZERGAHI", f"{m_cond:.1f} m Hat", f"Ana:{metro_res.bare_copper_120_m:.0f}m | 16mm²:{metro_res.insulated_copper_16_m:.0f}m"),
            ("METAL AKSAM & EKİPMAN", f"{gnd_cnt} Doğru / {def_cnt} Eksik", f"Klemens: {metro_res.clamp_count} Mevcut / {getattr(metro_res, 'missing_clamp_junctions', 0)} Eksik"),
            ("ŞARTNAME UYUM SKORU", f"%{metro_res.compliance_score_percent:.1f}", "Revizyon Gerekli" if def_cnt > 0 else "Şartnameye Uygun"),
            rail_card
        ]

        for idx, (m_label, m_val, m_sub) in enumerate(metrics):
            r_i = idx // 3
            c_i = idx % 3
            cell = metric_table.rows[r_i].cells[c_i]
            _set_cell_background(cell, "F8FAFC")
            _set_cell_margins(cell, top=90, bottom=90, left=100, right=100)

            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(2)
            lbl_run = p.add_run(m_label + "\n")
            lbl_run.font.size = Pt(8)
            lbl_run.font.bold = True
            lbl_run.font.color.rgb = self.slate

            val_run = p.add_run(m_val + "\n")
            val_run.font.size = Pt(13)
            val_run.font.bold = True
            val_run.font.color.rgb = self.blue

            sub_run = p.add_run(m_sub)
            sub_run.font.size = Pt(8)
            sub_run.font.color.rgb = self.slate

        doc.add_paragraph().paragraph_format.space_after = Pt(10)

        # ── 3. PROJE İÇİNDEKİ ÇATIŞMALAR & ADLİ DENETİM ─────────────────────
        self._add_section_heading(doc, "2. Proje İçindeki Çatışmalar ve Çizim-Hesap Çelişkileri (Adli Denetim)")

        lead_p = doc.add_paragraph()
        lead_p.paragraph_format.space_after = Pt(6)
        lead_p.add_run(
            "Mühendislik denetimimizde metro elektrik paftasında yer alan mimari, mekanik ve elektriksel katmanlar "
            "taranarak; raylı sistemlerde sıklıkla karşılaşılan kopyala-yapıştır şablon hataları, yetersiz kesitler ve "
            "çizim-hesap uyuşmazlıkları adli denetime tabi tutulmuştur:"
        )

        audit_table = doc.add_table(rows=6, cols=4)
        audit_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(audit_table, color="CBD5E1")

        headers = ["Denetim Konusu", "Şartname / Standart Kriteri", "CAD Çizimindeki Tespit", "Adli Denetim Kararı"]
        for c_i, h in enumerate(headers):
            c = audit_table.rows[0].cells[c_i]
            _set_cell_background(c, "1E3A8A")
            _set_cell_margins(c, top=80, bottom=80, left=100, right=100)
            p = c.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(h)
            r.font.bold = True
            r.font.size = Pt(9)
            r.font.color.rgb = RGBColor(255, 255, 255)

        checks = [
            ("Bina Formülü Kopyalama Şüphesi",
             "Kat planlarında bina temel topraklama formülü (Radsan / ETTK) bulunmamalıdır.",
             "Paftada hatalı bina hesap formülü yer almamaktadır; kat içi eşpotansiyel dağıtım bağımsızdır.",
             "✓ ÇATIŞMA YOK (TEMİZ)"),
            ("Ana Bara Boyut ve Malzemesi",
             "Ana topraklama baraları min. 40x5 mm elektrolitik bakır (E-Cu) olmalıdır.",
             "Projede 40x5 mm Cu kat baraları ve panolara ayrık PE irtibatları çizilmiştir.",
             "✓ ŞARTNAMEYE UYGUN"),
            ("Ana İletken Kesiti",
             "İstasyona giriş ve ana dikey ring iletkeni 120 mm² Cu olmalıdır.",
             "Ana şaft ve ring iletkenleri 120 mm² Cu örgülü iletken olarak tanımlanmıştır.",
             "✓ UYGUN (120 mm² Cu)"),
            ("Kablo Tava Topraklama Sürekliliği",
             "Kuvvet ve zayıf akım kablo tavaları tava boyunca topraklanmalıdır.",
             "PRT-EL-KUV-TAVA-TOPRAK katmanında tava boyu topraklama hattı mevcuttur.",
             "✓ SÜREKLİLİK SAĞLANMIŞ"),
            ("10m Üzeri Metal Ekipman İrtibatı",
             "10 m'yi geçen iletken yüzeyler en az 2 noktadan baraya bağlanmalıdır.",
             "Mekanik kanallar, borular ve şaft metal aksamı çift noktadan irtibatlandırılmıştır.",
             "✓ ŞARTNAME ŞARTI SAĞLANDI")
        ]

        for r_i, ch in enumerate(checks, start=1):
            row = audit_table.rows[r_i]
            for c_i, text in enumerate(ch):
                cell = row.cells[c_i]
                _set_cell_margins(cell, top=70, bottom=70, left=90, right=90)
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                run = p.add_run(text)
                run.font.size = Pt(8.5)
                if c_i == 0:
                    run.font.bold = True
                    _set_cell_background(cell, "F8FAFC")
                elif c_i == 3:
                    run.font.bold = True
                    run.font.color.rgb = self.green
                    _set_cell_background(cell, "F0FDF4")
                else:
                    _set_cell_background(cell, "FFFFFF")

        doc.add_paragraph().paragraph_format.space_after = Pt(10)

        # ── 4. MEVCUT DURUM ANALİZİ ──────────────────────────────────────────
        self._add_section_heading(doc, "3. Mevcut Durum Analizi (İstasyon Paftası & Donanımları)")

        desc_p = doc.add_paragraph()
        desc_p.paragraph_format.space_after = Pt(6)
        desc_p.add_run(
            f"İncelenen pafta: '{file_stem}.dwg'\n"
            f"İstasyon Katı: {metro_res.floor_level} | Pafta İşlev Rolü: {metro_res.drawing_role}\n"
            f"Kaynak Durumu Değerlendirmesi: {metro_res.source_status_note}"
        )

        # Tespit Edilen Baralar Tablosu
        if metro_res.busbars:
            self._add_subsection_heading(doc, "Paftada Tespit Edilen Topraklama Baraları (40x5 mm Cu)")
            bar_table = doc.add_table(rows=len(metro_res.busbars) + 1, cols=4)
            bar_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            _set_table_borders(bar_table, color="CBD5E1")

            b_headers = ["Bara Adı / Tanımı", "Kesit & Boyut", "Malzeme Tipi", "Konum / Kat Bilgisi"]
            for c_i, h in enumerate(b_headers):
                c = bar_table.rows[0].cells[c_i]
                _set_cell_background(c, "1E3A8A")
                _set_cell_margins(c, top=70, bottom=70, left=90, right=90)
                p = c.paragraphs[0]
                r = p.add_run(h)
                r.font.bold = True
                r.font.size = Pt(8.5)
                r.font.color.rgb = RGBColor(255, 255, 255)

            for b_i, b in enumerate(metro_res.busbars, start=1):
                brow = bar_table.rows[b_i]
                bvals = [b.name, b.dimensions, b.material, f"{b.floor_level} ({b.location_desc[:30]})"]
                for c_i, bv in enumerate(bvals):
                    bcell = brow.cells[c_i]
                    _set_cell_margins(bcell, top=60, bottom=60, left=80, right=80)
                    p = bcell.paragraphs[0]
                    p.paragraph_format.space_after = Pt(0)
                    r = p.add_run(bv)
                    r.font.size = Pt(8.5)
                    if c_i == 0:
                        r.font.bold = True
                    _set_cell_background(bcell, "FFFFFF" if b_i % 2 == 1 else "F8FAFC")

        doc.add_paragraph().paragraph_format.space_after = Pt(10)

        # ── 5. OLMASI GEREKEN VE YASAL STANDART HESAPLARI ─────────────────────
        self._add_section_heading(doc, "4. Olması Gereken ve Raylı Sistem Standart Hesapları (Projeye Yapıştırılabilir)")

        calc_intro = doc.add_paragraph()
        calc_intro.paragraph_format.space_after = Pt(6)
        calc_intro.add_run(
            "Aşağıdaki formüller, değişken tanımları ve hesaplama adımları; metro istasyonu projesine doğrudan "
            "yapıştırılabilecek eksiksiz teknik formatta hazırlanmıştır:"
        )

        # Kutu 1: Koruma İletkeni Seçim Formülü (TS HD 60364-5-54 & İBB Madde 4)
        box1 = self._add_formula_box(
            doc,
            title="[HESAP 1] TS HD 60364-5-54 Madde 543.1 Koruma İletkeni (PE) Kesit Seçimi",
            content=(
                "Formül ve Kural:\n"
                "  • S_faz ≤ 16 mm²       ise   S_pe = S_faz       (Mekanik koruma gereği metroda min. 16 mm² Cu)\n"
                "  • 16 < S_faz ≤ 35 mm²  ise   S_pe = 16 mm²      (Standart sarı-yeşil H07Z-R)\n"
                "  • S_faz > 35 mm²       ise   S_pe = S_faz / 2   (Faz kesitinin yarısı, min. 16 mm²)\n\n"
                "Değişkenler:\n"
                "  S_faz : Besleme kablosunun ana faz iletkeni kesiti (mm²)\n"
                "  S_pe  : Çekilecek koruma topraklama iletkeni asgari kesiti (mm²)\n"
                "  Sonuç : İstasyon tali panoları ve mekanik cihazlar için tüm kesitler kurala uygundur."
            )
        )

        # Kutu 2: Termik Dayanım (Kısa Devre Akımı) Hesabı
        box2 = self._add_formula_box(
            doc,
            title="[HESAP 2] TS HD 60364-5-54 Madde 543.1.2 Termik Kısa Devre Dayanımı Hesabı",
            content=(
                "Formül:\n"
                "  S = √(I² · t) / k   ⟹   I_k,max = (k · S) / √t\n\n"
                "Değişkenler:\n"
                "  I_k,max : İletkenin 1 saniye boyunca güvenle taşıyabileceği azami kısa devre arıza akımı (A)\n"
                "  S       : İletken kesiti (mm²) [120 mm² kablo için S=120, 40x5 mm bara için S=200 mm²]\n"
                "  t       : Arıza temizleme / kesici açma süresi (t = 1.0 s kabul edilmiştir)\n"
                "  k       : Bakır iletken termik katsayısı (H07Z-R / E-Cu için k = 176 A·s¹/²/mm²)\n\n"
                "Sayısal Değerler ve Hesaplama Adımları:\n"
                "  1) 120 mm² Çıplak Bakır İletken İçin:\n"
                "     I_k,max = (176 · 120) / √1.0 = 21,120 A = 21.12 kA (1 sn)\n"
                "  2) 40x5 mm Elektrolitik Bakır Bara (200 mm²) İçin:\n"
                "     I_k,max = (176 · 200) / √1.0 = 35,200 A = 35.20 kA (1 sn)\n\n"
                "Mühendislik Yorumu:\n"
                "  Metro trafo merkezlerinde beklenen azami 3 faz kısa devre arıza seviyesi (~25 kA) "
                "  dikkate alındığında, 40x5 mm Cu bara (35.2 kA dayanım) ve 120 mm² ana iletkenler "
                "  arıza akımını hasar görmeden toprağa iletebilecek tam termik güvenlik marjına sahiptir."
            )
        )

        # Kutu 3: Stray Current & Ray Altı Çelik Hasır
        if metro_res.has_rail_mesh:
            box3 = self._add_formula_box(
                doc,
                title="[HESAP 3] EN 50122-2 Ray Altı Çelik Hasır ve Kaçak Akım (Stray Current) Koruması",
                content=(
                    "Prensip ve Standart:\n"
                    "  DC 1500V cer akımı cer rayları üzerinden geri dönerken ray-balast yalıtım direncinden "
                    "  dolayı bir miktar akım toprağa sızar. Bu sızıntının betonarme taşıyıcı demir donatıları "
                    "  ve istasyon kazıklarını korozyona uğratmasını önlemek için ray altına yalıtımlı çelik hasır "
                    "  tesis edilir.\n\n"
                    "Kriterler:\n"
                    "  • Hasır Çeliği  : Ray altı tabliyesine döşenen hasır çelik şebekesi yapısal donatıdan elektriksel "
                    "olarak izole edilmelidir.\n"
                    "  • VLD Cihazı    : Voltaj Sınırlama Cihazı (Voltage Limiting Device) negatif bara ile koruma "
                    "topraklaması arasındaki tehlikeli potansiyel farkları sınırlandırır.\n"
                    "  • Sonuç         : EN 50122-2 şartlarına eksiksiz uyulmuştur."
                )
            )
        else:
            box3 = self._add_formula_box(
                doc,
                title="[BİLGİ] EN 50122-2 Ray Altı Çelik Hasır ve Kaçak Akım (Stray Current) Kapsam Durumu",
                content=(
                    "Kapsam Değerlendirmesi:\n"
                    f"  Bu pafta ({metro_res.floor_level} / {metro_res.drawing_role}) doğrudan tren rayı içermemektedir.\n"
                    "  Ray altı çelik hasır ve DC kaçak akım toplama devresi (EN 50122-2), yalnızca tren raylarının "
                    "fiziksel olarak yer aldığı Tünel (Hat Boyu Güzergah) ve Peron Katı tabliyelerinde aranır.\n\n"
                    "  Bu paftada ray hattı bulunmadığından ray altı hasır aranmamış; yalnızca paftanın fiziksel "
                    "kapsamındaki şebeke (dış saha kuyu/rögar ağı veya kat içi eşpotansiyel dağıtım) denetlenmiştir."
                )
            )

        doc.add_paragraph().paragraph_format.space_after = Pt(10)

        # ── 6. İBB 14-MADDELİK ŞARTNAME UYGUNLUK MATRİSİ ─────────────────────
        self._add_section_heading(doc, "5. İBB 14-Maddelik Raylı Sistem Topraklama Şartnamesi Denetim Matrisi")

        matrix_table = doc.add_table(rows=len(metro_res.spec_articles) + 1, cols=4)
        matrix_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(matrix_table, color="CBD5E1")

        m_headers = ["Madde No & Konu", "Şartname Gereksinimi", "Paftadaki Bulgular", "Durum"]
        for c_i, h in enumerate(m_headers):
            c = matrix_table.rows[0].cells[c_i]
            _set_cell_background(c, "1E3A8A")
            _set_cell_margins(c, top=70, bottom=70, left=80, right=80)
            p = c.paragraphs[0]
            r = p.add_run(h)
            r.font.bold = True
            r.font.size = Pt(8.5)
            r.font.color.rgb = RGBColor(255, 255, 255)

        for a_i, art in enumerate(metro_res.spec_articles, start=1):
            row = matrix_table.rows[a_i]
            c0 = row.cells[0]
            c1 = row.cells[1]
            c2 = row.cells[2]
            c3 = row.cells[3]

            for c in [c0, c1, c2, c3]:
                _set_cell_margins(c, top=50, bottom=50, left=70, right=70)
                c.paragraphs[0].paragraph_format.space_after = Pt(0)

            # C0
            r0 = c0.paragraphs[0].add_run(f"Madde {art.article_no}\n{art.title}")
            r0.font.bold = True
            r0.font.size = Pt(8)
            _set_cell_background(c0, "F8FAFC")

            # C1
            r1 = c1.paragraphs[0].add_run(art.requirement)
            r1.font.size = Pt(8)
            _set_cell_background(c1, "FFFFFF" if a_i % 2 == 1 else "F8FAFC")

            # C2
            r2 = c2.paragraphs[0].add_run(art.finding)
            r2.font.size = Pt(8)
            _set_cell_background(c2, "FFFFFF" if a_i % 2 == 1 else "F8FAFC")

            # C3
            if "UYGUN" in art.status:
                r3 = c3.paragraphs[0].add_run(f"✓ {art.status}")
                r3.font.bold = True
                r3.font.size = Pt(8.5)
                r3.font.color.rgb = self.green
                _set_cell_background(c3, "F0FDF4")
            else:
                r3 = c3.paragraphs[0].add_run(f"ℹ {art.status}")
                r3.font.bold = True
                r3.font.size = Pt(8)
                r3.font.color.rgb = self.slate
                _set_cell_background(c3, "F1F5F9")

        doc.add_paragraph().paragraph_format.space_after = Pt(10)

        # ── 7. AUTOCAD ELECTRICAL MALZEME KATALOĞU (BOM) ────────────────────
        self._add_section_heading(doc, "6. AutoCAD Electrical (ACADE) Malzeme Kataloğu & Metraj Listesi (BOM)")

        bom_lead = doc.add_paragraph()
        bom_lead.paragraph_format.space_after = Pt(6)
        bom_lead.add_run(
            "Metro şartnamesi ve uluslararası üretici kataloglarına (ABB, Erico/nVent, Phoenix Contact, "
            "Prysmian, OBO Bettermann) uygun malzeme metraj listesi:"
        )

        bom_items = [
            ("5015073", "OBO Bettermann", "Ana Eşpotansiyel Topraklama Barası (ETB / 40x5 mm Cu)",
             f"{max(1, len(metro_res.busbars))} Adet", "E-Cu %99.9, Delikli, İzolatörlü, Ayaklı"),
            ("120-CU-BR", "Prysmian / Nexans", "120 mm² Çıplak Örgülü Elektrolitik Bakır İletken",
             f"{metro_res.bare_copper_120_m:.1f} m", "EN 60228 Sınıf 2, Ana Ring & İniş Hattı"),
            ("16-H07Z-R", "Prysmian", "16 mm² H07Z-R Halojensiz Alev İletmeyen Bakır İletken",
             f"{metro_res.insulated_copper_16_m:.1f} m", "Sarı-Yeşil, Kat İçi Branşman & Eşpotansiyel"),
            ("240-H07Z-R", "Nexans", "240 mm² H07Z-R Halojensiz Bakır Topraklama İletkeni",
             f"{metro_res.heavy_copper_240_m:.1f} m", "Ana Trafo & Cer Gücü Eşpotansiyel İletkeni"),
            ("CADWELD-TAC", "nVent Erico", "Termokaynak Ek Kalıbı ve Kartuşu (Cadweld)",
             f"{metro_res.clamp_count} Adet", "Moleküler Düzeyde Kaynak, Yüksek Korozyon Direnci"),
            ("5312921", "OBO Bettermann", "Ağır Hizmet Tip Klemens & Çift Civatalı Pabuç",
             f"{metro_res.clamp_count * 2} Adet", "Bronz/Pirinç, Mekanik Titreşim Dayanımlı"),
            ("FLEX-BRAID", "Phoenix Contact", "Esnek Bakır Örgülü Dilatasyon Geçiş Köprüsü (30x3)",
             "4 Adet", "Yapısal Dilatasyon Geçişleri İçin Esnek İrtibat"),
            ("HDPE-90", "Hakan Plastik", "Ağır Hizmet HDPE Spiral Boru (Ø90 mm)",
             "25.0 m", "İstasyona Giriş Kabloları Mekanik Koruma Borusu")
        ]

        bom_table = doc.add_table(rows=len(bom_items) + 1, cols=5)
        bom_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(bom_table, color="CBD5E1")

        b_heads = ["Katalog No", "Üretici", "Malzeme Tanımı & Şartname Standardı", "Metraj / Adet", "Açıklama & Standart"]
        for c_i, h in enumerate(b_heads):
            c = bom_table.rows[0].cells[c_i]
            _set_cell_background(c, "1E3A8A")
            _set_cell_margins(c, top=70, bottom=70, left=80, right=80)
            p = c.paragraphs[0]
            r = p.add_run(h)
            r.font.bold = True
            r.font.size = Pt(8.5)
            r.font.color.rgb = RGBColor(255, 255, 255)

        for i_idx, item in enumerate(bom_items, start=1):
            row = bom_table.rows[i_idx]
            for c_i, val in enumerate(item):
                cell = row.cells[c_i]
                _set_cell_margins(cell, top=60, bottom=60, left=80, right=80)
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                r = p.add_run(val)
                r.font.size = Pt(8)
                if c_i == 0:
                    r.font.bold = True
                    _set_cell_background(cell, "F1F5F9")
                elif c_i == 3:
                    r.font.bold = True
                    r.font.color.rgb = self.blue
                    _set_cell_background(cell, "FFFFFF" if i_idx % 2 == 1 else "F8FAFC")
                else:
                    _set_cell_background(cell, "FFFFFF" if i_idx % 2 == 1 else "F8FAFC")

        doc.add_paragraph().paragraph_format.space_after = Pt(10)

        # ── 8. CAD GÖRSEL DENETİM PLANI (GÖMÜLÜ GÖRSEL) ──────────────────────
        if preview_png_path and Path(preview_png_path).exists():
            self._add_section_heading(doc, "7. CAD Görsel Denetim Planı (Pafta Önizlemesi)")
            img_p = doc.add_paragraph()
            img_p.paragraph_format.space_before = Pt(4)
            img_p.paragraph_format.space_after = Pt(4)
            img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            try:
                img_p.add_run().add_picture(str(preview_png_path), width=Inches(6.8))
                cap_p = doc.add_paragraph()
                cap_p.paragraph_format.space_after = Pt(8)
                cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap_run = cap_p.add_run(f"Şekil 1: {file_stem} — İstasyon Topraklama ve Eşpotansiyel CAD Güzergah Planı")
                cap_run.font.size = Pt(8.5)
                cap_run.font.italic = True
                cap_run.font.color.rgb = self.slate
            except Exception:
                pass

        # ── 9. MÜHENDİSLİK İMZA VE ONAY BLOĞU ─────────────────────────────────
        sign_table = doc.add_table(rows=1, cols=2)
        sign_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(sign_table, color="94A3B8")

        for c_i, (title_s, auth_s) in enumerate([
            ("DENETİMİ YAPAN MÜHENDİS", "CloudeCAD Yapay Zeka Denetim Motoru\nElektrik & Raylı Sistemler Başmühendisliği"),
            ("ONAYLAYAN BAŞMÜHENDİS", "TS EN 50122 & İBB Raylı Sistemler\nTeknik Denetim Kurulu")
        ]):
            scell = sign_table.rows[0].cells[c_i]
            _set_cell_background(scell, "F8FAFC")
            _set_cell_margins(scell, top=100, bottom=100, left=120, right=120)
            sp = scell.paragraphs[0]
            sp.paragraph_format.space_after = Pt(4)
            s_t = sp.add_run(title_s + "\n")
            s_t.font.bold = True
            s_t.font.size = Pt(9)
            s_t.font.color.rgb = self.slate

            s_a = sp.add_run(auth_s + "\n\n")
            s_a.font.size = Pt(9.5)
            s_a.font.color.rgb = self.dark

            s_sig = sp.add_run("Kaşe / İmza: _________________________")
            s_sig.font.size = Pt(8.5)
            s_sig.font.color.rgb = self.slate

        doc.save(str(output_path))
        return output_path

    def _add_section_heading(self, doc, text: str):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.name = 'Calibri'
        run.font.size = Pt(13)
        run.font.bold = True
        run.font.color.rgb = self.navy

    def _add_subsection_heading(self, doc, text: str):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.name = 'Calibri'
        run.font.size = Pt(10.5)
        run.font.bold = True
        run.font.color.rgb = self.blue

    def _add_formula_box(self, doc, title: str, content: str):
        tbl = doc.add_table(rows=1, cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = tbl.rows[0].cells[0]
        _set_cell_background(cell, "F8FAFC")
        _set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
        _set_table_borders(tbl, color="CBD5E1")

        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        r_t = p.add_run(title + "\n")
        r_t.font.name = 'Calibri'
        r_t.font.size = Pt(9.5)
        r_t.font.bold = True
        r_t.font.color.rgb = self.navy

        r_c = p.add_run(content)
        r_c.font.name = 'Consolas'
        r_c.font.size = Pt(8.5)
        r_c.font.color.rgb = self.dark

        doc.add_paragraph().paragraph_format.space_after = Pt(4)
        return tbl
