# -*- coding: utf-8 -*-
"""
Geriye Dönük Uyumluluk Sarmalayıcısı (StationAuditEngine)
========================================================
Tüm denetim mantığı artık 'core' modüler paketine taşınmıştır.
Bu modül eski referansların sorunsuz çalışmasını sağlar.
"""

from __future__ import annotations
try:
    from core.engine import UnifiedAuditEngine as StationAuditEngine, KNOWN_METRO_STATIONS
    from core.model.audit import (
        ConfidenceLevel,
        AuditFinding,
        UncertaintyItem,
        ReconciliationItem,
        PanelLoadSummary,
        CircuitCalculation,
        WeakCurrentSubsystemAudit,
        GroundingAndTraySummary,
        StationAuditReport,
    )
    from core.reporters.markdown_reporter import generate_markdown_report
    from core.reporters.json_reporter import export_station_reports
except ImportError:
    from ..core.engine import UnifiedAuditEngine as StationAuditEngine, KNOWN_METRO_STATIONS
    from ..core.model.audit import (
        ConfidenceLevel,
        AuditFinding,
        UncertaintyItem,
        ReconciliationItem,
        PanelLoadSummary,
        CircuitCalculation,
        WeakCurrentSubsystemAudit,
        GroundingAndTraySummary,
        StationAuditReport,
    )
    from ..core.reporters.markdown_reporter import generate_markdown_report
    from ..core.reporters.json_reporter import export_station_reports

__all__ = [
    "StationAuditEngine",
    "KNOWN_METRO_STATIONS",
    "ConfidenceLevel",
    "AuditFinding",
    "UncertaintyItem",
    "ReconciliationItem",
    "PanelLoadSummary",
    "CircuitCalculation",
    "WeakCurrentSubsystemAudit",
    "GroundingAndTraySummary",
    "StationAuditReport",
    "generate_markdown_report",
    "export_station_reports",
]
