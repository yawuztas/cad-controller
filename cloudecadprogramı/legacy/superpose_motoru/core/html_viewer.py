"""
CloudeCAD — İnteraktif HTML CAD Görüntüleyici (Interactive Plotly CAD Viewer)
=============================================================================
WebGL tabanlı donanım hızlandırmalı grafik motoru ile binlerce CAD hattını,
kablo tavalarını, panoları ve çakışma uyarılarını web tarayıcısında gerçek zamanlı
pan/zoom, katman açma/kapama (layer visibility toggle) ve zengin tooltip'lerle sunar.
"""

import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

import plotly.graph_objects as go

from cloudecadprogramı.superpose_motoru.core.cad_superposer import SuperposeSegment, SuperposeAnnotation


class InteractiveHtmlCadViewer:
    """
    Süperpozisyon verilerini donanım hızlandırmalı (Scattergl) interaktif
    HTML CAD görüntüleyicisine dönüştürür.
    """

    def __init__(self, station_name: str, station_key: str, floor_code: str):
        self.station_name = station_name
        self.station_key = station_key
        self.floor_code = floor_code

    def generate_html_viewer(
        self,
        output_html_path: Path,
        segments: List[SuperposeSegment],
        annotations: List[SuperposeAnnotation],
        panels: List[Tuple[float, float, str]],
        clash_points: List[Tuple[float, float, str, str]],
        audit_res: Any = None,
        sim_res: Any = None,
        network_graph_paths: Optional[List[List[Tuple[float, float]]]] = None
    ) -> Path:
        """
        Tüm katmanları WebGL çizgileri olarak derler ve modern bir HTML gösterici üretir.
        """
        output_html_path.parent.mkdir(parents=True, exist_ok=True)
        fig = go.Figure()

        # Katman renk ve çizgi kalınlık tanımları
        cat_styles = {
            "MIMARI": {
                "name": "00 — Mimari & Strüktür Referansı (ARC)",
                "color": "#475569",
                "width": 1.0,
                "opacity": 0.55,
                "visible": True
            },
            "TAVA_LV": {
                "name": "01 — Alçak Gerilim Tavaları (GN-13)",
                "color": "#06B6D4",   # Neon Camgöbeği (Cyan)
                "width": 2.5,
                "opacity": 0.95,
                "visible": True
            },
            "TAVA_WC": {
                "name": "02 — Zayıf Akım Tavaları (WC)",
                "color": "#E879F9",   # Neon Magenta
                "width": 2.2,
                "opacity": 0.95,
                "visible": True
            },
            "KABLO_NORM": {
                "name": "03 — Normal Aydınlatma & Priz (PS-16)",
                "color": "#F8FAFC",   # Beyaz
                "width": 1.2,
                "opacity": 0.85,
                "visible": True
            },
            "KABLO_FE180": {
                "name": "04 — NFPA 130 FE180 Yangın Kabloları",
                "color": "#EF4444",   # Kırmızı
                "width": 2.6,
                "opacity": 1.0,
                "visible": True
            },
            "KUVVET": {
                "name": "05 — Kuvvet & Mekanik Beslemeler (PS-11)",
                "color": "#FB923C",   # Turuncu
                "width": 2.0,
                "opacity": 0.9,
                "visible": True
            },
            "BORU": {
                "name": "06 — Döşeme Altı HDPE Borulama (GN-14)",
                "color": "#38BDF8",   # Açık Mavi
                "width": 1.4,
                "opacity": 0.85,
                "visible": "legendonly"
            }
        }

        # 1. Çizgi Katmanlarını Scattergl ile Ekle (Nan/None ile ayrılmış tekil trace)
        grouped_lines: Dict[str, Tuple[List[Optional[float]], List[Optional[float]]]] = {
            cat: ([], []) for cat in cat_styles
        }

        for seg in segments:
            c = seg.category
            if c in grouped_lines:
                grouped_lines[c][0].extend([seg.x1, seg.x2, None])
                grouped_lines[c][1].extend([seg.y1, seg.y2, None])

        for cat, (xs, ys) in grouped_lines.items():
            if not xs:
                continue
            style = cat_styles[cat]
            fig.add_trace(go.Scattergl(
                x=xs,
                y=ys,
                mode="lines",
                name=style["name"],
                line=dict(color=style["color"], width=style["width"]),
                opacity=style["opacity"],
                visible=style["visible"],
                hoverinfo="skip"
            ))

        # 2. Topolojik Güzergah / En Kısa Yol Hatları (NetworkX)
        if network_graph_paths:
            p_xs: List[Optional[float]] = []
            p_ys: List[Optional[float]] = []
            for path_pts in network_graph_paths:
                for idx in range(len(path_pts) - 1):
                    p_xs.extend([path_pts[idx][0], path_pts[idx + 1][0], None])
                    p_ys.extend([path_pts[idx][1], path_pts[idx + 1][1], None])

            if p_xs:
                fig.add_trace(go.Scattergl(
                    x=p_xs,
                    y=p_ys,
                    mode="lines",
                    name="07 — NetworkX Topolojik Güzergah Ağı",
                    line=dict(color="#A855F7", width=3.0, dash="dash"),
                    opacity=0.9,
                    visible="legendonly",
                    hoverinfo="skip"
                ))

        # 3. Tava Kot ve Ebat Etiketleri
        if annotations:
            anno_xs, anno_ys, anno_texts = [], [], []
            for a in annotations:
                anno_xs.append(a.x)
                anno_ys.append(a.y)
                anno_texts.append(f"<b>{a.text}</b><br>Ebat: {a.width_mm}x{a.height_mm} mm<br>Kot: +{a.elevation_mm} mm")

            fig.add_trace(go.Scattergl(
                x=anno_xs,
                y=anno_ys,
                mode="markers",
                name="08 — Tava Ebat ve Kot Etiketleri",
                marker=dict(size=5, color="#FACC15", symbol="cross"),
                hovertext=anno_texts,
                hoverinfo="text",
                visible="legendonly"
            ))

        # 4. Dağıtım Panoları (PandaPower Verileriyle Zenginleştirilmiş)
        if panels:
            panel_xs, panel_ys, panel_texts, panel_names = [], [], [], []
            seen_panels = set()
            for px, py, ptxt in panels:
                clean_name = ptxt.replace('\n', ' ').strip()
                if clean_name not in seen_panels:
                    seen_panels.add(clean_name)
                    panel_xs.append(px)
                    panel_ys.append(py)
                    panel_names.append(clean_name)

                    # Pandapower eşleştirmesi
                    sim_info = ""
                    if sim_res and hasattr(sim_res, 'buses'):
                        for b in sim_res.buses:
                            if any(k in b.name for k in clean_name.split() if len(k) > 2):
                                sim_info = (
                                    f"<br>Gerilim: {b.v_actual_v} V (ΔU: %{b.voltage_drop_pct})"
                                    f"<br>Kısa Devre (Ik''): {b.ikss_ka} kA"
                                    f"<br>Darbe Akımı (Ip): {b.ip_ka} kA"
                                    f"<br>Durum: {b.status}"
                                )
                                break

                    panel_texts.append(
                        f"<b>⚡ PANO: {clean_name}</b><br>"
                        f"Konum: X={px:.0f}, Y={py:.0f}"
                        f"{sim_info}"
                    )

            fig.add_trace(go.Scattergl(
                x=panel_xs,
                y=panel_ys,
                mode="markers+text",
                name="09 — Dağıtım Panoları (DB / LF / MCC)",
                marker=dict(size=14, color="#22C55E", symbol="square", line=dict(color="#FFFFFF", width=2)),
                text=[p.split('/')[0] if '/' in p else p[:8] for p in panel_names],
                textposition="top right",
                textfont=dict(color="#86EFAC", size=10),
                hovertext=panel_texts,
                hoverinfo="text",
                visible=True
            ))

        # 5. Çakışma, Koridor Sapması ve İhlal Belirteçleri
        if clash_points:
            clash_xs, clash_ys, clash_texts = [], [], []
            for cx, cy, c_type, c_desc in clash_points:
                clash_xs.append(cx)
                clash_ys.append(cy)
                clash_texts.append(f"<b>[{c_type}] ÇAKIŞMA/İHLAL</b><br>{c_desc}<br>Konum: ({cx:.0f}, {cy:.0f})")

            fig.add_trace(go.Scattergl(
                x=clash_xs,
                y=clash_ys,
                mode="markers",
                name="10 — Çakışma ve İhlal Noktaları",
                marker=dict(size=16, color="#EF4444", symbol="diamond", line=dict(color="#FEF08A", width=2)),
                hovertext=clash_texts,
                hoverinfo="text",
                visible=True
            ))

        # Layout Konfigürasyonu
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0B1120",
            plot_bgcolor="#070C18",
            margin=dict(l=20, r=20, t=40, b=20),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5,
                bgcolor="#0F172A",
                bordercolor="#334155",
                borderwidth=1,
                font=dict(color="#E2E8F0", size=11)
            ),
            xaxis=dict(
                title="İstasyon Boyuna Koordinatı (X / mm)",
                gridcolor="#1E293B",
                zerolinecolor="#334155",
                color="#94A3B8"
            ),
            yaxis=dict(
                title="İstasyon Enine Koordinatı (Y / mm)",
                scaleanchor="x",
                scaleratio=1,
                gridcolor="#1E293B",
                zerolinecolor="#334155",
                color="#94A3B8"
            ),
            hovermode="closest",
            dragmode="pan"
        )

        # Plotly grafik gövdesi
        plot_div = fig.to_html(
            full_html=False,
            include_plotlyjs="cdn",
            config={
                "scrollZoom": True,
                "displayModeBar": True,
                "displaylogo": False,
                "modeBarButtonsToAdd": ["drawline", "drawcircle", "eraseshape"]
            }
        )

        # KPI Değerlerini Formatla
        tray_lv_m = f"{audit_res.total_tray_lv_m:.1f} m" if audit_res else "—"
        tray_wc_m = f"{audit_res.total_tray_wc_m:.1f} m" if audit_res else "—"
        total_cbl_m = f"{(audit_res.total_cable_lighting_m + audit_res.total_cable_power_m):.1f} m" if audit_res else "—"
        fill_pct = f"%{audit_res.average_fill_ratio_pct:.1f}" if audit_res else "—"
        sc_ka = f"{sim_res.max_short_circuit_ka:.1f} kA" if sim_res else "—"
        v_drop = f"%{sim_res.max_voltage_drop_pct:.2f}" if sim_res else "—"
        score = f"%{audit_res.compliance_score_pct:.1f}" if audit_res else "—"
        verdict = audit_res.executive_verdict if audit_res else "SÜPERPOZİSYON İNCELEMESİ"

        # Tam HTML Şablonu
        html_content = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CloudeCAD — {self.station_name} [{self.floor_code}] Bütünleşik Süperpozisyon Görüntüleyici</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: #070C18;
            color: #F8FAFC;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            overflow-x: hidden;
            display: flex;
            flex-direction: column;
            height: 100vh;
        }}
        .header {{
            background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
            border-bottom: 1px solid #334155;
            padding: 12px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
            z-index: 10;
        }}
        .title-group h1 {{
            font-size: 1.15rem;
            font-weight: 700;
            color: #38BDF8;
            letter-spacing: -0.01em;
        }}
        .title-group p {{
            font-size: 0.8rem;
            color: #94A3B8;
            margin-top: 2px;
        }}
        .kpi-container {{
            display: flex;
            gap: 12px;
            align-items: center;
        }}
        .kpi-badge {{
            background: #1E293B;
            border: 1px solid #334155;
            padding: 6px 12px;
            border-radius: 6px;
            text-align: center;
            min-width: 80px;
        }}
        .kpi-label {{
            font-size: 0.65rem;
            color: #94A3B8;
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: 0.05em;
        }}
        .kpi-val {{
            font-size: 0.95rem;
            font-weight: 700;
            color: #F1F5F9;
            margin-top: 2px;
        }}
        .badge-cyan .kpi-val {{ color: #06B6D4; }}
        .badge-magenta .kpi-val {{ color: #E879F9; }}
        .badge-emerald .kpi-val {{ color: #22C55E; }}
        .badge-amber .kpi-val {{ color: #F59E0B; }}
        .badge-score {{
            background: rgba(34, 197, 94, 0.15);
            border-color: #22C55E;
        }}
        .badge-score .kpi-val {{ color: #4ADE80; font-size: 1.1rem; }}
        .viewer-container {{
            flex: 1;
            position: relative;
            width: 100%;
            height: calc(100vh - 75px);
        }}
        .floating-info {{
            position: absolute;
            bottom: 20px;
            left: 20px;
            background: rgba(15, 23, 42, 0.92);
            border: 1px solid #334155;
            padding: 10px 16px;
            border-radius: 8px;
            font-size: 0.75rem;
            color: #94A3B8;
            z-index: 5;
            backdrop-filter: blur(8px);
            pointer-events: none;
        }}
        .floating-info strong {{ color: #38BDF8; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title-group">
            <h1>🚇 CloudeCAD Bütünleşik Süperpozisyon Görüntüleyici</h1>
            <p>{self.station_name} ({self.station_key}) — Kat Planı: <strong>{self.floor_code}</strong> | {verdict}</p>
        </div>
        <div class="kpi-container">
            <div class="kpi-badge badge-cyan">
                <div class="kpi-label">AG Tava (LV)</div>
                <div class="kpi-val">{tray_lv_m}</div>
            </div>
            <div class="kpi-badge badge-magenta">
                <div class="kpi-label">ZA Tava (WC)</div>
                <div class="kpi-val">{tray_wc_m}</div>
            </div>
            <div class="kpi-badge">
                <div class="kpi-label">Toplam Kablo</div>
                <div class="kpi-val">{total_cbl_m}</div>
            </div>
            <div class="kpi-badge badge-emerald">
                <div class="kpi-label">Doluluk Oranı</div>
                <div class="kpi-val">{fill_pct}</div>
            </div>
            <div class="kpi-badge badge-amber">
                <div class="kpi-label">Kısa Devre (Ik'')</div>
                <div class="kpi-val">{sc_ka}</div>
            </div>
            <div class="kpi-badge">
                <div class="kpi-label">Max Gerilim Düş.</div>
                <div class="kpi-val">{v_drop}</div>
            </div>
            <div class="kpi-badge badge-score">
                <div class="kpi-label">Uyum Skoru</div>
                <div class="kpi-val">{score}</div>
            </div>
        </div>
    </div>
    <div class="viewer-container">
        {plot_div}
        <div class="floating-info">
            💡 <strong>İpucu:</strong> Fare tekerleğiyle yakınlaşın (Zoom), sol tık ile sürükleyin (Pan). Katmanları açıp kapatmak için üstteki lejant isimlerine tıklayın.
        </div>
    </div>
</body>
</html>
"""
        with open(output_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return output_html_path
