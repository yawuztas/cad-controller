# -*- coding: utf-8 -*-
"""
Evrensel Topoloji, DBSCAN Ada Kümeleme ve momepy/libpysal Mahal Analizi Testleri
==================================================================================
Hiçbir CAD yazılımına (AutoCAD / Revit / MicroStation) veya örnek proje adına
bağlı kalmadan evrensel fiziksel boyut, hiyerarşi ağacı, DBSCAN yoğunluk
kümeleme ve kapalı mahal morfolojisini doğrular.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
MOTOR_ROOT = ROOT_DIR / "03_hesap_motoru"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from cad_okuma.disiplin_ayirici import (  # noqa: E402
    build_container_block_names,
    classify_insert_role,
    is_container_insert,
    partition_outside_regions,
)
from cad_okuma.mahal_analizi import (  # noqa: E402
    check_coverage_in_enclosures,
    extract_architectural_enclosures,
)
from cad_okuma.schema import BBox2D, RawInsert, RawPath, RawText  # noqa: E402


def test_topology_container_vs_leaf_zero_name_bias() -> None:
    """Blok adında 'FloorPlan-'/_RVT geçse bile küçük yaprak sembol konteyner sayılmamalı; mimari paneller ayıklanmalı."""
    du_to_m = 0.001  # mm

    macro = RawInsert(
        handle="C1",
        block_name="Rastgele_Kat_Altligi_Alpha",
        effective_name="Rastgele_Kat_Altligi_Alpha",
        layer="0",
        x=0.0,
        y=0.0,
        bbox=BBox2D(minx=0.0, miny=0.0, maxx=25000.0, maxy=18000.0),  # 25m x 18m
    )
    trap_leaf = RawInsert(
        handle="L1",
        block_name="FloorPlan-KAT01_dwg_AYDINLATMA_ARMATUR_X",
        effective_name="FloorPlan-KAT01_dwg_AYDINLATMA_ARMATUR_X",
        layer="0",
        x=5000.0,
        y=5000.0,
        parent_chain="Rastgele_Kat_Altligi_Alpha",
        bbox=BBox2D(minx=4750.0, miny=4750.0, maxx=5250.0, maxy=5250.0),  # 0.5m x 0.5m
    )
    arch_glaze = RawInsert(
        handle="A1",
        block_name="System Panel - Glazed",
        effective_name="System Panel - Glazed",
        layer="0",
        x=2000.0,
        y=2000.0,
        bbox=BBox2D(minx=1500.0, miny=1950.0, maxx=2500.0, maxy=2050.0),
    )
    arch_booth = RawInsert(
        handle="A2",
        block_name="C1090_20_TELEPHONE BOOTH",
        effective_name="C1090_20_TELEPHONE BOOTH",
        layer="0",
        x=3000.0,
        y=2000.0,
        bbox=BBox2D(minx=2500.0, miny=1500.0, maxx=3500.0, maxy=2500.0),
    )
    arch_sove = RawInsert(
        handle="A3",
        block_name="Asansör Önü söve_11",
        effective_name="Asansör Önü söve_11",
        layer="0",
        x=4000.0,
        y=2000.0,
        bbox=BBox2D(minx=3500.0, miny=1900.0, maxx=4500.0, maxy=2100.0),
    )

    containers = build_container_block_names([macro, trap_leaf, arch_glaze, arch_booth, arch_sove], du_to_m)
    assert "Rastgele_Kat_Altligi_Alpha" in containers
    assert "FloorPlan-KAT01_dwg_AYDINLATMA_ARMATUR_X" not in containers
    assert is_container_insert(macro, du_to_m, containers) is True
    assert is_container_insert(trap_leaf, du_to_m, containers) is False

    rg_l, cat_l, _, _, _ = classify_insert_role(trap_leaf, {})
    assert rg_l == "ELECTRICAL"
    assert cat_l == "AYDINLATMA"

    for arch_ins in (arch_glaze, arch_booth, arch_sove):
        rg_a, _, disc_a, _, _ = classify_insert_role(arch_ins, {})
        assert rg_a == "ARCHITECTURAL", arch_ins.block_name
        assert disc_a == "MIMARI"


@pytest.mark.parametrize("unit_name,scale", [("m", 1.0), ("mm", 1000.0)])
def test_dbscan_outside_regions_unit_invariant(unit_name: str, scale: float) -> None:
    """Başlıksız dağınık iki adayı DBSCAN fiziksel ölçekten bağımsız 2 ayrı kümeye ayırır."""
    du_to_m = 1.0 / scale
    ins_a1 = RawInsert(
        handle="I1", block_name="ARM1", effective_name="ARM1",
        x=1.0 * scale, y=1.0 * scale,
        bbox=BBox2D(minx=0.8 * scale, miny=0.8 * scale, maxx=1.2 * scale, maxy=1.2 * scale),
    )
    ins_a2 = RawInsert(
        handle="I2", block_name="ARM1", effective_name="ARM1",
        x=2.0 * scale, y=1.0 * scale,
        bbox=BBox2D(minx=1.8 * scale, miny=0.8 * scale, maxx=2.2 * scale, maxy=1.2 * scale),
    )
    ins_b1 = RawInsert(
        handle="I3", block_name="PRZ1", effective_name="PRZ1",
        x=30.0 * scale, y=1.0 * scale,
        bbox=BBox2D(minx=29.8 * scale, miny=0.8 * scale, maxx=30.2 * scale, maxy=1.2 * scale),
    )
    ins_b2 = RawInsert(
        handle="I4", block_name="PRZ1", effective_name="PRZ1",
        x=31.0 * scale, y=1.5 * scale,
        bbox=BBox2D(minx=30.8 * scale, miny=1.3 * scale, maxx=31.2 * scale, maxy=1.7 * scale),
    )

    regions = partition_outside_regions([], [ins_a1, ins_a2, ins_b1, ins_b2], [], du_to_m)
    clusters = [r for r in regions if r["source_kind"] == "CERCEVESIZ_KUME"]
    assert len(clusters) == 2
    assert sorted(len(c["inserts"]) for c in clusters) == [2, 2]


@pytest.mark.parametrize("unit_name,scale", [("m", 1.0), ("mm", 1000.0)])
def test_momepy_libpysal_enclosures_and_coverage(unit_name: str, scale: float) -> None:
    """Bitişik iki odadan momepy + libpysal ile doğru m², komşuluk grafı ve kapsama oranı çıkar."""
    du_to_m = 1.0 / scale

    def mk_line(h: str, x1: float, y1: float, x2: float, y2: float) -> RawPath:
        px1, py1, px2, py2 = x1 * scale, y1 * scale, x2 * scale, y2 * scale
        return RawPath(
            handle=h,
            dxftype="LINE",
            layer="A-WALL",
            points=[(px1, py1), (px2, py2)],
            length_du=((px2 - px1) ** 2 + (py2 - py1) ** 2) ** 0.5,
            bbox=BBox2D(minx=min(px1, px2), miny=min(py1, py2), maxx=max(px1, px2), maxy=max(py1, py2)),
        )

    # Oda 1: [0..4] x [0..5] = 20 m², Oda 2: [4..10] x [0..5] = 30 m² (x=4 ortak duvar)
    walls = [
        mk_line("W1", 0, 0, 10, 0),
        mk_line("W2", 0, 5, 10, 5),
        mk_line("W3", 0, 0, 0, 5),
        mk_line("W4", 4, 0, 4, 5),
        mk_line("W5", 10, 0, 10, 5),
    ]
    txts = [
        RawText(handle="T1", dxftype="TEXT", text="TRAFO ODASI", x=2.0 * scale, y=2.5 * scale, height=0.2 * scale,
                bbox=BBox2D(minx=1.5 * scale, miny=2.3 * scale, maxx=2.5 * scale, maxy=2.7 * scale)),
        RawText(handle="T2", dxftype="TEXT", text="AG PANO ODASI", x=7.0 * scale, y=2.5 * scale, height=0.2 * scale,
                bbox=BBox2D(minx=6.5 * scale, miny=2.3 * scale, maxx=7.5 * scale, maxy=2.7 * scale)),
    ]

    enclosures, gdf = extract_architectural_enclosures(walls, du_to_m, texts=txts)
    assert len(enclosures) == 2
    assert len(gdf) == 2
    areas = sorted(e["area_m2"] for e in enclosures)
    assert areas == pytest.approx([20.0, 30.0], abs=0.05)
    # İki oda Queen komşusu olmalı
    assert all(len(e["neighbor_ids"]) == 1 for e in enclosures)
    labels = {e["label"] for e in enclosures}
    assert labels == {"TRAFO ODASI", "AG PANO ODASI"}

    # Oda 1 merkezine konan r=2.0m sensör Oda 1'i kısmen kapsar (~12.5 m²), Oda 2'yi kısmen taşar
    cov = check_coverage_in_enclosures(enclosures, [(2.0, 2.5)], radius_m=2.0)
    assert len(cov) == 2
    by_lbl = {c["label"]: c for c in cov}
    assert 55.0 <= by_lbl["TRAFO ODASI"]["coverage_pct"] <= 70.0
    assert by_lbl["AG PANO ODASI"]["uncovered_m2"] > 25.0


def test_pandapower_radial_loadflow_and_short_circuit() -> None:
    """`pandapower` ile çok baralı yük akışı ve IEC 60909 kısa devre + kesit duyarlılık testi."""
    from cad_okuma.sebeke_analizi import (
        NetworkFeederInput,
        TransformerInput,
        analyze_radial_network_pandapower,
    )

    tr = TransformerInput(name="TR-TEST", sn_kva=1000.0, vn_hv_kv=34.5, vn_lv_kv=0.4, vk_percent=6.0)
    branches_thin = [
        NetworkFeederInput(parent_bus="AGADP", target_bus="PANO_A", power_kw=120.0, cable_spec="3x95+50 N2XH", length_m=80.0),
        NetworkFeederInput(parent_bus="PANO_A", target_bus="PANO_B", power_kw=35.0, cable_spec="5x16 N2XH", length_m=50.0),
    ]
    branches_thick = [
        NetworkFeederInput(parent_bus="AGADP", target_bus="PANO_A", power_kw=120.0, cable_spec="3x185+95 N2XH", length_m=80.0),
        NetworkFeederInput(parent_bus="PANO_A", target_bus="PANO_B", power_kw=35.0, cable_spec="5x35 N2XH", length_m=50.0),
    ]

    res_thin = analyze_radial_network_pandapower(branches_thin, transformer=tr)
    res_thick = analyze_radial_network_pandapower(branches_thick, transformer=tr)

    assert res_thin.converged is True
    assert res_thick.converged is True
    assert res_thin.transformer_loading_pct is not None and res_thin.transformer_loading_pct > 10.0
    assert res_thin.max_voltage_drop_pct > res_thick.max_voltage_drop_pct
    assert all(b.ikss_ka is not None and b.ikss_ka > 1.0 for b in res_thin.buses)


def test_multi_sheet_metro_station_bundle_and_plotly(tmp_path: Path) -> None:
    """Çoklu DWG/DXF istasyon birleştirme: antet tutarsızlığı, ray-toprak teması, LSZH ve Plotly raporu."""
    import ezdxf
    from cad_okuma.proje_birlestirici import analyze_multi_sheet_project, save_multi_sheet_reports

    p_power = tmp_path / "01_Kuvvetli_Akim" / "kat_guc.dxf"
    p_copy = tmp_path / "01_Kuvvetli_Akim" / "Copy of kat_guc.dxf"
    p_ground = tmp_path / "02_Topraklama" / "kat_toprak.dxf"
    p_power.parent.mkdir(parents=True)
    p_ground.parent.mkdir(parents=True)

    # 1) Kuvvetli akım DXF: KUZEY İSTASYONU anteti + tava etiketi + NYY (PVC) kablo uyarısı adayı
    doc1 = ezdxf.new("R2018")
    doc1.header["$INSUNITS"] = 6
    msp1 = doc1.modelspace()
    msp1.add_lwpolyline([(0, 0), (30, 0), (30, 20), (0, 20)], close=True, dxfattribs={"layer": "CERCEVE"})
    msp1.add_text("WC/ 400/ 250", dxfattribs={"layer": "E-CABL-TRAY", "height": 0.25, "insert": (5, 10)})
    msp1.add_text("3x16+10 NYY", dxfattribs={"layer": "0", "height": 0.25, "insert": (6, 8)})
    ps1 = doc1.layout("Layout1")
    ps1.add_text("KUZEY İSTASYONU - PERON KATI GÜÇ PLANI", dxfattribs={"height": 0.3, "insert": (1, 1)})
    doc1.saveas(str(p_power))
    doc1.saveas(str(p_copy))  # Yedek kopya atlanmalı

    # 2) Topraklama DXF: GÜNEY İSTASYONU (tutarsız antet!) + ray ve topraklama doğrudan kesişimi
    doc2 = ezdxf.new("R2018")
    doc2.header["$INSUNITS"] = 6
    msp2 = doc2.modelspace()
    msp2.add_line((0, 5), (20, 5), dxfattribs={"layer": "E-TRAK-RAIL"})
    msp2.add_line((10, 0), (10, 10), dxfattribs={"layer": "E-EAR-MESH"})
    ps2 = doc2.layout("Layout1")
    ps2.add_text("GÜNEY İSTASYONU - TOPRAKLAMA PLANI", dxfattribs={"height": 0.3, "insert": (1, 1)})
    doc2.saveas(str(p_ground))

    rep = analyze_multi_sheet_project(tmp_path, rule_pack="ibb_metro", use_cache=False)
    assert rep.files_scanned == 2
    assert "Copy of kat_guc.dxf" in rep.files_skipped_duplicates
    assert len(rep.detected_station_names) == 2
    assert any(t.system_code == "WC" and t.width_mm == 400 and t.height_mm == 250 for t in rep.tray_inventory)

    cats = {f.category for f in rep.findings}
    assert "Pafta Antet Tutarlılığı" in cats
    assert "Ray-Toprak Doğrudan Teması (Floating Return İhlali)" in cats
    assert "Halogen-Free (LSZH / FE180) Kablo Şartı" in cats

    out_files = save_multi_sheet_reports(rep, tmp_path / "cikti", base_name="test_istasyon")
    for k in ("json", "md", "xlsx", "html"):
        assert out_files[k].exists() and out_files[k].stat().st_size > 100


def test_n1_transformer_redundancy_and_audit_bridge() -> None:
    """N-1 trafo yedeklilik hesabı + eksik veri uydurmama + PanelAuditRow->pandapower köprü testi."""
    from cad_okuma.hesap_denetleyici import PanelAuditRow
    from cad_okuma.sebeke_analizi import (
        analyze_radial_network_pandapower,
        build_feeders_from_audit_rows,
        check_n1_transformer_redundancy,
    )

    # 1. N-1 Uygun: 2 x 1250 kVA -> kalan 1250 kVA, P_talep = 900 kW (1000 kVA @ cos0.9) => %80 UYGUN
    r_ok = check_n1_transformer_redundancy([1250.0, 1250.0], demand_kw=900.0, cos_phi=0.90)
    assert r_ok.status == "UYGUN"
    assert r_ok.n1_utilization_pct == pytest.approx(80.0, abs=0.2)

    # 2. N-1 Yetersiz: 2 x 1000 kVA -> kalan 1000 kVA, P_talep = 1170 kW (1300 kVA) => %130 KRITIK
    r_fail = check_n1_transformer_redundancy([1000.0, 1000.0], demand_kw=1170.0, cos_phi=0.90)
    assert r_fail.status == "KRITIK"
    assert r_fail.n1_utilization_pct > 100.0

    # 3. Talep gücü yoksa asla sayı uydurulmaz -> BELIRSIZ
    r_missing = check_n1_transformer_redundancy([2000.0, 2000.0], demand_kw=None)
    assert r_missing.status == "BELIRSIZ"
    assert r_missing.n1_remaining_kva == 2000.0

    # 4. PanelAuditRow köprüsü: eksik L'li satırı atlamalı, eksiksiz satırdan pandapower çalıştırmalı
    rows = [
        PanelAuditRow(panel_name="P-EKSIK", demand_power_w=12000.0, cable_spec="5x6 NYY", feeder_length_m=None),
        PanelAuditRow(panel_name="P-TAM1", demand_power_w=18000.0, cable_spec="5x10 NYY", feeder_length_m=35.0),
        PanelAuditRow(panel_name="P-TAM2", demand_power_w=9000.0, cable_spec="5x6 NYY", feeder_length_m=22.0),
    ]
    feeders, skipped = build_feeders_from_audit_rows("ADP", rows)
    assert len(feeders) == 2
    assert any("P-EKSIK" in s for s in skipped)
    na = analyze_radial_network_pandapower(feeders)
    assert na.converged is True
    assert na.max_voltage_drop_pct > 0.0
    assert len(na.buses) == 3


def test_metro_grounding_discipline_arrow_and_layer_guards() -> None:
    """
    Metro topraklama paftası evrensellik testi:
      1. XREF önekli ok (`...-AYDINLATMA-000-...$0$okk-4862529-KAT`) ve `Spot Elevations`
         yanlışlıkla `AYDINLATMA` sayılmamalı (ARCHITECTURAL olmalı).
      2. Üzerinde 50 adet arka plan panosu bulunan `TOPRAKLAMA SİSTEMİ` paftası yine de
         `TOPRAKLAMA` disiplini olarak sınıflandırılmalı (sınırlı sembol oylaması).
      3. `_find_grounding_layer_names` mimari (`A-WALL`, `S-FNDN`) ve yazı (`_YAZI`)
         katmanlarını asla topraklama ringine almamalı; `KOLON ŞEMASI` başlığı da `KOLON_SEMASI` olmalı.
    """
    from cad_okuma.disiplin_ayirici import classify_drawing_discipline, classify_insert_role
    from cad_okuma.pafta_ayirici import _classify_frame_role
    from cad_okuma.schema import (
        BBox2D,
        CanonicalProjectModel,
        RawCADSnapshot,
        RawInsert,
        RawPath,
        RawText,
        SheetFrame,
        UnitCalibration,
    )
    from cad_okuma.topoloji_ve_topraklama import _find_grounding_layer_names

    bb = BBox2D(minx=0, miny=0, maxx=0.3, maxy=0.3)
    ins_okk = RawInsert(
        handle="O1",
        block_name="Plan-AYDINLATMA-000-06-U$0$okk-4862529-BIT 01",
        effective_name="Plan-AYDINLATMA-000-06-U$0$okk-4862529-BIT 01",
        layer="0",
        x=1.0,
        y=1.0,
        bbox=bb,
    )
    rg_o, _, _, _, _ = classify_insert_role(ins_okk, {})
    assert rg_o == "ARCHITECTURAL"

    ins_spot = RawInsert(
        handle="S1",
        block_name="DET_dwg_Spot Elevations - D_DAT_ELE",
        effective_name="DET_dwg_Spot Elevations - D_DAT_ELE",
        layer="0",
        x=2.0,
        y=2.0,
        bbox=bb,
    )
    rg_s, _, _, _, _ = classify_insert_role(ins_spot, {})
    assert rg_s == "ARCHITECTURAL"

    # Arka planda 50 adet pano bloğu taşıyan topraklama paftası TOPRAKLAMA kalmalı
    panel_inserts = [
        RawInsert(
            handle=f"P{i}",
            block_name=f"Switchboard_{i}",
            effective_name=f"Switchboard_{i}",
            layer="E-ELEC-EQPM",
            x=float(i),
            y=5.0,
            bbox=BBox2D(minx=float(i), miny=5.0, maxx=float(i) + 0.4, maxy=5.4),
        )
        for i in range(50)
    ]
    sh_t = SheetFrame(
        frame_id="M_1",
        title="BİNA İÇİ TOPRAKLAMA SİSTEMİ UYGULAMA PROJESİ",
        role="TOPRAKLAMA",
        bbox_du=BBox2D(minx=0, miny=0, maxx=100, maxy=60),
        bbox_m=BBox2D(minx=0, miny=0, maxx=100, maxy=60),
    )
    snap_t = RawCADSnapshot(
        filepath="istasyon_toprak.dxf",
        filename="istasyon_toprak.dxf",
        dxf_path="istasyon_toprak.dxf",
        inserts=panel_inserts,
        texts=[
            RawText(
                handle="T1",
                dxftype="TEXT",
                text="BİNA İÇİ TOPRAKLAMA SİSTEMİ UYGULAMA PROJESİ",
                x=10.0,
                y=2.0,
                height=0.5,
                space="PAPERSPACE:Layout1",
                bbox=BBox2D(minx=10, miny=2, maxx=30, maxy=2.5),
            )
        ],
    )
    m_t = CanonicalProjectModel(
        filepath="istasyon_toprak.dxf",
        filename="istasyon_toprak.dxf",
        unit=UnitCalibration(unit_name="m", du_to_mm=1000.0, du_to_m=1.0, confidence=1.0, source="test"),
        sheets=[sh_t],
    )
    disc_t, _ = classify_drawing_discipline(snap_t, m_t, source_path="00-PS-17-TOPRAK.dwg")
    assert disc_t == "TOPRAKLAMA"

    # Mimari duvar/statik temel katmanları topraklama ringine sızmamalı
    paths_mix = [
        RawPath(handle="W1", dxftype="LINE", points=[(0, 0), (10, 0)], layer="A-WALL", bbox=BBox2D(minx=0, miny=0, maxx=10, maxy=0.1)),
        RawPath(handle="W2", dxftype="LINE", points=[(0, 0), (10, 0)], layer="S-FNDN", bbox=BBox2D(minx=0, miny=0, maxx=10, maxy=0.1)),
        RawPath(handle="W3", dxftype="LINE", points=[(0, 0), (10, 0)], layer="PRT-EL-TOPRAK_YAZI", bbox=BBox2D(minx=0, miny=0, maxx=10, maxy=0.1)),
        RawPath(handle="E1", dxftype="LINE", points=[(0, 0), (10, 0)], layer="E-ELEC-EQPM", bbox=BBox2D(minx=0, miny=0, maxx=10, maxy=0.1)),
    ]
    g_lays = _find_grounding_layer_names(paths_mix, [])
    assert "A-WALL" not in g_lays
    assert "S-FNDN" not in g_lays
    assert "PRT-EL-TOPRAK_YAZI" not in g_lays
    assert "E-ELEC-EQPM" in g_lays

    # Topraklama Kolon Şeması TOPRAKLAMA planı değil KOLON_SEMASI olmalı
    riser_texts = [
        RawText(handle="R1", dxftype="TEXT", text="BİNA İÇİ TOPRAKLAMA SİSTEMİ KOLON ŞEMASI", x=5, y=5, height=20, bbox=BBox2D(minx=5, miny=5, maxx=80, maxy=25)),
    ]
    riser_role, _, _, _ = _classify_frame_role(riser_texts, door_arc_count=0, paths=paths_mix)
    assert riser_role == "KOLON_SEMASI"


@pytest.mark.parametrize("unit_name,scale,insunits", [("m", 1.0, 6), ("mm", 1000.0, 4)])
def test_metro_universal_signal_weak_current_cables_and_audit_anti_overfit(
    tmp_path: Path, unit_name: str, scale: float, insunits: int
) -> None:
    """
    Örnek proje adı/koordinatından tamamen bağımsız sentetik metro paftaları:
    - ARKA_PLAN + Revizyon Tablosu antet koruması + KABLOLAMA PLANI / KOTU PLANI rolü
    - TURNSTILE + E-CABL-TRAY bir arada iken ZAYIF_AKIM baskınlığı, KOMUTATÖR != ATO
    - N2XRH-J (FE180), U/FTP CAT6 LS0H (>90 m sınırı) ve 3x(1x185/25ş) XLPE PE/S oranı
    """
    import ezdxf
    from cad_okuma.disiplin_ayirici import classify_drawing_discipline
    from cad_okuma.hesap_denetleyici import build_calculation_audit_report
    from cad_okuma.kalip_olusturucu import build_canonical_model
    from cad_okuma.metraj_cikarici import build_project_inventory

    # 1) Sinyal / PLC + ARKA_PLAN + Revizyon Tablosu + N2XRH / U/FTP CAT6
    doc_sig = ezdxf.new("R2018")
    doc_sig.header["$INSUNITS"] = insunits
    msp1 = doc_sig.modelspace()
    msp1.add_lwpolyline(
        [(0, 0), (40 * scale, 0), (40 * scale, 25 * scale), (0, 25 * scale)],
        close=True,
        dxfattribs={"layer": "CERCEVE"},
    )
    msp1.add_text(
        "SYN-PLC VE RTU KABLOLAMA PLANI (+12.50 KOTU PLANI)",
        dxfattribs={"height": 0.4 * scale, "insert": (2 * scale, 23 * scale)},
    )
    msp1.add_line((1 * scale, 1 * scale), (20 * scale, 1 * scale), dxfattribs={"layer": "ARKA_PLAN"})
    blk_rev = doc_sig.blocks.new("SYN_ANTET_REVIZYON_TABLOSU")
    blk_rev.add_lwpolyline([(0, 0), (5 * scale, 0), (5 * scale, 2 * scale), (0, 2 * scale)], close=True)
    msp1.add_blockref("SYN_ANTET_REVIZYON_TABLOSU", (30 * scale, 2 * scale), dxfattribs={"layer": "Cartiglio interno no_stampa"})
    blk_kom = doc_sig.blocks.new("KOMUTATOR_ANAHTAR")
    blk_kom.add_circle((0, 0), radius=0.15 * scale)
    msp1.add_blockref("KOMUTATOR_ANAHTAR", (5 * scale, 5 * scale), dxfattribs={"layer": "E-LITE"})
    # Metraj tablosu: > 90m CAT6 ve N2XRH FE180 + ekranlı OG/AG kablo
    y0 = 18 * scale
    for r_i, (c1, c2, c3) in enumerate([
        ("LİNYE NO", "KABLO", "UZUNLUK (m)"),
        ("S-01", "U/FTP CAT6 LS0H", "115.0 m"),
        ("S-02", "3x2,5 mm² N2XRH-J (FE180)", "42.0 m"),
        ("P-01", "3x(1x185/25ş mm2 XLPE)", "65.0 m"),
    ]):
        ry = y0 - r_i * 1.2 * scale
        msp1.add_text(c1, dxfattribs={"height": 0.25 * scale, "insert": (4 * scale, ry)})
        msp1.add_text(c2, dxfattribs={"height": 0.25 * scale, "insert": (9 * scale, ry)})
        msp1.add_text(c3, dxfattribs={"height": 0.25 * scale, "insert": (22 * scale, ry)})
    msp1.add_line((4 * scale, 10 * scale), (24 * scale, 10 * scale), dxfattribs={"layer": "E-CABL"})

    p_sig = tmp_path / f"syn_sig_{unit_name}.dxf"
    doc_sig.saveas(str(p_sig))
    snap1, model1 = build_canonical_model(p_sig, use_cache=False)
    disc1, _ = classify_drawing_discipline(snap1, model1)
    assert disc1 == "SINYAL"
    assert model1.sheets[0].role == "KAT_PLANI"

    inv1 = build_project_inventory(snap1, model1)
    bom_map = {c.spec: c for c in inv1.cable_bom}
    assert any("CAT6" in k and bom_map[k].explicit_length_m == pytest.approx(115.0) for k in bom_map)
    assert any("N2XRH-J" in k and bom_map[k].explicit_length_m == pytest.approx(42.0) for k in bom_map)
    assert any("185/25" in k and bom_map[k].explicit_length_m == pytest.approx(65.0) for k in bom_map)
    sym_map = {s.block_name: s for s in inv1.symbol_bom}
    assert "SYN_ANTET_REVIZYON_TABLOSU" not in sym_map
    assert sym_map["KOMUTATOR_ANAHTAR"].discipline == "KUVVETLI_AKIM"

    rep1 = build_calculation_audit_report(snap1, model1, inventory=inv1)
    assert rep1.regulation_pack == "ibb_metro"
    cats = {f.category: f.severity for f in rep1.findings}
    assert cats.get("Zayıf Akım Bakır Hat Uzunluğu") == "KRITIK"
    assert cats.get("PE / Konsantrik Ekran Kesit Oranı") == "UYARI"
    assert cats.get("Yangın Güvenliği / Halojen-Free Kablo") == "UYGUN"

    # 2) Zayıf akım istasyon turnikeleri + yoğun Cable Tray -> hala ZAYIF_AKIM
    doc_wc = ezdxf.new("R2018")
    doc_wc.header["$INSUNITS"] = insunits
    msp2 = doc_wc.modelspace()
    msp2.add_lwpolyline(
        [(0, 0), (30 * scale, 0), (30 * scale, 20 * scale), (0, 20 * scale)],
        close=True,
        dxfattribs={"layer": "CERCEVE"},
    )
    blk_t = doc_wc.blocks.new("STATION_TURNSTILE_V2")
    blk_t.add_lwpolyline([(0, 0), (1 * scale, 0), (1 * scale, 0.4 * scale), (0, 0.4 * scale)], close=True)
    blk_tray = doc_wc.blocks.new("Cable Tray Horizontal Tee")
    blk_tray.add_line((0, 0), (0.6 * scale, 0))
    for i in range(4):
        msp2.add_blockref("STATION_TURNSTILE_V2", ((3 + i * 2) * scale, 5 * scale), dxfattribs={"layer": "E-ELEC-EQPM"})
    for j in range(12):
        msp2.add_blockref("Cable Tray Horizontal Tee", ((2 + j * 1.5) * scale, 10 * scale), dxfattribs={"layer": "E-CABL-TRAY"})
    msp2.add_text("BİLET HOLÜ TURNİKE YERLEŞİM PLANI", dxfattribs={"height": 0.4 * scale, "insert": (2 * scale, 18 * scale)})

    p_wc = tmp_path / f"syn_wc_{unit_name}.dxf"
    doc_wc.saveas(str(p_wc))
    snap2, model2 = build_canonical_model(p_wc, use_cache=False)
    disc2, _ = classify_drawing_discipline(snap2, model2)
    assert disc2 == "ZAYIF_AKIM"


def test_clean_report_grouping_all_six_calcs_and_metro_dedup() -> None:
    """Bina raporunda tüm 6 hesabın daima gösterilmesi, tekrarsız gruplama ve metro trafo/antet tekilleştirmesi."""
    from cad_okuma.hesap_denetleyici import (
        AuditFindingItem,
        CalculationAuditReport,
        MainIncomerAudit,
        PowerBudgetAudit,
        _compact_panel_names,
        _group_findings_for_display,
        format_calculation_audit_markdown,
    )
    from cad_okuma.proje_birlestirici import (
        _deduplicate_station_ratings,
        _format_kva_summary,
        _normalize_station_name,
    )

    assert _compact_panel_names(["DT-1", "DT-2", "DT-3", "DT-4", "DT-6"]) == "DT-1..DT-4, DT-6 (5 pano)"
    rep = CalculationAuditReport(
        filename="sentetik_bina.dxf",
        unit_name="cm",
        regulation_pack="turkey_bina",
        summary_counts={"KRITIK": 0, "UYARI": 4, "UYGUN": 0, "incelenen_pano": 4},
        findings=[
            AuditFindingItem(
                finding_id=f"H-{i:02d}",
                severity="UYARI",
                category="Faz Yük Dengesizliği",
                location=f"Yükleme Cetveli (DT-{i} / TBL_{i:03d})",
                project_value="R=4000W, S=3100W, T=2790W (%Δ=36.7%)",
                engine_value="%Δ <= %15.0",
                standard_ref="EİTY Md. 57",
                description="Dengesizlik",
            )
            for i in range(1, 5)
        ],
        power_budget=PowerBudgetAudit(subpanel_count=4, subpanels_installed_sum_w=40000.0, subpanels_demand_sum_w=22000.0),
        main_incomer=MainIncomerAudit(panel_name="AT"),
    )
    grouped = _group_findings_for_display(rep.findings)
    assert len(grouped) == 1
    assert "DT-1..DT-4" in grouped[0]["location"]

    md = format_calculation_audit_markdown(rep)
    for heading in (
        "## 2. Güç Bütçesi",
        "## 3. Isınma",
        "## 4. Gerilim Düşümü",
        "## 5. Temel Topraklama",
        "## 6. Aydınlatma Hesabı",
        "## 7. Şebeke Yük Akışı",
    ):
        assert heading in md
    assert "Projede Yok" in md

    assert _normalize_station_name("BATI İSTASYONU - BİLET HOLÜ KATI +8.20") == "BATI İSTASYONU"
    assert _normalize_station_name("DOĞU İSTASYONU YOLCU GEÇİŞ KONTROL") == "DOĞU İSTASYONU"
    assert _normalize_station_name("KUZEY - GÜNEY METRO HATTI İNŞAATI") == ""

    dedup_tr = _deduplicate_station_ratings([
        ("KUVVETLI_AKIM", [2500.0, 2500.0, 2000.0, 2000.0]),
        ("KUVVETLI_AKIM", [2500.0, 2000.0]),
        ("ZAYIF_AKIM", [2500.0, 2500.0, 2500.0, 2500.0, 2000.0]),
    ])
    assert dedup_tr == [2500.0, 2500.0, 2000.0, 2000.0]
    assert _format_kva_summary(dedup_tr) == "2×2500 kVA + 2×2000 kVA"





