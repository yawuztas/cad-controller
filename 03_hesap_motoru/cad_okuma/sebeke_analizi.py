# -*- coding: utf-8 -*-
"""
Evrensel Ağ Yük Akışı, Kısa Devre (`pandapower`) ve İnteraktif HTML (`plotly`) Raporu
======================================================================================
Bina ana kolonundan büyük Metro OG-AG dağıtım şemalarına kadar tüm radyal
pano/trafo/kablo ağaçlarında:
  1. `pandapower` ile gerçek çok baralı AC yük akışı (`runpp`) ve
  2. `IEC 60909` üç faz kısa devre akımı (`ikss_ka`) hesabı,
  3. `plotly` ile tek dosyalık interaktif mühendislik özet grafikleri
üretir. Çizimde bulunmayan trafo/şebeke parametrelerini gizlemez, açıkça not düşer.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import pandapower as pp
import pandapower.shortcircuit as sc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pydantic import BaseModel, Field

_MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(_MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_MOTOR_ROOT))

from core.calculators.electrical_calc import (  # noqa: E402
    CABLE_IMPEDANCE_TABLE,
    parse_cable_spec,
)


class NetworkFeederInput(BaseModel):
    parent_bus: str
    target_bus: str
    power_kw: float = 0.0
    cos_phi: float = 0.90
    cable_spec: str = ""
    length_m: float = 0.0
    parallel_runs: int = 1
    ampacity_a: Optional[float] = None


class TransformerInput(BaseModel):
    name: str = "TR-01"
    sn_kva: float = 1000.0
    vn_hv_kv: float = 34.5
    vn_lv_kv: float = 0.4
    vk_percent: float = 6.0
    vkr_percent: float = 1.0
    vk_is_assumed: bool = True


class BusLoadFlowResult(BaseModel):
    bus_name: str
    vm_pu: float
    voltage_drop_pct: float
    ikss_ka: Optional[float] = None


class LineLoadFlowResult(BaseModel):
    from_bus: str
    to_bus: str
    cable_spec: str
    length_m: float
    current_ka: float
    loading_percent: Optional[float] = None
    pl_kw: float = 0.0


class NetworkAnalysisReport(BaseModel):
    converged: bool = False
    nominal_lv_kv: float = 0.4
    transformer_loading_pct: Optional[float] = None
    max_voltage_drop_pct: float = 0.0
    assumptions_notes: List[str] = Field(default_factory=list)
    skipped_branches: List[str] = Field(default_factory=list)
    buses: List[BusLoadFlowResult] = Field(default_factory=list)
    lines: List[LineLoadFlowResult] = Field(default_factory=list)


class TransformerRedundancyResult(BaseModel):
    transformer_count: int = 0
    ratings_kva: List[float] = Field(default_factory=list)
    total_installed_kva: float = 0.0
    n1_remaining_kva: float = 0.0
    demand_kw: Optional[float] = None
    demand_kva: Optional[float] = None
    n1_utilization_pct: Optional[float] = None
    status: str = "BELIRSIZ"  # UYGUN, KRITIK, BELIRSIZ
    note: str = ""


def check_n1_transformer_redundancy(
    transformer_kvas: Sequence[float],
    demand_kw: Optional[float] = None,
    *,
    cos_phi: float = 0.90,
) -> TransformerRedundancyResult:
    """
    Tek trafo devre dışıyken (N-1) kalan trafo kapasitesinin toplam istasyon/tesis
    talep yükünü %100 karşılayıp karşılamadığını deterministik olarak denetler.
    """
    kvas = sorted((float(k) for k in transformer_kvas if k and k > 0), reverse=True)
    if not kvas:
        return TransformerRedundancyResult(
            status="BELIRSIZ",
            note="Çizimlerde trafo anma gücü (kVA) bilgisi tespit edilemedi.",
        )

    tot_kva = sum(kvas)
    rem_kva = (tot_kva - kvas[0]) if len(kvas) >= 2 else 0.0

    if len(kvas) == 1:
        res = TransformerRedundancyResult(
            transformer_count=1,
            ratings_kva=kvas,
            total_installed_kva=tot_kva,
            n1_remaining_kva=0.0,
            status="KRITIK" if demand_kw else "UYARI",
            note=f"Yalnızca 1 adet {kvas[0]:.0f} kVA trafo bulundu; N-1 yedeklilik bulunmuyor.",
        )
        if demand_kw and demand_kw > 0:
            d_kva = demand_kw / max(min(cos_phi, 1.0), 0.5)
            res.demand_kw = round(demand_kw, 2)
            res.demand_kva = round(d_kva, 2)
        return res

    if demand_kw is None or demand_kw <= 0:
        return TransformerRedundancyResult(
            transformer_count=len(kvas),
            ratings_kva=kvas,
            total_installed_kva=tot_kva,
            n1_remaining_kva=round(rem_kva, 2),
            status="BELIRSIZ",
            note=(
                f"{len(kvas)} adet trafo ({' + '.join(f'{k:.0f}' for k in kvas)} kVA, N-1 kalan={rem_kva:.0f} kVA) "
                "tespit edildi; toplam talep gücü (P_talep) paftada okunamadığı için N-1 yüklenme oranı BELİRSİZ."
            ),
        )

    d_kva = demand_kw / max(min(cos_phi, 1.0), 0.5)
    util_pct = (d_kva / max(rem_kva, 1e-6)) * 100.0
    compliant = util_pct <= 100.0
    return TransformerRedundancyResult(
        transformer_count=len(kvas),
        ratings_kva=kvas,
        total_installed_kva=round(tot_kva, 2),
        n1_remaining_kva=round(rem_kva, 2),
        demand_kw=round(demand_kw, 2),
        demand_kva=round(d_kva, 2),
        n1_utilization_pct=round(util_pct, 2),
        status="UYGUN" if compliant else "KRITIK",
        note=(
            f"N-1 kalan kapasite={rem_kva:.0f} kVA, talep={d_kva:.1f} kVA ({demand_kw:.1f} kW, cosφ={cos_phi:.2f}), "
            f"yüklenme=%{util_pct:.1f}."
        ),
    )


def build_feeders_from_audit_rows(
    main_panel_name: str,
    panel_rows: Sequence[Any],
    vd_formulas: Sequence[Any] = (),
) -> Tuple[List[NetworkFeederInput], List[str]]:
    """
    `PanelAuditRow` ve `VoltageDropFormulaRow` verilerinden yalnız tüm fiziksel verileri
    (P > 0, L > 0, kablo/kesit > 0) eksiksiz okunmuş gerçek `pandapower` kolları üretir.
    Eksik verili kollar için ASLA sayı uydurmaz; `skipped` listesinde açıklar.
    """
    root_name = (main_panel_name or "ANA_PANO").strip()
    feeders: List[NetworkFeederInput] = []
    skipped: List[str] = []
    seen_targets: set[str] = set()

    for pr in panel_rows:
        pname = str(getattr(pr, "panel_name", "") or "").strip()
        if not pname or pname == root_name or pname in seen_targets:
            continue
        p_w = getattr(pr, "demand_power_w", None) or getattr(pr, "calc_dwelling_demand_w", None) or getattr(pr, "installed_power_w", None)
        length_m = getattr(pr, "feeder_length_m", None) or getattr(pr, "schematic_length_m", None)
        cable_spec = str(getattr(pr, "cable_spec", "") or "").strip()
        phase_mm2 = getattr(pr, "phase_mm2", None)
        if not cable_spec and phase_mm2 and phase_mm2 > 0:
            cable_spec = f"5x{phase_mm2:g} NYY"

        missing = []
        if not p_w or p_w <= 0:
            missing.append("P_talep")
        if not length_m or length_m <= 0:
            missing.append("L")
        if not cable_spec and (not phase_mm2 or phase_mm2 <= 0):
            missing.append("Kablo/Kesit")
        if missing:
            skipped.append(f"{pname}: eksik {', '.join(missing)}")
            continue

        cos_phi = float(getattr(pr, "cos_phi_project", None) or 0.90)
        amp_a = getattr(pr, "engine_iz_yaml_a", None) or getattr(pr, "project_iz_a", None)
        feeders.append(
            NetworkFeederInput(
                parent_bus=root_name,
                target_bus=pname,
                power_kw=round(float(p_w) / 1000.0, 3),
                cos_phi=min(0.99, max(0.5, cos_phi)),
                cable_spec=cable_spec,
                length_m=float(length_m),
                ampacity_a=float(amp_a) if amp_a and amp_a > 0 else None,
            )
        )
        seen_targets.add(pname)

    # Eğer pano kolon satırları yoksa doğrudan GD formül bloklarından doğrusal zincir kur
    if not feeders and vd_formulas:
        prev_bus = root_name
        for vf in vd_formulas:
            seg = str(getattr(vf, "segment_name", "") or "").strip()
            p_w = getattr(vf, "power_w", None)
            length_m = getattr(vf, "length_m", None)
            sec = getattr(vf, "section_mm2", None)
            cable_spec = str(getattr(vf, "cable_spec", "") or "").strip() or (f"5x{sec:g} NYY" if sec and sec > 0 else "")
            if not seg or not p_w or p_w <= 0 or not length_m or length_m <= 0 or not cable_spec:
                continue
            target_bus = seg if seg not in seen_targets and seg != prev_bus else f"{seg}_{len(feeders) + 1}"
            feeders.append(
                NetworkFeederInput(
                    parent_bus=prev_bus,
                    target_bus=target_bus,
                    power_kw=round(float(p_w) / 1000.0, 3),
                    cos_phi=0.90,
                    cable_spec=cable_spec,
                    length_m=float(length_m),
                )
            )
            seen_targets.add(target_bus)
            if getattr(vf, "is_three_phase", True):
                prev_bus = target_bus

    return feeders, skipped


def _cable_rx_per_km(cable_spec: str, length_m: float, parallel_runs: int = 1) -> tuple[float, float, float]:
    """`electrical_calc` empedans tablosundan birim R (ohm/km), X (ohm/km) ve yaklaşık max_i_ka döner."""
    spec = parse_cable_spec(cable_spec or "")
    sec = float(spec.phase_mm2 or 0.0)
    if sec <= 0:
        return (1.5, 0.085, 0.10)
    nearest = min(CABLE_IMPEDANCE_TABLE.keys(), key=lambda k: abs(k - sec))
    imp = CABLE_IMPEDANCE_TABLE[nearest]
    par = max(1, int(parallel_runs))
    r_km = imp["r_90c"] / par
    x_km = imp["x"] / par
    # Yaklaşık ampasite tahmini (detaylı derating hesap_denetleyici içinde yapılır)
    approx_i_a = max(15.0, min(750.0, sec * 4.5)) * par
    return (r_km, x_km, approx_i_a / 1000.0)


def analyze_radial_network_pandapower(
    feeders: Sequence[NetworkFeederInput],
    transformer: Optional[TransformerInput] = None,
    *,
    nominal_lv_kv: float = 0.4,
    grid_s_sc_mva: float = 500.0,
) -> NetworkAnalysisReport:
    """
    Verilen radyal pano-kablo ağacından `pandapower` şebekesi kurarak
    AC yük akışı (`runpp`) ve IEC 60909 üç faz kısa devre (`calc_sc`) hesaplar.
    """
    rep = NetworkAnalysisReport(nominal_lv_kv=nominal_lv_kv)
    if not feeders:
        rep.assumptions_notes.append("Şebeke dalı (fider) verisi olmadığı için yük akışı kurulmadı.")
        return rep

    net = pp.create_empty_network(sn_mva=1.0, f_hz=50.0)
    bus_map: Dict[str, int] = {}

    def _get_or_create_bus(name: str, vn_kv: float) -> int:
        key = name.strip() or "BAR"
        if key not in bus_map:
            bus_map[key] = int(pp.create_bus(net, vn_kv=vn_kv, name=key))
        return bus_map[key]

    # Kök AG barayı belirle (kimsenin hedefi olmayan ebeveyn bara)
    targets = {f.target_bus.strip() for f in feeders}
    roots = [f.parent_bus.strip() for f in feeders if f.parent_bus.strip() not in targets]
    root_name = roots[0] if roots else feeders[0].parent_bus.strip()

    if transformer is not None and transformer.sn_kva > 0:
        hv_bus = _get_or_create_bus(f"{transformer.name}_OG", transformer.vn_hv_kv)
        lv_bus = _get_or_create_bus(root_name, transformer.vn_lv_kv)
        pp.create_ext_grid(
            net,
            hv_bus,
            vm_pu=1.0,
            s_sc_max_mva=grid_s_sc_mva,
            rx_max=0.1,
            x0x_max=1.0,
            r0x0_max=0.1,
        )
        pp.create_transformer_from_parameters(
            net,
            hv_bus,
            lv_bus,
            sn_mva=transformer.sn_kva / 1000.0,
            vn_hv_kv=transformer.vn_hv_kv,
            vn_lv_kv=transformer.vn_lv_kv,
            vk_percent=transformer.vk_percent,
            vkr_percent=transformer.vkr_percent,
            pfe_kw=max(0.5, transformer.sn_kva * 0.0015),
            i0_percent=0.3,
            vector_group="Dyn11",
            vk0_percent=transformer.vk_percent,
            vkr0_percent=transformer.vkr_percent,
            mag0_percent=100.0,
            mag0_rx=0.0,
            si0_hv_partial=0.9,
            name=transformer.name,
        )
        lv_kv = transformer.vn_lv_kv
        if transformer.vk_is_assumed:
            rep.assumptions_notes.append(
                f"Trafo {transformer.name} kısa devre gerilimi (uk={transformer.vk_percent}%) tipik değerle modellenmiştir."
            )
    else:
        lv_kv = nominal_lv_kv
        lv_bus = _get_or_create_bus(root_name, lv_kv)
        pp.create_ext_grid(
            net,
            lv_bus,
            vm_pu=1.0,
            s_sc_max_mva=min(grid_s_sc_mva, 50.0),
            rx_max=0.25,
            x0x_max=1.0,
            r0x0_max=0.25,
        )
        rep.assumptions_notes.append("Trafo bilgisi çizimde yok; ana bara AG kaynak olarak modellenmiştir.")

    line_meta: List[tuple[int, NetworkFeederInput]] = []
    for f in feeders:
        b_from = _get_or_create_bus(f.parent_bus, lv_kv)
        b_to = _get_or_create_bus(f.target_bus, lv_kv)
        length_km = max(f.length_m / 1000.0, 0.001)
        r_km, x_km, est_i_ka = _cable_rx_per_km(f.cable_spec, f.length_m, f.parallel_runs)
        max_i_ka = (f.ampacity_a / 1000.0) if (f.ampacity_a and f.ampacity_a > 0) else est_i_ka
        l_idx = int(
            pp.create_line_from_parameters(
                net,
                from_bus=b_from,
                to_bus=b_to,
                length_km=length_km,
                r_ohm_per_km=r_km,
                x_ohm_per_km=x_km,
                c_nf_per_km=300.0,
                max_i_ka=max_i_ka,
                r0_ohm_per_km=r_km * 4.0,
                x0_ohm_per_km=x_km * 4.0,
                c0_nf_per_km=300.0,
                name=f"{f.parent_bus}->{f.target_bus}",
            )
        )
        line_meta.append((l_idx, f))
        if f.power_kw > 0:
            cosphi = min(0.999, max(0.5, f.cos_phi))
            q_mvar = (f.power_kw / 1000.0) * math.tan(math.acos(cosphi))
            pp.create_load(net, b_to, p_mw=f.power_kw / 1000.0, q_mvar=q_mvar, name=f.target_bus)

    try:
        pp.runpp(net, numba=False)
        rep.converged = bool(net.converged)
    except Exception as exc:
        rep.assumptions_notes.append(f"pandapower yük akışı yakınsamadı: {exc}")
        return rep

    sc_map: Dict[int, float] = {}
    try:
        sc.calc_sc(net, case="max", fault="3ph")
        for b_idx, row in net.res_bus_sc.iterrows():
            sc_map[int(b_idx)] = round(float(row["ikss_ka"]), 3)
    except Exception:
        pass

    if len(net.res_trafo) > 0:
        rep.transformer_loading_pct = round(float(net.res_trafo["loading_percent"].max()), 2)

    lv_root_vm = float(net.res_bus.loc[lv_bus, "vm_pu"])
    max_vd = 0.0
    for b_name, b_idx in bus_map.items():
        if b_name.endswith("_OG"):
            continue
        vm = float(net.res_bus.loc[b_idx, "vm_pu"])
        # Kök AG baraya göre bağıl düşüm (trafo sekonderinden itibaren)
        rel_vd_pct = max(0.0, ((lv_root_vm - vm) / max(lv_root_vm, 1e-6)) * 100.0)
        max_vd = max(max_vd, rel_vd_pct)
        rep.buses.append(
            BusLoadFlowResult(
                bus_name=b_name,
                vm_pu=round(vm, 5),
                voltage_drop_pct=round(rel_vd_pct, 3),
                ikss_ka=sc_map.get(b_idx),
            )
        )
    rep.max_voltage_drop_pct = round(max_vd, 3)

    for l_idx, f in line_meta:
        row = net.res_line.loc[l_idx]
        rep.lines.append(
            LineLoadFlowResult(
                from_bus=f.parent_bus,
                to_bus=f.target_bus,
                cable_spec=f.cable_spec,
                length_m=round(f.length_m, 2),
                current_ka=round(float(row["i_ka"]), 4),
                loading_percent=round(float(row["loading_percent"]), 2),
                pl_kw=round(float(row["pl_mw"]) * 1000.0, 3),
            )
        )
    return rep


def build_interactive_plotly_report(
    title: str,
    out_html: Union[str, Path],
    *,
    discipline_counts: Optional[Dict[str, int]] = None,
    bus_results: Optional[Sequence[BusLoadFlowResult]] = None,
    finding_severity_counts: Optional[Dict[str, int]] = None,
    include_plotlyjs: Union[bool, str] = "cdn",
) -> Path:
    """
    Proje metrajı, `pandapower` bara gerilim düşümü ve denetim bulgularını
    tek dosyalık interaktif `plotly` HTML panosu olarak kaydeder.
    """
    fig = make_subplots(
        rows=1,
        cols=3,
        subplot_titles=(
            "Disiplin / Ekipman Dağılımı",
            "Bara Bazlı Gerilim Düşümü (%e)",
            "Denetim Bulguları Şiddet Dağılımı",
        ),
    )

    if discipline_counts:
        fig.add_trace(
            go.Bar(
                x=list(discipline_counts.keys()),
                y=list(discipline_counts.values()),
                name="Adet",
                marker_color="#2563eb",
            ),
            row=1,
            col=1,
        )

    if bus_results:
        fig.add_trace(
            go.Bar(
                x=[b.bus_name for b in bus_results],
                y=[b.voltage_drop_pct for b in bus_results],
                name="%e Düşüm",
                marker_color="#059669",
            ),
            row=1,
            col=2,
        )

    if finding_severity_counts:
        color_map = {"DURDURUCU": "#991b1b", "KRITIK": "#dc2626", "UYARI": "#d97706", "BILGI": "#2563eb", "UYGUN": "#16a34a"}
        keys = list(finding_severity_counts.keys())
        fig.add_trace(
            go.Bar(
                x=keys,
                y=[finding_severity_counts[k] for k in keys],
                name="Bulgu",
                marker_color=[color_map.get(k, "#475569") for k in keys],
            ),
            row=1,
            col=3,
        )

    fig.update_layout(
        title_text=title,
        height=480,
        showlegend=False,
        template="plotly_white",
    )
    out_p = Path(out_html)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out_p), full_html=True, include_plotlyjs=include_plotlyjs)
    return out_p
