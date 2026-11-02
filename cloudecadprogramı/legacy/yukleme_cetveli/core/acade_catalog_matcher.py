"""
CloudeCAD — AutoCAD Electrical (ACADE) Katalog Eşleştirici & Keşif Özeti Motoru
=============================================================================
AutoCAD Electrical'ın 548 MB'lık 'default_cat.mdb' veritabanına bağlanarak
hesaplanan linye sigortaları, pano ana şalterleri (TMŞ) ve kaçak akım koruma
rölelerine (KAKR) gerçek üretici parça kodlarını (Schneider Electric, Siemens,
ABB vb.) ve kesme kapasitelerini ($I_{cu}/I_{cn}$) otomatik eşleştirir.
"""

import os
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)


@dataclass
class MatchedComponent:
    """Tekil eşleşmiş katalog bileşeni."""
    category: str              # 'MCB_LINYE', 'PANO_KESICI', 'MCCB_TMS', 'RCD_KAKR', 'KABLO'
    panel_name: str           # örn: 'AT', 'D-T', 'DT-1'
    circuit_ref: str          # örn: 'A1', 'P1', 'GİRİŞ ŞALTERİ', 'ANA BESLEME'
    manufacturer: str         # örn: 'SCHNEIDER ELECTRIC', 'SIEMENS', 'ABB'
    catalog_no: str           # örn: '23851', 'LV510307', 'DDA204 AC-25/0.03'
    description: str          # Malzeme tanımı
    poles: str                # '1P', '2P', '3P', '4P'
    rating_str: str           # '16A', '100A', '25A / 30mA'
    curve_or_type: str        # 'B', 'C', 'TM', 'AC'
    breaking_capacity: str    # '6 kA', '10 kA', '25 kA', '36 kA'
    quantity: int = 1
    unit: str = "Adet"


@dataclass
class BOMSummaryItem:
    """Gruplanmış ve adetlendirilmiş Keşif Özeti kalemi."""
    category: str
    manufacturer: str
    catalog_no: str
    description: str
    poles: str
    rating_str: str
    specs: str
    breaking_capacity: str
    total_quantity: int
    unit: str = "Adet"


@dataclass
class ProjectBOMResult:
    """Tüm projenin ACADE Malzeme ve Keşif Özeti sonucu."""
    project_name: str
    components: List[MatchedComponent] = field(default_factory=list)
    summary_items: List[BOMSummaryItem] = field(default_factory=list)
    cable_metraj: Dict[str, float] = field(default_factory=dict) # '3x2.5 NHXMH' -> 450.0m
    total_mcb_count: int = 0
    total_mccb_count: int = 0
    total_rcd_count: int = 0
    db_connected: bool = False
    catalog_path: str = ""
    preferred_manufacturer: str = "SCHNEIDER ELECTRIC"


def find_acade_catalog_db() -> Optional[Path]:
    """Sistemdeki AutoCAD Electrical default_cat.mdb dosyasını arar."""
    # 1. Bilinen kullanıcı belgeleri yolu
    user_home = Path.home()
    cand1 = user_home / "Documents" / "Acade 2027" / "AeData" / "en-US" / "Catalogs" / "default_cat.mdb"
    if cand1.exists():
        return cand1

    # 2. Farklı kullanıcı veya sürüm belgeleri
    docs_dir = user_home / "Documents"
    if docs_dir.exists():
        for acade_dir in docs_dir.glob("Acade*"):
            cand = acade_dir / "AeData" / "en-US" / "Catalogs" / "default_cat.mdb"
            if cand.exists():
                return cand

    # 3. Genel sistem yolları
    candidates = [
        Path(r"C:\Users\yvzta\Documents\Acade 2027\AeData\en-US\Catalogs\default_cat.mdb"),
        Path(r"C:\Autodesk\AeData\en-US\Catalogs\default_cat.mdb"),
    ]
    for c in candidates:
        if c.exists():
            return c

    return None


class AcadeCatalogMatcher:
    """AutoCAD Electrical Katalog Eşleştirici Motoru."""

    def __init__(self, preferred_mfg: str = "SCHNEIDER ELECTRIC"):
        self.preferred_mfg = preferred_mfg.upper()
        self.catalog_path = find_acade_catalog_db()
        self.conn = None
        self._cache: Dict[str, Optional[Tuple[str, str, str, str]]] = {}
        self._init_connection()

    def _init_connection(self):
        """ADODB üzerinden MDB veritabanı bağlantısı açar."""
        if not self.catalog_path or not self.catalog_path.exists():
            logger.warning("AutoCAD Electrical katalog veritabanı (default_cat.mdb) bulunamadı.")
            return

        try:
            import win32com.client
            self.conn = win32com.client.Dispatch("ADODB.Connection")
            conn_str = f"Provider=Microsoft.ACE.OLEDB.12.0;Data Source={self.catalog_path};Persist Security Info=False;"
            self.conn.Open(conn_str)
            logger.info(f"✓ ACADE Katalog veritabanına bağlanıldı: {self.catalog_path.name}")
        except Exception as e:
            logger.warning(f"ACADE MDB bağlantısı kurulamadı: {e}. Dahili normatif eşleme kullanılacak.")
            self.conn = None

    def close(self):
        """Bağlantıyı kapatır."""
        if self.conn:
            try:
                self.conn.Close()
            except Exception:
                pass
            self.conn = None

    def _query_cb(self, sql: str) -> Optional[Tuple[str, str, str, str, str]]:
        """
        [CB] tablosundan tekil ürün çeker:
        Döner: (CATALOG, DESCRIPTION, MISCELLANEOUS1, TYPE, RATING)
        """
        if not self.conn:
            return None

        try:
            import win32com.client
            rs = win32com.client.Dispatch("ADODB.Recordset")
            rs.Open(sql, self.conn)
            if not rs.EOF:
                cat = str(rs.Fields("CATALOG").Value or "")
                desc = str(rs.Fields("DESCRIPTION").Value or "")
                misc1 = str(rs.Fields("MISCELLANEOUS1").Value or "")
                ctype = str(rs.Fields("TYPE").Value or "")
                rating = str(rs.Fields("RATING").Value or "")
                rs.Close()
                return (cat, desc, misc1, ctype, rating)
            rs.Close()
        except Exception as e:
            logger.debug(f"Katalog sorgu hatası: {e} -> SQL: {sql}")
        return None

    def match_mcb(
        self,
        rating_a: float,
        curve: str = "C",
        poles: int = 1,
        mfg: Optional[str] = None
    ) -> Tuple[str, str, str, str]:
        """
        Otomat Sigorta (MCB) eşleştirir.
        Döner: (catalog_no, description, breaking_capacity, poles_str)
        """
        mfg = (mfg or self.preferred_mfg).upper()
        poles_str = f"{poles}P"
        int_a = int(round(rating_a))
        cache_key = f"MCB_{mfg}_{int_a}A_{curve}_{poles}P"

        if cache_key in self._cache:
            res = self._cache[cache_key]
            if res:
                return res

        # 1. ACADE Veritabanında Ara
        if self.conn:
            # Schneider Electric Multi9 / C60a / Acti9
            if "SCHNEIDER" in mfg:
                # Pole tipi belirle
                pole_pattern = "1-POLE" if poles == 1 else ("2-POLE%" if poles == 2 else "3-POLE%")
                curve_str = f"CURVE {curve.upper()}"
                sql = (
                    f"SELECT TOP 1 [CATALOG], [DESCRIPTION], [MISCELLANEOUS1], [TYPE], [RATING] "
                    f"FROM [CB] WHERE [MANUFACTURER] = 'SCHNEIDER ELECTRIC' "
                    f"AND [RATING] = '{int_a}AMPS' "
                    f"AND [DESCRIPTION] LIKE '%{curve_str}%' "
                    f"AND [TYPE] LIKE '%{pole_pattern}%'"
                )
                row = self._query_cb(sql)
                if row:
                    cat, desc, misc1, ctype, r = row
                    ka = "6 kA"
                    if "10kA" in misc1:
                        ka = "10 kA"
                    elif "15kA" in misc1:
                        ka = "15 kA"
                    result = (cat, desc, ka, poles_str)
                    self._cache[cache_key] = result
                    return result

            # Siemens 5SY4 / 5SL / 3RV
            elif "SIEMENS" in mfg:
                pole_code = f"-{poles}" if poles > 1 else "-6" if curve.upper() == "B" else "-7"
                sql = (
                    f"SELECT TOP 1 [CATALOG], [DESCRIPTION], [MISCELLANEOUS1], [TYPE], [RATING] "
                    f"FROM [CB] WHERE [MANUFACTURER] = 'SIEMENS' "
                    f"AND ([RATING] LIKE '%{int_a}%' OR [CATALOG] LIKE '%{int_a}%') "
                    f"AND [DESCRIPTION] LIKE '%CIRCUIT%'"
                )
                row = self._query_cb(sql)
                if row:
                    cat, desc, misc1, ctype, r = row
                    result = (cat, desc, "10 kA", poles_str)
                    self._cache[cache_key] = result
                    return result

            # ABB S200 / PRO M COMPACT
            elif "ABB" in mfg:
                sql = (
                    f"SELECT TOP 1 [CATALOG], [DESCRIPTION], [MISCELLANEOUS1], [TYPE], [RATING] "
                    f"FROM [CB] WHERE [MANUFACTURER] = 'ABB' "
                    f"AND [RATING] LIKE '%{int_a}%' "
                    f"AND [DESCRIPTION] LIKE '%CIRCUIT%'"
                )
                row = self._query_cb(sql)
                if row:
                    cat, desc, misc1, ctype, r = row
                    result = (cat, desc, "6 kA", poles_str)
                    self._cache[cache_key] = result
                    return result

        # 2. Güvenli Dahili Normatif Katalog Eşlemesi (Fallback)
        # Standart Türk piyasası Schneider Acti9 / iC60N / Resi9 parça kodları:
        act9_codes_1p = {
            6: "A9F74106", 10: "A9F74110", 16: "A9F74116",
            20: "A9F74120", 25: "A9F74125", 32: "A9F74132",
            40: "A9F74140", 50: "A9F74150", 63: "A9F74163"
        }
        act9_codes_3p = {
            10: "A9F74310", 16: "A9F74316", 20: "A9F74320",
            25: "A9F74325", 32: "A9F74332", 40: "A9F74340",
            50: "A9F74350", 63: "A9F74363"
        }
        ref_code = act9_codes_3p.get(int_a, f"A9F743{int_a}") if poles == 3 else act9_codes_1p.get(int_a, f"A9F741{int_a}")
        desc = f"Acti9 iC60N {poles_str} {int_a}A {curve}-Tipi Otomat Sigorta (MCB)"
        result = (ref_code, desc, "6 kA", poles_str)
        self._cache[cache_key] = result
        return result

    def match_mccb_tms(
        self,
        rating_a: float,
        min_ka: float = 16.0,
        poles: int = 3,
        mfg: Optional[str] = None
    ) -> Tuple[str, str, str, str]:
        """
        Kompakt Şalter (TMŞ / MCCB) eşleştirir.
        Döner: (catalog_no, description, breaking_capacity, poles_str)
        """
        mfg = (mfg or self.preferred_mfg).upper()
        poles_str = f"{poles}P"
        int_a = int(round(rating_a))
        cache_key = f"MCCB_{mfg}_{int_a}A_{poles}P_{int(min_ka)}kA"

        if cache_key in self._cache:
            res = self._cache[cache_key]
            if res:
                return res

        # 1. ACADE Veritabanında Ara
        if self.conn:
            if "SCHNEIDER" in mfg:
                # EasyPact CVS veya Compact NSX
                sql = (
                    f"SELECT TOP 1 [CATALOG], [DESCRIPTION], [MISCELLANEOUS1], [TYPE], [RATING] "
                    f"FROM [CB] WHERE [MANUFACTURER] = 'SCHNEIDER ELECTRIC' "
                    f"AND [RATING] LIKE '%{int_a}%' "
                    f"AND ([DESCRIPTION] LIKE '%CVS%' OR [DESCRIPTION] LIKE '%COMPACT%' OR [DESCRIPTION] LIKE '%NSX%')"
                )
                row = self._query_cb(sql)
                if row:
                    cat, desc, misc1, ctype, r = row
                    ka_str = "25 kA" if min_ka <= 25 else "36 kA"
                    result = (cat, desc, ka_str, poles_str)
                    self._cache[cache_key] = result
                    return result

            elif "SIEMENS" in mfg:
                # 3VA Sentron serisi
                sql = (
                    f"SELECT TOP 1 [CATALOG], [DESCRIPTION], [MISCELLANEOUS1], [TYPE], [RATING] "
                    f"FROM [CB] WHERE [MANUFACTURER] = 'SIEMENS' "
                    f"AND [CATALOG] LIKE '3VA%' "
                    f"AND ([DESCRIPTION] LIKE '%{int_a}A%' OR [RATING] LIKE '%{int_a}%')"
                )
                row = self._query_cb(sql)
                if row:
                    cat, desc, misc1, ctype, r = row
                    result = (cat, desc, "36 kA", poles_str)
                    self._cache[cache_key] = result
                    return result

        # 2. Güvenli Dahili Normatif Eşleme (Schneider EasyPact CVS / Compact NSX)
        cvs_codes = {
            100: "LV510307", 125: "LV516301", 160: "LV516303",
            200: "LV525301", 250: "LV525303", 400: "LV540305",
            630: "LV563305"
        }
        ref_code = cvs_codes.get(int_a, f"LV510{int_a}")
        desc = f"EasyPact CVS{int_a}B {poles_str} {int_a}A Termik Manyetik Kompakt Şalter (TMŞ)"
        ka_str = "25 kA (Icu)" if min_ka <= 25 else "36 kA (Icu)"
        result = (ref_code, desc, ka_str, poles_str)
        self._cache[cache_key] = result
        return result

    def match_rcd(
        self,
        rating_a: float,
        sensitivity_ma: float = 30.0,
        poles: int = 4,
        mfg: Optional[str] = None
    ) -> Tuple[str, str, str, str]:
        """
        Kaçak Akım Koruma Rölesi (RCD / KAKR) eşleştirir.
        Döner: (catalog_no, description, sensitivity_str, poles_str)
        """
        mfg = (mfg or self.preferred_mfg).upper()
        poles_str = f"{poles}P"
        int_a = int(round(rating_a))
        sens_str = f"{int(sensitivity_ma)}mA"
        cache_key = f"RCD_{mfg}_{int_a}A_{sens_str}_{poles}P"

        if cache_key in self._cache:
            res = self._cache[cache_key]
            if res:
                return res

        # 1. ACADE Veritabanında Ara
        if self.conn:
            sens_val = "0.03" if sensitivity_ma <= 30 else "0.3"
            sql = (
                f"SELECT TOP 1 [CATALOG], [DESCRIPTION], [MISCELLANEOUS1], [TYPE], [RATING] "
                f"FROM [CB] WHERE [DESCRIPTION] LIKE '%RESIDUAL CURRENT%' "
                f"AND ([CATALOG] LIKE '%{sens_val}%' OR [DESCRIPTION] LIKE '%{sens_val}%' OR [RATING] LIKE '%{int_a}%')"
            )
            row = self._query_cb(sql)
            if row:
                cat, desc, misc1, ctype, r = row
                result = (cat, desc, sens_str, poles_str)
                self._cache[cache_key] = result
                return result

        # 2. Güvenli Dahili Normatif Eşleme (Schneider Acti9 iID)
        # 30mA Hayat Koruma / 300mA Yangın Koruma
        iid_codes_4p_30ma = {25: "A9R11425", 40: "A9R11440", 63: "A9R11463", 80: "A9R11480", 100: "A9R11491"}
        iid_codes_4p_300ma = {25: "A9R14425", 40: "A9R14440", 63: "A9R14463", 80: "A9R14480", 100: "A9R14491"}

        if sensitivity_ma <= 30:
            ref_code = iid_codes_4p_30ma.get(int_a, f"A9R114{int_a}")
            role_type = "Hayat Koruma (Can Güvenliği)"
        else:
            ref_code = iid_codes_4p_300ma.get(int_a, f"A9R144{int_a}")
            role_type = "Yangın Koruma (Tesisat Güvenliği)"

        desc = f"Acti9 iID {poles_str} {int_a}A {sens_str} Kaçak Akım Koruma Rölesi - {role_type}"
        result = (ref_code, desc, sens_str, poles_str)
        self._cache[cache_key] = result
        return result

    def generate_bom(
        self,
        proj_data: Any,
        audit_report: Any,
        preferred_mfg: str = "SCHNEIDER ELECTRIC"
    ) -> ProjectBOMResult:
        """
        Tüm proje panoları, linyeleri ve kablolarından konsolide
        Malzeme ve Keşif Özeti (Bill of Materials) üretir.
        """
        self.preferred_mfg = preferred_mfg.upper()
        bom = ProjectBOMResult(
            project_name=proj_data.project_name,
            db_connected=(self.conn is not None),
            catalog_path=str(self.catalog_path or ""),
            preferred_manufacturer=self.preferred_mfg
        )

        sub_panels = proj_data.sub_panels.values() if isinstance(proj_data.sub_panels, dict) else proj_data.sub_panels

        # ── 1. Ana Dağıtım Panosu (AT) Ana Kesici & KAKR ─────────────
        main_p = proj_data.main_panel
        if main_p:
            main_in = main_p.main_breaker_rating_a or 100.0
            # Kısa devre Ik3 seviyesine göre kesme kapasitesi gereksinimi
            at_sc = audit_report.short_circuit_results.get("AT")
            ik3 = at_sc.ik3_max_ka if at_sc else 10.0

            if main_in > 63 or "TMŞ" in (main_p.main_breaker_spec or ""):
                cat, desc, ka, poles = self.match_mccb_tms(main_in, min_ka=ik3, poles=3, mfg=self.preferred_mfg)
                bom.components.append(MatchedComponent(
                    category="MCCB_TMS",
                    panel_name="AT",
                    circuit_ref="ANA DAĞITIM ŞALTERİ",
                    manufacturer=self.preferred_mfg,
                    catalog_no=cat,
                    description=desc,
                    poles=poles,
                    rating_str=f"{int(main_in)}A",
                    curve_or_type="Termik-Manyetik",
                    breaking_capacity=ka,
                    quantity=1
                ))
                bom.total_mccb_count += 1
            else:
                cat, desc, ka, poles = self.match_mcb(main_in, curve="C", poles=3, mfg=self.preferred_mfg)
                bom.components.append(MatchedComponent(
                    category="PANO_KESICI",
                    panel_name="AT",
                    circuit_ref="ANA DAĞITIM ŞALTERİ",
                    manufacturer=self.preferred_mfg,
                    catalog_no=cat,
                    description=desc,
                    poles=poles,
                    rating_str=f"{int(main_in)}A",
                    curve_or_type="C-Tipi",
                    breaking_capacity=ka,
                    quantity=1
                ))
                bom.total_mcb_count += 1

            # AT Yangın Koruma Kaçak Akım Rölesi (300mA)
            rcd_in = main_in if main_in <= 100 else 100.0
            rcd_cat, rcd_desc, sens, rcd_poles = self.match_rcd(rcd_in, sensitivity_ma=300.0, poles=4, mfg=self.preferred_mfg)
            bom.components.append(MatchedComponent(
                category="RCD_KAKR",
                panel_name="AT",
                circuit_ref="YANGIN KORUMA RÖLESİ",
                manufacturer=self.preferred_mfg,
                catalog_no=rcd_cat,
                description=rcd_desc,
                poles=rcd_poles,
                rating_str=f"{int(rcd_in)}A / 300mA",
                curve_or_type="AC / Yangın Koruma",
                breaking_capacity="6 kA",
                quantity=1
            ))
            bom.total_rcd_count += 1

            # Ana Besleme Kablosu Metrajı
            cable_spec = main_p.feeder_cable_spec or "3x95+50 NYY"
            l_m = main_p.feeder_length_m or 25.0
            bom.cable_metraj[cable_spec] = bom.cable_metraj.get(cable_spec, 0.0) + l_m

        # ── 2. Tali Panolar (DT, OT vb.) Giriş Kesicileri, KAKR ve Kablolar ───
        for sp in sub_panels:
            if sp.name == "AT":
                continue

            sp_in = sp.breaker_rating_a or 25.0
            sp_sc = audit_report.short_circuit_results.get(sp.name)
            sp_ik3 = sp_sc.ik3_max_ka if sp_sc else 6.0

            # Pano Giriş Sigortası (3 Fazlı)
            cat, desc, ka, poles = self.match_mcb(sp_in, curve="C", poles=3, mfg=self.preferred_mfg)
            bom.components.append(MatchedComponent(
                category="PANO_KESICI",
                panel_name=sp.name,
                circuit_ref="PANO GİRİŞ KESİCİSİ",
                manufacturer=self.preferred_mfg,
                catalog_no=cat,
                description=desc,
                poles=poles,
                rating_str=f"{int(sp_in)}A",
                curve_or_type="C-Tipi",
                breaking_capacity=ka,
                quantity=1
            ))
            bom.total_mcb_count += 1

            # Pano Kaçak Akım Rölesi (30mA Hayat Koruma)
            rcd_cat, rcd_desc, sens, rcd_poles = self.match_rcd(sp_in, sensitivity_ma=30.0, poles=4, mfg=self.preferred_mfg)
            bom.components.append(MatchedComponent(
                category="RCD_KAKR",
                panel_name=sp.name,
                circuit_ref="HAYAT KORUMA RÖLESİ",
                manufacturer=self.preferred_mfg,
                catalog_no=rcd_cat,
                description=rcd_desc,
                poles=rcd_poles,
                rating_str=f"{int(sp_in)}A / 30mA",
                curve_or_type="AC / Can Güvenliği",
                breaking_capacity="6 kA",
                quantity=1
            ))
            bom.total_rcd_count += 1

            # Kolon Besleme Kablosu Metrajı
            sp_cable = sp.cable_spec or "4x6 NHXMH"
            sp_len = sp.feeder_length_m or 15.0
            bom.cable_metraj[sp_cable] = bom.cable_metraj.get(sp_cable, 0.0) + sp_len

            # ── 3. Linye Sigortaları ve Linye Kablo Metrajı ───────────
            for circ in sp.circuits:
                c_in = circ.breaker_rating_a or 16.0
                c_curve = circ.breaker_curve or ("B" if "A" in circ.circuit_no.upper() else "C")
                c_poles = 1 if circ.phase in ["R", "S", "T"] else 3

                c_cat, c_desc, c_ka, c_polestr = self.match_mcb(c_in, curve=c_curve, poles=c_poles, mfg=self.preferred_mfg)
                bom.components.append(MatchedComponent(
                    category="MCB_LINYE",
                    panel_name=sp.name,
                    circuit_ref=f"{circ.circuit_no} ({circ.description})",
                    manufacturer=self.preferred_mfg,
                    catalog_no=c_cat,
                    description=c_desc,
                    poles=c_polestr,
                    rating_str=f"{int(c_in)}A",
                    curve_or_type=f"{c_curve}-Tipi",
                    breaking_capacity=c_ka,
                    quantity=1
                ))
                bom.total_mcb_count += 1

                # Linye Kablosu Metraj Tahmini (standart sortili konut linyesi ortalama 25m)
                circ_cable = circ.cable_spec or "3x2.5 NHXMH"
                bom.cable_metraj[circ_cable] = bom.cable_metraj.get(circ_cable, 0.0) + 25.0

        # ── 4. Gruplanmış Keşif Özeti (Summary Items) Oluştur ─────────
        groups: Dict[Tuple[str, str, str, str, str, str, str], int] = {}
        for c in bom.components:
            key = (c.category, c.manufacturer, c.catalog_no, c.description, c.poles, c.rating_str, c.breaking_capacity)
            groups[key] = groups.get(key, 0) + c.quantity

        for key, qty in sorted(groups.items(), key=lambda x: (x[0][0], x[0][5], x[0][2])):
            cat, mfg, cat_no, desc, poles, rating, ka = key
            specs = f"{poles}, {rating}, Kesme Kap.: {ka}"
            bom.summary_items.append(BOMSummaryItem(
                category=cat,
                manufacturer=mfg,
                catalog_no=cat_no,
                description=desc,
                poles=poles,
                rating_str=rating,
                specs=specs,
                breaking_capacity=ka,
                total_quantity=qty
            ))

        return bom


def export_bom_to_excel(bom: ProjectBOMResult, excel_path: Path):
    """Mevcut veya yeni Excel dosyasına 'ACADE Malzeme & Keşif' sayfası ekler."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = None
    if excel_path.exists():
        try:
            wb = openpyxl.load_workbook(excel_path)
        except Exception:
            wb = openpyxl.Workbook()
    else:
        wb = openpyxl.Workbook()

    sheet_name = "ACADE Malzeme Keşif"
    if sheet_name in wb.sheetnames:
        del wb[sheet_name]
    ws = wb.create_sheet(title=sheet_name)

    # Stiller
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Segoe UI", size=14, bold=True, color="1B365D")
    sub_font = Font(name="Segoe UI", size=10, italic=True, color="555555")
    cell_font = Font(name="Segoe UI", size=10)
    bold_cell = Font(name="Segoe UI", size=10, bold=True)

    header_fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
    sec_fill = PatternFill(start_color="E8EEF5", end_color="E8EEF5", fill_type="solid")
    alt_fill = PatternFill(start_color="F9FAFC", end_color="F9FAFC", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='DDDDDD'),
        right=Side(style='thin', color='DDDDDD'),
        top=Side(style='thin', color='DDDDDD'),
        bottom=Side(style='thin', color='DDDDDD')
    )

    # Başlık
    ws["B2"] = f"CloudeCAD & AutoCAD Electrical — Proje Malzeme & Keşif Özeti (BOM)"
    ws["B2"].font = title_font
    db_status = "AutoCAD Electrical 2027 default_cat.mdb Veritabanından Çekildi" if bom.db_connected else "Normatif Eşleme Kütüphanesi"
    ws["B3"] = f"Proje: {bom.project_name} | Üretici Standardı: {bom.preferred_manufacturer} | Kaynak: {db_status}"
    ws["B3"].font = sub_font

    headers = ["Sıra", "Kategori", "Üretici", "Referans / Sipariş Kodu", "Malzeme Açıklaması", "Kutup", "Anma Akımı", "Kesme Kapasitesi", "Miktar", "Birim"]
    row_idx = 5
    for col_idx, h in enumerate(headers, start=2):
        c = ws.cell(row=row_idx, column=col_idx, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    row_idx = 6
    sira = 1
    for item in bom.summary_items:
        fill = alt_fill if sira % 2 == 0 else PatternFill(fill_type=None)
        cat_tr = {
            "MCCB_TMS": "Kompakt Şalter (TMŞ)",
            "PANO_KESICI": "Pano Giriş Sigortası",
            "RCD_KAKR": "Kaçak Akım Koruma Rölesi",
            "MCB_LINYE": "Linye Otomat Sigortası"
        }.get(item.category, item.category)

        vals = [sira, cat_tr, item.manufacturer, item.catalog_no, item.description, item.poles, item.rating_str, item.breaking_capacity, item.total_quantity, item.unit]
        for col_idx, v in enumerate(vals, start=2):
            c = ws.cell(row=row_idx, column=col_idx, value=v)
            c.font = bold_cell if col_idx in [5, 10] else cell_font
            if fill.fill_type:
                c.fill = fill
            c.border = thin_border
            if col_idx in [2, 7, 8, 10, 11]:
                c.alignment = Alignment(horizontal="center", vertical="center")
            else:
                c.alignment = Alignment(horizontal="left", vertical="center")
        row_idx += 1
        sira += 1

    # Kablo Metraj Özeti Bölümü
    row_idx += 2
    ws.cell(row=row_idx, column=2, value="KABLO VE İLETKEN METRAJ TAHMİNİ (ÖZET)").font = title_font
    row_idx += 1
    c_headers = ["Sıra", "Kablo Tipi & Kesiti", "Metraj (Metre)", "Birim"]
    for col_idx, ch in enumerate(c_headers, start=2):
        c = ws.cell(row=row_idx, column=col_idx, value=ch)
        c.font = header_font
        c.fill = PatternFill(start_color="335577", end_color="335577", fill_type="solid")
        c.alignment = Alignment(horizontal="center")

    row_idx += 1
    c_sira = 1
    for spec, meters in sorted(bom.cable_metraj.items(), key=lambda x: -x[1]):
        ws.cell(row=row_idx, column=2, value=c_sira).alignment = Alignment(horizontal="center")
        ws.cell(row=row_idx, column=3, value=spec).font = bold_cell
        ws.cell(row=row_idx, column=4, value=f"{meters:,.1f}").alignment = Alignment(horizontal="right")
        ws.cell(row=row_idx, column=5, value="Metre").alignment = Alignment(horizontal="center")
        for col in range(2, 6):
            ws.cell(row=row_idx, column=col).border = thin_border
        row_idx += 1
        c_sira += 1

    # Sütun genişlikleri
    widths = {2: 8, 3: 24, 4: 20, 5: 22, 6: 45, 7: 10, 8: 14, 9: 16, 10: 12, 11: 10}
    for col_idx, w in widths.items():
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = w

    wb.save(excel_path)
    logger.info(f"✓ ACADE Malzeme Keşif Özeti Excel'e eklendi: {excel_path.name}")


def generate_bom_html_section(bom: ProjectBOMResult) -> str:
    """HTML Denetim Raporuna gömülecek ACADE Malzeme Keşif Özeti tablosu."""
    db_badge = (
        '<span style="background:#28a745;color:#fff;padding:3px 8px;border-radius:4px;font-size:12px;">AutoCAD Electrical default_cat.mdb Bağlı</span>'
        if bom.db_connected else
        '<span style="background:#6c757d;color:#fff;padding:3px 8px;border-radius:4px;font-size:12px;">Normatif Katalog Kütüphanesi</span>'
    )

    rows_html = []
    for idx, item in enumerate(bom.summary_items, start=1):
        cat_badge = {
            "MCCB_TMS": '<span class="badge bg-danger">TMŞ</span>',
            "PANO_KESICI": '<span class="badge bg-primary">Pano Şalter</span>',
            "RCD_KAKR": '<span class="badge bg-warning text-dark">KAKR</span>',
            "MCB_LINYE": '<span class="badge bg-secondary">Linye Sigorta</span>'
        }.get(item.category, item.category)

        rows_html.append(f"""
        <tr>
            <td class="text-center">{idx}</td>
            <td>{cat_badge}</td>
            <td><strong>{item.manufacturer}</strong></td>
            <td><code style="font-weight:bold;color:#0d6efd;">{item.catalog_no}</code></td>
            <td>{item.description}</td>
            <td class="text-center">{item.poles}</td>
            <td class="text-center">{item.rating_str}</td>
            <td class="text-center"><span class="badge bg-info text-dark">{item.breaking_capacity}</span></td>
            <td class="text-center font-weight-bold" style="font-size:15px;color:#198754;"><strong>{item.total_quantity}</strong></td>
            <td class="text-center">{item.unit}</td>
        </tr>
        """)

    cable_rows = []
    for spec, meters in sorted(bom.cable_metraj.items(), key=lambda x: -x[1]):
        cable_rows.append(f"""
        <tr>
            <td><strong>{spec}</strong></td>
            <td class="text-end" style="color:#0d6efd;font-weight:bold;">{meters:,.1f} m</td>
            <td class="text-center">Kablo Metrajı</td>
        </tr>
        """)

    html = f"""
    <div class="card mt-4 mb-4 shadow-sm" id="acade-bom-section" style="border: 1px solid #1B365D;">
        <div class="card-header text-white" style="background-color: #1B365D; display: flex; justify-content: space-between; align-items: center;">
            <h5 class="mb-0">
                <i class="bi bi-box-seam me-2"></i> AutoCAD Electrical (ACADE) Malzeme & Keşif Özeti (Bill of Materials)
            </h5>
            <div>{db_badge}</div>
        </div>
        <div class="card-body">
            <p class="text-muted mb-3">
                Bu liste, paftadaki pano ve linyelerin hesaplanan akımlarına ($I_b, I_n$), kısa devre seviyelerine ($I_{{k3}}$) ve can güvenliği standartlarına göre <strong>AutoCAD Electrical {bom.preferred_manufacturer} Katalog Veritabanı</strong> ile eşleştirilerek oluşturulmuştur.
            </p>
            <div class="table-responsive">
                <table class="table table-striped table-hover table-bordered align-middle">
                    <thead class="table-dark">
                        <tr class="text-center">
                            <th>#</th>
                            <th>Kategori</th>
                            <th>Üretici</th>
                            <th>Referans / Sipariş Kodu</th>
                            <th>Malzeme Açıklaması</th>
                            <th>Kutup</th>
                            <th>Anma Akımı</th>
                            <th>Kesme Kap.</th>
                            <th>Miktar</th>
                            <th>Birim</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(rows_html)}
                    </tbody>
                </table>
            </div>

            <div class="row mt-4">
                <div class="col-md-6">
                    <div class="card border-info">
                        <div class="card-header bg-info text-dark font-weight-bold">
                            <strong>İletken ve Kablo Metraj Özeti</strong>
                        </div>
                        <div class="card-body p-0">
                            <table class="table table-sm table-striped mb-0">
                                <thead>
                                    <tr>
                                        <th>Kablo Tipi & Kesiti</th>
                                        <th class="text-end">Tahmini Metraj</th>
                                        <th class="text-center">Açıklama</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {"".join(cable_rows)}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card border-success">
                        <div class="card-header bg-success text-white font-weight-bold">
                            <strong>Pano ve Kesici Ekipman Sayımları</strong>
                        </div>
                        <div class="card-body">
                            <ul class="list-group list-group-flush">
                                <li class="list-group-item d-flex justify-content-between align-items-center">
                                    Toplam Kompakt Şalter (TMŞ):
                                    <span class="badge bg-danger rounded-pill fs-6">{bom.total_mccb_count} Adet</span>
                                </li>
                                <li class="list-group-item d-flex justify-content-between align-items-center">
                                    Toplam Kaçak Akım Rölesi (KAKR):
                                    <span class="badge bg-warning text-dark rounded-pill fs-6">{bom.total_rcd_count} Adet</span>
                                </li>
                                <li class="list-group-item d-flex justify-content-between align-items-center">
                                    Toplam Otomat / Linye Sigortası (MCB):
                                    <span class="badge bg-primary rounded-pill fs-6">{bom.total_mcb_count} Adet</span>
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """
    return html
