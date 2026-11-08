# -*- coding: utf-8 -*-
"""
CAD Güvenlik, Birim Ölçekleme ve Cerrahi Mutasyon Kütüphanesi (cad_safety.py)
=============================================================================
Modül 1 (LayerAndBlockDoctor), Modül 2 (TopologicalWireHealer),
Modül 3 (ElectricalAutoOptimizer) ve Modül 4 (CADTableGenerator) tarafından
ortak kullanılan, pazarlığa kapalı 4 güvenlik kalkanını uygular:

1. XREF Dokunulmazlığı: XREF blok tanımları ve iç varlıkları read-only'dir; asla değiştirilmez.
2. Blok Tanımı (BLOCK_RECORD / ATTDEF) vs Örnek (INSERT / ATTRIB) Ayrımı:
   Sembol blok tanımlarına asla dokunulmaz; yalnızca ModelSpace'teki INSERT referansı
   veya INSERT'e bağlı ATTRIB örneği güncellenir.
3. CTB / Baskı Stili Koruması: Katman taşımalarında lineweight (0.09mm..0.35mm),
   BYLAYER renk/çizgi tipi ve kilit bayrakları standart şablonla zorlanır.
4. INSUNITS Dinamik Ölçekleme ve MTEXT Biçim Korumalı Metin Güncelleme.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import re
import statistics
from typing import Any, Dict, List, Optional, Tuple


# AutoCAD $INSUNITS -> 1 çizim biriminin milimetre (mm) karşılığı
INSUNITS_TO_MM: Dict[int, float] = {
    1: 25.4,     # Inches
    2: 304.8,    # Feet
    4: 1.0,      # Millimeters
    5: 10.0,     # Centimeters
    6: 1000.0,   # Meters
}

# MTEXT başında yer alabilecek biçimlendirme dizileri (\A1;, \fArial|b0|i0;, \H2.5x;, \C1; vb.)
_MTEXT_PREFIX_RE = re.compile(
    r"^((?:\{)?(?:\\[A-Za-z][^;]*;)+)(.*?)(\})?$",
    re.DOTALL,
)


@dataclass(frozen=True)
class LayerStandardSpec:
    """CTB/STB baskı güvenliğini de içeren standart katman şablonu."""
    name: str
    color: int                          # AutoCAD Color Index (1..255)
    lineweight: int                     # mm'nin yüzde biri (örn: 9 = 0.09mm, 25 = 0.25mm, 35 = 0.35mm)
    linetype: str = "CONTINUOUS"
    locked: bool = False
    plot: bool = True
    plotstyle_name: str = "Standard"
    description: str = ""


@dataclass
class MutationSafetyVerdict:
    """Bir DXF varlığının değiştirilip değiştirilemeyeceğine dair güvenlik kararı."""
    allowed: bool
    reason: str
    handle: str = ""
    dxftype: str = ""
    owner_name: str = ""
    is_xref: bool = False
    is_block_def_entity: bool = False


class UnitScaleResolver:
    """
    Çizim birimini ($INSUNITS veya Unitless=0 durumunda yazı/sembol medyan boyutu)
    çözümleyerek milimetre/santimetre toleranslarını çizim birimine çevirir.
    """

    @classmethod
    def resolve_unit_to_mm(cls, doc: Any, scene: Optional[Any] = None) -> Tuple[float, str]:
        """
        1 çizim biriminin kaç mm olduğunu ve tespit kaynağını döner.
        Örn:
        - mm çizimi -> (1.0, "INSUNITS_MM")
        - cm çizimi -> (10.0, "INSUNITS_CM")
        - m çizimi  -> (1000.0, "INSUNITS_M")
        """
        insunits = 0
        try:
            insunits = int(doc.header.get("$INSUNITS", 0))
        except Exception:
            insunits = 0

        if insunits in INSUNITS_TO_MM:
            unit_mm = INSUNITS_TO_MM[insunits]
            unit_label = {1: "INCH", 2: "FEET", 4: "MM", 5: "CM", 6: "M"}.get(insunits, "KNOWN")
            return unit_mm, f"INSUNITS_{unit_label}"

        # $INSUNITS == 0 (Unitless) veya tanımsız ise yazı yüksekliği medyanı VE çizim yayılımı (extents) ile çapraz doğrula
        heights: List[float] = []
        xs: List[float] = []
        ys: List[float] = []

        if scene is not None and getattr(scene, "texts", None):
            for t in scene.texts:
                h = float(getattr(t, "height", 0.0) or 0.0)
                if h > 0:
                    heights.append(h)
                pos = getattr(t, "pos", None)
                if pos and len(pos) >= 2:
                    xs.append(float(pos[0]))
                    ys.append(float(pos[1]))

        if doc is not None:
            try:
                extmin = doc.header.get("$EXTMIN", None)
                extmax = doc.header.get("$EXTMAX", None)
                if extmin is not None and extmax is not None:
                    span_hdr = max(abs(float(extmax[0]) - float(extmin[0])), abs(float(extmax[1]) - float(extmin[1])))
                    if 1.0 < span_hdr < 1e9:
                        xs.extend([float(extmin[0]), float(extmax[0])])
                        ys.extend([float(extmin[1]), float(extmax[1])])
            except Exception:
                pass

            if not heights or len(xs) < 2:
                try:
                    sampled = 0
                    for ent in doc.modelspace():
                        dtype = ent.dxftype()
                        if dtype in ("TEXT", "MTEXT"):
                            h = float(getattr(ent.dxf, "height", getattr(ent.dxf, "char_height", 0.0)) or 0.0)
                            if h > 0:
                                heights.append(h)
                            ins = getattr(ent.dxf, "insert", None)
                            if ins is not None:
                                xs.append(float(ins.x))
                                ys.append(float(ins.y))
                        elif dtype == "LINE":
                            s_pt = getattr(ent.dxf, "start", None)
                            e_pt = getattr(ent.dxf, "end", None)
                            if s_pt is not None and e_pt is not None:
                                xs.extend([float(s_pt.x), float(e_pt.x)])
                                ys.extend([float(s_pt.y), float(e_pt.y)])
                        elif dtype == "INSERT":
                            ins = getattr(ent.dxf, "insert", None)
                            if ins is not None:
                                xs.append(float(ins.x))
                                ys.append(float(ins.y))
                        sampled += 1
                        if sampled >= 400:
                            break
                except Exception:
                    pass

        span = max(max(xs) - min(xs), max(ys) - min(ys)) if len(xs) >= 2 else 0.0

        if heights:
            med_h = statistics.median(heights)
            # Çizim yayılımı (span) biliniyorsa med_h ile çapraz doğrula:
            # Tipik bina/istasyon boyutu 10m..250m -> m: 10..250, cm: 1000..25000, mm: 10000..250000
            if span > 1.0:
                if span < 400.0 and med_h < 1.0:
                    return 1000.0, f"HEURISTIC_METER(median_text_h={med_h:.4f},span={span:.1f})"
                if 400.0 <= span < 18000.0 and med_h < 50.0:
                    return 10.0, f"HEURISTIC_CM(median_text_h={med_h:.3f},span={span:.1f})"
                if span >= 18000.0 and med_h >= 20.0:
                    return 1.0, f"HEURISTIC_MM(median_text_h={med_h:.2f},span={span:.1f})"

            # Span tekil veya dar ise yalnızca gerçekçi mühendislik yazı yüksekliği bantlarını kullan:
            # - Metre çizimde 1/50..1/100 ölçekli veya kağıt ölçekli yazı: <= 0.45 m
            # - Santimetre çizimde (1/50..1/100 ölçekte 10..30 cm; 1:1 ölçekte 0.25..5 cm): 0.45 < med_h < 45.0
            # - Milimetre çizimde (1/50..1/100 ölçekte 75..300 mm): med_h >= 45.0 (veya 1:1 şemada 1.8..4.5 mm)
            if med_h <= 0.45:
                return 1000.0, f"HEURISTIC_METER(median_text_h={med_h:.4f})"
            if 5.0 <= med_h < 45.0:
                return 10.0, f"HEURISTIC_CM(median_text_h={med_h:.3f})"
            if 0.45 < med_h < 1.8:
                return 10.0, f"HEURISTIC_CM(median_text_h={med_h:.3f})"
            return 1.0, f"HEURISTIC_MM(median_text_h={med_h:.2f})"

        if span > 1.0:
            if span < 400.0:
                return 1000.0, f"HEURISTIC_METER_BY_SPAN(span={span:.1f})"
            if span < 18000.0:
                return 10.0, f"HEURISTIC_CM_BY_SPAN(span={span:.1f})"
            return 1.0, f"HEURISTIC_MM_BY_SPAN(span={span:.1f})"

        return 1.0, "FALLBACK_MM"

    @classmethod
    def mm_to_drawing_units(cls, mm_val: float, doc: Any, scene: Optional[Any] = None) -> float:
        """Milimetre cinsinden verilen fiziksel toleransı çizim birimine dönüştürür."""
        unit_mm, _ = cls.resolve_unit_to_mm(doc, scene)
        if unit_mm <= 0:
            return float(mm_val)
        return float(mm_val) / unit_mm

    @classmethod
    def cm_to_drawing_units(cls, cm_val: float, doc: Any, scene: Optional[Any] = None) -> float:
        """Santimetre cinsinden verilen fiziksel toleransı (örn: 20 cm) çizim birimine dönüştürür."""
        return cls.mm_to_drawing_units(cm_val * 10.0, doc, scene)


class CADSafetyGuard:
    """
    XREF dokunulmazlığı, Blok Tanımı vs INSERT ayrımı, MTEXT biçim koruma
    ve CTB uyumlu katman oluşturma kurallarını zorlayan güvenlik kalkanı.
    """

    @staticmethod
    def is_xref_block_record(blk: Any, block_name: str = "") -> bool:
        """Blok kaydının dış referans (XREF / XREF Overlay) olup olmadığını kontrol eder."""
        bname_up = (block_name or getattr(blk, "name", "") or "").upper()
        if "|" in bname_up:
            return True
        if blk is not None:
            if getattr(blk, "is_xref", False) or getattr(blk, "is_xref_overlay", False):
                return True
            try:
                if hasattr(blk, "block_record") and blk.block_record is not None:
                    if getattr(blk.block_record, "is_xref", False):
                        return True
            except Exception:
                pass
        if "XREF" in bname_up or "M3-ARC" in bname_up:
            return True
        return False

    @classmethod
    def count_block_instances(cls, doc: Any) -> Dict[str, int]:
        """Çizimdeki her blok tanımının kaç kez INSERT edildiğini sayar."""
        counts: Dict[str, int] = {}
        try:
            for ent in doc.modelspace():
                if ent.dxftype() == "INSERT":
                    bname = getattr(ent.dxf, "name", "")
                    if bname:
                        counts[bname] = counts.get(bname, 0) + 1
            for blk in doc.blocks:
                if blk.name.startswith("*Model_Space") or blk.name.startswith("*Paper_Space"):
                    continue
                if cls.is_xref_block_record(blk, blk.name):
                    continue
                for ent in blk:
                    if ent.dxftype() == "INSERT":
                        bname = getattr(ent.dxf, "name", "")
                        if bname:
                            counts[bname] = counts.get(bname, 0) + 1
        except Exception:
            pass
        return counts

    @classmethod
    def resolve_owner_name(cls, doc: Any, ent: Any) -> str:
        """Varlığın sahibi olan Layout veya Blok adını çözümler."""
        owner_handle = getattr(ent.dxf, "owner", None)
        if not owner_handle or doc is None:
            return "*Model_Space"
        try:
            owner_obj = doc.entitydb.get(owner_handle)
            if owner_obj is None:
                return "*Model_Space"
            if owner_obj.dxftype() == "BLOCK_RECORD":
                return getattr(owner_obj.dxf, "name", "*Model_Space")
            if owner_obj.dxftype() == "INSERT":
                return f"INSERT:{getattr(owner_obj.dxf, 'handle', '')}"
        except Exception:
            pass
        return "*Model_Space"

    @classmethod
    def check_entity_mutable(
        cls,
        doc: Any,
        entity_or_handle: Any,
        allow_single_instance_container: bool = False,
        allow_xref_insert_ref: bool = False,
        block_instance_counts: Optional[Dict[str, int]] = None,
    ) -> MutationSafetyVerdict:
        """
        Bir varlığın güvenli biçimde değiştirilip değiştirilemeyeceğini denetler.
        - XREF içi varlıklar -> RED (XREF_INTERNAL_READONLY)
        - XREF INSERT referansı -> varsayılan olarak RED (XREF_INSERT_REFERENCE_PROTECTED)
        - Blok tanımı (BLOCK, BLOCK_RECORD, ATTDEF) -> RED (BLOCK_DEFINITION_IMMUTABLE)
        - Paylaşılan blok tanımı içindeki varlıklar -> RED (SHARED_BLOCK_DEFINITION_ENTITY)
        """
        if doc is None:
            return MutationSafetyVerdict(allowed=False, reason="DOC_IS_NONE")

        ent = entity_or_handle
        if isinstance(entity_or_handle, str):
            if not entity_or_handle:
                return MutationSafetyVerdict(allowed=False, reason="EMPTY_HANDLE")
            ent = doc.entitydb.get(entity_or_handle)
            if ent is None:
                return MutationSafetyVerdict(allowed=False, reason="HANDLE_NOT_FOUND", handle=entity_or_handle)

        if getattr(ent, "is_alive", True) is False:
            return MutationSafetyVerdict(allowed=False, reason="ENTITY_DESTROYED")

        dxftype = ent.dxftype()
        handle = getattr(ent.dxf, "handle", "")

        # 1. Blok tanımı veya ATTDEF kontrolü
        if dxftype in ("BLOCK", "ENDBLK", "BLOCK_RECORD", "ATTDEF"):
            return MutationSafetyVerdict(
                allowed=False,
                reason=f"BLOCK_DEFINITION_IMMUTABLE({dxftype})",
                handle=handle,
                dxftype=dxftype,
                is_block_def_entity=True,
            )

        owner_name = cls.resolve_owner_name(doc, ent)

        # 2. Eğer varlık bir INSERT ise, referans verdiği bloğun XREF olup olmadığını kontrol et
        if dxftype == "INSERT":
            target_bname = getattr(ent.dxf, "name", "")
            target_blk = doc.blocks.get(target_bname) if hasattr(doc, "blocks") else None
            if cls.is_xref_block_record(target_blk, target_bname):
                if not allow_xref_insert_ref:
                    return MutationSafetyVerdict(
                        allowed=False,
                        reason=f"XREF_INSERT_REFERENCE_PROTECTED({target_bname})",
                        handle=handle,
                        dxftype=dxftype,
                        owner_name=owner_name,
                        is_xref=True,
                    )

        # 3. Sahibin (Owner) XREF veya Blok Tanımı olup olmadığını kontrol et
        if owner_name.startswith("INSERT:"):
            # ATTRIB gibi bir INSERT'e bağlı alt varlık: sahibi olan INSERT'ü kontrol et
            parent_ins_handle = owner_name.split(":", 1)[1]
            parent_verdict = cls.check_entity_mutable(
                doc,
                parent_ins_handle,
                allow_single_instance_container=allow_single_instance_container,
                allow_xref_insert_ref=allow_xref_insert_ref,
                block_instance_counts=block_instance_counts,
            )
            if not parent_verdict.allowed:
                return MutationSafetyVerdict(
                    allowed=False,
                    reason=f"PARENT_INSERT_PROTECTED({parent_verdict.reason})",
                    handle=handle,
                    dxftype=dxftype,
                    owner_name=owner_name,
                    is_xref=parent_verdict.is_xref,
                    is_block_def_entity=parent_verdict.is_block_def_entity,
                )
            return MutationSafetyVerdict(
                allowed=True,
                reason="OK_INSERT_ATTRIB",
                handle=handle,
                dxftype=dxftype,
                owner_name=owner_name,
            )

        owner_up = owner_name.upper()
        if owner_up.startswith("*MODEL_SPACE") or owner_up.startswith("*PAPER_SPACE"):
            return MutationSafetyVerdict(
                allowed=True,
                reason="OK_LAYOUT_ENTITY",
                handle=handle,
                dxftype=dxftype,
                owner_name=owner_name,
            )

        # Buraya gelindiyse varlık bir BLOCK_RECORD (blok tanımı) içindedir!
        owner_blk = doc.blocks.get(owner_name) if hasattr(doc, "blocks") else None
        if cls.is_xref_block_record(owner_blk, owner_name):
            return MutationSafetyVerdict(
                allowed=False,
                reason=f"XREF_INTERNAL_ENTITY_READONLY({owner_name})",
                handle=handle,
                dxftype=dxftype,
                owner_name=owner_name,
                is_xref=True,
                is_block_def_entity=True,
            )

        if allow_single_instance_container:
            counts = block_instance_counts or cls.count_block_instances(doc)
            if counts.get(owner_name, 0) == 1 and ("FLOORPLAN-" in owner_up or "KAT_PLANI" in owner_up):
                return MutationSafetyVerdict(
                    allowed=True,
                    reason=f"OK_SINGLE_INSTANCE_CONTAINER({owner_name})",
                    handle=handle,
                    dxftype=dxftype,
                    owner_name=owner_name,
                )

        return MutationSafetyVerdict(
            allowed=False,
            reason=f"SHARED_BLOCK_DEFINITION_PROTECTED({owner_name})",
            handle=handle,
            dxftype=dxftype,
            owner_name=owner_name,
            is_block_def_entity=True,
        )

    @classmethod
    def ensure_standard_layer(cls, doc: Any, spec: LayerStandardSpec) -> Any:
        """
        Standart katmanı renk, çizgi tipi, CTB/lineweight ve kilit durumuyla oluşturur veya günceller.
        """
        if spec.linetype != "CONTINUOUS" and spec.linetype not in doc.linetypes:
            try:
                doc.linetypes.add(spec.linetype, pattern=[0.5, 0.25, -0.25])
            except Exception:
                pass

        if spec.name in doc.layers:
            layer = doc.layers.get(spec.name)
        else:
            layer = doc.layers.add(spec.name)

        layer.color = spec.color
        layer.dxf.lineweight = spec.lineweight
        if spec.linetype in doc.linetypes:
            layer.dxf.linetype = spec.linetype
        layer.dxf.plot = 1 if spec.plot else 0

        if spec.locked:
            layer.lock()
        else:
            layer.unlock()

        return layer

    @classmethod
    def replace_mtext_preserving_formatting(cls, raw_mtext: str, new_visible_text: str, old_substring: Optional[str] = None) -> str:
        """
        MTEXT içindeki AutoCAD biçimlendirme kodlarını (\\fArial|b0|i0;, \\A1;, \\H2.5x;, { })
        bozmadan yalnızca görünür metni günceller.
        """
        if not raw_mtext:
            return new_visible_text

        # Eğer belirli bir alt metin değiştirilecekse ve biçim kodlarına dokunmuyorsa:
        if old_substring and old_substring in raw_mtext:
            # Biçim kodu içinde mi kontrol et (örn. \f...; kısmına dokunma)
            m = _MTEXT_PREFIX_RE.match(raw_mtext)
            if m:
                prefix, body, suffix = m.group(1), m.group(2), m.group(3) or ""
                if old_substring in body:
                    return f"{prefix}{body.replace(old_substring, new_visible_text, 1)}{suffix}"
            return raw_mtext.replace(old_substring, new_visible_text, 1)

        # Tüm görünür metin değiştirilecekse baştaki tüm \...; biçim kodlarını koru
        m = _MTEXT_PREFIX_RE.match(raw_mtext)
        if m:
            prefix, _, suffix = m.group(1), m.group(2), m.group(3) or ""
            return f"{prefix}{new_visible_text}{suffix}"

        return new_visible_text

    @classmethod
    def safe_update_text_entity(
        cls,
        doc: Any,
        handle: str,
        new_text: str,
        old_substring: Optional[str] = None,
        allow_single_instance_container: bool = False,
    ) -> Tuple[bool, str, str]:
        """
        TEXT, MTEXT veya INSERT'e bağlı ATTRIB varlığının metnini güvenli biçimde günceller.
        Blok tanımı içindeki ATTDEF veya statik TEXT'lere kesinlikle dokunmaz.
        Dönüş: (başarılı_mı, durum_mesajı, eski_ham_metin)
        """
        verdict = cls.check_entity_mutable(
            doc, handle, allow_single_instance_container=allow_single_instance_container
        )
        if not verdict.allowed:
            return False, verdict.reason, ""

        ent = doc.entitydb.get(handle)
        dxftype = ent.dxftype()

        if dxftype == "TEXT":
            old_raw = getattr(ent.dxf, "text", "")
            if old_substring and old_substring in old_raw:
                ent.dxf.text = old_raw.replace(old_substring, new_text, 1)
            else:
                ent.dxf.text = new_text
            return True, "UPDATED_TEXT", old_raw

        if dxftype == "MTEXT":
            old_raw = ent.text
            ent.text = cls.replace_mtext_preserving_formatting(old_raw, new_text, old_substring=old_substring)
            return True, "UPDATED_MTEXT_PRESERVING_FORMAT", old_raw

        if dxftype == "ATTRIB":
            old_raw = getattr(ent.dxf, "text", "")
            if old_substring and old_substring in old_raw:
                ent.dxf.text = old_raw.replace(old_substring, new_text, 1)
            else:
                ent.dxf.text = new_text
            return True, "UPDATED_INSERT_ATTRIB", old_raw

        return False, f"UNSUPPORTED_TEXT_ENTITY_TYPE({dxftype})", ""
