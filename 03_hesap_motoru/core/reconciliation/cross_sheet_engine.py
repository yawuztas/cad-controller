# -*- coding: utf-8 -*-
"""
Paftalar Arası Çapraz Mutabakat Motoru (CrossSheetReconciliationEngine)
======================================================================
Plan çizimleri, kablo metraj tabloları, kolon dağıtım şemaları ve hesap metinleri
arasındaki tutarlılığı doğrular; uyuşmazlıkları ve eksiklikleri kanıtlarıyla raporlar.
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import List, Dict, Tuple, Set, Optional, Any
from collections import defaultdict

from ..model.entities import DrawingSceneGraph
from ..model.audit import ReconciliationItem, AuditFinding, StationAuditReport, UncertaintyItem
from ..calculators.electrical_calc import parse_cross_section_mm2, check_pe_cross_section_iec60364_5_54


def _extract_floor_code(filename: str) -> str:
    fn_u = filename.upper()
    m = re.search(r"S\d{2}-([A-Z0-9]{3}-[A-Z0-9]{2})-", fn_u)
    if m:
        return m.group(1)
    m2 = re.search(r"(?:^|[-_/\\])(BT\d{2}|CT\d{2}|000-00|000-01|000-99)(?:[-_/\\]|$)", fn_u)
    if m2:
        return m2.group(1)
    return "GENEL"


class CrossSheetReconciliationEngine:
    @classmethod
    def reconcile_plan_vs_schedule_tables(
        cls, scenes: Dict[str, DrawingSceneGraph], report: StationAuditReport
    ) -> None:
        """Kuvvetli akım planındaki kablo etiketleri ile metraj tablosunu karşılaştırır."""
        for fname, sc in scenes.items():
            if "PS-11" not in fname or not sc.tables:
                continue

            plan_cables: Dict[str, Dict[str, Any]] = {}
            for co in sc.callouts:
                if co.category == "CABLE_TAG":
                    cid = co.metadata.get("circuit_id", "").strip()
                    if cid:
                        plan_cables[cid] = co.metadata

            for tb in sc.tables:
                tb_cables: Dict[str, Dict[str, str]] = {}
                for r in tb.rows:
                    lno = r.get("LİNYE NO", "").strip()
                    if lno:
                        tb_cables[lno] = r

                common_cids = sorted(set(plan_cables.keys()) & set(tb_cables.keys()))
                for cid in common_cids:
                    p_meta = plan_cables[cid]
                    t_row = tb_cables[cid]
                    p_sec_comma = p_meta.get("cross_section", "").replace(".", ",")
                    p_sec_dot = p_meta.get("cross_section", "").replace(",", ".")
                    p_typ = p_meta.get("cable_type", "")
                    p_full = p_meta.get("full_code", "")
                    t_kab = t_row.get("KABLO", "")
                    t_len = t_row.get("UZUNLUK (m)", "")

                    if p_sec_comma and (p_sec_comma not in t_kab and p_sec_dot not in t_kab):
                        item = ReconciliationItem(
                            category="PLAN_VS_TABLO_KESİT",
                            sheet_name=fname,
                            item_id=f"{cid} ({p_full})" if p_full else cid,
                            source_a_label=f"Plan Çizimi: {p_sec_comma} {p_typ}",
                            source_b_label=f"Metraj Tablosu: {t_kab} ({t_len} m)",
                            status="UYUŞMAZLIK",
                            detail=f"{cid} linyesinde plandaki kablo kesiti ({p_sec_comma}) ile metraj tablosundaki kesit ({t_kab}) çelişkilidir!",
                            confidence_score=1.0,
                        )
                        report.reconciliation_items.append(item)
                        report.findings.append(AuditFinding(
                            severity="CRITICAL",
                            module="ÇAPRAZ_MUTABAKAT",
                            code=f"REC-SEC-{cid}",
                            title=f"Plan Çizimi ile Kablo Metraj Tablosu Kesit Uyuşmazlığı ({cid})",
                            floor_or_scope=f"{sc.floor_name or fname}",
                            sheet_names=[fname],
                            element_id=f"{cid} ({p_full})" if p_full else cid,
                            measured_value=f"Planda: '{p_sec_comma} {p_typ}' != Tabloda: '{t_kab}'",
                            standard_limit="Plan Çizimi ve Metraj Tablosu Kesitleri Birebir Eşleşmelidir",
                            standard_ref="İBB Raylı Sistemler As-Built Çizim ve Metraj Standartları",
                            engineering_explanation=(
                                f"'{fname}' paftasında {cid} hattı üzerinde planda '{p_sec_comma} {p_typ}' "
                                f"yazarken metraj tablosunda '{t_kab}' ({t_len}m) yazmaktadır."
                            ),
                            recommendation="Sahadaki fiili kablo kesiti kontrol edilerek plan veya tablo düzeltilmelidir.",
                            confidence_level="KESİN",
                            confidence_score=1.0,
                            evidence_chain=[
                                f"Plan etiketi: '{p_sec_comma} {p_typ}'",
                                f"Tablo satırı: '{t_kab}' ({tb.name})",
                            ],
                        ))

                    # IEC 60364-5-54 PE kesit kontrolü
                    _, phase_mm2, pe_mm2 = parse_cross_section_mm2(t_kab)
                    if pe_mm2 is not None:
                        is_ok, req_pe, exp = check_pe_cross_section_iec60364_5_54(phase_mm2, pe_mm2)
                        if not is_ok:
                            report.findings.append(AuditFinding(
                                severity="CRITICAL",
                                module="ÇAPRAZ_MUTABAKAT",
                                code=f"REC-PE-{cid}",
                                title=f"Ana Besleme Kablosu Nötr/Koruma Kesiti Yetersiz ({cid})",
                                floor_or_scope=f"{sc.floor_name or fname}",
                                sheet_names=[fname],
                                element_id=cid,
                                measured_value=f"Faz: {phase_mm2} mm², Nötr/PE: {pe_mm2} mm² ({t_kab})",
                                standard_limit=f"S_PE >= {req_pe} mm²",
                                standard_ref="IEC 60364-5-54 Tablo 54.2 & Topraklamalar Yönetmeliği",
                                engineering_explanation=exp,
                                recommendation=f"Kablo kesiti nötr/PE iletkeni en az {req_pe} mm² olacak şekilde revize edilmelidir.",
                                confidence_level="KESİN",
                                confidence_score=1.0,
                                evidence_chain=[f"Metraj tablosundaki kablo: '{t_kab}'", exp],
                            ))

                # Planda çizilip metraj tablosunda eksik kalan linyeler
                in_plan_not_tb = sorted(set(plan_cables.keys()) - set(tb_cables.keys()))
                if in_plan_not_tb:
                    report.reconciliation_items.append(ReconciliationItem(
                        category="PLAN_VS_TABLO_EKSİK",
                        sheet_name=fname,
                        item_id=f"{len(in_plan_not_tb)} Adet Tali Güç/MCC Linyesi",
                        source_a_label=f"Planda Etiketli: {len(in_plan_not_tb)} linye ({', '.join(in_plan_not_tb[:6])}...)",
                        source_b_label="Metraj Tablosunda: YOK",
                        status="EKSİK",
                        detail=f"Planda çizilen {len(in_plan_not_tb)} adet MCC/cihaz linyesi paftadaki metraj tablosuna işlenmemiştir.",
                        confidence_score=1.0,
                    ))
                    report.findings.append(AuditFinding(
                        severity="WARNING",
                        module="ÇAPRAZ_MUTABAKAT",
                        code=f"REC-TBL-OMIT",
                        title=f"Planda Çizilen {len(in_plan_not_tb)} Adet Linye/Cihazın Metraj Tablosunda Yer Almaması",
                        floor_or_scope=f"{sc.floor_name or fname}",
                        sheet_names=[fname],
                        element_id=", ".join(in_plan_not_tb[:5]),
                        measured_value=f"Planda {len(plan_cables)} linye var; Tabloda bu linyelerin {len(in_plan_not_tb)} adedi eksik",
                        standard_limit="Kablo Metraj Tablosu Çizimdeki Tüm Beslemeleri İçermelidir",
                        standard_ref="İBB Raylı Sistemler As-Built Şartnamesi",
                        engineering_explanation="Planda etiketlenen bazı tali pano/MCC kabloları ana kablo tablosuna eklenmemiştir.",
                        recommendation="Eksik linyeler için paftaya ek kablo metraj cetveli eklenmelidir.",
                        confidence_level="KESİN",
                        confidence_score=1.0,
                    ))

    @classmethod
    def reconcile_panels_vs_grounding_sheets(
        cls, scenes: Dict[str, DrawingSceneGraph], report: StationAuditReport
    ) -> None:
        """Kuvvetli akım panoları ile istasyonun topraklama etiketlerini kademeli olarak eşleştirir."""
        ka_panels: Set[str] = set()
        panel_to_floors: Dict[str, Set[str]] = defaultdict(set)
        ka_sheets: List[str] = []
        tp_sheets: List[str] = []
        station_code = report.station_code.upper()
        station_number = station_code.removeprefix("S")

        # 1. Kuvvetli Akım Panolarını Topla
        for fname, sc in scenes.items():
            target_fn = sc.filename if getattr(sc, "filename", None) else Path(fname).name
            fn_u = target_fn.upper()
            if any(k in fn_u for k in ("PS-08", "PS-11", "PS-16", "AY-", "AYD", "PRZ", "GUC")):
                ka_sheets.append(target_fn)
                fl = _extract_floor_code(target_fn)
                for lc in sc.logical_circuits:
                    p_clean = lc.panel_tag.strip()
                    p_norm = re.sub(r"[^A-Z0-9]", "", p_clean.upper().replace("İ", "I"))
                    if p_norm.startswith(station_code) or len(p_norm) >= 6:
                        ka_panels.add(p_clean)
                        if fl != "GENEL":
                            panel_to_floors[p_clean].add(fl)

        # 2. Topraklama Paftalarını, Etiketlerini ve ECB Baralarını Topla
        tp_floors: Set[str] = set()
        grounding_texts: List[str] = []
        grounding_normalized_set: Set[str] = set()
        grounding_parts: Set[str] = set()
        ecb_bars_by_floor: Dict[str, Set[str]] = defaultdict(set)

        for fname, sc in scenes.items():
            target_fn = sc.filename if getattr(sc, "filename", None) else Path(fname).name
            fn_u = target_fn.upper()
            if any(k in fn_u for k in ("PS-17", "GN-13", "GN-14", "TOPRAKLAMA")) or sc.system_discipline == "02_TOPRAKLAMA":
                tp_sheets.append(target_fn)
                fl = _extract_floor_code(target_fn)
                if fl != "GENEL":
                    tp_floors.add(fl)

                for t in sc.texts:
                    tu = t.text.upper()
                    # ECB Baraları
                    if "/ECB" in tu or "ECB/" in tu or "E.T.B" in tu:
                        raw_bar = t.text.strip()
                        ecb_bars_by_floor[fl].add(raw_bar)
                        ecb_bars_by_floor["ALL"].add(raw_bar)

                    # Topraklama Bağlantı ve Pano Etiketleri
                    is_ts = bool(
                        re.search(rf"\bTS{re.escape(station_number)}(?!\d)", tu)
                        or re.search(r"\bTS\d{2}", tu)
                        or re.search(r"\bTS-", tu)
                    )
                    is_grnd_lbl = is_ts or "/ECB" in tu or "ECB/" in tu or any(
                        k in tu for k in ("MCC", "LVS", "İAP", "IAP", "CDB", "PANO", "PANEL", "UPS")
                    )
                    if is_grnd_lbl:
                        raw_txt = t.text.strip()
                        grounding_texts.append(raw_txt)
                        norm_txt = re.sub(r"[^A-Z0-9]", "", raw_txt.upper().replace("İ", "I"))
                        if norm_txt:
                            grounding_normalized_set.add(norm_txt)

                        for part in re.split(r"[/\\_\-\s\+]+", raw_txt.upper().replace("İ", "I")):
                            p_sub = re.sub(r"[^A-Z0-9]", "", part)
                            if p_sub:
                                grounding_parts.add(p_sub)
                                p_stripped = re.sub(rf"^(?:TS{re.escape(station_number)}|TS|S{re.escape(station_number)})", "", p_sub)
                                if p_stripped and len(p_stripped) >= 3:
                                    grounding_parts.add(p_stripped)

        if not ka_panels or not tp_sheets:
            return

        # 3. Kademeli Eşleştirme ve Şiddet Yönetimi
        unmatched_ground: List[str] = []

        for pan in sorted(ka_panels):
            pan_u = pan.upper()
            pan_norm = re.sub(r"[^A-Z0-9]", "", pan_u.replace("İ", "I"))
            pan_floors = panel_to_floors.get(pan, set())
            pan_core = re.sub(rf"^S{re.escape(station_number)}", "", pan_norm)

            matched = False
            match_status = "UYGUN"
            match_confidence = 1.0
            match_detail = ""

            # Tier 1: Birebir / Normalize Eşleşme
            if pan_norm in grounding_normalized_set or pan_norm in grounding_parts:
                matched = True
                match_confidence = 1.0
                match_detail = f"Topraklama paftasında birebir etiket ile teyit edildi ({pan})"
            elif pan_core and len(pan_core) >= 5 and (pan_core in grounding_parts or any(pan_core in gp for gp in grounding_parts)):
                matched = True
                match_confidence = 0.90
                matched_gp = next((gp for gp in grounding_parts if pan_core in gp or gp in pan_core), pan_core)
                match_detail = f"Topraklama paftasındaki bağlantı etiketiyle ({matched_gp}) çekirdek kod ({pan_core}) üzerinden eşleşti."
            else:
                # Tier 2: Çekirdek Kod / Alt Parça Eşleşmesi (örn: TS19LVS401/S19MCC301/01 -> LVS401 veya MCC301)
                for gt in grounding_texts:
                    gt_norm = re.sub(r"[^A-Z0-9]", "", gt.upper().replace("İ", "I"))
                    if pan_core and len(pan_core) >= 4 and pan_core in gt_norm:
                        matched = True
                        match_confidence = 0.85
                        match_detail = f"Topraklama paftasındaki '{gt}' irtibatı ile çekirdek kod ({pan_core}) üzerinden eşleşti."
                        break
                    if pan_norm in gt_norm:
                        matched = True
                        match_confidence = 0.90
                        match_detail = f"Topraklama paftasındaki '{gt}' irtibatı ile eşleşti."
                        break

            # Tier 3: Kat / Mahal Eşpotansiyel Bara (ECB) İrtibatı
            if not matched and pan_floors:
                for fl in pan_floors:
                    fl_ecbs = ecb_bars_by_floor.get(fl, set())
                    m_num = re.search(r"(\d{3})", pan_norm)
                    if m_num:
                        p_num = m_num.group(1)
                        matching_ecb = next((ecb for ecb in fl_ecbs if p_num in ecb), None)
                        if matching_ecb:
                            matched = True
                            match_confidence = 0.80
                            match_detail = f"Topraklama paftasında {fl} katı eşpotansiyel barası ({matching_ecb}) ile mahal üzerinden eşleşti."
                            break

            if matched:
                report.reconciliation_items.append(ReconciliationItem(
                    category="PANO_VS_TOPRAKLAMA",
                    sheet_name=", ".join(tp_sheets[:3]),
                    item_id=pan,
                    source_a_label=f"Kuvvetli Akım Panosu: {pan}",
                    source_b_label=match_detail,
                    status=match_status,
                    detail=match_detail,
                    confidence_score=match_confidence,
                ))
            else:
                # Tier 4: Şiddeti Kanıta Bağlamak (Evidence-based Severity)
                has_floor_coverage = False
                if pan_floors and tp_floors:
                    has_floor_coverage = any(f in tp_floors for f in pan_floors)
                elif tp_sheets:
                    has_floor_coverage = len(tp_sheets) >= len(ka_sheets)

                if not has_floor_coverage and pan_floors and "GENEL" not in pan_floors:
                    # DURUM A: Katın topraklama paftası analiz setinde yok -> UNCERTAINTY (hata/uyarı değil!)
                    scope_str = ", ".join(pan_floors)
                    report.reconciliation_items.append(ReconciliationItem(
                        category="PANO_VS_TOPRAKLAMA",
                        sheet_name=", ".join(tp_sheets[:3]) if tp_sheets else "Yok",
                        item_id=pan,
                        source_a_label=f"Kuvvetli Akım Panosu: {pan} ({scope_str})",
                        source_b_label="Bu kata ait PS-17/GN-14 topraklama paftası analiz setinde bulunamadı",
                        status="İNCELEME_GEREKLİ",
                        detail=f"{pan} panosu {scope_str} katında yer almakta olup, bu kata ait PS-17 topraklama paftası analiz setinde bulunmadığından topraklama irtibatı kesin teyit edilememiştir.",
                        confidence_score=0.50,
                    ))
                    report.uncertainties.append(UncertaintyItem(
                        code=f"UNC-GRND-SHEET-MISSING-{pan_norm}",
                        title=f"Topraklama Paftası Kapsamı Dışında Kalan Pano ({pan})",
                        floor_or_scope=scope_str,
                        suspected_element=pan,
                        confidence_score=0.50,
                        evidence=f"Kuvvetli akım panosu {pan} tespit edildi ancak panonun katına ({scope_str}) ait PS-17 topraklama paftası analiz setinde yer almadığı için topraklama irtibatı teyit edilemedi.",
                        impact_description="Panonun topraklama irtibatının projede olup olmadığı doğrulanamadı.",
                        recommended_verification=f"İlgili kata ({scope_str}) ait PS-17/GN-14 topraklama paftası analiz setine dahil edilmelidir.",
                    ))
                else:
                    # DURUM B: Katın topraklama paftası var ama pano etiketi bulunamadı -> WARNING + MUHTEMEL
                    unmatched_ground.append(pan)
                    report.reconciliation_items.append(ReconciliationItem(
                        category="PANO_VS_TOPRAKLAMA",
                        sheet_name=", ".join(tp_sheets[:3]),
                        item_id=pan,
                        source_a_label=f"Kuvvetli Akım Panosu: {pan}",
                        source_b_label=f"Topraklama Paftasında ({', '.join(tp_sheets[:3])}) bağlantı kodu tespit edilemedi",
                        status="EKSİK",
                        detail=f"{pan} panosu Kuvvetli Akım paftasında aktif linye beslerken topraklama paftasında {station_code}/ECB veya TS{station_number} bağlantısıyla etiketlenmemiştir.",
                        confidence_score=0.70,
                    ))

        if unmatched_ground:
            report.findings.append(AuditFinding(
                severity="WARNING",
                module="ÇAPRAZ_MUTABAKAT",
                code="REC-GRND-MISSING",
                title=f"Kuvvetli Akım Panolarının Topraklama Paftasında {station_code} Bağlantı Teyit Edilemedi",
                floor_or_scope="İstasyon Geneli",
                sheet_names=ka_sheets + tp_sheets,
                element_id=", ".join(unmatched_ground[:5]),
                measured_value=f"Topraklama irtibatı teyit edilemeyen panolar: {', '.join(unmatched_ground)}",
                standard_limit=f"Tüm Dağıtım Panolarının Topraklama Paftasında {station_code}/ECB veya TS{station_number} irtibat kodu olmalıdır",
                standard_ref="EN 50122-1 & Elektrik Tesislerinde Topraklamalar Yönetmeliği",
                engineering_explanation=f"İlgili katın topraklama paftası mevcut olmasına rağmen {len(unmatched_ground)} adet panonun açık topraklama irtibat kodu (TS veya ECB) tespit edilemedi. İsimlendirme farklılığı (varyasyon) olabileceğinden mühendis teyidi önerilir.",
                recommendation="Bu panoların en yakın Eşpotansiyel Baraya (ECB) bağlantı kodları PS-17 paftasında kontrol edilmelidir.",
                confidence_level="MUHTEMEL",
                confidence_score=0.70,
                evidence_chain=[
                    f"Kuvvetli akım panoları: {', '.join(unmatched_ground[:4])}",
                    f"Topraklama paftaları: {', '.join(tp_sheets[:3])}",
                    "Kademeli eşleştirmede (birebir ve çekirdek kod) doğrudan eşleşme bulunamadı."
                ],
                standard_version="EN 50122-1:2022",
                clause_or_table="EN 50122-1 Madde 6 (Equipotential Bonding of Substation Panels)",
                data_sources={"panel_source": "EXPLICIT_CIRCUIT_TAG", "grounding_source": "EXPLICIT_TEXT_SCAN"},
                assumptions_used=["Pano ve topraklama paftası etiketlerinde isimlendirme varyasyonu olabileceği dikkate alındı."],
            ))
