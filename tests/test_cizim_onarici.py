# -*- coding: utf-8 -*-
"""
Evrensel Çizim, Katman ve Topoloji Onarıcı (`cizim_onarici.py`) Anti-Overfit Testleri
=====================================================================================
GEMINI.md Bölüm 4.1 gereğince mevcut örnek projeden tamamen bağımsız,
sentetik blok isimleri, farklı çizim birimleri (mm / cm) ve iki farklı
katman geleneği (`00-*` ve `E-*`) üzerinde doğrulama yapar.
"""

from __future__ import annotations

from pathlib import Path
import sys

import ezdxf
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
MOTOR_ROOT = ROOT_DIR / "03_hesap_motoru"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from cad_okuma.cizim_onarici import (  # noqa: E402
    consolidate_architecture_to_single_layer,
    merge_arch_and_elec_dxf,
    rehabilitate_electrical_dxf,
)
from cad_okuma.kalip_olusturucu import build_canonical_model  # noqa: E402


@pytest.mark.parametrize("unit_name,scale,insunits", [("mm", 1.0, 4), ("cm", 0.1, 5)])
def test_consolidate_architecture_single_layer_and_dedup(
    unit_name: str, scale: float, insunits: int
) -> None:
    """
    Mimari DXF'teki tüm varlıkları ve blok içi alt elemanları tek `MIMARI`
    katmanına toplar; mükerrer INSERT/LINE ve < 1 mm sıfır boy LINE silinir.
    """
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = insunits
    for lay in ("M-DUVAR", "M-KOLON", "M-KAPI", "BOS_KATMAN", "BLK_IC_KATMAN"):
        doc.layers.add(lay)

    # Blok tanımla ve blok içine farklı katmanda alt varlık koy
    blk = doc.blocks.new("SYN_ARCH_DOOR")
    blk.add_line((0, 0), (900 * scale, 0), dxfattribs={"layer": "BLK_IC_KATMAN"})
    blk.add_arc((0, 0), radius=900 * scale, start_angle=0, end_angle=90, dxfattribs={"layer": "M-KAPI"})

    msp = doc.modelspace()
    # 1 adet normal + 1 adet mükerrer INSERT
    msp.add_blockref("SYN_ARCH_DOOR", (1000 * scale, 1000 * scale), dxfattribs={"layer": "M-KAPI"})
    msp.add_blockref("SYN_ARCH_DOOR", (1000 * scale, 1000 * scale), dxfattribs={"layer": "M-KAPI"})

    # 1 normal duvar LINE + 1 ters yönlü mükerrer LINE + 1 mikro (< 1 mm) LINE
    msp.add_line((0, 0), (5000 * scale, 0), dxfattribs={"layer": "M-DUVAR"})
    msp.add_line((5000 * scale, 0), (0, 0), dxfattribs={"layer": "M-KOLON"})
    msp.add_line((200 * scale, 200 * scale), (200.2 * scale, 200.1 * scale), dxfattribs={"layer": "M-DUVAR"})

    stats = consolidate_architecture_to_single_layer(
        doc,
        target_layer="MIMARI",
        color=8,
        lineweight=9,
        purge_unused_layers=True,
    )

    assert stats["deleted_duplicate_inserts"] == 1
    assert stats["deleted_duplicate_lines"] == 1
    assert stats["deleted_zero_length_lines"] == 1
    assert stats["remaining_msp_entities"] == 2  # 1 INSERT + 1 LINE

    for ent in doc.modelspace():
        assert ent.dxf.layer == "MIMARI"
        assert ent.dxf.color == 256
        assert ent.dxf.lineweight == -1

    for sub in doc.blocks.get("SYN_ARCH_DOOR"):
        if sub.dxftype() not in ("BLOCK", "ENDBLK"):
            assert sub.dxf.layer == "MIMARI"

    lay_obj = doc.layers.get("MIMARI")
    assert lay_obj.color == 8
    assert lay_obj.dxf.lineweight == 9
    assert not lay_obj.is_locked()

    remaining_layer_names = {lay.dxf.name for lay in doc.layers}
    assert "BOS_KATMAN" not in remaining_layer_names
    assert "M-DUVAR" not in remaining_layer_names
    assert "BLK_IC_KATMAN" not in remaining_layer_names


@pytest.mark.parametrize(
    "convention,seed_layers,exp_light,exp_sw,exp_fire,exp_panel,exp_text",
    [
        (
            "00",
            ("00-AYD", "00-ANHTR", "00-YANGIN", "00-TABLO", "00-ELKYAZ", "00-TOPRAK", "00-PRZ", "00-24V", "00-CERCEVE", "00-YAZI"),
            "00-AYD",
            "00-ANHTR",
            "00-YANGIN",
            "00-TABLO",
            "00-ELKYAZ",
        ),
        (
            "E",
            ("E-LITE", "E-SWITCH", "E-YANGIN", "E-PANO", "E-ETIKET", "E-GRND", "E-PRIZ", "E-ZAYIF", "00-CERCEVE", "00-YAZI"),
            "E-LITE",
            "E-SWITCH",
            "E-YANGIN",
            "E-PANO",
            "E-ETIKET",
        ),
    ],
)
def test_rehabilitate_electrical_relocation_and_wire_heal(
    tmp_path: Path,
    convention: str,
    seed_layers: tuple[str, ...],
    exp_light: str,
    exp_sw: str,
    exp_fire: str,
    exp_panel: str,
    exp_text: str,
) -> None:
    """
    Yanlış katmana düşmüş armatür, anahtar, yangın dedektörü, pano detayı ve yazıları
    projenin kendi katman düzenine (`00-*` veya `E-*`) taşır; buatları devre
    katmanında korur ve kopuk/mükerrer kablo uçlarını onarır.
    """
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 5  # cm: 1 DU = 1 cm = 0.01 m
    for ln in seed_layers + ("CIRCUIT_AYD", "CIRCUIT_LBL"):
        if ln not in doc.layers:
            doc.layers.add(ln)

    # Sentetik bloklar (örnek projeyle sıfır ortak isim)
    for bname, rad in (("SYN_L_X", 15.0), ("SYN_S_Y", 12.0), ("SYN_B_W", 8.0), ("SYN_ETB", 10.0), ("SYN_L_LBL", 8.0)):
        b = doc.blocks.new(bname)
        b.add_circle((0, 0), radius=rad, dxfattribs={"layer": "0"})

    # Yangın dedektörü bloğunun iç geometrisi 00-ELKYAZ katmanında olsun (Rule 1b regresyonu)
    if "00-ELKYAZ" not in doc.layers:
        doc.layers.add("00-ELKYAZ")
    fire_blk = doc.blocks.new("SYN_F_Z")
    fire_blk.add_circle((0, 0), radius=12.0, dxfattribs={"layer": "00-ELKYAZ"})

    panel_blk = doc.blocks.new("SYN_PANO_DETAY")
    panel_blk.add_lwpolyline([(0, 0), (120, 0), (120, 80), (0, 80)], close=True, dxfattribs={"layer": exp_panel})

    msp = doc.modelspace()

    # Lejant kutusu (sol üst bölgede, 1m = 100 DU)
    msp.add_lwpolyline([(0, 1800), (1600, 1800), (1600, 3400), (0, 3400)], close=True, dxfattribs={"layer": "00-CERCEVE"})
    msp.add_text("LEJANT", dxfattribs={"height": 30, "insert": (100, 3250), "layer": "00-YAZI"})

    legend_entries = [
        ("SYN_L_X", "TAVAN LED ARMATUR", 3000),
        ("SYN_S_Y", "ADİ ANAHTAR", 2800),
        ("SYN_F_Z", "OPTIK DUMAN DEDEKTORU", 2600),
        ("SYN_B_W", "BUAT", 2400),
        ("SYN_ETB", "Eşpotansiyel Topraklama Barası (E.T.B)", 2200),
        ("SYN_L_LBL", "P (priz linyesi)", 2000),
    ]
    for bname, desc, yy in legend_entries:
        msp.add_blockref(bname, (150, yy), dxfattribs={"layer": "0"})
        msp.add_text(desc, dxfattribs={"height": 18, "insert": (280, yy - 8), "layer": "00-YAZI"})

    # Kat planında yanlış katmanlara yerleştirilmiş semboller
    light_ref = msp.add_blockref("SYN_L_X", (1000, 500), dxfattribs={"layer": seed_layers[5]})   # TOPRAK/GRND katmanında yanlış
    sw_ref = msp.add_blockref("SYN_S_Y", (600, 500), dxfattribs={"layer": seed_layers[6]})      # PRZ/PRIZ katmanında yanlış
    fire_ref = msp.add_blockref("SYN_F_Z", (1400, 500), dxfattribs={"layer": seed_layers[7]})   # 24V/ZAYIF katmanında yanlış
    etb_ref = msp.add_blockref("SYN_ETB", (400, 300), dxfattribs={"layer": seed_layers[5]})     # TOPRAK/GRND katmanında DOĞRU (kalmalı!)
    lbl_ref = msp.add_blockref("SYN_L_LBL", (400, 500), dxfattribs={"layer": "CIRCUIT_LBL"})    # Hat/Linye etiketi korunmalı
    buat_ref = msp.add_blockref("SYN_B_W", (800, 500), dxfattribs={"layer": "CIRCUIT_AYD"})     # Devresinde kalmalı
    panel_ref = msp.add_blockref("SYN_PANO_DETAY", (2000, 2000), dxfattribs={"layer": "00-CERCEVE"})
    note_txt = msp.add_text("ZEMİN KAT AYDINLATMA PLANI", dxfattribs={"height": 25, "insert": (500, 1200), "layer": "00-YAZI"})

    # Kablo topolojisi: (1) Mükerrer kablo, (2) 3 cm doğrusal kopukluk, (3) Armatüre 3 cm kala kopuk uç
    msp.add_line((600, 500), (800, 500), dxfattribs={"layer": "CIRCUIT_AYD"})
    msp.add_line((600, 500), (800, 500), dxfattribs={"layer": "CIRCUIT_AYD"})  # duplicate
    # 3 cm kopukluk (x=880 -> 910, sonrasinda 913 -> 982; 982 ile 1000 merkezindeki R=15 armatur kenari arasi 3 cm)
    msp.add_line((800, 500), (910, 500), dxfattribs={"layer": "CIRCUIT_AYD"})
    msp.add_line((913, 500), (982, 500), dxfattribs={"layer": "CIRCUIT_AYD"})

    dxf_path = tmp_path / f"syn_elec_{convention}.dxf"
    doc.saveas(dxf_path)

    snap, model = build_canonical_model(str(dxf_path), use_cache=False)
    doc_rehab = ezdxf.readfile(dxf_path)
    res = rehabilitate_electrical_dxf(doc_rehab, snap, model, drawing_name=f"syn_{convention}")

    # Handle bazlı kontrol
    by_handle = {str(getattr(e.dxf, "handle", "")): e for e in doc_rehab.modelspace()}
    assert by_handle[light_ref.dxf.handle].dxf.layer == exp_light
    assert by_handle[sw_ref.dxf.handle].dxf.layer == exp_sw
    assert by_handle[fire_ref.dxf.handle].dxf.layer == exp_fire
    assert by_handle[etb_ref.dxf.handle].dxf.layer == seed_layers[5]
    assert by_handle[etb_ref.dxf.handle].dxf.layer != exp_light
    assert by_handle[panel_ref.dxf.handle].dxf.layer == exp_panel
    assert by_handle[note_txt.dxf.handle].dxf.layer == exp_text
    # Buat ve linye etiketi kendi devre/etiket katmanında korunmuş olmalı
    assert by_handle[lbl_ref.dxf.handle].dxf.layer == "CIRCUIT_LBL"
    assert by_handle[buat_ref.dxf.handle].dxf.layer == "CIRCUIT_AYD"

    # Mükerrer veya kopuk kablo onarımlarından en az 1'i önerilmiş / uygulanmış olmalı
    assert sum(res["wire_heal_summary"].values()) >= 1
    assert res["moved_inserts_total"] >= 4
    assert res["moved_texts_total"] >= 1


def test_merge_arch_and_elec_handles_block_name_collision(tmp_path: Path) -> None:
    """
    Mimari ve elektrik dosyalarında aynı blok adı bulunsa bile `merge_arch_and_elec_dxf`
    mimari bloku `ARCH__...` ile yeniden adlandırıp çakışmasız birleştirmelidir.
    """
    doc_arch = ezdxf.new("R2018")
    b_arch = doc_arch.blocks.new("SHARED_BLK")
    b_arch.add_line((0, 0), (100, 0), dxfattribs={"layer": "M1"})
    doc_arch.modelspace().add_blockref("SHARED_BLK", (10, 10), dxfattribs={"layer": "M1"})
    consolidate_architecture_to_single_layer(doc_arch)

    doc_elec = ezdxf.new("R2018")
    b_elec = doc_elec.blocks.new("SHARED_BLK")
    b_elec.add_circle((0, 0), radius=10, dxfattribs={"layer": "0"})
    doc_elec.modelspace().add_blockref("SHARED_BLK", (500, 500), dxfattribs={"layer": "00-AYD"})

    out_merged = tmp_path / "merged.dxf"
    merge_arch_and_elec_dxf(doc_arch, doc_elec, out_merged)

    merged = ezdxf.readfile(out_merged)
    auditor = merged.audit()
    assert len(auditor.errors) == 0

    inserts = [e for e in merged.modelspace() if e.dxftype() == "INSERT"]
    assert len(inserts) == 2
    names_by_layer = {e.dxf.layer: e.dxf.name for e in inserts}
    assert names_by_layer["00-AYD"] == "SHARED_BLK"
    assert names_by_layer["MIMARI"] == "ARCH__SHARED_BLK"


def test_separate_and_simplify_to_two_layers_and_discipline_split(tmp_path: Path) -> None:
    """
    Evrensel 2-layer sadeleştirme (1_MIMARI tek katman + 2_ELEKTRIK maks 2 katman:
    ELEKTRIK + HESAPLAR_TABLOLAR) ve 4 disiplin sınıflandırması anti-overfit testi.
    """
    from cad_okuma.cizim_onarici import separate_and_simplify_to_two_layers
    from cad_okuma.disiplin_ayirici import classify_drawing_discipline

    src = tmp_path / "karma_proje.dxf"
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    for lay in ("A-WALL", "I-FURN", "G-ANNO-TEXT", "E-LITE", "E-CABL", "ESKI_TABLO"):
        doc.layers.add(lay)

    msp = doc.modelspace()
    # Mimari duvar + oda yazısı
    msp.add_line((0, 0), (15, 0), dxfattribs={"layer": "A-WALL"})
    msp.add_line((0, 10), (15, 10), dxfattribs={"layer": "A-WALL"})
    msp.add_text("TEKNİK ODA", dxfattribs={"layer": "G-ANNO-TEXT", "height": 0.25, "insert": (2, 5)})

    # Elektrik armatür bloğu + kablo + kablo metni (G-ANNO-TEXT içinde!)
    blk_l = doc.blocks.new("LED_ARMATUR_X")
    blk_l.add_circle((0, 0), radius=0.25, dxfattribs={"layer": "0"})
    msp.add_blockref("LED_ARMATUR_X", (5, 5), dxfattribs={"layer": "E-LITE"})
    msp.add_line((5, 5), (10, 5), dxfattribs={"layer": "E-CABL"})
    msp.add_text("3x2.5 N2XH", dxfattribs={"layer": "G-ANNO-TEXT", "height": 0.2, "insert": (7, 5.4)})

    # Hesap / Yükleme Cetveli çerçevesi ve metinleri
    msp.add_lwpolyline([(20, 0), (35, 0), (35, 12), (20, 12)], close=True, dxfattribs={"layer": "ESKI_TABLO"})
    msp.add_text("YÜKLEME CETVELİ", dxfattribs={"layer": "ESKI_TABLO", "height": 0.4, "insert": (22, 10)})
    msp.add_text("PANO", dxfattribs={"layer": "ESKI_TABLO", "height": 0.25, "insert": (21, 8)})
    msp.add_text("GÜÇ (kW)", dxfattribs={"layer": "ESKI_TABLO", "height": 0.25, "insert": (28, 8)})
    msp.add_text("P-01", dxfattribs={"layer": "ESKI_TABLO", "height": 0.25, "insert": (21, 6)})
    msp.add_text("18.5 kW", dxfattribs={"layer": "ESKI_TABLO", "height": 0.25, "insert": (28, 6)})

    # Sinyal/SCADA başlığı (PaperSpace)
    ps = doc.layout("Layout1")
    ps.add_text("SCADA-PCS HABERLEŞME KOLON ŞEMASI", dxfattribs={"height": 0.3, "insert": (1, 1)})
    doc.saveas(str(src))

    snap, model = build_canonical_model(src, use_cache=False)
    disc, scores = classify_drawing_discipline(snap, model)
    assert disc == "SINYAL"
    assert scores["SINYAL"] > 0

    out_arch = tmp_path / "1_mimari.dxf"
    out_elec = tmp_path / "2_elektrik_2layer.dxf"
    stats = separate_and_simplify_to_two_layers(
        src,
        snap,
        model,
        out_arch_dxf=out_arch,
        out_elec_dxf=out_elec,
        heal_wires=False,
    )

    assert stats["arch_layers_after"] == ["MIMARI"]
    assert set(stats["elec_layers_after"]) == {"ELEKTRIK", "HESAPLAR_TABLOLAR"}

    d_a = ezdxf.readfile(out_arch)
    a_lays = {e.dxf.layer for e in d_a.modelspace()}
    assert a_lays == {"MIMARI"}

    d_e = ezdxf.readfile(out_elec)
    e_lays = {e.dxf.layer for e in d_e.modelspace()}
    assert e_lays <= {"ELEKTRIK", "HESAPLAR_TABLOLAR"}
    assert "ELEKTRIK" in e_lays and "HESAPLAR_TABLOLAR" in e_lays
    # G-ANNO-TEXT içindeki kablo yazısı elektrikte korunmuş, "TEKNİK ODA" mimariye ayrılmış olmalı
    e_texts = [e.dxf.text for e in d_e.modelspace() if e.dxftype() == "TEXT"]
    assert "3x2.5 N2XH" in e_texts
    assert "TEKNİK ODA" not in e_texts


def test_archicad_structural_and_shell_mtext_stay_in_architecture(tmp_path):
    """ArchiCAD/BIM `Structural-*` ve `Shell-*` MTEXT katmanları `2_ELEKTRIK` içine sızmamalıdır."""
    from cad_okuma import build_canonical_model, separate_and_simplify_to_two_layers

    src = tmp_path / "archicad_bim.dxf"
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 5  # cm
    for lay in ("Structural-Combined10", "Shell-Roof92", "00-AYD", "00-ELKYAZ"):
        doc.layers.add(lay)
    msp = doc.modelspace()
    msp.add_mtext("1", dxfattribs={"layer": "Structural-Combined10", "insert": (100, 100), "char_height": 15})
    msp.add_mtext("90 CM SIKISTIRILMIS TOPRAK DOLGU", dxfattribs={"layer": "Shell-Roof92", "insert": (200, 100), "char_height": 15})
    msp.add_line((0, 0), (300, 0), dxfattribs={"layer": "00-AYD"})
    msp.add_text("3x2.5 NHXMH", dxfattribs={"layer": "00-ELKYAZ", "insert": (150, 20), "height": 12})
    doc.saveas(str(src))

    snap, model = build_canonical_model(src, use_cache=False)
    out_arch = tmp_path / "arch.dxf"
    out_elec = tmp_path / "elec.dxf"
    separate_and_simplify_to_two_layers(
        src, snap, model, out_arch_dxf=out_arch, out_elec_dxf=out_elec, heal_wires=False
    )

    d_a = ezdxf.readfile(out_arch)
    d_e = ezdxf.readfile(out_elec)
    a_mtexts = [e.plain_text() for e in d_a.modelspace() if e.dxftype() == "MTEXT"]
    e_mtexts = [e.plain_text() for e in d_e.modelspace() if e.dxftype() == "MTEXT"]
    assert "90 CM SIKISTIRILMIS TOPRAK DOLGU" in a_mtexts
    assert "1" in a_mtexts
    assert not e_mtexts


def test_partial_vd_formula_and_blank_main_demand_no_sibling_steal():
    """Ana pano talep gücü `--W` boş bırakıldığında komşu pano gücü çalınmamalı ve kısmi GD formülü korunmalıdır."""
    from cad_okuma.hesap_denetleyici import _audit_voltage_drop_formulas
    from cad_okuma.schema import BBox2D, CanonicalProjectModel, FormulaBlock, UnitCalibration

    fb_main = FormulaBlock(
        formula_id="FRM_001",
        sheet_id="M_01",
        formula_kind="VOLTAGE_DROP",
        label="GD",
        numerator_texts=["40 x --,--"],
        denominator_texts=["70"],
        coefficient_texts=["0,0124 x"],
        result_texts=[],
        parsed_result_value=None,
        parse_status="PARTIAL",
        bbox_du=BBox2D(minx=10, miny=10, maxx=50, maxy=30),
    )
    fb_seg = FormulaBlock(
        formula_id="FRM_002",
        sheet_id="M_01",
        formula_kind="FEEDER_SEGMENT",
        label="GD",
        numerator_texts=["3x70+35NYY"],
        denominator_texts=["40m"],
        coefficient_texts=[],
        result_texts=["40m"],
        parsed_result_value=40.0,
        parse_status="OK",
        bbox_du=BBox2D(minx=10, miny=40, maxx=50, maxy=60),
    )
    fb_sub = FormulaBlock(
        formula_id="FRM_003",
        sheet_id="M_01",
        formula_kind="VOLTAGE_DROP",
        label="GD",
        numerator_texts=["15 x 4,5"],
        denominator_texts=["4"],
        coefficient_texts=["0,0124 x"],
        result_texts=["0,21"],
        parsed_result_value=0.21,
        parse_status="OK",
        bbox_du=BBox2D(minx=80, miny=10, maxx=120, maxy=30),
    )
    model = CanonicalProjectModel(
        filename="sentetik.dxf",
        filepath="sentetik.dxf",
        unit=UnitCalibration(unit_name="cm", du_to_mm=10.0, du_to_m=0.01, source="test", confidence=1.0, evidence={}),
        formula_blocks=[fb_main, fb_seg, fb_sub],
    )
    rows, w_tot, eng_proj_tot, eng_std_tot = _audit_voltage_drop_formulas(
        model, fallback_main_power_w=95000.0
    )
    assert len(rows) == 2
    assert rows[0].segment_name == "Ana Besleme"
    assert rows[0].cable_spec == "3x70+35NYY"
    assert rows[0].power_w is None
    assert rows[0].project_vd_pct is None
    assert rows[0].engine_vd_proj_v_pct is not None and rows[0].engine_vd_proj_v_pct > 0.5
    assert rows[1].segment_name == "Kolon Hattı"
    assert eng_proj_tot is not None and eng_proj_tot > (w_tot or 0.0)


def test_word_boundary_wire_keys_and_geometry_layer_consensus_no_keyword_whackamole(tmp_path):
    """Kelime listesine ekleme yapmadan: 'HAT'/'TEL' alt-dizi çakışması ('BAG_HATILI', 'OTEL_DUVAR')
    engellenmeli ve geometrik olarak mimari çıkan bilinmeyen katmanlar ('KATMAN_XYZ_99') konsensüsle 1_MIMARI'de kalmalıdır."""
    from cad_okuma import build_canonical_model, separate_and_simplify_to_two_layers
    from cad_okuma.disiplin_ayirici import _matches_wire_layer_key

    assert not _matches_wire_layer_key("BAG_HATILI")
    assert not _matches_wire_layer_key("A_HATCH")
    assert not _matches_wire_layer_key("OTEL_DUVAR")
    assert _matches_wire_layer_key("BESLEME_HATTI")
    assert _matches_wire_layer_key("ACIL-BUTON_HAT")
    assert _matches_wire_layer_key("YP-EL-EL1")

    src = tmp_path / "bilinmeyen_katmanlar.dxf"
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6  # m
    for lay in ("BAG_HATILI", "KATMAN_XYZ_99", "YP-EL-EL1"):
        doc.layers.add(lay)
    msp = doc.modelspace()
    # BAG_HATILI ve KATMAN_XYZ_99: elektrik sembollerinden uzak yapısal çizgiler + mimari yazı
    for i in range(5):
        msp.add_line((0, i * 2.0), (12, i * 2.0), dxfattribs={"layer": "BAG_HATILI"})
        msp.add_line((20, i * 2.0), (30, i * 2.0), dxfattribs={"layer": "KATMAN_XYZ_99"})
    msp.add_text("AKS-1", dxfattribs={"layer": "KATMAN_XYZ_99", "insert": (22, 1.0), "height": 0.3})
    # YP-EL-EL1: elektrik topraklama detay çizgileri + metni
    msp.add_line((50, 0), (60, 0), dxfattribs={"layer": "YP-EL-EL1"})
    msp.add_text("120mm2 TOPRAKLAMA ILETKENI", dxfattribs={"layer": "YP-EL-EL1", "insert": (52, 1.0), "height": 0.3})
    doc.saveas(str(src))

    snap, model = build_canonical_model(src, use_cache=False)
    out_arch = tmp_path / "arch.dxf"
    out_elec = tmp_path / "elec.dxf"
    separate_and_simplify_to_two_layers(
        src, snap, model, out_arch_dxf=out_arch, out_elec_dxf=out_elec, heal_wires=False
    )

    doc_o = ezdxf.readfile(str(src))
    orig_lay = {e.dxf.handle: e.dxf.layer for e in doc_o.modelspace()}
    d_a = ezdxf.readfile(str(out_arch))
    d_e = ezdxf.readfile(str(out_elec))
    a_orig = {orig_lay.get(e.dxf.handle) for e in d_a.modelspace()}
    e_orig = {orig_lay.get(e.dxf.handle) for e in d_e.modelspace()}

    assert "BAG_HATILI" in a_orig and "BAG_HATILI" not in e_orig
    assert "KATMAN_XYZ_99" in a_orig and "KATMAN_XYZ_99" not in e_orig
    assert "YP-EL-EL1" in e_orig and "YP-EL-EL1" not in a_orig


def test_blind_layer_pure_shape_and_spatial_separation(tmp_path):
    """Hiçbir katman adının anlamlı olmadığı ('KATMAN_1'..'KATMAN_6') kör senaryoda bile
    çift çizgili duvar, merdiven basamağı, kapı yayı, basamak numarası, patlatılmış tarama ve oda adları
    saf şekil + topolojiyle 1_MIMARI'ye, elektrik sembol + hattı 2_ELEKTRIK'e ayrılmalıdır."""
    from cad_okuma import build_canonical_model, separate_and_simplify_to_two_layers

    src = tmp_path / "kor_katmanlar.dxf"
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6  # m
    for lay in ("KATMAN_1", "KATMAN_2", "KATMAN_3", "KATMAN_4", "KATMAN_5", "KATMAN_6"):
        doc.layers.add(lay)
    msp = doc.modelspace()

    # KATMAN_1: Çift çizgili 20 cm duvarlar
    msp.add_line((0, 0), (8, 0), dxfattribs={"layer": "KATMAN_1"})
    msp.add_line((0, 0.2), (8, 0.2), dxfattribs={"layer": "KATMAN_1"})
    msp.add_line((0, 5), (8, 5), dxfattribs={"layer": "KATMAN_1"})
    msp.add_line((0, 5.2), (8, 5.2), dxfattribs={"layer": "KATMAN_1"})

    # KATMAN_2: 8 basamaklı merdiven + 90 derece kapı yayı
    for k in range(8):
        msp.add_line((10, k * 0.28), (11.2, k * 0.28), dxfattribs={"layer": "KATMAN_2"})
    msp.add_arc((2, 0.2), radius=0.9, start_angle=0, end_angle=90, dxfattribs={"layer": "KATMAN_2"})

    # KATMAN_3: Merdiven basamak numaraları 1..8 (salt MTEXT katmanı)
    for k in range(1, 9):
        msp.add_mtext(str(k), dxfattribs={"layer": "KATMAN_3", "insert": (10.6, (k - 1) * 0.28 + 0.14), "char_height": 0.12})

    # KATMAN_4: Patlatılmış paralel tarama (10 sık çizgi)
    for k in range(10):
        msp.add_line((14, k * 0.08), (16, k * 0.08), dxfattribs={"layer": "KATMAN_4"})

    # KATMAN_5: Oda isimleri (salt MTEXT katmanı)
    msp.add_mtext("OTURMA ODASI 24m2", dxfattribs={"layer": "KATMAN_5", "insert": (15, 4.0), "char_height": 0.25})
    msp.add_mtext("MUTFAK 12m2", dxfattribs={"layer": "KATMAN_5", "insert": (15, 6.0), "char_height": 0.25})
    msp.add_mtext("BANYO 6m2", dxfattribs={"layer": "KATMAN_5", "insert": (15, 8.0), "char_height": 0.25})

    # KATMAN_6: Lejantta tanımlı elektrik armatür sembolleri + bağlantı hattı + kablo yazısı
    blk = doc.blocks.new("SYM_LAMP_X")
    blk.add_circle((0, 0), radius=0.2, dxfattribs={"layer": "0"})
    msp.add_lwpolyline([(25, 0), (35, 0), (35, 5), (25, 5)], close=True, dxfattribs={"layer": "KATMAN_6"})
    msp.add_text("LEJANT", dxfattribs={"layer": "KATMAN_6", "insert": (28, 4.2), "height": 0.3})
    msp.add_blockref("SYM_LAMP_X", (26, 2.5), dxfattribs={"layer": "KATMAN_6"})
    msp.add_text("LED ARMATUR", dxfattribs={"layer": "KATMAN_6", "insert": (27.5, 2.5), "height": 0.2})
    msp.add_blockref("SYM_LAMP_X", (3, 2.5), dxfattribs={"layer": "KATMAN_6"})
    msp.add_blockref("SYM_LAMP_X", (6, 2.5), dxfattribs={"layer": "KATMAN_6"})
    msp.add_line((3, 2.5), (6, 2.5), dxfattribs={"layer": "KATMAN_6"})
    msp.add_text("3x1.5 NHXMH", dxfattribs={"layer": "KATMAN_6", "insert": (4.2, 2.8), "height": 0.18})
    doc.saveas(str(src))

    snap, model = build_canonical_model(src, use_cache=False)
    out_arch = tmp_path / "arch.dxf"
    out_elec = tmp_path / "elec.dxf"
    separate_and_simplify_to_two_layers(
        src, snap, model, out_arch_dxf=out_arch, out_elec_dxf=out_elec, heal_wires=False
    )

    orig_lay = {e.dxf.handle: e.dxf.layer for e in ezdxf.readfile(str(src)).modelspace()}
    a_orig = {orig_lay.get(e.dxf.handle) for e in ezdxf.readfile(str(out_arch)).modelspace()}
    e_orig = {orig_lay.get(e.dxf.handle) for e in ezdxf.readfile(str(out_elec)).modelspace()}

    for arch_l in ("KATMAN_1", "KATMAN_2", "KATMAN_3", "KATMAN_4", "KATMAN_5"):
        assert arch_l in a_orig and arch_l not in e_orig
    assert "KATMAN_6" in e_orig and "KATMAN_6" not in a_orig




