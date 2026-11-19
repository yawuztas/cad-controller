# -*- coding: utf-8 -*-
"""
Evrensel CAD Veri Kalıbı Şeması (`CanonicalProjectModel` & `RawCADSnapshot`)
=============================================================================
Hiçbir proje/firma/istasyon hardcode'u olmadan, tüm bina ve metro elektrik
CAD dosyalarını tek ve doğrulanabilir bir veri kalıbına (Pydantic v2) döker.
"""

from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field


class BBox2D(BaseModel):
    minx: float
    miny: float
    maxx: float
    maxy: float

    @property
    def width(self) -> float:
        return max(0.0, self.maxx - self.minx)

    @property
    def height(self) -> float:
        return max(0.0, self.maxy - self.miny)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.minx + self.maxx) * 0.5, (self.miny + self.maxy) * 0.5)

    def contains_xy(self, x: float, y: float, tol: float = 0.0) -> bool:
        return (self.minx - tol) <= x <= (self.maxx + tol) and (self.miny - tol) <= y <= (self.maxy + tol)


# ==============================================================================
# KATMAN A: KAYIPSIZ HAM ÇIKARIM MODELLERİ (DXF BİRLERİ / DU CİNSİNDEN)
# ==============================================================================

class LayerInfo(BaseModel):
    name: str
    color: int = 7
    linetype: str = "CONTINUOUS"
    lineweight: int = -3
    is_locked: bool = False
    is_on: bool = True
    is_frozen: bool = False
    plot: bool = True


class RawText(BaseModel):
    handle: str = ""
    dxftype: str  # TEXT, MTEXT, ATTRIB
    text: str
    lines: List[str] = Field(default_factory=list)  # Çok satırlı yapı korunur
    raw_text: str = ""
    x: float
    y: float
    z: float = 0.0
    height: float = 0.0
    rotation: float = 0.0
    layer: str = "0"
    color: int = 256
    space: str = "MODEL"
    owner_block: str = "MODELSPACE"
    parent_chain: str = ""
    is_attribute: bool = False
    attrib_tag: str = ""
    from_align_point: bool = False
    bbox: BBox2D


class RawInsert(BaseModel):
    handle: str = ""
    block_name: str               # DXF'deki ham adı (dinamikte *U123 olabilir)
    effective_name: str           # AcDbBlockRepBTag varsa gerçek kök blok adı
    is_dynamic: bool = False
    is_xref: bool = False
    x: float
    y: float
    z: float = 0.0
    xscale: float = 1.0
    yscale: float = 1.0
    rotation: float = 0.0
    layer: str = "0"
    color: int = 256
    space: str = "MODEL"
    owner_block: str = "MODELSPACE"
    parent_chain: str = ""
    attribs: Dict[str, str] = Field(default_factory=dict)
    internal_layers: List[str] = Field(default_factory=list)
    bbox: BBox2D


class RawPath(BaseModel):
    handle: str = ""
    dxftype: str  # LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE, ELLIPSE, SPLINE, HATCH_BOUNDARY, SOLID
    points: List[Tuple[float, float]]
    closed: bool = False
    is_circle: bool = False
    radius_du: Optional[float] = None
    arc_sweep_deg: Optional[float] = None
    length_du: float = 0.0
    layer: str = "0"
    color: int = 256
    linetype: str = "BYLAYER"
    space: str = "MODEL"
    owner_block: str = "MODELSPACE"
    parent_chain: str = ""
    bbox: BBox2D


class RawAcadTable(BaseModel):
    handle: str = ""
    layer: str = "0"
    space: str = "MODEL"
    x: float = 0.0
    y: float = 0.0
    rows: List[List[str]] = Field(default_factory=list)
    bbox: Optional[BBox2D] = None


class RawDimension(BaseModel):
    handle: str = ""
    dimtype: int = 0
    text_override: str = ""
    measurement_du: Optional[float] = None
    x: float
    y: float
    layer: str = "0"
    space: str = "MODEL"


class RawLeader(BaseModel):
    handle: str = ""
    dxftype: str  # LEADER, MLEADER
    vertices: List[Tuple[float, float]] = Field(default_factory=list)
    text: str = ""
    layer: str = "0"
    space: str = "MODEL"


class RawOleObject(BaseModel):
    handle: str = ""
    dxftype: str  # OLE2FRAME, IMAGE, WIPEOUT
    layer: str = "0"
    space: str = "MODEL"
    bbox: BBox2D
    note: str = ""
    decode_status: Literal["OK", "PARTIAL", "UNREADABLE"] = "UNREADABLE"
    decoded_title: str = ""
    decoded_rows: List[List[str]] = Field(default_factory=list)
    decoded_text_count: int = 0


class RawCADSnapshot(BaseModel):
    """Tek geçişte dosyadan kayıpsız çıkarılan ham CAD envanteri."""
    filepath: str
    filename: str
    dxf_path: str
    dxf_version: str = ""
    insunits_header: int = 0
    extmin: Optional[Tuple[float, float]] = None
    extmax: Optional[Tuple[float, float]] = None
    layouts: List[str] = Field(default_factory=list)
    layers: List[LayerInfo] = Field(default_factory=list)
    texts: List[RawText] = Field(default_factory=list)
    inserts: List[RawInsert] = Field(default_factory=list)
    paths: List[RawPath] = Field(default_factory=list)
    acad_tables: List[RawAcadTable] = Field(default_factory=list)
    dimensions: List[RawDimension] = Field(default_factory=list)
    leaders: List[RawLeader] = Field(default_factory=list)
    ole_objects: List[RawOleObject] = Field(default_factory=list)
    raw_entity_counts: Dict[str, int] = Field(default_factory=dict)
    unhandled_entity_counts: Dict[str, int] = Field(default_factory=dict)
    extraction_warnings: List[str] = Field(default_factory=list)


# ==============================================================================
# KATMAN B: EVRENSEL YAPISAL KALIP (METRE NORMALİZELİ CANONICAL MODEL)
# ==============================================================================

class UnitCalibration(BaseModel):
    unit_name: Literal["mm", "cm", "m", "unknown"]
    du_to_mm: float
    du_to_m: float
    confidence: float = Field(ge=0.0, le=1.0)
    source: str
    evidence: Dict[str, Any] = Field(default_factory=dict)


class SheetFrame(BaseModel):
    frame_id: str
    space: str = "MODEL"
    bbox_du: BBox2D
    bbox_m: BBox2D
    role: Literal[
        "KAT_PLANI",
        "KOLON_SEMASI",
        "TEK_HAT",
        "GERILIM_DUSUMU",
        "YUKLEME_CETVELI",
        "TOPRAKLAMA",
        "LEJANT",
        "DETAY",
        "DIGER",
    ] = "DIGER"
    role_confidence: float = 0.0
    role_evidence: List[str] = Field(default_factory=list)
    title: str = ""
    sheet_code: str = ""
    border_handle: str = ""
    text_count: int = 0
    insert_count: int = 0
    path_count: int = 0
    ole_count: int = 0


class LegendEntry(BaseModel):
    symbol_key: str
    block_names: List[str] = Field(default_factory=list)
    description: str
    sheet_id: str = ""
    source_handles: List[str] = Field(default_factory=list)


class NormalizedTable(BaseModel):
    table_id: str
    sheet_id: str = ""
    source_kind: Literal["ACAD_TABLE", "TEXT_GRID", "BORDERED_GRID", "OLE2_DECODED"]
    title: str = ""
    headers: List[str] = Field(default_factory=list)
    rows: List[Dict[str, str]] = Field(default_factory=list)
    raw_matrix: List[List[str]] = Field(default_factory=list)
    bbox_du: Optional[BBox2D] = None
    confidence: float = 1.0
    source_handles: List[str] = Field(default_factory=list)


class FormulaBlock(BaseModel):
    formula_id: str
    sheet_id: str = ""
    formula_kind: Literal["VOLTAGE_DROP", "FEEDER_SEGMENT", "GROUNDING", "LOAD_BALANCE", "GENERIC"] = "GENERIC"
    label: str = ""
    numerator_texts: List[str] = Field(default_factory=list)
    denominator_texts: List[str] = Field(default_factory=list)
    coefficient_texts: List[str] = Field(default_factory=list)
    result_texts: List[str] = Field(default_factory=list)
    parsed_result_value: Optional[float] = None
    parse_status: Literal["OK", "PARTIAL", "UNREADABLE"] = "PARTIAL"
    bbox_du: BBox2D
    source_handles: List[str] = Field(default_factory=list)


class SchematicNode(BaseModel):
    node_id: str
    node_type: Literal["UTILITY_INCOMER", "PANEL", "BREAKER", "LOAD_MOTOR", "JUNCTION", "UNKNOWN"] = "UNKNOWN"
    label: str = ""
    pos_m: Tuple[float, float]
    texts: List[str] = Field(default_factory=list)
    handles: List[str] = Field(default_factory=list)


class SchematicEdge(BaseModel):
    edge_id: str
    source_node: str
    target_node: str
    path_handles: List[str] = Field(default_factory=list)
    texts_along_edge: List[str] = Field(default_factory=list)
    length_m: float = 0.0


class SchematicGraph(BaseModel):
    graph_id: str
    sheet_id: str = ""
    nodes: List[SchematicNode] = Field(default_factory=list)
    edges: List[SchematicEdge] = Field(default_factory=list)
    connected_components: int = 0


class GroundingLoop(BaseModel):
    loop_id: str
    sheet_id: str = ""
    outer_perimeter_m: float = 0.0
    area_m2: float = 0.0
    equivalent_diameter_m: float = 0.0
    inner_conductors_m: float = 0.0
    ring_plus_inner_m: float = 0.0
    ring_conductor_spec: str = ""
    spur_count: int = 0
    spur_total_m: float = 0.0
    spur_conductor_spec: str = ""
    rod_block_count: Optional[int] = None
    total_conductor_m: float = 0.0
    layer_names: List[str] = Field(default_factory=list)
    source_handles: List[str] = Field(default_factory=list)


class EmbeddedAlert(BaseModel):
    alert_type: Literal["OLE2FRAME_EMBEDDED", "EXTERNAL_XREF", "UNREADABLE_TEXT", "LARGE_UNCLASSIFIED_CLUSTER"]
    sheet_id: str = ""
    space: str = "MODEL"
    layer: str = "0"
    handle: str = ""
    bbox_du: Optional[BBox2D] = None
    message: str


class CanonicalProjectModel(BaseModel):
    """Tüm CAD okuma aşamalarının tek çıktısı — JSON olarak serileştirilebilir."""
    schema_version: str = "1.0.0"
    filename: str
    filepath: str
    unit: UnitCalibration
    sheets: List[SheetFrame] = Field(default_factory=list)
    legend: Dict[str, LegendEntry] = Field(default_factory=dict)
    tables: List[NormalizedTable] = Field(default_factory=list)
    formula_blocks: List[FormulaBlock] = Field(default_factory=list)
    schematics: List[SchematicGraph] = Field(default_factory=list)
    grounding_loops: List[GroundingLoop] = Field(default_factory=list)
    embedded_alerts: List[EmbeddedAlert] = Field(default_factory=list)
    extraction_metrics: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# KATMAN C — MÜHENDİS DOĞRULAMA ENVANTERİ & METRAJ ÖZETİ (BOQ)
# ---------------------------------------------------------------------------

class PanelInventoryItem(BaseModel):
    """Şemalardan ve planlardan dinamik tespit edilen pano / dağıtım tablosu."""
    panel_name: str
    role: Literal["ANA_PANO", "TALI_PANO", "ORTAK_PANO", "SAYAC_PANOSU", "BELIRSIZ"] = "BELIRSIZ"
    parent_panel: Optional[str] = None
    sheet_ids: List[str] = Field(default_factory=list)
    breaker_rating: Optional[str] = None
    rcd_rating: Optional[str] = None
    feeder_cable: Optional[str] = None
    installed_power_w: Optional[float] = None
    demand_power_w: Optional[float] = None
    source_handles: List[str] = Field(default_factory=list)


class SwitchgearBomItem(BaseModel):
    """Kesici, KAKR, kompakt şalter, sayaç ve koruma ekipmanı metraj kalemi."""
    category: Literal["KAKR", "SIGORTA_SALTER", "SAYAC", "PARAFUDR_AOS", "DIGER_SALT"]
    spec: str
    count: int
    sheet_breakdown: Dict[str, int] = Field(default_factory=dict)
    source_handles: List[str] = Field(default_factory=list)


class CableBomItem(BaseModel):
    """Kablo etiketi, kesit ve (varsa) yazılı metraj özeti."""
    spec: str
    occurrences: int
    explicit_length_m: Optional[float] = None
    sheet_breakdown: Dict[str, int] = Field(default_factory=dict)
    source_handles: List[str] = Field(default_factory=list)


class SymbolBomItem(BaseModel):
    """Kat planları ve bloklardan çıkarılan ekipman/armatür/priz metrajı."""
    category: str
    block_name: str
    description: str
    description_source: Literal["LEJANT", "KAT_ETIKETI", "KATMAN_ADI", "BLOK_ADI", "ATTRIB", "BELIRSIZ"] = "BELIRSIZ"
    discipline: Literal["KUVVETLI_AKIM", "ZAYIF_AKIM", "TOPRAKLAMA", "SINYAL", "BELIRSIZ"] = "KUVVETLI_AKIM"
    layer_names: List[str] = Field(default_factory=list)
    total_count: int
    sheet_breakdown: Dict[str, int] = Field(default_factory=dict)


class WireLayerBomItem(BaseModel):
    """Katman bazlı yatay kablo / iletken metraj kalemi."""
    layer: str
    description: str = ""
    segment_count: int = 0
    total_length_m: float = 0.0


class LoadScheduleBreakerItem(BaseModel):
    """Yükleme cetveli (OLE2 / ACAD_TABLE / TEXT_GRID) içinden okunan linye kesici ve kablo kalemi."""
    panel_name: str
    breaker_spec: str
    cable_spec: str = ""
    count: int = 0
    total_power_kw: float = 0.0
    source_kind: str = ""
    source_handle: str = ""


class OutsideClusterSummary(BaseModel):
    """Pafta çerçevesi dışında kalan antetsiz alanların mekânsal küme özeti."""
    cluster_id: str
    title: str
    source_kind: str = "CERCEVESIZ_PLAN"
    title_position: str = "ALTINDA"
    floor_or_scope: str = ""
    discipline: str = "BELIRSIZ"
    text_count: int = 0
    electrical_symbol_count: int = 0
    non_electrical_count: int = 0
    uncertain_block_count: int = 0
    arch_path_count: int = 0
    elec_wire_count: int = 0
    elec_wire_length_m: float = 0.0
    symbols: List[SymbolBomItem] = Field(default_factory=list)
    wires_by_layer: List[WireLayerBomItem] = Field(default_factory=list)


class ProjectViewSummary(BaseModel):
    """Kat x Disiplin ekseninde mimari altlıktan arındırılmış tekil görünüm özeti."""
    view_id: str
    source_kind: Literal["PAFTA", "CERCEVESIZ_PLAN", "CERCEVESIZ_KUME"]
    floor_or_scope: str
    discipline: Literal[
        "KUVVETLI_AKIM",
        "ZAYIF_AKIM",
        "TOPRAKLAMA",
        "KARMA_ELEKTRIK",
        "SALT_MIMARI_ALTLIK",
        "SEMA_HESAP",
        "LEJANT_DETAY",
        "BELIRSIZ",
    ]
    title: str
    title_position: Literal["ICINDE", "ALTINDA", "YOK"] = "ICINDE"
    arch_block_count: int = 0
    arch_path_count: int = 0
    elec_symbol_count: int = 0
    elec_wire_count: int = 0
    elec_wire_length_m: float = 0.0
    uncertain_block_count: int = 0
    minx_du: Optional[float] = None
    miny_du: Optional[float] = None
    symbols: List[SymbolBomItem] = Field(default_factory=list)
    wires_by_layer: List[WireLayerBomItem] = Field(default_factory=list)


class OleTableSummary(BaseModel):
    """OLE2FRAME gömülü nesneden çözülen tablo özeti."""
    handle: str
    sheet_id: str
    title: str
    row_count: int
    cell_count: int
    preview_rows: List[List[str]] = Field(default_factory=list)


class ProjectInventory(BaseModel):
    """Mühendisin projeyle 30 saniyede eşleştirip doğrulayabileceği metraj özeti."""
    filename: str
    unit_name: str
    sheet_count: int
    views: List[ProjectViewSummary] = Field(default_factory=list)
    architectural_summary: Dict[str, int] = Field(default_factory=dict)
    panels: List[PanelInventoryItem] = Field(default_factory=list)
    switchgear_bom: List[SwitchgearBomItem] = Field(default_factory=list)
    load_schedule_breakers: List[LoadScheduleBreakerItem] = Field(default_factory=list)
    cable_bom: List[CableBomItem] = Field(default_factory=list)
    grounding_loops: List[GroundingLoop] = Field(default_factory=list)
    symbol_bom: List[SymbolBomItem] = Field(default_factory=list)
    schematic_symbol_bom: List[SymbolBomItem] = Field(default_factory=list)
    outside_clusters: List[OutsideClusterSummary] = Field(default_factory=list)
    ole_decoded_tables: List[OleTableSummary] = Field(default_factory=list)
    non_electrical_block_count: int = 0
    uncertain_block_count: int = 0
    outside_text_count: int = 0
    outside_electrical_insert_count: int = 0
    alerts_summary: List[str] = Field(default_factory=list)
