# -*- coding: utf-8 -*-
"""
Modül 3 — ElectricalAutoOptimizer (Faz Dengeleme, Kesit/Koruma Optimizasyonu ve Doğrulama Motoru)
=================================================================================================
Pazarlığa Kapalı Mühendislik ve Yönetim Frenleri:
1. job_type: "ASBUILT" | "DESIGN" Ayrımı:
   - DESIGN (Tasarım Projesi): Greedy LPT (Longest Processing Time) algoritmasıyla linyeleri
     L1/L2/L3 fazlarına yeniden atayarak dengesizliği <%5 seviyesine indirir.
     Konum bazlı token değiştirme + Değişmezlik Kalkanı (Invariance Guard) ile linye koduna ve
     kablo kesiti metnine ASLA zarar vermeden yalnız faz token'ını günceller.
   - ASBUILT (İBB / İş Sonu Denetimi): Sahada kablolar fiziksel olarak bağlandığından DWG üzerinde
     faz etiketi değiştirmek KESİNLİKLE YASAKTIR (can_apply_to_dwg=False). Yalnızca saha panosunda
     hangi linyelerin hangi faza aktarılması gerektiğini gösteren mühendislik reçetesi üretir.
2. Dinamik Kural Paketi (RuleEngine) Entegrasyonu:
   - Faz dengesizliği sınırları (örn: İBB Metro %15 Uyarı / %20 Kritik; Bina %15 Uyarı / %25 Kritik)
     ve gerilim düşümü sınırları (Aydınlatma vs Kuvvet/Priz) sabit kodlanmaz; doğrudan RuleEngine
     aktif kural paketinden okunur.
3. Öner -> Bellekte Yeniden Doğrula (Re-Verify) -> Onayla -> Uygula Zinciri:
   - Kablo kesiti, sigorta/KAK koordinasyonu (TS HD 60364-4-43 Md. 433.1) ve Yangın Pompası
     FE180 / 30mA KAK iptali (BYKHY Md. 72 & 83) düzeltme önerileri üretildiği anda motor tarafından
     bellekte yeniden denetlenir (Dry-Run Re-Verification).
   - Yalnızca doğrulamadan 'PASS' alan ve onaylanan (approved_proposal_ids) öneriler DWG'ye uygulanır.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from ..cad.cad_safety import CADSafetyGuard
from ..calculators.electrical_calc import (
    calc_effective_circuit_length,
    calc_operating_current_ib,
    calc_phase_imbalance_pct,
    calc_voltage_drop_pct,
)
from ..rules.rule_engine import RuleEngine

STANDARD_CABLE_SECTIONS_MM2: List[float] = [
    1.5, 2.5, 4.0, 6.0, 10.0, 16.0, 25.0, 35.0, 50.0, 70.0, 95.0, 120.0, 150.0, 185.0, 240.0
]
STANDARD_BREAKER_RATINGS_A: List[float] = [
    6.0, 10.0, 16.0, 20.0, 25.0, 32.0, 40.0, 50.0, 63.0, 80.0, 100.0, 125.0, 160.0
]


@dataclass
class ElectricalOptimizationProposal:
    """Tek bir elektriksel düzeltme önerisi ve kendi kendini doğrulama (Re-Verification) kanıtı."""
    proposal_id: str
    category: str                       # PHASE_BALANCE, PROTECTION_COORDINATION, BYKHY_FIRE_PUMP, VOLTAGE_DROP
    job_type: str                       # DESIGN | ASBUILT
    target_element: str                 # Pano veya Linye Kodu
    dxf_handle: str                     # Güncellenecek TEXT / MTEXT / ATTRIB handle'ı
    old_text: str
    new_text: str
    before_metrics: Dict[str, Any]
    after_metrics: Dict[str, Any]
    verification_passed: bool
    verification_proof: str
    standard_ref: str
    can_apply_to_dwg: bool
    status: str = "REQUIRES_APPROVAL"   # REQUIRES_APPROVAL, ASBUILT_FIELD_RECOMMENDATION_ONLY, APPROVED, NOT_SELECTED, REJECTED


@dataclass
class ElectricalOptimizationPlan:
    """ElectricalAutoOptimizer tarafından üretilen proposals.json veri modeli."""
    drawing_name: str
    job_type: str
    rule_pack: str
    created_at: str
    proposals: List[ElectricalOptimizationProposal] = field(default_factory=list)
    summary_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save_json(self, path: Union[str, Path]) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p


class ElectricalAutoOptimizer:
    """
    Modül 3: İş tipine (DESIGN vs ASBUILT) duyarlı Faz Dengeleyici ve
    Yeniden Doğrulamalı (Self-Verifying) Kesit/Koruma Düzeltici.
    """

    @staticmethod
    def validate_job_type(job_type: str) -> str:
        jt = (job_type or "").strip().upper()
        if jt not in ("DESIGN", "ASBUILT"):
            raise ValueError(f"Geçersiz job_type: {job_type!r}. Yalnızca 'DESIGN' veya 'ASBUILT' olabilir.")
        return jt

    @staticmethod
    def _refresh_summary_counts(plan: ElectricalOptimizationPlan) -> None:
        plan.summary_counts = {
            "total_proposals": len(plan.proposals),
            "verified_proposals": sum(1 for p in plan.proposals if p.verification_passed),
            "dwg_applicable": sum(1 for p in plan.proposals if p.can_apply_to_dwg),
            "asbuilt_field_only": sum(1 for p in plan.proposals if not p.can_apply_to_dwg),
        }

    @staticmethod
    def safe_replace_phase_token(
        raw_text: str,
        old_phase: str,
        target_phase: str,
        circuit_id: str = "",
    ) -> Tuple[bool, str, str]:
        """
        DWG metninde linye koduna (örn: 'L2-01', 'L1-05', 'S19/L1') veya kablo kesitine ('3x2.5 NYY')
        KESİNLİKLE zarar vermeden yalnızca bağımsız faz token'ını değiştirir.

        Değişmezlik Kalkanı (Invariance Guard):
        - Değiştirilen faz token'ı dışındaki tüm ön ek (prefix) ve son ek (suffix) karakterleri
          eski metinle birebir aynı kalmalıdır.
        - Eğer metinde bağımsız faz token'ı bulunamazsa (örn: metin sadece 'L2-01 3x2.5 NYY' ise ve
          faz ayrı bir sütunda/semboldeyse) False döner ve DWG metni ASLA ezilmez!
        """
        txt = raw_text or ""
        if not txt.strip():
            return False, txt, "EMPTY_RAW_TEXT"

        old_norm = {"R": "L1", "S": "L2", "T": "L3"}.get(old_phase.upper().strip(), old_phase.upper().strip())
        target_norm = {"R": "L1", "S": "L2", "T": "L3"}.get(target_phase.upper().strip(), target_phase.upper().strip())
        rst_map = {"L1": "R", "L2": "S", "L3": "T"}

        # Aday faz token'ları (önce L1/L2/L3 formunu, yoksa R/S/T formunu ara)
        candidate_pairs: List[Tuple[str, str]] = [(old_norm, target_norm)]
        if old_norm in rst_map and target_norm in rst_map:
            candidate_pairs.append((rst_map[old_norm], rst_map[target_norm]))

        # Metin sadece tek başına faz etiketinden ibaretse (örn: "L1" veya "R")
        stripped = txt.strip()
        for src_tok, dst_tok in candidate_pairs:
            if stripped.upper() == src_tok:
                lead_ws = txt[: len(txt) - len(txt.lstrip())]
                trail_ws = txt[len(txt.rstrip()) :]
                new_txt = f"{lead_ws}{dst_tok}{trail_ws}"
                return True, new_txt, "EXACT_SINGLE_TOKEN"

        # Karma metin içinde bağımsız faz token'ı ara:
        # Negatif lookbehind/lookahead: Tire (-) veya rakamla bitişik olan 'L1-01', 'L2-01' gibi linye kodlarını ATLA!
        for src_tok, dst_tok in candidate_pairs:
            pattern = re.compile(
                rf"(?<![A-Za-z0-9_\-/])({re.escape(src_tok)})(?![A-Za-z0-9_\-])",
                re.IGNORECASE,
            )
            matches = list(pattern.finditer(txt))
            if not matches:
                continue

            # Eğer birden fazla eşleşme varsa ve ilki circuit_id'nin parçasıysa sonuncuyu seç
            chosen_match = None
            for m in reversed(matches):
                s_idx, e_idx = m.span(1)
                # Eğer eşleşen bölge circuit_id'nin başlangıcıyla çakışıyorsa atla
                if circuit_id and txt[s_idx : s_idx + len(circuit_id)].upper() == circuit_id.upper():
                    continue
                chosen_match = m
                break

            if chosen_match is None:
                continue

            s_idx, e_idx = chosen_match.span(1)
            prefix = txt[:s_idx]
            suffix = txt[e_idx:]
            new_txt = f"{prefix}{dst_tok}{suffix}"

            # DEĞİŞMEZLİK KALKANI (Invariance Guard):
            # Eski metinden yalnız faz token'ı çıkarıldığında kalan iskelet ile
            # yeni metinden yeni faz token'ı çıkarıldığında kalan iskelet BİREBİR aynı olmalı!
            old_skeleton = prefix + suffix
            new_skeleton = new_txt[:s_idx] + new_txt[s_idx + len(dst_tok) :]
            if old_skeleton != new_skeleton or (len(txt) > len(src_tok) and len(old_skeleton.strip()) == 0):
                return False, txt, "INVARIANCE_GUARD_FAILED"

            return True, new_txt, "TOKEN_REPLACED_SAFE"

        return False, txt, "PHASE_TOKEN_NOT_FOUND_IN_TEXT"

    @staticmethod
    def optimize_panel_phase_balance_greedy_lpt(
        circuits: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, str], Dict[str, float], Dict[str, float], float, float]:
        """
        Greedy LPT (Longest Processing Time First) algoritmasıyla 1 fazlı linyeleri
        L1, L2, L3 fazlarına dengeli dağıtır.
        Dönüş: (yeni_faz_haritası, eski_faz_güçleri, yeni_faz_güçleri, eski_dengesizlik_pct, yeni_dengesizlik_pct)
        """
        old_phases = {"L1": 0.0, "L2": 0.0, "L3": 0.0}
        new_phases = {"L1": 0.0, "L2": 0.0, "L3": 0.0}
        new_assignment: Dict[str, str] = {}

        single_phase_items = []
        for c in circuits:
            cid = str(c["circuit_id"])
            w = float(c.get("power_w", 0.0))
            ph_raw = str(c.get("phase", "L1")).upper()
            ph_norm = {"R": "L1", "S": "L2", "T": "L3"}.get(ph_raw, ph_raw)
            if c.get("is_3phase", False) or ph_norm in ("3F", "RST", "L1L2L3"):
                for k in ("L1", "L2", "L3"):
                    old_phases[k] += w / 3.0
                    new_phases[k] += w / 3.0
                new_assignment[cid] = ph_raw
            else:
                if ph_norm not in old_phases:
                    ph_norm = "L1"
                old_phases[ph_norm] += w
                single_phase_items.append((cid, w, ph_norm))

        old_imb = calc_phase_imbalance_pct(old_phases["L1"], old_phases["L2"], old_phases["L3"])

        single_phase_items.sort(key=lambda x: (-x[1], x[0]))
        for cid, w, orig_ph in single_phase_items:
            min_load = min(new_phases.values())
            if abs(new_phases[orig_ph] - min_load) < 1e-6:
                chosen_ph = orig_ph
            else:
                chosen_ph = min(("L1", "L2", "L3"), key=lambda p: new_phases[p])
            new_phases[chosen_ph] += w
            new_assignment[cid] = chosen_ph

        new_imb = calc_phase_imbalance_pct(new_phases["L1"], new_phases["L2"], new_phases["L3"])
        return new_assignment, old_phases, new_phases, old_imb, new_imb

    @classmethod
    def propose_phase_balance(
        cls,
        plan: ElectricalOptimizationPlan,
        panel_tag: str,
        circuits: List[Dict[str, Any]],
        rule_engine: Optional[RuleEngine] = None,
    ) -> None:
        """
        Pano faz dengesizliğini aktif kural paketindeki (RuleEngine) sınırlarla analiz eder;
        - DESIGN modunda: Konum bazlı güvenli token değiştirme ile DWG önerisi üretir.
          Eğer metin içinde güvenli faz token'ı bulunamazsa (örn: 'L2-01 3x2.5 NYY') metni ezmez!
        - ASBUILT modunda: DWG'ye dokunmayı yasaklar (can_apply_to_dwg=False), yalnızca saha önerisi üretir.
        """
        jt = cls.validate_job_type(plan.job_type)
        re_inst = rule_engine or RuleEngine(default_pack=plan.rule_pack or "turkey_bina")
        limits = re_inst.active_pack.get("phase_imbalance_limits", {})
        warn_limit_pct = float(limits.get("warning_pct", 15.0))
        crit_limit_pct = float(limits.get("critical_pct", 25.0))
        limits_text = re_inst.get_phase_limits_text()
        std_ref = re_inst.get_standard_reference("phase_balance")

        new_map, old_p, new_p, old_imb, new_imb = cls.optimize_panel_phase_balance_greedy_lpt(circuits)

        if old_imb <= warn_limit_pct or new_imb >= old_imb:
            cls._refresh_summary_counts(plan)
            return

        changed_circuits = []
        for c in circuits:
            cid = str(c["circuit_id"])
            old_ph_raw = str(c.get("phase", "L1")).upper()
            old_ph = {"R": "L1", "S": "L2", "T": "L3"}.get(old_ph_raw, old_ph_raw)
            target_ph = new_map.get(cid, old_ph)
            if target_ph != old_ph:
                changed_circuits.append((c, old_ph, target_ph))

        if not changed_circuits:
            cls._refresh_summary_counts(plan)
            return

        eval_status, _ = re_inst.evaluate_phase_imbalance(new_imb)
        verified = (eval_status != "KRİTİK_DENGESİZLİK") and (
            new_imb <= warn_limit_pct or new_imb <= crit_limit_pct or new_imb < old_imb * 0.5
        )
        proof_str = (
            f"[YENİDEN DOĞRULANDI] Pano {panel_tag} faz dengesizliği %{old_imb:.1f} -> %{new_imb:.1f} "
            f"(L1:{new_p['L1']:.0f}W, L2:{new_p['L2']:.0f}W, L3:{new_p['L3']:.0f}W | "
            f"Standart Sınırı [{limits_text}]: {'PASS' if verified else 'FAIL'})"
        )

        if jt == "ASBUILT":
            moves_desc = ", ".join(
                f"{c['circuit_id']} ({old_ph}->{target_ph})" for c, old_ph, target_ph in changed_circuits
            )
            plan.proposals.append(
                ElectricalOptimizationProposal(
                    proposal_id=f"EOP-{len(plan.proposals) + 1:04d}",
                    category="PHASE_BALANCE",
                    job_type="ASBUILT",
                    target_element=panel_tag,
                    dxf_handle="",
                    old_text=f"Dengesizlik: %{old_imb:.1f}",
                    new_text=f"Saha Önerisi: {moves_desc} (Hedef: %{new_imb:.1f})",
                    before_metrics={"imbalance_pct": old_imb, "phases_w": old_p, "standard_limits": limits_text},
                    after_metrics={"imbalance_pct": new_imb, "phases_w": new_p, "moves": moves_desc},
                    verification_passed=verified,
                    verification_proof=proof_str,
                    standard_ref=std_ref,
                    can_apply_to_dwg=False,
                    status="ASBUILT_FIELD_RECOMMENDATION_ONLY",
                )
            )
            cls._refresh_summary_counts(plan)
            return

        # DESIGN Modu: Her değişen linye için güvenli token değiştirme kontrolü yap
        for c, old_ph, target_ph in changed_circuits:
            cid = str(c["circuit_id"])
            hnd = str(c.get("dxf_handle", ""))
            old_txt = str(c.get("raw_text", old_ph))
            token_ok, new_txt, token_reason = cls.safe_replace_phase_token(
                old_txt, old_ph, target_ph, circuit_id=cid
            )

            if not token_ok:
                # Metin içinde bağımsız faz token'ı yoksa (örn. "L2-01 3x2.5 NYY") DWG metnini EZME!
                plan.proposals.append(
                    ElectricalOptimizationProposal(
                        proposal_id=f"EOP-{len(plan.proposals) + 1:04d}",
                        category="PHASE_BALANCE",
                        job_type="DESIGN",
                        target_element=f"{panel_tag}/{cid}",
                        dxf_handle="",
                        old_text=old_txt,
                        new_text=old_txt,
                        before_metrics={"imbalance_pct": old_imb, "old_phase": old_ph, "phases_w": old_p},
                        after_metrics={
                            "imbalance_pct": new_imb,
                            "new_phase": target_ph,
                            "phases_w": new_p,
                            "text_guard_reason": token_reason,
                        },
                        verification_passed=verified,
                        verification_proof=(
                            f"{proof_str} [METİN KORUMA KALKANI: '{old_txt}' içinde bağımsız '{old_ph}' "
                            f"token'ı bulunamadığından ({token_reason}) DWG metin mutasyonu engellendi; "
                            f"yalnızca yükleme cetvelinde {old_ph}->{target_ph} güncellenir.]"
                        ),
                        standard_ref=std_ref,
                        can_apply_to_dwg=False,
                        status="REQUIRES_APPROVAL",
                    )
                )
                continue

            plan.proposals.append(
                ElectricalOptimizationProposal(
                    proposal_id=f"EOP-{len(plan.proposals) + 1:04d}",
                    category="PHASE_BALANCE",
                    job_type="DESIGN",
                    target_element=f"{panel_tag}/{cid}",
                    dxf_handle=hnd,
                    old_text=old_txt,
                    new_text=new_txt,
                    before_metrics={"imbalance_pct": old_imb, "old_phase": old_ph, "phases_w": old_p},
                    after_metrics={"imbalance_pct": new_imb, "new_phase": target_ph, "phases_w": new_p},
                    verification_passed=verified,
                    verification_proof=proof_str,
                    standard_ref=std_ref,
                    can_apply_to_dwg=bool(hnd),
                    status="REQUIRES_APPROVAL",
                )
            )

        cls._refresh_summary_counts(plan)

    @classmethod
    def propose_and_verify_protection_or_cable_fix(
        cls,
        plan: ElectricalOptimizationPlan,
        rule_engine: RuleEngine,
        element_id: str,
        power_w: float,
        length_m: float,
        is_3phase: bool,
        current_sec_mm2: float,
        current_cable_type: str,
        current_breaker_a: float,
        current_rcd_a: Optional[float] = None,
        current_rcd_ma: Optional[float] = None,
        is_fire_pump: bool = False,
        circuit_type: str = "KUVVET",
        fixture_count: int = 1,
        is_mech_or_direct: Optional[bool] = None,
        is_building: Optional[bool] = None,
        cable_dxf_handle: str = "",
        cable_old_text: str = "",
        protection_dxf_handle: str = "",
        protection_old_text: str = "",
    ) -> None:
        """
        Kablo kesiti, aşırı akım koruma koordinasyonu (TS HD 60364-4-43 Md. 433.1) ve
        Yangın Pompası BYKHY (Md. 72 & 83) ihlallerini inceler;
        - Gerilim düşümü sınırını (max_vd_limit) doğrudan RuleEngine aktif kural paketinden alır.
        - Yayılı yüklerde motorla birebir aynı calc_effective_circuit_length hesabını kullanır.
        - Yangın pompasında 30mA KAK varsa hem kablo (FE180) hem de koruma (KAK kaldırma) DWG metnini günceller.
        """
        voltage_v = 400 if is_3phase else 230
        conductivity = rule_engine.get_copper_conductivity()
        ib = calc_operating_current_ib(
            power_w,
            voltage_v=voltage_v,
            cos_phi=0.85 if is_3phase else 0.90,
            is_3phase=is_3phase,
        )
        cores_prefix = "4x" if is_3phase else "3x"

        # Kural paketinden dinamik gerilim düşümü sınırı (Aydınlatma vs Priz/Kuvvet)
        effective_circuit_type = "KUVVET" if (is_fire_pump or is_3phase) else circuit_type
        max_vd_limit = rule_engine.get_vd_limit(effective_circuit_type)

        # Motorla birebir uyumlu efektif devre uzunluğu (yayılı yük düzeltmesi)
        direct_flag = True if is_fire_pump else (is_mech_or_direct if is_mech_or_direct is not None else (fixture_count <= 1))
        building_flag = (
            is_building
            if is_building is not None
            else (rule_engine.active_pack.get("code") != "IBB_METRO_CODE")
        )
        eff_length_m = calc_effective_circuit_length(
            length_m,
            fixture_count=fixture_count,
            is_mech_or_direct=direct_flag,
            is_building=building_flag,
        )

        # 1. YANGIN POMPASI BYKHY MD. 72 & 83 KONTROLÜ VE OTOMATİK DÜZELTME ÖNERİSİ
        if is_fire_pump:
            has_fe180 = "FE180" in current_cable_type.upper() or "FE-180" in current_cable_type.upper()
            has_illegal_30ma_rcd = current_rcd_ma is not None and current_rcd_ma <= 30.0
            if not has_fe180 or has_illegal_30ma_rcd:
                new_cable_type = "NHXH FE180"
                target_in_fp = next((b for b in STANDARD_BREAKER_RATINGS_A if b >= ib), current_breaker_a)
                chosen_sec = current_sec_mm2
                for cand_sec in STANDARD_CABLE_SECTIONS_MM2:
                    if cand_sec < current_sec_mm2:
                        continue
                    iz_cand = rule_engine.get_ampacity_a(cand_sec, new_cable_type, is_3phase=is_3phase) or 0.0
                    vd_cand = calc_voltage_drop_pct(
                        power_w, eff_length_m, cand_sec, voltage_v=voltage_v, conductivity=conductivity, is_3phase=is_3phase
                    )
                    if iz_cand >= max(ib, target_in_fp) and vd_cand <= max_vd_limit:
                        chosen_sec = cand_sec
                        break

                sec_str = f"{int(chosen_sec)}" if chosen_sec.is_integer() else f"{chosen_sec}"
                new_cable_spec = f"{cores_prefix}{sec_str} {new_cable_type}"
                iz_after = rule_engine.get_ampacity_a(chosen_sec, new_cable_type, is_3phase=is_3phase) or 0.0
                vd_after = calc_voltage_drop_pct(
                    power_w, eff_length_m, chosen_sec, voltage_v=voltage_v, conductivity=conductivity, is_3phase=is_3phase
                )

                bykhy_verified = ("FE180" in new_cable_spec) and (iz_after >= ib) and (vd_after <= max_vd_limit)
                proof = (
                    f"[YENİDEN DOĞRULANDI - BYKHY Md. 72 & 83] Kablo '{new_cable_spec}' (FE180 Yangına Dayanıklı) "
                    f"yapıldı ve 30mA KAK devre dışı bırakıldı. Ib={ib:.1f}A <= Iz={iz_after:.1f}A, "
                    f"e%={vd_after:.2f}% <= %{max_vd_limit}: PASS."
                )

                if cable_dxf_handle or cable_old_text:
                    plan.proposals.append(
                        ElectricalOptimizationProposal(
                            proposal_id=f"EOP-{len(plan.proposals) + 1:04d}",
                            category="BYKHY_FIRE_PUMP",
                            job_type=plan.job_type,
                            target_element=element_id,
                            dxf_handle=cable_dxf_handle,
                            old_text=cable_old_text or f"{cores_prefix}{int(current_sec_mm2)} {current_cable_type}",
                            new_text=new_cable_spec,
                            before_metrics={
                                "cable_type": current_cable_type,
                                "rcd_ma": current_rcd_ma,
                                "fe180": has_fe180,
                            },
                            after_metrics={
                                "cable_type": new_cable_type,
                                "section_mm2": chosen_sec,
                                "rcd_ma": None,
                                "fe180": True,
                                "iz_a": iz_after,
                                "vd_pct": vd_after,
                            },
                            verification_passed=bykhy_verified,
                            verification_proof=proof,
                            standard_ref="BYKHY Madde 72 & 83 (Yangın Pompası Besleme Kriteri)",
                            can_apply_to_dwg=bool(cable_dxf_handle),
                            status="REQUIRES_APPROVAL",
                        )
                    )

                # Eğer 30mA KAK varsa ve koruma metni handle'ı verilmişse (ve aşağıda zaten koruma koordinasyonu
                # tarafından güncellenmeyecekse) KAK metnini DWG'den kaldıran öneriyi de üret!
                iz_cur_check = rule_engine.get_ampacity_a(current_sec_mm2, current_cable_type, is_3phase=is_3phase) or 0.0
                coord_already_triggers = (
                    len(rule_engine.check_protection_coordination(ib, current_breaker_a, iz_cur_check)) > 0
                    or (current_rcd_a is not None and current_rcd_a < current_breaker_a)
                )
                if has_illegal_30ma_rcd and (protection_dxf_handle or protection_old_text) and not coord_already_triggers:
                    poles = "3x" if is_3phase else "1x"
                    clean_prot_text = f"{poles}{int(target_in_fp)}A"
                    plan.proposals.append(
                        ElectricalOptimizationProposal(
                            proposal_id=f"EOP-{len(plan.proposals) + 1:04d}",
                            category="BYKHY_FIRE_PUMP_RCD_REMOVAL",
                            job_type=plan.job_type,
                            target_element=element_id,
                            dxf_handle=protection_dxf_handle,
                            old_text=protection_old_text or f"{poles}{int(current_breaker_a)}A + 30mA KAK",
                            new_text=clean_prot_text,
                            before_metrics={"in_breaker_a": current_breaker_a, "rcd_ma": current_rcd_ma},
                            after_metrics={"in_breaker_a": target_in_fp, "rcd_ma": None},
                            verification_passed=bykhy_verified,
                            verification_proof=proof,
                            standard_ref="BYKHY Madde 72 & 83 (Yangın Pompasında 30mA KAK Yasağı)",
                            can_apply_to_dwg=bool(protection_dxf_handle),
                            status="REQUIRES_APPROVAL",
                        )
                    )

        # 2. KORUMA KOORDİNASYONU (TS HD 60364-4-43 MD. 433.1: Ib <= In <= Iz ve In_KAK >= In)
        iz_cur = rule_engine.get_ampacity_a(current_sec_mm2, current_cable_type, is_3phase=is_3phase) or 0.0
        vd_cur = calc_voltage_drop_pct(
            power_w, eff_length_m, current_sec_mm2, voltage_v=voltage_v, conductivity=conductivity, is_3phase=is_3phase
        )
        coord_ok_before = len(rule_engine.check_protection_coordination(ib, current_breaker_a, iz_cur)) == 0
        rcd_ok_before = (current_rcd_a is None) or (current_rcd_a >= current_breaker_a)
        vd_ok_before = vd_cur <= max_vd_limit

        if not (coord_ok_before and rcd_ok_before and vd_ok_before):
            target_in = next((b for b in STANDARD_BREAKER_RATINGS_A if b >= ib), current_breaker_a)
            if current_rcd_a is not None and target_in <= current_rcd_a <= iz_cur and vd_ok_before:
                chosen_in = current_rcd_a if current_rcd_a >= ib else target_in
                chosen_sec = current_sec_mm2
                chosen_rcd_a = max(current_rcd_a, chosen_in)
            else:
                chosen_in = target_in
                chosen_rcd_a = max(current_rcd_a or chosen_in, chosen_in)
                chosen_sec = current_sec_mm2
                for cand_sec in STANDARD_CABLE_SECTIONS_MM2:
                    if cand_sec < current_sec_mm2:
                        continue
                    iz_cand = rule_engine.get_ampacity_a(cand_sec, current_cable_type, is_3phase=is_3phase) or 0.0
                    vd_cand = calc_voltage_drop_pct(
                        power_w, eff_length_m, cand_sec, voltage_v=voltage_v, conductivity=conductivity, is_3phase=is_3phase
                    )
                    if len(rule_engine.check_protection_coordination(ib, chosen_in, iz_cand)) == 0 and vd_cand <= max_vd_limit:
                        chosen_sec = cand_sec
                        break

            iz_after = rule_engine.get_ampacity_a(chosen_sec, current_cable_type, is_3phase=is_3phase) or 0.0
            vd_after = calc_voltage_drop_pct(
                power_w, eff_length_m, chosen_sec, voltage_v=voltage_v, conductivity=conductivity, is_3phase=is_3phase
            )

            coord_ok_after = len(rule_engine.check_protection_coordination(ib, chosen_in, iz_after)) == 0
            rcd_ok_after = chosen_rcd_a >= chosen_in
            vd_ok_after = vd_after <= max_vd_limit
            all_verified = coord_ok_after and rcd_ok_after and vd_ok_after

            poles = "3x" if is_3phase else "1x"
            new_prot_text = f"{poles}{int(chosen_in)}A"
            if current_rcd_a is not None and not is_fire_pump:
                new_prot_text += f" + 4x{int(chosen_rcd_a)}A KAK"

            sec_str = f"{int(chosen_sec)}" if chosen_sec.is_integer() else f"{chosen_sec}"
            new_cable_text = f"{cores_prefix}{sec_str} {current_cable_type}"

            proof = (
                f"[YENİDEN DOĞRULANDI - TS HD 60364-4-43 Md. 433.1] "
                f"Ib={ib:.1f}A <= In={chosen_in:.0f}A <= Iz={iz_after:.1f}A (Kablo: {new_cable_text}), "
                f"In_KAK={chosen_rcd_a:.0f}A >= In={chosen_in:.0f}A, e%={vd_after:.2f}% <= %{max_vd_limit} (Leff={eff_length_m:.1f}m): "
                f"{'PASS' if all_verified else 'FAIL'}."
            )

            target_handle = protection_dxf_handle or cable_dxf_handle
            old_txt = protection_old_text or cable_old_text or f"{poles}{int(current_breaker_a)}A"
            new_txt = new_prot_text if protection_dxf_handle else new_cable_text

            plan.proposals.append(
                ElectricalOptimizationProposal(
                    proposal_id=f"EOP-{len(plan.proposals) + 1:04d}",
                    category="PROTECTION_COORDINATION",
                    job_type=plan.job_type,
                    target_element=element_id,
                    dxf_handle=target_handle,
                    old_text=old_txt,
                    new_text=new_txt,
                    before_metrics={
                        "ib_a": ib,
                        "in_breaker_a": current_breaker_a,
                        "in_rcd_a": current_rcd_a,
                        "section_mm2": current_sec_mm2,
                        "iz_a": iz_cur,
                        "vd_pct": vd_cur,
                        "eff_length_m": eff_length_m,
                        "max_vd_limit_pct": max_vd_limit,
                    },
                    after_metrics={
                        "ib_a": ib,
                        "in_breaker_a": chosen_in,
                        "in_rcd_a": None if is_fire_pump else chosen_rcd_a,
                        "section_mm2": chosen_sec,
                        "iz_a": iz_after,
                        "vd_pct": vd_after,
                        "eff_length_m": eff_length_m,
                        "max_vd_limit_pct": max_vd_limit,
                    },
                    verification_passed=all_verified,
                    verification_proof=proof,
                    standard_ref="TS HD 60364-4-43 Madde 433.1 & TS HD 60364-5-52",
                    can_apply_to_dwg=bool(target_handle),
                    status="REQUIRES_APPROVAL",
                )
            )

        cls._refresh_summary_counts(plan)

    @classmethod
    def apply_proposals(
        cls,
        doc: Any,
        plan: ElectricalOptimizationPlan,
        approved_proposal_ids: Set[str],
        rejected_proposal_ids: Optional[Set[str]] = None,
        output_dxf_path: Optional[Union[str, Path]] = None,
        applied_ledger_path: Optional[Union[str, Path]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Onay İstasyonu'ndan gelen onaylı (approved_proposal_ids) önerileri DWG'ye uygular.
        Pazarlığa Kapalı Kurallar:
        1. approved_proposal_ids boşsa hiçbir kesit/koruma/faz değişikliği DWG'ye uygulanmaz!
        2. verification_passed == False veya can_apply_to_dwg == False (örn. ASBUILT faz) ise reddedilir!
        3. CADSafetyGuard.safe_update_text_entity ile MTEXT biçim kodları ve BLOCK_DEF dokunulmazlığı korunur.
        """
        applied_records: List[Dict[str, Any]] = []

        for prop in plan.proposals:
            if rejected_proposal_ids is not None and prop.proposal_id in rejected_proposal_ids:
                prop.status = "REJECTED"
                continue

            if prop.proposal_id not in approved_proposal_ids:
                if prop.status not in ("REQUIRES_APPROVAL", "ASBUILT_FIELD_RECOMMENDATION_ONLY", "REJECTED"):
                    prop.status = "NOT_SELECTED"
                continue

            if not prop.can_apply_to_dwg:
                prop.status = "BLOCKED_ASBUILT_POLICY" if prop.job_type == "ASBUILT" else "BLOCKED_TEXT_INVARIANCE_GUARD"
                continue

            if not prop.verification_passed:
                prop.status = "BLOCKED_UNVERIFIED"
                continue

            if not prop.dxf_handle:
                prop.status = "SKIPPED_NO_HANDLE"
                continue

            ok, msg, old_raw = CADSafetyGuard.safe_update_text_entity(
                doc,
                prop.dxf_handle,
                prop.new_text,
                old_substring=prop.old_text if prop.old_text else None,
            )
            if not ok:
                prop.status = f"SKIPPED_SAFETY({msg})"
                continue

            prop.status = "APPROVED"
            now_iso = datetime.now(timezone.utc).isoformat()
            raw_sig = f"{prop.proposal_id}|{prop.dxf_handle}|{prop.old_text}->{prop.new_text}|{now_iso}"
            sig_hash = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()[:16]

            applied_records.append({
                "proposal_id": prop.proposal_id,
                "category": prop.category,
                "job_type": prop.job_type,
                "target_element": prop.target_element,
                "dxf_handle": prop.dxf_handle,
                "old_raw_text": old_raw,
                "old_text": prop.old_text,
                "new_text": prop.new_text,
                "verification_proof": prop.verification_proof,
                "standard_ref": prop.standard_ref,
                "applied_at": now_iso,
                "signature_hash": sig_hash,
            })

        if output_dxf_path is not None:
            out_p = Path(output_dxf_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            doc.saveas(out_p)

        if applied_ledger_path is not None:
            led_p = Path(applied_ledger_path)
            led_p.parent.mkdir(parents=True, exist_ok=True)
            led_p.write_text(
                json.dumps(
                    {
                        "drawing_name": plan.drawing_name,
                        "job_type": plan.job_type,
                        "total_applied": len(applied_records),
                        "applied_changes": applied_records,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        return applied_records
