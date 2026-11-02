# -*- coding: utf-8 -*-
"""
Geriye Dönük Uyumluluk Sarmalayıcısı (UniversalCADReader)
========================================================
Tüm CAD okuma mantığı artık 'core' modüler paketine taşınmıştır.
Bu modül eski referansların sorunsuz çalışmasını sağlar.
"""

from __future__ import annotations
try:
    from core.cad.reader import UniversalCADReader, BlockHierarchyFlattener
    from core.cad.geometry import (
        clean_turkish_text,
        strip_revit_view_suffix,
        TextReconstructionEngine,
        GeometricTableExtractor,
    )
    from core.cad.classifier import MultiEvidenceClassifier
    from core.cad.frame_detector import SpatialZoneMapper
    from core.topology.circuit_resolver import LogicalCircuitResolver as HybridCircuitTopologyEngine
    from core.topology.route_builder import PhysicalRouteBuilder
    from core.model.entities import (
        TextToken,
        PlacedSymbol,
        LogicalCircuit,
        LinearRoute,
        ExtractedTable,
        CalloutGroup,
        SubPlanZone,
        DrawingSceneGraph,
    )
except ImportError:
    from ..core.cad.reader import UniversalCADReader, BlockHierarchyFlattener
    from ..core.cad.geometry import (
        clean_turkish_text,
        strip_revit_view_suffix,
        TextReconstructionEngine,
        GeometricTableExtractor,
    )
    from ..core.cad.classifier import MultiEvidenceClassifier
    from ..core.cad.frame_detector import SpatialZoneMapper
    from ..core.topology.circuit_resolver import LogicalCircuitResolver as HybridCircuitTopologyEngine
    from ..core.topology.route_builder import PhysicalRouteBuilder
    from ..core.model.entities import (
        TextToken,
        PlacedSymbol,
        LogicalCircuit,
        LinearRoute,
        ExtractedTable,
        CalloutGroup,
        SubPlanZone,
        DrawingSceneGraph,
    )

__all__ = [
    "UniversalCADReader",
    "BlockHierarchyFlattener",
    "clean_turkish_text",
    "strip_revit_view_suffix",
    "TextReconstructionEngine",
    "GeometricTableExtractor",
    "MultiEvidenceClassifier",
    "SpatialZoneMapper",
    "HybridCircuitTopologyEngine",
    "PhysicalRouteBuilder",
    "TextToken",
    "PlacedSymbol",
    "LogicalCircuit",
    "LinearRoute",
    "ExtractedTable",
    "CalloutGroup",
    "SubPlanZone",
    "DrawingSceneGraph",
]
