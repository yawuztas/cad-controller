"""
CloudeCAD — CAD Görsel Denetim ve Çizim Render Motoru (CAD Visual Renderer)
===========================================================================
Topraklama analizi, bina sınır poligonu, iletken şebekesi, kazıklar ve klemensleri
yüksek çözünürlüklü PNG görseli olarak render eder (Word ve HTML raporlarına gömmek için).
"""

from pathlib import Path
from typing import Optional, Any
import matplotlib
matplotlib.use('Agg')  # Arka plan render'ı (GUI gerektirmez)
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.lines import Line2D


def render_cad_preview_png(
    drawing: Any,
    geo: Any,
    calc: Any,
    output_png: Path,
    dpi: int = 200
) -> Optional[Path]:
    """
    Çizim geometrisini ve analiz sonuçlarını ölçekli ve yüksek çözünürlüklü
    bir PNG dosyasına render eder.
    """
    output_png = Path(output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 7), dpi=dpi)
    fig.patch.set_facecolor('#ffffff')
    ax.set_facecolor('#f8fafc')

    # 1. Bina Sınır Poligonu
    if geo.building_polygon:
        try:
            x, y = geo.building_polygon.exterior.xy
            poly_patch = patches.Polygon(
                list(zip(x, y)),
                closed=True,
                facecolor='#e2e8f0',
                edgecolor='#64748b',
                linestyle='--',
                linewidth=1.8,
                alpha=0.6,
                zorder=1,
                label=f'Bina Temeli ({geo.building_area_m2:.0f} m²)'
            )
            ax.add_patch(poly_patch)
        except Exception:
            pass

    # 2. İletken Şeritleri (Yeşil Kalın Hatlar)
    target_segs = geo.active_foundation_floor.grounding_segments if (geo.active_foundation_floor and geo.active_foundation_floor.grounding_segments) else drawing.grounding_segments
    for seg in target_segs:
        ax.plot(
            [seg.start[0], seg.end[0]],
            [seg.start[1], seg.end[1]],
            color='#16a34a',
            linewidth=2.5,
            solid_capstyle='round',
            zorder=3
        )

    # 3. Bloklar (Kazıklar, Klemensler, Baralar)
    target_inserts = geo.active_foundation_floor.grounding_inserts if (geo.active_foundation_floor and geo.active_foundation_floor.grounding_inserts) else drawing.grounding_inserts
    
    # Bounding box sınırları
    if geo.building_polygon:
        minx, miny, maxx, maxy = geo.building_polygon.bounds
        margin = 4000.0
        bx_min, bx_max = minx - margin, maxx + margin
        by_min, by_max = miny - margin, maxy + margin
    else:
        bx_min, bx_max = -1e9, 1e9
        by_min, by_max = -1e9, 1e9

    rod_x, rod_y = [], []
    clamp_x, clamp_y = [], []
    bar_x, bar_y = [], []

    for ins in target_inserts:
        ix, iy = ins.position[0], ins.position[1]
        if not (bx_min <= ix <= bx_max and by_min <= iy <= by_max):
            continue
        bname = ins.block_name.lower()
        if any(k in bname for k in ['1tp', 'tp', 'rod', 'cubuk', 'kazik']):
            rod_x.append(ix)
            rod_y.append(iy)
        elif any(k in bname for k in ['1ekk', 'klemens']):
            clamp_x.append(ix)
            clamp_y.append(iy)
        elif any(k in bname for k in ['etb', 'bara']):
            bar_x.append(ix)
            bar_y.append(iy)

    if rod_x:
        ax.scatter(rod_x, rod_y, s=140, c='#2563eb', edgecolors='#1e3a8a', linewidths=2.0, marker='o', zorder=5, label=f'Topraklama Kazığı ({len(rod_x)} Adet)')
    if clamp_x:
        ax.scatter(clamp_x, clamp_y, s=90, c='#f59e0b', edgecolors='#b45309', linewidths=1.5, marker='s', zorder=4, label=f'İrtibat Klemensi ({len(clamp_x)} Adet)')
    if bar_x:
        ax.scatter(bar_x, bar_y, s=180, c='#8b5cf6', edgecolors='#5b21b6', linewidths=2.0, marker='D', zorder=5, label=f'Eşpotansiyel Bara ({len(bar_x)} Adet)')

    ax.set_aspect('equal', adjustable='box')
    ax.grid(True, linestyle=':', alpha=0.5, color='#cbd5e1')
    
    # Başlık ve bilgi kutusu
    status_str = "UYGUNDUR (GÜVENLİ)" if calc.overall_status() == "UYGUN" else "DÜZELTME GEREKLİ"
    ax.set_title(
        f"CloudeCAD — Temel Topraklama CAD Görsel Denetim Planı\n"
        f"Re = {calc.laurent_niemann.Re_combined_ohm:.2f} Ω (EMO) | Rg = {calc.ieee_sverak.Re_sverak_ohm:.2f} Ω (IEEE 80) — [{status_str}]",
        fontsize=12,
        fontweight='bold',
        color='#0f172a',
        pad=15
    )

    ax.legend(loc='upper right', framealpha=0.92, facecolor='#ffffff', edgecolor='#cbd5e1', fontsize=9)
    ax.set_xlabel("X Koordinatı (CAD Birimi)", fontsize=9, color='#64748b')
    ax.set_ylabel("Y Koordinatı (CAD Birimi)", fontsize=9, color='#64748b')

    fig.tight_layout()
    fig.savefig(output_png, bbox_inches='tight')
    plt.close(fig)

    return output_png


def render_metro_cad_preview_png(
    drawing: Any,
    metro_res: Any,
    output_png: Path,
    dpi: int = 180
) -> Optional[Path]:
    """
    Metro istasyonu paftasını ve topraklama/tava hatlarını PNG olarak render eder.
    """
    output_png = Path(output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 7), dpi=dpi)
    fig.patch.set_facecolor('#ffffff')
    ax.set_facecolor('#f8fafc')

    # 1. Yapısal Duvar ve Kolon Hatları (Açık Gri Arka Plan)
    struct_segs = getattr(drawing, 'structural_segments', [])
    # Performans için gerekirse subsample
    step = 1 if len(struct_segs) < 3000 else (len(struct_segs) // 2000)
    for seg in struct_segs[::step]:
        ax.plot(
            [seg.start[0], seg.end[0]],
            [seg.start[1], seg.end[1]],
            color='#cbd5e1',
            linewidth=0.8,
            alpha=0.6,
            zorder=1
        )

    # 2. Topraklama ve Kablo Tava Hatları (Yeşil Kalın Hatlar)
    g_segs = getattr(drawing, 'grounding_segments', [])
    for seg in g_segs:
        ax.plot(
            [seg.start[0], seg.end[0]],
            [seg.start[1], seg.end[1]],
            color='#16a34a',
            linewidth=2.0,
            solid_capstyle='round',
            zorder=3
        )

    # 3. Baralar
    bar_x, bar_y = [], []
    for b in getattr(metro_res, 'busbars', []):
        if hasattr(b, 'position') and (b.position[0] != 0 or b.position[1] != 0):
            bar_x.append(b.position[0])
            bar_y.append(b.position[1])

    if bar_x:
        ax.scatter(bar_x, bar_y, s=180, c='#8b5cf6', edgecolors='#5b21b6', linewidths=2.0, marker='D', zorder=5, label=f'Topraklama Barası ({len(bar_x)} Adet)')

    # 4. Doğru Topraklanmış Ekipmanlar (Yeşil Onay Noktaları)
    gnd_x, gnd_y = [], []
    for ge in getattr(metro_res, 'grounded_elements', []):
        pos = getattr(ge, 'position', (0.0, 0.0))
        if pos and (pos[0] != 0 or pos[1] != 0):
            gnd_x.append(pos[0])
            gnd_y.append(pos[1])
    if gnd_x:
        ax.scatter(gnd_x, gnd_y, s=55, c='#dcfce7', edgecolors='#15803d', linewidths=1.3, marker='o', zorder=4)

    # 5. Eksik Klemens (kkk) T-Ek Noktaları (Turuncu Uyarı Üçgenleri)
    mc_pts = getattr(metro_res, 'missing_clamp_points', [])
    if mc_pts:
        mc_x = [p[0] for p in mc_pts]
        mc_y = [p[1] for p in mc_pts]
        ax.scatter(mc_x, mc_y, s=65, c='#fb923c', edgecolors='#c2410c', linewidths=1.2, marker='^', alpha=0.85, zorder=5)

    # 6. Unutulmuş / Topraklanmamış Ekipman ve Kapaklar (Kırmızı Hata İşaretleri + Numaralar)
    def_x, def_y = [], []
    defects = getattr(metro_res, 'spatial_defects', [])
    for idx, df in enumerate(defects, 1):
        pos = getattr(df, 'position', (0.0, 0.0))
        if pos and (pos[0] != 0 or pos[1] != 0):
            def_x.append(pos[0])
            def_y.append(pos[1])
            if idx <= 25:
                ax.annotate(
                    f"!{idx}",
                    (pos[0], pos[1]),
                    textcoords="offset points",
                    xytext=(5, 5),
                    fontsize=7.5,
                    fontweight='bold',
                    color='#991b1b',
                    bbox=dict(boxstyle='round,pad=0.18', facecolor='#fef2f2', edgecolor='#dc2626', lw=0.8, alpha=0.92),
                    zorder=7
                )
    if def_x:
        ax.scatter(def_x, def_y, s=150, c='#ef4444', edgecolors='#7f1d1d', linewidths=1.8, marker='X', zorder=6)

    ax.set_aspect('equal', adjustable='box')
    ax.grid(True, linestyle=':', alpha=0.5, color='#cbd5e1')

    pname = getattr(metro_res, 'project_name', 'Metro İstasyonu')
    flevel = getattr(metro_res, 'floor_level', 'İstasyon Katı')
    role = getattr(metro_res, 'drawing_role', 'Dağıtım')
    verdict_badge = f"✗ {len(defects)} EKSİK TESPİT EDİLDİ" if defects else "✓ UYGUNDUR"
    title_color = '#991b1b' if defects else '#0f172a'

    ax.set_title(
        f"CloudeCAD — Raylı Sistem & Metro İstasyonu Görsel Denetim Haritası\n"
        f"{pname} | {flevel} ({role}) — [{verdict_badge}]",
        fontsize=10.5,
        fontweight='bold',
        color=title_color,
        pad=12
    )

    ax.set_xlabel("X Koordinatı (CAD Birimi)", fontsize=8.5, color='#64748b')
    ax.set_ylabel("Y Koordinatı (CAD Birimi)", fontsize=8.5, color='#64748b')

    # Legend
    legend_elements = [
        Line2D([0], [0], color='#16a34a', lw=2, label=f'Topraklama & Tava Güzergahı ({metro_res.total_conductor_m:.1f} m)'),
        Line2D([0], [0], color='#cbd5e1', lw=1, label='Mimari / Taşıyıcı Duvar & Kolonlar')
    ]
    if bar_x:
        legend_elements.append(Line2D([0], [0], marker='D', color='w', markerfacecolor='#8b5cf6', markeredgecolor='#5b21b6', markersize=8, label=f'Bakır Bara 40x5mm ({len(bar_x)} Adet)'))
    if gnd_x:
        legend_elements.append(Line2D([0], [0], marker='o', color='w', markerfacecolor='#dcfce7', markeredgecolor='#15803d', markersize=7, label=f'Doğru Topraklanmış Ekipman ({len(gnd_x)} Adet)'))
    if def_x:
        legend_elements.append(Line2D([0], [0], marker='X', color='w', markerfacecolor='#ef4444', markeredgecolor='#7f1d1d', markersize=9, label=f'Unutulmuş / Topraklanmamış ({len(def_x)} Adet)'))
    if mc_pts:
        legend_elements.append(Line2D([0], [0], marker='^', color='w', markerfacecolor='#fb923c', markeredgecolor='#c2410c', markersize=7, label=f'Klemens (kkk) Sembolü Eksik T-Ek ({len(mc_pts)} Adet)'))

    ax.legend(handles=legend_elements, loc='upper right', framealpha=0.93, facecolor='#ffffff', edgecolor='#cbd5e1', fontsize=8.0)

    fig.tight_layout()
    fig.savefig(output_png, bbox_inches='tight')
    plt.close(fig)

    return output_png


