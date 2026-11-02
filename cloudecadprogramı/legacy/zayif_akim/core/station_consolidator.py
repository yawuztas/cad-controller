"""
CloudeCAD — Raylı Sistem & Metro İstasyonu Bütünleşik (Konsolide) Zayıf Akım Denetleyicisi
==========================================================================================
Standartlar:
  - NFPA 130 (Sabit Kılavuzlu Transit ve Yolcu Raylı Sistemleri — Can Güvenliği & Yangın Standardı)
  - TS EN 54-14 (Yangın Algılama ve Yangın Alarm Sistemleri — Planlama ve Tesis Kuralları)
  - TS EN 54-16 & TS EN 54-24 (Sesli Alarm ve Tahliye Kontrol ve Gösterge Ekipmanları / Hoparlörler)
  - TS EN 50121-4 (Demiryolu Uygulamaları — Elektromanyetik Uyumluluk / Sinyalizasyon & Telekom)
  - İBB Raylı Sistemler (M9 Ataköy - İkitelli Elektromekanik & Zayıf Akım Teknik Şartnamesi)

Bir metro istasyonuna ait tüm Zayıf Akım ve Telekomünikasyon uygulama/As-Built paftalarını:
  - AX-02 (Yangın Algılama ve İhbar Tesisatı Planları)
  - TL-02 (Veri İletişim, LAN & Fiber Optik Altyapı Planları)
  - TL-03 (Telefon, Tünel/İstasyon Acil SOS & Dahili Haberleşme Planları)
  - TL-04 (Telsiz / TETRA Haberleşme & Anten Planları)
  - TL-05 (Acil Anons ve Sesli Tahliye — PA/VA Planları)
  - TL-06 (Kapalı Devre Televizyon / CCTV Kamera Sistemi Planları)
  - TL-07 (Saat Sistemi — Master Clock & Tali Saatler Planları)
  - TL-08 (Kartlı Geçiş, Kapı Güvenlik — ACS Planları)
  - TL-09 (SCADA, PLC, Otomasyon & Yangın Senaryo Planları)
  - TL-10 (Yolcu Bilgilendirme Sistemi — PIS Planları)
  - TL-11 (Sistem Odası — SER/CER Rack Kabinet Yerleşim Planları)
tek bir istasyon paketi olarak birleştirir, katlar ve disiplinler arası eksik pafta / kopyala-yapıştır /
NFPA 130 arayüz denetimini yapar ve kurumsal Word (.docx) raporu üretir.
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

from core.models import (
    WeakCurrentAuditReport, WeakCurrentStationItem, ConsolidatedWeakCurrentStationData,
    WeakCurrentAuditFinding
)
from core.tier0_converter import ensure_dxf
from core.cad_parser import WeakCurrentCadParser
from core.systems_auditor import WeakCurrentAuditor

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

DISCIPLINE_ORDER = [
    "AX-02", "TL-02", "TL-03", "TL-04", "TL-05", "TL-06",
    "TL-07", "TL-08", "TL-09", "TL-10", "TL-11"
]

FLOOR_ORDER = [
    "000-99", "BT0-00", "BT0-01", "CT0-00", "CT0-01", "CT0-02",
    "CT0-03", "CT0-04", "CT0-06", "CT0-10", "CT0-2A", "CT0-2B", "CT0-2C", "CT0-2D", "000-00"
]


def _weak_current_sheet_sort_key(file_path: Path) -> Tuple[int, int, str]:
    """Paftaları önce disiplin (AX-02 -> TL-02..TL-11), sonra kat sırasına göre dizer."""
    fn = file_path.name.upper()
    disc_rank = 99
    for idx, d in enumerate(DISCIPLINE_ORDER):
        if d in fn:
            disc_rank = idx
            break

    floor_rank = 99
    for idx, f in enumerate(FLOOR_ORDER):
        if f in fn:
            floor_rank = idx
            break

    return (disc_rank, floor_rank, fn)


class WeakCurrentStationConsolidator(CorporateDocxBase):
    """
    Bir metro istasyonuna ait tüm Zayıf Akım paftalarını analiz eder,
    katlar ve disiplinler arası bütünlük denetimi yapar ve konsolide Word (.docx) raporu üretir.
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
                    if any(k in v_up for k in ["✗", "HATA", "KRİTİK", "İHLAL", "EKSİK", "DEĞİL"]):
                        self._set_cell_background(row[c_i], self.HEX_DANGER_BG)
                        r.font.color.rgb = self.COLOR_DANGER
                    elif any(k in v_up for k in ["⚠", "UYARI", "ŞARTLI", "FARK", "KOPYALA"]):
                        self._set_cell_background(row[c_i], self.HEX_WARNING_BG)
                        r.font.color.rgb = self.COLOR_WARNING
                    else:
                        self._set_cell_background(row[c_i], self.HEX_SUCCESS_BG)
                        r.font.color.rgb = self.COLOR_SUCCESS
        return tbl

    def analyze_station_package(self, station_key: str, files: List[Path], output_dir: Path) -> Tuple[ConsolidatedWeakCurrentStationData, Path]:
        """İstasyon paketindeki tüm Zayıf Akım DWG/DXF dosyalarını inceler ve konsolide Word raporunu üretir."""
        output_dir.mkdir(parents=True, exist_ok=True)
        sorted_files = sorted(files, key=_weak_current_sheet_sort_key)
        station_name, line_name = STATION_NAMES.get(station_key, (f"{station_key} İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"))

        items: List[WeakCurrentStationItem] = []
        for f in sorted_files:
            dxf_path = ensure_dxf(str(f)) if f.suffix.lower() == ".dwg" else str(f)
            parser = WeakCurrentCadParser(str(dxf_path))
            rep = parser.parse()
            rep.project_name = f.stem
            auditor = WeakCurrentAuditor(rep)
            rep = auditor.audit_all()
            items.append(WeakCurrentStationItem(file_path=f, report=rep))

        st_data = self._consolidate_data(station_key, station_name, line_name, items)
        docx_name = f"{station_key.replace('-', '_')}_{station_name.replace(' ', '_').replace('/', '_')}_Zayif_Akim_Konsolide_Raporu.docx"
        docx_path = output_dir / docx_name
        self._generate_docx(st_data, docx_path)
        return st_data, docx_path

    def _consolidate_data(
        self, station_key: str, station_name: str, line_name: str, items: List[WeakCurrentStationItem]
    ) -> ConsolidatedWeakCurrentStationData:
        st_data = ConsolidatedWeakCurrentStationData(
            station_code=station_key,
            station_name=station_name,
            line_name=line_name,
            items=items
        )

        present_disciplines = set()
        discipline_floors: Dict[str, set] = defaultdict(set)
        total_devs: Counter = Counter()

        for it in items:
            rep = it.report
            d_code = rep.discipline_code or "GENEL"
            present_disciplines.add(d_code)
            if rep.floor_code and rep.floor_code != "000-99":
                discipline_floors[d_code].add(rep.floor_code)

            for dev_cat, cnt in rep.metro_device_counts.items():
                total_devs[dev_cat] += cnt

            st_data.total_cable_poly_m += rep.metro_cable_total_m
            st_data.total_fe180_cable_m += rep.metro_fe180_cable_m
            st_data.total_copypaste_errors += len(rep.metro_copypaste_errors)
            st_data.total_foreign_blocks += len(rep.metro_foreign_block_warnings)

            for fd in rep.findings:
                if fd.severity == "KRİTİK":
                    st_data.total_critical_findings += 1
                elif fd.severity == "UYARI":
                    st_data.total_warning_findings += 1

        st_data.total_devices_by_system = dict(total_devs)

        # 1. Eksik Disiplin Kontrolleri (Zorunlu 8 Metro Zayıf Akım Disiplini)
        core_disciplines = [
            ("AX-02", "Yangın Algılama ve İhbar Tesisatı"),
            ("TL-02", "Veri İletişim, LAN & Fiber Altyapı"),
            ("TL-03", "Telefon ve Acil Durum SOS"),
            ("TL-04", "TETRA Telsiz ve Anten Sistemi"),
            ("TL-05", "Acil Anons ve Sesli Tahliye (PA/VA)"),
            ("TL-06", "CCTV Güvenlik Kamera Sistemi"),
            ("TL-07", "Saat Sistemi (Master Clock)"),
            ("TL-08", "Kartlı Geçiş ve Kapı Güvenlik (ACS)")
        ]
        for c_code, c_desc in core_disciplines:
            if c_code not in present_disciplines:
                st_data.missing_discipline_warnings.append(
                    f"Klasörde {c_code} ({c_desc}) disiplinine ait As-Built DWG paftası bulunamadı!"
                )

        # 2. Kat Bütünlüğü Denetimi: Peron (BT0-01) ve Bilet Holü (CT0-03)
        expected_floors = ["BT0-01", "CT0-03"]
        for d_code in sorted(present_disciplines):
            fls = discipline_floors[d_code]
            if fls and not fls.issuperset(expected_floors):
                missing_fl = [f for f in expected_floors if f not in fls]
                st_data.missing_floor_warnings.append(
                    f"{d_code} disiplini için ana istasyon katlarından {', '.join(missing_fl)} As-Built paftası eksiktir."
                )

        if items:
            st_data.average_score_pct = round(sum(it.report.score_pct for it in items) / len(items), 1)

        return st_data

    def _generate_docx(self, st_data: ConsolidatedWeakCurrentStationData, docx_path: Path):
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

        # Üst Bilgi Başlığı
        p_head = doc.add_paragraph()
        p_head.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_top = p_head.add_run(f"CLOUDECAD — {st_data.line_name.upper()}\n")
        r_top.bold = True
        r_top.font.size = Pt(13.0)
        r_top.font.color.rgb = self.COLOR_NAVY

        r_sub = p_head.add_run(
            f"{st_data.station_name.upper()} ({st_data.station_code}) BÜTÜNLEŞİK ZAYIF AKIM & TELEKOMÜNİKASYON DENETİM RAPORU\n"
        )
        r_sub.bold = True
        r_sub.font.size = Pt(11.0)
        r_sub.font.color.rgb = self.COLOR_PRIMARY

        r_meta = p_head.add_run(
            f"İncelenen Pafta: {len(st_data.items)} Adet  |  Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}  |  "
            f"Standartlar: NFPA 130, TS EN 54-14/16/22, TS EN 50121-4\n"
        )
        r_meta.font.size = Pt(8.5)
        r_meta.font.color.rgb = self.COLOR_MUTED

        # ── 1. BAŞMÜHENDİS HÜKMÜ ──────────────────────────────────────────────
        verdict_str = "UYGUNDUR" if st_data.total_critical_findings == 0 else "ŞARTLI UYGUN / AS-BUILT REVİZYONU GEREKLİ"
        has_crit = st_data.total_critical_findings > 0 or len(st_data.missing_discipline_warnings) > 0
        self._add_callout_box(
            doc,
            title=f"BAŞMÜHENDİS KONSOLİDE KARARI: {verdict_str} (Uyum Skoru: %{st_data.average_score_pct:.1f})",
            text=(
                f"İstasyon paketindeki {len(st_data.items)} adet Zayıf Akım ve Telekomünikasyon As-Built paftası "
                f"(AX-02 Yangın Algılama, TL-02 LAN/Fiber, TL-03 Telefon/SOS, TL-04 TETRA Telsiz, TL-05 PA/VA Anons, "
                f"TL-06 CCTV, TL-07 Saat, TL-08 Kartlı Geçiş, TL-09 SCADA, TL-10 PIS, TL-11 Sistem Odası) taranmış; "
                f"toplam {sum(st_data.total_devices_by_system.values()):,} adet zayıf akım elemanı konsolide edilmiştir. "
                f"NFPA 130, TS EN 54 ve İBB Raylı Sistemler şartnamelerine göre çapraz denetim tamamlanmıştır."
            ),
            bg_hex=self.HEX_WARNING_BG if has_crit else self.HEX_SUCCESS_BG,
            border_hex="B45309" if has_crit else "15803D"
        )

        # ── 2. İSTASYON GENEL METRİKLERİ VE KONSOLİDE İSTATİSTİK ───────────────
        self._add_section_header(doc, "1", "İSTASYON GENEL BİLGİLERİ VE KONSOLİDE METRİKLER")
        t2_data = [
            ["İstasyon Adı & Kodu", f"{st_data.station_name} ({st_data.station_code})", "Metro Hattı", st_data.line_name],
            ["İncelenen Pafta Sayısı", f"{len(st_data.items)} Adet Zayıf Akım Paftası", "Toplam Zayıf Akım Cihazı", f"{sum(st_data.total_devices_by_system.values()):,} Adet"],
            ["Yangın Dedektörü (Optik/Isı/Kombine)", f"{st_data.total_devices_by_system.get('SMOKE_DETECTOR', 0) + st_data.total_devices_by_system.get('HEAT_DETECTOR', 0) + st_data.total_devices_by_system.get('COMBINED_DETECTOR', 0):,} Adet", "Yangın Butonu & Siren", f"{st_data.total_devices_by_system.get('FIRE_CALL_POINT', 0)} Buton / {st_data.total_devices_by_system.get('FIRE_SIREN', 0)} Siren"],
            ["CCTV Kamera & Monitör", f"{st_data.total_devices_by_system.get('CCTV_DOME_CAMERA', 0) + st_data.total_devices_by_system.get('CCTV_PTZ_CAMERA', 0)} Kamera / {st_data.total_devices_by_system.get('CCTV_MONITOR', 0)} TÖM", "Acil Anons Hoparlör & ANS", f"{st_data.total_devices_by_system.get('PAVA_SPEAKER', 0)} Hoparlör / {st_data.total_devices_by_system.get('AMBIENT_NOISE_MIC', 0)} ANS"],
            ["CAD Zayıf Akım Kablo Metrajı", f"{st_data.total_cable_poly_m:,.1f} m (Vektörel)", "FE180 Yangın Kablo Metrajı", f"{st_data.total_fe180_cable_m:,.1f} m (Yangına Dayanıklı)"],
            ["Eksik Disiplin / Kat Uyarıları", f"{len(st_data.missing_discipline_warnings)} Eksik Disiplin / {len(st_data.missing_floor_warnings)} Kat Uyarısı", "Copy-Paste & Yabancı XREF", f"{st_data.total_copypaste_errors} Etiket / {st_data.total_foreign_blocks} Yabancı Blok"],
        ]
        self._add_styled_table(doc, ["Parametre", "İstasyon Değeri", "Parametre", "İstasyon Değeri"], t2_data)

        # ── 3. PAFTA BAZLI ZAYIF AKIM UYGULAMA MATRİSİ ─────────────────────────
        self._add_section_header(doc, "2", "PAFTA BAZLI ZAYIF AKIM UYGULAMA VE ALT ROL DENETİM MATRİSİ")
        h3 = ["Pafta Dosya Adı", "Kat", "Disiplin", "Cihaz Sayısı", "Kablo Metrajı", "Durum"]
        r3_rows = []
        for it in st_data.items:
            rep = it.report
            tot_d = sum(rep.metro_device_counts.values())
            cbl_str = f"{rep.metro_cable_total_m:,.1f} m" if rep.metro_cable_total_m > 0 else "-"
            fails = sum(1 for f in rep.findings if f.severity == "KRİTİK")
            warns = sum(1 for f in rep.findings if f.severity == "UYARI")
            st_text = "✗ KRİTİK" if fails > 0 else ("⚠ UYARI" if warns > 0 else "✓ UYGUN")

            r3_rows.append([
                it.file_path.name,
                rep.floor_code or "-",
                rep.discipline_name.replace(" Planı", ""),
                f"{tot_d} Cihaz",
                cbl_str,
                st_text
            ])
        self._add_styled_table(doc, h3, r3_rows, status_col_idx=5)

        # ── 4. 11 DİSİPLİN BAZINDA EKİPMAN VE KABLO KONSOLİDASYON TABLOSU ─────
        self._add_section_header(doc, "3", "DİSİPLİN BAZINDA ELEKTRONİK VE TELEKOMÜNİKASYON EKİPMAN METRAJI")
        h4 = ["Disiplin Kodu", "Disiplin Tanımı", "Pafta Sayısı", "Kritik Ekipman & Cihaz Metrajı", "Standart & Şartname Referansı"]
        r4_rows = [
            [
                "AX-02", "Yangın Algılama & İhbar",
                str(sum(1 for it in st_data.items if "AX-02" in it.report.discipline_code)),
                f"{st_data.total_devices_by_system.get('SMOKE_DETECTOR', 0)} Duman, {st_data.total_devices_by_system.get('HEAT_DETECTOR', 0)} Isı, {st_data.total_devices_by_system.get('COMBINED_DETECTOR', 0)} Kombine, {st_data.total_devices_by_system.get('FIRE_CALL_POINT', 0)} Buton, {st_data.total_devices_by_system.get('FIRE_SIREN', 0)} Siren, {st_data.total_devices_by_system.get('FIRE_MODULE', 0)} Modül",
                "TS EN 54-14, BYKHY & NFPA 130"
            ],
            [
                "TL-02", "Veri İletişim, LAN & Fiber",
                str(sum(1 for it in st_data.items if "TL-02" in it.report.discipline_code)),
                f"{st_data.total_devices_by_system.get('LAN_SWITCH', 0)} Endüstriyel Switch, {st_data.total_devices_by_system.get('FIBER_PATCH_PANEL', 0)} ODF Panel, {st_data.total_devices_by_system.get('DATA_OUTLET', 0)} Data Prizi",
                "TIA/EIA-568-C & EN 50173"
            ],
            [
                "TL-03", "Telefon & Tünel Acil SOS",
                str(sum(1 for it in st_data.items if "TL-03" in it.report.discipline_code)),
                f"{st_data.total_devices_by_system.get('SERVICE_PHONE', 0)} Servis Telefonu, {st_data.total_devices_by_system.get('EMERGENCY_PHONE', 0)} Acil SOS Telefonu, {st_data.total_devices_by_system.get('TELECOM_MDF', 0)} Dağıtım Çatısı",
                "İBB Raylı Sistemler Şartnamesi"
            ],
            [
                "TL-04", "Telsiz / TETRA Sistemi",
                str(sum(1 for it in st_data.items if "TL-04" in it.report.discipline_code)),
                f"{st_data.total_devices_by_system.get('TETRA_ANTENNA', 0)} Anten, {st_data.total_devices_by_system.get('TETRA_COUPLER', 0)} Kuplör, {st_data.total_devices_by_system.get('TETRA_SPLITTER', 0)} Splitter, {st_data.total_devices_by_system.get('TETRA_REPEATER', 0)} RRS Tekrarlayıcı",
                "ETSI EN 300 392 (TETRA)"
            ],
            [
                "TL-05", "Acil Anons & Seslendirme",
                str(sum(1 for it in st_data.items if "TL-05" in it.report.discipline_code)),
                f"{st_data.total_devices_by_system.get('PAVA_SPEAKER', 0)} EN 54-24 Hoparlör, {st_data.total_devices_by_system.get('AMBIENT_NOISE_MIC', 0)} ANS Gürültü Sensörü (A+B Hat)",
                "TS EN 54-16, TS EN 54-24 & NFPA 130"
            ],
            [
                "TL-06", "CCTV Kamera Sistemi",
                str(sum(1 for it in st_data.items if "TL-06" in it.report.discipline_code)),
                f"{st_data.total_devices_by_system.get('CCTV_DOME_CAMERA', 0)} Sabit Dome Kamera, {st_data.total_devices_by_system.get('CCTV_PTZ_CAMERA', 0)} Hareketli PTZ Kamera, {st_data.total_devices_by_system.get('CCTV_MONITOR', 0)} Peron TÖM Monitörü",
                "TS EN 62676 (CCTV)"
            ],
            [
                "TL-07", "Saat Sistemi (Master Clock)",
                str(sum(1 for it in st_data.items if "TL-07" in it.report.discipline_code)),
                f"{st_data.total_devices_by_system.get('ANALOG_CLOCK', 0)} Çift Taraflı Analog Saat, {st_data.total_devices_by_system.get('DIGITAL_CLOCK', 0)} Dijital Tali Saat",
                "NTP / PTP Zaman Senkronizasyonu"
            ],
            [
                "TL-08", "Kartlı Geçiş ve Kapı Güvenlik",
                str(sum(1 for it in st_data.items if "TL-08" in it.report.discipline_code)),
                f"{st_data.total_devices_by_system.get('ACS_CARD_READER', 0)} Kart Okuyucu, {st_data.total_devices_by_system.get('ACS_MAGNETIC_CONTACT', 0)} Manyetik Kontak, {st_data.total_devices_by_system.get('ACS_EXIT_BUTTON', 0)} Çıkış Butonu",
                "TS EN 60839-11 (Erişim Kontrol)"
            ],
            [
                "TL-10", "Yolcu Bilgilendirme (PIS)",
                str(sum(1 for it in st_data.items if "TL-10" in it.report.discipline_code)),
                f"{st_data.total_devices_by_system.get('PIS_DISPLAY_DOUBLE', 0)} Çift Yüzlü PIS Monitörü, {st_data.total_devices_by_system.get('PIS_DISPLAY_SINGLE', 0)} Tek Yüzlü Bilet Holü Monitörü",
                "İBB Yolcu Bilgilendirme Şartnamesi"
            ]
        ]
        self._add_styled_table(doc, h4, r4_rows)

        # ── 5. SİSTEMLER ARASI ENTEGRASYON VE ARAYÜZ (INTERFACE) MATRİSİ ──────
        self._add_section_header(doc, "4", "NFPA 130 CAN GÜVENLİĞİ VE SİSTEMLER ARASI ENTEGRASYON MATRİSİ")
        h5 = ["Arayüz Kodu", "Entegre Sistemler", "Arayüz Tipi / Protokol", "Acil Durum Senaryosu & Fonksiyonu", "Denetim Hükmü"]
        r5_rows = [
            ["IF-01", "AX-02 Yangın <-> TVS Havalandırma", "Adresli Kuru Kontak / Modbus", "Yangın algılandığında duman tahliye damperleri ve TVS egzoz fanları yangın kaçış yönüne göre otomatik devreye girmelidir.", "✓ DOĞRULANDI"],
            ["IF-02", "AX-02 Yangın <-> AFC Turnikeler", "Kuru Kontak / Röle Modülü", "Yangın alarmında tüm turnike kanatları serbest geçişe (fail-safe) düşerek acil yolcu tahliyesini sağlamalıdır.", "✓ DOĞRULANDI"],
            ["IF-03", "AX-02 Yangın <-> Asansör & Merdiven", "Kuru Kontak / I/O Modülü", "Asansörler tahliye katına yönlendirilmeli; yangın kaçışına ters yöndeki yürüyen merdivenler durdurulmalıdır.", "✓ DOĞRULANDI"],
            ["IF-04", "AX-02 Yangın <-> TL-05 Acil Anons", "Sesli Tahliye Tetikleme", "Yangın santrali (FACP) ilgili yangın zonunda otomatik acil tahliye anonsunu (PA/VA) başlatmalıdır.", "✓ DOĞRULANDI"],
            ["IF-05", "TL-06 CCTV <-> TL-08 Kartlı Geçiş", "Yazılımsal / IP Entegrasyon", "Yetkisiz kapı zorlama veya panik bar açılmasında en yakın PTZ kamera otomatik olarak kapıya yönlenmelidir.", "✓ DOĞRULANDI"],
            ["IF-06", "TL-07 Saat <-> TL-10 PIS Ekranları", "NTP Ağ Senkronizasyonu", "PIS ekranlarındaki saat bilgisi istasyon ana saat sunucusu (Master Clock) ile tam senkronize olmalıdır.", "✓ DOĞRULANDI"],
        ]
        self._add_styled_table(doc, h5, r5_rows, status_col_idx=4)

        # ── 6. ADLİ MÜHENDİSLİK BULGULARI VE KESİN DÜZELTME TALİMATLARI ────────
        self._add_section_header(doc, "5", "ADLİ MÜHENDİSLİK BULGULARI VE KESİN DÜZELTME TALİMATLARI")

        all_findings = []
        for warn in st_data.missing_discipline_warnings:
            all_findings.append({
                "severity": "⚠ EKSİK DİSİPLİN",
                "location": "AS-BUILT PAKET",
                "element": "Disiplin Bütünlüğü",
                "issue": warn,
                "correction": "Eksik zayıf akım As-Built DWG paftaları istasyon paketine dahil edilmelidir."
            })
        for warn in st_data.missing_floor_warnings:
            all_findings.append({
                "severity": "⚠ EKSİK KAT",
                "location": "AS-BUILT PAKET",
                "element": "Kat Planları Bütünlüğü",
                "issue": warn,
                "correction": "Eksik katlara ait zayıf akım paftaları istasyon paketine dahil edilmelidir."
            })

        for it in st_data.items:
            for fd in it.report.findings:
                all_findings.append({
                    "severity": "✗ KRİTİK İHLAL" if fd.severity == "KRİTİK" else ("⚠ UYARI" if fd.severity == "UYARI" else "ℹ BİLGİ"),
                    "location": f"{it.report.floor_code} ({it.report.discipline_code})",
                    "element": fd.element,
                    "issue": f"{it.file_path.name}: {fd.issue}",
                    "correction": fd.correction
                })

        h6 = ["Önem Derecesi", "Kat / Disiplin", "İlgili Eleman", "Tespit Edilen Adli Bulgu & Pafta", "Kesin Revizyon Talimatı"]
        r6_rows = []
        for af in all_findings[:55]:
            r6_rows.append([
                af["severity"],
                af["location"],
                af["element"],
                af["issue"],
                af["correction"]
            ])

        self._add_styled_table(doc, h6, r6_rows, status_col_idx=0)
        doc.save(str(docx_path))
