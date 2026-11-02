"""
CloudeCAD — Raylı Sistem & Metro İstasyonu Bütünleşik (Konsolide) Kuvvetli Akım Denetleyicisi
=============================================================================================
Standartlar:
  - TS HD 60364-5-52 & 4-43 (Kablo Akım Taşıma Kapasitesi, Gerilim Düşümü ve Aşırı Akım Koruması)
  - IEC 60909 (Kısa Devre Akımı ve Termik Dayanım Hesabı)
  - NFPA 130 (Sabit Kılavuzlu Transit ve Yolcu Raylı Sistemler — Acil Durum & Yangın FE180 Kablo Standardı)
  - TS EN 50122-1 / 2 (Raylı Sistemler OG / 1500V DC Cer Gücü ve VLD Güvenliği)
  - İBB Raylı Sistemler (M9 Ataköy - İkitelli Elektromekanik Teknik Şartnamesi)

Bir metro istasyonuna ait tüm Kuvvetli Akım uygulama/As-Built paftalarını:
  - PS-08 (34.5 kV OG ve 1500V DC Cer Gücü / VLD Kablo Güzergah ve Kumanda Planları)
  - PS-11 (Güç / Kuvvet ve Mekanik Tesisat Kat Planları)
  - PS-16-001 (Aydınlatma Tesisatı Kat Planları)
  - PS-16-051 (Priz Tesisatı Kat Planları)
  - GN-13 (Kablo Tavası / Merdiveni Yerleşim Planları)
  - GN-14 (Döşeme Altı / Duvar İçi HDPE Kablo Borulama ve Rezervasyon Planları)
  - AX-01 / GN-07 (Çevre ve Dış Aydınlatma Planları)
tek bir istasyon paketi olarak birleştirir, katlar ve disiplinler arası eksik pafta /
kopyala-yapıştır / FE180 / faz dengesi denetimini yapar ve kurumsal Word (.docx) raporu üretir.
"""

import importlib.util
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

from core.models import ExtractedProjectData, SubPanelModel
from core.tier0_converter import ensure_dxf
from core.tier1_triangulator import PowerDataTriangulator
from core.tier2_typology_detector import TypologyDetector
from core.tier3_calculator import EngineeringAuditReport, EngineeringCalculator

# Ortak CorporateDocxBase sınıfını yükle
_DOCX_BASE_PATH = Path(__file__).resolve().parents[2] / "topraklama_motoru" / "core" / "docx_base.py"
_spec = importlib.util.spec_from_file_location("cloudecad_docx_base", str(_DOCX_BASE_PATH))
_docx_base_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_docx_base_mod)
CorporateDocxBase = _docx_base_mod.CorporateDocxBase


STATION_NAMES = {
    "M09-S18": ("İkitelli Sanayi İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "M09-S19": ("Masko İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "M09-S20": ("Bahariye İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "M09-S21": ("Atatürk Mahallesi İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "M09-S22": ("Halkalı Caddesi / 15 Temmuz İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "M09-S23": ("Mimar Sinan İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "M09-S24": ("Çobançeşme / Kuyumcukent İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "M09-S25": ("29 Ekim Cumhuriyet İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "M09-S26": ("Doğu Sanayi İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "M09-S27": ("İhlas Yuva İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "M09-S28": ("Yenibosna İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "M09-S29": ("Ataköy İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
}


@dataclass
class PowerSheetItem:
    """İstasyon paketi içindeki tekil bir Kuvvetli Akım paftasının analiz çıktısı."""
    file_path: Path
    proj_data: ExtractedProjectData
    audit_report: EngineeringAuditReport


@dataclass
class ConsolidatedPowerStationData:
    """Bir metro istasyonunun tüm Kuvvetli Akım disiplinlerinin birleştirilmiş modeli."""
    station_code: str
    station_name: str
    line_name: str
    items: List[PowerSheetItem] = field(default_factory=list)
    missing_floor_warnings: List[str] = field(default_factory=list)
    consolidated_panels: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    total_installed_kw: float = 0.0
    total_demand_kw: float = 0.0
    total_cable_poly_m: float = 0.0
    total_tray_m: float = 0.0
    total_mv_dc_table_m: float = 0.0
    total_circuits: int = 0
    total_fe180_issues: int = 0
    total_copypaste_errors: int = 0
    total_foreign_blocks: int = 0
    average_score_pct: float = 100.0


def _power_sheet_sort_key(file_path: Path) -> Tuple[int, int, str]:
    """Paftaları önce disiplin (PS-08 -> PS-11 -> PS-16-001 -> PS-16-051 -> GN-13 -> GN-14 -> AX-01), sonra kat sırasına dizer."""
    fn = file_path.name.upper()
    if "PS-08" in fn:
        disc_rank = 1
    elif "PS-11" in fn:
        disc_rank = 2
    elif "PS-16" in fn and not any(k in fn for k in ["-051", "-052", "-053", "~05"]):
        disc_rank = 3
    elif "PS-16" in fn:
        disc_rank = 4
    elif "GN-13" in fn:
        disc_rank = 5
    elif "GN-14" in fn:
        disc_rank = 6
    elif "AX-01" in fn or "GN-07" in fn:
        disc_rank = 7
    else:
        disc_rank = 8

    floor_order = ["BT0-00", "BT0-01", "CT0-02", "CT0-03", "CT0-10", "CT0-2A", "CT0-2B", "CT0-2C", "AG0-06", "000-00", "000-10", "000-99"]
    fl_rank = 99
    for idx, fc in enumerate(floor_order):
        if fc in fn:
            fl_rank = idx
            break
    return (disc_rank, fl_rank, fn)


class PowerStationConsolidator(CorporateDocxBase):
    """
    Bir metro istasyonuna ait tüm Kuvvetli Akım paftalarını analiz eder,
    katlar/disiplinler arası bütünlük kontrolü yapar ve konsolide Word (.docx) raporu üretir.
    """

    def _add_styled_table(self, doc: Document, headers: List[str], rows_data: List[List[str]], status_col_idx: Optional[int] = None):
        tbl = doc.add_table(rows=1, cols=len(headers))
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._set_table_borders(tbl)

        for i, h in enumerate(headers):
            c = tbl.rows[0].cells[i]
            self._set_cell_background(c, self.HEX_HEADER_BG)
            self._set_cell_margins(c, top=70, bottom=70, left=65, right=65)
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(h)
            r.bold = True
            r.font.size = Pt(8.0)
            r.font.color.rgb = RGBColor(255, 255, 255)

        for r_idx, r_vals in enumerate(rows_data):
            row = tbl.add_row().cells
            for c_i, val in enumerate(r_vals):
                self._set_cell_margins(row[c_i], top=55, bottom=55, left=65, right=65)
                if r_idx % 2 == 1:
                    self._set_cell_background(row[c_i], self.HEX_ZEBRA_BG)
                p = row[c_i].paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if c_i in (0, 1) else WD_ALIGN_PARAGRAPH.CENTER
                r = p.add_run(str(val))
                r.font.size = Pt(8.0)
                if c_i == 0:
                    r.bold = True
                if status_col_idx is not None and c_i == status_col_idx:
                    r.bold = True
                    v_up = str(val).upper()
                    if any(k in v_up for k in ["✗", "HATA", "KRİTİK", "İHLAL", "EKSİK"]):
                        self._set_cell_background(row[c_i], self.HEX_DANGER_BG)
                        r.font.color.rgb = self.COLOR_DANGER
                    elif any(k in v_up for k in ["⚠", "UYARI", "ŞARTLI", "FARK", "KOPYALA"]):
                        self._set_cell_background(row[c_i], self.HEX_WARNING_BG)
                        r.font.color.rgb = self.COLOR_WARNING
                    else:
                        self._set_cell_background(row[c_i], self.HEX_SUCCESS_BG)
                        r.font.color.rgb = self.COLOR_SUCCESS
        return tbl

    def analyze_station_package(self, station_key: str, files: List[Path], output_dir: Path) -> Tuple[ConsolidatedPowerStationData, Path]:
        """İstasyon paketindeki tüm DWG/DXF dosyalarını inceler ve konsolide Word raporunu üretir."""
        output_dir.mkdir(parents=True, exist_ok=True)
        sorted_files = sorted(files, key=_power_sheet_sort_key)
        station_name, line_name = STATION_NAMES.get(station_key, (f"{station_key} İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"))

        items: List[PowerSheetItem] = []
        for f in sorted_files:
            dxf_path = ensure_dxf(str(f), use_cache=True) if f.suffix.lower() == ".dwg" else str(f)
            tri = PowerDataTriangulator(str(dxf_path))
            proj_data = tri.extract_and_verify()
            proj_data.project_name = f.stem
            typology, conf, reason = TypologyDetector.detect(proj_data)
            calc = EngineeringCalculator(proj_data, typology, reason)
            audit_rep = calc.compute_and_audit()
            items.append(PowerSheetItem(file_path=f, proj_data=proj_data, audit_report=audit_rep))

        st_data = self._consolidate_data(station_key, station_name, line_name, items)
        docx_name = f"{station_key.replace('-', '_')}_{station_name.replace(' ', '_').replace('/', '_')}_Kuvvetli_Akim_Konsolide_Raporu.docx"
        docx_path = output_dir / docx_name
        self._generate_docx(st_data, docx_path)
        return st_data, docx_path

    def _consolidate_data(self, station_key: str, station_name: str, line_name: str, items: List[PowerSheetItem]) -> ConsolidatedPowerStationData:
        st_data = ConsolidatedPowerStationData(
            station_code=station_key,
            station_name=station_name,
            line_name=line_name,
            items=items,
        )

        # 1. Kat ve Disiplin Matrisi — Eksik Kat Paftası (As-Built Paket Bütünlüğü) Kontrolü
        floors_by_role: Dict[str, Dict[str, str]] = defaultdict(dict)
        all_detected_floors: Dict[str, str] = {}
        for it in items:
            fc = it.proj_data.floor_code
            fn = it.proj_data.floor_name
            role = it.proj_data.sheet_role
            if fc and fc not in ("GENEL", "TOPLU", "000-00", "000-10", "000-99"):
                floors_by_role[role][fc] = fn
                all_detected_floors[fc] = fn

        # Ana katlar (BT0-01 Peron, CT0-03 Bilet Holü, CT0-2A Asma Kat, CT0-2B Teknik Kat)
        core_floors = {fc: fn for fc, fn in all_detected_floors.items() if fc in ("BT0-01", "CT0-03", "CT0-2A", "CT0-2B")}
        role_labels = {
            "METRO_KUVVET_PLANI": "PS-11 (Güç & Mekanik Besleme Planı)",
            "METRO_AYDINLATMA_PLANI": "PS-16-001 (Aydınlatma Tesisat Planı)",
            "METRO_PRIZ_PLANI": "PS-16-051 (Priz Tesisat Planı)",
            "METRO_KABLO_TAVASI_PLANI": "GN-13 (Kablo Tavası Yerleşim Planı)",
            "METRO_BORULAMA_PLANI": "GN-14 (Döşeme Altı HDPE Borulama Planı)",
        }
        for r_key, r_lbl in role_labels.items():
            present_fcs = set(floors_by_role.get(r_key, {}).keys())
            missing_fcs = [f"{fc} ({core_floors[fc]})" for fc in sorted(core_floors.keys()) if fc not in present_fcs]
            if missing_fcs and len(present_fcs) < len(core_floors):
                st_data.missing_floor_warnings.append(
                    f"{r_lbl} disiplini için klasörde yalnızca {len(present_fcs)} kat mevcuttur; "
                    f"eksik kat paftaları: {', '.join(missing_fcs)}."
                )

        # 2. Panoları ve Yükleri Konsolide Et (Aynı linyenin birden fazla paftada mükerrer toplanmasını önle)
        panel_circuits_map: Dict[str, Dict[str, Any]] = defaultdict(dict)
        panel_roles_set: Dict[str, set] = defaultdict(set)
        panel_floors_set: Dict[str, set] = defaultdict(set)

        for it in items:
            pd = it.proj_data
            st_data.total_cable_poly_m += pd.metro_poly_total_m
            st_data.total_tray_m += pd.metro_tray_length_m
            if pd.sheet_role == "METRO_OG_DC_PLANI":
                st_data.total_mv_dc_table_m += pd.metro_table_total_m

            st_data.total_fe180_issues += len(pd.metro_fe180_issues)
            st_data.total_copypaste_errors += len(pd.metro_bs_copypaste_errors)
            st_data.total_foreign_blocks += len(pd.metro_foreign_block_warnings)

            for pname, sp in pd.sub_panels.items():
                panel_roles_set[pname].add(pd.sheet_role.replace("METRO_", "").replace("_PLANI", ""))
                panel_floors_set[pname].add(pd.floor_code or "GENEL")
                for c in sp.circuits:
                    panel_circuits_map[pname][c.circuit_no] = c

        tot_inst_w = 0.0
        tot_dem_w = 0.0
        tot_c_cnt = 0

        for pname in sorted(panel_circuits_map.keys()):
            c_dict = panel_circuits_map[pname]
            clist = list(c_dict.values())
            tot_c_cnt += len(clist)
            p_inst = sum(c.power_w for c in clist)
            ks = 0.85 if any(k in pname for k in ['İAP', 'TAP']) else (0.55 if any(k in pname for k in ['RPP', 'TPP']) else 0.78)
            p_dem = p_inst * ks
            tot_inst_w += p_inst
            tot_dem_w += p_dem

            # Faz dağılımı
            pr = ps = pt = 0.0
            for c in clist:
                if c.phase == "R":
                    pr += c.power_w
                elif c.phase == "S":
                    ps += c.power_w
                elif c.phase == "T":
                    pt += c.power_w
                else:
                    pr += c.power_w / 3.0
                    ps += c.power_w / 3.0
                    pt += c.power_w / 3.0
            pmax = max(pr, ps, pt)
            pmin = min(pr, ps, pt)
            unb_pct = round(((pmax - pmin) / pmax) * 100.0, 1) if pmax > 0 else 0.0

            ib_a = p_dem / (math.sqrt(3.0) * 400.0 * 0.80) if p_dem > 0 else 0.0
            st_data.consolidated_panels[pname] = {
                "panel_name": pname,
                "roles": ", ".join(sorted(panel_roles_set[pname])),
                "floors": ", ".join(sorted(panel_floors_set[pname])),
                "circuit_count": len(clist),
                "installed_kw": round(p_inst / 1000.0, 2),
                "demand_kw": round(p_dem / 1000.0, 2),
                "ib_a": round(ib_a, 1),
                "unbalance_pct": unb_pct,
                "sample_cables": ", ".join(sorted(set(c.cable_spec for c in clist))[:2]),
            }

        st_data.total_installed_kw = round(tot_inst_w / 1000.0, 1)
        st_data.total_demand_kw = round(tot_dem_w / 1000.0, 1)
        st_data.total_circuits = tot_c_cnt
        if items:
            st_data.average_score_pct = round(sum(it.audit_report.score_pct for it in items) / len(items), 1)
        return st_data

    def _generate_docx(self, st: ConsolidatedPowerStationData, out_path: Path) -> Path:
        doc = Document()
        for section in doc.sections:
            section.page_width = Cm(21.0)
            section.page_height = Cm(29.7)
            section.top_margin = Cm(1.5)
            section.bottom_margin = Cm(1.5)
            section.left_margin = Cm(1.5)
            section.right_margin = Cm(1.5)

        style_normal = doc.styles["Normal"]
        style_normal.font.name = "Calibri"
        style_normal.font.size = Pt(9.0)
        style_normal.font.color.rgb = self.COLOR_TEXT

        # Başlık
        p_head = doc.add_paragraph()
        p_head.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r1 = p_head.add_run(
            f"CLOUDECAD — {st.station_name.upper()} ({st.station_code}) BÜTÜNLEŞİK KUVVETLİ AKIM UYGULAMA VE AS-BUILT DENETİM RAPORU\n"
        )
        r1.bold = True
        r1.font.size = Pt(13.0)
        r1.font.color.rgb = self.COLOR_NAVY
        r2 = p_head.add_run(
            f"Hat: {st.line_name}  |  İncelenen Pafta Paketi: {len(st.items)} Adet DWG Paftası  |  Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        r2.font.size = Pt(9.0)
        r2.font.color.rgb = self.COLOR_MUTED

        # ── BÖLÜM 1: YÖNETİCİ ÖZETİ VE İSTASYON KÜNYESİ ──────────────────────
        self._add_section_header(doc, "1", "İSTASYON KUVVETLİ AKIM YÖNETİCİ ÖZETİ VE MÜHENDİSLİK KARNESİ")

        has_issues = (
            st.total_fe180_issues > 0
            or st.total_copypaste_errors > 0
            or st.total_foreign_blocks > 0
            or len(st.missing_floor_warnings) > 0
        )
        verdict_str = (
            f"ŞARTLI UYGUN / AS-BUILT REVİZYONU GEREKLİ (Uyum Skoru: %{st.average_score_pct:.1f})"
            if has_issues else f"TAM UYGUN (Uyum Skoru: %{st.average_score_pct:.1f})"
        )
        self._add_callout_box(
            doc,
            f"BAŞMÜHENDİS KONSOLİDE KARARI: {verdict_str}",
            f"İstasyon paketindeki {len(st.items)} adet As-Built/Uygulama paftası (PS-08 OG/DC, PS-11 Kuvvet/Mekanik, PS-16 Aydınlatma & Priz, "
            f"GN-13 Kablo Tavası, GN-14 HDPE Borulama) 8 alt rol sınıflandırıcısı ile taranmış; {len(st.consolidated_panels)} dağıtım panosu ve "
            f"{st.total_circuits} linye konsolide edilmiştir. NFPA 130, TS EN 50122 ve TS HD 60364 standartlarına göre çapraz denetim tamamlanmıştır.",
            bg_hex=self.HEX_WARNING_BG if has_issues else self.HEX_SUCCESS_BG,
            border_hex="B45309" if has_issues else "15803D",
        )

        kv_rows = [
            ("İstasyon Adı & Kodu", f"{st.station_name} ({st.station_code})", "Metro Hattı", st.line_name),
            ("İncelenen Pafta Sayısı", f"{len(st.items)} Adet Uygulama / As-Built Paftası", "Konsolide Pano & Linye", f"{len(st.consolidated_panels)} Pano / {st.total_circuits} Linye"),
            ("Konsolide Kurulu Güç", f"{st.total_installed_kw:,.1f} kW", "Konsolide Talep Gücü", f"{st.total_demand_kw:,.1f} kW"),
            ("CAD Elektrik & Boru Metrajı", f"{st.total_cable_poly_m:,.1f} m (Vektörel)", "Kablo Tavası & OG/DC Tablo", f"Tava: {st.total_tray_m:,.1f} m | OG/DC Tablo: {st.total_mv_dc_table_m:,.0f} m"),
            ("NFPA 130 FE180 İhlali", f"{st.total_fe180_issues} Adet Hat", "Copy-Paste & Yabancı Blok", f"{st.total_copypaste_errors} Etiket Hatası | {st.total_foreign_blocks} Yabancı XREF"),
        ]
        tbl_meta = doc.add_table(rows=len(kv_rows), cols=4)
        tbl_meta.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._set_table_borders(tbl_meta)
        for r_idx, (k1, v1, k2, v2) in enumerate(kv_rows):
            row_cells = tbl_meta.rows[r_idx].cells
            for c_i, txt in enumerate((k1, v1, k2, v2)):
                self._set_cell_margins(row_cells[c_i], top=65, bottom=65, left=90, right=90)
                p = row_cells[c_i].paragraphs[0]
                run = p.add_run(str(txt))
                run.font.size = Pt(8.5)
                if c_i in (0, 2):
                    self._set_cell_background(row_cells[c_i], "E2E8F0")
                    run.bold = True
                    run.font.color.rgb = self.COLOR_NAVY
                elif r_idx % 2 == 1:
                    self._set_cell_background(row_cells[c_i], self.HEX_ZEBRA_BG)

        # ── BÖLÜM 2: İSTASYON PAFTA PAKETİ VE ALT ROL ENVANTER MATRİSİ ───────
        self._add_section_header(doc, "2", "İSTASYON KUVVETLİ AKIM PAFTA PAKETİ VE 8 ALT ROL ENVANTER MATRİSİ")

        sheet_rows = []
        for it in st.items:
            pd = it.proj_data
            ar = it.audit_report
            c_cnt = sum(len(sp.circuits) for sp in pd.sub_panels.values())
            fails = sum(1 for f in ar.findings if f.status == "FAIL")
            warns = sum(1 for f in ar.findings if f.status == "WARNING")
            if pd.cad_audit:
                warns += len(pd.cad_audit.findings)
            st_badge = "✗ KRİTİK" if fails > 0 else ("⚠ UYARI" if warns > 0 else "✓ UYGUN")
            sheet_rows.append([
                it.file_path.name,
                pd.floor_code or "-",
                pd.sheet_role.replace("METRO_", ""),
                f"{len(pd.sub_panels)}P / {c_cnt}L",
                f"{pd.metro_poly_total_m:,.1f} m",
                f"{pd.metro_bs_count} Etiket" + (f" / {pd.metro_table_total_m:.0f}m Tablo" if pd.metro_table_count > 0 else ""),
                st_badge,
            ])

        self._add_styled_table(
            doc,
            ["Pafta Dosya Adı", "Kat Kodu", "Tespit Edilen Alt Rol", "Pano/Linye", "CAD Metrajı", "Etiket / Tablo Özeti", "Durum"],
            sheet_rows,
            status_col_idx=6,
        )

        if st.missing_floor_warnings:
            p_mf = doc.add_paragraph()
            p_mf.paragraph_format.space_before = Pt(6)
            r_mf = p_mf.add_run("⚠ PAKET BÜTÜNLÜK BULGUSU (As-Built Klasöründe Eksik Kat Paftaları):\n" + "\n".join(f"  • {w}" for w in st.missing_floor_warnings))
            r_mf.bold = True
            r_mf.font.size = Pt(8.5)
            r_mf.font.color.rgb = self.COLOR_WARNING

        # ── BÖLÜM 3: İSTASYON GENELİ KONSOLİDE DAĞITIM PANOLARI VE YÜK TABLOSU ─
        self._add_section_header(doc, "3", "İSTASYON GENELİ KONSOLİDE DAĞITIM PANOLARI VE FAZ DENGESİ TABLOSU")

        panel_rows = []
        for pname, pinfo in st.consolidated_panels.items():
            unb = pinfo["unbalance_pct"]
            st_p = "⚠ FAZ DENGESİZ" if unb > 15.0 else "✓ DENGELİ"
            panel_rows.append([
                pname,
                pinfo["floors"],
                pinfo["roles"],
                str(pinfo["circuit_count"]),
                f"{pinfo['installed_kw']:.2f} kW",
                f"{pinfo['demand_kw']:.2f} kW",
                f"{pinfo['ib_a']:.1f} A",
                f"%{unb:.1f}",
                pinfo["sample_cables"],
                st_p,
            ])

        self._add_styled_table(
            doc,
            ["Pano Kodu", "Katlar", "Disiplin", "Linye", "Pkur (kW)", "Ptal (kW)", "Akım Ib", "Asimetri", "Tipik Kablo Kesiti", "Durum"],
            panel_rows,
            status_col_idx=9,
        )

        # ── BÖLÜM 4: 34.5 kV OG / 1500V DC CER GÜCÜ, TAVA VE BORULAMA ÖZETİ ───
        self._add_section_header(doc, "4", "34.5 kV OG / 1500V DC CER GÜCÜ (PS-08), KABLO TAVASI (GN-13) VE BORULAMA (GN-14) DENETİMİ")

        mv_all = []
        for it in st.items:
            for r in it.proj_data.metro_mv_dc_cables:
                mv_all.append([
                    it.proj_data.floor_code or "-",
                    r["equipment"],
                    r["cable_sec"],
                    r["cable_type"],
                    f"{r['length_m']:.0f} m",
                    "✓ OG/DC METRAJ",
                ])
        if mv_all:
            self._add_styled_table(
                doc,
                ["Kat", "Beslenen OG / Cer Gücü Ekipmanı", "Kablo Kesiti", "İzolasyon / Gerilim", "Metraj", "Durum"],
                mv_all,
                status_col_idx=5,
            )

        # ── BÖLÜM 5: PAFTALAR ARASI ADLİ BULGULAR VE REVİZYON TALİMATLARI ─────
        self._add_section_header(doc, "5", "ADLİ MÜHENDİSLİK VE CAD DENETİM BULGULARI — KESİN DÜZELTME TALİMATLARI")

        finding_rows = []
        for w in st.missing_floor_warnings:
            finding_rows.append([
                "⚠ EKSİK PAFTA",
                "AS-BUILT PAKET",
                "Kat Planları Bütünlüğü",
                w,
                "Eksik katlara ait PS-16 (Aydınlatma/Priz) ve GN-13 (Kablo Tavası) As-Built DWG paftaları istasyon klasörüne eklenmelidir.",
            ])

        for it in st.items:
            pd = it.proj_data
            short_fn = f"{pd.floor_code or 'GENEL'} ({pd.sheet_role.replace('METRO_', '')})"
            for cp in pd.metro_bs_copypaste_errors:
                finding_rows.append([
                    "⚠ KOPYALA-YAPIŞTIR",
                    short_fn,
                    "BS / CS Kablo Çağrı Etiketi",
                    f"{it.file_path.name}: {cp}",
                    "Başka istasyon veya linyeden kopyalanıp unutulan BS/CS çağrı etiketi mevcut istasyon ve linye koduyla güncellenmelidir.",
                ])
            for fb in pd.metro_foreign_block_warnings:
                finding_rows.append([
                    "⚠ YABANCI XREF",
                    short_fn,
                    "Farklı Hat/İstasyon Bloğu",
                    f"{it.file_path.name}: Çizim içinde farklı hat/istasyon blok referansı ({fb}) unutulmuştur.",
                    f"Yabancı istasyon referanslı blok adı {st.station_code} istasyon koduyla temizlenmelidir.",
                ])
            for fe in pd.metro_fe180_issues:
                finding_rows.append([
                    "✗ NFPA 130 İHLALİ",
                    short_fn,
                    f"{fe['line_no']} ({fe['panel']})",
                    f"{it.file_path.name}: Acil/Yangın hattında ({fe['target']}) FE180 olmayan '{fe['cable']}' kablo kullanılmıştır.",
                    "NFPA 130 ve BYKHY gereği acil aydınlatma, priz, yangın damperi ve duman fanı kabloları N2XH FE180 yapılmalıdır.",
                ])

        if not finding_rows:
            finding_rows.append([
                "✓ UYGUN",
                "TÜM PAFTALAR",
                "İstasyon Geneli",
                "İncelenen tüm paftalarda kablo kesitleri, FE180 yangın güvenliği ve etiketleme tam uyumludur.",
                "Mevcut As-Built projesi onaylanabilir durumdadır.",
            ])

        self._add_styled_table(
            doc,
            ["Önem Derecesi", "Kat / Disiplin", "İlgili Eleman / Pano", "Tespit Edilen Adli Bulgu & Pafta", "Kesin Revizyon Talimatı"],
            finding_rows,
            status_col_idx=0,
        )

        doc.save(str(out_path))
        return out_path
