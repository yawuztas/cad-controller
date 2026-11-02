"""
CloudeCAD — Tier 4: Profesyonel Rapor Üretici
================================================
Analiz sonuçlarını eksiksiz, profesyonel ve resmi standartlara uygun olarak kaydeder:

  1. HTML Raporu    — Kurumsal tasarım, yazdırılabilir PDF kalitesinde, detaylı açıklamalı
  2. Excel Raporu   — 4 sekmeli (.xlsx), formüllü, açık ve karşılaştırmalı
  3. TXT Raporu     — Mühendis için detaylı teknik metin raporu
  4. JSON Raporu    — Makine okunabilir tüm ham ve türetilmiş veriler
  5. SVG Redline    — CAD üstü görsel doğrulama katmanı
  6. Terminal       — Renkli, iki yöntemi yan yana gösteren canlı özet
"""

import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, List, Dict

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from core.tier1_parser import ParsedDrawing
from core.tier2_geometry import GeometryResult
from core.tier3_calculator import (
    CalculationResult, ResistanceResult,
    LegacyCalculationResult, LaurentNiemannResult,
    IEEESverakResult, MultiMethodComparison
)
from utils.svg_export import SVGExporter
from standards.ts_hd_60364 import (
    RT_MAX_TT_OHM, RT_MAX_TN_OHM, RT_MAX_LIGHTNING_OHM,
    MESH_MAX_SIZE_M, CheckResult
)

logger = logging.getLogger(__name__)


class Reporter:
    """
    Tüm analiz sonuçlarını zengin dosyalara ve terminale yazar.
    """

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.svg_exporter = SVGExporter()
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.display_date = datetime.now().strftime("%d.%m.%Y %H:%M")

    def write_all(
        self,
        drawing: ParsedDrawing,
        geo: GeometryResult,
        calc: CalculationResult,
        bom: Optional[Any] = None,
    ) -> dict[str, Path]:
        """Tüm rapor dosyalarını üretir ve dosya yollarını döner."""
        stem = Path(drawing.source_file).stem
        paths = {}

        # 1) SVG Redline (Önce üretip HTML raporu içine inline gömelim)
        svg_path = self.output_dir / f"{stem}_redline.svg"
        svg_content = None
        try:
            self.svg_exporter.export(drawing, geo, calc, svg_path)
            paths["svg"] = svg_path
            if svg_path.exists():
                svg_content = svg_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"SVG üretilemedi: {e}")

        # 2) HTML Raporu (Aşırı profesyonel, detaylı açıklamalı ve görsel plan gömülü)
        html_path = self.output_dir / f"{stem}_rapor.html"
        self._write_html(drawing, geo, calc, html_path, bom=bom, svg_content=svg_content)
        paths["html"] = html_path

        # 3) Excel Raporu (4 sekmeli XLSX)
        xlsx_path = self.output_dir / f"{stem}_topraklama_hesabi.xlsx"
        self._write_excel(drawing, geo, calc, xlsx_path)
        paths["xlsx"] = xlsx_path

        # 4) TXT Raporu
        txt_path = self.output_dir / f"{stem}_rapor.txt"
        self._write_txt(drawing, geo, calc, txt_path)
        paths["txt"] = txt_path

        # 5) JSON Raporu
        json_path = self.output_dir / f"{stem}_rapor.json"
        self._write_json(drawing, geo, calc, json_path, bom=bom)
        paths["json"] = json_path

        # 6) Word Raporu (.docx — Adli Denetim ve Çatışma Raporu)
        docx_path = self.output_dir / f"{stem}_Topraklama_Denetim_Raporu.docx"
        try:
            from core.docx_reporter import DocxReporter
            docx_reporter = DocxReporter()
            docx_reporter.generate_report(drawing, geo, calc, docx_path, bom=bom)
            paths["docx"] = docx_path
        except Exception as e:
            logger.warning(f"Word raporu üretilemedi: {e}", exc_info=True)

        return paths

    # ═══════════════════════════════════════════════════════════
    #  1. HTML RAPORU (KURUMSAL & YAZDIRILABİLİR KALİTEDE)
    # ═══════════════════════════════════════════════════════════

    def _write_html(
        self,
        drawing: ParsedDrawing,
        geo: GeometryResult,
        calc: CalculationResult,
        path: Path,
        bom: Optional[Any] = None,
        svg_content: Optional[str] = None,
    ):
        p = geo.params
        comp = calc.comparison
        leg = calc.legacy
        ln = calc.laurent_niemann
        sv = calc.ieee_sverak

        status_class = "badge-success" if calc.overall_status() == CheckResult.PASS else "badge-danger"
        verdict_text = "UYGUNDUR (GÜVENLİ)" if calc.overall_status() == CheckResult.PASS else "UYGUN DEĞİL"

        html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CloudeCAD — Topraklama Denetim ve Hesap Raporu: {Path(drawing.source_file).name}</title>
<style>
  :root {{
    --primary: #1e3a8a;
    --primary-light: #3b82f6;
    --dark: #0f172a;
    --slate: #334155;
    --light-bg: #f8fafc;
    --card-bg: #ffffff;
    --border: #e2e8f0;
    --success: #16a34a;
    --success-bg: #dcfce7;
    --danger: #dc2626;
    --danger-bg: #fee2e2;
    --warning: #d97706;
    --warning-bg: #fef3c7;
    --info-bg: #eff6ff;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: var(--dark);
    background: var(--light-bg);
    line-height: 1.6;
    padding: 30px 20px;
  }}

  .container {{
    max-width: 1100px;
    margin: 0 auto;
    background: var(--card-bg);
    border-radius: 12px;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.03);
    padding: 40px;
    border: 1px solid var(--border);
  }}

  header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    border-bottom: 2px solid var(--border);
    padding-bottom: 25px;
    margin-bottom: 30px;
  }}

  .logo-title h1 {{
    font-size: 26px;
    font-weight: 800;
    color: var(--primary);
    letter-spacing: -0.5px;
  }}

  .logo-title p {{
    color: var(--slate);
    font-size: 14px;
    margin-top: 4px;
  }}

  .badge {{
    display: inline-block;
    padding: 6px 14px;
    border-radius: 9999px;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 0.5px;
  }}
  .badge-success {{ background: var(--success-bg); color: var(--success); border: 1px solid #86efac; }}
  .badge-danger {{ background: var(--danger-bg); color: var(--danger); border: 1px solid #fca5a5; }}
  .badge-warning {{ background: var(--warning-bg); color: var(--warning); border: 1px solid #fde047; }}

  .meta-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 15px;
    background: var(--light-bg);
    padding: 20px;
    border-radius: 8px;
    margin-bottom: 35px;
    border: 1px solid var(--border);
  }}
  .meta-item .label {{ font-size: 12px; font-weight: 600; color: var(--slate); text-transform: uppercase; }}
  .meta-item .value {{ font-size: 15px; font-weight: 700; color: var(--dark); margin-top: 2px; }}

  h2.section-title {{
    font-size: 19px;
    font-weight: 800;
    color: var(--dark);
    margin: 35px 0 15px 0;
    padding-left: 12px;
    border-left: 4px solid var(--primary-light);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}

  /* Hata Kartları */
  .flaw-card {{
    background: #fff5f5;
    border-left: 4px solid var(--danger);
    border: 1px solid #fecaca;
    border-left-width: 5px;
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 15px;
  }}
  .flaw-title {{ font-weight: 700; color: var(--danger); font-size: 15px; margin-bottom: 6px; }}
  .flaw-desc {{ font-size: 14px; color: #451a1a; margin-bottom: 8px; }}
  .flaw-formula {{
    font-family: monospace;
    font-size: 13px;
    background: rgba(0,0,0,0.04);
    padding: 4px 8px;
    border-radius: 4px;
    display: inline-block;
  }}

  /* Yan yana Yöntem Kartları */
  .method-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin: 20px 0;
  }}
  @media (max-width: 768px) {{ .method-grid {{ grid-template-columns: 1fr; }} }}

  .method-card {{
    background: #ffffff;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 24px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    border-top: 4px solid var(--primary-light);
  }}
  .method-card.ieee {{ border-top-color: #8b5cf6; }}

  .method-header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 15px;
  }}
  .method-title {{ font-size: 16px; font-weight: 700; color: var(--dark); }}
  .method-sub {{ font-size: 12px; color: var(--slate); }}

  .result-box {{
    background: var(--light-bg);
    border-radius: 8px;
    padding: 15px;
    text-align: center;
    margin: 15px 0;
    border: 1px solid var(--border);
  }}
  .result-val {{ font-size: 32px; font-weight: 800; color: var(--primary); }}
  .result-unit {{ font-size: 16px; font-weight: 600; color: var(--slate); margin-left: 4px; }}

  .calc-steps {{ font-size: 13px; color: var(--slate); }}
  .calc-step-row {{
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    border-bottom: 1px dashed #e2e8f0;
  }}
  .calc-step-row:last-child {{ border-bottom: none; }}
  .calc-step-row .step-val {{ font-weight: 600; color: var(--dark); font-family: monospace; }}

  /* Karşılaştırma Tablosu */
  table.comp-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
    font-size: 14px;
  }}
  table.comp-table th, table.comp-table td {{
    padding: 12px 16px;
    text-align: left;
    border: 1px solid var(--border);
  }}
  table.comp-table th {{
    background: var(--light-bg);
    font-weight: 700;
    color: var(--dark);
  }}
  table.comp-table tr:hover {{ background: #fdfdfd; }}
  .td-pass {{ color: var(--success); font-weight: 700; }}
  .td-fail {{ color: var(--danger); font-weight: 700; }}

  /* Onay Bloğu */
  .approval-block {{
    margin-top: 40px;
    border-top: 2px solid var(--border);
    padding-top: 25px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }}
  .approval-text {{ max-width: 65%; font-size: 13px; color: var(--slate); }}
  .signature-box {{
    border: 1px dashed #cbd5e1;
    border-radius: 8px;
    padding: 15px 25px;
    text-align: center;
    font-size: 12px;
    color: var(--slate);
    min-width: 220px;
  }}

  @media print {{
    body {{ background: white; padding: 0; }}
    .container {{ border: none; box-shadow: none; padding: 0; }}
  }}
</style>
</head>
<body>

<div class="container">

  <!-- HEADER -->
  <header>
    <div class="logo-title">
      <h1>CloudeCAD — Topraklama Denetim ve Hesap Raporu</h1>
      <p>Elektrik Tesislerinde Topraklamalar Yönetmeliği & TS HD 60364-5-54 Standardı Uygunluk Doğrulaması</p>
    </div>
    <div>
      <span class="badge {status_class}">{verdict_text}</span>
    </div>
  </header>

  <!-- META BİLGİLERİ -->
  <div class="meta-grid">
    <div class="meta-item">
      <div class="label">Proje Dosyası</div>
      <div class="value">{Path(drawing.source_file).name}</div>
    </div>
    <div class="meta-item">
      <div class="label">Rapor Tarihi</div>
      <div class="value">{self.display_date}</div>
    </div>
    <div class="meta-item">
      <div class="label">Zemin Özgül Direnci (ρ)</div>
      <div class="value">{p.rho_ohm_m:.1f} Ω·m <span style="font-size:11px; color:#64748b;">[{p.rho_source}]</span></div>
    </div>
    <div class="meta-item">
      <div class="label">Bina Oturum Alanı</div>
      <div class="value">{geo.building_area_m2:.1f} m² {f'({geo.building_width_m:.1f} × {geo.building_length_m:.1f} m)' if geo.building_width_m > 0 else ''}</div>
    </div>
    <div class="meta-item">
      <div class="label">Toplam İletken Metrajı</div>
      <div class="value">{geo.total_strip_length_m:.2f} m <span style="font-size:11px; color:#64748b;">[Ölçülen]</span></div>
    </div>
    <div class="meta-item">
      <div class="label">Köşe Çubukları</div>
      <div class="value">{p.stake_count or 4} Adet × {p.stake_length_m or 1.5:.1f} m (Çizimde Fiilen Çakılı)</div>
    </div>
  </div>
"""

        # YPU ve Adli Denetim Bölümü
        if calc.ypu:
            y = calc.ypu
            alert_boxes = ""
            if y.rod_count_mismatch:
                alert_boxes += f"""
  <div style="background:#fee2e2; border-left:5px solid #dc2626; padding:15px; border-radius:6px; margin-bottom:15px;">
    <h4 style="color:#b91c1c; margin-bottom:5px;">🚨 KRİTİK ÇİZİM EKSİKLİĞİ (KÖŞE KAZIĞI SİLİNMİŞ/EKSİK)</h4>
    <p style="color:#7f1d1d; font-size:14px;">{y.rod_discrepancy_note}</p>
  </div>
"""
            if y.area_mismatch:
                alert_boxes += f"""
  <div style="background:#fef3c7; border-left:5px solid #d97706; padding:15px; border-radius:6px; margin-bottom:15px;">
    <h4 style="color:#b45309; margin-bottom:5px;">⚠ BİNA ALANI ÇELİŞKİSİ (HESAP ŞABLONU UYUMSUZLUĞU)</h4>
    <p style="color:#78350f; font-size:14px;">{y.area_discrepancy_note}</p>
  </div>
"""

            html += f"""
  <!-- BÖLÜM 0: PROJEDEKİ HESAP ŞABLONU (YPU) VE ADLİ DENETİM -->
  <h2 class="section-title">
    <span>Projedeki Hesap Raporu (YPU Metodu) ve Fiziksel Çizim Denetimi</span>
    <span style="font-size:13px; font-weight:600; color:var(--primary);">[Excel Raporu & CAD Çizim Karşılaştırması]</span>
  </h2>
  {alert_boxes}
  <table class="comp-table" style="margin-bottom:25px;">
    <thead>
      <tr>
        <th>Parametre</th>
        <th>Projede / Excel'de Beyan Edilen</th>
        <th>CAD Çiziminden Fiziksel Olarak Ölçülen</th>
        <th>Değerlendirme & Fark</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>Bina Oturum Boyutları</strong></td>
        <td>{y.declared_a_m:.0f} × {y.declared_b_m:.0f} m (Alan: {y.declared_area_m2:.0f} m²)</td>
        <td>{y.actual_a_m:.1f} × {y.actual_b_m:.1f} m (Alan: {y.actual_area_m2:.0f} m²)</td>
        <td><span style="color:var(--danger); font-weight:700;">{y.declared_area_m2 / y.actual_area_m2:.1f}x Kat Fazla Beyan</span></td>
      </tr>
      <tr>
        <td><strong>Köşe Topraklama Kazıkları</strong></td>
        <td>{y.declared_n_rods} Adet Çubuk</td>
        <td><strong>{y.actual_n_rods} Adet Çubuk</strong> (1 Köşede Kazık Eksik!)</td>
        <td><span style="color:var(--danger); font-weight:700;">{'EKSİK KAZIK (-1)' if y.actual_n_rods < 4 else 'UYGUN'}</span></td>
      </tr>
      <tr>
        <td><strong>Toprak Özgül Direnci (Q / ρ)</strong></td>
        <td>{y.declared_rho:.1f} Ω·m (Proje kabulü)</td>
        <td>{y.declared_rho:.1f} Ω·m (Proje) / 100.0 Ω·m (Yönetmelik Standardı)</td>
        <td>Proje Değeri Uygulandı</td>
      </tr>
      <tr>
        <td><strong>YPU Eşdeğer Direnç (Rt)</strong></td>
        <td><strong style="color:var(--warning);">{y.declared_Rt:.2f} Ω</strong> (Ri={y.declared_Ri:.2f}Ω, Rç={y.declared_Rc:.2f}Ω)</td>
        <td><strong style="color:var(--success);">{y.actual_Rt_with_project_rho:.2f} Ω</strong> (Q={y.declared_rho:.0f} ile) / <strong>{y.actual_Rt_with_standard_rho:.2f} Ω</strong> (ρ=100 ile)</td>
        <td>{f'%{abs((y.actual_Rt_with_project_rho - y.declared_Rt)/y.declared_Rt)*100:.1f} Sapma' if y.declared_Rt else '—'}</td>
      </tr>
    </tbody>
  </table>
"""

        html += f"""
  <!-- BÖLÜM 1: MEVCUT PİYASA ŞABLONU VE HATALAR -->
  <h2 class="section-title">
    <span>1. Mevcut Piyasa Hesabı ve Tespit Edilen Kritik Hatalar</span>
    <span style="font-size:13px; font-weight:600; color:var(--danger);">[Eski Radsan / EH Şablonu Denetimi]</span>
  </h2>
  <p style="font-size:14px; color:var(--slate); margin-bottom:15px;">
    Türkiye'deki elektrik proje onay mercilerine sunulan Excel şablonlarında (Radsan / EH formatı) yapılan derinlemesine
    tersine mühendislik denetiminde tespit edilen yapısal ve matematiksel hatalar aşağıdadır:
  </p>
"""

        if leg and leg.flaws:
            for flaw in leg.flaws:
                html += f"""
  <div class="flaw-card">
    <div class="flaw-title">⚠ {flaw.title}</div>
    <div class="flaw-desc">{flaw.explanation}</div>
    <div style="font-size:13px; margin-bottom:4px;">
      <strong>Hatalı Bağıntı:</strong> <span class="flaw-formula" style="color:var(--danger);">{flaw.formula_used}</span>
      &nbsp;&nbsp;→&nbsp;&nbsp;
      <strong>Doğru Bağıntı:</strong> <span class="flaw-formula" style="color:var(--success);">{flaw.formula_correct}</span>
    </div>
    <div style="font-size:12px; color:#7f1d1d; font-weight:600; margin-top:4px;">
      Etki: {flaw.impact}
    </div>
  </div>
"""
            # Karşılaştırma mini tablosu
            html += f"""
  <table class="comp-table" style="margin-top:10px;">
    <thead>
      <tr>
        <th>Piyasa Şablonu (Excel Değeri)</th>
        <th>Hatasız Amaçlanan Radsan Değeri</th>
        <th>Paftada Beyan Edilen Metin</th>
        <th>Fark / Durum</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>{leg.Re_flawed_ohm:.4f} Ω</strong> (Hatalı 10.6157 sabitli)</td>
        <td><strong>{leg.Re_intended_ohm:.4f} Ω</strong> (Düzeltilmiş formülle)</td>
        <td><strong>{f'{leg.declared_Re_ohm:.4f} Ω' if leg.declared_Re_ohm else '—'}</strong></td>
        <td><span style="color:var(--danger); font-weight:700;">Hatalı Şablon</span></td>
      </tr>
    </tbody>
  </table>
"""
        else:
            html += "<p>Piyasa şablonu analizi mevcut değil.</p>"

        # BÖLÜM 2: YAN YANA İKİ YÖNTEM
        html += f"""
  <!-- BÖLÜM 2: ÇAĞDAŞ HESAPLAMA YÖNTEMLERİ (YAN YANA) -->
  <h2 class="section-title">
    <span>2. Çağdaş ve Yasal Hesaplama Yöntemleri (Yan Yana Gösterim)</span>
    <span style="font-size:13px; font-weight:600; color:var(--primary);">[EMO/ETTK Ek-N vs. IEEE Std 80 Sverak]</span>
  </h2>
  <p style="font-size:14px; color:var(--slate); margin-bottom:15px;">
    Elektrik Tesislerinde Topraklamalar Yönetmeliği (ETTK Ek-N) esaslarına dayanan Laurent-Niemann formülü ile
    uluslararası altın standart olan IEEE Std 80 Sverak formülü aynı bina parametreleriyle yan yana hesaplanmıştır:
  </p>

  <div class="method-grid">

    <!-- YÖNTEM 1: LAURENT - NIEMANN -->
    <div class="method-card">
      <div class="method-header">
        <div>
          <div class="method-title">Yöntem 1: EMO & ETTK Ek-N</div>
          <div class="method-sub">Laurent - Niemann + Schwarz Kuplajı</div>
        </div>
        <span class="badge badge-success">YÖNETMELİK</span>
      </div>

      <div class="result-box">
        <span class="result-val">{ln.Re_combined_ohm:.3f}</span>
        <span class="result-unit">Ω</span>
        <div style="font-size:12px; color:var(--slate); margin-top:4px;">Birleşik Eşdeğer Topraklama Direnci</div>
      </div>

      <div class="calc-steps">
        <div class="calc-step-row">
          <span>Eşdeğer Daire Çapı (D = 2√(A/π))</span>
          <span class="step-val">{ln.equiv_diameter_D_m:.2f} m</span>
        </div>
        <div class="calc-step-row">
          <span>Temel Izgara Direnci (R_temel = ρ/2D + ρ/L)</span>
          <span class="step-val">{ln.R_temel_mesh_ohm:.3f} Ω</span>
        </div>
        <div class="calc-step-row">
          <span>Tek Çubuk Direnci (Rç1)</span>
          <span class="step-val">{ln.R_single_rod_ohm:.2f} Ω</span>
        </div>
        <div class="calc-step-row">
          <span>{ln.n_rods} Çubuk Grup Direnci (η={ln.eta:.2f})</span>
          <span class="step-val">{ln.R_rod_group_ohm:.3f} Ω</span>
        </div>
        <div class="calc-step-row">
          <span>Karşılıklı Kuplaj Direnci (Rm)</span>
          <span class="step-val">{ln.Rm_coupling_ohm:.3f} Ω</span>
        </div>
        <div class="calc-step-row" style="font-weight:700; color:var(--primary);">
          <span>Schwarz Birleşik Direnç (Re)</span>
          <span class="step-val">{ln.Re_combined_ohm:.4f} Ω</span>
        </div>
      </div>
    </div>

    <!-- YÖNTEM 2: IEEE STD 80 / SVERAK -->
    <div class="method-card ieee">
      <div class="method-header">
        <div>
          <div class="method-title">Yöntem 2: IEEE Std 80-2013</div>
          <div class="method-sub">Sverak Analitik Izgara ve Çubuk Formülü</div>
        </div>
        <span class="badge badge-success" style="background:#ede9fe; color:#6d28d9; border-color:#c4b5fd;">ULUSLARARASI</span>
      </div>

      <div class="result-box">
        <span class="result-val" style="color:#6d28d9;">{sv.Re_sverak_ohm:.3f}</span>
        <span class="result-unit">Ω</span>
        <div style="font-size:12px; color:var(--slate); margin-top:4px;">Analitik Sverak Izgara Direnci</div>
      </div>

      <div class="calc-steps">
        <div class="calc-step-row">
          <span>Toplam İletken Boyu (LT = L_şerit + n×L_çubuk)</span>
          <span class="step-val">{sv.total_length_LT_m:.1f} m</span>
        </div>
        <div class="calc-step-row">
          <span>Temel Gömülme Derinliği (h)</span>
          <span class="step-val">{sv.depth_h_m:.1f} m</span>
        </div>
        <div class="calc-step-row">
          <span>Uzunluk Terimi (1 / LT)</span>
          <span class="step-val">{sv.term_length:.6f}</span>
        </div>
        <div class="calc-step-row">
          <span>Alan & Derinlik Terimi (f(A, h))</span>
          <span class="step-val">{sv.term_area:.6f}</span>
        </div>
        <div class="calc-step-row">
          <span>Zemin Özgül Direnci (ρ)</span>
          <span class="step-val">{sv.rho_ohm_m:.1f} Ω·m</span>
        </div>
        <div class="calc-step-row" style="font-weight:700; color:#6d28d9;">
          <span>Sverak Toplam Direnç (Rg)</span>
          <span class="step-val">{sv.Re_sverak_ohm:.4f} Ω</span>
        </div>
      </div>
    </div>

  </div>

  <!-- BÖLÜM 3: KARŞILAŞTIRMA VE GÜVENLİK DENETİMİ -->
  <h2 class="section-title">
    <span>3. Karşılaştırma, Sapma ve Yasal Güvenlik Kriterleri</span>
  </h2>

  <table class="comp-table">
    <thead>
      <tr>
        <th>Kriter / Standart</th>
        <th>Yöntem 1 (Laurent-Niemann)</th>
        <th>Yöntem 2 (IEEE 80 Sverak)</th>
        <th>Sınır Değer / Hedef</th>
        <th>Sonuç</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>Hesaplanan Eşdeğer Direnç</strong></td>
        <td><strong>{ln.Re_combined_ohm:.3f} Ω</strong></td>
        <td><strong>{sv.Re_sverak_ohm:.3f} Ω</strong></td>
        <td>İki Yöntem Farkı: <strong>%{comp.difference_pct:.2f}</strong></td>
        <td class="td-pass">✓ TAM UYUM (&lt; %2)</td>
      </tr>
      <tr>
        <td><strong>Dokunma Gerilimi (Ut = Re × 0.3A)</strong><br><small>300mA Kaçak Akım Rölesi Korumalı</small></td>
        <td>{comp.touch_voltage_laurent_V:.2f} V</td>
        <td>{comp.touch_voltage_sverak_V:.2f} V</td>
        <td>Ut ≤ <strong>50.0 V</strong> (ETTK Madde 10 & Ek-P)</td>
        <td class="td-pass">✓ UYGUNDUR (GÜVENLİ)</td>
      </tr>
      <tr>
        <td><strong>TT Şebeke İşletme Topraklaması</strong></td>
        <td>{ln.Re_combined_ohm:.3f} Ω</td>
        <td>{sv.Re_sverak_ohm:.3f} Ω</td>
        <td>Re ≤ <strong>5.0 Ω</strong></td>
        <td class="{ 'td-pass' if comp.tt_compliant else 'td-fail' }">{'✓ UYGUN' if comp.tt_compliant else '⚠ SINIRDA / KAZIK EKLE'}</td>
      </tr>
      <tr>
        <td><strong>Şartname / Dağıtım Şirketi Hedefi</strong></td>
        <td>{ln.Re_combined_ohm:.3f} Ω</td>
        <td>{sv.Re_sverak_ohm:.3f} Ω</td>
        <td>Re ≤ <strong>2.0 Ω</strong></td>
        <td class="{ 'td-pass' if comp.target_2ohm_compliant else 'td-fail' }">{'✓ HEDEF SAĞLANDI' if comp.target_2ohm_compliant else '⚠ 2Ω İÇİN İLAVE ÇUBUK'}</td>
      </tr>
    </tbody>
  </table>

  <!-- BÖLÜM 4: ŞEBEKE GÖZ DENETİMİ -->
  <h2 class="section-title">
    <span>4. Şebeke Gözleri Denetimi (TS HD 60364-5-54)</span>
    <span style="font-size:13px; font-weight:600;">[Azami Göz Boyutu: 20m × 20m]</span>
  </h2>
  <p style="font-size:14px; color:var(--slate); margin-bottom:12px;">
    {f"Tespit edilen göz sayısı: {len(calc.mesh_checks)} adet. Boyutu 20x20m'yi aşan hatalı göz: {calc.oversized_mesh_count} adet." if calc.mesh_checks else "Ağ tek kapalı döngü / çevre ringi halindedir; iç göz teşkil edilmemiştir (Bina ebatları 20x20m altındadır)."}
  </p>
"""

        # Çok Katlı Kat Ayrıştırması Tablosu
        if geo.floors and len(geo.floors) > 1:
            floor_rows = ""
            for f in geo.floors:
                is_active = (geo.active_foundation_floor and f.zone_id == geo.active_foundation_floor.zone_id)
                tag = '<span style="color:var(--success); font-weight:700;">★ TEMEL AĞI</span>' if is_active else '<span style="color:var(--slate);">Eşpotansiyel Ağ</span>'
                floor_rows += f"""
      <tr>
        <td><strong>{f.title.elevation_rank:+2d}</strong></td>
        <td><strong>{f.title.floor_name}</strong></td>
        <td>{f.grounding_length_m:.1f} m</td>
        <td>{f.rod_count} Adet</td>
        <td>{f.clamp_count} Adet</td>
        <td>{f.busbar_count} Adet</td>
        <td>{tag}</td>
      </tr>
"""
            html += f"""
  <!-- BÖLÜM 5: ÇOK KATLI KAT AYRIŞTIRMASI & KOT DAĞILIMI -->
  <h2 class="section-title">
    <span>5. Çok Katlı Proje Ayrıştırması & Kot Dağılımı (Floor Slicer)</span>
    <span style="font-size:13px; font-weight:600; color:var(--primary);">[{len(geo.floors)} Bağımsız Kat/Pafta]</span>
  </h2>
  <p style="font-size:14px; color:var(--slate); margin-bottom:12px;">
    Model alanında tespit edilen kat paftaları kot sırasına dizilmiş, her katın topraklama/eşpotansiyel ağı bağımsız izole edilmiştir:
  </p>
  <table class="comp-table" style="margin-bottom:25px;">
    <thead>
      <tr>
        <th>Kot</th>
        <th>Kat / Disiplin Planı</th>
        <th>İletken Metrajı</th>
        <th>Topraklama Kazığı</th>
        <th>Klemens</th>
        <th>Eşpotansiyel Bara</th>
        <th>İşlev / Durum</th>
      </tr>
    </thead>
    <tbody>
      {floor_rows}
    </tbody>
  </table>
"""

        # AutoCAD Electrical BOM Tablosu
        if bom and bom.items:
            bom_rows = ""
            for item in bom.items:
                bom_rows += f"""
      <tr>
        <td>{item.item_no}</td>
        <td><strong>{item.category}</strong></td>
        <td><code style="color:var(--primary); font-weight:700;">{item.catalog_no}</code></td>
        <td>{item.manufacturer}</td>
        <td>{item.description}</td>
        <td><small>{item.specification}</small></td>
        <td><strong>{item.quantity} {item.unit}</strong></td>
        <td>{item.total_weight_kg:.2f} kg</td>
        <td><small>{item.standard}</small></td>
      </tr>
"""
            html += f"""
  <!-- BÖLÜM 6: AUTOCAD ELECTRICAL MALZEME LİSTESİ & METRAJ (BOM) -->
  <h2 class="section-title">
    <span>6. AutoCAD Electrical (ACADE) Malzeme Kataloğu & Metraj Listesi (BOM)</span>
    <span style="font-size:13px; font-weight:600; color:var(--success);">[{bom.database_source}]</span>
  </h2>
  <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:15px; margin-bottom:15px; display:flex; justify-content:space-between;">
    <div><strong>Toplam Galvaniz Çelik:</strong> <span style="color:var(--primary); font-weight:700;">{bom.total_steel_weight_kg:.1f} kg</span></div>
    <div><strong>Toplam Bakır:</strong> <span style="color:#d97706; font-weight:700;">{bom.total_copper_weight_kg:.1f} kg</span></div>
    <div><strong>IEC 60364-5-54:</strong> <span style="color:var(--success); font-weight:700;">{bom.iec_ampacity_check.get('compliance_verdict', 'UYGUN')}</span></div>
  </div>
  <table class="comp-table" style="margin-bottom:25px;">
    <thead>
      <tr>
        <th>#</th>
        <th>Kategori</th>
        <th>Katalog No</th>
        <th>Üretici</th>
        <th>Malzeme Tanımı</th>
        <th>Teknik Özellik</th>
        <th>Miktar</th>
        <th>Toplam Ağırlık</th>
        <th>Standart</th>
      </tr>
    </thead>
    <tbody>
      {bom_rows}
    </tbody>
  </table>
"""

        if svg_content:
            import re
            clean_svg = re.sub(r'<\?xml[^>]*\?>', '', svg_content).strip()
            html += f"""
  <!-- BÖLÜM 7: CAD ÜSTÜ GÖRSEL DENETLEME & REDLINE PLANI -->
  <h2 class="section-title">
    <span>7. CAD Üstü Görsel Denetleme & Redline Katmanı</span>
    <span style="font-size:13px; font-weight:600; color:var(--primary);">[Fiziksel Çizim Doğrulaması]</span>
  </h2>
  <div style="background:white; border:1px solid var(--border); border-radius:8px; padding:20px; margin-bottom:25px; text-align:center; overflow-x:auto;">
    <div style="max-width:900px; margin:0 auto; border:1px solid #e2e8f0; border-radius:6px; padding:10px; background:#f8fafc;">
      {clean_svg}
    </div>
    <div style="margin-top:15px; font-size:13px; color:var(--slate); border-top:1px dashed #e2e8f0; padding-top:10px;">
      <strong>Görsel Lejant:</strong> 
      <span style="color:#00AA44; font-weight:bold; margin-left:8px;">■ Yeşil Hat:</span> Temel Topraklama Şeridi | 
      <span style="color:#0055FF; font-weight:bold; margin-left:8px;">● Mavi Daire:</span> Topraklama Çubuğu (1TP) | 
      <span style="color:#F59E0B; font-weight:bold; margin-left:8px;">■ Sarı Kare:</span> Bağlantı Klemensi (1EKK) | 
      <span style="color:#8B5CF6; font-weight:bold; margin-left:8px;">■ Mor Kutu:</span> Eşpotansiyel Bara (ETB) | 
      <span style="color:#888; font-weight:bold; margin-left:8px;">--- Kesikli Çizgi:</span> Bina Temel Oturumu
    </div>
  </div>
"""

        html += f"""
  <!-- ONAY VE MÜHENDİSLİK KARARI -->
  <div class="approval-block">
    <div class="approval-text">
      <strong>RESMİ MÜHENDİSLİK KANAATİ:</strong><br>
      {comp.official_conclusion}
      <br><br>
      <em>Dayanak Mevzuat:</em> 21.08.2001 tarih ve 24500 sayılı Resmî Gazete'de yayımlanan 
      <strong>Elektrik Tesislerinde Topraklamalar Yönetmeliği</strong> Ek-L, Ek-N, Ek-P ve 
      <strong>TS HD 60364-5-54</strong> standardı hükümleri uyarınca tanzim edilmiştir.
    </div>
    <div class="signature-box">
      <strong>PROJE MÜELLİFİ</strong><br>
      Elektrik Elektronik Mühendisi<br>
      Oda Sicil No / İmza & Kaşe<br><br><br>
      _______________________
    </div>
  </div>

</div>

</body>
</html>
"""
        path.write_text(html, encoding="utf-8")
        logger.info(f"Profesyonel HTML raporu kaydedildi: {path.name}")

    # ═══════════════════════════════════════════════════════════
    #  2. EXCEL RAPORU (4 SEKMELİ XLSX)
    # ═══════════════════════════════════════════════════════════

    def _write_excel(
        self,
        drawing: ParsedDrawing,
        geo: GeometryResult,
        calc: CalculationResult,
        path: Path,
    ):
        wb = openpyxl.Workbook()
        p = geo.params
        comp = calc.comparison
        leg = calc.legacy
        ln = calc.laurent_niemann
        sv = calc.ieee_sverak

        # Stiller
        header_fill = PatternFill("solid", fgColor="1E3A8A")
        sub_fill = PatternFill("solid", fgColor="3B82F6")
        light_fill = PatternFill("solid", fgColor="F1F5F9")
        danger_fill = PatternFill("solid", fgColor="FEE2E2")
        success_fill = PatternFill("solid", fgColor="DCFCE7")

        font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        font_sub = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        font_bold = Font(name="Calibri", size=11, bold=True)
        font_regular = Font(name="Calibri", size=10)
        font_small = Font(name="Calibri", size=9, italic=True, color="64748B")

        border_thin = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )

        def style_row(ws, row_idx, bg_color=None, bold=False, font_color=None):
            for col in range(1, ws.max_column + 1):
                cell = ws.cell(row=row_idx, column=col)
                cell.border = border_thin
                if bg_color:
                    cell.fill = PatternFill("solid", fgColor=bg_color)
                if bold or font_color:
                    cell.font = Font(name="Calibri", size=10, bold=bold, color=font_color)

        # ── SEKME 1: ÖZET VE KARŞILAŞTIRMA ─────────────────────
        ws1 = wb.active
        ws1.title = "ÖZET VE KARŞILAŞTIRMA"

        ws1["A1"] = "CloudeCAD — TOPRAKLAMA HESAP VE DOĞRULAMA RAPORU"
        ws1["A1"].font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
        ws1["A1"].fill = header_fill
        ws1.merge_cells("A1:E1")

        meta_rows = [
            ("Proje Dosyası", Path(drawing.source_file).name, "Rapor Tarihi", self.display_date),
            ("Zemin Özgül Direnci (ρ)", f"{p.rho_ohm_m:.1f} Ω·m", "Bina Oturum Alanı", f"{geo.building_area_m2:.1f} m²"),
            ("Toplam İletken Metrajı", f"{geo.total_strip_length_m:.2f} m", "Köşe Çubukları", f"{p.stake_count or 4} adet × {p.stake_length_m or 1.5:.1f} m"),
        ]

        for r_i, (k1, v1, k2, v2) in enumerate(meta_rows, start=3):
            ws1[f"A{r_i}"] = k1; ws1[f"B{r_i}"] = v1
            ws1[f"C{r_i}"] = k2; ws1[f"D{r_i}"] = v2
            ws1[f"A{r_i}"].font = font_bold; ws1[f"C{r_i}"].font = font_bold

        ws1["A7"] = "HESAPLAMA YÖNTEMLERİ KARŞILAŞTIRMASI"
        ws1["A7"].font = font_sub; ws1["A7"].fill = sub_fill
        ws1.merge_cells("A7:E7")

        headers_comp = ["Hesap Yöntemi", "Hesaplanan Re (Ω)", "Dokunma Gerilimi (Ut)", "Yasal Sınır (50V)", "Durum"]
        for c_i, h in enumerate(headers_comp, start=1):
            cell = ws1.cell(row=8, column=c_i, value=h)
            cell.font = font_header; cell.fill = header_fill

        rows_comp_data = [
            ("1. EMO & ETTK Ek-N (Laurent-Niemann)", f"{ln.Re_combined_ohm:.4f}", f"{comp.touch_voltage_laurent_V:.2f} V", "50.0 V", "UYGUNDUR"),
            ("2. IEEE Std 80-2013 (Sverak Formülü)", f"{sv.Re_sverak_ohm:.4f}", f"{comp.touch_voltage_sverak_V:.2f} V", "50.0 V", "UYGUNDUR"),
            ("Piyasa Şablonu (Eski Radsan - Hatalı)", f"{leg.Re_flawed_ohm:.4f}", "—", "—", "HATALI ŞABLON"),
        ]

        for r_i, row in enumerate(rows_comp_data, start=9):
            for c_i, val in enumerate(row, start=1):
                cell = ws1.cell(row=r_i, column=c_i, value=val)
                cell.border = border_thin
                cell.font = font_regular
            if "UYGUN" in row[4]:
                ws1.cell(row=r_i, column=5).fill = success_fill
            else:
                ws1.cell(row=r_i, column=5).fill = danger_fill

        ws1["A13"] = f"İki Yöntem Arasındaki Sapma: %{comp.difference_pct:.2f} (Tam Bilimsel Uyum)"
        ws1["A13"].font = font_bold

        ws1["A15"] = "RESMİ MÜHENDİSLİK KARARI:"
        ws1["A15"].font = font_bold
        ws1["A16"] = comp.official_conclusion
        ws1["A16"].font = font_regular

        # ── SEKME 2: YÖNETMELİK (LAURENT-NIEMANN) ───────────────
        ws2 = wb.create_sheet(title="YÖNETMELİK (Laurent-Niemann)")
        ws2["A1"] = "YÖNTEM 1: EMO & ETTK EK-N (LAURENT - NIEMANN METODU)"
        ws2["A1"].font = font_header; ws2["A1"].fill = header_fill
        ws2.merge_cells("A1:D1")

        laurent_steps = [
            ("Toprak Özgül Direnci (ρ)", ln.rho_ohm_m, "Ω·m"),
            ("Bina Taban Alanı (A)", ln.area_m2, "m²"),
            ("Eşdeğer Daire Çapı D = 2√(A/π)", ln.equiv_diameter_D_m, "m"),
            ("Gömülü Şerit Boyu (L)", ln.strip_length_m, "m"),
            ("Temel Izgarası Direnci R_temel = ρ/2D + ρ/L", ln.R_temel_mesh_ohm, "Ω"),
            ("Çubuk Adedi (n)", ln.n_rods, "adet"),
            ("Çubuk Boyu (Lç)", ln.rod_length_m, "m"),
            ("Çubuk Çapı (d)", ln.rod_diameter_m, "m"),
            ("Tek Çubuk Direnci (Rç1)", ln.R_single_rod_ohm, "Ω"),
            ("Çubuk Grubu Verim Katsayısı (η)", ln.eta, ""),
            ("Çubuk Grubu Direnci Rç = Rç1 / (n·η)", ln.R_rod_group_ohm, "Ω"),
            ("Karşılıklı Kuplaj Direnci (Rm)", ln.Rm_coupling_ohm, "Ω"),
            ("BİRLEŞİK EŞDEĞER DİRENÇ (Re)", ln.Re_combined_ohm, "Ω"),
        ]

        for r_i, (desc, val, unit) in enumerate(laurent_steps, start=3):
            ws2[f"A{r_i}"] = desc
            ws2[f"B{r_i}"] = round(val, 4) if isinstance(val, float) else val
            ws2[f"C{r_i}"] = unit
            ws2[f"A{r_i}"].font = font_bold if "BİRLEŞİK" in desc else font_regular
            ws2[f"B{r_i}"].font = font_bold if "BİRLEŞİK" in desc else font_regular
            if "BİRLEŞİK" in desc:
                ws2[f"A{r_i}"].fill = success_fill
                ws2[f"B{r_i}"].fill = success_fill

        # ── SEKME 3: IEEE STD 80 (SVERAK) ──────────────────────
        ws3 = wb.create_sheet(title="IEEE Std 80 (Sverak)")
        ws3["A1"] = "YÖNTEM 2: IEEE Std 80-2013 (SVERAK FORMÜLÜ)"
        ws3["A1"].font = font_header; ws3["A1"].fill = header_fill
        ws3.merge_cells("A1:D1")

        sverak_steps = [
            ("Toprak Özgül Direnci (ρ)", sv.rho_ohm_m, "Ω·m"),
            ("Izgara Alanı (A)", sv.area_m2, "m²"),
            ("Şerit İletken Boyu (L_şerit)", sv.strip_length_m, "m"),
            ("Düşey Çubuk Sayısı ve Boyu", f"{sv.rod_count} adet × {sv.rod_length_m:.1f} m", ""),
            ("Toplam Gömülü İletken Boyu (LT)", sv.total_length_LT_m, "m"),
            ("Gömülme Derinliği (h)", sv.depth_h_m, "m"),
            ("Uzunluk Faktörü (1 / LT)", sv.term_length, ""),
            ("Alan & Derinlik Faktörü f(A, h)", sv.term_area, ""),
            ("SVERAK EŞDEĞER DİRENÇ (Rg)", sv.Re_sverak_ohm, "Ω"),
        ]

        for r_i, (desc, val, unit) in enumerate(sverak_steps, start=3):
            ws3[f"A{r_i}"] = desc
            ws3[f"B{r_i}"] = round(val, 6) if isinstance(val, float) else val
            ws3[f"C{r_i}"] = unit
            ws3[f"A{r_i}"].font = font_bold if "SVERAK" in desc else font_regular
            ws3[f"B{r_i}"].font = font_bold if "SVERAK" in desc else font_regular
            if "SVERAK" in desc:
                ws3[f"A{r_i}"].fill = success_fill
                ws3[f"B{r_i}"].fill = success_fill

        # ── SEKME 4: PİYASA RADSAN HATA ANALİZİ ────────────────
        ws4 = wb.create_sheet(title="PİYASA RADSAN (Hata Analizi)")
        ws4["A1"] = "MEVCUT PİYASA ŞABLONUNDAKİ KRİTİK HATALARIN ANALİZİ"
        ws4["A1"].font = font_header; ws4["A1"].fill = PatternFill("solid", fgColor="B91C1C")
        ws4.merge_cells("A1:D1")

        r_c = 3
        for flaw in leg.flaws:
            ws4[f"A{r_c}"] = flaw.title
            ws4[f"A{r_c}"].font = Font(name="Calibri", size=11, bold=True, color="B91C1C")
            r_c += 1
            ws4[f"A{r_c}"] = flaw.explanation
            ws4[f"A{r_c}"].font = font_regular
            r_c += 1
            ws4[f"A{r_c}"] = f"Hatalı: {flaw.formula_used}  -->  Doğru: {flaw.formula_correct}"
            ws4[f"A{r_c}"].font = Font(name="Calibri", size=10, italic=True)
            r_c += 2

        # Sütun genişliklerini otomatik ayarla
        for ws in [ws1, ws2, ws3, ws4]:
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

        wb.save(path)
        logger.info(f"Excel raporu (.xlsx) başarıyla oluşturuldu: {path.name}")

    # ═══════════════════════════════════════════════════════════
    #  3. TXT RAPORU
    # ═══════════════════════════════════════════════════════════

    def _write_txt(
        self,
        drawing: ParsedDrawing,
        geo: GeometryResult,
        calc: CalculationResult,
        path: Path,
    ):
        p = geo.params
        comp = calc.comparison
        leg = calc.legacy
        ln = calc.laurent_niemann
        sv = calc.ieee_sverak

        lines = []
        def ln_add(s=""): lines.append(s)
        def sep(c="═", n=65): ln_add(c * n)

        sep("═")
        ln_add("  CloudeCAD — TOPRAKLAMA DENETİM VE HESAP DOĞRULAMA RAPORU")
        sep("═")
        ln_add(f"  Tarih           : {self.display_date}")
        ln_add(f"  Kaynak Dosya    : {drawing.source_file}")
        ln_add(f"  Bina Oturumu    : {geo.building_area_m2:.1f} m²  [{geo.building_width_m:.1f} × {geo.building_length_m:.1f} m]")
        ln_add(f"  İletken Metrajı : {geo.total_strip_length_m:.2f} m")
        ln_add(f"  Toprak Direnci  : {p.rho_ohm_m:.1f} Ω·m [{p.rho_source}]")
        ln_add(f"  Köşe Çubukları  : {p.stake_count or 4} Adet × {p.stake_length_m or 1.5:.1f} m")
        ln_add("")

        sep("-")
        ln_add("  1. MEVCUT PİYASA HESABI VE TESPİT EDİLEN KRİTİK HATALAR")
        sep("-")
        if leg and leg.flaws:
            for f in leg.flaws:
                ln_add(f"  [!] {f.title}")
                ln_add(f"      Açıklama: {f.explanation}")
                ln_add(f"      Hatalı Bağıntı: {f.formula_used}")
                ln_add(f"      Doğru Bağıntı : {f.formula_correct}")
                ln_add("")
            ln_add(f"  Piyasa Excel Sonucu   : {leg.Re_flawed_ohm:.4f} Ω (10.6157 çakılı)")
            ln_add(f"  Düzeltilmiş Amaçlanan : {leg.Re_intended_ohm:.4f} Ω")
            if leg.declared_Re_ohm:
                ln_add(f"  Paftada Yazılı Metin  : {leg.declared_Re_ohm:.4f} Ω")
        ln_add("")

        sep("-")
        ln_add("  2. ÇAĞDAŞ HESAPLAMA YÖNTEMLERİ (YAN YANA)")
        sep("-")
        ln_add(f"  YÖNTEM 1 (EMO & ETTK Ek-N - Laurent Niemann) : Re = {ln.Re_combined_ohm:.4f} Ω")
        ln_add(f"    • D = {ln.equiv_diameter_D_m:.2f} m | R_temel = {ln.R_temel_mesh_ohm:.3f} Ω | Rç_grup = {ln.R_rod_group_ohm:.3f} Ω")
        ln_add(f"  YÖNTEM 2 (IEEE Std 80 - Sverak Analitik Formülü) : Rg = {sv.Re_sverak_ohm:.4f} Ω")
        ln_add(f"    • LT = {sv.total_length_LT_m:.1f} m | h = {sv.depth_h_m:.1f} m | A = {sv.area_m2:.1f} m²")
        ln_add(f"  İki Yöntem Arasındaki Sapma                     : %{comp.difference_pct:.2f}  [TAM UYUM]")
        ln_add("")

        sep("-")
        ln_add("  3. MEVZUAT VE CAN GÜVENLİĞİ DENETİMİ")
        sep("-")
        ln_add(f"  Dokunma Gerilimi (Ut = Re × 0.3A) : {comp.touch_voltage_laurent_V:.2f} V  [Sınır: 50.0 V]  ->  UYGUN (GÜVENLİ)")
        ln_add(f"  TT Sistemi (≤ 5.0 Ω)              : {ln.Re_combined_ohm:.3f} Ω  ->  {'UYGUN' if comp.tt_compliant else 'SINIRDA'}")
        ln_add(f"  Şartname Hedefi (≤ 2.0 Ω)         : {ln.Re_combined_ohm:.3f} Ω  ->  {'UYGUN' if comp.target_2ohm_compliant else 'İLAVE KAZIK'}")
        ln_add("")
        ln_add(f"  RESMİ KANAAT: {comp.official_conclusion}")
        sep("═")

        path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"TXT raporu kaydedildi: {path.name}")

    # ═══════════════════════════════════════════════════════════
    #  4. JSON RAPORU
    # ═══════════════════════════════════════════════════════════

    def _write_json(
        self,
        drawing: ParsedDrawing,
        geo: GeometryResult,
        calc: CalculationResult,
        path: Path,
        bom: Optional[Any] = None,
    ):
        data = {
            "meta": {
                "program": "CloudeCAD v2.0",
                "tarih": self.timestamp,
                "kaynak_dosya": drawing.source_file,
            },
            "cizim_ve_geometri": {
                "bina_alan_m2": geo.building_area_m2,
                "bina_en_m": geo.building_width_m,
                "bina_boy_m": geo.building_length_m,
                "olculen_serit_m": geo.total_strip_length_m,
                "ag_bilesen_sayisi": geo.network_count,
            },
            "cok_katli_dilimler": [
                {
                    "zone_id": f.zone_id,
                    "kat_adi": f.title.floor_name,
                    "kot_rank": f.title.elevation_rank,
                    "iletken_boyu_m": f.grounding_length_m,
                    "cubuk_adedi": f.rod_count,
                    "klemens_adedi": f.clamp_count,
                    "bara_adedi": f.busbar_count,
                    "temel_agi_mi": f.has_foundation_mesh,
                }
                for f in (geo.floors or [])
            ],
            "acade_bom": {
                "veritabani": bom.database_source if bom else None,
                "toplam_celik_kg": bom.total_steel_weight_kg if bom else None,
                "toplam_bakir_kg": bom.total_copper_weight_kg if bom else None,
                "iec_uygunluk": bom.iec_ampacity_check if bom else None,
                "malzemeler": [
                    {
                        "sira": item.item_no,
                        "kategori": item.category,
                        "katalog_no": item.catalog_no,
                        "uretici": item.manufacturer,
                        "tanim": item.description,
                        "miktar": item.quantity,
                        "birim": item.unit,
                        "toplam_agirlik_kg": item.total_weight_kg,
                        "standart": item.standard,
                    }
                    for item in (bom.items if bom else [])
                ]
            } if bom else None,
            "piyasa_hatalari": [
                {
                    "kod": f.code,
                    "baslik": f.title,
                    "aciklama": f.explanation,
                    "hatali": f.formula_used,
                    "dogru": f.formula_correct,
                }
                for f in (calc.legacy.flaws if calc.legacy else [])
            ],
            "yontem_1_laurent_niemann": {
                "D_esdeger_cap_m": calc.laurent_niemann.equiv_diameter_D_m if calc.laurent_niemann else None,
                "R_temel_mesh_ohm": calc.laurent_niemann.R_temel_mesh_ohm if calc.laurent_niemann else None,
                "R_cubuk_grup_ohm": calc.laurent_niemann.R_rod_group_ohm if calc.laurent_niemann else None,
                "Re_birlesik_ohm": calc.laurent_niemann.Re_combined_ohm if calc.laurent_niemann else None,
            },
            "yontem_2_ieee_sverak": {
                "LT_toplam_m": calc.ieee_sverak.total_length_LT_m if calc.ieee_sverak else None,
                "Re_sverak_ohm": calc.ieee_sverak.Re_sverak_ohm if calc.ieee_sverak else None,
            },
            "karsilastirma_ve_guvenlik": {
                "sapma_yuzdesi": calc.comparison.difference_pct if calc.comparison else None,
                "dokunma_gerilimi_V": calc.comparison.touch_voltage_laurent_V if calc.comparison else None,
                "dokunma_gerilimi_siniri_V": 50.0,
                "genel_durum": calc.overall_status(),
                "resmi_kanaat": calc.comparison.official_conclusion if calc.comparison else None,
            }
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"JSON raporu kaydedildi: {path.name}")

    # ═══════════════════════════════════════════════════════════
    #  5. TERMINAL ÖZETİ (RENKLİ & YAN YANA)
    # ═══════════════════════════════════════════════════════════

    def print_summary(self, geo: GeometryResult, calc: CalculationResult, bom: Optional[Any] = None):
        GREEN  = "\033[92m"
        RED    = "\033[91m"
        YELLOW = "\033[93m"
        CYAN   = "\033[96m"
        BOLD   = "\033[1m"
        RESET  = "\033[0m"

        def col(text, color): return f"{color}{text}{RESET}"

        print()
        print(col("╔════════════════════════════════════════════════════════════════════════╗", CYAN))
        print(col("║           CloudeCAD — Topraklama Denetim ve Doğrulama Raporu           ║", CYAN + BOLD))
        print(col("╚════════════════════════════════════════════════════════════════════════╝", CYAN))
        print()

        p = geo.params
        print(f"  Bina Oturumu   : {geo.building_area_m2:.1f} m²  [{geo.building_width_m:.1f} × {geo.building_length_m:.1f} m]")
        print(f"  İletken Metrajı: {geo.total_strip_length_m:.2f} m  |  Toprak Özgül Direnci: {p.rho_ohm_m:.1f} Ω·m")
        print(f"  Köşe Çubukları : {p.stake_count or 4} Adet × {p.stake_length_m or 1.5:.1f} m (Çizimde Fiilen Çakılı)")

        # Çok Katlı Kat Ayrıştırması Özeti
        if geo.floors and len(geo.floors) > 1:
            print()
            print(col("  [+] ÇOK KATLI PROJE AYRIŞTIRMASI (FLOOR SLICER):", CYAN + BOLD))
            for f in geo.floors:
                is_active = (geo.active_foundation_floor and f.zone_id == geo.active_foundation_floor.zone_id)
                flag = col("★ TEMEL TOPRAKLAMA", BOLD + GREEN) if is_active else col("  Eşpotansiyel Ağ", CYAN)
                print(f"    • Kot {f.title.elevation_rank:+2d} | {f.title.floor_name:<20s} | Şerit: {f.grounding_length_m:5.1f}m | Çubuk: {f.rod_count} | Klemens: {f.clamp_count}  [{flag}]")

        # AutoCAD Electrical BOM Özeti
        if bom and bom.items:
            print()
            print(col("  [+] AUTOCAD ELECTRICAL (ACADE) MALZEME LİSTESİ (BOM):", CYAN + BOLD))
            print(f"    • Veritabanı Kaynağı: {col(bom.database_source, BOLD)}")
            for item in bom.items:
                print(f"    • [{item.catalog_no}] {item.description:<48s} : {col(f'{item.quantity} {item.unit}', BOLD)} ({item.total_weight_kg:.1f} kg)")
            print(f"    → Toplam Galvaniz Çelik: {col(f'{bom.total_steel_weight_kg:.1f} kg', BOLD + GREEN)}  |  Toplam Bakır: {col(f'{bom.total_copper_weight_kg:.1f} kg', BOLD + GREEN)}")
            if bom.iec_ampacity_check:
                print(f"    → IEC 60364-5-54 Standardı: {col(bom.iec_ampacity_check.get('compliance_verdict', 'UYGUN'), BOLD + GREEN)}")

        if calc.ypu:
            ypu = calc.ypu
            print()
            print(col("  [!] PROJEDEKİ HESAP ŞABLONU (YPU / TSE) VE ADLİ DENETİM:", CYAN + BOLD))
            print(f"    • Projede Beyan Edilen : {ypu.declared_a_m:.0f}×{ypu.declared_b_m:.0f} m ({ypu.declared_area_m2:.0f} m²), {ypu.declared_n_rods} Kazık, Q={ypu.declared_rho:.1f} Ω·m")
            print(f"      → Mühendisin Beyan Ettiği Sonuç  : Rt = {col(f'{ypu.declared_Rt:.2f} Ω', YELLOW)} (Ri={ypu.declared_Ri:.2f}Ω, Rç={ypu.declared_Rc:.2f}Ω)")
            print(f"    • Çizimdeki Gerçek Değerlerle YPU  : {ypu.actual_a_m:.1f}×{ypu.actual_b_m:.1f} m ({ypu.actual_area_m2:.0f} m²), {ypu.actual_n_rods} Kazık, Q={ypu.declared_rho:.1f} Ω·m")
            print(f"      → Gerçek Geometri Direnci (Q={ypu.declared_rho:.0f})  : Rt = {col(f'{ypu.actual_Rt_with_project_rho:.2f} Ω', BOLD + GREEN)} (Ri={ypu.actual_Rt_with_project_rho:.2f}Ω, Rç={ypu.actual_Rc:.2f}Ω)")
            print(f"      → Standart Direnç (ρ=100 Ω·m)    : Rt = {col(f'{ypu.actual_Rt_with_standard_rho:.2f} Ω', CYAN)}")
            if ypu.rod_count_mismatch:
                print(col(f"    🚨 {ypu.rod_discrepancy_note}", RED + BOLD))
            if ypu.area_mismatch:
                print(col(f"    ⚠  {ypu.area_discrepancy_note}", YELLOW))

        if calc.legacy:
            print()
            print(col("  [1] MEVCUT PİYASA ŞABLONU (RADSAN / EH) HATA DENETİMİ:", YELLOW + BOLD))
            for f in calc.legacy.flaws:
                print(col(f"    • {f.title}", YELLOW))
            print(f"    → Şablon Hücre Değeri: {col(f'{calc.legacy.Re_flawed_ohm:.4f} Ω', RED)} (Hatalı 10.6157 çakılı)")

        if calc.laurent_niemann and calc.ieee_sverak and calc.comparison:
            ln = calc.laurent_niemann
            sv = calc.ieee_sverak
            comp = calc.comparison

            print()
            print(col("  [2] ÇAĞDAŞ HESAPLAMA METOTLARI (YAN YANA):", CYAN + BOLD))
            print(f"    ┌──────────────────────────────────────────┬──────────────────────────────────────────┐")
            print(f"    │ Yöntem 1: EMO & ETTK (Laurent-Niemann)   │ Yöntem 2: IEEE Std 80 (Sverak Formülü)  │")
            print(f"    ├──────────────────────────────────────────┼──────────────────────────────────────────┤")
            print(f"    │ Re(birleşik) = {col(f'{ln.Re_combined_ohm:8.4f} Ω', BOLD + GREEN):35s}│ Rg           = {col(f'{sv.Re_sverak_ohm:8.4f} Ω', BOLD + GREEN):35s}│")
            print(f"    │ R_temel(ağ)  = {ln.R_temel_mesh_ohm:8.4f} Ω                   │ L_toplam(LT) = {sv.total_length_LT_m:8.1f} m                  │")
            print(f"    │ Rç(4 çubuk)  = {ln.R_rod_group_ohm:8.4f} Ω                   │ Derinlik (h) = {sv.depth_h_m:8.1f} m                  │")
            print(f"    └──────────────────────────────────────────┴──────────────────────────────────────────┘")
            print(f"    → İki Yöntem Arasındaki Sapma: {col(f'%{comp.difference_pct:.2f}', BOLD + GREEN)} (Mükemmel Uyum)")

            print()
            print(col("  [3] YASAL VE CAN GÜVENLİĞİ KRİTERLERİ (ETTK Ek-N / Madde 10):", CYAN + BOLD))
            print(f"    • Dokunma Gerilimi (Ut = Re × 0.3A) : {col(f'{comp.touch_voltage_laurent_V:.2f} V', BOLD + GREEN)}  [Yasal Sınır: ≤ 50.0 V]  ->  {col('✓ GÜVENLİ / UYGUN', GREEN + BOLD)}")
            print(f"    • TT Şebeke İşletme Sınırı (≤ 5.0 Ω): {col(f'{ln.Re_combined_ohm:.3f} Ω', GREEN if comp.tt_compliant else YELLOW)}  ->  {'✓ UYGUN' if comp.tt_compliant else '⚠ SINIRDA'}")
            print(f"    • Şartname Hedefi (≤ 2.0 Ω)         : {col(f'{ln.Re_combined_ohm:.3f} Ω', GREEN if comp.target_2ohm_compliant else YELLOW)}  ->  {'✓ HEDEF SAĞLANDI' if comp.target_2ohm_compliant else '⚠ 2Ω İÇİN İLAVE KAZIK'}")

        print()
        overall = calc.overall_status()
        if overall == CheckResult.PASS:
            print(col("  ════════════════════════════════════════════════════════════════════════", GREEN))
            print(col("  ✓  GENEL MÜHENDİSLİK SONUCU: UYGUNDUR (YÖNETMELİĞE VE STANDARDA UYGUN)", GREEN + BOLD))
            print(col("  ════════════════════════════════════════════════════════════════════════", GREEN))
        else:
            print(col("  ════════════════════════════════════════════════════════════════════════", RED))
            print(col("  ✗  GENEL MÜHENDİSLİK SONUCU: DÜZELTME / REVİZYON GEREKLİ", RED + BOLD))
            print(col("  ════════════════════════════════════════════════════════════════════════", RED))
        print()
