# -*- coding: utf-8 -*-
"""
CloudeCAD v2.0 — Referans Test Projeleri ve Doğrulama Paketi (Gold-Standard Test Suite)
=======================================================================================
Bu test paketi sistemin 3 temel garantisini programatik olarak doğrular:
1. Varsayımsız Hesaplama (Zero-Assumption Calculation) ve Veri Kaynağı İzlenebilirliği
2. TS HD 60364-5-52 / 4-43 / BYKHY Mevzuat Doğruluğu ve Kural İzlenebilirliği
3. Bilinen Temiz, Hatalı ve Eksik Verili Referans Projelerde %100 Deterministik Sonuç
"""

from __future__ import annotations
import sys
from pathlib import Path
import pytest
import ezdxf

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "03_hesap_motoru"))

from core.engine import UnifiedAuditEngine
from core.rules.rule_engine import RuleEngine


def _add_symbol_block(doc: ezdxf.document.Drawing, name: str) -> None:
    if name not in doc.blocks:
        blk = doc.blocks.new(name=name)
        blk.add_circle((0, 0), radius=50, dxfattribs={"layer": "00-AYDINLATMA"})


def _add_metraj_table_block(
    doc: ezdxf.document.Drawing,
    block_name: str,
    rows: list[tuple[str, str, str, str, str]],
) -> None:
    """
    METRAJ_TABLOSU bloğu oluşturur:
    Sütunlar: x=0 (LİNYE NO), x=500 (KABLO KESİTİ), x=1000 (KABLO TİPİ), x=1500 (UZUNLUK (m)), x=2000 (GÜÇ (W))
    """
    blk = doc.blocks.new(name=block_name)
    headers = ["LİNYE NO", "KABLO KESİTİ", "KABLO TİPİ", "UZUNLUK (m)", "TOPLAM GÜÇ (W)"]
    col_x = [0.0, 500.0, 1000.0, 1500.0, 2000.0]
    y_header = 1000.0
    for cx, h_txt in zip(col_x, headers):
        blk.add_text(h_txt, dxfattribs={"insert": (cx, y_header), "height": 2.5})

    for idx, row in enumerate(rows, start=1):
        ry = y_header - idx * 20.0
        for cx, val in zip(col_x, row):
            blk.add_text(str(val), dxfattribs={"insert": (cx, ry), "height": 2.5})


# ==============================================================================
# TEST 1: TEMİZ REFERANS PROJE (0 HATA, %100 KESİN VERİ KAYNAĞI)
# ==============================================================================
def test_ref01_clean_pass_metro_station(tmp_path: Path):
    """
    Referans 01 (Temiz Proje):
    - Tüm armatür güçleri açıkça tanımlı (36W LED)
    - Tüm linye kesitleri ve kablo tipleri açıkça tanımlı (3x2.5 N2XH-J FE180)
    - Tüm linye mesafeleri metraj tablosunda açıkça tanımlı (20.0 m)
    - L1, L2, L3 faz yükleri tam dengeli (her fazda 5x36W = 180W, %0 dengesizlik)
    Beklenen:
    - 0 Kritik Hata, 0 Uyarı
    - Tüm devreler 'UYGUN', veri kaynakları 'EXPLICIT_*', varsayım listesi boş.
    """
    station_dir = tmp_path / "M09-S99_RefClean" / "01_Kuvvetli_Akim"
    station_dir.mkdir(parents=True, exist_ok=True)
    dxf_file = station_dir / "AG-USK-M09-S99-000-01-AY-01.dxf"

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    _add_symbol_block(doc, "ELC_ARMATUR_LED_36W")

    # 3 dengeli linye: A10101 (L1), A10102 (L2), A10103 (L3)
    circuits = [
        ("A10101", "L1", 1000.0, 1000.0),
        ("A10102", "L2", 5000.0, 1000.0),
        ("A10103", "L3", 9000.0, 1000.0),
    ]
    for c_prefix, phase, base_x, base_y in circuits:
        for i in range(5):
            sx = base_x + i * 200.0
            sy = base_y
            msp.add_blockref("ELC_ARMATUR_LED_36W", (sx, sy), dxfattribs={"layer": "00-AYDINLATMA"})
            msp.add_text(
                f"{c_prefix}/0{i+1}/{phase}",
                dxfattribs={"insert": (sx, sy + 60.0), "height": 20.0, "layer": "00-AYDINLATMA"},
            )
        # Kablo kesit ve tip etiketleri
        msp.add_text("3x2.5 N2XH-J FE180", dxfattribs={"insert": (base_x, base_y + 140.0), "height": 25.0, "layer": "00-AYDINLATMA"})

    # Metraj tablosu bloğu ekle
    _add_metraj_table_block(
        doc,
        "AYDINLATMA_METRAJ_TABLOSU",
        [
            ("A101-01", "3x2.5", "N2XH-J FE180", "20.0", "180"),
            ("A101-02", "3x2.5", "N2XH-J FE180", "20.0", "180"),
            ("A101-03", "3x2.5", "N2XH-J FE180", "20.0", "180"),
        ],
    )
    msp.add_blockref("AYDINLATMA_METRAJ_TABLOSU", (20000.0, 20000.0))
    doc.saveas(dxf_file)

    engine = UnifiedAuditEngine(use_cache=False, rule_pack="ibb_metro")
    report = engine.audit_station(
        station_dir=station_dir.parent,
        station_code="S99",
        station_name="Referans Temiz İstasyon",
    )

    crit = [f for f in report.findings if f.severity == "CRITICAL"]
    warn = [f for f in report.findings if f.severity == "WARNING"]

    assert report.station_code == "S99"
    assert len(crit) == 0, f"Temiz projede beklenmeyen kritik bulgu: {[f.code for f in crit]}"
    assert len(warn) == 0, f"Temiz projede beklenmeyen uyarı: {[f.code for f in warn]}"
    assert len(report.circuit_calculations) == 3

    for cc in report.circuit_calculations:
        assert cc.status == "UYGUN"
        assert cc.cable_source.startswith("EXPLICIT")
        assert cc.power_source.startswith("EXPLICIT")
        assert cc.length_source == "EXPLICIT_TABLE"
        assert cc.confidence_score >= 0.95
        assert cc.ampacity_iz_a == 25.2  # TS HD 60364-5-52 XLPE 90C Method E 2.5mm2 (36A) * 0.70 derating = 25.2 A
        assert cc.voltage_drop_pct is not None and cc.voltage_drop_pct < 0.5

    assert len(report.panel_summaries) == 1
    p = report.panel_summaries[0]
    assert p.panel_tag == "S99/İAP-N/101"
    assert p.imbalance_pct == 0.0
    assert p.power_source == "EXPLICIT"


# ==============================================================================
# TEST 2: BİLİNEN HATALI REFERANS PROJE (DETERMİNİSTİK HATA YAKALAMA & İZLENEBİLİRLİK)
# ==============================================================================
def test_ref02_known_violations_project(tmp_path: Path):
    """
    Referans 02 (Bilinen İhlaller):
    1. Aşırı Yüklenmiş Kablo (Ib > Iz):
       P10101/01/L1 linyesinde 3x1.5 N2XH-J FE180 kablo üzerinde 14 x 500W = 7000W yük
       (Ib = 33.54 A > Iz = 23.0 A) -> KA-AMP-P10101_01_L1 (CRITICAL)
    2. Aşırı Gerilim Düşümü (%e > %3.0):
       A10101/01/L1 linyesinde 3x1.5 N2XH-J FE180 kablo üzerinde 2000W yük ve 95.0 m mesafe
       (%e = 9.70% > %3.0) -> KA-VD-A10101_01_L1 (CRITICAL)
    3. Acil Aydınlatma Linyesinde FE180 Eksikliği:
       E10101/01/L1 acil linyesinde 3x2.5 NYM kablo -> KA-FE180-E10101_01_L1 (CRITICAL)
    4. Pano Faz Dengesizliği (> %25):
       P10101 panosunda L1=7000W, L2=500W, L3=500W -> KA-BAL-P10101 (CRITICAL)
    """
    station_dir = tmp_path / "M09-S98_RefViolations" / "01_Kuvvetli_Akim"
    station_dir.mkdir(parents=True, exist_ok=True)
    dxf_file = station_dir / "AG-USK-M09-S98-000-01-AY-01.dxf"

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    _add_symbol_block(doc, "ELC_PRIZ_500W")
    _add_symbol_block(doc, "ELC_ARMATUR_LED_200W")

    # 1) P10101/01/L1 -> 7000W on 3x1.5 (Ib > Iz)
    msp.add_blockref("ELC_PRIZ_500W", (1000.0, 1000.0), dxfattribs={"layer": "00-PRIZ"})
    msp.add_text("P10101/01/L1", dxfattribs={"insert": (1000.0, 1060.0), "height": 25.0, "layer": "00-PRIZ"})

    # P10102/01/L2 (500W) ve P10103/01/L3 (500W) -> Faz dengesizliği oluşturmak için
    msp.add_blockref("ELC_PRIZ_500W", (1000.0, 3000.0), dxfattribs={"layer": "00-PRIZ"})
    msp.add_text("P10102/01/L2", dxfattribs={"insert": (1000.0, 3060.0), "height": 25.0, "layer": "00-PRIZ"})

    msp.add_blockref("ELC_PRIZ_500W", (1000.0, 5000.0), dxfattribs={"layer": "00-PRIZ"})
    msp.add_text("P10103/01/L3", dxfattribs={"insert": (1000.0, 5060.0), "height": 25.0, "layer": "00-PRIZ"})

    # 2) A10101/01/L1 -> 2000W, 95m mesafe, 3x1.5 kablo (%e > %3.0)
    msp.add_blockref("ELC_ARMATUR_LED_200W", (8000.0, 1000.0), dxfattribs={"layer": "00-AYDINLATMA"})
    msp.add_text("A10101/01/L1", dxfattribs={"insert": (8000.0, 1060.0), "height": 25.0, "layer": "00-AYDINLATMA"})

    # 3) E10101/01/L1 -> Acil aydınlatma linyesinde NYM kablo (FE180 yok)
    msp.add_blockref("ELC_ARMATUR_LED_200W", (8000.0, 4000.0), dxfattribs={"layer": "00-AYDINLATMA"})
    msp.add_text("E10101/01/L1", dxfattribs={"insert": (8000.0, 4060.0), "height": 25.0, "layer": "00-AYDINLATMA"})

    _add_metraj_table_block(
        doc,
        "KUVVET_METRAJ_TABLOSU",
        [
            ("P101-01", "3x1.5", "N2XH-J FE180", "15.0", "7000"),
            ("P101-02", "3x2.5", "N2XH-J FE180", "15.0", "500"),
            ("P101-03", "3x2.5", "N2XH-J FE180", "15.0", "500"),
            ("A101-01", "3x1.5", "N2XH-J FE180", "95.0", "2000"),
            ("E101-01", "3x2.5", "NYM", "20.0", "200"),
        ],
    )
    msp.add_blockref("KUVVET_METRAJ_TABLOSU", (20000.0, 20000.0))
    doc.saveas(dxf_file)

    engine = UnifiedAuditEngine(use_cache=False, rule_pack="ibb_metro")
    report = engine.audit_station(
        station_dir=station_dir.parent,
        station_code="S98",
        station_name="Referans İhlal İstasyonu",
    )

    finding_map = {f.code: f for f in report.findings}

    # 1. Ampacity ihlali kontrolü
    assert "KA-AMP-S98-İAP-N-101-P101-01" in finding_map
    f_amp = finding_map["KA-AMP-S98-İAP-N-101-P101-01"]
    assert f_amp.severity == "CRITICAL"
    assert f_amp.confidence_level == "KESİN"
    assert "TS HD 60364" in f_amp.standard_version
    assert "B.52" in f_amp.clause_or_table
    assert f_amp.data_sources["cable"].startswith("EXPLICIT")

    # 2. Gerilim düşümü ihlali kontrolü
    assert "KA-VD-S98-İAP-N-101-A101-01" in finding_map
    f_vd = finding_map["KA-VD-S98-İAP-N-101-A101-01"]
    assert f_vd.severity == "CRITICAL"
    assert f_vd.confidence_level == "KESİN"
    assert "Bölüm 525" in f_vd.clause_or_table

    # 3. Acil linye FE180 ihlali kontrolü
    assert "KA-FE180-S98-İAP-E-101-E101-01" in finding_map
    f_fe = finding_map["KA-FE180-S98-İAP-E-101-E101-01"]
    assert f_fe.severity == "CRITICAL"
    assert "BYKHY" in f_fe.standard_version

    # 4. Pano faz dengesizliği kontrolü
    assert "KA-BAL-S98-İAP-N-101" in finding_map
    f_bal = finding_map["KA-BAL-S98-İAP-N-101"]
    assert f_bal.severity == "CRITICAL"
    assert f_bal.confidence_level == "KESİN"


# ==============================================================================
# TEST 3: EKSİK VERİLİ PROJE (VARSAYIMSIZ HESAP & BELİRSİZLİK YÖNETİMİ)
# ==============================================================================
def test_ref03_missing_data_and_uncertainties(tmp_path: Path):
    """
    Referans 03 (Eksik Veri ve Belirsizlik Yönetimi):
    - Kat planında armatürlerin gücü yazılı değil (ELC_ARMATUR_STANDART)
    - Kat planında linye etiketleri (A1, A2, P1) var fakat kablo kesiti (3x1.5 vb.) YAZILI DEĞİL.
    - Kolon şemasında 4x4 N2XH kablo + 3x32A şalter uyumsuzluğu mevcut.
    Beklenen:
    - Sistem asla gizlice '3x1.5' veya '3x2.5' uydurmamalı!
    - Kablo kesiti olmayan devreler 'VERİ_YETERSİZ' olarak işaretlenmeli (Iz=None, %e=None, güven=0.0).
    - Kablo kesiti olmayan devreler için sahte 'KA-AMP' veya 'KA-VD' hatası üretilmemeli.
    - 'UNC-MISSING-CABLE-SPEC' belirsizliği kaydedilmeli.
    - Sembol gücü çizimde olmadığından 'ESTIMATED_DEFAULT' olarak işaretlenmeli ve varsayım kaydedilmeli.
    - Açıkça yazılı olan 4x4mm2 + 32A koruma koordinasyon hatası KESİN olarak yakalanmalı.
    """
    dxf_file = tmp_path / "ref03_missing_data_bina.dxf"
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Güç bilgisi içermeyen sembol bloğu
    _add_symbol_block(doc, "ELC_ARMATUR_STANDART")

    # Alt pafta çerçevesi (ZEMİN KAT AYDINLATMA PLANI)
    msp.add_lwpolyline(
        [(0, 0), (6000, 0), (6000, 4000), (0, 4000), (0, 0)],
        dxfattribs={"layer": "00-CERCEVE"},
    )
    msp.add_text("ZEMİN KAT AYDINLATMA PLANI", dxfattribs={"insert": (500, 3800), "height": 50.0})

    # A1 linyesi (kablo kesiti etiketi YOK!)
    for i in range(4):
        msp.add_blockref(
            "ELC_ARMATUR_STANDART",
            (1000.0 + i * 200.0, 2000.0),
            dxfattribs={"layer": "00-AYDINLATMA"},
        )
    msp.add_text("A1", dxfattribs={"insert": (1000.0, 2080.0), "height": 25.0, "layer": "00-AYDINLATMA"})

    # Kolon şemasında açıkça yazılı 4x4 N2XH ve 3x32A AOS + 4x25A KAK hatası
    msp.add_text("4x4 N2XH", dxfattribs={"insert": (7000.0, 2000.0), "height": 25.0})
    msp.add_text("3x32A AOS", dxfattribs={"insert": (7000.0, 1900.0), "height": 25.0})
    msp.add_text("4x25A 30mA KAK", dxfattribs={"insert": (7000.0, 1800.0), "height": 25.0})

    doc.saveas(dxf_file)

    engine = UnifiedAuditEngine(use_cache=False, rule_pack="turkey_bina")
    report = engine.audit_single_dwg_project(
        dwg_path=dxf_file,
        explicit_station_code="BINA03",
    )

    assert len(report.circuit_calculations) >= 1
    cc_a1 = report.circuit_calculations[0]
    assert cc_a1.cable_cross_section == "BELİRTİLMEMİŞ"
    assert cc_a1.cable_source == "MISSING"
    assert cc_a1.power_source == "ESTIMATED_DEFAULT"
    assert cc_a1.ampacity_iz_a is None
    assert cc_a1.voltage_drop_pct is None
    assert cc_a1.status == "VERİ_YETERSİZ"
    assert cc_a1.confidence_score == 0.0
    assert len(cc_a1.assumptions_used) > 0

    # Eksik kablolu devre için sahte KA-AMP veya KA-VD hatası üretilmemeli
    finding_codes = {f.code for f in report.findings}
    assert not any(c.startswith("KA-AMP-") for c in finding_codes)
    assert not any(c.startswith("KA-VD-") for c in finding_codes)

    # Belirsizlik listesinde UNC-MISSING-CABLE-SPEC olmalı
    unc_codes = {u.code for u in report.uncertainties}
    assert "UNC-MISSING-CABLE-SPEC" in unc_codes

    # Açıkça yazılı olan koruma koordinasyon hatası yakalanmalı ve standart maddesi izlenebilir olmalı
    assert "KORUMA-KOORDINASYON-4MM2-32A" in finding_codes
    f_coord = next(f for f in report.findings if f.code == "KORUMA-KOORDINASYON-4MM2-32A")
    assert f_coord.severity == "CRITICAL"
    assert "433.1" in f_coord.clause_or_table


# ==============================================================================
# TEST 4: TS HD 60364-5-52 TABLO DOĞRULUĞU VE BİLİNMEYEN KESİT GÜVENLİĞİ
# ==============================================================================
def test_ref04_tshd60364_ampacity_table_accuracy():
    """
    TS HD 60364-5-52:2014 Çizelge B.52.2 - B.52.5 değerlerinin yalıtım tipi (PVC 70C vs XLPE 90C),
    döşeme yöntemi (B1, C, E) ve yüklü iletken sayısına (1 Faz vs 3 Faz) göre doğruluğunu test eder.
    """
    re_bina = RuleEngine("turkey_bina")

    # 1) 2.5 mm² NYM (PVC 70C), Yöntem C, 1 Faz (2 yüklü iletken) -> Tablo: 27.0 A, Derated (x0.85): 22.9 A
    iz_raw, clause1, _ = re_bina.get_ampacity_detailed(
        2.5, "NYM", is_3phase=False, install_method="C", apply_derating=False
    )
    assert iz_raw == 27.0
    assert "PVC_70C" in clause1 and "Yöntem C" in clause1

    iz_derated, _, _ = re_bina.get_ampacity_detailed(
        2.5, "NYM", is_3phase=False, install_method="C", apply_derating=True
    )
    assert iz_derated == 22.9

    # 2) 4.0 mm² N2XH (XLPE 90C), Yöntem B1, 3 Faz (3 yüklü iletken) -> Tablo: 37.0 A, Derated (x0.85): 31.4 A
    iz_xlpe_b1_3p, clause2, _ = re_bina.get_ampacity_detailed(
        4.0, "N2XH", is_3phase=True, install_method="B1", apply_derating=False
    )
    assert iz_xlpe_b1_3p == 37.0
    assert "XLPE_90C" in clause2 and "3_LOADED" in clause2

    # 3) 4.0 mm² NYM (PVC 70C), Yöntem B1, 3 Faz (3 yüklü iletken) -> Tablo: 28.0 A, Derated (x0.85): 23.8 A
    iz_pvc_b1_3p, _, _ = re_bina.get_ampacity_detailed(
        4.0, "NYM", is_3phase=True, install_method="B1", apply_derating=True
    )
    assert iz_pvc_b1_3p == 23.8

    # 4) Standart dışı kesit (999 mm²) -> Asla 25A varsaymamalı, None dönmeli
    iz_unknown, clause_unk, _ = re_bina.get_ampacity_detailed(999.0, "N2XH", is_3phase=False)
    assert iz_unknown is None
    assert "Tanımsız" in clause_unk


# ==============================================================================
# TEST 5: İSTASYON KODU ÖNCELİK HİYERARŞİSİ, ANTET UYUŞMAZLIĞI VE RAPORLAYICI
# ==============================================================================
def test_ref05_station_code_priority_and_markdown_reporter(tmp_path: Path):
    """
    Referans 05:
    - Dosya adı 'AG-USK-M09-S24-000-99-TL-02-A-T-2I-001.dxf' (S24 Çobançeşme)
    - Ancak pafta içinde başka istasyondan kalan 'S28' metni ve 'Mimar Sinan İstasyonu İletim Sistemi Projesi' başlığı var.
    Beklenen:
    - İstasyon kodu S28 değil, kesinlikle S24 (Çobançeşme - Kuyumcukent İstasyonu) olmalı.
    - 'ANTET-BASLIK-UYUSMAZLIGI' uyarısı otomatik olarak yakalanmalı.
    - Zayıf akım paftası olduğu için asla 'YUKLEME-CETVELI-EKSIK' uyarısı üretilmemeli.
    - Markdown raporu hatasız üretilmeli ve kural izlenebilirlik alanlarını içermeli.
    """
    from core.reporters.markdown_reporter import generate_markdown_report

    dxf_file = tmp_path / "AG-USK-M09-S24-000-99-TL-02-A-T-2I-001.dxf"
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_text("S28 REFERANS NOTU", dxfattribs={"insert": (100, 500), "height": 10.0})
    msp.add_text(
        "Mimar Sinan İstasyonu İletim Sistemi Projesi",
        dxfattribs={"insert": (100, 100), "height": 20.0},
    )
    doc.saveas(dxf_file)

    engine = UnifiedAuditEngine(use_cache=False, rule_pack="ibb_metro")
    report = engine.audit_single_dwg_project(dwg_path=dxf_file)

    assert report.station_code == "S24"
    assert "Çobançeşme" in report.station_name

    finding_codes = {f.code for f in report.findings}
    assert "REC-STATION-TITLE-MISMATCH" in finding_codes
    assert "YUKLEME-CETVELI-EKSIK" not in finding_codes

    md_text = generate_markdown_report(report)
    assert "S24" in md_text
    assert "REC-STATION-TITLE-MISMATCH" in md_text


# ==============================================================================
# TEST 6: SEMBOL TRİYAJI (anonim blok tek başına silinmez)
# ==============================================================================
def test_ref06_symbol_triage_evidence_based():
    from shapely.geometry import box
    from core.cad.triage import SymbolTriage
    from core.model.entities import PlacedSymbol, TextToken

    def mk(name, layer, x, y, parent="", cls="EQUIPMENT"):
        return PlacedSymbol(
            block_name=name, clean_family_name=name, pos=(x, y, 0.0), scale=(1, 1, 1),
            rotation=0.0, layer=layer, color=256, bbox=box(x, y, x + 1, y + 1),
            parent_view=parent, classification=cls,
        )

    ref_lum = mk("ELC_ARMATUR_LED_36W", "00-AYDINLATMA", 0, 0, cls="LUMINAIRE")
    anon_arch = mk("A$C1234ABCD", "MOBILYA", 50000, 50000, parent="M3-ARC XREF")        # mimari kanıt, elektrik yok
    anon_elec_layer = mk("A$C9999EEEE", "E-POWER", 60000, 60000)                          # elektrik katmanı
    anon_near_elec = mk("A$CNEAR0001", "0", 300, 300)                                     # elektrik sembolüne yakın
    anon_unknown = mk("1LL", "0", 90000, 90000)                                           # kanıt yok
    anon_arch_but_elec = mk("MOBILYA_X", "MOBILYA", 400, 0)                               # mimari ama armatür yanında
    syms = [ref_lum, anon_arch, anon_elec_layer, anon_near_elec, anon_unknown, anon_arch_but_elec]

    counts = SymbolTriage.triage(syms, [])

    assert anon_arch.classification == "IGNORED_ARCHITECTURAL"
    assert anon_elec_layer.classification == "EQUIPMENT" and anon_elec_layer.triage_status == "UNCERTAIN_ELECTRICAL"
    assert anon_near_elec.triage_status == "UNCERTAIN_ELECTRICAL"
    assert anon_unknown.triage_status == "UNCLASSIFIED" and anon_unknown.classification == "EQUIPMENT"
    assert anon_arch_but_elec.triage_status == "UNCERTAIN_ELECTRICAL"   # çelişkide silinmez
    assert counts == {"IGNORED_ARCHITECTURAL": 1, "UNCERTAIN_ELECTRICAL": 3, "UNCLASSIFIED": 1}


def test_ref07_metro_sheet_codes_and_station_grounding_are_dynamic():
    from shapely.geometry import box
    from core.engine import (
        UnifiedAuditEngine,
        is_grounding_sheet_filename,
        is_power_sheet_filename,
    )
    from core.model.audit import StationAuditReport
    from core.model.entities import DrawingSceneGraph, TextToken

    assert is_power_sheet_filename("AG-PRT-M09-S19-BT0-00-PS-08-A-T-2I-001-A.dwg")
    assert is_grounding_sheet_filename("AG-PRT-M09-S19-BT0-00-GN-14-A-T-2I-001-A.dwg")

    text = TextToken(
        text="S19/ECB/01",
        pos=(0.0, 0.0, 0.0),
        height=2.5,
        rotation=0.0,
        layer="02-TOPRAKLAMA",
        color=256,
        bbox=box(0, 0, 1, 1),
    )
    bond_text = TextToken(
        text="TS19LVS401/S19MCC301/01",
        pos=(10.0, 0.0, 0.0),
        height=2.5,
        rotation=0.0,
        layer="02-TOPRAKLAMA",
        color=256,
        bbox=box(10, 0, 11, 1),
    )
    scene = DrawingSceneGraph(
        filepath="S19-PS-17.dwg",
        filename="AG-PRT-M09-S19-BT0-00-PS-17-A-T-2I-001-A.dwg",
        station_code="S19",
        station_name="Masko İstasyonu",
        sheet_title="",
        system_discipline="02_TOPRAKLAMA",
        floor_name="BT0",
        elevation_kot=None,
        sub_plans=[],
        symbol_dictionary={},
        symbols=[],
        texts=[text, bond_text],
        callouts=[],
        tables=[],
        physical_routes=[],
        logical_circuits=[],
        raw_stats={},
    )
    report = StationAuditReport(
        station_code="S19",
        station_name="Masko İstasyonu",
        total_sheets_analyzed=1,
    )

    UnifiedAuditEngine(use_cache=False, rule_pack="ibb_metro")._run_module4_grounding_and_trays(
        {scene.filename: scene}, report
    )

    assert len(report.grounding_tray_summaries) == 1
    summary = report.grounding_tray_summaries[0]
    assert summary.ecb_bars == ["S19/ECB/01"]
    assert summary.ts28_panel_bonds == ["TS19LVS401/S19MCC301/01"]


# ==============================================================================
# TEST 8: KADEMELİ TOPRAKLAMA EŞLEŞTİRME VE KANITA BAĞLI ŞİDDET YÖNETİMİ
# ==============================================================================
def test_ref08_graduated_grounding_reconciliation():
    """
    Kademeli topraklama çapraz mutabakatı ve kanıta bağlı şiddet kuralı:
    1. Birebir veya kompozit alt parça (TS19LVS401/S19MCC301/01 -> S19MCC301) eşleşir -> UYGUN (güven >= 0.85).
    2. Kat topraklama paftası eksik olan pano (CT0 katı için PS-17 yok) -> HATA DEĞİL, UncertaintyItem üretilir.
    3. Kat topraklama paftası mevcut olup bulunamayan pano -> Asla CRITICAL değil, WARNING (REC-GRND-MISSING).
    """
    from shapely.geometry import box
    from core.model.entities import DrawingSceneGraph, TextToken, LogicalCircuit
    from core.model.audit import StationAuditReport
    from core.reconciliation.cross_sheet_engine import CrossSheetReconciliationEngine

    # BT0 Katı Kuvvetli Akım Paftası (PS-16): S19LVS401, S19MCC301 ve topraklamasız S19PANEL_X
    scene_ka_bt0 = DrawingSceneGraph(
        filepath="S19-BT0-PS-16.dwg",
        filename="AG-PRT-M09-S19-BT0-00-PS-16-A-T-2I-001-A.dwg",
        station_code="S19",
        station_name="Masko İstasyonu",
        sheet_title="",
        system_discipline="01_KUVVETLI_AKIM",
        floor_name="BT0",
        elevation_kot=None,
        sub_plans=[],
        symbol_dictionary={},
        symbols=[],
        texts=[],
        callouts=[],
        tables=[],
        physical_routes=[],
        logical_circuits=[
            LogicalCircuit(panel_tag="S19LVS401", circuit_no="L1", phase="R"),
            LogicalCircuit(panel_tag="S19MCC301", circuit_no="L2", phase="S"),
            LogicalCircuit(panel_tag="S19PANEL_X", circuit_no="L3", phase="T"),
        ],
        raw_stats={},
    )

    # CT0 Katı Kuvvetli Akım Paftası (PS-16): S19PANEL_CT0 (Bu katın topraklama paftası analiz setinde yok!)
    scene_ka_ct0 = DrawingSceneGraph(
        filepath="S19-CT0-PS-16.dwg",
        filename="AG-PRT-M09-S19-CT0-2A-PS-16-A-T-2I-001-A.dwg",
        station_code="S19",
        station_name="Masko İstasyonu",
        sheet_title="",
        system_discipline="01_KUVVETLI_AKIM",
        floor_name="CT0",
        elevation_kot=None,
        sub_plans=[],
        symbol_dictionary={},
        symbols=[],
        texts=[],
        callouts=[],
        tables=[],
        physical_routes=[],
        logical_circuits=[
            LogicalCircuit(panel_tag="S19PANEL_CT0", circuit_no="L1", phase="R"),
        ],
        raw_stats={},
    )

    # Sadece BT0 Katı Topraklama Paftası (PS-17) analiz setinde var
    scene_tp_bt0 = DrawingSceneGraph(
        filepath="S19-BT0-PS-17.dwg",
        filename="AG-PRT-M09-S19-BT0-00-PS-17-A-T-2I-001-A.dwg",
        station_code="S19",
        station_name="Masko İstasyonu",
        sheet_title="",
        system_discipline="02_TOPRAKLAMA",
        floor_name="BT0",
        elevation_kot=None,
        sub_plans=[],
        symbol_dictionary={},
        symbols=[],
        texts=[
            TextToken(text="S19/ECB/051", pos=(0, 0, 0), height=2.5, rotation=0, layer="02-TOPRAKLAMA", color=256, bbox=box(0, 0, 1, 1)),
            TextToken(text="TS19LVS401/S19MCC301/01", pos=(10, 0, 0), height=2.5, rotation=0, layer="02-TOPRAKLAMA", color=256, bbox=box(10, 0, 11, 1)),
        ],
        callouts=[],
        tables=[],
        physical_routes=[],
        logical_circuits=[],
        raw_stats={},
    )

    scenes = {
        scene_ka_bt0.filename: scene_ka_bt0,
        scene_ka_ct0.filename: scene_ka_ct0,
        scene_tp_bt0.filename: scene_tp_bt0,
    }

    report = StationAuditReport(
        station_code="S19",
        station_name="Masko İstasyonu",
        total_sheets_analyzed=3,
    )

    CrossSheetReconciliationEngine.reconcile_panels_vs_grounding_sheets(scenes, report)

    # 1. Kontrol: S19LVS401 ve S19MCC301 başarıyla eşleşmeli
    reconciled_map = {item.item_id: item for item in report.reconciliation_items}
    assert "S19LVS401" in reconciled_map
    assert reconciled_map["S19LVS401"].status == "UYGUN"
    assert reconciled_map["S19LVS401"].confidence_score >= 0.85

    assert "S19MCC301" in reconciled_map
    assert reconciled_map["S19MCC301"].status == "UYGUN"
    assert reconciled_map["S19MCC301"].confidence_score >= 0.85

    # 2. Kontrol: S19PANEL_CT0 katının topraklama paftası yok -> Kesinlikle HATA DEĞİL, Belirsizlik (Uncertainty)
    assert "S19PANEL_CT0" in reconciled_map
    assert reconciled_map["S19PANEL_CT0"].status == "İNCELEME_GEREKLİ"
    unc_codes = {u.code for u in report.uncertainties}
    assert any("UNC-GRND-SHEET-MISSING" in c for c in unc_codes)

    # 3. Kontrol: S19PANEL_X BT0 katında, o katın PS-17'si var ama pano bulunamadı -> WARNING (CRITICAL DEĞİL!)
    assert "S19PANEL_X" in reconciled_map
    assert reconciled_map["S19PANEL_X"].status == "EKSİK"

    findings = [f for f in report.findings if f.code == "REC-GRND-MISSING"]
    assert len(findings) == 1
    f_grnd = findings[0]
    assert f_grnd.severity == "WARNING"  # CRITICAL asla olmamalı
    assert f_grnd.confidence_level == "MUHTEMEL"
    assert f_grnd.confidence_score == 0.70
    assert "S19PANEL_X" in f_grnd.element_id
    assert "S19PANEL_CT0" not in f_grnd.element_id  # Katı olmayan pano hataya dahil edilmemeli


# ==============================================================================
# TEST 9: MODÜL 1 (LayerAndBlockDoctor) VE CAD_SAFETY 3 TUZAK DOĞRULAMASI
# ==============================================================================
def test_ref09_layer_doctor_and_cad_safety(tmp_path: Path):
    """
    Modül 1 (LayerAndBlockDoctor) ve cad_safety.py kütüphanesinin pazarlığa kapalı
    kurallarını doğrular:
    1. Tuzak 1 (XREF Dokunulmazlığı): XREF blok içi geometri ve XREF INSERT referansları
       asla taşınmaz, çökmez, safety_skipped_counts içine kaydedilir.
    2. Tuzak 2 (Block Def vs INSERT Ayrımı): Ortak bir blok tanımının (ORTAK_TEFRIS)
       bir örneği IGNORED_ARCHITECTURAL olarak 'A-MIMARI-ALTYAPI' katmanına taşındığında
       yalnızca o INSERT taşınır; blok tanımı (doc.blocks) ve elektrik armatürü yanındaki
       ikinci INSERT (UNCERTAIN_ELECTRICAL) korunur!
    3. Tuzak 3 (CTB / Lineweight / Kilit Koruması): 'A-MIMARI-ALTYAPI' katmanı Color 8 (Gri),
       lineweight=9 (0.09mm ince baskı) ve KİLİTLİ (is_locked=True) olarak üretilir;
       taşınan nesneler BYLAYER (color=256, lineweight=-1) yapılır.
    4. cad_safety: INSUNITS dinamik ölçekleme (mm vs metre), MTEXT biçim koruma (\fArial...;)
       ve ATTRIB vs ATTDEF koruması.
    """
    import json
    from shapely.geometry import box
    from core.cad.cad_safety import CADSafetyGuard, UnitScaleResolver
    from core.cad.triage import SymbolTriage
    from core.healer.layer_doctor import LayerAndBlockDoctor
    from core.model.entities import PlacedSymbol

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6  # 6 = Metre birimli pafta!
    msp = doc.modelspace()

    # --- 1) INSUNITS Ölçekleme Doğrulaması (20 cm = Metre paftada 0.20 birim!) ---
    tol_20cm_in_m = UnitScaleResolver.cm_to_drawing_units(20.0, doc)
    assert abs(tol_20cm_in_m - 0.20) < 1e-6

    doc_mm = ezdxf.new("R2018")
    doc_mm.header["$INSUNITS"] = 4  # 4 = Milimetre birimli pafta!
    tol_20cm_in_mm = UnitScaleResolver.cm_to_drawing_units(20.0, doc_mm)
    assert abs(tol_20cm_in_mm - 200.0) < 1e-6

    # --- 2) XREF Blok Tanımı ve XREF INSERT (Tuzak 1) ---
    xref_blk = doc.blocks.new(name="M3-ARC_XREF_KAT1")
    xref_internal_line = xref_blk.add_line((0, 0), (10, 10), dxfattribs={"layer": "XREF_DUVAR"})
    xref_ins = msp.add_blockref("M3-ARC_XREF_KAT1", (0, 0), dxfattribs={"layer": "0"})

    # --- 3) Paylaşılan Blok Tanımı ve 2 Farklı INSERT Örneği (Tuzak 2) ---
    shared_blk = doc.blocks.new(name="A$C_ORTAK_BLOK")
    blk_circle = shared_blk.add_circle((0, 0), radius=1.0, dxfattribs={"layer": "0", "color": 1})
    attdef = shared_blk.add_attdef(tag="ETIKET", insert=(0, 0), text="VARSAYILAN", dxfattribs={"height": 0.2})

    # Örnek A: Uzakta, MOBILYA katmanında -> Kanıtlı IGNORED_ARCHITECTURAL
    ins_arch = msp.add_blockref("A$C_ORTAK_BLOK", (50000, 50000), dxfattribs={"layer": "MOBILYA", "color": 3})

    # Örnek B: Armatürün hemen yanında -> UNCERTAIN_ELECTRICAL (Otomatik mimariye ATILMAMALI!)
    ins_near_elec = msp.add_blockref("A$C_ORTAK_BLOK", (105, 100), dxfattribs={"layer": "0", "color": 4})

    # --- 4) Gerçek Elektrik Sembolü (LUMINAIRE) ve ATTRIB Testi ---
    lum_blk = doc.blocks.new(name="ELC_LED_60x60")
    lum_blk.add_circle((0, 0), radius=0.3, dxfattribs={"layer": "0"})
    ins_lum = msp.add_blockref("ELC_LED_60x60", (100, 100), dxfattribs={"layer": "0", "color": 1})
    att_lum = ins_lum.add_attrib("LINYE", "W1-OLD", insert=(100, 100))

    # --- 5) MTEXT Biçim Korumalı Metin Güncelleme Testi ---
    mtext_ent = msp.add_mtext(r"{\fArial|b1|i0;\C1;4x4 N2XH}", dxfattribs={"insert": (100, 102), "layer": "0"})

    # Sembol Nesnelerini Hazırla ve Triyajdan Geçir
    sym_lum = PlacedSymbol(
        block_name="ELC_LED_60x60",
        clean_family_name="ELC_LED_60x60",
        pos=(100.0, 100.0, 0.0),
        scale=(1, 1, 1),
        rotation=0.0,
        layer="0",
        color=1,
        bbox=box(99, 99, 101, 101),
        classification="LUMINAIRE",
        confidence_score=1.0,
        dxf_handle=ins_lum.dxf.handle,
    )
    sym_arch = PlacedSymbol(
        block_name="A$C_ORTAK_BLOK",
        clean_family_name="A$C_ORTAK_BLOK",
        pos=(50000.0, 50000.0, 0.0),
        scale=(1, 1, 1),
        rotation=0.0,
        layer="MOBILYA",
        color=3,
        bbox=box(49999, 49999, 50001, 50001),
        classification="EQUIPMENT",
        dxf_handle=ins_arch.dxf.handle,
    )
    sym_near = PlacedSymbol(
        block_name="A$C_ORTAK_BLOK",
        clean_family_name="A$C_ORTAK_BLOK",
        pos=(105.0, 100.0, 0.0),
        scale=(1, 1, 1),
        rotation=0.0,
        layer="0",
        color=4,
        bbox=box(104, 99, 106, 101),
        classification="EQUIPMENT",
        dxf_handle=ins_near_elec.dxf.handle,
    )

    SymbolTriage.triage([sym_lum, sym_arch, sym_near], [])
    assert sym_arch.classification == "IGNORED_ARCHITECTURAL"
    assert sym_near.triage_status == "UNCERTAIN_ELECTRICAL"

    # --- LayerAndBlockDoctor: Öneri Planı Üret ---
    plan = LayerAndBlockDoctor.analyze_and_propose(
        doc,
        symbols=[sym_lum, sym_arch, sym_near],
        routes=[],
        drawing_name="test_doctor.dxf",
    )

    # XREF iç çizgisi ve XREF INSERT'ü kesinlikle korunmuş olmalı
    assert plan.safety_skipped_counts.get("XREF_INTERNAL_ENTITY_READONLY", 0) >= 1
    assert plan.safety_skipped_counts.get("XREF_INSERT_REFERENCE_PROTECTED", 0) >= 1

    # sym_near (UNCERTAIN_ELECTRICAL) auto_approvable=False ve REQUIRES_APPROVAL olmalı
    prop_near = next(p for p in plan.proposals if p.dxf_handle == ins_near_elec.dxf.handle)
    assert prop_near.auto_approvable is False
    assert prop_near.status == "REQUIRES_APPROVAL"

    # --- Planı Uygula ve Dosyaları Üret ---
    cleaned_dxf = tmp_path / "cleaned.dxf"
    plan_json = tmp_path / "change_plan.json"
    ledger_json = tmp_path / "applied_changes.json"

    applied = LayerAndBlockDoctor.apply_plan(
        doc,
        plan,
        output_dxf_path=cleaned_dxf,
        change_plan_path=plan_json,
        applied_ledger_path=ledger_json,
    )

    assert cleaned_dxf.exists()
    assert plan_json.exists()
    assert ledger_json.exists()
    assert len(applied) == 2  # Sadece sym_lum ve sym_arch otomatik onaylanıp taşınmalı

    # --- DOĞRULAMA 1: XREF Dokunulmazlığı ---
    assert xref_internal_line.dxf.layer == "XREF_DUVAR"
    assert xref_ins.dxf.layer == "0"

    # --- DOĞRULAMA 2: Block Def vs INSERT Ayrımı ---
    # ins_arch 'A-MIMARI-ALTYAPI' katmanına taşındı:
    assert ins_arch.dxf.layer == "A-MIMARI-ALTYAPI"
    assert ins_arch.dxf.color == 256        # BYLAYER
    assert ins_arch.dxf.lineweight == -1    # BYLAYER
    # AMA aynı bloğun tanımı (blk_circle) ve diğer örneği (ins_near_elec) ASLA değişmedi!
    assert blk_circle.dxf.layer == "0"
    assert blk_circle.dxf.color == 1
    assert ins_near_elec.dxf.layer == "0"

    # --- DOĞRULAMA 3: CTB / Lineweight / Kilit Koruması ---
    arch_layer = doc.layers.get("A-MIMARI-ALTYAPI")
    assert arch_layer.color == 8
    assert arch_layer.dxf.lineweight == 9   # 0.09mm ince baskı
    assert arch_layer.is_locked() is True

    lum_layer = doc.layers.get("E-AYDINLATMA-ARMATUR")
    assert ins_lum.dxf.layer == "E-AYDINLATMA-ARMATUR"
    assert ins_lum.dxf.color == 256
    assert lum_layer.dxf.lineweight == 25   # 0.25mm standart elektrik sembol kalınlığı
    assert lum_layer.is_locked() is False

    # --- DOĞRULAMA 4: MTEXT Biçim Koruması ve ATTRIB vs ATTDEF Kalkanı ---
    ok_mt, msg_mt, _ = CADSafetyGuard.safe_update_text_entity(
        doc, mtext_ent.dxf.handle, "4x4 NHXH FE180", old_substring="4x4 N2XH"
    )
    assert ok_mt is True
    assert mtext_ent.text == r"{\fArial|b1|i0;\C1;4x4 NHXH FE180}"

    # Blok tanımı içindeki ATTDEF'i değiştirmeye çalışırsak güvenlik kalkanı reddetmeli!
    ok_attdef, msg_attdef, _ = CADSafetyGuard.safe_update_text_entity(
        doc, attdef.dxf.handle, "YENI"
    )
    assert ok_attdef is False
    assert "BLOCK_DEFINITION_IMMUTABLE" in msg_attdef
    assert attdef.dxf.text == "VARSAYILAN"

    # INSERT'e bağlı ATTRIB örneğini değiştirmek ise güvenli ve başarılı olmalı!
    ok_att, msg_att, _ = CADSafetyGuard.safe_update_text_entity(
        doc, att_lum.dxf.handle, "W1-NEW"
    )
    assert ok_att is True
    assert att_lum.dxf.text == "W1-NEW"

    # Mesuliyet defterinde (applied_changes.json) imzalı kayıtların kontrolü
    ledger_data = json.loads(ledger_json.read_text(encoding="utf-8"))
    assert ledger_data["total_applied"] == 2
    assert all(len(item["signature_hash"]) == 16 for item in ledger_data["applied_changes"])


# ==============================================================================
# TEST 10: MODÜL 2 (TopologicalWireHealer) 4 ŞARTLI STITCH, SNAP VE OVERKILL
# ==============================================================================
def test_ref10_topological_wire_healer_4_conditions(tmp_path: Path):
    """
    Modül 2 (TopologicalWireHealer) pazarlığa kapalı kurallarını doğrular:
    1. Duplicate Cleaner (OVERKILL): Üst üste binmiş mükerrer çizgiyi yakalar ve siler.
    2. Collinear Stitcher (4 Şartın Tamamı Sağlandığında):
       Aynı katman + doğrusal hizalı (köprü açısı <= 5°) + arada sembol/engel yok + aynı devre (W1)
       -> auto_approvable=True olarak köprülenir.
    3. Mayın Koruması A (Yan Yana Paralel İki Hat):
       Uçları birbirine 10 cm yakın ama yan yana paralel giden iki kabloda köprü açısı ~90° olduğu için
       ASLA otomatik birleştirilmez (auto_approvable=False, status='REQUIRES_APPROVAL').
    4. Mayın Koruması B (Farklı Devre Etiketleri W1 vs W2):
       Doğrusal hizalı olsa bile uçlarda W1 ve W2 yazıyorsa ASLA otomatik birleştirilmez
       (auto_approvable=False, status='REQUIRES_APPROVAL').
    5. Symbol Snapper ve INSUNITS Ölçekleme:
       Metre birimli ($INSUNITS=6) çizimde 12 cm (0.12 m) açık kalmış kablo ucu armatüre mıknatıslanır.
    """
    from shapely.geometry import box
    from core.healer.wire_healer import TopologicalWireHealer
    from core.model.entities import PlacedSymbol, TextToken

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6  # 6 = Metre birimli çizim (20 cm = 0.20 birim!)
    msp = doc.modelspace()

    # 1) Üst üste mükerrer çizgi (OVERKILL adayı)
    dup_a = msp.add_line((0.0, 0.0), (2.0, 0.0), dxfattribs={"layer": "E-KABLO-AYDINLATMA"})
    dup_b = msp.add_line((0.0, 0.0), (2.0, 0.0), dxfattribs={"layer": "E-KABLO-AYDINLATMA"})

    # 2) 4/4 Koşulu Sağlayan Kopuk Kablo (15 cm = 0.15 m boşluk, ikisi de W1 devresi, doğrusal)
    col_a = msp.add_line((10.0, 0.0), (12.0, 0.0), dxfattribs={"layer": "E-KABLO-AYDINLATMA"})
    col_b = msp.add_line((12.15, 0.0), (14.0, 0.0), dxfattribs={"layer": "E-KABLO-AYDINLATMA"})

    # 3) MAYIN A: Yan yana paralel uzanan iki hat (aralarındaki mesafe 10 cm = 0.10 m, uçları hizalı!)
    par_a = msp.add_line((20.0, 0.0), (22.0, 0.0), dxfattribs={"layer": "E-KABLO-PRIZ"})
    par_b = msp.add_line((22.0, 0.10), (24.0, 0.10), dxfattribs={"layer": "E-KABLO-PRIZ"})

    # 4) MAYIN B: Doğrusal hizalı ama farklı devre etiketli (W1 vs W2) iki hat (15 cm boşluk)
    diff_a = msp.add_line((30.0, 0.0), (32.0, 0.0), dxfattribs={"layer": "E-KABLO-AYDINLATMA"})
    diff_b = msp.add_line((32.15, 0.0), (34.0, 0.0), dxfattribs={"layer": "E-KABLO-AYDINLATMA"})

    # 5) Sembole 4 cm (0.04 m <= 5 cm mikro snap sınırı) mesafede açık kalmış kablo ucu (Otomatik Snap adayı)
    snap_line = msp.add_line((40.0, 0.0), (41.96, 0.0), dxfattribs={"layer": "E-KABLO-AYDINLATMA"})
    sym_target = PlacedSymbol(
        block_name="ELC_ARMATUR",
        clean_family_name="ELC_ARMATUR",
        pos=(42.0, 0.0, 0.0),
        scale=(1, 1, 1),
        rotation=0.0,
        layer="E-AYDINLATMA-ARMATUR",
        color=2,
        bbox=box(41.95, -0.05, 42.05, 0.05),
        classification="LUMINAIRE",
        confidence_score=0.95,
        dxf_handle="SYM_H1",
    )

    texts = [
        TextToken(text="W1", pos=(11.0, 0.05, 0.0), height=0.1, rotation=0.0, layer="0", color=7, bbox=box(10.9, 0, 11.1, 0.1)),
        TextToken(text="W1", pos=(13.0, 0.05, 0.0), height=0.1, rotation=0.0, layer="0", color=7, bbox=box(12.9, 0, 13.1, 0.1)),
        TextToken(text="W1", pos=(31.0, 0.05, 0.0), height=0.1, rotation=0.0, layer="0", color=7, bbox=box(30.9, 0, 31.1, 0.1)),
        TextToken(text="W2", pos=(33.0, 0.05, 0.0), height=0.1, rotation=0.0, layer="0", color=7, bbox=box(32.9, 0, 33.1, 0.1)),
    ]

    plan = TopologicalWireHealer.analyze_and_propose(
        doc,
        symbols=[sym_target],
        texts=texts,
        drawing_name="test_wire_healer.dxf",
        max_stitch_gap_cm=20.0,
        max_snap_gap_cm=15.0,
    )

    # INSUNITS=6 (Metre) olduğu için 20 cm = 0.20 çizim birimi olarak çözümlenmeli
    assert abs(plan.max_stitch_gap_units - 0.20) < 1e-6
    assert plan.summary_counts["duplicates_found"] == 1
    assert plan.summary_counts["collinear_stitches_auto"] == 1
    assert plan.summary_counts["collinear_stitches_blocked"] == 2
    assert plan.summary_counts["symbol_snaps"] == 1

    # Mayın A (Yan yana paralel kablolar) kesinlikle REQUIRES_APPROVAL olmalı
    prop_par = next(
        p for p in plan.proposals
        if {p.primary_handle, p.secondary_handle} == {par_a.dxf.handle, par_b.dxf.handle}
    )
    assert prop_par.auto_approvable is False
    assert prop_par.status == "REQUIRES_APPROVAL"
    assert prop_par.conditions_met["2_collinear_aligned"] is False

    # Mayın B (W1 vs W2 farklı devreler) kesinlikle REQUIRES_APPROVAL olmalı
    prop_diff = next(
        p for p in plan.proposals
        if {p.primary_handle, p.secondary_handle} == {diff_a.dxf.handle, diff_b.dxf.handle}
    )
    assert prop_diff.auto_approvable is False
    assert prop_diff.status == "REQUIRES_APPROVAL"
    assert prop_diff.conditions_met["4_same_circuit_context"] is False

    # Otomatik onaylanabilir olanları uygula
    out_dxf = tmp_path / "healed_wires.dxf"
    applied = TopologicalWireHealer.apply_plan(doc, plan, output_dxf_path=out_dxf)
    assert out_dxf.exists()
    assert len(applied) == 3  # 1 duplicate silindi + 1 doğrusal kopukluk köprülendi + 1 sembol snap yapıldı

    # Snap kontrolü: snap_line'ın bitiş noktası (42.0, 0.0) sembol merkezine oturmuş olmalı
    assert abs(snap_line.dxf.end.x - 42.0) < 1e-6
    assert abs(snap_line.dxf.end.y - 0.0) < 1e-6


# ==============================================================================
# TEST 11: MODÜL 3 (ElectricalAutoOptimizer) ASBUILT vs DESIGN VE YENİDEN DOĞRULAMA
# ==============================================================================
def test_ref11_electrical_optimizer_asbuilt_vs_design_and_reverify(tmp_path: Path):
    """
    Modül 3 (ElectricalAutoOptimizer) pazarlığa kapalı 3 kuralını doğrular:
    1. job_type='ASBUILT' modunda faz dengeleme önerisi DWG'ye uygulanamaz (can_apply_to_dwg=False,
       status='ASBUILT_FIELD_RECOMMENDATION_ONLY'). Onay listesine eklense bile apply_proposals reddeder!
    2. job_type='DESIGN' modunda Greedy LPT algoritması faz dengesizliğini <%5 seviyesine indirir
       ve onaylandığında DWG metnini günceller.
    3. Kesit/Koruma (4x4 mm² + 32A Sigorta + 25A KAK) ve Yangın Pompası (FE180 + 30mA KAK kaldırma)
       önerileri bellekte YENİDEN DOĞRULANIR (verification_passed=True) ve MTEXT biçim kodlarını
       bozmadan DWG'ye işlenir.
    """
    from datetime import datetime, timezone
    from core.healer.electrical_optimizer import (
        ElectricalAutoOptimizer,
        ElectricalOptimizationPlan,
    )
    from core.rules.rule_engine import RuleEngine

    doc = ezdxf.new("R2018")
    msp = doc.modelspace()

    # Faz etiketleri (DWG içindeki TEXT nesneleri)
    txt_c1 = msp.add_text("L1", dxfattribs={"insert": (0, 0)})
    txt_c2 = msp.add_text("L1", dxfattribs={"insert": (0, 5)})
    txt_c3 = msp.add_text("L1", dxfattribs={"insert": (0, 10)})

    # Yangın pompası kablo etiketi (MTEXT biçim kodlu!) ve Koruma etiketi
    mt_fp_cable = msp.add_mtext(r"{\fArial|b1|i0;\C1;4x4 N2XH}", dxfattribs={"insert": (10, 0)})
    txt_prot = msp.add_text("3x32A + 4x25A KAK", dxfattribs={"insert": (10, 5)})

    unbalanced_circuits = [
        {"circuit_id": "W1", "power_w": 2000.0, "phase": "L1", "dxf_handle": txt_c1.dxf.handle, "raw_text": "L1"},
        {"circuit_id": "W2", "power_w": 2000.0, "phase": "L1", "dxf_handle": txt_c2.dxf.handle, "raw_text": "L1"},
        {"circuit_id": "W3", "power_w": 2000.0, "phase": "L1", "dxf_handle": txt_c3.dxf.handle, "raw_text": "L1"},
    ]

    # --- A) ASBUILT MODU TESTİ: DWG FAZ DEĞİŞİKLİĞİ KESİNLİKLE YASAK ---
    plan_asbuilt = ElectricalOptimizationPlan(
        drawing_name="asbuilt_station.dxf",
        job_type="ASBUILT",
        rule_pack="ibb_metro",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    ElectricalAutoOptimizer.propose_phase_balance(plan_asbuilt, "S19-TDP1", unbalanced_circuits)
    assert len(plan_asbuilt.proposals) == 1
    prop_ab = plan_asbuilt.proposals[0]
    assert prop_ab.can_apply_to_dwg is False
    assert prop_ab.status == "ASBUILT_FIELD_RECOMMENDATION_ONLY"
    assert prop_ab.verification_passed is True

    # Kullanıcı zorla onaylasa bile ASBUILT faz önerisi DWG'ye uygulanmamalı!
    applied_ab = ElectricalAutoOptimizer.apply_proposals(
        doc, plan_asbuilt, approved_proposal_ids={prop_ab.proposal_id}
    )
    assert len(applied_ab) == 0
    assert prop_ab.status == "BLOCKED_ASBUILT_POLICY"
    assert txt_c1.dxf.text == "L1" and txt_c2.dxf.text == "L1" and txt_c3.dxf.text == "L1"

    # --- B) DESIGN MODU TESTİ: FAZ DENGELEME + KORUMA KOORDİNASYONU + YANGIN POMPASI FE180 ---
    plan_design = ElectricalOptimizationPlan(
        drawing_name="design_building.dxf",
        job_type="DESIGN",
        rule_pack="bina_genel",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    ElectricalAutoOptimizer.propose_phase_balance(plan_design, "TDP-1", unbalanced_circuits)

    rule_engine = RuleEngine(default_pack="turkey_bina")
    # Musa Demir benzeri gerçek hata: 11 kW Yangın Pompası, 4x4 N2XH (FE180 değil), 32A Sigorta, 25A/30mA KAK
    ElectricalAutoOptimizer.propose_and_verify_protection_or_cable_fix(
        plan=plan_design,
        rule_engine=rule_engine,
        element_id="TDP-1/YANGIN-POMPASI",
        power_w=11000.0,
        length_m=35.0,
        is_3phase=True,
        current_sec_mm2=4.0,
        current_cable_type="N2XH",
        current_breaker_a=32.0,
        current_rcd_a=25.0,
        current_rcd_ma=30.0,
        is_fire_pump=True,
        cable_dxf_handle=mt_fp_cable.dxf.handle,
        cable_old_text="4x4 N2XH",
        protection_dxf_handle=txt_prot.dxf.handle,
        protection_old_text="3x32A + 4x25A KAK",
    )

    # Tüm öneriler bellekte yeniden doğrulanmış (verification_passed=True) olmalı
    assert len(plan_design.proposals) >= 3
    assert all(p.verification_passed is True for p in plan_design.proposals)

    # Faz dengesizliği %100'den %0.0'a düşmüş olmalı
    phase_props = [p for p in plan_design.proposals if p.category == "PHASE_BALANCE"]
    assert len(phase_props) == 2
    assert phase_props[0].after_metrics["imbalance_pct"] == 0.0

    # Onay İstasyonu: Tüm önerileri onayla ve uygula
    all_ids = {p.proposal_id for p in plan_design.proposals}
    ledger_path = tmp_path / "optimizer_applied_changes.json"
    applied_design = ElectricalAutoOptimizer.apply_proposals(
        doc,
        plan_design,
        approved_proposal_ids=all_ids,
        applied_ledger_path=ledger_path,
    )
    assert len(applied_design) == len(plan_design.proposals)
    assert ledger_path.exists()

    # DWG üzerindeki faz etiketleri L1, L2, L3 olarak dengelenmiş olmalı
    phases_on_dwg = {txt_c1.dxf.text, txt_c2.dxf.text, txt_c3.dxf.text}
    assert phases_on_dwg == {"L1", "L2", "L3"}

    # MTEXT içindeki font kodu korunarak kablo FE180'e yükseltilmiş olmalı
    assert mt_fp_cable.text.startswith(r"{\fArial|b1|i0;\C1;")
    assert "FE180" in mt_fp_cable.text


# ==============================================================================
# TEST 12: MODÜL 4 (CADTableGenerator) DWG CETVEL ÇİZİMİ VE .XLSX ÜRETİMİ
# ==============================================================================
def test_ref12_cad_table_generator_dwg_and_xlsx(tmp_path: Path):
    """
    Modül 4 (CADTableGenerator) doğrulaması:
    1. Doğrulanmış linye verilerinden DWG içine E-ETIKET-TABLO katmanında LINE + TEXT ızgarası çizer.
    2. Mevcut DWG tablo hücresi handle'ları verilmişse CADSafetyGuard ile yerinde günceller.
    3. openpyxl ile kurumsal .xlsx yükleme cetvelini üretir ve faz dengesizliği / talep gücü özetini yazar.
    """
    import openpyxl
    from core.healer.table_generator import (
        CADTableGenerator,
        ScheduleRowInput,
    )

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4  # mm
    msp = doc.modelspace()

    # Mevcut bir tablo hücresi metni (yerinde güncelleme testi için)
    existing_cell = msp.add_text("3x2.5 NYM (ESKI)", dxfattribs={"insert": (500, 500)})

    rows = [
        ScheduleRowInput(
            circuit_id="L1",
            description="Aydınlatma Sortisi 1",
            load_watts=1500.0,
            phase="L1",
            cable_spec="3x2.5 N2XH",
            breaker_spec="1x16A B",
            rcd_spec="30mA",
            length_m=22.0,
            voltage_drop_pct=0.85,
            cell_handles={"cable_spec": existing_cell.dxf.handle},
        ),
        ScheduleRowInput(
            circuit_id="L2",
            description="Priz Linyesi 1",
            load_watts=1500.0,
            phase="L2",
            cable_spec="3x2.5 N2XH",
            breaker_spec="1x16A C",
            rcd_spec="30mA",
            length_m=28.0,
            voltage_drop_pct=1.10,
        ),
        ScheduleRowInput(
            circuit_id="L3",
            description="Klima Linyesi",
            load_watts=1500.0,
            phase="L3",
            cable_spec="3x4 N2XH",
            breaker_spec="1x20A C",
            rcd_spec="30mA",
            length_m=30.0,
            voltage_drop_pct=0.92,
        ),
    ]

    gen = CADTableGenerator(target_layer="E-ETIKET-TABLO")
    # Onaysız çağrıldığında mevcut hücre metni ASLA değişmemeli!
    dwg_rep_unapproved = gen.draw_panel_schedule_in_dwg(
        doc,
        panel_name="TDP-01",
        rows=rows,
        insert_pos=(0.0, 0.0),
        demand_factor=0.80,
        approved_cell_handles=None,
    )
    assert dwg_rep_unapproved.dwg_cells_updated == 0
    assert existing_cell.dxf.text == "3x2.5 NYM (ESKI)"

    # Onay İstasyonu'ndan handle onaylandığında hücre güncellenmeli!
    dwg_rep = gen.draw_panel_schedule_in_dwg(
        doc,
        panel_name="TDP-01",
        rows=rows,
        insert_pos=(0.0, -2000.0),
        demand_factor=0.80,
        approved_cell_handles={existing_cell.dxf.handle},
    )

    assert dwg_rep.total_installed_power_kw == 4.5
    assert dwg_rep.demand_power_kw == 3.6
    assert dwg_rep.phase_imbalance_pct == 0.0
    assert dwg_rep.dwg_entities_created > 20
    assert dwg_rep.dwg_cells_updated == 1
    assert existing_cell.dxf.text == "3x2.5 N2XH"

    xlsx_path = tmp_path / "TDP_01_Yukleme_Cetveli.xlsx"
    xlsx_rep = gen.export_panel_schedule_xlsx(
        panel_name="TDP-01",
        rows=rows,
        output_xlsx_path=str(xlsx_path),
        demand_factor=0.80,
    )
    assert xlsx_path.exists()
    assert xlsx_rep.phase_imbalance_pct == 0.0

    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active
    assert "TDP-01" in str(ws["A1"].value)
    assert ws.cell(row=4, column=1).value == "L1"
    assert ws.cell(row=4, column=7).value == "3x2.5 N2XH"


# ==============================================================================
# TEST 13: YAKALANAN 11 KRİTİK/ORTA/KÜÇÜK BULGUNUN REGRESYON DOĞRULAMASI
# ==============================================================================
def test_ref13_all_11_audit_fixes_regression():
    """
    Canlı denetimde yakalanan 11 bulgunun tamamının regresyonsuz kapatıldığını doğrular:
    1. Kritik 1 (Faz Etiketi Replace Kalkanı):
       - "L2-01 3x2.5 NYY" (faz L1->L2) metninde bağımsız L1 token'ı olmadığı için metin ASLA "L2"ye
         ezilmez (can_apply_to_dwg=False, metin korunur).
       - "L1-01 3x2.5 NYY (L1)" metninde ise baştaki "L1-01" linye koduna dokunulmaz, yalnız sondaki
         bağımsız "(L1)" -> "(L2)" yapılır!
    2. Kritik 2 (Dinamik Kural Paketi Sınırları):
       - 1-fazlı priz/kuvvet linyesinde (%2.1 gerilim düşümü, paket sınırı %3.0 iken) eski sabit %1.5
         yüzünden yanlış kesit büyütme önerisi üretilmez.
    3. Orta 1 (Duplicate Cleaner Devre Bağlamı):
       - Üst üste binmiş çizgilerde W1 ve W2 farklı devre etiketleri varsa auto_approvable=False,
         status='REQUIRES_APPROVAL' olur.
    4. Orta 3 (Snap Kademeli Onay + Çift Müdahale Koruması):
       - >5 cm (örn. 10 cm) snap önerisi auto_approvable=False ('REQUIRES_APPROVAL') olur.
       - STITCH adayı olan kablo ucuna ikinci kez SNAP üretilmez.
    5. Orta 4 (apply_plan Statü Koruması):
       - Kısmi onayda seçilmeyen öneriler 'REJECTED' değil 'NOT_SELECTED' olur.
    6. Küçük 1 (Unitless cm Heuristik):
       - $INSUNITS=0 olan cm çizimde (0.25 birim yazı, 5000 birim span) birim 10.0 mm (cm) bulunur.
    7. Küçük 2 (E-KAPI-GUVENLIK Substring Koruması):
       - 'E-KAPI-GUVENLIK' katmanındaki varlık 'KAPI' kelimesi yüzünden 'A-MIMARI-ALTYAPI'ya taşınmaz.
    8. Küçük 4 & 5 (Yayılı Yük Efektif Boy + Yangın Pompası KAK Kaldırma + summary_counts):
       - phase_balance sonrası summary_counts günceldir; yangın pompasında KAK metni de kaldırılır.
    """
    from datetime import datetime, timezone
    from shapely.geometry import box
    from core.cad.cad_safety import UnitScaleResolver
    from core.healer.electrical_optimizer import (
        ElectricalAutoOptimizer,
        ElectricalOptimizationPlan,
    )
    from core.healer.layer_doctor import LayerAndBlockDoctor
    from core.healer.wire_healer import TopologicalWireHealer
    from core.model.entities import PlacedSymbol, TextToken
    from core.rules.rule_engine import RuleEngine

    # --- 1) KRİTİK 1: Faz Etiketi Replace ve Değişmezlik Kalkanı (Invariance Guard) ---
    ok1, new1, reason1 = ElectricalAutoOptimizer.safe_replace_phase_token(
        "L2-01 3x2.5 NYY", old_phase="L1", target_phase="L2", circuit_id="L2-01"
    )
    assert ok1 is False
    assert new1 == "L2-01 3x2.5 NYY"  # Metin ASLA "L2"ye ezilmedi!
    assert reason1 == "PHASE_TOKEN_NOT_FOUND_IN_TEXT"

    ok2, new2, reason2 = ElectricalAutoOptimizer.safe_replace_phase_token(
        "L1-01 3x2.5 NYY (L1)", old_phase="L1", target_phase="L2", circuit_id="L1-01"
    )
    assert ok2 is True
    assert new2 == "L1-01 3x2.5 NYY (L2)"  # Baştaki L1-01 korundu, yalnız sondaki (L1) -> (L2) oldu!

    # DWG üzerinde canlı kontrol: "L2-01 3x2.5 NYY" metni onaylansa bile ezilmemeli
    doc_opt = ezdxf.new("R2018")
    msp_opt = doc_opt.modelspace()
    t_protected = msp_opt.add_text("L2-01 3x2.5 NYY", dxfattribs={"insert": (0, 0)})
    t_safe = msp_opt.add_text("L1-02 3x2.5 NYY (L1)", dxfattribs={"insert": (0, 5)})
    t_keep = msp_opt.add_text("L1", dxfattribs={"insert": (0, 10)})

    plan_opt = ElectricalOptimizationPlan(
        drawing_name="invariance_test.dxf",
        job_type="DESIGN",
        rule_pack="turkey_bina",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    ElectricalAutoOptimizer.propose_phase_balance(
        plan_opt,
        "TDP-INV",
        [
            {"circuit_id": "L1-00", "power_w": 2000.0, "phase": "L1", "dxf_handle": t_keep.dxf.handle, "raw_text": "L1"},
            {"circuit_id": "L2-01", "power_w": 2000.0, "phase": "L1", "dxf_handle": t_protected.dxf.handle, "raw_text": "L2-01 3x2.5 NYY"},
            {"circuit_id": "L1-02", "power_w": 1900.0, "phase": "L1", "dxf_handle": t_safe.dxf.handle, "raw_text": "L1-02 3x2.5 NYY (L1)"},
        ],
    )
    # Küçük 5: propose_phase_balance sonrasında summary_counts güncel olmalı!
    assert plan_opt.summary_counts["total_proposals"] == 2
    assert plan_opt.summary_counts["dwg_applicable"] == 1  # Yalnız t_safe DWG'de değiştirilebilir!

    ElectricalAutoOptimizer.apply_proposals(
        doc_opt, plan_opt, approved_proposal_ids={p.proposal_id for p in plan_opt.proposals}
    )
    assert t_protected.dxf.text == "L2-01 3x2.5 NYY"  # Kesinlikle korundu!
    assert t_safe.dxf.text in ("L1-02 3x2.5 NYY (L2)", "L1-02 3x2.5 NYY (L3)")

    # --- 2) KRİTİK 2 & KÜÇÜK 4: Dinamik Kural Paketi Sınırı (%3.0 Priz) ve Efektif Boy ---
    re_bina = RuleEngine(default_pack="turkey_bina")
    plan_vd = ElectricalOptimizationPlan(
        drawing_name="vd_test.dxf",
        job_type="DESIGN",
        rule_pack="turkey_bina",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    # 1 Faz PRİZ linyesi: 2200W, 30m, 2.5mm², 16A sigorta -> e% ~ %2.37 (<= %3.0 Priz sınırı, ama > %1.5!).
    # Eski kod sabit %1.5 kullandığı için buna yanlışlıkla kesit büyütme öneriyordu; artık 0 öneri üretmeli!
    ElectricalAutoOptimizer.propose_and_verify_protection_or_cable_fix(
        plan=plan_vd,
        rule_engine=re_bina,
        element_id="TDP-1/PRIZ-1",
        power_w=2200.0,
        length_m=30.0,
        is_3phase=False,
        current_sec_mm2=2.5,
        current_cable_type="N2XH",
        current_breaker_a=16.0,
        circuit_type="PRIZ",
        fixture_count=1,
    )
    assert len(plan_vd.proposals) == 0

    # --- 3) ORTA 1, 3, 4: Duplicate Çelişki, Snap Kademeli Onay, Çift Müdahale ve NOT_SELECTED ---
    doc_wh = ezdxf.new("R2018")
    doc_wh.header["$INSUNITS"] = 6  # Metre
    msp_wh = doc_wh.modelspace()

    # Üst üste iki çizgi ama W1 ve W2 etiketli -> REQUIRES_APPROVAL olmalı!
    d1 = msp_wh.add_line((0.0, 0.0), (2.0, 0.0), dxfattribs={"layer": "E-KABLO-HAT"})
    d2 = msp_wh.add_line((0.0, 0.0), (2.0, 0.0), dxfattribs={"layer": "E-KABLO-HAT"})

    # Sembole 10 cm (0.10m > 5cm) mesafede kablo ucu -> Snap REQUIRES_APPROVAL olmalı!
    s_line = msp_wh.add_line((10.0, 0.0), (11.90, 0.0), dxfattribs={"layer": "E-KABLO-HAT"})
    sym_far = PlacedSymbol(
        block_name="ELC_PRIZ",
        clean_family_name="ELC_PRIZ",
        pos=(12.0, 0.0, 0.0),
        scale=(1, 1, 1),
        rotation=0.0,
        layer="E-PRIZ-SORTI",
        color=30,
        bbox=box(11.95, -0.05, 12.05, 0.05),
        classification="SOCKET",
        confidence_score=0.95,
        dxf_handle="SYM_P1",
    )

    wh_texts = [
        TextToken(text="W1", pos=(0.5, 0.02, 0.0), height=0.1, rotation=0.0, layer="0", color=7, bbox=box(0.4, 0, 0.6, 0.1)),
        TextToken(text="W2", pos=(1.5, 0.02, 0.0), height=0.1, rotation=0.0, layer="0", color=7, bbox=box(1.4, 0, 1.6, 0.1)),
    ]
    wh_plan = TopologicalWireHealer.analyze_and_propose(doc_wh, symbols=[sym_far], texts=wh_texts)
    assert wh_plan.summary_counts["duplicates_blocked"] == 1
    assert wh_plan.summary_counts["symbol_snaps_requires_approval"] == 1

    # Kısmi apply çağrıldığında seçilmeyenler 'REJECTED' değil, statülerini korumalı / 'NOT_SELECTED' olmalı
    TopologicalWireHealer.apply_plan(doc_wh, wh_plan, approved_proposal_ids=set())
    assert all(p.status != "REJECTED" for p in wh_plan.proposals)

    # --- 4) KÜÇÜK 1: Unitless ($INSUNITS=0) cm Çizim Tespiti ---
    doc_cm = ezdxf.new("R2018")
    doc_cm.header["$INSUNITS"] = 0
    msp_cm = doc_cm.modelspace()
    msp_cm.add_line((0, 0), (3500, 2500))  # 35m x 25m bina = 3500 x 2500 cm
    msp_cm.add_text("PRIZ LINYESI", dxfattribs={"insert": (100, 100), "height": 0.25})  # 0.25 birim yazı
    unit_mm_cm, src_cm = UnitScaleResolver.resolve_unit_to_mm(doc_cm)
    assert unit_mm_cm == 10.0
    assert "HEURISTIC_CM" in src_cm

    # --- 5) KÜÇÜK 2: E-KAPI-GUVENLIK Katmanı Asla Mimariye Taşınmaz ---
    doc_ld = ezdxf.new("R2018")
    msp_ld = doc_ld.modelspace()
    ent_acs = msp_ld.add_line((0, 0), (10, 0), dxfattribs={"layer": "E-KAPI-GUVENLIK"})
    ent_wall = msp_ld.add_line((0, 5), (10, 5), dxfattribs={"layer": "A-DUVAR"})
    ld_plan = LayerAndBlockDoctor.analyze_and_propose(doc_ld)
    moved_handles = {p.dxf_handle for p in ld_plan.proposals}
    assert ent_wall.dxf.handle in moved_handles
    assert ent_acs.dxf.handle not in moved_handles  # Elektrik/Kartlı geçiş katmanı korundu!

    # --- 6) WIRE HEALER KATMAN FİLTRESİ: Patlatılmış Mimari/Antet/Tefriş Çizgileri Kablo Sanılmaz ---
    doc_wf = ezdxf.new("R2018")
    doc_wf.header["$INSUNITS"] = 4  # mm
    msp_wf = doc_wf.modelspace()
    # Patlatılmış mimari ve tefriş çizgileri (F-AFFFEQM, G-PLANOTM, A_RC, A_DOOR)
    msp_wf.add_line((0, 0), (1000, 0), dxfattribs={"layer": "F-AFFFEQM"})
    msp_wf.add_line((1100, 0), (2000, 0), dxfattribs={"layer": "F-AFFFEQM"})
    msp_wf.add_line((0, 500), (1000, 500), dxfattribs={"layer": "G-PLANOTM"})
    msp_wf.add_line((1100, 500), (2000, 500), dxfattribs={"layer": "G-PLANOTM"})
    msp_wf.add_line((0, 1000), (1000, 1000), dxfattribs={"layer": "A_RC"})
    msp_wf.add_line((1100, 1000), (2000, 1000), dxfattribs={"layer": "A_RC"})
    # Gerçek elektrik kablo çizgisi (E-KABLO-HAT)
    msp_wf.add_line((0, 2000), (1000, 2000), dxfattribs={"layer": "E-KABLO-HAT"})
    msp_wf.add_line((1100, 2000), (2000, 2000), dxfattribs={"layer": "E-KABLO-HAT"})

    wf_plan = TopologicalWireHealer.analyze_and_propose(doc_wf)
    assert wf_plan.summary_counts["skipped_non_wire_layer_lines"] == 6
    assert len(wf_plan.proposals) == 1
    assert wf_plan.proposals[0].layer == "E-KABLO-HAT"





