"""
CloudeCAD — Zayıf Akım CAD ve Katman Ayrıştırıcı (WeakCurrentCadParser)
======================================================================
AutoCAD DXF dosyasından yangın algılama, telefon/data, TV/uydu ve
interkom katmanlarını, bloklarını ve kolon şeması metinlerini ayıklar.
"""

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import ezdxf
from config import WEAK_CURRENT_LAYERS, WEAK_CURRENT_BLOCKS
from core.models import (
    WeakCurrentBlockItem, FireAlarmSystemModel, TelecomSystemModel,
    SmatvSystemModel, IntercomSystemModel, WeakCurrentAuditReport
)


class WeakCurrentCadParser:
    """Zayıf akım çizim ve şema ayrıştırıcısı."""

    def __init__(self, dxf_path: str):
        self.dxf_path = Path(dxf_path)
        self.doc: Optional[ezdxf.document.Drawing] = None
        self.logs: List[str] = []
        self.found_layers: List[str] = []
        self.block_counts: Dict[str, Counter] = defaultdict(Counter) # {system: Counter(block_names)}
        self.insert_counts: Counter = Counter()
        self.poly_layer_lengths_m: Dict[str, float] = {}
        self.stream_ordered_texts: List[str] = []
        self.all_layers_set: set = set()
        self.plan_titles: List[str] = []
        self.riser_titles: List[str] = []
        self.raw_texts: List[str] = []
        self.fe180_found: bool = False
        self.scada_found: bool = False
        self.lhd_length_m: float = 0.0
        self.beam_flame_cnt: int = 0
        self.ex_proof_cnt: int = 0
        self.pava_cnt: int = 0
        self.cctv_cnt: int = 0
        self.fiber_ring_cnt: int = 0
        self.detector_coords: List[Tuple[float, float, str]] = []
        self.room_labels: List[Tuple[float, float, str]] = []

    def _fast_stream_dxf(self) -> None:
        """Büyük Metro DXF dosyalarını milisaniyeler içinde stream ederek metinleri, blokları ve kablo boylarını çıkarır."""
        layer_lens_mm: Dict[str, float] = {}
        with open(str(self.dxf_path), 'r', encoding='utf-8', errors='ignore') as f:
            cur_type = ''
            cur_layer = '0'
            last_x = None
            pts = []
            x1 = y1 = x2 = y2 = 0.0

            for line in f:
                s = line.strip()
                if not s:
                    continue
                c = s
                try:
                    v = next(f).strip()
                except StopIteration:
                    break

                if c == '0':
                    if cur_type == 'LWPOLYLINE' and len(pts) >= 2:
                        plen = 0.0
                        for i in range(len(pts) - 1):
                            plen += ((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** 0.5
                        layer_lens_mm[cur_layer] = layer_lens_mm.get(cur_layer, 0.0) + plen
                    elif cur_type == 'LINE':
                        llen = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                        layer_lens_mm[cur_layer] = layer_lens_mm.get(cur_layer, 0.0) + llen

                    cur_type = v
                    cur_layer = '0'
                    pts = []
                    last_x = None
                    x1 = y1 = x2 = y2 = 0.0
                    continue

                if c == '8':
                    cur_layer = v
                    self.all_layers_set.add(v)
                    continue

                if cur_type == 'INSERT' and c == '2':
                    self.insert_counts[v] += 1
                elif cur_type in ('TEXT', 'MTEXT', 'ATTRIB') and c in ('1', '3') and v:
                    try:
                        from common.universal_cad_reader import clean_turkish_text
                        clean = clean_turkish_text(v)
                    except Exception:
                        clean = re.sub(r'\\U\+0130', 'İ', v, flags=re.I)
                        clean = re.sub(r'\\U\+015E', 'Ş', clean, flags=re.I)
                        clean = re.sub(r'\\U\+011E', 'Ğ', clean, flags=re.I)
                        clean = re.sub(r'\\U\+[0-9A-Fa-f]{4}', '', clean).replace('\\P', ' ').strip()
                    if clean:
                        self.stream_ordered_texts.append(clean)
                        if len(self.raw_texts) < 500:
                            self.raw_texts.append(clean)
                elif cur_type == 'LWPOLYLINE':
                    lu = cur_layer.upper()
                    if any(k in lu for k in ['FIRE', 'YANGIN', 'TEL', 'DATA', 'CCTV', 'ANONS', 'PAVA', 'CLOCK', 'SAAT', 'TELS', 'TETRA', 'SCADA', 'PIS', 'LHD']):
                        if c == '10':
                            try:
                                last_x = float(v)
                            except ValueError:
                                last_x = None
                        elif c == '20' and last_x is not None:
                            try:
                                pts.append((last_x, float(v)))
                            except ValueError:
                                pass
                            last_x = None
                elif cur_type == 'LINE':
                    lu = cur_layer.upper()
                    if any(k in lu for k in ['FIRE', 'YANGIN', 'TEL', 'DATA', 'CCTV', 'ANONS', 'PAVA', 'CLOCK', 'SAAT', 'TELS', 'TETRA', 'SCADA', 'PIS', 'LHD']):
                        try:
                            if c == '10':
                                x1 = float(v)
                            elif c == '20':
                                y1 = float(v)
                            elif c == '11':
                                x2 = float(v)
                            elif c == '21':
                                y2 = float(v)
                        except ValueError:
                            pass

        self.poly_layer_lengths_m = {
            k: round(val / 1000.0, 1)
            for k, val in sorted(layer_lens_mm.items(), key=lambda x: -x[1])
            if val >= 500.0
        }

    @staticmethod
    def _classify_metro_weak_current_role(fn_u: str, texts: List[str]) -> Tuple[str, str, str, str, str, str]:
        """
        Dosya adı ve içerik metinlerinden:
        (station_code, sheet_role, discipline_code, discipline_name, floor_code, floor_name) döner.
        """
        # 1. İstasyon Kodu
        m_st = re.search(r'M(\d{2})[-_]?S[-_]?(\d{2})', fn_u)
        station_code = f"M{m_st.group(1)}-S{m_st.group(2)}" if m_st else "M09-S00"

        # 2. Kat Kodu ve Adı
        floor_map = {
            "BT0-00": "PERON ALTI KATI (-48.55 Kotu)",
            "BT0-01": "PERON KATI",
            "CT0-00": "PERON VE HAT ALTI KATI",
            "CT0-01": "PERON KATI",
            "CT0-02": "ARA KAT / KONKURS KATI",
            "CT0-03": "BİLET HOLÜ / TURNİKE KATI",
            "CT0-04": "BİLET HOLÜ / GİRİŞ KATI",
            "CT0-06": "GİRİŞ / CADDE KATI",
            "CT0-10": "BİLET HOLÜ / GİRİŞ BAĞLANTI KATI",
            "CT0-2A": "ASMA KAT",
            "CT0-2B": "TEKNİK KAT 1-2 (Trafo & SER/CER Odaları)",
            "CT0-2C": "ÜST TABLİYE KATI",
            "CT0-2D": "TEKNİK KAT / ŞAFT & KABLO GALERİSİ KATI",
            "000-00": "TÜNEL HAT BOYU GÜZERGAHI",
            "000-10": "DIŞ SAHA / ÇEVRE VAZİYET PLANI",
            "000-99": "İSTASYON GENEL / TOPLU PLAN",
        }
        floor_code = "000-99"
        floor_name = "İSTASYON GENEL / TOPLU PLAN"
        for fc, fnm in floor_map.items():
            if fc in fn_u:
                floor_code = fc
                floor_name = fnm
                break

        # 3. Disiplin ve Alt Rol
        disc_map = {
            "AX-02": ("METRO_YANGIN_ALGILAMA", "Yangın Algılama ve İhbar Tesisatı Planı"),
            "TL-02": ("METRO_VERI_ILETISIM_LAN", "Veri İletişim, LAN & Fiber Optik Altyapı Planı"),
            "TL-03": ("METRO_TELEFON_INTERKOM", "Telefon, Acil SOS & Dahili Haberleşme Planı"),
            "TL-04": ("METRO_TETRA_TELSIZ", "Telsiz / TETRA Haberleşme & Anten Planı"),
            "TL-05": ("METRO_ACIL_ANONS_PAVA", "Acil Anons ve Sesli Tahliye (PA/VA) Planı"),
            "TL-06": ("METRO_CCTV_KAMERA", "Kapalı Devre Televizyon / CCTV Kamera Sistemi Planı"),
            "TL-07": ("METRO_SAAT_SISTEMI", "Saat Sistemi (Master Clock & Tali Saatler) Planı"),
            "TL-08": ("METRO_KARTLI_GECIS_ACS", "Kartlı Geçiş, Kapı Güvenlik (ACS) Planı"),
            "TL-09": ("METRO_SCADA_OTOMASYON", "SCADA, PLC, Otomasyon & Yangın Senaryo Planı"),
            "TL-10": ("METRO_YOLCU_BILGILENDIRME_PIS", "Yolcu Bilgilendirme Sistemi (PIS) Planı"),
            "TL-11": ("METRO_SISTEM_ODASI_RACK", "Sistem Odası (SER/CER) Rack Kabinet Yerleşim Planı"),
        }
        disc_code = "GENEL"
        sheet_role = "METRO_GENEL_ZAYIF_AKIM"
        disc_name = "Metro Genel Zayıf Akım Planı"

        for dc, (sr, dn) in disc_map.items():
            if dc in fn_u:
                disc_code = dc
                sheet_role = sr
                disc_name = dn
                break

        return station_code, sheet_role, disc_code, disc_name, floor_code, floor_name

    @staticmethod
    def _match_block_alias(bu: str, al: str) -> bool:
        """Kısa blok sembollerinde (örn: T, YB, DS, SD, Z, KO) tam kelime eşleşmesi; uzunlarda alt dize araması yapar."""
        alu = al.upper()
        if len(alu) <= 3:
            return bu == alu or bu.startswith(f"{alu}_") or bu.endswith(f"_{alu}") or f"_{alu}_" in bu or f"-{alu}-" in bu
        return alu in bu

    def parse(self) -> WeakCurrentAuditReport:
        """Tüm zayıf akım katman ve bloklarını tarar, rapor nesnesini döner."""
        report = WeakCurrentAuditReport(
            project_name=self.dxf_path.stem,
            dxf_path=str(self.dxf_path)
        )

        try:
            self._fast_stream_dxf()
        except Exception as e:
            self.logs.append(f"Fast stream tarama hatası: {e}")

        # 1. Mevcut Katmanları Listele ve Eşleştir
        layer_names = list(self.all_layers_set)
        matched_systems = defaultdict(list)
        for lname in layer_names:
            u_lname = lname.upper()
            for sys_key, aliases in WEAK_CURRENT_LAYERS.items():
                if any(alias == u_lname or u_lname.endswith(alias) for alias in aliases):
                    matched_systems[sys_key].append(lname)
                    if lname not in self.found_layers:
                        self.found_layers.append(lname)
            if any(k in u_lname for k in ["YANGIN", "FIRE", "PAVA", "PA-VA", "CCTV", "SCADA", "TELEKOM", "FIBER", "LHD"]):
                if lname not in self.found_layers:
                    self.found_layers.append(lname)

        report.cad_layers_found = self.found_layers
        self.logs.append(f"Zayıf akım katmanları tespit edildi: {', '.join(self.found_layers)}")

        # 2. Tipoloji Algılama
        typology, conf, rationale = self._detect_typology(layer_names)
        report.typology = typology
        report.typology_confidence = conf
        report.typology_rationale = rationale

        fn_u = self.dxf_path.name.upper()
        is_metro = (typology == "METRO_RAIL") or any(k in fn_u for k in ['AX-02', 'TL-0', 'TL-1', 'AG-USK', 'AG-ELM'])

        if is_metro:
            # Metro paftalarında ezdxf.readfile 3.6GB DXF yüklemesini atla (70x hızlanma)
            for bname, cnt in self.insert_counts.items():
                u_bname = bname.upper()
                if any(k in u_bname for k in ["BEAM", "ALEV", "FLAME", "GAZ", "GAS"]):
                    self.beam_flame_cnt += cnt
                if any(k in u_bname for k in ["EX", "ATEX"]):
                    self.ex_proof_cnt += cnt
                if any(k in u_bname for k in ["HOP", "SPK", "SPEAKER", "ANONS", "PAVA"]):
                    self.pava_cnt += cnt
                if any(k in u_bname for k in ["CAM", "CCTV", "KAMERA", "IPC"]):
                    self.cctv_cnt += cnt

            for t in self.stream_ordered_texts:
                tu = t.upper()
                if any(k in tu for k in ["FE180", "PH120", "JE-H(ST)H", "LIH(ST)CH"]):
                    self.fe180_found = True
                if any(k in tu for k in ["SCADA", "PLC", "FIBER RING", "FO RING"]):
                    self.scada_found = True
                    self.fiber_ring_cnt = max(1, self.fiber_ring_cnt)
        else:
            # Bina projelerinde ezdxf üzerinden oda poligonu ve dedektör koordinat eşleştirmesi
            try:
                self.doc = ezdxf.readfile(str(self.dxf_path))
                msp = self.doc.modelspace()
            except Exception as e:
                self.logs.append(f"DXF ezdxf okuma: {e}")
                msp = []

            smoke_aliases = {x.upper() for x in WEAK_CURRENT_BLOCKS["SMOKE_DETECTOR"]}
            heat_aliases = {x.upper() for x in WEAK_CURRENT_BLOCKS["HEAT_DETECTOR"]}
            comb_aliases = {x.upper() for x in WEAK_CURRENT_BLOCKS["COMBINED_DETECTOR"]}

            for e in msp:
                dxftype = e.dxftype()
                if dxftype == 'INSERT':
                    bname = e.dxf.name.strip()
                    u_bname = bname.upper()
                    ins_pt = getattr(e.dxf, 'insert', None)
                    ix, iy = (float(ins_pt.x), float(ins_pt.y)) if ins_pt is not None else (0.0, 0.0)

                    if any(k in u_bname for k in ["BEAM", "ALEV", "FLAME", "GAZ", "GAS"]):
                        self.beam_flame_cnt += 1
                        self.detector_coords.append((ix, iy, "BEAM"))
                    if any(k in u_bname for k in ["EX", "ATEX"]):
                        self.ex_proof_cnt += 1
                    if any(k in u_bname for k in ["HOP", "SPK", "SPEAKER", "ANONS", "PAVA"]):
                        self.pava_cnt += 1
                    if any(k in u_bname for k in ["CAM", "CCTV", "KAMERA", "IPC"]):
                        self.cctv_cnt += 1

                    if u_bname in smoke_aliases:
                        self.detector_coords.append((ix, iy, "SMOKE"))
                    elif u_bname in heat_aliases:
                        self.detector_coords.append((ix, iy, "HEAT"))
                    elif u_bname in comb_aliases:
                        self.detector_coords.append((ix, iy, "COMBINED"))

                    for sys_key, layer_list in matched_systems.items():
                        if e.dxf.layer in layer_list:
                            self.block_counts[sys_key][bname] += 1
                            break
                    else:
                        for b_cat, b_aliases in WEAK_CURRENT_BLOCKS.items():
                            if any(u_bname == al.upper() for al in b_aliases):
                                if "FIRE" in b_cat or "SMOKE" in b_cat or "HEAT" in b_cat or "COMBINED" in b_cat:
                                    self.block_counts["FIRE_ALARM"][bname] += 1
                                elif "TELECOM" in b_cat or "PHONE" in b_cat:
                                    self.block_counts["TELECOM_DATA"][bname] += 1
                                elif "LAN" in b_cat or "ROUTER" in b_cat or "FIBER" in b_cat:
                                    self.block_counts["TELECOM_DATA"][bname] += 1
                                elif "TV" in b_cat:
                                    self.block_counts["SMATV_TV"][bname] += 1
                                elif "INTERCOM" in b_cat or "DOOR" in b_cat:
                                    self.block_counts["INTERCOM"][bname] += 1
                                elif "CCTV" in b_cat:
                                    self.block_counts["CCTV"][bname] += 1
                                elif "PAVA" in b_cat or "NOISE" in b_cat:
                                    self.block_counts["PA_VA_ANONS"][bname] += 1
                                elif "ACS" in b_cat:
                                    self.block_counts["ACCESS_CONTROL"][bname] += 1
                                elif "CLOCK" in b_cat:
                                    self.block_counts["CLOCK_SYSTEM"][bname] += 1
                                elif "TETRA" in b_cat:
                                    self.block_counts["TETRA_RADIO"][bname] += 1
                                elif "PIS" in b_cat:
                                    self.block_counts["PIS_DISPLAY"][bname] += 1
                                break

                elif dxftype in ('TEXT', 'MTEXT'):
                    txt = (e.dxf.text if dxftype == 'TEXT' else e.text).strip()
                    u_txt = txt.upper()
                    ins_pt = getattr(e.dxf, 'insert', None)
                    tx, ty = (float(ins_pt.x), float(ins_pt.y)) if ins_pt is not None else (0.0, 0.0)

                    if 3 <= len(u_txt) <= 38 and any(
                        rk in u_txt for rk in [
                            "SALON", "KORİDOR", "KORIDOR", "HOL", "MUTFAK", "YATAK ODASI",
                            "TRAFO", "PANO ODASI", "MDP", "UPS", "SİNYALİZASYON", "TELEKOM",
                            "JENERATÖR", "KAZAN DAİRESİ", "OTOPARK", "SIĞINAK", "ARŞİV", "DEPO",
                            "SER", "CER", "TÖM", "PERON", "BİLET", "TURNİKE"
                        ]
                    ):
                        self.room_labels.append((tx, ty, txt))

        fn_u = self.dxf_path.name.upper()
        if typology == "METRO_RAIL" or any(k in fn_u for k in ['AX-02', 'TL-0', 'TL-1', 'AG-USK', 'AG-ELM']):
            st_code, sh_role, d_code, d_name, fl_code, fl_name = self._classify_metro_weak_current_role(fn_u, self.stream_ordered_texts)
            report.sheet_role = sh_role
            report.station_code = st_code
            report.discipline_code = d_code
            report.discipline_name = d_name
            report.floor_code = fl_code
            report.floor_name = fl_name

            # Metro Cihaz Sayımları
            m_devs: Counter = Counter()
            for bname, cnt in self.insert_counts.items():
                bu = bname.upper()
                for cat, aliases in WEAK_CURRENT_BLOCKS.items():
                    if any(self._match_block_alias(bu, al) for al in aliases):
                        m_devs[cat] += cnt
                        break

            report.metro_device_counts = dict(m_devs)
            report.metro_cable_lengths_m = dict(self.poly_layer_lengths_m)
            report.metro_cable_total_m = round(sum(self.poly_layer_lengths_m.values()), 1)
            report.metro_fe180_cable_m = round(sum(
                v for k, v in self.poly_layer_lengths_m.items()
                if any(x in k.upper() for x in ['FE180', 'PH120', 'FIRE', 'YANGIN'])
            ), 1)

            # Copy-Paste ve Yabancı XREF Kontrolü
            foreign_by_st: Dict[str, List[str]] = {}
            copypaste_list = []
            cur_st_num = re.search(r'S(\d{2})', st_code)
            cur_num = cur_st_num.group(1) if cur_st_num else ""

            for bname in self.insert_counts.keys():
                bu = bname.upper()
                m_f = re.search(r'(?:PRT|ELM|USK)-M0?\d-(S-?\d{2})|-(S0[1-9]|S1[0-7]|S2[0-9])-', bu)
                if m_f and cur_num:
                    f_st = (m_f.group(1) or m_f.group(2)).replace('-', '')
                    if f_st != f"S{cur_num}":
                        foreign_by_st.setdefault(f_st, []).append(bname)

            for t in self.stream_ordered_texts[:3000]:
                m_tag = re.search(r'\bS(\d{2})[A-Z0-9/_-]+', t.upper())
                if m_tag and cur_num and m_tag.group(1) != cur_num:
                    copypaste_list.append(f"{t} (Farklı İstasyon Kodu: S{m_tag.group(1)})")

            report.metro_copypaste_errors = sorted(list(set(copypaste_list)))[:10]
            report.metro_foreign_block_warnings = [
                f"{f_st} yabancı istasyon referanslı {len(b_list)} adet blok (Örn: {b_list[0][:70]})"
                for f_st, b_list in sorted(foreign_by_st.items())
            ]

        # 3. Sistem Modellerini Doldur (Bina uyumluluğu korunur)
        report.fire_alarm = self._parse_fire_alarm()
        report.telecom = self._parse_telecom()
        report.smatv = self._parse_smatv()
        report.intercom = self._parse_intercom()

        # 4. Bağımsız Bölüm ve Kat Sayısı Tahmini
        candidates = []
        if report.intercom.monitors > 0:
            candidates.append(report.intercom.monitors)
        if report.smatv.tv_sockets > 0:
            candidates.append(report.smatv.tv_sockets)
        if report.telecom.sockets > 0:
            candidates.append(report.telecom.sockets // 2)

        dwelling_est = max(candidates) if candidates else (0 if typology != "BUILDING" else 10)
        report.dwelling_count = dwelling_est
        report.floor_count = max(len(self.plan_titles), 2 if typology != "BUILDING" else 5)
        report.building_height_m = 10.5 if typology == "INDUSTRIAL" else (report.floor_count * 2.8)

        report.extraction_logs = self.logs
        return report

    def _detect_typology(self, layer_names: List[str]) -> Tuple[str, float, str]:
        """Dosya adı, katmanlar ve CAD metinlerinden BUILDING / METRO_RAIL / INDUSTRIAL sınıflandırması yapar."""
        combined = " ".join([
            self.dxf_path.stem.lower(),
            " ".join(l.lower() for l in layer_names[:150]),
            " ".join(t.lower() for t in self.raw_texts[:250])
        ])
        metro_kws = [
            "metro", "istasyon", "station", "tünel", "tunel", "peron", "concourse",
            "bilet hol", "ag-prt", "m09", "m07", "m11", "m12", "raylı", "rayli",
            "nfpa 130", "tvf", "psd", "katener", "aygm"
        ]
        ind_kws = [
            "fabrika", "endüstriyel", "endustriyel", "üretim", "atölye", "osb",
            "trafo merkezi", "154kv", "34.5kv", "şalt", "salt", "atex", "ex-proof",
            "proses", "kazan dairesi", "depolama", "lojistik", "hangar"
        ]
        m_hits = [k for k in metro_kws if k in combined]
        i_hits = [k for k in ind_kws if k in combined]

        if len(m_hits) >= 2 or any(k in self.dxf_path.stem.lower() for k in ["m09", "ag-prt", "metro", "tunel"]):
            return (
                "METRO_RAIL",
                min(0.98, 0.70 + 0.06 * len(m_hits)),
                f"Metro / Raylı Sistem / Tünel İçi Zayıf Akım & Yangın Altyapısı (Anahtarlar: {', '.join(m_hits[:5])}) — NFPA 130, TS EN 54-16/22 & EN 50121-4"
            )
        if len(i_hits) >= 2:
            return (
                "INDUSTRIAL",
                min(0.95, 0.65 + 0.07 * len(i_hits)),
                f"Endüstriyel Tesis / Fabrika / Trafo Merkezi Zayıf Akım & Yangın Altyapısı (Anahtarlar: {', '.join(i_hits[:5])}) — BYKHY, TS EN 54-12 (Beam) & ATEX"
            )
        return (
            "BUILDING",
            0.90,
            "Konut / Ticari Bina Zayıf Akım & Yangın Tesisatı — BYKHY, TS EN 54-14, BTK & TS EN 50083"
        )

    def _parse_fire_alarm(self) -> FireAlarmSystemModel:
        """Yangın algılama bloklarını analiz eder."""
        counts = self.block_counts.get("FIRE_ALARM", Counter())
        smoke = 0
        heat = 0
        call_points = 0
        sirens = 0
        panels = 0

        for bname, cnt in counts.items():
            b_u = bname.upper()
            if b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["SMOKE_DETECTOR"]]:
                smoke += cnt
            elif b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["HEAT_DETECTOR"]]:
                heat += cnt
            elif b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["FIRE_CALL_POINT"]]:
                call_points += cnt
            elif b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["FIRE_SIREN"]]:
                sirens += cnt
            elif b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["FIRE_PANEL"]]:
                panels += cnt

        total = smoke + heat + call_points + sirens + panels + self.beam_flame_cnt
        is_drawn = total > 0 or self.lhd_length_m > 0

        unmonitored_rooms: List[str] = []
        over_spaced_cnt: int = 0
        if self.detector_coords:
            try:
                from shapely.geometry import Point
                from shapely import STRtree
                pts = [Point(x, y) for x, y, _ in self.detector_coords]
                tree = STRtree(pts)

                # Çizim birim ölçeğini (m / cm / mm) koordinat açıklığından tahmin et
                xs = [c[0] for c in self.detector_coords]
                ys = [c[1] for c in self.detector_coords]
                span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
                unit_per_m = 1000.0 if span > 5000.0 else (100.0 if span > 500.0 else 1.0)

                # 1. Dedektörler arası kapsama yarıçapı (TS EN 54-14: Duman r=6.2m -> max aralık ~9.0m, aynı kat kümesinde <= 22m)
                max_spacing_units = 9.0 * unit_per_m
                same_floor_cluster_units = 24.0 * unit_per_m
                if len(pts) >= 2:
                    for i, pt in enumerate(pts):
                        idxs, dists = tree.query_nearest(pt, return_distance=True, all_matches=False)
                        # Kendisi dışındaki en yakın komşuyu bul
                        cand_Indices = tree.query(pt.buffer(same_floor_cluster_units))
                        other_dists = [pt.distance(pts[j]) for j in cand_Indices if j != i and pt.distance(pts[j]) > 0.01]
                        if other_dists and min(other_dists) > max_spacing_units:
                            over_spaced_cnt += 1

                # 2. Mahal / Oda Kör Nokta Denetimi (r = 7.5 m içinde dedektör var mı?)
                room_search_radius = 7.5 * unit_per_m
                seen_rooms = set()
                for rx, ry, rname in self.room_labels:
                    if rname in seen_rooms:
                        continue
                    seen_rooms.add(rname)
                    r_pt = Point(rx, ry)
                    # Sadece dedektörlerin çizildiği plan bölgesi içindeki (<= 45m) odaları kontrol et
                    near_plan = tree.query(r_pt.buffer(45.0 * unit_per_m))
                    if len(near_plan) > 0:
                        in_cov = tree.query(r_pt.buffer(room_search_radius))
                        if len(in_cov) == 0:
                            unmonitored_rooms.append(rname)
            except Exception:
                pass

        return FireAlarmSystemModel(
            smoke_detectors=smoke,
            heat_detectors=heat,
            beam_flame_detectors=self.beam_flame_cnt,
            ex_proof_devices=self.ex_proof_cnt,
            linear_heat_detector_m=self.lhd_length_m,
            manual_call_points=call_points,
            sirens_flashers=sirens,
            control_panels=panels,
            total_devices=total,
            is_drawn=is_drawn,
            system_type="ADRESLİ" if (total >= 64 or self.scada_found) else "KONVANSİYONEL",
            fe180_cable_specified=self.fe180_found,
            elevator_interface_relay=is_drawn,
            fire_pump_interface_relay=is_drawn,
            scada_hvac_interface=self.scada_found,
            unmonitored_rooms=unmonitored_rooms[:10],
            over_spaced_detectors=over_spaced_cnt,
            status="UYGUN" if is_drawn else "ÇİZİMDE_YOK",
            notes=f"Toplam {total} adet yangın elemanı tespit edildi (Duman: {smoke}, Beam/Alev: {self.beam_flame_cnt}, Buton: {call_points}, Siren: {sirens}, Santral: {panels})."
        )

    def _parse_telecom(self) -> TelecomSystemModel:
        """Telefon ve data bloklarını analiz eder."""
        counts = self.block_counts.get("TELECOM_DATA", Counter())
        sockets = 0
        floor_boxes = 0
        main_boxes = 0

        for bname, cnt in counts.items():
            b_u = bname.upper()
            if b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["TELECOM_SOCKET"]]:
                sockets += cnt
            elif b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["FLOOR_TELECOM_BOX"]]:
                floor_boxes += cnt
            elif b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["BUILDING_TELECOM_BOX"]]:
                main_boxes += cnt

        is_drawn = (sockets + floor_boxes + main_boxes + self.fiber_ring_cnt + self.cctv_cnt + self.pava_cnt) > 0

        return TelecomSystemModel(
            sockets=sockets,
            floor_boxes=floor_boxes,
            main_boxes=main_boxes,
            fiber_backbone_rings=self.fiber_ring_cnt,
            cctv_cameras=self.cctv_cnt,
            pava_speakers=self.pava_cnt,
            estimated_pairs=sockets,
            btk_capacity_adequate=main_boxes > 0 or self.fiber_ring_cnt > 0,
            is_drawn=is_drawn,
            status="UYGUN" if is_drawn else "ÇİZİMDE_YOK",
            notes=f"Toplam {sockets} adet data/telefon prizi, {floor_boxes} kat kutusu, {main_boxes} ana kutu, {self.pava_cnt} PA/VA hoparlör, {self.cctv_cnt} kamera tespit edildi."
        )

    def _parse_smatv(self) -> SmatvSystemModel:
        """TV / Uydu bloklarını analiz eder."""
        counts = self.block_counts.get("SMATV_TV", Counter())
        tv_sockets = 0
        tap_offs = 0
        floor_boxes = 0
        multiswitches = 0

        for bname, cnt in counts.items():
            b_u = bname.upper()
            if b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["TV_SOCKET"]]:
                tv_sockets += cnt
            elif b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["TV_TAP_OFF"]]:
                tap_offs += cnt
            elif b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["FLOOR_TV_BOX"]]:
                floor_boxes += cnt
            elif b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["TV_MULTISWITCH"]]:
                multiswitches += cnt

        is_drawn = (tv_sockets + tap_offs + multiswitches) > 0

        return SmatvSystemModel(
            tv_sockets=tv_sockets,
            tap_offs=tap_offs,
            floor_boxes=floor_boxes,
            multiswitches=multiswitches,
            is_drawn=is_drawn,
            status="UYGUN" if is_drawn else "ÇİZİMDE_YOK",
            notes=f"Toplam {tv_sockets} adet TV prizi, {tap_offs} adet kat dağıtıcı (TAP), {multiswitches} adet TV santrali (TVS) tespit edildi."
        )

    def _parse_intercom(self) -> IntercomSystemModel:
        """İnterkom / diafon bloklarını analiz eder."""
        counts = self.block_counts.get("INTERCOM", Counter())
        monitors = 0
        bells = 0
        door_releases = 0
        entrance_panels = 0

        for bname, cnt in counts.items():
            b_u = bname.upper()
            if b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["INTERCOM_MONITOR"]]:
                monitors += cnt
            elif b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["DOOR_BELL_BUTTON"]]:
                bells += cnt
            elif b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["DOOR_RELEASE"]]:
                door_releases += cnt
            elif b_u in [x.upper() for x in WEAK_CURRENT_BLOCKS["DOOR_PANEL"]]:
                entrance_panels += cnt

        # 24V güç beslemesi
        power_cnt = sum(self.block_counts.get("POWER_24V", Counter()).values())

        is_drawn = (monitors + bells + door_releases) > 0

        return IntercomSystemModel(
            monitors=monitors,
            door_bell_buttons=bells,
            door_releases=door_releases,
            entrance_panels=entrance_panels,
            power_supplies=power_cnt,
            is_drawn=is_drawn,
            status="UYGUN" if is_drawn else "ÇİZİMDE_YOK",
            notes=f"Toplam {monitors} adet daire içi diafon (ID), {bells} adet kapı zili (Z), {door_releases} adet kapı otomatiği (KO) tespit edildi."
        )
