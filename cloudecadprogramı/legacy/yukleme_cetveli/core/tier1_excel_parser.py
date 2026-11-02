"""
CloudeCAD — Yol 3: Harici Excel Yükleme Cetveli Analizi (Excel Parser)
=====================================================================
Proje klasöründeki veya 'raporlar' altındaki ilgili Excel Yükleme Cetvelini
(faruk demir - Yükleme Cetveli.xls, adem abi - Yükleme Cetveli.xls vb.)
sayfa sayfa okuyarak tam detaylı linye ve pano parametrelerini ayıklar.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import xlrd

from core.models import CircuitModel, MainPanelModel, SubPanelModel
from core.tier1_cad_parser import extract_cross_section_from_cable


class ExcelPowerParser:
    """Excel yükleme cetvellerini ayrıştıran motor."""

    def __init__(self, excel_path: Optional[str] = None):
        self.excel_path = Path(excel_path) if excel_path else None
        self.logs: List[str] = []

    @classmethod
    def find_matching_excel(cls, dxf_path: str, search_roots: Optional[List[Path]] = None) -> Optional[Path]:
        """DXF dosya adına göre en uygun Yükleme Cetveli Excel dosyasını arar."""
        dxf_p = Path(dxf_path)
        base_name = dxf_p.stem.lower()
        keywords = [
            part for part in base_name.replace('-', ' ').replace('_', ' ').split()
            if len(part) > 2 and part not in ['elektrik', 'dxf', 'dwg', 'projesi', 'mimari', 'temiz']
        ]

        roots = search_roots or [
            dxf_p.parent,
            dxf_p.parent.parent / "raporlar",
            Path(r"D:\autocad projesi\raporlar"),
        ]

        for sdir in roots:
            if not sdir.exists():
                continue
            for f in sdir.glob("*Yükleme*.xls*"):
                fname = f.stem.lower()
                if any(kw in fname for kw in keywords):
                    return f
        return None

    def parse(self) -> Tuple[Optional[MainPanelModel], Dict[str, SubPanelModel]]:
        """
        Dönüş: (main_panel, sub_panels_dict)
        """
        if not self.excel_path or not self.excel_path.exists():
            self.logs.append("Excel: Eşleşen Yükleme Cetveli bulunamadı.")
            return None, {}

        self.logs.append(f"Excel: Yükleme Cetveli açılıyor: {self.excel_path.name}")
        try:
            wb = xlrd.open_workbook(str(self.excel_path))
        except Exception as e:
            self.logs.append(f"Excel okuma hatası: {e}")
            return None, {}

        sub_panels: Dict[str, SubPanelModel] = {}
        main_panel = MainPanelModel()
        main_panel.sources = ["EXCEL"]

        # 1. 'RAPOR' sayfasını tara (Özet Pano Listesi)
        if 'RAPOR' in wb.sheet_names():
            self._parse_rapor_sheet(wb.sheet_by_name('RAPOR'), sub_panels, main_panel)

        # 2. 'Kolon Gerilim' sayfasını tara (Projedeki Gerilim Düşümleri ve Metrajlar)
        if 'Kolon Gerilim' in wb.sheet_names():
            self._parse_kolon_gerilim_sheet(wb.sheet_by_name('Kolon Gerilim'), sub_panels)

        # 3. Bireysel Pano Sayfalarını tara (DT-1..n, O-T, İŞ-T)
        for sname in wb.sheet_names():
            sname_clean = sname.replace('İ', 'I').replace('ş', 's').replace('Ş', 'S').upper()
            is_panel_sheet = (
                sname in sub_panels or
                sname.startswith('DT-') or
                sname in ('O-T', 'İŞ-T', 'IS-T', 'D-T') or
                'IS-T' in sname_clean or
                sname_clean.startswith('DT-')
            )
            if is_panel_sheet:
                sheet = wb.sheet_by_name(sname)
                circuits = self._parse_circuits_sheet(sname, sheet)
                if circuits:
                    canonical_name = sname
                    if 'IS-T' in sname_clean or 'İŞ-T' in sname:
                        canonical_name = 'İŞ-T'
                    if canonical_name in sub_panels:
                        sub_panels[canonical_name].circuits = circuits
                    else:
                        sub_panels[canonical_name] = SubPanelModel(
                            name=canonical_name,
                            circuits=circuits,
                            sources=["EXCEL"]
                        )

        self.logs.append(f"Excel: Toplam {len(sub_panels)} pano ve detaylı linyeleri okundu.")
        return main_panel, sub_panels

    def _parse_rapor_sheet(self, sheet, sub_panels: Dict[str, SubPanelModel], main_panel: MainPanelModel):
        """'RAPOR' sayfasındaki tüm tabloların özet değerlerini ayıklar."""
        for r in range(2, sheet.nrows):
            pname = str(sheet.cell_value(r, 1)).strip()
            if not pname or pname == "0.0":
                continue
            if pname == 'IS-T':
                pname = 'İŞ-T'

            try:
                p_inst = float(sheet.cell_value(r, 2))
                div_str = str(sheet.cell_value(r, 3)).strip()
                p_dem = float(sheet.cell_value(r, 4))
                breaker = str(sheet.cell_value(r, 5)).strip()
                rcd = str(sheet.cell_value(r, 8)).strip() if sheet.ncols > 8 else "4x25A 30mA"
                cable = str(sheet.cell_value(r, 10)).strip()
                length_val = sheet.cell_value(r, 11)
                length_m = float(length_val) if length_val and isinstance(length_val, (int, float)) else 10.0

                cross_sec = extract_cross_section_from_cable(cable)
                div_fac = round(p_dem / p_inst, 2) if p_inst > 0 else 1.0

                # Giriş sigortası anma akımını ayıkla
                m_brk = re.search(r'\d+\s*[xX*]\s*(\d+)', breaker)
                if m_brk:
                    brk_rating = float(m_brk.group(1))
                else:
                    m_num = re.search(r'(\d+)', breaker)
                    brk_rating = float(m_num.group(1)) if m_num else 20.0

                sub_panels[pname] = SubPanelModel(
                    name=pname,
                    installed_power_w=p_inst,
                    demand_power_w=p_dem,
                    diversity_factor=div_fac,
                    cable_spec=cable,
                    cable_cross_section_mm2=cross_sec,
                    feeder_length_m=length_m,
                    breaker_spec=breaker,
                    breaker_rating_a=brk_rating,
                    rcd_spec=rcd if rcd else "4x25A 30mA",
                    sources=["EXCEL"]
                )
            except Exception:
                pass

        if sub_panels:
            main_panel.total_dwelling_count = len([p for p in sub_panels if p.startswith('DT-') or p == 'D-T'])
            main_panel.installed_power_w = sum(sp.installed_power_w for sp in sub_panels.values() if sp.name != 'AT')
            from standards.eity_regulations import get_building_diversity_factor
            ks = get_building_diversity_factor(main_panel.total_dwelling_count)
            main_panel.diversity_factor = ks
            main_panel.demand_power_w = round(main_panel.installed_power_w * ks, 0)

    def _parse_kolon_gerilim_sheet(self, sheet, sub_panels: Dict[str, SubPanelModel]):
        """'Kolon Gerilim' sayfasındaki mühendislik gerilim düşümlerini ayıklar."""
        for r in range(sheet.nrows - 7):
            cell_tag = str(sheet.cell_value(r, 1)).strip()
            if cell_tag == 'TABLO ADI':
                pname = str(sheet.cell_value(r, 2)).strip()
                if pname == 'IS-T':
                    pname = 'İŞ-T'
                if not pname or pname == '0.0':
                    continue

                try:
                    # Metraj ve kablo
                    dist = float(sheet.cell_value(r, 10)) if isinstance(sheet.cell_value(r, 10), (int, float)) else 0.0
                    cable_raw = str(sheet.cell_value(r + 1, 2)).strip()
                    # Gerilim düşümleri
                    v_kolon = float(sheet.cell_value(r + 6, 2)) if isinstance(sheet.cell_value(r + 6, 2), (int, float)) else 0.0
                    v_linye = float(sheet.cell_value(r + 6, 13)) if isinstance(sheet.cell_value(r + 6, 13), (int, float)) else 0.0
                    v_total = round(v_kolon + v_linye, 3)

                    if pname in sub_panels:
                        sp = sub_panels[pname]
                        sp.project_vdrop_kolon_pct = v_kolon
                        sp.project_vdrop_linye_pct = v_linye
                        sp.project_vdrop_total_pct = v_total
                        if dist > 0:
                            sp.feeder_length_m = dist
                        if cable_raw:
                            sp.cable_spec = cable_raw
                            sp.cable_cross_section_mm2 = extract_cross_section_from_cable(cable_raw)
                except Exception:
                    pass

    def _parse_circuits_sheet(self, panel_name: str, sheet) -> List[CircuitModel]:
        """Pano sekmesindeki linye satırlarını ayıklar."""
        circuits = []
        for r in range(4, sheet.nrows):
            c_no_raw = str(sheet.cell_value(r, 7)).strip() if sheet.ncols > 7 else ""
            if not c_no_raw or c_no_raw == "TOPLAM":
                continue

            c_no = c_no_raw
            desc = str(sheet.cell_value(r, 12)).strip() if sheet.ncols > 12 else ""

            # Sortiler
            ayd = int(sheet.cell_value(r, 14)) if sheet.ncols > 14 and isinstance(sheet.cell_value(r, 14), (int, float)) else 0
            prz = int(sheet.cell_value(r, 15)) if sheet.ncols > 15 and isinstance(sheet.cell_value(r, 15), (int, float)) else 0
            mot = int(sheet.cell_value(r, 16)) if sheet.ncols > 16 and isinstance(sheet.cell_value(r, 16), (int, float)) else 0

            # Fazlar (R, S, T, RST)
            p_r = float(sheet.cell_value(r, 17)) if sheet.ncols > 17 and isinstance(sheet.cell_value(r, 17), (int, float)) else 0.0
            p_s = float(sheet.cell_value(r, 18)) if sheet.ncols > 18 and isinstance(sheet.cell_value(r, 18), (int, float)) else 0.0
            p_t = float(sheet.cell_value(r, 19)) if sheet.ncols > 19 and isinstance(sheet.cell_value(r, 19), (int, float)) else 0.0
            p_rst = float(sheet.cell_value(r, 20)) if sheet.ncols > 20 and isinstance(sheet.cell_value(r, 20), (int, float)) else 0.0

            if p_rst > 0:
                phase = "3P" # Üç Faz / Trifaze
                pw = p_rst
            elif p_r > 0:
                phase = "R"
                pw = p_r
            elif p_s > 0:
                phase = "S"
                pw = p_s
            elif p_t > 0:
                phase = "T"
                pw = p_t
            else:
                phase = "R"
                pw = 0.0
                if sheet.ncols > 21:
                    try:
                        pw = float(sheet.cell_value(r, 21))
                    except Exception:
                        pass

            cable = str(sheet.cell_value(r, 22)).strip() if sheet.ncols > 22 else "3x2,5NHXMH"
            conduit = float(sheet.cell_value(r, 23)) if sheet.ncols > 23 and isinstance(sheet.cell_value(r, 23), (int, float)) else 18.0

            # Sigorta anma akımı (örn: '3x32' -> 32A, '16' -> 16A, '10' -> 10A)
            raw_breaker = sheet.cell_value(r, 9) if sheet.ncols > 9 and sheet.cell_value(r, 9) else 16.0
            if isinstance(raw_breaker, (int, float)):
                breaker_a = float(raw_breaker)
            else:
                b_str = str(raw_breaker).strip()
                m_3x = re.search(r'\d+\s*[xX*]\s*(\d+)', b_str)
                if m_3x:
                    breaker_a = float(m_3x.group(1))
                else:
                    m_brk = re.search(r'(\d+)', b_str)
                    breaker_a = float(m_brk.group(1)) if m_brk else 16.0

            curve_str = str(sheet.cell_value(r, 10)).strip() if sheet.ncols > 10 else "C"
            curve = "B" if "B" in curve_str else "C"

            # Açıklama boşsa otomatik sınıflandır
            if not desc:
                if c_no.startswith("A"):
                    desc = "Aydınlatma"
                elif mot > 0 or "4x4" in cable or "4x16" in cable:
                    desc = "Motor / Cihaz"
                else:
                    desc = "Priz"

            circuits.append(CircuitModel(
                panel_name=panel_name,
                circuit_no=c_no,
                description=desc,
                light_points=ayd,
                socket_points=prz,
                motor_points=mot,
                power_w=pw,
                phase=phase,
                cable_spec=cable,
                conduit_dia_mm=conduit,
                breaker_rating_a=breaker_a,
                breaker_curve=curve
            ))

        return circuits
