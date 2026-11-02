"""
CloudeCAD — Yol 2: Gömülü OLE Nesneleri Analizi (OLE Parser)
============================================================
AutoCAD çizimine Excel'den yapıştırılmış OLE2FRAME (EMF/WMF)
bloklarını ayıklar, binary/EMF akışındaki metinleri ve tablo
hücrelerini çözer.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from core.models import SubPanelModel


class OlePowerParser:
    """Çizimdeki gömülü OLE2FRAME nesnelerini ayrıştıran motor."""

    def __init__(self, dxf_path: str):
        self.dxf_path = Path(dxf_path)
        self.ole_count = 0
        self.extracted_texts: List[str] = []
        self.logs: List[str] = []

    def parse(self) -> Tuple[int, Dict[str, Dict[str, Any]]]:
        """
        Dönüş: (ole_count, ole_panel_data_dict)
        """
        if not self.dxf_path.exists():
            return 0, {}

        try:
            with open(self.dxf_path, 'r', encoding='utf-8', errors='replace') as f:
                # Hızlı ön kontrol: Dosyada OLE2FRAME yoksa tam metin belleğe alma
                has_ole = False
                for line in f:
                    if 'OLE2FRAME' in line:
                        has_ole = True
                        break
                if not has_ole:
                    self.logs.append("OLE: Gömülü OLE2FRAME nesnesi bulunmadı.")
                    return 0, {}
                f.seek(0)
                content = f.read()
        except Exception as e:
            self.logs.append(f"OLE okuma hatası: {e}")
            return 0, {}

        matches = list(re.finditer(r'(?<!\w)OLE2FRAME', content))
        self.ole_count = len(matches)
        self.logs.append(f"OLE: Toplam {self.ole_count} adet OLE2FRAME nesnesi tespit edildi.")

        ole_data: Dict[str, Dict[str, Any]] = {}

        for idx, m in enumerate(matches):
            chunk = content[m.start():m.start() + 40000]
            hex_lines = re.findall(r'\n310\n([0-9A-Fa-f]+)', chunk)
            if not hex_lines:
                continue

            try:
                raw_bytes = bytes.fromhex(''.join(hex_lines))
                # EMF akışı içerisindeki ASCII/UTF-16 metinleri ara
                strings_found = self._extract_strings_from_binary(raw_bytes)
                if strings_found:
                    self.extracted_texts.extend(strings_found)
                    # Pano ve güç anahtarlarını tara
                    for s in strings_found:
                        m_dt = re.search(r'\b(DT-\d+|O-T|İŞ-T|IS-T|D-T)\b', s, re.IGNORECASE)
                        if m_dt:
                            pname = m_dt.group(1).upper()
                            if pname not in ole_data:
                                ole_data[pname] = {"name": pname, "raw_texts": []}
                            ole_data[pname]["raw_texts"].append(s)
            except Exception:
                pass

        return self.ole_count, ole_data

    def _extract_strings_from_binary(self, data: bytes, min_len: int = 3) -> List[str]:
        """Binary veri içerisindeki okunabilir metin parçalarını çeker."""
        # ASCII metinler
        ascii_matches = re.findall(rb'[\x20-\x7E]{' + str(min_len).encode() + rb',}', data)
        # UTF-16LE metinler
        utf16_matches = re.findall(rb'(?:[\x20-\x7E]\x00){' + str(min_len).encode() + rb',}', data)

        results = []
        for m in ascii_matches:
            try:
                s = m.decode('ascii').strip()
                if any(kw in s.lower() for kw in ['dt-', 'tablo', 'kurulu', 'talep', 'watt', 'kw', 'kablo', 'sigorta']):
                    results.append(s)
            except Exception:
                pass

        for m in utf16_matches:
            try:
                s = m.decode('utf-16le').strip()
                if any(kw in s.lower() for kw in ['dt-', 'tablo', 'kurulu', 'talep', 'watt', 'kw', 'kablo', 'sigorta']):
                    results.append(s)
            except Exception:
                pass

        return results
