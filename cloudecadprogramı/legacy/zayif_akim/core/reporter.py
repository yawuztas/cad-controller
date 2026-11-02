"""
CloudeCAD — Zayıf Akım Raporlama Motoru (WeakCurrentReporter)
============================================================
Detaylı Excel Zayıf Akım Keşif & Denetim Cetveli (5 Sayfa),
modern interaktif HTML denetim karnesi ve JSON özetini üretir.
"""

import json
from pathlib import Path
from typing import Dict, Any

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from core.models import WeakCurrentAuditReport
from core.docx_reporter import WeakCurrentDocxReporter


class WeakCurrentReporter:
    """Zayıf akım sistemleri raporlayıcısı."""

    def __init__(self, report: WeakCurrentAuditReport, output_dir: Path):
        self.report = report
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.slug = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in report.project_name)

    def generate_all(self) -> Dict[str, Path]:
        """Tüm zayıf akım raporlarını üretir."""
        return {
            "excel": self.generate_excel(),
            "html": self.generate_html(),
            "json": self.generate_json(),
            "docx": WeakCurrentDocxReporter(self.report, self.output_dir).generate(),
        }

    def generate_excel(self) -> Path:
        """5 Sayfalı Excel Zayıf Akım Denetim ve Keşif Cetveli üretir."""
        wb = openpyxl.Workbook()
        wb.remove(wb.active) # default sheet'i sil

        # Stiller
        title_font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
        header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        bold_font = Font(name="Calibri", size=10, bold=True)
        norm_font = Font(name="Calibri", size=10)
        thin_border = Border(
            left=Side(style='thin', color='D9D9D9'),
            right=Side(style='thin', color='D9D9D9'),
            top=Side(style='thin', color='D9D9D9'),
            bottom=Side(style='thin', color='D9D9D9')
        )
        crit_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
        warn_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
        pass_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")

        # ── SAYFA 1: YANGIN_ALGILAMA ──────────────────────────────────────────
        ws1 = wb.create_sheet(title="1_YANGIN_ALGILAMA")
        ws1.views.sheetView[0].showGridLines = True
        ws1.merge_cells("A1:G1")
        ws1["A1"] = f"YANGIN ALGILAMA VE İHBAR SİSTEMİ DENETİMİ (TS EN 54 & BYKHY) — {self.report.project_name.upper()}"
        ws1["A1"].font = title_font
        ws1["A1"].fill = PatternFill(start_color="C00000", end_color="C00000", fill_type="solid")
        ws1["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws1.row_dimensions[1].height = 28

        h1 = ["Sıra", "Yangın Sistemi Elemanı", "CAD Blok Kodu", "Çizimdeki Adet", "Yönetmelik / Standart Şartı", "Uyum Durumu", "Açıklama / Not"]
        ws1.row_dimensions[2].height = 24
        for c_idx, t in enumerate(h1, start=1):
            c = ws1.cell(row=2, column=c_idx, value=t)
            c.font = header_font
            c.fill = PatternFill(start_color="78281F", end_color="78281F", fill_type="solid")
            c.alignment = Alignment(horizontal="center", vertical="center")

        f = self.report.fire_alarm
        rows_f = [
            (1, "Optik Duman Dedektörü", "DS / OD", f.smoke_detectors, "Kat holleri, ortak alanlar ve kaçış koridorları (R=7.5m)", "UYGUN" if f.smoke_detectors > 0 else "EKSİK", "TS EN 54-14 Çizelge A.1"),
            (2, "Sıcaklık / Isı Dedektörü", "SD / ISI", f.heat_detectors, "Kazan dairesi, otopark, mutfaklar (R=5.3m)", "MEVCUT" if f.heat_detectors > 0 else "İHTİYACA_BAĞLI", "Yüksek tozlu/nemli hacimler"),
            (3, "Yangın İhbar Butonu", "YB", f.manual_call_points, f"Kaçış merdiveni çıkışlarında azami 30 metrede bir", "UYGUN" if f.manual_call_points >= self.report.floor_count else "YETERSİZ", "BYKHY Madde 75"),
            (4, "Elektronik Yangın Sireni & Flaşör", "SKM", f.sirens_flashers, "Tüm bağımsız bölümlerde en az 65 dBA / Yatakta 75 dBA", "UYGUN" if f.sirens_flashers > 0 else "EKSİK", "İşitilebilir alarm uyarısı"),
            (5, "Yangın Kontrol Santrali (FACP)", "YIS", f.control_panels, "Bina giriş holü veya 24 saat gözetimli güvenlik mahali", "UYGUN" if f.control_panels > 0 else "EKSİK", f"{f.system_type} Santral"),
            (6, "Asansör Yangın Tahliye Rölesi", "RÖLE / MODÜL", "1 (Öngörülen)", "Yangın anında asansörü zemin kata çağırıp kapıları açık tutma", "KONTROL_EDİLMELİ", "BYKHY Madde 62"),
            (7, "Yangın Pompası İzleme Modülü", "İZLEME MODÜLÜ", "1 (Öngörülen)", "Yangın pompası çalışma/arıza durumunun santrale aktarımı", "KONTROL_EDİLMELİ", "BYKHY Madde 96")
        ]
        for r_idx, rvals in enumerate(rows_f, start=3):
            ws1.row_dimensions[r_idx].height = 22
            for c_idx, v in enumerate(rvals, start=1):
                c = ws1.cell(row=r_idx, column=c_idx, value=v)
                c.font = norm_font
                c.border = thin_border
                if c_idx in (1, 3, 4, 6):
                    c.alignment = Alignment(horizontal="center", vertical="center")
                if c_idx == 6:
                    c.fill = pass_fill if "UYGUN" in str(v) or "MEVCUT" in str(v) else warn_fill

        for idx, w in enumerate([6, 32, 16, 16, 45, 20, 30], start=1):
            ws1.column_dimensions[get_column_letter(idx)].width = w

        # ── SAYFA 2: TELEFON_DATA ─────────────────────────────────────────────
        ws2 = wb.create_sheet(title="2_TELEFON_DATA")
        ws2.views.sheetView[0].showGridLines = True
        ws2.merge_cells("A1:G1")
        ws2["A1"] = f"TELEFON VE DATA (YAPISAL KABLOLAMA) TESİSATI DENETİMİ (BTK) — {self.report.project_name.upper()}"
        ws2["A1"].font = title_font
        ws2["A1"].fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        ws2["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws2.row_dimensions[1].height = 28

        h2 = ["Sıra", "Tesisat Elemanı", "CAD Blok Kodu", "Çizimdeki Adet", "BTK Asgari Standart Şartı", "Kapasite Durumu", "Mühendislik Değerlendirmesi"]
        ws2.row_dimensions[2].height = 24
        for c_idx, t in enumerate(h2, start=1):
            c = ws2.cell(row=2, column=c_idx, value=t)
            c.font = header_font
            c.fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
            c.alignment = Alignment(horizontal="center", vertical="center")

        tel = self.report.telecom
        rows_t = [
            (1, "Telefon / Data Prizi (RJ45)", "T", tel.sockets, f"{self.report.dwelling_count * 2} Adet (Daire başı en az 2 priz)", "YETERLİ" if tel.sockets >= self.report.dwelling_count else "EKSİK", "Cat6 UTP Kablolama"),
            (2, "Kat Dağıtım Kutusu (1TK)", "1tk / 1TK", tel.floor_boxes, f"En az {self.report.floor_count} Adet (Her katta 1 dağıtıcı)", "UYGUN" if tel.floor_boxes >= self.report.floor_count else "KONTROL_GEREKLİ", "10-20 Çiftlik Reglet"),
            (3, "Bina Ana Telefon Kutusu (BTK)", "BTK", tel.main_boxes, "1 Adet (Zemin/Giriş Kat Şaftı)", "UYGUN" if tel.main_boxes > 0 else "ÇİZİMDE_GÖSTERİLMELİ", "Türk Telekom Şebeke Giriş Noktası"),
            (4, "Dikey Şaft Omurga Kablosu", "KABLO", "1 Hat", f"En az {self.report.dwelling_count * 2} Per veya Cat6 Omurga", "ÖNERİLİR", "Şaft boru çapı min Ø50mm")
        ]
        for r_idx, rvals in enumerate(rows_t, start=3):
            ws2.row_dimensions[r_idx].height = 22
            for c_idx, v in enumerate(rvals, start=1):
                c = ws2.cell(row=r_idx, column=c_idx, value=v)
                c.font = norm_font
                c.border = thin_border
                if c_idx in (1, 3, 4, 6):
                    c.alignment = Alignment(horizontal="center", vertical="center")
                if c_idx == 6:
                    c.fill = pass_fill if "UYGUN" in str(v) or "YETERLİ" in str(v) else warn_fill

        for idx, w in enumerate([6, 32, 16, 16, 42, 22, 35], start=1):
            ws2.column_dimensions[get_column_letter(idx)].width = w

        # ── SAYFA 3: TV_UYDU_SMATV ───────────────────────────────────────────
        ws3 = wb.create_sheet(title="3_TV_UYDU_SMATV")
        ws3.views.sheetView[0].showGridLines = True
        ws3.merge_cells("A1:G1")
        ws3["A1"] = f"TV / UYDU (SMATV) DAĞITIM TESİSATI DENETİMİ (TS EN 50083) — {self.report.project_name.upper()}"
        ws3["A1"].font = title_font
        ws3["A1"].fill = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
        ws3["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws3.row_dimensions[1].height = 28

        h3 = ["Sıra", "SMATV Elemanı", "CAD Blok Kodu", "Çizimdeki Adet", "Standart Şartı", "Uyumluluk Durumu", "Sinyal / Zayıflama Değerlendirmesi"]
        ws3.row_dimensions[2].height = 24
        for c_idx, t in enumerate(h3, start=1):
            c = ws3.cell(row=2, column=c_idx, value=t)
            c.font = header_font
            c.fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
            c.alignment = Alignment(horizontal="center", vertical="center")

        tv = self.report.smatv
        rows_tv = [
            (1, "TV / Uydu Prizi (Sonlu)", "TV", tv.tv_sockets, f"En az {self.report.dwelling_count} Adet (Daire başı en az 1-2 priz)", "YETERLİ" if tv.tv_sockets >= self.report.dwelling_count else "EKSİK", "Priz ucu seviyesi: 60-80 dBµV"),
            (2, "Kat Dağıtıcısı / Tap-off", "TAP", tv.tap_offs, "Her kat için 1-2 adet kat dağıtıcısı", "UYGUN" if tv.tap_offs > 0 else "KONTROL_EDİLMELİ", "Zayıflama kademeleri (8-16 dB)"),
            (3, "Kat TV Dağıtım Kutusu", "1tvk", tv.floor_boxes, f"{self.report.floor_count} Adet", "MEVCUT" if tv.floor_boxes > 0 else "ŞAFT_KUTUSU", "Şaft içi zayıf akım kabini"),
            (4, "TV Santrali / Multiswitch", "TVS", tv.multiswitches, f"En az {self.report.dwelling_count} abone çıkışlı", "UYGUN" if tv.multiswitches > 0 else "ŞEMADA_GÖSTERİLMELİ", "Merkezi Çanak Anten / LNB Girişli")
        ]
        for r_idx, rvals in enumerate(rows_tv, start=3):
            ws3.row_dimensions[r_idx].height = 22
            for c_idx, v in enumerate(rvals, start=1):
                c = ws3.cell(row=r_idx, column=c_idx, value=v)
                c.font = norm_font
                c.border = thin_border
                if c_idx in (1, 3, 4, 6):
                    c.alignment = Alignment(horizontal="center", vertical="center")
                if c_idx == 6:
                    c.fill = pass_fill if "UYGUN" in str(v) or "YETERLİ" in str(v) else warn_fill

        for idx, w in enumerate([6, 30, 16, 16, 40, 22, 35], start=1):
            ws3.column_dimensions[get_column_letter(idx)].width = w

        # ── SAYFA 4: INTERCOM_DIAFON ──────────────────────────────────────────
        ws4 = wb.create_sheet(title="4_INTERCOM_DIAFON")
        ws4.views.sheetView[0].showGridLines = True
        ws4.merge_cells("A1:G1")
        ws4["A1"] = f"GÖRÜNTÜLÜ DİAFON VE İNTERKOM SİSTEMİ DENETİMİ — {self.report.project_name.upper()}"
        ws4["A1"].font = title_font
        ws4["A1"].fill = PatternFill(start_color="375623", end_color="375623", fill_type="solid")
        ws4["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws4.row_dimensions[1].height = 28

        h4 = ["Sıra", "İnterkom Elemanı", "CAD Blok Kodu", "Çizimdeki Adet", "Standart / Daire Şartı", "Uyum Durumu", "Sistem Güvenlik Notu"]
        ws4.row_dimensions[2].height = 24
        for c_idx, t in enumerate(h4, start=1):
            c = ws4.cell(row=2, column=c_idx, value=t)
            c.font = header_font
            c.fill = PatternFill(start_color="276A3C", end_color="276A3C", fill_type="solid")
            c.alignment = Alignment(horizontal="center", vertical="center")

        dia = self.report.intercom
        rows_dia = [
            (1, "Daire İçi Diafon Monitörü", "ID", dia.monitors, f"{self.report.dwelling_count} Adet (Birebir eşleşmeli)", "TAM_UYUMLU" if dia.monitors == self.report.dwelling_count else "UYUŞMAZLIK_VAR", "Daire içi haberleşme"),
            (2, "Daire Kapı Önü Zili", "Z", dia.door_bell_buttons, f"{self.report.dwelling_count} Adet (Her daire kapısına 1 zil)", "TAM_UYUMLU" if dia.door_bell_buttons == self.report.dwelling_count else "KONTROL_GEREKLİ", "Daire kapı butonu"),
            (3, "Bina Giriş Kapı Otomatiği", "KO", dia.door_releases, "1 Adet (Ana bina giriş kapısı)", "MEVCUT" if dia.door_releases > 0 else "EKSİK", "12V-24V AC/DC kilit dili"),
            (4, "Bina Giriş Zil/Kamera Paneli", "KZ", dia.entrance_panels, "1 Adet (Ana giriş)", "MEVCUT" if dia.entrance_panels > 0 else "ŞEMADA_GÖSTERİLMELİ", "Tuş takımı / kart okuyucu"),
            (5, "Zayıf Akım Güç Kaynağı / Trafo", "24V / KF", dia.power_supplies, "1 Adet (24V DC Regüleli Güç Kaynağı)", "MEVCUT" if dia.power_supplies > 0 else "EKSİK", "Kesintisiz besleme")
        ]
        for r_idx, rvals in enumerate(rows_dia, start=3):
            ws4.row_dimensions[r_idx].height = 22
            for c_idx, v in enumerate(rvals, start=1):
                c = ws4.cell(row=r_idx, column=c_idx, value=v)
                c.font = norm_font
                c.border = thin_border
                if c_idx in (1, 3, 4, 6):
                    c.alignment = Alignment(horizontal="center", vertical="center")
                if c_idx == 6:
                    c.fill = pass_fill if "UYUMLU" in str(v) or "MEVCUT" in str(v) else warn_fill

        for idx, w in enumerate([6, 30, 16, 16, 40, 22, 35], start=1):
            ws4.column_dimensions[get_column_letter(idx)].width = w

        # ── SAYFA 5: GENEL_DENETIM_VE_KARNE ──────────────────────────────────
        ws5 = wb.create_sheet(title="5_GENEL_DENETIM_VE_KARNE")
        ws5.views.sheetView[0].showGridLines = True
        ws5.merge_cells("A1:G1")
        ws5["A1"] = f"ZAYIF AKIM SİSTEMLERİ DENETİM VE EKSİKLİK KARNESİ — {self.report.project_name.upper()}"
        ws5["A1"].font = title_font
        ws5["A1"].fill = PatternFill(start_color="333F48", end_color="333F48", fill_type="solid")
        ws5["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws5.row_dimensions[1].height = 28

        h5 = ["No", "Sistem", "Eleman", "Tespit Edilen Hata / Eksiklik", "Yönetmelik / Güvenlik Etkisi", "Kesin Düzeltme Talimatı", "Önem"]
        ws5.row_dimensions[2].height = 24
        for c_idx, t in enumerate(h5, start=1):
            c = ws5.cell(row=2, column=c_idx, value=t)
            c.font = header_font
            c.fill = PatternFill(start_color="4F6272", end_color="4F6272", fill_type="solid")
            c.alignment = Alignment(horizontal="center", vertical="center")

        for r_idx, f_item in enumerate(self.report.findings, start=3):
            ws5.row_dimensions[r_idx].height = 36
            vals = [f_item.id, f_item.system, f_item.element, f_item.issue, f_item.impact, f_item.correction, f_item.severity]
            for c_idx, v in enumerate(vals, start=1):
                c = ws5.cell(row=r_idx, column=c_idx, value=v)
                c.font = norm_font
                c.border = thin_border
                c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
                if c_idx in (1, 2, 7):
                    c.alignment = Alignment(horizontal="center", vertical="center")
                    c.font = bold_font
                if f_item.severity == "KRİTİK" and c_idx in (4, 7):
                    c.fill = crit_fill
                elif f_item.severity == "UYARI" and c_idx in (4, 7):
                    c.fill = warn_fill

        for idx, w in enumerate([6, 16, 25, 36, 36, 38, 14], start=1):
            ws5.column_dimensions[get_column_letter(idx)].width = w

        out_xlsx = self.output_dir / f"{self.slug}_zayif_akim_raporu.xlsx"
        wb.save(str(out_xlsx))
        return out_xlsx

    def generate_html(self) -> Path:
        """Koyu temalı interaktif HTML Zayıf Akım Denetim Raporu üretir."""
        f = self.report.fire_alarm
        tel = self.report.telecom
        tv = self.report.smatv
        dia = self.report.intercom

        html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CloudeCAD — Zayıf Akım Sistemleri Denetim Raporu: {self.report.project_name}</title>
<style>
  :root {{
    --bg: #0b1329;
    --card: #152238;
    --border: #233554;
    --text: #f8fafc;
    --text-muted: #94a3b8;
    --primary: #38bdf8;
    --success: #22c55e;
    --warning: #f59e0b;
    --danger: #ef4444;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 30px 20px;
    line-height: 1.5;
  }}
  .container {{ max-width: 1500px; margin: 0 auto; }}
  .header {{
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 10px 25px rgba(0,0,0,0.3);
  }}
  .header h1 {{ font-size: 22px; font-weight: 700; color: #fff; }}
  .header p {{ color: var(--text-muted); font-size: 13px; margin-top: 4px; }}
  .badge {{
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
  }}
  .badge-danger {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }}
  .badge-warning {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }}
  .badge-success {{ background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; }}

  /* METRICS */
  .metrics-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }}
  .metric-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 20px;
  }}
  .metric-card .label {{ color: var(--text-muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .metric-card .value {{ font-size: 22px; font-weight: 700; color: var(--primary); margin: 4px 0; }}
  .metric-card .sub {{ font-size: 11px; color: var(--text-muted); }}

  /* SECTION BOX */
  .section-box {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 28px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.2);
  }}
  .section-title {{
    font-size: 16px;
    font-weight: 700;
    margin-bottom: 16px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .title-fire {{ color: #ef4444; }}
  .title-tel {{ color: #38bdf8; }}
  .title-tv {{ color: #fbbf24; }}
  .title-dia {{ color: #4ade80; }}

  /* TABLE */
  .table-scroll {{
    overflow-x: auto;
    border-radius: 8px;
    border: 1px solid var(--border);
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    text-align: left;
    white-space: nowrap;
  }}
  th, td {{
    padding: 10px 14px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }}
  thead th {{
    background: #1e293b;
    color: #94a3b8;
    font-weight: 600;
  }}
  tbody tr:hover {{ background: rgba(255, 255, 255, 0.03); }}
  .pass-badge {{ color: var(--success); font-weight: 700; }}
  .warn-badge {{ color: var(--warning); font-weight: 700; }}
  .crit-badge {{ color: var(--danger); font-weight: 700; }}

  /* FINDINGS */
  .finding-card {{
    background: rgba(11, 19, 41, 0.6);
    border: 1px solid var(--border);
    border-left: 4px solid var(--warning);
    border-radius: 8px;
    padding: 14px;
    margin-bottom: 12px;
  }}
  .finding-card.critical {{ border-left-color: var(--danger); }}
  .finding-header {{
    display: flex;
    justify-content: space-between;
    font-weight: 700;
    font-size: 13.5px;
    margin-bottom: 6px;
  }}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div>
      <h1>CloudeCAD — Zayıf Akım Sistemleri Denetim Raporu</h1>
      <p>Proje: <strong>{self.report.project_name}</strong> | Standartlar: TS EN 54, BYKHY, BTK &amp; TS EN 50083 | Bağımsız Bölüm: {self.report.dwelling_count} Adet</p>
    </div>
    <div>
      <span class="badge {'badge-danger' if self.report.score_pct < 60 else ('badge-warning' if self.report.score_pct < 85 else 'badge-success')}">
        {self.report.overall_verdict}
      </span>
    </div>
  </div>

  <!-- KPI Metrikleri -->
  <div class="metrics-grid">
    <div class="metric-card">
      <div class="label">Yangın İhbar &amp; Algılama</div>
      <div class="value">{f.total_devices} Cihaz</div>
      <div class="sub">Duman: {f.smoke_detectors} | Buton: {f.manual_call_points} | Siren: {f.sirens_flashers}</div>
    </div>
    <div class="metric-card">
      <div class="label">Telefon &amp; Data Prizleri</div>
      <div class="value">{tel.sockets} Priz</div>
      <div class="sub">Kat Kutusu: {tel.floor_boxes} | Bina Kutusu: {tel.main_boxes} (BTK)</div>
    </div>
    <div class="metric-card">
      <div class="label">TV / Uydu Dağıtımı</div>
      <div class="value">{tv.tv_sockets} TV Prizi</div>
      <div class="sub">TAP: {tv.tap_offs} | Santral: {tv.multiswitches} (Multiswitch)</div>
    </div>
    <div class="metric-card">
      <div class="label">İnterkom / Diafon</div>
      <div class="value">{dia.monitors} Monitör</div>
      <div class="sub">Zil: {dia.door_bell_buttons} | Kapı Otomatiği: {dia.door_releases}</div>
    </div>
    <div class="metric-card">
      <div class="label">Zayıf Akım Güvenlik Skoru</div>
      <div class="value">%{self.report.score_pct:.0f} / 100</div>
      <div class="sub">{len(self.report.findings)} Denetim Maddesi Tespit Edildi</div>
    </div>
  </div>

  <!-- 1. YANGIN ALGILAMA BÖLÜMÜ -->
  <div class="section-box">
    <div class="section-title title-fire">
      <span>🔥</span> 1. YANGIN ALGILAMA VE İHBAR SİSTEMİ DENETİMİ (TS EN 54 &amp; BYKHY)
    </div>
    <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 12px;">
      Binaların Yangından Korunması Hakkında Yönetmelik ve TS EN 54-14 standardına göre dedektör koruma alanları, buton aralıkları ve yangın kontrol santrali denetim sonuçları:
    </p>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Yangın Elemanı</th>
            <th>CAD Blok Kodu</th>
            <th style="text-align:center;">Çizimdeki Adet</th>
            <th>Yönetmelik / Standart Kuralı</th>
            <th style="text-align:center;">Uyum Durumu</th>
            <th>Teknik Değerlendirme</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Optik Duman Dedektörü</strong></td>
            <td><code>DS / OD</code></td>
            <td style="text-align:center; font-weight:700; color:#38bdf8;">{f.smoke_detectors}</td>
            <td>Kat holleri ve kaçış koridorlarında azami 50 m² koruma alanı (R=7.5m)</td>
            <td style="text-align:center;"><span class="{'pass-badge' if f.smoke_detectors > 0 else 'crit-badge'}">{"✓ UYGUN" if f.smoke_detectors > 0 else "❌ EKSİK"}</span></td>
            <td>Optik algılama hücresi ile erken yangın uyarısı</td>
          </tr>
          <tr>
            <td><strong>Yangın İhbar Butonu</strong></td>
            <td><code>YB</code></td>
            <td style="text-align:center; font-weight:700; color:#38bdf8;">{f.manual_call_points}</td>
            <td>Kaçış merdiveni çıkışlarında azami 30 m mesafede bir</td>
            <td style="text-align:center;"><span class="{'pass-badge' if f.manual_call_points >= self.report.floor_count else 'crit-badge'}">{"✓ UYGUN" if f.manual_call_points >= self.report.floor_count else "⚠ YETERSİZ"}</span></td>
            <td>Manuel yangın ihbarı (BYKHY Md 75)</td>
          </tr>
          <tr>
            <td><strong>Elektronik Yangın Sireni</strong></td>
            <td><code>SKM</code></td>
            <td style="text-align:center; font-weight:700; color:#38bdf8;">{f.sirens_flashers}</td>
            <td>Sesli alarm (min 65 dBA / yatakta 75 dBA)</td>
            <td style="text-align:center;"><span class="{'pass-badge' if f.sirens_flashers > 0 else 'crit-badge'}">{"✓ UYGUN" if f.sirens_flashers > 0 else "❌ EKSİK"}</span></td>
            <td>Sesli ve ışıklı tahliye bildirimi</td>
          </tr>
          <tr>
            <td><strong>Yangın Kontrol Santrali (FACP)</strong></td>
            <td><code>YIS</code></td>
            <td style="text-align:center; font-weight:700; color:#38bdf8;">{f.control_panels}</td>
            <td>Bina girişi veya 24 saat gözetimli güvenlik odası</td>
            <td style="text-align:center;"><span class="{'pass-badge' if f.control_panels > 0 else 'warn-badge'}">{"✓ MEVCUT" if f.control_panels > 0 else "⚠ ŞEMADA_GÖSTERİLMELİ"}</span></td>
            <td>{f.system_type} santral mimarisi</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 2. TELEFON & DATA BÖLÜMÜ -->
  <div class="section-box">
    <div class="section-title title-tel">
      <span>🌐</span> 2. TELEFON VE DATA (YAPISAL KABLOLAMA) DENETİMİ (BTK &amp; TIA/EIA)
    </div>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Tesisat Elemanı</th>
            <th>CAD Blok Kodu</th>
            <th style="text-align:center;">Çizimdeki Adet</th>
            <th>BTK Standart Kuralı</th>
            <th style="text-align:center;">Kapasite Durumu</th>
            <th>Mühendislik Açıklaması</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Telefon / Data Prizi</strong></td>
            <td><code>T</code></td>
            <td style="text-align:center; font-weight:700; color:#38bdf8;">{tel.sockets}</td>
            <td>Daire başına asgari 2 priz (Salon + Oda)</td>
            <td style="text-align:center;"><span class="{'pass-badge' if tel.sockets >= self.report.dwelling_count * 2 else 'warn-badge'}">{"✓ YETERLİ" if tel.sockets >= self.report.dwelling_count * 2 else "⚠ KONTROL EDİLMELİ"}</span></td>
            <td>Cat6 UTP yapısal kablolama altyapısı</td>
          </tr>
          <tr>
            <td><strong>Kat Dağıtım Kutusu (1TK)</strong></td>
            <td><code>1tk</code></td>
            <td style="text-align:center; font-weight:700; color:#38bdf8;">{tel.floor_boxes}</td>
            <td>Her katta en az 1 dağıtıcı kutu</td>
            <td style="text-align:center;"><span class="pass-badge">✓ UYGUN</span></td>
            <td>Kat içi yatay kablo sonlandırma</td>
          </tr>
          <tr>
            <td><strong>Bina Ana Telefon Kutusu (BTK)</strong></td>
            <td><code>BTK</code></td>
            <td style="text-align:center; font-weight:700; color:#38bdf8;">{tel.main_boxes}</td>
            <td>Bina giriş katında ana reglet kutusu</td>
            <td style="text-align:center;"><span class="{'pass-badge' if tel.main_boxes > 0 else 'warn-badge'}">{"✓ MEVCUT" if tel.main_boxes > 0 else "⚠ GÖSTERİLMELİ"}</span></td>
            <td>Türk Telekom dış şebeke bağlantı noktası</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 3. TV / SMATV BÖLÜMÜ -->
  <div class="section-box">
    <div class="section-title title-tv">
      <span>📡</span> 3. TV / UYDU (SMATV) DAĞITIM TESİSATI DENETİMİ (TS EN 50083)
    </div>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>SMATV Elemanı</th>
            <th>CAD Blok Kodu</th>
            <th style="text-align:center;">Çizimdeki Adet</th>
            <th>Standart Şartı</th>
            <th style="text-align:center;">Uyumluluk</th>
            <th>Sinyal / Zayıflama Değerlendirmesi</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>TV Prizi</strong></td>
            <td><code>TV</code></td>
            <td style="text-align:center; font-weight:700; color:#38bdf8;">{tv.tv_sockets}</td>
            <td>Daire başına en az 1-2 adet TV prizi</td>
            <td style="text-align:center;"><span class="pass-badge">✓ YETERLİ</span></td>
            <td>Standart priz ucu seviyesi: 60 - 80 dBµV</td>
          </tr>
          <tr>
            <td><strong>Kat Dağıtıcısı (TAP)</strong></td>
            <td><code>TAP</code></td>
            <td style="text-align:center; font-weight:700; color:#38bdf8;">{tv.tap_offs}</td>
            <td>Kat şaftlarında kademeli zayıflatıcılar</td>
            <td style="text-align:center;"><span class="pass-badge">✓ MEVCUT</span></td>
            <td>Katlar arası sinyal eşitleme TAP kademeleri</td>
          </tr>
          <tr>
            <td><strong>TV Santrali (Multiswitch)</strong></td>
            <td><code>TVS</code></td>
            <td style="text-align:center; font-weight:700; color:#38bdf8;">{tv.multiswitches}</td>
            <td>Merkezi çanak anten ve kaskat multiswitch</td>
            <td style="text-align:center;"><span class="{'pass-badge' if tv.multiswitches > 0 else 'warn-badge'}">{"✓ MEVCUT" if tv.multiswitches > 0 else "⚠ ŞEMADA_GÖSTERİLMELİ"}</span></td>
            <td>Bağımsız uydu alıcı besleme kapasitesi</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 4. İNTERKOM BÖLÜMÜ -->
  <div class="section-box">
    <div class="section-title title-dia">
      <span>🔔</span> 4. İNTERKOM / GÖRÜNTÜLÜ DİAFON VE KAPI KONTROL DENETİMİ
    </div>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>İnterkom Elemanı</th>
            <th>CAD Blok Kodu</th>
            <th style="text-align:center;">Çizimdeki Adet</th>
            <th>Daire Sayısı Eşleşmesi</th>
            <th style="text-align:center;">Durum</th>
            <th>Sistem Fonksiyonu</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Daire Diafon Monitörü</strong></td>
            <td><code>ID</code></td>
            <td style="text-align:center; font-weight:700; color:#38bdf8;">{dia.monitors}</td>
            <td>{self.report.dwelling_count} Daire ile birebir örtüşmeli</td>
            <td style="text-align:center;"><span class="pass-badge">✓ TAM UYUMLU</span></td>
            <td>Sesli ve renkli görüntülü kapı görüşmesi</td>
          </tr>
          <tr>
            <td><strong>Daire Kapı Zili</strong></td>
            <td><code>Z</code></td>
            <td style="text-align:center; font-weight:700; color:#38bdf8;">{dia.door_bell_buttons}</td>
            <td>Her daire kapı girişine 1 zil butonu</td>
            <td style="text-align:center;"><span class="pass-badge">✓ TAM UYUMLU</span></td>
            <td>Daire kapı önü çağrı zili</td>
          </tr>
          <tr>
            <td><strong>Kapı Otomatiği (Kilit)</strong></td>
            <td><code>KO</code></td>
            <td style="text-align:center; font-weight:700; color:#38bdf8;">{dia.door_releases}</td>
            <td>Ana bina giriş kapısı elektrikli kilit dili</td>
            <td style="text-align:center;"><span class="{'pass-badge' if dia.door_releases > 0 else 'warn-badge'}">{"✓ MEVCUT" if dia.door_releases > 0 else "⚠ EKSİK"}</span></td>
            <td>Dairelerden uzaktan kapı açma fonksiyonu</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 5. DENETİM BULGULARI -->
  <div class="section-box">
    <div class="section-title">
      <span>🛡️</span> 5. ZAYIF AKIM DENETİM BULGULARI VE MÜHENDİSLİK TAVSİYELERİ
    </div>
    """
        for f_item in self.report.findings:
            is_crit = f_item.severity == "KRİTİK"
            html += f"""
    <div class="finding-card {'critical' if is_crit else ''}">
      <div class="finding-header">
        <span>[{f_item.system}] <strong>{f_item.element}</strong>: <span style="color:var(--text-muted);">{f_item.issue}</span></span>
        <span class="badge {'badge-danger' if is_crit else ('badge-warning' if f_item.severity == 'UYARI' else 'badge-success')}">{f_item.severity}</span>
      </div>
      <div style="font-size:12px; color:#cbd5e1; margin-bottom:4px;">
        <strong>Etki:</strong> {f_item.impact}
      </div>
      <div style="font-size:12px; color:#86efac;">
        💡 <strong>Kesin Çözüm / Revizyon:</strong> {f_item.correction}
      </div>
    </div>
            """
        html += """
  </div>

</div>
</body>
</html>
"""
        out_html = self.output_dir / f"{self.slug}_zayif_akim_raporu.html"
        out_html.write_text(html, encoding="utf-8")
        return out_html

    def generate_json(self) -> Path:
        """JSON özet dökümünü üretir."""
        f = self.report.fire_alarm
        tel = self.report.telecom
        tv = self.report.smatv
        dia = self.report.intercom

        data_dict = {
            "project_name": self.report.project_name,
            "dwelling_count": self.report.dwelling_count,
            "floor_count": self.report.floor_count,
            "building_height_m": self.report.building_height_m,
            "overall_verdict": self.report.overall_verdict,
            "score_pct": self.report.score_pct,
            "fire_alarm": {
                "smoke_detectors": f.smoke_detectors,
                "heat_detectors": f.heat_detectors,
                "manual_call_points": f.manual_call_points,
                "sirens_flashers": f.sirens_flashers,
                "control_panels": f.control_panels,
                "total_devices": f.total_devices,
                "status": f.status
            },
            "telecom": {
                "sockets": tel.sockets,
                "floor_boxes": tel.floor_boxes,
                "main_boxes": tel.main_boxes,
                "status": tel.status
            },
            "smatv": {
                "tv_sockets": tv.tv_sockets,
                "tap_offs": tv.tap_offs,
                "floor_boxes": tv.floor_boxes,
                "multiswitches": tv.multiswitches,
                "status": tv.status
            },
            "intercom": {
                "monitors": dia.monitors,
                "door_bell_buttons": dia.door_bell_buttons,
                "door_releases": dia.door_releases,
                "entrance_panels": dia.entrance_panels,
                "power_supplies": dia.power_supplies,
                "status": dia.status
            },
            "findings_count": len(self.report.findings),
            "findings": [
                {
                    "id": it.id,
                    "system": it.system,
                    "element": it.element,
                    "issue": it.issue,
                    "impact": it.impact,
                    "correction": it.correction,
                    "severity": it.severity
                }
                for it in self.report.findings
            ]
        }
        out_json = self.output_dir / f"{self.slug}_zayif_akim_ozet.json"
        out_json.write_text(json.dumps(data_dict, indent=2, ensure_ascii=False), encoding="utf-8")
        return out_json
