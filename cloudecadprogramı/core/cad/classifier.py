# -*- coding: utf-8 -*-
"""
Çok Kanıtlı ve Güven Puanlı Sembol Sınıflandırıcı (MultiEvidenceClassifier)
===========================================================================
Revit görünüm sonekini (-AYD 02 FFL...) temizledikten sonra blok adını,
ATTRIB içeriğini, lejant sözlüğünü ve katmanı değerlendirerek gerçek cihaz sınıfını,
güven puanını (0.0..1.0) ve kanıt zincirini ("Neden bu sonuca varıldı?") üretir.
"""

from __future__ import annotations
import re
from typing import Dict, Tuple, List, Optional
from ..model.entities import PlacedSymbol
from ..model.audit import ConfidenceLevel


class MultiEvidenceClassifier:
    FIRE_REGEX = re.compile(r"(?:JE-H\(St\)H|NHXMH|FE-?180|FACP|FPP|DEDEKT|BUTON|FLA[SŞ]|S[İI]REN|YANGIN)", re.IGNORECASE)
    DATA_REGEX = re.compile(r"(?:CAT-?6|F/O|PATCH|RACK|SWITCH|FIBER|FİBER|SM F/O|TELEFON|DATA|BAĞLANTI PANELİ)", re.IGNORECASE)
    WATT_REGEX = re.compile(r"(\d+(?:\.\d+)?)\s*W\b", re.IGNORECASE)

    @classmethod
    def classify_and_enrich_symbol(cls, sym: PlacedSymbol, sym_dict: Dict[str, str]) -> None:
        fam_up = sym.clean_family_name.upper()
        all_att = " ".join(sym.attribs.values()).upper()
        evidence_chain: List[str] = []

        # 1. Watt Gücü ve Faz Çıkarımı (Yalnızca Açık Kanıt Varsa!)
        m_w = cls.WATT_REGEX.search(sym.clean_family_name)
        if m_w:
            try:
                sym.power_w = float(m_w.group(1))
                sym.power_source = "EXPLICIT_BLOCK_NAME"
                evidence_chain.append(f"Güç blok adından okundu: {sym.power_w}W")
            except ValueError:
                pass
        elif all_att:
            m_att_w = cls.WATT_REGEX.search(all_att)
            if m_att_w:
                try:
                    sym.power_w = float(m_att_w.group(1))
                    sym.power_source = "EXPLICIT_ATTRIB"
                    evidence_chain.append(f"Güç blok özniteliğinden (ATTRIB) okundu: {sym.power_w}W")
                except ValueError:
                    pass
        if "3PH" in fam_up or "3Ø" in fam_up:
            sym.phases = 3
            evidence_chain.append("Faz sayısı 3 olarak belirlendi")

        # ----------------------------------------------------------------------
        # KANIT 1: LEJANT SÖZLÜĞÜ (En Yüksek Güven — 1.0 KESİN)
        # ----------------------------------------------------------------------
        desc = sym_dict.get(sym.clean_family_name, "").upper()
        if desc:
            sym.legend_description = desc
            evidence_chain.append(f"Pafta lejant tanımıyla eşleşti: '{desc}'")

            if "BUAT" in desc and "TELEFON" not in desc and "TV" not in desc:
                sym.classification = "JUNCTION_BOX"
                sym.confidence_level = "KESİN"
                sym.confidence_score = 1.0
                sym.evidence_chain = evidence_chain
                return

            if "ANAHTAR" in desc:
                sym.classification = "SWITCH"
                sym.confidence_level = "KESİN"
                sym.confidence_score = 1.0
                sym.evidence_chain = evidence_chain
                return

            if any(k in desc for k in ["PANEL", "PANO", "TABLO", "SANTRALİ", "SANTRALI"]):
                if "YANGIN" in desc:
                    sym.classification = "FIRE_DEVICE"
                elif any(k in desc for k in ["TELEFON", "TV", "İNTERKOM", "INTERKOM"]):
                    sym.classification = "DATA_DEVICE"
                else:
                    sym.classification = "PANEL"
                sym.confidence_level = "KESİN"
                sym.confidence_score = 1.0
                sym.evidence_chain = evidence_chain
                return

            if any(k in desc for k in ["TOPRAKLAMA", "E.T.B", "ELEKTROD", "KLEMENS", "KADVELT"]):
                sym.classification = "GROUNDING_CLAMP"
                sym.confidence_level = "KESİN"
                sym.confidence_score = 1.0
                sym.evidence_chain = evidence_chain
                return

            if any(k in desc for k in ["DEDEKTÖR", "DEDEKTOR", "YANGIN", "BUTON", "SİREN", "SIREN", "FLAŞÖR", "FLASOR"]):
                sym.classification = "FIRE_DEVICE"
                sym.confidence_level = "KESİN"
                sym.confidence_score = 1.0
                sym.evidence_chain = evidence_chain
                return

            if any(k in desc for k in ["TELEFON", "TV", "TELEVİZYON", "TELEVIZYON", "ANTEN", "İNTERKOM", "INTERKOM", "İNTERCOM", "INTERCOM", "DİAFON", "DIAFON", "DUAFON", "ZİL", "ZIL", "KAPI OTOMAT", "ÇOĞALTICI", "COGALTICI"]):
                sym.classification = "DATA_DEVICE"
                sym.confidence_level = "KESİN"
                sym.confidence_score = 1.0
                sym.evidence_chain = evidence_chain
                return

            if any(k in desc for k in ["AYDINLATMA", "ARMATÜR", "ARMATUR", "FLORESANT", "AVİZE", "AVIZE", "APLİK", "APLIK", "SPOT", "GLOB"]):
                sym.classification = "LUMINAIRE"
                if sym.power_w == 0.0:
                    m_dw = cls.WATT_REGEX.search(desc)
                    if m_dw:
                        sym.power_w = float(m_dw.group(1))
                        sym.power_source = "EXPLICIT_LEGEND"
                        evidence_chain.append(f"Güç lejant metninden okundu: {sym.power_w}W")
                    elif "2X36" in desc or "2*36" in desc:
                        sym.power_w = 72.0
                        sym.power_source = "EXPLICIT_LEGEND"
                        evidence_chain.append("Güç lejant tanımından (2x36W) okundu: 72W")
                    elif "1X36" in desc or "1*36" in desc:
                        sym.power_w = 36.0
                        sym.power_source = "EXPLICIT_LEGEND"
                        evidence_chain.append("Güç lejant tanımından (1x36W) okundu: 36W")
                    elif "36" in fam_up:
                        sym.power_w = 36.0
                        sym.power_source = "EXPLICIT_BLOCK_NAME"
                        evidence_chain.append("Güç blok kodundan (36) okundu: 36W")
                    elif "75" in fam_up:
                        sym.power_w = 75.0
                        sym.power_source = "EXPLICIT_BLOCK_NAME"
                        evidence_chain.append("Güç blok kodundan (75) okundu: 75W")
                    else:
                        sym.power_w = 0.0
                        sym.power_source = "MISSING"
                sym.confidence_level = "KESİN"
                sym.confidence_score = 1.0
                sym.evidence_chain = evidence_chain
                return

            if "PRİZ" in desc or "PRIZ" in desc:
                sym.classification = "SOCKET"
                if sym.power_w == 0.0:
                    m_pw = cls.WATT_REGEX.search(desc)
                    if m_pw:
                        sym.power_w = float(m_pw.group(1))
                        sym.power_source = "EXPLICIT_LEGEND"
                        evidence_chain.append(f"Priz gücü lejanttan okundu: {sym.power_w}W")
                    else:
                        sym.power_w = 0.0
                        sym.power_source = "MISSING"
                sym.confidence_level = "KESİN"
                sym.confidence_score = 1.0
                sym.evidence_chain = evidence_chain
                return

        # ----------------------------------------------------------------------
        # KANIT 2: TEMİZLENMİŞ FAMILY / BLOK ADI (Yüksek Güven — 0.85 - 0.95)
        # ----------------------------------------------------------------------
        if fam_up in ("1AOS3", "1KAR", "SSSS", "1KOM", "1AMPER"):
            sym.classification = "SWITCHGEAR"
            sym.confidence_level = "YÜKSEK GÜVEN"
            sym.confidence_score = 0.95
            evidence_chain.append(f"Kolon şeması şalt cihazı kodu ile eşleşti: {fam_up}")
            sym.evidence_chain = evidence_chain
            return

        if fam_up == "B":
            sym.classification = "JUNCTION_BOX"
            sym.confidence_level = "YÜKSEK GÜVEN"
            sym.confidence_score = 0.90
            evidence_chain.append("Standart Türk buat sembol kodu (B)")
            sym.evidence_chain = evidence_chain
            return

        if any(p in fam_up for p in ["PANELBOARD", "SWITCHBOARD", "PANO", "PANEL", "UPS UNIT", "BATTERY UNIT", "MVS", "TVC", "EXC", "CDB", "FACP", "1T1", "1ITDT"]):
            sym.classification = "PANEL"
            sym.confidence_level = "YÜKSEK GÜVEN"
            sym.confidence_score = 0.90
            evidence_chain.append(f"Blok adı elektrik dağıtım panosu kelimesi içeriyor: {fam_up}")
            sym.evidence_chain = evidence_chain
            return

        if any(p in fam_up for p in ["LIGHTING FIXTURE", "PENDANT LIGHT", "EXIT LIGHT", "ARMATÜR", "ARMATUR", "FLUORESCENT", "PROJEKTÖR", "AVIZE"]):
            sym.classification = "LUMINAIRE"
            if sym.power_w == 0.0:
                sym.power_source = "MISSING"
            sym.confidence_level = "YÜKSEK GÜVEN"
            sym.confidence_score = 0.90
            evidence_chain.append(f"Blok adı aydınlatma armatürü kelimesi içeriyor: {fam_up}")
            sym.evidence_chain = evidence_chain
            return

        if any(p in fam_up for p in ["LIGHTING SWITCH", "ANAHTAR"]):
            sym.classification = "SWITCH"
            sym.confidence_level = "YÜKSEK GÜVEN"
            sym.confidence_score = 0.90
            evidence_chain.append(f"Blok adı anahtar kelimesi içeriyor: {fam_up}")
            sym.evidence_chain = evidence_chain
            return

        if any(p in fam_up for p in ["SOCKET OUTLET", "PRİZ", "PRIZ"]):
            sym.classification = "SOCKET"
            if sym.power_w == 0.0:
                sym.power_source = "MISSING"
            sym.confidence_level = "YÜKSEK GÜVEN"
            sym.confidence_score = 0.90
            evidence_chain.append(f"Blok adı priz kelimesi içeriyor: {fam_up}")
            sym.evidence_chain = evidence_chain
            return

        if any(p in fam_up for p in ["KKK", "TOPRAKLAMA", "BARASI", "_TB-", "C7CD84BE7", "ETB", "1EKK", "1KAD", "1TP"]):
            sym.classification = "GROUNDING_CLAMP"
            sym.confidence_level = "YÜKSEK GÜVEN"
            sym.confidence_score = 0.90
            evidence_chain.append(f"Blok adı topraklama elemanı içeriyor: {fam_up}")
            sym.evidence_chain = evidence_chain
            return

        if cls.FIRE_REGEX.search(fam_up) or cls.FIRE_REGEX.search(all_att):
            sym.classification = "FIRE_DEVICE"
            sym.confidence_level = "YÜKSEK GÜVEN"
            sym.confidence_score = 0.85
            evidence_chain.append(f"Blok veya öznitelik yangın cihazı deseniyle eşleşti")
            sym.evidence_chain = evidence_chain
            return

        if cls.DATA_REGEX.search(fam_up) or cls.DATA_REGEX.search(all_att):
            sym.classification = "DATA_DEVICE"
            sym.confidence_level = "YÜKSEK GÜVEN"
            sym.confidence_score = 0.85
            evidence_chain.append(f"Blok veya öznitelik data/zayıf akım deseniyle eşleşti")
            sym.evidence_chain = evidence_chain
            return

        # ----------------------------------------------------------------------
        # KANIT 3: KATMAN ADI (Muhtemel Güven — 0.65 - 0.75)
        # ----------------------------------------------------------------------
        l_up = sym.layer.upper()
        if "LITE" in l_up:
            sym.classification = "LUMINAIRE"
            sym.confidence_level = "MUHTEMEL"
            sym.confidence_score = 0.75
            evidence_chain.append(f"Katman adı aydınlatma ('LITE') katmanı: {sym.layer}")
            sym.evidence_chain = evidence_chain
            return

        if "PRZ" in l_up or "PRIZ" in l_up:
            sym.classification = "SOCKET"
            sym.confidence_level = "MUHTEMEL"
            sym.confidence_score = 0.75
            evidence_chain.append(f"Katman adı priz ('PRZ') katmanı: {sym.layer}")
            sym.evidence_chain = evidence_chain
            return

        if "FIRE" in l_up or "YANGIN" in l_up or "HCS" in l_up:
            sym.classification = "FIRE_DEVICE"
            sym.confidence_level = "MUHTEMEL"
            sym.confidence_score = 0.75
            evidence_chain.append(f"Katman adı yangın katmanı: {sym.layer}")
            sym.evidence_chain = evidence_chain
            return

        if any(k in l_up for k in ["TEL", "DATA", "USKOM", "İLETİM", "INTERCOM", "İNTERCOM", "TV", "ZIL", "ZİL"]):
            sym.classification = "DATA_DEVICE"
            sym.confidence_level = "MUHTEMEL"
            sym.confidence_score = 0.70
            evidence_chain.append(f"Katman adı zayıf akım katmanı: {sym.layer}")
            sym.evidence_chain = evidence_chain
            return

        # ----------------------------------------------------------------------
        # KANIT 4: BELİRSİZ EKİPMAN (İnceleme Gerekli — < 0.50)
        # ----------------------------------------------------------------------
        sym.classification = "EQUIPMENT"
        sym.confidence_level = "İNCELEME GEREKLİ (BELİRSİZ)"
        sym.confidence_score = 0.40
        evidence_chain.append("Lejant, blok adı veya katmandan kesin elektrik sınıfı çıkarılamadı")
        sym.evidence_chain = evidence_chain
