# -*- coding: utf-8 -*-
"""
Modül 1 — LayerAndBlockDoctor (Akıllı Katman ve Blok Rehabilitasyon Motoru)
===========================================================================
Kanıtlanmış mimari elemanları (IGNORED_ARCHITECTURAL) tek bir 'A-MIMARI-ALTYAPI'
katmanında (Color 8 Gri, 0.09mm CTB/Lineweight, Kilitli) toplar; elektrik
sembollerini ve güzergahlarını standart disiplin katmanlarına taşır.

Pazarlığa Kapalı 3 Güvenlik Kuralı:
1. XREF Dokunulmazlığı: XREF blok tanımları ve XREF INSERT referansları atlanır.
2. Block Def vs INSERT Ayrımı: Katman değişikliği yalnızca INSERT referansına uygulanır;
   blok tanımındaki (doc.blocks[name]) iç geometrilere asla dokunulmaz.
3. CTB / Baskı Stili Koruması: Katman şablonu renk (ACI), çizgi kalınlığı (lineweight)
   ve plotstyle bilgilerini taşır; taşınan varlıkların renk/kalınlık özellikleri
   BYLAYER (color=256, lineweight=-1) yapılarak CTB uyumu garanti altına alınır.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import ezdxf

from ..cad.cad_safety import (
    CADSafetyGuard,
    LayerStandardSpec,
    MutationSafetyVerdict,
    UnitScaleResolver,
)
from ..model.entities import DrawingSceneGraph, LinearRoute, PlacedSymbol, TextToken


# Standart Katman Şablonu (CTB / Lineweight / Kilit Korumalı)
STANDARD_LAYER_SPECS: Dict[str, LayerStandardSpec] = {
    "A-MIMARI-ALTYAPI": LayerStandardSpec(
        name="A-MIMARI-ALTYAPI",
        color=8,                        # Gri (ACI 8)
        lineweight=9,                   # 0.09 mm (Monochrome CTB'de dahi çok ince arka plan çıkar)
        linetype="CONTINUOUS",
        locked=True,                    # Yanlışlıkla mimari silinmesini/taşınmasını önler
        plot=True,
        plotstyle_name="Architectural_Screened_0.09mm",
        description="Kanıtlanmış mimari tefriş, duvar ve altyapı katmanı (Kilitli)",
    ),
    "E-AYDINLATMA-ARMATUR": LayerStandardSpec(
        name="E-AYDINLATMA-ARMATUR",
        color=2,                        # Sarı
        lineweight=25,                  # 0.25 mm
        linetype="CONTINUOUS",
        locked=False,
        plot=True,
        plotstyle_name="Electrical_Symbol_0.25mm",
        description="Aydınlatma armatürleri ve acil yönlendirme sembolleri",
    ),
    "E-PRIZ-SORTI": LayerStandardSpec(
        name="E-PRIZ-SORTI",
        color=30,                       # Turuncu
        lineweight=25,                  # 0.25 mm
        linetype="CONTINUOUS",
        locked=False,
        plot=True,
        plotstyle_name="Electrical_Symbol_0.25mm",
        description="Şebeke, UPS ve endüstriyel priz sortileri",
    ),
    "E-ANAHTAR": LayerStandardSpec(
        name="E-ANAHTAR",
        color=3,                        # Yeşil
        lineweight=20,                  # 0.20 mm
        linetype="CONTINUOUS",
        locked=False,
        plot=True,
        plotstyle_name="Electrical_Symbol_0.20mm",
        description="Aydınlatma anahtarları, sensörler ve butonlar",
    ),
    "E-PANO": LayerStandardSpec(
        name="E-PANO",
        color=5,                        # Mavi
        lineweight=35,                  # 0.35 mm
        linetype="CONTINUOUS",
        locked=False,
        plot=True,
        plotstyle_name="Electrical_Panel_0.35mm",
        description="Ana ve tali dağıtım panoları, MCC ve UPS kabinleri",
    ),
    "E-SALTER-KORUMA": LayerStandardSpec(
        name="E-SALTER-KORUMA",
        color=6,                        # Magenta
        lineweight=25,                  # 0.25 mm
        linetype="CONTINUOUS",
        locked=False,
        plot=True,
        plotstyle_name="Electrical_Symbol_0.25mm",
        description="Sigorta, şalter, KAK ve koruma ekipmanları",
    ),
    "E-YANGIN-ALGILAMA": LayerStandardSpec(
        name="E-YANGIN-ALGILAMA",
        color=1,                        # Kırmızı
        lineweight=25,                  # 0.25 mm
        linetype="CONTINUOUS",
        locked=False,
        plot=True,
        plotstyle_name="Fire_Alarm_0.25mm",
        description="Yangın algılama dedektörleri, butonları ve sirenleri",
    ),
    "E-ZAYIF-AKIM-DATA": LayerStandardSpec(
        name="E-ZAYIF-AKIM-DATA",
        color=4,                        # Cyan
        lineweight=20,                  # 0.20 mm
        linetype="CONTINUOUS",
        locked=False,
        plot=True,
        plotstyle_name="Weak_Current_0.20mm",
        description="Data, telefon, CCTV, anons ve kartlı geçiş ekipmanları",
    ),
    "E-BUAT": LayerStandardSpec(
        name="E-BUAT",
        color=2,                        # Sarı
        lineweight=18,                  # 0.18 mm
        linetype="CONTINUOUS",
        locked=False,
        plot=True,
        plotstyle_name="Electrical_Symbol_0.18mm",
        description="Buat ve bağlantı kutuları",
    ),
    "E-TOPRAKLAMA": LayerStandardSpec(
        name="E-TOPRAKLAMA",
        color=3,                        # Yeşil
        lineweight=30,                  # 0.30 mm
        linetype="DASHED",
        locked=False,
        plot=True,
        plotstyle_name="Grounding_0.30mm",
        description="Eşpotansiyel topraklama baraları, klemensleri ve iletkenleri",
    ),
    "E-EKIPMAN": LayerStandardSpec(
        name="E-EKIPMAN",
        color=40,                       # Altın sarısı
        lineweight=25,                  # 0.25 mm
        linetype="CONTINUOUS",
        locked=False,
        plot=True,
        plotstyle_name="Electrical_Symbol_0.25mm",
        description="Mekanik/elektrik motor ve genel elektrik ekipmanları",
    ),
    "E-KABLO-HAT": LayerStandardSpec(
        name="E-KABLO-HAT",
        color=1,                        # Kırmızı
        lineweight=25,                  # 0.25 mm
        linetype="CONTINUOUS",
        locked=False,
        plot=True,
        plotstyle_name="Electrical_Cable_0.25mm",
        description="Besleme ve linye kablo güzergahları",
    ),
    "E-KABLO-TAVA": LayerStandardSpec(
        name="E-KABLO-TAVA",
        color=140,                      # Açık Mavi
        lineweight=35,                  # 0.35 mm
        linetype="CONTINUOUS",
        locked=False,
        plot=True,
        plotstyle_name="Cable_Tray_0.35mm",
        description="Kuvvetli ve zayıf akım kablo tavaları / merdivenleri",
    ),
}

CLASSIFICATION_TO_STD_LAYER: Dict[str, str] = {
    "IGNORED_ARCHITECTURAL": "A-MIMARI-ALTYAPI",
    "LUMINAIRE": "E-AYDINLATMA-ARMATUR",
    "SOCKET": "E-PRIZ-SORTI",
    "SWITCH": "E-ANAHTAR",
    "PANEL": "E-PANO",
    "SWITCHGEAR": "E-SALTER-KORUMA",
    "FIRE_DEVICE": "E-YANGIN-ALGILAMA",
    "DATA_DEVICE": "E-ZAYIF-AKIM-DATA",
    "JUNCTION_BOX": "E-BUAT",
    "GROUNDING_CLAMP": "E-TOPRAKLAMA",
    "EQUIPMENT": "E-EKIPMAN",
}

PROVEN_ARCH_RAW_LAYERS = (
    "DUVAR", "SIVA", "DSIVA", "DSİVA", "TEFRS", "TEFRIS", "TEFRİŞ",
    "MOBILYA", "MOBİLYA", "KAPI", "KAPİ", "PENCERE", "DKAPIPENCERE",
    "MERDIVEN", "MERDİVEN", "TARAMA", "HATCH", "A-WALL", "A-DOOR", "A-GLAZ", "A-FURN",
)

# Elektrik veya Zayıf Akım disiplin öneki / anahtar kelimesi taşıyan katmanlar ASLA mimariye atılamaz!
ELECTRIC_PROTECTED_LAYER_PREFIXES = (
    "E-", "E_", "ELK", "ELEK", "ELC", "POW", "LGT", "LIGHT", "AYD", "PRIZ", "PRİZ",
    "PANO", "KABLO", "TAVA", "TRAY", "TOPRAK", "GRND", "DATA", "CCTV", "YANGIN",
    "FIRE", "ANONS", "PAVA", "SCADA", "ACS", "GUVENLIK", "GÜVENLİK", "KARTLI",
    "TL-", "TL_", "AX-", "AX_", "PS-", "PS_", "GN-", "GN_",
)


def _is_protected_electrical_layer(layer_name: str) -> bool:
    """Katman adında elektrik/zayıf akım öneki veya anahtar kelimesi varsa True döner."""
    lay_up = (layer_name or "").upper().strip()
    if not lay_up:
        return False
    if lay_up.startswith(("E-", "E_", "TL-", "AX-", "PS-", "GN-", "00-", "01-", "02-", "03-")):
        return True
    return any(tok in lay_up for tok in ELECTRIC_PROTECTED_LAYER_PREFIXES)


@dataclass
class LayerChangeProposal:
    """Tek bir DXF varlığı için katman ve stil taşıma önerisi."""
    proposal_id: str
    dxf_handle: str
    dxftype: str
    entity_label: str
    old_layer: str
    new_layer: str
    old_color: int
    new_color: int                      # 256 = BYLAYER
    target_layer_color: int
    target_lineweight: int
    target_plotstyle: str
    target_locked: bool
    classification: str
    triage_status: str
    confidence_score: float
    reason: str
    auto_approvable: bool
    status: str = "PROPOSED"            # PROPOSED, REQUIRES_APPROVAL, APPROVED, REJECTED


@dataclass
class SkippedEntityRecord:
    """Güvenlik kalkanı (XREF veya Blok Tanımı) nedeniyle dokunulmayan varlık kaydı."""
    dxf_handle: str
    dxftype: str
    entity_label: str
    reason: str


@dataclass
class DoctorChangePlan:
    """LayerAndBlockDoctor tarafından üretilen change_plan.json veri modeli."""
    drawing_name: str
    unit_to_mm: float
    unit_source: str
    created_at: str
    proposals: List[LayerChangeProposal] = field(default_factory=list)
    skipped_entities: List[SkippedEntityRecord] = field(default_factory=list)
    safety_skipped_counts: Dict[str, int] = field(default_factory=dict)
    summary_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save_json(self, path: Union[str, Path]) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p


@dataclass
class AppliedChangeRecord:
    """Onay İstasyonu sonrasında applied_changes.json mesuliyet defterine yazılan imzalı kayıt."""
    proposal_id: str
    dxf_handle: str
    dxftype: str
    entity_label: str
    old_layer: str
    new_layer: str
    old_color: int
    new_color_bylayer: int
    layer_aci_color: int
    layer_lineweight: int
    plotstyle_name: str
    layer_locked: bool
    reason: str
    applied_at: str
    signature_hash: str


class LayerAndBlockDoctor:
    """
    Modül 1: Sınıflandırılmış ve triyajlanmış CAD varlıklarını güvenli biçimde
    standart katmanlara taşıyan, XREF ve blok tanımlarını koruyan rehabilitasyon motoru.
    """

    @staticmethod
    def _match_symbol_handle_in_modelspace(doc: Any, sym: PlacedSymbol) -> str:
        """Eğer PlacedSymbol üzerinde dxf_handle yoksa ModelSpace içinde koordinat ve blok adıyla bulur."""
        if sym.dxf_handle:
            return sym.dxf_handle
        try:
            for ent in doc.modelspace():
                if ent.dxftype() == "INSERT":
                    bname = getattr(ent.dxf, "name", "")
                    if bname == sym.block_name or bname == sym.clean_family_name:
                        ins = ent.dxf.insert
                        if math.hypot(ins.x - sym.pos[0], ins.y - sym.pos[1]) <= 1.0:
                            return getattr(ent.dxf, "handle", "")
        except Exception:
            pass
        return ""

    @classmethod
    def analyze_and_propose(
        cls,
        doc: Any,
        symbols: Optional[List[PlacedSymbol]] = None,
        routes: Optional[List[LinearRoute]] = None,
        drawing_name: str = "drawing.dxf",
        include_raw_arch_layers: bool = True,
    ) -> DoctorChangePlan:
        """
        Çizimi ve sembol/güzergah listesini inceleyerek katman taşıma öneri planı (DoctorChangePlan) üretir.
        XREF içeriklerini ve blok tanımlarını kesinlikle reddeder ve raporlar.
        """
        symbols = symbols or []
        routes = routes or []
        unit_mm, unit_src = UnitScaleResolver.resolve_unit_to_mm(doc)
        block_counts = CADSafetyGuard.count_block_instances(doc)

        plan = DoctorChangePlan(
            drawing_name=drawing_name,
            unit_to_mm=unit_mm,
            unit_source=unit_src,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        processed_handles: Set[str] = set()
        prop_seq = 1

        def _record_skip(handle: str, dxftype: str, entity_label: str, reason: str):
            bucket = reason.split("(", 1)[0]
            plan.safety_skipped_counts[bucket] = plan.safety_skipped_counts.get(bucket, 0) + 1
            plan.skipped_entities.append(
                SkippedEntityRecord(dxf_handle=handle, dxftype=dxftype, entity_label=entity_label, reason=reason)
            )

        # 0. XREF Blok Tanımlarını Tara ve Korumaya Alındığını Kaydet
        for blk in doc.blocks:
            if blk.name.startswith("*Model_Space") or blk.name.startswith("*Paper_Space"):
                continue
            if CADSafetyGuard.is_xref_block_record(blk, blk.name):
                for x_ent in blk:
                    _record_skip(
                        handle=getattr(x_ent.dxf, "handle", ""),
                        dxftype=x_ent.dxftype(),
                        entity_label=f"{blk.name}::{x_ent.dxftype()}",
                        reason=f"XREF_INTERNAL_ENTITY_READONLY({blk.name})",
                    )

        # 1. Sınıflandırılmış & Triyajlanmış Sembolleri Değerlendir
        for sym in symbols:
            handle = cls._match_symbol_handle_in_modelspace(doc, sym)
            if not handle:
                continue
            if handle in processed_handles:
                continue

            verdict: MutationSafetyVerdict = CADSafetyGuard.check_entity_mutable(
                doc,
                handle,
                allow_single_instance_container=False,
                allow_xref_insert_ref=False,
                block_instance_counts=block_counts,
            )
            if not verdict.allowed:
                _record_skip(handle, verdict.dxftype or "INSERT", sym.block_name, verdict.reason)
                continue

            processed_handles.add(handle)

            # Belirsiz elektrik veya sınıflandırılamayan semboller -> Otomatik mimariye ATILMAZ, Onay İstasyonu'na düşer!
            if sym.triage_status in ("UNCERTAIN_ELECTRICAL", "UNCLASSIFIED"):
                target_layer = "E-EKIPMAN"
                spec = STANDARD_LAYER_SPECS[target_layer]
                plan.proposals.append(
                    LayerChangeProposal(
                        proposal_id=f"LDP-{prop_seq:04d}",
                        dxf_handle=handle,
                        dxftype=verdict.dxftype or "INSERT",
                        entity_label=sym.block_name,
                        old_layer=sym.layer,
                        new_layer=target_layer,
                        old_color=sym.color,
                        new_color=256,
                        target_layer_color=spec.color,
                        target_lineweight=spec.lineweight,
                        target_plotstyle=spec.plotstyle_name,
                        target_locked=spec.locked,
                        classification=sym.classification,
                        triage_status=sym.triage_status,
                        confidence_score=0.50,
                        reason=f"Şüpheli/sınıflandırılamayan blok ({sym.triage_status}); mühendis onayı olmadan mimariye taşınmaz.",
                        auto_approvable=False,
                        status="REQUIRES_APPROVAL",
                    )
                )
                prop_seq += 1
                continue

            target_layer = CLASSIFICATION_TO_STD_LAYER.get(sym.classification, "")
            if not target_layer:
                continue

            spec = STANDARD_LAYER_SPECS[target_layer]
            ent_obj = doc.entitydb.get(handle)
            cur_layer = getattr(ent_obj.dxf, "layer", sym.layer) if ent_obj else sym.layer
            cur_color = getattr(ent_obj.dxf, "color", sym.color) if ent_obj else sym.color

            if cur_layer == target_layer and cur_color == 256:
                continue

            reason_txt = (
                "Kanıtlanmış mimari sembol (IGNORED_ARCHITECTURAL) -> Kilitli ve gri A-MIMARI-ALTYAPI katmanına alındı."
                if sym.classification == "IGNORED_ARCHITECTURAL"
                else f"Tanınan elektrik sembolü ({sym.classification}) -> Standart '{target_layer}' katmanına taşındı."
            )

            plan.proposals.append(
                LayerChangeProposal(
                    proposal_id=f"LDP-{prop_seq:04d}",
                    dxf_handle=handle,
                    dxftype=verdict.dxftype or "INSERT",
                    entity_label=sym.block_name,
                    old_layer=cur_layer,
                    new_layer=target_layer,
                    old_color=cur_color,
                    new_color=256,
                    target_layer_color=spec.color,
                    target_lineweight=spec.lineweight,
                    target_plotstyle=spec.plotstyle_name,
                    target_locked=spec.locked,
                    classification=sym.classification,
                    triage_status=sym.triage_status,
                    confidence_score=sym.confidence_score if sym.classification != "IGNORED_ARCHITECTURAL" else 0.95,
                    reason=reason_txt,
                    auto_approvable=True,
                    status="PROPOSED",
                )
            )
            prop_seq += 1

        # 2. Fiziksel Kablo ve Tava Güzergahlarını Değerlendir
        for route in routes:
            target_layer = "E-KABLO-TAVA" if route.subsystem == "TRAY" else "E-KABLO-HAT"
            spec = STANDARD_LAYER_SPECS[target_layer]
            for hnd in route.entity_handles:
                if not hnd or hnd in processed_handles:
                    continue
                verdict = CADSafetyGuard.check_entity_mutable(
                    doc, hnd, allow_single_instance_container=False, block_instance_counts=block_counts
                )
                if not verdict.allowed:
                    _record_skip(hnd, verdict.dxftype, f"ROUTE_{route.subsystem}", verdict.reason)
                    continue
                processed_handles.add(hnd)
                ent_obj = doc.entitydb.get(hnd)
                cur_layer = getattr(ent_obj.dxf, "layer", route.layer)
                cur_color = getattr(ent_obj.dxf, "color", route.color)
                if cur_layer == target_layer and cur_color == 256:
                    continue
                plan.proposals.append(
                    LayerChangeProposal(
                        proposal_id=f"LDP-{prop_seq:04d}",
                        dxf_handle=hnd,
                        dxftype=verdict.dxftype,
                        entity_label=f"{route.subsystem}:{cur_layer}",
                        old_layer=cur_layer,
                        new_layer=target_layer,
                        old_color=cur_color,
                        new_color=256,
                        target_layer_color=spec.color,
                        target_lineweight=spec.lineweight,
                        target_plotstyle=spec.plotstyle_name,
                        target_locked=spec.locked,
                        classification=route.subsystem,
                        triage_status="VERIFIED_ROUTE",
                        confidence_score=0.95,
                        reason=f"Fiziksel {route.subsystem} güzergahı -> '{target_layer}' katmanına standartlaştırıldı.",
                        auto_approvable=True,
                        status="PROPOSED",
                    )
                )
                prop_seq += 1

        # 3. ModelSpace İçindeki Ham Mimari Katman Varlıklarını (DUVAR, MOBILYA vb.) ve XREF INSERT'lerini Kontrol Et
        if include_raw_arch_layers:
            arch_spec = STANDARD_LAYER_SPECS["A-MIMARI-ALTYAPI"]
            for ent in doc.modelspace():
                hnd = getattr(ent.dxf, "handle", "")
                if not hnd or hnd in processed_handles:
                    continue

                verdict = CADSafetyGuard.check_entity_mutable(
                    doc, ent, allow_single_instance_container=False, allow_xref_insert_ref=False, block_instance_counts=block_counts
                )
                if not verdict.allowed:
                    _record_skip(
                        hnd,
                        ent.dxftype(),
                        getattr(ent.dxf, "name", ent.dxftype()),
                        verdict.reason,
                    )
                    processed_handles.add(hnd)
                    continue

                lay_up = getattr(ent.dxf, "layer", "0").upper().strip()
                if lay_up == "A-MIMARI-ALTYAPI":
                    continue

                # Elektrik / Zayıf akım katmanıysa (örn. E-KAPI-GUVENLIK) substring tuzağına düşme, ASLA mimariye taşıma!
                if _is_protected_electrical_layer(lay_up):
                    continue

                if any(k in lay_up for k in PROVEN_ARCH_RAW_LAYERS):
                    processed_handles.add(hnd)
                    cur_layer = getattr(ent.dxf, "layer", "0")
                    cur_color = getattr(ent.dxf, "color", 256)
                    plan.proposals.append(
                        LayerChangeProposal(
                            proposal_id=f"LDP-{prop_seq:04d}",
                            dxf_handle=hnd,
                            dxftype=ent.dxftype(),
                            entity_label=getattr(ent.dxf, "name", ent.dxftype()),
                            old_layer=cur_layer,
                            new_layer="A-MIMARI-ALTYAPI",
                            old_color=cur_color,
                            new_color=256,
                            target_layer_color=arch_spec.color,
                            target_lineweight=arch_spec.lineweight,
                            target_plotstyle=arch_spec.plotstyle_name,
                            target_locked=arch_spec.locked,
                            classification="IGNORED_ARCHITECTURAL",
                            triage_status="RAW_ARCH_LAYER",
                            confidence_score=0.90,
                            reason=f"Mimari katmandaki ({cur_layer}) varlık -> 'A-MIMARI-ALTYAPI' katmanına alındı.",
                            auto_approvable=True,
                            status="PROPOSED",
                        )
                    )
                    prop_seq += 1

        # Özet İstatistikler
        plan.summary_counts = {
            "total_proposals": len(plan.proposals),
            "auto_approvable": sum(1 for p in plan.proposals if p.auto_approvable),
            "requires_approval": sum(1 for p in plan.proposals if not p.auto_approvable),
            "moved_to_arch_layer": sum(1 for p in plan.proposals if p.new_layer == "A-MIMARI-ALTYAPI"),
            "moved_to_elec_layers": sum(
                1 for p in plan.proposals if p.new_layer.startswith("E-") and p.auto_approvable
            ),
            "total_safety_skipped": len(plan.skipped_entities),
        }
        return plan

    @classmethod
    def apply_plan(
        cls,
        doc: Any,
        plan: DoctorChangePlan,
        approved_proposal_ids: Optional[Set[str]] = None,
        rejected_proposal_ids: Optional[Set[str]] = None,
        output_dxf_path: Optional[Union[str, Path]] = None,
        change_plan_path: Optional[Union[str, Path]] = None,
        applied_ledger_path: Optional[Union[str, Path]] = None,
    ) -> List[AppliedChangeRecord]:
        """
        Onaylanan katman taşıma önerilerini DXF belgesi üzerinde uygular.
        - Sadece INSERT / ModelSpace varlıklarını taşır; blok tanımlarına (doc.blocks) asla dokunmaz.
        - Standart katmanları CTB uyumlu lineweight ve kilit bayraklarıyla oluşturur.
        - Uygulanan her değişikliği imzalı olarak applied_changes.json mesuliyet defterine yazar.
        """
        applied_records: List[AppliedChangeRecord] = []
        used_specs: Set[str] = set()
        block_counts = CADSafetyGuard.count_block_instances(doc)

        # Önce kullanılacak standart katmanları oluştur (kilitleri en son kapatacağız)
        for prop in plan.proposals:
            should_apply = (
                (approved_proposal_ids is not None and prop.proposal_id in approved_proposal_ids)
                or (approved_proposal_ids is None and prop.auto_approvable)
            )
            if should_apply and prop.new_layer in STANDARD_LAYER_SPECS:
                used_specs.add(prop.new_layer)

        for layer_name in used_specs:
            spec = STANDARD_LAYER_SPECS[layer_name]
            layer_obj = CADSafetyGuard.ensure_standard_layer(doc, spec)
            # Taşıma sırasında kilidi geçici aç, işlem sonunda kilitle
            layer_obj.unlock()

        # Önerileri Uygula
        for prop in plan.proposals:
            if rejected_proposal_ids is not None and prop.proposal_id in rejected_proposal_ids:
                prop.status = "REJECTED"
                continue

            if approved_proposal_ids is not None:
                if prop.proposal_id not in approved_proposal_ids:
                    if prop.status not in ("REQUIRES_APPROVAL", "REJECTED"):
                        prop.status = "NOT_SELECTED"
                    continue
            else:
                if not prop.auto_approvable:
                    continue

            verdict = CADSafetyGuard.check_entity_mutable(
                doc,
                prop.dxf_handle,
                allow_single_instance_container=False,
                allow_xref_insert_ref=False,
                block_instance_counts=block_counts,
            )
            if not verdict.allowed:
                prop.status = f"SKIPPED_SAFETY({verdict.reason})"
                continue

            ent = doc.entitydb.get(prop.dxf_handle)
            if ent is None:
                continue

            old_layer = getattr(ent.dxf, "layer", "0")
            old_color = getattr(ent.dxf, "color", 256)

            # Sadece referansın (INSERT / LINE vb.) katmanını ve BYLAYER özelliklerini güncelle
            ent.dxf.layer = prop.new_layer
            ent.dxf.color = 256         # BYLAYER (CTB uyumu için zorunlu)
            ent.dxf.lineweight = -1     # BYLAYER (Katman çizgi kalınlığını miras alır)
            ent.dxf.linetype = "BYLAYER"

            prop.status = "APPROVED"
            now_iso = datetime.now(timezone.utc).isoformat()
            raw_sig = f"{prop.proposal_id}|{prop.dxf_handle}|{old_layer}->{prop.new_layer}|{now_iso}"
            sig_hash = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()[:16]

            spec = STANDARD_LAYER_SPECS.get(
                prop.new_layer,
                LayerStandardSpec(name=prop.new_layer, color=7, lineweight=25),
            )
            applied_records.append(
                AppliedChangeRecord(
                    proposal_id=prop.proposal_id,
                    dxf_handle=prop.dxf_handle,
                    dxftype=ent.dxftype(),
                    entity_label=prop.entity_label,
                    old_layer=old_layer,
                    new_layer=prop.new_layer,
                    old_color=old_color,
                    new_color_bylayer=256,
                    layer_aci_color=spec.color,
                    layer_lineweight=spec.lineweight,
                    plotstyle_name=spec.plotstyle_name,
                    layer_locked=spec.locked,
                    reason=prop.reason,
                    applied_at=now_iso,
                    signature_hash=sig_hash,
                )
            )

        # Kilitli olması gereken standart katmanları (örn: A-MIMARI-ALTYAPI) kilitle
        for layer_name in used_specs:
            spec = STANDARD_LAYER_SPECS[layer_name]
            if spec.locked and layer_name in doc.layers:
                doc.layers.get(layer_name).lock()

        # Çıktı dosyalarını kaydet
        if output_dxf_path is not None:
            out_p = Path(output_dxf_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            doc.saveas(out_p)

        if change_plan_path is not None:
            plan.save_json(change_plan_path)

        if applied_ledger_path is not None:
            led_p = Path(applied_ledger_path)
            led_p.parent.mkdir(parents=True, exist_ok=True)
            ledger_payload = {
                "drawing_name": plan.drawing_name,
                "total_applied": len(applied_records),
                "applied_changes": [asdict(r) for r in applied_records],
            }
            led_p.write_text(json.dumps(ledger_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return applied_records
