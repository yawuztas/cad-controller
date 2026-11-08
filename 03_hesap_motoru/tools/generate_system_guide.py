# -*- coding: utf-8 -*-
"""
CloudeCAD v3.0 - Sistem Mimarisi, Kod Haritası ve Çalışma Prensipleri Ana Rehberi Üreteci
========================================================================================
Bu betik sistemin eksiksiz mimari dokümantasyonunu hem profesyonel Microsoft Word (.docx)
hem de Markdown (.md) formatında üretir.
"""

import sys
import os
from pathlib import Path

# Windows konsolunda UTF-8 karakter uyumluluğu
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

DOCX_OUTPUT_PATH = ROOT_DIR / "CLOUDECAD_SISTEM_REHBERI.docx"
MD_OUTPUT_PATH = ROOT_DIR / "CLOUDECAD_SISTEM_REHBERI.md"

COLOR_NAVY = RGBColor(11, 37, 69)       # #0B2545
COLOR_STEEL = RGBColor(19, 64, 116)     # #134074
COLOR_ACCENT = RGBColor(0, 122, 204)    # #007ACC
COLOR_TEXT = RGBColor(30, 30, 30)       # #1E1E1E
COLOR_MUTED = RGBColor(100, 110, 120)   # #646E78


def set_cell_background(cell, fill_hex: str):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)


def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)


def add_callout_box(doc, text: str, title: str = "ÖNEMLİ MÜHENDİSLİK PRENSİBİ", border_color: str = "007ACC", bg_color: str = "F4F6F8"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, bg_color)
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)

    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:left w:val="single" w:sz="24" w:space="0" w:color="{border_color}"/>'
        f'<w:top w:val="none"/>'
        f'<w:bottom w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)

    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.15
    run_t = p.add_run(f"📌 {title}\n")
    run_t.bold = True
    run_t.font.name = "Calibri"
    run_t.font.size = Pt(10.5)
    run_t.font.color.rgb = COLOR_STEEL

    run_body = p.add_run(text)
    run_body.font.name = "Calibri"
    run_body.font.size = Pt(9.5)
    run_body.font.color.rgb = COLOR_TEXT

    p_after = doc.add_paragraph()
    p_after.paragraph_format.space_before = Pt(0)
    p_after.paragraph_format.space_after = Pt(4)


def add_code_block(doc, code_text: str):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, "F8F9FA")
    set_cell_margins(cell, top=100, bottom=100, left=150, right=150)

    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:left w:val="single" w:sz="8" w:space="0" w:color="D0D5DD"/>'
        f'<w:top w:val="single" w:sz="8" w:space="0" w:color="D0D5DD"/>'
        f'<w:bottom w:val="single" w:sz="8" w:space="0" w:color="D0D5DD"/>'
        f'<w:right w:val="single" w:sz="8" w:space="0" w:color="D0D5DD"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)

    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.05
    run = p.add_run(code_text)
    run.font.name = "Consolas"
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor(40, 50, 60)

    p_after = doc.add_paragraph()
    p_after.paragraph_format.space_before = Pt(0)
    p_after.paragraph_format.space_after = Pt(4)


def style_table(tbl, col_widths, headers, data_rows):
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER

    hdr_cells = tbl.rows[0].cells
    for i, h_txt in enumerate(headers):
        hdr_cells[i].text = h_txt
        set_cell_background(hdr_cells[i], "0B2545")
        set_cell_margins(hdr_cells[i], top=120, bottom=120, left=120, right=120)
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for r in p.runs:
            r.bold = True
            r.font.name = "Calibri"
            r.font.size = Pt(9.5)
            r.font.color.rgb = RGBColor(255, 255, 255)

    for r_idx, row in enumerate(data_rows):
        row_cells = tbl.add_row().cells
        bg_color = "F9FBFC" if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, val in enumerate(row):
            row_cells[c_idx].text = str(val)
            set_cell_background(row_cells[c_idx], bg_color)
            set_cell_margins(row_cells[c_idx], top=80, bottom=80, left=120, right=120)
            p = row_cells[c_idx].paragraphs[0]
            for r in p.runs:
                r.font.name = "Calibri"
                r.font.size = Pt(9.0)
                r.font.color.rgb = COLOR_TEXT

    for row in tbl.rows:
        for idx, width in enumerate(col_widths):
            row.cells[idx].width = width
            tcPr = row.cells[idx]._tc.get_or_add_tcPr()
            borders = parse_xml(
                f'<w:tcBorders {nsdecls("w")}>'
                f'<w:left w:val="single" w:sz="4" w:space="0" w:color="E0E4E8"/>'
                f'<w:top w:val="single" w:sz="4" w:space="0" w:color="E0E4E8"/>'
                f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="E0E4E8"/>'
                f'<w:right w:val="single" w:sz="4" w:space="0" w:color="E0E4E8"/>'
                f'</w:tcBorders>'
            )
            tcPr.append(borders)


def add_heading_1(doc, text):
    h = doc.add_paragraph()
    h.paragraph_format.space_before = Pt(16)
    h.paragraph_format.space_after = Pt(6)
    h.paragraph_format.keep_with_next = True
    r = h.add_run(text)
    r.bold = True
    r.font.name = "Segoe UI"
    r.font.size = Pt(15.0)
    r.font.color.rgb = COLOR_NAVY
    return h


def add_heading_2(doc, text):
    h = doc.add_paragraph()
    h.paragraph_format.space_before = Pt(12)
    h.paragraph_format.space_after = Pt(4)
    h.paragraph_format.keep_with_next = True
    r = h.add_run(text)
    r.bold = True
    r.font.name = "Segoe UI"
    r.font.size = Pt(12.5)
    r.font.color.rgb = COLOR_STEEL
    return h


def add_heading_3(doc, text):
    h = doc.add_paragraph()
    h.paragraph_format.space_before = Pt(8)
    h.paragraph_format.space_after = Pt(3)
    h.paragraph_format.keep_with_next = True
    r = h.add_run(text)
    r.bold = True
    r.font.name = "Segoe UI"
    r.font.size = Pt(10.5)
    r.font.color.rgb = COLOR_ACCENT
    return h


def add_body_p(doc, text, bold_prefix="", space_after=4):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.bold = True
        r_pre.font.name = "Calibri"
        r_pre.font.size = Pt(10.0)
        r_pre.font.color.rgb = COLOR_TEXT
    r = p.add_run(text)
    r.font.name = "Calibri"
    r.font.size = Pt(10.0)
    r.font.color.rgb = COLOR_TEXT
    return p


def add_bullet_p(doc, text, bold_prefix=""):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.bold = True
        r_pre.font.name = "Calibri"
        r_pre.font.size = Pt(9.5)
        r_pre.font.color.rgb = COLOR_TEXT
    r = p.add_run(text)
    r.font.name = "Calibri"
    r.font.size = Pt(9.5)
    r.font.color.rgb = COLOR_TEXT
    return p


def generate_documents():
    print(f"Creating Document: {DOCX_OUTPUT_PATH.name}")
    doc = docx.Document()

    # Sayfa Yapısı: Kenar Boşlukları 2.0 cm (0.78 inç)
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)
        section.page_width = Inches(8.27)   # A4
        section.page_height = Inches(11.69) # A4

        # Üst ve Alt Bilgi
        header = section.header
        hp = header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hrun = hp.add_run("CloudeCAD v3.0 — Sistem Mimarisi, Kod Haritası ve Çalışma Prensipleri Rehberi")
        hrun.font.name = "Calibri"
        hrun.font.size = Pt(8.0)
        hrun.font.color.rgb = COLOR_MUTED

        footer = section.footer
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        frun = fp.add_run("Sayfa Alt Bilgisi | Tek Doğruluk Kaynağı (Single Source of Truth) | Gizli & Mühendislik Dokümantasyonu")
        frun.font.name = "Calibri"
        frun.font.size = Pt(8.0)
        frun.font.color.rgb = COLOR_MUTED

    # --------------------------------------------------------------------------
    # BAŞLIK BLOĞU
    # --------------------------------------------------------------------------
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(12)
    title_p.paragraph_format.space_after = Pt(2)
    r_title = title_p.add_run("CloudeCAD v3.0")
    r_title.bold = True
    r_title.font.name = "Segoe UI"
    r_title.font.size = Pt(24.0)
    r_title.font.color.rgb = COLOR_NAVY

    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_before = Pt(0)
    sub_p.paragraph_format.space_after = Pt(10)
    r_sub = sub_p.add_run("Sistem Mimarisi, Kod Haritası ve Çalışma Prensipleri Ana Rehberi (SSOT)")
    r_sub.font.name = "Calibri"
    r_sub.font.size = Pt(13.0)
    r_sub.font.color.rgb = COLOR_STEEL

    # Metadata Tablosu
    meta_tbl = doc.add_table(rows=1, cols=4)
    meta_headers = ["Proje Sürümü", "Belge Türü", "Tarih", "Kapsam"]
    meta_rows = [["v3.0 Gold Release (Healer Katmanı Dahil)", "Tek Doğruluk Kaynağı (SSOT)", "01 Kasım 2026", "Metro İstasyonları & Bina Tesisat Projeleri"]]
    style_table(meta_tbl, [Inches(1.5), Inches(2.0), Inches(1.2), Inches(2.0)], meta_headers, meta_rows)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # --------------------------------------------------------------------------
    # BÖLÜM 1: GİRİŞ VE BELGENİN AMACI
    # --------------------------------------------------------------------------
    add_heading_1(doc, "1. Giriş ve Belgenin Amacı (Single Source of Truth)")
    add_body_p(
        doc,
        "Bu doküman, CloudeCAD v3.0 CAD Odaklı (DXF/DWG) Elektrik ve Raylı Sistem Proje Denetim ve Onarım Platformunun "
        "tüm mimarisini, veri modellerini, harici araç bağımlılıklarını, dosya ve fonksiyon ilişkilerini "
        "ve mühendislik algoritmalarını tek bir merkezde toplayan resmi mimari başvuru kaynağıdır (Single Source of Truth).",
    )
    add_callout_box(
        doc,
        "BU BELGENİN TEMEL VAROLUŞ AMACI:\n"
        "Gelecekteki her yeni konuşmada, her yapay zeka (YZ) oturumunda veya projeye dahil olan yeni mühendislerde "
        "binlerce satırlık kod tabanını baştan sona tarama zorunluluğunu ortadan kaldırmaktır. "
        "Sisteme yeni bir kural, yeni bir CAD filtresi veya yeni bir hesaplama modülü eklendiğinde doğrudan "
        "bu Word dokümanı açılacak, mevcut durum doğrulanacak ve güncellemeler buraya işlenecektir.",
        title="YAPAY ZEKA VE GELİŞTİRİCİLER İÇİN ÇALIŞMA PROTOKOLÜ",
        border_color="0B2545",
        bg_color="F0F4F8"
    )

    # --------------------------------------------------------------------------
    # BÖLÜM 2: SİSTEMİN TEMEL ÇALIŞMA MANTIĞI VE 5 TEMEL PRENSİP
    # --------------------------------------------------------------------------
    add_heading_1(doc, "2. Sistemin Temel Çalışma Mantığı ve 5 Mühendislik Prensibi")
    add_body_p(
        doc,
        "CloudeCAD, geleneksel kurallı yazılımlardan farklı olarak gerçek şantiye ve as-built projelerindeki "
        "çizim varyasyonlarını, eksik verileri ve isimlendirme farklılıklarını yönetebilen deterministik bir motordur. "
        "Platform beş katı mühendislik ilkesi üzerine inşa edilmiştir:"
    )

    add_heading_2(doc, "2.1. Sıfır Varsayım İlkesi (Zero-Assumption Engineering)")
    add_body_p(
        doc,
        "Bir elektrik projesinde çizimde açıkça yazmayan bir kablo kesiti (örn: 3x2.5), sigorta değeri (örn: 16A), "
        "cihaz gücü veya hat mesafesi asla varsayılarak hesap tablosuna enjekte edilmez. "
        "Sistem veri kaynağını (Data Source Provenance) dört seviyede izler:"
    )
    add_bullet_p(doc, "Çizimdeki blok özniteliğinden (ATTRIB), kablo etiketinden veya tablodan birebir okundu. Güven Skoru: 1.0 (%100).", "EXPLICIT (Kesin Kanıt): ")
    add_bullet_p(doc, "Sembol adı veya katmandan çıkarıldı (örn: 'LED_36W' bloğundan 36W alınması). Güven Skoru: 0.85 (%85).", "PARTIAL_EXPLICIT: ")
    add_bullet_p(doc, "Çizimde güç yazılmadığı için kural paketindeki standart linye gücü kullanıldı. Rapor Güven Seviyesi 'MUHTEMEL (TAHMİNİ YÜK)' olarak işaretlenir. Güven Skoru: 0.70 (%70).", "ESTIMATED_DEFAULT: ")
    add_bullet_p(doc, "Kablo kesiti veya güzergah çizimde hiç yok. Otomatik kesit atanmaz; devre 'VERİ_YETERSİZ' statüsüne alınır ve Belirsizlik Listesine (Uncertainty Review List) eklenir. Güven Skoru: 0.0 (%0).", "MISSING (Eksik Veri): ")

    add_heading_2(doc, "2.2. Kanıta Dayalı Sembol Triyajı (Evidence-Based Symbol Triage)")
    add_body_p(
        doc,
        "AutoCAD projelerinde sıkça karşılaşılan anonim bloklar (A$C..., *U... vb.) doğrudan silinmez veya "
        "tamamen mimari tefriş kabul edilerek elenmez. SymbolTriage motoru her blok için 4 kanıt katmanını inceler:"
    )
    add_bullet_p(doc, "Blok mimari XREF içinde veya MOBILYA/TEFRIS katmanında ve yakınında hiçbir elektrik sembolü/yazısı yoksa 'IGNORED_ARCHITECTURAL' olarak filtrelenir ve raporda sayısal olarak özetlenir.", "1. Mimari Kanıt: ")
    add_bullet_p(doc, "Blok elektrik katmanındaysa (E-POWER, 00-AYDINLATMA vb.) veya yakın çevresinde (yakın elektrik sembolü için 1000, yakın elektrik yazısı için 600 çizim birimi) elektrik sembolü/etiketi varsa silinmez; 'UNCERTAIN_ELECTRICAL' statüsüne alınarak mühendis incelemesine sunulur.", "2. Elektrik Katmanı Kanıtı: ")
    add_bullet_p(doc, "Ne mimari ne de elektrik kanıtı bulunamayan bloklar 'UNCLASSIFIED' statüsünde Belirsizlik Listesinde tutulur.", "3. Kanıtsızlık Durumu: ")
    add_bullet_p(doc, "Bir blok hem mimari katmanda olup hem de bir aydınlatma armatürünün tam yanındaysa elektrik izi ağır basar ve blok asla silinmez.", "4. Çelişki Yönetimi: ")

    add_heading_2(doc, "2.3. Kademeli Eşleştirme (Graduated / Tiered Matching)")
    add_body_p(
        doc,
        "Raylı sistem ve büyük bina projelerinde kuvvetli akım dağıtım panoları ile topraklama paftaları, "
        "kablo kanalları ve kolon şemaları arasında birebir metin eşleşmesi nadiren görülür. "
        "CrossSheetReconciliationEngine üç kademeli eşleştirme uygular:"
    )
    add_bullet_p(doc, "Pano etiketinin normalize hali topraklama etiketleri veya parçalarıyla birebir eşleşir (örn: S19MCC301 == S19MCC301). Güven: 1.0 (KESİN).", "Tier 1 — Birebir & Normalize Eşleşme: ")
    add_bullet_p(doc, "Topraklama paftasındaki kompozit bağlantı etiketleri (örn: 'TS19LVS401/S19MCC301/01') alt bileşenlerine parçalanır; panonun çekirdek kodu ('MCC301' veya 'LVS401') ile eşleştirilir. Güven: 0.85-0.90 (YÜKSEK).", "Tier 2 — Çekirdek Kod & Alt Parça Ayrıştırma: ")
    add_bullet_p(doc, "Pano kodunun mahal numarası ile o katın Eşpotansiyel Barası (örn: S19/ECB/051) mahal bazında eşleştirilir. Güven: 0.80.", "Tier 3 — Kat / Mahal ECB İrtibatı: ")

    add_heading_2(doc, "2.4. Şiddetin Kanıta Bağlanması (Evidence-Based Severity & Scope Handling)")
    add_body_p(
        doc,
        "Denetim motoru girdi kapsamı sınırlılığı ile gerçek mühendislik hatalarını birbirinden ayırır:"
    )
    add_bullet_p(doc, "Kullanıcı 5 paftalık kısmi bir set yüklediğinde, kuvvetli akım panosunun bulunduğu katın PS-17 topraklama paftası analiz setine hiç verilmemişse bu bir tasarım hatası değil, girdi kapsamı sınırlılığıdır. Asla CRITICAL veya WARNING üretilmez; UncertaintyItem ('UNC-GRND-SHEET-MISSING') üretilerek durum 'İNCELEME_GEREKLİ' (%50 güven) olarak işaretlenir.", "Durum A (Kısmi Set Koruması): ")
    add_bullet_p(doc, "O kata ait topraklama paftası analiz setinde mevcut olmasına rağmen panonun topraklama irtibat kodu bulunamıyorsa; isimlendirme varyasyonu ihtimali nedeniyle bulgu CRITICAL değil, WARNING (Güven: %70, MUHTEMEL) olarak üretilir.", "Durum B (Mevcut Paftada Bulunamama): ")
    add_bullet_p(doc, "Açıkça çizilmiş ve kanıtlanmış kural ihlallerinde (örn: TS HD 60364-4-43 Madde 433.1 uyarınca 4x4 mm² kabloya 32A sigorta ve 25A KAK takılması) bulgu CRITICAL (%100 KESİN) olarak raporlanır.", "Durum C (Doğrudan Standart İhlali): ")

    add_heading_2(doc, "2.5. İstasyon Kodu ve Antet Hiyerarşisi")
    add_body_p(
        doc,
        "Projeler kopyala-yapıştır ile çoğaltıldığında çizim içinde eski istasyonlardan kalma metinler kalabilir. "
        "Sistem istasyon kimliğini kesin bir öncelik hiyerarşisi ile belirler:\n"
        "1. Öncelik: İstasyon Klasör Adı (Örn: M09-S24_Cobancesme)\n"
        "2. Öncelik: Pafta Dosya Adı (Örn: AG-USK-M09-S24-000-99-TL-02-A-T-2I-001.dwg)\n"
        "3. Öncelik: DWG içi blok ve antet metinleri.\n"
        "Eğer dosya adı S24 olduğu halde pafta başlığında S28 Mimar Sinan yazıyorsa sistem istasyonu S24 kabul eder "
        "ve 'REC-STATION-TITLE-MISMATCH' mühendislik uyarısını otomatik raporlar."
    )

    # --------------------------------------------------------------------------
    # BÖLÜM 3: KULLANILAN HARİCİ PROGRAMLAR VE SİSTEM BAĞIMLILIKLARI
    # --------------------------------------------------------------------------
    add_heading_1(doc, "3. Kullanılan Harici Programlar ve Sistem Bağımlılıkları")
    add_body_p(
        doc,
        "CloudeCAD v3.0, yerel AutoCAD kurulumlarının güçlü headless araçlarını ve arka plan servislerini entegre biçimde kullanır:"
    )

    ext_headers = ["Harici Araç / Çevre", "Sistemdeki Yolu / Türü", "Çalışma Mantığı ve Entegrasyonu"]
    ext_rows = [
        [
            "AutoCAD Core Console\n(accoreconsole.exe)",
            r"C:\Program Files\Autodesk\AutoCAD 20XX\accoreconsole.exe",
            "Autodesk'in GUI'siz çalışan ultra-hızlı konsol motorudur. Script üzerinden 'FILEDIA 0 -> _AUDIT _Y -> _DXFOUT dosya 16 -> _QUIT _Y' "
            "komut dizisini çalıştırır. Bozuk BTR ve Dictionary nesnelerini onararak eksiksiz ASCII DXF çıktısı üretir."
        ],
        [
            "AutoCAD COM Automation\n(win32com.client)",
            "AutoCAD.Application ActiveX / COM",
            "Core Console bulunamadığında veya özel nesne kilitlenmelerinde ikincil yedek dönüştürücü olarak devreye girer. "
            "Arka planda görünmez (Visible=False) bir AutoCAD örneği açarak Audit ve DXFOUT uygular."
        ],
        [
            "Merkezi DXF Önbelleği\n(.dxf_cache/)",
            r"D:\autocad projesi\.dxf_cache",
            "Tüm DWG dönüşümleri '{safe_stem}_{st_size}_{st_mtime}.dxf' hash formatında merkezi önbellekte saklanır. "
            "Her okumada dosya sonundaki 'EOF' ve 'ENDSEC' etiketleri doğrulanır; yarım kalmış dosyalar otomatik tespit edilip baştan onarılır."
        ],
        [
            "Python 3.11 Sanal Ortamı\n(venv)",
            r"D:\autocad projesi\venv",
            "İzole mühendislik kütüphanelerini barındıran çalışma ortamı. Tüm CLI betikleri ve test paketleri bu yorumlayıcı üzerinden çalışır."
        ]
    ]
    ext_tbl = doc.add_table(rows=1, cols=3)
    style_table(ext_tbl, [Inches(1.8), Inches(2.2), Inches(3.2)], ext_headers, ext_rows)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # --------------------------------------------------------------------------
    # BÖLÜM 4: KULLANILAN KÜTÜPHANELER VE ROLLERİ
    # --------------------------------------------------------------------------
    add_heading_1(doc, "4. Kullanılan Python Kütüphaneleri ve Fonksiyonları")
    add_body_p(
        doc,
        "CloudeCAD çekirdeğinde yer alan üçüncü taraf açık kaynak kütüphaneler ve üstlendikleri mühendislik görevleri aşağıda listelenmiştir:"
    )

    lib_headers = ["Kütüphane", "Sürüm", "İçe Aktarıldığı Modüller", "Mühendislik Fonksiyonu ve Rolü"]
    lib_rows = [
        [
            "ezdxf",
            ">=1.3.0",
            "core/cad/reader.py\ncore/topology/route_builder.py",
            "AutoCAD DXF dosyalarını okur; ModelSpace ve PaperSpace varlıklarını (INSERT, LINE, LWPOLYLINE, TEXT, MTEXT, ATTRIB, DIMENSION) parse eder. Not: DWG->DXF dönüştürücü (dxf_converter.py) ezdxf kullanmaz; accoreconsole/COM subprocess çalıştırır."
        ],
        [
            "shapely",
            ">=2.0.0",
            "core/cad/geometry.py\ncore/cad/frame_detector.py\ncore/cad/triage.py",
            "2D poligon kesişimleri (intersection), içeren alanlar (contains), Bounding Box hesapları, iç içe pafta sınırları ve semboller arası mesafe ölçümü."
        ],
        [
            "networkx",
            ">=3.3",
            "core/topology/route_builder.py\ncore/topology/circuit_resolver.py",
            "Kablo güzergahları ve devre topolojisi için graf teorisi (Graph / MultiGraph). Minimum Spanning Tree (MST) ile yaklaşık kablo boyu hesabı."
        ],
        [
            "python-docx",
            ">=1.2.0",
            "tools/generate_system_guide.py\nlegacy/*/docx_reporter.py",
            "Microsoft Word (.docx) formatında resmi denetim raporları, mühendislik kılavuzları ve dokümantasyon üretimi."
        ],
        [
            "openpyxl & xlrd",
            ">=3.1.0\n>=2.0.1",
            "legacy/yukleme_cetveli\nlegacy/topraklama_motoru",
            "Excel formatındaki pano yükleme cetvellerini (.xlsx / .xls) okuma (yalnızca v1.0 legacy modüller). NOT: v2.0 çekirdek denetim motoru Excel okumaz; tüm linye verisi çizimden (DXF) alınır."
        ],
        [
            "numpy",
            ">=1.26.0",
            "legacy/superpose_motoru",
            "Süperpoze çakışma analizinde sayısal matris işlemleri (legacy modül). v2.0 elektrik hesaplayıcıları (electrical_calc.py) saf Python'dır; numpy kullanmaz."
        ],
        [
            "matplotlib",
            ">=3.9.0",
            "legacy/superpose_motoru\nlegacy/topraklama_motoru",
            "Kuvvetli akım ve topraklama paftalarının çakışma planları, koordinasyon haritaları ve redline PNG görselleştirmeleri (legacy modüller)."
        ],
        [
            "PyYAML",
            ">=6.0",
            "core/rules/rule_engine.py",
            "YAML kural paketlerinin (turkey_bina.yaml / ibb_metro.yaml) yüklenmesi; yönetmelik eşiklerinin koddan ayrılması (gerçek tek doğruluk kaynağı kural dosyalarıdır)."
        ],
        [
            "pywin32 (win32com)",
            ">=306",
            "common/dxf_converter.py",
            "Windows ActiveX ve AutoCAD COM Automation arayüzü ile çizim denetimi ve dışa aktarma kontrolü."
        ],
        [
            "pytest",
            ">=9.1.0",
            "tests/test_reference_projects.py",
            "13 Altın Referans Testinin (Gold-Standard Test Suite) regresyonsuz ve deterministik biçimde otomatik doğrulanması."
        ]
    ]
    lib_tbl = doc.add_table(rows=1, cols=4)
    style_table(lib_tbl, [Inches(1.2), Inches(0.8), Inches(2.2), Inches(3.0)], lib_headers, lib_rows)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # --------------------------------------------------------------------------
    # BÖLÜM 5: MİMARİ KOD HARİTASI (HANGİ DOSYA NEREDE, NEYE BAĞLI?)
    # --------------------------------------------------------------------------
    add_heading_1(doc, "5. Kod Mimarisi ve Dosya Haritası (Hangi Kod Nerede, Neye Bağlı?)")
    add_body_p(
        doc,
        "Proje dizini modüler, katmanlı bir mimariye sahiptir. Aşağıdaki şemada sistemin dosya ağacı "
        "ve modüller arası bağımlılık zinciri gösterilmiştir:"
    )

    code_tree = (
        "D:\\autocad projesi\\\n"
        "├── cloudecad.py                      <- MERKEZİ GİRİŞ NOKTASI (Unified CLI, Interactive Menu, Watch Mode)\n"
        "├── batch_inspector.py                <- Toplu Proje Denetim Köprüsü (Klasör İzleme & Tarama)\n"
        "├── cloudecad.bat                     <- Hızlı Başlatıcı (UTF-8 güvenli venv sarmalayıcısı)\n"
        "├── otomatik_denetim.bat              <- Tek Tıkla Toplu Denetim / Watch Servisi Menüsü\n"
        "├── tools/\n"
        "│   ├── generate_system_guide.py      <- BU REHBERİ DERLEYEN BETİK (docx + md tek komutla yenilenir)\n"
        "│   ├── field_run_healer.py           <- SAHA İNDİRİM: gerçek paftalarda Healer zinciri (v3.0)\n"
        "│   ├── review_station.py             <- ONAY İSTASYONU: FastAPI + kural bazlı toplu triyaj (v3.0)\n"
        "│   └── compose_delivery.py           <- COMPOSER: DXF→DWG + teslim paketi; başarısız olursa COM ile orijinal DWG üzerinden onarır (v3.0)\n"
        "├── jobs/                             <- İş kabul/üretim klasörü (JOB-YYYY-*; plans/output/redline/delivery)\n"
        "├── tests/\n"
        "│   └── test_reference_projects.py    <- 13 ADET GOLD-STANDARD BİRİM, DENETİM VE HEALER TESTİ\n"
        "├── lispkodlar/                       <- AutoCAD Üretim Hızlandırma LISP Araçları (kullanıcı aracı)\n"
        "├── ornekprojeler/                    <- Tekil Örnek DWG Girdileri (--file modu)\n"
        "├── incelenecek projeler/             <- Toplu Denetim Girdi Klasörü (--scan / --watch)\n"
        "├── projelerin inceleme sonuçları/    <- Üretilen Denetim Raporları (varsayılan çıktı klasörü)\n"
        "├── raporlar/                         <- Proje Onay Evrakları & Yükleme Cetvelleri (arşiv)\n"
        "├── ErrorReports/                     <- Çökme tanılama kayıtları\n"
        "├── CLOUDECAD_SISTEM_REHBERI.docx     <- RESMİ SİSTEM MİMARİSİ VE ÇALIŞMA PRENSİPLERİ REHBERİ (WORD)\n"
        "├── CLOUDECAD_SISTEM_REHBERI.md       <- SİSTEM REHBERİ (MARKDOWN KOPYASI)\n"
        "├── cloudecadprogramı/\n"
        "│   ├── requirements.txt              <- Python Paket Bağımlılıkları\n"
        "│   ├── kur.bat                       <- Sanal Ortam + Paket Kurulum Betiği\n"
        "│   ├── common/\n"
        "│   │   ├── dxf_converter.py          <- accoreconsole / COM DWG->DXF Dönüştürücü ve .dxf_cache Yöneticisi\n"
        "│   │   ├── com_dwgs.py               <- COM tabanlı DWG Düzeltici (ezdxf yazımı AutoCAD'i çökertirse yedek yol)\n"
        "│   │   ├── universal_cad_reader.py   <- Geriye Dönük Uyumluluk Sarmalayıcısı (-> core/cad/reader.py)\n"
        "│   │   └── station_audit_engine.py   <- Geriye Dönük Uyumluluk Sarmalayıcısı (-> core/engine.py)\n"
        "│   ├── core/\n"
        "│   │   ├── engine.py                 <- ORKESTRASYON MOTORU (UnifiedAuditEngine; StationAuditEngine takma adı)\n"
        "│   │   ├── cad/\n"
        "│   │   │   ├── reader.py             <- UniversalCADReader (DXF -> DrawingSceneGraph + Handle Provenance)\n"
        "│   │   │   ├── cad_safety.py         <- CADSafetyGuard & UnitScaleResolver (XREF, Block Def, CTB, INSUNITS, MTEXT)\n"
        "│   │   │   ├── frame_detector.py     <- FrameDetector (İç İçe Paftalar, Antetler, Kat Planı Bölgeleri)\n"
        "│   │   │   ├── triage.py             <- SymbolTriage (Kanıta Dayalı Anonim Blok ve Sembol Triyajı)\n"
        "│   │   │   ├── classifier.py         <- Sembol Sınıflandırıcı ve Lejant Analizi\n"
        "│   │   │   └── geometry.py           <- Shapely 2D Geometri ve Uzaysal İndeksleme Yardımcıları\n"
        "│   │   ├── healer/                   <- v3.0 OTOMATİK ONARIM, OPTİMİZASYON VE YENİDEN ÜRETİM MOTORU\n"
        "│   │   │   ├── layer_doctor.py       <- Modül 1: LayerAndBlockDoctor (Katman Standardizasyonu & Mimari Kilit)\n"
        "│   │   │   ├── wire_healer.py        <- Modül 2: TopologicalWireHealer (4 Şartlı Stitch, Snap & Overkill)\n"
        "│   │   │   ├── electrical_optimizer.py <- Modül 3: ElectricalAutoOptimizer (ASBUILT/DESIGN & Re-Verify)\n"
        "│   │   │   └── table_generator.py    <- Modül 4: CADTableGenerator (DWG Yükleme Cetveli & .xlsx Üretici)\n"
        "│   │   ├── calculators/\n"
        "│   │   │   └── electrical_calc.py    <- Elektrik Mühendisliği Hesaplayıcıları (Iz, e%, Faz Dengesi, PE Kesit)\n"
        "│   │   ├── model/\n"
        "│   │   │   ├── entities.py           <- CAD Varlık Modelleri (DrawingSceneGraph, PlacedSymbol, TextToken...)\n"
        "│   │   │   └── audit.py              <- Denetim & Rapor Modelleri (StationAuditReport, AuditFinding...)\n"
        "│   │   ├── reconciliation/\n"
        "│   │   │   └── cross_sheet_engine.py <- ÇAPRAZ MUTABAKAT MOTORU (Plan vs Tablo, Pano vs Topraklama PS-17)\n"
        "│   │   ├── rules/\n"
        "│   │   │   ├── rule_engine.py        <- Dinamik Kural Paketi Yöneticisi ve TS HD 60364-5-52 Tabloları\n"
        "│   │   │   └── packs/\n"
        "│   │   │       ├── turkey_bina.yaml  <- Türkiye Bina & Tesis Elektrik Yönetmeliği Kural Paketi\n"
        "│   │   │       └── ibb_metro.yaml    <- İBB Raylı Sistemler As-Built Elektrik Şartnamesi Paketi\n"
        "│   │   ├── topology/\n"
        "│   │   │   ├── circuit_resolver.py   <- Mantıksal Linye ve Devre Çözümleyici\n"
        "│   │   │   └── route_builder.py      <- Fiziksel Kablo Güzergahı ve Ağaç Oluşturucu\n"
        "│   │   └── reporters/\n"
        "│   │       ├── markdown_reporter.py  <- Markdown (.md) Formatında Mühendislik Raporu Üreteci\n"
        "│   │       └── json_reporter.py      <- JSON Formatında Tam Yapılandırılmış Denetim Verisi Üreteci\n"
        "│   └── legacy/                       <- v1.0 Eski İzole Modüller (Referans & Arşiv Amaçlı)\n"
        "└── .dxf_cache/                       <- Dönüştürülmüş ve Onarılmış DXF Dosyaları Önbelleği"
    )
    add_code_block(doc, code_tree)

    add_heading_2(doc, "5.1. Modüller Arası Veri Akışı ve Bağımlılık Zinciri")
    add_body_p(
        doc,
        "Sistem bir DWG dosyasını veya istasyon klasörünü denetlerken şu katı yürütme sırasını takip eder:"
    )
    add_bullet_p(doc, "cloudecad.py kullanıcı parametrelerini ayrıştırır, UnifiedAuditEngine nesnesini başlatır.", "1. CLI Girişi: ")
    add_bullet_p(doc, "DWG dosyası common/dxf_converter.py üzerinden accoreconsole ile _AUDIT ve _DXFOUT işlemine sokulur, .dxf_cache içine kaydedilir.", "2. Dönüştürme & Önbellek: ")
    add_bullet_p(doc, "core/cad/reader.py (UniversalCADReader) DXF'i okur; ezdxf varlıklarını core/model/entities.py veri sınıflarına (DrawingSceneGraph) aktarır.", "3. CAD Okuma: ")
    add_bullet_p(doc, "core/cad/frame_detector.py ModelSpace içindeki dış sınırları, antetleri ve alt pafta bölgelerini (SubPlanZone) poligon olarak çıkarır.", "4. Pafta & Antet Tespiti: ")
    add_bullet_p(doc, "core/cad/triage.py sembolleri 4 kanıt süzgecinden geçirerek mimari tefrişleri eler, elektrik ekipmanlarını korur.", "5. Sembol Triyajı: ")
    add_bullet_p(doc, "core/engine.py 5 ana denetim modülünü (Kuvvetli Akım, Çapraz Mutabakat, Zayıf Akım, Topraklama/Tava, Belirsizlik) sırayla çalıştırır.", "6. Denetim Modülleri: ")
    add_bullet_p(doc, "core/reporters/markdown_reporter.py ve json_reporter.py StationAuditReport nesnesini disk üzerine rapor olarak yazar.", "7. Raporlama: ")

    # --------------------------------------------------------------------------
    # BÖLÜM 6: BEŞ ÇEKİRDEK DENETİM MODÜLÜNÜN İŞLEYİŞİ
    # --------------------------------------------------------------------------
    add_heading_1(doc, "6. Beş Çekirdek Denetim Modülünün Detaylı İşleyişi")
    add_body_p(
        doc,
        "UnifiedAuditEngine bünyesinde çalışan 5 çekirdek modül ve gerçekleştirdikleri mühendislik denetimleri şunlardır:"
    )

    add_heading_2(doc, "Modül 1 — Kuvvetli Akım ve Pano Faz Yük Dengesi")
    add_body_p(
        doc,
        "Kat planlarındaki linye etiketleri (A1, P1, CDB1...) ve panolar taranır. "
        "Her linye için faz bilgisi (L1/R, L2/S, L3/T), armatür/priz adedi, cihaz gücü ve kablo kesiti eşleştirilir. "
        "Pano bazında faz yük dengesizliği aşağıdaki formülle hesaplanır:"
    )
    add_code_block(
        doc,
        "Δ% = ((I_max - I_min) / I_max) * 100\n"
        "İBB Metro Paketi (ibb_metro.yaml) Sınırları: Δ% <= %15 (UYGUN) | %15 < Δ% <= %20 (UYARI) | Δ% > %20 (KRİTİK UYGUNSUZLUK)\n"
        "Bina Paketi (turkey_bina.yaml) Kritik Sınırı: Δ% > %25"
    )
    add_body_p(
        doc,
        "Ayrıca linye kabloları için TS HD 60364-5-52 akım taşıma kapasitesi (Iz) ve gerilim düşümü (e%) doğrulanır; "
        "aşırı yük durumunda KA-BAL ve KA-AMP hata kodları üretilir."
    )
    add_body_p(
        doc,
        "Not: v2.0 çekirdek motoru linye verilerini yalnızca çizimden (DXF) okur. Excel yükleme cetveli okuma "
        "(openpyxl/xlrd) yalnızca legacy v1.0 modüllerinde bulunur; çizimde yazmayan hiçbir güç cetvelden otomatik çekilmez.",
        bold_prefix="Veri Kaynağı Notu: "
    )

    add_heading_2(doc, "Modül 2 — Paftalar Arası Çapraz Mutabakat (Cross-Sheet Engine)")
    add_body_p(
        doc,
        "CrossSheetReconciliationEngine iki kritik çapraz denetim yapar:\n"
        "1. Plan vs Metraj Tablosu: Kuvvetli akım planında (PS-11) çizilen kablo etiketleri ile paftadaki metraj tablosundaki satırlar karşılaştırılır. "
        "Tabloda yer almayan linyeler 'REC-TBL-OMIT' koduyla raporlanır.\n"
        "2. Pano vs Topraklama Paftaları: Kuvvetli akım panoları (PS-08, PS-16) ile topraklama paftalarındaki (PS-17, GN-14) "
        "Eşpotansiyel Baralar (ECB) ve Trafo/Pano bağlantıları (TS19...) kademeli olarak eşleştirilir."
    )

    add_heading_2(doc, "Modül 3 — Zayıf Akım 11 Alt Sistem Analizi")
    add_body_p(
        doc,
        "İstasyon projelerinde yer alan 11 alt sistem (AX-02 + TL-02..TL-11), pafta dosya adındaki sistem kodundan "
        "dinamik olarak tanınır ve aktif kural paketindeki haritayla eşleştirilir (M09 hattı DXF içerik analiziyle doğrulanmıştır):\n"
        "• AX-02: Yangın Algılama ve İhbar Sistemi\n"
        "• TL-02: Veri İletişim, LAN & Fiber Optik Altyapı (SDH/OTN Omurga)\n"
        "• TL-03: Telefon, Acil SOS & Dahili Haberleşme (PABX/Interkom)\n"
        "• TL-04: Telsiz / TETRA Haberleşme & Anten\n"
        "• TL-05: Acil Anons ve Sesli Tahliye (PA/VA)\n"
        "• TL-06: CCTV Kamera Sistemi\n"
        "• TL-07: Saat Sistemi (Master Clock & Tali Saatler)\n"
        "• TL-08: Geçiş Kontrol ve Güvenlik (ACS)\n"
        "• TL-09: SCADA, PLC & Otomasyon\n"
        "• TL-10: Yolcu Bilgilendirme Sistemi (PIS)\n"
        "• TL-11: Sistem Odası (SER/CER) Rack Kabinet Yerleşimi.\n"
        "Denetim Kriterleri: Riser (kolon şeması) ve kat planı sembol sayıları karşılaştırılır. "
        "Kritik yangın ve acil durum hatlarında FE180 yangına dayanıklı kablo varlığı denetlenir. "
        "CAT6 veri kablolarında 90 metrelik kanal sınırı (plan güzergahı varsa) doğrulanır; güzergah yoksa sahte değer atanmaz, belirsizlik maddesi açılır."
    )

    add_heading_2(doc, "Modül 4 — Topraklama ve Tava Kapsamı")
    add_body_p(
        doc,
        "Kat bazında Eşpotansiyel Topraklama Baraları (S19/ECB/001..052), ray ve trafo topraklama bağlantıları (TS19...) taranır. "
        "Kablo tava ve merdiven metrajları (A-TRAY-LV, A-TRAY-WC vb.) kat bazında çıkarılarak özetlenir."
    )

    add_heading_2(doc, "Modül 5 — Belirsizlik Listesi ve Güven Analizi (Uncertainty Review List)")
    add_body_p(
        doc,
        "Çizimdeki eksiklik veya kısıtlardan kaynaklanan durumlar doğrudan 'hata' ilan edilmez; mühendisin onayına sunulacak "
        "özel bir inceleme listesi olarak üretilir:\n"
        "• UNC-SYM-...: Fonksiyonu lejantta veya katmanda kanıtlanamayan şüpheli bloklar.\n"
        "• UNC-MISSING-CABLE-...: Kat planında linye numarası olup kablo kesiti yazılmamış devreler.\n"
        "• UNC-GRND-SHEET-MISSING-...: Katın topraklama paftası analiz setinde bulunmadığı için teyit edilemeyen panolar.\n"
        "• UNC-CAT6-SPAN-...: Kat planında fiziksel güzergahı çizilmediği için mesafesi ölçülemeyen CAT6 hatları."
    )

    # --------------------------------------------------------------------------
    # BÖLÜM 7: MEVZUAT, STANDARTLAR VE HESAP FORMÜLLERİ
    # --------------------------------------------------------------------------
    # --------------------------------------------------------------------------
    # BÖLÜM 6B: v3.0 ONARIM VE ÜRETİM HATTI
    # --------------------------------------------------------------------------
    add_heading_1(doc, "6B. v3.0 Onarım ve Üretim Hattı (Healer + Onay İstasyonu + Composer)")
    add_body_p(
        doc,
        "v2.0 denetim motorunun üzerine, denetim bulgusundan kontrollü onarıma ve teslimata uzayan "
        "üç yeni katman eklenmiştir. Akış: Saha Koşumu → Onay İstasyonu → Composer.",
    )
    add_bullet_p(doc, "core/healer/ altında 4 modül: LayerAndBlockDoctor (katman standardizasyonu), TopologicalWireHealer (4 şartlı kablo onarımı), ElectricalAutoOptimizer (ASBUILT/DESIGN frenli hesap düzeltmeleri), CADTableGenerator (DWG içi yükleme cetveli + .xlsx). Ortak güvenlik kalkanı: core/cad/cad_safety.py (XREF/blok dokunulmazlığı, CTB, INSUNITS ölçekleme, MTEXT koruması).", "1. Healer Katmanı: ")
    add_bullet_p(doc, "tools/field_run_healer.py — Okuma→Triyaj→LayerDoctor→WireHealer→ASBUILT Optimizasyon zincirini gerçek paftalarda koşar; temiz DXF + imzalı mesuliyet defteri + redline PNG üretir. Saha kanıtı: 7 gerçek S19 paftası, 58.000+ varlık korundu, PS-16'da %141,7 faz dengesizliği reçetesi üretildi.", "2. Saha Koşumu: ")
    add_bullet_p(doc, "tools/review_station.py — FastAPI + tarayıcı arayüzü. Kural bazlı toplu triyaj (örn. 'açı ≤ 3°'), tekil onay/ret, statü koruması (NOT_SELECTED), redline görüntüleme, Composer tetikleme. Her karar SHA-256 imzalı deftere yazılır; eşzamanlı yazım kilidi ve atomik dosya yazımı içerir.", "3. Onay İstasyonu: ")
    add_bullet_p(doc, "tools/compose_delivery.py — Onaylı DXF'i DWG 2018'e çevirir ve teslim paketi üretir (DWG+DXF+redline+planlar+defter+README+MANIFEST). Dönüşüm kademelidir: accoreconsole → gerekiyorsa Revit-artığı SPLINE temizliği → gerekiyorsa COM onarımı (orijinal DWG üzerinde AutoCAD API ile uygulama). COM kademesi, ezdxf yeniden yazımının AutoCAD 2027'yi çökerttiği paftalar için kalıcı çözümdür (cloudecadprogramı/common/com_dwgs.py).", "4. Composer: ")
    add_bullet_p(doc, "jobs/JOB-*/ klasörü: intake.yaml (iş künyesi) + output/ (temiz DXF) + plans/ (öneri JSON'ları) + applied/ + redline/ + delivery/ + RESPONSIBILITE_DEFTERI.json + canlı üretilen RAPOR.md.", "5. İş Klasörü Düzeni: ")

    add_heading_2(doc, "6B.1 Modül Olgunluk Tablosu (Aktif / Prototip / Legacy / Yarım)")
    mat_headers = ["Katman", "Konum", "Durum", "Not"]
    mat_rows = [
        ["Denetim motoru (engine, cross_sheet, rules, reporters)", "core/", "AKTİF-ÜRETİM", "13 test; İBB saha raporlarıyla doğrulanmış"],
        ["CAD okuma + triyaj + pafta tespiti", "core/cad/", "AKTİF-ÜRETİM", "388 DXF önbelleğinde gerçek paftalarla çalışıyor"],
        ["Healer 4 modülü + güvenlik kalkanı", "core/healer/ + core/cad/cad_safety.py", "AKTİF-PROTOTİP", "7 pafta saha koşumu + 13 test; üretim kullanımına hazır"],
        ["Onay İstasyonu", "tools/review_station.py", "AKTİF-PROTOTİP", "Tek kullanıcılı; mühendis onay akışı doğrulandı"],
        ["Composer + COM onarımı", "tools/compose_delivery.py + common/com_dwgs.py", "AKTİF-PROTOTİP", "7/7 pafta DWG üretildi; COM kademesi AutoCAD GUI başlatır"],
        ["CAT6 90 m fiziksel güzergâh ölçümü", "core/topology/", "YARIM", "Gerçek M09 setinde CAT6/UTP yalnızca antet (KMM_Antet) blok notlarında geçiyor; devre bazlı CAT6 etiketi yok -> 90 m ölçümü çoğu paftada yapılamaz, UNC-CAT6-SPAN belirsizliği beklenir. Öneri: antet notlarından proje notu çıkarımı"],
        ["Metro pafta kodları tanıma", "core/engine.py", "AKTİF (M09 odaklı)", "AX/TL/PS/GN/ELM/USK/PRT kodları gerçek M09 setiyle doğrulandı; diğer hatlar için genişletme gerekir"],
        ["Excel yükleme cetveli okuma", "legacy/", "LEGACY-ARŞİV", "v2.0 çekirdeği Excel okumaz"],
        ["Süperpoze / topraklama motoru (v1)", "legacy/", "LEGACY-ARŞİV", "Referans amaçlı"],
        ["BIM/IFC/Revit parser", "—", "YOK (yol haritası)", "Aktif çekirdek DXF/DWG odaklıdır"],
        ["LLM/vision tabanlı çizim anlama", "—", "YOK", "Sistem heuristik + geometri + isimlendirme + katman + yakınlık + tablo kanıtlarıyla çalışır"],
    ]
    mat_tbl = doc.add_table(rows=1, cols=4)
    style_table(mat_tbl, [Inches(2.4), Inches(1.7), Inches(1.3), Inches(2.5)], mat_headers, mat_rows)

    add_body_p(
        doc,
        "Sıfır Varsayım İlkesi istisnası (belgelenmiş): CADTableGenerator, fazı çizimden okunamayan linyelerin "
        "gücünü mühendislik tablosu için üç faza eşit paylaştırır; bu durum tabloda açıkça '(faz belirsiz — "
        "TAHMİNİ eşit dağıtım)' olarak etiketlenir ve ESTIMATED_DEFAULT kategorisinde raporlanır. Hesapsal "
        "denetimlerde (engine) belirsiz faz asla varsayılmaz; belirsizlik maddesi açılır.",
        bold_prefix="Not: ",
    )

    add_heading_1(doc, "7. Mevzuat, Standartlar ve Mühendislik Formülleri")
    add_body_p(
        doc,
        "CloudeCAD bünyesinde yer alan tüm kontroller ulusal ve uluslararası standartlara referanslıdır:"
    )

    std_headers = ["Standart / Yönetmelik", "İlgili Madde / Tablo", "Denetim Kriteri ve Uygulanan Formül"]
    std_rows = [
        [
            "TS HD 60364-5-52:2014",
            "Çizelge B.52.2 - B.52.5\nÇizelge B.52.14 / B.52.17",
            "Kablo Akım Taşıma Kapasitesi (Iz):\n"
            "• XLPE 90°C ve PVC 70°C yalıtım tipleri\n"
            "• B1 (Boruda), C (Duvarda), E (Tavada) döşeme yöntemleri\n"
            "• 1-Faz (2 yüklü) ve 3-Faz (3 yüklü) iletken ayrımı\n"
            "• Ortam sıcaklığı (35°C için x0.94 vb.) ve gruplama katsayıları (x0.85 vb.)"
        ],
        [
            "TS HD 60364-4-43",
            "Madde 433.1\n(Aşırı Akım Koordinasyonu)",
            "Ib <= In <= Iz ve In_KAK >= In_sigorta\n"
            "Çalışma akımı (Ib), koruma cihazı anma akımından (In) küçük olmalı; In ise kablo akım kapasitesini (Iz) aşamaz."
        ],
        [
            "Binaların Yangından Korunması\nHakkında Yönetmelik (BYKHY)",
            "Madde 72 & 83\n(Acil Durum Beslemeleri)",
            "Yangın pompası ve acil durum ekipmanları beslemesinde FE180 yangına dayanıklı kablo zorunludur. "
            "Yangın pompası besleme devresine 30mA Hayat Koruma Kaçak Akım Rölesi takılması KESİNLİKLE YASAKTIR (yangın anında pompanın açmasını önlemek için)."
        ],
        [
            "İBB Raylı Sistemler\nAs-Built Şartnamesi",
            "AG Dağıtım Kriterleri &\nZayıf Akım Şartnamesi",
            "• Pano Faz Yük Dengesizliği: Maks. %15 (Uyarı), %20 (Kritik) — İBB metro paketi\n"
            "• Zayıf Akım Acil Sistemler: FE180 kablo zorunluluğu\n"
            "• Yapısal Kablolama: CAT6 kanal boyu maks. 90 metre"
        ],
        [
            "EN 50122-1 &\nETTY RG:24560",
            "Madde 6\n(Equipotential Bonding)",
            "Tüm alçak gerilim ana ve tali panolarının istasyon topraklama ağına (ECB baraları veya TS topraklama kuşaklama hatları) bağlantısı bulunmalıdır."
        ],
        [
            "IEC 60364-5-54",
            "Madde 543.1\n(PE Koruma İletkeni)",
            "Faz kesitine göre minimum koruma iletkeni kesiti:\n"
            "• S <= 16 mm² ise Spe = S\n"
            "• 16 < S <= 35 mm² ise Spe = 16 mm²\n"
            "• S > 35 mm² ise Spe = S / 2"
        ]
    ]
    std_tbl = doc.add_table(rows=1, cols=3)
    style_table(std_tbl, [Inches(1.8), Inches(1.8), Inches(3.6)], std_headers, std_rows)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # --------------------------------------------------------------------------
    # BÖLÜM 8: DOĞRULAMA VE TEST MİMARİSİ (8 GOLD-STANDARD TEST)
    # --------------------------------------------------------------------------
    add_heading_1(doc, "8. Doğrulama ve Test Mimarisi (Gold-Standard Test Paketi)")
    add_body_p(
        doc,
        "Sistemin regresyona uğramadığını, hiçbir kuralın bozulmadığını ve determinizmini doğrulamak için "
        "tests/test_reference_projects.py dosyasında 13 altın test yer almaktadır:"
    )

    tst_headers = ["Test Adı", "Kapsam ve Denetlenen Kural", "Beklenen Deterministik Sonuç"]
    tst_rows = [
        [
            "test_ref01_clean_pass_metro_station",
            "Eksiksiz, kurallara tam uyan metro istasyonu modeli.",
            "0 Kritik Hata, 0 Uyarı, PASS statüsü."
        ],
        [
            "test_ref02_known_violations_project",
            "Bilerek enjekte edilmiş gerilim düşümü (>%3), koruma koordinasyon hatası ve yangın pompası 30mA KAK ihlali.",
            "Tüm ihlallerin CRITICAL olarak %100 KESİN yakalanması."
        ],
        [
            "test_ref03_missing_data_and_uncertainties",
            "Kablo kesiti yazılmamış eksik projeler.",
            "Otomatik 25A kesit atanmaz; 'UNC-MISSING-CABLE-SPEC' belirsizliği üretilir."
        ],
        [
            "test_ref04_tshd60364_ampacity_table_accuracy",
            "TS HD 60364-5-52 Çizelge B.52.2-B.52.5 tablosunun sayısal doğruluğu.",
            "PVC/XLPE, B1/C/E, 1/3 Faz akım değerleri birebir uyuşur; 999mm² kesit None döner."
        ],
        [
            "test_ref05_station_code_priority_and_markdown_reporter",
            "S24 dosyasında S28 antet metni bulunması durumu.",
            "İstasyon S24 seçilir, 'REC-STATION-TITLE-MISMATCH' uyarısı üretilir, Markdown raporu hatasız basılır."
        ],
        [
            "test_ref06_symbol_triage_evidence_based",
            "Anonim blokların (A$C...) 4 kanıt süzgeciyle triyajı.",
            "Mimari tefriş elenir, elektrik katmanındakiler korunur, çelişkili armatür yanındakiler silinmez."
        ],
        [
            "test_ref07_metro_sheet_codes_and_station_grounding_are_dynamic",
            "PS-08 ve GN-14 paftalarının dinamik tanınması, ECB/TS bağlantıları.",
            "S19/ECB/01 ve TS19LVS401 dinamik olarak istasyon özetine girer."
        ],
        [
            "test_ref08_graduated_grounding_reconciliation",
            "Kademeli topraklama eşleştirme ve kanıta bağlı şiddet kuralı.",
            "Kompozit etiketler Tier 2 ile UYGUN eşleşir; kat paftası eksikse hata değil belirsizlik açılır; paftada bulunamayan pano WARNING seviyesine iner."
        ],
        [
            "test_ref09_layer_doctor_and_cad_safety",
            "Modül 1 (LayerAndBlockDoctor) ve cad_safety 3 tuzak koruması (XREF, Block Def vs INSERT, CTB/Lineweight, INSUNITS, MTEXT).",
            "XREF ve Blok Tanımı korunur; IGNORED_ARCHITECTURAL 'A-MIMARI-ALTYAPI' (Color 8, 0.09mm, Kilitli) katmanına taşınır; imzalı applied_changes.json üretilir."
        ],
        [
            "test_ref10_topological_wire_healer_4_conditions",
            "Modül 2 (TopologicalWireHealer) 4 şartlı doğrusal birleştirme, yan yana paralel hat mayın koruması, OVERKILL ve Snap.",
            "4/4 koşulu sağlayan kopukluk köprülenir; yan yana paralel hatlar (~90° köprü) ve W1 vs W2 farklı devreler REQUIRES_APPROVAL olarak durdurulur."
        ],
        [
            "test_ref11_electrical_optimizer_asbuilt_vs_design_and_reverify",
            "Modül 3 (ElectricalAutoOptimizer) ASBUILT vs DESIGN iş tipi freni ve Öner -> Yeniden Doğrula -> Onayla -> Uygula zinciri.",
            "ASBUILT faz değişimi DWG'ye uygulanamaz; DESIGN modunda Greedy LPT dengesizliği %0'a indirir; FE180 ve koruma koordinasyonu bellekte yeniden doğrulanıp MTEXT formatı korunarak işlenir."
        ],
        [
            "test_ref12_cad_table_generator_dwg_and_xlsx",
            "Modül 4 (CADTableGenerator) DWG içi LINE+TEXT yükleme cetveli çizimi, mevcut tablo hücresi güncelleme ve .xlsx üretimi.",
            "E-ETIKET-TABLO katmanında ölçekli cetvel ızgarası çizilir, mevcut hücre handle'ı onay kapısından geçerek güncellenir ve kurumsal Excel (.xlsx) dosyası oluşturulur."
        ],
        [
            "test_ref13_all_11_audit_fixes_regression",
            "Canlı denetimde yakalanan 11 kritik/orta/küçük bulgunun regresyon doğrulaması.",
            "Faz token Değişmezlik Kalkanı ('L2-01 3x2.5 NYY' korunur), dinamik kural paketi sınırları, STRtree hızlandırması, Duplicate devre çelişki koruması, kademeli Snap ve Unitless cm tespiti doğrulanır."
        ]
    ]
    tst_tbl = doc.add_table(rows=1, cols=3)
    style_table(tst_tbl, [Inches(2.4), Inches(2.4), Inches(2.4)], tst_headers, tst_rows)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    add_body_p(doc, "Test paketini çalıştırmak için komut satırından şu komut yürütülür:", bold_prefix="Test Komutu: ")
    add_code_block(doc, '& "D:\\autocad projesi\\venv\\Scripts\\python.exe" -m pytest "D:\\autocad projesi\\tests" -v')

    # --------------------------------------------------------------------------
    # BÖLÜM 9: KULLANIM VE ÇALIŞTIRMA KILAVUZU (CLI & İZLEME SERVİSİ)
    # --------------------------------------------------------------------------
    add_heading_1(doc, "9. Kullanım ve Çalıştırma Kılavuzu (CLI & İzleme Servisi)")
    add_body_p(
        doc,
        "CloudeCAD hem interaktif menü üzerinden hem de gelişmiş komut satırı (CLI) bayraklarıyla çalıştırılabilir:"
    )

    cli_headers = ["Kullanım Senaryosu", "Komut Satırı Sözdizimi", "Açıklama"]
    cli_rows = [
        [
            "İnteraktif Terminal Menüsü",
            "python cloudecad.py",
            "Kullanıcıya 1-4 arası seçenekler sunan kılavuzlu menüyü açar."
        ],
        [
            "Tekil Pafta İncelemesi",
            'python cloudecad.py --file "pafta.dwg"',
            "Belirtilen tek bir DWG/DXF dosyasını okur, alt paftaları ayırır, devreleri çözer ve raporlar."
        ],
        [
            "İstasyon Klasörü Denetimi",
            'python cloudecad.py "klasor_yolu"',
            "Klasördeki tüm DWG'leri birleşik bir istasyon olarak analiz eder, çapraz mutabakat uygular."
        ],
        [
            "İstasyon Kodunu Zorlama",
            'python cloudecad.py --station "klasor" --code S19',
            "İstasyon kodunu elle S19 olarak belirler ve bu kural paketini uygular."
        ],
        [
            "Toplu Tarama (Batch Scan)",
            "python cloudecad.py --scan",
            "'incelenecek projeler' altındaki tüm istasyon paketlerini sırayla denetler."
        ],
        [
            "Sürekli Klasör İzleme (Watch Mode)",
            "python cloudecad.py --watch",
            "Girdi klasörünü 4 saniyede bir yoklar; yeni veya güncellenen DWG tespit edildiğinde otomatik denetim başlatır."
        ],
        [
            "SAHA İNDİRİM (v3.0 Healer)",
            'python tools/field_run_healer.py',
            "Gerçek paftalarda Okuma→Triyaj→LayerDoctor→WireHealer→ASBUILT Optimizasyon zincirini koşar; temiz DXF + mesuliyet defteri + redline üretir."
        ],
        [
            "ONAY İSTASYONU (v3.0)",
            'python tools/review_station.py --job jobs/JOB-YYYY-* --port 8765',
            "FastAPI yerel web arayüzü: kural bazlı toplu triyaj (örn. açı≤3°), tekil onay/ret, DWG'ye cerrahi uygulama."
        ],
        [
            "COMPOSER (v3.0 Teslimat)",
            'python tools/compose_delivery.py --job jobs/JOB-YYYY-*',
            "Temiz DXF'i accoreconsole ile DWG 2018'e çevirir; redline+planlar+defter içeren teslim paketini delivery/ altında toplar."
        ]
    ]
    cli_tbl = doc.add_table(rows=1, cols=3)
    style_table(cli_tbl, [Inches(1.8), Inches(2.7), Inches(2.7)], cli_headers, cli_rows)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # --------------------------------------------------------------------------
    # BÖLÜM 10: GELECEKTEKİ GELİŞTİRİCİLER VE YZ İÇİN BAKIM PROTOKOLÜ
    # --------------------------------------------------------------------------
    add_heading_1(doc, "10. Gelecekteki Geliştiriciler ve Yapay Zeka İçin Bakım Protokolü")
    add_callout_box(
        doc,
        "1. KOD DEĞİŞİKLİĞİ ÖNCESİ BU BELGEYİ KONTROL ET:\n"
        "Herhangi bir modülde değişiklik yapmadan önce ilgili modülün bu belgedeki bağımlılık zincirini inceleyin.\n\n"
        "2. SIFIR VARSAYIM İLKESİNİ ASLA İHLAL ETME:\n"
        "Çizimde bulunmayan hiçbir elektriksel büyüklüğü (kesit, güç, boy vb.) koda sabit sayı (hardcoded) olarak gömmeyin. "
        "Veri eksikse mutlaka UncertaintyItem üretin.\n\n"
        "3. KURAL DEĞİŞİKLİKLERİNİ YAML PAKETLERİNDE YAPIN:\n"
        "Yönetmelik katsayılarını doğrudan python koduna yazmayın; 'turkey_bina.yaml' veya 'ibb_metro.yaml' içine ekleyin.\n\n"
        "4. TESTLERİ ÇALIŞTIRIN:\n"
        "Yapılan her düzenlemeden sonra 'pytest tests/test_reference_projects.py -v' komutunu çalıştırın. 13 testin tümü yeşil olmadan kodu onaylamayın.\n\n"
        "5. BU REHBERİ GÜNCELLEYİN:\n"
        "Yeni bir modül, yeni bir denetim kriteri veya yeni bir kütüphane eklendiğinde bu Word belgesini güncelleyin.",
        title="GELİŞTİRME VE GÜNCELLEME ALTIN KURALLARI",
        border_color="0B2545",
        bg_color="F9FAFB"
    )

    # Kaydet
    doc.save(DOCX_OUTPUT_PATH)
    print(f"✓ DOCX created successfully: {DOCX_OUTPUT_PATH.resolve()}")

    # Markdown Kopyasını da Oluştur
    generate_markdown_companion()


def generate_markdown_companion():
    print(f"Creating Markdown Companion: {MD_OUTPUT_PATH.name}")
    md_content = r"""# CloudeCAD v3.0 — Sistem Mimarisi, Kod Haritası ve Çalışma Prensipleri Ana Rehberi (SSOT)

> **Belge Türü:** Tek Doğruluk Kaynağı (Single Source of Truth - SSOT)  
> **Sürüm:** v3.0 Gold Release (Healer Katmanı Dahil)  
> **Tarih:** 01 Kasım 2026  
> **Kapsam:** CAD (DXF/DWG) Çizim Denetimi ve Kontrollü Onarım — Metro İstasyonları ve Bina Tesisat Projeleri (BIM/IFC entegrasyonu yol haritasındadır, aktif değildir)  
> **Microsoft Word Formatı:** `CLOUDECAD_SISTEM_REHBERI.docx`

---

## 1. Giriş ve Belgenin Amacı

Bu doküman, **CloudeCAD v3.0 CAD Odaklı (DXF/DWG) Elektrik ve Raylı Sistem Proje Denetim ve Onarım Platformunun** tüm mimarisini, veri modellerini, harici araç bağımlılıklarını, dosya ve fonksiyon ilişkilerini ve mühendislik algoritmalarını tek bir merkezde toplayan resmi mimari başvuru kaynağıdır.

### 📌 Yapay Zeka ve Geliştiriciler İçin Çalışma Protokolü
Gelecekteki her yeni konuşmada, her yapay zeka (YZ) oturumunda veya projeye dahil olan yeni mühendislerde **binlerce satırlık kod tabanını baştan sona tarama zorunluluğunu ortadan kaldırmak** hedeflenmiştir. Sisteme yeni bir kural, yeni bir CAD filtresi veya yeni bir hesaplama modülü eklendiğinde doğrudan bu rehber açılacak, mevcut durum doğrulanacak ve güncellemeler buraya işlenecektir.

---

## 2. Sistemin Temel Çalışma Mantığı ve 5 Mühendislik Prensibi

### 2.1. Sıfır Varsayım İlkesi (Zero-Assumption Engineering)
Bir elektrik projesinde çizimde açıkça yazmayan bir kablo kesiti (örn: 3x2.5), sigorta değeri (örn: 16A), cihaz gücü veya hat mesafesi **asla varsayılarak kesin hesaba dahil edilmez**. Sistem veri kaynağını (Data Source Provenance) dört seviyede izler:
- `EXPLICIT` (Güven: 1.0): Çizimdeki blok özniteliğinden (ATTRIB), kablo etiketinden veya tablodan birebir okundu.
- `PARTIAL_EXPLICIT` (Güven: 0.85): Sembol adı veya katmandan çıkarıldı (örn: 'LED_36W' bloğundan 36W alınması).
- `ESTIMATED_DEFAULT` (Güven: 0.70): Çizimde güç yazılmadığı için kural paketindeki standart linye gücü kullanıldı. Rapor Güven Seviyesi `MUHTEMEL (TAHMİNİ YÜK)` olarak işaretlenir.
- `MISSING` (Güven: 0.0): Kablo kesiti veya güzergah çizimde hiç yok. Otomatik kesit atanmaz; devre `VERİ_YETERSİZ` statüsüne alınır ve Belirsizlik Listesine (`UncertaintyItem`) eklenir.

### 2.2. Kanıta Dayalı Sembol Triyajı (Evidence-Based Symbol Triage)
AutoCAD projelerindeki anonim bloklar (`A$C...`, `*U...` vb.) doğrudan silinmez. `SymbolTriage` motoru her blok için 4 kanıt katmanını inceler:
1. **Mimari Kanıt:** Blok mimari XREF içinde veya MOBILYA/TEFRIS katmanında ve yakınında hiçbir elektrik sembolü/yazısı yoksa `IGNORED_ARCHITECTURAL` olarak filtrelenir ve raporda sayısal olarak özetlenir.
2. **Elektrik Katmanı Kanıtı:** Blok elektrik katmanındaysa (`E-POWER`, `00-AYDINLATMA` vb.) veya yakın çevresinde (yakın elektrik sembolü için 1000, yakın elektrik yazısı için 600 çizim birimi) elektrik sembolü/etiketi varsa silinmez; `UNCERTAIN_ELECTRICAL` statüsüne alınarak mühendis incelemesine sunulur.
3. **Kanıtsızlık Durumu:** Ne mimari ne de elektrik kanıtı bulunamayan bloklar `UNCLASSIFIED` statüsünde Belirsizlik Listesinde tutulur.
4. **Çelişki Yönetimi:** Bir blok hem mimari katmanda olup hem de bir aydınlatma armatürünün tam yanındaysa elektrik izi ağır basar ve blok asla silinmez.

### 2.3. Kademeli Eşleştirme (Graduated / Tiered Matching)
Raylı sistem ve büyük bina projelerinde kuvvetli akım dağıtım panoları ile topraklama paftaları, kablo kanalları ve kolon şemaları arasında üç kademeli eşleştirme uygulanır:
- **Tier 1 (Birebir & Normalize Eşleşme):** Pano etiketinin normalize hali topraklama etiketleri veya parçalarıyla birebir eşleşir (örn: `S19MCC301 == S19MCC301`). Güven: 1.0 (KESİN).
- **Tier 2 (Çekirdek Kod & Alt Parça Ayrıştırma):** Topraklama paftasındaki kompozit bağlantı etiketleri (örn: `TS19LVS401/S19MCC301/01`) alt bileşenlerine parçalanır; panonun çekirdek kodu (`MCC301`, `LVS401`, `İAP-E/301`) ile eşleştirilir. Güven: 0.85-0.90 (YÜKSEK).
- **Tier 3 (Kat / Mahal ECB İrtibatı):** Pano kodunun mahal numarası ile o katın Eşpotansiyel Barası (örn: `S19/ECB/051`) mahal bazında eşleştirilir. Güven: 0.80.

### 2.4. Şiddetin Kanıta Bağlanması (Evidence-Based Severity & Scope Handling)
Denetim motoru girdi kapsamı sınırlılığı ile gerçek mühendislik hatalarını birbirinden ayırır:
- **Durum A (Kısmi Set Koruması):** Kullanıcı 5 paftalık kısmi bir set yüklediğinde, kuvvetli akım panosunun bulunduğu katın `PS-17` topraklama paftası analiz setine hiç verilmemişse bu bir tasarım hatası değil, girdi kapsamı sınırlılığıdır. Asla `CRITICAL` veya `WARNING` üretilmez; `UncertaintyItem` (`UNC-GRND-SHEET-MISSING-...`) üretilerek durum `İNCELEME_GEREKLİ` (%50 güven) olarak işaretlenir.
- **Durum B (Mevcut Paftada Bulunamama):** O kata ait topraklama paftası analiz setinde mevcut olmasına rağmen panonun topraklama irtibat kodu bulunamıyorsa; isimlendirme varyasyonu ihtimali nedeniyle bulgu `CRITICAL` değil, `WARNING` (Güven: %70, MUHTEMEL) olarak üretilir.
- **Durum C (Doğrudan Standart İhlali):** Açıkça çizilmiş ve kanıtlanmış kural ihlallerinde (örn: TS HD 60364-4-43 Madde 433.1 uyarınca 4x4 mm² kabloya 32A sigorta ve 25A KAK takılması) bulgu `CRITICAL` (%100 KESİN) olarak raporlanır.

### 2.5. İstasyon Kodu ve Antet Hiyerarşisi
Öncelik Sırası: `1. Klasör Adı (M09-S24) > 2. Pafta Dosya Adı (AG-...-S24-...) > 3. DWG İçi Blok/Antet Metinleri`. Dosya adı S24 olduğu halde antette S28 Mimar Sinan yazıyorsa istasyon S24 kabul edilir ve `REC-STATION-TITLE-MISMATCH` mühendislik uyarısı üretilir.

---

## 3. Kullanılan Harici Programlar ve Sistem Bağımlılıkları

| Harici Araç / Çevre | Sistemdeki Yolu / Türü | Çalışma Mantığı ve Entegrasyonu |
| :--- | :--- | :--- |
| **AutoCAD Core Console** (`accoreconsole.exe`) | `C:\Program Files\Autodesk\AutoCAD 20XX\accoreconsole.exe` | Autodesk'in GUI'siz konsol motorudur. Script üzerinden `FILEDIA 0 -> _AUDIT _Y -> _DXFOUT dosya 16 -> _QUIT _Y` komut dizisini çalıştırır. Bozuk nesneleri onararak temiz ASCII DXF üretir. |
| **AutoCAD COM Automation** (`win32com.client`) | `AutoCAD.Application` ActiveX / COM | Core Console bulunamadığında arka planda görünmez (`Visible=False`) bir AutoCAD açarak Audit ve DXFOUT uygular. |
| **Merkezi DXF Önbelleği** (`.dxf_cache/`) | `D:\autocad projesi\.dxf_cache` | `{safe_stem}_{st_size}_{st_mtime}.dxf` hash formatında çalışır. Dosya sonundaki `EOF` ve `ENDSEC` kontrolleri ile yarım kalmış dosyalar otomatik tespit edilip baştan onarılır. |
| **Python 3.11 Sanal Ortamı** (`venv`) | `D:\autocad projesi\venv` | İzole çalışma ortamı. Tüm CLI komutları ve pytest testleri bu sanal ortamda koşar. |

---

## 4. Kullanılan Python Kütüphaneleri ve Fonksiyonları

| Kütüphane | Sürüm | İçe Aktarıldığı Modüller | Mühendislik Fonksiyonu ve Rolü |
| :--- | :--- | :--- | :--- |
| `ezdxf` | >=1.3.0 | `core/cad/reader.py`, `core/topology/route_builder.py` | AutoCAD DXF parsing; INSERT, LINE, LWPOLYLINE, TEXT, MTEXT, ATTRIB nesnelerini okuma. Not: `dxf_converter.py` ezdxf kullanmaz; accoreconsole/COM subprocess çalıştırır. |
| `shapely` | >=2.0.0 | `core/cad/geometry.py`, `core/cad/frame_detector.py`, `core/cad/triage.py` | 2D poligon kesişimleri, Bounding Box, iç içe pafta sınırları ve semboller arası mesafe ölçümü. |
| `networkx` | >=3.3 | `core/topology/route_builder.py`, `core/topology/circuit_resolver.py` | Devre topolojisi ve kablo güzergahları için graf teorisi. Minimum Spanning Tree (MST) kablo boyu hesabı. |
| `python-docx` | >=1.2.0 | `tools/generate_system_guide.py`, `legacy/*/docx_reporter.py` | Microsoft Word (.docx) formatında resmi denetim raporları ve kılavuz dokümantasyon üretimi. |
| `openpyxl` & `xlrd` | >=3.1.0, >=2.0.1 | `legacy/yukleme_cetveli`, `legacy/topraklama_motoru` | Excel yükleme cetvelleri (.xlsx/.xls) okuma — yalnızca v1.0 legacy modüller. **v2.0 çekirdek motoru Excel okumaz; tüm linye verisi çizimden alınır.** |
| `numpy` | >=1.26.0 | `legacy/superpose_motoru` | Süperpoze çakışma analizinde sayısal matrisler (legacy). `electrical_calc.py` saf Python'dır. |
| `matplotlib` | >=3.9.0 | `legacy/superpose_motoru`, `legacy/topraklama_motoru` | Koordinasyon planları, süperpoze çakışma haritaları ve redline PNG görselleştirmeleri (legacy). |
| `PyYAML` | >=6.0 | `core/rules/rule_engine.py` | YAML kural paketlerinin (turkey_bina/ibb_metro) yüklenmesi; yönetmelik eşikleri koddan ayrı tutulur. |
| `pywin32` | >=306 | `common/dxf_converter.py` | Windows ActiveX ve AutoCAD COM Automation arayüzü kontrolü. |
| `pytest` | >=9.1.0 | `tests/test_reference_projects.py` | 13 Altın Referans Testinin deterministik ve otomatik doğrulanması (denetim + healer + regresyon). |

---

## 5. Mimari Kod Haritası (Hangi Dosya Nerede, Neye Bağlı?)

```text
D:\autocad projesi\
├── cloudecad.py                      <- MERKEZİ GİRİŞ NOKTASI (Unified CLI, Interactive Menu, Watch Mode)
├── batch_inspector.py                <- Toplu Proje Denetim Köprüsü (Klasör İzleme & Tarama)
├── cloudecad.bat                     <- Hızlı Başlatıcı (UTF-8 güvenli venv sarmalayıcısı)
├── otomatik_denetim.bat              <- Tek Tıkla Toplu Denetim / Watch Servisi Menüsü
├── tools/
│   ├── generate_system_guide.py      <- BU REHBERİ DERLEYEN BETİK (docx + md tek komutla yenilenir)
│   ├── field_run_healer.py           <- SAHA İNDİRİM: gerçek paftalarda Healer zinciri (v3.0)
│   ├── review_station.py             <- ONAY İSTASYONU: FastAPI + kural bazlı toplu triyaj (v3.0)
│   └── compose_delivery.py           <- COMPOSER: DXF→DWG + teslim paketi; başarısız olursa COM ile orijinal DWG üzerinden onarır (v3.0)
├── jobs/                             <- İş kabul/üretim klasörü (JOB-YYYY-*; plans/output/redline/delivery)
├── CLOUDECAD_SISTEM_REHBERI.docx     <- RESMİ SİSTEM MİMARİSİ VE ÇALIŞMA PRENSİPLERİ REHBERİ (WORD)
├── CLOUDECAD_SISTEM_REHBERI.md       <- SİSTEM REHBERİ (MARKDOWN KOPYASI)
├── tests/
│   └── test_reference_projects.py    <- 13 ADET GOLD-STANDARD BİRİM, DENETİM VE HEALER TESTİ
├── lispkodlar/                       <- AutoCAD Üretim Hızlandırma LISP Araçları (kullanıcı aracı)
├── ornekprojeler/                    <- Tekil Örnek DWG Girdileri (--file modu)
├── incelenecek projeler/             <- Toplu Denetim Girdi Klasörü (--scan / --watch)
├── projelerin inceleme sonuçları/    <- Üretilen Denetim Raporları (varsayılan çıktı klasörü)
├── raporlar/                         <- Proje Onay Evrakları & Yükleme Cetvelleri (arşiv)
├── ErrorReports/                     <- Çökme tanılama kayıtları
├── cloudecadprogramı/
│   ├── requirements.txt              <- Python Paket Bağımlılıkları
│   ├── kur.bat                       <- Sanal Ortam + Paket Kurulum Betiği
│   ├── common/
│   │   ├── dxf_converter.py          <- accoreconsole / COM DWG->DXF Dönüştürücü ve .dxf_cache Yöneticisi
│   │   ├── com_dwgs.py               <- COM tabanlı DWG Düzeltici (ezdxf yazımı AutoCAD'i çökertirse yedek yol)
│   │   ├── universal_cad_reader.py   <- Geriye Dönük Uyumluluk Sarmalayıcısı (-> core/cad/reader.py)
│   │   └── station_audit_engine.py   <- Geriye Dönük Uyumluluk Sarmalayıcısı (-> core/engine.py)
│   ├── core/
│   │   ├── engine.py                 <- ORKESTRASYON MOTORU (UnifiedAuditEngine; StationAuditEngine takma adı)
│   │   ├── cad/
│   │   │   ├── reader.py             <- UniversalCADReader (DXF -> DrawingSceneGraph + Handle Provenance)
│   │   │   ├── cad_safety.py         <- CADSafetyGuard & UnitScaleResolver (XREF, Block Def, CTB, INSUNITS, MTEXT)
│   │   │   ├── frame_detector.py     <- FrameDetector (İç İçe Paftalar, Antetler, Kat Planı Bölgeleri)
│   │   │   ├── triage.py             <- SymbolTriage (Kanıta Dayalı Anonim Blok ve Sembol Triyajı)
│   │   │   ├── classifier.py         <- Sembol Sınıflandırıcı ve Lejant Analizi
│   │   │   └── geometry.py           <- Shapely 2D Geometri ve Uzaysal İndeksleme Yardımcıları
│   │   ├── healer/                   <- v3.0 OTOMATİK ONARIM, OPTİMİZASYON VE YENİDEN ÜRETİM MOTORU
│   │   │   ├── layer_doctor.py       <- Modül 1: LayerAndBlockDoctor (Katman Standardizasyonu & Mimari Kilit)
│   │   │   ├── wire_healer.py        <- Modül 2: TopologicalWireHealer (4 Şartlı Stitch, Snap & Overkill)
│   │   │   ├── electrical_optimizer.py <- Modül 3: ElectricalAutoOptimizer (ASBUILT/DESIGN & Re-Verify)
│   │   │   └── table_generator.py    <- Modül 4: CADTableGenerator (DWG Yükleme Cetveli & .xlsx Üretici)
│   │   ├── calculators/
│   │   │   └── electrical_calc.py    <- Elektrik Mühendisliği Hesaplayıcıları (Iz, e%, Faz Dengesi, PE Kesit)
│   │   ├── model/
│   │   │   ├── entities.py           <- CAD Varlık Modelleri (DrawingSceneGraph, PlacedSymbol, TextToken...)
│   │   │   └── audit.py              <- Denetim & Rapor Modelleri (StationAuditReport, AuditFinding...)
│   │   ├── reconciliation/
│   │   │   └── cross_sheet_engine.py <- ÇAPRAZ MUTABAKAT MOTORU (Plan vs Tablo, Pano vs Topraklama PS-17)
│   │   ├── rules/
│   │   │   ├── rule_engine.py        <- Dinamik Kural Paketi Yöneticisi ve TS HD 60364-5-52 Tabloları
│   │   │   └── packs/
│   │   │       ├── turkey_bina.yaml  <- Türkiye Bina & Tesis Elektrik Yönetmeliği Kural Paketi
│   │   │       └── ibb_metro.yaml    <- İBB Raylı Sistemler As-Built Elektrik Şartnamesi Paketi
│   │   ├── topology/
│   │   │   ├── circuit_resolver.py   <- Mantıksal Linye ve Devre Çözümleyici
│   │   │   └── route_builder.py      <- Fiziksel Kablo Güzergahı ve Ağaç Oluşturucu
│   │   └── reporters/
│   │       ├── markdown_reporter.py  <- Markdown (.md) Formatında Mühendislik Raporu Üreteci
│   │       └── json_reporter.py      <- JSON Formatında Tam Yapılandırılmış Denetim Verisi Üreteci
│   └── legacy/                       <- v1.0 Eski İzole Modüller (Referans & Arşiv Amaçlı)
└── .dxf_cache/                       <- Dönüştürülmüş ve Onarılmış DXF Dosyaları Önbelleği
```

---

## 6. Beş Çekirdek Denetim Modülünün İşleyişi

1. **Modül 1 — Kuvvetli Akım ve Pano Faz Yük Dengesi:**
   - Kat planlarındaki linyeler çizimden (DXF) toplanır. Not: v2.0 çekirdek motoru Excel okumaz; openpyxl/xlrd yalnız legacy modüllerdedir.
   - Pano bazında faz yük dengesizliği: `Δ% = ((I_max - I_min) / I_max) * 100` formülüyle denetlenir. Sınırlar aktif kural paketinden okunur: İBB metro paketi %15 Uyarı / **%20 Kritik**; bina paketi %15 Uyarı / %25 Kritik.
   - Kablo akım taşıma kapasitesi ($I_z$) ve gerilim düşümü hesaplanır.

2. **Modül 2 — Paftalar Arası Çapraz Mutabakat:**
   - Plan vs Metraj Tablosu: Kuvvetli akım planındaki (PS-11) kablo etiketleri ile tablodaki satırlar karşılaştırılır (`REC-TBL-OMIT`).
   - Pano vs Topraklama: Dağıtım panoları ile topraklama paftaları (PS-17, GN-14) kademeli eşleştirmeye tabi tutulur.

3. **Modül 3 — Zayıf Akım 11 Alt Sistem Analizi:**
   - `AX-02` Yangın Algılama ve `TL-02..TL-11` alt sistemleri pafta dosya adından dinamik tanınır; harita M09 hattı DXF içerik analiziyle doğrulanmıştır: TL-02 LAN/F.O., TL-03 Telefon/SOS, TL-04 TETRA/Anten, TL-05 Anons (PA/VA), TL-06 CCTV, TL-07 Saat, TL-08 Kartlı Geçiş, TL-09 SCADA, TL-10 Yolcu Bilgilendirme (PIS), TL-11 Sistem Odası Rack.
   - Kolon şeması ile kat planı sembol sayıları karşılaştırılır.
   - CAT6 kablolarda 90 metre sınır kontrolü, acil hatlarda FE180 yangına dayanıklı kablo kontrolü yapılır.

4. **Modül 4 — Topraklama ve Tava Kapsamı:**
   - Eşpotansiyel Baralar (`S19/ECB/...`), Trafo/Pano bağlantıları (`TS19...`), Kablo tavaları ve merdiven metrajları özetlenir.

5. **Modül 5 — Belirsizlik Listesi ve Güven Analizi (Uncertainty Review List):**
   - Fonksiyonu kanıtlanamayan bloklar (`UNC-SYM-...`), kesiti yazılmamış linyeler (`UNC-MISSING-CABLE-...`) ve paftası eksik panolar (`UNC-GRND-SHEET-MISSING-...`) raporda mühendise sunulur.

---

## 6B. v3.0 Onarım ve Üretim Hattı (Healer + Onay İstasyonu + Composer)

Akış: **Saha Koşumu → Onay İstasyonu → Composer.**

1. **Healer Katmanı:** `core/healer/` — LayerAndBlockDoctor, TopologicalWireHealer (4 şartlı stitch), ElectricalAutoOptimizer (ASBUILT/DESIGN frenli), CADTableGenerator (DWG cetveli + .xlsx). Ortak kalkan: `core/cad/cad_safety.py`.
2. **Saha Koşumu:** `tools/field_run_healer.py` — zinciri gerçek paftalarda koşar; temiz DXF + imzalı defter + redline üretir. Saha kanıtı: 7 S19 paftası, 58.000+ korunan varlık, %141,7 dengesizlik reçetesi.
3. **Onay İstasyonu:** `tools/review_station.py` — kural bazlı toplu triyaj, tekil onay/ret, statü koruması, redline; her karar SHA-256 imzalı deftere yazılır (kilit + atomik yazma).
4. **Composer:** `tools/compose_delivery.py` — onaylı DXF → DWG 2018 + teslim paketi. Kademeli dönüşüm: accoreconsole → SPLINE temizliği → **COM onarımı** (`common/com_dwgs.py`; ezdxf yazımının AutoCAD 2027'yi çökerttiği paftalar için kalıcı çözüm, düzenlemeler orijinal DWG üzerinde AutoCAD API ile uygulanır).
5. **İş Klasörü:** `jobs/JOB-*/` — intake.yaml, output/, plans/, applied/, redline/, delivery/, RESPONSIBILITE_DEFTERI.json, canlı RAPOR.md.

### 6B.1 Modül Olgunluk Tablosu

| Katman | Konum | Durum | Not |
| :--- | :--- | :--- | :--- |
| Denetim motoru (engine, cross_sheet, rules, reporters) | `core/` | AKTİF-ÜRETİM | 13 test; İBB saha raporlarıyla doğrulanmış |
| CAD okuma + triyaj + pafta tespiti | `core/cad/` | AKTİF-ÜRETİM | 388 DXF önbelleğinde gerçek paftalarla çalışıyor |
| Healer 4 modülü + güvenlik kalkanı | `core/healer/` + `core/cad/cad_safety.py` | AKTİF-PROTOTİP | 7 pafta saha koşumu + 13 test |
| Onay İstasyonu | `tools/review_station.py` | AKTİF-PROTOTİP | Tek kullanıcılı; onay akışı doğrulandı |
| Composer + COM onarımı | `tools/compose_delivery.py` + `common/com_dwgs.py` | AKTİF-PROTOTİP | 7/7 DWG üretildi; COM AutoCAD GUI başlatır |
| CAT6 90 m fiziksel ölçüm | `core/topology/` | YARIM | Gerçek M09 setinde CAT6/UTP yalnızca antet notlarında geçiyor (devre bazlı etiket yok) → çoğu paftada ölçülemez, UNC-CAT6-SPAN belirsizliği beklenir |
| Metro pafta kodu tanıma | `core/engine.py` | AKTİF (M09 odaklı) | AX/TL/PS/GN/ELM/USK/PRT doğrulandı; diğer hatlar genişletme ister |
| Excel yükleme cetveli okuma | `legacy/` | LEGACY-ARŞİV | v2.0 çekirdeği Excel okumaz |
| Süperpoze / topraklama motoru (v1) | `legacy/` | LEGACY-ARŞİV | Referans |
| BIM/IFC/Revit parser | — | YOK (yol haritası) | Çekirdek DXF/DWG odaklı |
| LLM/vision çizim anlama | — | YOK | Heuristik + geometri + kanıt zinciri yaklaşımı |

> **Sıfır Varsayım istisnası (belgelenmiş):** CADTableGenerator, fazı okunamayan linyeleri tabloda üç faza
> eşit paylaştırır ve bunu **(faz belirsiz — TAHMİNİ eşit dağıtım)** etiketiyle ESTIMATED_DEFAULT olarak
> raporlar. Denetim motorunda belirsiz faz asla varsayılmaz; belirsizlik maddesi açılır.

---

## 7. Mevzuat, Standartlar ve Kabul Kriterleri

- **TS HD 60364-5-52:2014 (Çizelge B.52.2 - B.52.5):** XLPE 90°C ve PVC 70°C, B1/C/E döşeme yöntemleri, sıcaklık ve gruplama katsayıları.
- **TS HD 60364-4-43 Madde 433.1:** $I_b \le I_n \le I_z$ ve $I_n \le I_{n,KAK}$ aşırı akım koordinasyonu.
- **BYKHY Madde 72 & 83:** Yangın pompası beslemesinde FE180 kablo zorunludur; 30mA KAK kullanımı kesinlikle yasaktır.
- **İBB Raylı Sistemler As-Built Elektrik Şartnamesi:** Faz dengesizliği $\le \%15$ (Uyarı) / $\%20$ (Kritik — metro paketi; bina paketinde $\%25$); CAT6 kanal mesafesi maks. 90m.
- **EN 50122-1 & ETTY:** İstasyon dağıtım panolarının ana topraklama ağına irtibat kodu zorunluluğu.
- **IEC 60364-5-54 Madde 543.1:** Faz kesitine göre PE iletkeni minimum kesit kontrolü ($S \le 16 \to S$, $16 < S \le 35 \to 16$, $S > 35 \to S/2$).

---

## 8. Doğrulama ve Test Mimarisi (Gold-Standard Test Paketi)

| Test Adı | Kapsam ve Denetlenen Kural | Beklenen Deterministik Sonuç |
| :--- | :--- | :--- |
| `test_ref01_clean_pass_metro_station` | Eksiksiz metro istasyonu modeli. | 0 Kritik Hata, 0 Uyarı, PASS. |
| `test_ref02_known_violations_project` | Gerilim düşümü ihlali, sigorta koordinasyon hatası ve yangın pompası 30mA KAK ihlali. | Tüm ihlallerin CRITICAL olarak %100 KESİN yakalanması. |
| `test_ref03_missing_data_and_uncertainties` | Kesiti yazılmamış eksik projeler. | Otomatik 25A atanmaz; `UNC-MISSING-CABLE-SPEC` üretilir. |
| `test_ref04_tshd60364_ampacity_table_accuracy` | TS HD 60364-5-52 akım taşıma tablosu doğruluğu. | PVC/XLPE, B1/C/E akım değerleri birebir uyuşur; 999mm² None döner. |
| `test_ref05_station_code_priority_and_markdown_reporter` | S24 dosyasında S28 antet metni bulunması. | İstasyon S24 seçilir, antet uyumsuzluğu raporlanır. |
| `test_ref06_symbol_triage_evidence_based` | Anonim blokların 4 kanıt süzgeciyle triyajı. | Mimari elenir, elektrik korunur, armatür yanındakiler silinmez. |
| `test_ref07_metro_sheet_codes_and_station_grounding_are_dynamic` | PS-08 ve GN-14 dinamik pafta tanıma. | Dinamik istasyon kodları ve ECB/TS bağlantıları özetlenir. |
| `test_ref08_graduated_grounding_reconciliation` | Kademeli topraklama eşleştirme ve kanıta bağlı şiddet. | Kompozit etiketler Tier 2 ile UYGUN eşleşir; kat paftası eksikse hata değil belirsizlik açılır; paftada bulunamayan pano WARNING olur. |
| `test_ref09_layer_doctor_and_cad_safety` | Modül 1 (`LayerAndBlockDoctor`) ve `cad_safety.py` 3 tuzak koruması. | XREF ve Blok Tanımı korunur; `IGNORED_ARCHITECTURAL` elemanlar `A-MIMARI-ALTYAPI` (Color 8, 0.09mm, Kilitli) katmanına taşınır; imzalı `applied_changes.json` üretilir. |
| `test_ref10_topological_wire_healer_4_conditions` | Modül 2 (`TopologicalWireHealer`) 4 şartlı doğrusal birleştirme, yan yana paralel hat mayın koruması, OVERKILL ve Snap. | 4/4 koşulu sağlayan kopukluk köprülenir; yan yana paralel hatlar (~90° köprü) ve `W1` vs `W2` farklı devreler `REQUIRES_APPROVAL` olarak durdurulur. |
| `test_ref11_electrical_optimizer_asbuilt_vs_design_and_reverify` | Modül 3 (`ElectricalAutoOptimizer`) `ASBUILT` vs `DESIGN` iş tipi freni ve Öner -> Yeniden Doğrula -> Onayla -> Uygula zinciri. | `ASBUILT` faz değişimi DWG'ye uygulanamaz; `DESIGN` modunda Greedy LPT dengesizliği %0'a indirir; FE180 ve koruma koordinasyonu bellekte yeniden doğrulanıp MTEXT formatı korunarak işlenir. |
| `test_ref12_cad_table_generator_dwg_and_xlsx` | Modül 4 (`CADTableGenerator`) DWG içi LINE+TEXT yükleme cetveli çizimi, mevcut tablo hücresi güncelleme ve `.xlsx` üretimi. | `E-ETIKET-TABLO` katmanında ölçekli cetvel ızgarası çizilir, mevcut hücre handle'ı onay kapısından geçerek güncellenir ve kurumsal Excel (`.xlsx`) dosyası oluşturulur. |
| `test_ref13_all_11_audit_fixes_regression` | Canlı denetimde yakalanan 11 kritik/orta/küçük bulgunun regresyon doğrulaması. | Faz token Değişmezlik Kalkanı (`L2-01 3x2.5 NYY` korunur), dinamik kural paketi sınırları, `STRtree` hızlandırması, Duplicate devre çelişki koruması, kademeli Snap ve Unitless `cm` tespiti doğrulanır. |

**Test Çalıştırma:**
```powershell
& "D:\autocad projesi\venv\Scripts\python.exe" -m pytest "D:\autocad projesi\tests" -v
```

---

## 9. Kullanım Kılavuzu (CLI & İzleme Servisi)

```powershell
# İnteraktif Menü
python cloudecad.py

# Tekil Pafta İncelemesi
python cloudecad.py --file "D:\autocad projesi\ornekprojeler\faruk demir 10 lu - Elektrik.dwg"

# İstasyon Klasörü Denetimi
python cloudecad.py "D:\autocad projesi\incelenecek projeler\işsonları_duzenlenmis\M09-S19_Masko"

# Toplu Tarama (Batch Scan)
python cloudecad.py --scan

# Sürekli İzleme Servisi (Watch Mode - Klasöre dosya atıldıkça otomatik denetim)
python cloudecad.py --watch

# v3.0 SAHA İNDİRİM: Healer zinciri (temiz DXF + mesuliyet defteri + redline)
python tools/field_run_healer.py

# v3.0 ONAY İSTASYONU: kural bazlı toplu triyaj + tekil onay/ret (yerel web arayüzü)
python tools/review_station.py --job jobs/JOB-2026-S19-SAHA-01 --port 8765

# v3.0 COMPOSER: temiz DXF -> DWG 2018 + teslim paketi (delivery/)
python tools/compose_delivery.py --job jobs/JOB-2026-S19-SAHA-01
```

---

## 10. Gelecekteki Geliştiriciler ve Yapay Zeka İçin Bakım Protokolü

1. **Kod Değişikliği Öncesi Bu Belgeyi Kontrol Edin:** Değişiklik yapılacak modülün bu rehberdeki bağımlılıklarını inceleyin.
2. **Sıfır Varsayım İlkesini Asla İhlal Etmeyin:** Çizimde yazmayan hiçbir veriyi koda sabit olarak gömmeyin. Veri eksikse `UncertaintyItem` açın.
3. **Kural Değişikliklerini YAML Dosyalarında Yapın:** Yönetmelik parametrelerini `turkey_bina.yaml` veya `ibb_metro.yaml` dosyalarında yönetin.
4. **Test Paketini Çalıştırın:** Yapılan her değişiklikten sonra `pytest tests/test_reference_projects.py -v` komutu ile 13 testin tümünün yeşil olduğunu doğrulayın.
5. **Bu Rehberi Güncelleyin:** Yeni bir kural, CAD filtresi veya modül eklendiğinde bu dokümanı (`CLOUDECAD_SISTEM_REHBERI.docx` ve `.md`) güncel tutun.
"""
    MD_OUTPUT_PATH.write_text(md_content, encoding="utf-8")
    print(f"✓ MD created successfully: {MD_OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    generate_documents()
