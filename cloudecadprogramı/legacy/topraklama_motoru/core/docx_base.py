"""
CloudeCAD — Ortak Kurumsal Microsoft Word (.docx) Raporlama Çekirdeği
=====================================================================
Tüm Word raporlayıcıların (Bina, Metro Tekil, Metro Konsolide, Endüstriyel/Trafo)
ortak kullandığı XML tablo kenarlığı, hücre arka planı, hücre iç boşluğu,
bilgi kutusu (callout box) ve kurumsal tipografi metotlarını tek merkezde toplar.
"""

from docx.shared import Pt, RGBColor
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls


class CorporateDocxBase:
    """
    Kurumsal Word raporları için ortak XML ve stil yardımcı sınıfı.
    """

    # Kurumsal Renk Paleti
    COLOR_NAVY = RGBColor(15, 23, 42)        # #0F172A — Ana Başlıklar
    COLOR_PRIMARY = RGBColor(30, 58, 138)    # #1E3A8A — Bölüm Başlıkları
    COLOR_ACCENT = RGBColor(3, 105, 161)     # #0369A1 — Alt Başlık / Vurgu
    COLOR_TEXT = RGBColor(30, 41, 59)        # #1E293B — Gövde Metni
    COLOR_MUTED = RGBColor(100, 116, 139)    # #64748B — Açıklama / Altbilgi
    COLOR_SUCCESS = RGBColor(21, 128, 61)    # #15803D — UYGUN (Yeşil)
    COLOR_WARNING = RGBColor(180, 83, 9)     # #B45309 — UYARI / NOT (Kehribar)
    COLOR_DANGER = RGBColor(185, 28, 28)     # #B91C1C — KRİTİK / EKSİK (Kırmızı)

    HEX_HEADER_BG = "1E3A8A"                 # Tablo Başlığı Koyu Lacivert
    HEX_SUBHEADER_BG = "0F172A"              # İstasyon / Paket Özet Başlığı
    HEX_ZEBRA_BG = "F8FAFC"                  # Zebra Satır Açık Gri
    HEX_SUCCESS_BG = "DCFCE7"                # Uygun Hücre Açık Yeşil
    HEX_WARNING_BG = "FEF3C7"                # Uyarı Hücre Açık Sarı
    HEX_DANGER_BG = "FEE2E2"                 # Hata Hücre Açık Kırmızı
    HEX_BORDER = "CBD5E1"                    # İnce Gri Kenarlık

    def _set_cell_background(self, cell, hex_color: str) -> None:
        """Tablo hücresinin arka plan rengini ayarlar."""
        shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
        cell._tc.get_or_add_tcPr().append(shading_elm)

    def _set_cell_margins(self, cell, top=100, bottom=100, left=140, right=140) -> None:
        """Hücre içi boşlukları (padding) dxa cinsinden ayarlar."""
        tcPr = cell._tc.get_or_add_tcPr()
        tcMar = OxmlElement('w:tcMar')
        for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
            node = OxmlElement(f'w:{m}')
            node.set(qn('w:w'), str(val))
            node.set(qn('w:type'), 'dxa')
            tcMar.append(node)
        tcPr.append(tcMar)

    def _set_table_borders(self, table, color="CBD5E1", sz="4", val="single") -> None:
        """Tabloya zarif kurumsal kenarlıklar ekler."""
        tblPr = table._tbl.tblPr
        borders = parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            f'<w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'<w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'<w:left w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'<w:right w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'<w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'<w:insideV w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'</w:tblBorders>'
        )
        tblPr.append(borders)

    def _add_section_header(self, doc, number_str: str, title_str: str):
        """Numaralı, alt çizgili kurumsal bölüm başlığı oluşturur."""
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.keep_with_next = True

        pPr = p._p.get_or_add_pPr()
        pBdr = parse_xml(
            f'<w:pBdr {nsdecls("w")}>'
            f'<w:bottom w:val="single" w:sz="12" w:space="4" w:color="1E3A8A"/>'
            f'</w:pBdr>'
        )
        pPr.append(pBdr)

        r_num = p.add_run(f"{number_str}. ")
        r_num.bold = True
        r_num.font.size = Pt(12.5)
        r_num.font.color.rgb = self.COLOR_ACCENT

        r_title = p.add_run(title_str.upper())
        r_title.bold = True
        r_title.font.size = Pt(12.5)
        r_title.font.color.rgb = self.COLOR_PRIMARY
        return p

    def _add_callout_box(self, doc, title: str, text: str, bg_hex="F1F5F9", border_hex="1E3A8A") -> None:
        """Vurgulu mühendislik bilgi/not kutusu ekler."""
        tbl = doc.add_table(rows=1, cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = tbl.cell(0, 0)
        self._set_cell_background(cell, bg_hex)
        self._set_cell_margins(cell, top=130, bottom=130, left=180, right=180)

        tcPr = cell._tc.get_or_add_tcPr()
        borders = parse_xml(
            f'<w:tcBorders {nsdecls("w")}>'
            f'<w:left w:val="single" w:sz="24" w:space="0" w:color="{border_hex}"/>'
            f'<w:top w:val="none"/>'
            f'<w:right w:val="none"/>'
            f'<w:bottom w:val="none"/>'
            f'</w:tcBorders>'
        )
        tcPr.append(borders)

        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        rt = p.add_run(title + "\n")
        rt.bold = True
        rt.font.size = Pt(9.5)
        rt.font.color.rgb = self.COLOR_PRIMARY

        rb = p.add_run(text)
        rb.font.size = Pt(9.0)
        rb.font.color.rgb = self.COLOR_TEXT
        doc.add_paragraph().paragraph_format.space_after = Pt(2)
