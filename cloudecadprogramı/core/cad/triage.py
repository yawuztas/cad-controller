# -*- coding: utf-8 -*-
"""
Sınıflandırılamayan Blokların Kanıtlı Triyajı (SymbolTriage)
=============================================================
Yalnızca "anonim blok" veya bilinmeyen isim olduğu için hiçbir sembol silinmez.
Her sınıflandırılamayan (EQUIPMENT) sembol; blok sahibi (parent/XREF), katman,
blok adı, yakındaki yazılar ve yakındaki elektrik sembolleriyle değerlendirilir.

Sonuç kategorileri (sym.triage_status):
  IGNORED_ARCHITECTURAL  : Mimari/XREF olduğu KANITLANDI ve elektrik izi YOK -> belirsizlik listesinden çıkar
  UNCERTAIN_ELECTRICAL   : Elektrik katmanında / elektrik sembolü veya etiketi yakınında -> belirsizlikte KALIR
  UNCLASSIFIED           : Ne mimari ne elektrik kanıtı var -> belirsizlikte KALIR
"""

from __future__ import annotations
import re
from typing import Dict, List, Tuple

from shapely.geometry import Point
from shapely.strtree import STRtree

from ..model.entities import PlacedSymbol, TextToken

ELECTRICAL_CLASSES = {
    "LUMINAIRE", "SOCKET", "SWITCH", "PANEL", "SWITCHGEAR", "JUNCTION_BOX",
    "GROUNDING_CLAMP", "FIRE_DEVICE", "DATA_DEVICE",
}

ELECTRICAL_LAYER_KW = (
    "E-", "ELC", "ELEC", "LIGHT", "LITE", "PWR", "POWER", "GUC", "GÜÇ", "PRZ", "PRIZ", "PRİZ",
    "PANO", "PANEL", "TAVA", "TRAY", "CABLE", "KABLO", "FIRE", "YANGIN", "TOPRAK", "EARTH",
    "AYDINLATMA", "ZAYIF", "KUVVETLI", "KUVVETLİ", "TEL", "DATA", "USKOM", "HCS",
)

ARCH_PARENT_KW = ("XREF", "M3-ARC", "ARCH", "KAT_PLANI", "FLOORPLAN-", "M3-STR", "M3-MEC")

ARCH_LAYER_KW = (
    "DUVAR", "SIVA", "DSIVA", "DSİVA", "TEFRS", "TEFRIS", "TEFRİŞ", "MOBILYA", "MOBİLYA",
    "KAPI", "KAPİ", "PENCERE", "CERCEVE", "ÇERÇEVE", "MERDIVEN", "MERDİVEN", "TARAMA", "HATCH",
    "A-WALL", "A-DOOR", "A-GLAZ", "A-FURN", "A-", "S-", "OLCU", "ÖLÇÜ",
)

ARCH_BLOCK_KW = (
    "MOBILYA", "MOBİLYA", "KOLTUK", "SANDALYE", "MASA", "YATAK", "DOOR", "WINDOW", "KAPI",
    "PENCERE", "FURN", "CHAIR", "TABLE", "BED", "SOFA", "WC", "LAVABO", "KLOZET", "RAILING",
    "HANDRAIL", "STAIR", "MERDIVEN", "MERDİVEN", "TREE", "AGAC", "AĞAÇ", "CAR", "ARAC", "ARAÇ",
)

ELEC_TEXT_RE = re.compile(
    r"(?:\b(?:CDB|PE|[AEKP])\d{3}\d{2}/\d{2}/L[123]\b"      # metro linye etiketi
    r"|\b\d+\s*[xX]\s*\d+(?:[.,]\d+)?\b.*?(?:N2XH|NHXMH|NYY|NYM|LIHCH|FE\s*180)"  # kablo
    r"|\b\d+(?:[.,]\d+)?\s*W\b"                                # güç
    r"|\b(?:PANO|TABLO|DB|LP|UPS|JENERATÖR|TRAFO|PRİZ|PRIZ|ARMATÜR|ARMATUR|ANAHTAR|BUAT|TOPRAKLAMA)\b"
    r"|\b[A-Z]{1,2}\d{1,3}\b)",
    re.IGNORECASE,
)

NEAR_SYMBOL_DIST = 1000.0
NEAR_TEXT_DIST = 600.0


def _tu(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def _has_kw(text: str, kws: Tuple[str, ...], prefix_only: Tuple[str, ...] = ("A-", "S-", "E-")) -> bool:
    t = _tu(text)
    for k in kws:
        if k in prefix_only:
            if t.startswith(k):
                return True
        elif k in t:
            return True
    return False


class SymbolTriage:
    @classmethod
    def triage(cls, symbols: List[PlacedSymbol], tokens: List[TextToken]) -> Dict[str, int]:
        elec_syms = [s for s in symbols if s.classification in ELECTRICAL_CLASSES]
        sym_tree = STRtree([Point(s.pos[0], s.pos[1]) for s in elec_syms]) if elec_syms else None
        elec_sym_pts = [Point(s.pos[0], s.pos[1]) for s in elec_syms]

        elec_tokens = [t for t in tokens if ELEC_TEXT_RE.search(t.text)]
        tok_tree = STRtree([Point(t.pos[0], t.pos[1]) for t in elec_tokens]) if elec_tokens else None
        elec_tok_pts = [Point(t.pos[0], t.pos[1]) for t in elec_tokens]

        counts = {
            "IGNORED_ARCHITECTURAL": 0,
            "UNCERTAIN_ELECTRICAL": 0,
            "UNCLASSIFIED": 0,
        }

        for s in symbols:
            if s.classification != "EQUIPMENT":
                continue

            pt = Point(s.pos[0], s.pos[1])
            electrical_evidence: List[str] = []
            arch_evidence: List[str] = []

            # --- Elektrik kanıtları ---
            if _has_kw(s.layer, ELECTRICAL_LAYER_KW):
                electrical_evidence.append(f"Katman elektrik katmanı: '{s.layer}'")
            if sym_tree is not None:
                idx = sym_tree.nearest(pt)
                if idx is not None and pt.distance(elec_sym_pts[int(idx)]) <= NEAR_SYMBOL_DIST:
                    near = elec_syms[int(idx)]
                    electrical_evidence.append(
                        f"Yakınında sınıflı elektrik sembolü var ({near.classification}: {near.clean_family_name})"
                    )
            if tok_tree is not None:
                idx = tok_tree.nearest(pt)
                if idx is not None and pt.distance(elec_tok_pts[int(idx)]) <= NEAR_TEXT_DIST:
                    electrical_evidence.append(
                        f"Yakınında elektrik etiketi/yazısı var: '{elec_tokens[int(idx)].text[:40]}'"
                    )

            # --- Mimari kanıtları ---
            if s.parent_view and _has_kw(s.parent_view, ARCH_PARENT_KW, prefix_only=()):
                arch_evidence.append(f"Blok sahibi mimari/XREF görünümü: '{s.parent_view[:60]}'")
            if _has_kw(s.layer, ARCH_LAYER_KW):
                arch_evidence.append(f"Katman mimari katmanı: '{s.layer}'")
            if _has_kw(s.clean_family_name, ARCH_BLOCK_KW, prefix_only=()):
                arch_evidence.append(f"Blok adı mimari eleman içeriyor: '{s.clean_family_name}'")

            if arch_evidence and not electrical_evidence:
                status = "IGNORED_ARCHITECTURAL"
                s.confidence_level = "MİMARİ (KANITLI)"
                s.confidence_score = 0.90
                s.evidence_chain.extend(arch_evidence)
                s.evidence_chain.append("Elektrik kanıtı bulunmadı -> IGNORED_ARCHITECTURAL")
            elif electrical_evidence:
                status = "UNCERTAIN_ELECTRICAL"
                s.evidence_chain.extend(electrical_evidence)
                if arch_evidence:
                    s.evidence_chain.append("Çelişen mimari ipuçları da var; mühendis teyidi gerekir: " + "; ".join(arch_evidence))
            else:
                status = "UNCLASSIFIED"
                s.evidence_chain.append("Ne mimari ne elektrik kanıtı bulundu; sınıflandırılamadı")

            s.triage_status = status
            if status == "IGNORED_ARCHITECTURAL":
                s.classification = "IGNORED_ARCHITECTURAL"
            counts[status] += 1

        return counts
