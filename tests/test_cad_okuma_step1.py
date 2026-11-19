# -*- coding: utf-8 -*-
"""
Adım 1 — Evrensel CAD Okuma & Kanonik Kalıp Doğrulama Testleri
==============================================================
Sıfır hardcode (anti-overfit): tamamen farklı blok isimleri, farklı çizim
birimleri (mm / cm / m), dinamik bloklar (*U), ACAD_TABLE, çok-satırlı MTEXT,
hizalı TEXT (align_point) ve L-tipi çokgen topraklama senaryolarını test eder.
"""

from __future__ import annotations
from pathlib import Path
import sys

import ezdxf
import pytest

MOTOR_ROOT = Path(__file__).resolve().parents[1] / "03_hesap_motoru"
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from cad_okuma import (  # noqa: E402
    build_calculation_audit_report,
    build_canonical_model,
    build_project_inventory,
    calibrate_unit,
    extract_raw_snapshot,
    format_calculation_audit_markdown,
    format_inventory_markdown,
    save_calculation_audit_reports,
    save_inventory_reports,
)


def _add_door_arc(msp, cx: float, cy: float, radius: float) -> None:
    msp.add_arc(center=(cx, cy), radius=radius, start_angle=0.0, end_angle=90.0, dxfattribs={"layer": "A-KAPI"})


def test_step1_unit_calibration_insunits4_protection(tmp_path: Path) -> None:
    """
    Açıkça INSUNITS=4 (mm) olan bir şemada kapı yayı yoksa ve metin 20 mm ise
    kalibratör bunu YANLIŞLIKLA cm'e çevirmemelidir!
    """
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    for i in range(6):
        msp.add_text(f"PANO-{i}", dxfattribs={"height": 20.0, "insert": (100 * i, 100)})
    msp.add_line((0, 0), (3000, 0))
    msp.add_line((3000, 0), (3000, 2000))
    dxf_path = tmp_path / "pure_mm_schematic.dxf"
    doc.saveas(dxf_path)

    snap = extract_raw_snapshot(dxf_path, use_cache=False)
    uc = calibrate_unit(snap)
    assert uc.unit_name == "mm"
    assert uc.du_to_m == pytest.approx(0.001)


@pytest.mark.parametrize("unit_name,scale", [("m", 1.0), ("cm", 100.0), ("mm", 1000.0)])
def test_step1_unit_invariant_grounding_and_frames(tmp_path: Path, unit_name: str, scale: float) -> None:
    """
    L-şeklinde çokgen temel ringi + 3 filiz + çok-satırlı GD formülü m / cm / mm
    olarak çizildiğinde sonuçlar metre cinsinden birebir aynı kalmalıdır.
    """
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4  # Kasıtlı şablon yanıltması: her ölçekte 4!
    msp = doc.modelspace()

    # Pafta 1: Topraklama Planı (35m x 25m)
    msp.add_lwpolyline([(0, 0), (35 * scale, 0), (35 * scale, 25 * scale), (0, 25 * scale)], close=True)
    msp.add_text("TEMEL TOPRAKLAMA PLANI", dxfattribs={"height": 0.40 * scale, "insert": (1 * scale, 23 * scale)})
    for k in range(3):
        _add_door_arc(msp, (2 + k * 2) * scale, 2 * scale, 0.90 * scale)

    # L-şekilli ring: (5,5)-(20,5)-(20,10)-(12,10)-(12,16)-(5,16)
    # Kenarlar: 15 + 5 + 8 + 6 + 7 + 11 = 52.0 m | Alan: 15*5 + 7*6 = 75 + 42 = 117.0 m²
    l_pts = [
        (5 * scale, 5 * scale),
        (20 * scale, 5 * scale),
        (20 * scale, 10 * scale),
        (12 * scale, 10 * scale),
        (12 * scale, 16 * scale),
        (5 * scale, 16 * scale),
    ]
    msp.add_lwpolyline(l_pts, close=True, dxfattribs={"layer": "E-TOPRAKLAMA"})
    # 3 adet 2.5m dış filiz
    msp.add_line((5 * scale, 5 * scale), (5 * scale, 2.5 * scale), dxfattribs={"layer": "E-TOPRAKLAMA"})
    msp.add_line((20 * scale, 5 * scale), (22.5 * scale, 5 * scale), dxfattribs={"layer": "E-TOPRAKLAMA"})
    msp.add_line((5 * scale, 16 * scale), (5 * scale, 18.5 * scale), dxfattribs={"layer": "E-TOPRAKLAMA"})

    # Pafta 2: İki satırlı Gerilim Düşümü Hesabı (15m x 8m)
    ox = 40 * scale
    msp.add_lwpolyline([(ox, 0), (ox + 15 * scale, 0), (ox + 15 * scale, 8 * scale), (ox, 8 * scale)], close=True)
    th = 0.25 * scale
    msp.add_text("GERİLİM DÜŞÜMÜ HESABI", dxfattribs={"height": th * 1.4, "insert": (ox + 1 * scale, 7 * scale)})
    msp.add_text("40 x 12,500", dxfattribs={"height": th, "insert": (ox + 3.5 * scale, 4.7 * scale)})
    msp.add_text("0,0124 x ------------------", dxfattribs={"height": th, "insert": (ox + 1.5 * scale, 4.3 * scale)})
    msp.add_text("16", dxfattribs={"height": th, "insert": (ox + 4.3 * scale, 3.8 * scale)})
    # Sonuç bir alt satırda ayrı TEXT nesnesi
    msp.add_text("%%%e =", dxfattribs={"height": th, "insert": (ox + 1.5 * scale, 3.1 * scale)})
    msp.add_text("0,39", dxfattribs={"height": th, "insert": (ox + 4.1 * scale, 3.1 * scale)})

    dxf_path = tmp_path / f"l_shape_{unit_name}.dxf"
    doc.saveas(dxf_path)

    _, model = build_canonical_model(dxf_path, use_cache=False)
    assert model.unit.unit_name == unit_name
    assert len(model.grounding_loops) == 1
    gnd = model.grounding_loops[0]
    assert gnd.outer_perimeter_m == pytest.approx(52.0, abs=0.1)
    assert gnd.area_m2 == pytest.approx(117.0, abs=0.2)
    assert gnd.spur_count == 3
    assert gnd.spur_total_m == pytest.approx(7.5, abs=0.1)

    vd_ok = [fb for fb in model.formula_blocks if fb.formula_kind == "VOLTAGE_DROP" and fb.parse_status == "OK"]
    assert len(vd_ok) == 1
    assert vd_ok[0].parsed_result_value == pytest.approx(0.39, abs=0.005)


def test_step1_lossless_mtext_align_point_acad_table_and_dynamic_block(tmp_path: Path) -> None:
    """
    MTEXT çok satırlı yapı (\\P), hizalı TEXT (align_point), ACAD_TABLE ve
    LEADER nesnelerinin kayıpsız çıkarıldığını doğrular.
    """
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 5  # Explicit cm
    msp = doc.modelspace()

    # Çok satırlı MTEXT
    msp.add_mtext(r"SATIR BIR\PSATIR IKI\P{\fArial|b1;SATIR UC}", dxfattribs={"char_height": 15.0, "insert": (100, 500)})

    # Sağa hizalı TEXT: insert=(0,0) iken gerçek konum align_point=(320, 420)
    t_al = msp.add_text("HIZALI ETIKET", dxfattribs={"height": 12.0, "halign": 2, "valign": 1})
    t_al.dxf.insert = (0.0, 0.0)
    t_al.dxf.align_point = (320.0, 420.0, 0.0)

    # LEADER
    msp.add_leader([(50.0, 50.0), (120.0, 120.0)])

    # INSERT + ATTRIB (özgün isimler, zero-hardcode)
    blk = doc.blocks.new(name="CUSTOM_PANEL_SYM")
    blk.add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)], close=True)
    blk.add_attdef("PANO_ADI", insert=(5, 5), dxfattribs={"height": 4.0})
    ins = msp.add_blockref("CUSTOM_PANEL_SYM", (600.0, 400.0))
    ins.add_auto_attribs({"PANO_ADI": "PANO-X99"})

    dxf_path = tmp_path / "entities_full.dxf"
    doc.saveas(dxf_path)

    snap, model = build_canonical_model(dxf_path, use_cache=False)
    mtexts = [t for t in snap.texts if t.dxftype == "MTEXT"]
    assert len(mtexts) == 1
    assert mtexts[0].lines == ["SATIR BIR", "SATIR IKI", "SATIR UC"]

    aligned = [t for t in snap.texts if t.text == "HIZALI ETIKET"]
    assert len(aligned) == 1
    assert aligned[0].from_align_point is True
    assert aligned[0].x == pytest.approx(320.0, abs=0.1)
    assert aligned[0].y == pytest.approx(420.0, abs=0.1)

    assert len(snap.leaders) == 1
    assert len(snap.leaders[0].vertices) == 2

    panels = [i for i in snap.inserts if i.effective_name == "CUSTOM_PANEL_SYM"]
    assert len(panels) == 1
    assert panels[0].attribs.get("PANO_ADI") == "PANO-X99"


def test_step1_schematic_graph_topology_anti_overfit(tmp_path: Path) -> None:
    """
    Sabit pano/sembol isimleri olmadan T-kavşaklı kolon/tek-hat şemasının
    tek bağlı topolojik graf olarak çıkarıldığını doğrular.
    """
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 5  # cm
    msp = doc.modelspace()

    # Çerçeve (20m x 15m -> 2000cm x 1500cm)
    msp.add_lwpolyline([(0, 0), (2000, 0), (2000, 1500), (0, 1500)], close=True)
    msp.add_text("KOLON SEMASI", dxfattribs={"height": 30.0, "insert": (100, 1420)})

    # T-kavşaklı besleme omurgası + 2 kol
    msp.add_line((200, 800), (1600, 800))          # Ana bara
    msp.add_line((900, 800), (900, 1150))          # Dikey T-kavşak branşman
    msp.add_line((1600, 800), (1600, 450))         # Alt branşman

    msp.add_text("KAYNAK-ALPHA", dxfattribs={"height": 18.0, "insert": (180, 820)})
    msp.add_text("4x16 N2XH", dxfattribs={"height": 15.0, "insert": (450, 815)})
    msp.add_text("PANO-Q7", dxfattribs={"height": 18.0, "insert": (880, 1170)})
    msp.add_text("PANO-Z9", dxfattribs={"height": 18.0, "insert": (1580, 420)})

    dxf_path = tmp_path / "schematic_anti_overfit.dxf"
    doc.saveas(dxf_path)

    _, model = build_canonical_model(dxf_path, use_cache=False)
    assert model.unit.unit_name == "cm"
    assert len(model.schematics) == 1
    sg = model.schematics[0]
    assert sg.connected_components == 1
    assert len(sg.edges) >= 3
    all_edge_texts = " ".join(" ".join(e.texts_along_edge) for e in sg.edges)
    all_node_texts = " ".join(" ".join(n.texts) for n in sg.nodes)
    combined = f"{all_edge_texts} {all_node_texts}"
    assert "KAYNAK-ALPHA" in combined
    assert "PANO-Q7" in combined
    assert "PANO-Z9" in combined


@pytest.mark.parametrize(
    "rel_path,expected_vd,expected_perim",
    [
        ("_arsiv/ornekprojeler/5katlı 10 daireli.dxf", {0.36, 0.37}, 70.79),
        ("_arsiv/ornekprojeler/adem_abi_elektrik.dxf", {0.15, 0.1, 0.82}, 41.77),
        ("_arsiv/ornekprojeler/osman_yesildemir_elektrik.dxf", {0.25, 0.45}, 44.63),
    ],
)
def test_step1_real_building_corpus_regression(
    rel_path: str,
    expected_vd: set[float],
    expected_perim: float,
) -> None:
    """
    Gerçek arşiv projelerinde sıfır hata/uyarı ile birim kalibrasyonu,
    temel topraklama ringi, çok-satırlı VD formülü ve OLE gömülü tespiti.
    """
    root_dir = Path(__file__).resolve().parents[1]
    dxf_path = root_dir / rel_path
    if not dxf_path.exists():
        pytest.skip(f"Referans DXF bulunamadı: {dxf_path}")

    snap, model = build_canonical_model(dxf_path, use_cache=False)
    assert snap.extraction_warnings == []
    assert model.unit.unit_name == "cm"
    assert model.unit.confidence >= 0.90
    assert len(snap.ole_objects) >= 1
    assert all(o.decode_status == "OK" and o.decoded_text_count > 0 for o in snap.ole_objects)
    assert all(
        fb.parse_status == "OK"
        for fb in model.formula_blocks
        if fb.formula_kind == "VOLTAGE_DROP"
    )
    inv = build_project_inventory(snap, model)
    assert len(inv.ole_decoded_tables) == len(snap.ole_objects)
    assert not any("çözülemeyen gömülü OLE" in a or "kısmi/eksik okundu" in a for a in inv.alerts_summary)
    assert len(model.grounding_loops) >= 1
    assert model.grounding_loops[0].outer_perimeter_m == pytest.approx(expected_perim, abs=0.05)

    vd_ok = {
        round(fb.parsed_result_value, 2)
        for fb in model.formula_blocks
        if fb.formula_kind == "VOLTAGE_DROP" and fb.parse_status == "OK" and fb.parsed_result_value is not None
    }
    assert expected_vd.issubset(vd_ok)


def test_step1_project_inventory_bom_anti_overfit(tmp_path: Path) -> None:
    """
    Özgün pano isimleri (MDP-BETA, KAT-P4), Sembol/Açıklaması lejantı, şalt kümesi
    (KAKR + TMŞ + sayaç + kablo) ve mimari blok filtresi ile metraj özetini doğrular.
    """
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 5  # cm
    msp = doc.modelspace()

    b_priz = doc.blocks.new(name="S_X")
    b_priz.add_circle((0, 0), radius=10)
    b_arm = doc.blocks.new(name="A_Y")
    b_arm.add_circle((0, 0), radius=15)
    b_arch = doc.blocks.new(name="KLOZET_2")
    b_arch.add_lwpolyline([(0, 0), (40, 0), (40, 50), (0, 50)], close=True)

    # Pafta 1: Lejant ("Sembol" / "Açıklaması")
    msp.add_lwpolyline([(0, 0), (2000, 0), (2000, 1500), (0, 1500)], close=True)
    msp.add_text("LEJANT", dxfattribs={"height": 30.0, "insert": (100, 1400)})
    msp.add_text("Sembol", dxfattribs={"height": 15.0, "insert": (200, 1250)})
    msp.add_text("Açıklaması", dxfattribs={"height": 15.0, "insert": (350, 1250)})
    msp.add_blockref("S_X", (220, 1100), dxfattribs={"layer": "E-PRIZ"})
    msp.add_text("Toprakli Priz", dxfattribs={"height": 12.0, "insert": (350, 1095)})
    msp.add_blockref("A_Y", (220, 950), dxfattribs={"layer": "E-AYD"})
    msp.add_text("LED Tavan Armaturu", dxfattribs={"height": 12.0, "insert": (350, 945)})

    # Pafta 2: Kolon Şeması (MDP-BETA ve KAT-P4)
    ox = 2500.0
    msp.add_lwpolyline([(ox, 0), (ox + 2000, 0), (ox + 2000, 1500), (ox, 1500)], close=True)
    msp.add_text("KUVVETLİ AKIM KOLON DAĞITIM ŞEMASI", dxfattribs={"height": 30.0, "insert": (ox + 100, 1400)})
    msp.add_text("MDP-BETA", dxfattribs={"height": 16.0, "insert": (ox + 300, 1150)})
    msp.add_text("3x63A", dxfattribs={"height": 12.0, "insert": (ox + 300, 1100)})
    msp.add_text("TMS", dxfattribs={"height": 12.0, "insert": (ox + 340, 1100)})
    msp.add_text("4x10N2XH", dxfattribs={"height": 12.0, "insert": (ox + 300, 1020)})
    msp.add_text("25m", dxfattribs={"height": 12.0, "insert": (ox + 350, 995)})
    msp.add_text("KAT-P4", dxfattribs={"height": 16.0, "insert": (ox + 900, 1150)})
    msp.add_text("3x10(30A)", dxfattribs={"height": 12.0, "insert": (ox + 900, 1100)})
    msp.add_text("4x40A", dxfattribs={"height": 12.0, "insert": (ox + 900, 1040)})
    msp.add_text("KAK", dxfattribs={"height": 12.0, "insert": (ox + 900, 1015)})
    msp.add_text("30mA", dxfattribs={"height": 12.0, "insert": (ox + 900, 990)})
    msp.add_text("12500W", dxfattribs={"height": 12.0, "insert": (ox + 900, 950)})

    # Pafta 3: Kat Planı (7 priz, 4 armatür, 2 mimari klozet)
    px = 5000.0
    msp.add_lwpolyline([(px, 0), (px + 2500, 0), (px + 2500, 1500), (px, 1500)], close=True)
    msp.add_text("1. KAT KUVVETLİ AKIM PLANI", dxfattribs={"height": 30.0, "insert": (px + 100, 1400)})
    _add_door_arc(msp, px + 300, 300, 90.0)
    for k in range(7):
        msp.add_blockref("S_X", (px + 400 + k * 120, 600), dxfattribs={"layer": "E-PRIZ"})
    for k in range(4):
        msp.add_blockref("A_Y", (px + 400 + k * 200, 900), dxfattribs={"layer": "E-AYD"})
    for k in range(2):
        msp.add_blockref("KLOZET_2", (px + 400 + k * 150, 200), dxfattribs={"layer": "A-MIMARI"})

    dxf_path = tmp_path / "inventory_anti_overfit.dxf"
    doc.saveas(dxf_path)

    snap, model = build_canonical_model(dxf_path, use_cache=False)
    inv = build_project_inventory(snap, model)

    panel_names = {p.panel_name for p in inv.panels}
    assert {"MDP-BETA", "KAT-P4"}.issubset(panel_names)
    kat_p4 = next(p for p in inv.panels if p.panel_name == "KAT-P4")
    assert kat_p4.installed_power_w == pytest.approx(12500.0)

    sg_specs = {s.spec: s.count for s in inv.switchgear_bom}
    assert sg_specs.get("3x63A TMŞ") == 1
    assert sg_specs.get("4x40A 30mA KAKR") == 1
    assert sg_specs.get("Sayaç 3x10(30A)") == 1

    cabs = {c.spec: c for c in inv.cable_bom}
    assert "4x10N2XH" in cabs
    assert cabs["4x10N2XH"].explicit_length_m == pytest.approx(25.0)

    syms = {s.block_name: s for s in inv.symbol_bom}
    assert syms["S_X"].total_count == 7
    assert syms["S_X"].description == "Toprakli Priz"
    assert syms["A_Y"].total_count == 4
    assert syms["A_Y"].category == "AYDINLATMA"
    assert inv.non_electrical_block_count == 2
    assert "MDP-BETA" in format_inventory_markdown(inv, sheets=model.sheets)
    docx_p, md_p, js_p = save_inventory_reports(inv, tmp_path / "out", sheets=model.sheets)
    assert docx_p.exists() and docx_p.suffix == ".docx" and docx_p.stat().st_size > 5000
    assert md_p.exists() and js_p.exists()


def test_step1_outside_clusters_and_feeder_segments(tmp_path: Path):
    """Çerçevesiz (antetsiz) alan kümeleri ve kablo+uzunluk hat etiketlerini doğrular (anti-overfit)."""
    import ezdxf

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5  # cm
    msp = doc.modelspace()

    # Fiziksel birim kalibrasyonu için kapı yayı (85 cm)
    msp.add_arc((100.0, 100.0), radius=85.0, start_angle=0.0, end_angle=90.0)

    # Tek çerçeveli pafta: Gerilim Düşümü Hesabı (kablo + metre barı içeren)
    msp.add_lwpolyline([(0, 0), (3000, 0), (3000, 2000), (0, 2000)], close=True)
    msp.add_text("GERILIM DUSUMU HESABI", dxfattribs={"height": 30, "insert": (200, 1850)})
    msp.add_line((400, 1200), (750, 1200))
    msp.add_text("4x10NYM", dxfattribs={"height": 20, "insert": (520, 1230)})
    msp.add_text("18m", dxfattribs={"height": 20, "insert": (540, 1165)})

    # Elektrik blok tanımları
    for blk_name in ("PRIZ_DUVAR", "ARMATUR_TAVAN"):
        blk = doc.blocks.new(name=blk_name)
        blk.add_circle((0, 0), radius=12.0)

    # Pafta dışı Alan 1 (5000..5400, 0..400) -> 50 m'den fazla uzakta
    msp.add_text("BOLUM-ALFA KAT PLANI", dxfattribs={"height": 28, "insert": (5050, 350)})
    msp.add_text("Kablo hattı notu", dxfattribs={"height": 15, "insert": (5050, 300)})
    msp.add_text("Aydınlatma linyesi", dxfattribs={"height": 15, "insert": (5050, 260)})
    msp.add_blockref("PRIZ_DUVAR", (5100, 150))
    msp.add_blockref("PRIZ_DUVAR", (5250, 150))

    # Pafta dışı Alan 2 (12000..12400, 0..400) -> Alan 1'den 66 m uzakta
    msp.add_text("BOLUM-BETA KAT PLANI", dxfattribs={"height": 28, "insert": (12050, 350)})
    msp.add_text("Priz devresi", dxfattribs={"height": 15, "insert": (12050, 300)})
    msp.add_text("Acil çıkışı", dxfattribs={"height": 15, "insert": (12050, 260)})
    msp.add_blockref("ARMATUR_TAVAN", (12100, 150))
    msp.add_blockref("ARMATUR_TAVAN", (12200, 150))
    msp.add_blockref("PRIZ_DUVAR", (12300, 150))

    dxf_path = tmp_path / "sentetik_antetsiz.dxf"
    doc.saveas(dxf_path)

    snap, model = build_canonical_model(dxf_path, use_cache=False)
    inv = build_project_inventory(snap, model)

    feeders = [fb for fb in model.formula_blocks if fb.formula_kind == "FEEDER_SEGMENT"]
    vd_partial = [
        fb for fb in model.formula_blocks
        if fb.formula_kind == "VOLTAGE_DROP" and fb.parse_status != "OK"
    ]
    assert len(feeders) == 1
    assert feeders[0].parse_status == "OK"
    assert feeders[0].parsed_result_value == pytest.approx(18.0, abs=0.01)
    assert vd_partial == []

    assert len(inv.outside_clusters) == 2
    titles = {c.title for c in inv.outside_clusters}
    assert "BOLUM-ALFA KAT PLANI" in titles
    assert "BOLUM-BETA KAT PLANI" in titles
    counts = sorted(c.electrical_symbol_count for c in inv.outside_clusters)
    assert counts == [2, 3]

    md_text = format_inventory_markdown(inv, sheets=model.sheets)
    assert "Bölüm 4B" in md_text
    assert "BOLUM-ALFA KAT PLANI" in md_text
    assert "BOLUM-BETA KAT PLANI" in md_text


def test_step1_ole2_xlsx_decode_and_emf_grouping(tmp_path: Path):
    """Sentetik Excel XLSX baytlarını ve EMF satır/sütun gruplamasını doğrular."""
    import openpyxl
    from cad_okuma.ham_cikarici import _decode_ole2_payload, _group_emf_cells_to_rows

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Yukleme"
    ws.append(["PANO YÜKLEME CETVELİ", "", ""])
    ws.append(["Linyesi", "Güç (kW)", "Sigorta"])
    ws.append(["L1", 2.4, "B16"])
    xlsx_path = tmp_path / "tablo.xlsx"
    wb.save(xlsx_path)

    class _FakeOle:
        def __init__(self, data: bytes):
            self._data = data

        def binary_data(self) -> bytes:
            return self._data

    status, title, rows, cell_count = _decode_ole2_payload(_FakeOle(xlsx_path.read_bytes()))
    assert status == "OK"
    assert "PANO YÜKLEME CETVELİ" in title
    assert len(rows) == 3
    assert cell_count >= 6
    assert rows[2][0] == "L1" and rows[2][2] == "B16"

    # EMF hücre koordinatlarının (y, x, metin) satır ve sütun sırasına doğru dizilmesi
    emf_rows = _group_emf_cells_to_rows([
        (100, 300, "Güç"),
        (100, 100, "Pano"),
        (160, 102, "T-10"),
        (162, 301, "12.5 kW"),
    ])
    assert emf_rows == [["Pano", "Güç"], ["T-10", "12.5 kW"]]


def test_step1_arch_vs_elec_and_below_title_views(tmp_path: Path):
    """
    'mm' biriminde:
    1) Mimari duvar/kapı/anonim bloklar ile '0' katmanındaki temaslı elektrik hatlarını ayırır.
    2) Üstteki 2x2 çerçevesiz planları altlarındaki başlıklara göre Kat x Disiplin olarak böler.
    """
    import ezdxf

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4  # mm (fiziksel kapı yayıyla doğrulanır)
    msp = doc.modelspace()

    for blk_name in ("Kloz_W1", "A$C99887766", "ZAYIF_TV", "PRIZ_220", "TP_CUBUK"):
        blk = doc.blocks.new(name=blk_name)
        blk.add_circle((0, 0), radius=120.0)

    # Referans çerçevesi (mm: 30m x 20m = 30000 x 20000) sadece kalibrasyon + tablo testi
    msp.add_lwpolyline([(0, 0), (15000, 0), (15000, 10000), (0, 10000)], close=True)
    msp.add_text("LEJANT", dxfattribs={"height": 300, "insert": (1000, 9000)})
    # Fiziksel kapı yayı (r = 900 mm = 0.90 m)
    msp.add_arc((2000, 2000), radius=900.0, start_angle=0.0, end_angle=90.0)

    # --- Çerçeve Dışı 2x2 Plan Matrisi (her bölgenin başlığı tam ALTINDA) ---
    # Üst Sol: Asma Kat - Zayıf Akım (y=40..50m, başlık y=38m)
    msp.add_blockref("ZAYIF_TV", (22000, 44000), dxfattribs={"layer": "E-ZAYIF"})
    msp.add_blockref("ZAYIF_TV", (24000, 44000), dxfattribs={"layer": "E-ZAYIF"})
    msp.add_blockref("Kloz_W1", (23000, 46000), dxfattribs={"layer": "TF2"})
    msp.add_text("1. ASMA KAT PLANI", dxfattribs={"height": 500, "insert": (22000, 38000)})

    # Üst Sağ: Teras Çatı - Salt Mimari Altlık (0 elektrik sembolü!)
    msp.add_blockref("Kloz_W1", (47000, 45000), dxfattribs={"layer": "A-MIMARI"})
    msp.add_line((46000, 42000), (50000, 42000), dxfattribs={"layer": "0"})  # Temassız duvar
    msp.add_text("TERAS CATI PLANI", dxfattribs={"height": 500, "insert": (47000, 38000)})

    # Alt Sol: Asma Kat - Kuvvetli Akım + '0' katmanında temaslı kablo hattı + anonim blok
    msp.add_blockref("PRIZ_220", (22000, 18000), dxfattribs={"layer": "E-PRIZ"})
    msp.add_blockref("PRIZ_220", (24500, 18000), dxfattribs={"layer": "E-PRIZ"})
    msp.add_blockref("A$C99887766", (23500, 19500), dxfattribs={"layer": "0"})
    msp.add_line((22000, 18000), (24500, 18000), dxfattribs={"layer": "0"})  # Sembole değen hat = 2.5 m
    msp.add_line((21000, 15000), (26000, 15000), dxfattribs={"layer": "0"})  # Temassız duvar = mimari/belirsiz
    msp.add_text("1. ASMA KAT PLANI", dxfattribs={"height": 500, "insert": (22000, 12000)})

    # Alt Sağ: 2. Bodrum Kat - Topraklama
    msp.add_blockref("TP_CUBUK", (47000, 18000), dxfattribs={"layer": "E-TOPRAK"})
    msp.add_blockref("TP_CUBUK", (48500, 18000), dxfattribs={"layer": "E-TOPRAK"})
    msp.add_text("2. BODRUM KAT PLANI", dxfattribs={"height": 500, "insert": (47000, 12000)})

    dxf_path = tmp_path / "mm_mimari_elektrik_views.dxf"
    doc.saveas(dxf_path)

    snap, model = build_canonical_model(dxf_path, use_cache=False)
    assert model.unit.unit_name == "mm"
    inv = build_project_inventory(snap, model)

    outside_views = [v for v in inv.views if v.source_kind == "CERCEVESIZ_PLAN"]
    assert len(outside_views) == 4
    by_disc = {v.discipline: v for v in outside_views}
    assert set(by_disc.keys()) == {"ZAYIF_AKIM", "SALT_MIMARI_ALTLIK", "KUVVETLI_AKIM", "TOPRAKLAMA"}

    # Anonim A$C99887766 elektrik olarak sayılmaz, belirsiz olarak ayrılır
    v_pwr = by_disc["KUVVETLI_AKIM"]
    assert v_pwr.floor_or_scope == "1. Asma Kat" or "Asma Kat" in v_pwr.floor_or_scope
    assert v_pwr.elec_symbol_count == 2
    assert v_pwr.uncertain_block_count == 1
    assert v_pwr.elec_wire_count == 1
    assert v_pwr.elec_wire_length_m == pytest.approx(2.5, abs=0.1)

    v_arch = by_disc["SALT_MIMARI_ALTLIK"]
    assert v_arch.floor_or_scope == "Çatı / Teras"
    assert v_arch.elec_symbol_count == 0
    assert v_arch.arch_block_count == 1

    v_gnd = by_disc["TOPRAKLAMA"]
    assert "Bodrum Kat" in v_gnd.floor_or_scope
    assert v_gnd.elec_symbol_count == 2

    md = format_inventory_markdown(inv, sheets=model.sheets)
    assert "Görünüm Haritası" in md
    assert "Salt Mimari Altlık" in md


def test_step1_legend_exclusion_1to1_match_grounding_and_panel_crosscheck(tmp_path: Path):
    """
    Evrensellik ve anti-overfit testi (sentetik cm projesi, farklı pano isimleri KP-1..KP-4 & ANA):
    1) Sıkı satırlı lejantta komşu satır açıklamaları birbiriyle birleşmez (SAYAÇ / ZAYIF_AKIM doğru kalır).
    2) Topraklama paftasındaki gömülü yerel lejant kutusu örnek blokları/çizgileri saha sayımına girmez.
    3) 3 filiz vs 2 çubuk farkı + 'NOTLAR' kutusu yanlış rol almaz + 40x4mm şerit ve 35mm2 bakır okunur.
    4) Kolon şemasında 3(32A), KP-1..4 dikey koridor eşleşmesi + eksik KP-4 kesici/KAKR/kablo uyarısı + şema/saha ayrımı.
    """
    import ezdxf

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5  # cm
    msp = doc.modelspace()

    for blk_name in ("TOP_ROD", "PRIZ_220", "ZIL_BTN", "SAY_SYM"):
        blk = doc.blocks.new(name=blk_name)
        blk.add_circle((0, 0), radius=12.0)

    # Pafta 1: LEJANT (sıkı dikey aralık: dy=35 cm, h=15 cm -> sadece en yakın satır eşleşmeli)
    msp.add_lwpolyline([(0, 0), (1500, 0), (1500, 1000), (0, 1000)], close=True)
    msp.add_text("LEJANT", dxfattribs={"height": 30, "insert": (100, 900)})
    msp.add_text("Sembol", dxfattribs={"height": 15, "insert": (120, 820)})
    msp.add_text("Açıklaması", dxfattribs={"height": 15, "insert": (280, 820)})
    legend_rows = [
        ("ZIL_BTN", 760, "Zil Butonu"),
        ("SAY_SYM", 725, "Elektrik Sayacı"),
        ("PRIZ_220", 690, "Topraklı Priz"),
        ("TOP_ROD", 655, "Topraklama Çubuğu"),
    ]
    for bname, yy, desc in legend_rows:
        msp.add_blockref(bname, (150, yy), dxfattribs={"layer": "E-SEMBOL"})
        msp.add_text(desc, dxfattribs={"height": 15, "insert": (280, yy - 5)})

    # Pafta 2: TOPRAKLAMA PLANI (cm: 1200 x 800 cm = 12 m x 8 m ring, 3 filiz ama sadece 2 çubuk, + yerel lejant)
    ox = 2000.0
    msp.add_lwpolyline([(ox, 0), (ox + 3500, 0), (ox + 3500, 2500), (ox, 2500)], close=True)
    msp.add_text("TEMEL TOPRAKLAMA PLANI", dxfattribs={"height": 30, "insert": (ox + 100, 2350)})
    # Kapalı ring (12m x 8m => çevre 40.0 m, alan 96.0 m2)
    msp.add_lwpolyline(
        [(ox + 400, 400), (ox + 1600, 400), (ox + 1600, 1200), (ox + 400, 1200)],
        close=True,
        dxfattribs={"layer": "E-TOPRAK"},
    )
    # 3 adet 2.0 m filiz ama köşe 3'te TOP_ROD silinmiş!
    spurs = [((400, 400), (400, 200), True), ((1600, 400), (1600, 200), True), ((1600, 1200), (1600, 1400), False)]
    for (sx0, sy0), (sx1, sy1), has_rod in spurs:
        msp.add_line((ox + sx0, sy0), (ox + sx1, sy1), dxfattribs={"layer": "E-TOPRAK"})
        if has_rod:
            msp.add_blockref("TOP_ROD", (ox + sx1, sy1), dxfattribs={"layer": "E-TOPRAK"})
    msp.add_text("40x4mm Galvaniz Çelik Lama", dxfattribs={"height": 18, "insert": (ox + 600, 100)})
    msp.add_text("35mm2 Çıplak Örgü Bakır", dxfattribs={"height": 18, "insert": (ox + 600, 60)})
    # Aynı paftada sağ üst köşede yerel "Sembol | Açıklaması" lejant kutusu (sayıma GİRMEMELİ)
    msp.add_text("Sembol", dxfattribs={"height": 15, "insert": (ox + 2800, 2200)})
    msp.add_text("Açıklaması", dxfattribs={"height": 15, "insert": (ox + 2950, 2200)})
    msp.add_blockref("TOP_ROD", (ox + 2830, 2140), dxfattribs={"layer": "E-TOPRAK"})
    msp.add_text("Topraklama Çubuğu", dxfattribs={"height": 15, "insert": (ox + 2950, 2135)})
    msp.add_line((ox + 2790, 2080), (ox + 2880, 2080), dxfattribs={"layer": "E-TOPRAK"})
    msp.add_text("40x4mm Galvaniz Çelik Lama", dxfattribs={"height": 15, "insert": (ox + 2950, 2075)})

    # Pafta 3: GENEL NOTLAR kutusu ('CETVELINDE' ve 'TOPRAKLAMA' geçse bile TOPRAKLAMA değil DETAY olmalı)
    nx = 6000.0
    msp.add_lwpolyline([(nx, 0), (nx + 1500, 0), (nx + 1500, 1200), (nx, 1200)], close=True)
    msp.add_text("AYDINLATMA - PRIZ NOTLAR:", dxfattribs={"height": 20, "insert": (nx + 100, 1050)})
    msp.add_text("1- YUKLEME CETVELINDE 60W ALINACAKTIR.", dxfattribs={"height": 20, "insert": (nx + 100, 950)})
    msp.add_text("2- TEMEL TOPRAKLAMA LEVHALARA BAGLANACAKTIR.", dxfattribs={"height": 20, "insert": (nx + 100, 880)})

    # Pafta 4: KAT PLANI (fiziksel saha: 2 adet PRIZ_220, 1 adet ZIL_BTN)
    fx = 8000.0
    msp.add_lwpolyline([(fx, 0), (fx + 2000, 0), (fx + 2000, 1500), (fx, 1500)], close=True)
    msp.add_text("1. KAT KUVVETLI AKIM PLANI", dxfattribs={"height": 30, "insert": (fx + 100, 1380)})
    msp.add_blockref("PRIZ_220", (fx + 400, 500), dxfattribs={"layer": "E-PRIZ"})
    msp.add_blockref("PRIZ_220", (fx + 800, 500), dxfattribs={"layer": "E-PRIZ"})
    msp.add_blockref("ZIL_BTN", (fx + 500, 900), dxfattribs={"layer": "E-ZAYIF"})

    # Pafta 5: KOLON ŞEMASI (KP-1..KP-4 -> ANA, KP-4 kesici/KAKR/kablo eksik, 3(32A), ve 3 adet SAY_SYM)
    kx = 10500.0
    msp.add_lwpolyline([(kx, 0), (kx + 2500, 0), (kx + 2500, 1800), (kx, 1800)], close=True)
    msp.add_text("KOLON SEMASI", dxfattribs={"height": 30, "insert": (kx + 100, 1680)})
    msp.add_text("ANA", dxfattribs={"height": 20, "insert": (kx + 250, 450)})
    msp.add_text("4x63A", dxfattribs={"height": 18, "insert": (kx + 250, 390)})
    msp.add_text("4x16 NYY", dxfattribs={"height": 18, "insert": (kx + 450, 450)})
    msp.add_text("3(32A)", dxfattribs={"height": 18, "insert": (kx + 250, 200)})
    for idx, yy in enumerate((1400, 1200, 1000, 800), start=1):
        pname = f"KP-{idx}"
        msp.add_text(pname, dxfattribs={"height": 20, "insert": (kx + 650, yy)})
        msp.add_text("7200W", dxfattribs={"height": 18, "insert": (kx + 1150, yy + 30)})
        msp.add_text("4300W", dxfattribs={"height": 18, "insert": (kx + 1150, yy - 10)})
        if idx <= 3:
            msp.add_text("C3(25A)", dxfattribs={"height": 18, "insert": (kx + 780, yy + 20)})
            msp.add_text("4x25A 30mA KAK", dxfattribs={"height": 18, "insert": (kx + 880, yy + 20)})
            msp.add_text("5x6NYY/6mm2", dxfattribs={"height": 18, "insert": (kx + 1000, yy + 20)})
            msp.add_blockref("SAY_SYM", (kx + 720, yy), dxfattribs={"layer": "E-SEMBOL"})

    dxf_path = tmp_path / "synthetic_audit_universal.dxf"
    doc.saveas(dxf_path)

    snap, model = build_canonical_model(dxf_path, use_cache=False)
    inv = build_project_inventory(snap, model)

    # 1) Lejant satırları komşularıyla karışmamalı
    leg = model.legend
    assert leg["ZIL_BTN"].description == "Zil Butonu"
    assert leg["SAY_SYM"].description == "Elektrik Sayacı"

    # 2) Notlar paftası DETAY olmalı (TOPRAKLAMA değil)
    roles = {sh.frame_id: sh.role for sh in model.sheets}
    assert sum(1 for r in roles.values() if r == "TOPRAKLAMA") == 1
    assert sum(1 for r in roles.values() if r == "DETAY") == 1

    # 3) Topraklama: yerel lejant çubuğu hariç 2 çubuk, 3 filiz, doğru iletken isimleri ve uyumsuzluk uyarısı
    assert len(model.grounding_loops) == 1
    g = model.grounding_loops[0]
    assert g.rod_block_count == 2
    assert g.spur_count == 3
    assert g.outer_perimeter_m == pytest.approx(40.0, abs=0.2)
    assert g.area_m2 == pytest.approx(96.0, abs=0.5)
    assert g.ring_conductor_spec and "Galvaniz" in g.ring_conductor_spec
    assert g.spur_conductor_spec and "Bakır" in g.spur_conductor_spec

    # 4) Fiziksel saha BOM vs Kolon Şeması sembolleri birbirine karışmaz
    field_bom = {s.block_name: s for s in inv.symbol_bom}
    sch_bom = {s.block_name: s for s in inv.schematic_symbol_bom}
    assert field_bom["TOP_ROD"].total_count == 2  # Lejant örnekleri hariç!
    assert field_bom["PRIZ_220"].total_count == 2
    assert field_bom["ZIL_BTN"].total_count == 1
    assert field_bom["ZIL_BTN"].category == "ZAYIF AKIM"
    assert "SAY_SYM" not in field_bom
    assert sch_bom["SAY_SYM"].total_count == 3
    assert sch_bom["SAY_SYM"].category == "SAYAÇ"

    # 5) 3(32A), KP-1..KP-4 + ANA ve kardeş eksiklik uyarısı
    sw_specs = {x.spec: x.count for x in inv.switchgear_bom}
    assert sw_specs.get("3(32A)") == 1
    by_p = {p.panel_name: p for p in inv.panels}
    assert by_p["KP-1"].breaker_rating == "C3(25A)"
    assert by_p["KP-1"].installed_power_w == pytest.approx(7200.0)
    assert by_p["KP-1"].demand_power_w == pytest.approx(4300.0)
    assert by_p["KP-4"].breaker_rating is None
    assert any("KP-4" in a and "Kesici" in a for a in inv.alerts_summary)
    assert any("3 adet filiz hattı" in a and "2 adet topraklama çubuğu" in a for a in inv.alerts_summary)


def test_step1_ckdtree_clone_superposition_arch_separation(tmp_path: Path):
    """
    Adım 1 Evrensel Kopya Çakıştırma (cKDTree) + 2-Hop Uç Nokta Kablo Takibi Testi:
    Tamamı '0' katmanında çizilmiş, (dX=3500, dY=0) ötelenmiş Kuvvetli Akım ve Zayıf Akım
    paftalarında:
      1) Duvar üstüne priz/soket yerleştirilmiş olsa dahi ortak duvarlar %100 ARCHITECTURAL ayrılır.
      2) Ortak anonim/katmansız blok kopyaları ('A$C1234', layer='0') BELİRSİZ değil ARCHITECTURAL sayılır.
      3) Her paftanın kendi 2-hop elektrik kabloları ('0' katmanı) %100 ELECTRICAL_WIRE olarak korunur.
    """
    import ezdxf

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5  # cm
    msp = doc.modelspace()

    for bname in ("PRIZ_D", "TEL_Z", "A$C1234"):
        blk = doc.blocks.new(name=bname)
        blk.add_circle((0, 0), radius=10.0)

    # Ortak mimari şablon ('0' katmanında duvarlar, pencere çizgileri, kapı yayı ve tefriş A$C1234)
    def _draw_arch_floor(ox: float) -> None:
        # Pafta çerçevesi (25m x 18m)
        msp.add_lwpolyline([(ox, 0), (ox + 2500, 0), (ox + 2500, 1800), (ox, 1800)], close=True)
        # Fiziksel kapı yayı (85 cm)
        _add_door_arc(msp, ox + 250.0, 250.0, 85.0)
        # Farklı uzunluklarda '0' katmanı duvar & bölme çizgileri (cm)
        walls = [
            ((200, 300), (1400, 300)),
            ((1400, 300), (1400, 1100)),
            ((1400, 1100), (200, 1100)),
            ((200, 1100), (200, 420)),
            ((650, 300), (650, 950)),
            ((650, 720), (1180, 720)),
            ((900, 950), (1400, 950)),
        ]
        for p0, p1 in walls:
            msp.add_line((ox + p0[0], p0[1]), (ox + p1[0], p1[1]), dxfattribs={"layer": "0"})
        # Katmansız/anonim kopya tefriş bloğu
        msp.add_blockref("A$C1234", (ox + 1050.0, 500.0), dxfattribs={"layer": "0"})

    # Pafta 1 (x=0): 1. Kat Kuvvetli Akım Planı
    _draw_arch_floor(0.0)
    msp.add_text("1. KAT KUVVETLI AKIM PLANI", dxfattribs={"height": 30, "insert": (150, 1650)})
    # Tam alt duvarın ((200,300)-(1400,300)) üstünde priz -> yine de duvar mimari kalmalı!
    msp.add_blockref("PRIZ_D", (450.0, 300.0), dxfattribs={"layer": "E-PRIZ"})
    # 2-hop elektrik kablosu ('0' katmanı): segment1 (2.5m) + segment2 (3.5m) = 6.0 m
    msp.add_line((450.0, 300.0), (450.0, 550.0), dxfattribs={"layer": "0"})
    msp.add_line((450.0, 550.0), (800.0, 550.0), dxfattribs={"layer": "0"})

    # Pafta 2 (x=3500): 1. Kat Zayıf Akım Planı
    ox2 = 3500.0
    _draw_arch_floor(ox2)
    msp.add_text("1. KAT ZAYIF AKIM PLANI", dxfattribs={"height": 30, "insert": (ox2 + 150, 1650)})
    # Duvar üstünde zayıf akım soketi + 2-hop kablo ('0' katmanı): 3.0m + 4.0m = 7.0 m
    msp.add_blockref("TEL_Z", (ox2 + 1200.0, 1100.0), dxfattribs={"layer": "E-ZAYIF"})
    msp.add_line((ox2 + 1200.0, 1100.0), (ox2 + 1200.0, 800.0), dxfattribs={"layer": "0"})
    msp.add_line((ox2 + 1200.0, 800.0), (ox2 + 1600.0, 800.0), dxfattribs={"layer": "0"})

    dxf_path = tmp_path / "ckdtree_clone_arch_test.dxf"
    doc.saveas(dxf_path)

    snap, model = build_canonical_model(dxf_path, use_cache=False)
    inv = build_project_inventory(snap, model)

    by_disc = {v.discipline: v for v in inv.views}
    assert {"KUVVETLI_AKIM", "ZAYIF_AKIM"}.issubset(by_disc.keys())

    v_pwr = by_disc["KUVVETLI_AKIM"]
    v_weak = by_disc["ZAYIF_AKIM"]

    # Kopya anonim blok 'A$C1234' her iki paftada ARCHITECTURAL ayrılır, UNCERTAIN kalmaz
    assert v_pwr.uncertain_block_count == 0
    assert v_weak.uncertain_block_count == 0
    assert v_pwr.arch_block_count >= 1
    assert v_weak.arch_block_count >= 1

    # Duvar üstüne priz binse bile 7 ortak duvar + 1 kapı yayı >= 8 ARCHITECTURAL çizgi ayrılır
    assert v_pwr.arch_path_count >= 8
    assert v_weak.arch_path_count >= 8

    # Her iki paftada da yalnızca 2-hop elektrik kablosu ELECTRICAL_WIRE olarak korunur
    assert v_pwr.elec_wire_count == 2
    assert v_pwr.elec_wire_length_m == pytest.approx(6.0, abs=0.05)
    assert v_weak.elec_wire_count == 2
    assert v_weak.elec_wire_length_m == pytest.approx(7.0, abs=0.05)


def test_step1_bim_suffix_and_arch_container_classification():
    """BIM görünüm son eki (-1234567-PRZ ...), XREF bind ön eki ve -ARC-/Antet kapsamı anti-overfit testi."""
    from cad_okuma.schema import BBox2D, RawInsert
    from cad_okuma.disiplin_ayirici import classify_insert_role

    bb = BBox2D(minx=0.0, miny=0.0, maxx=500.0, maxy=500.0)

    # 1. E-ELEC-EQPM katmanında "-PRZ ..." görünüm son ekli pano bloğu PRİZ'e değil PANO / TABLO'ya gitmeli
    panel_ins = RawInsert(
        handle="H1",
        block_name="D5020_30_Panelboard_Alpha - 600x800x2000-9123456-PRZ 04 FFL TEKNİK KAT",
        effective_name="D5020_30_Panelboard_Alpha - 600x800x2000-9123456-PRZ 04 FFL TEKNİK KAT",
        layer="E-ELEC-EQPM",
        x=250.0,
        y=250.0,
        bbox=bb,
    )
    rg1, cat1, disc1, _, _ = classify_insert_role(panel_ins, {})
    assert rg1 == "ELECTRICAL"
    assert cat1 == "PANO / TABLO"
    assert disc1 == "KUVVETLI_AKIM"

    # 2. "-ARC-" kapsayıcı içindeki '0' katmanı kapı/mobilya bloğu "-PRZ ..." son eki yüzünden PRİZ olmamalı
    door_ins = RawInsert(
        handle="H2",
        block_name="_Custom_Flush_Gate-8654321-PRZ 01 FFL PERON KATI",
        effective_name="_Custom_Flush_Gate-8654321-PRZ 01 FFL PERON KATI",
        layer="0",
        x=250.0,
        y=250.0,
        bbox=bb,
        parent_chain="LIN-01-M3-ARC-02_rvt-1-PRZ 01 FFL PERON KATI",
    )
    rg2, cat2, disc2, _, _ = classify_insert_role(door_ins, {})
    assert rg2 == "ARCHITECTURAL"
    assert disc2 == "MIMARI"

    # 3. Başlığında "Kuvvetli Akım" geçen antet bloğu KUVVET / TESİSAT'a değil ARCHITECTURAL'a ayrılmalı
    antet_ins = RawInsert(
        handle="H3",
        block_name="Istasyon_Antet_Kuvvetli Akım",
        effective_name="Istasyon_Antet_Kuvvetli Akım",
        layer="0",
        x=250.0,
        y=250.0,
        bbox=bb,
    )
    rg3, _, disc3, _, _ = classify_insert_role(antet_ins, {})
    assert rg3 == "ARCHITECTURAL"
    assert disc3 == "MIMARI"

    # 4. XREF bind ön ekli ("AYDINLATMA-...$0$sym") blok yanlışlıkla AYDINLATMA değil kendi katmanıyla (PRİZ) eşleşmeli
    bind_ins = RawInsert(
        handle="H4",
        block_name="HAT-AYDINLATMA-02$0$sym_out",
        effective_name="HAT-AYDINLATMA-02$0$sym_out",
        layer="PRT-EL-PRZ_N",
        x=250.0,
        y=250.0,
        bbox=bb,
    )
    rg4, cat4, disc4, _, _ = classify_insert_role(bind_ins, {})
    assert rg4 == "ELECTRICAL"
    assert cat4 == "PRİZ"
    assert disc4 == "KUVVETLI_AKIM"


def test_step1_metraj_annotation_wire_filter_1to1_feeder_len_and_load_schedule_xlsx(tmp_path):
    """
    Evrensel metraj iyileştirmeleri (anti-overfit):
    - 00-LINYE_NO / 00-ELKYAZ çizim etiketleri kablo metresini şişirmez; 00-AYD / 00-06 katman bazlı raporlanır
    - Lejant 'P (priz linyesi)' -> 'HAT / LİNYE ETİKETİ' ayrılır
    - Kolon şeması kablo boyları 3.6*H dikey mesafede 1'e 1 eşlenir ve GERILIM_DUSUMU ile çift sayılmaz
    - Sentetik yükleme cetveli (split 16A | C | AOS) ve kesilmemiş grup listesi + .xlsx üretimi doğrulanır
    """
    from cad_okuma.disiplin_ayirici import classify_paths_arch_vs_elec
    from cad_okuma.metraj_cikarici import (
        _category_from_legend_desc,
        _extract_load_schedule_breakers,
        _extract_schematic_bom,
        build_project_inventory,
        format_inventory_markdown,
        save_inventory_reports,
    )
    from cad_okuma.schema import (
        BBox2D,
        CanonicalProjectModel,
        NormalizedTable,
        RawCADSnapshot,
        RawInsert,
        RawPath,
        RawText,
        SheetFrame,
        UnitCalibration,
    )

    assert _category_from_legend_desc("P (priz linyesi)") == "HAT / LİNYE ETİKETİ"
    assert _category_from_legend_desc("Topraklı priz") == "PRİZ"

    bb = BBox2D(minx=0.0, miny=0.0, maxx=5000.0, maxy=4000.0)
    ins_lamp = RawInsert(
        handle="L1",
        block_name="SYM_ARM",
        effective_name="SYM_ARM",
        layer="00-AYD",
        x=100.0,
        y=100.0,
        bbox=BBox2D(minx=90.0, miny=90.0, maxx=110.0, maxy=110.0),
    )
    p_wire = RawPath(handle="W1", dxftype="LINE", layer="00-AYD", points=[(100.0, 100.0), (600.0, 100.0)], length_du=500.0, bbox=bb)
    p_aux = RawPath(handle="W2", dxftype="LINE", layer="00-06", points=[(100.0, 200.0), (300.0, 200.0)], length_du=200.0, bbox=bb)
    p_linye_no = RawPath(handle="N1", dxftype="CIRCLE", layer="00-LINYE_NO", points=[(100.0, 100.0), (120.0, 100.0), (100.0, 120.0)], is_closed=True, is_circle=True, length_du=62.8, bbox=bb)
    p_tick = RawPath(handle="N2", dxftype="LINE", layer="00-ELKYAZ", points=[(100.0, 100.0), (110.0, 110.0)], length_du=14.14, bbox=bb)
    p_callout_blk = RawPath(handle="N3", dxftype="LINE", layer="00-05", points=[(200.0, 200.0), (400.0, 200.0)], length_du=200.0, bbox=bb, parent_chain="A$C9999")

    split = classify_paths_arch_vs_elec(
        [p_wire, p_aux, p_linye_no, p_tick, p_callout_blk],
        [ins_lamp],
        du_to_m=0.01,
    )
    wire_layers = {p.layer for p in split["ELECTRICAL_WIRE"]}
    assert wire_layers == {"00-AYD", "00-06"}

    # Kolon şeması 1'e 1 mesafe testi (h_med=5.0, dy=18.0 -> 3.6*h_med) + GERILIM_DUSUMU çift sayım engeli
    sh_kol = SheetFrame(frame_id="M_01", bbox_du=bb, bbox_m=BBox2D(minx=0, miny=0, maxx=50, maxy=40), role="KOLON_SEMASI", title="KOLON ŞEMASI")
    sh_vd = SheetFrame(frame_id="M_02", bbox_du=bb, bbox_m=BBox2D(minx=0, miny=0, maxx=50, maxy=40), role="GERILIM_DUSUMU", title="GERİLİM DÜŞÜMÜ")
    t_bb = BBox2D(minx=0.0, miny=0.0, maxx=10.0, maxy=10.0)
    t_map = {
        "M_01": [
            RawText(handle="T1", dxftype="TEXT", text="4x10 N2XH", layer="00-ELKYAZ", x=100.0, y=200.0, height=5.0, bbox=t_bb),
            RawText(handle="T2", dxftype="TEXT", text="18m", layer="00-ELKYAZ", x=102.0, y=182.0, height=5.0, bbox=t_bb),
            RawText(handle="T3", dxftype="TEXT", text="4x10 N2XH", layer="00-ELKYAZ", x=250.0, y=200.0, height=5.0, bbox=t_bb),
            RawText(handle="T4", dxftype="TEXT", text="24m", layer="00-ELKYAZ", x=251.0, y=182.0, height=5.0, bbox=t_bb),
        ],
        "M_02": [
            RawText(handle="T5", dxftype="TEXT", text="4x10 N2XH", layer="00-ELKYAZ", x=100.0, y=100.0, height=5.0, bbox=t_bb),
            RawText(handle="T6", dxftype="TEXT", text="99m", layer="00-ELKYAZ", x=102.0, y=82.0, height=5.0, bbox=t_bb),
        ],
    }
    _, _, cables = _extract_schematic_bom([sh_kol, sh_vd], t_map, {"M_01": [], "M_02": []})
    assert len(cables) == 1
    assert cables[0].occurrences == 2
    assert cables[0].explicit_length_m == pytest.approx(42.0, abs=0.01)

    # Sentetik Yükleme Cetveli (split sigorta+eğri hücreleri + topraklama tablosu filtreleme)
    tbl_sched = NormalizedTable(
        table_id="TBL_1",
        sheet_id="M_03",
        source_kind="OLE2_DECODED",
        title="KP-99 KAT PANOSU YÜKLEME CETVELİ",
        raw_matrix=[
            ["LİNYE", "AÇIKLAMA", "GÜÇ (kW)", "SİGORTA", "", "", "KABLO"],
            ["1", "AYDINLATMA", "1,2", "10A", "B", "AOS", "3x1,5 NHXMH"],
            ["2", "PRİZ", "2,4", "16A", "C", "AOS", "3x2,5 NHXMH"],
            ["3", "PRİZ-2", "2,0", "16A", "C", "AOS", "3x2,5 NHXMH"],
            ["TOPLAM", "", "5,6", "", "", "", ""],
        ],
    )
    tbl_ground = NormalizedTable(
        table_id="TBL_2",
        sheet_id="M_04",
        source_kind="OLE2_DECODED",
        title="TEMEL TOPRAKLAMA HESABI",
        raw_matrix=[["L = 40 m", "A = 100 m2", "R = 1.2 ohm"]],
    )
    ls_breakers = _extract_load_schedule_breakers([tbl_sched, tbl_ground])
    assert len(ls_breakers) == 2
    assert {b.panel_name for b in ls_breakers} == {"KP-99"}
    assert sum(b.count for b in ls_breakers) == 3

    # Tam rapor + Excel (.xlsx) çıktısı ve 10 sembol için [:8] kesilmemesi
    sh_plan = SheetFrame(frame_id="M_05", bbox_du=bb, bbox_m=BBox2D(minx=0, miny=0, maxx=50, maxy=40), role="KAT_PLANI", title="NORMAL KAT KUVVETLİ PLANI")
    sym_inserts = [
        RawInsert(
            handle=f"S{i}",
            block_name=f"SYM_{i:02d}",
            effective_name=f"SYM_{i:02d}",
            layer="00-AYD",
            x=100.0 + i * 20.0,
            y=100.0,
            bbox=BBox2D(minx=95.0 + i * 20.0, miny=95.0, maxx=105.0 + i * 20.0, maxy=105.0),
        )
        for i in range(10)
    ]
    snap = RawCADSnapshot(
        filepath="sentetik_metraj.dxf",
        filename="sentetik_metraj.dxf",
        dxf_path="sentetik_metraj.dxf",
        inserts=sym_inserts,
        paths=[p_wire, p_aux],
        texts=[],
    )
    model = CanonicalProjectModel(
        filename="sentetik_metraj.dxf",
        filepath="sentetik_metraj.dxf",
        unit=UnitCalibration(unit_name="cm", du_to_mm=10.0, du_to_m=0.01, confidence=0.95, source="SYNTH"),
        sheets=[sh_plan, sh_kol],
        tables=[tbl_sched],
    )
    inv = build_project_inventory(snap, model)
    md_text = format_inventory_markdown(inv, sheets=model.sheets)
    for i in range(10):
        assert f"SYM_{i:02d}" in md_text
    assert len(inv.load_schedule_breakers) == 2

    docx_p, md_p, json_p = save_inventory_reports(inv, tmp_path, sheets=model.sheets)
    xlsx_p = tmp_path / "sentetik_metraj_metraj.xlsx"
    assert docx_p.exists() and md_p.exists() and json_p.exists() and xlsx_p.exists()


def test_step3_calculation_audit_generalization(tmp_path: Path):
    """
    Adım 3 (Hesap Denetleyici) Evrensellik, Anti-Overfit ve Regresyon Testi:
      1) Tamamen farklı pano isimleri (MDP-GAMMA, KAT-01), farklı talep gücü,
         özgül direnç (rho), oda boyutu ve kesit/kesici değerleriyle sonuçların
         (Ib, %e, Re, k, Z) dinamik olarak değiştiğini ve sabit sayı olmadığını kanıtlar.
      2) Şema sütununda KAKR < Sigorta koordinasyon ihlalinin evrensel yakalandığını
         ve .xlsx/.docx/.md/.json raporlarının üretildiğini doğrular.
      3) Faruk Demir düzenlenmiş DXF mevcutsa ana besleme, antet +20 kW farkı, O-T
         linye %e formül hatası, topraklama Rç/Ry formül hataları ve DT-1/DT-3/DT-4
         kesici kontrollerini uçtan uca doğrular.
    """
    from cad_okuma.schema import (
        BBox2D,
        CanonicalProjectModel,
        FormulaBlock,
        GroundingLoop,
        NormalizedTable,
        PanelInventoryItem,
        ProjectInventory,
        RawCADSnapshot,
        RawText,
        SheetFrame,
        UnitCalibration,
    )

    def _txt(t: str, x: float, y: float, h: float = 10.0) -> RawText:
        return RawText(
            dxftype="TEXT",
            text=t,
            x=x,
            y=y,
            height=h,
            bbox=BBox2D(minx=x, miny=y, maxx=x + len(t) * h * 0.6, maxy=y + h),
        )

    def _run_synth(
        p_dem_main_w: float,
        rho_val: float,
        room_w_m: float,
        room_e_lux: float,
        sub_len_m: float,
        sub_brk_str: str,
        sub_rcd_str: str,
        tag: str,
    ):
        bb_sch = BBox2D(minx=0.0, miny=0.0, maxx=2000.0, maxy=2000.0)
        bb_gnd = BBox2D(minx=3000.0, miny=0.0, maxx=5000.0, maxy=2000.0)
        bb_vd = BBox2D(minx=6000.0, miny=0.0, maxx=8000.0, maxy=2000.0)

        texts = [
            _txt("MDP-GAMMA", 500.0, 500.0),
            _txt(f"{int(round(p_dem_main_w))}W", 620.0, 500.0),
            _txt("0,50", 620.0, 480.0),
            _txt("3x160A TMS", 450.0, 520.0),
            _txt("4x160A 300mA KAKR", 450.0, 470.0),
            _txt("3x50+25N2XH", 520.0, 460.0),
            _txt("30m", 520.0, 440.0),
            # Alt kol: pano ve KAKR/sigorta sütunu
            _txt("KAT-01", 900.0, 500.0),
            _txt(sub_brk_str, 900.0, 620.0),
            _txt("4x25A", 900.0, 560.0),
            _txt("30mA", 900.0, 570.0),
            _txt("KAK", 900.0, 550.0),
            _txt("ASANSOR MOTOR", 900.0, 720.0),
        ]

        snap = RawCADSnapshot(
            filepath=f"sentetik_{tag}.dxf",
            filename=f"sentetik_{tag}.dxf",
            dxf_path=f"sentetik_{tag}.dxf",
            texts=texts,
        )

        sheets = [
            SheetFrame(frame_id="S_01", bbox_du=bb_sch, bbox_m=bb_sch, role="KOLON_SEMASI"),
            SheetFrame(frame_id="S_02", bbox_du=bb_gnd, bbox_m=bb_gnd, role="TOPRAKLAMA"),
            SheetFrame(frame_id="S_03", bbox_du=bb_vd, bbox_m=bb_vd, role="GERILIM_DUSUMU"),
        ]

        gnd_tbl = NormalizedTable(
            table_id="TBL_GND",
            sheet_id="S_02",
            source_kind="OLE2_DECODED",
            bbox_du=bb_gnd,
            raw_matrix=[
                ["GOMULU ILETKEN TOPRAKLAMA", ""],
                ["L=", "80", "a=", "10", "b=", "25"],
                ["A=", "E", "250", "H=", "1"],
                ["ρe=", str(int(rho_val))],
                ["2) GOMULU CUBUK", "n=", "4", "L=", "1.5", "d=", "0.02"],
                ["Rc=", "16.0", "Ry=", "4.10", "Re=", "3.30"],
            ],
        )
        light_tbl = NormalizedTable(
            table_id="TBL_LGT",
            sheet_id="S_02",
            source_kind="OLE2_DECODED",
            bbox_du=bb_gnd,
            raw_matrix=[
                ["AYDINLATMA HESABI", "OFIS-A", "OFIS-B"],
                ["MAHAL ENI (a) m", f"{room_w_m:.1f}", "4.0"],
                ["MAHAL BOYU (b) m", "10.0", "4.0"],
                ["MAHAL YUKSEKLIGI (H) m", "3.0", "3.0"],
                ["ARMATUR YUKSEKLIGI (hm) m", "2.15", "2.15"],
                ["ISTENILEN AYDINLIK SIDDETI (E) Lux", f"{room_e_lux:.0f}", "150"],
                ["YANSITMA FAKTORLERI", "80-50-30", "80-50-30"],
                ["MAHAL VERIMI (n)", "0,55", "0,40"],
                ["ARMATUR GUCU (W)", "36", "36"],
                ["ISIK AKISI (lm)", "2800", "2800"],
                ["KULLANILACAK ARMATUR", "P 4x36 W", "P 2x36 W"],
            ],
        )
        sched_tbl = NormalizedTable(
            table_id="TBL_LOAD",
            sheet_id="S_01",
            source_kind="OLE2_DECODED",
            bbox_du=bb_sch,
            raw_matrix=[
                ["PANO ADI", "KAT-01", "YUKLEME CETVELI", ""],
                ["LINYE", "SIGORTA", "ACIKLAMA", "SORTI", "GUC (W)", "KABLO"],
                ["A1", "AOS 10 3 kA B", "Aydinlatma", "5", "400", "3x2,5NHXMH"],
                ["P1", "AOS 16 3 kA C", "Priz", "4", "1200", "3x2,5NHXMH"],
                ["TOPLAM", "5", "4", "0", "400", "1200", "0", "0", "1600"],
            ],
        )
        thm_tbl = NormalizedTable(
            table_id="TBL_THM",
            sheet_id="S_03",
            source_kind="OLE2_DECODED",
            bbox_du=bb_vd,
            raw_matrix=[
                ["TABLO", "KURULU GÜÇ (W)", "KAT-01", "25000", "Metraj", str(int(sub_len_m)), "LİNYE NO", "1.KOL", "P1"],
                ["DİVERSİTELİ GÜÇ (W)", "15000", "KESİT (mm2)", "MESAFE (m)", "2,5", "10"],
                ["HAT AKIMI (A)", "28,5", "4x6N2XH", "Cosφ", "0,80", "2500"],
                ["KABLO AKIM TAŞIMA", "KAPASİTESİ (A)", "52", "GERİLİM DÜŞÜMÜ", "0,25"],
                ["0,60", "<1,5"],
            ],
        )
        vd_main_val = round((100.0 * 30.0 * p_dem_main_w) / (56.0 * 50.0 * (380.0 ** 2)), 2)
        vd_sub_val = round((100.0 * sub_len_m * 15000.0) / (56.0 * 6.0 * (380.0 ** 2)), 2)
        formulas = [
            FormulaBlock(
                formula_id="FRM_M1",
                sheet_id="S_03",
                formula_kind="VOLTAGE_DROP",
                parse_status="OK",
                label="Ana Besleme",
                numerator_texts=[f"30 x {p_dem_main_w / 1000.0:.3f}"],
                denominator_texts=["50"],
                coefficient_texts=["0,0124"],
                result_texts=[f"%{vd_main_val:.2f}"],
                parsed_result_value=vd_main_val,
                bbox_du=bb_vd,
            ),
            FormulaBlock(
                formula_id="FRM_K1",
                sheet_id="S_03",
                formula_kind="VOLTAGE_DROP",
                parse_status="OK",
                label="Kolon Hatti",
                numerator_texts=[f"{int(round(sub_len_m))} x 15.000"],
                denominator_texts=["6"],
                coefficient_texts=["0,0124"],
                result_texts=[f"%{vd_sub_val:.2f}"],
                parsed_result_value=vd_sub_val,
                bbox_du=bb_vd,
            ),
        ]

        model = CanonicalProjectModel(
            filename=f"sentetik_{tag}.dxf",
            filepath=f"sentetik_{tag}.dxf",
            unit=UnitCalibration(unit_name="cm", du_to_mm=10.0, du_to_m=0.01, confidence=0.99, source="SYNTH"),
            sheets=sheets,
            tables=[gnd_tbl, light_tbl, sched_tbl, thm_tbl],
            formula_blocks=formulas,
            grounding_loops=[
                GroundingLoop(
                    loop_id="GND_S",
                    sheet_id="S_02",
                    outer_perimeter_m=70.0,
                    area_m2=250.0,
                    equivalent_diameter_m=17.84,
                    inner_conductors_m=10.0,
                    ring_plus_inner_m=80.0,
                    spur_total_m=4.0,
                    rod_block_count=4,
                )
            ],
        )
        inv = ProjectInventory(
            filename=f"sentetik_{tag}.dxf",
            unit_name="cm",
            sheet_count=len(sheets),
            panels=[
                PanelInventoryItem(
                    panel_name="MDP-GAMMA",
                    role="ANA_PANO",
                    sheet_ids=["S_01"],
                    installed_power_w=p_dem_main_w * 2.0,
                    demand_power_w=p_dem_main_w,
                ),
                PanelInventoryItem(
                    panel_name="KAT-01",
                    role="TALI_PANO",
                    parent_panel="MDP-GAMMA",
                    sheet_ids=["S_01"],
                    breaker_rating=sub_brk_str,
                    rcd_rating=sub_rcd_str,
                    feeder_cable="4x6N2XH",
                    installed_power_w=25000.0,
                    demand_power_w=15000.0,
                ),
            ],
        )
        return build_calculation_audit_report(snap, model, inv)

    r1 = _run_synth(60000.0, 80.0, 6.0, 300.0, 20.0, "3(32A)", "4x25A 30mA", "c1")
    r2 = _run_synth(110000.0, 160.0, 12.0, 250.0, 45.0, "3(25A)", "4x40A 30mA", "c2")

    assert r1.power_budget.main_panel_name == "MDP-GAMMA"
    assert r2.main_incomer.engine_ib_400v_a > r1.main_incomer.engine_ib_400v_a
    assert r1.grounding is not None and r2.grounding is not None
    assert r2.grounding.engine_cad_R_schwarz_ohm == pytest.approx(
        r1.grounding.engine_cad_R_schwarz_ohm * 2.0, rel=1e-2
    )
    assert r2.lighting_rooms[0].calc_k > r1.lighting_rooms[0].calc_k
    assert r2.lighting_rooms[0].calc_z_exact > r1.lighting_rooms[0].calc_z_exact
    assert r2.panel_rows[0].engine_vd_kolon_proj_pct > r1.panel_rows[0].engine_vd_kolon_proj_pct
    assert r1.load_schedules and r1.load_schedules[0].circuits[0].breaker_amp_a == 10.0
    assert any(f.category == "KAKR Akım Koordinasyonu" and f.severity == "KRITIK" for f in r1.findings)
    assert not any(f.category == "KAKR Akım Koordinasyonu" for f in r2.findings)

    out_paths = save_calculation_audit_reports(r1, tmp_path / "audit_out", base_name="sentetik_audit")
    assert all(p.exists() and p.stat().st_size > 0 for p in out_paths.values())
    assert "MDP-GAMMA" in format_calculation_audit_markdown(r1)

    # Faruk Demir tam proje regresyon testi (mevcutsa)
    fd_dxf = Path("04_cikti/3_duzenlenmis_elektrik/faruk_demir_3_birlesik_tam_proje_duzenlenmis.dxf")
    if fd_dxf.exists():
        snap_fd, model_fd = build_canonical_model(fd_dxf, use_cache=True)
        inv_fd = build_project_inventory(snap_fd, model_fd)
        rep_fd = build_calculation_audit_report(snap_fd, model_fd, inv_fd)
        assert rep_fd.power_budget.subpanel_count == 57
        assert rep_fd.power_budget.subpanels_installed_sum_w == pytest.approx(533490.0)
        assert rep_fd.power_budget.titleblock_installed_w == pytest.approx(553490.0)
        assert rep_fd.power_budget.installed_diff_titleblock_w == pytest.approx(20000.0)
        assert rep_fd.main_incomer.breaker_in_a == 320.0
        assert rep_fd.main_incomer.ib_in_iz_ok is False
        assert rep_fd.main_incomer.pe_ok is False
        assert rep_fd.main_incomer.min_compliant_section_mm2 == 120.0
        assert len(rep_fd.load_schedules) == 2
        by_p = {p.panel_name: p for p in rep_fd.panel_rows}
        assert by_p["DT-1"].breaker_in_a == 20.0
        assert by_p["DT-3"].breaker_in_a is None
        assert by_p["DT-4"].breaker_in_a is None
        assert by_p["O-T"].project_iz_a == 54.0 and by_p["O-T"].engine_iz_yaml_a == 76.0
        assert by_p["O-T"].project_vd_linye_pct == pytest.approx(0.694, abs=0.01)
        assert by_p["O-T"].engine_vd_linye_proj_pct == pytest.approx(0.116, abs=0.01)
        assert rep_fd.grounding is not None
        assert rep_fd.grounding.table_A_m2 == pytest.approx(336.0)
        assert rep_fd.grounding.engine_tbl_R_temel_ohm == pytest.approx(3.37, abs=0.05)
        assert rep_fd.grounding.engine_tbl_R_rods_dwight_ohm == pytest.approx(18.91, abs=0.25)
        assert rep_fd.grounding.engine_cad_R_schwarz_ohm == pytest.approx(3.16, abs=0.1)
        assert len(rep_fd.grounding.formula_anomalies) >= 2
        assert any(f.category == "KAKR Akım Koordinasyonu" and f.severity == "KRITIK" for f in rep_fd.findings)
        assert all(
            (f.bbox_du is not None or f.anchor_xy is not None or f.extra_anchors)
            for f in rep_fd.findings
        )


def test_step4_redline_annotation_and_dwg_conversion(tmp_path: Path):
    """
    Adım 4 (_DENETIM_BULGULARI redline + AutoCAD .dwg dönüşümü) evrensel ve aykırı nokta korumalı testi:
    1) Sentetik 'mm' ve 'm' birimlerinde, orijinal varlıklara dokunulmadan sadece '_DENETIM_BULGULARI'
       katmanında bulut + etiket + özet kutusu oluşturulduğunu ve uzak aykırı noktanın kutuyu
       uzaya fırlatmadığını doğrular.
    2) Sistemde accoreconsole.exe mevcutsa sentetik DXF -> DWG dönüşümünü gerçekten doğrular.
    """
    import ezdxf
    from cad_okuma.denetim_isaretleyici import (
        DEFAULT_AUDIT_LAYER,
        annotate_dxf_with_audit_findings,
        convert_dxf_to_dwg,
    )
    from cad_okuma.hesap_denetleyici import AuditFindingItem, CalculationAuditReport

    for unit_name, scale in (("m", 1.0), ("mm", 1000.0)):
        src_dxf = tmp_path / f"synth_{unit_name}.dxf"
        dst_dxf = tmp_path / f"synth_{unit_name}_bulgulu.dxf"

        doc = ezdxf.new("R2018")
        msp = doc.modelspace()
        # Normal pafta içeriği (~0..20m)
        for idx in range(6):
            msp.add_line((idx * 3.0 * scale, 0.0), (idx * 3.0 * scale, 10.0 * scale), dxfattribs={"layer": "ELEKTRIK"})
            msp.add_text(f"PANO-{idx+1}", dxfattribs={"layer": "ELEKTRIK", "height": 0.15 * scale, "insert": (idx * 3.0 * scale + 0.5 * scale, 5.0 * scale)})
        # Çizim dışındaki uzak aykırı nokta (özet kutusu buraya sürüklenmemeli)
        msp.add_line((1_000_000.0, 1_000_000.0), (1_000_001.0, 1_000_001.0), dxfattribs={"layer": "0"})
        doc.saveas(str(src_dxf))
        orig_count = len(msp)

        rep = CalculationAuditReport(
            filename=src_dxf.name,
            unit_name=unit_name,
            summary_counts={"KRITIK": 1, "UYARI": 1, "BILGI": 0, "UYGUN": 0, "toplam_bulgu": 2},
            findings=[
                AuditFindingItem(
                    finding_id="H-01",
                    severity="KRITIK",
                    category="KAKR Akım Koordinasyonu",
                    location="PANO-1",
                    project_value="25A < 32A",
                    engine_value="KAKR >= 32A",
                    standard_ref="TS HD 60364-5-53",
                    description="Sentetik kritik bulgu testi.",
                    recommendation="40A KAKR secilmelidir.",
                    bbox_du=(0.5 * scale, 4.0 * scale, 2.0 * scale, 6.0 * scale),
                ),
                AuditFindingItem(
                    finding_id="H-02",
                    severity="UYARI",
                    category="Aydınlatma Hesabı",
                    location="MAHAL-A",
                    project_value="E=50 lx",
                    engine_value="E>=100 lx",
                    standard_ref="TS EN 12464-1",
                    description="Sentetik uyarı testi.",
                    bbox_du=(3.5 * scale, 4.0 * scale, 5.5 * scale, 6.0 * scale),
                ),
            ],
        )

        res = annotate_dxf_with_audit_findings(src_dxf, dst_dxf, rep)
        assert dst_dxf.exists()
        assert res.findings_considered == 2
        assert res.clouds_drawn == 2
        assert res.unanchored_finding_ids == []
        assert res.summary_box_placed is True

        out_doc = ezdxf.readfile(str(dst_dxf))
        out_msp = out_doc.modelspace()
        non_audit = [e for e in out_msp if e.dxf.layer != DEFAULT_AUDIT_LAYER]
        audit_ents = [e for e in out_msp if e.dxf.layer == DEFAULT_AUDIT_LAYER]
        # Orijinal çizim entity sayısı birebir korunur
        assert len(non_audit) == orig_count
        # Tüm bulut, rozet, kart ve özet varlıkları tek katmanda toplanır
        assert len(audit_ents) >= 10
        summary_mtexts = [e for e in audit_ents if e.dxftype() == "MTEXT" and "ÖZETİ" in e.plain_text()]
        assert len(summary_mtexts) == 1
        sx, sy, _ = summary_mtexts[0].dxf.insert
        assert abs(sx) < 50.0 * scale and abs(sy) < 500.0 * scale

    # AutoCAD Core Console mevcutsa gerçek DWG dönüşümünü test et
    from common.dxf_converter import find_acad_core_console
    if find_acad_core_console() is not None:
        dwg_out = tmp_path / "synth_m_bulgulu.dwg"
        dwg_res = convert_dxf_to_dwg(tmp_path / "synth_m_bulgulu.dxf", dwg_out, timeout=120)
        assert dwg_res.success is True, dwg_res.error
        assert dwg_out.exists() and dwg_out.stat().st_size > 10_000
        # Faruk Demir çıktıları mevcutsa DWG ve DXF kontrolleri
        fd_ann_dwg = Path("04_cikti/5_hesap_kontrol/faruk_demir_denetim_bulgulu.dwg")
        fd_clean_dwg = Path("04_cikti/3_duzenlenmis_elektrik/faruk_demir_3_birlesik_tam_proje_duzenlenmis.dwg")
        if fd_ann_dwg.exists():
            assert fd_ann_dwg.stat().st_size > 100_000
        if fd_clean_dwg.exists():
            assert fd_clean_dwg.stat().st_size > 100_000


def test_step3_vd_segment_1to1_and_small_building_main_incomer_anti_overfit():
    """
    Evrensellik testi:
    1. Üstteki FEEDER_SEGMENT etiketleri sağa/sola kaymış olsa bile VOLTAGE_DROP formülleri
       linear_sum_assignment ile uzunluk/kesit/sıra uyumlu 1'e 1 eşleşmeli.
    2. Küçük yapılarda (10 mm² ana kablo, 3(25A) AOS ana kesici, YKR 300mA) ve anma akımı
       yazısız 300mA ana KAKR yanında alt 30mA KAKR'lar varken ana pano yanlış `KRİTİK İHLAL`
       veya `30mA` almamalı; veri eksikse dürüstçe `BELİRSİZ` raporlamalı.
    """
    from cad_okuma.hesap_denetleyici import (
        _audit_voltage_drop_formulas,
        _extract_main_incomer_from_schematic,
        _load_bina_rules,
        format_calculation_audit_markdown,
        CalculationAuditReport,
        MainIncomerAudit,
        PowerBudgetAudit,
    )
    from cad_okuma.schema import (
        BBox2D,
        CanonicalProjectModel,
        FormulaBlock,
        PanelInventoryItem,
        ProjectInventory,
        RawCADSnapshot,
        RawText,
        SheetFrame,
        UnitCalibration,
    )

    rules = _load_bina_rules()

    # 1. Sağa kayık FEEDER_SEGMENT vs VOLTAGE_DROP 1-e-1 eşleme
    sh_gd = SheetFrame(
        frame_id="M_GD",
        title="GERİLİM DÜŞÜMÜ HESABI",
        role="DIGER",
        bbox_du=BBox2D(minx=0, miny=0, maxx=1000, maxy=500),
        bbox_m=BBox2D(minx=0, miny=0, maxx=10, maxy=5),
    )
    vd1 = FormulaBlock(
        formula_id="FRM_1",
        sheet_id="M_GD",
        formula_kind="VOLTAGE_DROP",
        numerator_texts=["40 x 8,400"],
        denominator_texts=["16"],
        coefficient_texts=["0,0124 x"],
        result_texts=["%e =", "0,26"],
        parsed_result_value=0.26,
        parse_status="OK",
        bbox_du=BBox2D(minx=200, miny=100, maxx=400, maxy=150),  # cx=300
    )
    vd2 = FormulaBlock(
        formula_id="FRM_2",
        sheet_id="M_GD",
        formula_kind="VOLTAGE_DROP",
        numerator_texts=["8 x 2,200"],
        denominator_texts=["2,5"],
        coefficient_texts=["0,074 x"],
        result_texts=["%e =", "0,52"],
        parsed_result_value=0.52,
        parse_status="OK",
        bbox_du=BBox2D(minx=500, miny=100, maxx=700, maxy=150),  # cx=600
    )
    # Bilerek seg1 (cx=80) ve seg2 (cx=440 -> vd1'e mesafe 140 < 220): eski kod vd1'i seg2 ile eşlerdi!
    seg1 = FormulaBlock(
        formula_id="SEG_1",
        sheet_id="M_GD",
        formula_kind="FEEDER_SEGMENT",
        numerator_texts=["4x16NYY"],
        denominator_texts=["40m"],
        result_texts=["40m"],
        parsed_result_value=40.0,
        parse_status="OK",
        bbox_du=BBox2D(minx=20, miny=250, maxx=140, maxy=300),  # cx=80
    )
    seg2 = FormulaBlock(
        formula_id="SEG_2",
        sheet_id="M_GD",
        formula_kind="FEEDER_SEGMENT",
        numerator_texts=["3x2,5NHXMH"],
        denominator_texts=["8m"],
        result_texts=["8m"],
        parsed_result_value=8.0,
        parse_status="OK",
        bbox_du=BBox2D(minx=380, miny=250, maxx=500, maxy=300),  # cx=440
    )
    u_cm = UnitCalibration(unit_name="cm", du_to_mm=10.0, du_to_m=0.01, confidence=1.0, source="test")
    m_vd = CanonicalProjectModel(
        filepath="synth_vd.dxf",
        filename="synth_vd.dxf",
        unit=u_cm,
        sheets=[sh_gd],
        formula_blocks=[vd1, vd2, seg1, seg2],
    )
    vd_rows, _, _, _ = _audit_voltage_drop_formulas(m_vd)
    assert len(vd_rows) == 2
    assert vd_rows[0].cable_spec == "4x16NYY"
    assert vd_rows[1].cable_spec == "3x2,5NHXMH"

    # 2. Küçük bina ana besleme: 10 mm² kablo + 3(25A) AOS + 4x25A 300mA YKR + 3x10(30A) sayaç hariç
    sh_kol = SheetFrame(
        frame_id="M_KOL",
        title="KUVVETLİ AKIM KOLON DAĞITIM ŞEMASI",
        role="KOLON_SEMASI",
        bbox_du=BBox2D(minx=0, miny=0, maxx=2000, maxy=1500),
        bbox_m=BBox2D(minx=0, miny=0, maxx=20, maxy=15),
    )
    texts_small = [
        RawText(handle="T1", dxftype="TEXT", text="MDP", x=300, y=500, height=20, bbox=BBox2D(minx=290, miny=490, maxx=340, maxy=510)),
        RawText(handle="T2", dxftype="TEXT", text="6800W", x=420, y=470, height=18, bbox=BBox2D(minx=410, miny=460, maxx=490, maxy=480)),
        RawText(handle="T3", dxftype="TEXT", text="4x25A", x=700, y=400, height=18, bbox=BBox2D(minx=690, miny=390, maxx=760, maxy=410)),
        RawText(handle="T4", dxftype="TEXT", text="300mA", x=700, y=425, height=18, bbox=BBox2D(minx=690, miny=415, maxx=760, maxy=435)),
        RawText(handle="T5", dxftype="TEXT", text="YKR", x=700, y=380, height=18, bbox=BBox2D(minx=690, miny=370, maxx=740, maxy=390)),
        RawText(handle="T6", dxftype="TEXT", text="3(25A)", x=860, y=400, height=18, bbox=BBox2D(minx=850, miny=390, maxx=920, maxy=410)),
        RawText(handle="T7", dxftype="TEXT", text="AOS", x=860, y=370, height=18, bbox=BBox2D(minx=850, miny=360, maxx=900, maxy=380)),
        RawText(handle="T8", dxftype="TEXT", text="4x10NYY", x=1120, y=360, height=18, bbox=BBox2D(minx=1110, miny=350, maxx=1200, maxy=370)),
        RawText(handle="T9", dxftype="TEXT", text="45m", x=1120, y=330, height=18, bbox=BBox2D(minx=1110, miny=320, maxx=1160, maxy=340)),
        # Sayaç & tali pano 30mA alt kesiciler karışmamalı
        RawText(handle="T10", dxftype="TEXT", text="3x10(30A)", x=820, y=620, height=18, bbox=BBox2D(minx=810, miny=610, maxx=900, maxy=630)),
        RawText(handle="T11", dxftype="TEXT", text="4x25A", x=400, y=800, height=18, bbox=BBox2D(minx=390, miny=790, maxx=460, maxy=810)),
        RawText(handle="T12", dxftype="TEXT", text="30mA", x=400, y=825, height=18, bbox=BBox2D(minx=390, miny=815, maxx=450, maxy=835)),
        RawText(handle="T13", dxftype="TEXT", text="KAK", x=400, y=780, height=18, bbox=BBox2D(minx=390, miny=770, maxx=440, maxy=790)),
    ]
    snap_small = RawCADSnapshot(filepath="small.dxf", filename="small.dxf", dxf_path="small.dxf", texts=texts_small)
    inv_small = ProjectInventory(
        filename="small.dxf",
        unit_name="cm",
        sheet_count=1,
        panels=[
            PanelInventoryItem(panel_name="MDP", role="ANA_PANO", installed_power_w=12000.0, demand_power_w=6800.0, sheet_ids=["M_KOL"]),
            PanelInventoryItem(panel_name="SUB-1", role="TALI_PANO", parent_panel="MDP", sheet_ids=["M_KOL"]),
        ],
    )
    m_small = CanonicalProjectModel(
        filepath="small.dxf",
        filename="small.dxf",
        unit=u_cm,
        sheets=[sh_kol],
    )
    mi_small, _, _, _ = _extract_main_incomer_from_schematic(snap_small, m_small, inv_small, rules)
    assert mi_small.cable_spec == "4x10NYY"
    assert mi_small.length_m == pytest.approx(45.0)
    assert mi_small.breaker_in_a == pytest.approx(25.0)
    assert mi_small.rcd_ma == pytest.approx(300.0)
    assert mi_small.engine_iz_yaml_a == pytest.approx(57.0)
    assert mi_small.ib_in_iz_ok is True

    # 3. ib_in_iz_ok=None (kesici verisi eksik) iken sahte KRİTİK İHLAL yerine BELİRSİZ yazılmalı
    rep_none = CalculationAuditReport(
        filename="missing_brk.dxf",
        unit_name="cm",
        power_budget=PowerBudgetAudit(),
        main_incomer=MainIncomerAudit(panel_name="AT", ib_in_iz_ok=None),
    )
    md_none = format_calculation_audit_markdown(rep_none)
    assert "BELİRSİZ (Veri Eksik)" in md_none
    assert "KRİTİK İHLAL" not in md_none








