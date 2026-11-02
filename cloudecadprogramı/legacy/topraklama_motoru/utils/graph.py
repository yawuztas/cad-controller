"""
CloudeCAD — NetworkX Topoloji Yardımcıları
============================================
Topraklama ağını bir devre grafiği olarak modeller.

Düğümler: Hat kesişimleri, kazıklar, buat noktaları
Kenarlar: İletken segmentler (ağırlık = uzunluk)

Kapalı döngüler (gözler) NetworkX'in döngü tabanı algoritması
ile tespit edilir.
"""

import logging
import math
from typing import Optional

import networkx as nx

logger = logging.getLogger(__name__)

# Koordinat hassasiyeti — node karşılaştırma için yuvarlama
_NODE_ROUND = 1   # 1 mm hassasiyet (snap sonrası yeterli)


def _node_key(x: float, y: float) -> tuple[int, int]:
    """Koordinatı tamsayı tuple'a dönüştür (graph node key)."""
    return (round(x, _NODE_ROUND), round(y, _NODE_ROUND))


def build_graph(segments: list) -> nx.Graph:
    """
    Segment listesinden NetworkX undirected graph oluşturur.

    Her segmentin başlangıç ve bitiş noktası düğüm olur.
    Kenar ağırlığı segmentin uzunluğudur (mm).

    Döner:
        nx.Graph — düğümler (x, y) tuple, kenarlar {weight: mm, ...}
    """
    G = nx.Graph()

    for seg in segments:
        u = _node_key(*seg.start)
        v = _node_key(*seg.end)

        if u == v:
            continue   # Dejenere kenar atla

        G.add_node(u, x=seg.start[0], y=seg.start[1])
        G.add_node(v, x=seg.end[0],   y=seg.end[1])
        G.add_edge(u, v,
                   weight=seg.length,
                   layer=seg.layer,
                   entity_type=seg.entity_type,
                   handle=seg.handle)

    logger.info(
        f"Graf oluşturuldu: {G.number_of_nodes()} düğüm, "
        f"{G.number_of_edges()} kenar"
    )
    return G


def find_cycles(G: nx.Graph) -> list[list]:
    """
    Grafın minimum döngü tabanını (cycle basis) bul.

    Her döngü = bir topraklama ağı gözü.
    Döner: Düğüm listelerinin listesi (her döngü = kapalı yol)
    """
    if G.number_of_edges() == 0:
        return []
    try:
        cycles = nx.cycle_basis(G)
        logger.info(f"{len(cycles)} kapalı döngü (göz) tespit edildi.")
        return cycles
    except Exception as e:
        logger.warning(f"Döngü tespiti başarısız: {e}")
        return []


def get_connected_components(G: nx.Graph, warn_disconnected: bool = True) -> list[nx.Graph]:
    """
    Grafın bağlı bileşenlerini döner.
    Kopuk topraklama ağlarını tespit etmek için kullanılır.
    """
    components = [G.subgraph(c).copy() for c in nx.connected_components(G)]
    if len(components) > 1 and warn_disconnected:
        logger.warning(
            f"⚠️  {len(components)} ayrı topraklama ağı tespit edildi. "
            f"Ağ kesintisiz değil!"
        )
    return components


def total_length_m(G: nx.Graph) -> float:
    """Grafın toplam kenar uzunluğunu metre cinsinden döner (mm → m)."""
    total_mm = sum(d.get("weight", 0.0) for _, _, d in G.edges(data=True))
    return total_mm / 1000.0


def find_free_ends(G: nx.Graph) -> list[tuple]:
    """
    Serbest uçları (degree=1 düğümler) döner.
    Bunlar topolojik olarak "asılı" hatlardır — tasarım hatası olabilir.
    """
    free = [n for n, deg in G.degree() if deg == 1]
    if free:
        logger.debug(f"{len(free)} serbest uç (degree=1) bulundu.")
    return free


def find_isolated_nodes(G: nx.Graph) -> list[tuple]:
    """Bağlantısız (degree=0) düğümleri döner."""
    return [n for n, deg in G.degree() if deg == 0]


def cycle_bounding_box(
    G: nx.Graph, cycle: list[tuple]
) -> tuple[float, float, float, float]:
    """
    Bir döngünün minimum bounding box'ını hesaplar.
    Döner: (min_x, min_y, max_x, max_y) — mm cinsinden
    """
    xs = [G.nodes[n]["x"] for n in cycle if n in G.nodes]
    ys = [G.nodes[n]["y"] for n in cycle if n in G.nodes]
    if not xs:
        return (0, 0, 0, 0)
    return (min(xs), min(ys), max(xs), max(ys))


def cycle_dimensions_m(
    G: nx.Graph, cycle: list[tuple]
) -> tuple[float, float]:
    """
    Bir döngünün genişlik ve yüksekliğini metre cinsinden döner.
    Döner: (width_m, height_m)
    """
    bb = cycle_bounding_box(G, cycle)
    width_mm  = bb[2] - bb[0]
    height_mm = bb[3] - bb[1]
    return (width_mm / 1000.0, height_mm / 1000.0)
