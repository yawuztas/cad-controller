# -*- coding: utf-8 -*-
"""
Evrensel Disiplin & Mimari Altlık Ayırıcı (`disiplin_ayirici.py`)
===================================================================
Proje genelindeki blok, çizgi ve yazıları **sıfır hardcode** ile:
1. **Mimari Altlık** (duvar, tefriş, kapı/pencere, aks, ölçü, kolon, salt altlık)
   ve **Elektrik Sistemi** (Kuvvetli Akım, Zayıf Akım/Yangın, Topraklama, Kablo Hattı)
   olarak ayırır.
2. Çerçeveli paftaların ve çerçevesiz plan bölgelerinin **altında yer alan başlık
   yazısını** geometrik olarak bularak her bölgeyi `Kat / Bölüm × Disiplin` eksenine
   oturtur.
"""

from __future__ import annotations
from collections import Counter, defaultdict
import math
import re
import statistics
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point, box
from shapely.strtree import STRtree
from sklearn.cluster import DBSCAN

from .metin_temizleyici import norm_tr
from .schema import (
    BBox2D,
    LegendEntry,
    RawInsert,
    RawPath,
    RawText,
    SheetFrame,
)

# ---------------------------------------------------------------------------
# Evrensel Mühendislik Katman ve Sembol Anahtar Sözlükleri
# ---------------------------------------------------------------------------

_ARCH_LAYER_KEYS: Tuple[str, ...] = (
    "MIMARI", "MİMARI", "TEFRIS", "TEFRİŞ", "KAPI", "PENCERE", "DUVAR",
    "AKSLAR", "AKS", "TARAMA", "HATCH", "KOLONLAR", "PERDE", "MERDIVEN", "MERDİVEN",
    "CERCEVE", "ÇERÇEVE", "ANTET", "TF1", "TF2", "TEF1", "TEF2", "KAPEN", "KAPIPENCERE",
    "DOGRAMA", "SIVA", "MOBILYA", "PEYZAJ", "ESYA", "EŞYA", "OLCU", "OLÇÜ",
    "BETON", "GORUNUS", "SUPURGELIK", "ZEMINTARAM", "MATERIAL",
    "ARKA_PLAN", "CARTIGLIO", "ARREDO", "P-SANR",
    "A-GENM", "A-FLOR", "A-DETL", "A-DOOR", "A-GLAZ", "A-WALL", "A-AREA",
    "I-WALL", "S-STRS", "S-COLS", "S-BEAM", "S-SLAB", "S-GRID", "Q-SPCQ", "G-ANNO", "M-AREA",
    "AXIS", "WALL", "DOOR", "WINDOW", "ARCH", "FURN", "DEFPOINTS", "SLAB",
)
_RE_ARCH_BOUNDARY_KEYS: Dict[str, re.Pattern[str]] = {
    k: re.compile(rf"(?<![A-Z]){re.escape(k)}(?![A-Z])")
    for k in ("AKS", "SIVA", "ARCH", "SLAB", "WALL", "DOOR", "FURN", "AXIS", "OLCU", "KAPI", "TF1", "TF2", "TEF1", "TEF2", "ESYA")
}


def _matches_arch_layer_key(lay_u: str) -> bool:
    """Mimari kısa anahtarları ('AKS' -> 'TAKSIM', 'ARCH' -> 'SEARCH' çakışmasın diye) kelime sınırıyla eşler."""
    for k in _ARCH_LAYER_KEYS:
        rx = _RE_ARCH_BOUNDARY_KEYS.get(k)
        if rx is not None:
            if rx.search(lay_u):
                return True
        elif k in lay_u:
            return True
    return False

_ARCH_BLOCK_KEYS: Tuple[str, ...] = (
    "KLOZ", "DUS", "DUŞ", "LAVABO", "LAV", "LVB", "EVYE", "EVIYE", "KAPI", "PENCERE",
    "YATAK", "KOLTUK", "MASA", "TABLE", "SEH50", "SEHPA", "ARABA", "AGAC", "AĞAÇ", "DUVAR",
    "ANTET", "CERCEVE", "_ARCHTICK", "ARCHITECT", "SINK", "TOILET", "BED", "SOFA",
    "CERAMIC", "SERAMIK", "GRID HEAD", "D_DAT_GRID", "LEVEL HEAD", "D_DAT_LEVEL",
    "SPACE TAG", "D_TAG_ROOM", "RAILING", "KORKULUK", "SECTION", "VIEWTITLE",
    "C2010_", "C30", "D2010_", "D4030_", "B1080_", "E2050_",
    "FIRE CABINET", "YANGIN DOLABI", "ARC-01", "STR-01", "MEC-01",
    "C1070_", "CEILING", "KOSEBENT", "LOCKER", "SWINGING", "AKE ESC",
    "MULLION", "LIFT ASSEMBLY", "FLOORS ", "TOP RAIL", "BALUSTER",
    "STAIR", "LADDER", "DISPEN", "ESCALATOR",
    "GLAZ", "CURTAIN", "BOOTH", "SOVE", "DRAINER", "PRECAST", "WALL OPENING",
    "LENTO", "HAT EKSEN", "GRENLI", "SPOT ELEVATION", "D_DAT_ELE",
    "-MEC-", "-ARC-", "-STR-",
)

_GROUNDING_KEYS: Tuple[str, ...] = (
    "TOPRAK", "GND", "EARTH", "PARATONER", "YILDIRIM", "SERIT", "EKK", "KAD", "ETB",
)

_WEAK_KEYS: Tuple[str, ...] = (
    "ZAYIF", "DATA", "TEL", "TELEFON", "TV", "DUAFON", "INTERCOM", "CCTV",
    "KAMERA", "SES", "UYDU", "YANGIN", "FIRE", "IHBAR", "DUMAN", "SIREN",
    "BTK", "TVS", "TVK", "SKM", "YIS",
)

_POWER_LAYER_CATEGORY_RULES: Tuple[Tuple[Tuple[str, ...], str, str], ...] = (
    (("BUAT", "JUNCTION", "KASAS"), "BUAT", "KUVVETLI_AKIM"),
    (("LINYESI", "LINYE_NO", "LINYE NO", "KOLON NO", "LINE NR", "KOLONNO", "00-KOL_NO"), "HAT / LİNYE ETİKETİ", "KUVVETLI_AKIM"),
    (("TELEFON PRIZ", "TELEVIZYON PRIZ", "TV PRIZ", "DATA PRIZ", "ZIL BUTONU", "ZAYIF AKIM", "ZAYIF"), "ZAYIF AKIM", "ZAYIF_AKIM"),
    (("TURNSTILE", "TURNIKE", "FARE C", "FARE GATE", "VALIDATOR", "KART OKUYUCU", "BILET MAKIN", "TICKET VENDING", "TVM"), "GEÇİŞ / BİLET SİSTEMİ", "ZAYIF_AKIM"),
    (("CESB", "PLC", "RTU", "SCADA", "CBTC", "ETCS", "AXLE COUNTER", "BALISE", "INTERLOCKING", "SINYAL", "SIGNAL", "ATS", "ATO", "ATP", "ETHERNET SWITCH", "RIO PANEL"), "KONTROL / SİNYAL", "SINYAL"),
    (("CABLE TRAY", "CABL-TRAY", "KABLO TAVA", "KABLOTAVA", "TAVA_"), "KABLO TAVA / TAŞIYICI", "KUVVETLI_AKIM"),
    (("PRIZ", "PRZ", "SOCKET", "OUTLET", "D5030_50_", "PRT-EL-PRZ"), "PRİZ", "KUVVETLI_AKIM"),
    (("YANGIN", "FIRE", "IHBAR", "DUMAN", "SIREN", "SONLANDIRMA", "D7050_"), "YANGIN ALGILAMA", "ZAYIF_AKIM"),
    (("DATA", "TEL", "TELEFON", "TV", "DUAFON", "INTERCOM", "CCTV", "KAMERA", "SES", "UYDU", "BTK", "TVS", "TVK", "ZIL", "KAPI OTOM", "LOUDSPEAKER", "D6030_", "D6010_", "D6020_", "D6060_", "D7030_", "00-24V"), "ZAYIF AKIM", "ZAYIF_AKIM"),
    (("ELEKTRIK SAYAC", "SAYAC", "KWH SAYAC"), "SAYAÇ", "KUVVETLI_AKIM"),
    (("PANELBOARD", "SWITCHBOARD", "TRANSFORMER", "PANO", "TABLO", "PANEL", "DAGITIM", "ITDT", "D5020_", "D5010_", "PRT-EL-RPP", "E-ELEC-EQPM"), "PANO / TABLO", "KUVVETLI_AKIM"),
    (("SALTER", "KORUMA", "KESICI", "SIGORTA", "AOS", "KAR", "TMS", "00-04", "00-05", "00-06"), "ŞALT / KORUMA", "KUVVETLI_AKIM"),
    (("ANAHTAR", "SWITCH", "KOMUTAT", "VAVIEN"), "ANAHTAR", "KUVVETLI_AKIM"),
    (("TOPRAK", "GND", "EARTH", "PARATONER", "YILDIRIM", "SERIT", "EKK", "KAD", "ETB", "KLEMENS", "CUBUG", "BARAS", "KADVELT", "ESPOTANSIYEL"), "TOPRAKLAMA", "TOPRAKLAMA"),
    (("AYD", "ARMATUR", "LIGHT", "LAMP", "AYDINLATMA", "FLORESAN", "AVIZE", "SPOT", "E-ELEC-FIXT"), "AYDINLATMA", "KUVVETLI_AKIM"),
    (("KUVVET", "MOTOR", "ASANSOR", "POMPA", "KLIMA", "BESLEME"), "KUVVET / TESİSAT", "KUVVETLI_AKIM"),
)

_BOUNDARY_MATCH_KEYS: Set[str] = {
    "SPOT", "AYD", "TEL", "TV", "SES", "ZIL", "PRZ", "GND",
    "EKK", "KAD", "ETB", "BTK", "TVS", "TVK", "AOS", "KAR",
    "TMS", "LAMP", "FIRE", "DATA",
    "ATS", "ATO", "ATP", "PLC", "RTU", "CESB", "TVM", "ETCS", "CBTC",
}
_RE_BOUNDARY_KEYS: Dict[str, re.Pattern[str]] = {
    k: re.compile(rf"(?<![A-Z]){re.escape(k)}(?![A-Z])")
    for k in _BOUNDARY_MATCH_KEYS
}

_ELEC_WIRE_LAYER_KEYS: Tuple[str, ...] = (
    "KABLO", "WIRE", "CONDUIT", "LINYE", "SORTI", "AYD", "PRZ", "PRIZ",
    "ZAYIF", "TOPRAK", "SERIT", "YANGIN", "TEL", "TV", "DATA", "INTERCOM",
    "ANHTR", "BUAT", "HAT", "00-KOL", "KOLON_HAT",
    "KOLON_SEMA", "E-KOLON",
    "E-COMM", "E-BORU", "PRT-EL-", "YP-EL",
    "00-06", "00-24V", "00-TOPRAK",
)
_RE_WIRE_BOUNDARY_KEYS: Dict[str, re.Pattern[str]] = {
    "HAT": re.compile(r"(?<![A-Z])HAT(?:TI|LAR|LARI)?(?![A-Z])"),
    "TEL": re.compile(r"(?<![A-Z])TEL(?:EFON)?(?![A-Z])"),
    "TV": re.compile(r"(?<![A-Z])TV(?![A-Z])"),
    "AYD": re.compile(r"(?<![A-Z])AYD(?:INLATMA)?(?![A-Z])"),
    "PRZ": re.compile(r"(?<![A-Z])PRZ(?![A-Z])"),
    "DATA": re.compile(r"(?<![A-Z])DATA(?![A-Z])"),
}


def _matches_wire_layer_key(lay_u: str) -> bool:
    """Kısa/çakışabilen anahtarları ('HAT' -> 'HATCH'/'BAG_HATILI' gibi) yalnızca kelime sınırıyla eşler."""
    for k in _ELEC_WIRE_LAYER_KEYS:
        rx = _RE_WIRE_BOUNDARY_KEYS.get(k)
        if rx is not None:
            if rx.search(lay_u):
                return True
        elif k in lay_u:
            return True
    return False

_NON_WIRE_ANNOTATION_KEYS: Tuple[str, ...] = (
    "ELKYAZ", "CERCEVE", "ÇERÇEVE", "ANTET", "LINYE_NO", "LİNYE_NO", "LINYE NO",
    "KOL_NO", "KOLON_NO", "KOLON NO", "LINE NR", "TABLO", "YAZI", "ETIKET",
    "00-04", "00-05",
)

_ARCH_INTERNAL_LAYER_KEYS: Tuple[str, ...] = (
    "TARAMA", "TEFRIS", "SUPURGELIK", "TASLAR", "MOBILYA", "DOGRAMA",
    "DUVAR", "PENCERE", "SIVA", "DOSEME", "MERDIVEN", "YAZI_MIM", "MIMARI",
    "BANYO", "MUTFAK", "VITRIFIYE", "PEYZAJ", "ARAZI",
)
_RE_ARCH_TF_LAYER = re.compile(r"^(?:A[-_]?)?TF\d*$")
_ELEC_DETAIL_INTERNAL_KEYS: Tuple[str, ...] = (
    "00-04", "00-05", "00-06", "00-24V", "00-KOL_NO",
    "00-LINYE", "00-PANO", "00-AYD", "00-PRZ", "00-TEL", "00-TV", "00-TOPRAK",
    "E-POWR", "E-LITE", "E-COMM", "E-BORU",
)


def describe_wire_layer(layer_name: str) -> str:
    """Kablo / iletken katman adından mühendis için okunaklı evrensel hat tanımı üretir."""
    lu = norm_tr(layer_name).upper()
    if any(k in lu for k in ("TOPRAK", "SERIT", "GND", "EARTHING")):
        return f"Topraklama İletkeni / Şeridi ({layer_name})"
    if any(k in lu for k in ("AYD", "LITE")):
        return f"Aydınlatma Kablo / Sorti Hattı ({layer_name})"
    if any(k in lu for k in ("PRZ", "PRIZ", "POWR")):
        return f"Priz / Kuvvet Kablo Hattı ({layer_name})"
    if any(k in lu for k in ("YANGIN", "FIRE", "24V")):
        return f"Yangın Algılama / 24V Hattı ({layer_name})"
    if "INTERCOM" in lu or "DUAFON" in lu:
        return f"İntercom / Duafon Hattı ({layer_name})"
    if "TV" in lu or "UYDU" in lu:
        return f"TV / Uydu Anten Hattı ({layer_name})"
    if "TEL" in lu or "DATA" in lu or "COMM" in lu:
        return f"Telefon / Data Hattı ({layer_name})"
    if "00-06" in lu:
        return f"Kuvvet / Ek Tesisat ve Atlama Hattı ({layer_name})"
    return f"Elektrik Kablo / Tesisat Hattı ({layer_name})"
_RE_COVER_TITLEBLOCK = re.compile(r"^(?:BSL\d+|ANTET|BASLIK\d*)$")

_AMBIGUOUS_LAYERS: Set[str] = {"0", "", "DEFPOINTS", "ELKYAZ", "00-ELKYAZ", "YAZI"}

_RE_ANON_BLOCK = re.compile(r"^(?:A\$C[0-9A-F]+|\*[UX]\d+)$", re.IGNORECASE)
_RE_DIM_OR_TICK_BLOCK = re.compile(r"^(?:_DOT|\*X\d+|_OPEN\d*|_OBLIQUE|_ARCHTICK.*|OKK?|ARROW\d*)$", re.IGNORECASE)
_RE_BIM_VIEW_SUFFIX = re.compile(r"-(?:\d{3,10}|V\d+|_?RVT-\d+)-.*$", re.IGNORECASE)
_RE_XREF_BIND_PREFIX = re.compile(r"^.*\$0\$", re.IGNORECASE)
_RE_PLAN_TITLE = re.compile(
    r"(?:PLANI|PLAN\b|KAT\b|BODRUM|ZEM[Iİ]N|NORMAL|ASMA|[CÇ]ATI|TERAS|TOPRAKLAMA|TEMEL|VAZ[Iİ]YET|KES[Iİ]T)",
    re.IGNORECASE,
)


def _clean_block_core_name(blk_u: str) -> str:
    """Önce XREF bind ön ekini (`...$0$`), sonra BIM/Revit görünüm son ekini (`-123456-PRZ ...`) sıyırarak yaprak aile adını bırakır."""
    cleaned = _RE_XREF_BIND_PREFIX.sub("", blk_u.strip()).strip()
    cleaned = _RE_BIM_VIEW_SUFFIX.sub("", cleaned).strip()
    return cleaned or blk_u


def build_container_block_names(inserts: Sequence[RawInsert], du_to_m: float) -> Set[str]:
    """
    Blok adlarına ('FloorPlan-', '_RVT-' vb.) bağımlı kalmadan tamamen evrensel olarak
    fiziksel boyut ve topolojik ebeveyn-çocuk ağacından kapsayıcı (container) blokları bulur:
      1) Fiziksel boyutu sembol ölçeğini aşan makro bloklar (> 3.8 m kenar veya > 12 m² alan),
      2) Kendi içinde başka gerçek alt INSERT'ler barındıran (>= 1.5 m veya >= 2 farklı alt
         sembol içeren) hiyerarşik montaj / kat altlığı blokları.
    Böylece makro altlığın içindeki küçük yaprak ('leaf') cihaz sembolleri adı ne olursa
    olsun konteyner sanılıp elenmez.
    """
    scale = max(du_to_m, 1e-6)
    containers: Set[str] = set()
    block_max_dim: Dict[str, float] = {}
    children_by_parent: Dict[str, Set[str]] = defaultdict(set)

    for ins in inserts:
        bname = (ins.effective_name or ins.block_name).strip()
        if not bname:
            continue
        w_m = ins.bbox.width * scale
        h_m = ins.bbox.height * scale
        dim_m = max(w_m, h_m)
        if dim_m > block_max_dim.get(bname, 0.0):
            block_max_dim[bname] = dim_m
        if dim_m > 3.8 or (w_m * h_m) > 12.0:
            containers.add(bname)

        if ins.parent_chain:
            cname = ins.effective_name or ins.block_name
            if not is_dim_or_tick_subprimitive(cname) and not is_dim_or_tick_subprimitive(ins.block_name):
                for seg in ins.parent_chain.split(">"):
                    p_name = seg.strip()
                    if p_name:
                        children_by_parent[p_name].add(bname)

    for p_name, child_set in children_by_parent.items():
        p_dim = block_max_dim.get(p_name, 0.0)
        if p_dim >= 1.5 or len(child_set) >= 2:
            containers.add(p_name)

    return containers


def is_container_insert(
    ins: RawInsert,
    du_to_m: float,
    container_block_names: Optional[Set[str]] = None,
) -> bool:
    """Fiziksel boyut veya topolojik alt-blok hiyerarşisine göre kapsayıcı (makro) blok mu?"""
    scale = max(du_to_m, 1e-6)
    w_m = ins.bbox.width * scale
    h_m = ins.bbox.height * scale
    if max(w_m, h_m) > 3.8 or (w_m * h_m) > 12.0:
        return True
    if container_block_names is not None:
        bname = (ins.effective_name or ins.block_name).strip()
        return bname in container_block_names
    return False


def is_dim_or_tick_subprimitive(block_name: str) -> bool:
    """AutoCAD ölçü oku, nokta veya tik gibi yardımcı çizim alt bloğu mu?"""
    return bool(_RE_DIM_OR_TICK_BLOCK.match(block_name.strip()))


def is_clean_legend_desc(desc: str) -> bool:
    """Lejanttaki açıklama gerçek mühendislik tanımı mı yoksa kısa/gürültü etiketi mi?"""
    s = desc.strip()
    if len(s) < 4:
        return False
    if re.match(r"^(?:[\d/]+|[a-zçğıöşü]\s+[a-zçğıöşü\d]+)$", s.lower()):
        return False
    return True


def _match_category_discipline(text_upper: str) -> Optional[Tuple[str, str]]:
    if any(tk in text_upper for tk in ("REVIZYON", "REVISION TABLE", "ANTET", "TITLEBLOCK", "CARTIGLIO")):
        return None
    for keys, cat, disc in _POWER_LAYER_CATEGORY_RULES:
        for k in keys:
            pat = _RE_BOUNDARY_KEYS.get(k)
            if pat is not None:
                if pat.search(text_upper):
                    return cat, disc
            elif k in text_upper:
                return cat, disc
    return None


_NON_ARCH_CLONE_ROLES: Set[str] = {
    "KOLON_SEMASI", "TEK_HAT", "GERILIM_DUSUMU", "YUKLEME_CETVELI", "DUAFON_SEMASI", "LEJANT", "DETAY"
}


def _is_label_layer(layer_name: str) -> bool:
    lu = norm_tr(layer_name).upper()
    return any(k in lu for k in ("ELKYAZ", "YAZI"))


def _quick_view_discipline(inserts: List[RawInsert], paths: List[RawPath], role: str) -> str:
    if role == "TOPRAKLAMA":
        return "TOPRAKLAMA"
    counts: Counter[str] = Counter()
    tray_hits = 0
    for ins in inserts:
        bname = ins.effective_name or ins.block_name
        rule = _match_category_discipline(norm_tr(bname).upper()) or _match_category_discipline(norm_tr(ins.layer).upper())
        if rule is not None:
            if rule[0] == "KABLO TAVA / TAŞIYICI":
                tray_hits += 1
            elif rule[1] in ("KUVVETLI_AKIM", "ZAYIF_AKIM", "TOPRAKLAMA", "SINYAL"):
                counts[rule[1]] += 1
    if not counts and tray_hits > 0:
        counts["KUVVETLI_AKIM"] += tray_hits
    for p in paths:
        if _is_label_layer(p.layer):
            continue
        lu = norm_tr(p.layer).upper()
        if any(k in lu for k in ("CERCEVE", "ANTET")):
            continue
        rule = _match_category_discipline(lu)
        if rule is not None and rule[1] in ("KUVVETLI_AKIM", "ZAYIF_AKIM", "TOPRAKLAMA"):
            counts[rule[1]] += 1
    return counts.most_common(1)[0][0] if counts else "SALT_MIMARI"


def detect_cloned_architectural_entities(
    view_bundles: List[Dict[str, Any]],
    du_to_m: float,
) -> Tuple[Set[int], Set[int]]:
    """
    Aynı binanın farklı görünümleri (Kuvvetli Akım, Zayıf Akım, Topraklama, çerçevesiz kopyalar)
    arasında öteleme vektörünü (`(dX, dY)`) oylayıp `scipy.spatial.cKDTree` (`query_ball_point`)
    ile birebir çakışan çizgi (`id(RawPath)`) ve blok (`id(RawInsert)`) kopyalarını mimari altlık
    olarak tespit eder. Aynı disiplinli kopyalarda elektrik sembolüne temas eden hatları korur.
    """
    du_to_m_safe = max(du_to_m, 1e-6)
    min_sig_len_du = 0.25 / du_to_m_safe
    min_shift_du = 1.0 / du_to_m_safe
    bucket_du = max(0.25 / du_to_m_safe, 1.0)
    tol_du = max(0.08 / du_to_m_safe, 1.0)
    snap_du = max(0.35 / du_to_m_safe, 1.0)

    prepared: List[Dict[str, Any]] = []
    for vb in view_bundles:
        role = vb.get("role", "")
        if role in _NON_ARCH_CLONE_ROLES:
            continue
        top_paths: List[RawPath] = [
            p for p in vb.get("paths", [])
            if not p.parent_chain and not _is_label_layer(p.layer)
        ]
        if len(top_paths) < 4:
            continue
        sigs: Dict[Tuple[str, float, float, float], List[Tuple[float, float]]] = defaultdict(list)
        for p in top_paths:
            if p.length_du < min_sig_len_du:
                continue
            sig = (
                p.dxftype,
                round(p.bbox.width * du_to_m, 2),
                round(p.bbox.height * du_to_m, 2),
                round(p.length_du * du_to_m, 2),
            )
            sigs[sig].append(p.bbox.center)
        if len(sigs) < 3:
            continue

        arr_p = np.array(
            [[p.bbox.center[0], p.bbox.center[1], p.bbox.width, p.bbox.height] for p in top_paths],
            dtype=np.float64,
        )
        inserts: List[RawInsert] = list(vb.get("inserts", []))
        ins_arr = (
            np.array([[ins.x, ins.y] for ins in inserts], dtype=np.float64)
            if inserts
            else None
        )
        prepared.append({
            "disc": _quick_view_discipline(inserts, top_paths, role),
            "top_paths": top_paths,
            "sigs": sigs,
            "arr_p": arr_p,
            "tree_p": cKDTree(arr_p),
            "inserts": inserts,
            "ins_arr": ins_arr,
            "tree_ins": cKDTree(ins_arr) if ins_arr is not None else None,
        })

    cloned_path_ids: Set[int] = set()
    cloned_insert_ids: Set[int] = set()
    if len(prepared) < 2:
        return cloned_path_ids, cloned_insert_ids

    def _touches_cloned_symbol(path_obj: RawPath, sym_list: List[RawInsert], sym_tree: Optional[STRtree]) -> bool:
        if sym_tree is None or len(path_obj.points) < 2:
            return False
        q_bb = box(
            path_obj.bbox.minx - snap_du,
            path_obj.bbox.miny - snap_du,
            path_obj.bbox.maxx + snap_du,
            path_obj.bbox.maxy + snap_du,
        )
        hits = sym_tree.query(q_bb)
        if len(hits) == 0:
            return False
        ls = LineString(path_obj.points)
        return any(ls.distance(Point(sym_list[int(hi)].x, sym_list[int(hi)].y)) <= snap_du for hi in hits)

    for i in range(len(prepared)):
        va = prepared[i]
        sigs_a = va["sigs"]
        for j in range(i + 1, len(prepared)):
            vb = prepared[j]
            sigs_b = vb["sigs"]
            common = [s for s in sigs_a if s in sigs_b]
            if len(common) < 3:
                continue

            # Az tekrarlı (ayırt edici) şekil imzalarını öne alarak öteleme oylaması yap
            common.sort(key=lambda s: len(sigs_a[s]) * len(sigs_b[s]))
            buckets: Dict[Tuple[int, int], List[Tuple[float, float]]] = defaultdict(list)
            pair_votes = 0
            for s in common:
                pts_a = sigs_a[s]
                pts_b = sigs_b[s]
                if len(pts_a) > 25 or len(pts_b) > 25:
                    continue
                for ax, ay in pts_a:
                    for bx, by in pts_b:
                        dx = bx - ax
                        dy = by - ay
                        if abs(dx) + abs(dy) <= min_shift_du:
                            continue
                        buckets[(int(round(dx / bucket_du)), int(round(dy / bucket_du)))].append((dx, dy))
                        pair_votes += 1
                if pair_votes >= 3500:
                    break

            if not buckets:
                continue
            best_bk, best_vals = max(buckets.items(), key=lambda kv: len(kv[1]))
            if len(best_vals) < 2:
                continue

            cand_deltas: List[Tuple[float, float]] = [
                v
                for ox in (-1, 0, 1)
                for oy in (-1, 0, 1)
                for v in buckets.get((best_bk[0] + ox, best_bk[1] + oy), ())
            ]
            m_dx = statistics.median(v[0] for v in cand_deltas)
            m_dy = statistics.median(v[1] for v in cand_deltas)
            within = [
                v for v in cand_deltas
                if abs(v[0] - m_dx) <= 0.6 * bucket_du and abs(v[1] - m_dy) <= 0.6 * bucket_du
            ]
            if len(within) < 4:
                continue

            shift_x = statistics.median(v[0] for v in within)
            shift_y = statistics.median(v[1] for v in within)
            if abs(shift_x) + abs(shift_y) <= min_shift_du:
                continue

            # Önce 2B cKDTree ile aynı blok adına sahip kopya INSERT nesnelerini eşle
            pair_cloned_a: List[RawInsert] = []
            pair_cloned_b: List[RawInsert] = []
            if va["ins_arr"] is not None and vb["tree_ins"] is not None:
                q_ins = va["ins_arr"].copy()
                q_ins[:, 0] += shift_x
                q_ins[:, 1] += shift_y
                matches = vb["tree_ins"].query_ball_point(q_ins, r=tol_du)
                ins_a = va["inserts"]
                ins_b = vb["inserts"]
                seen_a_ins: Set[int] = set()
                seen_b_ins: Set[int] = set()
                for ai, b_list in enumerate(matches):
                    if not b_list:
                        continue
                    bn_a = (ins_a[ai].effective_name or ins_a[ai].block_name).strip().lower()
                    for bi in b_list:
                        bn_b = (ins_b[bi].effective_name or ins_b[bi].block_name).strip().lower()
                        if bn_a == bn_b:
                            if ai not in seen_a_ins:
                                seen_a_ins.add(ai)
                                pair_cloned_a.append(ins_a[ai])
                            if bi not in seen_b_ins:
                                seen_b_ins.add(bi)
                                pair_cloned_b.append(ins_b[bi])
                            cloned_insert_ids.add(id(ins_a[ai]))
                            cloned_insert_ids.add(id(ins_b[bi]))

            same_disc = va["disc"] == vb["disc"] and va["disc"] != "SALT_MIMARI"
            tree_sym_a = (
                STRtree([box(ins.x - snap_du, ins.y - snap_du, ins.x + snap_du, ins.y + snap_du) for ins in pair_cloned_a])
                if (same_disc and pair_cloned_a)
                else None
            )
            tree_sym_b = (
                STRtree([box(ins.x - snap_du, ins.y - snap_du, ins.x + snap_du, ins.y + snap_du) for ins in pair_cloned_b])
                if (same_disc and pair_cloned_b)
                else None
            )

            # 4B cKDTree [cx, cy, w, h] küre sorgusu (query_ball_point) ile çakışan tüm çizgileri yakala
            q_p = va["arr_p"].copy()
            q_p[:, 0] += shift_x
            q_p[:, 1] += shift_y
            ball_idxs = vb["tree_p"].query_ball_point(q_p, r=tol_du, p=np.inf)
            top_a = va["top_paths"]
            top_b = vb["top_paths"]
            for ai, b_list in enumerate(ball_idxs):
                if not b_list:
                    continue
                pa = top_a[ai]
                for bi in b_list:
                    pb = top_b[bi]
                    if pa.dxftype == pb.dxftype or abs(pa.length_du - pb.length_du) <= 2.0 * tol_du:
                        if same_disc:
                            # Aynı disiplin kopyasında yalnızca elektrik sembolüne temas etmeyen '0' çizgilerini altlık say
                            if norm_tr(pa.layer).upper() == "0" and not _touches_cloned_symbol(pa, pair_cloned_a, tree_sym_a):
                                cloned_path_ids.add(id(pa))
                            if norm_tr(pb.layer).upper() == "0" and not _touches_cloned_symbol(pb, pair_cloned_b, tree_sym_b):
                                cloned_path_ids.add(id(pb))
                        else:
                            cloned_path_ids.add(id(pa))
                            cloned_path_ids.add(id(pb))

    return cloned_path_ids, cloned_insert_ids


def classify_insert_role(
    ins: RawInsert,
    legend: Dict[str, LegendEntry],
    cloned_insert_ids: Optional[Set[int]] = None,
) -> Tuple[str, str, str, str, str]:
    """
    Bir INSERT bloğunu evrensel kanıtlara göre sınıflandırır.
    Dönüş: (role_group, category, discipline, desc, desc_source)
      - role_group: 'ARCHITECTURAL' | 'ELECTRICAL' | 'UNCERTAIN'
      - discipline: 'MIMARI' | 'KUVVETLI_AKIM' | 'ZAYIF_AKIM' | 'TOPRAKLAMA' | 'BELIRSIZ'
    """
    bname = ins.effective_name or ins.block_name
    lay_u = norm_tr(ins.layer).upper()
    blk_u = norm_tr(bname).upper()
    blk_core_u = _clean_block_core_name(blk_u)
    chain_u = norm_tr(ins.parent_chain).upper() if ins.parent_chain else ""
    leg = legend.get(bname) or legend.get(bname.strip()) or legend.get(bname.strip().lower())
    has_leg = leg is not None and is_clean_legend_desc(leg.description)
    leg_rule = _match_category_discipline(norm_tr(leg.description).upper()) if (has_leg and leg is not None) else None
    int_lays_u = [norm_tr(il).upper() for il in getattr(ins, "internal_layers", []) if il]
    has_arch_internal = any(
        any(k in il_u for k in _ARCH_INTERNAL_LAYER_KEYS) or bool(_RE_ARCH_TF_LAYER.match(il_u))
        for il_u in int_lays_u
    )
    has_elec_detail_internal = any(
        any(k in il_u for k in _ELEC_DETAIL_INTERNAL_KEYS)
        for il_u in int_lays_u
    )
    is_cover_titleblock = (
        bool(_RE_COVER_TITLEBLOCK.match(blk_u))
        or any(tk in blk_u for tk in ("ANTET", "TITLEBLOCK", "KAPAK"))
    )

    # 0. Ölçü oku/tik veya açık mimari/statik/mekanik model ya da antet kapsayıcısı
    if is_dim_or_tick_subprimitive(blk_core_u) or is_dim_or_tick_subprimitive(bname):
        return "ARCHITECTURAL", "MIMARI_TEFRIS", "MIMARI", f"Ölçü/İşaret '{bname}'", "KATMAN_ADI"
    if (
        chain_u
        and any(mk in chain_u for mk in ("-ARC-", "-STR-", "-MEC-", "ANTET", "CERCEVE"))
        and not lay_u.startswith("E-")
        and not has_leg
    ):
        return "ARCHITECTURAL", "MIMARI_TEFRIS", "MIMARI", f"Mimari Altlık Elemanı '{bname}'", "KATMAN_ADI"

    # 1. Açık tefriş/mimari blok adları ve kapak antetleri
    blk_rule = _match_category_discipline(blk_core_u)
    is_arch_blk = any(k in blk_u for k in _ARCH_BLOCK_KEYS)
    arch_override = any(
        ak in blk_u
        for ak in (
            "ANTET", "CERCEVE", "TABLE", "MASA", "D4030_", "D2010_", "B1080_", "E2050_",
            "FIRE CABINET", "YANGIN DOLABI", "SWINGING", "LOCKER", "TOP RAIL", "BALUSTER",
            "LIFT ASSEMBLY", "STAIR", "LADDER", "MULLION", "FLOORS ", "DISPEN", "ESCALATOR",
            "VIEWTITLE", "SPACE TAG", "D_TAG_ROOM", "GRID HEAD", "D_DAT_GRID",
            "LEVEL HEAD", "D_DAT_LEVEL", "SECTION", "RAILING", "C2010_", "C30",
            "ARC-01", "STR-01", "MEC-01",
            "GLAZ", "CURTAIN", "BOOTH", "SOVE", "DRAINER", "PRECAST", "WALL OPENING",
            "LENTO", "HAT EKSEN", "GRENLI", "SPOT ELEVATION", "D_DAT_ELE",
            "-MEC-", "-ARC-", "-STR-",
        )
    )
    if is_cover_titleblock or (is_arch_blk and (blk_rule is None or arch_override)):
        return "ARCHITECTURAL", "MIMARI_TEFRIS", "MIMARI", f"Mimari/Tefriş '{bname}'", "KATMAN_ADI"

    # 1b. Blok içi katman analizi: elektrik katmanına yanlış konmuş tefriş/tarama blokları
    #     veya çerçeve/nötr katmana çizilmiş saf elektrik detay/şema blokları
    lay_rule = _match_category_discipline(lay_u)
    if has_arch_internal and not has_leg and blk_rule is None:
        return "ARCHITECTURAL", "MIMARI_TEFRIS", "MIMARI", f"Mimari İç Katman '{bname}' ({ins.layer})", "KATMAN_ADI"
    if has_elec_detail_internal and not has_arch_internal and not is_cover_titleblock and not has_leg and lay_rule is None:
        if blk_rule is not None:
            cat, disc = blk_rule
            return "ELECTRICAL", cat, disc, f"Elektrik Detay/Pano '{bname}' ({ins.layer})", "KATMAN_ADI"
        return "ELECTRICAL", "SEMA / DETAY", "KUVVETLI_AKIM", f"Elektrik Detay/Şema '{bname}' ({ins.layer})", "KATMAN_ADI"

    # 2. Açık elektrik blok veya elektrik katman adı (genel BIM fixtures katmanında blok adına öncelik ver)
    if lay_rule is not None:
        if any(gk in lay_u for gk in ("E-ELEC-FIXT", "E-ELEC-EQPM", "E-COMM")) and blk_rule is not None:
            cat, disc = leg_rule if leg_rule is not None else blk_rule
        else:
            cat, disc = leg_rule if leg_rule is not None else lay_rule
        if has_leg and leg is not None:
            return "ELECTRICAL", cat, disc, leg.description, "LEJANT"
        return "ELECTRICAL", cat, disc, f"{cat.title()} ({ins.layer})", "KATMAN_ADI"

    # 3. Açık mimari katman (blok adı elektrik veya Lejant değilse kesin mimari!)
    if any(k in lay_u for k in _ARCH_LAYER_KEYS):
        if blk_rule is not None and not any(k in blk_u for k in ("TABLE", "TEF", "LAMP")):
            cat, disc = blk_rule
            return "ELECTRICAL", cat, disc, f"Blok '{bname}'", "BLOK_ADI"
        return "ARCHITECTURAL", "MIMARI_TEFRIS", "MIMARI", f"Mimari '{bname}' ({ins.layer})", "KATMAN_ADI"

    # 4. Lejantta tanımlı elektrik sembolü
    if has_leg and leg is not None:
        d_rule = leg_rule or blk_rule
        if d_rule:
            cat, disc = d_rule
        else:
            cat, disc = "DİĞER ELEKTRİK", "KUVVETLI_AKIM"
        return "ELECTRICAL", cat, disc, leg.description, "LEJANT"

    # 5. Blok adı açıkça elektrik anahtarı içeriyorsa (katman belirsiz olsa bile)
    if blk_rule is not None:
        cat, disc = blk_rule
        return "ELECTRICAL", cat, disc, f"Blok '{bname}'", "BLOK_ADI"

    # 6. Katman adı 'E-' veya 'ELEKTRIK' ile başlıyorsa (anonim blok değilse)
    if (lay_u.startswith("E-") or lay_u == "ELEKTRIK") and not _RE_ANON_BLOCK.match(bname):
        return "ELECTRICAL", "DİĞER ELEKTRİK", "KUVVETLI_AKIM", f"Blok '{bname}' ({ins.layer})", "KATMAN_ADI"

    # 7. ATTRIB içinde pano/elektrik verisi varsa
    for k in ins.attribs:
        ku = norm_tr(k).upper()
        if any(tok in ku for tok in ("PANO", "PANEL", "TABLO", "LINYE", "SIGORTA", "AKIM")):
            return "ELECTRICAL", "PANO / TABLO", "KUVVETLI_AKIM", f"Pano/Ekipman '{ins.block_name}'", "ATTRIB"

    # 8. Kopya çakıştırma (cKDTree) ile farklı görünümlerde tekrar ettiği kanıtlanan tanımsız/anonim blok mimaridir
    if cloned_insert_ids and id(ins) in cloned_insert_ids:
        return "ARCHITECTURAL", "MIMARI_TEFRIS", "MIMARI", f"Mimari Kopya '{ins.block_name}' ({ins.layer})", "KOPYA_CAKISTIRMA"

    # 9. Anonim veya bilinmeyen katmandaki kanıtsız bloklar (sahte elektrik sayılmaz!)
    return "UNCERTAIN", "BELIRSIZ_ANONIM", "BELIRSIZ", f"Tanımsız/Anonim Blok '{ins.block_name}' ({ins.layer})", "BELIRSIZ"


def _is_door_arc(p: RawPath, du_to_m: float) -> bool:
    return (
        p.dxftype == "ARC"
        and p.radius_du is not None
        and p.arc_sweep_deg is not None
        and 70.0 <= abs(p.arc_sweep_deg) <= 110.0
        and 0.55 <= (p.radius_du * du_to_m) <= 1.35
    )


def detect_architectural_shapes(
    paths: Sequence[RawPath],
    du_to_m: float,
    elec_symbol_pts: Optional[np.ndarray] = None,
) -> Set[int]:
    """
    Katman adlarına HİÇ bakmadan, yalnızca vektör şekillerinden mimari/yapısal çizgileri tanır:
      1) Çift çizgili paralel duvar / perde / kiriş / bağ hatılı çiftleri
         (uzunluk >= 0.50 m, paralel <= 2.5°, dik aralık 0.06–0.55 m, boyca >= %50 örtüşme;
         iki ucu da elektrik sembolüne bağlı kablo çiftleri hariç),
      2) Merdiven basamağı dizileri (>= 5 eşit aralıklı 0.18–0.42 m paralel basamak, 0.6–4.0 m),
      3) Patlatılmış sık paralel tarama dizileri (>= 6 paralel çizgi, aralık <= 0.14 m).
    Dönüş: `paths` içindeki mimari şekil indeksleri (`Set[int]`).
    """
    arch_idxs: Set[int] = set()
    if not paths:
        return arch_idxs

    du_m = max(du_to_m, 1e-6)
    sym_tree = cKDTree(elec_symbol_pts) if (elec_symbol_pts is not None and len(elec_symbol_pts) > 0) else None
    sym_tol_du = max(0.30 / du_m, 0.5)

    # 2 noktalı düz çizgileri (veya düz segmentli 2-noktalı poligonları) çıkar
    segs: List[Tuple[int, float, float, float, float, float, float, float, float]] = []
    # (orig_idx, x1, y1, x2, y2, mx, my, len_m, ang_deg_0_180)
    for idx, p in enumerate(paths):
        if len(p.points) != 2 or p.is_circle or p.dxftype == "ARC":
            continue
        (x1, y1), (x2, y2) = p.points[0], p.points[1]
        dx = x2 - x1
        dy = y2 - y1
        len_du = math.hypot(dx, dy)
        len_m = len_du * du_m
        if len_m < 0.08 or len_m > 120.0:
            continue
        ang = math.degrees(math.atan2(dy, dx)) % 180.0
        segs.append((idx, x1, y1, x2, y2, (x1 + x2) * 0.5, (y1 + y2) * 0.5, len_m, ang))

    if len(segs) < 2:
        return arch_idxs

    # Açı kovalarına (3° adım) bölerek paralel eşleştirme: O(N log N)
    by_ang: Dict[int, List[int]] = defaultdict(list)
    for si, s in enumerate(segs):
        b = int(round(s[8] / 3.0)) % 60
        by_ang[b].append(si)

    # 1) Paralel çift çizgili duvar / kiriş / bağ hatılı tespiti
    wall_cand_local = [si for si, s in enumerate(segs) if s[7] >= 0.50]
    if len(wall_cand_local) >= 2:
        w_mids = np.array([[segs[si][5], segs[si][6]] for si in wall_cand_local], dtype=np.float64)
        w_tree = cKDTree(w_mids)
        # Orta noktalar arası mesafe en fazla (max_len/2 + 0.6 m); makul duvar arama yarıçapı 6.0 m
        search_r = max(6.0 / du_m, 1.0)
        for wi, si in enumerate(wall_cand_local):
            orig_i, x1, y1, x2, y2, mx1, my1, l1_m, a1 = segs[si]
            ux = (x2 - x1) / max(math.hypot(x2 - x1, y2 - y1), 1e-9)
            uy = (y2 - y1) / max(math.hypot(x2 - x1, y2 - y1), 1e-9)
            t1_a = x1 * ux + y1 * uy
            t1_b = x2 * ux + y2 * uy
            if t1_a > t1_b:
                t1_a, t1_b = t1_b, t1_a
            n1 = -x1 * uy + y1 * ux

            nbrs = w_tree.query_ball_point(w_mids[wi], r=min(search_r, max(l1_m, 1.0) / du_m))
            for wj in nbrs:
                if wj <= wi:
                    continue
                sj = wall_cand_local[wj]
                orig_j, jx1, jy1, jx2, jy2, _, _, l2_m, a2 = segs[sj]
                da = abs(a1 - a2)
                if da > 90.0:
                    da = 180.0 - da
                if da > 2.5:
                    continue
                n2 = -jx1 * uy + jy1 * ux
                d_perp_m = abs(n2 - n1) * du_m
                if not (0.06 <= d_perp_m <= 0.55):
                    continue
                t2_a = jx1 * ux + jy1 * uy
                t2_b = jx2 * ux + jy2 * uy
                if t2_a > t2_b:
                    t2_a, t2_b = t2_b, t2_a
                ov_du = min(t1_b, t2_b) - max(t1_a, t2_a)
                min_len_du = min(t1_b - t1_a, t2_b - t2_a)
                if min_len_du <= 1e-6 or (ov_du / min_len_du) < 0.50:
                    continue
                # Güvenlik: her iki segmentin uçları doğrudan elektrik sembolüne bağlıysa paralel kablo olabilir, atla
                if sym_tree is not None:
                    d_end_i = min(
                        float(sym_tree.query([x1, y1])[0]),
                        float(sym_tree.query([x2, y2])[0]),
                    )
                    d_end_j = min(
                        float(sym_tree.query([jx1, jy1])[0]),
                        float(sym_tree.query([jx2, jy2])[0]),
                    )
                    if d_end_i <= sym_tol_du and d_end_j <= sym_tol_du and max(l1_m, l2_m) < 2.0:
                        continue
                arch_idxs.add(orig_i)
                arch_idxs.add(orig_j)

    # 2) Merdiven basamağı dizileri (>= 5 eşit aralıklı paralel basamak) & patlatılmış sık taramalar
    for b_key, s_idxs in by_ang.items():
        if len(s_idxs) < 5:
            continue
        ang_rad = math.radians(b_key * 3.0)
        ux, uy = math.cos(ang_rad), math.sin(ang_rad)
        # Segmentleri uzunluk eksenindeki projeksiyon (merkez) ve dik eksendeki konum (n) ile grupla
        proj_items = []
        for si in s_idxs:
            orig_i, x1, y1, x2, y2, mx, my, lm, _ = segs[si]
            t_mid = (mx * ux + my * uy) * du_m
            n_val = (-mx * uy + my * ux) * du_m
            proj_items.append((t_mid, n_val, lm, orig_i))
        # t_mid'e göre yakınsayan kolonlara ayır (aynı merdiven kolu veya tarama şeridi)
        proj_items.sort(key=lambda r: r[0])
        col_group: List[Tuple[float, float, float, int]] = [proj_items[0]]

        def _flush_group(grp: List[Tuple[float, float, float, int]]) -> None:
            if len(grp) < 5:
                return
            grp.sort(key=lambda r: r[1])
            # Ardışık eşit aralıklı alt dizileri tara
            run: List[Tuple[float, float, float, int]] = [grp[0]]
            for item in grp[1:]:
                prev = run[-1]
                dn = item[1] - prev[1]
                len_ratio = min(item[2], prev[2]) / max(item[2], prev[2], 1e-6)
                if 0.005 <= dn <= 0.45 and len_ratio >= 0.72:
                    run.append(item)
                else:
                    _eval_run(run)
                    run = [item]
            _eval_run(run)

        def _eval_run(run: List[Tuple[float, float, float, int]]) -> None:
            if len(run) < 5:
                return
            gaps = [run[k + 1][1] - run[k][1] for k in range(len(run) - 1)]
            med_gap = statistics.median(gaps)
            med_len = statistics.median(r[2] for r in run)
            # Merdiven basamağı: >= 5 basamak, 0.18–0.42 m eşit aralık, 0.60–4.5 m genişlik
            is_stair = (
                0.17 <= med_gap <= 0.43
                and 0.55 <= med_len <= 4.5
                and sum(1 for g in gaps if abs(g - med_gap) <= max(0.06, med_gap * 0.25)) >= int(len(gaps) * 0.75)
            )
            # Patlatılmış tarama: >= 6 sık paralel çizgi (<= 0.14 m aralık)
            is_hatch = len(run) >= 6 and med_gap <= 0.14
            if is_stair or is_hatch:
                for _, _, _, o_idx in run:
                    arch_idxs.add(o_idx)

        for item in proj_items[1:]:
            if abs(item[0] - col_group[-1][0]) <= 0.45:
                col_group.append(item)
            else:
                _flush_group(col_group)
                col_group = [item]
        _flush_group(col_group)

    return arch_idxs


def classify_paths_arch_vs_elec(
    paths: List[RawPath],
    elec_inserts: List[RawInsert],
    du_to_m: float,
    cloned_path_ids: Optional[Set[int]] = None,
    container_block_names: Optional[Set[str]] = None,
) -> Dict[str, List[RawPath]]:
    """
    Çizgisel nesneleri ('LINE', 'LWPOLYLINE', 'ARC', vb.) MİMARİ ALTLIK vs. ELEKTRİK HATTI
    olarak ayırır:
      1) Blok içi çizgilerde: küçük elektrik sembolünün iç ikonu atlanır; birleşik kat planı /
         tefriş / kapı bloklarının iç çizgileri mimariye (veya E-BORU/E-COMM kablo hattına) alınır.
      2) Kapı salınım yayı ve açık mimari katmanlar -> ARCHITECTURAL
      3) Açık elektrik kablo/hat katmanları -> ELECTRICAL_WIRE
      4) Kopya çakıştırma (`cKDTree` ile başka görünümlerde birebir tekrar eden altlık) -> ARCHITECTURAL
      5) Karışık katmanda (`0` vb.): elektrik sembollerine fiziksel temas (`STRtree`) ve
         uç noktalar (`p.points[0]`, `p.points[-1]`) üzerinden `cKDTree` ile 2-hop zincirleme hat takibi.
    """
    res: Dict[str, List[RawPath]] = {"ARCHITECTURAL": [], "ELECTRICAL_WIRE": [], "UNCERTAIN": []}
    if not paths:
        return res

    du_to_m_safe = max(du_to_m, 1e-6)
    snap_du = max(0.35 / du_to_m_safe, 1.0)
    ins_geoms = [
        box(ins.x - snap_du, ins.y - snap_du, ins.x + snap_du, ins.y + snap_du)
        for ins in elec_inserts
    ]
    ins_tree = STRtree(ins_geoms) if ins_geoms else None

    elec_sym_blocks: Set[str] = set()
    for ins in elec_inserts:
        if is_container_insert(ins, du_to_m, container_block_names=container_block_names):
            continue
        if ins.effective_name:
            elec_sym_blocks.add(ins.effective_name)
        if ins.block_name:
            elec_sym_blocks.add(ins.block_name)

    mixed_paths: List[RawPath] = []
    for p in paths:
        lay_u = norm_tr(p.layer).upper()

        # 0) Blok içinden gelen alt çizgiler: küçük elektrik ikonlarını atla, birleşik kat/mimari blokları koru
        if p.parent_chain:
            leaf_blk = p.parent_chain.split(">")[-1].strip()
            if p.owner_block in elec_sym_blocks or leaf_blk in elec_sym_blocks:
                continue
            chain_u = norm_tr(p.parent_chain).upper()
            if _is_door_arc(p, du_to_m):
                res["ARCHITECTURAL"].append(p)
                continue
            if (
                cloned_path_ids
                and id(p) in cloned_path_ids
                and not lay_u.startswith(("00-", "E-", "PRT-EL-"))
            ):
                res["ARCHITECTURAL"].append(p)
                continue
            if (
                any(k in lay_u for k in ("00-06", "00-24V"))
            ) and not (
                _RE_COVER_TITLEBLOCK.match(chain_u)
                or any(tk in chain_u for tk in ("ANTET", "TITLEBLOCK", "KAPAK"))
                or any(k in chain_u for k in _ARCH_BLOCK_KEYS)
            ):
                if (
                    not any(ak in lay_u for ak in _NON_WIRE_ANNOTATION_KEYS)
                    and "PANO" not in lay_u
                    and not p.is_circle
                    and (p.length_du * du_to_m) >= 0.05
                ):
                    res["ELECTRICAL_WIRE"].append(p)
                continue
            if lay_u in ("KOLON", "KOLONLAR", "STATIK_KOLON", "BETON_KOLON"):
                res["ARCHITECTURAL"].append(p)
                continue
            if (
                not any(ak in lay_u for ak in _NON_WIRE_ANNOTATION_KEYS)
                and not any(ek in lay_u for ek in ("FIXT", "EQPM", "PANO"))
                and not p.is_circle
            ):
                is_inblk_wire = (
                    "E-BORU" in chain_u
                    or "E-CABL" in chain_u
                    or lay_u.startswith(("E-COMM", "E-BORU", "PRT-EL-", "YP-EL"))
                    or (
                        _matches_wire_layer_key(lay_u)
                        and not (lay_u == "TOPRAK" and any(k in chain_u for k in _ARCH_BLOCK_KEYS))
                    )
                )
                if is_inblk_wire and (p.length_du * du_to_m) >= 0.05:
                    res["ELECTRICAL_WIRE"].append(p)
                    continue
            if any(ak in lay_u for ak in _NON_WIRE_ANNOTATION_KEYS) and not any(k in chain_u for k in _ARCH_BLOCK_KEYS):
                res["UNCERTAIN"].append(p)
                continue
            res["ARCHITECTURAL"].append(p)
            continue

        # 1) Kapı salınım yayı her zaman mimaridir (katmandan bağımsız)
        if _is_door_arc(p, du_to_m):
            res["ARCHITECTURAL"].append(p)
            continue

        # 2) Kopya çakıştırma (cKDTree): duvar/doğrama üstüne elektrik/topraklama katmanı binmiş olsa bile mimaridir
        #    (resmi elektrik ön-ekleri '00-', 'E-', 'PRT-EL-' hariç)
        if (
            cloned_path_ids
            and id(p) in cloned_path_ids
            and not lay_u.startswith(("00-", "E-", "PRT-EL-", "YP-EL"))
        ):
            res["ARCHITECTURAL"].append(p)
            continue

        # 3) Açık mimari/yapısal AIA/ISO ön-ekleri ve HATCH ('HATCH' içindeki 'HAT' alt-dizisi elektrik kablosu değildir!)
        if (
            lay_u.startswith(("A-", "A_", "I-", "I_", "S-", "S_", "M-", "M_", "G-PLAN"))
            or "HATCH" in lay_u
            or "TARAMA" in lay_u
        ) and not lay_u.startswith(("E-", "E_", "EE-", "00-", "PRT-EL-", "PRT-EL_", "PRT_", "YP-EL")):
            res["ARCHITECTURAL"].append(p)
            continue

        # 3B) Açık elektrik kablo/hat katmanları (ekipman/cihaz katmanları FIXT/EQPM ve açıklama/tablo katmanları hariç)
        if any(ak in lay_u for ak in _NON_WIRE_ANNOTATION_KEYS):
            res["UNCERTAIN"].append(p)
            continue

        is_wire_layer = (
            (lay_u.startswith(("E-", "E_", "EE-", "PRT-EL-", "PRT-EL_", "PRT_", "YP-EL")) and not any(ek in lay_u for ek in ("FIXT", "EQPM")))
            or _matches_wire_layer_key(lay_u)
        )
        if is_wire_layer:
            res["ELECTRICAL_WIRE"].append(p)
            continue

        # 4) Açık mimari katmanları (kelime sınırıyla; yapısal 'kolon' katmanı dahil)
        if _matches_arch_layer_key(lay_u) or lay_u in ("KOLON", "KOLONLAR", "STATIK_KOLON", "BETON_KOLON"):
            res["ARCHITECTURAL"].append(p)
            continue

        mixed_paths.append(p)

    # 4B) Saf Şekil & Morfoloji Tespiti (Katman adı ne olursa olsun: çift çizgili duvar/kiriş/hatıl, merdiven, tarama)
    sym_pts_arr = (
        np.array([[ins.x, ins.y] for ins in elec_inserts], dtype=np.float64)
        if elec_inserts
        else None
    )
    shape_arch_idxs = detect_architectural_shapes(mixed_paths, du_to_m_safe, elec_symbol_pts=sym_pts_arr)

    # 5) Karışık katman ('0' veya bilinmeyen katmanlar): sembol teması (STRtree) + 2-hop uç nokta zinciri (cKDTree)
    wire_set: Set[int] = set()
    cand_idxs: List[int] = []
    for mi, p in enumerate(mixed_paths):
        if mi in shape_arch_idxs:
            continue
        lu_m = norm_tr(p.layer).upper()
        if any(ak in lu_m for ak in _NON_WIRE_ANNOTATION_KEYS):
            continue
        if len(p.points) >= 2 and 0.08 <= (p.length_du * du_to_m) <= 120.0:
            cand_idxs.append(mi)

    if cand_idxs and ins_tree is not None:
        for mi in cand_idxs:
            p = mixed_paths[mi]
            q_bb = box(p.bbox.minx - snap_du, p.bbox.miny - snap_du, p.bbox.maxx + snap_du, p.bbox.maxy + snap_du)
            hits = ins_tree.query(q_bb)
            if len(hits) > 0:
                ls = LineString(p.points)
                if any(ls.distance(Point(elec_inserts[int(ci)].x, elec_inserts[int(ci)].y)) <= snap_du for ci in hits):
                    wire_set.add(mi)

        if wire_set:
            ep_coords: List[Tuple[float, float]] = []
            ep_owners: List[int] = []
            for mi in cand_idxs:
                pts = mixed_paths[mi].points
                ep_coords.append(pts[0])
                ep_owners.append(mi)
                ep_coords.append(pts[-1])
                ep_owners.append(mi)
            ep_tree = cKDTree(np.array(ep_coords, dtype=np.float64))
            ep_tol = max(0.20 / du_to_m_safe, 1.0)
            frontier = sorted(wire_set)
            for _hop in range(2):
                if not frontier:
                    break
                q_pts: List[Tuple[float, float]] = []
                for mi in frontier:
                    pts = mixed_paths[mi].points
                    q_pts.append(pts[0])
                    q_pts.append(pts[-1])
                nbr_lists = ep_tree.query_ball_point(np.array(q_pts, dtype=np.float64), r=ep_tol)
                next_frontier: List[int] = []
                for nlist in nbr_lists:
                    for ei in nlist:
                        nb_mi = ep_owners[ei]
                        if nb_mi not in wire_set:
                            wire_set.add(nb_mi)
                            next_frontier.append(nb_mi)
                frontier = next_frontier

    for mi, p in enumerate(mixed_paths):
        if mi in shape_arch_idxs:
            res["ARCHITECTURAL"].append(p)
        elif mi in wire_set:
            res["ELECTRICAL_WIRE"].append(p)
        elif norm_tr(p.layer).upper() in _AMBIGUOUS_LAYERS:
            res["UNCERTAIN"].append(p)
        else:
            res["ARCHITECTURAL"].append(p)

    return res


def parse_floor_label(text: str, role: str = "") -> str:
    """Başlıktan kat/bölüm adını evrensel olarak çıkarır."""
    tu = norm_tr(text).upper()
    if any(k in tu for k in ("LEJANT", "SEMBOL LIST")):
        return "Lejant"
    if any(k in tu for k in ("KOLON", "TEK HAT", "GERILIM DUSUM", "YUKLEME CETV")):
        return "Şema / Hesap"
    if any(k in tu for k in ("VAZIYET", "TOPRAKLAMA", "TEMEL TOPRAK")):
        return "Temel / Vaziyet"
    m_bod = re.search(r"(\d+\s*\.\s*)?BODRUM(?:\s+KAT)?", tu)
    if m_bod:
        prefix = m_bod.group(1).strip() if m_bod.group(1) else ""
        return f"{prefix} Bodrum Kat".strip()
    if "ZEMIN" in tu or "ZEMİN" in tu:
        return "Zemin Kat"
    if "ASMA" in tu:
        return "Asma Kat"
    m_rng = re.search(r"(\d+(?:\s*[-–,./]\s*\d+)*\s*\.\s*KAT)", tu)
    if m_rng:
        return re.sub(r"\s+", "", m_rng.group(1)).replace(".", ". ").strip().title()
    if "NORMAL KAT" in tu:
        return "Normal Kat"
    if "CATI" in tu or "TERAS" in tu:
        return "Çatı / Teras"
    if "TEKNIK KAT" in tu:
        return "Teknik Kat"
    if "BILET HOLU" in tu:
        return "Bilet Holü Katı"
    if "PERON ALTI" in tu:
        return "Peron Altı Katı"
    if "PERON KAT" in tu or "PERON" in tu:
        return "Peron Katı"
    if "ARA KAT" in tu:
        return "Ara Kat"
    if "SAFT" in tu:
        return "Elektrik Şaftı"
    if "EKIPMAN ODASI" in tu:
        return "Ekipman Odası"
    if "DETAY" in tu:
        return "Detay"
    if role == "TOPRAKLAMA":
        return "Temel / Vaziyet"
    if role in ("KOLON_SEMASI", "TEK_HAT", "GERILIM_DUSUMU"):
        return "Şema / Hesap"
    if role == "LEJANT":
        return "Lejant"
    if role == "DETAY":
        return "Detay"
    return "Genel / Diğer"


def infer_view_discipline(
    title: str,
    sheet_role: str,
    elec_disciplines: Counter,
    elec_wire_count: int,
    has_grounding_loop: bool = False,
) -> str:
    """
    Başlık + bölgenin içindeki gerçek elektrik nesnelerine bakarak disiplini belirler.
    İçerikte hiç elektrik yoksa dürüstçe 'SALT_MIMARI_ALTLIK' döndürür.
    """
    tu = norm_tr(title).upper()
    total_elec = sum(elec_disciplines.values())

    if sheet_role in ("KOLON_SEMASI", "TEK_HAT", "GERILIM_DUSUMU", "YUKLEME_CETVELI"):
        return "SEMA_HESAP"
    if sheet_role in ("LEJANT", "DETAY"):
        return "LEJANT_DETAY"

    if has_grounding_loop or "TOPRAKLAMA" in tu or "VAZIYET" in tu:
        if total_elec == 0 and elec_wire_count == 0 and not has_grounding_loop and "VAZIYET" not in tu:
            return "SALT_MIMARI_ALTLIK"
        return "TOPRAKLAMA"

    if total_elec == 0 and elec_wire_count == 0 and sheet_role in ("", "KAT_PLANI", "DIGER"):
        return "SALT_MIMARI_ALTLIK"

    if any(k in tu for k in ("ZAYIF AKIM", "TELEFON", "TV", "DUAFON", "YANGIN")):
        return "ZAYIF_AKIM"
    if any(k in tu for k in ("KUVVETLI AKIM", "AYDINLATMA", "PRIZ")):
        return "KUVVETLI_AKIM"

    n_pow = elec_disciplines.get("KUVVETLI_AKIM", 0)
    n_weak = elec_disciplines.get("ZAYIF_AKIM", 0)
    n_gnd = elec_disciplines.get("TOPRAKLAMA", 0)
    if n_gnd > max(n_pow, n_weak) and n_gnd > 0:
        return "TOPRAKLAMA"
    if n_weak > 0 and n_pow == 0:
        return "ZAYIF_AKIM"
    if n_pow > 0 and n_weak == 0:
        return "KUVVETLI_AKIM"
    if n_pow > 0 and n_weak > 0:
        if min(n_pow, n_weak) >= 0.25 * max(n_pow, n_weak):
            return "KARMA_ELEKTRIK"
        return "KUVVETLI_AKIM" if n_pow >= n_weak else "ZAYIF_AKIM"
    if elec_wire_count > 0:
        return "KUVVETLI_AKIM"
    return "BELIRSIZ"


def find_below_title_for_sheet(
    sheet: SheetFrame,
    outside_texts: List[RawText],
    du_to_m: float,
) -> Optional[RawText]:
    """
    İçinde başlık yazısı olmayan çerçeveli bir planın (ör. kapalı betonarme kontur)
    tam alt kenarının hemen altında yer alan başlık metnini bulur.
    """
    b = sheet.bbox_du
    pad_x = max(0.20 * b.width, 3.0 / max(du_to_m, 1e-6))
    max_drop = max(0.85 * b.height, 8.0 / max(du_to_m, 1e-6))
    cands: List[RawText] = []
    for t in outside_texts:
        if (b.minx - pad_x) <= t.x <= (b.maxx + pad_x) and (b.miny - max_drop) <= t.y <= b.miny:
            if _RE_PLAN_TITLE.search(t.text) and len(t.text.strip()) >= 5:
                cands.append(t)
    if not cands:
        return None
    cx = (b.minx + b.maxx) * 0.5
    return min(cands, key=lambda t: (abs(b.miny - t.y), abs(t.x - cx) * 0.2, -t.height))


def partition_outside_regions(
    outside_texts: List[RawText],
    outside_inserts: List[RawInsert],
    outside_paths: List[RawPath],
    du_to_m: float,
    claimed_anchor_handles: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Çerçeve dışında (antetsiz) duran kat/topraklama planlarını **altlarındaki
    başlık metinlerini** çıpa alarak geometrik Voronoi bölgelerine ayırır.
    Başlık dışı artıkları sıkı (2.5 m) ızgarayla toplar.
    """
    if not outside_texts and not outside_inserts:
        return []

    heights = [t.height for t in outside_texts if t.height > 0]
    h_med = statistics.median(heights) if heights else (0.20 / max(du_to_m, 1e-6))
    min_title_h = max(h_med * 1.15, 0.20 / max(du_to_m, 1e-6))

    raw_anchors = [
        t for t in outside_texts
        if _RE_PLAN_TITLE.search(t.text)
        and len(t.text.strip()) >= 6
        and (t.height >= min_title_h or len(t.text.strip()) >= 10)
    ]

    # Üst üste binen çok satırlı başlıkları tek çıpada birleştir
    raw_anchors.sort(key=lambda t: (-t.height, -t.y, t.x))
    anchors: List[RawText] = []
    for cand in raw_anchors:
        dup_tol_x = max(8.0 * cand.height, 4.0 / max(du_to_m, 1e-6))
        dup_tol_y = max(3.5 * cand.height, 2.0 / max(du_to_m, 1e-6))
        if any(abs(cand.x - a.x) <= dup_tol_x and abs(cand.y - a.y) <= dup_tol_y for a in anchors):
            continue
        anchors.append(cand)

    regions: List[Dict[str, Any]] = []
    used_t: Set[int] = set()
    used_i: Set[int] = set()
    used_p: Set[int] = set()

    if anchors:
        # Yatay satırları grupla (benzer Y kotundaki başlıklar aynı görünüm sırasındadır)
        row_tol_y = max(4.0 * statistics.median([a.height for a in anchors if a.height > 0] or [h_med]), 4.0 / max(du_to_m, 1e-6))
        sorted_by_y = sorted(anchors, key=lambda a: -a.y)
        rows: List[List[RawText]] = []
        for a in sorted_by_y:
            if not rows or abs(a.y - rows[-1][0].y) > row_tol_y:
                rows.append([a])
            else:
                rows[-1].append(a)
        for r in rows:
            r.sort(key=lambda a: a.x)

        # Varsayılan kolon ve satır adımı (komşu aralıklardan dinamik ölçülür)
        col_gaps = [r[k + 1].x - r[k].x for r in rows for k in range(len(r) - 1) if r[k + 1].x > r[k].x]
        row_gaps = [rows[idx][0].y - rows[idx + 1][0].y for idx in range(len(rows) - 1) if rows[idx][0].y > rows[idx + 1][0].y]
        def_col_pitch = statistics.median(col_gaps) if col_gaps else (35.0 / max(du_to_m, 1e-6))
        def_row_pitch = statistics.median(row_gaps) if row_gaps else (35.0 / max(du_to_m, 1e-6))

        region_boxes: List[Tuple[RawText, BBox2D]] = []
        top_reach = max(def_row_pitch * 1.25, 45.0 / max(du_to_m, 1e-6))
        side_reach = max(0.55 * def_col_pitch, 25.0 / max(du_to_m, 1e-6))

        # Başlıklar üstteki bölgenin ALTINDA mı yoksa ÜSTÜNDE mi? Çok satırlı yerleşimde kendiliğinden ölç
        obj_ys = [i.y for i in outside_inserts] + [p.bbox.center[1] for p in outside_paths]
        titles_are_below = True
        if len(rows) >= 2 and obj_ys:
            top_row_y = rows[0][0].y
            bot_row_y = rows[-1][0].y
            above_top = sum(1 for y in obj_ys if y > top_row_y + h_med)
            below_bot = sum(1 for y in obj_ys if y < bot_row_y - h_med)
            titles_are_below = above_top >= below_bot

        for r_idx, row in enumerate(rows):
            for c_idx, anc in enumerate(row):
                pad = max(2.2 * anc.height, 1.5 / max(du_to_m, 1e-6))
                if len(rows) == 1:
                    # Tek yatay sırada hem alt başlık hem üst başlık kapsanır
                    ymin = anc.y - top_reach
                    ymax = anc.y + top_reach
                elif titles_are_below:
                    ymin = anc.y - pad
                    if r_idx > 0:
                        up_anc = min(rows[r_idx - 1], key=lambda u: abs(u.x - anc.x))
                        ymax = up_anc.y - max(2.2 * up_anc.height, 1.5 / max(du_to_m, 1e-6))
                    else:
                        ymax = anc.y + top_reach
                else:
                    ymax = anc.y + pad
                    if r_idx + 1 < len(rows):
                        dn_anc = min(rows[r_idx + 1], key=lambda d: abs(d.x - anc.x))
                        ymin = dn_anc.y + max(2.2 * dn_anc.height, 1.5 / max(du_to_m, 1e-6))
                    else:
                        ymin = anc.y - top_reach

                xmin = (row[c_idx - 1].x + anc.x) * 0.5 if c_idx > 0 else anc.x - side_reach
                xmax = (anc.x + row[c_idx + 1].x) * 0.5 if c_idx + 1 < len(row) else anc.x + side_reach
                if xmax <= xmin:
                    xmax = xmin + def_col_pitch
                if ymax <= ymin:
                    ymax = ymin + top_reach
                region_boxes.append((anc, BBox2D(minx=xmin, miny=ymin, maxx=xmax, maxy=ymax)))

        # Nesneleri başlık bölgesine dağıt
        reg_items: List[Tuple[RawText, List[RawText], List[RawInsert], List[RawPath]]] = [
            (anc, [], [], []) for anc, _ in region_boxes
        ]

        def _match_region(sp: str, x: float, y: float) -> Optional[int]:
            hits = [
                idx for idx, (anc, bb) in enumerate(region_boxes)
                if anc.space == sp and bb.minx <= x <= bb.maxx and bb.miny <= y <= bb.maxy
            ]
            if not hits:
                return None
            if len(hits) == 1:
                return hits[0]
            return min(hits, key=lambda idx: math.hypot(x - region_boxes[idx][0].x, y - region_boxes[idx][0].y))

        for ti, t in enumerate(outside_texts):
            ri = _match_region(t.space, t.x, t.y)
            if ri is not None:
                reg_items[ri][1].append(t)
                used_t.add(ti)
        for ii, ins in enumerate(outside_inserts):
            ri = _match_region(ins.space, ins.x, ins.y)
            if ri is not None:
                reg_items[ri][2].append(ins)
                used_i.add(ii)
        for pi, p in enumerate(outside_paths):
            cx, cy = p.bbox.center
            ri = _match_region(p.space, cx, cy)
            if ri is not None:
                reg_items[ri][3].append(p)
                used_p.add(pi)

        for anc, r_txts, r_ins, r_paths in reg_items:
            if claimed_anchor_handles and anc.handle and anc.handle in claimed_anchor_handles and not r_ins:
                continue
            if not r_ins and len(r_txts) <= 1 and not r_paths:
                continue
            item_ys = [i.y for i in r_ins] + [p.bbox.center[1] for p in r_paths]
            tpos = "ALTINDA" if (not item_ys or statistics.median(item_ys) >= anc.y) else "ICINDE"
            regions.append({
                "source_kind": "CERCEVESIZ_PLAN",
                "title": anc.text.strip()[:90],
                "title_position": tpos,
                "texts": r_txts,
                "inserts": r_ins,
                "paths": r_paths,
            })

    # Kalan başlık dışı dağınık nesneleri scikit-learn DBSCAN ile (Öklid 3.0 m) adalara böl
    rem_texts = [t for idx, t in enumerate(outside_texts) if idx not in used_t]
    rem_inserts = [i for idx, i in enumerate(outside_inserts) if idx not in used_i]
    rem_paths = [p for idx, p in enumerate(outside_paths) if idx not in used_p]

    if rem_inserts or rem_texts:
        eps_du = max(3.0 / max(du_to_m, 1e-6), 1.0)
        by_space_t: Dict[str, List[RawText]] = defaultdict(list)
        by_space_i: Dict[str, List[RawInsert]] = defaultdict(list)
        by_space_p: Dict[str, List[RawPath]] = defaultdict(list)
        for t in rem_texts:
            by_space_t[t.space].append(t)
        for ins in rem_inserts:
            by_space_i[ins.space].append(ins)
        for p in rem_paths:
            by_space_p[p.space].append(p)

        fallback_groups: List[Tuple[List[RawText], List[RawInsert], List[RawPath]]] = []
        for sp in sorted(set(by_space_t) | set(by_space_i)):
            sp_t = by_space_t.get(sp, [])
            sp_i = by_space_i.get(sp, [])
            sp_p = by_space_p.get(sp, [])
            coords: List[Tuple[float, float]] = (
                [(t.x, t.y) for t in sp_t]
                + [(ins.x, ins.y) for ins in sp_i]
                + [p.bbox.center for p in sp_p]
            )
            if not coords:
                continue
            pts = np.asarray(coords, dtype=np.float64)
            labels = DBSCAN(eps=eps_du, min_samples=1).fit_predict(pts)
            clusters: Dict[int, Tuple[List[RawText], List[RawInsert], List[RawPath]]] = defaultdict(lambda: ([], [], []))
            n_t = len(sp_t)
            n_i = len(sp_i)
            for idx_pt, lbl in enumerate(labels):
                if lbl < 0:
                    continue
                if idx_pt < n_t:
                    clusters[int(lbl)][0].append(sp_t[idx_pt])
                elif idx_pt < n_t + n_i:
                    clusters[int(lbl)][1].append(sp_i[idx_pt - n_t])
                else:
                    clusters[int(lbl)][2].append(sp_p[idx_pt - n_t - n_i])
            for ct, ci, cp in clusters.values():
                if ci or len(ct) >= 5:
                    fallback_groups.append((ct, ci, cp))

        fallback_groups.sort(key=lambda grp: (
            -(max([x.y for x in grp[0]] + [x.y for x in grp[1]] or [0.0])),
            min([x.x for x in grp[0]] + [x.x for x in grp[1]] or [0.0]),
        ))
        for f_idx, (ct, ci, cp) in enumerate(fallback_groups, 1):
            regions.append({
                "source_kind": "CERCEVESIZ_KUME",
                "title": f"Çerçevesiz Alan {f_idx}",
                "title_position": "YOK",
                "texts": ct,
                "inserts": ci,
                "paths": cp,
            })

    return regions


def extract_grounding_material_specs(texts: List[RawText]) -> Tuple[str, str]:
    """
    Topraklama paftası metinlerinden ana halka/şerit malzemesi (örn. 30x3,5mm Galvaniz Çelik Lama)
    ile filiz/bakır bağlantı iletkenini (örn. 50mm2 Çıplak Örgü Bakır) dinamik olarak çıkarır.
    """
    strip_cands: Counter[str] = Counter()
    copper_cands: Counter[str] = Counter()

    for t in texts:
        s = re.sub(r"\s+", " ", t.text).strip()
        if not s or len(s) > 65:
            continue
        nu = norm_tr(s).upper()
        if any(k in nu for k in ("GALVANIZ", "LAMA", "SERIT")) and re.search(r"\d+\s*[xX*]\s*\d+", s):
            strip_cands[s] += 1
        elif any(k in nu for k in ("ORGU BAKIR", "CIPLAK BAKIR", "CU")) and re.search(r"\d+\s*MM2", nu):
            if "CUBUG" not in nu:
                copper_cands[s] += 1

    ring_spec = strip_cands.most_common(1)[0][0] if strip_cands else ""
    spur_spec = copper_cands.most_common(1)[0][0] if copper_cands else ""
    return ring_spec, spur_spec


def classify_drawing_discipline(
    snapshot: Any,
    model: Any,
    *,
    source_path: Optional[str] = None,
) -> Tuple[str, Dict[str, int]]:
    """
    Bir CAD çizimini yalnızca dosya adına bakmadan PaperSpace anteti, pafta
    başlıkları, katman isimleri, blok adları ve sembol/kablo içeriğine göre
    evrensel olarak 4 ana disipline ayırır:
      - 'TOPRAKLAMA'
      - 'SINYAL' (SCADA / PCS / CBTC / Sinyalizasyon / RTU-PLC)
      - 'ZAYIF_AKIM' (Yangın / CCTV / PA-VA / Telefon / Data / ACS / PIS)
      - 'KUVVETLI_AKIM' (Güç / Aydınlatma / Tava / Trafo / Pano / Tek Hat)
    (Birden çok disiplin dengeli şekilde aynı dosyada ise baskın disiplini ve
    tüm skor dökümünü döner.)
    """
    scores: Dict[str, int] = {
        "TOPRAKLAMA": 0,
        "SINYAL": 0,
        "ZAYIF_AKIM": 0,
        "KUVVETLI_AKIM": 0,
    }

    # 1. PaperSpace anteti + dosya/pafta başlıkları (yüksek ağırlık)
    title_blobs: List[str] = []
    if source_path:
        title_blobs.append(source_path)
    if getattr(snapshot, "filename", ""):
        title_blobs.append(snapshot.filename)
    for sh in getattr(model, "sheets", []) or []:
        if getattr(sh, "title", ""):
            title_blobs.append(sh.title)
    for t in getattr(snapshot, "texts", []) or []:
        sp = str(getattr(t, "space", "") or "")
        tag_u = norm_tr(str(getattr(t, "attrib_tag", "") or "")).upper()
        raw_u = norm_tr(str(getattr(t, "text", "") or "")).upper()
        if sp.startswith("PAPERSPACE:") and (
            tag_u in ("PAFTAADI", "BASLIK", "TITLE", "DISCIPLIN")
            or any(k in raw_u for k in ("PROJESİ", "PROJESI", "PLANI", "ŞEMASI", "SEMASI", "AS-BUILT", "ASBUİLT"))
        ):
            title_blobs.append(raw_u)
        elif any(k in raw_u for k in ("KOLON SEMASI", "KOLON ŞEMASI", "HABERLESME", "SCADA-PCS")):
            title_blobs.append(raw_u)

    joined_titles = " | ".join(norm_tr(x).upper() for x in title_blobs)
    if any(k in joined_titles for k in ("TOPRAKLAMA", "PS-17", "EARTHING", "GROUNDING", "YILDIRIM", "PARATONER")):
        scores["TOPRAKLAMA"] += 90
    has_signal_title = any(k in joined_titles for k in ("SCADA", "PCS", "SINYAL", "SIGNAL", "CBTC", "RTU", "PLC", "TL-09"))
    if has_signal_title:
        scores["SINYAL"] += 90
    has_weak_title = any(
        k in joined_titles
        for k in (
            "ZAYIF AKIM", "YANGIN ALGILAMA", "CCTV", "ANONS", "PAVA", "TELEFON",
            "DATA", "ACS", "PIS", "USK",
            "TL-01", "TL-02", "TL-03", "TL-04", "TL-05", "TL-06", "TL-07", "TL-08", "TL-10", "TL-11",
            "AX-02", "TURNIKE", "TURNSTILE", "UCRET TOPLAMA", "GECIS KONTROL",
        )
    )
    if has_weak_title:
        scores["ZAYIF_AKIM"] += 90
    power_title_keys = (
        ("KUVVETLI AKIM", "GUC DAGITIM", "AYDINLATMA", "ACIL AYDINLATMA", "OG GUC", "PS-08", "PS-11", "PS-16", "GN-07", "GN-13", "GN-14")
        + (() if (has_weak_title or has_signal_title) else ("TAVA",))
    )
    if any(k in joined_titles for k in power_title_keys):
        scores["KUVVETLI_AKIM"] += 90

    # 2. Topraklama ringi ve şema/tablo/sembol içeriği (tekil ekipman tekrarları başlığı boğmayacak şekilde sınırlı oylanır)
    g_loops = getattr(model, "grounding_loops", []) or []
    if g_loops:
        scores["TOPRAKLAMA"] += 15 * len(g_loops)

    containers = build_container_block_names(snapshot.inserts, max(getattr(model.unit, "du_to_m", 1.0), 1e-6))
    sym_scores: Dict[str, int] = {k: 0 for k in scores}
    sym_families: Dict[str, Set[str]] = {k: set() for k in scores}
    tray_sym_count = 0
    for ins in snapshot.inserts:
        if is_container_insert(ins, max(getattr(model.unit, "du_to_m", 1.0), 1e-6), containers):
            continue
        bu = norm_tr(ins.effective_name or ins.block_name).upper()
        lu = norm_tr(ins.layer).upper()
        comb = f"{bu} {lu}"
        if any(k in comb for k in ("SCADA", "RTU", "PLC", "SINYAL", "SIGNAL", "CBTC")):
            sym_scores["SINYAL"] += 1
            sym_families["SINYAL"].add(_clean_block_core_name(bu))
            continue
        role, cat, disc, _, _ = classify_insert_role(ins, getattr(model, "legend", {}) or {})
        if role == "ELECTRICAL" and disc in scores:
            if cat == "KABLO TAVA / TAŞIYICI":
                tray_sym_count += 1
                continue
            sym_scores[disc] += 1
            sym_families[disc].add(_clean_block_core_name(bu))
    if tray_sym_count > 0 and sym_scores["ZAYIF_AKIM"] == 0 and sym_scores["SINYAL"] == 0 and sym_scores["TOPRAKLAMA"] == 0:
        sym_scores["KUVVETLI_AKIM"] += tray_sym_count
        sym_families["KUVVETLI_AKIM"].add("KABLO_TAVA")
    for disc in scores:
        scores[disc] += min(len(sym_families[disc]) * 4 + min(sym_scores[disc], 20), 60)

    # 3. Kablo / tava / metin yoğunluğu
    txt_scores: Dict[str, int] = {k: 0 for k in scores}
    for t in getattr(snapshot, "texts", []) or []:
        tu = norm_tr(t.text or "").upper()
        lu = norm_tr(t.layer or "").upper()
        if any(k in tu for k in ("SCADA", "PCS", "RTU", "PLC", "MODBUS", "IEC 60870", "ETB/SCADA")):
            txt_scores["SINYAL"] += 2
        elif any(k in tu for k in ("TOPRAKLAMA", "VLD", "MEB", "EPTB", "ESPOTANSIYEL", "120MM2", "30X3,5", "30X3.5")):
            txt_scores["TOPRAKLAMA"] += 2
        elif any(k in tu for k in ("CCTV", "KAMERA", "HOPARLOR", "ANONS", "PAVA", "YANGIN", "DEDEKTOR", "TURNIKE", "TURNSTILE")):
            txt_scores["ZAYIF_AKIM"] += 2
        elif any(k in lu for k in ("TRAY", "TAVA")) or re.search(r"\b(?:WC|LV|HV)\s*/\s*\d{2,4}\b", tu):
            txt_scores["KUVVETLI_AKIM"] += 1
    for disc in scores:
        scores[disc] += min(txt_scores[disc], 40)

    # 4. Dosya adında PS-17 / USK / TL-* gibi net disiplin kodu varsa güçlü sinyal ekle
    fn_u = norm_tr(str(source_path or getattr(snapshot, "filename", ""))).upper()
    if "PS-17" in fn_u or "TOPRAK" in fn_u:
        scores["TOPRAKLAMA"] += 35
    elif any(k in fn_u for k in ("USK", "TL-", "AX-02", "ZAYIF")):
        scores["ZAYIF_AKIM"] += 35
    elif any(k in fn_u for k in ("SCADA", "SINYAL", "CBTC")):
        scores["SINYAL"] += 35
    elif any(k in fn_u for k in ("PS-08", "PS-11", "PS-16", "GN-13", "GN-14", "KUVVET")):
        scores["KUVVETLI_AKIM"] += 35

    best_disc = max(scores.keys(), key=lambda k: (scores[k], k == "KUVVETLI_AKIM"))
    return best_disc, scores
