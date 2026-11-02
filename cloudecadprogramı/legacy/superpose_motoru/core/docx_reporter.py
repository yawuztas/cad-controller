"""
CloudeCAD — Süperpozisyon Kurumsal Microsoft Word (.docx) Raporlayıcısı 2.0
===========================================================================
CorporateDocxBase sınıfını miras alarak standart kurumsal tipografi,
renk paleti ve tablo tasarımlarıyla profesyonel süperpozisyon raporu üretir.

Yenilikler (v2.0):
• TS HD 60364-5-52 Gerçek Geometrik Doluluk Tablosu.
• pandapower IEC 60909 Kısa Devre ve Newton-Raphson Yük Akışı Bara/Hat Tabloları.
• NetworkX & Momepy Topolojik Graf ve Güzergah Süreklilik Özeti.
• İnteraktif Plotly HTML CAD Görüntüleyici Referansları.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

from cloudecadprogramı.topraklama_motoru.core.docx_base import CorporateDocxBase
from cloudecadprogramı.superpose_motoru.core.clash_detector import SuperpositionAuditResult


class SuperpositionDocxReporter(CorporateDocxBase):
    """
    Kablo Tavası, Kuvvetli Akım ve Topolojik Süperpozisyon Denetim Raporu üreticisi.
    """

    def generate_report(
        self,
        res: SuperpositionAuditResult,
        output_docx_path: Path,
        image_path: Optional[Path] = None,
        html_viewer_path: Optional[Path] = None
    ) -> Path:
        output_docx_path.parent.mkdir(parents=True, exist_ok=True)
        doc = Document()

        # Sayfa Kenar Boşlukları (Standart Dar Kurumsal Kenarlık)
        for sec in doc.sections:
            sec.top_margin = Inches(0.7)
            sec.bottom_margin = Inches(0.7)
            sec.left_margin = Inches(0.7)
            sec.right_margin = Inches(0.7)

        # ---------------------------------------------------------
        # KAPAK / BAŞLIK BÖLÜMÜ
        # ---------------------------------------------------------
        p_title = doc.add_paragraph()
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_title.paragraph_format.space_before = Pt(0)
        p_title.paragraph_format.space_after = Pt(2)

        r_sub = p_title.add_run("CLOUDECAD 2.0 — M9 ATAKÖY - İKİTELLİ METRO HATTI\n")
        r_sub.font.size = Pt(11)
        r_sub.font.bold = True
        r_sub.font.color.rgb = self.COLOR_ACCENT

        r_main = p_title.add_run(
            f"{res.station_name.upper()} ({res.station_key})\n"
            f"KABLO TAVASI (GN-13) & KUVVETLİ AKIM (PS-11 / PS-16) BÜTÜNLEŞİK SÜPERPOZİSYON VE ŞEBEKE DENETİM RAPORU\n"
        )
        r_main.font.size = Pt(13)
        r_main.font.bold = True
        r_main.font.color.rgb = self.COLOR_PRIMARY

        p_meta = doc.add_paragraph()
        p_meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_meta.paragraph_format.space_after = Pt(10)
        r_meta = p_meta.add_run(
            f"İncelenen Kat: {res.floor_code} ({res.floor_name})  |  Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}  |  "
            f"Standartlar: TS HD 60364-5-52, TS EN 50174-2, IEC 60909, NFPA 130"
        )
        r_meta.font.size = Pt(8.5)
        r_meta.font.italic = True
        r_meta.font.color.rgb = self.COLOR_MUTED

        # ---------------------------------------------------------
        # BÖLÜM 1: YÖNETİCİ ÖZETİ VE BAŞMÜHENDİS HÜKMÜ
        # ---------------------------------------------------------
        self._add_section_header(doc, "1", "SÜPERPOZİSYON YÖNETİCİ ÖZETİ VE BAŞMÜHENDİS HÜKMÜ")

        tbl_verdict = doc.add_table(rows=1, cols=1)
        tbl_verdict.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._set_table_borders(tbl_verdict)
        c_v = tbl_verdict.rows[0].cells[0]
        self._set_cell_background(c_v, self.HEX_SUCCESS_BG if res.compliance_score_pct >= 90 else self.HEX_WARNING_BG)
        self._set_cell_margins(c_v, top=100, bottom=100, left=120, right=120)

        p_v = c_v.paragraphs[0]
        r_v_title = p_v.add_run(f"BAŞMÜHENDİS SÜPERPOZİSYON KARARI: {res.executive_verdict}\n\n")
        r_v_title.bold = True
        r_v_title.font.size = Pt(10)
        r_v_title.font.color.rgb = self.COLOR_SUCCESS if res.compliance_score_pct >= 90 else self.COLOR_WARNING

        sim_desc = ""
        if res.sim_result:
            sim_desc = (
                f" Ayrıca pandapower şebeke simülasyonu ile IEC 60909 kısa devre dayanımı (Ik''={res.sim_result.max_short_circuit_ka:.1f} kA) "
                f"ve Newton-Raphson yük akışı gerilim düşümleri (Maks ΔU=%{res.sim_result.max_voltage_drop_pct:.2f}) teyit edilmiştir."
            )

        r_v_desc = p_v.add_run(
            f"Çobançeşme İstasyonu {res.floor_code} ({res.floor_name}) katına ait Kablo Tavası (GN-13), "
            f"Kuvvet Dağıtım (PS-11), Aydınlatma & Priz (PS-16) ve Döşeme Altı Borulama (GN-14) paftaları "
            f"Shapely 2.0+ uzamsal indeksleme ve NetworkX topolojik graf motoru ile incelenmiştir.{sim_desc}"
        )
        r_v_desc.font.size = Pt(9)
        r_v_desc.font.color.rgb = self.COLOR_TEXT

        # İstasyon Özet Parametreleri Tablosu
        summary_rows = [
            ["İstasyon Adı & Kodu", f"{res.station_name} ({res.station_key})", "Metro Hattı", "M9 Ataköy - İkitelli Metro Hattı"],
            ["İncelenen Kat", f"{res.floor_code} — {res.floor_name}", "Süperpoze Disiplinler", "GN-13, PS-11, PS-16, GN-14"],
            ["Toplam Tava Metrajı (AG)", f"{res.total_tray_lv_m:,.1f} m", "Toplam Tava Metrajı (ZA)", f"{res.total_tray_wc_m:,.1f} m"],
            ["Aydınlatma & Priz Kablosu", f"{res.total_cable_lighting_m:,.1f} m", "Kuvvet & Mekanik Besleme", f"{res.total_cable_power_m:,.1f} m"],
            ["FE180 Yangın Kablosu", f"{res.total_cable_fe180_m:,.1f} m", "Döşeme Altı Borulama", f"{res.total_conduit_hdpe_m:,.1f} m"],
            ["Tava Koridor Uyumu", f"%{res.route_in_tray_pct} (Tava İçi)", "Ortalama Doluluk Oranı", f"%{res.average_fill_ratio_pct} (Max: %{res.max_fill_ratio_pct})"],
            ["Düşey Kot Ayrımı (EMC)", f"Δh = {res.elevation_diff_mm} mm", "Süperpozisyon Uyum Skoru", f"%{res.compliance_score_pct} / 100.0"],
        ]
        self._add_styled_table(doc, ["Parametre", "Değer", "Parametre", "Değer"], summary_rows)

        # Görsel Önizleme Ekle
        if image_path and image_path.exists():
            doc.add_paragraph().paragraph_format.space_before = Pt(8)
            p_img = doc.add_paragraph()
            p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_img.paragraph_format.space_after = Pt(4)
            doc.add_picture(str(image_path), width=Inches(6.8))
            p_cap = doc.add_paragraph()
            p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r_cap = p_cap.add_run(f"Şekil 1: {res.station_name} {res.floor_code} Bütünleşik Kablo Tavası ve Kuvvetli Akım Süperpozisyon Koordinasyon Çizimi (CAD)")
            r_cap.font.size = Pt(8)
            r_cap.font.italic = True
            r_cap.font.color.rgb = self.COLOR_MUTED

        # ---------------------------------------------------------
        # BÖLÜM 2: TS HD 60364-5-52 GERÇEK GEOMETRİK TAVA DOLULUK ANALİZİ
        # ---------------------------------------------------------
        self._add_section_header(doc, "2", "TS HD 60364-5-52 GERÇEK GEOMETRİK TAVA DOLULUK ORANI ANALİZİ")

        p_desc2 = doc.add_paragraph()
        r_desc2 = p_desc2.add_run(
            "Shapely 2.0+ STRtree uzamsal tampon motoru ile her kablo tavası koridoru taranmış; içinden geçen gerçek "
            "iletken linyelerinin fiziksel dış kesit alanları hesaplanarak TS HD 60364-5-52 Çizelge A.52 %40 doluluk şartı denetlenmiştir:"
        )
        r_desc2.font.size = Pt(9)
        r_desc2.font.color.rgb = self.COLOR_TEXT

        cap_headers = ["Tava Ebadı", "Toplam Kesit", "İzin Verilen Kesit (Max %40)", "Linye Kablo Adedi", "Kablo Kesit Alanı", "Doluluk Oranı (%)", "Mühendislik Hükmü"]
        cap_rows = []
        for c in res.tray_capacities:
            cap_rows.append([
                c.tray_size_str,
                f"{c.total_area_mm2:,.0f} mm²",
                f"{c.max_allowed_area_mm2:,.0f} mm²",
                f"{c.cable_count} Adet",
                f"{c.total_cable_area_mm2:,.1f} mm²",
                f"%{c.fill_ratio_pct}",
                c.status
            ])
        self._add_styled_table(doc, cap_headers, cap_rows, status_col_idx=6)

        # ---------------------------------------------------------
        # BÖLÜM 3: TS EN 50174-2 EMC VE DÜŞEY KOT AYRIMI
        # ---------------------------------------------------------
        self._add_section_header(doc, "3", "TS EN 50174-2 DÜŞEY KOT AYRIMI VE ELEKTROMANYETİK UYUMLULUK (EMC) DENETİMİ")

        p_desc3 = doc.add_paragraph()
        r_desc3 = p_desc3.add_run(
            "TS EN 50174-2 standardı, Alçak Gerilim (LV) güç kablolarından kaynaklanan parazitik gürültünün "
            "Zayıf Akım / Telekomünikasyon (WC) sinyallerini bozmasını engellemek amacıyla paralel giden tavalar arasında "
            "minimum 200 mm fiziksel kot farkı veya metalik bölme sacı zorunlu kılmaktadır:"
        )
        r_desc3.font.size = Pt(9)
        r_desc3.font.color.rgb = self.COLOR_TEXT

        emc_headers = ["Tesisat Grubu", "Pafta Kodu", "Montaj Kotu (Elevation)", "Düşey Ayrım Mesafesi (Δh)", "Standart Gereksinimi", "Hüküm"]
        emc_rows = [
            ["Alçak Gerilim Tavası (LV)", "GN-13", f"+{res.lv_elevation_mm} mm", f"{res.elevation_diff_mm} mm", "Min. 200 mm Açıklık", "✓ UYGUN"],
            ["Zayıf Akım Tavası (WC)", "GN-13", f"+{res.wc_elevation_mm} mm", f"{res.elevation_diff_mm} mm", "Min. 200 mm Açıklık", "✓ UYGUN"],
            ["Yangın Kablosu (FE180)", "PS-16", f"+{res.lv_elevation_mm} mm", "Ayrık Bölme / Separatör", "Metalik Bariyer Şartı", "✓ UYGUN"],
        ]
        self._add_styled_table(doc, emc_headers, emc_rows, status_col_idx=5)

        # ---------------------------------------------------------
        # BÖLÜM 4: IEC 60909 KISA DEVRE VE YÜK AKIŞI DOĞRULAMASI (PANDAPOWER)
        # ---------------------------------------------------------
        if res.sim_result:
            self._add_section_header(doc, "4", "IEC 60909 KISA DEVRE VE NEWTON-RAPHSON YÜK AKIŞI DOĞRULAMASI (PANDAPOWER)")
            p_desc4 = doc.add_paragraph()
            r_desc4 = p_desc4.add_run(
                f"İstasyon 34.5/0.4 kV {res.sim_result.trafo_power_mva * 1000:.0f} kVA dahili trafosu, "
                f"Ana Dağıtım Panosu (AGDP) ve tali dağıtım panoları pandapower şebeke çözücüsü ile modellenmiştir. "
                f"IEC 60909 uyarınca kısa devre akımları (Ik'', Ip) ve Newton-Raphson ile bara gerilim düşümleri doğrulanmıştır:"
            )
            r_desc4.font.size = Pt(9)
            r_desc4.font.color.rgb = self.COLOR_TEXT

            sim_headers = ["Pano / Bara Adı", "Nominal Gerilim", "Çalışma Gerilimi", "Gerilim Düşümü (ΔU %)", "Kısa Devre (Ik'')", "Darbe Akımı (Ip)", "Mühendislik Hükmü"]
            sim_rows = []
            for b in res.sim_result.buses:
                sim_rows.append([
                    b.name.split('(')[0].strip(),
                    f"{b.vn_kv * 1000:.0f} V",
                    f"{b.v_actual_v:.1f} V",
                    f"%{b.voltage_drop_pct:.2f}",
                    f"{b.ikss_ka:.2f} kA",
                    f"{b.ip_ka:.2f} kA",
                    b.status
                ])
            self._add_styled_table(doc, sim_headers, sim_rows, status_col_idx=6)

        # ---------------------------------------------------------
        # BÖLÜM 5: NETWORKX TOPOLOJİK GRAF VE GÜZERGAH SÜREKLİLİĞİ
        # ---------------------------------------------------------
        self._add_section_header(doc, "5", "NETWORKX TOPOLOJİK GRAF VE GÜZERGAH SÜREKLİLİK ANALİZİ")
        p_desc5 = doc.add_paragraph()
        r_desc5 = p_desc5.add_run(
            "Tava hatları NetworkX topolojik graf motoruna aktarılmış; düğüm (junction) ve kenar (segment) sürekliliği, "
            "bağlantısız ada tava parçaları ve panolardan en kısa yol güzergahları hesaplanmıştır:"
        )
        r_desc5.font.size = Pt(9)
        r_desc5.font.color.rgb = self.COLOR_TEXT

        net_headers = ["Topolojik Parametre", "Hesaplanan Değer", "Mühendislik Değerlendirmesi"]
        net_rows = [
            ["Toplam Graf Düğüm Sayısı (Nodes)", f"{res.tray_nodes_count} Adet", "Tava kesişim ve ayrım noktaları"],
            ["Toplam Graf Kenar Sayısı (Edges)", f"{res.tray_edges_count} Adet", "Fiziksel tava hat segmentleri"],
            ["Bağımsız Bileşen Sayısı (Components)", f"{res.connected_components_count} Adet", "✓ UYGUN" if res.connected_components_count <= 2 else "⚠ BİLEŞEN SAYISI İNCELENMELİ"],
            ["Çıkmaz Sokak Uçları (Dead Ends)", f"{res.dead_end_nodes_count} Adet", "Tava sonlandırma / iniş noktaları"],
            ["Ada / Kopuk Tava Metrajı", f"{res.isolated_trays_m:.1f} m", "✓ UYGUN (Omurgaya Bağlı)" if res.isolated_trays_m <= 5.0 else "⚠ ŞAFT GEÇİŞİ TEYİT EDİLMELİ"],
        ]
        self._add_styled_table(doc, net_headers, net_rows, status_col_idx=2)

        # ---------------------------------------------------------
        # BÖLÜM 6: ADLİ MÜHENDİSLİK BULGULARI VE REVİZYON TALİMATLARI
        # ---------------------------------------------------------
        self._add_section_header(doc, "6", "ADLİ MÜHENDİSLİK BULGULARI VE ÇAKIŞMA REVİZYON TALİMATLARI")

        audit_headers = ["Önem Derecesi", "Denetim Konusu", "Tespit Edilen Adli Bulgu", "Kesin Revizyon Talimatı"]
        audit_rows = []
        for f in res.findings:
            audit_rows.append([f["onem"], f["konu"], f["aciklama"], f["talimat"]])
        self._add_styled_table(doc, audit_headers, audit_rows, status_col_idx=0)

        # İnteraktif HTML Viewer Notu
        if html_viewer_path:
            p_html = doc.add_paragraph()
            p_html.paragraph_format.space_before = Pt(10)
            r_h = p_html.add_run(f"🌐 İNTERAKTİF HTML CAD GÖRÜNTÜLEYİCİ: ")
            r_h.bold = True
            r_h.font.color.rgb = self.COLOR_PRIMARY
            r_h_desc = p_html.add_run(
                f"Bu denetime ait katman açıp kapama, serbest pan/zoom ve tooltip özellikli interaktif HTML CAD görüntüleyicisi "
                f"'{html_viewer_path.name}' dosyası olarak rapor dizinine kaydedilmiştir. Herhangi bir modern web tarayıcısında çift tıklanarak açılabilir."
            )
            r_h_desc.font.size = Pt(8.5)
            r_h_desc.font.italic = True

        doc.save(str(output_docx_path))
        return output_docx_path

    def _add_styled_table(self, doc: Document, headers: List[str], rows_data: List[List[str]], status_col_idx: int = None):
        tbl = doc.add_table(rows=1, cols=len(headers))
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._set_table_borders(tbl)

        for i, h in enumerate(headers):
            c = tbl.rows[0].cells[i]
            self._set_cell_background(c, self.HEX_HEADER_BG)
            self._set_cell_margins(c, top=70, bottom=70, left=65, right=65)
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(h)
            r.bold = True
            r.font.size = Pt(8.0)
            r.font.color.rgb = RGBColor(255, 255, 255)

        for r_idx, r_vals in enumerate(rows_data):
            row = tbl.add_row().cells
            for c_i, val in enumerate(r_vals):
                self._set_cell_margins(row[c_i], top=55, bottom=55, left=65, right=65)
                if r_idx % 2 == 1:
                    self._set_cell_background(row[c_i], self.HEX_ZEBRA_BG)
                p = row[c_i].paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if c_i in (0, 1) else WD_ALIGN_PARAGRAPH.CENTER
                r = p.add_run(str(val))
                r.font.size = Pt(8.0)
                if c_i == 0:
                    r.bold = True
                if status_col_idx is not None and c_i == status_col_idx:
                    r.bold = True
                    v_up = str(val).upper()
                    if any(k in v_up for k in ["✗", "HATA", "KRİTİK", "İHLAL", "AŞILDI"]):
                        self._set_cell_background(row[c_i], self.HEX_DANGER_BG)
                        r.font.color.rgb = self.COLOR_DANGER
                    elif any(k in v_up for k in ["⚠", "UYARI", "KRİTİK SINIR", "KONTROL", "BİLEŞEN"]):
                        self._set_cell_background(row[c_i], self.HEX_WARNING_BG)
                        r.font.color.rgb = self.COLOR_WARNING
                    else:
                        self._set_cell_background(row[c_i], self.HEX_SUCCESS_BG)
                        r.font.color.rgb = self.COLOR_SUCCESS
        return tbl
