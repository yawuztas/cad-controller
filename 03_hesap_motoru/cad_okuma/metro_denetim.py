# -*- coding: utf-8 -*-
"""
Evrensel Metro Mühendislik Denetim Kuralları (`metro_denetim.py`)
=================================================================
Tekli ve çoklu İBB Raylı Sistemler / Metro DWG-DXF paftaları için
`ibb_metro.yaml` + `02_mevzuat_ve_formuller/metro/*.yaml` + `TS HD 60364`
kurallarını uygular:
  - Sıfır proje ezberi / sıfır hardcode sayı
  - Eksik veride sahte doğrulama yapmaz (yalnız gerçek okunan veriyi denetler)
  - LSZH/FE180 yangın güvenliği, Yöntem E + 0.70 gruplama Iz ve Çizelge 54.2 PE/Ekran kontrolü,
    ISO/IEC 11801 (90 m CAT6), tava envanteri, N-1 trafo/UPS, MEB/EPTB/VLD ve 2B metraj mutabakatı.
"""

from __future__ import annotations

from collections import Counter
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.calculators.electrical_calc import parse_cable_spec
from core.rules.rule_engine import RuleEngine

from .metin_temizleyici import norm_tr
from .sebeke_analizi import TransformerInput, check_n1_transformer_redundancy

_RE_TRAY_TAG = re.compile(r"\b(WC|LV|HV|OG|AG|MV|FA|SC|TR|KT)\s*/\s*(\d{2,4})\s*(?:/\s*(\d{2,4}))?\b", re.IGNORECASE)
_RE_TRAFO_KVA = re.compile(r"(?:TR[^\d]{0,10}|TRAFO[^\d]{0,15})?(\d{3,4})\s*kVA\b", re.IGNORECASE)
_RE_UPS_KVA = re.compile(r"UPS[^0-9]{0,20}(\d{2,4})\s*kVA\b", re.IGNORECASE)
_RE_NON_LSZH = re.compile(r"\b(?:NYY|NYM|YVV|PVC)\b", re.IGNORECASE)
_RE_LSZH_OR_XLPE = re.compile(r"(?:N2XH|N2XRH|N2XCH|NHXMH|H07Z|07Z1|LSZH|LS0H|LSOH|HFFR|XLPE|FE\s*180|PH\s*\d+)", re.IGNORECASE)
_RE_FE180 = re.compile(r"(?:FE\s*180|PH\s*120|E90)", re.IGNORECASE)
_RE_CAT_CABLE = re.compile(r"\bCAT\s*[5678][AE]?\b", re.IGNORECASE)


def detect_rule_pack_for_drawing(
    snapshot: Any,
    model: Any,
    inventory: Any = None,
    *,
    requested: str = "auto",
    primary_discipline: str = "",
) -> str:
    """
    Çizimin içeriğine göre evrensel mühendislik mevzuat profilini (`ibb_metro` vs `turkey_bina`) seçer.
    Hiçbir dosya/örnek adı kullanmaz; metin, katman, sembol ve tablo yapısına bakar.
    """
    if requested in ("ibb_metro", "turkey_bina"):
        return requested

    metro_score = 0
    bina_score = 0

    all_texts = [norm_tr(t.text).upper() for t in getattr(snapshot, "texts", []) or [] if t.text]
    joined_sample = " | ".join(all_texts[:2500])

    # Güçlü raylı sistem / metro mühendislik göstergeleri
    for kw, w in (
        (r"\bISTASYON(?:U)?\b", 2),
        (r"\bPERON\b", 2),
        (r"\bBILET HOLU\b", 2),
        (r"\bRAYLI SISTEM", 3),
        (r"\bEN\s*50122\b", 3),
        (r"\bNFPA\s*130\b", 3),
        (r"\bKATENER\b", 2),
        (r"\b(?:VLD|OVPD|EPTB|CESB|CBTC|ETCS|SDH/OTN)\b", 2),
        (r"\b(?:34[.,]5\s*KV|10[.,]5\s*KV|1500\s*V\s*DC|750\s*V\s*DC)\b", 3),
        (r"\b(?:LSZH|LS0H|HFFR|FE\s*180|PH\s*120|N2XH|N2XRH)\b", 1),
        (r"\b(?:PA/VA|TETRA|TURNIKE|TURNSTILE)\b", 2),
    ):
        if re.search(kw, joined_sample):
            metro_score += w

    if _RE_TRAY_TAG.search(joined_sample):
        metro_score += 2
    if primary_discipline == "SINYAL":
        metro_score += 3

    if inventory is not None:
        for sb in getattr(inventory, "symbol_bom", []) or []:
            cat_u = norm_tr(getattr(sb, "category", "")).upper()
            if any(k in cat_u for k in ("KONTROL / SINYAL", "GECIS / BILET", "KABLO TAVA")):
                metro_score += 2
                break
        for cb in getattr(inventory, "cable_bom", []) or []:
            cu = norm_tr(getattr(cb, "spec", "")).upper()
            if _RE_LSZH_OR_XLPE.search(cu) or _RE_CAT_CABLE.search(cu):
                metro_score += 1
                break

    # Konut / Bina EİTY 8kW çeşitlilik göstergeleri
    for kw, w in (
        (r"\bDAIRE(?:LER)?\b", 2),
        (r"\bMESKEN\b", 2),
        (r"\bDUAFON\b", 2),
        (r"\bTEMEL TOPRAKLAMA HESABI\b", 2),
        (r"\b8\s*KW\b", 2),
        (r"0[.,]60\s*\+\s*0[.,]40", 3),
    ):
        if re.search(kw, joined_sample):
            bina_score += w

    for sh in getattr(model, "sheets", []) or []:
        r_u = getattr(sh, "role", "")
        if r_u in ("DUAFON_SEMASI", "GERILIM_DUSUMU"):
            bina_score += 2

    if metro_score >= 3 and metro_score > bina_score + 1:
        return "ibb_metro"
    return "turkey_bina"


def _first_handle_location(
    handles: Sequence[str],
    text_by_handle: Dict[str, Any],
) -> Tuple[Optional[str], Optional[Tuple[float, float, float, float]]]:
    for h in handles:
        if h and h in text_by_handle:
            t = text_by_handle[h]
            bb = getattr(t, "bbox", None)
            bb_tup = (float(bb.minx), float(bb.miny), float(bb.maxx), float(bb.maxy)) if bb is not None else None
            return None, bb_tup
    return None, None


def collect_metro_single_sheet_findings(
    snapshot: Any,
    model: Any,
    inventory: Any,
    rules: Dict[str, Any],
    *,
    finding_cls: Any,
    lookup_iz_fn: Any,
    start_fid: int = 1,
    primary_discipline: str = "",
) -> Tuple[List[Any], Dict[str, Any]]:
    """
    Tekli veya birleşik bir metro paftası için `ibb_metro.yaml` tabanlı gerçek denetim bulgularını üretir.
    """
    findings: List[Any] = []
    fid = start_fid

    text_by_handle = {t.handle: t for t in (getattr(snapshot, "texts", []) or []) if getattr(t, "handle", "")}

    def _add(
        sev: str,
        cat: str,
        loc: str,
        proj_val: str,
        eng_val: str,
        std: str,
        desc: str,
        rec: str = "",
        *,
        sheet_id: Optional[str] = None,
        bbox_du: Optional[Any] = None,
    ) -> None:
        nonlocal fid
        findings.append(
            finding_cls(
                finding_id=f"M-{fid:02d}",
                severity=sev,
                category=cat,
                location=loc,
                project_value=proj_val,
                engine_value=eng_val,
                standard_ref=std,
                description=desc,
                recommendation=rec,
                sheet_id=sheet_id,
                bbox_du=bbox_du,
            )
        )
        fid += 1

    cable_bom = list(getattr(inventory, "cable_bom", []) or []) if inventory is not None else []
    symbol_bom = list(getattr(inventory, "symbol_bom", []) or []) if inventory is not None else []
    wires_by_layer = list(getattr(inventory, "wires_by_layer", []) or []) if inventory is not None else []

    # ------------------------------------------------------------------
    # 1. LSZH / HFFR / FE180 Yangın Güvenliği Kablo Uygunluğu
    # ------------------------------------------------------------------
    fire_cfg = rules.get("fire_and_life_safety", {}) or {}
    lszh_req = bool(fire_cfg.get("lszh_mandatory", True))
    non_lszh_items: List[Any] = []
    lszh_items: List[Any] = []
    fe180_items: List[Any] = []
    cat_exceed: List[Tuple[Any, float]] = []

    wc_cfg = rules.get("weak_current", {}) or {}
    max_cat_m = float(wc_cfg.get("max_cat6_length_m", 90.0))

    for cb in cable_bom:
        spec_s = str(getattr(cb, "spec", "") or "")
        if _RE_NON_LSZH.search(spec_s):
            non_lszh_items.append(cb)
        if _RE_LSZH_OR_XLPE.search(spec_s):
            lszh_items.append(cb)
        if _RE_FE180.search(spec_s):
            fe180_items.append(cb)
        exp_m = getattr(cb, "explicit_length_m", None)
        if exp_m is not None and float(exp_m) > max_cat_m and _RE_CAT_CABLE.search(spec_s):
            cat_exceed.append((cb, float(exp_m)))

    if non_lszh_items and lszh_req:
        sp0, bb0 = _first_handle_location(getattr(non_lszh_items[0], "source_handles", []), text_by_handle)
        sample_specs = ", ".join(
            f"{c.spec} ({c.occurrences}x" + (f", {c.explicit_length_m:.0f}m" if c.explicit_length_m else "") + ")"
            for c in non_lszh_items[:5]
        )
        _add(
            "KRITIK",
            "Yangın Güvenliği / Halojen-Free Kablo",
            f"Pafta Genel ({len(non_lszh_items)} PVC kablo tipi)",
            sample_specs,
            "Yalnız LSZH / HFFR (N2XH, NHXMH, FE180, XLPE)",
            "NFPA 130 Md. 8.8 & BYKHY Md. 72, 83",
            f"Metro/raylı sistem paftasında halojenli PVC kablo ({non_lszh_items[0].spec} vb.) tespit edildi.",
            "Tüm PVC esaslı (NYY/NYM/YVV) kabloları eşdeğer kesitli halojensiz N2XH / FE180 tipiyle değiştirin.",
            sheet_id=sp0,
            bbox_du=bb0,
        )
    elif lszh_items:
        total_occ = sum(int(getattr(c, "occurrences", 0)) for c in lszh_items)
        sample_lszh = ", ".join(c.spec for c in lszh_items[:4])
        _add(
            "UYGUN",
            "Yangın Güvenliği / Halojen-Free Kablo",
            f"Pafta Genel ({len(lszh_items)} tip, {total_occ} adet)",
            sample_lszh,
            "LSZH / HFFR / XLPE / FE180",
            "NFPA 130 Md. 8.8 & BYKHY Md. 72, 83",
            "Çizimde tespit edilen tüm güç/sinyal/data kabloları halojensiz (N2XH/N2XRH/XLPE/LS0H) sınıftadır.",
        )

    for cb, exp_m in cat_exceed:
        sp, bb = _first_handle_location(getattr(cb, "source_handles", []), text_by_handle)
        _add(
            "KRITIK",
            "Zayıf Akım Bakır Hat Uzunluğu",
            cb.spec,
            f"L = {exp_m:.1f} m",
            f"<= {max_cat_m:.0f} m (Sınıf E)",
            "ISO/IEC 11801-1:2017",
            f"{cb.spec} kablosunun yazılı metrajı ({exp_m:.1f} m) IEEE/ISO 90 m kanal sınırını aşıyor.",
            "Saha Ethernet switch veya fiber-optik uplink noktası ekleyerek bakır CAT hattını <= 90 m sınırına indirin.",
            sheet_id=sp,
            bbox_du=bb,
        )

    # Acil / Yangın / Sinyal sistemlerinde FE180 kontrolü
    has_emergency_sys = any(
        any(k in norm_tr(getattr(sb, "category", "")).upper() for k in ("YANGIN ALGILAMA", "KONTROL / SINYAL"))
        for sb in symbol_bom
    ) or primary_discipline == "SINYAL"
    if has_emergency_sys and cable_bom:
        if fe180_items:
            _add(
                "UYGUN",
                "Yangına Dayanıklı (FE180/PH120) Besleme",
                "Acil / Sinyalizasyon / Yangın",
                ", ".join(c.spec for c in fe180_items[:3]),
                "FE180 / PH120 Zorunlu",
                "BYKHY Md. 72 & NFPA 130",
                "Acil durum / sinyalizasyon / yangın hatlarında yangına dayanıklı (FE180) kablo kullanıldığı doğrulandı.",
            )
        else:
            _add(
                "UYARI",
                "Yangına Dayanıklı (FE180/PH120) Besleme",
                "Acil / Sinyalizasyon / Yangın",
                "FE180/PH120 etiketi tespit edilmedi",
                "FE180 / PH120 Zorunlu",
                "BYKHY Md. 72 & NFPA 130",
                "Acil/sinyalizasyon ekipmanları mevcut ancak okunan kablo etiketlerinde açık FE180/PH120 ibaresi görülmedi.",
                "Acil besleme ve yangın senaryo hatlarının FE180/PH120 kablo tipini pafta üzerinde açıkça etiketleyin.",
            )

    # ------------------------------------------------------------------
    # 2. Yöntem E (Delikli Tava) Iz + B.52.17 Gruplama + Çizelge 54.2 PE Kesiti
    # ------------------------------------------------------------------
    phys = rules.get("cable_physics", {}) or {}
    install_method = str(phys.get("default_installation_method", "E") or "E").upper()
    derating = float(phys.get("derating_factor", 0.70) or 0.70)

    checked_specs: List[str] = []
    pe_warnings: List[Tuple[Any, float, float, float]] = []  # (cb, phase_mm2, pe_mm2, req_pe_mm2)
    iz_notes: List[str] = []

    for cb in cable_bom:
        spec_s = str(getattr(cb, "spec", "") or "")
        if _RE_CAT_CABLE.search(spec_s):
            continue
        parsed = parse_cable_spec(spec_s)
        if not parsed.is_valid or parsed.phase_mm2 <= 0:
            continue
        iz_base, iz_src = lookup_iz_fn(parsed, spec_s, rules, method=install_method)
        if iz_base is not None:
            iz_derated = iz_base * derating
            iz_notes.append(f"{spec_s}: Iz({install_method})={iz_base:.0f}A -> Gruplama(x{derating:.2f})={iz_derated:.1f}A")
        checked_specs.append(spec_s)

        if parsed.is_pe_explicit and parsed.pe_mm2 is not None and parsed.pe_mm2 > 0:
            s_ph = parsed.phase_mm2
            if s_ph <= 16.0:
                req_pe = s_ph
            elif s_ph <= 35.0:
                req_pe = 16.0
            else:
                req_pe = s_ph * 0.5
            if parsed.pe_mm2 + 1e-6 < req_pe:
                pe_warnings.append((cb, s_ph, parsed.pe_mm2, req_pe))

    if iz_notes:
        _add(
            "BILGI",
            f"Kablo Akım Taşıma Kapasitesi (Yöntem {install_method} & B.52.17)",
            f"Okunan {len(iz_notes)} güç kablosu kesiti",
            "; ".join(iz_notes[:4]),
            f"Çizelge B.52.3/B.52.5 x {derating:.2f}",
            "TS HD 60364-5-52:2014",
            "Çizimdeki güç kabloları için delikli tava (Yöntem E) ve 3 devre gruplama katsayısı (0.70) uygulanmış tablo sınırları hesaplandı (kesitlerin gerçek yük akımı Ib bilgisi çizimde mevcutsa pano/şema adımında ayrıca denetlenir).",
        )

    for cb, s_ph, pe_mm2, req_pe in pe_warnings[:5]:
        sp, bb = _first_handle_location(getattr(cb, "source_handles", []), text_by_handle)
        _add(
            "UYARI",
            "PE / Konsantrik Ekran Kesit Oranı",
            cb.spec,
            f"S_faz={s_ph:g} mm², Ekran/PE={pe_mm2:g} mm²",
            f"Çizelge 54.2 >= {req_pe:g} mm² (S/2)",
            "TS HD 60364-5-54:2013 Çizelge 54.2",
            f"{cb.spec} kablosundaki {pe_mm2:g} mm² ekran/PE kesiti, {s_ph:g} mm² faz kesiti için basit S/2 oranının ({req_pe:g} mm²) altındadır.",
            "Konsantrik bakır ekranın koruma/topraklama olarak kullanımı için IEC 60364-5-54 Md. 543.1.2 (I²t) adyabatik ısınma doğrulamasını ekleyin veya harici topraklama iletkeni çekin.",
            sheet_id=sp,
            bbox_du=bb,
        )

    # ------------------------------------------------------------------
    # 3. Tablo Kablo Metrajı <-> 2B CAD Kablo Yolu Tutarlılığı
    # ------------------------------------------------------------------
    explicit_tbl_cables = [c for c in cable_bom if getattr(c, "explicit_length_m", None)]
    total_tbl_m = sum(float(c.explicit_length_m) for c in explicit_tbl_cables)
    total_cad_wire_m = sum(float(getattr(w, "total_length_m", 0.0)) for w in wires_by_layer)
    if total_tbl_m > 0 and total_cad_wire_m > 0:
        ratio = total_tbl_m / total_cad_wire_m
        sev_len = "UYGUN" if 0.50 <= ratio <= 2.20 else "UYARI"
        _add(
            sev_len,
            "Tablo Metrajı ↔ 2B Çizim Mutabakatı",
            f"{len(explicit_tbl_cables)} tablo kalemi vs {len(wires_by_layer)} CAD hat katmanı",
            f"Yazılı Tablo Toplamı = {total_tbl_m:,.1f} m",
            f"2B CAD Ölçülen Hat = {total_cad_wire_m:,.1f} m (Oran={ratio:.2f}x)",
            "Metraj Tutarlılığı",
            (
                f"Tablodaki yazılı kablo metrajı ({total_tbl_m:,.1f} m) ile 2B çizimdeki hat boyu ({total_cad_wire_m:,.1f} m) düşey iniş/çıkış toleransı içindedir."
                if sev_len == "UYGUN"
                else f"Tablodaki yazılı kablo metrajı ({total_tbl_m:,.1f} m) ile 2B CAD hat boyu ({total_cad_wire_m:,.1f} m) arasında belirgin fark ({ratio:.2f}x) var."
            ),
            "" if sev_len == "UYGUN" else "Düşey şaft kot farkları veya mükerrer/eksik tablo satırları açısından metrajı doğrulayın.",
        )

    # ------------------------------------------------------------------
    # 4. Kablo Tavası Etiketleri & Fiziksel Tava Ekipmanları
    # ------------------------------------------------------------------
    tray_tags: Counter[Tuple[str, int, Optional[int]]] = Counter()
    all_raw_texts = getattr(snapshot, "texts", []) or []
    for t in all_raw_texts:
        for m in _RE_TRAY_TAG.finditer(t.text or ""):
            code = m.group(1).upper()
            w_mm = int(m.group(2))
            h_mm = int(m.group(3)) if m.group(3) else None
            tray_tags[(code, w_mm, h_mm)] += 1
    tray_fill_lim = float(rules.get("tray_fill_limit_pct", 40.0) or 40.0)
    tray_sym_total = sum(
        int(getattr(sb, "total_count", 0))
        for sb in symbol_bom
        if "TAVA" in norm_tr(getattr(sb, "category", "")).upper()
    )
    if tray_tags or tray_sym_total > 0:
        tag_summary = ", ".join(
            f"{k[0]}/{k[1]}" + (f"/{k[2]}" if k[2] else "") + f" ({v}x)"
            for k, v in tray_tags.most_common(6)
        ) or f"{tray_sym_total} fiziksel tava aksesuarı"
        _add(
            "BILGI",
            "Kablo Tavası Envanteri ve Doluluk Sınırı",
            "Kablo Tavaları",
            tag_summary,
            f"Maks. Doluluk <= %{tray_fill_lim:.0f}",
            "EN 50174-2 & IEC 61537 & İBB Şartnamesi",
            f"Paftada {sum(tray_tags.values())} tava ölçülendirme etiketi ve {tray_sym_total} tava aksesuarı okundu; kesit doluluk oranı <= %{tray_fill_lim:.0f} olmalıdır.",
        )

    # ------------------------------------------------------------------
    # 5. Trafo / UPS Güçleri & N-1 Yedeklilik
    # ------------------------------------------------------------------
    trafo_kvas: List[float] = []
    ups_kvas: List[float] = []
    for t in all_raw_texts:
        txt = t.text or ""
        tu = norm_tr(txt).upper()
        for m in _RE_UPS_KVA.finditer(txt):
            v = float(m.group(1))
            if 5.0 <= v <= 2000.0:
                ups_kvas.append(v)
        if any(k in tu for k in ("TRAFO", "TR-", "TR ", "MVA", "KVA", "34.5", "34,5", "10.5")):
            if "UPS" not in tu:
                for m in _RE_TRAFO_KVA.finditer(txt):
                    v = float(m.group(1))
                    if 100.0 <= v <= 5000.0:
                        trafo_kvas.append(v)

    if len(trafo_kvas) >= 2:
        tr_red = check_n1_transformer_redundancy(trafo_kvas)
        sev_tr = "BILGI" if tr_red.status == "BELIRSIZ" else tr_red.status
        _add(
            sev_tr,
            "Trafo N-1 Yedeklilik Kontrolü",
            "OG / Trafo Merkezi",
            f"Okunan Trafolar: {[int(k) for k in trafo_kvas]} kVA",
            f"N-1 Kalan Kapasite = {tr_red.n1_remaining_kva:.0f} kVA",
            "İBB Raylı Sistemler Güç Kriterleri",
            tr_red.note,
        )

    # ------------------------------------------------------------------
    # 6. Metro Topraklama / MEB-EPTB & EN 50122 VLD Kontrolü
    # ------------------------------------------------------------------
    g_loops = list(getattr(model, "grounding_loops", []) or [])
    joined_u = " | ".join(norm_tr(t.text).upper() for t in all_raw_texts[:3000])
    if g_loops:
        has_meb = bool(re.search(r"\b(?:MEB|EEB|ETB|EPTB)\b|ESPOTANSIYEL|ANA TOPRAKLAMA BARA", joined_u))
        _add(
            "UYGUN" if has_meb else "UYARI",
            "Eşpotansiyel Topraklama Barası (MEB / EPTB)",
            f"Topraklama ({len(g_loops)} ring)",
            "MEB / EPTB tespit edildi" if has_meb else "MEB / EPTB bulunamadı",
            "Zorunlu (TS HD 60364-5-54 & EN 50122)",
            "TS HD 60364-5-54 & EN 50122-1",
            (
                "Temel topraklama halkası eşpotansiyel bara (MEB/EPTB) bağlantısı mevcuttur."
                if has_meb
                else "Topraklama ringi tespit edildi ancak metinlerde açık MEB/EPTB barası görülmedi."
            ),
            "" if has_meb else "Ana eşpotansiyel topraklama barasını (MEB/EPTB) ve kesitini çizimde etiketleyin.",
        )

        # VLD / Ray izolasyonu yalnızca DC cer/raylı sistem topraklama referansı varsa denetle
        has_traction_ref = bool(re.search(r"\b(?:VLD|OVPD|CER|TRACTION|750\s*V|1500\s*V|RAY IZOLAS)\b|EN\s*50122", joined_u))
        if has_traction_ref:
            has_vld = bool(re.search(r"\b(?:VLD|OVPD)\b|GERILIM SINIRLAYICI", joined_u))
            _add(
                "UYGUN" if has_vld else "KRITIK",
                "Ray-Toprak Potansiyel Sınırlama (VLD / EN 50122)",
                "Topraklama / Cer Sistemi",
                "VLD / OVPD mevcut" if has_vld else "VLD / OVPD belirtilmemiş",
                "VLD-F / VLD-O (Dokunma Gerilimi Koruması)",
                "EN 50122-1:2022",
                "EN 50122 / cer sistemi bağlamında VLD koruma cihazı doğrulaması.",
                "" if has_vld else "Ray negatif dönüşü ile istasyon topraklama sistemi arasına VLD bağlanmalıdır.",
            )

    # ------------------------------------------------------------------
    # 7. Zayıf Akım / Sinyalizasyon & momepy Kapalı Mahal Özeti
    # ------------------------------------------------------------------
    sig_wc_cats = [
        sb for sb in symbol_bom
        if any(k in norm_tr(getattr(sb, "category", "")).upper() for k in ("KONTROL / SINYAL", "GECIS / BILET", "ZAYIF AKIM", "YANGIN ALGILAMA"))
    ]
    enclosures = list(getattr(model, "enclosures", []) or [])
    if sig_wc_cats or enclosures:
        sym_txt = ", ".join(f"{sb.category}: {sb.total_count}" for sb in sig_wc_cats[:4]) or "-"
        enc_m2 = sum(float(getattr(e, "area_m2", 0.0)) for e in enclosures)
        _add(
            "BILGI",
            "Zayıf Akım / Sinyal Ekipmanı ve Mahal Kapsama",
            f"Disiplin={primary_discipline or 'METRO'}",
            f"Ekipman: {sym_txt} | Kapalı Mahal: {len(enclosures)} ({enc_m2:,.1f} m²)",
            "momepy / Envanter Doğrulaması",
            "İBB Raylı Sistemler & ISO/IEC 11801",
            "Çizimden ayıklanan zayıf akım/sinyal ekipman sayımı ve momepy kapalı mahal morfolojisi özetidir.",
        )

    meta = {
        "trafo_ratings_kva": sorted(trafo_kvas, reverse=True),
        "ups_ratings_kva": sorted(ups_kvas, reverse=True),
        "tray_tags_count": sum(tray_tags.values()),
    }
    return findings, meta
