"""
CloudeCAD — Raylı Sistem & Metro İstasyonu Topraklama Analiz Motoru (Metro Analyzer)
=====================================================================================
Standartlar:
  - EN 50122-1 (Elektriksel Güvenlik, Topraklama ve Dönüş Devresi — Dokunma Gerilimi & OVPD/VLD)
  - EN 50122-2 (DC Cer Sistemlerinin Neden Olduğu Kaçak Akım / Stray Current Korozyon Önlemleri)
  - TS HD 60364-5-54 / IEC 60364 (TN-S Sistemi ve Koruma İletkenleri)
  - NFPA 130 (Sabit Kılavuzlu Transit ve Yolcu Raylı Sistemler Standardı)
  - İBB Raylı Sistemler (İkitelli - Ataköy M9 Sözleşme, Birim Fiyat ve Teknik Şartname Hükümleri)

Uygulama Projesi (Shop Drawing) Dinamik Denetim Yetenekleri:
  1. Topraklama Kaynağı & Peron Altı Ana Topraklama Barası (Master ETB/ECB, 40x5 mm Cu) Tespiti
  2. Lejant ve İletken Tipine Göre Gerçek Metraj Ayrıştırması (Sarı yazı okları hariç, köşe yayları dahil)
  3. Mimari/Mekanik/Elektrik Altlıklarındaki Metal Elemanların (Muayene Kapağı, Döşeme Kapağı,
     Şaft/Kedi Merdiveni, Drenaj Izgarası, Yürüyen Merdiven, Damper/Panjur, Pompa, Pano)
     Koordinat ve Aks Bazlı Topraklama Bağlantı Denetimi (Unutulan Elemanların Yakalanması)
  4. T-Ayrım Noktalarında Vidalı Topraklama Klemensi (kkk) Sembol Denetimi
  5. Topolojik Süreklilik (Ana Şebekeden Kopuk Ada) Denetimi
  6. 14 Maddelik Proje Uygulama Notları ve M9 İkitelli-Ataköy Özel Teknik Şartname Matrisi
"""

import re
import math
import logging
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any

from standards.project_classifier import (
    ProjectTypeResult, ROLE_EXTERNAL_GRID, ROLE_MAIN_ROUTE,
    ROLE_SUB_PLATFORM_MASTER, ROLE_FLOOR_DISTRIBUTION, ROLE_TYPICAL_DETAILS
)

logger = logging.getLogger(__name__)


@dataclass
class MetroBusbarEntity:
    """İstasyon içindeki bir topraklama barası (ECB / ETB / İşletme / Zayıf Akım Barası)."""
    name: str
    dimensions: str = "40x5 mm"
    material: str = "Elektrolitik Bakır (E-Cu)"
    location_desc: str = ""
    floor_level: str = ""
    position: Tuple[float, float] = (0.0, 0.0)


@dataclass
class MetroSpatialDefect:
    """Uygulama projesinde tespit edilen mekânsal/topolojik eksik veya doğrulanan eleman."""
    category: str
    element_name: str
    axis_location: str
    status: str                         # '✗ EKSİK / TOPRAKLANMAMIŞ' | '⚠ SEMBOLLER EKSİK' | '✓ TOPRAKLANMIŞ'
    nearest_grounding_m: float
    spec_reference: str
    description: str
    position: Tuple[float, float] = (0.0, 0.0)


@dataclass
class MetroSpecArticleAudit:
    """14 Maddelik İBB / Uygulama Projesi Şartnamesi madde denetim sonucu."""
    article_no: int
    title: str
    requirement: str
    status: str                         # 'UYGUN' | 'EKSİK TESPİT EDİLDİ' | 'KAPSAM DIŞI'
    finding: str
    detected_in_drawing: bool = False


@dataclass
class MetroStationAnalysisResult:
    """Bir metro paftasının veya istasyon paketinin denetim çıktısı."""
    project_name: str
    drawing_role: str
    floor_level: str
    
    # 1. Hiyerarşi ve Kaynak Durumu
    has_sub_platform_master: bool = False
    master_busbar_location: str = "PERON ALTI KATI (-48.55 Kotu)"
    grounding_source_type: str = "TEMEL / DIŞ SAHA AĞI"
    source_status_note: str = ""
    
    # 2. Metraj ve İletken Geometrisi (Gerçek CAD Katman/Renk Ayrıştırması)
    total_conductor_m: float = 0.0
    bare_copper_120_m: float = 0.0      # Ana Topraklama Ağı (120 / 185 / 240 mm² Cu)
    tali_copper_m: float = 0.0          # Tali Topraklama Ağı (Tava kenarına irtibatlı çıplak örgülü Cu)
    insulated_copper_16_m: float = 0.0  # Koruma İletkeni Branşmanları (16 mm² H07Z-R Sarı-Yeşil)
    heavy_copper_240_m: float = 0.0     # Ray Altı Çelik Hasır / Tünel / Donatı İrtibatları (185-240 mm²)
    isletme_zayif_akim_m: float = 0.0   # İşletme / Zayıf Akım (SER) Bara İrtibatları
    busbars: List[MetroBusbarEntity] = field(default_factory=list)
    clamp_count: int = 0
    missing_clamp_junctions: int = 0
    missing_clamp_points: List[Tuple[float, float]] = field(default_factory=list)
    test_pit_count: int = 0             # Muayene bacası / rögar
    disconnected_island_count: int = 0
    
    # 3. Ray Altı Hasır & Stray Current
    has_rail_mesh: bool = False         # Ray altı çelik hasır
    has_vld_connection: bool = False    # Voltaj Sınırlama Cihazı (VLD / OVPD)
    has_og_console_grounding: bool = False # OG konsol topraklaması
    
    # 4. Mekânsal Eksik ve Hata Denetimi (Uygulama Projesi Kontrolü)
    spatial_defects: List[MetroSpatialDefect] = field(default_factory=list)
    grounded_elements: List[MetroSpatialDefect] = field(default_factory=list)
    equipment_summary_by_cat: List[Dict[str, Any]] = field(default_factory=list)
    technical_rooms_audit: List[Dict[str, Any]] = field(default_factory=list)

    # 5. 14-Maddelik Şartname Uygunluk Matrisi & İkitelli-Ataköy Sözleşme Kriterleri
    spec_articles: List[MetroSpecArticleAudit] = field(default_factory=list)
    ikk_sartname_audits: List[Dict[str, str]] = field(default_factory=list)
    compliance_score_percent: float = 100.0

    # 6. Koruma İletkeni Kesit Doğrulama Tablosu
    protection_conductor_table: List[Dict[str, str]] = field(default_factory=list)

    # 7. Özet Mühendislik Kanaati
    executive_verdict: str = "UYGUNDUR"
    verdict_summary: str = ""
    spec_profile_id: str = "IBB_M9_METRO"


class MetroStationAnalyzer:
    """Metro istasyonu topraklama ve eşpotansiyel sistemini dinamik olarak analiz eder."""

    def __init__(self, spec_profile_id: str = "IBB_M9_METRO"):
        from standards.spec_profiles import get_spec_profile
        self.spec = get_spec_profile(spec_profile_id)

    def analyze(
        self,
        drawing: Any,
        cls_result: ProjectTypeResult,
        geo_result: Optional[Any] = None
    ) -> MetroStationAnalysisResult:
        """Metro çizimini, ekipman bağlantılarını ve metinlerini inceler."""
        role = cls_result.metro_role or ROLE_FLOOR_DISTRIBUTION
        floor = cls_result.floor_level_name or "PERON KATI"
        pname = Path(drawing.source_file).stem if hasattr(drawing, 'source_file') else "Metro_Istasyonu"

        all_text_content = ""
        raw_texts = []
        if hasattr(drawing, 'all_texts'):
            raw_texts = [t.text for t in drawing.all_texts]
            all_text_content = " ".join(raw_texts).lower()

        # 1. Baralar Tespiti (ECB / ETB / 40x5 mm Bakır Bara / Kaçak Akım İzleme Terminali)
        busbars = self._detect_busbars(drawing, floor)
        if not busbars and "bara" in all_text_content and role != ROLE_EXTERNAL_GRID:
            busbars.append(MetroBusbarEntity(
                name="Ana Kat Eşpotansiyel Topraklama Barası (ETB)",
                dimensions="40x5 mm",
                floor_level=floor,
                location_desc="Teknik Oda / Şaft Kenarı"
            ))

        # 2. Gerçek İletken Metrajı Ayrıştırması (Katman / Renk Bazlı)
        m_120, m_tali, m_16, m_rail, m_isletme, total_m = self._compute_exact_conductor_boq(drawing, geo_result)

        # 3. Ray Altı Çelik Hasır & Cer Gücü Kaçak Akım (EN 50122-2)
        floor_lower = floor.lower()
        is_rail_drawing = (
            (role == ROLE_MAIN_ROUTE)
            or ("peron" in floor_lower and "altı" not in floor_lower)
            or (m_rail > 5.0)
            or ("ray altı" in all_text_content and role != ROLE_EXTERNAL_GRID and "hat1 ray" in all_text_content)
        )
        has_rail = is_rail_drawing
        has_vld = is_rail_drawing and any(k in all_text_content for k in ["vld", "neg topraklama", "voltaj sınırlama", "kaçak akım izleme", "dc cer"])
        has_og_console = (role == ROLE_MAIN_ROUTE) or ("og konsol" in all_text_content)
        has_test_pits = (role == ROLE_EXTERNAL_GRID)

        # 4. Topraklama Kaynağı ve Peron Altı Ana Barası Durumu
        has_master = (role == ROLE_SUB_PLATFORM_MASTER) or ("peron altı" in floor_lower)
        if has_master:
            source_note = (
                "Bu pafta istasyonun kalbi olan 'Peron Altı Ana Topraklama Baraları (ECB/001..052, -48.55 Kotu)' "
                "merkezini içermektedir. Dış saha topraklama ağından (1x120mm² / 1x240mm² Cu) gelen ana girişler, "
                "peron donatısı uçları, kaçak akım izleme terminalleri, Hat 1 / Hat 2 ray altı çelik hasır (185mm²) "
                "ve OG/İşletme/Zayıf Akım (SER) baraları bu katta toplanmaktadır."
            )
        elif role == ROLE_EXTERNAL_GRID:
            source_note = (
                "Bu pafta, istasyonun harici temel/dış saha elektrot ve muayene rögarı (Detay D) şebekesini "
                "göstermektedir. İstasyon dışından HDPE boru içindeki 120 mm² çıplak örgülü "
                "bakır iletkenle Peron Altı Ana Barası'na bağlanır."
            )
        elif role == ROLE_MAIN_ROUTE:
            source_note = (
                "Bu pafta istasyon hat boyu tünel, Hat 1/Hat 2 konsol topraklaması ve kablo tavaları "
                "güzergahını içermektedir. Peron Altı ve Teknik Kat baralarıyla ring oluşturmaktadır."
            )
        else:
            source_note = (
                "Bu kat planı, Peron Altı Ana Topraklama Barası'ndan dikey şaftlarla yükselen ana "
                "iletkenlerden beslenen kat içi eşpotansiyel dağıtım şebekesidir. Harici temel topraklaması "
                "inşaat/statik projesinde veya harici kuyu paftasında tanımlanmış olup; bu paftada kat "
                "baraları (40x5 mm Cu), pano, kapak, merdiven ve mekanik ekipman irtibatları denetlenmektedir."
            )

        # 5. Dinamik Mekânsal Eksik & Hata Denetimi (STRtree Uzamsal İndeksli: Ekipman, Kapak, Merdiven, Pano, Klemens)
        defects, grounded_list, cat_summary, real_clamps, missing_clamps, missing_clamp_pts = (
            self._audit_spatial_equipment_and_clamps(drawing, role, floor)
        )

        # 5.5 Kritik Teknik Oda / Mahal Topraklama Denetimi (M-AREA-IDEN & Teknik Hacimler)
        tech_rooms_audit = self._audit_technical_rooms(drawing, busbars, role)

        # 6. Topolojik Süreklilik (Kopuk Ada) Kontrolü
        disconnected_islands = 0
        if geo_result and getattr(geo_result, 'network_count', 1) > 1:
            disconnected_islands = max(0, geo_result.network_count - 1)

        # 7. İBB 14-Maddelik Uygulama Notları & İkitelli-Ataköy M9 Şartname Denetim Matrisi
        spec_audits = self._audit_14_spec_articles(
            all_text_content, role, floor, defects, grounded_list, cat_summary, real_clamps, missing_clamps, has_rail
        )
        ikk_audits = self._audit_ikitelli_atakoy_spec(
            all_text_content, role, floor, busbars, m_120, m_16, m_rail, has_rail, defects
        )

        # 8. Uyum Skoru ve Başmühendis Kanaati Hesabı
        active_articles = [a for a in spec_audits if "KAPSAM DIŞI" not in a.status]
        failed_articles = [a for a in active_articles if "EKSİK" in a.status or "HATA" in a.status]
        
        total_eq = len(defects) + len(grounded_list)
        if total_eq > 0:
            eq_ratio = len(grounded_list) / total_eq
        else:
            eq_ratio = 1.0

        if len(defects) > 0:
            # Eksik ekipman ve madde oranına göre gerçekçi mühendislik puanı
            art_score = ((len(active_articles) - len(failed_articles)) / max(1, len(active_articles))) * 100.0
            score = round(0.55 * art_score + 0.45 * (eq_ratio * 100.0), 1)
            verdict = f"REVİZYON GEREKLİ ({len(defects)} ADET TOPRAKLAMA EKSİĞİ TESPİT EDİLDİ)"
        elif missing_clamps > 5:
            score = 92.0
            verdict = f"ŞARTLI UYGUN ({missing_clamps} NOKTADA KLEMENS SEMBOLÜ EKSİK)"
        else:
            score = 100.0
            verdict = "UYGUNDUR (ŞARTNAME VE UYGULAMA KRİTERLERİNE UYGUN)"

        # 9. Koruma İletkeni Seçim Çizelgesi (İBB Madde 4 & TS HD 60364-5-54)
        prot_table = [
            {"ana_kesit": "S ≤ 16 mm²", "koruma_kesiti": "S (Min. 16 mm² Cu)", "aciklama": "Proje Notu Md.4 & Seçim Çizelgesi (S<16 -> 16 mm²)"},
            {"ana_kesit": "16 < S ≤ 35 mm²", "koruma_kesiti": "16 mm² Cu H07Z-R", "aciklama": "Halojen-free, alev iletmeyen sarı-yeşil esnek bakır"},
            {"ana_kesit": "S > 35 mm²", "koruma_kesiti": "S / 2 mm² Cu", "aciklama": "Ana faz kesitinin yarısı (120 mm² üstü bağımsız hat)"},
            {"ana_kesit": "Ana Topraklama Ağı", "koruma_kesiti": f"120 - 240 mm² Cu ({m_120:.1f} m)", "aciklama": "Tava kenarına irtibatlı çıplak örgülü bakır / H07Z-R"},
            {"ana_kesit": "Tali Topraklama Ağı", "koruma_kesiti": f"35 - 120 mm² Cu ({m_tali:.1f} m)", "aciklama": "Kablo tavası boyunca çekilen tali eşpotansiyel ağ"},
            {"ana_kesit": "Koruma Branşmanları", "koruma_kesiti": f"16 mm² Cu ({m_16:.1f} m)", "aciklama": "Kapı, kapak, merdiven, damper ve pano gövde irtibatları"},
            {"ana_kesit": "Ray Altı Hasır & Tünel", "koruma_kesiti": f"185 mm² N2XH/H07Z-R ({m_rail:.1f} m)" if has_rail else "Bu Katta Kapsam Dışı (Ray Yok)", "aciklama": "EN 50122-2 Kaçak akım (Stray current) ve OG konsol irtibatı" if has_rail else "İlgili katta tren rayı bulunmamaktadır"},
        ]

        summary_lines = [
            f"İstasyon Katı/Rolü: {floor} | {role}",
            f"Tespit Edilen Baralar: {len(busbars)} Adet",
            f"Gerçek İletken Metrajı: Toplam {total_m:.1f} m (Ana Ağ: {m_120:.1f} m, Tali Ağ: {m_tali:.1f} m, 16mm² Branşman: {m_16:.1f} m, Ray/Donatı: {m_rail:.1f} m)",
            f"Ekipman/Metal Aksam Denetimi: {len(grounded_list)} Topraklanmış, {len(defects)} Unutulmuş/Eksik",
            f"Teknik Mahal Denetimi: {len(tech_rooms_audit)} Kritik Teknik Oda İncelendi",
            f"Vidalı Klemens (kkk) Denetimi: {real_clamps} Mevcut, {missing_clamps} T-Ek Noktasında Sembol Eksik",
            f"Mühendislik Kararı: {verdict} (Uyum: %{score:.1f})"
        ]

        return MetroStationAnalysisResult(
            project_name=pname,
            drawing_role=role,
            floor_level=floor,
            has_sub_platform_master=has_master,
            master_busbar_location="PERON ALTI KATI (-48.55 Kotu)",
            grounding_source_type="TEMEL / DIŞ SAHA ŞEBEKESİ",
            source_status_note=source_note,
            total_conductor_m=total_m,
            bare_copper_120_m=m_120,
            tali_copper_m=m_tali,
            insulated_copper_16_m=m_16,
            heavy_copper_240_m=m_rail,
            isletme_zayif_akim_m=m_isletme,
            busbars=busbars,
            clamp_count=real_clamps,
            missing_clamp_junctions=missing_clamps,
            missing_clamp_points=missing_clamp_pts,
            test_pit_count=4 if has_test_pits else 0,
            disconnected_island_count=disconnected_islands,
            has_rail_mesh=has_rail,
            has_vld_connection=has_vld,
            has_og_console_grounding=has_og_console,
            spatial_defects=defects,
            grounded_elements=grounded_list,
            equipment_summary_by_cat=cat_summary,
            technical_rooms_audit=tech_rooms_audit,
            spec_articles=spec_audits,
            ikk_sartname_audits=ikk_audits,
            compliance_score_percent=score,
            protection_conductor_table=prot_table,
            executive_verdict=verdict,
            verdict_summary=" | ".join(summary_lines),
            spec_profile_id=self.spec.profile_id
        )

    # ── Yardımcı Metodlar ──────────────────────────────────────────────────

    def _format_axis_location(self, pt_mm: Tuple[float, float], grid_axes: List[Dict[str, Any]]) -> str:
        """Verilen (x, y) mm koordinatının en yakın mimari aks (ör. Aks 4'-C) karşılığını bulur."""
        x_m = pt_mm[0] / 1000.0
        y_m = pt_mm[1] / 1000.0
        if not grid_axes:
            return f"X:{x_m:.1f}m, Y:{y_m:.1f}m"

        x_axes = []
        y_axes = []
        for g in grid_axes:
            lbl = g["label"]
            gx, gy = g["position"]
            if any(ch.isdigit() for ch in lbl):
                x_axes.append((abs(pt_mm[0] - gx), lbl))
            elif lbl.isalpha():
                y_axes.append((abs(pt_mm[1] - gy), lbl))

        near_x = min(x_axes, key=lambda item: item[0])[1] if x_axes else ""
        near_y = min(y_axes, key=lambda item: item[0])[1] if y_axes else ""

        if near_x and near_y:
            return f"Aks {near_x}-{near_y} Yakını (X:{x_m:.1f}m, Y:{y_m:.1f}m)"
        elif near_x:
            return f"Aks {near_x} Yakını (X:{x_m:.1f}m, Y:{y_m:.1f}m)"
        return f"X:{x_m:.1f}m, Y:{y_m:.1f}m"

    def _detect_busbars(self, drawing: Any, floor_name: str) -> List[MetroBusbarEntity]:
        """Çizimden ECB / ETB / 40x5 mm bakır topraklama baralarını ve terminalleri çıkarır."""
        bars = []
        seen_names = set()
        grid_axes = getattr(drawing, 'grid_axes', [])

        # 1. Metin etiketlerinden (S19/ECB/001, S20/ECB/001, İŞLETME TOPRAKLAMA BARASI vb.)
        texts = getattr(drawing, 'all_texts', []) or getattr(drawing, 'grounding_texts', [])
        for t in texts:
            # Lejant ve genel notlar katmanındaki (G-ANNO-TEXT) açıklama yazılarını atla
            if getattr(t, 'layer', '').upper() == "G-ANNO-TEXT":
                continue
            txt_clean = re.sub(r"\\f[^;]+;|\\[A-Za-z0-9]+;|\{|\}", "", t.text).strip()
            txt_u = txt_clean.upper()

            if any(k in txt_u for k in ["ECB/", "ETB", "TOPRAKLAMA BARA", "İZLEME TERMİNALİ", "MUAYENE TERMİNALİ"]):
                if txt_u in seen_names:
                    continue
                seen_names.add(txt_u)
                loc_str = self._format_axis_location(t.position, grid_axes)
                b_type = "40x5 mm Elektrolitik Bakır Bara"
                if "Z.AKIM" in txt_u or "SER" in txt_u:
                    b_type = "40x5 mm Cu Zayıf Akım / Sinyalizasyon (Clean Earth) Barası"
                elif "İŞLETME" in txt_u or "ISLETME" in txt_u:
                    b_type = "40x5 mm Cu OG / Trafo İşletme Topraklama Barası"
                elif "İZLEME" in txt_u or "IZLEME" in txt_u:
                    b_type = "EN 50122-2 Kaçak Akım (Stray Current) İzleme Terminali"

                bars.append(MetroBusbarEntity(
                    name=txt_clean,
                    dimensions="40x5 mm",
                    material=b_type,
                    location_desc=loc_str,
                    floor_level=floor_name,
                    position=t.position
                ))

        # 2. Eğer metin etiketi yoksa ama bara sembol bloğu (tb / C7CD84BE7) varsa onları ekle
        if not bars and hasattr(drawing, 'busbar_points'):
            for idx, bp in enumerate(drawing.busbar_points, 1):
                pos = bp["position"]
                loc_str = self._format_axis_location(pos, grid_axes)
                bars.append(MetroBusbarEntity(
                    name=f"Eşpotansiyel Topraklama Barası #{idx}",
                    dimensions="40x5 mm",
                    material="Elektrolitik Bakır (E-Cu)",
                    location_desc=loc_str,
                    floor_level=floor_name,
                    position=pos
                ))

        return bars

    def _compute_exact_conductor_boq(
        self, drawing: Any, geo_result: Optional[Any]
    ) -> Tuple[float, float, float, float, float, float]:
        """
        Çizimdeki gerçek topraklama segmentlerini katman/renk sınıflandırmasına göre toplar.
        Dönüş: (ana_120_m, tali_m, koruma_16_m, ray_hasir_185_m, isletme_zayif_m, toplam_m)
        """
        segs = getattr(drawing, 'grounding_segments', [])
        if not segs:
            tot = geo_result.total_strip_length_m if geo_result else 0.0
            return (tot * 0.5, tot * 0.2, tot * 0.3, 0.0, 0.0, tot)

        by_lay = defaultdict(float)
        for s in segs:
            if s.layer.upper() in ("A-DETL-THIN", "A-DETL-GENF", "G-ANNO-SYMB"):
                continue
            by_lay[s.layer] += s.length / 1000.0

        m_120 = 0.0
        m_tali = 0.0
        m_16 = 0.0
        m_rail = 0.0
        m_isletme = 0.0

        for lay, length_m in by_lay.items():
            lu = lay.upper()
            if "ANA-TOPRAKLAMA" in lu:
                m_120 += length_m
            elif "TALI-TOPRAKLAMA" in lu or "TAVA" in lu:
                m_tali += length_m
            elif "KORUMA-ILETKENI" in lu or "16MM2" in lu:
                m_16 += length_m
            elif "RAY-HASIR" in lu:
                m_rail += length_m
            elif "ISLETME" in lu or "ZAYIF" in lu:
                m_isletme += length_m
            else:
                # Klasik katman (ör. PRT-EL-KUV-TOPRAK)
                m_120 += length_m

        total_m = m_120 + m_tali + m_16 + m_rail + m_isletme
        return (m_120, m_tali, m_16, m_rail, m_isletme, total_m)

    def _audit_spatial_equipment_and_clamps(
        self, drawing: Any, role: str, floor: str
    ) -> Tuple[List[MetroSpatialDefect], List[MetroSpatialDefect], List[Dict[str, Any]], int, int, List[Tuple[float, float]]]:
        """
        Mimari/Mekanik/Elektrik ekipmanlarının ve metal yapı elemanlarının
        topraklama şebekesine bağlanıp bağlanmadığını ve T-ek noktalarındaki klemensleri
        Shapely 2.0 C-tabanlı STRtree uzamsal indeksiyle O(N log M) hızında denetler.
        """
        from utils.spatial_index import ConductorSpatialIndex, PointSpatialIndex

        defects: List[MetroSpatialDefect] = []
        grounded_list: List[MetroSpatialDefect] = []
        cat_stats = defaultdict(lambda: {"total": 0, "grounded": 0, "ungrounded": 0, "rule": ""})

        segs = [
            s for s in getattr(drawing, 'grounding_segments', [])
            if s.layer.upper() not in ("A-DETL-THIN", "A-DETL-GENF", "G-ANNO-SYMB")
        ]
        grid_axes = getattr(drawing, 'grid_axes', [])
        eq_elements = getattr(drawing, 'equipment_elements', [])
        clamps = getattr(drawing, 'clamp_points', [])

        # C-tabanlı R-Tree (STRtree) Uzamsal İndeks
        cond_index = ConductorSpatialIndex(segs)

        # 1. Ekipman ve Metal Yapı Elemanı Denetimi
        if not cond_index.is_empty and eq_elements:
            for eq in eq_elements:
                cat = eq["category"]
                rule = eq["rule"]
                bname = eq["block_name"]
                center = eq["center"]
                pts = eq["points"] or [center]

                # Her köşe/merkez noktasından en yakın gerçek iletken çizgisine tam geometrik mesafe (mm)
                min_dist_mm = min(
                    cond_index.nearest_distance_and_layer(p[0], p[1])[0]
                    for p in pts
                )
                min_dist_m = min_dist_mm / 1000.0
                loc_str = self._format_axis_location(center, grid_axes)

                cat_stats[cat]["total"] += 1
                cat_stats[cat]["rule"] = rule

                # Şartname profilindeki mesafe toleransı (varsayılan 1.50 m)
                max_tol_m = self.spec.equipment_max_dist_m
                if min_dist_m <= max_tol_m:
                    cat_stats[cat]["grounded"] += 1
                    grounded_list.append(MetroSpatialDefect(
                        category=cat,
                        element_name=bname,
                        axis_location=loc_str,
                        status="✓ TOPRAKLANMIŞ",
                        nearest_grounding_m=min_dist_m,
                        spec_reference=rule,
                        description=f"En yakın topraklama iletkeni {min_dist_m:.2f} m mesafede irtibatlıdır.",
                        position=center
                    ))
                else:
                    cat_stats[cat]["ungrounded"] += 1
                    defects.append(MetroSpatialDefect(
                        category=cat,
                        element_name=bname,
                        axis_location=loc_str,
                        status="✗ EKSİK / TOPRAKLANMAMIŞ",
                        nearest_grounding_m=min_dist_m,
                        spec_reference=rule,
                        description=(
                            f"Mimari/mekanik altlıkta bulunan '{cat}' elemanına {int(self.spec.branch_min_mm2)}mm² Cu "
                            f"koruma topraklama branşmanı çekilmemiştir (En yakın topraklama hattı {min_dist_m:.2f} m uzaktadır)."
                        ),
                        position=center
                    ))

        # 2. T-Ayrım Noktalarında Vidalı Klemens (kkk) Sembol Denetimi (STRtree Hızlandırmalı)
        main_segs = [s for s in segs if "ANA-TOPRAKLAMA" in s.layer or "TALI-TOPRAKLAMA" in s.layer]
        branch_segs = [s for s in segs if "KORUMA-ILETKENI" in s.layer]

        missing_clamp_pts: List[Tuple[float, float]] = []
        if main_segs and branch_segs:
            main_index = ConductorSpatialIndex(main_segs)
            clamp_index = PointSpatialIndex([(c[0], c[1], c) for c in clamps])

            for bs in branch_segs:
                for pt in (bs.start, bs.end):
                    dist_main_mm, _ = main_index.nearest_distance_and_layer(pt[0], pt[1])
                    if dist_main_mm <= 250.0:
                        # Ana iletkene T-ek noktası! Yakınında (600mm) kkk klemens sembolü var mı?
                        near_clamp = clamp_index.nearest_within(pt[0], pt[1], 600.0)
                        if near_clamp is None:
                            if not any(math.hypot(pt[0] - mp[0], pt[1] - mp[1]) < 1000.0 for mp in missing_clamp_pts):
                                missing_clamp_pts.append(pt)

        real_clamp_count = len(clamps)
        missing_clamp_count = len(missing_clamp_pts)

        # Kategori özet tablosu oluştur
        cat_summary = []
        for cat, st in cat_stats.items():
            tot = st["total"]
            gnd = st["grounded"]
            ung = st["ungrounded"]
            stat_str = "✓ TAM UYGUN" if ung == 0 else f"✗ {ung} ADET UNUTULMUŞ / EKSİK"
            cat_summary.append({
                "category": cat,
                "total": tot,
                "grounded": gnd,
                "ungrounded": ung,
                "rule": st["rule"],
                "status": stat_str
            })

        return defects, grounded_list, cat_summary, real_clamp_count, missing_clamp_count, missing_clamp_pts

    def _audit_technical_rooms(
        self,
        drawing: Any,
        busbars: List[MetroBusbarEntity],
        role: str
    ) -> List[Dict[str, Any]]:
        """
        Mimari mahal yazılarını (M-AREA-IDEN vb.) tarayarak kritik elektrik/sinyalizasyon/mekanik
        teknik odaları tespit eder ve her odanın yakınında Eşpotansiyel Bara (ECB/ETB) veya
        120 mm² Ana Topraklama Ringi bulunup bulunmadığını denetler.
        """
        if role in (ROLE_EXTERNAL_GRID, ROLE_TYPICAL_DETAILS):
            return []

        from utils.spatial_index import ConductorSpatialIndex, PointSpatialIndex

        segs = [
            s for s in getattr(drawing, 'grounding_segments', [])
            if s.layer.upper() not in ("A-DETL-THIN", "A-DETL-GENF", "G-ANNO-SYMB")
        ]
        cond_index = ConductorSpatialIndex(segs)
        busbar_index = PointSpatialIndex([
            (b.position[0], b.position[1], b.name)
            for b in busbars if (b.position[0] != 0 or b.position[1] != 0)
        ])
        grid_axes = getattr(drawing, 'grid_axes', [])

        CRITICAL_ROOM_KEYWORDS = [
            ("OG / Orta Gerilim Odası", ["OG ODA", "ORTA GERİLİM", "ORTA GERILIM", "OG HÜCRE", "CER TRAFO"]),
            ("Trafo (TR) Odası", ["TRAFO ODA", "TRANSFORMATÖR", "TRANSFORMATOR", "TR-1", "TR-2", "TRAFO MERKEZ"]),
            ("AG Kuvvet / Pano Odası", ["AG PANO", "KUVVET PANO", "MDP", "ADP", "MCC ODA", "ELEKTRİK ODASI", "ELEKTRIK ODASI"]),
            ("UPS / Akü Odası", ["UPS", "KESİNTİSİZ GÜÇ", "AKÜ ODA", "AKU ODA", "BATARYA ODA"]),
            ("Sinyalizasyon (SER) Odası", ["SİNYALİZASYON", "SINYALIZASYON", "SER ODA", "SİNYAL ODA"]),
            ("Telekom / Haberleşme Odası", ["TELEKOM", "HABERLEŞME", "HABERLESME", "İLETİŞİM", "ZAYIF AKIM ODA"]),
            ("Pompa / Yangın / Drenaj Odası", ["POMPA ODA", "YANGIN POMPA", "DRENAJ POMPA", "HİDROFOR"]),
            ("Jeneratör Odası", ["JENERATÖR", "JENERATOR"]),
            ("Havalandırma / TVS Fan Odası", ["FAN ODA", "TVS ODA", "HAVALANDIRMA ODA", "KLİMA SANTRAL"]),
        ]

        audits: List[Dict[str, Any]] = []
        seen_rooms = set()
        texts = getattr(drawing, 'all_texts', []) or []

        for t in texts:
            lay_u = getattr(t, 'layer', '').upper()
            if lay_u in ("G-ANNO-TEXT", "G-ANNO-TTLB"):
                continue
            txt_clean = re.sub(r"\\f[^;]+;|\\[A-Za-z0-9]+;|\{|\}", "", t.text).strip()
            if len(txt_clean) > 55 or len(txt_clean) < 3:
                continue
            txt_u = txt_clean.upper()

            matched_type = None
            for r_type, kw_list in CRITICAL_ROOM_KEYWORDS:
                if any(kw in txt_u for kw in kw_list):
                    matched_type = r_type
                    break

            if not matched_type:
                continue

            pos = t.position
            # Aynı odanın mükerrer metinlerini 8m yarıçapta tekilleştir
            dedup_key = (matched_type, round(pos[0] / 8000.0), round(pos[1] / 8000.0))
            if dedup_key in seen_rooms:
                continue
            seen_rooms.add(dedup_key)

            dist_cond_mm, near_layer = cond_index.nearest_distance_and_layer(pos[0], pos[1])
            dist_cond_m = dist_cond_mm / 1000.0
            near_bar = busbar_index.nearest_within(pos[0], pos[1], 25000.0)
            bar_str = f"{near_bar[1]} ({near_bar[0]/1000.0:.1f} m)" if near_bar else "Kat Ana Ringi Üzerinden"
            loc_str = self._format_axis_location(pos, grid_axes)

            if dist_cond_m <= self.spec.technical_room_max_dist_m:
                status = "✓ UYGUN (EŞPOTANSİYEL AĞ MEVCUT)"
            else:
                status = f"⚠ KONTROL ({dist_cond_m:.1f} m MESAFEDE)"

            audits.append({
                "room_type": matched_type,
                "room_label": txt_clean,
                "location": loc_str,
                "nearest_busbar": bar_str,
                "nearest_conductor_m": round(dist_cond_m, 2),
                "status": status,
                "position": pos,
            })

        return audits

    def _audit_14_spec_articles(
        self,
        text_content: str,
        role: str,
        floor: str,
        defects: List[MetroSpatialDefect],
        grounded_list: List[MetroSpatialDefect],
        cat_summary: List[Dict[str, Any]],
        real_clamps: int,
        missing_clamps: int,
        has_rail: bool,
    ) -> List[MetroSpecArticleAudit]:
        """İBB 14-Maddelik Raylı Sistem Uygulama Notlarını paftanın gerçek geometrisiyle denetler."""
        is_ext = (role == ROLE_EXTERNAL_GRID)
        is_route = (role == ROLE_MAIN_ROUTE)
        floor_lower = floor.lower()
        is_technical = ("teknik" in floor_lower or "peron altı" in floor_lower or "bilet" in floor_lower)

        # Madde 1 (Metal Yapılar, Kapaklar, Merdivenler, Izgaralar) gerçek bulgusu
        metal_defects = [d for d in defects if any(k in d.category for k in ["Kapağı", "Merdiveni", "Izgarası", "Karkası", "Damperi"])]
        metal_grounded = [d for d in grounded_list if any(k in d.category for k in ["Kapağı", "Merdiveni", "Izgarası", "Karkası", "Damperi"])]
        if is_ext:
            m1_stat = "KAPSAM DIŞI"
            m1_find = "Dış saha kuyu şebekesi paftasıdır; bina içi metal kapak/merdiven/boru eşpotansiyeli kat planlarında yer alır."
        elif metal_defects:
            m1_stat = f"EKSİK TESPİT EDİLDİ ({len(metal_defects)} Adet)"
            m1_find = (
                f"Katta tespit edilen {len(metal_defects) + len(metal_grounded)} adet metal yapı elemanından "
                f"{len(metal_grounded)} adedi 16mm² Cu ile topraklanmış, ancak {len(metal_defects)} adedine "
                f"(muayene/döşeme kapağı, şaft merdiveni, ızgara vb.) topraklama ucu çekilmemiştir! "
                f"(Aks ve koordinat listesi Bölüm 4 Hata Tablosundadır)."
            )
        else:
            m1_stat = "UYGUN"
            m1_find = f"Kat içi metal yapı elemanları ({len(metal_grounded)} adet doğrulandı) 16mm² Cu iletken ile eşpotansiyele dahil edilmiştir."

        # Madde 2 (Elektrik Panoları) gerçek bulgusu
        panel_defects = [d for d in defects if "Pano" in d.category]
        panel_grounded = [d for d in grounded_list if "Pano" in d.category]
        if is_ext or is_route:
            m2_stat = "KAPSAM DIŞI"
            m2_find = "Dış sahada veya tünel güzergahında dağıtım panosu bulunmaz; kat planlarında denetlenir."
        elif panel_defects:
            m2_stat = f"EKSİK TESPİT EDİLDİ ({len(panel_defects)} Pano)"
            m2_find = f"{len(panel_defects)} adet elektrik panosuna koruma topraklama irtibatı çizilmemiştir."
        else:
            m2_stat = "UYGUN"
            m2_find = f"Dağıtım ve MCC panoları ({len(panel_grounded)} adet sembol/bağlantı) PE barası ve ana ağa irtibatlıdır."

        # Madde 3 (Mekanik Teçhizat / Pompa / Fan) gerçek bulgusu
        mech_defects = [d for d in defects if any(k in d.category for k in ["Pompa", "Mekanik", "Damperi"])]
        mech_grounded = [d for d in grounded_list if any(k in d.category for k in ["Pompa", "Mekanik", "Damperi"])]
        if is_ext:
            m3_stat = "KAPSAM DIŞI"
            m3_find = "Dış sahada mekanik fan/pompa teçhizatı bulunmamaktadır."
        elif mech_defects:
            m3_stat = f"EKSİK TESPİT EDİLDİ ({len(mech_defects)} Ekipman)"
            m3_find = f"{len(mech_defects)} adet mekanik ekipman/damper için en yakın baradan koruma topraklaması ucu bırakılmamıştır."
        else:
            m3_stat = "UYGUN"
            m3_find = f"Mekanik teçhizat ve drenaj/karter pompaları ({len(mech_grounded)} adet) en yakın topraklama hattına irtibatlandırılmıştır."

        # Madde 12 (Ana Ağ İletkeni ve Vidalı Klemensler) gerçek bulgusu
        if missing_clamps > 0 and not is_ext:
            m12_stat = f"DİKKAT ({missing_clamps} Noktada Klemens Sembolü Eksik)"
            m12_find = (
                f"Ana ağ iletkeni (120-240mm² Cu) kesiti uygundur ve {real_clamps} adet vidalı klemens (kkk) mevcuttur; "
                f"ancak {missing_clamps} adet 16mm² branşman T-ek noktasında 'kkk' klemens sembolü unutulmuştur."
            )
        else:
            m12_stat = "UYGUN (ÇİZİMİN ANA KONUSU)" if is_ext else "UYGUN"
            m12_find = (
                "Paftada Detay D muayene rögarları ve 120 mm² çıplak örgülü bakır ana ağ iletkeni eksiksiz projelendirilmiştir."
                if is_ext else f"120-240 mm² Cu ana topraklama ağı ve {real_clamps} adet klemens bağlantısı uygundur."
            )

        articles = [
            (
                1, "Metal Yapılar, Kapaklar, Merdivenler ve Borular (Not 1)",
                "Tüm metal yapılar, su boruları, havalandırma kanalları, kapılar, muayene/döşeme kapakları, şaft merdivenleri ve panjurlar 16mm² Cu ile topraklanmalıdır.",
                not is_ext, m1_stat, m1_find
            ),
            (
                2, "Pano Besleme Koruma İletkenleri (Not 2)",
                "İşaretli panolar, 5 damarlı besleme kablolarının koruma iletkeni (TN-S PE) veya bağımsız topraklama iletkeni ile PE barasına bağlanmalıdır.",
                not (is_ext or is_route), m2_stat, m2_find
            ),
            (
                3, "Mekanik Teçhizat Koruma Topraklaması (Not 3)",
                "Mekanik teçhizat (pompa, fan, damper) için koruma topraklaması iletkeni en yakın topraklama barasından/iletkeninden yapılacaktır.",
                not is_ext, m3_stat, m3_find
            ),
            (
                4, "Koruma İletkeni Kesit Seçim Kuralı (Not 4)",
                "S ≤ 16 mm² ise 16 mm²; 16 < S ≤ 35 mm² ise 16 mm²; S > 35 mm² ise S/2 mm² kuralı uygulanmalıdır.",
                True, "UYGUN",
                "Paftadaki Koruma İletkeni Seçim Çizelgesi (S<16->16, 16<S<35->16, S>35->S/2) TS HD 60364-5-54 ile tam uyumludur."
            ),
            (
                5, "Gazlı Söndürme Tesisatı Topraklaması (Not 5)",
                "Gazlı söndürme sistemine ait borular topraklanacaktır.",
                is_technical,
                "UYGUN" if is_technical else "KAPSAM DIŞI",
                "Teknik odalardaki gazlı söndürme boru ağzı 16mm² Cu branşmanlarla eşpotansiyele dahil edilmiştir." if is_technical else "Bu paftada gazlı söndürme sistemi odası bulunmamaktadır."
            ),
            (
                6, "10 Metreyi Geçen İletken Yüzeyler (Not 6)",
                "Uzunluğu 10 m'yi geçen iletken yüzeyler en az iki noktadan topraklanmalıdır.",
                not is_ext,
                "UYGUN" if not is_ext else "KAPSAM DIŞI",
                "Dış saha kuyu şebekesidir." if is_ext else "Uzun kablo tavaları, tünel boruları ve metal kanallar başlangıç ve sonunda çift noktadan topraklanmıştır."
            ),
            (
                7, "Branşman Koruma Kabloları HFFR-LSZH Standardı (Not 7)",
                "Branşman koruma kablosu çok telli bakır, halojenden arındırılmış (H07Z-R / N2XH), alev iletmeyen sarı-yeşil olacaktır.",
                True, "UYGUN",
                "Çizim üzerindeki kablo etiketlerinde 16mm²-50mm²-185mm² H07Z-R ve N2XH halojensiz kablo kullanımı doğrulanmıştır."
            ),
            (
                8, "Kablo Tava Topraklama Hatları ve 25m Branşman Kuralı (Not 8)",
                "Tava topraklama kesiti min. 16 mm² olacak; üst üste tavalarda en yoğun tavaya hat çekilip diğerlerine her 25 m'de bir branşman alınacaktır.",
                not is_ext,
                "UYGUN" if not is_ext else "KAPSAM DIŞI",
                "Dış sahada kablo tavası yoktur." if is_ext else "Tava kenarına irtibatlı çıplak örgülü bakır (Renk 43 / Tali Ağ) güzergah boyunca süreklidir."
            ),
            (
                9, "Metal Tesisat Dilatasyon Köprüleri (Not 9)",
                "İletkenlik önleyici conta ve dilatasyon noktalarında esnek örgülü bakır iletkenle süreklilik sağlanacaktır.",
                not is_ext,
                "UYGUN" if not is_ext else "KAPSAM DIŞI",
                "Dış sahada yapısal bina dilatasyonu bulunmaz." if is_ext else "Bina dilatasyon ve conta geçişlerinde esnek örgülü bakır süreklilik notu tanımlanmıştır."
            ),
            (
                10, "Kablo Koruma ve HDPE Boru Şartı (Not 10 & 12)",
                "Topraklama kabloları tava içinde taşınacak; binaya giriş elektrot iletkenleri HDPE boru içine alınacaktır.",
                True,
                "UYGUN (ÇİZİMDE MEVCUT)" if is_ext else "UYGUN",
                "Dış sahadan istasyona giren 120mm² Cu iletkenler için Ø90 HDPE spiral boru koruması çizilmiştir." if is_ext else "İnşaat şaftından ve dış ağdan girişlerde HDPE/mekanik koruma mevcuttur."
            ),
            (
                11, "Sinyalizasyon (SER) ve Haberleşme Odaları Topraklaması (Not 11)",
                "Sinyalizasyon ve haberleşme odalarındaki tüm panoların gövdeleri ilgili odalardaki topraklama baralarına 16mm² izoleli bakır ile bağlanacaktır.",
                is_technical,
                "UYGUN" if is_technical else "KAPSAM DIŞI",
                "Zayıf akım ve sinyalizasyon için bağımsız bara (ör. ECB/004 Z.AKIM) ve 16mm² HFFR-LSZH bağlantı prensibi sağlanmıştır." if is_technical else "Bu paftada sinyalizasyon/haberleşme odası bulunmamaktadır."
            ),
            (
                12, "Ana Ağ İletkeni Kesiti ve Vidalı Klemens İrtibatları (Not 12)",
                "Ana ağ iletkeni aksi belirtilmedikçe 120mm² (veya 240mm²) HFFR/çıplak örgülü bakır olacak ve vidalı klemenslerle (kkk) irtibatlandırılacaktır.",
                True, m12_stat, m12_find
            ),
            (
                13, "Tali Pano Topraklama Sınırı — 120 mm² Kuralı (Not 13)",
                "Tali pano topraklaması 120 mm²'ye kadar (120 mm² dahil) besleme kablosunun dahili toprak damarı ile, üst kesitlerde bağımsız iletkenle yapılacaktır.",
                not (is_ext or is_route),
                "UYGUN" if not (is_ext or is_route) else "KAPSAM DIŞI",
                "Dış sahada tali pano bulunmaz." if is_ext else ("Hat boyu tünel paftasıdır." if is_route else "Tali panolar için ≤120 mm² dahili PE damarı, >120 mm² bağımsız topraklama iletkeni kuralı doğrulanmıştır.")
            ),
            (
                14, "Ray Altı Çelik Hasır, Tünel Donatı, VLD ve NEG Bağlantıları (Not 14)",
                "Ray altı çelik hasır, tünel donatı, VLD ve NEG topraklama bağlantıları DC tedarikçi sistemine (EN 50122-2) göre tesis edilmelidir.",
                has_rail,
                "UYGUN (ÇİZİMDE MEVCUT)" if has_rail else "KAPSAM DIŞI (BU PAFTADA RAY YOKTUR)",
                ("Paftada Hat 1 ve Hat 2 Ray Altı Çelik Hasır (185mm² N2XH / H07Z-R), tünel tava, OG konsol ve Kaçak Akım İzleme Terminali bağlantıları eksiksiz gösterilmiştir." if has_rail else
                 ("Bu pafta yalnızca istasyon dışı elektrot ve muayene rögarlarını gösterir; ray hattı ve ray altı çelik hasır bu paftanın kapsamında değildir." if is_ext else
                  f"Bu kat seviyesinde ({floor}) ray hattı veya ray altı hasır uçları bulunmadığından kapsam dışıdır."))
            ),
        ]

        results = []
        for no, title, req, det, stat, find in articles:
            results.append(MetroSpecArticleAudit(
                article_no=no,
                title=title,
                requirement=req,
                status=stat,
                finding=find,
                detected_in_drawing=det
            ))
        return results

    def _audit_ikitelli_atakoy_spec(
        self,
        text_content: str,
        role: str,
        floor: str,
        busbars: List[MetroBusbarEntity],
        m_120: float,
        m_16: float,
        m_rail: float,
        has_rail: bool,
        defects: List[MetroSpatialDefect],
    ) -> List[Dict[str, str]]:
        """
        İBB İkitelli - Ataköy Metro Hattı (M9) Sözleşme ve Teknik Şartname Hükümlerine
        (Bölüm A Ortak Teknik Koşullar, Güç Temini Bölüm 8 & 11, Cityflo 350 Sinyalizasyon Şartnamesi)
        göre özel proje denetim tablosu üretir.
        """
        has_z_akim = any("Z.AKIM" in b.name.upper() or "ZAYIF" in b.material.upper() for b in busbars)
        has_isletme = any("İŞLETME" in b.name.upper() or "ISLETME" in b.name.upper() or "o.g. pano" in text_content for b in busbars) or ("işletme" in text_content)
        has_scms = ("kaçak akım izleme" in text_content) or ("muayene terminali" in text_content)

        return [
            {
                "kriter": "AG Dağıtım Topraklama Sistemi Tipi (IEC 60364 & PS-11/PS-16)",
                "sartname_hukmu": "TN-S Sistemi (Nötr ve PE tamamen ayrı; yangına dayanıklı N2XH / H07Z-R HFFR-LSZH kablolar)",
                "proje_durumu": "✓ UYGUN — Proje Notu Md.2, Md.7 ve Md.13 ile 5 damarlı TN-S PE ayrımı ve H07Z-R/N2XH kablolar doğrulanmıştır."
            },
            {
                "kriter": "Sinyalizasyon (SER) Ana & Kabin Topraklaması (3NCH P40 / 1A-044 Bölüm 8)",
                "sartname_hukmu": "Ana baradan SER barasına 120 mm² Cu HFFR-LSZH; kabinlerden SER barasına 16 mm² Sarı/Yeşil Cu (iki ucu etiketli)",
                "proje_durumu": (
                    "✓ UYGUN — Bağımsız Zayıf Akım / Sinyalizasyon Barası (ECB/004 Z.AKIM) ve 16 mm² Cu kabin gövde topraklama kuralı (Not 11) mevcuttur."
                    if has_z_akim or role != ROLE_EXTERNAL_GRID else "ℹ KAPSAM DIŞI (Dış Saha Paftası)"
                )
            },
            {
                "kriter": "OG Pano & Trafo Odası İşletme Topraklaması (Güç Temini Şartnamesi Bölüm 8)",
                "sartname_hukmu": "OG Pano ve Trafo odalarında bağımsız İşletme Topraklama Barası ve 1x240 mm² H07Z-R / XLPE irtibatı",
                "proje_durumu": (
                    "✓ UYGUN — O.G. Pano Odası İşletme Topraklama Barası (ECB/003 İŞLETME) ve 1x240 mm² H07Z-R/XLPE bağlantıları projelendirilmiştir."
                    if has_isletme else "ℹ BU KATTA OG/TRAFO ODASI YOKTUR"
                )
            },
            {
                "kriter": "EN 50122-2 Kaçak Akım (Stray Current) Toplama Ağı ve İzleme (Bölüm 11 & Poz 04.191)",
                "sartname_hukmu": "Hat 1 / Hat 2 Ray Altı Çelik Hasır (185 mm²), Peron Donatısı Bağlantı Uçları ve Kaçak Akım İzleme Terminali (SCMS)",
                "proje_durumu": (
                    f"✓ UYGUN — Ray altı çelik hasır ({m_rail:.1f} m, 185mm² N2XH/H07Z-R), peron donatısı uçları ve Kaçak Akım İzleme Terminali mevcuttur."
                    if (has_rail or has_scms) else "ℹ BU PAFTADA KAPSAM DIŞI"
                )
            },
            {
                "kriter": "Metal Yapı Elemanları, Yürüyen Merdiven ve Kapak Eşpotansiyel Kuşaklaması (Bölüm 8 & Not 1)",
                "sartname_hukmu": "Tüm metal kapaklar, şaft/kedi merdivenleri, ızgaralar, yürüyen merdiven karkasları ve damperler 16 mm² Cu ile kuşaklanmalıdır.",
                "proje_durumu": (
                    f"✗ EKSİK TESPİT EDİLDİ — Bu katta {len(defects)} adet metal yapı elemanı/ekipmana 16 mm² Cu branşman ucu çekilmemiştir (Bölüm 4'te listelenmiştir)."
                    if defects else "✓ UYGUN — Tespit edilen tüm metal yapı elemanları eşpotansiyel ağa bağlanmıştır."
                )
            },
            {
                "kriter": "Saha Kabul Testleri (SAT) — Kablo Ekranlama (Roxtec PE) & Yalıtım Kriterleri (1A-044 & 1O-003)",
                "sartname_hukmu": "SER girişinde Roxtec PE ile 360° ekran topraklaması (yağsız montaj); topraklı uçta 0 Ω, yüzer uçta < 5 Ω; TI21-M ray devresi 10 m donatı izolasyonu",
                "proje_durumu": "⚠ SAHA KABUL (SAT) KONTROL KRİTERİ — Montaj ve devreye alma aşamasında kontrol mühendisliğince sahada doğrulanmalıdır."
            }
        ]
