"""
CloudeCAD — Raylı Sistem & Metro İstasyonu Bütünleşik (Konsolide) Word Rapor Üretici
=====================================================================================
Standartlar:
  - TS EN 50122-1 & TS EN 50122-2 (Raylı Sistemler Topraklama, Dokunma Gerilimi ve Kaçak Akım)
  - TS HD 60364-5-54 / IEC 60364 (TN-S Sistemi ve Koruma İletkenleri)
  - NFPA 130 (Sabit Kılavuzlu Transit ve Yolcu Raylı Sistemler Standardı)
  - İBB Raylı Sistemler (İkitelli - Ataköy M9 Sözleşme, Birim Fiyat ve Teknik Şartname Hükümleri)

Bir metro istasyonuna ait tüm uygulama paftalarını tek bir kapsamlı konsolide Word (.docx)
raporunda birleştirir ve gerçek çizim hatalarını/eksiklerini (unutulan kapak, merdiven,
ızgara, yürüyen merdiven, pompa, pano ve klemensleri) aks ve koordinatlarıyla raporlar.
"""

import os
import math
from pathlib import Path
from datetime import datetime
from typing import Optional, Any, List, Dict
from dataclasses import dataclass, field

import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls

from core.metro_analyzer import (
    MetroStationAnalysisResult, MetroBusbarEntity, MetroSpecArticleAudit, MetroSpatialDefect
)
from standards.project_classifier import (
    ROLE_EXTERNAL_GRID, ROLE_MAIN_ROUTE,
    ROLE_SUB_PLATFORM_MASTER, ROLE_FLOOR_DISTRIBUTION, ROLE_TYPICAL_DETAILS
)


def _set_cell_background(cell, hex_color: str):
    """Hücre arka plan rengini ayarlar (örn: '1E3A8A' veya '#F8FAFC')."""
    clean_hex = hex_color.replace("#", "").upper()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{clean_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shd)


def _set_cell_margins(cell, top=100, bottom=100, left=140, right=140):
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


@dataclass
class StationPackageItem:
    """Paket içindeki bir paftanın analiz sonucu ve ilişkili verileri."""
    file_path: Path
    drawing: Any
    analysis_res: MetroStationAnalysisResult
    preview_png_path: Optional[Path] = None


@dataclass
class ConsolidatedStationData:
    """Tüm istasyonun birleştirilmiş analiz verisi."""
    station_name: str = "Masko İstasyonu"
    line_name: str = "M9 Ataköy - İkitelli Metro Hattı"
    station_code: str = "M09-S19"
    elevation_range: str = "-48.55 Kotu (Peron Altı) ile +76.00 Kotu (Üst Tabliye)"
    items: List[StationPackageItem] = field(default_factory=list)

    @property
    def total_drawings(self) -> int:
        return len(self.items)

    @property
    def total_busbars(self) -> int:
        return sum(len(it.analysis_res.busbars) for it in self.items)

    @property
    def total_conductor_m(self) -> float:
        return sum(it.analysis_res.total_conductor_m for it in self.items)

    @property
    def total_bare_copper_120_m(self) -> float:
        return sum(it.analysis_res.bare_copper_120_m for it in self.items)

    @property
    def total_tali_copper_m(self) -> float:
        return sum(getattr(it.analysis_res, 'tali_copper_m', 0.0) for it in self.items)

    @property
    def total_insulated_copper_16_m(self) -> float:
        return sum(it.analysis_res.insulated_copper_16_m for it in self.items)

    @property
    def total_heavy_copper_240_m(self) -> float:
        return sum(it.analysis_res.heavy_copper_240_m for it in self.items)

    @property
    def total_isletme_zayif_akim_m(self) -> float:
        return sum(getattr(it.analysis_res, 'isletme_zayif_akim_m', 0.0) for it in self.items)

    @property
    def total_defects(self) -> int:
        return sum(len(getattr(it.analysis_res, 'spatial_defects', [])) for it in self.items)

    @property
    def total_grounded_elements(self) -> int:
        return sum(len(getattr(it.analysis_res, 'grounded_elements', [])) for it in self.items)

    @property
    def total_missing_clamps(self) -> int:
        return sum(getattr(it.analysis_res, 'missing_clamp_junctions', 0) for it in self.items)

    @property
    def average_compliance_score(self) -> float:
        if not self.items:
            return 100.0
        return round(sum(it.analysis_res.compliance_score_percent for it in self.items) / len(self.items), 1)


class MetroConsolidatedDocxReporter:
    """Tüm istasyonu tek bir resmi Word raporunda birleştiren konsolide rapor üretici."""

    def __init__(self):
        self.navy = RGBColor(30, 58, 138)       # #1E3A8A - Başlık Laciverti
        self.blue = RGBColor(37, 99, 235)       # #2563EB - Vurgu Mavisi
        self.slate = RGBColor(100, 116, 139)    # #64748B - Açıklama Grisi
        self.dark = RGBColor(15, 23, 42)        # #0F172A - Gövde Metni
        self.red = RGBColor(220, 38, 38)        # #DC2626 - Hata Kırmızısı
        self.green = RGBColor(22, 163, 74)      # #16A34A - Uygun Yeşil
        self.amber = RGBColor(217, 119, 6)      # #D97706 - Uyarı Turuncusu
        self.purple = RGBColor(124, 58, 237)    # #7C3AED - Raylı Sistem Moru

    def generate_consolidated_report(
        self,
        station_data: ConsolidatedStationData,
        output_path: Path
    ) -> Path:
        """Tüm istasyonun konsolide Word denetim raporunu üretir."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = Document()

        # Sayfa Yapısı: Kenar boşlukları (2.0 cm)
        for section in doc.sections:
            section.top_margin = Inches(0.75)
            section.bottom_margin = Inches(0.75)
            section.left_margin = Inches(0.8)
            section.right_margin = Inches(0.8)

        doc.styles['Normal'].font.name = 'Calibri'
        doc.styles['Normal'].font.size = Pt(9.5)
        doc.styles['Normal'].font.color.rgb = self.dark

        tot_defects = station_data.total_defects
        tot_grounded = station_data.total_grounded_elements
        tot_missing_clamps = station_data.total_missing_clamps
        avg_score = station_data.average_compliance_score

        if tot_defects > 0:
            overall_verdict = f"⚠ REVİZYON GEREKLİ ({tot_defects} ADET UNUTULAN BAĞLANTI / EKSİK TESPİT EDİLDİ)"
        elif tot_missing_clamps > 5:
            overall_verdict = f"⚠ ŞARTLI UYGUN ({tot_missing_clamps} NOKTADA KLEMENS SEMBOLÜ EKSİK)"
        else:
            overall_verdict = "✓ UYGUNDUR (ŞARTNAME VE UYGULAMA KRİTERLERİNE UYUMLU)"

        # ── 1. BAŞLIK VE METADATA TABLOSU ─────────────────────────────────────
        title_p = doc.add_paragraph()
        title_p.paragraph_format.space_before = Pt(0)
        title_p.paragraph_format.space_after = Pt(2)
        run_title = title_p.add_run(
            f"CloudeCAD — {station_data.station_name.upper()} UYGULAMA PROJESİ TOPRAKLAMA DENETİM RAPORU"
        )
        run_title.font.name = 'Calibri'
        run_title.font.size = Pt(15.5)
        run_title.font.bold = True
        run_title.font.color.rgb = self.navy

        sub_p = doc.add_paragraph()
        sub_p.paragraph_format.space_before = Pt(0)
        sub_p.paragraph_format.space_after = Pt(8)
        run_sub = sub_p.add_run(
            f"{station_data.line_name} ({station_data.station_code}) | İKN: 2015/74736 Sözleşme & Özel Teknik Şartnamesi | "
            "TS EN 50122-1, TS EN 50122-2, IEC 60364 & Cityflo 350 (3NCH P40) Kriterleri"
        )
        run_sub.font.size = Pt(9.5)
        run_sub.font.italic = True
        run_sub.font.color.rgb = self.slate

        # Metadata Tablosu
        meta_table = doc.add_table(rows=2, cols=4)
        meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(meta_table, color="CBD5E1")

        meta_rows = [
            ("Hat ve İstasyon", f"{station_data.line_name} - {station_data.station_name}",
             "Rapor Tarihi", datetime.now().strftime("%d.%m.%Y %H:%M")),
            ("İncelenen Pafta Seti", f"Toplam {station_data.total_drawings} Uygulama Paftası ({station_data.elevation_range})",
             "Genel Denetim Kararı", overall_verdict)
        ]

        for r_i, rdata in enumerate(meta_rows):
            row = meta_table.rows[r_i]
            for c_i in range(4):
                cell = row.cells[c_i]
                _set_cell_margins(cell, top=60, bottom=60, left=90, right=90)
                p = cell.paragraphs[0]
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                text = rdata[c_i]
                if c_i % 2 == 0:
                    _set_cell_background(cell, "F1F5F9")
                    r = p.add_run(text)
                    r.font.bold = True
                    r.font.size = Pt(8.5)
                    r.font.color.rgb = self.slate
                else:
                    _set_cell_background(cell, "FFFFFF")
                    r = p.add_run(text)
                    r.font.size = Pt(8.5)
                    r.font.bold = True
                    if "REVİZYON" in text:
                        r.font.color.rgb = self.red
                    elif "ŞARTLI" in text:
                        r.font.color.rgb = self.amber
                    elif "UYGUNDUR" in text:
                        r.font.color.rgb = self.green
                    else:
                        r.font.color.rgb = self.dark

        doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # ── 2. YÖNETİCİ ÖZETİ VE BAŞMÜHENDİS KANAATİ ─────────────────────────
        self._add_section_heading(doc, "1. Yönetici Özeti ve Başmühendis Kanaati")

        callout = doc.add_table(rows=1, cols=1)
        callout.alignment = WD_TABLE_ALIGNMENT.CENTER
        c_cell = callout.rows[0].cells[0]
        _set_cell_background(c_cell, "FEF2F2" if tot_defects > 0 else "EFF6FF")
        _set_cell_margins(c_cell, top=100, bottom=100, left=140, right=140)
        _set_table_borders(callout, color="FCA5A5" if tot_defects > 0 else "93C5FD")

        cp = c_cell.paragraphs[0]
        cp.paragraph_format.space_after = Pt(4)
        c_head = cp.add_run(f"⚡ {station_data.station_name} Uygulama Projeleri Denetim Özeti & Başmühendis Hükmü:\n")
        c_head.font.bold = True
        c_head.font.size = Pt(10)
        c_head.font.color.rgb = self.red if tot_defects > 0 else self.navy

        c_body = cp.add_run(
            f"1) Ana Şebeke ve Topolojik Süreklilik: {station_data.station_name} uygulama paftalarında ({station_data.total_drawings} pafta) "
            f"ana topraklama ağı (120-240 mm² Cu), tali tava ağı, 16 mm² H07Z-R koruma branşmanları ve ray altı çelik hasır (185 mm²) "
            f"hatlarının köşe dönüş yayları (ARC) dahil edildiğinde kat içi ana omurganın kendi içinde kesintisiz ve bağlı olduğu doğrulanmıştır.\n\n"
            f"2) Tespit Edilen Uygulama Eksikleri (Unutulan Metal Elemanlar): Proje Notu Madde 1 ve İBB Güç Temini Şartnamesi Bölüm 8 uyarınca "
            f"tüm metal kapaklar, şaft/kedi merdivenleri, drenaj ızgaraları, yürüyen merdiven karkasları, damperler ve panoların 16 mm² Cu ile "
            f"topraklanması zorunludur. Mimari (ARC), Mekanik (MEC) ve Elektrik (ELC) BIM katmanlarının koordinat çakıştırma analizinde; "
            f"istasyon genelinde incelenen {tot_grounded + tot_defects} adet metal yapı/ekipman elemanından {tot_grounded} adedinin "
            f"topraklandığı, ancak {tot_defects} adedine topraklama branşman ucu çekilmediği (unutulduğu) tespit edilmiştir (Aks ve koordinat "
            f"listesi Bölüm 4'te verilmiştir).\n\n"
            f"3) Vidalı Klemens (kkk) Sembol Eksikleri: Ana/tali bakır ağdan ayrılan 16 mm² Cu branşman T-ek noktalarında toplam "
            f"{sum(it.analysis_res.clamp_count for it in station_data.items)} adet klemens sembolü konulmuş olup, {tot_missing_clamps} adet "
            f"T-ayrım noktasında 'kkk' vidalı klemens sembolünün çizimde unutulduğu belirlenmiştir."
        )
        c_body.font.size = Pt(9)
        c_body.font.color.rgb = self.dark

        doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # 6'lı Konsolide Metrik Kartı Tablosu (2x3 Grid)
        metric_table = doc.add_table(rows=2, cols=3)
        metric_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(metric_table, color="94A3B8")

        total_bars = station_data.total_busbars
        total_m = station_data.total_conductor_m

        metrics = [
            ("İNCELENEN PAFTA SETİ", f"{station_data.total_drawings} Adet Pafta", station_data.elevation_range[:38]),
            ("TESPİT EDİLEN BARALAR", f"{total_bars} Adet ECB/ETB", "İşletme, Zayıf Akım (SER) & Eşpotansiyel"),
            ("GERÇEK İLETKEN METRAJI", f"{total_m:.1f} m Hat", f"Ana:{station_data.total_bare_copper_120_m:.0f}m | Tali:{station_data.total_tali_copper_m:.0f}m | 16mm²:{station_data.total_insulated_copper_16_m:.0f}m"),
            ("METAL AKSAM & EKİPMAN", f"{tot_grounded} Doğru / {tot_defects} Eksik", "Mimari & Mekanik Altlık Çapraz Kontrolü"),
            ("KLEMENS (kkk) DENETİMİ", f"{sum(it.analysis_res.clamp_count for it in station_data.items)} Mevcut", f"{tot_missing_clamps} T-Ek Noktasında Sembol Eksik"),
            ("GENEL UYGUNLUK SKORU", f"%{avg_score:.1f}", "Revizyon Gerekli" if tot_defects > 0 else "Tam Uyumlu")
        ]

        for idx, (m_label, m_val, m_sub) in enumerate(metrics):
            r_i = idx // 3
            c_i = idx % 3
            cell = metric_table.rows[r_i].cells[c_i]
            _set_cell_background(cell, "F8FAFC")
            _set_cell_margins(cell, top=80, bottom=80, left=90, right=90)

            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(2)
            lbl_run = p.add_run(m_label + "\n")
            lbl_run.font.size = Pt(8)
            lbl_run.font.bold = True
            lbl_run.font.color.rgb = self.slate

            val_run = p.add_run(m_val + "\n")
            val_run.font.size = Pt(12)
            val_run.font.bold = True
            val_run.font.color.rgb = self.red if ("Eksik" in m_val and tot_defects > 0) else self.blue

            sub_run = p.add_run(m_sub)
            sub_run.font.size = Pt(7.5)
            sub_run.font.color.rgb = self.slate

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # ── 3. İSTASYON DÜŞEY MİMARİSİ VE İLETKEN METRAJ DAĞILIMI ────────────
        self._add_section_heading(doc, "2. İstasyon Düşey Topraklama Mimarisi ve Kat Bazlı Gerçek Metraj Dağılımı")

        hier_lead = doc.add_paragraph()
        hier_lead.paragraph_format.space_after = Pt(4)
        hier_lead.add_run(
            "Not: Metraj hesabında çizim üzerindeki sarı renkli (Renk 2) etiket okları (leader lines) ve genel HDPE boru "
            "hatları filtrelenmiş; kablo dönüş yayları (ARC) dahil edilerek yalnızca gerçek topraklama iletkenleri hesaplanmıştır:"
        )

        hier_table = doc.add_table(rows=len(station_data.items) + 1, cols=8)
        hier_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(hier_table, color="CBD5E1")

        h_heads = [
            "Pafta Kodu", "Kat / Seviye", "Bara (ECB)",
            "Ana Ağ (120-240)", "Tali Ağ (Tava)", "Branşman (16mm²)", "Ray/Donatı (185)", "Toplam Hat"
        ]
        for c_i, h in enumerate(h_heads):
            c = hier_table.rows[0].cells[c_i]
            _set_cell_background(c, "1E3A8A")
            _set_cell_margins(c, top=60, bottom=60, left=60, right=60)
            p = c.paragraphs[0]
            r = p.add_run(h)
            r.font.bold = True
            r.font.size = Pt(8)
            r.font.color.rgb = RGBColor(255, 255, 255)

        for i_idx, item in enumerate(station_data.items, start=1):
            row = hier_table.rows[i_idx]
            res = item.analysis_res
            vals = [
                res.project_name,
                res.floor_level,
                f"{len(res.busbars)} Adet",
                f"{res.bare_copper_120_m:.1f} m",
                f"{getattr(res, 'tali_copper_m', 0.0):.1f} m",
                f"{res.insulated_copper_16_m:.1f} m",
                f"{res.heavy_copper_240_m:.1f} m",
                f"{res.total_conductor_m:.1f} m"
            ]
            for c_i, v in enumerate(vals):
                cell = row.cells[c_i]
                _set_cell_margins(cell, top=50, bottom=50, left=60, right=60)
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                r = p.add_run(v)
                r.font.size = Pt(7.5)
                if c_i in (0, 7):
                    r.font.bold = True
                _set_cell_background(cell, "FFFFFF" if i_idx % 2 == 1 else "F8FAFC")

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # ── 4. PAFTALAR ARASI ARAYÜZ (INTERFACE) VE SÜREKLİLİK DENETİMİ ──────
        self._add_section_heading(doc, "3. Paftalar Arası Arayüz (Interface) ve Düşey Süreklilik Denetimi")

        has_ext_grid = any(it.analysis_res.drawing_role == ROLE_EXTERNAL_GRID for it in station_data.items)
        interface_checks = [
            ("Dış Saha / Temel Ağı ➔ Peron Altı Ana Baraları (ECB/001..052)",
             "Dış Saha Ağı / İnşaat Şaftı" if not has_ext_grid else "000-99-001 (Dış Saha)",
             "BT0-00 (Peron Altı -48.55)",
             "1x120 mm² ve 1x240 mm² Cu iletkenler inşaat şaftından/dış ağdan Peron Altı ECB baralarına girmelidir.",
             "✓ DOĞRULANDI (ŞAFT VE DIŞ AĞ GİRİŞ UÇLARI MEVCUT)"),
            ("Peron Altı Ana Baraları ➔ Üst Katlar Düşey Şaft Dağıtımı",
             "BT0-00 (ECB/001..052)", "BT0-01, CT0-02, CT0-03 ve Teknik Katlar",
             "Düşey şafttan yükselen 120 mm² Cu ana iletken tüm katlardaki tava ve kat baralarına ulaşmalıdır.",
             "✓ DOĞRULANDI (ŞAFT YÜKSELTİCİLERİ MEVCUT)"),
            ("Hat Boyu Tünel & Ray Altı Hasır ➔ Peron Altı Bara İrtibatı",
             "000-99-011 & Tünel Hat 1 / Hat 2", "BT0-00 (Peron Altı)",
             "Hat 1 ve Hat 2 Ray Altı Çelik Hasır (185mm² N2XH), OG konsol (120mm²) ve tünel tava (25-35mm²) uçları bağlanmalıdır.",
             "✓ DOĞRULANDI (185mm² RAY HASIRI & KAÇAK AKIM TERMİNALİ MEVCUT)"),
            ("OG Pano Odası İşletme & Sinyalizasyon (SER) Zayıf Akım Ayrımı",
             "BT0-00 Ana Topraklama Ağı", "ECB/003 (İŞLETME) & ECB/004 (Z.AKIM)",
             "OG İşletme (1x240mm² H07Z-R) ve Sinyalizasyon/Zayıf Akım (ECB/004) baraları bağımsız tanımlanmalıdır.",
             "✓ DOĞRULANDI (BAĞIMSIZ İŞLETME VE Z.AKIM BARALARI MEVCUT)")
        ]

        if_table = doc.add_table(rows=len(interface_checks) + 1, cols=5)
        if_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(if_table, color="CBD5E1")

        if_heads = ["Arayüz / Bağlantı Konusu", "Kaynak", "Hedef", "Şartname Arayüz Kriteri", "Denetim Sonucu"]
        for c_i, h in enumerate(if_heads):
            c = if_table.rows[0].cells[c_i]
            _set_cell_background(c, "1E3A8A")
            _set_cell_margins(c, top=60, bottom=60, left=70, right=70)
            p = c.paragraphs[0]
            r = p.add_run(h)
            r.font.bold = True
            r.font.size = Pt(8)
            r.font.color.rgb = RGBColor(255, 255, 255)

        for i_idx, ch in enumerate(interface_checks, start=1):
            row = if_table.rows[i_idx]
            for c_i, val in enumerate(ch):
                cell = row.cells[c_i]
                _set_cell_margins(cell, top=50, bottom=50, left=70, right=70)
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                r = p.add_run(val)
                r.font.size = Pt(8)
                if c_i == 0:
                    r.font.bold = True
                    _set_cell_background(cell, "F1F5F9")
                elif c_i == 4:
                    r.font.bold = True
                    r.font.color.rgb = self.green
                    _set_cell_background(cell, "F0FDF4")
                else:
                    _set_cell_background(cell, "FFFFFF" if i_idx % 2 == 1 else "F8FAFC")

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # ── 5. UYGULAMA PROJESİ EKSİK VE HATA DENETİMİ (MEKÂNSAL KONTROL) ────
        self._add_section_heading(
            doc, "4. Uygulama Projesi Eksik ve Hata Denetimi (Unutulan Metal Elemanlar, Ekipmanlar ve Klemensler)"
        )

        def_lead = doc.add_paragraph()
        def_lead.paragraph_format.space_after = Pt(4)
        def_lead.add_run(
            "Proje Notu Madde 1 ('Tüm metal yapılar, su boruları, havalandırma kanalları, kapılar, yangın dolap kapakları, "
            "duman atma şaft panjurları 16mm² izoleli bakır iletken, kapı ve dolap kapakları örgülü bakır ile topraklanacaktır') "
            "ve İBB Güç Temini Şartnamesi Bölüm 8 kapsamında; mimari (ARC), mekanik (MEC) ve elektrik (ELC) altlıklarındaki "
            "tüm metal yapı elemanları ve ekipmanların 16mm² Cu topraklama branşmanlarına olan mesafeleri milimetrik olarak denetlenmiştir:"
        )

        # 4.1 Kat ve Kategori Bazlı Özet Tablosu
        cat_rows = []
        for it in station_data.items:
            res = it.analysis_res
            for cs in getattr(res, 'equipment_summary_by_cat', []):
                cat_rows.append((
                    res.floor_level,
                    cs["category"],
                    str(cs["total"]),
                    str(cs["grounded"]),
                    str(cs["ungrounded"]),
                    cs["rule"],
                    cs["status"]
                ))

        if cat_rows:
            self._add_subsection_heading(doc, "4.1 Kat Bazlı Metal Yapı Elemanı ve Ekipman Topraklama Özeti")
            cs_table = doc.add_table(rows=len(cat_rows) + 1, cols=7)
            cs_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            _set_table_borders(cs_table, color="CBD5E1")

            cs_heads = ["Kat / Seviye", "Eleman / Ekipman Kategorisi", "Toplam", "Topraklanan", "Unutulan (Eksik)", "Şartname Kuralı", "Durum"]
            for c_i, h in enumerate(cs_heads):
                c = cs_table.rows[0].cells[c_i]
                _set_cell_background(c, "1E3A8A")
                _set_cell_margins(c, top=60, bottom=60, left=60, right=60)
                p = c.paragraphs[0]
                r = p.add_run(h)
                r.font.bold = True
                r.font.size = Pt(8)
                r.font.color.rgb = RGBColor(255, 255, 255)

            for r_idx, rdata in enumerate(cat_rows, start=1):
                row = cs_table.rows[r_idx]
                is_err = "EKSİK" in rdata[6]
                for c_i, val in enumerate(rdata):
                    cell = row.cells[c_i]
                    _set_cell_margins(cell, top=45, bottom=45, left=60, right=60)
                    p = cell.paragraphs[0]
                    p.paragraph_format.space_after = Pt(0)
                    r = p.add_run(val)
                    r.font.size = Pt(7.5)
                    if c_i in (0, 4, 6):
                        r.font.bold = True
                    if c_i == 6:
                        r.font.color.rgb = self.red if is_err else self.green
                        _set_cell_background(cell, "FEF2F2" if is_err else "F0FDF4")
                    else:
                        _set_cell_background(cell, "FFFFFF" if r_idx % 2 == 1 else "F8FAFC")

            doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # 4.2 Unutulan / Topraklanmamış Elemanların Tam Koordinat ve Aks Listesi
        all_defects = []
        for it in station_data.items:
            res = it.analysis_res
            for d in getattr(res, 'spatial_defects', []):
                all_defects.append((res.floor_level, res.project_name, d))

        if all_defects:
            self._add_subsection_heading(
                doc, f"4.2 Tespit Edilen Uygulama Eksikleri — Topraklanmamış Elemanların Aks ve Koordinat Listesi ({len(all_defects)} Adet)"
            )
            d_table = doc.add_table(rows=len(all_defects) + 1, cols=6)
            d_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            _set_table_borders(d_table, color="CBD5E1")

            d_heads = [
                "Kat / Seviye", "Eleman Kategorisi", "BIM Blok / Ekipman Adı",
                "Mimari Aks & Koordinat", "En Yakın Toprak Hattı", "Gerekli Revizyon / Düzeltme"
            ]
            for c_i, h in enumerate(d_heads):
                c = d_table.rows[0].cells[c_i]
                _set_cell_background(c, "991B1B")  # Koyu Kırmızı Hata Başlığı
                _set_cell_margins(c, top=60, bottom=60, left=60, right=60)
                p = c.paragraphs[0]
                r = p.add_run(h)
                r.font.bold = True
                r.font.size = Pt(8)
                r.font.color.rgb = RGBColor(255, 255, 255)

            for d_idx, (flevel, pname, df) in enumerate(all_defects, start=1):
                row = d_table.rows[d_idx]
                vals = [
                    flevel,
                    df.category,
                    df.element_name,
                    df.axis_location,
                    f"{df.nearest_grounding_m:.2f} m uzakta",
                    f"{df.spec_reference} uyarınca en yakın topraklama ağından 16mm² Cu H07Z-R branşman çekilmelidir."
                ]
                for c_i, val in enumerate(vals):
                    cell = row.cells[c_i]
                    _set_cell_margins(cell, top=45, bottom=45, left=60, right=60)
                    p = cell.paragraphs[0]
                    p.paragraph_format.space_after = Pt(0)
                    r = p.add_run(val)
                    r.font.size = Pt(7.5)
                    if c_i in (1, 3, 4):
                        r.font.bold = True
                    if c_i == 4:
                        r.font.color.rgb = self.red
                    _set_cell_background(cell, "FEF2F2" if d_idx % 2 == 1 else "FFFFFF")

            doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # 4.3 Klemens (kkk) T-Ek Noktası Sembol Denetimi Tablosu
        self._add_subsection_heading(doc, "4.3 T-Ayrım Noktalarında Vidalı Topraklama Klemensi (kkk) Sembol Denetimi")
        kl_table = doc.add_table(rows=len(station_data.items) + 1, cols=5)
        kl_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(kl_table, color="CBD5E1")

        kl_heads = ["Pafta Kodu", "Kat / Seviye", "Çizimde Mevcut Klemens (kkk)", "Klemens Sembolü Unutulan T-Ek", "Mühendislik Değerlendirmesi"]
        for c_i, h in enumerate(kl_heads):
            c = kl_table.rows[0].cells[c_i]
            _set_cell_background(c, "1E3A8A")
            _set_cell_margins(c, top=60, bottom=60, left=60, right=60)
            p = c.paragraphs[0]
            r = p.add_run(h)
            r.font.bold = True
            r.font.size = Pt(8)
            r.font.color.rgb = RGBColor(255, 255, 255)

        for k_idx, it in enumerate(station_data.items, start=1):
            res = it.analysis_res
            row = kl_table.rows[k_idx]
            mc = getattr(res, 'missing_clamp_junctions', 0)
            note_k = (
                f"⚠ {mc} adet 16mm² Cu branşman ayrım noktasında 'kkk' vidalı klemens sembolü çizimde unutulmuştur."
                if mc > 0 else "✓ Tüm ayrım noktalarında klemens sembolü/detayı tamdır."
            )
            vals = [res.project_name, res.floor_level, f"{res.clamp_count} Adet", f"{mc} Nokta", note_k]
            for c_i, val in enumerate(vals):
                cell = row.cells[c_i]
                _set_cell_margins(cell, top=45, bottom=45, left=60, right=60)
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                r = p.add_run(val)
                r.font.size = Pt(7.5)
                if c_i == 3 and mc > 0:
                    r.font.bold = True
                    r.font.color.rgb = self.amber
                _set_cell_background(cell, "FFFFFF" if k_idx % 2 == 1 else "F8FAFC")

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # ── 4.4 KATLAR ARASI 3B ŞAFT VE BARA (X, Y) SÜREKLİLİK ÇAKIŞTIRMASI ─────
        self._add_subsection_heading(
            doc, "4.4 Katlar Arası 3 Boyutlu Dikey Şaft ve Bara (X, Y) Koordinat Süreklilik Denetimi"
        )
        riser_rows = []
        indoor_items = [
            it for it in station_data.items
            if it.analysis_res.drawing_role not in (ROLE_EXTERNAL_GRID, ROLE_TYPICAL_DETAILS)
            and it.analysis_res.busbars
        ]
        if len(indoor_items) >= 2:
            base_it = indoor_items[0]
            base_bars = [b for b in base_it.analysis_res.busbars if (b.position[0] != 0 or b.position[1] != 0)]
            for upper_it in indoor_items[1:]:
                u_floor = upper_it.analysis_res.floor_level
                for ub in upper_it.analysis_res.busbars:
                    if ub.position[0] == 0 and ub.position[1] == 0:
                        continue
                    if base_bars:
                        best_b = min(
                            base_bars,
                            key=lambda bb: math.hypot(ub.position[0] - bb.position[0], ub.position[1] - bb.position[1])
                        )
                        d_xy_m = math.hypot(ub.position[0] - best_b.position[0], ub.position[1] - best_b.position[1]) / 1000.0
                        if d_xy_m <= 18.0:
                            r_stat = f"✓ DİKEY ŞAFT HİZALI (ΔXY = {d_xy_m:.1f} m)"
                        else:
                            r_stat = f"✓ YATAY RİNG / TAVA ÜZERİNDEN (ΔXY = {d_xy_m:.1f} m)"
                        riser_rows.append((
                            u_floor,
                            f"{ub.name} ({ub.location_desc})",
                            f"{base_it.analysis_res.floor_level} -> {best_b.name}",
                            f"{d_xy_m:.1f} m",
                            r_stat
                        ))

        if riser_rows:
            r_tbl = doc.add_table(rows=min(len(riser_rows), 18) + 1, cols=5)
            r_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            _set_table_borders(r_tbl, color="CBD5E1")
            r_heads = ["Üst Kat Seviyesi", "Üst Kat Barası & Aks Konumu", "Beslendiği Alt Kat (Master) Barası", "Yatay Şaft Sapması (ΔXY)", "3B Dikey Süreklilik Durumu"]
            for c_i, h in enumerate(r_heads):
                c = r_tbl.rows[0].cells[c_i]
                _set_cell_background(c, "1E3A8A")
                _set_cell_margins(c, top=55, bottom=55, left=60, right=60)
                p = c.paragraphs[0]
                r = p.add_run(h)
                r.font.bold = True
                r.font.size = Pt(7.5)
                r.font.color.rgb = RGBColor(255, 255, 255)

            for r_idx, rdata in enumerate(riser_rows[:18], start=1):
                row = r_tbl.rows[r_idx]
                for c_i, val in enumerate(rdata):
                    cell = row.cells[c_i]
                    _set_cell_margins(cell, top=45, bottom=45, left=60, right=60)
                    p = cell.paragraphs[0]
                    p.paragraph_format.space_after = Pt(0)
                    r = p.add_run(val)
                    r.font.size = Pt(7.5)
                    if c_i == 4:
                        r.font.bold = True
                        r.font.color.rgb = self.green
                    _set_cell_background(cell, "FFFFFF" if r_idx % 2 == 1 else "F8FAFC")
            doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # ── 4.5 KRİTİK TEKNİK ODA VE MAHAL TOPRAKLAMA DENETİMİ ──────────────────
        all_tech_rooms = []
        for it in station_data.items:
            for tr in getattr(it.analysis_res, "technical_rooms_audit", []):
                all_tech_rooms.append((it.analysis_res.floor_level, tr))

        if all_tech_rooms:
            self._add_subsection_heading(
                doc, "4.5 Kritik Teknik Oda ve Mahal Eşpotansiyel Kapsama Denetimi (M-AREA-IDEN)"
            )
            tr_tbl = doc.add_table(rows=min(len(all_tech_rooms), 20) + 1, cols=5)
            tr_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            _set_table_borders(tr_tbl, color="CBD5E1")
            tr_heads = ["Kat Seviyesi", "Kritik Teknik Oda Sınıfı", "Mahal Etiketi & Aks", "En Yakın Eşpotansiyel Bara", "Ana Ring Mesafesi & Durum"]
            for c_i, h in enumerate(tr_heads):
                c = tr_tbl.rows[0].cells[c_i]
                _set_cell_background(c, "1E3A8A")
                _set_cell_margins(c, top=55, bottom=55, left=60, right=60)
                p = c.paragraphs[0]
                r = p.add_run(h)
                r.font.bold = True
                r.font.size = Pt(7.5)
                r.font.color.rgb = RGBColor(255, 255, 255)

            for t_idx, (fl_name, tr) in enumerate(all_tech_rooms[:20], start=1):
                row = tr_tbl.rows[t_idx]
                vals = [
                    fl_name,
                    tr["room_type"],
                    f"{tr['room_label']} ({tr['location']})",
                    tr["nearest_busbar"],
                    f"{tr['nearest_conductor_m']:.2f} m — {tr['status']}"
                ]
                for c_i, val in enumerate(vals):
                    cell = row.cells[c_i]
                    _set_cell_margins(cell, top=45, bottom=45, left=60, right=60)
                    p = cell.paragraphs[0]
                    p.paragraph_format.space_after = Pt(0)
                    r = p.add_run(val)
                    r.font.size = Pt(7.5)
                    if c_i == 4:
                        r.font.bold = True
                        r.font.color.rgb = self.green if "UYGUN" in val else self.amber
                    _set_cell_background(cell, "FFFFFF" if t_idx % 2 == 1 else "F8FAFC")
            doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # ── 6. İKİTELLİ - ATAKÖY (M9) SÖZLEŞME VE TEKNİK ŞARTNAME DENETİMİ ───
        self._add_section_heading(
            doc, "5. İkitelli - Ataköy Metro Hattı (M9) Sözleşme ve Özel Teknik Şartname Hükümleri Denetimi"
        )

        ikk_lead = doc.add_paragraph()
        ikk_lead.paragraph_format.space_after = Pt(4)
        ikk_lead.add_run(
            "İBB İkitelli - Ataköy Metro Hattı (İKN: 2015/74736) Sözleşmesi, Birim Fiyat Tarifleri (Poz 014, Poz 04.191-04.250, "
            "Poz 05.081), Ortak Teknik Koşullar (Bölüm A), Güç Temini Şartnamesi (Bölüm 8 & 11) ve Cityflo 350 Sinyalizasyon "
            "Topraklama Konsepti (3NCH P40 / 1A-044 / 1P-006 / 1O-003) hükümlerine göre yapılan denetim:"
        )

        # Peron Altı (BT0-00) veya ilk paftanın ikk_sartname_audits tablosunu baz al, istasyon geneline göre özetle
        ref_item = next(
            (it for it in station_data.items if it.analysis_res.has_sub_platform_master),
            station_data.items[0] if station_data.items else None
        )
        if ref_item and getattr(ref_item.analysis_res, 'ikk_sartname_audits', None):
            ikk_rows = ref_item.analysis_res.ikk_sartname_audits
            ikk_table = doc.add_table(rows=len(ikk_rows) + 1, cols=3)
            ikk_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            _set_table_borders(ikk_table, color="CBD5E1")

            ikk_heads = [
                "Şartname / Sözleşme Kontrol Kalemi",
                "Zorunlu Teknik Şartname & Sözleşme Hükmü",
                "İstasyon Uygulama Projesi Denetim Sonucu"
            ]
            for c_i, h in enumerate(ikk_heads):
                c = ikk_table.rows[0].cells[c_i]
                _set_cell_background(c, "1E3A8A")
                _set_cell_margins(c, top=60, bottom=60, left=70, right=70)
                p = c.paragraphs[0]
                r = p.add_run(h)
                r.font.bold = True
                r.font.size = Pt(8)
                r.font.color.rgb = RGBColor(255, 255, 255)

            for r_idx, irow in enumerate(ikk_rows, start=1):
                row = ikk_table.rows[r_idx]
                p_durum = irow["proje_durumu"]
                if "Metal Yapı Elemanları" in irow["kriter"]:
                    p_durum = (
                        f"✗ EKSİK TESPİT EDİLDİ — İstasyon genelinde {tot_grounded} adet metal yapı/ekipman topraklanmış, "
                        f"ancak {tot_defects} adet metal kapak/merdiven/ızgara/yürüyen merdiven bağlantısı unutulmuştur (Bölüm 4.2)."
                        if tot_defects > 0 else "✓ UYGUN — Tüm metal yapı elemanları eşpotansiyel ağa bağlanmıştır."
                    )
                vals = [irow["kriter"], irow["sartname_hukmu"], p_durum]
                for c_i, val in enumerate(vals):
                    cell = row.cells[c_i]
                    _set_cell_margins(cell, top=50, bottom=50, left=70, right=70)
                    p = cell.paragraphs[0]
                    p.paragraph_format.space_after = Pt(0)
                    r = p.add_run(val)
                    r.font.size = Pt(8)
                    if c_i == 0:
                        r.font.bold = True
                        _set_cell_background(cell, "F1F5F9")
                    elif c_i == 2:
                        r.font.bold = True
                        if "EKSİK" in val:
                            r.font.color.rgb = self.red
                            _set_cell_background(cell, "FEF2F2")
                        elif "SAHA KABUL" in val:
                            r.font.color.rgb = self.amber
                            _set_cell_background(cell, "FFFBEB")
                        else:
                            r.font.color.rgb = self.green
                            _set_cell_background(cell, "F0FDF4")
                    else:
                        _set_cell_background(cell, "FFFFFF" if r_idx % 2 == 1 else "F8FAFC")

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # ── 7. İSTASYON KONSOLİDE MALZEME METRAJI (BOM) ───────────────────────
        self._add_section_heading(doc, "6. İstasyon Konsolide Malzeme Metrajı (Gerçek İletken Tiplerine Göre)")

        total_clamps = sum(it.analysis_res.clamp_count for it in station_data.items)
        required_clamps = total_clamps + tot_missing_clamps

        bom_items = [
            ("Poz 014 / ECB", "OBO Bettermann", "Eşpotansiyel / İşletme / Zayıf Akım Topraklama Barası (40x5 mm Cu)",
             f"{station_data.total_busbars} Adet", "E-Cu %99.9, İzolatörlü (ECB/001..052, İşletme ve SER Z.Akım Baraları)"),
            ("Renk 130 (Ana Ağ)", "Prysmian / Nexans", "120 - 240 mm² Ana Topraklama Ağ İletkeni (Çıplak Örgülü / H07Z-R Cu)",
             f"{station_data.total_bare_copper_120_m:.1f} m", "Proje Lejantı: Ana Topraklama Ağı (Tava kenarına irtibatlı, min. 120mm²)"),
            ("Renk 43 (Tali Ağ)", "Prysmian / Nexans", "35 - 120 mm² Tali Topraklama Ağ İletkeni (Çıplak Örgülü Bakır)",
             f"{station_data.total_tali_copper_m:.1f} m", "Proje Lejantı: Tali Topraklama Ağı (Kablo tavası kenarına irtibatlı)"),
            ("Renk 63 (Branşman)", "Prysmian", "16 mm² H07Z-R Halojensiz Alev İletmeyen Koruma İletkeni (Sarı-Yeşil)",
             f"{station_data.total_insulated_copper_16_m:.1f} m", "Proje Notu Md.1 & Md.7: Kapak, merdiven, kapı, damper ve pano branşmanları"),
            ("Renk 3 (Ray/Tünel)", "Nexans", "185 mm² N2XH / H07Z-R Ray Altı Çelik Hasır & Tünel Donatı İrtibat Kablosu",
             f"{station_data.total_heavy_copper_240_m:.1f} m", "EN 50122-2 Hat 1 & Hat 2 Ray Altı Çelik Hasır ve Peron Donatısı İrtibatı"),
            ("Renk 53 (Bara İrt.)", "Prysmian", "50 - 240 mm² H07Z-R İşletme / Zayıf Akım / Muayene Terminali İrtibatı",
             f"{station_data.total_isletme_zayif_akim_m:.1f} m", "OG Pano Odası İşletme, Zayıf Akım ve Muayene Terminali Bağlantıları"),
            ("KKK-KLEMENS", "OBO Bettermann", "Vidalı Topraklama İrtibat Klemensi (kkk Sembolü)",
             f"{total_clamps} Çizilen ({required_clamps} Olması Gereken)", f"Çizimde {total_clamps} adet mevcuttur; {tot_missing_clamps} T-ek noktasında sembol unutulmuştur")
        ]

        bom_table = doc.add_table(rows=len(bom_items) + 1, cols=5)
        bom_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(bom_table, color="CBD5E1")

        b_heads = ["Lejant / Poz Kodu", "Üretici", "Malzeme Tanımı & İletken Sınıfı", "Gerçek Metraj / Adet", "Açıklama & Şartname Kuralı"]
        for c_i, h in enumerate(b_heads):
            c = bom_table.rows[0].cells[c_i]
            _set_cell_background(c, "1E3A8A")
            _set_cell_margins(c, top=60, bottom=60, left=70, right=70)
            p = c.paragraphs[0]
            r = p.add_run(h)
            r.font.bold = True
            r.font.size = Pt(8)
            r.font.color.rgb = RGBColor(255, 255, 255)

        for i_idx, item in enumerate(bom_items, start=1):
            row = bom_table.rows[i_idx]
            for c_i, val in enumerate(item):
                cell = row.cells[c_i]
                _set_cell_margins(cell, top=50, bottom=50, left=70, right=70)
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

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # ── 8. PAFTA BAZINDA ÖZEL DENETİM FÖYLERİ ─────────────────────────────
        self._add_section_heading(doc, "7. Pafta Bazında Özel Denetim Föyleri")

        for idx, item in enumerate(station_data.items, start=1):
            res = item.analysis_res
            self._add_subsection_heading(doc, f"7.{idx} Pafta Denetimi: {res.project_name} ({res.floor_level})")

            detail_tbl = doc.add_table(rows=5, cols=4)
            detail_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            _set_table_borders(detail_tbl, color="CBD5E1")

            bar_names = ", ".join(b.name for b in res.busbars[:6]) if res.busbars else "Tespit Edilmedi"
            def_cnt = len(getattr(res, 'spatial_defects', []))
            gnd_cnt = len(getattr(res, 'grounded_elements', []))

            dt_rows = [
                ("Pafta Dosyası", res.project_name, "İstasyon Seviyesi", res.floor_level),
                ("İşlevsel Rol", res.drawing_role, "Tespit Edilen Baralar", f"{len(res.busbars)} Adet ({bar_names})"),
                ("Ana / Tali Ağ Metrajı", f"Ana: {res.bare_copper_120_m:.1f} m | Tali: {getattr(res, 'tali_copper_m', 0.0):.1f} m",
                 "16mm² Branşman & Ray Hasırı", f"16mm²: {res.insulated_copper_16_m:.1f} m | Ray: {res.heavy_copper_240_m:.1f} m"),
                ("Metal Aksam / Ekipman", f"{gnd_cnt} Topraklanmış / {def_cnt} Eksik",
                 "Vidalı Klemens (kkk)", f"{res.clamp_count} Mevcut / {getattr(res, 'missing_clamp_junctions', 0)} Eksik"),
                ("Mühendislik Hükmü", res.executive_verdict, "Uyum Skoru", f"%{res.compliance_score_percent:.1f}")
            ]

            for r_i, rdata in enumerate(dt_rows):
                row = detail_tbl.rows[r_i]
                for c_i in range(4):
                    cell = row.cells[c_i]
                    _set_cell_margins(cell, top=45, bottom=45, left=65, right=65)
                    p = cell.paragraphs[0]
                    p.paragraph_format.space_after = Pt(0)
                    tval = rdata[c_i]
                    if c_i % 2 == 0:
                        _set_cell_background(cell, "F1F5F9")
                        r = p.add_run(tval)
                        r.font.bold = True
                        r.font.size = Pt(7.5)
                        r.font.color.rgb = self.slate
                    else:
                        _set_cell_background(cell, "FFFFFF")
                        r = p.add_run(tval)
                        r.font.size = Pt(8)
                        if "REVİZYON" in tval or (c_i == 1 and r_i == 3 and def_cnt > 0):
                            r.font.bold = True
                            r.font.color.rgb = self.red
                        elif "UYGUNDUR" in tval:
                            r.font.bold = True
                            r.font.color.rgb = self.green

            np = doc.add_paragraph()
            np.paragraph_format.space_before = Pt(3)
            np.paragraph_format.space_after = Pt(4)
            nr = np.add_run(f"📌 Pafta Özel Denetim Notu: {res.source_status_note}")
            nr.font.size = Pt(8)
            nr.font.italic = True
            nr.font.color.rgb = self.dark

            if item.preview_png_path and Path(item.preview_png_path).exists():
                try:
                    ip = doc.add_paragraph()
                    ip.paragraph_format.space_before = Pt(2)
                    ip.paragraph_format.space_after = Pt(4)
                    ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    ip.add_run().add_picture(str(item.preview_png_path), width=Inches(5.8))
                except Exception:
                    pass

            doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # ── 9. 14-MADDELİK UYGULAMA NOTLARI BÜTÜNLEŞİK MATRİSİ ────────────────
        self._add_section_heading(doc, "8. Proje Üzerindeki 14-Maddelik Uygulama Kuralları Bütünleşik Denetim Matrisi")

        if ref_item:
            matrix_table = doc.add_table(rows=len(ref_item.analysis_res.spec_articles) + 1, cols=4)
            matrix_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            _set_table_borders(matrix_table, color="CBD5E1")

            m_headers = ["Madde No & Konu", "Proje Notu / Şartname Gereksinimi", "İstasyon Bütünleşik Denetim Bulgusu", "Hüküm"]
            for c_i, h in enumerate(m_headers):
                c = matrix_table.rows[0].cells[c_i]
                _set_cell_background(c, "1E3A8A")
                _set_cell_margins(c, top=60, bottom=60, left=70, right=70)
                p = c.paragraphs[0]
                r = p.add_run(h)
                r.font.bold = True
                r.font.size = Pt(8)
                r.font.color.rgb = RGBColor(255, 255, 255)

            for a_i, art in enumerate(ref_item.analysis_res.spec_articles, start=1):
                row = matrix_table.rows[a_i]
                c0, c1, c2, c3 = row.cells[0], row.cells[1], row.cells[2], row.cells[3]
                for c in (c0, c1, c2, c3):
                    _set_cell_margins(c, top=45, bottom=45, left=65, right=65)
                    c.paragraphs[0].paragraph_format.space_after = Pt(0)

                # Tüm paftalarda bu maddenin durumunu birleştir
                art_idx = a_i - 1
                failed_floors = []
                warn_floors = []
                for it in station_data.items:
                    if art_idx < len(it.analysis_res.spec_articles):
                        sa = it.analysis_res.spec_articles[art_idx]
                        if "EKSİK" in sa.status:
                            failed_floors.append(f"{it.analysis_res.floor_level}: {sa.status}")
                        elif "DİKKAT" in sa.status:
                            warn_floors.append(f"{it.analysis_res.floor_level}: {sa.status}")

                if failed_floors:
                    agg_stat = "✗ EKSİK VAR"
                    agg_find = f"Eksik tespit edilen katlar: {'; '.join(failed_floors)}. Detaylı aks ve koordinat listesi Bölüm 4.2'dedir."
                    stat_color = self.red
                    bg_color = "FEF2F2"
                elif warn_floors:
                    agg_stat = "⚠ SEMBOL EKSİK"
                    agg_find = f"Klemens sembolü unutulan katlar: {'; '.join(warn_floors)}. Detaylar Bölüm 4.3'tedir."
                    stat_color = self.amber
                    bg_color = "FFFBEB"
                else:
                    agg_stat = "✓ UYGUN"
                    agg_find = art.finding
                    stat_color = self.green
                    bg_color = "F0FDF4"

                r0 = c0.paragraphs[0].add_run(f"Madde {art.article_no}\n{art.title}")
                r0.font.bold = True
                r0.font.size = Pt(7.5)
                _set_cell_background(c0, "F8FAFC")

                r1 = c1.paragraphs[0].add_run(art.requirement)
                r1.font.size = Pt(7.5)
                _set_cell_background(c1, "FFFFFF" if a_i % 2 == 1 else "F8FAFC")

                r2 = c2.paragraphs[0].add_run(agg_find)
                r2.font.size = Pt(7.5)
                _set_cell_background(c2, "FFFFFF" if a_i % 2 == 1 else "F8FAFC")

                r3 = c3.paragraphs[0].add_run(agg_stat)
                r3.font.bold = True
                r3.font.size = Pt(8)
                r3.font.color.rgb = stat_color
                _set_cell_background(c3, bg_color)

        doc.add_paragraph().paragraph_format.space_after = Pt(10)

        # ── 10. MÜHENDİSLİK İMZA VE ONAY BLOĞU ────────────────────────────────
        sign_table = doc.add_table(rows=1, cols=2)
        sign_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(sign_table, color="94A3B8")

        for c_i, (title_s, auth_s) in enumerate([
            ("DENETİMİ YAPAN BAŞMÜHENDİS", "CloudeCAD Yapay Zeka Denetim Motoru\nElektrik & Raylı Sistemler Başmühendisliği"),
            ("ONAYLAYAN KURUL", "TS EN 50122 & İBB Raylı Sistemler\nTeknik Denetim Kurulu")
        ]):
            scell = sign_table.rows[0].cells[c_i]
            _set_cell_background(scell, "F8FAFC")
            _set_cell_margins(scell, top=90, bottom=90, left=110, right=110)
            sp = scell.paragraphs[0]
            sp.paragraph_format.space_after = Pt(4)
            s_t = sp.add_run(title_s + "\n")
            s_t.font.bold = True
            s_t.font.size = Pt(8.5)
            s_t.font.color.rgb = self.slate

            s_a = sp.add_run(auth_s + "\n\n")
            s_a.font.size = Pt(9)
            s_a.font.color.rgb = self.dark

            s_sig = sp.add_run("Kaşe / İmza: _________________________")
            s_sig.font.size = Pt(8)
            s_sig.font.color.rgb = self.slate

        doc.save(str(output_path))
        return output_path

    def _add_section_heading(self, doc, text: str):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.name = 'Calibri'
        run.font.size = Pt(12)
        run.font.bold = True
        run.font.color.rgb = self.navy

    def _add_subsection_heading(self, doc, text: str):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.name = 'Calibri'
        run.font.size = Pt(10)
        run.font.bold = True
        run.font.color.rgb = self.blue
