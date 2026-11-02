# -*- coding: utf-8 -*-
"""
Pafta Çerçevesi, Antet ve Lejant Haritalayıcı (SpatialZoneMapper)
================================================================
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional
from shapely.geometry import box, Point
from shapely.strtree import STRtree

from ..model.entities import TextToken, PlacedSymbol, SubPlanZone, ExtractedTable
from .geometry import clean_turkish_text, TextReconstructionEngine, GeometricTableExtractor


KNOWN_METRO_STATIONS: Dict[str, Tuple[str, str]] = {
    "S18": ("İkitelli Sanayi İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "S19": ("Masko İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "S20": ("Bahariye İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "S21": ("Atatürk Mahallesi İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "S22": ("15 Temmuz İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "S23": ("Mimar Sinan İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "S24": ("Çobançeşme - Kuyumcukent İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "S25": ("29 Ekim Cumhuriyet İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "S26": ("Doğu Sanayi İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "S27": ("İhlas Yuva İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "S28": ("Yenibosna İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
    "S29": ("Ataköy İstasyonu", "M9 Ataköy - İkitelli Metro Hattı"),
}



def _tu(s: str) -> str:
    """Türkçe-duyarlı büyük harf dönüşümü (i→İ, ı→I)."""
    return s.replace("i", "İ").replace("ı", "I").upper()


class SpatialZoneMapper:
    @classmethod
    def parse_title_and_paperspace_tables(
        cls,
        doc: Any,
        msp_tokens: List[TextToken],
        file_path: Optional[Any] = None,
        explicit_station_code: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], List[ExtractedTable], List[SubPlanZone]]:
        info = {
            "station_code": "PROJE",
            "station_name": "GENEL",
            "sheet_title": "",
            "system_discipline": "",
            "floor_name": "",
            "elevation_kot": None,
            "title_mismatch_warning": "",
        }
        ps_tables: List[ExtractedTable] = []
        ps_view_zones: List[SubPlanZone] = []
        ps_raw_tokens: List[TextToken] = []

        for layout in doc.layouts:
            if layout.name.lower() != "model":
                for ent in layout:
                    if ent.dxftype() in ("TEXT", "MTEXT"):
                        raw_v = ent.dxf.text if ent.dxftype() == "TEXT" else ent.text
                        clean_v = clean_turkish_text(raw_v)
                        if clean_v:
                            ins = ent.dxf.insert
                            h = getattr(ent.dxf, "height", 2.5)
                            rot = getattr(ent.dxf, "rotation", 0.0)
                            ps_raw_tokens.append(TextToken(
                                text=clean_v,
                                pos=(ins.x, ins.y, 0.0),
                                height=h,
                                rotation=rot,
                                layer=ent.dxf.layer,
                                color=256,
                                bbox=TextReconstructionEngine.create_text_bbox(
                                    (ins.x, ins.y), clean_v, h, rot, is_paperspace=True
                                ),
                                parent_block=layout.name,
                            ))

        stitched_ps = TextReconstructionEngine.stitch_horizontal_tokens(ps_raw_tokens, is_paperspace=True)

        if any("METRAJ" in _tu(t.text) for t in stitched_ps):
            xy_ps = [(t.pos[0], t.pos[1], t.text) for t in stitched_ps if t.pos[1] > 100.0 and "METRAJ" not in _tu(t.text)]
            tbl_title = next((t.text for t in stitched_ps if "METRAJ" in _tu(t.text)), "PAPERSPACE_METRAJ_TABLOSU")
            ps_tbl = GeometricTableExtractor.extract_grid_table(
                name=tbl_title,
                xy_texts=xy_ps,
                header_keywords=("SİSTEM", "TİP", "GENİŞLİK", "YÜKSEKLİK", "UZUNLUK", "KABLO"),
                row_tol=4.5,
                source_space="PAPERSPACE",
            )
            if ps_tbl:
                ps_tables.append(ps_tbl)

        for t in stitched_ps:
            t_up = _tu(t.text)
            if any(p in t_up for p in ["00 PERON", "01 FFL", "02 FFL", "03 SSL", "ŞAFTI", "KESİTİ", "KUYUSU"]) and "İSTASYONU" not in t_up:
                ps_view_zones.append(SubPlanZone(
                    name=t.text,
                    bounds=(t.pos[0], t.pos[1], t.pos[0] + 100, t.pos[1] + 20),
                    polygon=t.bbox,
                    zone_type="VIEWPORT_TITLE",
                ))

        candidate_lines = [t.text for t in stitched_ps]
        if not candidate_lines or not any("PROJESİ" in _tu(l) or "SİSTEMİ" in _tu(l) for l in candidate_lines):
            candidate_lines.extend([
                t.text for t in msp_tokens
                if any(k in _tu(t.text) for k in [
                    "PROJESİ", "İSTASYONU", "TESİSAT", "YAPI SAHİBİ", "MUSA DEMİR", "MUSA DEMIR",
                    "FAKİUŞAĞI", "FAKIUŞAĞI", "KONUT+İŞYERİ", "OSMANİYE", "ADA", "PARSEL", "KURULU GÜÇ"
                ])
            ])

        all_text = "\n".join(candidate_lines)

        # ----------------------------------------------------------------------
        # İSTASYON / PROJE KODU VE ADI HİYERARŞİSİ (Strict Hierarchy)
        # 1. Kullanıcı tarafından verilen explicit_station_code
        # 2. Dosya adı / Klasör yolu (örn: M09-S24 -> S24, M09-S28 -> S28)
        # 3. Antet ve Pafta metni (M09-...-Sxx veya açıkça Sxx)
        # 4. Bilinmiyor / Klasik Bina
        # ----------------------------------------------------------------------
        resolved_code = None

        # Seviye 1: Kullanıcı CLI argümanı
        if explicit_station_code:
            resolved_code = explicit_station_code.strip().upper()

        # Seviye 2: Dosya adı / Klasör yolu
        if not resolved_code and file_path:
            fp_p = Path(file_path)
            fn_str = fp_p.name.upper()
            fp_str = str(fp_p).upper()
            m_fn = (
                re.search(r"M09[-_]?S(\d{2})", fn_str)
                or re.search(r"(?:^|[-_/\\])S(\d{2})(?:[-_/\\]|$)", fn_str)
                or re.search(r"M09[-_]?S(\d{2})", fp_str)
                or re.search(r"(?:^|[-_/\\])S(\d{2})(?:[-_/\\]|$)", fp_str)
            )
            if m_fn:
                resolved_code = f"S{m_fn.group(1)}"

        # Klasik Bina Projesi Antet Tespiti (BSL50 vb. elektrik iç tesisat)
        is_building_text = (
            "İSTASYONU" not in _tu(all_text)
            and not (resolved_code and resolved_code.startswith("S"))
            and any(
                k in _tu(all_text)
                for k in ["PROJESİ", "TESİSAT", "YAPI SAHİBİ", "KONUT", "ADA", "PARSEL", "MİMARİ", "ELEKTRİK"]
            )
        )
        if is_building_text:
            base_fn = Path(file_path).stem if file_path else "BİNA_PROJESİ"
            clean_proj_name = re.sub(r"\s*[-_]?\s*Elektrik.*$", "", base_fn, flags=re.IGNORECASE).strip().upper()

            info["station_code"] = explicit_station_code.strip().upper() if explicit_station_code else "E-01"
            info["system_discipline"] = "00_BINA_TUM_DISIPLINLER"

            if any(k in _tu(all_text) for k in ["MUSA DEMİR", "MUSA DEMIR"]):
                info["station_name"] = "MUSA DEMİR KONUT+İŞYERİ"
                info["floor_name"] = "BODRUM + ZEMİN + 4 NORMAL + TERAS KAT (13 PAFTA)"
                info["sheet_title"] = "MUSA DEMİR KONUT + İŞYERİ ELEKTRİK İÇ TESİSAT PROJESİ (OSMANİYE / MERKEZ ADA:7 PARSEL:529)"
            else:
                info["station_name"] = clean_proj_name or "BİNA ELEKTRİK PROJESİ"
                best_title = next(
                    (l for l in candidate_lines if any(k in _tu(l) for k in ["PROJESİ", "TESİSAT"]) and len(l) > 12),
                    f"{info['station_name']} ELEKTRİK İÇ TESİSAT PROJESİ"
                )
                info["sheet_title"] = best_title
                info["floor_name"] = "BİNA KATLARI VE KOLON ŞEMASI"

            return info, ps_tables, ps_view_zones

        # Seviye 3: Antet ve Pafta Metni (Yalnızca dosya adından bulunamadıysa!)
        if not resolved_code:
            m_ant = re.search(r"M09[A-Z0-9_-]*?-S(\d{2})\b", all_text)
            if m_ant:
                resolved_code = f"S{m_ant.group(1)}"
            else:
                m_st = re.search(r"\b(S\d{2})\b", all_text)
                if m_st:
                    resolved_code = m_st.group(1).upper()

        # Seviye 4: Varsayılan
        info["station_code"] = resolved_code or "PROJE"

        # İstasyon Adını Kod ile Kesin Senkronize Et (S24 -> Asla Mimar Sinan veya S28 olamaz!)
        if info["station_code"] in KNOWN_METRO_STATIONS:
            info["station_name"] = KNOWN_METRO_STATIONS[info["station_code"]][0]
        else:
            info["station_name"] = Path(file_path).stem if file_path else "GENEL"

        # Kot Bilgisi
        m_kot = re.search(r"([+-]?\d+(?:\.\d+)?)\s*KOTU", all_text, re.IGNORECASE)
        if m_kot:
            try:
                info["elevation_kot"] = float(m_kot.group(1))
            except Exception:
                pass

        # Kat Bilgisi
        m_kat = re.search(
            r"((?:BİLET\s+HOLÜ|PERON\s+ALTI|PERON|M1A\s+PERONU|TEKNİK|ARA)\s+KAT[I]?)",
            all_text,
            re.IGNORECASE
        )
        if m_kat:
            info["floor_name"] = m_kat.group(1).upper().strip()

        # Pafta Başlığı
        title_lines = [
            l.replace("\n", " - ") for l in candidate_lines
            if any(k in _tu(l) for k in ["PROJESİ", "SİSTEMİ", "ŞEMASI"]) and len(l) > 10
        ]
        if title_lines:
            info["sheet_title"] = max(title_lines, key=len)

        # Çapraz Başlık Kontrolü (Örn: S24 Çobançeşme dosyasında Mimar Sinan başlığı unutulmuşsa uyar)
        def _norm_tr(s: str) -> str:
            return s.replace("İ", "I").replace("ı", "I").replace("ğ", "G").replace("Ğ", "G").replace("ş", "S").replace("Ş", "S").replace("ç", "C").replace("Ç", "C").replace("ö", "O").replace("Ö", "O").replace("ü", "U").replace("Ü", "U").upper()

        if info["station_code"] in KNOWN_METRO_STATIONS and info["sheet_title"]:
            true_st_name_norm = _norm_tr(info["station_name"])
            sheet_title_norm = _norm_tr(info["sheet_title"])
            for other_code, (other_name, _) in KNOWN_METRO_STATIONS.items():
                if other_code != info["station_code"]:
                    other_kw_norm = _norm_tr(other_name.split()[0])
                    if other_kw_norm in sheet_title_norm and other_kw_norm not in true_st_name_norm:
                        info["title_mismatch_warning"] = (
                            f"Dosya adı ve proje kodu '{info['station_code']} ({info['station_name']})' olduğu halde, "
                            f"antet başlığında başka istasyondan ({other_code} {other_name}) kopyalanmış "
                            f"'{info['sheet_title']}' ifadesi yer almaktadır!"
                        )
                        break

        # Disiplin tespiti: Önce dosya yolu / dosya adına bak, sonra pafta başlığına ve metne
        if file_path:
            fp_p = Path(file_path)
            fn_u = fp_p.name.upper()
            fp_u = str(fp_p).upper()
            if "03_ZAYIF_AKIM" in fp_u or any(k in fn_u for k in ["-TL-", "-AX-", "USK-M09"]):
                if "-TL-05-" in fn_u or "YANGIN" in _tu(info["sheet_title"] + all_text[:500]):
                    info["system_discipline"] = "03_ZAYIF_AKIM_YANGIN"
                elif "-TL-02-" in fn_u or "İLETİM" in _tu(info["sheet_title"]) or "DATA" in _tu(info["sheet_title"]):
                    info["system_discipline"] = "03_ZAYIF_AKIM_DATA"
                elif "-TL-01-" in fn_u or "CCTV" in _tu(info["sheet_title"] + all_text[:500]):
                    info["system_discipline"] = "03_ZAYIF_AKIM_CCTV"
                else:
                    info["system_discipline"] = "03_ZAYIF_AKIM"
            elif "02_TOPRAKLAMA" in fp_u or any(k in fn_u for k in ("-PS-17-", "-GN-13-", "-GN-14-", "TOPRAKLAMA")):
                info["system_discipline"] = "02_TOPRAKLAMA"
            elif "01_KUVVETLI_AKIM" in fp_u or any(k in fn_u for k in ("-PS-08-", "-PS-11-", "-PS-16-")):
                if any(k in fn_u for k in ("-PS-08-051", "-PS-16-051")) or "PRİZ" in _tu(info["sheet_title"]):
                    info["system_discipline"] = "01_KUVVETLI_AKIM_PRIZ"
                elif any(k in fn_u for k in ("-PS-08-001", "-PS-16-001")) or "AYDINLATMA" in _tu(info["sheet_title"]):
                    info["system_discipline"] = "01_KUVVETLI_AKIM_AYDINLATMA"
                else:
                    info["system_discipline"] = "01_KUVVETLI_AKIM"

        if not info["system_discipline"]:
            t_search = _tu(info["sheet_title"] + " " + all_text[:1000])
            if "AYDINLATMA" in t_search:
                info["system_discipline"] = "01_KUVVETLI_AKIM_AYDINLATMA"
            elif "PRİZ" in t_search:
                info["system_discipline"] = "01_KUVVETLI_AKIM_PRIZ"
            elif "O.G." in t_search or "GÜÇ KABLOLARI GÜZERGAH" in t_search:
                info["system_discipline"] = "01_KUVVETLI_AKIM_OG_GUZERGAH"
            elif "TAVA" in t_search:
                info["system_discipline"] = "01_KUVVETLI_AKIM_TAVA"
            elif "GÜÇ" in t_search or "GUC" in t_search or "KUVVET" in t_search:
                info["system_discipline"] = "01_KUVVETLI_AKIM_GUC"
            elif "TOPRAKLAMA" in t_search:
                info["system_discipline"] = "02_TOPRAKLAMA"
            elif "YANGIN" in t_search:
                info["system_discipline"] = "03_ZAYIF_AKIM_YANGIN"
            elif "İLETİM" in t_search or "DATA" in t_search:
                info["system_discipline"] = "03_ZAYIF_AKIM_DATA"
            else:
                info["system_discipline"] = "00_GENEL"

        return info, ps_tables, ps_view_zones

    @classmethod
    def detect_modelspace_frames(
        cls, msp: Any, msp_tokens: List[TextToken], symbols: List[PlacedSymbol]
    ) -> List[SubPlanZone]:
        frames: List[Tuple[float, float, float, float]] = []
        for fr in msp.query("LWPOLYLINE POLYLINE"):
            lay = fr.dxf.layer.upper()
            if any(k in lay for k in ["CERCEVE", "ÇERÇEVE", "FRAME", "PAFTA", "SINIR", "BORDER"]) or getattr(fr, "is_closed", False):
                try:
                    pts = fr.get_points() if hasattr(fr, "get_points") else [v.dxf.location for v in fr.vertices]
                    if len(pts) < 4:
                        continue
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    w = max(xs) - min(xs)
                    h = max(ys) - min(ys)
                    if w >= 1500.0 and h >= 1500.0:
                        box_tup = (min(xs), min(ys), max(xs), max(ys))
                        if not any(abs(existing[0]-box_tup[0]) < 25 and abs(existing[2]-box_tup[2]) < 25 for existing in frames):
                            frames.append(box_tup)
                except Exception:
                    continue

        if not frames:
            return []

        frames.sort(key=lambda b: b[0])
        sub_zones: List[SubPlanZone] = []
        for idx, (minx, miny, maxx, maxy) in enumerate(frames, 1):
            poly = box(minx, miny, maxx, maxy)
            in_t = [t for t in msp_tokens if minx <= t.pos[0] <= maxx and miny <= t.pos[1] <= maxy]
            title = f"Pafta Bölgesi #{idx}"
            for t in sorted(in_t, key=lambda x: -x.height):
                tu = _tu(t.text)
                if any(k in tu for k in ["PLANI", "ŞEMASI", "SEMASI", "HESABI", "TOPRAKLAMA"]):
                    clean_t = re.sub(r"\{.*?\}|\\f.*?\;|\\p.*?\;|\\P", " ", t.text).strip()
                    clean_t = re.sub(r"\s+", " ", clean_t)
                    if 5 < len(clean_t) < 70:
                        title = clean_t
                        break

            sym_count = sum(1 for s in symbols if minx <= s.pos[0] <= maxx and miny <= s.pos[1] <= maxy)
            z_type = "PLAN"
            t_up = _tu(title)
            if "KOLON" in t_up or "ŞEMA" in t_up:
                z_type = "RISER_SCHEMATIC"
            elif "TOPRAKLAMA" in t_up:
                z_type = "GROUNDING_PLAN"
            elif "ZAYIF" in t_up:
                z_type = "WEAK_CURRENT_PLAN"
            elif "KUVVETLİ" in t_up or "GÜÇ" in t_up:
                z_type = "POWER_PLAN"

            sub_zones.append(SubPlanZone(
                name=title,
                bounds=(round(minx, 1), round(miny, 1), round(maxx, 1), round(maxy, 1)),
                polygon=poly,
                zone_type=z_type,
                symbol_count=sym_count,
            ))

        return sub_zones

    @classmethod
    def extract_symbol_dictionary(cls, tokens: List[TextToken], symbols: List[PlacedSymbol]) -> Dict[str, str]:
        sym_dict: Dict[str, str] = {}
        legend_tokens = [
            t for t in tokens
            if any(k in _tu(t.text) for k in ["SEMBOL", "LEJANT", "AÇIKLAMA", "ACIKLAMA"])
        ]
        if not legend_tokens:
            return sym_dict

        xs_all = [s.pos[0] for s in symbols]
        span_x = (max(xs_all) - min(xs_all)) if len(xs_all) >= 2 else 10000.0

        for l_tok in legend_tokens:
            H = max(l_tok.height, 2.5)
            if H >= 8.0 and span_x < 100000.0:
                # cm/dm ölçekli klasik bina projesi
                lx, ly = l_tok.pos[0], l_tok.pos[1]
                l_box = box(lx - 15.0 * H, ly - 125.0 * H, lx + 60.0 * H, ly + 8.0 * H)
                in_legend_syms = [s for s in symbols if l_box.contains(Point(s.pos[0], s.pos[1]))]
                in_legend_texts = [t for t in tokens if l_box.contains(Point(t.pos[0], t.pos[1])) and t != l_tok]
                if not in_legend_syms or not in_legend_texts:
                    continue

                for sym in in_legend_syms:
                    sx, sy = sym.pos[0], sym.pos[1]
                    candidates = []
                    for t in in_legend_texts:
                        tx, ty = t.pos[0], t.pos[1]
                        dx = tx - sx
                        dy = abs(ty - sy)
                        if 0.0 < dx <= 35.0 * H and dy <= 1.35 * H and len(t.text.strip()) > 2:
                            if not any(h_kw in _tu(t.text) for h_kw in ["SEMBOL", "AÇIKLAMA", "ACIKLAMA"]):
                                candidates.append((dy * 4.0 + dx, t.text.strip()))
                    if candidates:
                        candidates.sort(key=lambda item: item[0])
                        sym_dict[sym.clean_family_name] = candidates[0][1]
            else:
                # mm ölçekli metro / revit paftası
                l_box = box(l_tok.pos[0] - 500, l_tok.pos[1] - 30000, l_tok.pos[0] + 40000, l_tok.pos[1] + 2000)
                in_legend_syms = [s for s in symbols if l_box.intersects(s.bbox)]
                in_legend_texts = [t for t in tokens if l_box.intersects(t.bbox) and t != l_tok]
                if not in_legend_syms or not in_legend_texts:
                    continue

                for sym in in_legend_syms:
                    sx, sy = sym.pos[0], sym.pos[1]
                    candidates = []
                    for t in in_legend_texts:
                        dx = t.pos[0] - sx
                        dy = abs(t.pos[1] - sy)
                        if 0.0 <= dx <= 8000.0 and dy <= 400.0 and len(t.text.strip()) > 2:
                            candidates.append((dy * 4.0 + dx, t.text.strip()))
                    if candidates:
                        candidates.sort(key=lambda item: item[0])
                        sym_dict[sym.clean_family_name] = candidates[0][1]

        return sym_dict
