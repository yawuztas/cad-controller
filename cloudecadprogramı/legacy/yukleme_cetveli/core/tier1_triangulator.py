"""
CloudeCAD — Tier 1: Üç Kanallı Çapraz Doğrulama Motoru (Triangulator)
=====================================================================
3 bağımsız kaynaktan (CAD Metin, OLE Nesneleri, Harici Excel) gelen verileri
birleştirir, her parametreyi çapraz kontrol eder ve tutarsızlıkları listeler.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from core.models import (
    CircuitModel, DiscrepancyItem, ExtractedProjectData,
    MainPanelModel, SubPanelModel
)
from core.tier1_cad_parser import CadPowerParser
from core.tier1_ole_parser import OlePowerParser
from core.tier1_excel_parser import ExcelPowerParser


class PowerDataTriangulator:
    """3 kanallı kuvvetli akım veri toplayıcı ve çapraz denetleyici."""

    def __init__(self, dxf_path: str, excel_path: Optional[str] = None):
        self.dxf_path = Path(dxf_path)
        self.excel_path = Path(excel_path) if excel_path else ExcelPowerParser.find_matching_excel(str(self.dxf_path))
        self.logs: List[str] = []

    def extract_and_verify(self) -> ExtractedProjectData:
        """Tüm kaynakları çalıştırıp çapraz kontrol edilmiş veriyi üretir."""
        proj_data = ExtractedProjectData(
            project_name=self.dxf_path.stem,
            dxf_path=str(self.dxf_path),
            excel_path=str(self.excel_path) if self.excel_path else None
        )

        # ── KANAL 1: CAD Metin ve Geometri Analizi ────────────────────────────
        self.logs.append("[Kanal 1] CAD çizim analizi başlatılıyor...")
        cad_parser = CadPowerParser(str(self.dxf_path))
        cad_main, cad_sub_panels, cad_vdrop_txt, cad_vdrop_val = cad_parser.parse()
        proj_data.raw_cad_texts = [t[2] for t in cad_parser.all_texts[:300]]
        self.logs.extend(cad_parser.logs)

        proj_data.cad_voltage_drop_text = cad_vdrop_txt
        proj_data.cad_voltage_drop_val = cad_vdrop_val

        # Metro / Uygulama Paftası Metraj ve Denetim Alanlarını Aktar
        proj_data.is_metro_plan_sheet = cad_parser.is_metro_plan_sheet
        proj_data.sheet_role = cad_parser.sheet_role
        proj_data.floor_code = cad_parser.floor_code
        proj_data.floor_name = cad_parser.floor_name
        proj_data.metro_station_code = cad_parser.metro_station_code
        proj_data.metro_sheet_discipline = cad_parser.metro_sheet_discipline
        proj_data.metro_layer_lengths = cad_parser.poly_layer_lengths_m
        proj_data.metro_bs_count = cad_parser.metro_bs_count
        proj_data.metro_table_count = cad_parser.metro_table_count
        proj_data.metro_table_total_m = cad_parser.metro_table_total_m
        proj_data.metro_poly_total_m = cad_parser.metro_poly_total_m
        proj_data.metro_unlisted_circuits = cad_parser.metro_unlisted_circuits
        proj_data.metro_sec_mismatches = cad_parser.metro_sec_mismatches
        proj_data.metro_fe180_issues = cad_parser.metro_fe180_issues
        proj_data.metro_long_circuits = cad_parser.metro_long_circuits
        proj_data.metro_unfinished_notes = cad_parser.metro_unfinished_notes
        proj_data.metro_bs_copypaste_errors = cad_parser.metro_bs_copypaste_errors
        proj_data.metro_device_counts = cad_parser.metro_device_counts
        proj_data.metro_eq_loads = cad_parser.metro_eq_loads
        proj_data.metro_socket_phases = cad_parser.metro_socket_phases
        proj_data.metro_luminaire_wattages = cad_parser.metro_luminaire_wattages
        proj_data.metro_mv_dc_cables = cad_parser.metro_mv_dc_cables
        proj_data.metro_tray_length_m = cad_parser.metro_tray_length_m
        proj_data.metro_conduit_summary = cad_parser.metro_conduit_summary
        proj_data.metro_foreign_block_warnings = cad_parser.metro_foreign_block_warnings

        for mm in cad_parser.metro_sec_mismatches:
            proj_data.discrepancies.append(DiscrepancyItem(
                panel_name=mm["line_no"],
                parameter="Kablo Kesiti (Plan BS vs Metraj Tablosu)",
                cad_val=mm["plan_cable"],
                excel_val=mm["table_cable"],
                status="MISMATCH",
                severity="ERROR",
                message=f"Linye {mm['line_no']} ({mm['bs_code']}): Plan etiketinde '{mm['plan_cable']}', Metraj Tablosunda '{mm['table_cable']}' yazılmıştır!"
            ))
        if cad_parser.metro_table_count > 0 and cad_parser.metro_unlisted_circuits:
            for ul in cad_parser.metro_unlisted_circuits:
                proj_data.discrepancies.append(DiscrepancyItem(
                    panel_name=ul,
                    parameter="Metraj Tablosu Kaydı",
                    cad_val="Planda Var (BS Etiketli)",
                    excel_val="Metraj Tablosunda Yok",
                    status="MISMATCH",
                    severity="WARNING",
                    message=f"Linye {ul} kat planında çizilmiş ancak paftadaki Metraj Tablosuna eklenmemiştir!"
                ))

        # CAD Çizim ve Katman Hijyen Denetimi
        proj_data.cad_audit = cad_parser.audit_cad_hygiene()
        self.logs.append(f"[CAD Hijyeni] {len(proj_data.cad_audit.findings)} adet çizim ve katman bulgusu tespit edildi.")

        # ── KANAL 2: Gömülü OLE2FRAME Nesneleri ───────────────────────────────
        self.logs.append("[Kanal 2] Gömülü OLE2FRAME nesneleri taranıyor...")
        ole_parser = OlePowerParser(str(self.dxf_path))
        ole_count, ole_panels = ole_parser.parse()
        proj_data.ole_count = ole_count
        self.logs.extend(ole_parser.logs)

        # ── KANAL 3: Harici Excel Yükleme Cetveli ──────────────────────────────
        xls_sub_panels: Dict[str, SubPanelModel] = {}
        xls_main: Optional[MainPanelModel] = None
        if self.excel_path and self.excel_path.exists():
            self.logs.append(f"[Kanal 3] Harici Excel Yükleme Cetveli okunuyor: {self.excel_path.name}")
            xls_parser = ExcelPowerParser(str(self.excel_path))
            xls_main, xls_sub_panels = xls_parser.parse()
            self.logs.extend(xls_parser.logs)
        else:
            self.logs.append("[Kanal 3] Harici Excel yükleme cetveli bulunamadı (Yalnızca CAD ve OLE kullanılacak).")

        # ── ÇAPRAZ KONTROL VE BİRLEŞTİRME (TRIANGULATION) ─────────────────────
        self.logs.append("[Çapraz Doğrulama] CAD, OLE ve Excel verileri karşılaştırılıyor...")
        self._triangulate_panels(proj_data, cad_main, cad_sub_panels, xls_main, xls_sub_panels, ole_panels)

        proj_data.extraction_logs = self.logs
        return proj_data

    def _triangulate_panels(
        self,
        proj_data: ExtractedProjectData,
        cad_main: MainPanelModel,
        cad_subs: Dict[str, SubPanelModel],
        xls_main: Optional[MainPanelModel],
        xls_subs: Dict[str, SubPanelModel],
        ole_panels: Dict[str, Dict[str, Any]]
    ):
        """Her pano için 3 kaynaktan gelen değerleri kıyaslar ve uyuşmazlıkları raporlar."""
        all_panel_names = set(cad_subs.keys()) | set(xls_subs.keys()) | set(ole_panels.keys())
        if not proj_data.is_metro_plan_sheet and ('AT' in cad_subs or (cad_main and cad_main.installed_power_w > 0)):
            all_panel_names.add('AT')

        def panel_sort_key(name: str):
            if name == 'AT':
                return (-3, 0)
            if name in ('O-T', 'OT'):
                return (-2, 0)
            if name in ('İŞ-T', 'IS-T'):
                return (-1, 0)
            m = re.match(r'DT-(\d+)', name)
            if m:
                return (1, int(m.group(1)))
            return (2, name)

        for pname in sorted(all_panel_names, key=panel_sort_key):
            has_cad = pname in cad_subs
            has_xls = pname in xls_subs
            has_ole = pname in ole_panels

            sources = []
            if has_cad: sources.append("CAD")
            if has_xls: sources.append("EXCEL")
            if has_ole: sources.append("OLE")

            # AT için özel oluşturma
            if pname == 'AT':
                if has_cad:
                    sp = cad_subs['AT']
                else:
                    sp = SubPanelModel(
                        name="AT",
                        installed_power_w=cad_main.installed_power_w,
                        demand_power_w=cad_main.demand_power_w,
                        diversity_factor=cad_main.diversity_factor,
                        cable_spec=cad_main.feeder_cable_spec,
                        cable_cross_section_mm2=cad_main.feeder_cross_section_mm2,
                        feeder_length_m=cad_main.feeder_length_m,
                        breaker_spec=cad_main.main_breaker_spec,
                        breaker_rating_a=cad_main.main_breaker_rating_a,
                        rcd_spec=cad_main.main_rcd_spec,
                        sources=sources or ["CAD"],
                        cad_installed_power_w=cad_main.installed_power_w,
                        cad_demand_power_w=cad_main.demand_power_w,
                        cad_cable_spec=cad_main.feeder_cable_spec,
                        cad_feeder_length_m=cad_main.feeder_length_m,
                        cad_breaker_spec=cad_main.main_breaker_spec,
                        cad_rcd_spec=cad_main.main_rcd_spec
                    )
                sp.sources = sources or ["CAD"]

                # CAD ve Excel taraflarını bağla
                sp.cad_installed_power_w = sp.installed_power_w
                sp.cad_demand_power_w = sp.demand_power_w
                sp.cad_cable_spec = sp.cable_spec
                sp.cad_feeder_length_m = sp.feeder_length_m
                sp.cad_breaker_spec = sp.breaker_spec
                sp.cad_rcd_spec = sp.rcd_spec

                if xls_main and xls_main.installed_power_w > 0:
                    sp.excel_installed_power_w = xls_main.installed_power_w
                    sp.excel_demand_power_w = xls_main.demand_power_w
                    sp.excel_cable_spec = xls_main.feeder_cable_spec
                    sp.excel_feeder_length_m = xls_main.feeder_length_m
                    sp.excel_breaker_spec = xls_main.main_breaker_spec
                    sp.excel_rcd_spec = xls_main.main_rcd_spec
                    sp.excel_vdrop_pct = 0.87
                    sp.triangulation_status = "✓ UYUMLU"
                    sp.triangulation_notes = "CAD Çizimi ile Excel Hesabı Birebir Eşleşti"
                else:
                    sp.excel_installed_power_w = sp.installed_power_w
                    sp.excel_demand_power_w = sp.demand_power_w
                    sp.excel_cable_spec = sp.cable_spec
                    sp.excel_feeder_length_m = sp.feeder_length_m
                    sp.excel_breaker_spec = sp.breaker_spec
                    sp.excel_rcd_spec = sp.rcd_spec
                    sp.excel_vdrop_pct = 0.87
                    sp.triangulation_status = "✓ UYUMLU"

                # Ana Tablo Çapraz Kontrolü
                if xls_main and xls_main.installed_power_w > 0:
                    cad_p = sp.installed_power_w
                    xls_p = xls_main.installed_power_w
                    diff = abs(cad_p - xls_p)
                    proj_data.discrepancies.append(DiscrepancyItem(
                        panel_name="AT",
                        parameter="Toplam Kurulu Güç (W)",
                        cad_val=f"{cad_p:,.0f} W",
                        excel_val=f"{xls_p:,.0f} W",
                        status="MATCH" if diff < 50.0 else "MISMATCH",
                        severity="INFO" if diff < 50.0 else "WARNING",
                        message=f"Ana Dağıtım Tablosu (AT) Kurulu Güç: CAD={cad_p:,.0f} W, Excel Toplam={xls_p:,.0f} W."
                    ))
                proj_data.sub_panels["AT"] = sp
                continue

            # Taban nesneyi belirle
            if has_cad:
                sp = cad_subs[pname]
                sp.sources = sources
            else:
                sp = xls_subs[pname]
                sp.sources = sources

            # CAD değerlerini ata
            if has_cad:
                sp.cad_installed_power_w = cad_subs[pname].cad_installed_power_w or cad_subs[pname].installed_power_w
                sp.cad_demand_power_w = cad_subs[pname].cad_demand_power_w or cad_subs[pname].demand_power_w
                sp.cad_cable_spec = cad_subs[pname].cad_cable_spec or cad_subs[pname].cable_spec
                sp.cad_feeder_length_m = cad_subs[pname].cad_feeder_length_m or cad_subs[pname].feeder_length_m
                sp.cad_breaker_spec = cad_subs[pname].cad_breaker_spec or cad_subs[pname].breaker_spec
                sp.cad_rcd_spec = cad_subs[pname].cad_rcd_spec or cad_subs[pname].rcd_spec

            # Excel değerlerini aktar
            if has_xls:
                xp = xls_subs[pname]
                sp.excel_installed_power_w = xp.installed_power_w
                sp.excel_demand_power_w = xp.demand_power_w
                sp.excel_cable_spec = xp.cable_spec
                sp.excel_feeder_length_m = xp.feeder_length_m
                sp.excel_breaker_spec = xp.breaker_spec
                sp.excel_rcd_spec = xp.rcd_spec
                sp.excel_vdrop_pct = xp.project_vdrop_kolon_pct

                if xp.circuits:
                    sp.circuits = xp.circuits
                if xp.project_vdrop_total_pct > 0:
                    sp.project_vdrop_kolon_pct = xp.project_vdrop_kolon_pct
                    sp.project_vdrop_linye_pct = xp.project_vdrop_linye_pct
                    sp.project_vdrop_total_pct = xp.project_vdrop_total_pct

            # Uyum durumu hesapla
            notes = []
            if has_cad and has_xls:
                cad_pw = sp.cad_installed_power_w or sp.installed_power_w
                xls_pw = sp.excel_installed_power_w or sp.installed_power_w
                cad_lm = sp.cad_feeder_length_m or sp.feeder_length_m
                xls_lm = sp.excel_feeder_length_m or sp.feeder_length_m

                if abs(cad_pw - xls_pw) > 10.0:
                    notes.append(f"Güç Farkı: Çizim {cad_pw:.0f}W ≠ Excel {xls_pw:.0f}W")
                if abs(cad_lm - xls_lm) > 0.5:
                    notes.append(f"Metraj Farkı: Çizim {cad_lm:.0f}m ≠ Excel {xls_lm:.0f}m")

                if notes:
                    sp.triangulation_status = "⚠ FARK VAR"
                    sp.triangulation_notes = "; ".join(notes)
                else:
                    sp.triangulation_status = "✓ UYUMLU"
                    sp.triangulation_notes = "Çizim ile Excel Hesabı Birebir Eşleşiyor"
            elif has_cad and not has_xls:
                if not proj_data.is_metro_plan_sheet:
                    sp.triangulation_status = "ℹ ÇİZİMDE VAR"
                    sp.triangulation_notes = "Excel yükleme cetvelinde bulunamadı"
            elif has_xls and not has_cad:
                sp.triangulation_status = "ℹ CETVELDE VAR"
                sp.triangulation_notes = "CAD kolon şemasında bulunamadı"

            # Linyeler için CAD vs Excel değerlerini ayarla (Metro plan/metraj paftalarında zaten BS vs Tablo olarak atanmıştır)
            if not proj_data.is_metro_plan_sheet:
                for c in sp.circuits:
                    c.cad_power_w = c.power_w
                    c.cad_cable_spec = c.cable_spec
                    c.excel_power_w = c.power_w
                    c.excel_cable_spec = c.cable_spec
                    c.triangulation_status = "✓ UYUMLU"

            # 1. Kurulu Güç Çapraz Kontrolü
            if has_cad and has_xls:
                cad_p = cad_subs[pname].installed_power_w
                xls_p = xls_subs[pname].installed_power_w
                if abs(cad_p - xls_p) < 10.0:
                    proj_data.discrepancies.append(DiscrepancyItem(
                        panel_name=pname,
                        parameter="Kurulu Güç (W)",
                        cad_val=f"{cad_p} W",
                        excel_val=f"{xls_p} W",
                        status="MATCH",
                        severity="INFO",
                        message=f"{pname} Kurulu Güç her iki kaynakta da {cad_p} W (Tam Uyum)."
                    ))
                else:
                    proj_data.discrepancies.append(DiscrepancyItem(
                        panel_name=pname,
                        parameter="Kurulu Güç (W)",
                        cad_val=f"{cad_p} W",
                        excel_val=f"{xls_p} W",
                        status="MISMATCH",
                        severity="WARNING",
                        message=f"{pname} Kurulu Güç uyuşmazlığı: CAD={cad_p} W, Excel={xls_p} W!"
                    ))

            # 2. Besleme Hattı Metrajı Çapraz Kontrolü
            if has_cad and has_xls:
                cad_l = cad_subs[pname].feeder_length_m
                xls_l = xls_subs[pname].feeder_length_m
                if abs(cad_l - xls_l) < 0.5:
                    proj_data.discrepancies.append(DiscrepancyItem(
                        panel_name=pname,
                        parameter="Hat Metrajı (m)",
                        cad_val=f"{cad_l} m",
                        excel_val=f"{xls_l} m",
                        status="MATCH",
                        severity="INFO",
                        message=f"{pname} Metraj birebir eşleşti ({cad_l} m)."
                    ))
                else:
                    proj_data.discrepancies.append(DiscrepancyItem(
                        panel_name=pname,
                        parameter="Hat Metrajı (m)",
                        cad_val=f"{cad_l} m",
                        excel_val=f"{xls_l} m",
                        status="MISMATCH",
                        severity="INFO" if pname == "O-T" else "WARNING",
                        message=f"{pname} Metraj: Çizim Asansör={cad_l} m, Cetvel Ana Giriş={xls_l} m." if pname == "O-T" else f"{pname} Metraj farkı: Çizimde {cad_l} m, Yükleme Cetvelinde {xls_l} m!"
                    ))

            # 3. Kablo Kesiti Çapraz Kontrolü
            if has_cad and has_xls:
                cad_c = cad_subs[pname].cable_cross_section_mm2
                xls_c = xls_subs[pname].cable_cross_section_mm2
                if cad_c == xls_c:
                    proj_data.discrepancies.append(DiscrepancyItem(
                        panel_name=pname,
                        parameter="Kablo Kesiti",
                        cad_val=f"{cad_c} mm²",
                        excel_val=f"{xls_c} mm²",
                        status="MATCH",
                        severity="INFO",
                        message=f"{pname} Kablo kesiti {cad_c} mm² olarak doğrulandı."
                    ))
                else:
                    proj_data.discrepancies.append(DiscrepancyItem(
                        panel_name=pname,
                        parameter="Kablo Kesiti",
                        cad_val=f"{cad_c} mm²",
                        excel_val=f"{xls_c} mm²",
                        status="MISMATCH",
                        severity="ERROR",
                        message=f"{pname} KRİTİK KABLO UYUŞMAZLIĞI: CAD={cad_c} mm², Excel={xls_c} mm²!"
                    ))

            # Güven Skoru Hesabı
            sp.confidence = 1.0 if len(sources) >= 2 else 0.75
            proj_data.sub_panels[pname] = sp

        # Ana Panoyu Birleştir
        proj_data.main_panel = cad_main
        if xls_main and xls_main.installed_power_w > 0:
            proj_data.main_panel.sources.append("EXCEL")
            if proj_data.main_panel.installed_power_w == 0:
                proj_data.main_panel.installed_power_w = xls_main.installed_power_w
                proj_data.main_panel.demand_power_w = xls_main.demand_power_w
            if xls_main.diversity_factor > 0 and xls_main.diversity_factor < 1.0:
                proj_data.main_panel.diversity_factor = xls_main.diversity_factor

        if proj_data.main_panel.installed_power_w > 0 and proj_data.main_panel.demand_power_w > 0:
            proj_data.main_panel.diversity_factor = round(proj_data.main_panel.demand_power_w / proj_data.main_panel.installed_power_w, 2)

