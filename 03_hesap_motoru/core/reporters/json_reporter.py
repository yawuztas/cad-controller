# -*- coding: utf-8 -*-
"""
JSON Rapor Dışa Aktarıcı (JSONReporter)
=======================================
"""

from __future__ import annotations
import re
import json
from pathlib import Path
from dataclasses import asdict
from typing import Dict

from ..model.audit import StationAuditReport
from .markdown_reporter import generate_markdown_report


def export_station_reports(report: StationAuditReport, output_dir: Path) -> Dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r"[^\w\s-]", "", report.station_name).strip()
    safe_name = re.sub(r"\s+", "_", safe_name)[:45].rstrip("_")
    prefix = f"{report.station_code}_{safe_name}"

    md_path = output_dir / f"{prefix}_DENETIM_RAPORU.md"
    json_path = output_dir / f"{prefix}_audit_report.json"

    md_content = generate_markdown_report(report)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, ensure_ascii=False, indent=2, default=str)

    return {"markdown": md_path, "json": json_path}
