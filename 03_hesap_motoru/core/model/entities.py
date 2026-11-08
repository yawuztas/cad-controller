# -*- coding: utf-8 -*-
"""
Ortak Elektrik Bilgi Modeli — Çizim ve Fiziksel Varlıklar
=========================================================
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from shapely.geometry import Polygon, MultiLineString, LineString, Point


@dataclass
class TextToken:
    text: str
    pos: Tuple[float, float, float]
    height: float
    rotation: float
    layer: str
    color: int
    bbox: Polygon
    parent_block: str = ""
    is_attribute: bool = False
    attrib_tag: str = ""
    dxf_handle: str = ""
    source_handles: List[str] = field(default_factory=list)
    owner_block: str = "MODELSPACE"


@dataclass
class PlacedSymbol:
    block_name: str
    clean_family_name: str
    pos: Tuple[float, float, float]
    scale: Tuple[float, float, float]
    rotation: float
    layer: str
    color: int
    bbox: Polygon
    attribs: Dict[str, str] = field(default_factory=dict)
    parent_view: str = ""
    sub_zone: str = ""
    classification: str = "UNKNOWN"
    legend_description: Optional[str] = None
    power_w: float = 0.0
    power_source: str = "MISSING"          # EXPLICIT_BLOCK_NAME, EXPLICIT_ATTRIB, EXPLICIT_LEGEND, MISSING
    phases: int = 1
    circuit_tag: str = ""
    confidence_level: str = "DEFINITE"    # DEFINITE, HIGH, PROBABLE, UNCERTAIN
    confidence_score: float = 1.0          # 0.0 .. 1.0
    evidence_chain: List[str] = field(default_factory=list)
    triage_status: str = ""                # IGNORED_ARCHITECTURAL, UNCERTAIN_ELECTRICAL, UNCLASSIFIED veya boş
    dxf_handle: str = ""
    owner_block: str = "MODELSPACE"
    is_xref: bool = False


@dataclass
class LogicalCircuit:
    panel_tag: str
    circuit_no: str
    phase: str
    fixtures: List[PlacedSymbol] = field(default_factory=list)
    fixture_count: int = 0
    total_power_w: float = 0.0
    cable_cross_section: str = ""
    cable_type: str = ""
    cable_full_code: str = ""
    estimated_route_length_m: float = 0.0
    sub_zone: str = ""
    confidence_level: str = "DEFINITE"
    confidence_score: float = 1.0
    evidence_chain: List[str] = field(default_factory=list)
    cable_source: str = "MISSING"          # EXPLICIT_CALLOUT, EXPLICIT_TABLE, EXPLICIT_TEXT, MISSING
    power_source: str = "MISSING"          # EXPLICIT, PARTIAL_EXPLICIT, ESTIMATED_DEFAULT, MISSING
    length_source: str = "MISSING"         # EXPLICIT_TABLE, EXPLICIT_ROUTE, ESTIMATED_MST, MISSING
    assumptions_used: List[str] = field(default_factory=list)


@dataclass
class LinearRoute:
    layer: str
    color: int
    linetype: str
    total_length_m: float
    geometry: Any
    subsystem: str = "CABLE"
    entity_handles: List[str] = field(default_factory=list)
    owner_block: str = "MODELSPACE"


@dataclass
class ExtractedTable:
    name: str
    headers: List[str]
    rows: List[Dict[str, str]]
    bbox: Polygon
    source_space: str
    table_type: str = "SCHEDULE"


@dataclass
class CalloutGroup:
    lines: List[str]
    pos: Tuple[float, float]
    layer: str
    parent_block: str
    category: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubPlanZone:
    name: str
    bounds: Tuple[float, float, float, float]
    polygon: Polygon
    zone_type: str
    symbol_count: int = 0


@dataclass
class DrawingSceneGraph:
    filepath: str
    filename: str
    station_code: str
    sheet_title: str
    system_discipline: str
    floor_name: str
    elevation_kot: Optional[float]
    sub_plans: List[SubPlanZone]
    symbol_dictionary: Dict[str, str]
    symbols: List[PlacedSymbol]
    texts: List[TextToken]
    callouts: List[CalloutGroup]
    tables: List[ExtractedTable]
    physical_routes: List[LinearRoute]
    logical_circuits: List[LogicalCircuit]
    raw_stats: Dict[str, Any]
    station_name: str = ""
